"""Aplica schema.cypher al contenedor Neo4j.

Idempotente: las declaraciones usan CREATE CONSTRAINT/INDEX ...
IF NOT EXISTS, por lo que ejecutarlo multiples veces no rompe nada.

Uso:
    python -m ingester.init_schema
    # o con credenciales explicitas
    NEO4J_URI=bolt://localhost:7687 \\
    NEO4J_USER=neo4j NEO4J_PASSWORD=neo4jpass \\
        python -m ingester.init_schema
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from neo4j import GraphDatabase

logger = logging.getLogger(__name__)

SCHEMA_FILE = Path(__file__).parent / "schema.cypher"


def _split_statements(cypher: str) -> list[str]:
    """Parte el .cypher en declaraciones separadas por ';', ignora comentarios."""
    statements: list[str] = []
    for raw in cypher.split(";"):
        lines = [
            ln for ln in raw.splitlines()
            if ln.strip() and not ln.strip().startswith("//")
        ]
        if lines:
            statements.append("\n".join(lines).strip())
    return statements


def apply_schema(uri: str, user: str, password: str) -> dict:
    """Ejecuta cada statement del schema y reporta conteos."""
    cypher = SCHEMA_FILE.read_text(encoding="utf-8")
    statements = _split_statements(cypher)

    applied = 0
    failed = 0
    with GraphDatabase.driver(uri, auth=(user, password)) as driver:
        driver.verify_connectivity()
        with driver.session() as session:
            for stmt in statements:
                try:
                    session.run(stmt).consume()
                    applied += 1
                    logger.debug("OK: %s", stmt.splitlines()[0])
                except Exception as exc:
                    logger.error("FALLO: %s\n  %s", stmt.splitlines()[0], exc)
                    failed += 1
    return {"applied": applied, "failed": failed, "total": len(statements)}


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "neo4jpass")

    logger.info("Aplicando schema Neo4j en %s", uri)
    stats = apply_schema(uri, user, password)
    logger.info(
        "Schema: %d/%d statements OK (fallados: %d)",
        stats["applied"],
        stats["total"],
        stats["failed"],
    )
    return 1 if stats["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())

