#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="compose.addon.yml"
SERVICE="sleep-checkins"
SCRIPT_DIR="/app/src/standalone_functions"

echo ""
echo "Garmin Sleep Check-Ins – Standalone Functions"
echo "---------------------------------------------"
echo "Select which standalone function you want to run:"
echo ""
echo "1) sleep_data_export.py        – Export sleep + journal data"
echo "2) demo.py                     – Run demo using sample data"
echo "3) delete_sleepjournal_entries.py – DELETE all SleepJournal entries"
echo ""
echo "q) Quit"
echo ""

read -rp "Enter your choice [1–3, q]: " choice

case "$choice" in
  1)
    SCRIPT="sleep_data_export.py"
    ;;
  2)
    SCRIPT="demo.py"
    ;;
  3)
    SCRIPT="delete_sleepjournal_entries.py"
    ;;
  q|Q)
    echo "Exiting."
    exit 0
    ;;
  *)
    echo "Invalid choice."
    exit 1
    ;;
esac

echo ""
echo "==> Running ${SCRIPT}"
echo ""

docker compose -f "${COMPOSE_FILE}" run --rm --build "${SERVICE}" \
  python "${SCRIPT_DIR}/${SCRIPT}"

echo ""
echo "Done."

