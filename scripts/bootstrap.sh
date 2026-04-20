#!/usr/bin/env bash
# Prepara los volúmenes bindeados para docker-compose con permisos del
# usuario actual (sin root). Uso:
#
#   ./scripts/bootstrap.sh
#   docker compose up -d
#
# Idempotente: se puede ejecutar varias veces.

set -euo pipefail
cd "$(dirname "$0")/.."

HOST_UID="$(id -u)"
HOST_GID="$(id -g)"

echo "→ Preparando volúmenes en ./data/ para UID=$HOST_UID GID=$HOST_GID"
mkdir -p data/chroma
mkdir -p data/neo4j/data data/neo4j/logs data/neo4j/import data/neo4j/plugins

# Chroma escribe su log en /chroma/chroma.log (fuera del volumen de
# datos). Si no pre-existe como archivo, Docker lo crearía como
# directorio y romperia el bind mount.
touch data/chroma.log

# Si Docker ya creó directorios como root (ej. por un `docker compose up`
# previo sin bootstrap), hay que devolverlos al usuario actual.
if find data -maxdepth 4 -not -user "$HOST_UID" -print -quit 2>/dev/null | grep -q .; then
  echo "⚠️  Hay archivos en ./data con otro dueño. Corrigiendo con sudo chown…"
  sudo chown -R "$HOST_UID:$HOST_GID" data/
else
  echo "→ Permisos de ./data/ OK"
fi

# Genera .env desde el template si no existe
if [[ ! -f .env ]]; then
  cp .env.example .env
  # Ajusta HOST_UID/HOST_GID reales
  sed -i.bak "s/^HOST_UID=.*/HOST_UID=$HOST_UID/" .env
  sed -i.bak "s/^HOST_GID=.*/HOST_GID=$HOST_GID/" .env
  rm -f .env.bak
  echo "→ .env generado con HOST_UID=$HOST_UID HOST_GID=$HOST_GID"
else
  echo "→ .env ya existe; verifica HOST_UID=$HOST_UID HOST_GID=$HOST_GID"
fi

echo "✓ Listo. Ahora corre: docker compose up -d"

