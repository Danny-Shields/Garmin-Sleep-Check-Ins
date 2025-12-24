#!/usr/bin/env python3
"""
demo.py (refactored)

Loads sample sleep summary data from:
  data/Demo_SleepSummary.jsonl

Then:
- picks the most recent record
- selects the prior 7 days of records (excluding the most recent)
- passes both into determenistic_output.build_sleep_summary_text()
- prints the returned text to stdout
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List

from deterministic_output import build_sleep_summary_text


DEFAULT_JSONL = Path("data") / "Demo_SleepSummary.jsonl"


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


def prior_week_records(records: List[SleepRecord], most_recent_time: datetime) -> List[SleepRecord]:
    start = most_recent_time - timedelta(days=7)
    return [r for r in records if start <= r.t_utc < most_recent_time]


def main() -> None:
    # uncomment below to override path to sample date if desired:
    #   DEMO_SLEEP_SUMMARY_JSONL=/app/data/Demo_SleepSummary.jsonl python demo.py
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

    current = records[-1]
    prior_week = prior_week_records(records, current.t_utc)

    text = build_sleep_summary_text(
        current_sleep=current.data,
        prior_week_sleeps=[r.data for r in prior_week],
    )
    print(text)


if __name__ == "__main__":
    main()
