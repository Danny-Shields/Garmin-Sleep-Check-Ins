
"""
time_utils.py

What this file does:
  - Single place for parsing Influx time strings into tz-aware UTC datetimes.
  - Keeps datetime handling consistent across fetch/select/baseline code.

This file does NOT:
  - Query databases
  - Render images
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def parse_time_utc(t: Any) -> datetime:
    """Parse Influx 'time' fields into a tz-aware UTC datetime."""
    if isinstance(t, datetime):
        return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t.astimezone(timezone.utc)

    if isinstance(t, (int, float)):
        # epoch seconds
        return datetime.fromtimestamp(float(t), tz=timezone.utc)

    if isinstance(t, str):
        s = t.strip()
        # Influx commonly returns RFC3339 like '...Z'
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)

    raise TypeError(f"Unsupported time type: {type(t)}")
