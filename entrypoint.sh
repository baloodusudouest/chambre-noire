#!/bin/sh
# Démarre en root, adopte le propriétaire du dossier /data (ton compte du NAS),
# puis lance l'appli avec ses droits. Aucun UID/GID à configurer.
set -eu

DATA="${CHAMBRE_NOIRE_DATA:-/data}"
mkdir -p "$DATA"

PUID="$(stat -c %u "$DATA")"
PGID="$(stat -c %g "$DATA")"
echo "chambre-noire : exécution avec UID=$PUID GID=$PGID (propriétaire de $DATA)"

export HOME="$DATA"
cd /app
exec gosu "$PUID:$PGID" uvicorn app.main:app --app-dir /app --host 0.0.0.0 --port "${CHAMBRE_NOIRE_PORT:-8100}" --proxy-headers --no-access-log
