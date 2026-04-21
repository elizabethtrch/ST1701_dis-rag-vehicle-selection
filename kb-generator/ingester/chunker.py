"""Ventana deslizante sobre palabras para generar chunks semánticos."""
from __future__ import annotations


def chunk_text(
    texto: str, chunk_size: int = 800, chunk_overlap: int = 80
) -> list[str]:
    palabras = texto.split()
    if not palabras:
        return []

    paso = max(chunk_size - chunk_overlap, 1)
    chunks: list[str] = []
    inicio = 0
    while inicio < len(palabras):
        fin = inicio + chunk_size
        chunks.append(" ".join(palabras[inicio:fin]))
        if fin >= len(palabras):
            break
        inicio += paso
    return chunks

