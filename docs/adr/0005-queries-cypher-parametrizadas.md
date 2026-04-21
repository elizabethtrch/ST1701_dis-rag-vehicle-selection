# ADR-0005: Queries Cypher fijas parametrizadas

- **Status**: Accepted
- **Date**: 2026-04-20
- **Deciders**: Edward Rayo, Elizabeth Toro, Santiago Cardona

## Contexto

Con Neo4j como segunda base del RAG hay dos maneras de hacer que el
servicio de recomendación consulte el grafo a partir del JSON de
entrada:

- **A — Queries Cypher fijas parametrizadas**: el código tiene un set
  pequeño de queries predefinidas, cada una con parámetros (`$productos`,
  `$origen`, `$destino`, `$flota`). El JSON de entrada de la API llena
  esos parámetros y el código ejecuta las queries. Los resultados se
  ensamblan como contexto estructurado que se pasa al LLM.
- **B — Text-to-Cypher agéntico**: el LLM recibe el esquema del grafo y
  la pregunta, y genera Cypher dinámicamente. El código ejecuta el
  Cypher en un sandbox.

## Decisión

Adoptar la **opción A** para el flujo principal de recomendación. El
`RecommendationService` ejecuta un set pequeño de queries Cypher fijas
(≈5) con parámetros extraídos del JSON de entrada. El LLM nunca escribe
Cypher; recibe los resultados ya estructurados como contexto en el
prompt, junto con los chunks recuperados de ChromaDB.

Flujo:

```
JSON entrada → extracción de parámetros → [Q1..Q5 Cypher + Chroma
  retrieval] → contexto estructurado → prompt al LLM → JSON salida
```

## Consecuencias

- **Positivas**:
  - Determinismo: las mismas entradas producen las mismas recuperaciones.
  - Costo y latencia bajos: no hay un paso intermedio de generación de
    Cypher.
  - Testeable: cada query puede probarse en aislamiento.
  - Seguro: sin riesgo de inyección Cypher.
- **Negativas**:
  - Menos flexible ante consultas fuera del catálogo fijo. Si aparece
    una necesidad nueva, hay que agregar la query.
  - Riesgo de evolucionar hacia un pseudo-ORM si el set de queries
    crece sin control.
- **Neutrales**:
  - La puerta al enfoque B queda abierta: se puede agregar más adelante
    una herramienta `tool_use` `query_grafo(cypher)` para casos
    ad-hoc, sin reemplazar las queries fijas.

