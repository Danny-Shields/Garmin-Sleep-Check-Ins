#!/usr/bin/env python3
"""
delete_sleepjournal.py

Deletes ALL data for the measurement "SleepJournal" from an InfluxDB v1 database.

Uses the same env vars as the rest of the project:
- INFLUXDB_HOST
- INFLUXDB_PORT
- INFLUXDB_DATABASE
- (optional) INFLUXDB_USERNAME
- (optional) INFLUXDB_PASSWORD
- (optional) INFLUXDB_SSL  ("true"/"false")
"""

import os
import sys
from influxdb import InfluxDBClient


MEASUREMENT = "SleepJournal"


def connect_influx() -> InfluxDBClient:
    host = os.getenv("INFLUXDB_HOST", "localhost")
    port = int(os.getenv("INFLUXDB_PORT", "8086"))
    db = os.getenv("INFLUXDB_DATABASE", "GarminStats")
    user = os.getenv("INFLUXDB_USERNAME", "") or None
    pwd = os.getenv("INFLUXDB_PASSWORD", "") or None
    ssl = os.getenv("INFLUXDB_SSL", "false").lower() in ("1", "true", "yes", "y")

    client = InfluxDBClient(
        host=host,
        port=port,
        username=user,
        password=pwd,
        ssl=ssl,
        verify_ssl=ssl,
        timeout=30,
        retries=3,
    )
    client.switch_database(db)
    return client


def measurement_exists(client: InfluxDBClient, name: str) -> bool:
    res = client.query("SHOW MEASUREMENTS")
    return any(p.get("name") == name for p in res.get_points())


def main() -> None:
    print('WARNING: Running this will delete all of the SleepJournal entries you have ever inputted.')
    answer = input('Do you wish to proceed? Type yes to delte all: ').strip()

    if answer.lower() != "yes":
        print("No SleepJournal Measurements were removed")
        return

    client = connect_influx()

    if not measurement_exists(client, MEASUREMENT):
        print("No SleepJournal Measurements were removed, as none were found in the Influx Database.")
        return

    # DROP MEASUREMENT removes all points/series for that measurement.
    client.query(f'DROP MEASUREMENT "{MEASUREMENT}"')

    print("SleepJournal Measurements were removed")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nNo SleepJournal Measurements were removed")
        sys.exit(1)

