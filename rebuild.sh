#!/usr/bin/env bash
set -euo pipefail
echo "==> Make sure you are in the root or the repo"

COMPOSE_FILE="compose.addon.yml"

echo "==> Stopping addon services..."
docker compose -f "$COMPOSE_FILE" stop

echo "==> Removing addon containers..."
docker compose -f "$COMPOSE_FILE" rm -f

echo "==> Bringing stack down (networks left alone if external)..."
docker compose -f "$COMPOSE_FILE" down --remove-orphans

echo "==> Rebuilding images..."
docker compose -f "$COMPOSE_FILE" build --no-cache

echo "==> Starting long-running services..."
# Start everything defined EXCEPT one-shot helpers (best practice is to not define one-shots as services)
docker compose -f "$COMPOSE_FILE" up -d

echo "==> Running containers:"
docker compose -f "$COMPOSE_FILE" ps

echo ""
echo "Done."
echo "Tip: run one-shots like this when needed it rebuilds the container to ensure saved updated scripts are included, note this isn't getting passed telegram variables or scheduled ones:"
echo "docker compose -f compose.addon.yml run --rm --build sleep-checkins python /app/src/sleep_data_export.py"

