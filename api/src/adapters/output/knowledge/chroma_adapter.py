"""
ChromaAdapter – adaptador de salida para ChromaDB vía HTTP.
Implementa el puerto KnowledgeRepository.
La base es compartida con kb-generator (ADR-0002 y ADR-0003).
"""
from __future__ import annotations

import logging
from src.core.ports.interfaces import EmbeddingProvider, Fragmento, KnowledgeRepository

logger = logging.getLogger(__name__)

# Clave de metadata usada por kb-generator al ingestar (ADR-0007)
_CAT_KEY = "categoria_rag"


class ChromaAdapter(KnowledgeRepository):

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        chroma_host: str = "localhost",
        chroma_port: int = 8001,
        collection_name: str = "agro_transport",
    ) -> None:
        try:
            import chromadb
        except ImportError as exc:
            raise ImportError("Instala chromadb: pip install chromadb") from exc

        import chromadb

        self._client = chromadb.HttpClient(
            host=chroma_host,
            port=chroma_port,
            settings=chromadb.Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
        )
        self._embeddings = embedding_provider
        logger.info(
            "ChromaDB HTTP en '%s:%d', colección '%s'. Fragmentos: %d",
            chroma_host, chroma_port, collection_name, self._collection.count(),
        )

    def search_semantic(
        self,
        query: str,
        k: int = 5,
        categoria: str | None = None,
    ) -> list[Fragmento]:
        if self._collection.count() == 0:
            logger.warning("La colección está vacía. Ejecuta la ingestión primero.")
            return []

        vector = self._embeddings.embed_text(query)
        where = {_CAT_KEY: categoria} if categoria else None

        try:
            results = self._collection.query(
                query_embeddings=[vector],
                n_results=min(k, self._collection.count()),
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            logger.error("Error en búsqueda ChromaDB: %s", exc)
            return []

        fragmentos = []
        for fid, doc, meta, dist in zip(
            results["ids"][0],
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            fragmentos.append(
                Fragmento(
                    id=fid,
                    contenido=doc,
                    categoria=meta.get(_CAT_KEY, meta.get("categoria", "")),
                    fuente=meta.get("fuente", ""),
                    score=1.0 - dist,
                    metadata=meta,
                )
            )
        return fragmentos

    def upsert_chunk(
        self,
        chunk_id: str,
        contenido: str,
        categoria: str,
        fuente: str,
        metadata: dict | None = None,
    ) -> None:
        vector = self._embeddings.embed_text(contenido)
        meta = {_CAT_KEY: categoria, "fuente": fuente}
        if metadata:
            meta.update(metadata)
        self._collection.upsert(
            ids=[chunk_id],
            embeddings=[vector],
            documents=[contenido],
            metadatas=[meta],
        )

    def list_by_category(self, categoria: str) -> list[Fragmento]:
        results = self._collection.get(
            where={_CAT_KEY: categoria},
            include=["documents", "metadatas"],
        )
        fragmentos = []
        for fid, doc, meta in zip(
            results["ids"], results["documents"], results["metadatas"]
        ):
            fragmentos.append(
                Fragmento(
                    id=fid,
                    contenido=doc,
                    categoria=meta.get(_CAT_KEY, ""),
                    fuente=meta.get("fuente", ""),
                    metadata=meta,
                )
            )
        return fragmentos

    def count(self) -> int:
        return self._collection.count()

