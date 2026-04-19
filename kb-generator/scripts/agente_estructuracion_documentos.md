# Prompt de estructuración de base de conocimiento
# API RAG para selección inteligente de vehículo – Dominio logística agrícola colombiana

---

## Cómo usar este prompt

1. Abre una conversación nueva con Claude.
2. Adjunta uno o más documentos PDF de la carpeta `base_conocimiento/`.
3. Indica a cuál de las cinco categorías pertenece el documento.
4. Pega el bloque del prompt que corresponda a esa categoría.
5. Guarda la salida en un archivo Markdown con el mismo nombre del PDF
   pero con extensión `.md`, dentro de la misma subcarpeta.

Puedes procesar varios documentos de la misma categoría en una sola
sesión adjuntando todos los PDFs al mismo tiempo.

---

## PROMPT UNIVERSAL (aplica a cualquier categoría)

```
Eres un especialista en logística agrícola colombiana y en la
preparación de bases de conocimiento para sistemas RAG
(Retrieval-Augmented Generation).

Tu tarea es procesar el documento adjunto y producir un archivo
Markdown estructurado que sirva como fuente documental para un
servicio de selección inteligente de vehículos de transporte
agrícola.

## Contexto del sistema RAG

El sistema recibe pedidos de productos agrícolas (aguacate, plátano,
café, flores, granos, hortalizas, entre otros) y debe recomendar
el vehículo más adecuado de una flota disponible, considerando:
- Requisitos de temperatura, humedad y ventilación del producto
- Restricciones normativas de transporte (cadena de frío, BPM)
- Condiciones de las rutas (vías terciarias, restricciones de peso)
- Costos y tiempos estimados de recorrido

Toda la información que extraigas debe estar orientada a responder
una o más de estas preguntas:
1. ¿Qué condiciones requiere este producto durante el transporte?
2. ¿Qué tipo de vehículo es apto para transportarlo?
3. ¿Qué normas regulan el transporte de este tipo de producto?
4. ¿Qué restricciones de ruta o temporada afectan el transporte?

## Instrucciones de procesamiento

1. Lee el documento completo antes de comenzar a estructurar.
2. Extrae únicamente información relevante para el contexto
   descrito. Omite secciones administrativas, referencias
   bibliográficas, índices y contenido que no aporte al
   razonamiento del sistema.
3. Organiza la información según la plantilla de la categoría
   indicada al final de este prompt.
4. Para cada dato numérico (temperatura, humedad, tiempo, peso),
   conserva la unidad de medida exactamente como aparece en el
   documento original.
5. Para cada norma o restricción, indica el artículo o numeral
   exacto de donde proviene.
6. Cuando el documento use términos técnicos específicos
   (por ejemplo, "cadena de frío", "vehículo isotérmico",
   "atmósfera controlada"), consérvelos tal como aparecen.
7. Si el documento menciona productos específicos con sus
   condiciones, crea una subsección por producto.
8. Si alguna sección de la plantilla no aplica a este documento,
   omítela sin dejar espacios vacíos.
9. No parafrasees las cifras técnicas. Transcríbelas fielmente.
10. Al final, incluye una sección de "Fragmentos clave para el RAG"
    con los tres a cinco párrafos del documento que más directamente
    responden las cuatro preguntas del contexto del sistema.

## Metadatos obligatorios al inicio del archivo

Incluye al comienzo del Markdown el siguiente bloque de metadatos:

---
fuente: [nombre de la entidad que publicó el documento]
titulo: [título exacto del documento]
anno: [año de publicación]
categoria_rag: [una de las cinco categorías de la Tabla 1]
tipo: [normativa | manual | ficha_tecnica | acta | reporte]
url_origen: [URL desde donde se descargó]
fecha_procesamiento: [fecha de hoy en formato YYYY-MM-DD]
productos_cubiertos: [lista de productos agrícolas mencionados]
ambito_geografico: [Colombia | regional | nacional | internacional]
---

## Categoría del documento que estás procesando

[REEMPLAZA ESTA LÍNEA con una de las cinco opciones:
 CATEGORÍA 1 – Fichas técnicas de productos
 CATEGORÍA 3 – Condiciones de rutas y vías
 CATEGORÍA 4 – Tarifas y costos de transporte
 CATEGORÍA 5 – Normativa de transporte agrícola]

Usa la plantilla correspondiente a esa categoría, que aparece
a continuación.
```

---

## PLANTILLA CATEGORÍA 1 – Fichas técnicas de productos

```
Aplica esta estructura al documento de fichas técnicas adjunto.

# [Título del documento]

## Resumen ejecutivo
[Dos a tres oraciones sobre el propósito del documento y su
relevancia para el transporte agrícola. Máximo 80 palabras.]

## Productos cubiertos
[Lista de todos los productos agrícolas mencionados en el documento,
con el nombre científico entre paréntesis si el documento lo incluye.]

## Fichas por producto

### [Nombre del producto 1]

#### Condiciones de transporte
| Parámetro            | Valor mínimo | Valor óptimo | Valor máximo | Unidad |
|----------------------|-------------|--------------|--------------|--------|
| Temperatura          |             |              |              | °C     |
| Humedad relativa     |             |              |              | %      |
| Ventilación requerida|             |              |              |        |
| Vida útil en tránsito|             |              |              | días   |

#### Tipo de vehículo recomendado
[Descripción del tipo de vehículo o carrocería adecuada: refrigerado,
isotérmico, abierto con ventilación, etc.]

#### Incompatibilidades
[Productos que no deben transportarse juntos. Si no aplica, omitir.]

#### Alertas de deterioro
[Señales de deterioro que el transportador debe vigilar durante
el recorrido.]

#### Condiciones especiales
[Restricciones adicionales: no apilar, frágil, requiere embalaje
específico, sensible a etileno, etc.]

---
[Repetir la sección "### [Nombre del producto]" para cada producto]
---

## Tabla comparativa de condiciones por producto
[Tabla resumen con todos los productos del documento y sus rangos
de temperatura y humedad relativa. Útil para búsqueda semántica
multiproducto.]

| Producto | Temp. mín (°C) | Temp. ópt (°C) | Temp. máx (°C) | Humedad (%) | Vida útil (días) |
|----------|----------------|----------------|----------------|-------------|------------------|
|          |                |                |                |             |                  |

## Fragmentos clave para el RAG
[Los tres a cinco párrafos o tablas del documento que más
directamente responden las preguntas: qué condiciones requiere
cada producto durante el transporte y qué tipo de vehículo es
apto para transportarlo. Transcríbelos fielmente.]
```

---

## PLANTILLA CATEGORÍA 3 – Condiciones de rutas y vías

```
Aplica esta estructura al documento de condiciones de rutas adjunto.

# [Título del documento]

## Resumen ejecutivo
[Dos a tres oraciones sobre el propósito del documento.]

## Cobertura geográfica
[Departamentos, regiones o corredores viales cubiertos
por el documento.]

## Estado de la red vial

### Red primaria
[Descripción del estado general de la red primaria cubierta.
Porcentajes en buen, regular o mal estado si están disponibles.]

### Red secundaria y terciaria
[Idem para red secundaria y terciaria. Este es el nivel más
relevante para el RAG por su impacto en el acceso a zonas
de producción agrícola.]

## Restricciones por tipo de vehículo

| Tipo de vía    | Restricción de peso (ton) | Restricción de dimensión | Observaciones |
|---------------|--------------------------|--------------------------|---------------|
|               |                          |                          |               |

## Restricciones temporales y climáticas
[Cierres por lluvia, temporadas de alto riesgo, restricciones
nocturnas, restricciones por cosecha, etc.]

## Tiempos de recorrido de referencia
[Si el documento incluye tiempos estimados por corredor o ruta,
transcribirlos aquí con sus unidades.]

## Zonas de riesgo
[Puntos críticos por deslizamientos, inundaciones, restricciones
sanitarias u otras condiciones que afecten la logística agrícola.]

## Fragmentos clave para el RAG
[Los tres a cinco párrafos que más directamente responden:
qué restricciones de ruta o temporada afectan el transporte.]
```

---

## PLANTILLA CATEGORÍA 5 – Normativa de transporte agrícola

```
Aplica esta estructura al documento normativo adjunto.

# [Número y nombre del acto normativo]

## Datos de la norma
- **Entidad emisora**: [MinTransporte | INVIMA | MinSalud | otro]
- **Fecha de expedición**: [DD/MM/AAAA]
- **Fecha de vigencia**: [DD/MM/AAAA o "vigente"]
- **Diario Oficial**: [número si está disponible]
- **Normas que modifica o complementa**: [listado]

## Resumen ejecutivo
[Dos a tres oraciones sobre el objeto y el ámbito de aplicación.
Máximo 80 palabras.]

## Ámbito de aplicación
[A quién aplica y a qué actividades o productos aplica.
Incluir las excepciones explícitas que mencione la norma.]

## Requisitos para vehículos transportadores de alimentos

### Condiciones de temperatura
[Extracto o paráfrasis fiel de los artículos que regulan
las temperaturas de transporte. Incluir número de artículo.]

### Condiciones de refrigeración y cadena de frío
[Ídem para cadena de frío.]

### Condiciones de higiene e inocuidad
[Requisitos de limpieza, desinfección, materiales de contacto
con alimentos.]

### Documentación y habilitación del vehículo
[Registros, permisos, actas que debe portar el transportador.]

## Sanciones e inspección
[Medidas sanitarias, sanciones por incumplimiento, autoridades
de inspección mencionadas.]

## Artículos de mayor relevancia para el RAG
[Lista de los artículos que más directamente afectan la decisión
de qué vehículo usar para transportar qué producto.
Formato: Artículo N – [tema breve] – [cita textual del artículo,
máximo tres oraciones.]]

## Fragmentos clave para el RAG
[Los tres a cinco artículos o incisos que más directamente
responden: qué normas regulan el transporte de este tipo
de producto y qué tipo de vehículo es legalmente apto.]
```

---

## Prompt adicional: verificación de cobertura

Una vez procesados todos los documentos, usa este prompt para
verificar que la base de conocimiento cubre los escenarios
del RAG:

```
Tienes acceso a los siguientes archivos Markdown de la base de
conocimiento del sistema RAG para selección de vehículos agrícolas:

[ADJUNTA LOS ARCHIVOS MARKDOWN GENERADOS]

Analiza la cobertura de la base de conocimiento y responde:

1. ¿Qué productos agrícolas colombianos comunes están cubiertos
   con fichas técnicas completas (temperatura, humedad, tipo de
   vehículo)?

2. ¿Qué productos importantes para la logística agrícola colombiana
   NO están cubiertos y deberían buscarse en fuentes adicionales?
   Sugiere dónde encontrar esa información (ICA, AGROSAVIA, FAO).

3. ¿Qué normativas de transporte están representadas? ¿Falta alguna
   resolución o decreto importante para el transporte de alimentos
   perecederos en Colombia?

4. Para el escenario de un pedido de aguacate Hass de 1.200 kg desde
   Antioquia a Bogotá, ¿la base de conocimiento actual tiene suficiente
   información para que el LLM fundamente una recomendación? ¿Qué falta?

5. Para el escenario de un pedido de flores de corte en temporada de
   lluvia, con restricciones de acceso por vía terciaria, ¿la base
   cubre los datos necesarios?

Presenta el análisis en una tabla de cobertura con columnas:
[Escenario | Información disponible | Información faltante | Fuente sugerida]
```

---

## Notas de implementación

**Sobre el tamaño de los chunks**: Los documentos procesados con
estas plantillas producen secciones bien delimitadas que el pipeline
de LangChain puede segmentar de forma más precisa que si se
vectorizara el PDF directamente. Cada sección de una ficha de
producto (por ejemplo, "Condiciones de transporte del aguacate Hass")
es un chunk natural de 200 a 500 tokens.

**Sobre los metadatos**: El bloque YAML al inicio de cada Markdown
se puede extraer automáticamente durante la ingestión para poblar
los campos `categoria`, `fuente` y `anno` de los metadatos del
chunk en ChromaDB.

**Sobre Neo4j**: Las tablas de incompatibilidades entre productos
(qué productos no deben transportarse juntos) y las tablas de
restricciones por tipo de vía son candidatas naturales para
modelarse como relaciones en el grafo Neo4j, no solo como
texto vectorizable.
