#!/usr/bin/env python3
"""
Validador determinístico de la base de conocimiento del RAG.

Valida:
- Archivos Markdown por categoría (YAML frontmatter, campos obligatorios,
  sección "Fragmentos clave para el RAG", tamaños razonables).
- JSON de corredores INVIAS (schema, tipos, rangos, frescura del snapshot).
- metadata.json (coherencia con el filesystem, sin huérfanos).

Códigos de salida:
    0 = todo OK
    1 = advertencias (no bloquean ingestión)
    2 = errores (bloquean ingestión)

Uso:
    python scripts/validar_base_conocimiento.py
    python scripts/validar_base_conocimiento.py --max-horas-snapshot 6

Requisitos:
    pip install pyyaml
"""

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

BASE = Path("./base_conocimiento")
BASE_FUENTES = BASE / "fuentes"
BASE_ESTRUCTURADOS = BASE / "estructurados"
METADATA_PATH = BASE / "metadata.json"
CORREDORES_JSON = BASE_ESTRUCTURADOS / "03_condiciones_rutas_vias" / "invias_corredores.json"
REPORTE_PATH = BASE / "reporte_validacion.json"

MAX_HORAS_SNAPSHOT_DEFAULT = 24
TAMANO_MIN_MD = 500
TAMANO_MAX_MD = 50_000

FRONTMATTER_COMUN = {
    "fuente", "titulo", "anno", "categoria_rag", "tipo",
    "fecha_procesamiento", "md_generado",
}

FRONTMATTER_POR_CATEGORIA = {
    "01_fichas_tecnicas_productos": {"productos_cubiertos", "ambito_geografico"},
    "02_catalogo_flota_vehicular": {"ambito_geografico"},
    "03_condiciones_rutas_vias": {"ambito_geografico"},
    "04_tarifas_costos_transporte": {"vigencia"},
    "05_normativa_transporte": {"normas_relacionadas"},
}

CORREDOR_REQUIRED = {
    "id": str,
    "nombre": str,
    "distancia_km": (int, float),
    "departamentos": list,
    "es_critico": bool,
    "tiempo_base_min_vehiculo_particular": (int, float),
    "tiempo_base_min_carga": (int, float),
    "tiempo_estimado_min_carga": (int, float),
    "estado_general": str,
    "cantidad_incidentes": int,
    "impacto_waze_min": (int, float),
    "impacto_min_vehiculo_particular": (int, float),
    "impacto_min_carga": (int, float),
    "resumen_alertas": dict,
    "resumen_congestiones": dict,
}

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")


# ---------------------------------------------------------------------------
# Acumulador de resultados
# ---------------------------------------------------------------------------


class ResultadoValidacion:
    def __init__(self):
        self.errores = []
        self.advertencias = []

    def error(self, archivo, mensaje):
        self.errores.append({"archivo": str(archivo), "mensaje": mensaje})

    def advertencia(self, archivo, mensaje):
        self.advertencias.append({"archivo": str(archivo), "mensaje": mensaje})

    def exit_code(self) -> int:
        if self.errores:
            return 2
        if self.advertencias:
            return 1
        return 0


# ---------------------------------------------------------------------------
# Validación de Markdown
# ---------------------------------------------------------------------------


def extraer_frontmatter(texto: str):
    m = re.match(r"^---\n(.*?)\n---\n", texto, re.DOTALL)
    return m.group(1) if m else None


def validar_markdown(ruta: Path, resultado: ResultadoValidacion):
    tamano = ruta.stat().st_size
    if tamano < TAMANO_MIN_MD:
        resultado.error(ruta, f"Archivo muy pequeño ({tamano} bytes, mín {TAMANO_MIN_MD})")
        return
    if tamano > TAMANO_MAX_MD:
        resultado.advertencia(
            ruta, f"Archivo grande ({tamano} bytes, máx recomendado {TAMANO_MAX_MD})"
        )

    texto = ruta.read_text(encoding="utf-8")

    fm_text = extraer_frontmatter(texto)
    if fm_text is None:
        resultado.error(ruta, "No se encontró bloque YAML frontmatter al inicio")
        return

    try:
        fm = yaml.safe_load(fm_text)
    except yaml.YAMLError as e:
        resultado.error(ruta, f"YAML frontmatter inválido: {e}")
        return

    if not isinstance(fm, dict):
        resultado.error(ruta, "Frontmatter no es un objeto YAML")
        return

    faltantes = FRONTMATTER_COMUN - set(fm.keys())
    if faltantes:
        resultado.error(ruta, f"Campos frontmatter faltantes: {sorted(faltantes)}")

    categoria = ruta.parent.name
    requeridos_cat = FRONTMATTER_POR_CATEGORIA.get(categoria, set())
    faltantes_cat = requeridos_cat - set(fm.keys())
    if faltantes_cat:
        resultado.advertencia(
            ruta, f"Campos específicos de {categoria} faltantes: {sorted(faltantes_cat)}"
        )

    if fm.get("md_generado") is not True:
        resultado.advertencia(ruta, "md_generado no es true en el frontmatter")

    anno = fm.get("anno")
    if anno is not None and not isinstance(anno, int):
        resultado.advertencia(
            ruta, f"anno debería ser entero, es {type(anno).__name__}"
        )

    if "Fragmentos clave para el RAG" not in texto:
        resultado.error(ruta, "Falta sección 'Fragmentos clave para el RAG'")


# ---------------------------------------------------------------------------
# Validación del JSON de corredores INVIAS
# ---------------------------------------------------------------------------


def _verificar_tipo(valor, tipo_esperado) -> bool:
    if isinstance(tipo_esperado, tuple):
        return isinstance(valor, tipo_esperado) and not isinstance(valor, bool) or (
            bool in tipo_esperado and isinstance(valor, bool)
        )
    return isinstance(valor, tipo_esperado)


def validar_corredores_json(ruta: Path, max_horas: int, resultado: ResultadoValidacion):
    if not ruta.exists():
        resultado.advertencia(ruta, "JSON de corredores INVIAS no existe todavía")
        return

    try:
        data = json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        resultado.error(ruta, f"JSON inválido: {e}")
        return

    meta = data.get("metadata")
    if not isinstance(meta, dict):
        resultado.error(ruta, "Falta objeto 'metadata'")
        return

    snapshot = meta.get("fecha_snapshot")
    if not snapshot:
        resultado.error(ruta, "metadata.fecha_snapshot ausente")
    else:
        try:
            snap_dt = datetime.fromisoformat(snapshot)
            if snap_dt.tzinfo is None:
                snap_dt = snap_dt.replace(tzinfo=timezone.utc)
            edad = datetime.now(timezone.utc) - snap_dt
            horas = edad.total_seconds() / 3600
            if horas > max_horas:
                resultado.advertencia(
                    ruta,
                    f"Snapshot viejo ({horas:.1f}h, máx aceptable {max_horas}h)",
                )
        except ValueError:
            resultado.error(ruta, f"metadata.fecha_snapshot mal formateada: {snapshot}")

    corredores = data.get("corredores")
    if not isinstance(corredores, list):
        resultado.error(ruta, "Falta lista 'corredores'")
        return

    if len(corredores) == 0:
        resultado.error(ruta, "Lista 'corredores' vacía")
        return

    total_meta = meta.get("total_corredores")
    if total_meta is not None and total_meta != len(corredores):
        resultado.advertencia(
            ruta,
            f"metadata.total_corredores ({total_meta}) no coincide con len(corredores) ({len(corredores)})",
        )

    for i, c in enumerate(corredores):
        cid = c.get("id", f"corredor #{i}")
        contexto = f"{ruta}::{cid}"

        for campo, tipo_esperado in CORREDOR_REQUIRED.items():
            if campo not in c:
                resultado.error(contexto, f"campo faltante '{campo}'")
                continue
            if not isinstance(c[campo], tipo_esperado):
                esperados = (
                    tipo_esperado if isinstance(tipo_esperado, tuple) else (tipo_esperado,)
                )
                nombres = ", ".join(t.__name__ for t in esperados)
                resultado.error(
                    contexto,
                    f"{campo}: tipo {type(c[campo]).__name__}, esperado {nombres}",
                )

        if isinstance(c.get("distancia_km"), (int, float)) and c["distancia_km"] <= 0:
            resultado.error(contexto, f"distancia_km inválida ({c['distancia_km']})")
        for campo_t in ("tiempo_base_min_carga", "tiempo_estimado_min_carga"):
            v = c.get(campo_t)
            if isinstance(v, (int, float)) and v < 0:
                resultado.error(contexto, f"{campo_t} negativo ({v})")


# ---------------------------------------------------------------------------
# Validación de JSONs de datasets tabulares (convertidos desde XLS/XLSX)
# ---------------------------------------------------------------------------


JSONS_CON_SCHEMA_PROPIO = {"invias_corredores.json", "metadata.json", "reporte_validacion.json"}


def validar_dataset_json(ruta: Path, resultado: ResultadoValidacion):
    """
    Valida JSONs generados por convertir_xls_a_json() en el orquestador.
    Contrato mínimo: objeto con 'metadata' (dict) y 'registros' (list o dict).
    """
    try:
        data = json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        resultado.error(ruta, f"JSON inválido: {e}")
        return

    if not isinstance(data, dict):
        resultado.error(ruta, "El JSON raíz debe ser un objeto")
        return

    meta = data.get("metadata")
    if not isinstance(meta, dict):
        resultado.error(ruta, "Falta objeto 'metadata'")
        return

    for campo in ("fuente", "fecha_procesamiento", "categoria_rag"):
        if not meta.get(campo):
            resultado.advertencia(ruta, f"metadata.{campo} vacío o ausente")

    registros = data.get("registros")
    if registros is None:
        resultado.error(ruta, "Falta clave 'registros'")
        return

    if isinstance(registros, list):
        if not registros:
            resultado.advertencia(ruta, "'registros' está vacío")
    elif isinstance(registros, dict):
        if not registros:
            resultado.advertencia(ruta, "'registros' no tiene hojas")
    else:
        resultado.error(
            ruta,
            f"'registros' debe ser list o dict, es {type(registros).__name__}",
        )


# ---------------------------------------------------------------------------
# Validación de metadata.json
# ---------------------------------------------------------------------------


def validar_metadata_json(resultado: ResultadoValidacion):
    if not METADATA_PATH.exists():
        resultado.advertencia(METADATA_PATH, "metadata.json no existe todavía")
        return

    try:
        data = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        resultado.error(METADATA_PATH, f"JSON inválido: {e}")
        return

    # Un archivo está "registrado y presente" si su entrada está en estado
    # 'descargado' o 'omitido_ya_existe' (ambos implican archivo en disco).
    ESTADOS_CON_ARCHIVO = {"descargado", "omitido_ya_existe"}
    registrados = set()
    for doc in data.get("documentos", []):
        if doc.get("estado") in ESTADOS_CON_ARCHIVO:
            ruta = doc.get("ruta_local")
            if ruta:
                p = Path(ruta)
                if not p.exists():
                    resultado.error(
                        METADATA_PATH, f"Archivo registrado no existe: {ruta}"
                    )
                else:
                    registrados.add(p.resolve())

    for patron in ("*.pdf", "*.xls", "*.xlsx"):
        for archivo in BASE.rglob(patron):
            if archivo.resolve() not in registrados:
                resultado.advertencia(
                    archivo, "Archivo en filesystem no registrado en metadata.json"
                )


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------


def imprimir_resumen(resultado: ResultadoValidacion):
    print("\n" + "=" * 60)
    print("RESUMEN DE VALIDACIÓN")
    print("=" * 60)
    print(f"  Errores:      {len(resultado.errores)}")
    print(f"  Advertencias: {len(resultado.advertencias)}")
    print()

    def mostrar(items, etiqueta, maximo=10):
        if not items:
            return
        print(f"{etiqueta}:")
        for it in items[:maximo]:
            print(f"  [{it['archivo']}]")
            print(f"    {it['mensaje']}")
        if len(items) > maximo:
            print(f"  ... y {len(items) - maximo} más (ver {REPORTE_PATH})")

    mostrar(resultado.errores, "ERRORES")
    mostrar(resultado.advertencias, "ADVERTENCIAS")
    print(f"\nReporte completo: {REPORTE_PATH.resolve()}")


def main():
    parser = argparse.ArgumentParser(description="Valida la estructura de la base de conocimiento.")
    parser.add_argument(
        "--max-horas-snapshot",
        type=int,
        default=MAX_HORAS_SNAPSHOT_DEFAULT,
        help=f"Máxima edad aceptable del snapshot de corredores (default {MAX_HORAS_SNAPSHOT_DEFAULT}h).",
    )
    args = parser.parse_args()

    if yaml is None:
        logging.error("pyyaml no está instalado. Ejecuta: pip install pyyaml")
        return 2

    if not BASE.exists():
        logging.error(f"No existe la carpeta base: {BASE.resolve()}")
        return 2

    resultado = ResultadoValidacion()

    # Los .md estructurados viven en estructurados/. Excluimos .raw.md temporales.
    scan_base = BASE_ESTRUCTURADOS if BASE_ESTRUCTURADOS.exists() else BASE
    mds = [
        m for m in scan_base.rglob("*.md")
        if not m.name.endswith(".raw.md")
        and m.name not in ("reporte_cobertura.md", "reporte_validacion_semantica.md")
    ]
    logging.info(f"Validando {len(mds)} archivo(s) Markdown...")
    for md in mds:
        validar_markdown(md, resultado)

    logging.info("Validando JSON de corredores INVIAS...")
    validar_corredores_json(CORREDORES_JSON, args.max_horas_snapshot, resultado)

    # Otros JSONs de datasets (convertidos desde XLS/XLSX) con schema mínimo común
    datasets = [
        j for j in BASE.rglob("*.json")
        if j.name not in JSONS_CON_SCHEMA_PROPIO
        and j.resolve() != CORREDORES_JSON.resolve()
    ]
    if datasets:
        logging.info(f"Validando {len(datasets)} dataset(s) JSON...")
        for j in datasets:
            validar_dataset_json(j, resultado)

    logging.info("Validando metadata.json...")
    validar_metadata_json(resultado)

    reporte = {
        "generado_en": datetime.now(timezone.utc).isoformat(),
        "total_errores": len(resultado.errores),
        "total_advertencias": len(resultado.advertencias),
        "errores": resultado.errores,
        "advertencias": resultado.advertencias,
    }
    REPORTE_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORTE_PATH.write_text(
        json.dumps(reporte, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    imprimir_resumen(resultado)
    return resultado.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())

