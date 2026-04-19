# API RAG – Selección Inteligente de Vehículo 🚛🌿

**Arquitectura hexagonal en Python** para recomendar el vehículo óptimo de transporte agrícola mediante Retrieval-Augmented Generation.

> Entregable académico – Arquitectura y Desarrollo para IA Generativa  
> Autores: Elizabeth Toro · Santiago Cardona · Edward Rayo

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────┐
│  ADAPTADORES DE ENTRADA                                  │
│  ┌───────────────────┐   ┌─────────────────────────┐    │
│  │  FastAPI REST API │   │  Batch CLI (ingestión)  │    │
│  │  POST /api/v1/... │   │  python -m src...ingest │    │
│  └────────┬──────────┘   └───────────┬─────────────┘    │
│           │                          │                   │
│  ┌────────▼──────────────────────────▼─────────────┐    │
│  │  NÚCLEO HEXAGONAL                                │    │
│  │  ┌──────────────────┐  ┌───────────────────┐    │    │
│  │  │RecommendationSvc │  │  IngestionService │    │    │
│  │  └──────────────────┘  └───────────────────┘    │    │
│  │  ┌────────────────┐  ┌──────────────────────┐   │    │
│  │  │  PromptBuilder │  │    ResponseParser    │   │    │
│  │  └────────────────┘  └──────────────────────┘   │    │
│  │                                                  │    │
│  │  PUERTOS (interfaces abstractas)                 │    │
│  │  KnowledgeRepository | LLMProvider | Embedding   │    │
│  └───────────┬───────────────────┬──────────────────┘    │
│              │                   │                        │
│  ┌───────────▼──────┐  ┌─────────▼──────────────────┐   │
│  │ CONOCIMIENTO     │  │ LLM ADAPTERS               │   │
│  │ ChromaAdapter    │  │ AnthropicAdapter (Claude)  │   │
│  │ (ChromaDB vec.)  │  │ OpenAIAdapter (GPT-4o)     │   │
│  └──────────────────┘  │ GoogleAdapter (Gemini)     │   │
│                         │ OllamaAdapter (local)      │   │
│  ┌──────────────────┐   └────────────────────────────┘   │
│  │ EMBEDDINGS       │                                     │
│  │ SentenceTransf.  │                                     │
│  │ OpenAIEmbedding  │                                     │
│  └──────────────────┘                                     │
└─────────────────────────────────────────────────────────┘
```

---

## Instalación rápida

```bash
# 1. Clonar / descomprimir el proyecto
cd rag-vehicle-api

# 2. Crear entorno virtual
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. Instalar dependencias
pip install -e .

# 4. Configurar variables de entorno
cp .env.example .env
# Editar .env con tu API key de Anthropic (u otro proveedor)

# 5. Indexar la base de conocimiento
python -m src.adapters.input.cli.ingest_cli seed

# 6. Arrancar el servidor
python main.py
```

El servidor queda disponible en `http://localhost:8000`  
Documentación interactiva: `http://localhost:8000/docs`

---

## Configuración de proveedores

Editar `.env`:

```env
# Usar Claude (Anthropic) — por defecto
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...

# O usar GPT-4o mini (OpenAI)
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...

# O Gemini Flash (Google)
LLM_PROVIDER=google
GOOGLE_API_KEY=AIza...

# O Ollama local (sin costo)
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1
```

---

## Uso de la API

### Autenticación
Todas las peticiones requieren el header:
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

---

## CLI de ingestión

```bash
# Indexar todos los documentos
python -m src.adapters.input.cli.ingest_cli ingest --path ./data/knowledge_base

# Ver estadísticas de la base de conocimiento
python -m src.adapters.input.cli.ingest_cli stats

# Cargar datos de ejemplo incluidos
python -m src.adapters.input.cli.ingest_cli seed
```

---

## Tests

```bash
# Ejecutar todos los tests unitarios (sin APIs externas)
python tests/unit/test_core.py

# Con pytest
pip install pytest
pytest tests/unit/ -v
```

---

## Estructura del proyecto

```
rag-vehicle-api/
├── main.py                        # Punto de entrada
├── src/
│   ├── config.py                  # Ensamblado de dependencias
│   ├── core/
│   │   ├── domain/models.py       # Entidades del dominio
│   │   ├── ports/interfaces.py    # Puertos abstractos (hexagonal)
│   │   ├── services/
│   │   │   ├── recommendation_service.py  # Caso de uso principal (RAG)
│   │   │   └── ingestion_service.py       # Pipeline de ingestión
│   │   └── utils/
│   │       ├── prompt_builder.py  # Construcción de prompts
│   │       └── response_parser.py # Parseo de respuesta LLM
│   └── adapters/
│       ├── input/
│       │   ├── api/router.py      # FastAPI REST
│       │   └── cli/ingest_cli.py  # CLI batch
│       └── output/
│           ├── llm/               # Anthropic, OpenAI, Google, Ollama
│           ├── embeddings/        # SentenceTransformers, OpenAI
│           └── knowledge/         # ChromaDB
├── data/knowledge_base/
│   ├── products/                  # Fichas técnicas de productos
│   ├── fleet/                     # Catálogo de flota
│   ├── routes/                    # Condiciones de vías
│   ├── costs/                     # Tarifas y costos
│   └── regulations/               # Normativa colombiana
├── tests/unit/test_core.py
├── Dockerfile
└── .env.example
```

---

## Códigos de error HTTP

| Código | Significado                                    |
|--------|------------------------------------------------|
| 200    | Recomendación generada exitosamente            |
| 401    | Token de autenticación ausente o inválido      |
| 422    | Payload no cumple el esquema Pydantic          |
| 500    | Error interno del servidor                     |

Todas las respuestas de error incluyen `trace_id` para trazabilidad.
