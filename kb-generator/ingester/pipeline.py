"""Orquestador del ingester: mueve datos de `base_conocimiento/` a Chroma + Neo4j.

Flujo actual (Fase 3 del plan de implementación):

  1. `metadata.json`                          → (:Documento) nodes
  2. `estructurados/03.../invias_corredores.json`
     → (:Corredor), (:Ciudad), (:Departamento) + relaciones
  3. `estructurados/**/*.md`                  → chunks en Chroma

Los mappers de producto/vehiculo/tarifa/normativa llegan con las
fases posteriores, cuando el agente estructurador haya producido
los MDs correspondientes.

Uso:
    python -m ingester.pipeline
"""
from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

from .chunker import chunk_text
from .clients.chroma_client import ChromaClient
from .clients.neo4j_client import Neo4jClient
from .config import Config
from .loaders.invias_loader import load_invias
from .loaders.md_loader import load_md
from .mappers.corredor import upsert_corredor
from .mappers.documento import upsert_documento

logger = logging.getLogger(__name__)

# Raíz de `base_conocimiento/`, relativa al root del repo.
# Se asume que el comando se corre desde `kb-generator/`.
BASE_PATH = Path("base_conocimiento")

INVIAS_PATH = (
    BASE_PATH / "estructurados" / "03_condiciones_rutas_vias" / "invias_corredores.json"
)
METADATA_PATH = BASE_PATH / "metadata.json"
ESTRUCTURADOS = BASE_PATH / "estructurados"


def ingest_all(config: Config | None = None) -> dict:
    cfg = config or Config.from_env()
    logger.info("Config: %s", {k: v for k, v in asdict(cfg).items() if "password" not in k})

    stats = {"documentos": 0, "corredores": 0, "chunks": 0, "errores": 0}

    chroma = ChromaClient(
        cfg.chroma_host, cfg.chroma_port, cfg.chroma_collection, cfg.embedding_model
    )

    with Neo4jClient(cfg.neo4j_uri, cfg.neo4j_user, cfg.neo4j_password) as neo:
        _ingest_documentos(neo, stats)
        _ingest_invias(neo, stats)
        _ingest_mds(chroma, cfg, stats)

    logger.info(
        "Ingesta completa: %d documentos, %d corredores, %d chunks (chroma=%d), %d errores",
        stats["documentos"],
        stats["corredores"],
        stats["chunks"],
        chroma.count(),
        stats["errores"],
    )
    return stats


def _ingest_documentos(neo: Neo4jClient, stats: dict) -> None:
    if not METADATA_PATH.exists():
        logger.warning("%s no existe; salto :Documento nodes", METADATA_PATH)
        return

    data = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    documentos = data.get("documentos", [])
    logger.info("Cargando %d entradas de metadata.json → (:Documento)", len(documentos))

    with neo.session() as session:
        for doc in documentos:
            try:
                upsert_documento(session, doc)
                stats["documentos"] += 1
            except Exception as exc:
                logger.error("Documento %s: %s", doc.get("id"), exc)
                stats["errores"] += 1


def _ingest_invias(neo: Neo4jClient, stats: dict) -> None:
    if not INVIAS_PATH.exists():
        logger.warning("%s no existe; salto corredores INVIAS", INVIAS_PATH)
        return

    snap = load_invias(INVIAS_PATH)
    logger.info("Cargando %d corredores INVIAS → (:Corredor)", len(snap.corredores))

    with neo.session() as session:
        for corredor in snap.corredores:
            try:
                upsert_corredor(session, corredor)
                stats["corredores"] += 1
            except Exception as exc:
                logger.error("Corredor %s: %s", corredor.get("id"), exc)
                stats["errores"] += 1


def _ingest_mds(chroma: ChromaClient, cfg: Config, stats: dict) -> None:
    if not ESTRUCTURADOS.exists():
        logger.warning("%s no existe; salto MDs", ESTRUCTURADOS)
        return

    mds = list(ESTRUCTURADOS.rglob("*.md"))
    if not mds:
        logger.info("No hay MDs estructurados aún; Chroma queda sin chunks")
        return

    logger.info("Procesando %d MDs → chunks Chroma", len(mds))
    for md_path in mds:
        try:
            doc = load_md(md_path)
            categoria = doc.frontmatter.get("categoria_rag", "")
            fuente = doc.frontmatter.get("fuente") or md_path.name
            chunks = chunk_text(doc.body, cfg.chunk_size, cfg.chunk_overlap)
            if not chunks:
                continue
            ids = [f"{md_path.stem}-{i:04d}" for i in range(len(chunks))]
            metadatas = [
                {
                    "categoria_rag": categoria,
                    "fuente": fuente,
                    "archivo": md_path.name,
                    "chunk_idx": i,
                }
                for i in range(len(chunks))
            ]
            chroma.upsert(ids=ids, contenidos=chunks, metadatas=metadatas)
            stats["chunks"] += len(chunks)
            logger.info("  ✓ %s → %d chunks", md_path.name, len(chunks))
        except Exception as exc:
            logger.error("MD %s: %s", md_path.name, exc)
            stats["errores"] += 1


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s"
    )
    stats = ingest_all()
    return 1 if stats["errores"] else 0


if __name__ == "__main__":
    sys.exit(main())

