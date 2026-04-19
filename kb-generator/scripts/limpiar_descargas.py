#!/usr/bin/env python3
"""
Limpia archivos inválidos en base_conocimiento/:

- Archivos con contenido corrupto (HTML en vez de PDF/XLS, magic bytes
  incorrectos, o tamaño sospechosamente pequeño).
- Archivos huérfanos: extensión PDF/XLS/XLSX presentes en disco pero sin
  entrada en el catálogo DOCUMENTOS del script de descarga.

Por defecto corre en modo DRY-RUN (solo reporta). Usa --borrar para eliminar.

Uso:
    python scripts/limpiar_descargas.py             # reporta
    python scripts/limpiar_descargas.py --borrar    # borra
"""

import argparse
import importlib.util
from pathlib import Path

BASE = Path("./base_conocimiento")
FUENTES = BASE / "fuentes"
CATALOGO_PY = Path("./scripts/descargar_base_conocimiento.py")

TAMANO_MIN_PDF = 10_000
TAMANO_MIN_EXCEL = 5_000

# Firmas de archivo reales
MAGIC_BYTES = {
    ".pdf": [b"%PDF-"],
    ".xlsx": [b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"],  # ZIP
    ".xls": [b"\xd0\xcf\x11\xe0"],  # OLE compound document
}

EXT_ANALIZADAS = (".pdf", ".xls", ".xlsx")


def cargar_registrados() -> set:
    """Importa DOCUMENTOS del script de descarga y retorna sus 'nombre'."""
    spec = importlib.util.spec_from_file_location("catalogo", CATALOGO_PY)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return {doc["nombre"] for doc in modulo.DOCUMENTOS}


def analizar_archivo(archivo: Path, registrados: set) -> tuple:
    """Retorna (clasificacion, motivo). clasificacion in {ok, basura, huerfano}."""
    ext = archivo.suffix.lower()
    tamano = archivo.stat().st_size

    # Tamaño sospechosamente pequeño
    minimo = TAMANO_MIN_PDF if ext == ".pdf" else TAMANO_MIN_EXCEL
    if tamano < minimo:
        return ("basura", f"tamaño muy pequeño ({tamano} B, mín esperado {minimo} B)")

    # Magic bytes
    with open(archivo, "rb") as f:
        cabecera = f.read(16)
    firmas_validas = MAGIC_BYTES.get(ext, [])
    if not any(cabecera.startswith(m) for m in firmas_validas):
        return (
            "basura",
            f"magic bytes no son {ext} válido (hex: {cabecera[:8].hex()})",
        )

    # Huérfano: existe en disco pero no en catálogo
    if archivo.name not in registrados:
        return ("huerfano", "no está en DOCUMENTOS")

    return ("ok", "")


def main():
    parser = argparse.ArgumentParser(
        description="Reporta y opcionalmente elimina archivos inválidos/huérfanos."
    )
    parser.add_argument(
        "--borrar",
        action="store_true",
        help="Elimina los archivos inválidos. Sin este flag solo reporta.",
    )
    args = parser.parse_args()

    if not BASE.exists():
        print(f"No existe la carpeta base: {BASE.resolve()}")
        return 1
    if not CATALOGO_PY.exists():
        print(f"No existe el script de descarga: {CATALOGO_PY.resolve()}")
        return 1

    # Compatibilidad hacia atrás: si existe fuentes/ escaneamos ahí; si no, la raíz
    raiz_escaneo = FUENTES if FUENTES.exists() else BASE
    print(f"Escaneando: {raiz_escaneo.resolve()}")

    registrados = cargar_registrados()
    print(f"Catálogo DOCUMENTOS: {len(registrados)} entradas registradas\n")

    basura, huerfanos, validos = [], [], []
    for archivo in sorted(raiz_escaneo.rglob("*")):
        if not archivo.is_file():
            continue
        if archivo.suffix.lower() not in EXT_ANALIZADAS:
            continue
        clasif, motivo = analizar_archivo(archivo, registrados)
        if clasif == "basura":
            basura.append((archivo, motivo))
        elif clasif == "huerfano":
            huerfanos.append((archivo, motivo))
        else:
            validos.append(archivo)

    if validos:
        print(f"VÁLIDOS ({len(validos)}):")
        for a in validos:
            print(f"  ✓ {a.relative_to(BASE.parent)}")
        print()

    if basura:
        print(f"BASURA ({len(basura)}) — contenido inválido:")
        for a, motivo in basura:
            print(f"  ✗ {a.relative_to(BASE.parent)}")
            print(f"      {motivo}")
        print()

    if huerfanos:
        print(f"HUÉRFANOS ({len(huerfanos)}) — no están en el catálogo:")
        for a, _ in huerfanos:
            print(f"  ? {a.relative_to(BASE.parent)}")
        print()

    a_borrar = [a for a, _ in basura] + [a for a, _ in huerfanos]
    if not a_borrar:
        print("Nada que limpiar.")
        return 0

    if args.borrar:
        print(f"Eliminando {len(a_borrar)} archivo(s)...")
        for a in a_borrar:
            try:
                a.unlink()
                print(f"  ✓ {a.relative_to(BASE.parent)}")
            except OSError as e:
                print(f"  ✗ Error: {a} → {e}")
    else:
        print(f"DRY-RUN: {len(a_borrar)} archivo(s) serían eliminados.")
        print("Ejecuta con --borrar para hacerlo efectivo.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

