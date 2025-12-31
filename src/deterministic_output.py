#!/usr/bin/env python3
"""
deterministic_output.py

Core, deterministic text-generation logic for the Garmin Sleep Check-Ins project.

Public API:
    build_sleep_summary_text(current_sleep: dict, prior_week_sleeps: list[dict]) -> str

Inputs:
- current_sleep: a dict representing the most recent SleepSummary record
- prior_week_sleeps: list of dicts representing SleepSummary records from the prior 7 days
  (excluding current_sleep)

Output:
- a single string containing one line per metric.

Formatting rules:
- Current time metrics (*Seconds): rounded to the nearest minute
- Current non-time metrics: rounded to the nearest whole number
- Averages: keep prior formatting (time shows seconds; non-time to 0.1)
- Total sleep time current: hours+minutes (HhMm), rounded to nearest minute
- Total sleep time average: hours+minutes (HhMm)
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

#list to keep track of if more is better or worse for the metric
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
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m = rem // 60
    return f"{h}h{m}m"


def sec_to_min_sec_round_minute(seconds: float) -> str:
    s = int(round(seconds / 60.0) * 60)
    m, r = divmod(s, 60)
    return f"{m}m"
    #return f"{m}m{r}sec"


def sec_to_hr_min_round_minute(seconds: float) -> str:
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
    """Averages: time -> seconds format; non-time -> 0.1. TST average -> HhMm."""
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


def avg_metric(records: List[Dict], metric: str) -> Optional[float]:
    vals: List[float] = []
    for r in records:
        v = safe_float(r.get(metric))
        if v is not None:
            vals.append(v)
    if not vals:
        return None
    return sum(vals) / len(vals)

#the main function that is called for this project
def build_sleep_summary_text(current_sleep: Dict, prior_week_sleeps: List[Dict]) -> str:
    """Build the multi-line text summary comparing current sleep to prior-week average."""
    lines: List[str] = []

    for metric, higher_is_better in METRICS:
        v = safe_float(current_sleep.get(metric))
        if v is None:
            lines.append(f"Your {metric_label(metric)} is missing in the most recent record.")
            continue

        avg = avg_metric(prior_week_sleeps, metric)
        if avg is None:
            lines.append(
                f"Your {metric_label(metric)} was {fmt_current_value(metric, v)}. "
                f"(Not enough prior-week data to compare.)"
            )
            continue

        verdict = compare(v, avg, higher_is_better)
        lines.append(
            f"Your {metric_label(metric)} was {fmt_current_value(metric, v)}; "
            f"this is {verdict} the previous week average of {fmt_avg_value(metric, avg)}."
        )
        
    #including a question to ellicit a response
    lines.append(
        f"Any thoughts on why your sleep was like this?"
    )

    return "\n".join(lines)
