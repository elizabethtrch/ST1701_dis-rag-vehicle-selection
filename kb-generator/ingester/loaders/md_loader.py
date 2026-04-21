"""Parser de Markdown con YAML frontmatter (PLANTILLAS 1-5 del SKILL)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class MarkdownDocument:
    path: Path
    frontmatter: dict
    body: str


def load_md(path: Path) -> MarkdownDocument:
    text = path.read_text(encoding="utf-8")

    # Formato esperado:
    #   ---\n<yaml>\n---\n<body>
    if not text.startswith("---"):
        return MarkdownDocument(path=path, frontmatter={}, body=text)

    # split en 3 partes: "", yaml, body
    parts = text.split("---", 2)
    if len(parts) < 3:
        return MarkdownDocument(path=path, frontmatter={}, body=text)

    frontmatter = yaml.safe_load(parts[1]) or {}
    if not isinstance(frontmatter, dict):
        frontmatter = {}
    body = parts[2].lstrip("\n").rstrip()

    return MarkdownDocument(path=path, frontmatter=frontmatter, body=body)

