#!/usr/bin/env python3
"""
sleep_data_export.py

Exports sleep data from InfluxDB v1 (InfluxQL) into:
- SleepSummary.jsonl + SleepSummary.csv
- SleepIntraday.jsonl + per-metric CSVs:
    SleepIntraday_heartRate.csv
    SleepIntraday_respirationValue.csv
    SleepIntraday_SleepMovementActivityLevel.csv
    SleepIntraday_SleepStageLevel.csv

CSV rules:
- Leftmost column is local time: time["<TZ>"]
- Rightmost column is time_utc
- Local time cells include the timezone name, e.g. "...-05:00 [America/Toronto]"
- Device/Database columns are removed from CSV outputs (JSONL stays lossless)

Timezone resolution order:
1) LOCAL_TIMEZONE env var (IANA name, e.g. America/Toronto)
2) TZ env var (IANA name)
3) /etc/timezone (works well when mounted from host)
4) UTC fallback
"""

import os
import json
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from influxdb import InfluxDBClient

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


# --------------------
# Config
# --------------------
INFLUXDB_HOST = os.getenv("INFLUXDB_HOST", "localhost")
INFLUXDB_PORT = int(os.getenv("INFLUXDB_PORT", "8086"))
INFLUXDB_DATABASE = os.getenv("INFLUXDB_DATABASE", "GarminStats")
INFLUXDB_USERNAME = os.getenv("INFLUXDB_USERNAME", "") or None
INFLUXDB_PASSWORD = os.getenv("INFLUXDB_PASSWORD", "") or None
INFLUXDB_SSL = os.getenv("INFLUXDB_SSL", "false").lower() in ("1", "true", "yes", "y")

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "5000"))
OUT_DIR = Path(os.getenv("OUT_DIR", "exports"))
OUT_DIR.mkdir(parents=True, exist_ok=True)

LOCAL_TIMEZONE_ENV = (os.getenv("LOCAL_TIMEZONE", "") or "").strip()
TZ_ENV = (os.getenv("TZ", "") or "").strip()

INTRADAY_METRICS = [
    "heartRate",
    "respirationValue",
    "SleepMovementActivityLevel",
    "SleepStageLevel",
]

METRIC_COLUMN_LABELS = {
    "heartRate": "HR (BPM)",
    "respirationValue": "Respiration (breaths/min)",
    "SleepMovementActivityLevel": "Movement (level)",
    "SleepStageLevel": "Sleep Stage (code)",
}

# NOTE (VERIFY): Mapping provided by user; must be verified against Garmin/garmin-grafana semantics.
# Stage 0: Deep Sleep (N3)
# Stage 1: Light Sleep (N1, N2)
# Stage 2: REM Sleep
# Stage 3: Awake
SLEEP_STAGE_LABELS: Dict[int, str] = {
    0: "Deep Sleep (N3)",
    1: "Light Sleep (N1, N2)",
    2: "REM Sleep",
    3: "Awake",
}

EXCLUDE_CSV_COLUMNS = {
    "Device",
    "Database_Name",
    "database_name",
    "database",
    "device",
    "Database",
}


# --------------------
# Helpers
# --------------------
def parse_influx_time(time_str: str) -> datetime:
    dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def format_utc(dt_utc: datetime) -> str:
    return dt_utc.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def format_local(dt_local: datetime, tz_name: str) -> str:
    return f"{dt_local.isoformat()} [{tz_name}]"


def local_time_header(tz_name: str) -> str:
    return f'time["{tz_name}"]'


def metric_label(metric: str) -> str:
    return METRIC_COLUMN_LABELS.get(metric, metric)


def should_exclude_csv_col(col: str) -> bool:
    return col in EXCLUDE_CSV_COLUMNS


def read_etc_timezone() -> Optional[str]:
    p = Path("/etc/timezone")
    if not p.exists():
        return None
    try:
        tz = p.read_text(encoding="utf-8").strip()
        return tz or None
    except Exception:
        return None


def resolve_local_timezone() -> Tuple[str, timezone]:
    tz_name = LOCAL_TIMEZONE_ENV or TZ_ENV or read_etc_timezone() or "UTC"

    if tz_name.upper() == "UTC" or ZoneInfo is None:
        return "UTC", timezone.utc

    try:
        return tz_name, ZoneInfo(tz_name)  # type: ignore[misc]
    except Exception:
        return "UTC", timezone.utc


# --------------------
# Influx utilities
# --------------------
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


def list_measurements(client: InfluxDBClient) -> List[str]:
    result = client.query("SHOW MEASUREMENTS")
    return [p["name"] for p in result.get_points()]


def stream_points(client: InfluxDBClient, measurement: str, chunk_size: int) -> Iterable[Dict]:
    last_time = "1970-01-01T00:00:00Z"
    while True:
        q = (
            f'SELECT * FROM "{measurement}" '
            f"WHERE time > '{last_time}' "
            f"ORDER BY time ASC "
            f"LIMIT {chunk_size}"
        )
        result = client.query(q)
        points = list(result.get_points())
        if not points:
            break
        for p in points:
            yield p
        last_time = points[-1]["time"]
        if len(points) < chunk_size:
            break


# --------------------
# Exports
# --------------------
def export_sleep_summary(client: InfluxDBClient, tz_name: str, tzinfo_obj: timezone) -> None:
    measurement = "SleepSummary"
    jsonl_path = OUT_DIR / f"{measurement}.jsonl"
    csv_path = OUT_DIR / f"{measurement}.csv"
    local_header = local_time_header(tz_name)

    with jsonl_path.open("w", encoding="utf-8") as jsonl_file:
        points_iter = stream_points(client, measurement, CHUNK_SIZE)
        try:
            first = next(points_iter)
        except StopIteration:
            print("No SleepSummary points found.")
            return

        other_cols = [
            k for k in first.keys()
            if k != "time" and not should_exclude_csv_col(k)
        ]

        fieldnames = [local_header] + other_cols + ["time_utc"]

        with csv_path.open("w", encoding="utf-8", newline="") as csv_file:
            w = csv.DictWriter(csv_file, fieldnames=fieldnames)
            w.writeheader()

            def write_point(p: Dict) -> None:
                jsonl_file.write(json.dumps(p, ensure_ascii=False) + "\n")
                dt_utc = parse_influx_time(p["time"])
                dt_local = dt_utc.astimezone(tzinfo_obj)

                row: Dict[str, object] = {local_header: format_local(dt_local, tz_name)}
                for k, v in p.items():
                    if k == "time" or should_exclude_csv_col(k):
                        continue
                    row[k] = v
                row["time_utc"] = format_utc(dt_utc)
                w.writerow(row)

            write_point(first)
            for p in points_iter:
                write_point(p)

    print(f"  Wrote {measurement}.jsonl and {measurement}.csv")


def export_sleep_intraday(client: InfluxDBClient, tz_name: str, tzinfo_obj: timezone) -> None:
    measurement = "SleepIntraday"
    jsonl_path = OUT_DIR / f"{measurement}.jsonl"
    local_header = local_time_header(tz_name)

    files: Dict[str, object] = {}
    writers: Dict[str, csv.DictWriter] = {}

    # Create per-metric CSVs
    metric_paths: Dict[str, Path] = {}
    for metric in INTRADAY_METRICS:
        metric_path = OUT_DIR / f"{measurement}_{metric}.csv"
        f = metric_path.open("w", encoding="utf-8", newline="")
        mcol = metric_label(metric)

        fieldnames = [local_header, mcol]
        if metric == "SleepStageLevel":
            fieldnames.append("Sleep Stage (label)")
        fieldnames.append("time_utc")

        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()

        files[metric] = f
        writers[metric] = w
        metric_paths[metric] = metric_path

    points_written = 0
    metric_rows = {m: 0 for m in INTRADAY_METRICS}

    with jsonl_path.open("w", encoding="utf-8") as jsonl_file:
        for p in stream_points(client, measurement, CHUNK_SIZE):
            points_written += 1
            jsonl_file.write(json.dumps(p, ensure_ascii=False) + "\n")

            dt_utc = parse_influx_time(p["time"])
            dt_local = dt_utc.astimezone(tzinfo_obj)

            for metric in INTRADAY_METRICS:
                value = p.get(metric)
                if value is None:
                    continue

                mcol = metric_label(metric)
                row: Dict[str, object] = {
                    local_header: format_local(dt_local, tz_name),
                    mcol: value,
                }

                if metric == "SleepStageLevel":
                    try:
                        code = int(float(value))
                        row["Sleep Stage (label)"] = SLEEP_STAGE_LABELS.get(code, "UNKNOWN")
                    except Exception:
                        row["Sleep Stage (label)"] = "UNKNOWN"

                row["time_utc"] = format_utc(dt_utc)
                writers[metric].writerow(row)
                metric_rows[metric] += 1

    for f in files.values():
        f.close()

    print(f"  Wrote {measurement}.jsonl ({points_written} points)")
    for metric in INTRADAY_METRICS:
        print(f"  Wrote {metric_paths[metric].name} ({metric_rows[metric]} rows)")


def main() -> None:
    client = connect_influx()
    tz_name, tzinfo_obj = resolve_local_timezone()

    measurements = list_measurements(client)

    if "SleepSummary" in measurements:
        export_sleep_summary(client, tz_name, tzinfo_obj)

    if "SleepIntraday" in measurements:
        export_sleep_intraday(client, tz_name, tzinfo_obj)

    print("Done, check Garmin-Sleep-Check-Ins/exports for your files")


if __name__ == "__main__":
    main()
