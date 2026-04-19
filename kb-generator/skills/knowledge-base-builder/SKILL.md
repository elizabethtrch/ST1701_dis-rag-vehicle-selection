---
name: knowledge-base-builder
description: >
  Skill para construir y mantener la base de conocimiento del RAG de selección
  de vehículos agrícolas. Úsalo siempre que el usuario pida descargar documentos,
  estructurar PDFs en Markdown, actualizar el catálogo de fuentes, revisar la
  cobertura de la base de conocimiento, agregar nuevos documentos al catálogo,
  o preparar archivos para ingestión al pipeline RAG. También úsalo cuando el
  usuario mencione "base de conocimiento", "documentos del RAG", "fichas técnicas",
  "normativa de transporte" o "metadatos de ingestión".
---

# Knowledge Base Builder

Agente para construir y mantener la base de conocimiento del proyecto
API RAG para selección inteligente de vehículos en logística agrícola
colombiana.

## Qué hace este agente

1. Descarga PDFs de fuentes institucionales colombianas (ICA, AGROSAVIA,
   INVIAS, INVIMA, MinTransporte, DANE-SIPSA) y los organiza en las cinco
   categorías documentales del proyecto.
2. Procesa cada PDF y produce un archivo Markdown estructurado con YAML
   front matter, tablas de condiciones técnicas y fragmentos clave para
   el retriever.
3. Mantiene el archivo `base_conocimiento/metadata.json` actualizado con
   el estado de cada documento.
4. Verifica la cobertura de la base de conocimiento frente a los escenarios
   de negocio del RAG.

---

## Flujo de trabajo

### Paso 1 — Identificar la tarea

Antes de hacer cualquier cosa, determina cuál de estas subtareas pide
el usuario:

- **A. Descarga**: el usuario quiere bajar documentos nuevos.
- **B. Estructuración**: el usuario tiene PDFs y quiere convertirlos a Markdown.
- **C. Verificación de cobertura**: el usuario quiere saber qué falta.
- **D. Actualización del catálogo**: el usuario quiere agregar una nueva fuente.

Si no está claro, pregunta una sola cosa: "¿Quieres descargar documentos,
estructurar los que ya tienes, o revisar qué falta?"

---

### Subtarea A — Descarga de documentos

**Ejecuta el script existente:**

```bash
cd api-rag-vehiculos
python scripts/descargar_base_conocimiento.py
```

**Después de la descarga:**

1. Lee el archivo `base_conocimiento/metadata.json` generado.
2. Reporta al usuario cuántos documentos se descargaron, cuántos fallaron
   y cuáles requieren descarga manual.
3. Para cada documento fallido, muestra la URL y la ruta de destino esperada.
4. Si hay documentos fallidos, ofrece reintentar o guiar la descarga manual.

**Si el usuario quiere agregar documentos al catálogo antes de descargar:**
Ir a Subtarea D primero, luego volver aquí.

---

### Subtarea B — Estructuración de PDFs a Markdown

Para cada PDF que el usuario indique (o todos los que no tengan `.md` aún):

#### B.1 Detectar PDFs sin Markdown

Los archivos fuente viven en `base_conocimiento/fuentes/<cat>/` y sus
contrapartes estructuradas en `base_conocimiento/estructurados/<cat>/`
(con la misma ruta relativa pero extensión `.md` o `.json`).

```python
from pathlib import Path

FUENTES = Path("base_conocimiento/fuentes")
ESTRUCTURADOS = Path("base_conocimiento/estructurados")

pendientes = []
for patron in ("*.pdf", "*.xls", "*.xlsx"):
    for doc in FUENTES.rglob(patron):
        rel = doc.relative_to(FUENTES)
        salida_md = ESTRUCTURADOS / rel.with_suffix(".md")
        salida_json = ESTRUCTURADOS / rel.with_suffix(".json")
        if not salida_md.exists() and not salida_json.exists():
            pendientes.append(doc)
```

Muestra la lista al usuario antes de proceder.

#### B.2 Determinar la categoría del documento

Lee la carpeta en que está el PDF. La carpeta es la categoría:

| Carpeta                        | Categoría                        | Plantilla |
|-------------------------------|----------------------------------|-----------|
| `01_fichas_tecnicas_productos` | Fichas técnicas de productos     | PLANTILLA_1 |
| `02_catalogo_flota_vehicular`  | Catálogo de flota                | PLANTILLA_2 |
| `03_condiciones_rutas_vias`    | Condiciones de rutas y vías      | PLANTILLA_3 |
| `04_tarifas_costos_transporte` | Tarifas y costos de transporte   | PLANTILLA_4 |
| `05_normativa_transporte`      | Normativa de transporte agrícola | PLANTILLA_5 |#### B.3 Leer el PDF

Usa la herramienta de lectura de archivos de Claude Code para leer el
contenido del PDF. Si el PDF tiene más de 50 páginas, lee primero las
secciones más relevantes según la categoría:

- Categoría 1: busca tablas de temperatura, humedad y vida útil.
- Categoría 3: busca restricciones de peso, dimensión y temporadas.
- Categoría 5: busca artículos sobre vehículos, refrigeración y sanciones.

#### B.4 Producir el archivo Markdown

Escribe el `.md` en `base_conocimiento/estructurados/<cat>/` con el mismo
nombre base del archivo fuente. Ejemplo:

    fuente:  base_conocimiento/fuentes/05_normativa_transporte/invima_acta.xls
    salida:  base_conocimiento/estructurados/05_normativa_transporte/invima_acta.md

Usa la plantilla correspondiente a la categoría (ver sección PLANTILLAS
más abajo).

**Reglas invariables para todos los Markdowns:**

- Siempre incluir el bloque YAML front matter al inicio.
- Conservar cifras técnicas exactamente como aparecen en el documento
  original (temperatura, humedad, pesos, artículos de ley).
- No parafrasear números. Si dice "entre 8°C y 12°C", escribir eso
  exactamente, no "temperatura moderada".
- Incluir siempre la sección "Fragmentos clave para el RAG" al final.
- Máximo 1500 palabras por archivo Markdown. Si el documento es muy extenso,
  priorizar los datos más relevantes para la decisión de transporte.

#### B.5 Actualizar metadata.json

Después de crear cada `.md`, actualizar el campo `md_generado: true` y
`fecha_estructuracion` en el documento correspondiente del `metadata.json`.

---

### Subtarea C — Verificación de cobertura

Lee todos los archivos `.md` de la base de conocimiento y responde:

1. **Productos cubiertos**: lista de productos con fichas técnicas completas
   (tienen temperatura, humedad y tipo de vehículo recomendado).

2. **Productos faltantes**: productos agrícolas colombianos importantes
   que no están en la base. Referencia mínima esperada:
   aguacate Hass, plátano hartón, café pergamino, flores de corte,
   papa, tomate, mango, mora, uchuva, espárragos.

3. **Normativa cubierta**: resoluciones y decretos presentes.
   Referencia mínima esperada: Resolución 2674/2013, Resolución 2505/2004.

4. **Escenarios de prueba**: evalúa estos dos escenarios concretos:

   - **Escenario A**: Pedido de 1.200 kg de aguacate Hass desde Antioquia
     a Bogotá, prioridad alta, flota con un vehículo refrigerado y uno
     abierto disponibles.
   - **Escenario B**: Pedido de flores de corte en temporada de lluvia,
     ruta con vía terciaria, vehículo con restricción de dimensión.

   Para cada escenario, responde: ¿la base actual tiene suficiente información
   para que el LLM fundamente una recomendación? ¿Qué falta?

Presenta el resultado como una tabla:

| Elemento | Estado | Fuente disponible | Acción recomendada |
|----------|--------|-------------------|--------------------|
|          |        |                   |                    |

---

### Subtarea D — Agregar fuente al catálogo

Cuando el usuario quiera agregar un documento nuevo:

1. Pedir al usuario: URL del documento, nombre descriptivo, categoría
   (1 a 5), fuente institucional y año.
2. Agregar la entrada al diccionario `DOCUMENTOS` en
   `scripts/descargar_base_conocimiento.py` con todos los campos requeridos.
3. Mostrar la entrada agregada para que el usuario la confirme.
4. Ofrecer ejecutar la descarga de inmediato.

**Campos requeridos para cada entrada:**

```python
{
    "id": "identificador_unico_sin_espacios",
    "nombre": "nombre_archivo.pdf",
    "url": "https://url-directa-al-pdf.pdf",
    "categoria": "01_fichas_tecnicas_productos",  # una de las cinco
    "fuente": "Nombre de la entidad",
    "descripcion": "Qué contiene y para qué sirve en el RAG.",
    "tipo": "normativa | manual | ficha_tecnica | acta | reporte",
    "anno": 2024,
}
```

---

## Plantillas de estructuración

### PLANTILLA_1 — Fichas técnicas de productos

```markdown
---
fuente: [entidad]
titulo: [título exacto]
anno: [año]
categoria_rag: fichas_tecnicas_productos
tipo: [manual | ficha_tecnica]
url_origen: [URL]
fecha_procesamiento: [YYYY-MM-DD]
productos_cubiertos: [lista]
ambito_geografico: [Colombia | internacional]
md_generado: true
---

# [Título del documento]

## Resumen
[Dos oraciones. Propósito y relevancia para el transporte. Máx. 60 palabras.]

## Condiciones por producto

### [Nombre del producto]

| Parámetro             | Valor mínimo | Valor óptimo | Valor máximo | Unidad |
|-----------------------|-------------|--------------|--------------|--------|
| Temperatura           |             |              |              | °C     |
| Humedad relativa      |             |              |              | %      |
| Vida útil en tránsito |             |              |              | días   |

**Tipo de vehículo recomendado**: [refrigerado | isotérmico | abierto ventilado]

**Incompatibilidades**: [productos que no deben ir juntos. Omitir si no aplica.]

**Alertas de deterioro**: [señales visibles durante el recorrido.]

**Condiciones especiales**: [fragilidad, apilamiento, etileno, etc.]

---
[Repetir por cada producto]

## Tabla comparativa

| Producto | Temp. mín (°C) | Temp. ópt (°C) | Temp. máx (°C) | Humedad (%) | Vida útil (días) |
|----------|----------------|----------------|----------------|-------------|------------------|

## Fragmentos clave para el RAG
[3 a 5 párrafos o tablas del documento original que respondan:
qué condiciones requiere el producto y qué vehículo es apto.
Transcribir fielmente, sin parafrasear cifras.]
```

---

### PLANTILLA_2 — Catálogo de flota vehicular

```markdown
---
fuente: [MinTransporte | equipo del proyecto]
titulo: [título del documento]
anno: [año]
categoria_rag: catalogo_flota_vehicular
tipo: [manual | json_estructurado]
url_origen: [URL o "interno"]
fecha_procesamiento: [YYYY-MM-DD]
ambito_geografico: Colombia
md_generado: true
---

# [Título del documento]

## Resumen
[Dos oraciones. Propósito y cobertura del documento. Máx. 60 palabras.]

## Configuraciones vehiculares reconocidas

| Configuración | Nombre común    | Capacidad máx (ton) | Tipo de carrocería permitida | Carga refrigerada |
|--------------|-----------------|--------------------|-----------------------------|-------------------|
|              |                 |                    |                             | Sí / No           |

## Especificaciones por vehículo

### [Nombre o matrícula del vehículo / configuración]

| Parámetro                 | Valor       | Unidad |
|--------------------------|-------------|--------|
| Capacidad en kg           |             | kg     |
| Capacidad en m³           |             | m³     |
| Tipo de carrocería        |             |        |
| Rango de temperatura      |             | °C     |
| Autonomía estimada        |             | km     |
| Restricción de dimensión  |             | m      |
| Costo por km referencia   |             | COP/km |

**Restricciones de acceso**: [zonas, tipos de vía o condiciones donde
no puede circular este vehículo.]

**Apto para**: [tipos de producto o condiciones de carga.]

---
[Repetir por cada vehículo o configuración]

## Fragmentos clave para el RAG
[3 a 5 párrafos o filas de tabla que respondan: qué vehículos están
disponibles y cuáles son sus capacidades y restricciones relevantes
para la decisión de transporte.]
```

---

### PLANTILLA_3 — Condiciones de rutas y vías

```markdown
---
fuente: [entidad]
titulo: [título exacto]
anno: [año]
categoria_rag: condiciones_rutas_vias
tipo: reporte
url_origen: [URL]
fecha_procesamiento: [YYYY-MM-DD]
ambito_geografico: [departamentos o corredores cubiertos]
md_generado: true
---

# [Título del documento]

## Resumen
[Dos oraciones. Máx. 60 palabras.]

## Estado de la red vial

### Red terciaria
[Condición general. Porcentajes en buen/regular/mal estado si disponibles.]

## Restricciones por tipo de vehículo

| Tipo de vía | Peso máximo (ton) | Dimensión máxima | Observaciones |
|-------------|------------------|-----------------|---------------|

## Restricciones temporales
[Cierres por lluvia, temporadas de riesgo, restricciones nocturnas.]

## Zonas de riesgo
[Puntos críticos por deslizamiento, inundación u otras condiciones.]

## Fragmentos clave para el RAG
[3 a 5 párrafos que respondan: qué restricciones de ruta o temporada
afectan el transporte de productos agrícolas.]
```

---

### PLANTILLA_4 — Tarifas y costos de transporte

```markdown
---
fuente: [MinTransporte | área financiera del proyecto]
titulo: [título del documento]
anno: [año]
categoria_rag: tarifas_costos_transporte
tipo: [manual | reporte | hoja_calculo]
url_origen: [URL o "interno"]
fecha_procesamiento: [YYYY-MM-DD]
vigencia: [fecha hasta la que aplican estas tarifas]
md_generado: true
---

# [Título del documento]

## Resumen
[Dos oraciones. Cobertura geográfica y tipos de vehículo incluidos.
Máx. 60 palabras.]

## Estructura de costos por componente

| Componente         | Descripción                          | % del costo total (ref.) |
|-------------------|--------------------------------------|--------------------------|
| Combustible        |                                      |                          |
| Peajes             |                                      |                          |
| Conductor          |                                      |                          |
| Mantenimiento      |                                      |                          |
| Seguro de carga    |                                      |                          |
| Administración     |                                      |                          |

## Tarifas de referencia por ruta y configuración

| Origen | Destino | Configuración vehicular | Tipo de carga | Tarifa (COP) | Unidad |
|--------|---------|------------------------|---------------|-------------|--------|
|        |         |                        |               |             | por ton-km |

## Tarifas para carga refrigerada

| Origen | Destino | Vehículo refrigerado | Tarifa base (COP) | Recargo refrigeración (COP) |
|--------|---------|---------------------|------------------|-----------------------------|

## Notas de vigencia y actualización
[Fecha de la última actualización de tarifas. Frecuencia de revisión.
Norma que regula los costos mínimos obligatorios (Res. 34405/2021).]

## Fragmentos clave para el RAG
[3 a 5 filas o párrafos que respondan: cuánto cuesta transportar
qué tipo de carga entre qué puntos con qué tipo de vehículo.]
```

---

### PLANTILLA_5 — Normativa de transporte agrícola

```markdown
---
fuente: [INVIMA | MinTransporte | MinSalud]
titulo: [número y nombre del acto normativo]
anno: [año de expedición]
categoria_rag: normativa_transporte_agricola
tipo: normativa
url_origen: [URL]
fecha_procesamiento: [YYYY-MM-DD]
normas_relacionadas: [lista de normas que modifica o complementa]
md_generado: true
---

# [Número y nombre del acto normativo]

## Datos de la norma
- **Entidad emisora**:
- **Fecha de expedición**:
- **Vigencia**:

## Resumen
[Dos oraciones sobre el objeto y ámbito de aplicación. Máx. 60 palabras.]

## Ámbito de aplicación
[A quién aplica y a qué actividades. Excepciones explícitas.]

## Requisitos para vehículos transportadores

### Temperatura de transporte
[Artículos relevantes con número de artículo.]

### Cadena de frío y refrigeración
[Ídem.]

### Higiene e inocuidad
[Requisitos de limpieza y materiales de contacto con alimentos.]

### Documentación requerida
[Registros, permisos y actas que debe portar el transportador.]

## Artículos clave para el RAG

- **Artículo [N]** – [tema]: "[cita textual, máx. 3 oraciones]"
- **Artículo [N]** – [tema]: "[cita textual, máx. 3 oraciones]"

## Fragmentos clave para el RAG
[3 a 5 artículos o incisos que respondan: qué normas regulan el
transporte de alimentos y qué vehículo es legalmente apto.]
```

---

## Validaciones antes de cerrar la tarea

Antes de reportar la tarea como completada, verifica:

- [ ] Cada PDF descargado tiene su `.md` correspondiente en la misma carpeta.
- [ ] Cada `.md` tiene el bloque YAML front matter completo.
- [ ] El campo `md_generado: true` está en el `metadata.json` para cada
      documento procesado.
- [ ] La sección "Fragmentos clave para el RAG" está presente en cada `.md`.
- [ ] No hay cifras técnicas parafraseadas (temperatura, humedad, artículos
      de ley deben ser literales).

---

## Qué NO hace este agente

- No construye el pipeline de ingestión (ChromaDB, Neo4j, embeddings).
- No genera el JSON de flota real. Ese archivo (`02_catalogo_flota_vehicular/flota_real.json`)
  debe ser provisto por el equipo del proyecto con los vehículos reales: matrícula, capacidad
  en kg y m³, tipo de carrocería, rango de temperatura, costo por km y restricciones. Sin ese
  archivo, el RAG puede describir el tipo de vehículo ideal pero no recomendar uno concreto
  de la flota. El documento ABC del SICE-TAC en la carpeta 02 sirve como referencia de los
  tipos legales mientras el JSON real no esté disponible.
- No descarga datos del DANE-SIPSA en tiempo real (requieren registro y API key).
- No accede a visores web interactivos de INVIAS.
- No descarga el Excel de estado de red vial de INVIAS (requiere navegación manual).
  La URL de descarga manual es:
  https://www.invias.gov.co/index.php/informacion-institucional/2-principal/57-estado-de-la-red-vial

Cuando el usuario pida algo fuera de este alcance, indicarlo claramente
y sugerir el siguiente paso.
