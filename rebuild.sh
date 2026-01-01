#!/usr/bin/env bash
set -euo pipefail

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

#Including a couple helpful commands while the main services are running
echo "For debugging if you want to see the output of your scheduler:"
echo "docker compose -f compose.addon.yml logs -f sleep-checkins-scheduler"
echo ""
echo "Tip: run one-shots like this when needed it rebuilds the container to ensure saved updated scripts are included, note this isn't getting passed telegram variables or scheduled ones:"
echo "docker compose -f compose.addon.yml run --rm --build sleep-checkins python /app/src/standalone_functions/sleep_data_export.py"

