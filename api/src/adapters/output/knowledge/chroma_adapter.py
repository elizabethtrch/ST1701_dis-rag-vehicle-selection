"""
ChromaAdapter – adaptador de salida para ChromaDB (base vectorial).
Implementa el puerto KnowledgeRepository.
"""
from __future__ import annotations
import logging
import os
from src.core.ports.interfaces import EmbeddingProvider, Fragmento, KnowledgeRepository

logger = logging.getLogger(__name__)


class ChromaAdapter(KnowledgeRepository):

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        chroma_path: str = "./data/chroma_db",
        collection_name: str = "agro_transport",
    ) -> None:
        try:
            import chromadb
        except ImportError as exc:
            raise ImportError("Instala chromadb: pip install chromadb") from exc

        import chromadb
        os.makedirs(chroma_path, exist_ok=True)
        self._client = chromadb.PersistentClient(path=chroma_path)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._embeddings = embedding_provider
        logger.info(
            "ChromaDB inicializado en '%s', colección '%s'. Fragmentos: %d",
            chroma_path, collection_name, self._collection.count(),
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
        where = {"categoria": categoria} if categoria else None

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
        ids = results["ids"][0]
        docs = results["documents"][0]
        metas = results["metadatas"][0]
        dists = results["distances"][0]

        for fid, doc, meta, dist in zip(ids, docs, metas, dists):
            fragmentos.append(
                Fragmento(
                    id=fid,
                    contenido=doc,
                    categoria=meta.get("categoria", ""),
                    fuente=meta.get("fuente", ""),
                    score=1.0 - dist,   # cosine distance → similarity
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
        meta = {"categoria": categoria, "fuente": fuente}
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
            where={"categoria": categoria},
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
                    categoria=meta.get("categoria", ""),
                    fuente=meta.get("fuente", ""),
                    metadata=meta,
                )
            )
        return fragmentos

    def count(self) -> int:
        return self._collection.count()
