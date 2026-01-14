#!/usr/bin/env python3
"""
demo.py (standalone_functions)

Purpose:
- Demo the project WITHOUT InfluxDB and WITHOUT Telegram.
- Uses sample JSONL files in the repo's data/ folder:
    data/Demo_SleepSummary.jsonl
    data/Demo_SleepIntraday.jsonl

It will:
1) Pick the most recent sleep summary record.
2) Compare it to the previous 7 days and print a text summary.
3) Generate an image summary PNG from the matching intraday stage data.
4) Attempt to open the image (best-effort); always prints the output path.

Run (Docker):
  docker compose -f compose.addon.yml run --rm --build sleep-checkins \
    python /app/src/standalone_functions/demo.py

Run (host python):
  python3 src/standalone_functions/demo.py
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore


# -----------------------
# Path / import helpers
# -----------------------
THIS_FILE = Path(__file__).resolve()
SRC_DIR = THIS_FILE.parents[1]               # .../src
REPO_ROOT = SRC_DIR.parent                   # repo root

# Make parent src/ importable (so we can import fixed_message, deterministic_output, image_summary, etc.)
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

#import the method to call the image summary
from fixed_image_summary import run_once

# -----------------------
# Time + JSONL helpers
# -----------------------
def parse_time_utc(s: str) -> datetime:
    # Influx-like timestamps often end with "Z"
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def resolve_tz() -> str:
    # Prefer LOCAL_TIMEZONE, then TZ, else default
    tz = (os.getenv("LOCAL_TIMEZONE", "") or "").strip() or (os.getenv("TZ", "") or "").strip()
    return tz or "America/Toronto"


# -----------------------
# Text summary (reuse your project logic if present)
# -----------------------
def build_text_summary(current_sleep: Dict[str, Any], prior_week: List[Dict[str, Any]]) -> str:
    """
    Prefer deterministic_output.build_sleep_summary_text if available.
    Fallback to a minimal internal formatter if it's missing.
    """
    try:
        from deterministic_output import build_sleep_summary_text  # type: ignore

        return build_sleep_summary_text(
            current_sleep=current_sleep,
            prior_week_sleeps=prior_week,
        )
    except Exception as e:
        # Minimal fallback (keeps demo usable even if imports move)
        def safe_float(x: Any) -> Optional[float]:
            try:
                return float(x)
            except Exception:
                return None

        def avg_metric(rows: List[Dict[str, Any]], key: str) -> Optional[float]:
            vals = [safe_float(r.get(key)) for r in rows]
            vals = [v for v in vals if v is not None]
            return sum(vals) / len(vals) if vals else None

        def fmt_seconds_to_hm(sec: float) -> str:
            m = int(round(sec / 60.0))
            h = m // 60
            mm = m % 60
            return f"{h}h{mm:02d}m" if h else f"{mm}m"

        # metric, higher_is_better
        METRICS = [
            ("avgSleepStress", False, "sleep stress", "num"),
            ("awakeCount", False, "awake count", "num"),
            ("awakeSleepSeconds", False, "awake time", "sec"),
            ("deepSleepSeconds", True, "deep sleep", "sec"),
            ("remSleepSeconds", True, "REM sleep", "sec"),
            ("restingHeartRate", False, "resting HR", "num"),
            ("restlessMomentsCount", False, "restless moments", "num"),
            ("sleepScore", True, "sleep score", "num"),
            ("sleepTimeSeconds", True, "total sleep", "sec"),
        ]

        lines: List[str] = [f"(Fallback summary; deterministic_output import failed: {e})"]
        for k, hib, label, kind in METRICS:
            v = safe_float(current_sleep.get(k))
            if v is None:
                lines.append(f"{label}: missing")
                continue
            avg = avg_metric(prior_week, k)
            if avg is None:
                cur = fmt_seconds_to_hm(v) if kind == "sec" else f"{v:.1f}"
                lines.append(f"{label}: {cur} (no prior-week avg)")
                continue

            better = (v > avg) if hib else (v < avg)
            verdict = "better" if better else "worse"
            cur = fmt_seconds_to_hm(v) if kind == "sec" else f"{v:.1f}"
            av  = fmt_seconds_to_hm(avg) if kind == "sec" else f"{avg:.1f}"
            lines.append(f"{label}: {cur} ({verdict} vs avg {av})")

        lines.append("Any thoughts on why your sleep was like this?")
        return "\n".join(lines)


# -----------------------
# Image summary from sample JSONL
# -----------------------
@dataclass
class SimpleStageSession:
    points: List[Dict[str, Any]]


def compute_baselines(summary_rows: List[Dict[str, Any]]) -> Dict[str, Tuple[float, float]]:
    """
    Returns {metric: (mean, std)} for the metrics used by image_summary.draw_metric_cards.
    """
    # Keep consistent with image_summary METRICS list
    metrics = [
        "avgSleepStress",
        "awakeCount",
        "awakeSleepSeconds",
        "deepSleepSeconds",
        "remSleepSeconds",
        "restingHeartRate",
        "restlessMomentsCount",
        "sleepScore",
        "sleepTimeSeconds",
    ]

    def safe_float(x: Any) -> Optional[float]:
        try:
            return float(x)
        except Exception:
            return None

    out: Dict[str, Tuple[float, float]] = {}
    for m in metrics:
        vals = [safe_float(r.get(m)) for r in summary_rows]
        vals = [v for v in vals if v is not None]
        if len(vals) < 2:
            mean = vals[0] if vals else 0.0
            out[m] = (float(mean), 0.0)
            continue
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
        out[m] = (float(mean), float(var ** 0.5))
    return out


def pick_current_and_prior_week(records: List[Dict[str, Any]], tz_name: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Choose most recent by 'time' (UTC), then prior-week by local date window.
    """
    tz = ZoneInfo(tz_name) if ZoneInfo else None
    rows = []
    for r in records:
        t = r.get("time")
        if isinstance(t, str):
            rows.append((parse_time_utc(t), r))
    rows.sort(key=lambda x: x[0])
    if not rows:
        raise SystemExit("No valid records found in Demo_SleepSummary.jsonl")

    current_t, current = rows[-1]
    current_local_date = current_t.astimezone(tz).date() if tz else current_t.date()

    # prior 7 days excluding current local day
    start_date = current_local_date - timedelta(days=7)
    prior_week: List[Dict[str, Any]] = []
    for t, r in rows[:-1]:
        d = t.astimezone(tz).date() if tz else t.date()
        if start_date <= d < current_local_date:
            prior_week.append(r)

    return current, prior_week

def select_intraday_window(
    intraday_rows: List[Dict[str, Any]],
    *,
    end_utc: datetime,
    total_session_seconds: float,
    require_key: str | None = None,
) -> List[Dict[str, Any]]:
    """
    Approximate sleep window:
      start = end - (sleepTimeSeconds + awakeSleepSeconds)
    Then filter intraday points in [start-10m, end+10m].

    If require_key is set, only include rows where row[require_key] is not None.
    """
    start_utc = end_utc - timedelta(seconds=total_session_seconds)
    lo = start_utc - timedelta(minutes=10)
    hi = end_utc + timedelta(minutes=10)

    pts: List[Dict[str, Any]] = []
    for r in intraday_rows:
        t = r.get("time")
        if not isinstance(t, str):
            continue
        dt = parse_time_utc(t)
        if not (lo <= dt <= hi):
            continue

        if require_key is not None:
            if r.get(require_key) is None:
                continue

        pts.append(r)

    pts.sort(key=lambda r: parse_time_utc(r["time"]))
    return pts
   

def try_open_image(path: Path) -> None:
    """
    Best-effort open. In Docker/headless this may do nothing; always prints the path.
    """
    print(f"Image written: {path}")

    # If running in docker or headless, opening likely won't work
    in_docker = Path("/.dockerenv").exists()
    if in_docker and not os.getenv("DISPLAY"):
        print("Not opening image (Docker/headless). Open it from the host filesystem.")
        return

    try:
        system = platform.system().lower()
        if system.startswith("linux"):
            subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif system == "darwin":
            subprocess.Popen(["open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif system.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            print("Auto-open not supported on this OS; open manually:", path)
    except Exception as e:
        print("Could not auto-open image:", e)
        print("Open manually:", path)


def main() -> None:
    tz_name = resolve_tz()

    data_dir = REPO_ROOT / "data"
    summary_path = data_dir / "Demo_SleepSummary.jsonl"
    intraday_path = data_dir / "Demo_SleepIntraday.jsonl"

    if not summary_path.exists():
        raise SystemExit(f"Missing sample file: {summary_path}")
    if not intraday_path.exists():
        raise SystemExit(f"Missing sample file: {intraday_path}")

    summary_records = list(iter_jsonl(summary_path))
    intraday_records = list(iter_jsonl(intraday_path))

    # 1) Pick current + prior week
    current, prior_week = pick_current_and_prior_week(summary_records, tz_name)

    # 2) Print text summary
    print("\n=== TEXT SUMMARY (sample data) ===\n")
    text = build_text_summary(current_sleep=current, prior_week=prior_week)
    print(text)

    # Determine end time + session duration
    end_utc = parse_time_utc(str(current["time"]))
    sleep_sec = float(current.get("sleepTimeSeconds") or 0)
    awake_sec = float(current.get("awakeSleepSeconds") or 0)
    total_session_seconds = max(0.0, sleep_sec + awake_sec)

    stage_points = select_intraday_window(
        intraday_records,
        end_utc=end_utc,
        total_session_seconds=total_session_seconds,
        require_key="SleepStageLevel",   #avoids null values
    )
    if not stage_points:
        raise SystemExit("Could not find any intraday rows with SleepStageLevel for the most recent sleep window in Demo_SleepIntraday.jsonl")

    session = SimpleStageSession(points=stage_points)

    # Baselines from prior week (fallback to all history if needed)
    baseline_source = prior_week if len(prior_week) >= 2 else summary_records
    baselines = compute_baselines(baseline_source)

    out_dir = REPO_ROOT / "exports" / "summary_screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)

    day_key = end_utc.astimezone(ZoneInfo(tz_name)).date().isoformat() if ZoneInfo else end_utc.date().isoformat()

    # 3) Build image summary
    print("\n=== IMAGE SUMMARY (sample data) ===\n")

    # Run the same pipeline used by the scheduler,
    # but disable telegram and force a day from sample data.
    try:
        run_once(
            summary_days=30,
            show_mean=True,
            show_sigma=True,
            send_telegram=False,   # critical: demo only
            day=day_key,           # derived from Demo_SleepSummary.jsonl
            display_tz=tz_name,
        )
        print("\nThe program succesfully saved " + str(day_key) + " sleep summary in exports folder")
    except Exception as e:
        raise SystemExit(f"Could not import run_once method from fixed_image_summary in src/: {e}")

    \


if __name__ == "__main__":
    main()

