# ADR-0004: Modelo de grafo de conocimiento en Neo4j

- **Status**: Accepted
- **Date**: 2026-04-20
- **Deciders**: Edward Rayo, Elizabeth Toro, Santiago Cardona

## Contexto

El dominio (logística agrícola colombiana) tiene entidades con
relaciones semánticas no triviales: un producto exige condiciones de
transporte que solo cumplen ciertos tipos de vehículo; un corredor
cruza departamentos y tiene tarifas distintas por categoría vehicular;
la normativa regula tipos de vehículo, productos y rutas.

Representar este conocimiento únicamente como chunks vectoriales
dificulta responder preguntas estructuradas (¿qué configuración cumple
refrigeración y tiene tarifa en este corredor?). El grafo complementa a
Chroma: Chroma recupera texto relevante, Neo4j responde hechos exactos.

El modelo se deriva de los datos reales disponibles y de las cinco
plantillas de estructuración del `kb-generator` (una por categoría
documental).

## Decisión

Modelar 12 tipos de nodo y 15 relaciones principales:

### Nodos

| Nodo | Origen | Propiedades clave |
|---|---|---|
| `Producto` | PLANTILLA_1 | `nombre`, `temp_min_c`, `temp_opt_c`, `temp_max_c`, `humedad_pct`, `vida_util_dias` |
| `TipoVehiculo` | PLANTILLA_1 | `tipo` ∈ `{refrigerado, isotermico, abierto_ventilado}` |
| `ConfiguracionVehicular` | SICE-TAC (PLANTILLA_2) | `nombre`, `capacidad_max_ton`, `carroceria`, `categoria_peaje` ∈ `{I..VII}` |
| `Vehiculo` | `flota_real.json` | `matricula`, `capacidad_kg`, `capacidad_m3`, `rango_temp_c`, `autonomia_km`, `costo_km_cop` |
| `Corredor` | `invias_corredores.json` | `id`, `nombre`, `distancia_km`, `tipo_terreno`, `es_critico`, `tiempo_base_min_carga`, `estado_general` |
| `Ciudad` | INVIAS | `nombre` |
| `Departamento` | INVIAS | `nombre` |
| `Tarifa` | XLSX peajes + PLANTILLA_4 | `origen`, `destino`, `tipo_carga`, `valor_cop`, `unidad`, `vigencia` |
| `Peaje` | XLSX peajes | `nombre`, `valor_cop`, `categoria_vehicular` |
| `Normativa` | PLANTILLA_5 | `numero`, `nombre`, `anno`, `entidad_emisora` |
| `Articulo` | PLANTILLA_5 | `numero`, `tema`, `cita_textual` |
| `Documento` | `metadata.json` | `id`, `nombre_archivo`, `categoria`, `fuente`, `url`, `sha256` |

### Relaciones

```cypher
(Producto)-[:REQUIERE_VEHICULO]->(TipoVehiculo)
(Producto)-[:INCOMPATIBLE_CON]->(Producto)

(Vehiculo)-[:ES_CONFIGURACION]->(ConfiguracionVehicular)
(ConfiguracionVehicular)-[:APTO_PARA]->(TipoVehiculo)

(Corredor)-[:ORIGEN]->(Ciudad)
(Corredor)-[:DESTINO]->(Ciudad)
(Corredor)-[:ATRAVIESA]->(Departamento)
(Ciudad)-[:UBICADA_EN]->(Departamento)

(Tarifa)-[:APLICA_A]->(Corredor)
(Tarifa)-[:APLICA_CONFIG]->(ConfiguracionVehicular)
(Peaje)-[:UBICADO_EN]->(Corredor)

(Normativa)-[:CONTIENE]->(Articulo)
(Normativa)-[:REGULA]->(TipoVehiculo)
(Normativa)-[:REGULA]->(Producto)
(Normativa)-[:MODIFICA]->(Normativa)

(Documento)-[:ORIGINA]->(*)   // trazabilidad documental
```

### Justificación de las decisiones clave

- **`ConfiguracionVehicular` separada de `Vehiculo`**: SICE-TAC define
  tipos legales (camión sencillo, tractocamión…); `Vehiculo` son las
  unidades reales de la flota. Así las tarifas/peajes se anclan al tipo
  legal y la recomendación elige la unidad concreta.
- **`Documento` como nodo de proveniencia**: cada nodo en Neo4j y cada
  chunk en Chroma apuntan al documento fuente → trazabilidad para la
  justificación del LLM.
- **`Corredor` como eje conector**: es el único nodo con datos reales
  ya disponibles (INVIAS) y conecta naturalmente con tarifas, peajes y
  productos transportables.

## Consecuencias

- **Positivas**:
  - Habilita traversals multi-hop para la recomendación (p.ej.
    `Producto → TipoVehiculo ← ConfiguracionVehicular ← Tarifa → Corredor`).
  - Trazabilidad documental completa vía `Documento`.
  - El LLM recibe hechos exactos (no alucinados) para razonar.
- **Negativas**:
  - Requiere mantener el mapeo `frontmatter YAML → nodos/relaciones` en
    el ingester.
  - Cambios de esquema en las plantillas implican migraciones en el
    grafo.
- **Neutrales**:
  - Los esquemas Cypher (constraints, índices únicos) se versionan
    junto con el ingester.

