# ADR-0007: Categorías unificadas con prefijo numérico español

- **Status**: Accepted
- **Date**: 2026-04-20
- **Deciders**: Edward Rayo, Elizabeth Toro, Santiago Cardona

## Contexto

Las cinco categorías documentales del proyecto tenían dos nombres
distintos según el componente:

- **API** (versión esqueleto): `products`, `fleet`, `routes`, `costs`,
  `regulations` (inglés, sin prefijo).
- **kb-generator**: `01_fichas_tecnicas_productos`,
  `02_catalogo_flota_vehicular`, `03_condiciones_rutas_vias`,
  `04_tarifas_costos_transporte`, `05_normativa_transporte` (español,
  con prefijo numérico que define orden).

La inconsistencia hacía que el filtro de categoría en ChromaDB, las
propiedades en Neo4j y las respuestas de la API divergieran.

## Decisión

Usar el formato del `kb-generator` como **única fuente de verdad**:

- **En disco** (carpetas): se conserva el prefijo numérico, p.ej.
  `01_fichas_tecnicas_productos/`. Así el orden de las categorías
  queda explícito en el filesystem.
- **En ChromaDB metadata, Neo4j y API**: se usa el slug sin prefijo,
  p.ej. `fichas_tecnicas_productos`. El prefijo solo ordena carpetas.

Slugs oficiales:

| Disco | Slug (metadata / API) |
|---|---|
| `01_fichas_tecnicas_productos` | `fichas_tecnicas_productos` |
| `02_catalogo_flota_vehicular` | `catalogo_flota_vehicular` |
| `03_condiciones_rutas_vias` | `condiciones_rutas_vias` |
| `04_tarifas_costos_transporte` | `tarifas_costos_transporte` |
| `05_normativa_transporte` | `normativa_transporte` |

El campo `categoria_rag` en el YAML frontmatter de cada MD estructurado
(ver `kb-generator/skills/knowledge-base-builder/SKILL.md`) ya usa el
slug, así que esta decisión alinea el resto del sistema con ese
contrato.

## Consecuencias

- **Positivas**:
  - Consistencia total: el mismo identificador cruza filesystem,
    Chroma, Neo4j y respuestas REST.
  - El frontmatter ya escrito por el kb-generator queda canónico sin
    transformaciones.
- **Negativas**:
  - La API queda con identificadores en español mezclados con campos
    técnicos en inglés (`trace_id`, `costo_estimado_cop`). Es
    aceptable: las categorías son parte del dominio del negocio en
    español.
  - Clientes externos de la API tienen que usar los slugs en español si
    filtran por categoría.
- **Neutrales**:
  - Se rompen los nombres de categoría que usaba el código anterior de
    la API (`products`, `fleet`, etc.). Como ese código se deprecia
    con ADR-0003, no hay callers que actualizar.

