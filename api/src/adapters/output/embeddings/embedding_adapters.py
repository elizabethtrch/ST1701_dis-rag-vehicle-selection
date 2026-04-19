"""
SentenceTransformersAdapter – embeddings locales con sentence-transformers.
Implementa el puerto EmbeddingProvider.
"""
from __future__ import annotations
import logging
from src.core.ports.interfaces import EmbeddingProvider

logger = logging.getLogger(__name__)


class SentenceTransformersAdapter(EmbeddingProvider):

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ImportError(
                "Instala sentence-transformers: pip install sentence-transformers"
            ) from exc

        logger.info("Cargando modelo de embeddings: %s", model_name)
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(model_name)
        self._dim = self._model.get_sentence_embedding_dimension()
        logger.info("Modelo cargado. Dimensión: %d", self._dim)

    def embed_text(self, text: str) -> list[float]:
        return self._model.encode(text, convert_to_numpy=True).tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, convert_to_numpy=True).tolist()

    def get_dimension(self) -> int:
        return self._dim


class OpenAIEmbeddingAdapter(EmbeddingProvider):
    """Usa text-embedding-3-small de OpenAI."""

    def __init__(self, api_key: str | None = None, model: str = "text-embedding-3-small") -> None:
        import os
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError("Instala openai: pip install openai") from exc
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key or os.environ["OPENAI_API_KEY"])
        self._model = model

    def embed_text(self, text: str) -> list[float]:
        resp = self._client.embeddings.create(model=self._model, input=text)
        return resp.data[0].embedding

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        resp = self._client.embeddings.create(model=self._model, input=texts)
        return [d.embedding for d in resp.data]

    def get_dimension(self) -> int:
        return 1536  # text-embedding-3-small
