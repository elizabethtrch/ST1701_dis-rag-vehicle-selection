"""
CostCalculator – cálculo determinista de costos y tiempos (ADR-0006).

Funciones puras: reciben datos del grafo (corredor, tarifas) y el
vehículo seleccionado; devuelven DesgloseCosto / int.

Constantes basadas en valores SICE-TAC y mercado colombiano 2024:
  - Precio diesel: ~$3 300 COP/litro
  - Viático conductor: $120 000 COP/día (8 h de conducción)
  - Tasa seguro carga agrícola: 0.2 % del valor estimado
  - Imprevistos: 5 % del subtotal (combustible + peajes + viáticos + seguro)
"""
from __future__ import annotations

import math

from src.core.domain.models import DesgloseCosto, VehiculoDisponible

# ── Constantes SICE-TAC (actualizables sin cambiar la lógica) ─

_PRECIO_DIESEL_COP_L = 3_300          # COP por litro de ACPM
_FACTOR_CONSUMO_CARGA = 1.15          # +15 % consumo con carga
_VIATICO_DIA_COP = 120_000            # viático conductor por día de ruta
_HORAS_CONDUCCION_DIA = 8             # horas efectivas de conducción/día
_VALOR_KG_AGRO_COP = 3_000            # valor promedio COP por kg carga agrícola
_TASA_SEGURO = 0.002                  # 0.2 % del valor de la carga
_FACTOR_IMPREVISTOS = 0.05            # 5 % sobre subtotal


def _rendimiento_km_l(capacidad_kg: float) -> float:
    """Rendimiento estimado en km/L según capacidad del vehículo."""
    if capacidad_kg <= 3_500:
        return 10.0   # camioneta / furgón ligero
    if capacidad_kg <= 10_000:
        return 7.0    # camión mediano (NHR/NPR)
    return 5.0        # tracto-camión / camión pesado


def calcular_tiempo(corredor: dict) -> int:
    """
    Tiempo total estimado en minutos.
    tiempo_estimado_min_carga + impacto_min_carga por estado INVIAS.
    Retorna 120 si el corredor no tiene datos.
    """
    if not corredor:
        return 120
    base = int(corredor.get("tiempo_estimado_min_carga") or 120)
    impacto = int(corredor.get("impacto_min_carga") or 0)
    return base + impacto


def calcular_costo(
    corredor: dict,
    vehiculo: VehiculoDisponible,
    tarifas: list[dict],
    peso_kg: float,
) -> DesgloseCosto:
    """
    Desglose de costos de transporte para un corredor y vehículo dados.

    - combustible_cop: distancia × consumo × precio diesel
    - peajes_cop: suma de tarifas del grafo para el corredor
    - viaticos_cop: días de viaje × viático diario
    - seguro_cop: 0.2 % del valor estimado de la carga
    - imprevistos_cop: 5 % del subtotal anterior
    """
    distancia_km = float((corredor or {}).get("distancia_km") or 0)

    # Combustible
    rendimiento = _rendimiento_km_l(vehiculo.capacidad_kg)
    litros = distancia_km / rendimiento * _FACTOR_CONSUMO_CARGA
    combustible_cop = litros * _PRECIO_DIESEL_COP_L

    # Peajes: suma de todos los valores traídos del grafo
    peajes_cop = sum(
        float(t.get("valor_cop") or 0)
        for t in (tarifas or [])
        if t.get("valor_cop") is not None
    )

    # Viáticos: días necesarios para el recorrido
    tiempo_min = calcular_tiempo(corredor)
    dias = math.ceil(tiempo_min / 60 / _HORAS_CONDUCCION_DIA)
    viaticos_cop = max(dias, 1) * _VIATICO_DIA_COP

    # Seguro de carga
    seguro_cop = peso_kg * _VALOR_KG_AGRO_COP * _TASA_SEGURO

    # Imprevistos
    subtotal = combustible_cop + peajes_cop + viaticos_cop + seguro_cop
    imprevistos_cop = subtotal * _FACTOR_IMPREVISTOS

    return DesgloseCosto(
        combustible_cop=round(combustible_cop, 2),
        peajes_cop=round(peajes_cop, 2),
        viaticos_cop=round(viaticos_cop, 2),
        seguro_cop=round(seguro_cop, 2),
        imprevistos_cop=round(imprevistos_cop, 2),
    )

