"""Configuración del ingester leída de variables de entorno.

Si existe un `.env` en la raíz del repo (misma ubicación que
`docker-compose.yml`), se carga automáticamente gracias a
`python-dotenv`. Los defaults apuntan a `docker compose up` local.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv

    _root_env = Path(__file__).resolve().parents[2] / ".env"
    if _root_env.exists():
        load_dotenv(_root_env, override=False)
except ImportError:
    pass


@dataclass(frozen=True)
class Config:
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    chroma_host: str
    chroma_port: int
    chroma_collection: str
    embedding_model: str
    chunk_size: int
    chunk_overlap: int

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
            neo4j_password=os.getenv("NEO4J_PASSWORD", "neo4jpass"),
            chroma_host=os.getenv("CHROMA_HOST", "localhost"),
            chroma_port=int(os.getenv("CHROMA_PORT", "8001")),
            chroma_collection=os.getenv("CHROMA_COLLECTION", "agro_transport"),
            embedding_model=os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
            chunk_size=int(os.getenv("CHUNK_SIZE", "800")),
            chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "80")),
        )

