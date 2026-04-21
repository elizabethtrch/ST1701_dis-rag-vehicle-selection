# Architecture Decision Records (ADRs)

Cada ADR captura una decisión arquitectónica relevante: el contexto que
la motivó, la decisión misma y sus consecuencias. Usamos el formato
[MADR](https://adr.github.io/madr/) simplificado.

## Ciclo de vida

- **Proposed** → propuesta en discusión
- **Accepted** → decisión vigente
- **Deprecated** → reemplazada o descartada (enlaza al ADR que la
  sustituye, si aplica)

Cuando una decisión cambie, **no edites el ADR original**: crea un ADR
nuevo que la supere y marca el anterior como `Deprecated`.

## Índice

| # | Título | Status |
|---|--------|--------|
| [0001](./0001-monorepo-unificado.md) | Monorepo unificado (api + kb-generator) | Accepted |
| [0002](./0002-bases-de-datos-contenerizadas.md) | Bases de datos contenerizadas (ChromaDB + Neo4j) | Accepted |
| [0003](./0003-ingesta-centralizada-en-kb-generator.md) | Ingesta centralizada en kb-generator | Accepted |
| [0004](./0004-modelo-de-grafo-neo4j.md) | Modelo de grafo de conocimiento en Neo4j | Accepted |
| [0005](./0005-queries-cypher-parametrizadas.md) | Queries Cypher fijas parametrizadas | Accepted |
| [0006](./0006-calculo-deterministico-costos-tiempos.md) | Cálculo determinista de costos y tiempos | Accepted |
| [0007](./0007-categorias-unificadas-prefijo-numerico.md) | Categorías unificadas con prefijo numérico español | Accepted |
| [0008](./0008-neo4j-community-invariantes-en-ingester.md) | Neo4j Community Edition — invariantes en el ingester | Accepted |
| [0009](./0009-venv-compartido.md) | Entorno Python compartido en la raíz del monorepo | Accepted |

## Plantilla para un ADR nuevo

```markdown
# ADR-NNNN: Título de la decisión

- **Status**: Proposed | Accepted | Deprecated
- **Date**: YYYY-MM-DD
- **Deciders**: nombres de quienes deciden

## Contexto

Problema o pregunta que motiva la decisión. Mencionar restricciones,
supuestos y alternativas consideradas.

## Decisión

Qué se decidió, en una o dos frases claras.

## Consecuencias

- **Positivas**: qué se gana.
- **Negativas**: qué se pierde o complica.
- **Neutrales**: qué cambia sin ser mejor o peor.
```

