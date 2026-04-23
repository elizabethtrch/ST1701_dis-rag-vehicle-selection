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
    openai_temperature: float = 0.2
    openai_timeout: float = 60.0
    google_api_key: str = ""
    google_model: str = "gemini-2.0-flash-lite"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"
    ollama_temperature: float = 0.2
    ollama_top_p: float = 0.9
    ollama_top_k: int = 40
    ollama_repeat_penalty: float = 1.1
    huggingface_api_key: str = ""
    huggingface_model: str = "mistralai/Mistral-7B-Instruct-v0.2"

    # Embeddings
    embedding_provider: str = "sentence_transformers"
    embedding_model: str = "all-MiniLM-L6-v2"

    # Knowledge — ChromaDB HTTP (ADR-0002)
    knowledge_adapter: str = "chroma"
    chroma_host: str = "localhost"
    chroma_port: int = 8001
    chroma_collection: str = "agro_transport"

    # Knowledge — Neo4j Bolt (ADR-0002, ADR-0004)
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "neo4jpass"

    # Ingestión (legado — se elimina en Fase 8)
    knowledge_base_path: str = "./data/knowledge_base"

    # Observabilidad — Langfuse
    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3000"

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
        chroma_host=settings.chroma_host,
        chroma_port=settings.chroma_port,
        collection_name=settings.chroma_collection,
    )


def _build_neo4j_adapter(settings: Settings):
    from src.adapters.output.knowledge.neo4j_adapter import Neo4jAdapter
    return Neo4jAdapter(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
    )


def _build_llm_provider(settings: Settings):
    provider = settings.llm_provider.lower()
    if provider == "anthropic":
        from src.adapters.output.llm.anthropic_adapter import AnthropicAdapter
        return AnthropicAdapter(settings.anthropic_api_key, settings.anthropic_model)
    if provider == "openai":
        from src.adapters.output.llm.openai_adapter import OpenAIAdapter
        return OpenAIAdapter(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            temperature=settings.openai_temperature,
            timeout=settings.openai_timeout,
        )
    if provider == "google":
        from src.adapters.output.llm.google_adapter import GoogleAdapter
        return GoogleAdapter(settings.google_api_key, settings.google_model)
    if provider == "ollama":
        from src.adapters.output.llm.ollama_adapter import OllamaAdapter
        return OllamaAdapter(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            temperature=settings.ollama_temperature,
            top_p=settings.ollama_top_p,
            top_k=settings.ollama_top_k,
            repeat_penalty=settings.ollama_repeat_penalty,
        )
    raise ValueError(f"LLM provider desconocido: {provider}")


def _build_observability(settings: Settings):
    import logging
    _log = logging.getLogger(__name__)
    if not settings.langfuse_enabled:
        _log.info("Observabilidad: Langfuse DESACTIVADO (LANGFUSE_ENABLED=false)")
        from src.adapters.output.observability.langfuse_adapter import NullObservabilityAdapter
        return NullObservabilityAdapter()
    if not settings.langfuse_public_key:
        _log.warning("Observabilidad: LANGFUSE_ENABLED=true pero LANGFUSE_PUBLIC_KEY está vacío")
        from src.adapters.output.observability.langfuse_adapter import NullObservabilityAdapter
        return NullObservabilityAdapter()
    _log.info(
        "Observabilidad: Langfuse ACTIVO → host=%s public_key=%s...",
        settings.langfuse_host,
        settings.langfuse_public_key[:8],
    )
    from src.adapters.output.observability.langfuse_adapter import LangfuseAdapter
    return LangfuseAdapter(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )


def build_recommendation_service(settings: Settings):
    from src.core.services.recommendation_service import RecommendationService
    emb = _build_embedding_provider(settings)
    repo = _build_chroma_adapter(settings, emb)
    llm = _build_llm_provider(settings)
    graph = _build_neo4j_adapter(settings)
    obs = _build_observability(settings)
    return RecommendationService(knowledge_repo=repo, llm_provider=llm, graph_repo=graph, observability=obs)


def build_recommendation_service_with_llm(settings: Settings, llm_provider: str):
    """Construye el servicio con el proveedor LLM especificado, ignorando el de settings."""
    from src.core.services.recommendation_service import RecommendationService

    override = settings.model_copy(update={"llm_provider": llm_provider})
    emb = _build_embedding_provider(settings)
    repo = _build_chroma_adapter(settings, emb)
    llm = _build_llm_provider(override)
    graph = _build_neo4j_adapter(settings)
    obs = _build_observability(settings)
    return RecommendationService(knowledge_repo=repo, llm_provider=llm, graph_repo=graph, observability=obs)


