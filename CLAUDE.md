# API RAG - Selección Inteligente de Vehículo
## Contexto del proyecto

Este proyecto construye una API RAG en Python para recomendar vehículos
de transporte en logística agrícola colombiana. La API usa arquitectura
hexagonal (ports and adapters) con ChromaDB como base vectorial y Neo4j
como base de grafos.

**Equipo**: Edward Rayo, Elizabeth Toro, Santiago Cardona

El repositorio agrupa dos componentes independientes pero complementarios:

- `api/` → servicio REST (FastAPI) que expone la recomendación RAG.
- `kb-generator/` → pipeline que descarga, estructura y valida la base
  de conocimiento que luego se ingesta en el RAG.

---

## Estructura del repositorio

```
ST1701_dis-rag-vehicle-selection/
├── CLAUDE.md                              ← este archivo
├── README.md
├── Dockerfile
├── .gitignore
│
├── api/                                   ← servicio RAG (FastAPI, hexagonal)
│   ├── main.py                            ← punto de entrada uvicorn
│   ├── pyproject.toml
│   ├── .env.example
│   ├── src/
│   │   ├── config.py                      ← ensamblado de dependencias
│   │   ├── core/                          ← dominio, puertos, servicios
│   │   │   ├── domain/models.py
│   │   │   ├── ports/interfaces.py
│   │   │   ├── services/
│   │   │   │   ├── recommendation_service.py
│   │   │   │   └── ingestion_service.py
│   │   │   └── utils/
│   │   │       ├── prompt_builder.py
│   │   │       └── response_parser.py
│   │   └── adapters/
│   │       ├── input/
│   │       │   ├── api/router.py          ← endpoints REST
│   │       │   └── cli/ingest_cli.py      ← CLI de ingestión
│   │       └── output/
│   │           ├── llm/                   ← Anthropic, OpenAI, Google, Ollama
│   │           ├── embeddings/            ← SentenceTransformers, OpenAI
│   │           └── knowledge/             ← ChromaDB
│   ├── ui/app.py                          ← front Streamlit
│   └── tests/unit/test_core.py
│
└── kb-generator/                          ← pipeline de base de conocimiento
    ├── requirements.txt
    ├── agents/
    │   └── knowledge_base_agent.py        ← orquestador del pipeline
    ├── scripts/
    │   ├── descargar_base_conocimiento.py ← descarga PDFs/XLS a fuentes/
    │   ├── descargar_corredores_invias.py ← API INVIAS → estructurados/
    │   ├── validar_base_conocimiento.py   ← validación estructural
    │   ├── limpiar_descargas.py           ← limpia basura/huérfanos
    │   └── agente_estructuracion_documentos.md
    ├── skills/
    │   └── knowledge-base-builder/SKILL.md
    └── base_conocimiento/                 ← generado (ignorado por git)
        ├── fuentes/                       ← descargas originales (PDF, XLS)
        ├── estructurados/                 ← artefactos listos para ingesta
        ├── metadata.json
        ├── descarga_log.txt
        └── reporte_*.{json,md}
```

> `kb-generator/base_conocimiento/` está en `.gitignore`: solo se versiona
> el código que **genera** la base de conocimiento, no los artefactos.

---

## Componente `api/` — servicio RAG

Arquitectura hexagonal con FastAPI. Para levantar el servicio en local:

```bash
cd api
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env         # editar con tu API key
python main.py               # http://localhost:8000/docs
```

Detalles de uso, endpoints y configuración de proveedores (Anthropic,
OpenAI, Google, Ollama) están en el `README.md` de la raíz.

---

## Componente `kb-generator/` — pipeline de base de conocimiento

Para construir la base de conocimiento de punta a punta:

```bash
cd kb-generator

# Flujo completo (descarga + estructuración + verificación)
python agents/knowledge_base_agent.py

# Solo descargar documentos
python agents/knowledge_base_agent.py --solo-descargar

# Solo estructurar PDFs ya descargados
python agents/knowledge_base_agent.py --solo-estructurar

# Solo verificar cobertura
python agents/knowledge_base_agent.py --verificar-cobertura
```

El agente evalúa el estado actual, decide qué pasos ejecutar y solo
interrumpe al usuario cuando necesita una decisión que no puede tomar solo.

### Skill de referencia

El agente usa este skill como guía de instrucciones para sus subagentes:

- `kb-generator/skills/knowledge-base-builder/SKILL.md` → plantillas de
  estructuración, reglas de calidad y criterios de verificación de
  cobertura.

---

## Convenciones del proyecto

- Python 3.11
- Un archivo `.md` estructurado por cada PDF descargado, mismo nombre,
  misma carpeta
- Metadatos en YAML front matter al inicio de cada `.md`
- Los archivos `.md` en `estructurados/` son los que se ingestarán al
  RAG, no los PDFs de `fuentes/`
- Categorías siempre con prefijo numérico: `01_`, `02_`, etc.

