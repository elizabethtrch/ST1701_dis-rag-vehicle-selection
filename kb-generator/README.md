# kb-generator — Pipeline de base de conocimiento

Pipeline que descarga documentos institucionales colombianos (ICA,
AGROSAVIA, INVIAS, INVIMA, MinTransporte, DANE-SIPSA), los estructura
en Markdown + JSON, y los ingesta en las bases compartidas del proyecto:

- **ChromaDB** — índice vectorial de chunks semánticos.
- **Neo4j** — grafo de conocimiento (productos, vehículos, corredores,
  tarifas, normativa) — ver [ADR-0004](../docs/adr/0004-modelo-de-grafo-neo4j.md).

Toda la ingesta vive aquí; la API solo consume (ver
[ADR-0003](../docs/adr/0003-ingesta-centralizada-en-kb-generator.md)).

---

> **Atajos**: ejecuta `make help` desde la raíz del repo para ver los
> targets disponibles (`bootstrap`, `up`, `down`, `health`,
> `schema-init`, `schema-verify`, etc.).

## 1. Pre-requisitos: contenedores arriba

Ambas bases se orquestan con `docker-compose.yml` de la raíz del repo
(ver [ADR-0002](../docs/adr/0002-bases-de-datos-contenerizadas.md)).

```bash
# Desde la raíz del repo, la primera vez:
make bootstrap     # crea volúmenes con tu UID + genera .env
make up            # docker compose up -d
```

### Validar los accesos

**Resumen rápido**

```bash
make ps        # docker compose ps — ambos Up (healthy)
make health    # heartbeat Chroma + RETURN 1 de Neo4j
```

**Neo4j Browser**

- URL: http://localhost:7474
- Connect URL: `bolt://localhost:7687`
- Credenciales: `neo4j` / `neo4jpass` (ajustables en `.env`)
- En el primer login pedirá cambiar la contraseña.

**Detalle adicional (opcional)**

```bash
curl -s http://localhost:8001/api/v1/version          # → "0.5.23"
curl -s http://localhost:8001/api/v1/collections      # → []

docker compose exec neo4j cypher-shell -u neo4j -p neo4jpass \
  "RETURN apoc.version() AS version"
```

**Prueba de persistencia**

```bash
docker compose exec neo4j cypher-shell -u neo4j -p neo4jpass \
  "CREATE (:Test {msg: 'hola'}) RETURN 'ok'"

make restart && sleep 15

docker compose exec neo4j cypher-shell -u neo4j -p neo4jpass \
  "MATCH (n:Test) RETURN n.msg"

docker compose exec neo4j cypher-shell -u neo4j -p neo4jpass \
  "MATCH (n:Test) DELETE n"
```

---

## 2. Setup de Python

Desde la raíz del repo:

```bash
make kb-install    # crea kb-generator/.venv + `pip install -e .`
```

El Makefile usa `python3.12` por defecto (`pyproject.toml` exige
`>=3.11`). Si tienes otra versión compatible, sobreescríbela:

```bash
make kb-install PYTHON=python3.11
```

O manualmente:

```bash
cd kb-generator
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e .
```

Las dependencias y entry points están declarados en `pyproject.toml`
(PEP 621). El install editable (`-e`) hace que los cambios al código
fuente se reflejen inmediatamente sin re-instalar.

---

## 3. Inicializar y verificar el schema de Neo4j

Aplica constraints (unicidad) e índices del grafo de conocimiento
definido en el [ADR-0004](../docs/adr/0004-modelo-de-grafo-neo4j.md).
Idempotente: se puede correr múltiples veces.

Desde la raíz del repo:

```bash
make schema-init      # aplica schema.cypher a Neo4j
make schema-verify    # compara contra el set esperado y reporta faltantes
```

Ambos targets llaman al venv de `kb-generator/`, así que primero debes
haber corrido `make kb-install`.

Salida esperada de `schema-verify`:

```
… | INFO | Constraints: 12/12
… | INFO | Indexes:     6/6
… | INFO | Schema COMPLETO
```

> **Nota**: las invariantes `IS NOT NULL` (property existence
> constraints) son una feature de Neo4j Enterprise Edition. En
> Community Edition solo usamos `UNIQUE`. Los campos críticos
> (`Corredor.nombre`, `Documento.categoria`) los valida el ingester
> en Python antes de cada `MERGE`.

> Los módulos subyacentes son `ingester.init_schema` y
> `ingester.verify_schema`. Puedes invocarlos directo con
> `kb-generator/.venv/bin/python -m ingester.init_schema` o, gracias a
> los entry points de `pyproject.toml`,
> `kb-generator/.venv/bin/ingester-init-schema` (ídem para `verify`).

---

## 4. Uso

### Flujo completo
```bash
python agents/knowledge_base_agent.py
```
Descarga, estructura y verifica cobertura en un solo paso.

### Solo una subtarea
```bash
python agents/knowledge_base_agent.py --solo-descargar
python agents/knowledge_base_agent.py --solo-estructurar
python agents/knowledge_base_agent.py --verificar-cobertura
```

### Ingester (por construir — Fases 3 y 4 del
[plan de implementación](../docs/implementation-plan.md))
```bash
python -m ingester.cli ingest-all              # batch completo
python -m ingester.cli ingest-file <path>      # documento suelto
python -m ingester.cli reindex --categoria X   # rebuild selectivo
python -m ingester.cli stats                   # inventario indexado
```

---

## Estructura

```
kb-generator/
├── agents/
│   └── knowledge_base_agent.py       # orquestador del pipeline
├── scripts/
│   ├── descargar_base_conocimiento.py
│   ├── descargar_corredores_invias.py
│   ├── validar_base_conocimiento.py
│   ├── limpiar_descargas.py
│   └── agente_estructuracion_documentos.md
├── skills/
│   └── knowledge-base-builder/SKILL.md   # guía del estructurador
├── ingester/                         # Chroma + Neo4j (en construcción)
├── base_conocimiento/                # generado (en .gitignore)
│   ├── fuentes/                      # PDFs/XLS originales
│   ├── estructurados/                # MDs con YAML front matter + JSON
│   ├── metadata.json
│   └── reporte_*.{json,md}
└── requirements.txt
```

---

## Referencias

- [ADRs del proyecto](../docs/adr/)
- [Plan de implementación](../docs/implementation-plan.md)
- [Skill del estructurador](skills/knowledge-base-builder/SKILL.md)

