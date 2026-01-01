
"""
selectors.py

What this file does:
  - Chooses the "current" SleepSummary record (usually the most recent)
  - Determines a reasonable intraday time window to fetch for the current night
  - Matches the intraday StageSession to the selected SleepSummary

This file does NOT:
  - Query databases
  - Render images
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .time_utils import parse_time_utc
from .stages import StageSession


def select_current(summary_points: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Select the most recent SleepSummary record by 'time'."""
    dated: List[Tuple[datetime, Dict[str, Any]]] = []
    for p in summary_points:
        t = p.get("time")
        if t is None:
            continue
        try:
            dated.append((parse_time_utc(t), p))
        except Exception:
            continue
    if not dated:
        return None
    dated.sort(key=lambda x: x[0])
    return dict(dated[-1][1])


def compute_intraday_fetch_window(
    current_summary: Mapping[str, Any],
    *,
    extra_before_hours: float = 4.0,
    extra_after_hours: float = 1.5,
    min_window_hours: float = 14.0,
    max_window_hours: float = 20.0,
) -> Tuple[datetime, datetime]:
    """
    Determine a safe window to fetch SleepIntraday for the current night.

    We only have:
      - 'time' (usually around the end of sleep)
      - durations (sleepTimeSeconds, awakeSleepSeconds)

    Strategy:
      - estimate sleep duration from available fields
      - build a window ending a bit after 'time' and starting far enough before
    """
    end_utc = parse_time_utc(current_summary.get("time"))
    sleep_s = float(current_summary.get("sleepTimeSeconds") or 0.0)
    awake_s = float(current_summary.get("awakeSleepSeconds") or 0.0)
    est_hours = (sleep_s + awake_s) / 3600.0
    window_hours = max(min_window_hours, min(max_window_hours, est_hours + extra_before_hours + extra_after_hours))

    start_utc = end_utc - timedelta(hours=window_hours)
    end_utc = end_utc + timedelta(hours=extra_after_hours)
    return start_utc, end_utc


def match_session_to_summary(
    current_summary: Mapping[str, Any],
    sessions: List[StageSession],
) -> StageSession:
    """Pick the session whose end time is closest to the summary time."""
    if not sessions:
        raise ValueError("No StageSession available to match.")
    target = parse_time_utc(current_summary.get("time"))
    return min(sessions, key=lambda s: abs((s.end_utc - target).total_seconds()))
