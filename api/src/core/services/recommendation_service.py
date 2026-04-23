"""
RecommendationService – caso de uso principal.
Orquesta el flujo RAG híbrido (Chroma + Neo4j):
  1. Recupera contexto semántico (KnowledgeRepository / Chroma)
  2. Recupera contexto estructurado (GraphRepository / Neo4j)  ← Fase 6
  3. Ensambla el prompt con ambos contextos
  4. Invoca el LLM
  5. Parsea la respuesta

Los costos y tiempos de tránsito son calculados por CostCalculator
(Fase 7), no por el LLM (ADR-0006).
"""
from __future__ import annotations

import logging

from src.core.domain.models import RecomendacionVehiculo, SolicitudRecomendacion
from src.core.ports.interfaces import GraphRepository, KnowledgeRepository, LLMProvider, ObservabilityPort, SCORE_KEYS
from src.core.utils.prompt_builder import PromptBuilder
from src.core.utils.response_parser import ResponseParser

logger = logging.getLogger(__name__)


def _tipos_vehiculo_de_flota(flota) -> list[str]:
    return list({"refrigerado" if v.refrigerado else "abierto_ventilado" for v in flota})


class RecommendationService:

    def __init__(
        self,
        knowledge_repo: KnowledgeRepository,
        llm_provider: LLMProvider,
        graph_repo: GraphRepository | None = None,
        prompt_builder: PromptBuilder | None = None,
        response_parser: ResponseParser | None = None,
        observability: ObservabilityPort | None = None,
        top_k: int = 6,
    ) -> None:
        self._repo = knowledge_repo
        self._graph = graph_repo
        self._llm = llm_provider
        self._prompt = prompt_builder or PromptBuilder()
        self._parser = response_parser or ResponseParser()
        self._obs = observability
        self._top_k = top_k

    def recuperar_contexto(
        self, solicitud: SolicitudRecomendacion
    ) -> tuple[list, dict]:
        """Recupera fragmentos de Chroma y contexto de Neo4j sin invocar el LLM."""
        fragmentos = self._recuperar_contexto_chroma(solicitud)
        contexto_grafo = self._recuperar_contexto_grafo(solicitud) if self._graph else {}
        return fragmentos, contexto_grafo

    def recomendar(self, solicitud: SolicitudRecomendacion) -> RecomendacionVehiculo:
        logger.info(
            "Recomendación: pedido=%s peso=%.0f kg",
            solicitud.pedido.identificador, solicitud.peso_total_kg,
        )

        # ── Fase recuperación ────────────────────────────────
        fragmentos = self._recuperar_contexto_chroma(solicitud)
        contexto_grafo = self._recuperar_contexto_grafo(solicitud) if self._graph else {}
        logger.info(
            "Fragmentos Chroma: %d | claves grafo: %s",
            len(fragmentos), list(contexto_grafo.keys()),
        )

        # ── Fase razonamiento LLM ────────────────────────────
        strict = self._llm.strict_output
        system_prompt = self._prompt.build_system_prompt(strict_mode=strict)
        user_prompt = self._prompt.build_user_prompt(solicitud, fragmentos, contexto_grafo, strict_mode=strict)

        llm_response = self._llm.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=1500,
        )
        logger.info(
            "LLM: %d in / %d out tokens, modelo=%s",
            llm_response.tokens_entrada, llm_response.tokens_salida, llm_response.modelo,
        )
        logger.debug("LLM respuesta completa:\n%s", llm_response.texto)

        # ── Fase parseo ──────────────────────────────────────
        recomendacion = self._parser.parse(
            llm_text=llm_response.texto,
            solicitud=solicitud,
            fragmentos_ids=[f.id for f in fragmentos],
            contexto_grafo=contexto_grafo,
        )
        logger.info(
            "Recomendación: vehiculo=%s trace=%s",
            recomendacion.vehiculo_recomendado.id, recomendacion.trace_id,
        )

        if self._obs:
            self._obs.trace_recommendation(
                trace_id=recomendacion.trace_id,
                solicitud_id=solicitud.pedido.identificador,
                proveedor=type(self._llm).__name__,
                modelo=llm_response.modelo,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                respuesta=llm_response.texto,
                tokens_entrada=llm_response.tokens_entrada,
                tokens_salida=llm_response.tokens_salida,
                latencia_ms=0,
                vehiculo_seleccionado=recomendacion.vehiculo_recomendado.id,
                metadata={
                    "fragmentos": len(fragmentos),
                    "requiere_refrigeracion": solicitud.requiere_refrigeracion,
                    "peso_total_kg": solicitud.peso_total_kg,
                },
            )
            self._obs.score_recommendation(
                trace_id=recomendacion.trace_id,
                scores=self._calcular_scores_basicos(recomendacion, solicitud),
            )

        return recomendacion

    def _calcular_scores_basicos(
        self, recomendacion, solicitud: SolicitudRecomendacion
    ) -> dict[str, float]:
        just = recomendacion.justificacion.lower()
        flota = {v.id: v for v in solicitud.flota_disponible}
        v_sel = recomendacion.vehiculo_recomendado

        # ── adherencia_schema ────────────────────────────────────
        schema = 10.0 if recomendacion.justificacion != "Sin justificación disponible." else 0.0

        # ── seleccion_vehiculo ───────────────────────────────────
        if v_sel.id not in flota:
            seleccion = 2.0
        elif solicitud.requiere_refrigeracion and not v_sel.refrigerado:
            seleccion = 3.0
        elif v_sel.capacidad_kg < solicitud.peso_total_kg:
            seleccion = 4.0
        else:
            seleccion = 10.0

        # ── completitud_alternativas ─────────────────────────────
        n_esperadas = len(solicitud.flota_disponible) - 1
        alts = recomendacion.alternativas
        if not alts:
            completitud = 2.0
        elif len(alts) < n_esperadas:
            completitud = 5.0
        else:
            correctas = 0
            for alt in alts:
                veh = flota.get(alt.id)
                if not veh:
                    continue
                motivo = alt.motivo.lower()
                if solicitud.requiere_refrigeracion and not veh.refrigerado:
                    if any(kw in motivo for kw in ["refriger", "frío", "frio", "cadena", "temperatura"]):
                        correctas += 1
                elif veh.capacidad_kg < solicitud.peso_total_kg:
                    if any(kw in motivo for kw in ["capacidad", "insuficiente", "kg", "supera", "excede"]):
                        correctas += 1
                else:
                    correctas += 1
            calidad = correctas / n_esperadas if n_esperadas else 1.0
            completitud = round(5.0 + calidad * 5.0)

        # ── calidad_justificacion ────────────────────────────────
        words = just.split()
        _TECH = ["refriger", "capacidad", "kg", "perecedero", "normativa", "resolución", "temperatura"]
        tiene_tecnica = any(t in just for t in _TECH)
        if len(words) >= 40 and tiene_tecnica:
            calidad_just = 10.0
        elif len(words) >= 20 and tiene_tecnica:
            calidad_just = 7.0
        elif len(words) >= 20:
            calidad_just = 5.0
        elif len(words) >= 10:
            calidad_just = 3.0
        else:
            calidad_just = 0.0

        # ── veracidad ────────────────────────────────────────────
        productos_nombres = [p.nombre.lower().split()[0] for p in solicitud.productos]
        menciona_producto = any(p in just for p in productos_nombres)
        menciona_peso = str(int(solicitud.peso_total_kg)) in just
        menciona_ciudad = (
            solicitud.origen.ciudad.lower() in just
            or solicitud.destino.ciudad.lower() in just
        )
        veracidad = float(menciona_producto * 3 + menciona_peso * 4 + menciona_ciudad * 3)

        # ── relevancia ───────────────────────────────────────────
        vid_en_flota = v_sel.id in flota
        if not vid_en_flota:
            relevancia = 2.0
        elif solicitud.requiere_refrigeracion:
            menciona_refrig = any(t in just for t in ["refriger", "frío", "frio", "temperatura", "cadena"])
            relevancia = 10.0 if menciona_refrig else 5.0
        else:
            menciona_cap = any(t in just for t in ["capacidad", "kg", "carga", "peso"])
            relevancia = 10.0 if menciona_cap else 7.0

        # ── idioma ───────────────────────────────────────────────
        _SPANISH = {"el", "la", "los", "las", "es", "para", "que", "con",
                    "del", "por", "vehículo", "refrigerado", "carga", "capacidad"}
        hits = len(set(just.split()) & _SPANISH)
        idioma = 10.0 if hits >= 4 else (5.0 if hits >= 2 else 0.0)

        # ── precision_tecnica ────────────────────────────────────
        tecnica = 10.0 if tiene_tecnica else 4.0

        # ── promedio ─────────────────────────────────────────────
        criterios = [schema, seleccion, calidad_just, completitud, veracidad, relevancia, tecnica, idioma]
        promedio = round(sum(criterios) / len(criterios), 2)

        scores = {
            "adherencia_schema": schema,
            "seleccion_vehiculo": seleccion,
            "calidad_justificacion": calidad_just,
            "completitud_alternativas": completitud,
            "veracidad": veracidad,
            "relevancia": relevancia,
            "precision_tecnica": tecnica,
            "idioma": idioma,
            "promedio": promedio,
        }
        assert set(scores) == set(SCORE_KEYS), (
            f"Score keys no coinciden con SCORE_KEYS: {set(scores) ^ set(SCORE_KEYS)}"
        )
        return scores

    # ── Recuperación del grafo (ADR-0005) ─────────────────────

    def _recuperar_contexto_grafo(self, solicitud: SolicitudRecomendacion) -> dict:
        ctx: dict = {}
        try:
            # Q1: Requisitos de transporte de los productos
            nombres = [p.nombre for p in solicitud.productos]
            ctx["requisitos_productos"] = self._graph.get_requisitos_productos(nombres)

            # Q2: Corredor entre origen y destino explícitos
            corredor = self._graph.get_corredor(
                solicitud.origen.ciudad,
                solicitud.destino.ciudad,
            )
            ctx["corredor"] = corredor

            # Q3: Tarifas del corredor para las categorías de la flota
            if corredor:
                tipos = _tipos_vehiculo_de_flota(solicitud.flota_disponible)
                ctx["tarifas"] = self._graph.get_tarifas_corredor(corredor["id"], tipos)
            else:
                ctx["tarifas"] = []

            # Q4: Normativa aplicable a los tipos de vehículo disponibles
            tipos = _tipos_vehiculo_de_flota(solicitud.flota_disponible)
            ctx["normativa"] = self._graph.get_normativa_tipos(tipos)

        except Exception as exc:
            logger.error("Error recuperando contexto del grafo: %s", exc)

        return ctx

    # ── Recuperación semántica Chroma ─────────────────────────

    def _recuperar_contexto_chroma(self, solicitud: SolicitudRecomendacion):
        nombres_productos = ", ".join(p.nombre for p in solicitud.productos)
        refrigeracion = "refrigerado" if solicitud.requiere_refrigeracion else "temperatura ambiente"
        query = (
            f"Transporte de {nombres_productos}, {solicitud.peso_total_kg:.0f} kg, "
            f"{refrigeracion}, "
            f"origen {solicitud.origen.ciudad} destino {solicitud.destino.ciudad}, "
            f"prioridad {solicitud.pedido.prioridad.value}"
        )
        fragmentos = self._repo.search_semantic(query, k=self._top_k)

        # Búsqueda adicional específica por catálogo de flota
        flota_frags = self._repo.search_semantic(
            f"especificaciones vehículos {refrigeracion} capacidad {solicitud.peso_total_kg:.0f} kg",
            k=3,
            categoria="catalogo_flota_vehicular",
        )
        ids_vistos = {f.id for f in fragmentos}
        for f in flota_frags:
            if f.id not in ids_vistos:
                fragmentos.append(f)
                ids_vistos.add(f.id)

        return fragmentos

