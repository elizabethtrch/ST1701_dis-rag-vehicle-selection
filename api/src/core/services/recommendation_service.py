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
from src.core.ports.interfaces import GraphRepository, KnowledgeRepository, LLMProvider
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
        top_k: int = 6,
    ) -> None:
        self._repo = knowledge_repo
        self._graph = graph_repo
        self._llm = llm_provider
        self._prompt = prompt_builder or PromptBuilder()
        self._parser = response_parser or ResponseParser()
        self._top_k = top_k

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
        system_prompt = self._prompt.build_system_prompt()
        user_prompt = self._prompt.build_user_prompt(solicitud, fragmentos, contexto_grafo)

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
        return recomendacion

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

