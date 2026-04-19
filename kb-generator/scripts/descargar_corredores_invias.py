#!/usr/bin/env python3
"""
Descarga los corredores viales publicados por la API de INVIAS
y genera un JSON estructurado para ingestión al RAG.

Uso:
    python scripts/descargar_corredores_invias.py

Salida:
    base_conocimiento/03_condiciones_rutas_vias/invias_corredores.json
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

API_BASE = "https://invias-viajero.vercel.app/api"
SALIDA = Path(
    "./base_conocimiento/estructurados/03_condiciones_rutas_vias/invias_corredores.json"
)
TIMEOUT_SEGUNDOS = 30
PAUSA_ENTRE_LLAMADAS = 1

HEADERS = {
    "User-Agent": (
        "RAG-KnowledgeBase-Builder/1.0 "
        "(api-rag-vehiculos; transporte agricola Colombia)"
    ),
    "Accept": "application/json",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
)


# ---------------------------------------------------------------------------
# Transformaciones
# ---------------------------------------------------------------------------


def transformar_nombre(nombre: str) -> str:
    """'Bogotá → Villavicencio' → 'De Bogotá a Villavicencio'."""
    if "→" in nombre:
        origen, destino = (p.strip() for p in nombre.split("→", 1))
        return f"De {origen} a {destino}"
    return nombre


def agregar_alertas(alertas: list) -> dict:
    """Cuenta alertas Waze por tipo sin conservar uuids individuales."""
    conteo = {
        "accidentes": 0,
        "vias_cerradas": 0,
        "peligros": 0,
        "otros": 0,
        "total": len(alertas),
        "criticas": 0,
    }
    for a in alertas:
        tipo = (a.get("tipo") or "").lower()
        if "accidente" in tipo:
            conteo["accidentes"] += 1
        elif "cerrada" in tipo:
            conteo["vias_cerradas"] += 1
        elif "peligro" in tipo:
            conteo["peligros"] += 1
        else:
            conteo["otros"] += 1
        if a.get("esCritica"):
            conteo["criticas"] += 1
    return conteo


def agregar_congestiones(congestiones: list) -> dict:
    """Resume congestiones Waze por nivel sin conservar polilíneas."""
    return {
        "total": len(congestiones),
        "nivel_4_criticas": sum(1 for c in congestiones if c.get("nivel") == 4),
        "nivel_5_paradas": sum(1 for c in congestiones if c.get("nivel") == 5),
        "longitud_total_m": sum(c.get("longitudM", 0) for c in congestiones),
    }


def transformar_corredor(detalle: dict) -> dict:
    """Aplana la respuesta del API al esquema acordado."""
    c = detalle["corredor"]
    est = detalle.get("estimacion", {})
    est_carga = detalle.get("estimacionCarga", {})
    waze = detalle.get("waze", {})

    return {
        "id": c["id"],
        "nombre": transformar_nombre(c.get("nombre", "")),
        "distancia_km": c.get("distanciaKm"),
        "departamentos": c.get("departamentos", []),
        "es_critico": c.get("esCritico", False),
        "tiempo_base_min_vehiculo_particular": c.get("tiempoBaseMin"),
        "tiempo_base_min_carga": est_carga.get("tiempoBaseMin"),
        "tiempo_estimado_min_carga": est_carga.get("tiempoEstimadoMin"),
        "tiempo_formateado_carga": est_carga.get("tiempoFormateado"),
        "estado_general": est.get("estadoGeneral"),
        "estado_general_carga": est_carga.get("estadoGeneral"),
        "cantidad_incidentes": est.get("cantidadIncidentes", 0),
        "impacto_waze_min": waze.get("impactoWazeMin", 0),
        "impacto_min_vehiculo_particular": est.get("impactoTotalMin", 0),
        "impacto_min_carga": est_carga.get("impactoTotalMin", 0),
        "resumen_alertas": agregar_alertas(waze.get("alertas", [])),
        "resumen_congestiones": agregar_congestiones(waze.get("congestiones", [])),
    }


# ---------------------------------------------------------------------------
# Llamadas al API
# ---------------------------------------------------------------------------


def obtener_lista_corredores() -> list:
    url = f"{API_BASE}/corredores"
    logging.info(f"Consultando lista: {url}")
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SEGUNDOS)
    r.raise_for_status()
    return r.json()


def obtener_detalle_corredor(corredor_id: str) -> dict:
    url = f"{API_BASE}/ruta/{corredor_id}"
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SEGUNDOS)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# Orquestación
# ---------------------------------------------------------------------------


def main():
    SALIDA.parent.mkdir(parents=True, exist_ok=True)

    try:
        lista = obtener_lista_corredores()
    except requests.RequestException as e:
        logging.error(f"No se pudo obtener la lista de corredores: {e}")
        return 1

    logging.info(f"Corredores disponibles en el API: {len(lista)}")

    corredores_procesados = []
    fallidos = []

    for i, item in enumerate(lista, 1):
        cid = item.get("corredor", {}).get("id")
        nombre = item.get("corredor", {}).get("nombreCorto", cid or "?")
        if not cid:
            logging.warning(f"[{i}/{len(lista)}] Entrada sin id, se omite.")
            continue

        logging.info(f"[{i}/{len(lista)}] {cid} — {nombre}")
        try:
            detalle = obtener_detalle_corredor(cid)
            corredores_procesados.append(transformar_corredor(detalle))
        except Exception as e:
            logging.error(f"  Fallo en {cid}: {e}")
            fallidos.append({"id": cid, "nombre": nombre, "error": str(e)})
        time.sleep(PAUSA_ENTRE_LLAMADAS)

    salida = {
        "metadata": {
            "fuente": "INVIAS - API corredores",
            "url_base": API_BASE,
            "fecha_snapshot": datetime.now(timezone.utc).isoformat(),
            "volatilidad": "alta",
            "nota_actualizacion": (
                "Los campos de trafico (estado_general, incidentes, alertas, "
                "congestiones) reflejan el estado al momento del snapshot. "
                "Re-ejecutar este script antes de cada ingestion al RAG."
            ),
            "total_corredores": len(corredores_procesados),
            "corredores_fallidos": fallidos,
        },
        "corredores": corredores_procesados,
    }

    SALIDA.write_text(
        json.dumps(salida, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logging.info(f"Archivo generado: {SALIDA.resolve()}")
    logging.info(f"Corredores procesados: {len(corredores_procesados)}")
    if fallidos:
        logging.warning(f"Corredores fallidos: {len(fallidos)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

