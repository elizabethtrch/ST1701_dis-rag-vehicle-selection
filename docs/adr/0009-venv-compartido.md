# ADR-0009: Entorno Python compartido en la raíz del monorepo

- **Status**: Accepted
- **Date**: 2026-04-20
- **Deciders**: Edward Rayo, Elizabeth Toro, Santiago Cardona

## Contexto

Al agregar las dependencias de embeddings e ingesta (`sentence-transformers`,
`chromadb`) en [`kb-generator/pyproject.toml`](../../kb-generator/pyproject.toml),
detectamos que `api/pyproject.toml` ya pide **las mismas deps pesadas**:
`sentence-transformers` (trae torch, ~500 MB) y `chromadb` (~200 MB con
onnxruntime). Mantener un venv por componente implicaba duplicar ~1 GB
en disco y volver a descargar todo cada vez que hay que recrear el
entorno.

Las versiones requeridas por ambos componentes son compatibles en el
alcance actual (ningún componente pide un rango de versiones que
contradiga al otro).

## Decisión

Usar **un único entorno virtual `.venv/` en la raíz del monorepo**.
El target `make install` lo crea y ejecuta:

```bash
pip install -e ./kb-generator -e ./api
```

Ambos `pyproject.toml` se instalan en **modo editable** en ese venv.
Los entry points de cada componente quedan disponibles en
`.venv/bin/` (p.ej. `ingester-ingest-all`, `uvicorn`), y los targets
de `Makefile` invocan directamente `.venv/bin/python`.

## Consecuencias

- **Positivas**:
  - 50 % menos de disco y una sola descarga de torch / transformers /
    chromadb para todo el monorepo.
  - `kb-generator/` y `api/` pueden compartir utilidades sin tener que
    publicarlas como paquete, solo cambiando imports relativos (siempre
    y cuando ambas viven en el mismo venv).
  - Flujo `make install` cubre ambos componentes: no hay que recordar
    dos targets separados.
- **Negativas**:
  - Las versiones de dependencias quedan **acopladas**: si más adelante
    `api/` necesita `pydantic 3.x` y `kb-generator/` está anclado en
    `2.x`, `pip` fallará la resolución y habrá que actualizar ambos a la
    vez.
  - Si algún colaborador prefiere venvs separados por componente, el
    Makefile no lo soporta nativamente y tendría que instalarlos a mano.
- **Neutrales**:
  - `.venv/` ya está en `.gitignore`; no hay cambios en infraestructura
    de CI.
  - Las instrucciones de setup se centralizan en el `README.md` de la
    raíz; los READMEs por componente remiten ahí.

