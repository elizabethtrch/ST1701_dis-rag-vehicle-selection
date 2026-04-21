#!/usr/bin/env python3
"""
Genera el .md de distancias SICE-TAC a partir del JSON ya estructurado.

El pipeline convierte el XLSX a JSON vía pandas (formato_ingesta: "json").
Este script lee ese JSON y produce un .md con las rutas entre hubs logísticos
principales de Colombia, listo para ingesta vectorial en ChromaDB.

Se ejecuta siempre que el JSON exista, sobreescribiendo el .md anterior
(el JSON es la fuente de verdad; el .md es derivado).

Uso:
    python scripts/generar_sicetac_md.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
JSON_PATH = (
    BASE_DIR
    / "base_conocimiento"
    / "estructurados"
    / "03_condiciones_rutas_vias"
    / "mintransporte_sicetac_distancias_tipo_terreno_rutas.json"
)
MD_PATH = JSON_PATH.with_suffix(".md")

# Hubs logísticos principales de Colombia relevantes para logística agrícola
HUBS = [
    "BOGOTÁ", "BOGOTA", "MEDELLÍN", "MEDELLIN", "CALI", "BARRANQUILLA",
    "BUCARAMANGA", "PEREIRA", "ARMENIA", "MANIZALES", "IBAGUÉ", "IBAGUE",
    "TUNJA", "VILLAVICENCIO", "BUENAVENTURA", "SANTA MARTA", "CARTAGENA",
    "MONTERÍA", "MONTERIA", "NEIVA", "PASTO", "CÚCUTA", "CUCUTA",
    "POPAYÁN", "POPAYAN", "PALMIRA", "BUGA", "RIONEGRO", "GIRARDOT",
    "HONDA", "ESPINAL", "URABÁ", "URABA", "APARTADÓ", "APARTADO",
]

FIELD_KEY = "DISTANCIAS POR TIPO DE TERRENO RUTAS SICETAC 01-04-2026"


def _es_hub(ciudad: str) -> bool:
    ciudad_upper = ciudad.upper()
    return any(h in ciudad_upper for h in HUBS)


def _filtrar_registros(data: dict) -> list[dict]:
    registros = []
    for r in data["registros"]:
        id_val = r.get(FIELD_KEY, "")
        if not isinstance(id_val, (int, float)):
            continue
        nombre = str(r.get("Unnamed: 3", "")).strip()
        partes = [p.strip() for p in nombre.split("_")]
        if len(partes) == 2 and _es_hub(partes[0]) and _es_hub(partes[1]):
            registros.append({
                "id": int(id_val),
                "nombre": nombre,
                "via": str(r.get("Unnamed: 4", "") or "").strip(),
                "distancia_km": float(r.get("Unnamed: 5") or 0),
                "plano_km": float(r.get("Unnamed: 6") or 0),
                "ondulado_km": float(r.get("Unnamed: 7") or 0),
                "montana_km": float(r.get("Unnamed: 8") or 0),
                "urbano_km": float(r.get("Unnamed: 9") or 0),
                "despavimentado_km": float(r.get("Unnamed: 10") or 0),
            })
    return sorted(registros, key=lambda x: x["nombre"])


def generar(json_path: Path = JSON_PATH, md_path: Path = MD_PATH) -> bool:
    if not json_path.exists():
        print(f"[ERROR] JSON no encontrado: {json_path}")
        print("        Ejecuta primero el pipeline de descarga/estructuración.")
        return False

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    registros = _filtrar_registros(data)
    total_dataset = data["metadata"]["total_registros"]

    lines = [
        "---",
        "fuente: MinTransporte / SICE-TAC",
        "titulo: Distancias y tipo de terreno por ruta – SICE-TAC 2026 (corredores entre hubs logísticos)",
        "anno: 2026",
        "categoria_rag: condiciones_rutas_vias",
        "tipo: dataset",
        f"url_origen: {data['metadata']['url_origen']}",
        f"fecha_procesamiento: {datetime.now().strftime('%Y-%m-%d')}",
        f"total_rutas_dataset_completo: {total_dataset}",
        f"total_rutas_este_archivo: {len(registros)}",
        "ambito_geografico: Colombia",
        "nota_cobertura: >",
        "  Subconjunto del dataset SICE-TAC con rutas hub↔hub (ambos extremos son",
        "  un centro logístico principal). El JSON fuente con las 9.675 rutas completas",
        "  se encuentra en el mismo directorio.",
        "md_generado: true",
        "---",
        "",
        "# Distancias y tipo de terreno por ruta – SICE-TAC 2026",
        "",
        "Datos oficiales de MinTransporte (SICE-TAC, abril 2026). Cada fila desglosa",
        "la distancia total de un corredor en kilómetros de terreno plano, ondulado,",
        "montañoso, urbano y despavimentado.",
        "",
        "**Interpretación para el RAG:**",
        "- **Plano**: velocidad alta, menor consumo, menor vibración.",
        "- **Ondulado**: velocidad media, consumo moderado.",
        "- **Montañoso**: velocidad baja (~30–45 km/h cargado), mayor consumo, mayor vibración.",
        "- **Despavimentado**: riesgo alto de daño a perecederos sensibles (flores, mora, espárrago).",
        "- **% montañoso > 30%**: se recomienda suspensión reforzada para carga frágil.",
        "",
        "## Corredores entre hubs logísticos principales",
        "",
        "| Ruta (Origen → Destino) | Dist. total (km) | Plano (km) | Ondulado (km) | Montañoso (km) | Urbano (km) | Despavimt. (km) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]

    for r in registros:
        via = r["via"]
        via_note = f" *(vía {via[:60]}{'...' if len(via) > 60 else ''})*" if via else ""
        lines.append(
            f"| {r['nombre']}{via_note} | {r['distancia_km']} | {r['plano_km']} | "
            f"{r['ondulado_km']} | {r['montana_km']} | {r['urbano_km']} | {r['despavimentado_km']} |"
        )

    lines += [
        "",
        "## Notas de uso",
        "",
        "- Las distancias son para el corredor oficial SICE-TAC; pueden existir rutas",
        "  alternativas con diferente perfil de terreno.",
        "- Velocidad media referencial para carga: 45 km/h montañoso, 60 km/h ondulado,",
        "  70 km/h plano.",
        "- Despavimentado > 0 km indica tramos de vía terciaria o destapada; en épocas",
        "  de lluvia pueden tener restricciones de circulación.",
        "",
        "## Fragmentos clave para el RAG",
        "",
        "**Cómo usar esta tabla:**",
        "\"Para consultar la distancia entre dos ciudades colombianas busca la fila cuyo",
        "NOMBRE sea 'CIUDAD_ORIGEN _ CIUDAD_DESTINO'. La columna Dist. total es la",
        "distancia oficial SICE-TAC en kilómetros. Las columnas Plano, Ondulado y",
        "Montañoso indican el perfil de terreno; un corredor con más del 30% de terreno",
        "montañoso requiere mayor tiempo de tránsito y puede aumentar el riesgo de daño",
        "a carga perecedera sensible (flores, mora, espárrago).\"",
        "",
        "**Estimación de tiempo de tránsito para carga:**",
        "\"Tiempo estimado (h) = km_plano/70 + km_ondulado/60 + km_montañoso/45.",
        "Agregar 20% de margen por paradas operativas (cargue/descargue, peajes, descansos).",
        "En corredores con despavimentado > 0 km agregar 30 min adicionales por cada",
        "10 km de vía sin pavimentar.\"",
        "",
        "**Corredores críticos para logística agrícola:**",
        "\"Los corredores con mayor tráfico agrícola son: Bogotá-Medellín (414 km,",
        "mayoría montañoso), Bogotá-Cali (~460 km, mixto), Armenia-Bogotá (264 km,",
        "49 km montañoso), Cali-Buenaventura (155 km, acceso al puerto de exportación),",
        "Tunja-Bogotá (148 km, corredor papa/cebolla/zanahoria de Boyacá).\"",
    ]

    md_path.write_text("\n".join(lines), encoding="utf-8")
    size_kb = md_path.stat().st_size // 1024
    print(f"[OK] {md_path.relative_to(BASE_DIR)} ({size_kb} KB, {len(registros)} rutas de {total_dataset})")
    return True


if __name__ == "__main__":
    ok = generar()
    sys.exit(0 if ok else 1)

