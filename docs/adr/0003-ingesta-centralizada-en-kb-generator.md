# ADR-0003: Ingesta centralizada en kb-generator

- **Status**: Accepted
- **Date**: 2026-04-20
- **Deciders**: Edward Rayo, Elizabeth Toro, Santiago Cardona

## Contexto

Originalmente la API incluía su propio pipeline de ingestión:

- `api/src/core/services/ingestion_service.py`
- `api/src/adapters/input/cli/ingest_cli.py`

En paralelo, `kb-generator/` genera los artefactos estructurados que
alimentan el RAG (Markdowns con YAML frontmatter, JSON de INVIAS), pero
no los ingesta a las bases. Mantener dos rutas de ingesta lleva a
divergencia de reglas (cómo se chunkea, qué metadatos se guardan, cómo
se extraen entidades para Neo4j) y diluye la responsabilidad.

## Decisión

Toda la ingesta vive en **`kb-generator/`** como módulo `ingester/` con
una CLI (`typer`) que soporta dos modos en el mismo punto de entrada:

- **Batch**: `ingest-all` lee todo `base_conocimiento/estructurados/` y
  reconstruye Chroma + Neo4j.
- **Ad-hoc**: `ingest-file <path>` indexa un documento suelto;
  `reindex [--categoria X]` re-procesa una categoría.
- **Operación**: `stats` reporta inventario indexado.

La API queda como **puro consumidor**: se eliminan
`api/src/core/services/ingestion_service.py` y
`api/src/adapters/input/cli/`.

## Consecuencias

- **Positivas**:
  - Un único lugar donde se definen reglas de chunking, extracción de
    entidades y carga de grafo.
  - Separación clara: `kb-generator` = productor (batch offline), `api`
    = consumidor (runtime online).
  - Consistencia garantizada entre MDs estructurados y lo que vive en
    las bases.
- **Negativas**:
  - Perdemos la ingesta desde la propia API (p.ej. subir un documento
    vía endpoint). Si más adelante se necesita, se puede agregar un
    endpoint en la API que dispare al ingester como proceso.
- **Neutrales**:
  - El código de ingestión se borra de `api/`; su historial queda en
    git como referencia.

