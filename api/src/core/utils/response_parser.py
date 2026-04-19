"""
ResponseParser – transforma la respuesta del LLM en un objeto de dominio.
Incluye validaciones defensivas ante respuestas mal formadas.
"""
from __future__ import annotations
import json
import re
import logging
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
    ) -> RecomendacionVehiculo:
        data = self._extract_json(llm_text)
        vehiculo = self._resolve_vehicle(data.get("vehiculo_id", ""), solicitud)
        alternativas = self._parse_alternativas(data.get("alternativas", []))
        alertas = self._parse_alertas(data.get("alertas", []))
        desglose = self._parse_desglose(data.get("desglose_costo", {}))

        return RecomendacionVehiculo.nuevo_trace(
            vehiculo_recomendado=vehiculo,
            justificacion=data.get("justificacion", "Sin justificación disponible."),
            alternativas=alternativas,
            alertas=alertas,
            costo_estimado_cop=desglose.total_cop,
            desglose_costo=desglose,
            tiempo_estimado_min=int(data.get("tiempo_estimado_min", 120)),
            fragmentos_consultados=fragmentos_ids,
        )

    # ── privados ─────────────────────────────────────────────

    def _extract_json(self, text: str) -> dict:
        # Intenta parseo directo
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Busca bloque JSON entre llaves
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
        # Fallback: el vehículo con mayor capacidad
        logger.warning(
            "Vehículo '%s' no encontrado en flota. Usando el de mayor capacidad.", vehicle_id
        )
        return max(solicitud.flota_disponible, key=lambda v: v.capacidad_kg)

    def _parse_alternativas(self, raw: list) -> list[Alternativa]:
        result = []
        for item in raw[:2]:  # máximo 2
            if isinstance(item, dict):
                result.append(
                    Alternativa(
                        id=str(item.get("id", "N/A")),
                        motivo=str(item.get("motivo", "")),
                    )
                )
        return result

    def _parse_alertas(self, raw: list) -> list[Alerta]:
        result = []
        nivel_map = {
            "alta": NivelAlerta.ALTA,
            "media": NivelAlerta.MEDIA,
            "baja": NivelAlerta.BAJA,
        }
        for item in raw:
            if isinstance(item, dict):
                nivel_str = str(item.get("nivel", "baja")).lower()
                result.append(
                    Alerta(
                        nivel=nivel_map.get(nivel_str, NivelAlerta.BAJA),
                        mensaje=str(item.get("mensaje", "")),
                    )
                )
        return result

    def _parse_desglose(self, raw: dict) -> DesgloseCosto:
        def _v(key: str) -> float:
            try:
                return float(raw.get(key, 0))
            except (TypeError, ValueError):
                return 0.0

        return DesgloseCosto(
            combustible_cop=_v("combustible_cop"),
            peajes_cop=_v("peajes_cop"),
            viaticos_cop=_v("viaticos_cop"),
            seguro_cop=_v("seguro_cop"),
            imprevistos_cop=_v("imprevistos_cop"),
        )
