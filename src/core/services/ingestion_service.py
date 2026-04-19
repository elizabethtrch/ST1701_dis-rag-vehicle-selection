"""
IngestionService – caso de uso de carga documental.
Pipeline: extracción → segmentación → vectorización → persistencia.
"""
from __future__ import annotations
import logging
import os
import uuid
from pathlib import Path
from src.core.ports.interfaces import KnowledgeRepository, EmbeddingProvider

logger = logging.getLogger(__name__)

# Categorías válidas de la base de conocimiento
CATEGORIAS = {
    "products":     "Fichas técnicas de productos agrícolas",
    "fleet":        "Catálogo de flota vehicular",
    "routes":       "Condiciones de rutas y vías",
    "costs":        "Tarifas y costos de transporte",
    "regulations":  "Normativa de transporte agrícola",
}


class IngestionService:

    def __init__(
        self,
        knowledge_repo: KnowledgeRepository,
        embedding_provider: EmbeddingProvider,
        chunk_size: int = 800,
        chunk_overlap: int = 80,
    ) -> None:
        self._repo = knowledge_repo
        self._embeddings = embedding_provider
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    def ingestar_directorio(self, base_path: str) -> dict:
        """Procesa todos los documentos bajo base_path/*/."""
        base = Path(base_path)
        stats = {"procesados": 0, "chunks": 0, "errores": 0}

        for categoria in CATEGORIAS:
            cat_path = base / categoria
            if not cat_path.exists():
                logger.warning("Directorio no encontrado: %s", cat_path)
                continue
            for archivo in cat_path.iterdir():
                if archivo.suffix.lower() in {".txt", ".md", ".json"}:
                    try:
                        n_chunks = self._procesar_archivo(archivo, categoria)
                        stats["procesados"] += 1
                        stats["chunks"] += n_chunks
                        logger.info("  ✓ %s → %d chunks", archivo.name, n_chunks)
                    except Exception as exc:
                        logger.error("  ✗ %s: %s", archivo.name, exc)
                        stats["errores"] += 1

        logger.info(
            "Ingestión completa: %d archivos, %d chunks, %d errores",
            stats["procesados"], stats["chunks"], stats["errores"],
        )
        return stats

    def ingestar_texto(
        self, texto: str, categoria: str, fuente: str
    ) -> int:
        """Ingesta un texto arbitrario directamente."""
        chunks = self._segmentar(texto)
        for chunk in chunks:
            chunk_id = str(uuid.uuid4())
            self._repo.upsert_chunk(
                chunk_id=chunk_id,
                contenido=chunk,
                categoria=categoria,
                fuente=fuente,
            )
        return len(chunks)

    # ── privados ─────────────────────────────────────────────

    def _procesar_archivo(self, path: Path, categoria: str) -> int:
        texto = self._extraer_texto(path)
        if not texto.strip():
            return 0
        chunks = self._segmentar(texto)
        for i, chunk in enumerate(chunks):
            chunk_id = f"{path.stem}_{i}_{uuid.uuid4().hex[:8]}"
            self._repo.upsert_chunk(
                chunk_id=chunk_id,
                contenido=chunk,
                categoria=categoria,
                fuente=path.name,
                metadata={"archivo": path.name, "chunk_idx": i},
            )
        return len(chunks)

    def _extraer_texto(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix in {".txt", ".md"}:
            return path.read_text(encoding="utf-8", errors="ignore")
        if suffix == ".json":
            import json
            data = json.loads(path.read_text(encoding="utf-8"))
            # Serializa el JSON como texto plano para indexarlo
            return json.dumps(data, ensure_ascii=False, indent=2)
        # Intentar PDF si pypdf disponible
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader
                reader = PdfReader(str(path))
                return "\n".join(
                    page.extract_text() or "" for page in reader.pages
                )
            except ImportError:
                logger.warning("pypdf no disponible; saltando %s", path.name)
                return ""
        return ""

    def _segmentar(self, texto: str) -> list[str]:
        """Segmentación simple por ventana deslizante sobre palabras."""
        palabras = texto.split()
        if not palabras:
            return []
        chunks = []
        inicio = 0
        while inicio < len(palabras):
            fin = inicio + self._chunk_size
            chunk = " ".join(palabras[inicio:fin])
            chunks.append(chunk)
            paso = self._chunk_size - self._chunk_overlap
            inicio += max(paso, 1)
        return chunks
