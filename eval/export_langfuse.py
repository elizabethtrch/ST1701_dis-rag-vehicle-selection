"""
Exporta trazas + scores desde Langfuse (self-hosted) a CSV y JSON.

Uso:
    python eval/export_langfuse.py --env api/.env
    python eval/export_langfuse.py --env api/.env --output eval/export --limit 200
    python eval/export_langfuse.py --env api/.env --format json
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Permite importar desde api/src sin instalar el paquete
sys.path.insert(0, str(Path(__file__).parent.parent / "api"))

from src.core.ports.interfaces import SCORE_KEYS

# Nombres históricos que se normalizan al nombre canónico actual.
# Agregar aquí cualquier rename futuro para mantener compatibilidad con trazas antiguas.
_SCORE_ALIASES: dict[str, str] = {
    "completitud": "completitud_alternativas",
}


def _cargar_env(env_path: str) -> dict[str, str]:
    cfg: dict[str, str] = {}
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            cfg[k.strip()] = v.strip().strip('"').strip("'")
    return cfg


def _build_client(cfg: dict):
    enabled = cfg.get("LANGFUSE_ENABLED", "false").lower()
    if enabled != "true":
        print("✗  LANGFUSE_ENABLED no es 'true' en el .env. Abortando.")
        sys.exit(1)

    pk = cfg.get("LANGFUSE_PUBLIC_KEY", "")
    sk = cfg.get("LANGFUSE_SECRET_KEY", "")
    host = cfg.get("LANGFUSE_HOST", "http://localhost:3000")

    if not pk or not sk:
        print("✗  Faltan LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY en el .env.")
        sys.exit(1)

    os.environ.setdefault("LANGFUSE_SDK_TELEMETRY_DISABLED", "true")

    try:
        from langfuse import Langfuse
    except ImportError:
        print("✗  langfuse no instalado. Corre: pip install 'langfuse>=2,<3'")
        sys.exit(1)

    return Langfuse(public_key=pk, secret_key=sk, host=host)


def _fetch_all_traces(client, limit: int) -> list:
    """Descarga trazas con scores completos usando get_trace por cada ID.

    fetch_traces() devuelve solo IDs de scores; get_trace() devuelve objetos
    Score_Numeric completos con name y value.
    """
    page = 1
    page_size = 50
    ids: list[str] = []
    print(f"Descargando IDs de trazas desde Langfuse (límite={limit})…")
    while len(ids) < limit:
        resp = client.fetch_traces(page=page, limit=page_size)
        batch = resp.data
        if not batch:
            break
        ids.extend(t.id for t in batch)
        print(f"  página {page}: {len(batch)} trazas ({len(ids)} total)")
        if len(batch) < page_size:
            break
        page += 1
    ids = ids[:limit]

    trazas = []
    print(f"Descargando detalle de {len(ids)} trazas…")
    for i, tid in enumerate(ids, 1):
        t = client.get_trace(tid)
        trazas.append(t)
        if i % 10 == 0 or i == len(ids):
            print(f"  {i}/{len(ids)} trazas descargadas")
    return trazas


def _flatten(trazas: list) -> list[dict]:
    """Aplana cada traza en un dict con scores como columnas.

    Normaliza nombres históricos mediante _SCORE_ALIASES para que trazas
    antiguas y nuevas queden en las mismas columnas canónicas.
    """
    rows = []
    score_keys: set[str] = set()

    for t in trazas:
        row: dict = {
            "trace_id": t.id,
            "timestamp": t.timestamp.isoformat() if t.timestamp else "",
            "solicitud_id": (t.input or {}).get("solicitud_id", ""),
            "vehiculo_seleccionado": (t.output or {}).get("vehiculo_seleccionado", ""),
            "fragmentos": (t.metadata or {}).get("fragmentos", ""),
            "requiere_refrigeracion": (t.metadata or {}).get("requiere_refrigeracion", ""),
            "peso_total_kg": (t.metadata or {}).get("peso_total_kg", ""),
        }
        for s in (t.scores or []):
            name = _SCORE_ALIASES.get(s.name, s.name)
            row[name] = s.value
            score_keys.add(name)
        rows.append(row)

    # Garantiza que todas las columnas canónicas existan en cada fila
    all_keys = score_keys | set(SCORE_KEYS)
    for row in rows:
        for k in all_keys:
            row.setdefault(k, None)

    return rows


def _guardar_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        print("Sin datos para exportar.")
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"✓  CSV guardado → {path}")


def _guardar_json(rows: list[dict], path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2, default=str)
    print(f"✓  JSON guardado → {path}")


def _imprimir_resumen(rows: list[dict]) -> None:
    if not rows:
        return

    score_cols = [k for k in rows[0] if k not in {
        "trace_id", "timestamp", "solicitud_id",
        "vehiculo_seleccionado", "fragmentos",
        "requiere_refrigeracion", "peso_total_kg",
    }]

    print(f"\n{'─'*55}")
    print(f"  Trazas exportadas : {len(rows)}")

    for col in sorted(score_cols):
        vals = [r[col] for r in rows if r.get(col) is not None]
        if not vals:
            continue
        promedio = sum(vals) / len(vals)
        minv = min(vals)
        maxv = max(vals)
        print(f"  {col:<32} avg={promedio:.2f}  min={minv:.1f}  max={maxv:.1f}")

    vehiculos = [r["vehiculo_seleccionado"] for r in rows if r.get("vehiculo_seleccionado")]
    if vehiculos:
        from collections import Counter
        top = Counter(vehiculos).most_common(5)
        print(f"\n  Vehículos más recomendados:")
        for veh, n in top:
            print(f"    {veh}: {n}x")
    print(f"{'─'*55}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Exporta trazas + scores desde Langfuse")
    parser.add_argument("--env", default="api/.env", help="Ruta al archivo .env")
    parser.add_argument("--output", default="eval/langfuse_export",
                        help="Prefijo de salida (sin extensión)")
    parser.add_argument("--format", choices=["csv", "json", "both"], default="both",
                        help="Formato de exportación (default: both)")
    parser.add_argument("--limit", type=int, default=500,
                        help="Máximo de trazas a descargar (default: 500)")
    args = parser.parse_args()

    cfg = _cargar_env(args.env)
    client = _build_client(cfg)

    trazas = _fetch_all_traces(client, args.limit)
    if not trazas:
        print("No se encontraron trazas en Langfuse.")
        return

    rows = _flatten(trazas)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"{out}_{ts}"

    if args.format in ("csv", "both"):
        _guardar_csv(rows, Path(f"{stem}.csv"))
    if args.format in ("json", "both"):
        _guardar_json(rows, Path(f"{stem}.json"))

    _imprimir_resumen(rows)


if __name__ == "__main__":
    main()

