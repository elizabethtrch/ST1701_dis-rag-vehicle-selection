"""
Script de descarga de documentos de alta prioridad
Base de conocimiento - API RAG para selección inteligente de vehículo

Uso:
    python descargar_base_conocimiento.py

Requisitos:
    pip install requests tqdm

Salida:
    Carpeta ./base_conocimiento/ con subcarpetas por categoría.
    Archivo ./base_conocimiento/metadata.json con metadatos de cada documento.
    Archivo ./base_conocimiento/descarga_log.txt con el log de la ejecución.
"""

import os
import json
import time
import hashlib
import logging
import requests
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuración general
# ---------------------------------------------------------------------------

BASE_CONOCIMIENTO = Path("./base_conocimiento")
CARPETA_BASE = BASE_CONOCIMIENTO / "fuentes"   # descargas originales
METADATA_PATH = BASE_CONOCIMIENTO / "metadata.json"
TIMEOUT_SEGUNDOS = 60
REINTENTOS = 3
PAUSA_ENTRE_DESCARGAS = 2  # segundos, para no saturar los servidores

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(BASE_CONOCIMIENTO / "descarga_log.txt", mode="w", encoding="utf-8")
        if BASE_CONOCIMIENTO.exists()
        else logging.NullHandler(),
    ],
)

# ---------------------------------------------------------------------------
# Catálogo de documentos de alta prioridad
#
# Cada entrada tiene:
#   - id          : identificador único del documento
#   - nombre      : nombre del archivo que se guardará localmente
#   - url         : URL de descarga directa
#   - categoria   : carpeta de destino (corresponde a las 5 categorías de la Tabla 1)
#   - fuente      : entidad que publica el documento
#   - descripcion : qué contiene y para qué sirve en el RAG
#   - tipo        : "normativa" | "ficha_tecnica" | "manual" | "acta"
#   - anno        : año de publicación o última actualización conocida
# ---------------------------------------------------------------------------

DOCUMENTOS = [
    # -----------------------------------------------------------------------
    # CATEGORÍA 1 – Fichas técnicas de productos
    # -----------------------------------------------------------------------
    {
        "id": "fao_postcosecha_frutas_tropicales",
        "nombre": "fao_manual_postcosecha_frutas_tropicales.pdf",
        "url": "https://openknowledge.fao.org/server/api/core/bitstreams/a111220e-d670-46ba-bf6e-f15d62f507b2/content",
        "categoria": "01_fichas_tecnicas_productos",
        "fuente": "FAO",
        "descripcion": (
            "Manual de manejo postcosecha de frutas tropicales. "
            "Contiene tablas de temperatura, humedad relativa, ritmo respiratorio "
            "y producción de etileno por producto. Referencia estándar usada por "
            "ICA y AGROSAVIA para manuales de transporte."
        ),
        "tipo": "manual",
        "anno": 2011,
    },
    {
        "id": "agrosavia_frutas_colombia_exportador",
        "nombre": "agrosavia_frutas_colombia_para_el_mundo_manual_exportador.pdf",
        "url": "https://repository.agrosavia.co/bitstreams/3f5f5926-80f8-4ade-96e2-ef52492c9303/download",
        "categoria": "01_fichas_tecnicas_productos",
        "fuente": "AGROSAVIA",
        "descripcion": (
            "Frutas de Colombia para el mundo: Manual del Exportador. "
            "Cubre transporte refrigerado en contenedor, empaque, normas de calidad "
            "y compatibilidad de frutas para transporte conjunto. "
            "Especificaciones técnicas por producto agrícola de exportación."
        ),
        "tipo": "manual",
        "anno": 1996,
        "nota": (
            "Si la descarga directa falla, buscar en el repositorio AGROSAVIA: "
            "https://repository.agrosavia.co/handle/20.500.12324/29469"
        ),
    },
    # -----------------------------------------------------------------------
    # CATEGORÍA 5 – Normativa de transporte agrícola
    # (priorizadas sobre categorías 3 y 4 por impacto directo en el RAG)
    # -----------------------------------------------------------------------
    {
        "id": "invima_res_2674_2013",
        "nombre": "invima_resolucion_2674_2013_requisitos_sanitarios_alimentos.pdf",
        "url": "https://www.invima.gov.co/invima_website/static/attachments/alimentos_otros_alimentos_y_bebidas/2674-2013.pdf",
        "categoria": "05_normativa_transporte",
        "fuente": "INVIMA",
        "descripcion": (
            "Resolución 2674 de 2013. Establece los requisitos sanitarios para "
            "fabricación, procesamiento, almacenamiento, transporte, distribución "
            "y comercialización de alimentos. Contiene condiciones de cadena de frío, "
            "temperatura de almacenamiento y normas de vehículos transportadores."
        ),
        "tipo": "normativa",
        "anno": 2013,
    },
    {
        "id": "minsalud_res_2674_2013_oficial",
        "nombre": "minsalud_resolucion_2674_2013_copia_oficial.pdf",
        "url": "https://www.minsalud.gov.co/sites/rid/Lists/BibliotecaDigital/RIDE/DE/DIJ/resolucion-2674-de-2013.pdf",
        "categoria": "05_normativa_transporte",
        "fuente": "Ministerio de Salud",
        "descripcion": (
            "Copia oficial de la Resolución 2674 de 2013 desde el Ministerio de Salud. "
            "Respaldo en caso de que la URL del INVIMA no esté disponible."
        ),
        "tipo": "normativa",
        "anno": 2013,
    },
    {
        "id": "invima_acta_vehiculos_transportadores",
        "nombre": "invima_acta_inspeccion_vehiculos_transportadores_alimentos.xls",
        "url": (
            "https://www.invima.gov.co/invima_website/static/attachments/"
            "alimentos_entidades_territoriales/"
            "10.Veh_C3_ADculos_20Transportadores_20de_20Alimentos.xls"
        ),
        "categoria": "05_normativa_transporte",
        "fuente": "INVIMA",
        "descripcion": (
            "Acta de inspección sanitaria de vehículos transportadores de alimentos. "
            "Aplica las Resoluciones 2505/2004 y 2674/2013. Incluye los criterios exactos "
            "de evaluación: refrigeración, limpieza, rotulado, condiciones del vehículo. "
            "Útil para enriquecer el razonamiento del LLM sobre requisitos de flota. "
            "Se distribuye como hoja de cálculo Excel; el pipeline la convierte "
            "automáticamente a Markdown antes de la estructuración."
        ),
        "tipo": "acta",
        "anno": 2013,
    },
    {
        "id": "fao_res_2674_copia_fao",
        "nombre": "fao_resolucion_2674_2013_colombia.pdf",
        "url": "https://faolex.fao.org/docs/pdf/col145241.pdf",
        "categoria": "05_normativa_transporte",
        "fuente": "FAO / FAOLEX",
        "descripcion": (
            "Copia de la Resolución 2674 de 2013 en el repositorio FAOLEX de la FAO. "
            "Tercera fuente de respaldo para asegurar disponibilidad del documento."
        ),
        "tipo": "normativa",
        "anno": 2013,
    },
    {
        "id": "mintransporte_res_2505_2004",
        "nombre": "mintransporte_resolucion_2505_2004_transporte_alimentos_perecederos.pdf",
        "url": "https://web.mintransporte.gov.co/jspui/bitstream/001/3868/1/Resolucion_2505_2004.pdf",
        "categoria": "05_normativa_transporte",
        "fuente": "MinTransporte",
        "descripcion": (
            "Resolución 2505 de 2004 del Ministerio de Transporte. "
            "Establece los requisitos que deben cumplir los vehículos para transporte "
            "de alimentos, medicamentos y productos que requieran cadena de frío. "
            "Define temperaturas máximas, condiciones de aislamiento, "
            "habilitación de empresas y requisitos de refrigeración."
        ),
        "tipo": "normativa",
        "anno": 2004,
    },
    # -----------------------------------------------------------------------
    # CATEGORÍA 1 – Fichas técnicas de productos (fuentes adicionales)
    # Cubre los 10 productos de referencia: aguacate Hass, plátano hartón,
    # café, flores de corte, papa, tomate, mango, mora, uchuva, espárragos.
    # -----------------------------------------------------------------------
    {
        "id": "fao_manual_calidad_frutas_hortalizas",
        "nombre": "fao_manual_calidad_frutas_hortalizas_codex.pdf",
        "url": "https://www.fao.org/3/y4893s/y4893s.pdf",
        "categoria": "01_fichas_tecnicas_productos",
        "fuente": "FAO / Codex Alimentarius",
        "descripcion": (
            "Manual para el mejoramiento del manejo postcosecha de frutas y hortalizas. "
            "Contiene tablas de temperatura, humedad relativa y vida de anaquel por producto, "
            "incluyendo aguacate, mango, tomate, papa y flores de corte. "
            "Complementa el manual de frutas tropicales con hortalizas y flores."
        ),
        "tipo": "manual",
        "anno": 2004,
    },
    {
        "id": "sena_unal_postcosecha_frutas_hortalizas_tropicales",
        "nombre": "sena_unal_tecnologia_postcosecha_frutas_hortalizas.pdf",
        "url": "https://repository.agrosavia.co/bitstreams/b9da71d0-fd6f-4fea-b198-bc6ca929f04c/download",
        "categoria": "01_fichas_tecnicas_productos",
        "fuente": "SENA / Universidad Nacional de Colombia",
        "descripcion": (
            "Tecnología del manejo postcosecha de frutas y hortalizas tropicales. "
            "Publicación conjunta del SENA y la Universidad Nacional de Colombia, "
            "con énfasis en productos colombianos: aguacate, plátano, mango, mora, "
            "uchuva y flores de corte. Condiciones de refrigeración y vida útil. "
            "Disponible a través del repositorio AGROSAVIA."
        ),
        "tipo": "manual",
        "anno": 2021,
    },
    # -----------------------------------------------------------------------
    # CATEGORÍA 2 – Catálogo de flota vehicular
    # La flota real es interna al proyecto. Se incluye aquí el decreto que
    # define los tipos de vehículos de carga en Colombia y sus capacidades
    # legales, como referencia documental para el RAG.
    # -----------------------------------------------------------------------
    {
        "id": "mintransporte_decreto_tipos_vehiculos_carga",
        "nombre": "mintransporte_abc_sicetac_tipos_vehiculos_carga.pdf",
        "url": "https://web.mintransporte.gov.co/jspui/bitstream/001/10564/1/ABC-SICETAC%20%281%29%20%283%29.pdf",
        "categoria": "02_catalogo_flota_vehicular",
        "fuente": "MinTransporte",
        "descripcion": (
            "ABC del SICE-TAC. Documento oficial del Ministerio de Transporte que "
            "define las 12 configuraciones de vehículos de carga reconocidas en Colombia: "
            "camión sencillo, doble troque, tractocamión, minimula, con furgón refrigerado "
            "y con furgón seco. Incluye capacidades por eje, pesos máximos y tipos de carga "
            "permitidos por configuración. Base documental para el catálogo de flota del RAG "
            "mientras el equipo construye el JSON de flota real."
        ),
        "tipo": "manual",
        "anno": 2018,
        "nota": (
            "Este documento cubre los tipos de vehículo legales en Colombia. "
            "El catálogo de flota real (vehículos específicos con matrícula, capacidad "
            "exacta y costo por km) debe ser provisto por el equipo del proyecto como "
            "JSON en esta misma carpeta: 02_catalogo_flota_vehicular/flota_real.json"
        ),
    },
    # -----------------------------------------------------------------------
    # CATEGORÍA 3 – Condiciones de rutas y vías
    # -----------------------------------------------------------------------
    {
        "id": "mintransporte_sicetac_distancias_rutas",
        "nombre": "mintransporte_sicetac_distancias_tipo_terreno_rutas.xlsx",
        "url": "https://plc.mintransporte.gov.co/Download.ashx?file=DISTANCIAS_TIPO_DE_TERRENO_RUTAS_SICETAC-2026-04-01.xlsx",
        "categoria": "03_condiciones_rutas_vias",
        "fuente": "MinTransporte / SICE-TAC",
        "descripcion": (
            "Distancias en kilómetros y tipo de terreno (plano, ondulado, montañoso) "
            "por ruta origen-destino reconocida oficialmente por el SICE-TAC. "
            "Dataset clave para que el RAG estime tiempo y consumo de combustible "
            "según la geografía real del corredor. Publicación de MinTransporte, "
            "actualización abril 2026."
        ),
        "tipo": "reporte",
        "anno": 2026,
        "formato_ingesta": "json",
    },
    # -----------------------------------------------------------------------
    # CATEGORÍA 4 – Tarifas y costos de transporte
    # -----------------------------------------------------------------------
    {
        "id": "mintransporte_sicetac_peajes_por_rutas",
        "nombre": "mintransporte_sicetac_peajes_por_rutas_con_tarifas.xlsx",
        "url": "https://plc.mintransporte.gov.co/Download.ashx?file=PeajesPorRutasConTarifas_SICETAC_2026-04-01.xlsx",
        "categoria": "04_tarifas_costos_transporte",
        "fuente": "MinTransporte / SICE-TAC",
        "descripcion": (
            "Peajes por ruta origen-destino con tarifas diferenciadas por categoría "
            "vehicular (I a VII). Dataset oficial del SICE-TAC que permite al RAG "
            "estimar el costo real de peajes en una ruta concreta. "
            "Actualización abril 2026."
        ),
        "tipo": "reporte",
        "anno": 2026,
        "formato_ingesta": "json",
    },
    {
        "id": "mintransporte_sicetac_abc_costos",
        "nombre": "mintransporte_sicetac_abc_costos_transporte_carga.pdf",
        "url": "https://web.mintransporte.gov.co/jspui/bitstream/001/10564/1/ABC-SICETAC%20%281%29%20%283%29.pdf",
        "categoria": "04_tarifas_costos_transporte",
        "fuente": "MinTransporte",
        "descripcion": (
            "ABC del SICE-TAC. El mismo documento de la categoría 02 se incluye aquí "
            "porque contiene la estructura de costos por tipo de vehículo: combustible, "
            "peajes, llantas, mantenimiento, conductor y administración. "
            "El RAG puede usar estos componentes para estimar costos cuando no hay "
            "tarifa específica de la flota real disponible."
        ),
        "tipo": "manual",
        "anno": 2018,
        "nota": (
            "Las tarifas reales negociadas por el área financiera del proyecto "
            "deben cargarse como hojas de cálculo en esta carpeta. "
            "Este documento es la referencia regulatoria de costos mínimos legales."
        ),
    },
]

# ---------------------------------------------------------------------------
# Funciones auxiliares
# ---------------------------------------------------------------------------


def crear_carpetas():
    """Crea la estructura de carpetas por categoría dentro de fuentes/."""
    BASE_CONOCIMIENTO.mkdir(exist_ok=True)
    CARPETA_BASE.mkdir(parents=True, exist_ok=True)
    categorias = set(doc["categoria"] for doc in DOCUMENTOS)
    for cat in categorias:
        (CARPETA_BASE / cat).mkdir(exist_ok=True)
    logging.info(f"Carpeta fuentes: {CARPETA_BASE.resolve()}")
    logging.info(f"Subcarpetas creadas: {sorted(categorias)}")


def calcular_hash(ruta_archivo: Path) -> str:
    """Calcula el hash SHA-256 del archivo descargado para verificación de integridad."""
    sha256 = hashlib.sha256()
    with open(ruta_archivo, "rb") as f:
        for bloque in iter(lambda: f.read(8192), b""):
            sha256.update(bloque)
    return sha256.hexdigest()


def descargar_documento(doc: dict) -> dict:
    """
    Descarga un documento y retorna un dict con el resultado y metadatos.
    Reintenta hasta REINTENTOS veces ante fallos de red.
    """
    ruta_destino = CARPETA_BASE / doc["categoria"] / doc["nombre"]

    # Si ya existe y tiene contenido, no volver a descargar
    if ruta_destino.exists() and ruta_destino.stat().st_size > 1000:
        logging.info(f"  [OMITIDO - ya existe] {doc['nombre']}")
        return {
            **doc,
            "estado": "omitido_ya_existe",
            "ruta_local": str(ruta_destino),
            "tamano_bytes": ruta_destino.stat().st_size,
            "sha256": calcular_hash(ruta_destino),
            "fecha_descarga": None,
        }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; RAG-KnowledgeBase-Builder/1.0; "
            "+https://github.com/tu-equipo/api-rag-vehiculos)"
        )
    }

    for intento in range(1, REINTENTOS + 1):
        try:
            logging.info(f"  [{intento}/{REINTENTOS}] Descargando: {doc['nombre']}")
            respuesta = requests.get(
                doc["url"],
                headers=headers,
                timeout=TIMEOUT_SEGUNDOS,
                stream=True,
                allow_redirects=True,
            )
            respuesta.raise_for_status()

            # Verificar que sea PDF
            content_type = respuesta.headers.get("Content-Type", "")
            if "html" in content_type.lower() and intento == REINTENTOS:
                logging.warning(
                    f"  [ADVERTENCIA] La respuesta parece HTML, no PDF: {doc['url']}"
                )

            # Guardar el archivo
            with open(ruta_destino, "wb") as f:
                for chunk in respuesta.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            tamano = ruta_destino.stat().st_size
            sha256 = calcular_hash(ruta_destino)
            fecha = datetime.now().isoformat()

            logging.info(
                f"  [OK] {doc['nombre']} "
                f"({tamano / 1024:.1f} KB) sha256={sha256[:12]}..."
            )

            return {
                **doc,
                "estado": "descargado",
                "ruta_local": str(ruta_destino),
                "tamano_bytes": tamano,
                "sha256": sha256,
                "fecha_descarga": fecha,
            }

        except requests.exceptions.HTTPError as e:
            logging.warning(f"  [HTTP {e.response.status_code}] {doc['url']}")
            if intento == REINTENTOS:
                return _resultado_fallido(doc, ruta_destino, str(e))
            time.sleep(PAUSA_ENTRE_DESCARGAS * intento)

        except requests.exceptions.ConnectionError as e:
            logging.warning(f"  [ERROR DE CONEXIÓN] {doc['url']}: {e}")
            if intento == REINTENTOS:
                return _resultado_fallido(doc, ruta_destino, str(e))
            time.sleep(PAUSA_ENTRE_DESCARGAS * intento)

        except requests.exceptions.Timeout:
            logging.warning(f"  [TIMEOUT] {doc['url']}")
            if intento == REINTENTOS:
                return _resultado_fallido(doc, ruta_destino, "Timeout")
            time.sleep(PAUSA_ENTRE_DESCARGAS * intento)

        except Exception as e:
            logging.error(f"  [ERROR INESPERADO] {doc['url']}: {e}")
            return _resultado_fallido(doc, ruta_destino, str(e))

    return _resultado_fallido(doc, ruta_destino, "Máximo de reintentos alcanzado")


def _resultado_fallido(doc: dict, ruta: Path, error: str) -> dict:
    """Construye un dict de resultado para un documento que no se pudo descargar."""
    if ruta.exists() and ruta.stat().st_size == 0:
        ruta.unlink()  # Eliminar archivo vacío
    logging.error(f"  [FALLIDO] {doc['nombre']}: {error}")
    if doc.get("nota"):
        logging.info(f"  → Nota: {doc['nota']}")
    return {
        **doc,
        "estado": "fallido",
        "ruta_local": None,
        "tamano_bytes": 0,
        "sha256": None,
        "fecha_descarga": None,
        "error": error,
    }


def guardar_metadata(resultados: list):
    """Guarda el archivo metadata.json con todos los resultados."""
    ruta_metadata = METADATA_PATH
    with open(ruta_metadata, "w", encoding="utf-8") as f:
        json.dump(
            {
                "generado_en": datetime.now().isoformat(),
                "total_documentos": len(resultados),
                "descargados": sum(1 for r in resultados if r["estado"] == "descargado"),
                "omitidos": sum(1 for r in resultados if r["estado"] == "omitido_ya_existe"),
                "fallidos": sum(1 for r in resultados if r["estado"] == "fallido"),
                "documentos": resultados,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    logging.info(f"Metadata guardada en: {ruta_metadata.resolve()}")


def imprimir_resumen(resultados: list):
    """Imprime un resumen legible al final de la ejecución."""
    descargados = [r for r in resultados if r["estado"] == "descargado"]
    omitidos = [r for r in resultados if r["estado"] == "omitido_ya_existe"]
    fallidos = [r for r in resultados if r["estado"] == "fallido"]

    print("\n" + "=" * 60)
    print("RESUMEN DE DESCARGA")
    print("=" * 60)
    print(f"  Total documentos procesados : {len(resultados)}")
    print(f"  Descargados exitosamente    : {len(descargados)}")
    print(f"  Omitidos (ya existían)      : {len(omitidos)}")
    print(f"  Fallidos                    : {len(fallidos)}")

    if fallidos:
        print("\nDOCUMENTOS QUE REQUIEREN DESCARGA MANUAL:")
        for r in fallidos:
            print(f"  - {r['nombre']}")
            print(f"    URL     : {r['url']}")
            if r.get("nota"):
                print(f"    Nota    : {r['nota']}")
            print(f"    Destino : {CARPETA_BASE / r['categoria'] / r['nombre']}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------


def main():
    print("\nDescarga de base de conocimiento - API RAG para selección de vehículo")
    print(f"Carpeta destino: {CARPETA_BASE.resolve()}\n")

    crear_carpetas()

    # Reconfigurar el handler de log al archivo ahora que la carpeta existe
    log_path = BASE_CONOCIMIENTO / "descarga_log.txt"
    file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s  %(levelname)s  %(message)s")
    )
    logging.getLogger().addHandler(file_handler)

    resultados = []
    for i, doc in enumerate(DOCUMENTOS, start=1):
        print(f"\n[{i}/{len(DOCUMENTOS)}] {doc['fuente']} → {doc['nombre']}")
        resultado = descargar_documento(doc)
        resultados.append(resultado)
        time.sleep(PAUSA_ENTRE_DESCARGAS)

    guardar_metadata(resultados)
    imprimir_resumen(resultados)
    print(f"\nLog completo en: {log_path.resolve()}")


if __name__ == "__main__":
    main()
