#!/usr/bin/env python3
"""
InfluxDB write helpers for inbound Telegram messages.

Measurement (hardcoded name):
  "SleepJournal"
  tags:   chat_id, from_id
  fields: text, msg_type, from_username, from_name, message_id, update_id
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from influxdb import InfluxDBClient

INFLUXDB_HOST = os.getenv("INFLUXDB_HOST", "localhost")
INFLUXDB_PORT = int(os.getenv("INFLUXDB_PORT", "8086"))
INFLUXDB_DATABASE = os.getenv("INFLUXDB_DATABASE", "GarminStats")
INFLUXDB_USERNAME = os.getenv("INFLUXDB_USERNAME", "") or None
INFLUXDB_PASSWORD = os.getenv("INFLUXDB_PASSWORD", "") or None
INFLUXDB_SSL = os.getenv("INFLUXDB_SSL", "false").lower() in ("1", "true", "yes", "y")


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


def write_telegram_journal_entry(
    client: InfluxDBClient,
    *,
    chat_id: str,
    from_id: str,
    text: str,
    msg_type: str = "text",
    from_username: str = "",
    from_name: str = "",
    message_id: Optional[int] = None,
    update_id: Optional[int] = None,
    ts_utc: Optional[datetime] = None,
) -> None:
    if ts_utc is None:
        ts_utc = datetime.now(timezone.utc)

    point: Dict[str, Any] = {
        "measurement": "SleepJournal",
        "time": ts_utc.isoformat().replace("+00:00", "Z"),
        "tags": {
            "chat_id": str(chat_id),
            "from_id": str(from_id),
        },
        "fields": {
            "text": text,
            "msg_type": msg_type,
            "from_username": from_username,
            "from_name": from_name,
        },
    }
    if message_id is not None:
        point["fields"]["message_id"] = int(message_id)
    if update_id is not None:
        point["fields"]["update_id"] = int(update_id)

    client.write_points([point], time_precision="s")
