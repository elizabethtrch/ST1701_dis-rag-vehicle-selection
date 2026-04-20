"""Verifica que el schema Neo4j esté completo.

Compara los nombres de CONSTRAINTS e INDEXES vivos en el servidor
contra los que debería haber creado schema.cypher. Falla con exit 1
si alguno falta.

Uso:
    python -m ingester.verify_schema
"""
from __future__ import annotations

import logging
import os
import sys

from neo4j import GraphDatabase

logger = logging.getLogger(__name__)

EXPECTED_CONSTRAINTS = {
    "producto_nombre_uq",
    "tipo_vehiculo_tipo_uq",
    "configuracion_vehicular_nombre_uq",
    "vehiculo_matricula_uq",
    "corredor_id_uq",
    "ciudad_nombre_uq",
    "departamento_nombre_uq",
    "tarifa_id_uq",
    "peaje_id_uq",
    "articulo_id_uq",
    "normativa_numero_uq",
    "documento_id_uq",
}

EXPECTED_INDEXES = {
    "producto_categoria_rag",
    "documento_categoria",
    "corredor_es_critico",
    "tarifa_origen_destino",
    "peaje_categoria_vehicular",
    "configuracion_categoria_peaje",
}


def verify(uri: str, user: str, password: str) -> dict:
    with GraphDatabase.driver(uri, auth=(user, password)) as driver:
        driver.verify_connectivity()
        with driver.session() as session:
            constraints = {r["name"] for r in session.run("SHOW CONSTRAINTS YIELD name").data()}
            # SHOW INDEXES incluye los implicitos de UNIQUE + los explicitos.
            # verify_schema solo se preocupa por los que creamos a proposito.
            indexes = {r["name"] for r in session.run("SHOW INDEXES YIELD name").data()}

    return {
        "constraints_missing": sorted(EXPECTED_CONSTRAINTS - constraints),
        "constraints_found": sorted(EXPECTED_CONSTRAINTS & constraints),
        "indexes_missing": sorted(EXPECTED_INDEXES - indexes),
        "indexes_found": sorted(EXPECTED_INDEXES & indexes),
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "neo4jpass")

    logger.info("Verificando schema Neo4j en %s", uri)
    report = verify(uri, user, password)

    n_c = len(report["constraints_found"])
    t_c = len(EXPECTED_CONSTRAINTS)
    n_i = len(report["indexes_found"])
    t_i = len(EXPECTED_INDEXES)
    logger.info("Constraints: %d/%d", n_c, t_c)
    logger.info("Indexes:     %d/%d", n_i, t_i)

    for name in report["constraints_missing"]:
        logger.error("  ✗ falta constraint: %s", name)
    for name in report["indexes_missing"]:
        logger.error("  ✗ falta index: %s", name)

    ok = not report["constraints_missing"] and not report["indexes_missing"]
    if ok:
        logger.info("Schema COMPLETO")
        return 0
    logger.error("Schema INCOMPLETO — corre `make schema-init` para aplicarlo")
    return 1


if __name__ == "__main__":
    sys.exit(main())

