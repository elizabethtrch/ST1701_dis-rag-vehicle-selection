"""
Batch CLI – adaptador de entrada para el pipeline de ingestión.
Invoca al IngestionService bajo demanda o desde tareas programadas.

Uso:
  python -m src.adapters.input.cli.ingest_cli ingest --path ./data/knowledge_base
  python -m src.adapters.input.cli.ingest_cli stats
  python -m src.adapters.input.cli.ingest_cli seed
"""
from __future__ import annotations
import logging
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from src.config import get_settings, build_ingestion_service

app = typer.Typer(
    name="ingest",
    help="Pipeline de ingestión de la base de conocimiento RAG.",
)
console = Console()
logger = logging.getLogger(__name__)


@app.command()
def ingest(
    path: str = typer.Option(
        "./data/knowledge_base",
        "--path", "-p",
        help="Ruta al directorio con las carpetas de categorías.",
    )
):
    """Procesa todos los documentos en el directorio y los indexa en ChromaDB."""
    settings = get_settings()
    service = build_ingestion_service(settings)

    console.print(f"\n[bold]Iniciando ingestión desde:[/bold] {path}\n")
    stats = service.ingestar_directorio(path)

    table = Table(title="Resultado de la ingestión")
    table.add_column("Métrica", style="cyan")
    table.add_column("Valor", justify="right")
    table.add_row("Archivos procesados", str(stats["procesados"]))
    table.add_row("Chunks generados", str(stats["chunks"]))
    table.add_row("Errores", str(stats["errores"]))
    console.print(table)


@app.command()
def stats(
    path: str = typer.Option("./data/chroma_db", "--db", help="Ruta a ChromaDB.")
):
    """Muestra estadísticas de la base de conocimiento indexada."""
    settings = get_settings()
    repo = _build_repo(settings)
    total = repo.count()
    console.print(f"\n[bold]Fragmentos indexados:[/bold] {total}\n")

    categorias = ["products", "fleet", "routes", "costs", "regulations"]
    table = Table(title="Fragmentos por categoría")
    table.add_column("Categoría", style="cyan")
    table.add_column("Fragmentos", justify="right")
    for cat in categorias:
        n = len(repo.list_by_category(cat))
        table.add_row(cat, str(n))
    console.print(table)


@app.command()
def seed():
    """Carga la base de conocimiento de ejemplo incluida en el proyecto."""
    settings = get_settings()
    service = build_ingestion_service(settings)
    seed_path = Path(__file__).parent.parent.parent.parent.parent / "data" / "knowledge_base"

    if not seed_path.exists():
        console.print(f"[red]No se encontró el directorio de datos: {seed_path}[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold]Cargando datos de ejemplo desde:[/bold] {seed_path}\n")
    stats = service.ingestar_directorio(str(seed_path))
    console.print(f"[green]✓ {stats['chunks']} chunks indexados desde {stats['procesados']} archivos.[/green]")


def _build_repo(settings):
    from src.config import _build_embedding_provider, _build_chroma_adapter
    emb = _build_embedding_provider(settings)
    return _build_chroma_adapter(settings, emb)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app()
