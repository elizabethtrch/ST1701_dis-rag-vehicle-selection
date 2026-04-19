#!/usr/bin/env python3
"""
Agente orquestador de la base de conocimiento
API RAG para selección inteligente de vehículo

Uso:
    python agents/knowledge_base_agent.py
    python agents/knowledge_base_agent.py --solo-descargar
    python agents/knowledge_base_agent.py --solo-estructurar
    python agents/knowledge_base_agent.py --verificar-cobertura

El agente evalúa el estado actual de la base de conocimiento y
decide autónomamente qué pasos ejecutar. Solo interrumpe al usuario
cuando necesita una decisión que no puede tomar solo.

Requisitos:
    pip install requests
    Claude Code instalado (comando `claude` disponible en PATH)
"""

import os
import json
import argparse
import subprocess
import sys
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent.parent
BASE_CONOCIMIENTO = BASE_DIR / "base_conocimiento"
BASE_FUENTES = BASE_CONOCIMIENTO / "fuentes"
BASE_ESTRUCTURADOS = BASE_CONOCIMIENTO / "estructurados"
SCRIPTS_DIR = BASE_DIR / "scripts"
SKILL_PATH = BASE_DIR / "skills" / "knowledge-base-builder" / "SKILL.md"
METADATA_PATH = BASE_CONOCIMIENTO / "metadata.json"
INVIAS_CORREDORES_SCRIPT = SCRIPTS_DIR / "descargar_corredores_invias.py"
INVIAS_CORREDORES_JSON = (
    BASE_ESTRUCTURADOS / "03_condiciones_rutas_vias" / "invias_corredores.json"
)
VALIDADOR_SCRIPT = SCRIPTS_DIR / "validar_base_conocimiento.py"
REPORTE_VALIDACION = BASE_CONOCIMIENTO / "reporte_validacion.json"


def ruta_salida(fuente: Path, extension: str) -> Path:
    """
    Mapea una ruta de fuentes/ a su contraparte en estructurados/ con otra extensión.
    Ej.: fuentes/05_X/y.xls + '.md' → estructurados/05_X/y.md
    """
    rel = fuente.relative_to(BASE_FUENTES)
    salida = BASE_ESTRUCTURADOS / rel.with_suffix(extension)
    salida.parent.mkdir(parents=True, exist_ok=True)
    return salida

CATEGORIAS = {
    "01_fichas_tecnicas_productos": "Fichas técnicas de productos",
    "02_catalogo_flota_vehicular": "Catálogo de flota vehicular",
    "03_condiciones_rutas_vias": "Condiciones de rutas y vías",
    "04_tarifas_costos_transporte": "Tarifas y costos de transporte",
    "05_normativa_transporte": "Normativa de transporte agrícola",
}
# ---------------------------------------------------------------------------
# Utilidades de consola
# ---------------------------------------------------------------------------


def log(mensaje: str, nivel: str = "INFO"):
    iconos = {"INFO": "→", "OK": "✓", "WARN": "!", "ERROR": "✗", "AGENTE": "◆"}
    icono = iconos.get(nivel, "→")
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {icono}  {mensaje}")


def separador(titulo: str = ""):
    linea = "─" * 60
    if titulo:
        print(f"\n{linea}")
        print(f"  {titulo}")
        print(f"{linea}")
    else:
        print(f"\n{linea}")


def preguntar(pregunta: str, opciones: list = None) -> str:
    """Interrumpe al agente y pide decisión al usuario."""
    separador("DECISIÓN REQUERIDA")
    print(f"\n  {pregunta}\n")
    if opciones:
        for i, op in enumerate(opciones, 1):
            print(f"  [{i}] {op}")
        while True:
            respuesta = input("\n  Tu elección: ").strip()
            if respuesta.isdigit() and 1 <= int(respuesta) <= len(opciones):
                return opciones[int(respuesta) - 1]
            print("  Por favor elige un número válido.")
    else:
        return input("  Respuesta: ").strip()


# ---------------------------------------------------------------------------
# Fase 1: Evaluar estado actual
# ---------------------------------------------------------------------------


def evaluar_estado() -> dict:
    """
    Evalúa el estado actual de la base de conocimiento sin ejecutar nada.
    Retorna un dict con lo que falta hacer.
    """
    separador("FASE 1 — Evaluando estado actual")

    estado = {
        "carpetas_existen": False,
        "pdfs_descargados": [],
        "pdfs_sin_markdown": [],
        "markdowns_sin_fragmentos_clave": [],
        "metadata_existe": False,
        "documentos_fallidos": [],
        "invias_corredores_json_existe": False,
        "invias_corredores_snapshot": None,
        "invias_corredores_total": 0,
    }

    # Verificar carpetas
    estado["carpetas_existen"] = BASE_CONOCIMIENTO.exists()
    if not estado["carpetas_existen"]:
        log("La carpeta base_conocimiento no existe todavía.", "WARN")
        return estado

    log(f"Carpeta base:          {BASE_CONOCIMIENTO.resolve()}", "OK")
    log(f"Fuentes:               {BASE_FUENTES.resolve()}", "OK")
    log(f"Estructurados:         {BASE_ESTRUCTURADOS.resolve()}", "OK")

    # Verificar metadata.json
    if METADATA_PATH.exists():
        estado["metadata_existe"] = True
        with open(METADATA_PATH, encoding="utf-8") as f:
            metadata = json.load(f)
        estado["documentos_fallidos"] = [
            d for d in metadata.get("documentos", [])
            if d.get("estado") == "fallido"
        ]
        log(f"metadata.json encontrado. Documentos: {metadata.get('total_documentos', 0)}", "OK")
        if estado["documentos_fallidos"]:
            log(f"Documentos fallidos: {len(estado['documentos_fallidos'])}", "WARN")
    else:
        log("metadata.json no encontrado. Las descargas no se han ejecutado.", "WARN")

    # Escanear fuentes/ y verificar que cada una tenga su salida en estructurados/
    extensiones_fuente = ("*.pdf", "*.xls", "*.xlsx")
    for categoria in CATEGORIAS:
        carpeta_fuentes = BASE_FUENTES / categoria
        if not carpeta_fuentes.exists():
            continue
        for patron in extensiones_fuente:
            for doc in carpeta_fuentes.glob(patron):
                estado["pdfs_descargados"].append(doc)
                # La salida esperada depende del formato declarado
                ext_salida = ".json" if formato_ingesta(doc) == "json" else ".md"
                salida = BASE_ESTRUCTURADOS / categoria / (doc.stem + ext_salida)
                if not salida.exists():
                    estado["pdfs_sin_markdown"].append(doc)
                elif salida.suffix == ".md":
                    contenido = salida.read_text(encoding="utf-8")
                    if "Fragmentos clave para el RAG" not in contenido:
                        estado["markdowns_sin_fragmentos_clave"].append(salida)

    log(f"Documentos fuente encontrados (PDF/XLS): {len(estado['pdfs_descargados'])}")
    log(f"Documentos sin salida estructurada: {len(estado['pdfs_sin_markdown'])}")
    if estado["markdowns_sin_fragmentos_clave"]:
        log(
            f"Markdowns incompletos (sin fragmentos clave): "
            f"{len(estado['markdowns_sin_fragmentos_clave'])}",
            "WARN",
        )

    # Estado del snapshot de corredores INVIAS
    if INVIAS_CORREDORES_JSON.exists():
        estado["invias_corredores_json_existe"] = True
        try:
            with open(INVIAS_CORREDORES_JSON, encoding="utf-8") as f:
                data = json.load(f)
            meta = data.get("metadata", {})
            estado["invias_corredores_snapshot"] = meta.get("fecha_snapshot")
            estado["invias_corredores_total"] = meta.get("total_corredores", 0)
            log(
                f"Corredores INVIAS: {estado['invias_corredores_total']} "
                f"(snapshot: {estado['invias_corredores_snapshot']})",
                "OK",
            )
        except Exception as e:
            log(f"invias_corredores.json ilegible: {e}", "WARN")
    else:
        log("invias_corredores.json no existe todavía.", "WARN")

    return estado


# ---------------------------------------------------------------------------
# Fase 2: Descargar documentos
# ---------------------------------------------------------------------------


def ejecutar_descarga() -> bool:
    """Ejecuta el script de descarga y retorna True si fue exitoso."""
    separador("FASE 2 — Descargando documentos")

    script = SCRIPTS_DIR / "descargar_base_conocimiento.py"
    if not script.exists():
        log(f"Script no encontrado: {script}", "ERROR")
        return False

    log("Iniciando descarga de documentos de alta prioridad...")
    resultado = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(BASE_DIR),
    )

    if resultado.returncode == 0:
        log("Descarga completada.", "OK")
        return True
    else:
        log("La descarga terminó con errores. Revisa el log.", "WARN")
        return False


# ---------------------------------------------------------------------------
# Fase 2B: Snapshot de corredores viales INVIAS
# ---------------------------------------------------------------------------


def ejecutar_validacion_deterministica() -> int:
    """
    Fase 4A. Corre el validador estructural.
    Retorna: 0 = OK, 1 = advertencias, 2 = errores (bloquea ingestión).
    """
    separador("FASE 4A — Validación determinística")

    if not VALIDADOR_SCRIPT.exists():
        log(f"Script no encontrado: {VALIDADOR_SCRIPT}", "ERROR")
        return 2

    resultado = subprocess.run(
        [sys.executable, str(VALIDADOR_SCRIPT)],
        cwd=str(BASE_DIR),
    )

    if resultado.returncode == 0:
        log("Validación OK (0 errores, 0 advertencias).", "OK")
    elif resultado.returncode == 1:
        log("Validación con advertencias (no bloquea).", "WARN")
    else:
        log("Validación con errores (bloquea ingestión).", "ERROR")

    return resultado.returncode


def validar_semantica():
    """
    Fase 4B (opcional). Subagente LLM revisa calidad semántica de los .md:
    cifras literales, contradicciones internas y omisiones críticas por categoría.
    """
    separador("FASE 4B — Validación semántica (subagente)")

    markdowns = [
        m for m in BASE_CONOCIMIENTO.rglob("*.md")
        if m.name not in ("reporte_cobertura.md", "reporte_validacion_semantica.md")
    ]
    if not markdowns:
        log("No hay archivos Markdown para validar semánticamente.", "WARN")
        return

    log(f"Markdowns a validar: {len(markdowns)}")
    rutas = "\n".join(f"- {md}" for md in markdowns)

    prompt = f"""
Eres un subagente de validación semántica para una base de conocimiento
RAG de logística agrícola colombiana.

Lee los siguientes archivos Markdown y reporta SOLO problemas de calidad
semántica que un validador estructural no puede detectar:

{rutas}

Para cada archivo verifica:

1. **Cifras literales**: temperaturas, humedades, pesos y artículos de ley
   deben estar transcritos textualmente, no parafraseados.
   Incorrecto: "temperatura moderada". Correcto: "entre 8°C y 12°C".

2. **Contradicciones internas**: valores que se contradigan dentro del
   mismo archivo (ej. temperatura mínima > máxima).

3. **Omisiones críticas por categoría**:
   - Fichas de producto: temperatura, humedad, tipo de vehículo.
   - Normativa: número de artículo, entidad emisora, vigencia.
   - Flota: capacidad, tipo de carrocería, restricciones.

Entrega un reporte Markdown con este formato:

## Validación semántica

### [nombre_archivo.md]
- [PROBLEMA] descripción breve
- [OK] si no hay problemas

Sé conciso. Una línea por hallazgo.
"""

    try:
        resultado = subprocess.run(
            [
                "claude",
                "--print",
                "--permission-mode", "acceptEdits",
                prompt,
            ],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=300,
        )
        print("\n" + resultado.stdout)

        reporte = BASE_CONOCIMIENTO / "reporte_validacion_semantica.md"
        reporte.write_text(
            f"# Reporte de validación semántica\n"
            f"Generado: {datetime.now().isoformat()}\n\n"
            + resultado.stdout,
            encoding="utf-8",
        )
        log(f"Reporte guardado en: {reporte}", "OK")
    except FileNotFoundError:
        log("Comando 'claude' no encontrado.", "ERROR")
    except subprocess.TimeoutExpired:
        log("Timeout en validación semántica.", "ERROR")


def ejecutar_descarga_corredores_invias() -> bool:
    """Refresca el snapshot de corredores INVIAS. Siempre se ejecuta por ser data volátil."""
    separador("FASE 2B — Snapshot de corredores INVIAS")

    if not INVIAS_CORREDORES_SCRIPT.exists():
        log(f"Script no encontrado: {INVIAS_CORREDORES_SCRIPT}", "ERROR")
        return False

    log("Consultando API de corredores INVIAS...")
    resultado = subprocess.run(
        [sys.executable, str(INVIAS_CORREDORES_SCRIPT)],
        cwd=str(BASE_DIR),
    )

    if resultado.returncode == 0:
        log("Snapshot de corredores actualizado.", "OK")
        return True
    else:
        log("La descarga de corredores terminó con errores.", "WARN")
        return False


# ---------------------------------------------------------------------------
# Fase 3: Estructurar PDFs con subagente Claude
# ---------------------------------------------------------------------------


def _cargar_catalogo() -> dict:
    """
    Parsea DOCUMENTOS del script de descarga sin ejecutar el módulo
    (evita side-effects como reabrir logs). Retorna {nombre: entrada}.
    """
    import ast

    catalogo_py = SCRIPTS_DIR / "descargar_base_conocimiento.py"
    if not catalogo_py.exists():
        return {}
    try:
        tree = ast.parse(catalogo_py.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return {}

    for nodo in tree.body:
        if isinstance(nodo, ast.Assign):
            for target in nodo.targets:
                if isinstance(target, ast.Name) and target.id == "DOCUMENTOS":
                    try:
                        docs = ast.literal_eval(nodo.value)
                        return {d["nombre"]: d for d in docs if isinstance(d, dict)}
                    except (ValueError, SyntaxError):
                        return {}
    return {}


_CATALOGO_CACHE = None


def catalogo() -> dict:
    """Catálogo indexado por nombre de archivo. Lazy-loaded."""
    global _CATALOGO_CACHE
    if _CATALOGO_CACHE is None:
        _CATALOGO_CACHE = _cargar_catalogo()
    return _CATALOGO_CACHE


def formato_ingesta(doc_path: Path) -> str:
    """'json' o 'markdown' según el catálogo. Default: markdown."""
    entry = catalogo().get(doc_path.name, {})
    return entry.get("formato_ingesta", "markdown")


def convertir_xls_a_json(xls_path: Path) -> bool:
    """
    Convierte un XLS/XLSX tabular a JSON estructurado con metadata.
    Se salta el subagente: pandas serializa directo. Útil para datasets puros.
    """
    try:
        import pandas as pd
    except ImportError:
        log("pandas no está instalado. pip install pandas openpyxl xlrd", "ERROR")
        return False

    entry = catalogo().get(xls_path.name, {})

    try:
        if xls_path.suffix.lower() == ".xlsx":
            hojas = pd.read_excel(xls_path, sheet_name=None, engine="openpyxl")
        else:
            hojas = pd.read_excel(xls_path, sheet_name=None)
    except Exception as e:
        log(f"  No se pudo leer {xls_path.name}: {e}", "ERROR")
        return False

    # Normalizar NaN a string vacío para serialización JSON
    if len(hojas) == 1:
        df = next(iter(hojas.values()))
        registros = df.fillna("").to_dict(orient="records")
        total = len(registros)
    else:
        registros = {
            nombre: df.fillna("").to_dict(orient="records")
            for nombre, df in hojas.items()
        }
        total = sum(len(v) for v in registros.values())

    # categoria_rag sin el prefijo numérico
    cat_folder = xls_path.parent.name
    categoria_rag = cat_folder.split("_", 1)[1] if "_" in cat_folder else cat_folder

    salida = {
        "metadata": {
            "fuente": entry.get("fuente", ""),
            "titulo": entry.get("id", xls_path.stem),
            "anno": entry.get("anno"),
            "categoria_rag": categoria_rag,
            "tipo": entry.get("tipo", "reporte"),
            "url_origen": entry.get("url", ""),
            "fecha_procesamiento": datetime.now().isoformat(),
            "fuente_archivo": xls_path.name,
            "total_registros": total,
            "descripcion": entry.get("descripcion", ""),
        },
        "registros": registros,
    }

    json_path = ruta_salida(xls_path, ".json")
    try:
        json_path.write_text(
            json.dumps(salida, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        log(f"  No se pudo escribir {json_path}: {e}", "ERROR")
        return False

    log(
        f"  → {json_path.relative_to(BASE_CONOCIMIENTO)} "
        f"({json_path.stat().st_size // 1024} KB, {total} registros)",
        "OK",
    )
    return True


def preprocesar_xls_a_markdown(xls_path: Path) -> Path:
    """
    Convierte un XLS/XLSX a un Markdown intermedio con tablas por hoja,
    para que el subagente pueda leerlo sin depender de parsers de Excel.
    Retorna la ruta del archivo generado (.raw.md) o None si falla.
    """
    try:
        import pandas as pd
    except ImportError:
        log("pandas no está instalado. Ejecuta: pip install pandas openpyxl xlrd", "ERROR")
        return None

    try:
        if xls_path.suffix.lower() == ".xlsx":
            hojas = pd.read_excel(xls_path, sheet_name=None, engine="openpyxl")
        else:
            hojas = pd.read_excel(xls_path, sheet_name=None)
    except Exception as e:
        log(f"No se pudo leer {xls_path.name}: {e}", "ERROR")
        return None

    partes = [f"# Contenido crudo extraído de {xls_path.name}\n"]
    for nombre_hoja, df in hojas.items():
        partes.append(f"\n## Hoja: {nombre_hoja}\n")
        if df.empty:
            partes.append("_(hoja vacía)_\n")
            continue
        try:
            partes.append(df.to_markdown(index=False))
        except Exception:
            partes.append("```\n" + df.to_string(index=False) + "\n```")
        partes.append("\n")

    # El .raw.md temporal va en estructurados/<cat>/ con sufijo .raw.md
    rel_dir = xls_path.parent.relative_to(BASE_FUENTES)
    raw_md = BASE_ESTRUCTURADOS / rel_dir / f"{xls_path.stem}.raw.md"
    raw_md.parent.mkdir(parents=True, exist_ok=True)
    raw_md.write_text("\n".join(partes), encoding="utf-8")
    log(f"  → XLS convertido a Markdown intermedio: {raw_md.name}", "OK")
    return raw_md


def estructurar_pdf(pdf_path: Path) -> bool:
    """
    Procesa un documento fuente (PDF, XLS, XLSX) y produce su salida
    estructurada. Bifurca según 'formato_ingesta' del catálogo:
    - 'json'   → pandas serializa directo (datasets).
    - 'markdown' (default) → subagente Claude aplica plantilla del SKILL.
    """
    categoria = pdf_path.parent.name
    nombre_categoria = CATEGORIAS.get(categoria, categoria)

    # Ruteo por formato de ingesta declarado en el catálogo
    if formato_ingesta(pdf_path) == "json":
        log(f"Convirtiendo a JSON: {pdf_path.name} [{nombre_categoria}]")
        return convertir_xls_a_json(pdf_path)

    md_destino = ruta_salida(pdf_path, ".md")

    log(f"Estructurando: {pdf_path.name} [{nombre_categoria}]")

    # Si es Excel, pre-convertir a Markdown crudo para que el subagente lo lea.
    archivo_fuente_para_subagente = pdf_path
    raw_md_temporal = None
    es_excel = pdf_path.suffix.lower() in (".xls", ".xlsx")
    if es_excel:
        raw_md_temporal = preprocesar_xls_a_markdown(pdf_path)
        if raw_md_temporal is None:
            return False
        archivo_fuente_para_subagente = raw_md_temporal

    # Leer el skill para pasarlo como contexto al subagente
    skill_contenido = ""
    if SKILL_PATH.exists():
        skill_contenido = SKILL_PATH.read_text(encoding="utf-8")

    tipo_fuente = "Markdown con tablas extraídas de un Excel" if es_excel else "PDF"

    # Prompt para el subagente
    prompt = f"""
Eres un subagente especializado en estructurar documentos para bases
de conocimiento RAG de logística agrícola colombiana.

Tu única tarea es leer el documento fuente y producir un archivo Markdown
estructurado siguiendo exactamente las instrucciones del skill.

## Skill de referencia
{skill_contenido}

## Tarea específica

1. Lee el archivo ({tipo_fuente}) ubicado en: {archivo_fuente_para_subagente}
2. Determina que pertenece a la categoría: {nombre_categoria}
3. Aplica la plantilla correspondiente a esa categoría (ver PLANTILLAS
   en el skill).
4. Escribe el resultado en: {md_destino}
5. Verifica que el archivo creado tiene:
   - Bloque YAML front matter completo al inicio
   - Cifras técnicas literales (no parafraseadas)
   - Sección "Fragmentos clave para el RAG" al final
6. Reporta "COMPLETADO" si el archivo fue creado correctamente,
   o "FALLIDO: [razón]" si hubo algún problema.

No hagas nada más que esta tarea. No expliques el proceso.
Solo produce el archivo y reporta el resultado.
"""

    try:
        resultado = subprocess.run(
            [
                "claude",
                "--print",
                "--permission-mode", "acceptEdits",
                prompt,
            ],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutos por documento
        )

        if md_destino.exists() and md_destino.stat().st_size > 500:
            log(f"  → {md_destino.name} creado ({md_destino.stat().st_size // 1024} KB)", "OK")
            exito = True
        else:
            log("  → Subagente no produjo el archivo esperado.", "WARN")
            if resultado.stdout:
                print(f"     Salida: {resultado.stdout[:200]}")
            exito = False

    except subprocess.TimeoutExpired:
        log(f"  → Timeout al estructurar {pdf_path.name}", "ERROR")
        exito = False
    except FileNotFoundError:
        log(
            "  → Comando 'claude' no encontrado. "
            "Verifica que Claude Code está instalado.",
            "ERROR",
        )
        exito = False

    # Limpiar archivo intermedio (.raw.md) generado para XLS
    if raw_md_temporal is not None and raw_md_temporal.exists():
        try:
            raw_md_temporal.unlink()
        except OSError:
            pass

    return exito


def ejecutar_estructuracion(pdfs_pendientes: list) -> dict:
    """Estructura todos los PDFs pendientes usando subagentes."""
    separador("FASE 3 — Estructurando PDFs en Markdown")

    if not pdfs_pendientes:
        log("No hay PDFs pendientes de estructurar.", "OK")
        return {"completados": 0, "fallidos": []}

    log(f"PDFs a estructurar: {len(pdfs_pendientes)}")
    resultados = {"completados": 0, "fallidos": []}

    for i, pdf in enumerate(pdfs_pendientes, 1):
        print(f"\n  [{i}/{len(pdfs_pendientes)}]", end=" ")
        exito = estructurar_pdf(pdf)
        if exito:
            resultados["completados"] += 1
        else:
            resultados["fallidos"].append(pdf)

    return resultados


# ---------------------------------------------------------------------------
# Fase 4: Verificar cobertura
# ---------------------------------------------------------------------------


def verificar_cobertura():
    """Lanza un subagente para evaluar la cobertura de la base de conocimiento."""
    separador("FASE 4 — Verificando cobertura")

    markdowns = list(BASE_CONOCIMIENTO.rglob("*.md"))
    fuentes = list(markdowns)
    if INVIAS_CORREDORES_JSON.exists():
        fuentes.append(INVIAS_CORREDORES_JSON)

    if not fuentes:
        log("No hay archivos Markdown ni JSON para verificar.", "WARN")
        return

    log(f"Archivos Markdown: {len(markdowns)}")
    if INVIAS_CORREDORES_JSON.exists():
        log(f"JSON de corredores INVIAS: {INVIAS_CORREDORES_JSON.name}")

    rutas = "\n".join(f"- {f}" for f in fuentes)
    prompt = f"""
Eres un subagente de verificación de cobertura para una base de
conocimiento RAG de logística agrícola colombiana.

Lee los siguientes archivos (Markdown y un JSON estructurado de
corredores viales INVIAS) y evalúa la cobertura:

{rutas}

Responde con una tabla en Markdown que tenga estas columnas:
| Elemento | Estado | Fuente disponible | Acción recomendada |

Evalúa:
1. Productos agrícolas cubiertos con temperatura, humedad y tipo de vehículo.
2. Productos importantes faltantes (aguacate Hass, plátano hartón, café,
   flores de corte, papa, tomate, mango, mora, uchuva, espárragos).
3. Normativa cubierta (mínimo: Res. 2674/2013 y Res. 2505/2004).
4. Cobertura para estos dos escenarios:
   - Escenario A: 1.200 kg de aguacate Hass, Antioquia a Bogotá,
     vehículo refrigerado vs abierto disponibles.
   - Escenario B: flores de corte, temporada de lluvia, vía terciaria,
     restricción de dimensión del vehículo.

Al final indica: ¿la base está lista para ingestión o qué falta primero?
"""

    try:
        resultado = subprocess.run(
            [
                "claude",
                "--print",
                "--permission-mode", "acceptEdits",
                prompt,
            ],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=180,
        )
        print("\n" + resultado.stdout)

        # Guardar el reporte
        reporte_path = BASE_CONOCIMIENTO / "reporte_cobertura.md"
        reporte_path.write_text(
            f"# Reporte de cobertura\nGenerado: {datetime.now().isoformat()}\n\n"
            + resultado.stdout,
            encoding="utf-8",
        )
        log(f"Reporte guardado en: {reporte_path}", "OK")

    except FileNotFoundError:
        log("Comando 'claude' no encontrado.", "ERROR")


# ---------------------------------------------------------------------------
# Orquestador principal
# ---------------------------------------------------------------------------


def orquestar(args):
    """
    Lógica principal del agente. Evalúa el estado y decide qué hacer,
    interrumpiendo al usuario solo cuando es necesario.
    """
    separador("AGENTE DE BASE DE CONOCIMIENTO")
    log("Iniciando orquestación autónoma...", "AGENTE")
    log(f"Proyecto: {BASE_DIR.resolve()}", "AGENTE")

    # --- Solo verificar cobertura ---
    if args.verificar_cobertura:
        verificar_cobertura()
        return

    # --- Solo refrescar corredores INVIAS ---
    if args.solo_corredores:
        ejecutar_descarga_corredores_invias()
        return

    # --- Solo validar estructura ---
    if args.solo_validar:
        ejecutar_validacion_deterministica()
        return

    # --- Evaluar estado ---
    estado = evaluar_estado()

    # --- Decidir si descargar ---
    if not args.solo_estructurar:
        if not estado["metadata_existe"] or not estado["pdfs_descargados"]:
            log("No hay documentos descargados. Iniciando descarga...", "AGENTE")
            ejecutar_descarga()
            estado = evaluar_estado()

        # Refrescar siempre el snapshot de corredores INVIAS (data volátil)
        log("Refrescando snapshot de corredores INVIAS...", "AGENTE")
        ejecutar_descarga_corredores_invias()
        estado = evaluar_estado()

        if estado["documentos_fallidos"]:
            opcion = preguntar(
                f"Hay {len(estado['documentos_fallidos'])} documentos que fallaron "
                f"en la última descarga. ¿Qué deseas hacer?",
                opciones=[
                    "Reintentar la descarga de los fallidos",
                    "Continuar con los que ya están descargados",
                    "Ver la lista de fallidos y decidir después",
                ],
            )
            if "Reintentar" in opcion:
                ejecutar_descarga()
                estado = evaluar_estado()
            elif "Ver la lista" in opcion:
                separador("Documentos fallidos")
                for doc in estado["documentos_fallidos"]:
                    print(f"  - {doc.get('nombre', 'sin nombre')}")
                    print(f"    URL: {doc.get('url', 'sin URL')}")
                return

    # --- Decidir si estructurar ---
    if not args.solo_descargar:
        if estado["pdfs_sin_markdown"]:
            log(
                f"Hay {len(estado['pdfs_sin_markdown'])} PDFs sin estructurar. "
                f"Iniciando estructuración...",
                "AGENTE",
            )
            resultado_estructuracion = ejecutar_estructuracion(estado["pdfs_sin_markdown"])

            if resultado_estructuracion["fallidos"]:
                log(
                    f"No se pudieron estructurar {len(resultado_estructuracion['fallidos'])} "
                    f"documentos.",
                    "WARN",
                )
                opcion = preguntar(
                    "¿Qué deseas hacer con los documentos que no se pudieron estructurar?",
                    opciones=[
                        "Reintentar los fallidos",
                        "Continuar de todas formas",
                        "Detener aquí",
                    ],
                )
                if "Reintentar" in opcion:
                    ejecutar_estructuracion(resultado_estructuracion["fallidos"])
                elif "Detener" in opcion:
                    return
        else:
            log("Todos los PDFs ya tienen su Markdown estructurado.", "OK")

        if estado["markdowns_sin_fragmentos_clave"]:
            log(
                f"Hay {len(estado['markdowns_sin_fragmentos_clave'])} Markdowns "
                f"incompletos (sin sección de fragmentos clave).",
                "WARN",
            )
            opcion = preguntar(
                "¿Quieres completar los Markdowns que les falta la sección "
                "'Fragmentos clave para el RAG'?",
                opciones=["Sí, completarlos ahora", "No, dejarlos así"],
            )
            if "Sí" in opcion:
                ejecutar_estructuracion(
                    [md.with_suffix(".pdf") for md in estado["markdowns_sin_fragmentos_clave"]
                     if md.with_suffix(".pdf").exists()]
                )

    # --- Fase 4A: Validación estructural determinística ---
    exit_code_validacion = ejecutar_validacion_deterministica()
    if exit_code_validacion == 2:
        opcion = preguntar(
            "La validación encontró errores que bloquearían la ingestión. "
            "¿Qué deseas hacer?",
            opciones=[
                "Detener y revisar el reporte",
                "Continuar de todas formas (no recomendado)",
            ],
        )
        if "Detener" in opcion:
            log(f"Revisa el reporte en: {REPORTE_VALIDACION}", "WARN")
            return

    # --- Fase 4B: Validación semántica (opcional) ---
    if args.validar_semantica:
        validar_semantica()

    # --- Verificación de cobertura automática al final ---
    separador("FASE FINAL — Verificación de cobertura")
    opcion = preguntar(
        "¿Deseas ejecutar la verificación de cobertura para saber "
        "si la base está lista para ingestión?",
        opciones=["Sí, verificar ahora", "No, terminar aquí"],
    )
    if "Sí" in opcion:
        verificar_cobertura()

    separador("COMPLETADO")
    log("El agente terminó su ejecución.", "OK")
    log(
        "Los archivos .md en base_conocimiento/ están listos para ingestión al RAG.",
        "OK",
    )


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Agente orquestador de base de conocimiento RAG"
    )
    parser.add_argument(
        "--solo-descargar",
        action="store_true",
        help="Solo ejecutar la fase de descarga, sin estructurar.",
    )
    parser.add_argument(
        "--solo-estructurar",
        action="store_true",
        help="Solo estructurar PDFs ya descargados, sin descargar nuevos.",
    )
    parser.add_argument(
        "--verificar-cobertura",
        action="store_true",
        help="Solo verificar cobertura de la base de conocimiento.",
    )
    parser.add_argument(
        "--solo-corredores",
        action="store_true",
        help="Solo refrescar el snapshot de corredores viales INVIAS.",
    )
    parser.add_argument(
        "--solo-validar",
        action="store_true",
        help="Solo ejecutar la validación estructural determinística.",
    )
    parser.add_argument(
        "--validar-semantica",
        action="store_true",
        help="Ejecutar también la validación semántica con subagente LLM.",
    )
    args = parser.parse_args()
    orquestar(args)
