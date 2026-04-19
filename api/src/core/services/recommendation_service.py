"""
RecommendationService – caso de uso principal.
Orquesta el flujo RAG completo:
  1. Construye la consulta semántica
  2. Recupera contexto documental (KnowledgeRepository)
  3. Ensambla el prompt (PromptBuilder)
  4. Invoca el LLM (LLMProvider)
  5. Parsea la respuesta (ResponseParser)
"""
from __future__ import annotations
import logging
from src.core.domain.models import RecomendacionVehiculo, SolicitudRecomendacion
from src.core.ports.interfaces import KnowledgeRepository, LLMProvider
from src.core.utils.prompt_builder import PromptBuilder
from src.core.utils.response_parser import ResponseParser

logger = logging.getLogger(__name__)


class RecommendationService:

    def __init__(
        self,
        knowledge_repo: KnowledgeRepository,
        llm_provider: LLMProvider,
        prompt_builder: PromptBuilder | None = None,
        response_parser: ResponseParser | None = None,
        top_k: int = 6,
    ) -> None:
        self._repo = knowledge_repo
        self._llm = llm_provider
        self._prompt = prompt_builder or PromptBuilder()
        self._parser = response_parser or ResponseParser()
        self._top_k = top_k

    def recomendar(self, solicitud: SolicitudRecomendacion) -> RecomendacionVehiculo:
        logger.info(
            "Iniciando recomendación para pedido=%s, peso=%.0f kg",
            solicitud.pedido.identificador,
            solicitud.peso_total_kg,
        )

        # ── Fase 2: recuperación de contexto ─────────────────
        fragmentos = self._recuperar_contexto(solicitud)
        logger.info("Fragmentos recuperados: %d", len(fragmentos))

        # ── Fase 3: razonamiento del LLM ─────────────────────
        system_prompt = self._prompt.build_system_prompt()
        user_prompt = self._prompt.build_user_prompt(solicitud, fragmentos)

        llm_response = self._llm.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=1500,
        )
        logger.info(
            "LLM respondió: %d tokens entrada, %d salida, modelo=%s",
            llm_response.tokens_entrada,
            llm_response.tokens_salida,
            llm_response.modelo,
        )

        # ── Fase 4: parseo de respuesta ───────────────────────
        fragmentos_ids = [f.id for f in fragmentos]
        recomendacion = self._parser.parse(
            llm_text=llm_response.texto,
            solicitud=solicitud,
            fragmentos_ids=fragmentos_ids,
        )

        logger.info(
            "Recomendación generada: vehículo=%s, trace_id=%s",
            recomendacion.vehiculo_recomendado.id,
            recomendacion.trace_id,
        )
        return recomendacion

    # ── privados ─────────────────────────────────────────────

    def _recuperar_contexto(self, solicitud: SolicitudRecomendacion):
        # Construye query semántica con los datos clave del pedido
        nombres_productos = ", ".join(p.nombre for p in solicitud.productos)
        refrigeracion = "refrigerado" if solicitud.requiere_refrigeracion else "temperatura ambiente"
        query = (
            f"Transporte de {nombres_productos}, {solicitud.peso_total_kg:.0f} kg, "
            f"{refrigeracion}, destino {solicitud.cliente.direccion}, "
            f"prioridad {solicitud.pedido.prioridad.value}"
        )

        # Búsqueda semántica general
        fragmentos = self._repo.search_semantic(query, k=self._top_k)

        # Búsqueda adicional específica por categoría de flota
        flota_frags = self._repo.search_semantic(
            f"especificaciones vehículos {refrigeracion} capacidad {solicitud.peso_total_kg:.0f} kg",
            k=3,
            categoria="fleet",
        )

        # Fusión sin duplicados
        ids_vistos = {f.id for f in fragmentos}
        for f in flota_frags:
            if f.id not in ids_vistos:
                fragmentos.append(f)
                ids_vistos.add(f.id)

        return fragmentos
