"""Cliente HTTP de ChromaDB con embeddings locales (sentence-transformers)."""
from __future__ import annotations

import logging
from typing import Sequence

import chromadb
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class ChromaClient:
    def __init__(
        self,
        host: str,
        port: int,
        collection: str,
        embedding_model: str,
    ) -> None:
        logger.info("Conectando a Chroma en %s:%d", host, port)
        self._client = chromadb.HttpClient(
            host=host,
            port=port,
            settings=chromadb.Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=collection,
        )
        logger.info("Cargando modelo de embeddings: %s", embedding_model)
        self._embedder = SentenceTransformer(embedding_model)

    def upsert(
        self,
        ids: Sequence[str],
        contenidos: Sequence[str],
        metadatas: Sequence[dict],
    ) -> None:
        if not ids:
            return
        embeddings = self._embedder.encode(
            list(contenidos), convert_to_numpy=True
        ).tolist()
        self._collection.upsert(
            ids=list(ids),
            embeddings=embeddings,
            documents=list(contenidos),
            metadatas=list(metadatas),
        )

    def delete_by_fuente(self, fuente: str) -> int:
        """Borra todos los chunks cuya metadata.fuente == fuente."""
        existing = self._collection.get(where={"fuente": fuente})
        ids = existing.get("ids", [])
        if ids:
            self._collection.delete(ids=ids)
        return len(ids)

    def delete_by_categoria(self, categoria_slug: str) -> int:
        """Borra todos los chunks de una categoría (reindex selectivo)."""
        existing = self._collection.get(where={"categoria_rag": categoria_slug})
        ids = existing.get("ids", [])
        if ids:
            self._collection.delete(ids=ids)
        return len(ids)

    def count(self) -> int:
        return self._collection.count()

