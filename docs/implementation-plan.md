# Plan de implementación — Pipeline de ingesta RAG

> Documento vivo. Actualizar al completar cada fase, cuando surjan
> bloqueadores o cuando cambien decisiones. Si abres una sesión nueva,
> empieza aquí.

## Contexto rápido

- **Rama**: `feat/pipeline-ingesta-rag`
- **Base**: `main` (commit `ed386fc`, unificación de api + kb-generator)
- **Objetivo del branch**: conectar `kb-generator` con la API a través
  de ChromaDB + Neo4j contenerizados, con ingesta centralizada y
  queries Cypher fijas.
- **Decisiones vigentes**: ver [`adr/`](./adr/) — ADRs 0001 a 0007.

## Fases

Cada fase cierra con un commit independiente. Los archivos listados son
los que entrega la fase.

| # | Fase | Estado | Commit |
|---|------|--------|--------|
| 0 | ADRs + estructura `docs/` | ✅ completo | `9e1b0ca` |
| 1 | `docker-compose.yml` + `.gitignore` + bootstrap | ⏳ en validación | pendiente |
| 2 | Schema inicial Neo4j (constraints + índices) | ⬜ pendiente | — |
| 3 | Módulo `kb-generator/ingester/` (loaders, chunker, clientes, mappers) | ⬜ pendiente | — |
| 4 | CLI del ingester (`ingest-all`, `ingest-file`, `reindex`, `stats`) | ⬜ pendiente | — |
| 5 | API: `ChromaAdapter` HTTP + `Neo4jAdapter` + puerto `GraphRepository` | ⬜ pendiente | — |
| 6 | `RecommendationService` con ~5 queries Cypher fijas + retrieval Chroma | ⬜ pendiente | — |
| 7 | Calculador determinista de costos y tiempos (ADR-0006) | ⬜ pendiente | — |
| 8 | Limpieza API: borrar `ingestion_service.py` y `ingest_cli.py` | ⬜ pendiente | — |
| 9 | Hook en `knowledge_base_agent.py` para disparar ingesta al final | ⬜ pendiente | — |

Leyenda: ✅ completo · ⏳ en progreso/validación · ⬜ pendiente · ⚠️ bloqueado

## Bloqueador actual

**Fase 1** — se fueron corrigiendo problemas al levantar el compose:

1. `Use of deprecated setting 'dbms.memory.heap.*'` → **corregido**
   renombrando a `server.memory.heap.*` en `docker-compose.yml`.
2. `Folder mounted to /data|/logs|/plugins is not writable` →
   **mitigado** con `scripts/bootstrap.sh`, que crea los directorios
   como usuario del host y arregla ownership si Docker los creó como
   root.
3. `PermissionError: /chroma/chroma.log` (Chroma) → **corregido**
   bind-mounteando `./data/chroma.log` como archivo a `/chroma/chroma.log`.
   `/chroma/` en la imagen es de root; solo podemos montar cosas
   específicas adentro. `bootstrap.sh` pre-crea el archivo vacío.

**Próximo paso**: el usuario debe ejecutar:

```bash
docker compose down -v
sudo rm -rf data/
./scripts/bootstrap.sh
docker compose up -d
docker compose logs chromadb neo4j | grep -iE 'warning|error|permission'
```

Si los logs salen limpios, committear Fase 1 y arrancar Fase 2.

## Archivos por fase

### Fase 1 (en validación)

- `docker-compose.yml` — servicios `chromadb` (HTTP) y `neo4j`
  (Bolt + Browser), ambos con `user: "${HOST_UID}:${HOST_GID}"`
- `.env.example` — `HOST_UID`, `HOST_GID`, puertos, credenciales Neo4j
- `.gitignore` — añade `data/chroma/` y `data/neo4j/`
- `scripts/bootstrap.sh` — idempotente: crea carpetas con ownership
  correcto, corrige si Docker las creó como root, genera `.env`
- `docs/adr/0002-bases-de-datos-contenerizadas.md` — posture de no-root

### Fase 2 (pendiente)

- `kb-generator/ingester/schema.cypher` — constraints + índices para
  los 12 nodos del ADR-0004.

### Fase 3 (pendiente)

Estructura propuesta:

```
kb-generator/ingester/
├── __init__.py
├── config.py              # URLs, credenciales, modelo embeddings
├── loaders/
│   ├── md_loader.py       # parsea YAML frontmatter + cuerpo MD
│   └── invias_loader.py   # parsea invias_corredores.json
├── chunker.py             # ventana deslizante para chunks semánticos
├── clients/
│   ├── chroma_client.py   # HttpClient + collection upsert
│   └── neo4j_client.py    # driver Bolt + session helpers
├── mappers/
│   ├── producto.py        # frontmatter → (:Producto)
│   ├── vehiculo.py        # → (:ConfiguracionVehicular), (:Vehiculo)
│   ├── corredor.py        # INVIAS JSON → (:Corredor), (:Ciudad), …
│   ├── tarifa.py          # XLSX peajes → (:Tarifa), (:Peaje)
│   └── normativa.py       # → (:Normativa), (:Articulo)
└── pipeline.py            # orquesta loader→chunker→chroma+neo4j
```

### Fase 4 (pendiente)

- `kb-generator/ingester/cli.py` con `typer`:
  - `ingest-all` — batch completo desde `base_conocimiento/estructurados/`
  - `ingest-file <path>` — documento suelto
  - `reindex [--categoria X]` — rebuild selectivo
  - `stats` — inventario indexado

### Fase 5 (pendiente)

- `api/src/core/ports/interfaces.py` — nuevo puerto `GraphRepository`
- `api/src/adapters/output/knowledge/chroma_adapter.py` — pasa de
  `PersistentClient` a `HttpClient`
- `api/src/adapters/output/knowledge/neo4j_adapter.py` — **nuevo**
- `api/src/config.py` — URLs Chroma/Neo4j desde `.env`; ensambla ambos
- `api/pyproject.toml` — dependencia `neo4j>=5.22`

### Fase 6 (pendiente)

- `api/src/core/services/recommendation_service.py` — refactor:
  - Extrae parámetros del JSON de entrada
  - Ejecuta ~5 queries Cypher fijas (requisitos producto, corredor,
    tarifas/peajes, normativa aplicable, chunks Chroma)
  - Ensambla contexto estructurado para el prompt
- `api/src/core/utils/prompt_builder.py` — actualiza prompt:
  LLM no produce costos/tiempos, solo elige vehículo + redacta
- `api/src/core/utils/response_parser.py` — deja de parsear
  `desglose_costo` / `tiempo_estimado_min` del LLM

### Fase 7 (pendiente)

- `api/src/core/services/cost_calculator.py` — **nuevo**:
  - `calcular_costo(corredor, vehiculo, config) → DesgloseCosto`
  - `calcular_tiempo(corredor) → int`
  - Usa datos ya traídos del grafo en Fase 6.

### Fase 8 (pendiente)

Borrar:
- `api/src/core/services/ingestion_service.py`
- `api/src/adapters/input/cli/ingest_cli.py`
- `api/src/adapters/input/cli/__init__.py` (si queda vacío)

Ajustar:
- `api/src/config.py` — quitar `build_ingestion_service()`
- `api/README.md` — quitar sección del CLI de ingestión
- `api/src/core/ports/interfaces.py` — `Fragmento.categoria`: cambiar
  comentario de `products|fleet|…` a slugs del ADR-0007

### Fase 9 (pendiente)

- `kb-generator/agents/knowledge_base_agent.py` — al finalizar
  estructuración + verificación, llamar `ingester.pipeline.ingest_all()`

## Decisiones clave (ADRs)

| ADR | Tema | Impacto en estas fases |
|-----|------|------------------------|
| [0001](./adr/0001-monorepo-unificado.md) | Monorepo | Fase 0 (ya aplicada) |
| [0002](./adr/0002-bases-de-datos-contenerizadas.md) | ChromaDB + Neo4j contenerizados, no-root | Fase 1 |
| [0003](./adr/0003-ingesta-centralizada-en-kb-generator.md) | Ingesta solo en kb-generator | Fases 3, 4, 8 |
| [0004](./adr/0004-modelo-de-grafo-neo4j.md) | 12 nodos / 15 relaciones | Fases 2, 3 |
| [0005](./adr/0005-queries-cypher-parametrizadas.md) | Cypher fijo, no text-to-cypher | Fase 6 |
| [0006](./adr/0006-calculo-deterministico-costos-tiempos.md) | Costos/tiempos en código, no LLM | Fases 6, 7 |
| [0007](./adr/0007-categorias-unificadas-prefijo-numerico.md) | Slug español sin prefijo numérico | Fases 3, 5, 6, 8 |

## Notas operativas

- **Python**: cada componente (`api/`, `kb-generator/`) mantiene su
  venv y requirements propios. El ingester hereda del de `kb-generator`.
- **Dependencias nuevas del ingester**: `chromadb`, `neo4j`,
  `sentence-transformers`, `python-frontmatter` (o `PyYAML` ya presente),
  `typer`.
- **Categorías canónicas** (ADR-0007):
  - `fichas_tecnicas_productos`
  - `catalogo_flota_vehicular`
  - `condiciones_rutas_vias`
  - `tarifas_costos_transporte`
  - `normativa_transporte`

## Cómo retomar esta implementación

Si este plan queda abandonado a mitad:

1. `git checkout feat/pipeline-ingesta-rag`
2. Leer este archivo completo.
3. Revisar `git log --oneline origin/main..HEAD` para ver commits hechos.
4. Identificar la primera fila sin ✅ en la tabla de fases.
5. Retomar desde ahí; los entregables de cada fase están listados.

