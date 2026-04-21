"""Mapper normativa_transporte → (:Normativa), (:TipoVehiculo), (:Articulo) + relaciones.

Estructura esperada en los MDs:
  - frontmatter: fuente, titulo, anno
  - body: sección "## Datos de la norma" con "**Entidad emisora**:"
  - body: sección "## Artículos clave para el RAG" con citas entre comillas dobles

Tipos inferidos por keywords del contenido:
  - "refrigerado"       → menciona refrigerado/isotermo/cadena de frío
  - "abierto_ventilado" → menciona abierto/ventilado/carga seca, o es normativa general
"""
from __future__ import annotations

import re
from pathlib import Path

from ..loaders.md_loader import load_md

# ── Cypher ──────────────────────────────────────────────────────────────────

_NORMATIVA_UPSERT = """
MERGE (n:Normativa {id: $id})
SET n.numero          = $numero,
    n.nombre          = $nombre,
    n.anno            = $anno,
    n.entidad_emisora = $entidad_emisora
"""

_TIPO_VEHICULO_LINK = """
MERGE (tv:TipoVehiculo {tipo: $tipo})
WITH tv
MATCH (n:Normativa {id: $normativa_id})
MERGE (n)-[:REGULA]->(tv)
"""

_ARTICULO_UPSERT = """
MATCH (n:Normativa {id: $normativa_id})
MERGE (a:Articulo {id: $articulo_id})
SET a.cita_textual = $cita_textual
MERGE (n)-[:CONTIENE]->(a)
"""

# ── keywords para inferir tipos de vehículo regulados ───────────────────────

_KEYWORDS_POR_TIPO: dict[str, list[str]] = {
    "refrigerado": [
        "refrigerado", "refrigeración", "isotermo", "congelado",
        "cadena de frío", "temperatura de conservación",
    ],
    "abierto_ventilado": [
        "abierto", "ventilado", "carga seca", "granel",
        "camioneta", "camión", "vehículo transportador",
    ],
}


# ── helpers de extracción ────────────────────────────────────────────────────

def _extract_numero(titulo: str) -> str:
    m = re.search(r"\b0*(\d{3,5})\b", titulo)
    return m.group(1) if m else ""


def _extract_entidad_emisora(body: str) -> str:
    m = re.search(r"\*\*Entidad emisora\*\*:\s*(.+)", body)
    return m.group(1).strip() if m else ""


def _extract_articulos(body: str) -> list[str]:
    """Extrae hasta 5 citas textuales de la sección 'Artículos clave para el RAG'."""
    sec = re.search(
        r"##\s+Artículos clave para el RAG\s*(.*?)(?:\n##\s|\Z)",
        body,
        re.DOTALL,
    )
    if not sec:
        return []
    return re.findall(r'"([^"]{40,})"', sec.group(1))[:5]


def _infer_tipos_vehiculo(body: str) -> list[str]:
    body_lower = body.lower()
    tipos = [t for t, kws in _KEYWORDS_POR_TIPO.items() if any(kw in body_lower for kw in kws)]
    return tipos or ["abierto_ventilado"]


# ── punto de entrada ─────────────────────────────────────────────────────────

def upsert_normativa(session, md_path: Path) -> None:
    """Crea/actualiza (:Normativa) + relaciones a partir de un MD estructurado."""
    doc = load_md(md_path)
    fm = doc.frontmatter
    body = doc.body

    titulo = fm.get("titulo") or md_path.stem
    anno = fm.get("anno")
    fuente = fm.get("fuente") or ""
    normativa_id = md_path.stem

    entidad_emisora = _extract_entidad_emisora(body) or fuente
    numero = _extract_numero(titulo)

    session.run(
        _NORMATIVA_UPSERT,
        id=normativa_id,
        numero=numero,
        nombre=titulo,
        anno=anno,
        entidad_emisora=entidad_emisora,
    ).consume()

    for tipo in _infer_tipos_vehiculo(body):
        session.run(_TIPO_VEHICULO_LINK, tipo=tipo, normativa_id=normativa_id).consume()

    for i, cita in enumerate(_extract_articulos(body)):
        session.run(
            _ARTICULO_UPSERT,
            normativa_id=normativa_id,
            articulo_id=f"{normativa_id}-art-{i:03d}",
            cita_textual=cita,
        ).consume()

