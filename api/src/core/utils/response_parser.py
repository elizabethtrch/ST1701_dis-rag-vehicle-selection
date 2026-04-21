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
        vehiculo = self._resolve_vehicle(self._extract_vehiculo_id(data), solicitud)
        alternativas = self._parse_alternativas(self._extract_alternativas(data))
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
            justificacion=self._extract_justificacion(data),
            alternativas=alternativas,
            alertas=alertas,
            costo_estimado_cop=desglose.total_cop,
            desglose_costo=desglose,
            tiempo_estimado_min=tiempo_min,
            fragmentos_consultados=fragmentos_ids,
        )

    # ── privados ─────────────────────────────────────────────

    def _strip_comments(self, text: str) -> str:
        text = re.sub(r"//[^\n]*", "", text)
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        return text

    def _extract_json(self, text: str) -> dict:
        text = text.strip()

        # Intento 1: JSON puro
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Intento 1b: mismo texto sin comentarios JS
        try:
            return json.loads(self._strip_comments(text))
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

    def _extract_vehiculo_id(self, data: dict) -> str:
        nested = data.get("selected_vehicle") or data.get("vehiculo_seleccionado") or {}
        return (
            data.get("vehiculo_id")
            or data.get("vehicle_id")
            or nested.get("vehicle_id")
            or nested.get("vehiculo_id")
            or nested.get("id")
            or ""
        )

    def _extract_justificacion(self, data: dict) -> str:
        nested = data.get("selected_vehicle") or data.get("vehiculo_seleccionado") or {}

        # Campo canónico
        if data.get("justificacion"):
            return data["justificacion"]

        # Variantes en inglés o anidadas como string o lista
        for candidate in (
            data.get("justification"),
            nested.get("justificacion"),
            nested.get("justification"),
        ):
            if isinstance(candidate, str) and candidate.strip():
                return candidate
            if isinstance(candidate, list):
                partes = [s for s in candidate if isinstance(s, str) and s.strip()]
                if partes:
                    return " ".join(partes)

        # justification/justificacion como objeto con subcampos de texto
        for obj in (data.get("justification"), nested.get("justification")):
            if isinstance(obj, dict):
                textos = [v for v in obj.values() if isinstance(v, str) and v.strip()]
                if textos:
                    return " ".join(textos)

        # reasoning como lista de objetos con campo "value"
        for key in ("reasoning", "reason"):
            reasoning = data.get(key) or nested.get(key)
            if isinstance(reasoning, list):
                partes = [
                    item.get("value", "") for item in reasoning
                    if isinstance(item, dict) and item.get("value")
                ]
                if partes:
                    return " ".join(partes)
            elif isinstance(reasoning, str) and reasoning.strip():
                return reasoning

        logger.warning("No se encontró campo de justificación en la respuesta del LLM.")
        return "Sin justificación disponible."

    def _extract_alternativas(self, data: dict) -> list:
        nested = data.get("selected_vehicle") or data.get("vehiculo_seleccionado") or {}
        return (
            data.get("alternativas")
            or data.get("alternatives")
            or nested.get("alternative_vehicles")
            or nested.get("alternativas")
            or []
        )

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
            if not isinstance(item, dict):
                continue
            alt_id = (
                item.get("id")
                or item.get("vehicle_id")
                or item.get("vehiculo_id")
                or "N/A"
            )
            _id_keys = {"id", "vehicle_id", "vehiculo_id"}
            motivo = next(
                (v for k, v in item.items() if k not in _id_keys and isinstance(v, str) and v.strip()),
                ""
            )
            result.append(Alternativa(id=str(alt_id), motivo=str(motivo)))
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

