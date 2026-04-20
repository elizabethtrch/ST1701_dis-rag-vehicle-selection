# api — Servicio RAG de recomendación de vehículos

Servicio REST (FastAPI) con arquitectura hexagonal que recomienda el
vehículo óptimo para un pedido de transporte agrícola. Consume
**ChromaDB** (retrieval semántico) y **Neo4j** (grafo de conocimiento)
— ver [ADR-0002](../docs/adr/0002-bases-de-datos-contenerizadas.md) y
[ADR-0004](../docs/adr/0004-modelo-de-grafo-neo4j.md).

> La API es **consumidor puro**: toda la ingesta vive en
> [`kb-generator/`](../kb-generator/README.md) — ver
> [ADR-0003](../docs/adr/0003-ingesta-centralizada-en-kb-generator.md).

---

## Arquitectura hexagonal

```
┌─────────────────────────────────────────────────────────┐
│  ADAPTADOR DE ENTRADA                                    │
│  ┌───────────────────┐                                   │
│  │  FastAPI REST API │                                   │
│  │  POST /api/v1/... │                                   │
│  └────────┬──────────┘                                   │
│           │                                              │
│  ┌────────▼──────────────────────────────────────────┐   │
│  │  NÚCLEO HEXAGONAL                                 │   │
│  │  RecommendationService                            │   │
│  │  PromptBuilder | ResponseParser | CostCalculator  │   │
│  │                                                   │   │
│  │  PUERTOS                                          │   │
│  │  KnowledgeRepository | GraphRepository            │   │
│  │  LLMProvider        | EmbeddingProvider           │   │
│  └───────────┬───────────────────┬───────────────────┘   │
│              │                   │                       │
│  ┌───────────▼──────┐  ┌─────────▼──────────────────┐    │
│  │ CONOCIMIENTO     │  │ LLM ADAPTERS               │    │
│  │ ChromaAdapter    │  │ AnthropicAdapter (Claude)  │    │
│  │ (HTTP)           │  │ OpenAIAdapter              │    │
│  │ Neo4jAdapter     │  │ GoogleAdapter              │    │
│  │ (Bolt)           │  │ OllamaAdapter (local)      │    │
│  └──────────────────┘  └────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

> **Nota**: `GraphRepository`, `Neo4jAdapter` y `CostCalculator` se
> añaden en las Fases 5-7 del [plan de implementación](../docs/implementation-plan.md).

---

## Setup local

Pre-requisitos: contenedores de datos arriba (ver `make up` desde la
raíz) y la base de conocimiento ingestada (ver
[`kb-generator/README.md`](../kb-generator/README.md)).

El entorno Python es **compartido** con `kb-generator/` en un solo
`.venv` en la raíz del repo (ver
[ADR-0009](../docs/adr/0009-venv-compartido.md)):

```bash
# Desde la raíz del repo
make install               # crea .venv + pip install -e ./kb-generator -e ./api
cp api/.env.example api/.env  # completar con tu API key de LLM
cd api && ../.venv/bin/python main.py   # http://localhost:8000/docs
```

O, si prefieres activar el venv:

```bash
source .venv/bin/activate
cd api && python main.py
```

---

## Configuración de proveedores LLM

Editar `api/.env`:

```env
# Claude (Anthropic) — por defecto
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...

# GPT-4o mini (OpenAI)
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...

# Gemini Flash (Google)
LLM_PROVIDER=google
GOOGLE_API_KEY=AIza...

# Ollama local (sin costo)
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1
```

---

## Uso de la API

### Autenticación

Todas las peticiones requieren:

```
Authorization: Bearer <API_SECRET_TOKEN>
```

El token por defecto en desarrollo es `dev-secret-token-change-in-prod`.

### Endpoint principal

```bash
curl -X POST http://localhost:8000/api/v1/vehicle-recommendation \
  -H "Authorization: Bearer dev-secret-token-change-in-prod" \
  -H "Content-Type: application/json" \
  -d '{
    "pedido": {
      "identificador": "PED-2025-0042",
      "fecha_entrega": "2025-06-20",
      "prioridad": "alta"
    },
    "productos": [
      {"nombre": "Aguacate Hass", "cantidad": 1200, "unidad": "kg"},
      {"nombre": "Plátano hartón", "cantidad": 800, "unidad": "kg"}
    ],
    "cliente": {
      "nombre": "Distribuidora Andina S.A.",
      "direccion": "Calle 80 # 45-12, Bogotá",
      "latitud": 4.6782,
      "longitud": -74.0584
    },
    "canal": "mayorista",
    "flota_disponible": [
      {"id": "VEH-015", "tipo": "TERRESTRE", "capacidad_kg": 3500, "refrigerado": true, "matricula": "ABC123"},
      {"id": "VEH-022", "tipo": "TERRESTRE", "capacidad_kg": 2000, "refrigerado": false, "matricula": "XYZ789"}
    ]
  }'
```

### Respuesta esperada

```json
{
  "trace_id": "7a3f2c1e-8b4d-4e5a-9f6c-2d1b8e0c3a7f",
  "vehiculo_recomendado": {"id": "VEH-015", "tipo": "TERRESTRE", "matricula": "ABC123"},
  "justificacion": "El VEH-015 se selecciona porque...",
  "alternativas": [{"id": "VEH-022", "motivo": "Sin refrigeración, riesgo para aguacate..."}],
  "alertas": [{"nivel": "media", "mensaje": "Verificar temperatura antes del cargue"}],
  "costo_estimado_cop": 521525,
  "desglose_costo": {
    "combustible_cop": 280000, "peajes_cop": 75000,
    "viaticos_cop": 90000, "seguro_cop": 8500,
    "imprevistos_cop": 68025, "total_cop": 521525
  },
  "tiempo_estimado_min": 420
}
```

> Los campos numéricos (`costo_estimado_cop`, `desglose_costo`,
> `tiempo_estimado_min`) **los calcula código determinista** a partir
> del grafo, no el LLM. Ver
> [ADR-0006](../docs/adr/0006-calculo-deterministico-costos-tiempos.md).

---

## Códigos de error HTTP

| Código | Significado |
|---|---|
| 200 | Recomendación generada |
| 401 | Token ausente o inválido |
| 422 | Payload no cumple el esquema Pydantic |
| 500 | Error interno del servidor |

Todas las respuestas de error incluyen `trace_id` para trazabilidad.

---

## Tests

```bash
# Desde la raíz del repo, con el venv compartido ya instalado
source .venv/bin/activate
cd api
pytest tests/unit/ -v
```

---

## Estructura

```
api/
├── main.py                       # punto de entrada uvicorn
├── pyproject.toml
├── .env.example
├── src/
│   ├── config.py                 # ensamblado de dependencias
│   ├── core/
│   │   ├── domain/models.py
│   │   ├── ports/interfaces.py   # KnowledgeRepository, GraphRepository, …
│   │   ├── services/
│   │   │   ├── recommendation_service.py
│   │   │   └── cost_calculator.py    (Fase 7)
│   │   └── utils/
│   │       ├── prompt_builder.py
│   │       └── response_parser.py
│   └── adapters/
│       ├── input/
│       │   └── api/router.py     # endpoints REST
│       └── output/
│           ├── llm/              # Anthropic, OpenAI, Google, Ollama
│           ├── embeddings/
│           └── knowledge/        # ChromaAdapter + Neo4jAdapter (Fase 5)
├── ui/app.py                     # front Streamlit
└── tests/
    ├── unit/
    └── integration/
```

