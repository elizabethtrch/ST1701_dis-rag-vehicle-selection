# ADR-0008: Neo4j Community Edition — invariantes de existencia en el ingester

- **Status**: Accepted
- **Date**: 2026-04-20
- **Deciders**: Edward Rayo, Elizabeth Toro, Santiago Cardona

## Contexto

En [ADR-0002](./0002-bases-de-datos-contenerizadas.md) decidimos
contenerizar Neo4j usando la imagen oficial `neo4j:5.22-community`.
Al aplicar el schema del grafo durante la Fase 2 del
[plan de implementación](../implementation-plan.md) descubrimos que
los _property existence constraints_ (`CREATE CONSTRAINT ... IS NOT NULL`)
son **una feature de Neo4j Enterprise Edition**. En Community Edition
se rechazan con:

```
Neo.DatabaseError.Schema.ConstraintCreationFailed:
Property existence constraint requires Neo4j Enterprise Edition.
```

Neo4j Community Edition tampoco ofrece: RBAC multiusuario, clustering
causal, múltiples bases por instancia, replicación ni backup online.

## Decisión

Continuar con **Neo4j Community Edition**. En particular:

- `schema.cypher` solo declara constraints `UNIQUE` e índices
  secundarios — todo compatible con Community.
- Los campos críticos que no podemos marcar como `NOT NULL` a nivel de
  DB (`Corredor.nombre`, `Documento.categoria`) los **valida el
  ingester en Python** antes de cada `MERGE`. Si el dato falta, el
  ingester aborta la operación con un error explícito.

## Consecuencias

- **Positivas**:
  - Licencia gratuita, suficiente para el alcance actual del proyecto
    (single-user, entornos académico y de desarrollo).
  - Imagen oficial más liviana y sin trámites de licenciamiento.
  - Las queries Cypher funcionan idénticamente entre Community y
    Enterprise, así que una eventual migración no afecta al
    `RecommendationService` ni al modelo de dominio.
- **Negativas**:
  - El código del ingester carga con la responsabilidad de validar
    invariantes de existencia. Un bug ahí podría insertar nodos con
    campos críticos `NULL`, y el DB no lo atajaría.
  - Mitigación: centralizar la validación en los mappers del ingester
    (un solo lugar por tipo de nodo) y cubrirla con tests unitarios.
- **Neutrales**:
  - Si más adelante se necesita RBAC, multi-DB o clustering, se puede
    migrar a Enterprise cambiando solo la imagen del `docker-compose`
    y volviendo a habilitar las constraints `IS NOT NULL` en
    `schema.cypher`. El resto del código no requiere cambios.

