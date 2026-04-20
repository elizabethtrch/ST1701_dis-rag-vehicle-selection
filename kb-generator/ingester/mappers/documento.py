"""Mapper de `metadata.json` → (:Documento).

Proveniencia documental: cada chunk en Chroma y cada nodo del grafo
debería poder trazar su origen a un :Documento.
"""
from __future__ import annotations


DOCUMENTO_UPSERT = """
MERGE (d:Documento {id: $id})
SET d.nombre_archivo = $nombre_archivo,
    d.categoria      = $categoria,
    d.fuente         = $fuente,
    d.url            = $url,
    d.sha256         = $sha256,
    d.anno           = $anno,
    d.tipo           = $tipo
"""


def upsert_documento(session, meta: dict) -> None:
    """Inserta o actualiza un (:Documento) a partir de una entrada de metadata.json.

    Valida en Python que `categoria` exista, ya que Neo4j Community
    no soporta `IS NOT NULL` (ver ADR-0008).
    """
    if not meta.get("id"):
        raise ValueError("metadata.json: entrada sin 'id'")
    if not meta.get("categoria"):
        raise ValueError(f"metadata.json: {meta['id']} sin 'categoria'")

    session.run(
        DOCUMENTO_UPSERT,
        id=meta["id"],
        nombre_archivo=meta.get("nombre"),
        categoria=_strip_num_prefix(meta["categoria"]),
        fuente=meta.get("fuente"),
        url=meta.get("url"),
        sha256=meta.get("sha256"),
        anno=meta.get("anno"),
        tipo=meta.get("tipo"),
    ).consume()


def _strip_num_prefix(categoria: str) -> str:
    # ADR-0007: en el grafo guardamos el slug sin prefijo numerico.
    # "01_fichas_tecnicas_productos" -> "fichas_tecnicas_productos"
    parts = categoria.split("_", 1)
    if parts[0].isdigit() and len(parts) > 1:
        return parts[1]
    return categoria

