#!/usr/bin/env python3
"""
fixed_message.py

Pulls SleepSummary data from InfluxDB, builds the deterministic sleep summary text,
then sends it via Telegram.

"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from influxdb import InfluxDBClient

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from deterministic_output import build_sleep_summary_text
from telegram_client import send_message


INFLUXDB_HOST = os.getenv("INFLUXDB_HOST", "localhost")
INFLUXDB_PORT = int(os.getenv("INFLUXDB_PORT", "8086"))
INFLUXDB_DATABASE = os.getenv("INFLUXDB_DATABASE", "GarminStats")
INFLUXDB_USERNAME = os.getenv("INFLUXDB_USERNAME", "") or None
INFLUXDB_PASSWORD = os.getenv("INFLUXDB_PASSWORD", "") or None
INFLUXDB_SSL = os.getenv("INFLUXDB_SSL", "false").lower() in ("1", "true", "yes", "y")


def parse_time_utc(t: str) -> datetime:
    dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def connect_influx() -> InfluxDBClient:
    client = InfluxDBClient(
        host=INFLUXDB_HOST,
        port=INFLUXDB_PORT,
        username=INFLUXDB_USERNAME,
        password=INFLUXDB_PASSWORD,
        ssl=INFLUXDB_SSL,
        verify_ssl=INFLUXDB_SSL,
        timeout=30,
        retries=3,
    )
    client.switch_database(INFLUXDB_DATABASE)
    return client


def fetch_sleep_summary_last_days(client: InfluxDBClient, days: int = 8) -> List[Dict]:
    q = f'SELECT * FROM "SleepSummary" WHERE time > now() - {days}d ORDER BY time ASC'
    result = client.query(q)
    return list(result.get_points())


def select_current_and_prior_week(points: List[Dict]) -> Optional[Tuple[Dict, List[Dict]]]:
    dated: List[Tuple[datetime, Dict]] = []
    for p in points:
        t = p.get("time")
        if isinstance(t, str):
            dated.append((parse_time_utc(t), p))

    if not dated:
        return None

    dated.sort(key=lambda x: x[0])
    current_time, current = dated[-1]
    start = current_time - timedelta(days=7)

    prior_week = [p for (t, p) in dated if start <= t < current_time]
    return current, prior_week


def main() -> None:
    client = connect_influx()
    points = fetch_sleep_summary_last_days(client, days=8)
    selection = select_current_and_prior_week(points)
    if selection is None:
        raise SystemExit("No SleepSummary data found in the last 8 days.")

    current, prior_week = selection
    text = build_sleep_summary_text(current_sleep=current, prior_week_sleeps=prior_week)

    send_message(text)
    print("Sent Telegram sleep summary.")


if __name__ == "__main__":
    main()
