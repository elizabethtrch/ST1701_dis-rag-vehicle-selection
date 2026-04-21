"""Mapper de `invias_corredores.json` → (:Corredor), (:Ciudad), (:Departamento).

Relaciones que crea:
  (Corredor)-[:ORIGEN]->(Ciudad)
  (Corredor)-[:DESTINO]->(Ciudad)
  (Corredor)-[:ATRAVIESA]->(Departamento)
"""
from __future__ import annotations


CORREDOR_UPSERT = """
MERGE (c:Corredor {id: $id})
SET c.nombre                    = $nombre,
    c.distancia_km              = $distancia_km,
    c.es_critico                = $es_critico,
    c.tiempo_base_min_carga     = $tiempo_base_min_carga,
    c.tiempo_estimado_min_carga = $tiempo_estimado_min_carga,
    c.estado_general            = $estado_general,
    c.estado_general_carga      = $estado_general_carga,
    c.cantidad_incidentes       = $cantidad_incidentes,
    c.impacto_min_carga         = $impacto_min_carga
"""


ORIGEN_DESTINO_UPSERT = """
MATCH (c:Corredor {id: $corredor_id})
MERGE (o:Ciudad {nombre: $origen_nombre})
MERGE (d:Ciudad {nombre: $destino_nombre})
MERGE (c)-[:ORIGEN]->(o)
MERGE (c)-[:DESTINO]->(d)
"""


DEPARTAMENTOS_UPSERT = """
MATCH (c:Corredor {id: $corredor_id})
UNWIND $departamentos AS dep_nombre
MERGE (dep:Departamento {nombre: dep_nombre})
MERGE (c)-[:ATRAVIESA]->(dep)
"""


def upsert_corredor(session, corredor: dict) -> None:
    """Inserta (:Corredor) + (:Ciudad) origen/destino + (:Departamento) atravesados."""
    if not corredor.get("id"):
        raise ValueError("INVIAS: corredor sin 'id'")
    if not corredor.get("nombre"):
        raise ValueError(f"INVIAS: corredor {corredor['id']} sin 'nombre'")

    session.run(
        CORREDOR_UPSERT,
        id=corredor["id"],
        nombre=corredor["nombre"],
        distancia_km=corredor.get("distancia_km"),
        es_critico=bool(corredor.get("es_critico", False)),
        tiempo_base_min_carga=corredor.get("tiempo_base_min_carga"),
        tiempo_estimado_min_carga=corredor.get("tiempo_estimado_min_carga"),
        estado_general=corredor.get("estado_general"),
        estado_general_carga=corredor.get("estado_general_carga"),
        cantidad_incidentes=corredor.get("cantidad_incidentes", 0),
        impacto_min_carga=corredor.get("impacto_min_carga"),
    ).consume()

    origen, destino = _parse_origen_destino(corredor["nombre"])
    if origen and destino:
        session.run(
            ORIGEN_DESTINO_UPSERT,
            corredor_id=corredor["id"],
            origen_nombre=origen,
            destino_nombre=destino,
        ).consume()

    deps = corredor.get("departamentos") or []
    if deps:
        session.run(
            DEPARTAMENTOS_UPSERT,
            corredor_id=corredor["id"],
            departamentos=deps,
        ).consume()


def _parse_origen_destino(nombre: str) -> tuple[str | None, str | None]:
    """'De Bogotá a Villavicencio' → ('Bogotá', 'Villavicencio')."""
    if not nombre:
        return None, None
    lower = nombre.lower()
    if lower.startswith("de ") and " a " in lower:
        rest = nombre[3:]
        parts = rest.split(" a ", 1)
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()
    return None, None

