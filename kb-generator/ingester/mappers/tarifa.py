"""Mapper SICE-TAC JSON → (:Tarifa)-[:APLICA_A]->(:Corredor).

Fuente: mintransporte_sicetac_peajes_por_rutas_con_tarifas.json
  - 8 859 rutas únicas, cada una con N peajes (68 k registros totales)
  - VALOR5 = tarifa categoría V (tracto-camión de 5 ejes), usada como
    referencia para carga agrícola pesada (criterio SICE-TAC)

Matching con corredores INVIAS:
  "De Bogotá a Medellín"   → normalizado → {"BOGOTA", "MEDELLIN"}
  "BOGOTA _ MEDELLIN"      → normalizado → {"BOGOTA", "MEDELLIN"}
  Si el conjunto de ciudades coincide, la ruta SICE-TAC se vincula al corredor.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

# ── Cypher ───────────────────────────────────────────────────────────────────

_TARIFA_UPSERT = """
MERGE (t:Tarifa {id: $id})
SET t.valor_cop  = $valor_cop,
    t.tipo_carga = $tipo_carga,
    t.vigencia   = $vigencia,
    t.num_peajes = $num_peajes
WITH t
MATCH (c:Corredor {id: $corredor_id})
MERGE (t)-[:APLICA_A]->(c)
"""

# ── helpers ───────────────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    """Normaliza a mayúsculas sin tildes: 'Bogotá' → 'BOGOTA'."""
    nfkd = unicodedata.normalize("NFD", s.upper())
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def _cities_from_invias_nombre(nombre: str) -> frozenset[str]:
    """'De Bogotá a Villavicencio' → frozenset({'BOGOTA', 'VILLAVICENCIO'})."""
    lower = nombre.lower()
    if lower.startswith("de ") and " a " in lower:
        rest = nombre[3:]
        parts = rest.split(" a ", 1)
        if len(parts) == 2:
            return frozenset(_norm(p.strip()) for p in parts)
    return frozenset()


def _cities_from_sicetac_nombre(nombre: str) -> frozenset[str]:
    """'BOGOTA _ MEDELLIN' → frozenset({'BOGOTA', 'MEDELLIN'})."""
    parts = re.split(r"\s*_\s*", nombre.strip())
    return frozenset(_norm(p.strip()) for p in parts if p.strip())


def _build_corredor_index(invias_path: Path) -> dict[frozenset, str]:
    """Lee invias_corredores.json y construye {frozenset(ciudades) → corredor_id}."""
    if not invias_path.exists():
        return {}
    data = json.loads(invias_path.read_text(encoding="utf-8"))
    index: dict[frozenset, str] = {}
    for c in data.get("corredores", []):
        cid = c.get("id")
        nombre = c.get("nombre", "")
        cities = _cities_from_invias_nombre(nombre)
        if cid and cities:
            index[cities] = cid
    return index


# ── punto de entrada ─────────────────────────────────────────────────────────

def upsert_tarifas(session, sicetac_json: Path, invias_json: Path) -> int:
    """Crea (:Tarifa)-[:APLICA_A]->(:Corredor) para cada corredor INVIAS con ruta SICE-TAC.

    Usa VALOR5 (categoría V — tracto-camión 5 ejes) como tarifa de referencia.
    Retorna el número de tarifas creadas.
    """
    corredor_idx = _build_corredor_index(invias_json)
    if not corredor_idx:
        return 0

    data = json.loads(sicetac_json.read_text(encoding="utf-8"))
    registros = [
        r for r in data.get("registros", [])
        if r.get("PEAJES POR RUTAS SICETAC 01-04-2026") not in ("", "RUTA_ID", None)
    ]

    # Agrega peajes por ruta: {ruta_id → {nombre, total_valor5, num_peajes}}
    rutas: dict[int, dict] = {}
    for r in registros:
        ruta_id = r["PEAJES POR RUTAS SICETAC 01-04-2026"]
        if ruta_id not in rutas:
            rutas[ruta_id] = {
                "nombre": str(r.get("Unnamed: 1", "")),
                "total_valor5": 0,
                "num_peajes": 0,
            }
        valor5 = r.get("Unnamed: 11") or 0
        try:
            rutas[ruta_id]["total_valor5"] += int(valor5)
            rutas[ruta_id]["num_peajes"] += 1
        except (ValueError, TypeError):
            pass

    created = 0
    for ruta_id, info in rutas.items():
        cities = _cities_from_sicetac_nombre(info["nombre"])
        corredor_id = corredor_idx.get(cities)
        if not corredor_id:
            continue

        tarifa_id = f"sicetac-{corredor_id}"
        session.run(
            _TARIFA_UPSERT,
            id=tarifa_id,
            valor_cop=info["total_valor5"],
            tipo_carga="carga_general",
            vigencia=2026,
            num_peajes=info["num_peajes"],
            corredor_id=corredor_id,
        ).consume()
        created += 1

    return created

