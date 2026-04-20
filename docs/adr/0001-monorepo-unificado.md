# ADR-0001: Monorepo unificado (api + kb-generator)

- **Status**: Accepted
- **Date**: 2026-04-19
- **Deciders**: Edward Rayo, Elizabeth Toro, Santiago Cardona

## Contexto

El proyecto se desarrolló inicialmente en dos repositorios separados:

- `api/` — servicio RAG en Python con arquitectura hexagonal.
- `kb-generator/` — pipeline que descarga PDFs institucionales y los
  estructura en Markdown para alimentar el RAG.

Al crecer el proyecto ambas partes empezaron a necesitar configuración
compartida (variables de entorno, infraestructura de datos, despliegue)
y versionamiento coherente. Mantener dos repos complicaba pruebas
end-to-end y desalineaba releases.

## Decisión

Unificar ambos componentes en un único repositorio con la siguiente
estructura en la raíz:

```
ST1701_dis-rag-vehicle-selection/
├── api/           # servicio FastAPI (consumidor)
├── kb-generator/  # pipeline de base de conocimiento (productor)
├── docs/          # documentación técnica (incluye ADRs)
└── ...            # infra compartida: docker-compose, .gitignore, README
```

Cada componente conserva su propia configuración interna (`api/pyproject.toml`,
`kb-generator/requirements.txt`) y puede ejecutarse independientemente.

## Consecuencias

- **Positivas**:
  - Una sola fuente de verdad para configuración e infraestructura.
  - Cambios que afectan ambos componentes se versionan en un único
    commit/PR.
  - Facilita pruebas integradas.
- **Negativas**:
  - El CI debe distinguir pipelines por subdirectorio si se quieren
    reglas distintas para cada componente.
- **Neutrales**:
  - Los entornos virtuales de Python se mantienen por subdirectorio.

