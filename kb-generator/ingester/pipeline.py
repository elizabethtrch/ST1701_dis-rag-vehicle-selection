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
from .mappers.normativa import upsert_normativa
from .mappers.producto import upsert_productos
from .mappers.tarifa import upsert_tarifas

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
        _ingest_normativas(neo, stats)
        _ingest_productos(neo, stats)
        _ingest_tarifas(neo, stats)
        _ingest_mds(chroma, cfg, stats)

    logger.info(
        "Ingesta completa: %d docs/normativas, %d corredores, %d chunks (chroma=%d), %d errores",
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


def _ingest_normativas(neo: Neo4jClient, stats: dict) -> None:
    normativa_path = ESTRUCTURADOS / "05_normativa_transporte"
    if not normativa_path.exists():
        logger.warning("%s no existe; salto normativas", normativa_path)
        return

    mds = list(normativa_path.glob("*.md"))
    logger.info("Cargando %d normativas → (:Normativa) + relaciones", len(mds))

    with neo.session() as session:
        for md_path in mds:
            try:
                upsert_normativa(session, md_path)
                stats["documentos"] += 1
                logger.info("  ✓ normativa %s", md_path.name)
            except Exception as exc:
                logger.error("Normativa %s: %s", md_path.name, exc)
                stats["errores"] += 1


def _ingest_productos(neo: Neo4jClient, stats: dict) -> None:
    fichas_path = ESTRUCTURADOS / "01_fichas_tecnicas_productos"
    if not fichas_path.exists():
        logger.warning("%s no existe; salto productos", fichas_path)
        return

    mds = list(fichas_path.glob("*.md"))
    logger.info("Cargando productos desde %d fichas técnicas → (:Producto)", len(mds))

    with neo.session() as session:
        for md_path in mds:
            try:
                n = upsert_productos(session, md_path)
                stats["documentos"] += n
                logger.info("  ✓ %s → %d productos", md_path.name, n)
            except Exception as exc:
                logger.error("Ficha %s: %s", md_path.name, exc)
                stats["errores"] += 1


def _ingest_tarifas(neo: Neo4jClient, stats: dict) -> None:
    sicetac_json = (
        ESTRUCTURADOS / "04_tarifas_costos_transporte"
        / "mintransporte_sicetac_peajes_por_rutas_con_tarifas.json"
    )
    if not sicetac_json.exists():
        logger.warning("%s no existe; salto tarifas SICE-TAC", sicetac_json)
        return

    logger.info("Cargando tarifas SICE-TAC → (:Tarifa)-[:APLICA_A]->(:Corredor)")
    with neo.session() as session:
        try:
            n = upsert_tarifas(session, sicetac_json, INVIAS_PATH)
            stats["documentos"] += n
            logger.info("  ✓ %d tarifas SICE-TAC vinculadas a corredores", n)
        except Exception as exc:
            logger.error("Tarifas SICE-TAC: %s", exc)
            stats["errores"] += 1


def _ingest_mds(chroma: ChromaClient, cfg: Config, stats: dict, root: Path | None = None) -> None:
    search_root = root or ESTRUCTURADOS
    if not search_root.exists():
        logger.warning("%s no existe; salto MDs", search_root)
        return

    mds = list(search_root.rglob("*.md"))
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


def ingest_single_file(path: Path, config: Config | None = None) -> dict:
    """Ingesta un único archivo en Chroma y/o Neo4j.

    - .json con 'invias' en el nombre → corredores INVIAS a Neo4j.
    - .md → chunks a Chroma (con frontmatter como metadata).
    """
    cfg = config or Config.from_env()
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    stats = {"documentos": 0, "corredores": 0, "chunks": 0, "errores": 0}
    chroma = ChromaClient(
        cfg.chroma_host, cfg.chroma_port, cfg.chroma_collection, cfg.embedding_model
    )

    suffix = path.suffix.lower()
    with Neo4jClient(cfg.neo4j_uri, cfg.neo4j_user, cfg.neo4j_password) as neo:
        if suffix == ".json" and "invias" in path.name.lower():
            snap = load_invias(path)
            with neo.session() as session:
                for corredor in snap.corredores:
                    try:
                        upsert_corredor(session, corredor)
                        stats["corredores"] += 1
                    except Exception as exc:
                        logger.error("Corredor %s: %s", corredor.get("id"), exc)
                        stats["errores"] += 1
        elif suffix == ".md":
            try:
                doc = load_md(path)
                categoria = doc.frontmatter.get("categoria_rag", "")
                fuente = doc.frontmatter.get("fuente") or path.name
                chunks = chunk_text(doc.body, cfg.chunk_size, cfg.chunk_overlap)
                if chunks:
                    ids = [f"{path.stem}-{i:04d}" for i in range(len(chunks))]
                    metas = [
                        {
                            "categoria_rag": categoria,
                            "fuente": fuente,
                            "archivo": path.name,
                            "chunk_idx": i,
                        }
                        for i in range(len(chunks))
                    ]
                    chroma.upsert(ids=ids, contenidos=chunks, metadatas=metas)
                    stats["chunks"] += len(chunks)
            except Exception as exc:
                logger.error("MD %s: %s", path.name, exc)
                stats["errores"] += 1
        else:
            raise ValueError(f"Tipo no soportado: {suffix}. Se esperaba .md o .json INVIAS")

    return stats


def ingest_categoria(categoria_slug: str, config: Config | None = None) -> dict:
    """Borra chunks Chroma de `categoria_slug` y re-ingesta sus MDs.

    Los nodos Neo4j no se borran: MERGE es idempotente.
    """
    cfg = config or Config.from_env()
    stats = {"documentos": 0, "corredores": 0, "chunks": 0, "errores": 0}

    chroma = ChromaClient(
        cfg.chroma_host, cfg.chroma_port, cfg.chroma_collection, cfg.embedding_model
    )
    deleted = chroma.delete_by_categoria(categoria_slug)
    logger.info("Eliminados %d chunks de '%s'", deleted, categoria_slug)

    cat_path = _find_categoria_path(categoria_slug)
    if cat_path is None:
        logger.warning("No se encontró carpeta para categoría '%s'", categoria_slug)
        return stats

    _ingest_mds(chroma, cfg, stats, root=cat_path)
    return stats


def get_stats(config: Config | None = None) -> dict:
    """Retorna conteos de elementos indexados en Chroma y Neo4j."""
    cfg = config or Config.from_env()

    chroma = ChromaClient(
        cfg.chroma_host, cfg.chroma_port, cfg.chroma_collection, cfg.embedding_model
    )
    chroma_total = chroma.count()

    neo4j_counts: dict = {}
    with Neo4jClient(cfg.neo4j_uri, cfg.neo4j_user, cfg.neo4j_password) as neo:
        with neo.session() as session:
            result = session.run(
                "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS total "
                "ORDER BY total DESC"
            )
            neo4j_counts = {r["label"]: r["total"] for r in result}

    return {"chroma": {"total": chroma_total}, "neo4j": neo4j_counts}


def _find_categoria_path(slug: str) -> Path | None:
    """Resuelve slug sin prefijo a carpeta en estructurados/."""
    if not ESTRUCTURADOS.exists():
        return None
    for folder in ESTRUCTURADOS.iterdir():
        if not folder.is_dir():
            continue
        # "01_fichas_tecnicas_productos" → "fichas_tecnicas_productos"
        parts = folder.name.split("_", 1)
        folder_slug = parts[1] if parts[0].isdigit() and len(parts) > 1 else folder.name
        if folder_slug == slug:
            return folder
    return None


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s"
    )
    stats = ingest_all()
    return 1 if stats["errores"] else 0


if __name__ == "__main__":
    sys.exit(main())

