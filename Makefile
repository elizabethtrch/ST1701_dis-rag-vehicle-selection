# Makefile — atajos para tareas comunes del proyecto RAG.
# Ejecuta `make help` para ver el listado de targets.

.PHONY: help bootstrap up down restart logs ps health \
        install install-kb install-api \
        schema-init schema-verify ingest-all

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

up: ## levanta ChromaDB + Neo4j en background
	$(COMPOSE) up -d

down: ## detiene contenedores (sin borrar datos)
	$(COMPOSE) down

restart: ## reinicia contenedores
	$(COMPOSE) restart

logs: ## sigue logs; uso: `make logs` o `make logs S=neo4j`
	$(COMPOSE) logs -f $(S)

ps: ## estado de contenedores
	$(COMPOSE) ps

health: ## chequeos rápidos de acceso a Chroma + Neo4j
	@echo "→ Chroma heartbeat:"
	@curl -s http://localhost:8001/api/v1/heartbeat || echo "  ✗ Chroma no responde"
	@echo
	@echo "→ Neo4j RETURN 1:"
	@$(COMPOSE) exec -T neo4j cypher-shell -u neo4j \
		-p $${NEO4J_PASSWORD:-neo4jpass} "RETURN 1 AS ok" \
		|| echo "  ✗ Neo4j no responde"

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

# ── kb-generator ─────────────────────────────────────────────

schema-init: ## aplica schema Neo4j (idempotente)
	@test -x $(VPY) || { echo "Falta venv. Corre: make install"; exit 1; }
	cd kb-generator && ../$(VPY) -m ingester.init_schema

schema-verify: ## verifica que el schema Neo4j esté completo
	@test -x $(VPY) || { echo "Falta venv. Corre: make install"; exit 1; }
	cd kb-generator && ../$(VPY) -m ingester.verify_schema

ingest-all: ## ingesta metadata.json + INVIAS + MDs a Neo4j + Chroma
	@test -x $(VPY) || { echo "Falta venv. Corre: make install"; exit 1; }
	cd kb-generator && ../$(VPY) -m ingester.pipeline

