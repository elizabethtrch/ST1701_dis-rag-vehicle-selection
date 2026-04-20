# API RAG – Selección Inteligente de Vehículo 🚛🌿

Monorepo del proyecto académico que construye una API RAG en Python
para recomendar el vehículo óptimo de transporte agrícola colombiano
combinando recuperación semántica (ChromaDB) y grafo de conocimiento
(Neo4j).

> Entregable académico — Arquitectura y Desarrollo para IA Generativa
> Autores: Edward Rayo · Elizabeth Toro · Santiago Cardona

---

## Componentes

El repositorio agrupa dos componentes independientes pero
complementarios sobre la misma infraestructura de datos:

- **[`api/`](./api/README.md)** — servicio REST (FastAPI, arquitectura
  hexagonal). Consume la base de conocimiento y recomienda vehículos.
- **[`kb-generator/`](./kb-generator/README.md)** — pipeline que
  descarga documentos institucionales, los estructura e ingesta en
  ChromaDB + Neo4j.

ChromaDB y Neo4j se orquestan con `docker-compose.yml` desde la raíz
(ver [ADR-0002](./docs/adr/0002-bases-de-datos-contenerizadas.md)).

---

## Pre-requisitos

| Herramienta | Versión mínima | Notas |
|---|---|---|
| Docker Engine | 24.x | con `docker compose` v2 |
| Python | 3.11+ | el Makefile usa `python3.12` por defecto; override con `PYTHON=pythonX.Y` |
| GNU Make | 3.81+ | para los atajos de `Makefile` |
| Bash | 4+ | usado por `scripts/bootstrap.sh` |
| `sudo` | — | solo la primera vez si Docker creó volúmenes como root |

Verificar:

```bash
docker --version && docker compose version
python3.12 --version
make --version
```

---

## Quick start

Desde la raíz del repo:

```bash
# 1. Infraestructura (primera vez)
make bootstrap        # prepara ./data/ con tu UID y genera .env
make up               # levanta ChromaDB + Neo4j
make ps               # ambos servicios en estado "Up (healthy)"
make health           # heartbeat Chroma + RETURN 1 en Neo4j

# 2. kb-generator: entorno + grafo
make kb-install       # crea kb-generator/.venv y pip install -e .
make schema-init      # aplica constraints/indices al grafo Neo4j
make schema-verify    # valida → "Schema COMPLETO"

# 3. [próximo] Ingesta de base de conocimiento
#    ver kb-generator/README.md — comandos `make ingest-all`, etc.
#    (Fases 3-4 del plan de implementación)

# 4. [próximo] API local
#    cd api && source .venv/bin/activate && python main.py
#    (Fases 5-7)
```

Ver todos los atajos con `make help`.

### Si cambias de versión de Python

```bash
rm -rf kb-generator/.venv
make kb-install PYTHON=python3.11
```

---

## Documentación

- **[ADRs](./docs/adr/README.md)** — decisiones arquitectónicas
  (monorepo, bases contenerizadas, ingesta centralizada, modelo de
  grafo, Cypher parametrizado, cálculo determinista, categorías
  unificadas, Community Edition).
- **[Plan de implementación](./docs/implementation-plan.md)** —
  documento vivo con las 9 fases del pipeline RAG, su estado actual y
  los archivos que entrega cada una.
- **[`api/README.md`](./api/README.md)** — uso detallado de la API
  REST, configuración de proveedores LLM, ejemplos `curl`.
- **[`kb-generator/README.md`](./kb-generator/README.md)** — pipeline
  de descarga + estructuración + ingesta.

---

## Estructura del monorepo

```
ST1701_dis-rag-vehicle-selection/
├── api/                      ← servicio REST (ver api/README.md)
├── kb-generator/             ← pipeline de base de conocimiento
├── docs/
│   ├── adr/                  ← Architecture Decision Records
│   ├── implementation-plan.md
│   └── README.md
├── scripts/
│   └── bootstrap.sh          ← prepara volúmenes con UID del host
├── docker-compose.yml        ← ChromaDB + Neo4j
├── Makefile                  ← atajos (make help)
├── .env.example
├── .gitignore
└── CLAUDE.md                 ← guía de colaboración con el agente
```

