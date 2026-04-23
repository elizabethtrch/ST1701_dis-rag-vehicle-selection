---
name: llm-evaluator
description: >
  Skill para analizar y comparar resultados de múltiples LLMs evaluados sobre
  el sistema RAG de selección de vehículos agrícolas. Úsalo cuando el agente
  de comparación necesite generar las secciones analíticas del informe técnico:
  comparación cualitativa de respuestas (3.1), valoración con tabla de criterios
  (3.2), análisis de librerías (4.1) y análisis de herramientas con ranking (4.2).
---

# Skill: LLM Evaluator — RAG Selección de Vehículo

## Propósito

Analizar los resultados de una evaluación comparativa de múltiples LLMs sobre un sistema RAG
de selección de vehículos para logística agrícola colombiana, y generar las secciones analíticas
de un informe técnico académico.

---

## Contexto del sistema evaluado

El sistema RAG recomienda vehículos de transporte para productos agrícolas colombianos.
Cada LLM recibe el mismo prompt con:
- Contexto documental recuperado de ChromaDB (fichas técnicas, normativa, corredores viales)
- Contexto estructurado de Neo4j (corredor, requisitos del producto, tarifas, normativa)
- Solicitud de transporte con flota disponible

El LLM debe responder en JSON con los campos: `vehiculo_id`, `justificacion`, `alternativas`, `alertas`.

---

## Criterios de evaluación

| Criterio | Descripción |
|---|---|
| Adherencia al Schema | El JSON contiene los 4 campos canónicos sin variaciones |
| Selección del Vehículo | Elige el vehículo técnicamente correcto (capacidad + refrigeración) |
| Calidad de Justificación | Justificación técnica, coherente, en español, > 40 palabras |
| Completitud | Lista todos los vehículos descartados en `alternativas` |
| Veracidad | Los datos mencionados coinciden con la solicitud real |
| Relevancia | Aborda directamente los requisitos del pedido |
| Precisión Técnica | Menciona capacidad exacta y normativa colombiana aplicable |
| Idioma | Responde en español |

---

## Instrucciones de análisis

### Sección 3.1 — Comparación de Resultados

1. Genera una tabla Markdown comparativa con columnas por proveedor evaluado.
   Filas: Estructura JSON, Vehículo seleccionado, Idioma, Calidad justificación,
   Alternativas incluidas, Latencia promedio.
2. Por cada proveedor, escribe un párrafo de análisis citando evidencia concreta
   de sus respuestas (fragmentos reales del JSON generado).
3. Destaca diferencias observadas: schema incorrecto, idioma incorrecto,
   campos inventados, justificaciones vacías o genéricas.

### Sección 3.2 — Valoración

1. Genera una tabla con columnas: Criterio | Descripción | [proveedor1] | [proveedor2] | ... | Mejor modelo
2. Usa los puntajes agregados (media sobre todas las solicitudes) para cada criterio.
3. Añade una columna "Mejor modelo" indicando qué proveedor obtuvo el mayor puntaje en ese criterio.
4. Escribe un párrafo de conclusión: qué modelo es más adecuado para producción y por qué.

### Sección 4.1 — Librerías y Frameworks

1. Genera una tabla: Librería | Proveedor | Separación system/user | Soporte JSON forzado |
   Facilidad de integración | Limitaciones observadas
2. Basa el análisis en lo observado en los resultados, no en descripciones genéricas.
3. Añade un párrafo comparativo final.

### Sección 4.2 — Herramientas

1. Genera una tabla: Herramienta | Rol | Fortalezas observadas | Limitaciones | Impacto en RAG
2. Genera tabla de ranking final: Posición | Proveedor | Modelo | Promedio global |
   Fortaleza principal | Debilidad principal | Recomendación de uso
3. Escribe conclusión indicando el LLM recomendado para este sistema en producción.

---

## Reglas de formato

- **Siempre** usa tablas Markdown donde se indique — es obligatorio.
- Escribe en español técnico y académico.
- Fundamenta cada afirmación en los datos del contexto proporcionado.
- No inventes datos que no estén en el contexto.
- No añadas secciones extra no solicitadas.
- Responde directamente con el contenido, sin encabezados adicionales de nivel 1 o 2.

