"""CLI del ingester RAG.

Subcomandos disponibles:

    ingest-all              Ingesta completa (metadata + INVIAS + MDs)
    ingest-file <path>      Documento suelto (.md o .json INVIAS)
    reindex                 Elimina + re-ingesta Chroma (toda o una categoría)
    stats                   Inventario indexado en Chroma y Neo4j

Uso:
    # Con el venv activado desde la raíz del repo:
    .venv/bin/ingester ingest-all
    .venv/bin/ingester ingest-file kb-generator/base_conocimiento/estructurados/03_.../invias_corredores.json
    .venv/bin/ingester reindex --categoria condiciones_rutas_vias
    .venv/bin/ingester stats

    # O vía make:
    make ingest-all
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .pipeline import get_stats, ingest_all, ingest_categoria, ingest_single_file

app = typer.Typer(
    name="ingester",
    help="Pipeline de ingesta de la base de conocimiento RAG.",
    no_args_is_help=True,
)
console = Console()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s | %(levelname)s | %(message)s")


@app.command("ingest-all")
def cmd_ingest_all(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Logs detallados"),
) -> None:
    """Ingesta completa: metadata.json + INVIAS + todos los MDs."""
    _setup_logging(verbose)
    stats = ingest_all()
    _print_stats_summary(stats)
    raise typer.Exit(1 if stats["errores"] else 0)


@app.command("ingest-file")
def cmd_ingest_file(
    path: Path = typer.Argument(..., help="Ruta al .md o .json INVIAS a ingestar"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Ingesta un documento suelto en Chroma y/o Neo4j."""
    _setup_logging(verbose)
    try:
        stats = ingest_single_file(path)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(1) from exc
    _print_stats_summary(stats)
    raise typer.Exit(1 if stats["errores"] else 0)


@app.command("reindex")
def cmd_reindex(
    categoria: Optional[str] = typer.Option(
        None,
        "--categoria",
        "-c",
        help="Slug de categoría (sin prefijo numérico). "
        "Omitir para re-ingestar todas las categorías.",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Elimina chunks en Chroma y re-ingesta (toda la base o solo una categoría)."""
    _setup_logging(verbose)
    if categoria:
        console.print(f"Reindexando categoría: [bold]{categoria}[/bold]")
        stats = ingest_categoria(categoria)
    else:
        console.print("Reindexando [bold]todas[/bold] las categorías")
        stats = ingest_all()
    _print_stats_summary(stats)
    raise typer.Exit(1 if stats["errores"] else 0)


@app.command("stats")
def cmd_stats() -> None:
    """Muestra el inventario indexado en ChromaDB y Neo4j."""
    logging.basicConfig(level=logging.WARNING)  # silencia info durante stats
    report = get_stats()

    # ── Chroma ─────────────────────────────────────────────────
    console.print(f"\n[bold]Chroma[/bold] — total chunks: {report['chroma']['total']}")

    # ── Neo4j ──────────────────────────────────────────────────
    neo4j = report.get("neo4j", {})
    if neo4j:
        table = Table(title="Neo4j — nodos por etiqueta")
        table.add_column("Etiqueta", style="cyan")
        table.add_column("Nodos", justify="right")
        for label, count in neo4j.items():
            table.add_row(label, str(count))
        console.print(table)
    else:
        console.print("[yellow]Neo4j sin nodos[/yellow]")


def _print_stats_summary(stats: dict) -> None:
    color = "red" if stats["errores"] else "green"
    console.print(
        f"[{color}]"
        f"documentos={stats['documentos']} "
        f"corredores={stats['corredores']} "
        f"chunks={stats['chunks']} "
        f"errores={stats['errores']}"
        f"[/{color}]"
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()

