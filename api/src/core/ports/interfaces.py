"""
Puertos del núcleo hexagonal.
Interfaces abstractas que el núcleo define;
los adaptadores de salida las implementan.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


# ── Fragmento documental recuperado ─────────────────────────

@dataclass
class Fragmento:
    id: str
    contenido: str
    categoria: str          # products | fleet | routes | costs | regulations
    fuente: str
    score: float = 0.0
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


# ══════════════════════════════════════════════════════════════
# Puerto 1 – KnowledgeRepository
# ══════════════════════════════════════════════════════════════

class KnowledgeRepository(ABC):
    """Abstrae el acceso a la base de conocimiento.
    Oculta si la fuente es vectorial, grafo, o combinación."""

    @abstractmethod
    def search_semantic(
        self,
        query: str,
        k: int = 5,
        categoria: str | None = None,
    ) -> list[Fragmento]:
        """Búsqueda por similitud semántica."""
        ...

    @abstractmethod
    def upsert_chunk(
        self,
        chunk_id: str,
        contenido: str,
        categoria: str,
        fuente: str,
        metadata: dict | None = None,
    ) -> None:
        """Persiste o actualiza un fragmento documental."""
        ...

    @abstractmethod
    def list_by_category(self, categoria: str) -> list[Fragmento]:
        """Retorna todos los fragmentos de una categoría."""
        ...

    @abstractmethod
    def count(self) -> int:
        """Número total de fragmentos indexados."""
        ...


# ══════════════════════════════════════════════════════════════
# Puerto 2 – LLMProvider
# ══════════════════════════════════════════════════════════════

@dataclass
class LLMResponse:
    texto: str
    tokens_entrada: int
    tokens_salida: int
    modelo: str


class LLMProvider(ABC):
    """Abstrae la invocación al modelo de lenguaje.
    Desacopla al núcleo del proveedor y protocolo específico."""

    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1500,
    ) -> LLMResponse:
        """Genera una respuesta del LLM."""
        ...

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Estima la cantidad de tokens de un texto."""
        ...

    @property
    @abstractmethod
    def nombre_modelo(self) -> str:
        """Identificador del modelo activo."""
        ...


# ══════════════════════════════════════════════════════════════
# Puerto 3 – EmbeddingProvider
# ══════════════════════════════════════════════════════════════

class EmbeddingProvider(ABC):
    """Abstrae la vectorización de texto.
    Permite elegir entre modelos remotos y locales."""

    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        """Vectoriza un texto individual."""
        ...

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Vectoriza un lote de textos."""
        ...

    @abstractmethod
    def get_dimension(self) -> int:
        """Dimensión del vector de embedding."""
        ...
