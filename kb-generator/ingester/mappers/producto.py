"""Mapper fichas_tecnicas_productos → (:Producto)-[:REQUIERE_VEHICULO]->(:TipoVehiculo).

Lee cada MD de 01_fichas_tecnicas_productos/:
  - frontmatter.productos_cubiertos  → lista de nombres de productos
  - body                             → extrae temp_opt_c, humedad_pct estimados
                                       y tipo de vehículo requerido
"""
from __future__ import annotations

import re
from pathlib import Path

from ..loaders.md_loader import load_md

# ── Cypher ──────────────────────────────────────────────────────────────────

_PRODUCTO_UPSERT = """
MERGE (p:Producto {nombre: $nombre})
SET p.temp_min_c     = $temp_min_c,
    p.temp_opt_c     = $temp_opt_c,
    p.temp_max_c     = $temp_max_c,
    p.humedad_pct    = $humedad_pct,
    p.vida_util_dias = $vida_util_dias,
    p.fuente_md      = $fuente_md
"""

_TIPO_VEHICULO_LINK = """
MERGE (tv:TipoVehiculo {tipo: $tipo})
WITH tv
MATCH (p:Producto {nombre: $nombre})
MERGE (p)-[:REQUIERE_VEHICULO]->(tv)
"""

# ── keywords para detección de refrigeración ────────────────────────────────

_KW_REFRIGERADO = [
    "cadena de frío", "refrigeración", "refrigerado", "temperatura controlada",
    "congelado", "isotermo", "-18", "cámara fría",
]
_KW_NO_REFRIGERADO = [
    "no requiere cadena de frío", "no requiere refrigeración",
    "sin refrigeración", "temperatura ambiente", "no requiere frío",
]


# ── helpers de extracción ────────────────────────────────────────────────────

def _extract_temp_range(body: str) -> tuple[float | None, float | None, float | None]:
    """Busca el primer rango de temperatura del cuerpo: 'X–Y °C' o 'X a Y °C'.

    Retorna (temp_min_c, temp_opt_c, temp_max_c).
    """
    pattern = re.search(
        r"(\d+(?:\.\d+)?)\s*[–\-a]\s*(\d+(?:\.\d+)?)\s*°\s*[Cc]",
        body,
    )
    if pattern:
        lo = float(pattern.group(1))
        hi = float(pattern.group(2))
        return lo, round((lo + hi) / 2, 1), hi
    single = re.search(r"(\d+(?:\.\d+)?)\s*°\s*[Cc]", body)
    if single:
        v = float(single.group(1))
        return None, v, None
    return None, None, None


def _extract_humedad(body: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*[–\-]\s*(\d+(?:\.\d+)?)\s*%\s*(?:HR|hr|humedad)", body)
    if m:
        return round((float(m.group(1)) + float(m.group(2))) / 2, 1)
    m2 = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(?:HR|hr|humedad)", body)
    if m2:
        return float(m2.group(1))
    return None


def _extract_vida_util(body: str) -> int | None:
    m = re.search(r"(\d+)\s*(?:a\s*(\d+)\s*)?d[íi]as", body, re.IGNORECASE)
    if m:
        if m.group(2):
            return int(round((int(m.group(1)) + int(m.group(2))) / 2))
        return int(m.group(1))
    return None


def _infer_tipo_vehiculo(body: str) -> str:
    body_lower = body.lower()
    if any(kw in body_lower for kw in _KW_NO_REFRIGERADO):
        return "abierto_ventilado"
    if any(kw in body_lower for kw in _KW_REFRIGERADO):
        return "refrigerado"
    return "abierto_ventilado"


# ── punto de entrada ─────────────────────────────────────────────────────────

def upsert_productos(session, md_path: Path) -> int:
    """Crea/actualiza (:Producto) por cada producto en productos_cubiertos.

    Retorna el número de productos creados/actualizados.
    """
    doc = load_md(md_path)
    fm = doc.frontmatter
    body = doc.body

    productos = fm.get("productos_cubiertos") or []
    if not productos:
        return 0

    temp_min, temp_opt, temp_max = _extract_temp_range(body)
    humedad = _extract_humedad(body)
    vida_util = _extract_vida_util(body)
    tipo_vehiculo = _infer_tipo_vehiculo(body)
    fuente = md_path.stem

    for nombre in productos:
        nombre = str(nombre).strip()
        if not nombre:
            continue
        session.run(
            _PRODUCTO_UPSERT,
            nombre=nombre,
            temp_min_c=temp_min,
            temp_opt_c=temp_opt,
            temp_max_c=temp_max,
            humedad_pct=humedad,
            vida_util_dias=vida_util,
            fuente_md=fuente,
        ).consume()
        session.run(_TIPO_VEHICULO_LINK, tipo=tipo_vehiculo, nombre=nombre).consume()

    return len(productos)

