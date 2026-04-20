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

## 1. Pre-requisitos: contenedores arriba

Ambas bases se orquestan con `docker-compose.yml` de la raíz del repo
(ver [ADR-0002](../docs/adr/0002-bases-de-datos-contenerizadas.md)).

```bash
# Desde la raíz del repo, la primera vez:
./scripts/bootstrap.sh      # crea volúmenes con tu UID + genera .env
docker compose up -d
```

### Validar los accesos

**Estado general**
```bash
docker compose ps
```
Ambos servicios deben mostrar `Up (healthy)` (~30-60 s).

**ChromaDB (HTTP)**
```bash
curl -s http://localhost:8001/api/v1/heartbeat
# → {"nanosecond heartbeat": <timestamp>}

curl -s http://localhost:8001/api/v1/version
# → "0.5.23"

curl -s http://localhost:8001/api/v1/collections
# → [] (vacío hasta la primera ingesta)
```

**Neo4j (Browser)**
- URL: http://localhost:7474
- Connect URL: `bolt://localhost:7687`
- Credenciales: `neo4j` / `neo4jpass` (ajustables en `.env`)
- En el primer login pedirá cambiar la contraseña.

**Neo4j (CLI Cypher)**
```bash
docker compose exec neo4j cypher-shell -u neo4j -p neo4jpass "RETURN 1 AS ok"
docker compose exec neo4j cypher-shell -u neo4j -p neo4jpass "RETURN apoc.version() AS version"
```

**Prueba de persistencia**
```bash
# Crea un nodo, reinicia y valida que sobreviva
docker compose exec neo4j cypher-shell -u neo4j -p neo4jpass \
  "CREATE (:Test {msg: 'hola'}) RETURN 'ok'"

docker compose restart neo4j && sleep 15

docker compose exec neo4j cypher-shell -u neo4j -p neo4jpass \
  "MATCH (n:Test) RETURN n.msg"

# Limpieza
docker compose exec neo4j cypher-shell -u neo4j -p neo4jpass \
  "MATCH (n:Test) DELETE n"
```

---

## 2. Setup de Python

```bash
cd kb-generator
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 3. Uso

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

