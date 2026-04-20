"""Loader para base_conocimiento/estructurados/03_.../invias_corredores.json."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class InviasSnapshot:
    metadata: dict
    corredores: list[dict]


def load_invias(path: Path) -> InviasSnapshot:
    data = json.loads(path.read_text(encoding="utf-8"))
    return InviasSnapshot(
        metadata=data.get("metadata", {}),
        corredores=data.get("corredores", []),
    )

