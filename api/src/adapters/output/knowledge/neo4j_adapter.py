"""
Neo4jAdapter – adaptador de salida para el grafo de conocimiento.
Implementa el puerto GraphRepository con las ~4 queries Cypher
parametrizadas definidas en el ADR-0005.

Las queries usan OPTIONAL MATCH para devolver resultados parciales
cuando el grafo aún no tiene todos los nodos cargados (mientras el
kb-generator estructura los PDFs pendientes).
"""
from __future__ import annotations

import logging

from neo4j import GraphDatabase

from src.core.ports.interfaces import GraphRepository

logger = logging.getLogger(__name__)

# ── Queries ───────────────────────────────────────────────────

# Q1: Condiciones de transporte por nombre de producto
_Q_REQUISITOS = """
UNWIND $nombres AS nombre_buscado
OPTIONAL MATCH (p:Producto)
WHERE toLower(p.nombre) = toLower(nombre_buscado)
OPTIONAL MATCH (p)-[:REQUIERE_VEHICULO]->(tv:TipoVehiculo)
RETURN
    nombre_buscado,
    p.nombre              AS nombre_encontrado,
    p.temp_min_c          AS temp_min_c,
    p.temp_opt_c          AS temp_opt_c,
    p.temp_max_c          AS temp_max_c,
    p.humedad_pct         AS humedad_pct,
    p.vida_util_dias      AS vida_util_dias,
    tv.tipo               AS tipo_vehiculo_requerido
"""

# Q2: Corredor vial entre ciudades.
# - Si $origen = '' → busca solo por destino (cuando el origen es desconocido,
#   ej. se extrae solo la ciudad del cliente desde su dirección).
# - Si $origen != '' → match AND pareado + soporte bidireccional.
_Q_CORREDOR = """
MATCH (c:Corredor)-[:ORIGEN]->(o:Ciudad)
MATCH (c)-[:DESTINO]->(d:Ciudad)
WHERE (
    $origen = '' AND (
        toLower(d.nombre) CONTAINS toLower($destino)
        OR toLower(o.nombre) CONTAINS toLower($destino)
    )
) OR (
    $origen <> '' AND (
        (toLower(o.nombre) CONTAINS toLower($origen)
         AND toLower(d.nombre) CONTAINS toLower($destino))
        OR
        (toLower(o.nombre) CONTAINS toLower($destino)
         AND toLower(d.nombre) CONTAINS toLower($origen))
    )
)
RETURN
    c.id                        AS id,
    c.nombre                    AS nombre,
    c.distancia_km              AS distancia_km,
    c.tiempo_estimado_min_carga AS tiempo_estimado_min_carga,
    c.estado_general            AS estado_general,
    c.estado_general_carga      AS estado_general_carga,
    c.impacto_min_carga         AS impacto_min_carga,
    c.es_critico                AS es_critico,
    o.nombre                    AS ciudad_origen,
    d.nombre                    AS ciudad_destino
ORDER BY c.distancia_km ASC
LIMIT 3
"""

# Q3: Tarifas y peajes de un corredor para ciertas categorías vehiculares
_Q_TARIFAS = """
MATCH (c:Corredor {id: $corredor_id})
OPTIONAL MATCH (t:Tarifa)-[:APLICA_A]->(c)
OPTIONAL MATCH (t)-[:APLICA_CONFIG]->(cfg:ConfiguracionVehicular)
WHERE cfg IS NULL OR cfg.categoria_peaje IN $categorias_peaje
RETURN
    t.id            AS tarifa_id,
    t.valor_cop     AS valor_cop,
    t.tipo_carga    AS tipo_carga,
    t.vigencia      AS vigencia,
    cfg.nombre      AS configuracion,
    cfg.categoria_peaje AS categoria_peaje
LIMIT 20
"""

# Q4: Normativa aplicable a los tipos de vehículo dados
_Q_NORMATIVA = """
OPTIONAL MATCH (n:Normativa)-[:REGULA]->(tv:TipoVehiculo)
WHERE tv.tipo IN $tipos_vehiculo
WITH n, collect(tv.tipo) AS tipos_regulados
WHERE n IS NOT NULL
OPTIONAL MATCH (n)-[:CONTIENE]->(a:Articulo)
WITH n, tipos_regulados, collect(a.cita_textual)[0..3] AS citas
RETURN
    n.numero            AS numero,
    n.nombre            AS nombre,
    n.anno              AS anno,
    n.entidad_emisora   AS entidad_emisora,
    tipos_regulados,
    citas               AS articulos_clave
"""


class Neo4jAdapter(GraphRepository):

    def __init__(self, uri: str, user: str, password: str) -> None:
        logger.info("Conectando a Neo4j en %s", uri)
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._driver.verify_connectivity()

    # ── Implementación del puerto ─────────────────────────────

    def get_requisitos_productos(self, nombres: list[str]) -> list[dict]:
        if not nombres:
            return []
        with self._driver.session() as session:
            result = session.run(_Q_REQUISITOS, nombres=nombres)
            return [dict(r) for r in result]

    def get_corredor(self, origen: str, destino: str) -> dict | None:
        with self._driver.session() as session:
            result = session.run(_Q_CORREDOR, origen=origen, destino=destino)
            rows = [dict(r) for r in result]
        return rows[0] if rows else None

    def get_tarifas_corredor(
        self, corredor_id: str, categorias_peaje: list[str]
    ) -> list[dict]:
        with self._driver.session() as session:
            result = session.run(
                _Q_TARIFAS,
                corredor_id=corredor_id,
                categorias_peaje=categorias_peaje,
            )
            return [dict(r) for r in result]

    def get_normativa_tipos(self, tipos_vehiculo: list[str]) -> list[dict]:
        if not tipos_vehiculo:
            return []
        with self._driver.session() as session:
            result = session.run(_Q_NORMATIVA, tipos_vehiculo=tipos_vehiculo)
            return [dict(r) for r in result]

    def close(self) -> None:
        self._driver.close()

    def __enter__(self) -> "Neo4jAdapter":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

