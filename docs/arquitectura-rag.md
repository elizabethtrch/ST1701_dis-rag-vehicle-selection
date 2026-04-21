# Arquitectura RAG — Selección Inteligente de Vehículo

## Flujo de una recomendación

```mermaid
%%{init: {
  'theme': 'base',
  'themeVariables': {
    'primaryColor': '#e1f5fe',
    'primaryTextColor': '#2c3e50',
    'primaryBorderColor': '#b3e5fc',
    'lineColor': '#95a5a6',
    'secondaryColor': '#f3e5f5',
    'tertiaryColor': '#e8f5e9',
    'mainBkg': '#ffffff',
    'nodeBorder': '#d1d9e6',
    'clusterBkg': '#fafafa'
  }
}}%%
flowchart TD
    subgraph INPUT["Entrada"]
        REQ["SolicitudRecomendacion<br>─────────────────<br>productos []<br>flota_disponible []<br>origen / destino<br>peso_total_kg"]
    end

    subgraph SERVICE["RecommendationService"]
        direction TB
        ORCH["Orquestador<br>(recommendation_service.py)"]
    end

    subgraph CHROMA["ChromaDB — Búsqueda semántica"]
        direction TB
        VEC["Embedding de la consulta<br>(SentenceTransformers)"]
        COLL["Colección agro_transport<br>~chunks de MDs estructurados"]
        FRAG["Fragmentos relevantes<br>(score de similitud coseno)"]
        VEC --> COLL --> FRAG
    end

    subgraph NEO4J["Neo4j — Conocimiento estructurado"]
        direction TB
        Q1["Q1 get_requisitos_productos<br>→ temp_opt, humedad, tipo_vehiculo_req"]
        Q2["Q2 get_corredor<br>→ distancia_km, tiempo_min, estado_via"]
        Q3["Q3 get_tarifas_corredor<br>→ peajes con valor_cop por categoría"]
        Q4["Q4 get_normativa_tipos<br>→ Normativa + citas_textuales"]
    end

    subgraph CALC["CostCalculator — Determinista (ADR-0006)"]
        COST["calcular_costo(corredor, vehiculo, tarifas)<br>→ combustible + peajes + viáticos + seguro + imprevistos"]
        TIME["calcular_tiempo(corredor)<br>→ base + impacto_min_carga"]
    end

    subgraph LLM["LLM (Anthropic / OpenAI / Ollama)"]
        PROMPT["PromptBuilder<br>ensambla contexto semántico + grafo"]
        GEN["Genera JSON:<br>vehiculo_id, justificacion,<br>alternativas, alertas"]
    end

    subgraph OUTPUT["Salida"]
        REC["RecomendacionVehiculo<br>─────────────────<br>vehiculo_recomendado<br>justificacion<br>desglose_costo (COP)<br>tiempo_estimado_min<br>alternativas / alertas"]
    end

    REQ --> ORCH

    ORCH -- "query semántica<br>(productos + ruta)" --> VEC
    FRAG -- "contexto documental<br>(fichas, normativas, rutas)" --> PROMPT

    ORCH -- "nombres productos" --> Q1
    ORCH -- "origen, destino" --> Q2
    ORCH -- "corredor_id" --> Q3
    ORCH -- "tipos vehículo de la flota" --> Q4

    Q1 -- "requisitos físicos<br>de la carga" --> PROMPT
    Q2 -- "datos exactos<br>del corredor" --> PROMPT
    Q3 -- "tarifas de peajes" --> PROMPT
    Q4 -- "normas aplicables<br>+ citas legales" --> PROMPT

    Q2 -- "corredor dict" --> COST
    Q2 -- "corredor dict" --> TIME
    Q3 -- "tarifas list" --> COST

    PROMPT --> GEN
    GEN -- "vehiculo_id elegido" --> REC
    COST -- "DesgloseCosto" --> REC
    TIME -- "minutos" --> REC

    style CHROMA fill:#e8f4f8,stroke:#2196F3
    style NEO4J fill:#f3e8f8,stroke:#9C27B0
    style CALC fill:#e8f8e8,stroke:#4CAF50
    style LLM fill:#fff8e8,stroke:#FF9800
```

## ¿Por qué ChromaDB y Neo4j juntos?

| | ChromaDB | Neo4j |
|---|---|---|
| **Tipo de consulta** | "¿qué fragmentos hablan de transporte refrigerado?" | "¿cuánto cobra exactamente el peaje X para categoría C3?" |
| **Fortaleza** | Encuentra contexto relevante aunque no sepas qué buscar exactamente | Devuelve hechos precisos y relaciones entre entidades |
| **Qué aporta al RAG** | Le da al LLM contexto documental rico para razonar | Le da datos estructurados que el LLM **no debe inventar** (distancias, tarifas, requisitos legales) |
| **Limitación** | No conoce relaciones entre entidades (qué peajes tiene un corredor) | No hace búsqueda por similitud semántica |

El LLM solo decide **qué vehículo elegir y por qué** — los números (costos, tiempos) los
calcula el `CostCalculator` con los datos que ya trajo Neo4j.

## Qué vive en cada base de datos

### ChromaDB — chunks semánticos

Fragmentos de texto (~800 tokens) extraídos de los MDs estructurados, organizados por
categoría (ADR-0007):

| Categoría | Contenido |
|---|---|
| `fichas_tecnicas_productos` | Requisitos de temperatura, humedad y embalaje por cultivo |
| `catalogo_flota_vehicular` | Fichas técnicas de camiones, furgones y tracto-camiones |
| `condiciones_rutas_vias` | Estado de vías, restricciones y tiempos por corredor INVIAS |
| `tarifas_costos_transporte` | Tablas de referencia SICE-TAC y tarifas de fletes |
| `normativa_transporte` | Resoluciones MinTransporte e INVIMA sobre transporte de alimentos |

### Neo4j — grafo de conocimiento

Nodos y relaciones estructuradas para consultas Cypher precisas (ADR-0004, ADR-0005):

```
(:Corredor)──[:PASA_POR]──►(:Ciudad)
(:Corredor)──[:TIENE_PEAJE]──►(:Peaje)──[:TIENE_TARIFA]──►(:Tarifa)
(:Producto)──[:REQUIERE]──►(:ConfiguracionVehicular)
(:Normativa)──[:REGULA]──►(:TipoVehiculo)
(:Normativa)──[:CONTIENE]──►(:Articulo)
```

Las 4 queries Cypher fijas del servicio evitan que el LLM genere Cypher dinámico
(ADR-0005), eliminando riesgo de inyección y resultados no deterministas.

