# Makefile — atajos para tareas comunes del proyecto RAG.
# Ejecuta `make help` para ver el listado de targets.

.PHONY: help bootstrap up down restart logs ps health ollama-pull \
        install install-kb install-api \
        schema-init schema-verify ingest-all \
        run-api \
        build-kb build-kb-download build-kb-structure build-kb-verify

COMPOSE := docker compose
VENV    := .venv
VPY     := $(VENV)/bin/python

# Binario de Python usado para crear el venv compartido. Debe cumplir
# >=3.11 (ver pyproject.toml). Override con `make install PYTHON=pythonX.Y`.
PYTHON  ?= python3.12

help: ## muestra este listado
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / \
		{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ── Infraestructura (Docker) ─────────────────────────────────

bootstrap: ## prepara volúmenes con UID del host y genera .env
	./scripts/bootstrap.sh

up: ## levanta ChromaDB + Neo4j + Ollama en background
	$(COMPOSE) up -d

down: ## detiene contenedores (sin borrar datos)
	$(COMPOSE) down

restart: ## reinicia contenedores
	$(COMPOSE) restart

logs: ## sigue logs; uso: `make logs` o `make logs S=neo4j`
	$(COMPOSE) logs -f $(S)

ps: ## estado de contenedores
	$(COMPOSE) ps

health: ## chequeos rápidos de acceso a Chroma + Neo4j + Ollama
	@echo "→ Chroma heartbeat:"
	@curl -s http://localhost:8001/api/v1/heartbeat || echo "  ✗ Chroma no responde"
	@echo
	@echo "→ Neo4j RETURN 1:"
	@$(COMPOSE) exec -T neo4j cypher-shell -u neo4j \
		-p $${NEO4J_PASSWORD:-neo4jpass} "RETURN 1 AS ok" \
		|| echo "  ✗ Neo4j no responde"
	@echo
	@echo "→ Ollama modelos disponibles:"
	@curl -s http://localhost:11434/api/tags | python3 -c \
		"import sys,json; [print(' ',m['name']) for m in json.load(sys.stdin).get('models',[])] or print('  (sin modelos descargados)')" \
		|| echo "  ✗ Ollama no responde"

ollama-pull: ## descarga un modelo; uso: `make ollama-pull M=llama3.1`
	@test -n "$(M)" || { echo "Especifica el modelo: make ollama-pull M=llama3.1"; exit 1; }
	$(COMPOSE) exec ollama ollama pull $(M)

# ── Entorno Python compartido (ADR-0009) ─────────────────────

# File target: crea el venv y actualiza pip solo si aún no existe.
$(VPY):
	$(PYTHON) -m venv $(VENV)
	$(VPY) -m pip install -U pip

install: install-kb install-api ## instala ambos componentes en el .venv compartido

install-kb: $(VPY) ## instala solo kb-generator (editable) en el .venv compartido
	$(VPY) -m pip install -e ./kb-generator

install-api: $(VPY) ## instala solo api (editable) en el .venv compartido
	$(VPY) -m pip install -e ./api

# ── API ──────────────────────────────────────────────────────

run-api: ## levanta la API FastAPI en http://localhost:8000
	@test -x $(VPY) || { echo "Falta venv. Corre: make install"; exit 1; }
	@test -f api/.env || { echo "Falta api/.env. Copia api/.env.example y edítalo"; exit 1; }
	cd api && ../$(VPY) main.py

# ── Base de conocimiento (kb-generator) ──────────────────────

build-kb: ## descarga + estructura + verifica la base de conocimiento completa
	@test -x $(VPY) || { echo "Falta venv. Corre: make install"; exit 1; }
	cd kb-generator && ../$(VPY) agents/knowledge_base_agent.py

build-kb-download: ## solo descarga PDFs/XLS a base_conocimiento/fuentes/
	@test -x $(VPY) || { echo "Falta venv. Corre: make install"; exit 1; }
	cd kb-generator && ../$(VPY) agents/knowledge_base_agent.py --solo-descargar

build-kb-structure: ## solo estructura PDFs ya descargados → MDs en estructurados/
	@test -x $(VPY) || { echo "Falta venv. Corre: make install"; exit 1; }
	cd kb-generator && ../$(VPY) agents/knowledge_base_agent.py --solo-estructurar

build-kb-verify: ## solo verifica cobertura de la base de conocimiento
	@test -x $(VPY) || { echo "Falta venv. Corre: make install"; exit 1; }
	cd kb-generator && ../$(VPY) agents/knowledge_base_agent.py --verificar-cobertura

schema-init: ## aplica schema Neo4j (idempotente)
	@test -x $(VPY) || { echo "Falta venv. Corre: make install"; exit 1; }
	cd kb-generator && ../$(VPY) -m ingester.init_schema

schema-verify: ## verifica que el schema Neo4j esté completo
	@test -x $(VPY) || { echo "Falta venv. Corre: make install"; exit 1; }
	cd kb-generator && ../$(VPY) -m ingester.verify_schema

ingest-all: ## ingesta metadata.json + INVIAS + MDs a Neo4j + Chroma
	@test -x $(VPY) || { echo "Falta venv. Corre: make install"; exit 1; }
	cd kb-generator && ../$(VPY) -m ingester.pipeline

