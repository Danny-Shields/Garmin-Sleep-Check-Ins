#!/usr/bin/env python3
"""
demo.py (sleep summary comparison)

Reads sample sleep data from:
  data/Demo_SleepSummary.jsonl

Finds the most recent sleep record and compares selected metrics against the
previous 7 days (calendar time window, excluding the most recent record).

Outputs one plain-English comment per metric.

Rules requested:
- avgSleepStress < better
- awakeCount < better
- awakeSleepSeconds < better
- deepSleepSeconds > better
- remSleepSeconds > better
- restingHeartRate < better
- restlessMomentsCount < better
- sleepScore > better
- sleepTimeSeconds > better

Formatting:
- Current time metrics (*Seconds) rounded to the nearest minute
- Current non-time metrics rounded to the nearest whole number
- Averages keep the prior formatting (time shown with seconds; non-time to 0.1)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

# -----------------------------
# Config
# -----------------------------
DEFAULT_JSONL = Path("data") / "Demo_SleepSummary.jsonl"

# (metric, higher_is_better)
METRICS: List[Tuple[str, bool]] = [
    ("avgSleepStress", False),
    ("awakeCount", False),
    ("awakeSleepSeconds", False),
    ("deepSleepSeconds", True),
    ("remSleepSeconds", True),
    ("restingHeartRate", False),
    ("restlessMomentsCount", False),
    ("sleepScore", True),
    ("sleepTimeSeconds", True),
]

SECONDS_METRICS = {
    "awakeSleepSeconds",
    "deepSleepSeconds",
    "remSleepSeconds",
    "sleepTimeSeconds",
}

LABELS = {
    "avgSleepStress": "sleep stress",
    "awakeCount": "awake count",
    "awakeSleepSeconds": "awake time",
    "deepSleepSeconds": "deep sleep",
    "remSleepSeconds": "REM sleep",
    "restingHeartRate": "resting heart rate",
    "restlessMomentsCount": "restless moments",
    "sleepScore": "sleep score",
    "sleepTimeSeconds": "total sleep time",
}


# -----------------------------
# Helpers
# -----------------------------
def parse_time_utc(t: str) -> datetime:
    dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iter_jsonl(path: Path) -> Iterable[Dict]:
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                raise RuntimeError(f"Invalid JSON on line {line_no} in {path}") from e


def safe_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def round_1(x: float) -> float:
    return round(x + 1e-12, 1)


def sec_to_min_sec(seconds: float) -> str:
    s = int(round(seconds))
    m, r = divmod(s, 60)
    return f"{m}m{r}sec"


def sec_to_hr_min(seconds: float) -> str:
    """Format seconds as HhMm (hours and minutes)."""
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m = rem // 60
    return f"{h}h{m}m"


def sec_to_min_sec_round_minute(seconds: float) -> str:
    """Format seconds as XmYsec, rounding to the nearest minute."""
    s = int(round(seconds / 60.0) * 60)
    m, r = divmod(s, 60)
    return f"{m}m{r}sec"


def sec_to_hr_min_round_minute(seconds: float) -> str:
    """Format seconds as HhMm, rounding to the nearest minute."""
    s = int(round(seconds / 60.0) * 60)
    h, rem = divmod(s, 3600)
    m = rem // 60
    return f"{h}h{m}m"


def fmt_current_value(metric: str, value: float) -> str:
    """Current values: time -> nearest minute; others -> nearest whole number."""
    if metric == "sleepTimeSeconds":
        return sec_to_hr_min_round_minute(value)
    if metric in SECONDS_METRICS:
        return sec_to_min_sec_round_minute(value)
    return str(int(round(value)))


def fmt_avg_value(metric: str, value: float) -> str:
    """Averages: keep existing formatting (time to seconds; others to 0.1)."""
    if metric == "sleepTimeSeconds":
        return sec_to_hr_min(value)
    if metric in SECONDS_METRICS:
        return sec_to_min_sec(value)
    return f"{round_1(value):.1f}"


def compare(value: float, avg: float, higher_is_better: bool) -> str:
    if abs(value - avg) < 1e-9:
        return "about the same as"
    if higher_is_better:
        return "better than" if value > avg else "worse than"
    return "better than" if value < avg else "worse than"


def metric_label(metric: str) -> str:
    return LABELS.get(metric, metric)


@dataclass(frozen=True)
class SleepRecord:
    t_utc: datetime
    data: Dict


def load_records(path: Path) -> List[SleepRecord]:
    records: List[SleepRecord] = []
    for obj in iter_jsonl(path):
        t = obj.get("time")
        if not isinstance(t, str):
            continue
        records.append(SleepRecord(t_utc=parse_time_utc(t), data=obj))
    records.sort(key=lambda r: r.t_utc)
    return records


def week_window(records: List[SleepRecord], most_recent_time: datetime) -> List[SleepRecord]:
    start = most_recent_time - timedelta(days=7)
    return [r for r in records if start <= r.t_utc < most_recent_time]


def avg_metric(records: List[SleepRecord], metric: str) -> Optional[float]:
    vals: List[float] = []
    for r in records:
        v = safe_float(r.data.get(metric))
        if v is not None:
            vals.append(v)
    if not vals:
        return None
    return sum(vals) / len(vals)


# -----------------------------
# Main
# -----------------------------
def main() -> None:
    # You can override the path with: DEMO_SLEEP_SUMMARY_JSONL=/app/data/Demo_SleepSummary.jsonl
    data_path = Path(os.getenv("DEMO_SLEEP_SUMMARY_JSONL", str(DEFAULT_JSONL)))

    if not data_path.exists():
        raise SystemExit(
            f"Could not find demo file: {data_path}\n"
            f"Expected default: {DEFAULT_JSONL}\n"
            f"Tip: put Demo_SleepSummary.jsonl in the repo's data/ folder."
        )

    records = load_records(data_path)
    if not records:
        raise SystemExit(f"No valid records found in {data_path}")

    most_recent = records[-1]
    prior_week = week_window(records, most_recent.t_utc)

    for metric, higher_is_better in METRICS:
        v = safe_float(most_recent.data.get(metric))
        if v is None:
            print(f"Your {metric_label(metric)} is missing in the most recent record.")
            continue

        avg = avg_metric(prior_week, metric)
        if avg is None:
            print(f"Your {metric_label(metric)} was {fmt_current_value(metric, v)}. (Not enough prior-week data to compare.)")
            continue

        verdict = compare(v, avg, higher_is_better)
        print(
            f"Your {metric_label(metric)} was {fmt_current_value(metric, v)}; "
            f"this is {verdict} the previous week average of {fmt_avg_value(metric, avg)}."
        )


if __name__ == "__main__":
    main()
