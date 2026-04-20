"""
ResponseParser – transforma la respuesta del LLM en un objeto de dominio.

En Fase 6 el LLM ya no devuelve costos ni tiempos (ADR-0006).
  - tiempo_estimado_min: se toma del corredor del grafo si está disponible.
  - desglose_costo: placeholder en ceros hasta que CostCalculator (Fase 7)
    lo calcule a partir del grafo.
"""
from __future__ import annotations

import json
import logging
import re

from src.core.domain.models import (
    Alternativa,
    Alerta,
    DesgloseCosto,
    NivelAlerta,
    RecomendacionVehiculo,
    SolicitudRecomendacion,
    VehiculoDisponible,
)

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

        # Tiempo del corredor del grafo; sino 120 min como placeholder
        corredor = (contexto_grafo or {}).get("corredor") or {}
        tiempo_min = int(
            corredor.get("tiempo_estimado_min_carga")
            or data.get("tiempo_estimado_min", 120)
        )

        # Costos: placeholder en ceros hasta Fase 7 (CostCalculator)
        desglose = DesgloseCosto(
            combustible_cop=0.0,
            peajes_cop=0.0,
            viaticos_cop=0.0,
            seguro_cop=0.0,
            imprevistos_cop=0.0,
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
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        logger.warning("No se pudo parsear JSON del LLM. Respuesta: %s", text[:200])
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

