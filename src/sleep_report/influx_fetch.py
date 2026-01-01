
"""
influx_fetch.py

What this file does:
  - Establishes an InfluxDB connection using the same env vars as fixed_message.py
  - Provides simple fetch functions:
      * SleepSummary points (for baseline + selecting the current night)
      * SleepIntraday points (for the stage chart / intraday series)

This file does NOT:
  - Compute statistics
  - Select sessions
  - Render plots
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, List

from influxdb import InfluxDBClient

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


INFLUXDB_HOST = os.getenv("INFLUXDB_HOST", "localhost")
INFLUXDB_PORT = int(os.getenv("INFLUXDB_PORT", "8086"))
INFLUXDB_DATABASE = os.getenv("INFLUXDB_DATABASE", "GarminStats")
INFLUXDB_USERNAME = os.getenv("INFLUXDB_USERNAME", "") or None
INFLUXDB_PASSWORD = os.getenv("INFLUXDB_PASSWORD", "") or None
INFLUXDB_SSL = os.getenv("INFLUXDB_SSL", "false").lower() in ("1", "true", "yes", "y")


def connect_influx() -> InfluxDBClient:
    """Create and return an InfluxDB client (v1 client)."""
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


def fetch_sleep_summary_last_days(client: InfluxDBClient, days: int = 30) -> List[Dict]:
    """Fetch SleepSummary points for the last N days."""
    q = f'SELECT * FROM "SleepSummary" WHERE time > now() - {int(days)}d ORDER BY time ASC'
    result = client.query(q)
    return list(result.get_points())



def fetch_sleep_summary_time_range(client: InfluxDBClient, start_utc: datetime, end_utc: datetime) -> List[Dict]:
    """
    Fetch SleepSummary points for a specific UTC time window.
    Useful for one-shot generation on a specific day, and for computing baselines
    relative to that day (instead of relative to 'now()').
    """
    start_s = start_utc.isoformat().replace("+00:00", "Z")
    end_s = end_utc.isoformat().replace("+00:00", "Z")
    q = (
        'SELECT * FROM "SleepSummary" '
        f"WHERE time >= '{start_s}' AND time <= '{end_s}' ORDER BY time ASC"
    )
    result = client.query(q)
    return list(result.get_points())


def fetch_sleep_intraday_range(
    client: InfluxDBClient,
    start_utc: datetime,
    end_utc: datetime,
    *,
    measurement: str = "SleepIntraday",
) -> List[Dict]:
    """Fetch intraday points for a UTC time window."""
    # Influx expects RFC3339 timestamps
    start_s = start_utc.isoformat().replace("+00:00", "Z")
    end_s = end_utc.isoformat().replace("+00:00", "Z")
    q = (
        f'SELECT * FROM "{measurement}" '
        f"WHERE time >= '{start_s}' AND time <= '{end_s}' ORDER BY time ASC"
    )
    result = client.query(q)
    return list(result.get_points())
