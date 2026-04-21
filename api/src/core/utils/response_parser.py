"""
ResponseParser – transforma la respuesta del LLM en un objeto de dominio.

El LLM elige vehículo, justificación, alternativas y alertas.
Costos y tiempos los calcula CostCalculator (ADR-0006).
"""
from __future__ import annotations

import json
import logging
import re

from src.core.domain.models import (
    Alternativa,
    Alerta,
    NivelAlerta,
    RecomendacionVehiculo,
    SolicitudRecomendacion,
    VehiculoDisponible,
)
from src.core.services.cost_calculator import calcular_costo, calcular_tiempo

logger = logging.getLogger(__name__)


class ParseError(Exception):
    pass


class ResponseParser:

    def parse(
        self,
        llm_text: str,
        solicitud: SolicitudRecomendacion,
        fragmentos_ids: list[str],
        contexto_grafo: dict | None = None,
    ) -> RecomendacionVehiculo:
        data = self._extract_json(llm_text)
        vehiculo = self._resolve_vehicle(data.get("vehiculo_id", ""), solicitud)
        alternativas = self._parse_alternativas(data.get("alternativas", []))
        alertas = self._parse_alertas(data.get("alertas", []))

        ctx = contexto_grafo or {}
        corredor = ctx.get("corredor") or {}
        tarifas = ctx.get("tarifas") or []

        tiempo_min = calcular_tiempo(corredor)
        desglose = calcular_costo(
            corredor=corredor,
            vehiculo=vehiculo,
            tarifas=tarifas,
            peso_kg=solicitud.peso_total_kg,
        )

        return RecomendacionVehiculo.nuevo_trace(
            vehiculo_recomendado=vehiculo,
            justificacion=data.get("justificacion", "Sin justificación disponible."),
            alternativas=alternativas,
            alertas=alertas,
            costo_estimado_cop=desglose.total_cop,
            desglose_costo=desglose,
            tiempo_estimado_min=tiempo_min,
            fragmentos_consultados=fragmentos_ids,
        )

    # ── privados ─────────────────────────────────────────────

    def _extract_json(self, text: str) -> dict:
        text = text.strip()

        # Intento 1: JSON puro
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Intento 2: bloque ```json ... ``` (respuesta típica de Ollama/LLaMA)
        block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if block:
            try:
                return json.loads(block.group(1))
            except json.JSONDecodeError:
                pass

        # Intento 3: primer objeto { ... } en el texto
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        logger.warning("No se pudo parsear JSON del LLM. Respuesta completa:\n%s", text)
        raise ParseError("Respuesta del LLM no contiene JSON válido.")

    def _resolve_vehicle(
        self, vehicle_id: str, solicitud: SolicitudRecomendacion
    ) -> VehiculoDisponible:
        idx = {v.id: v for v in solicitud.flota_disponible}
        if vehicle_id in idx:
            return idx[vehicle_id]
        logger.warning("Vehículo '%s' no encontrado. Usando el de mayor capacidad.", vehicle_id)
        return max(solicitud.flota_disponible, key=lambda v: v.capacidad_kg)

    def _parse_alternativas(self, raw: list) -> list[Alternativa]:
        result = []
        for item in raw[:2]:
            if isinstance(item, dict):
                result.append(Alternativa(id=str(item.get("id", "N/A")), motivo=str(item.get("motivo", ""))))
        return result

    def _parse_alertas(self, raw: list) -> list[Alerta]:
        nivel_map = {"alta": NivelAlerta.ALTA, "media": NivelAlerta.MEDIA, "baja": NivelAlerta.BAJA}
        result = []
        for item in raw:
            if isinstance(item, dict):
                nivel_str = str(item.get("nivel", "baja")).lower()
                result.append(Alerta(
                    nivel=nivel_map.get(nivel_str, NivelAlerta.BAJA),
                    mensaje=str(item.get("mensaje", "")),
                ))
        return result

