# ADR-0002: Bases de datos contenerizadas (ChromaDB + Neo4j)

- **Status**: Accepted
- **Date**: 2026-04-20
- **Deciders**: Edward Rayo, Elizabeth Toro, Santiago Cardona

## Contexto

El esqueleto inicial de la API usaba `chromadb.PersistentClient` en modo
archivo local, lo que acopla la base vectorial al proceso de la API y
dificulta que el pipeline de generación (`kb-generator/`) alimente los
mismos datos. Además, el diseño del RAG contempla **dos bases
complementarias**:

- **ChromaDB** para recuperación semántica (vectores + chunks).
- **Neo4j** para consultas estructuradas sobre el grafo de conocimiento
  (productos, vehículos, corredores, tarifas, normativa).

Sin contenerización, cada componente tendría que levantar su propia
instancia y no habría una única fuente de verdad.

## Decisión

Orquestar ambas bases con un `docker-compose.yml` en la raíz del
repositorio:

- **ChromaDB** expuesto por HTTP (API nativa de Chroma) → consumido por
  `kb-generator` para escribir y por `api` para leer (`HttpClient`).
- **Neo4j** expuesto por Bolt (puerto 7687) y Browser (7474) → consumido
  por ambos componentes con el driver oficial `neo4j`.
- Volúmenes persistentes en `./data/chroma/` y `./data/neo4j/`, ignorados
  en `.gitignore`.
- Credenciales y URLs parametrizadas vía `.env` en cada componente.
- **Posture de seguridad**: ambos servicios corren con `user:` forzado
  al `HOST_UID:HOST_GID` (no root). Los directorios bindeados del host
  deben existir y pertenecer a ese mismo UID antes del primer
  `docker compose up`.

## Consecuencias

- **Positivas**:
  - Una única instancia de datos alimentada por el generador y
    consumida por la API.
  - Levantar todo el stack local se reduce a `docker compose up`.
  - Permite reemplazar cualquiera de las dos bases sin tocar la lógica
    de negocio (vía adapters del puerto hexagonal).
- **Negativas**:
  - Agrega dependencia operativa en Docker para desarrollo local.
  - Requiere configurar volúmenes persistentes y backups cuando se vaya
    a producción.
- **Neutrales**:
  - La API deja de depender del filesystem local para Chroma.

