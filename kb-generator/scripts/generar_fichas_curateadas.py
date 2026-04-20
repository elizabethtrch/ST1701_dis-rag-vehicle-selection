#!/usr/bin/env python3
"""
Genera fichas técnicas curateadas que no tienen PDF fuente descargable.

Estas fichas representan conocimiento consolidado de múltiples fuentes
institucionales (ICA, FNC, AGROSAVIA, etc.) que no está disponible en
un único documento descargable. El contenido se mantiene versionado
aquí, dentro del código del pipeline.

Comportamiento: idempotente. Si el .md ya existe, no lo sobreescribe
a menos que se pase --forzar.

Uso:
    python scripts/generar_fichas_curateadas.py
    python scripts/generar_fichas_curateadas.py --forzar
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
ESTRUCTURADOS = BASE_DIR / "base_conocimiento" / "estructurados"

# ---------------------------------------------------------------------------
# Fichas curateadas
# Cada entrada: (ruta_relativa_a_estructurados, contenido_md)
# ---------------------------------------------------------------------------

FICHAS: list[tuple[str, str]] = [
    (
        "01_fichas_tecnicas_productos/ica_fnc_ficha_tecnica_transporte_cafe_colombia.md",
        """\
---
fuente: ICA / Federación Nacional de Cafeteros (FNC)
titulo: Ficha técnica de transporte de café colombiano – pergamino húmedo, pergamino seco y grano verde
anno: 2024
categoria_rag: fichas_tecnicas_productos
tipo: ficha_tecnica
url_origen: https://www.federaciondecafeteros.org
normas_relacionadas:
  - Resolución ICA 3168 de 2015 (transporte de material vegetal de café)
  - Norma Técnica Colombiana NTC 2090 (café verde, requisitos)
  - NTC 3534 (café tostado y molido)
  - Decreto 1071 de 2015 (uso y manejo de materiales de empaque para café)
fecha_procesamiento: 2026-04-20
ambito_geografico: Colombia
productos_cubiertos:
  - café pergamino húmedo (recién beneficiado)
  - café pergamino seco (beneficio completo)
  - café en grano verde (trilla)
  - café especial (microlotes, exportación)
md_generado: true
---

# Ficha técnica: Transporte de café colombiano

## Descripción del producto

El café es el principal producto de exportación agrícola de Colombia y el segundo
rubro de carga agrícola por volumen en el sistema vial nacional. Se transporta
en tres estados principales según la etapa de beneficio:

| Estado | Descripción | Humedad típica | Embalaje común |
|---|---|---|---|
| **Pergamino húmedo** | Recién despulpado y lavado; humedad alta | 40–55% | Costales de fique o polipropileno |
| **Pergamino seco** | Secado en marquesina/patio hasta punto de trilla | 10–12% | Costales de fique 50–70 kg |
| **Grano verde (trillado)** | Sin cáscara de pergamino, listo para exportación | 10–12.5% | Sacos de yute 60–70 kg (exportación) / big bags a granel |
| **Café especial** | Micro-lotes con trazabilidad, selección por calidad | 10–12% | Costales etiquetados individualmente |

---

## Condiciones de transporte requeridas

### Temperatura

| Estado del café | Temperatura óptima de transporte | Rango aceptable | Riesgo si se supera |
|---|---|---|---|
| Pergamino húmedo | 15–20 °C | 10–25 °C | Fermentación, desarrollo de hongos, pérdida de calidad en taza |
| Pergamino seco | 15–25 °C | 10–30 °C | Absorción de humedad si hay condensación en vehículo frío |
| Grano verde | 15–25 °C | 10–30 °C | Daño por humedad relativa alta > 70% si hay cambios bruscos de temperatura |
| Café especial | 15–20 °C | 10–25 °C | Oxidación prematura, pérdida de perfil aromático |

**El café NO requiere cadena de frío activa (refrigeración mecánica).** El control crítico
es la humedad relativa, no la temperatura.

### Humedad relativa (HR)

| Estado del café | HR óptima | HR máxima tolerable | Riesgo |
|---|---|---|---|
| Pergamino húmedo | — (requiere circulación de aire, no es almacenable) | — | Requiere procesamiento inmediato; no aplica almacenamiento prolongado |
| Pergamino seco | 55–65% | 70% | > 70% HR: rehumectación, desarrollo de hongos (*Aspergillus*, *Fusarium*) |
| Grano verde | 60–65% | 70% | Igual que pergamino seco |
| Café especial | 55–65% | 68% | Pérdida de perfil aromático, riesgo de certificación |

---

## Tipo de vehículo recomendado

| Distancia / condición | Tipo de vehículo recomendado | Justificación |
|---|---|---|
| Finca → cooperativa / punto de acopio (< 50 km, vía terciaria) | **Camión estacas** o **camioneta** con carpa impermeable | Vías estrechas y sin pavimentar; el fique transpira naturalmente; la carpa evita lluvia directa |
| Acopio → trilladora / puerto seco (50–400 km, vía primaria/secundaria) | **Camión sencillo o doble troque** con furgón seco o carpa | Carga a granel en costales; el furgón seco evita condensación |
| Puerto seco → puerto marítimo (exportación) | **Tractocamión** con contenedor de 20' o 40' seco | Normas de exportación exigen contenedor seco limpio, sin olores ajenos |
| Microlotes / cafés especiales | **Camioneta furgón seco** o **camión sencillo furgón** | Mantenimiento de trazabilidad; los costales etiquetados no deben mezclarse |

**El café NUNCA debe transportarse en vehículo refrigerado.** Las bajas temperaturas
del furgón refrigerado generan condensación cuando el café entra en contacto con
aire más cálido, lo que provoca rehumectación y pérdida de calidad irreversible.

---

## Requisitos de embalaje y estiba

- **Costales de fique (cabuya)**: material preferido para pergamino seco y grano verde.
  El fique es transpirable y no aporta olores al grano. Capacidad estándar 50–70 kg.
- **Costales de polipropileno**: aceptados para pergamino húmedo en tránsito corto;
  no recomendados para almacenamiento o transporte largo (no transpiran).
- **Big bags (FIBC)**: para carga a granel de grandes volúmenes (≥ 500 kg) en traslados
  finca-trilladora; deben ser de material transpirable o con liner de papel.
- **Estiba**: los sacos deben ir sobre estibas de madera o plástico, nunca directamente
  sobre el piso del vehículo; separación mínima de 10 cm de las paredes metálicas.
- **Prohibido mezclar**: el café NO debe transportarse con fertilizantes, plaguicidas,
  combustibles ni alimentos de fuerte olor (cebolla, ajo, pescado); absorbe olores
  con facilidad (artículo 29.8 Res. 2674/2013).

---

## Restricciones y alertas operativas

### Humedad del pergamino seco: control crítico en puerto

La NTC 2090 exige que el café verde exportado tenga humedad máxima de 12.5%.
Si el grano llega al puerto con humedad > 13%, puede ser rechazado por el comprador
o retenido por autoridades sanitarias. El transporte en vehículo abierto en épocas
de lluvia intensa puede elevar la humedad del grano si los costales no están cubiertos.

### Vías terciarias y café pergamino húmedo

El café pergamino húmedo se recoge en finca y debe llegar a la cooperativa/beneficiadero
en menos de **6–8 horas** para evitar fermentación excesiva. En vías terciarias con
restricciones por lluvia, este límite de tiempo puede incumplirse, afectando la calidad
de taza. Se recomienda tener rutas alternas identificadas o acordar recolección antes
de períodos de lluvia intensa.

### Corredor Eje Cafetero → Bogotá / Puertos

Los principales corredores de café en Colombia son:

| Corredor | Características de terreno | Observaciones |
|---|---|---|
| Chinchiná / Manizales → Bogotá | Alto porcentaje montañoso (Cordillera Central) | Velocidad media carga ~40 km/h; tiempo estimado 4–6 h |
| Armenia → Bogotá | Mixto: montañoso + plano (Sabana) | Perfil: Calarcá, Cajamarca, Ibagué, Fusagasugá; 264 km |
| Pereira → Bogotá | Montañoso al inicio, plano al final | Similar a Armenia; 290–310 km según ruta |
| Eje Cafetero → Buenaventura | Mayoritariamente plano (Valle del Cauca) desde Armenia/Pereira | Principal ruta de exportación marítima |
| Huila (Neiva) → Bogotá | Ondulado-montañoso (Cordillera Oriental) | ~315 km; incluye tramos con vías en mal estado |
| Sierra Nevada → Santa Marta (puerto) | Tramos despavimentados en finca; pavimentado desde Ciénaga | Puerto de Santa Marta recibe café de exportación |

---

## Normativa aplicable

| Norma | Alcance para el café |
|---|---|
| **NTC 2090** (ICONTEC) | Especificaciones café verde: humedad máx. 12.5%, defectos, granulometría |
| **Resolución ICA 3168/2015** | Movilización de material vegetal de café (semillas, colinos, plantas); requiere salvoconducto ICA |
| **Resolución INVIMA 2674/2013, Art. 29** | Condiciones higiénicas del vehículo; leyenda "Transporte de Alimentos"; prohibición de mezcla con sustancias peligrosas |
| **Resolución INVIMA 2674/2013, Art. 37** | El café en grano verde (sin transformación) está exento de Registro Sanitario pero sí debe cumplir condiciones de transporte del Art. 29 |
| **Mintransporte Res. 2505/2004** | No aplica directamente (es para alimentos que requieren control de temperatura); el café seco no requiere cadena de frío |
| **Normas FNC de calidad** | Estándares de humedad, impurezas y defectos aplicables a café que se entrega a la Federación bajo precio de garantía |

---

## Fragmentos clave para el RAG

**Condición de transporte principal:**
"El café pergamino seco y grano verde colombiano se transporta en vehículo seco (camión
estacas con carpa o furgón seco) a temperatura ambiente entre 15 y 25 °C, con humedad
relativa máxima de 70%. No requiere refrigeración. El control crítico es evitar la
rehumectación del grano, que provoca desarrollo de hongos y rechazo en exportación."

**Tipo de vehículo por etapa:**
"En finca y vías terciarias: camión estacas o camioneta con carpa impermeable.
En corredor principal (acopio → trilladora → puerto): camión sencillo o doble troque
con furgón seco o carrocería cerrada. Para exportación: tractocamión con contenedor
de 20 pies seco y limpio, sin olores ajenos."

**Café pergamino húmedo (tiempo crítico):**
"El café pergamino húmedo debe llegar al beneficiadero en menos de 6–8 horas desde
la recolección para evitar sobre-fermentación. En vías terciarias con restricciones
por lluvia este tiempo puede incumplirse, comprometiendo la calidad de taza. Es el
único estado del café donde el tiempo de tránsito es tan crítico como la temperatura
lo es para los perecederos refrigerados."

**Prohibición de mezcla:**
"El café absorbe olores con facilidad. Está prohibido transportarlo junto con
fertilizantes, plaguicidas, combustibles, cebolla, ajo, pescado u otros productos
de olor fuerte (Art. 29.8, Res. 2674/2013). Esta restricción es igualmente válida
para bodegas de almacenamiento intermedio."
""",
    ),
]


def generar_todas(forzar: bool = False) -> dict:
    creados = 0
    omitidos = 0
    errores = 0

    for ruta_rel, contenido in FICHAS:
        destino = ESTRUCTURADOS / ruta_rel
        destino.parent.mkdir(parents=True, exist_ok=True)

        if destino.exists() and not forzar:
            print(f"[--] Omitido (ya existe): {ruta_rel}")
            omitidos += 1
            continue

        try:
            destino.write_text(contenido, encoding="utf-8")
            accion = "Sobreescrito" if destino.exists() else "Creado"
            print(f"[OK] {accion}: {ruta_rel}")
            creados += 1
        except OSError as e:
            print(f"[ERROR] No se pudo escribir {ruta_rel}: {e}")
            errores += 1

    return {"creados": creados, "omitidos": omitidos, "errores": errores}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genera fichas técnicas curateadas sin PDF fuente.")
    parser.add_argument(
        "--forzar",
        action="store_true",
        help="Sobreescribir fichas aunque ya existan.",
    )
    args = parser.parse_args()

    stats = generar_todas(forzar=args.forzar)
    print(
        f"\nResumen: {stats['creados']} creados, "
        f"{stats['omitidos']} omitidos, {stats['errores']} errores."
    )
    sys.exit(1 if stats["errores"] else 0)

