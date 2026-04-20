// =============================================================
// Neo4j schema — grafo de conocimiento RAG
// Basado en ADR-0004: 12 nodos, 15 relaciones.
//
// Todo es idempotente (IF NOT EXISTS): se puede aplicar tantas
// veces como se quiera sin efectos adversos. Aplicado por
// kb-generator/ingester/init_schema.py
// =============================================================

// ── Unique constraints (identidad de cada nodo) ──────────────

CREATE CONSTRAINT producto_nombre_uq IF NOT EXISTS
FOR (p:Producto) REQUIRE p.nombre IS UNIQUE;

CREATE CONSTRAINT tipo_vehiculo_tipo_uq IF NOT EXISTS
FOR (t:TipoVehiculo) REQUIRE t.tipo IS UNIQUE;

CREATE CONSTRAINT configuracion_vehicular_nombre_uq IF NOT EXISTS
FOR (c:ConfiguracionVehicular) REQUIRE c.nombre IS UNIQUE;

CREATE CONSTRAINT vehiculo_matricula_uq IF NOT EXISTS
FOR (v:Vehiculo) REQUIRE v.matricula IS UNIQUE;

CREATE CONSTRAINT corredor_id_uq IF NOT EXISTS
FOR (c:Corredor) REQUIRE c.id IS UNIQUE;

CREATE CONSTRAINT ciudad_nombre_uq IF NOT EXISTS
FOR (c:Ciudad) REQUIRE c.nombre IS UNIQUE;

CREATE CONSTRAINT departamento_nombre_uq IF NOT EXISTS
FOR (d:Departamento) REQUIRE d.nombre IS UNIQUE;

// Tarifas, peajes y articulos no tienen identificador natural unico:
// el ingester construye un id sintetico (hash/composicion).
CREATE CONSTRAINT tarifa_id_uq IF NOT EXISTS
FOR (t:Tarifa) REQUIRE t.id IS UNIQUE;

CREATE CONSTRAINT peaje_id_uq IF NOT EXISTS
FOR (p:Peaje) REQUIRE p.id IS UNIQUE;

CREATE CONSTRAINT articulo_id_uq IF NOT EXISTS
FOR (a:Articulo) REQUIRE a.id IS UNIQUE;

CREATE CONSTRAINT normativa_numero_uq IF NOT EXISTS
FOR (n:Normativa) REQUIRE n.numero IS UNIQUE;

CREATE CONSTRAINT documento_id_uq IF NOT EXISTS
FOR (d:Documento) REQUIRE d.id IS UNIQUE;

// Nota: los "property existence constraints" (IS NOT NULL) son
// funcionalidad de Neo4j Enterprise Edition. En Community Edition no
// se pueden crear. El ingester es responsable de validar en Python
// que los campos criticos (Corredor.nombre, Documento.categoria) no
// sean NULL antes de cada MERGE.

// ── Secondary indexes (filtros y traversals frecuentes) ──────

CREATE INDEX producto_categoria_rag IF NOT EXISTS
FOR (p:Producto) ON (p.categoria_rag);

CREATE INDEX documento_categoria IF NOT EXISTS
FOR (d:Documento) ON (d.categoria);

CREATE INDEX corredor_es_critico IF NOT EXISTS
FOR (c:Corredor) ON (c.es_critico);

CREATE INDEX tarifa_origen_destino IF NOT EXISTS
FOR (t:Tarifa) ON (t.origen, t.destino);

CREATE INDEX peaje_categoria_vehicular IF NOT EXISTS
FOR (p:Peaje) ON (p.categoria_vehicular);

CREATE INDEX configuracion_categoria_peaje IF NOT EXISTS
FOR (c:ConfiguracionVehicular) ON (c.categoria_peaje);

