# PR: Pipeline de Ingesta RAG — `feat/pipeline-ingesta-rag` → `main`

## Resumen

Implementa el pipeline completo de ingesta de la base de conocimiento en ChromaDB y Neo4j,
conecta la API con ambas bases de datos a través de arquitectura hexagonal, y agrega el
calculador determinista de costos y tiempos. El resultado es un sistema RAG híbrido funcional
de punta a punta: desde la descarga de documentos hasta la recomendación de vehículo con
desglose de costos real.

---

## Cambios por área

### Infraestructura (`docker-compose.yml`, `scripts/bootstrap.sh`, `.env.example`)

- **ChromaDB** (HTTP :8001) y **Neo4j 5.22** (Bolt :7687, Browser :7474) orquestados con
  `docker-compose.yml`; ambos servicios corren con `user: HOST_UID:HOST_GID` para evitar
  problemas de permisos en volúmenes (ADR-0002).
- `scripts/bootstrap.sh`: script idempotente que crea los directorios `data/` con el UID del
  host, corrige ownership si Docker los creó como root, y genera `.env` desde `.env.example`.
- Servicio `rag-ollama` opcional para inferencia local con bind-mount `./data/ollama` y
  `OLLAMA_MODELS` para evitar el problema de escritura como root.

### `Makefile`

Targets nuevos para operar el monorepo sin recordar comandos largos:

| Target | Acción |
|---|---|
| `make bootstrap` | Prepara directorios y `.env` |
| `make up / down` | Levanta/baja los contenedores |
| `make install` | Crea `.venv/` compartido e instala `api/` y `kb-generator/` |
| `make schema-init` | Aplica constraints e índices en Neo4j |
| `make ingest-all` | Corre el pipeline de ingesta completo |
| `make build-kb` | Descarga, estructura y verifica la base de conocimiento |
| `make run-api` | Levanta el servidor FastAPI |
| `make ollama-pull` | Descarga el modelo configurado en Ollama |
| `make health` | Verifica que ChromaDB, Neo4j y Ollama respondan |

### `kb-generator/` — Pipeline de base de conocimiento

#### Schema Neo4j (`ingester/schema.cypher`, `ingester/init_schema.py`)

- 12 constraints `UNIQUE` + 6 índices secundarios para los nodos del modelo de grafo (ADR-0004).
- `init_schema.py`: aplicador idempotente (`IF NOT EXISTS`); se puede correr múltiples veces sin efecto.
- `verify_schema.py`: compara el schema actual contra el esperado; retorna exit 1 si falta algo.

#### Módulo de ingesta (`kb-generator/ingester/`)

Estructura completa implementada en las Fases 3 y 4:

```
ingester/
├── config.py          — Config.from_env() con auto-load del .env raíz
├── chunker.py         — sliding window sobre palabras para chunks semánticos
├── clients/
│   ├── chroma_client.py  — HttpClient + SentenceTransformers; upsert/delete por categoría
│   └── neo4j_client.py   — Bolt + context manager
├── loaders/
│   ├── md_loader.py      — YAML frontmatter + body markdown
│   └── invias_loader.py  — invias_corredores.json
├── mappers/
│   ├── documento.py   — metadata.json → (:Documento); valida invariantes en Python (ADR-0008)
│   ├── corredor.py    — INVIAS JSON → (:Corredor)/(:Ciudad)/(:Departamento) + relaciones
│   ├── normativa.py   — MDs de normativa → (:Normativa)-[:REGULA]->(:TipoVehiculo)
│   │                    + (:Normativa)-[:CONTIENE]->(:Articulo)
│   ├── producto.py    — fichas técnicas → (:Producto)-[:REQUIERE_VEHICULO]->(:TipoVehiculo)
│   │                    extrae temp_opt_c, humedad_pct y vida_util_dias por regex
│   └── tarifa.py      — JSON SICE-TAC (68 k registros) → (:Tarifa)-[:APLICA_A]->(:Corredor)
│                        normaliza nombres de ciudad para vincular al corredor INVIAS
└── pipeline.py        — orquestador: documentos → corredores → normativas →
                         productos → tarifas → chunks Chroma
```

#### CLI (`kb-generator/ingester/cli.py`)

Cuatro subcomandos con `typer`:

```bash
ingester ingest-all              # batch completo
ingester ingest-file <path>      # documento suelto (.md o JSON INVIAS)
ingester reindex [--categoria X] # elimina chunks y re-ingesta una categoría
ingester stats                   # conteos Neo4j + total Chroma
```

#### Scripts de generación de contenido curado

- `scripts/generar_sicetac_md.py`: convierte el JSON SICE-TAC (892 rutas hub-a-hub) en un
  `.md` estructurado con sección *Fragmentos clave para el RAG*.
- `scripts/generar_fichas_curateadas.py`: genera fichas técnicas de productos sin PDF fuente
  (primera entrada: café colombiano); idempotente.
- `scripts/descargar_base_conocimiento.py`: agrega Resolución 4100/2004 (pesos y dimensiones)
  e informe climático IDEAM (actualización mensual) al catálogo de descargas.

### `api/` — Servicio RAG

#### Adaptadores de salida nuevos / actualizados (Fase 5)

- **`chroma_adapter.py`**: migra de `PersistentClient` a `HttpClient`; filtra por
  `categoria_rag` consistente con el ingester (ADR-0007).
- **`neo4j_adapter.py`**: nuevo adaptador que implementa `GraphRepository` con 4 queries
  Cypher parametrizadas (ADR-0005):
  - `get_requisitos_productos` — temperatura, humedad y tipo de vehículo requerido
  - `get_corredor` — distancia, tiempo estimado y estado de la vía
  - `get_tarifas_corredor` — peajes con valor COP por categoría
  - `get_normativa_tipos` — resoluciones aplicables con citas textuales

#### `RecommendationService` — flujo RAG híbrido (Fase 6)

Reemplaza el servicio original (solo Chroma + LLM) por un flujo de tres etapas:

1. **Retrieval semántico** (ChromaDB): recupera fragmentos documentales relevantes.
2. **Retrieval estructurado** (Neo4j): ejecuta las 4 queries Cypher con los parámetros
   extraídos de la solicitud.
3. **Generación** (LLM): recibe contexto combinado y elige vehículo + justificación.

El LLM ya **no produce costos ni tiempos** — solo elige el vehículo y redacta la justificación.

#### `CostCalculator` — cálculo determinista (Fase 7, ADR-0006)

Funciones puras en `api/src/core/services/cost_calculator.py` con constantes SICE-TAC:

| Componente | Cálculo |
|---|---|
| Combustible | distancia × consumo (ajustado por carga) × precio ACPM |
| Peajes | suma de tarifas traídas del grafo |
| Viáticos | días de ruta × $120 000 COP/día |
| Seguro | 0.2 % del valor estimado de la carga |
| Imprevistos | 5 % del subtotal |

#### Refactor del dominio

- `Cliente` → `Ubicacion(ciudad, departamento?, direccion?)` con `origen`/`destino` explícitos
  en `SolicitudRecomendacion`.
- `router.py`, `prompt_builder.py` y `test_core.py` actualizados al nuevo modelo.

#### Limpieza (Fase 8)

- Eliminados `ingestion_service.py` e `ingest_cli.py` de la API: la ingesta es exclusiva del
  `kb-generator` (ADR-0003). La API es consumidor puro de ChromaDB y Neo4j.

### Documentación

- **`docs/adr/`**: ADRs 0001–0009 que registran todas las decisiones arquitectónicas del branch.
- **`docs/arquitectura-rag.md`**: diagrama Mermaid del flujo RAG híbrido y tabla comparativa
  ChromaDB vs Neo4j.
- **`docs/implementation-plan.md`**: plan de implementación vivo con estado de cada fase.
- **`CLAUDE.md`**: actualizado con la estructura real del repositorio.

---

## Flujo de uso tras el merge

```bash
# 1. Preparar entorno
./scripts/bootstrap.sh && make up && make install && make schema-init

# 2. Construir la base de conocimiento
make build-kb          # descarga + estructura + verifica

# 3. Ingestar en ChromaDB + Neo4j
make ingest-all

# 4. Levantar la API
make run-api           # http://localhost:8000/docs
```

---

## ADRs relacionados

| ADR | Decisión |
|---|---|
| [0002](docs/adr/0002-bases-de-datos-contenerizadas.md) | ChromaDB + Neo4j contenerizados, posture no-root |
| [0003](docs/adr/0003-ingesta-centralizada-en-kb-generator.md) | Ingesta solo en `kb-generator`; API es consumidor puro |
| [0004](docs/adr/0004-modelo-de-grafo-neo4j.md) | Modelo de grafo: 12 nodos, 15 relaciones |
| [0005](docs/adr/0005-queries-cypher-parametrizadas.md) | Cypher fijo parametrizado, no text-to-cypher |
| [0006](docs/adr/0006-calculo-deterministico-costos-tiempos.md) | Costos y tiempos en código, no generados por el LLM |
| [0007](docs/adr/0007-categorias-unificadas-prefijo-numerico.md) | Slugs de categoría unificados entre ingester y API |
| [0008](docs/adr/0008-neo4j-community-invariantes-en-ingester.md) | Community Edition; invariantes `IS NOT NULL` en Python |
| [0009](docs/adr/0009-venv-compartido.md) | `.venv/` compartido entre `api/` y `kb-generator/` |

