"""
Config – configuración y ensamblado de dependencias.
Selecciona el adaptador correcto según variables de entorno.
"""
from __future__ import annotations
import logging
import os
from functools import lru_cache

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # LLM
    llm_provider: str = "anthropic"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-6"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    google_api_key: str = ""
    google_model: str = "gemini-1.5-flash"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"
    huggingface_api_key: str = ""
    huggingface_model: str = "mistralai/Mistral-7B-Instruct-v0.2"

    # Embeddings
    embedding_provider: str = "sentence_transformers"
    embedding_model: str = "all-MiniLM-L6-v2"

    # Knowledge
    knowledge_adapter: str = "chroma"
    chroma_path: str = "./data/chroma_db"
    chroma_collection: str = "agro_transport"
    knowledge_base_path: str = "./data/knowledge_base"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_secret_token: str = "dev-secret-token-change-in-prod"
    log_level: str = "INFO"

    # Ingestión
    chunk_size: int = 800
    chunk_overlap: int = 80

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


# ── Builders ──────────────────────────────────────────────────

def _build_embedding_provider(settings: Settings):
    provider = settings.embedding_provider.lower()
    if provider == "sentence_transformers":
        from src.adapters.output.embeddings.embedding_adapters import SentenceTransformersAdapter
        return SentenceTransformersAdapter(settings.embedding_model)
    if provider == "openai":
        from src.adapters.output.embeddings.embedding_adapters import OpenAIEmbeddingAdapter
        return OpenAIEmbeddingAdapter(settings.openai_api_key, settings.embedding_model)
    raise ValueError(f"Embedding provider desconocido: {provider}")


def _build_chroma_adapter(settings: Settings, embedding_provider):
    from src.adapters.output.knowledge.chroma_adapter import ChromaAdapter
    return ChromaAdapter(
        embedding_provider=embedding_provider,
        chroma_path=settings.chroma_path,
        collection_name=settings.chroma_collection,
    )


def _build_llm_provider(settings: Settings):
    provider = settings.llm_provider.lower()
    if provider == "anthropic":
        from src.adapters.output.llm.anthropic_adapter import AnthropicAdapter
        return AnthropicAdapter(settings.anthropic_api_key, settings.anthropic_model)
    if provider == "openai":
        from src.adapters.output.llm.openai_adapter import OpenAIAdapter
        return OpenAIAdapter(settings.openai_api_key, settings.openai_model)
    if provider == "google":
        from src.adapters.output.llm.other_adapters import GoogleAdapter
        return GoogleAdapter(settings.google_api_key, settings.google_model)
    if provider == "ollama":
        from src.adapters.output.llm.other_adapters import OllamaAdapter
        return OllamaAdapter(settings.ollama_base_url, settings.ollama_model)
    raise ValueError(f"LLM provider desconocido: {provider}")


def build_recommendation_service(settings: Settings):
    from src.core.services.recommendation_service import RecommendationService
    emb = _build_embedding_provider(settings)
    repo = _build_chroma_adapter(settings, emb)
    llm = _build_llm_provider(settings)
    return RecommendationService(knowledge_repo=repo, llm_provider=llm)


def build_recommendation_service_with_llm(settings: Settings, llm_provider: str):
    """Construye el servicio con el proveedor LLM especificado, ignorando el de settings."""
    from src.core.services.recommendation_service import RecommendationService

    override = settings.model_copy(update={"llm_provider": llm_provider})
    emb = _build_embedding_provider(settings)
    repo = _build_chroma_adapter(settings, emb)
    llm = _build_llm_provider(override)
    return RecommendationService(knowledge_repo=repo, llm_provider=llm)


def build_ingestion_service(settings: Settings):
    from src.core.services.ingestion_service import IngestionService
    emb = _build_embedding_provider(settings)
    repo = _build_chroma_adapter(settings, emb)
    return IngestionService(
        knowledge_repo=repo,
        embedding_provider=emb,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
