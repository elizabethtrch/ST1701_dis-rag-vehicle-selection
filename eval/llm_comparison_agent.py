"""
LLM Comparison Agent — evalúa y compara múltiples proveedores LLM
sobre la misma solicitud RAG y genera un reporte Markdown.

Uso:
    cd <raíz del proyecto>
    python eval/llm_comparison_agent.py [--output reporte.md] [--providers ollama,google,openai]

Requiere el venv del proyecto:
    source .venv/bin/activate
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

# Permite importar desde api/src sin instalar el paquete
sys.path.insert(0, str(Path(__file__).parent.parent / "api"))

from src.config import get_settings, _build_chroma_adapter, _build_embedding_provider, _build_neo4j_adapter, _build_observability
from src.core.domain.models import (
    Canal, Pedido, Prioridad, Producto,
    SolicitudRecomendacion, TipoVehiculo, Ubicacion, VehiculoDisponible,
)
from src.core.ports.interfaces import Fragmento, LLMProvider, ObservabilityPort, SCORE_KEYS
from src.core.services.recommendation_service import RecommendationService
from src.core.utils.prompt_builder import PromptBuilder
from src.core.utils.response_parser import ResponseParser, ParseError


# ── Catálogo de solicitudes de prueba ────────────────────────

_SOLICITUDES: list[SolicitudRecomendacion] = [
    # 1. Caso base: frutas perecederas, flota mixta
    SolicitudRecomendacion(
        pedido=Pedido("EVAL-001", date(2025, 7, 15), Prioridad.ALTA),
        productos=[Producto("Aguacate Hass", 1200, "kg"), Producto("Plátano hartón", 800, "kg")],
        origen=Ubicacion("Medellín", "Antioquia"),
        destino=Ubicacion("Bogotá", "Cundinamarca"),
        canal=Canal.MAYORISTA,
        flota_disponible=[
            VehiculoDisponible("VEH-01", TipoVehiculo.TERRESTRE, 3500, True, "ABC123"),
            VehiculoDisponible("VEH-02", TipoVehiculo.TERRESTRE, 5000, False, "XYZ789"),
        ],
    ),
    # 2. Sin refrigeración: tubérculos secos, carga pesada
    SolicitudRecomendacion(
        pedido=Pedido("EVAL-002", date(2025, 7, 16), Prioridad.MEDIA),
        productos=[Producto("Papa pastusa", 3000, "kg"), Producto("Yuca", 1500, "kg")],
        origen=Ubicacion("Tunja", "Boyacá"),
        destino=Ubicacion("Bogotá", "Cundinamarca"),
        canal=Canal.MINORISTA,
        flota_disponible=[
            VehiculoDisponible("VEH-03", TipoVehiculo.TERRESTRE, 6000, False, "DEF456"),
            VehiculoDisponible("VEH-04", TipoVehiculo.TERRESTRE, 3000, True, "GHI789"),
        ],
    ),
    # 3. Flores: alta perecibilidad, refrigeración crítica
    SolicitudRecomendacion(
        pedido=Pedido("EVAL-003", date(2025, 7, 17), Prioridad.ALTA),
        productos=[Producto("Rosas frescas", 500, "kg"), Producto("Claveles", 300, "kg")],
        origen=Ubicacion("Rionegro", "Antioquia"),
        destino=Ubicacion("Bogotá", "Cundinamarca"),
        canal=Canal.EXPORTACION,
        flota_disponible=[
            VehiculoDisponible("VEH-05", TipoVehiculo.TERRESTRE, 2000, True, "JKL012"),
            VehiculoDisponible("VEH-06", TipoVehiculo.TERRESTRE, 4000, False, "MNO345"),
        ],
    ),
    # 4. Café pergamino: sin refrigeración, exportación
    SolicitudRecomendacion(
        pedido=Pedido("EVAL-004", date(2025, 7, 18), Prioridad.MEDIA),
        productos=[Producto("Café pergamino seco", 2000, "kg")],
        origen=Ubicacion("Armenia", "Quindío"),
        destino=Ubicacion("Buenaventura", "Valle del Cauca"),
        canal=Canal.EXPORTACION,
        flota_disponible=[
            VehiculoDisponible("VEH-07", TipoVehiculo.TERRESTRE, 5000, False, "PQR678"),
            VehiculoDisponible("VEH-08", TipoVehiculo.TERRESTRE, 2500, False, "STU901"),
        ],
    ),
    # 5. Lácteos: refrigeración crítica, ruta corta
    SolicitudRecomendacion(
        pedido=Pedido("EVAL-005", date(2025, 7, 19), Prioridad.ALTA),
        productos=[Producto("Leche pasteurizada", 800, "kg"), Producto("Queso fresco", 400, "kg")],
        origen=Ubicacion("Manizales", "Caldas"),
        destino=Ubicacion("Pereira", "Risaralda"),
        canal=Canal.INSTITUCIONAL,
        flota_disponible=[
            VehiculoDisponible("VEH-09", TipoVehiculo.TERRESTRE, 1500, True, "VWX234"),
            VehiculoDisponible("VEH-10", TipoVehiculo.TERRESTRE, 3000, False, "YZA567"),
        ],
    ),
    # 6. Edge case: carga supera capacidad del vehículo refrigerado
    SolicitudRecomendacion(
        pedido=Pedido("EVAL-006", date(2025, 7, 20), Prioridad.ALTA),
        productos=[Producto("Mango Tommy", 2500, "kg"), Producto("Papaya", 1500, "kg")],
        origen=Ubicacion("Valledupar", "Cesar"),
        destino=Ubicacion("Barranquilla", "Atlántico"),
        canal=Canal.MAYORISTA,
        flota_disponible=[
            VehiculoDisponible("VEH-11", TipoVehiculo.TERRESTRE, 2000, True, "BCD890"),
            VehiculoDisponible("VEH-12", TipoVehiculo.TERRESTRE, 6000, False, "EFG123"),
        ],
    ),
    # 7. Edge case: no hay vehículo refrigerado en la flota
    SolicitudRecomendacion(
        pedido=Pedido("EVAL-007", date(2025, 7, 21), Prioridad.MEDIA),
        productos=[Producto("Fresa", 600, "kg"), Producto("Mora", 400, "kg")],
        origen=Ubicacion("Bogotá", "Cundinamarca"),
        destino=Ubicacion("Cali", "Valle del Cauca"),
        canal=Canal.MINORISTA,
        flota_disponible=[
            VehiculoDisponible("VEH-13", TipoVehiculo.TERRESTRE, 3000, False, "HIJ456"),
            VehiculoDisponible("VEH-14", TipoVehiculo.TERRESTRE, 5000, False, "KLM789"),
        ],
    ),
    # 8. Carga mixta: granos secos + perecederos
    SolicitudRecomendacion(
        pedido=Pedido("EVAL-008", date(2025, 7, 22), Prioridad.BAJA),
        productos=[Producto("Maíz amarillo", 2000, "kg"), Producto("Tomate chonto", 800, "kg")],
        origen=Ubicacion("Montería", "Córdoba"),
        destino=Ubicacion("Medellín", "Antioquia"),
        canal=Canal.MAYORISTA,
        flota_disponible=[
            VehiculoDisponible("VEH-15", TipoVehiculo.TERRESTRE, 4000, True, "NOP012"),
            VehiculoDisponible("VEH-16", TipoVehiculo.TERRESTRE, 4000, False, "QRS345"),
        ],
    ),
    # 9. Carga liviana de alto valor: hierbas aromáticas
    SolicitudRecomendacion(
        pedido=Pedido("EVAL-009", date(2025, 7, 23), Prioridad.ALTA),
        productos=[Producto("Albahaca fresca", 100, "kg"), Producto("Cilantro", 150, "kg")],
        origen=Ubicacion("Villa de Leyva", "Boyacá"),
        destino=Ubicacion("Bogotá", "Cundinamarca"),
        canal=Canal.INSTITUCIONAL,
        flota_disponible=[
            VehiculoDisponible("VEH-17", TipoVehiculo.TERRESTRE, 1000, True, "TUV678"),
            VehiculoDisponible("VEH-18", TipoVehiculo.TERRESTRE, 3000, False, "WXY901"),
        ],
    ),
    # 10. Ruta larga: plátano y yuca hacia costa
    SolicitudRecomendacion(
        pedido=Pedido("EVAL-010", date(2025, 7, 24), Prioridad.MEDIA),
        productos=[Producto("Plátano hartón", 3000, "kg"), Producto("Ñame", 2000, "kg")],
        origen=Ubicacion("Bucaramanga", "Santander"),
        destino=Ubicacion("Santa Marta", "Magdalena"),
        canal=Canal.MAYORISTA,
        flota_disponible=[
            VehiculoDisponible("VEH-19", TipoVehiculo.TERRESTRE, 6000, False, "ZAB234"),
            VehiculoDisponible("VEH-20", TipoVehiculo.TERRESTRE, 3000, True, "CDE567"),
        ],
    ),
]


def _solicitudes_prueba(count: int) -> list[SolicitudRecomendacion]:
    return _SOLICITUDES[:min(count, len(_SOLICITUDES))]


def _recuperar_contexto_rag(
    solicitud: SolicitudRecomendacion,
) -> tuple[list[Fragmento], dict]:
    """
    Recupera fragmentos de ChromaDB y contexto de Neo4j una única vez.
    El mismo resultado se reutiliza para todos los proveedores LLM,
    garantizando que la comparación sea sobre el mismo input RAG.
    """
    settings = get_settings()
    emb = _build_embedding_provider(settings)
    repo = _build_chroma_adapter(settings, emb)
    graph = _build_neo4j_adapter(settings)

    # Reutilizamos la lógica de recuperación del servicio sin invocar ningún LLM
    dummy_service = RecommendationService(
        knowledge_repo=repo,
        llm_provider=None,   # no se invoca en esta fase
        graph_repo=graph,
    )
    fragmentos, contexto_grafo = dummy_service.recuperar_contexto(solicitud)

    try:
        graph.close()
    except Exception:
        pass

    return fragmentos, contexto_grafo


# ── Resultados y evaluación ───────────────────────────────────

@dataclass
class ProviderResult:
    provider: str
    model: str
    system_prompt: str
    user_prompt: str
    raw_response: str
    parsed: dict | None
    tokens_in: int
    tokens_out: int
    latency_s: float
    error: str | None = None
    trace_id: str | None = None


@dataclass
class CriterioScore:
    puntaje: int        # 0–10
    justificacion: str


@dataclass
class EvaluationScore:
    provider: str
    model: str
    adherencia_schema: CriterioScore
    seleccion_vehiculo: CriterioScore
    calidad_justificacion: CriterioScore
    completitud_alternativas: CriterioScore
    veracidad: CriterioScore
    relevancia: CriterioScore
    precision_tecnica: CriterioScore
    idioma: CriterioScore
    latency_s: float

    @property
    def promedio(self) -> float:
        scores = [
            self.adherencia_schema.puntaje,
            self.seleccion_vehiculo.puntaje,
            self.calidad_justificacion.puntaje,
            self.completitud_alternativas.puntaje,
            self.veracidad.puntaje,
            self.relevancia.puntaje,
            self.precision_tecnica.puntaje,
            self.idioma.puntaje,
        ]
        return round(sum(scores) / len(scores), 2)


@dataclass
class CriterioAgregado:
    media: float
    desv: float
    minimo: int
    maximo: int


@dataclass
class AggregatedScore:
    provider: str
    model: str
    adherencia_schema: CriterioAgregado
    seleccion_vehiculo: CriterioAgregado
    calidad_justificacion: CriterioAgregado
    completitud_alternativas: CriterioAgregado
    veracidad: CriterioAgregado
    relevancia: CriterioAgregado
    precision_tecnica: CriterioAgregado
    idioma: CriterioAgregado
    latencia_media: float
    total_runs: int

    @property
    def promedio_global(self) -> float:
        medias = [
            self.adherencia_schema.media, self.seleccion_vehiculo.media,
            self.calidad_justificacion.media, self.completitud_alternativas.media,
            self.veracidad.media, self.relevancia.media,
            self.precision_tecnica.media, self.idioma.media,
        ]
        return round(sum(medias) / len(medias), 2)


def _agregar_scores(provider: str, model: str, scores: list[EvaluationScore]) -> AggregatedScore:
    import statistics

    def _agg(vals: list[int]) -> CriterioAgregado:
        return CriterioAgregado(
            media=round(statistics.mean(vals), 2),
            desv=round(statistics.stdev(vals) if len(vals) > 1 else 0.0, 2),
            minimo=min(vals),
            maximo=max(vals),
        )

    criterios = [
        "adherencia_schema", "seleccion_vehiculo", "calidad_justificacion",
        "completitud_alternativas", "veracidad", "relevancia", "precision_tecnica", "idioma",
    ]
    kwargs = {c: _agg([getattr(s, c).puntaje for s in scores]) for c in criterios}
    return AggregatedScore(
        provider=provider,
        model=model,
        latencia_media=round(statistics.mean(s.latency_s for s in scores), 2),
        total_runs=len(scores),
        **kwargs,
    )


# ── Ejecución del pool ────────────────────────────────────────

class LLMPool:
    def __init__(
        self,
        providers: list[tuple[str, LLMProvider]],
        observability: ObservabilityPort | None = None,
    ):
        self._providers = providers
        self._builder = PromptBuilder()
        self._parser = ResponseParser()
        self._obs = observability

    def run(
        self,
        runs: list[tuple[SolicitudRecomendacion, list[Fragmento], dict]],
    ) -> dict[str, list[ProviderResult]]:
        """
        Ejecuta todas las solicitudes contra todos los proveedores.
        Retorna dict[provider_name -> lista de ProviderResult, uno por solicitud].
        """
        evaluator = ResponseEvaluator()
        results: dict[str, list[ProviderResult]] = {name: [] for name, _ in self._providers}
        for i, (solicitud, fragmentos, contexto_grafo) in enumerate(runs, 1):
            print(f"  Solicitud {i}/{len(runs)}: {solicitud.pedido.identificador}")
            for name, provider in self._providers:
                result = self._query(name, provider, solicitud, fragmentos, contexto_grafo)
                status = f"✗ {result.error}" if result.error else f"✓ {result.latency_s:.1f}s"
                print(f"    {name}: {status}")
                if self._obs and result.trace_id and not result.error:
                    score = evaluator.evaluate(result, solicitud)
                    scores = {
                        "adherencia_schema": float(score.adherencia_schema.puntaje),
                        "seleccion_vehiculo": float(score.seleccion_vehiculo.puntaje),
                        "calidad_justificacion": float(score.calidad_justificacion.puntaje),
                        "completitud_alternativas": float(score.completitud_alternativas.puntaje),
                        "veracidad": float(score.veracidad.puntaje),
                        "relevancia": float(score.relevancia.puntaje),
                        "precision_tecnica": float(score.precision_tecnica.puntaje),
                        "idioma": float(score.idioma.puntaje),
                        "promedio": float(score.promedio),
                    }
                    assert set(scores) == set(SCORE_KEYS), (
                        f"Score keys no coinciden con SCORE_KEYS: {set(scores) ^ set(SCORE_KEYS)}"
                    )
                    self._obs.score_recommendation(
                        trace_id=result.trace_id,
                        scores=scores,
                        comments={
                            "adherencia_schema": score.adherencia_schema.justificacion,
                            "seleccion_vehiculo": score.seleccion_vehiculo.justificacion,
                            "calidad_justificacion": score.calidad_justificacion.justificacion,
                        },
                    )
                results[name].append(result)
        return results

    def _query(
        self,
        name: str,
        provider: LLMProvider,
        solicitud: SolicitudRecomendacion,
        fragmentos: list[Fragmento],
        contexto_grafo: dict,
    ) -> ProviderResult:
        strict = provider.strict_output
        system_prompt = self._builder.build_system_prompt(strict_mode=strict)
        user_prompt = self._builder.build_user_prompt(
            solicitud, fragmentos, contexto_grafo, strict_mode=strict
        )
        t0 = time.time()
        try:
            resp = provider.generate(system_prompt, user_prompt, max_tokens=1500)
            latency = time.time() - t0
            try:
                parsed = self._parser._extract_json(resp.texto)
            except (ParseError, Exception):
                parsed = None
            result = ProviderResult(
                provider=name,
                model=resp.modelo,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                raw_response=resp.texto,
                parsed=parsed,
                tokens_in=resp.tokens_entrada,
                tokens_out=resp.tokens_salida,
                latency_s=latency,
            )
            if self._obs:
                import uuid as _uuid
                eval_trace_id = str(_uuid.uuid4())
                vehiculo = (parsed or {}).get("vehiculo_id", "—")
                self._obs.trace_recommendation(
                    trace_id=eval_trace_id,
                    solicitud_id=solicitud.pedido.identificador,
                    proveedor=name,
                    modelo=resp.modelo,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    respuesta=resp.texto,
                    tokens_entrada=resp.tokens_entrada,
                    tokens_salida=resp.tokens_salida,
                    latencia_ms=int(latency * 1000),
                    vehiculo_seleccionado=vehiculo,
                    metadata={"eval_run": True, "peso_kg": solicitud.peso_total_kg},
                )
                result.trace_id = eval_trace_id
            return result
        except Exception as exc:
            return ProviderResult(
                provider=name,
                model=name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                raw_response="",
                parsed=None,
                tokens_in=0,
                tokens_out=0,
                latency_s=time.time() - t0,
                error=str(exc),
            )


# ── Evaluación ────────────────────────────────────────────────

@dataclass
class ExpectedAnswer:
    vehiculo_optimo: str                      # vehículo que debería seleccionarse
    vehiculos_aceptables: list[str]           # IDs aceptables (incluye optimo)
    motivo_rechazo: dict[str, list[str]]      # vehicle_id -> keywords esperados en el motivo
    keywords_justificacion: list[str]         # términos técnicos esperados en la justificación
    requiere_alerta: bool = False             # si debe incluir una alerta
    descripcion_caso: str = ""               # descripción del caso de prueba


_EXPECTED_ANSWERS: dict[str, ExpectedAnswer] = {
    "EVAL-001": ExpectedAnswer(
        vehiculo_optimo="VEH-01",
        vehiculos_aceptables=["VEH-01"],
        motivo_rechazo={"VEH-02": ["refriger", "cadena de frío", "sin refriger", "no refrigerado", "frío"]},
        keywords_justificacion=["refriger", "aguacate", "cadena de frío"],
        requiere_alerta=False,
        descripcion_caso="requiere refrigeración; VEH-01 correcto, VEH-02 descartado por no tener refrigeración",
    ),
    "EVAL-002": ExpectedAnswer(
        vehiculo_optimo="VEH-03",
        vehiculos_aceptables=["VEH-03"],
        motivo_rechazo={"VEH-04": ["capacidad", "insuficiente", "3000", "menor", "supera"]},
        keywords_justificacion=["capacidad", "papa", "tubérculo"],
        requiere_alerta=False,
        descripcion_caso="sin refrigeración; VEH-04 descartado por capacidad insuficiente (3000 < 4500 kg)",
    ),
    "EVAL-003": ExpectedAnswer(
        vehiculo_optimo="VEH-05",
        vehiculos_aceptables=["VEH-05"],
        motivo_rechazo={"VEH-06": ["refriger", "flores", "exportación", "perecible", "temperatura", "cadena de frío"]},
        keywords_justificacion=["refriger", "flores", "exportación", "perecible"],
        requiere_alerta=False,
        descripcion_caso="flores de exportación requieren frío; VEH-06 descartado por no refrigerado",
    ),
    "EVAL-004": ExpectedAnswer(
        vehiculo_optimo="VEH-08",
        vehiculos_aceptables=["VEH-07", "VEH-08"],
        motivo_rechazo={"VEH-07": ["sobredimensionado", "exceso", "mayor capacidad", "ineficiente", "5000"]},
        keywords_justificacion=["café", "exportación", "capacidad"],
        requiere_alerta=False,
        descripcion_caso="ambos vehículos sin refrigeración; VEH-08 óptimo por mejor ajuste de capacidad (2500 vs 5000 para 2000 kg)",
    ),
    "EVAL-005": ExpectedAnswer(
        vehiculo_optimo="VEH-09",
        vehiculos_aceptables=["VEH-09"],
        motivo_rechazo={"VEH-10": ["refriger", "lácteo", "leche", "queso", "cadena de frío", "perecedero"]},
        keywords_justificacion=["refriger", "lácteo", "leche", "queso"],
        requiere_alerta=False,
        descripcion_caso="lácteos requieren frío; VEH-10 descartado por no refrigerado",
    ),
    "EVAL-006": ExpectedAnswer(
        vehiculo_optimo="VEH-12",
        vehiculos_aceptables=["VEH-11", "VEH-12"],
        motivo_rechazo={
            "VEH-11": ["capacidad", "insuficiente", "2000", "supera", "menor"],
            "VEH-12": ["refriger", "sin refriger", "no refrigerado", "frío"],
        },
        keywords_justificacion=["capacidad", "refriger", "alerta", "advertencia"],
        requiere_alerta=True,
        descripcion_caso="edge case: ningún vehículo es perfecto; VEH-11 sin capacidad suficiente, VEH-12 sin frío; debe alertar",
    ),
    "EVAL-007": ExpectedAnswer(
        vehiculo_optimo="VEH-13",
        vehiculos_aceptables=["VEH-13", "VEH-14"],
        motivo_rechazo={"VEH-14": ["sobredimensionado", "exceso", "mayor", "5000"]},
        keywords_justificacion=["refriger", "fresa", "mora", "alerta"],
        requiere_alerta=True,
        descripcion_caso="edge case: ningún vehículo refrigerado; debe alertar sobre riesgo de las frutas sin frío",
    ),
    "EVAL-008": ExpectedAnswer(
        vehiculo_optimo="VEH-15",
        vehiculos_aceptables=["VEH-15"],
        motivo_rechazo={"VEH-16": ["refriger", "tomate", "perecedero", "temperatura", "frío", "deterioro"]},
        keywords_justificacion=["refriger", "tomate", "perecedero", "ruta"],
        requiere_alerta=False,
        descripcion_caso="carga mixta; VEH-15 correcto por refrigeración que protege tomate chonto en ruta larga",
    ),
    "EVAL-009": ExpectedAnswer(
        vehiculo_optimo="VEH-17",
        vehiculos_aceptables=["VEH-17"],
        motivo_rechazo={"VEH-18": ["refriger", "sobredimensionado", "hierbas", "perecedero", "aromáticas", "exceso"]},
        keywords_justificacion=["refriger", "hierbas", "perecedero", "aromáticas"],
        requiere_alerta=False,
        descripcion_caso="hierbas aromáticas muy perecederas; VEH-17 correcto (refrigerado, bien dimensionado), VEH-18 descartado",
    ),
    "EVAL-010": ExpectedAnswer(
        vehiculo_optimo="VEH-19",
        vehiculos_aceptables=["VEH-19"],
        motivo_rechazo={"VEH-20": ["capacidad", "insuficiente", "3000", "supera", "menor"]},
        keywords_justificacion=["capacidad", "plátano", "ñame"],
        requiere_alerta=False,
        descripcion_caso="sin refrigeración; VEH-20 descartado por capacidad insuficiente (3000 < 5000 kg)",
    ),
}

_CANONICAL_KEYS = {"vehiculo_id", "justificacion", "alternativas", "alertas"}
_SPANISH_WORDS = {"el", "la", "los", "las", "un", "una", "es", "son", "para", "que",
                  "con", "del", "por", "vehículo", "carga", "producto", "refrigerado"}


class ResponseEvaluator:

    def evaluate(self, result: ProviderResult, solicitud: SolicitudRecomendacion) -> EvaluationScore:
        d = result.parsed or {}

        return EvaluationScore(
            provider=result.provider,
            model=result.model,
            adherencia_schema=self._eval_schema(d, result.error),
            seleccion_vehiculo=self._eval_seleccion(d, solicitud),
            calidad_justificacion=self._eval_justificacion(d),
            completitud_alternativas=self._eval_completitud(d, solicitud),
            veracidad=self._eval_veracidad(d, solicitud),
            relevancia=self._eval_relevancia(d, solicitud),
            precision_tecnica=self._eval_precision(d, solicitud),
            idioma=self._eval_idioma(d),
            latency_s=result.latency_s,
        )

    # ── criterios ────────────────────────────────────────────

    def _eval_schema(self, d: dict, error: str | None) -> CriterioScore:
        if error:
            return CriterioScore(0, f"Error de ejecución: {error}")
        if not d:
            return CriterioScore(0, "No se obtuvo JSON parseable.")
        present = _CANONICAL_KEYS & set(d.keys())
        score = int(len(present) / len(_CANONICAL_KEYS) * 10)
        missing = _CANONICAL_KEYS - present
        just = (
            f"Campos presentes: {sorted(present)}. "
            + (f"Faltantes: {sorted(missing)}." if missing else "Schema canónico completo.")
        )
        return CriterioScore(score, just)

    def _eval_seleccion(self, d: dict, solicitud: SolicitudRecomendacion) -> CriterioScore:
        if not d:
            return CriterioScore(0, "Sin respuesta.")
        vid = self._get_vehiculo_id(d)
        flota = {v.id: v for v in solicitud.flota_disponible}
        if vid not in flota:
            return CriterioScore(2, f"ID '{vid}' no pertenece a la flota disponible.")

        expected = _EXPECTED_ANSWERS.get(solicitud.pedido.identificador)
        v = flota[vid]

        # Restricciones duras independientes del ground truth
        if v.capacidad_kg < solicitud.peso_total_kg:
            motivo = f"{vid} con capacidad {v.capacidad_kg:.0f} kg insuficiente para {solicitud.peso_total_kg:.0f} kg."
            if expected and vid in expected.vehiculos_aceptables:
                return CriterioScore(5, motivo + " (aceptable dado edge case sin vehículo ideal)")
            return CriterioScore(4, motivo)

        if not expected:
            # Fallback heurístico si no hay ground truth definido
            if solicitud.requiere_refrigeracion and not v.refrigerado:
                return CriterioScore(3, f"{vid} seleccionado pero no tiene refrigeración requerida.")
            return CriterioScore(7, f"{vid} cumple requisitos básicos (sin ground truth definido).")

        # Evaluación contra el ground truth
        if vid == expected.vehiculo_optimo:
            return CriterioScore(
                10,
                f"{vid} es el vehículo óptimo esperado. Caso: {expected.descripcion_caso}",
            )
        if vid in expected.vehiculos_aceptables:
            return CriterioScore(
                8,
                f"{vid} es aceptable pero no el óptimo ({expected.vehiculo_optimo}). Caso: {expected.descripcion_caso}",
            )
        # Vehículo incorrecto — determinar el tipo de error
        if solicitud.requiere_refrigeracion and not v.refrigerado:
            return CriterioScore(
                3,
                f"{vid} no tiene refrigeración. Se esperaba {expected.vehiculo_optimo}. {expected.descripcion_caso}",
            )
        return CriterioScore(
            4,
            f"{vid} no es el vehículo esperado ({expected.vehiculo_optimo}). {expected.descripcion_caso}",
        )

    def _eval_justificacion(self, d: dict) -> CriterioScore:
        if not d:
            return CriterioScore(0, "Sin respuesta.")
        just = d.get("justificacion") or d.get("justification") or ""
        if not just or just == "Sin justificación disponible.":
            return CriterioScore(0, "Justificación ausente o placeholder.")
        words = just.split()
        if len(words) < 20:
            return CriterioScore(3, f"Justificación muy breve ({len(words)} palabras).")
        technical = any(t in just.lower() for t in
                        ["refriger", "capacidad", "kg", "perecedero", "normativa", "resolución", "temperatura"])
        if len(words) >= 40 and technical:
            return CriterioScore(10, f"Justificación completa ({len(words)} palabras) con términos técnicos.")
        if technical:
            return CriterioScore(7, f"Justificación con contenido técnico ({len(words)} palabras).")
        return CriterioScore(5, f"Justificación presente ({len(words)} palabras) pero sin términos técnicos clave.")

    def _eval_completitud(self, d: dict, solicitud: SolicitudRecomendacion) -> CriterioScore:
        if not d:
            return CriterioScore(0, "Sin respuesta.")
        alertas = d.get("alertas") or []
        alternativas_con_motivo = self._get_alternativas_con_motivo(d)
        expected = _EXPECTED_ANSWERS.get(solicitud.pedido.identificador)
        n_esperadas = len(solicitud.flota_disponible) - 1

        # Parte 1 — Presencia de alternativas (0–5 pts)
        n_presentes = len(alternativas_con_motivo)
        if n_presentes == 0:
            presencia_pts = 0
            presencia_desc = f"Sin alternativas. Se esperaban {n_esperadas}."
        elif n_presentes < n_esperadas:
            presencia_pts = 2
            presencia_desc = f"{n_presentes}/{n_esperadas} alternativas presentes."
        else:
            presencia_pts = 5
            presencia_desc = f"Todas las alternativas presentes ({n_presentes})."

        # Parte 2 — Calidad de razones de descarte (0–5 pts)
        razon_pts = 0
        razon_desc = ""
        if expected and expected.motivo_rechazo:
            correctas = 0
            total_esperadas = len(expected.motivo_rechazo)
            for veh_id, keywords in expected.motivo_rechazo.items():
                motivo_texto = alternativas_con_motivo.get(veh_id, "").lower()
                if any(kw.lower() in motivo_texto for kw in keywords):
                    correctas += 1
            if total_esperadas > 0:
                razon_pts = round((correctas / total_esperadas) * 5)
            if correctas == total_esperadas:
                razon_desc = f"Razones de descarte correctas para todos los vehículos descartados."
            elif correctas > 0:
                razon_desc = f"Razón correcta para {correctas}/{total_esperadas} vehículos descartados."
            else:
                razon_desc = f"Ninguna alternativa menciona el motivo correcto de descarte."
        elif n_presentes > 0:
            razon_pts = 3  # hay alternativas pero sin ground truth para verificar
            razon_desc = "Alternativas presentes (razón no verificable sin ground truth)."

        # Bonus por alertas en casos que las requieren
        alerta_pts = 0
        if expected and expected.requiere_alerta:
            if alertas:
                alerta_pts = 0  # ya incluido en los 5 pts de razon
                razon_desc += " Alerta presente (requerida)."
            else:
                razon_pts = max(0, razon_pts - 2)  # penalización por omitir alerta crítica
                razon_desc += " ¡Falta alerta requerida por el caso!"

        total = min(10, presencia_pts + razon_pts)
        return CriterioScore(total, f"{presencia_desc} {razon_desc}".strip())

    def _eval_veracidad(self, d: dict, solicitud: SolicitudRecomendacion) -> CriterioScore:
        if not d:
            return CriterioScore(0, "Sin respuesta.")
        just = (d.get("justificacion") or "").lower()
        productos = [p.nombre.lower() for p in solicitud.productos]
        menciona_producto = any(p.split()[0] in just for p in productos)
        peso_correcto = str(int(solicitud.peso_total_kg)) in just or str(solicitud.peso_total_kg) in just
        ruta = solicitud.origen.ciudad.lower() in just or solicitud.destino.ciudad.lower() in just
        score = sum([menciona_producto * 3, peso_correcto * 4, ruta * 3])
        detalles = []
        if menciona_producto:
            detalles.append("menciona producto")
        if peso_correcto:
            detalles.append("menciona peso correcto")
        if ruta:
            detalles.append("menciona ciudades de la ruta")
        return CriterioScore(
            min(score, 10),
            ", ".join(detalles) if detalles else "No se verificaron datos de la solicitud en la justificación."
        )

    def _eval_relevancia(self, d: dict, solicitud: SolicitudRecomendacion) -> CriterioScore:
        if not d:
            return CriterioScore(0, "Sin respuesta.")
        vid = self._get_vehiculo_id(d)
        flota_ids = [v.id for v in solicitud.flota_disponible]
        if vid not in flota_ids:
            return CriterioScore(2, "El vehículo seleccionado no pertenece a la flota de la solicitud.")
        just = (d.get("justificacion") or "").lower()
        expected = _EXPECTED_ANSWERS.get(solicitud.pedido.identificador)
        if expected:
            hits = sum(1 for kw in expected.keywords_justificacion if kw.lower() in just)
            total = len(expected.keywords_justificacion)
            score = round((hits / total) * 10) if total > 0 else 5
            return CriterioScore(
                min(score, 10),
                f"Justificación menciona {hits}/{total} términos clave esperados: {expected.keywords_justificacion}",
            )
        # fallback sin ground truth
        refrig_mencionada = any(t in just for t in ["refrig", "frío", "frio", "temperatura"])
        if solicitud.requiere_refrigeracion and refrig_mencionada:
            return CriterioScore(10, "Aborda explícitamente el requisito de refrigeración.")
        if solicitud.requiere_refrigeracion:
            return CriterioScore(5, "No aborda el requisito de refrigeración en la justificación.")
        return CriterioScore(8, "Respuesta relevante a la solicitud.")

    def _eval_precision(self, d: dict, solicitud: SolicitudRecomendacion) -> CriterioScore:
        if not d:
            return CriterioScore(0, "Sin respuesta.")
        just = (d.get("justificacion") or "").lower()
        flota = {v.id: v for v in solicitud.flota_disponible}
        vid = self._get_vehiculo_id(d)
        v = flota.get(vid)
        if not v:
            return CriterioScore(2, "Vehículo seleccionado no identificable.")
        cap_str = str(int(v.capacidad_kg))
        menciona_cap = cap_str in just or f"{v.capacidad_kg}" in just
        menciona_normativa = any(t in just for t in ["resolución", "resolucion", "normativa", "invima", "decreto"])
        score = 4 + (menciona_cap * 3) + (menciona_normativa * 3)
        detalles = []
        if menciona_cap:
            detalles.append(f"menciona capacidad {cap_str} kg")
        if menciona_normativa:
            detalles.append("referencia normativa")
        return CriterioScore(
            min(score, 10),
            ", ".join(detalles) if detalles else "Sin datos técnicos precisos en la justificación."
        )

    def _eval_idioma(self, d: dict) -> CriterioScore:
        if not d:
            return CriterioScore(0, "Sin respuesta.")
        just = (d.get("justificacion") or "").lower()
        if not just:
            return CriterioScore(0, "Sin justificación para evaluar idioma.")
        words = set(just.split())
        spanish_hits = len(words & _SPANISH_WORDS)
        if spanish_hits >= 4:
            return CriterioScore(10, f"Respuesta en español ({spanish_hits} palabras clave detectadas).")
        if spanish_hits >= 2:
            return CriterioScore(6, f"Respuesta parcialmente en español ({spanish_hits} palabras clave).")
        return CriterioScore(2, "Respuesta posiblemente en inglés u otro idioma.")

    # ── helpers ──────────────────────────────────────────────

    def _get_vehiculo_id(self, d: dict) -> str:
        nested = d.get("selected_vehicle") or {}
        return (
            d.get("vehiculo_id") or d.get("vehicle_id")
            or nested.get("id") or nested.get("vehicle_id") or ""
        )

    def _get_alternativas(self, d: dict) -> list:
        nested = d.get("selected_vehicle") or {}
        return (
            d.get("alternativas") or d.get("alternatives")
            or nested.get("alternative_vehicles") or []
        )

    def _get_alternativas_con_motivo(self, d: dict) -> dict[str, str]:
        """Retorna dict[vehicle_id -> motivo_texto] de las alternativas en la respuesta."""
        alts = self._get_alternativas(d)
        result: dict[str, str] = {}
        for alt in alts:
            if isinstance(alt, dict):
                vid = (alt.get("id") or alt.get("vehiculo_id") or alt.get("vehicle_id") or "")
                motivo = ""
                for k, v in alt.items():
                    if k not in {"id", "vehiculo_id", "vehicle_id"} and isinstance(v, str):
                        motivo = v
                        break
                if vid:
                    result[vid] = motivo
            elif isinstance(alt, str):
                result[alt] = ""
        return result


# ── Agente de análisis (LLM árbitro) ─────────────────────────

@dataclass
class AnalysisResult:
    comparacion_cualitativa: str
    valoracion_justificacion: str
    analisis_librerias: str
    analisis_herramientas: str


_SKILL_PATH = Path(__file__).parent / "skills" / "llm-evaluator" / "SKILL.md"
_EVAL_DIR = Path(__file__).parent.parent


class AnalysisAgent:
    """
    Usa Claude Code CLI para generar el análisis cualitativo del reporte.
    Sigue el mismo patrón que el knowledge_base_agent del kb-generator:
    invoca `claude --print` vía subprocess con el skill como guía.
    """

    def analizar(
        self,
        results: list[ProviderResult],
        aggregated: list[AggregatedScore],
        solicitud: SolicitudRecomendacion,
        fragmentos: list[Fragmento],
    ) -> AnalysisResult:
        contexto = self._construir_contexto(results, aggregated, solicitud, fragmentos)
        skill = _SKILL_PATH.read_text(encoding="utf-8") if _SKILL_PATH.exists() else ""
        print("  → Invocando Claude Code CLI...", flush=True)
        return AnalysisResult(
            comparacion_cualitativa=self._invocar_claude("3.1", contexto, skill),
            valoracion_justificacion=self._invocar_claude("3.2", contexto, skill),
            analisis_librerias=self._invocar_claude("4.1", contexto, skill),
            analisis_herramientas=self._invocar_claude("4.2", contexto, skill),
        )

    def analizar_desde_reporte(self, reporte_md: str) -> AnalysisResult:
        """Genera el análisis cualitativo a partir del contenido de un reporte Markdown previo."""
        skill = _SKILL_PATH.read_text(encoding="utf-8") if _SKILL_PATH.exists() else ""
        print("  → Invocando Claude Code CLI desde reporte Markdown...", flush=True)
        return AnalysisResult(
            comparacion_cualitativa=self._invocar_claude("3.1", reporte_md, skill),
            valoracion_justificacion=self._invocar_claude("3.2", reporte_md, skill),
            analisis_librerias=self._invocar_claude("4.1", reporte_md, skill),
            analisis_herramientas=self._invocar_claude("4.2", reporte_md, skill),
        )

    def _invocar_claude(self, seccion: str, contexto: str, skill: str) -> str:
        print(f"    → Sección {seccion}...", end=" ", flush=True)
        prompt = (
            f"Eres un evaluador experto en sistemas RAG. Sigue las instrucciones del skill "
            f"para generar la sección {seccion} del informe de comparación de LLMs.\n\n"
            f"## SKILL\n\n{skill}\n\n"
            f"## DATOS DE LA EVALUACIÓN\n\n{contexto}\n\n"
            f"## TAREA\n\n"
            f"Genera únicamente el contenido de la sección {seccion} según el skill. "
            f"Incluye las tablas Markdown requeridas. "
            f"Responde en español. Sin encabezados de nivel 1 o 2."
        )
        try:
            env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
            resultado = subprocess.run(
                ["claude", "--print", "-"],
                input=prompt,
                cwd=str(_EVAL_DIR),
                capture_output=True,
                text=True,
                timeout=300,
                env=env,
            )
            if resultado.returncode == 0 and resultado.stdout.strip():
                print("✓")
                return resultado.stdout.strip()
            print(f"✗ (returncode={resultado.returncode})")
            if resultado.stdout:
                print(f"      stdout: {resultado.stdout[:200]}")
            if resultado.stderr:
                print(f"      stderr: {resultado.stderr[:400]}")
            diag = resultado.stderr or resultado.stdout or "sin salida"
            return f"*(Error en sección {seccion} [rc={resultado.returncode}]: {diag[:300]})*"
        except FileNotFoundError:
            print("✗ (claude no encontrado)")
            return (
                "*(Claude Code CLI no encontrado. "
                "Instala con: npm install -g @anthropic-ai/claude-code)*"
            )
        except subprocess.TimeoutExpired:
            print("✗ (timeout)")
            return f"*(Timeout al generar sección {seccion})*"

    def _construir_contexto(
        self,
        results: list[ProviderResult],
        aggregated: list[AggregatedScore],
        solicitud: SolicitudRecomendacion,
        fragmentos: list[Fragmento],
    ) -> str:
        partes = [
            "## Solicitud de muestra",
            f"Pedido: {solicitud.pedido.identificador} | "
            f"Ruta: {solicitud.origen.ciudad}→{solicitud.destino.ciudad} | "
            f"Peso: {solicitud.peso_total_kg:.0f} kg | "
            f"Refrigeración requerida: {'Sí' if solicitud.requiere_refrigeracion else 'No'}",
            "## Fragmentos RAG recuperados",
            *[f"- [{f.categoria}|score={f.score:.2f}] {f.contenido[:200]}" for f in fragmentos],
            "\n## Respuesta de muestra por proveedor (primera solicitud)",
        ]
        for r in results:
            agg = next((a for a in aggregated if a.provider == r.provider), None)
            partes.append(f"\n### {r.provider} — {r.model}")
            if r.error:
                partes.append(f"ERROR: {r.error}")
            else:
                partes.append(f"Respuesta:\n```\n{r.raw_response[:1200]}\n```")
            if agg:
                partes.append(
                    f"Puntajes agregados ({agg.total_runs} runs): "
                    f"schema={agg.adherencia_schema.media} "
                    f"selección={agg.seleccion_vehiculo.media} "
                    f"justificación={agg.calidad_justificacion.media} "
                    f"completitud_alternativas={agg.completitud_alternativas.media} "
                    f"veracidad={agg.veracidad.media} "
                    f"relevancia={agg.relevancia.media} "
                    f"precisión={agg.precision_tecnica.media} "
                    f"idioma={agg.idioma.media} "
                    f"promedio_global={agg.promedio_global}"
                )
        return "\n".join(partes)



# ── Generación del reporte ────────────────────────────────────

class ReportGenerator:

    _CRITERIOS_DESC = {
        "adherencia_schema": (
            "Adherencia al Schema",
            "Verifica que la respuesta JSON contenga exactamente los 4 campos canónicos "
            "definidos en el contrato de la API: `vehiculo_id`, `justificacion`, `alternativas` y `alertas`. "
            "Un schema correcto garantiza que el sistema pueda parsear la respuesta sin fallbacks."
        ),
        "seleccion_vehiculo": (
            "Selección del Vehículo",
            "Evalúa si el vehículo elegido es técnicamente óptimo considerando dos restricciones duras: "
            "(1) la capacidad debe cubrir el peso total de la carga, "
            "(2) si la carga requiere refrigeración, el vehículo debe tenerla. "
            "Puntaje máximo solo si se selecciona el vehículo que cumple ambas restricciones."
        ),
        "calidad_justificacion": (
            "Calidad de Justificación",
            "Mide la extensión y profundidad técnica de la justificación. "
            "Se evalúa si menciona términos técnicos del dominio (refrigeración, capacidad, normativa, temperatura) "
            "y si supera un umbral mínimo de palabras para considerarse una explicación útil."
        ),
        "completitud_alternativas": (
            "Completitud de la Respuesta",
            "Verifica que se hayan listado todos los vehículos descartados en el campo `alternativas` "
            "y que se hayan generado alertas cuando corresponde. "
            "Una respuesta completa permite al usuario entender todas las opciones evaluadas."
        ),
        "veracidad": (
            "Veracidad",
            "Contrasta los datos mencionados en la justificación contra los datos reales de la solicitud "
            "(nombres de productos, peso total, ciudades de la ruta). "
            "Penaliza respuestas que inventen datos o ignoren los provistos en el contexto."
        ),
        "relevancia": (
            "Relevancia",
            "Evalúa si la respuesta aborda directamente los requisitos específicos del pedido: "
            "que el vehículo pertenezca a la flota disponible y que la justificación haga referencia "
            "a las restricciones más importantes (como la necesidad de refrigeración)."
        ),
        "precision_tecnica": (
            "Precisión Técnica",
            "Mide si la respuesta incluye datos técnicos verificables: "
            "capacidad exacta del vehículo seleccionado y referencias a normativa colombiana aplicable "
            "(Resolución 2674, Decreto 3075, etc.). Diferencia respuestas genéricas de respuestas especializadas."
        ),
        "idioma": (
            "Idioma",
            "Verifica que la respuesta esté redactada en español, idioma requerido para el contexto "
            "de logística agrícola colombiana. Una respuesta en inglés reduce la usabilidad del sistema "
            "para los operadores logísticos del cliente."
        ),
    }

    def generate(
        self,
        all_results: dict[str, list[ProviderResult]],
        all_scores: dict[str, list[EvaluationScore]],
        aggregated: list[AggregatedScore],
        solicitudes: list[SolicitudRecomendacion],
        analysis: AnalysisResult | None = None,
    ) -> str:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        sections = [
            self._header(ts),
            self._seccion_solicitudes(solicitudes),
            "## 3. Implementación de la Interacción con cada LLM",
            self._seccion_comparacion(all_results, analysis),
            self._seccion_valoracion(all_scores, aggregated, analysis),
            "## 4. Análisis de Resultados y Conclusiones",
            self._seccion_librerias(all_results, analysis),
            self._seccion_herramientas(all_results, aggregated, analysis),
        ]
        return "\n\n".join(sections)

    # ── secciones ────────────────────────────────────────────

    def _header(self, ts: str) -> str:
        return (
            f"# Comparación de LLMs — RAG Selección de Vehículo\n\n"
            f"**Generado:** {ts}  \n"
            f"**Proyecto:** ST1701 — Diseño RAG para Selección de Vehículo en Logística Agrícola  \n"
            f"**Equipo:** Edward Rayo, Elizabeth Toro, Santiago Cardona"
        )

    def _seccion_solicitudes(self, solicitudes: list[SolicitudRecomendacion]) -> str:
        rows = ["## Solicitudes de Prueba\n",
                f"Total: **{len(solicitudes)}** solicitudes evaluadas.\n",
                "| ID | Ruta | Productos | Peso (kg) | Refrigeración | Flota |",
                "|---|---|---|---|---|---|"]
        for s in solicitudes:
            prods = ", ".join(p.nombre for p in s.productos)
            flota = " / ".join(
                f"{v.id}({'❄' if v.refrigerado else '○'},{v.capacidad_kg}kg)"
                for v in s.flota_disponible
            )
            rows.append(
                f"| `{s.pedido.identificador}` "
                f"| {s.origen.ciudad}→{s.destino.ciudad} "
                f"| {prods} "
                f"| {s.peso_total_kg:.0f} "
                f"| {'Sí' if s.requiere_refrigeracion else 'No'} "
                f"| {flota} |"
            )
        return "\n".join(rows)

    def _seccion_comparacion(self, all_results: dict[str, list[ProviderResult]], analysis: AnalysisResult | None = None) -> str:
        parts = ["### 3.1 Comparación de Resultados con cada LLM\n"]
        if analysis:
            parts.append(analysis.comparacion_cualitativa + "\n")
            parts.append("---\n\n#### Evidencia — Prompts y respuestas por proveedor\n")
        for provider, results in all_results.items():
            parts.append(f"#### {provider}\n")
            for r in results:
                parts.append(f"##### Solicitud `{r.provider}` — {r.model} ({r.latency_s:.1f}s)\n")
                parts.append("**System Prompt:**\n")
                parts.append(f"```\n{r.system_prompt[:800]}{'…' if len(r.system_prompt) > 800 else ''}\n```\n")
                parts.append("**User Prompt:**\n")
                parts.append(f"```\n{r.user_prompt[:800]}{'…' if len(r.user_prompt) > 800 else ''}\n```\n")
                if r.error:
                    parts.append(f"**Error:** `{r.error}`\n")
                else:
                    raw = r.raw_response[:2000] + ("…[truncado]" if len(r.raw_response) > 2000 else "")
                    parts.append(f"**Respuesta cruda:**\n```json\n{raw}\n```\n")
                parts.append("---\n")
        return "\n".join(parts)

    def _seccion_valoracion(self, all_scores: dict[str, list[EvaluationScore]], aggregated: list[AggregatedScore], analysis: AnalysisResult | None = None) -> str:
        parts = ["### 3.2 Valoración de los LLM\n"]

        parts.append("#### Criterios de Evaluación\n")
        for key, (nombre, desc) in self._CRITERIOS_DESC.items():
            parts.append(f"**{nombre}:** {desc}\n")

        parts.append("\n#### Tabla Agregada (media ± desv. estándar sobre todas las solicitudes)\n")
        proveedores = [a.provider for a in aggregated]
        header = "| Criterio | " + " | ".join(proveedores) + " |"
        sep = "|---|" + "|".join(["---"] * len(proveedores)) + "|"
        parts.extend([header, sep])

        for key, (nombre, _) in self._CRITERIOS_DESC.items():
            row = f"| **{nombre}** |"
            for a in aggregated:
                c: CriterioAgregado = getattr(a, key)
                row += f" {c.media} ± {c.desv} |"
            parts.append(row)

        row_lat = "| **Latencia media** |"
        for a in aggregated:
            row_lat += f" {a.latencia_media}s |"
        parts.append(row_lat)

        row_avg = "| **Promedio global** |"
        for a in aggregated:
            row_avg += f" **{a.promedio_global}/10** |"
        parts.append(row_avg)

        if analysis:
            parts.append("\n#### Análisis Cualitativo de la Valoración\n")
            parts.append(analysis.valoracion_justificacion)

        return "\n".join(parts)

    def _seccion_librerias(self, all_results: dict[str, list[ProviderResult]], analysis: AnalysisResult | None = None) -> str:
        if analysis:
            return f"### 4.1 Consideraciones de las Librerías y Frameworks\n\n{analysis.analisis_librerias}"
        providers_usados = list(all_results.keys())
        return (
            "### 4.1 Consideraciones de las Librerías y Frameworks\n\n"
            "#### Anthropic SDK (`anthropic`)\n"
            "Separación nativa de roles system/user. Fácil integración.\n\n"
            "#### OpenAI SDK (`openai`)\n"
            "Estándar de facto en la industria con `messages[]`.\n\n"
            "#### Google Generative AI (`google-generativeai`)\n"
            "Concatenación de prompts como texto plano — sin separación de roles.\n\n"
            "#### Ollama (HTTP nativo)\n"
            "`/api/chat` con `format: json` fue clave para respuestas parseables.\n\n"
            f"**Proveedores ejecutados:** {', '.join(providers_usados) or 'ninguno'}"
        )

    def _seccion_herramientas(self, all_results: dict[str, list[ProviderResult]], aggregated: list[AggregatedScore], analysis: AnalysisResult | None = None) -> str:
        if analysis:
            return f"### 4.2 Análisis de las Herramientas\n\n{analysis.analisis_herramientas}"
        mejor = max(aggregated, key=lambda a: a.promedio_global) if aggregated else None
        peor = min(aggregated, key=lambda a: a.promedio_global) if aggregated else None
        return (
            "### 4.2 Análisis de las Herramientas\n\n"
            "#### ChromaDB\nRecuperación semántica efectiva para el dominio agrícola.\n\n"
            "#### Neo4j\nContexto estructurado de corredores y normativa.\n\n"
            "#### Ollama\n`format: json` y `/api/chat` fueron determinantes.\n\n"
            + (
                f"Mejor: **{mejor.provider}** ({mejor.promedio_global}/10). "
                f"Menor puntaje: **{peor.provider}** ({peor.promedio_global}/10)."
                if mejor and peor and mejor.provider != peor.provider else ""
            )
        )


# ── Construcción de proveedores ───────────────────────────────

def _build_providers(selected: list[str]) -> list[tuple[str, LLMProvider]]:
    providers = []

    if "ollama" in selected:
        try:
            from src.adapters.output.llm.ollama_adapter import OllamaAdapter
            model = os.getenv("OLLAMA_MODEL", "qwen2.5:3b-instruct-q4_K_M")
            url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            providers.append(("Ollama", OllamaAdapter(
                base_url=url, model=model,
                temperature=float(os.getenv("OLLAMA_TEMPERATURE", "0.2")),
                top_p=float(os.getenv("OLLAMA_TOP_P", "0.9")),
                top_k=int(os.getenv("OLLAMA_TOP_K", "40")),
                repeat_penalty=float(os.getenv("OLLAMA_REPEAT_PENALTY", "1.1")),
            )))
            print(f"  ✓ Ollama ({model})")
        except Exception as e:
            print(f"  ✗ Ollama no disponible: {e}")

    if "google" in selected:
        try:
            from src.adapters.output.llm.google_adapter import GoogleAdapter
            key = os.getenv("GOOGLE_API_KEY", "")
            model = os.getenv("GOOGLE_MODEL", "gemini-2.0-flash-lite")
            if not key:
                print("  ✗ Google: GOOGLE_API_KEY no configurada")
            else:
                providers.append(("Google", GoogleAdapter(api_key=key, model=model)))
                print(f"  ✓ Google ({model})")
        except Exception as e:
            print(f"  ✗ Google no disponible: {e}")

    if "openai" in selected:
        try:
            from src.adapters.output.llm.openai_adapter import OpenAIAdapter
            key = os.getenv("OPENAI_API_KEY", "")
            model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            if not key:
                print("  ✗ OpenAI: OPENAI_API_KEY no configurada")
            else:
                providers.append(("OpenAI", OpenAIAdapter(api_key=key, model=model)))
                print(f"  ✓ OpenAI ({model})")
        except Exception as e:
            print(f"  ✗ OpenAI no disponible: {e}")

    if "anthropic" in selected:
        try:
            from src.adapters.output.llm.anthropic_adapter import AnthropicAdapter
            key = os.getenv("ANTHROPIC_API_KEY", "")
            model = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
            if not key:
                print("  ✗ Anthropic: ANTHROPIC_API_KEY no configurada")
            else:
                providers.append(("Anthropic", AnthropicAdapter(api_key=key, model=model)))
                print(f"  ✓ Anthropic ({model})")
        except Exception as e:
            print(f"  ✗ Anthropic no disponible: {e}")

    return providers


# ── Persistencia de resultados ────────────────────────────────

def _guardar_datos(
    path: Path,
    all_results: dict[str, list[ProviderResult]],
    all_scores: dict[str, list[EvaluationScore]],
    aggregated: list[AggregatedScore],
    solicitudes: list[SolicitudRecomendacion],
) -> None:
    from dataclasses import asdict
    data = {
        "solicitudes": [
            {
                "id": s.pedido.identificador,
                "origen": s.origen.ciudad,
                "destino": s.destino.ciudad,
                "peso_total_kg": s.peso_total_kg,
                "requiere_refrigeracion": s.requiere_refrigeracion,
                "productos": [{"nombre": p.nombre, "cantidad": p.cantidad, "unidad": p.unidad} for p in s.productos],
                "flota": [{"id": v.id, "capacidad_kg": v.capacidad_kg, "refrigerado": v.refrigerado} for v in s.flota_disponible],
            }
            for s in solicitudes
        ],
        "results": {
            provider: [
                {
                    "provider": r.provider, "model": r.model,
                    "raw_response": r.raw_response, "parsed": r.parsed,
                    "tokens_in": r.tokens_in, "tokens_out": r.tokens_out,
                    "latency_s": r.latency_s, "error": r.error,
                    "system_prompt": r.system_prompt, "user_prompt": r.user_prompt,
                }
                for r in results
            ]
            for provider, results in all_results.items()
        },
        "scores": {
            provider: [
                {
                    "provider": s.provider, "model": s.model, "latency_s": s.latency_s,
                    **{
                        k: {"puntaje": getattr(s, k).puntaje, "justificacion": getattr(s, k).justificacion}
                        for k in ["adherencia_schema", "seleccion_vehiculo", "calidad_justificacion",
                                  "completitud_alternativas", "veracidad", "relevancia", "precision_tecnica", "idioma"]
                    },
                }
                for s in scores
            ]
            for provider, scores in all_scores.items()
        },
        "aggregated": [
            {
                "provider": a.provider, "model": a.model,
                "latencia_media": a.latencia_media, "total_runs": a.total_runs,
                **{
                    k: {"media": getattr(a, k).media, "desv": getattr(a, k).desv,
                        "minimo": getattr(a, k).minimo, "maximo": getattr(a, k).maximo}
                    for k in ["adherencia_schema", "seleccion_vehiculo", "calidad_justificacion",
                              "completitud_alternativas", "veracidad", "relevancia", "precision_tecnica", "idioma"]
                },
            }
            for a in aggregated
        ],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _cargar_datos(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))

    all_results = {
        provider: [
            ProviderResult(
                provider=r["provider"], model=r["model"],
                system_prompt=r.get("system_prompt", ""),
                user_prompt=r.get("user_prompt", ""),
                raw_response=r["raw_response"], parsed=r["parsed"],
                tokens_in=r["tokens_in"], tokens_out=r["tokens_out"],
                latency_s=r["latency_s"], error=r.get("error"),
            )
            for r in results
        ]
        for provider, results in data["results"].items()
    }

    all_scores = {
        provider: [
            EvaluationScore(
                provider=s["provider"], model=s["model"], latency_s=s["latency_s"],
                **{k: CriterioScore(puntaje=s[k]["puntaje"], justificacion=s[k]["justificacion"])
                   for k in ["adherencia_schema", "seleccion_vehiculo", "calidad_justificacion",
                             "completitud_alternativas", "veracidad", "relevancia", "precision_tecnica", "idioma"]}
            )
            for s in scores
        ]
        for provider, scores in data["scores"].items()
    }

    aggregated = [
        AggregatedScore(
            provider=a["provider"], model=a["model"],
            latencia_media=a["latencia_media"], total_runs=a["total_runs"],
            **{k: CriterioAgregado(media=a[k]["media"], desv=a[k]["desv"],
                                   minimo=a[k]["minimo"], maximo=a[k]["maximo"])
               for k in ["adherencia_schema", "seleccion_vehiculo", "calidad_justificacion",
                         "completitud_alternativas", "veracidad", "relevancia", "precision_tecnica", "idioma"]}
        )
        for a in data["aggregated"]
    ]

    solicitudes = [_solicitud_por_id(s["id"]) for s in data["solicitudes"]]

    return all_results, all_scores, aggregated, solicitudes


def _solicitud_por_id(pedido_id: str) -> SolicitudRecomendacion:
    return next((s for s in _SOLICITUDES if s.pedido.identificador == pedido_id), _SOLICITUDES[0])


# ── Entry point ───────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Compara LLMs sobre una solicitud RAG.")
    parser.add_argument(
        "--providers", default="ollama,google,openai",
        help="Proveedores separados por coma: ollama,google,openai,anthropic",
    )
    parser.add_argument(
        "--output", default="eval/reporte_comparacion.md",
        help="Ruta del archivo Markdown de salida.",
    )
    parser.add_argument(
        "--env", default="api/.env",
        help="Ruta del archivo .env con las API keys.",
    )
    parser.add_argument(
        "--no-analysis", action="store_true",
        help="Omite el análisis cualitativo con Claude Code",
    )
    parser.add_argument(
        "--analyze-only",
        help="Ruta al JSON de datos previos. Solo ejecuta el análisis con Claude Code.",
    )
    parser.add_argument(
        "--analyze-md",
        help="Ruta al reporte Markdown previo. Claude Code lo lee y genera el análisis.",
    )
    parser.add_argument(
        "--count", type=int, default=10,
        help="Número de solicitudes de prueba a ejecutar (máx 10, default 10)",
    )
    args = parser.parse_args()

    # Cargar .env si existe
    env_path = Path(args.env)
    if env_path.exists():
        from dotenv import load_dotenv
        load_dotenv(env_path)
        print(f"Variables cargadas desde {env_path}")

    # ── Modo analyze-md ───────────────────────────────────────
    if args.analyze_md:
        md_path = Path(args.analyze_md)
        if not md_path.exists():
            print(f"✗ Archivo no encontrado: {md_path}")
            sys.exit(1)
        print(f"\n── Leyendo reporte desde {md_path} ──")
        reporte_md = md_path.read_text(encoding="utf-8")
        print(f"  ✓ {len(reporte_md):,} caracteres")

        print("\n── Análisis cualitativo con Claude Code ──")
        analysis = AnalysisAgent().analizar_desde_reporte(reporte_md)

        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        contenido = reporte_md + "\n\n---\n\n## Análisis Generado por Claude Code\n\n"
        contenido += f"### 3.1 Comparación Cualitativa\n\n{analysis.comparacion_cualitativa}\n\n"
        contenido += f"### 3.2 Valoración\n\n{analysis.valoracion_justificacion}\n\n"
        contenido += f"### 4.1 Librerías y Frameworks\n\n{analysis.analisis_librerias}\n\n"
        contenido += f"### 4.2 Herramientas\n\n{analysis.analisis_herramientas}\n"
        output_path.write_text(contenido, encoding="utf-8")
        print(f"  Reporte con análisis guardado en: {output_path}")
        return

    # ── Modo analyze-only ─────────────────────────────────────
    if args.analyze_only:
        datos_path = Path(args.analyze_only)
        if not datos_path.exists():
            print(f"✗ Archivo no encontrado: {datos_path}")
            sys.exit(1)
        print(f"\n── Cargando datos desde {datos_path} ──")
        all_results, all_scores, aggregated, solicitudes = _cargar_datos(datos_path)
        print(f"  ✓ {len(aggregated)} proveedor(es), {aggregated[0].total_runs if aggregated else 0} runs")

        sample_results = [all_results[p][0] for p in all_results if all_results[p]]
        sample_sol = solicitudes[0] if solicitudes else _SOLICITUDES[0]
        sample_frags: list[Fragmento] = []

        print("\n── Análisis cualitativo con Claude Code ──")
        analysis = AnalysisAgent().analizar(sample_results, aggregated, sample_sol, sample_frags)

        print("\n── Generando reporte ──")
        report = ReportGenerator().generate(all_results, all_scores, aggregated, solicitudes, analysis)
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        print(f"  Reporte guardado en: {output_path}")
        return

    # ── Flujo completo ────────────────────────────────────────
    selected = [p.strip().lower() for p in args.providers.split(",")]

    print("\n── Inicializando proveedores ──")
    providers = _build_providers(selected)

    if not providers:
        print("\nNo hay proveedores disponibles. Verifica las API keys y que Ollama esté corriendo.")
        sys.exit(1)

    solicitudes = _solicitudes_prueba(args.count)
    print(f"\n── Recuperando contexto RAG para {len(solicitudes)} solicitudes ──")
    print("  El mismo contexto RAG se enviará a todos los proveedores por solicitud.")
    runs: list[tuple] = []
    for s in solicitudes:
        try:
            fragmentos, contexto_grafo = _recuperar_contexto_rag(s)
            claves = [k for k, v in contexto_grafo.items() if v]
            print(f"  ✓ {s.pedido.identificador}: {len(fragmentos)} frags | grafo: {claves or '∅'}")
            runs.append((s, fragmentos, contexto_grafo))
        except Exception as exc:
            print(f"  ✗ {s.pedido.identificador}: {exc}")

    if not runs:
        print("  No se pudo recuperar contexto RAG. Verifica que ChromaDB y Neo4j estén corriendo.")
        sys.exit(1)

    print(f"\n── Ejecutando pool ({len(providers)} proveedor(es) × {len(runs)} solicitudes) ──")
    settings = get_settings()
    obs = _build_observability(settings)
    if settings.langfuse_enabled and settings.langfuse_public_key:
        print(f"  ✓ Trazas Langfuse activas → {settings.langfuse_host}")
    else:
        print("  ○ Langfuse desactivado (configura LANGFUSE_ENABLED=true en api/.env)")
    pool = LLMPool(providers, observability=obs)
    all_results = pool.run(runs)

    print("\n── Evaluando respuestas ──")
    evaluator = ResponseEvaluator()
    all_scores: dict[str, list[EvaluationScore]] = {}
    for provider, results in all_results.items():
        provider_scores = [
            evaluator.evaluate(r, sol)
            for r, (sol, _, _) in zip(results, runs)
        ]
        all_scores[provider] = provider_scores

    aggregated = [
        _agregar_scores(
            provider,
            all_results[provider][0].model if all_results[provider] else provider,
            scores,
        )
        for provider, scores in all_scores.items()
    ]
    for a in aggregated:
        print(f"  {a.provider}: {a.promedio_global}/10 (media de {a.total_runs} runs)")

    datos_path = Path(args.output).with_suffix(".json")
    _guardar_datos(datos_path, all_results, all_scores, aggregated, [s for s, _, _ in runs])
    print(f"  Datos guardados en: {datos_path} (usa --analyze-only {datos_path} para re-analizar)")

    sample_results = [all_results[p][0] for p in all_results if all_results[p]]
    sample_sol, sample_frags, _ = runs[0]

    analysis = None
    if not args.no_analysis:
        print("\n── Análisis cualitativo con Claude Code ──")
        analysis = AnalysisAgent().analizar(
            sample_results, aggregated, sample_sol, sample_frags
        )

    print("\n── Generando reporte ──")
    report = ReportGenerator().generate(
        all_results, all_scores, aggregated, [s for s, _, _ in runs], analysis
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(f"  Reporte guardado en: {output_path}")


if __name__ == "__main__":
    main()

