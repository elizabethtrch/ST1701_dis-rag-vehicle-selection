"""Wrapper thin sobre el driver Neo4j con context manager de sesiones."""
from __future__ import annotations

import logging
from contextlib import contextmanager

from neo4j import GraphDatabase

logger = logging.getLogger(__name__)


class Neo4jClient:
    def __init__(self, uri: str, user: str, password: str) -> None:
        logger.info("Conectando a Neo4j en %s", uri)
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._driver.verify_connectivity()

    @contextmanager
    def session(self):
        with self._driver.session() as session:
            yield session

    def close(self) -> None:
        self._driver.close()

    def __enter__(self) -> "Neo4jClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

