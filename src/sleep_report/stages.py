
"""
stages.py

What this file does:
  - Converts raw SleepIntraday points into contiguous "sleep sessions"
    (one session per sleep event).
  - Each session can then be matched to a SleepSummary record.

Key idea:
  - Intraday data can contain gaps (daytime) and multiple sleep events (naps).
  - We split sessions whenever there's a long time gap (default 6 hours).

This file does NOT:
  - Query databases
  - Render images
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .time_utils import parse_time_utc


@dataclass
class StageSession:
    points: List[Dict[str, Any]]
    start_utc: datetime
    end_utc: datetime
    total_stage_seconds: float


def build_stage_sessions(
    intraday_rows: Sequence[Mapping[str, Any]],
    *,
    time_key: str = "time",
    stage_key: str = "SleepStageLevel",
    dur_key: str = "SleepStageSeconds",
    gap_hours: float = 6.0,
) -> List[StageSession]:
    rows = [r for r in intraday_rows if r.get(stage_key) is not None and r.get(time_key) is not None]
    rows.sort(key=lambda r: parse_time_utc(r[time_key]))

    sessions: List[List[Dict[str, Any]]] = []
    cur: List[Dict[str, Any]] = []
    prev_t: Optional[datetime] = None
    gap_s = gap_hours * 3600

    for r in rows:
        t = parse_time_utc(r[time_key])
        if prev_t is not None and (t - prev_t).total_seconds() > gap_s and cur:
            sessions.append(cur)
            cur = []
        cur.append(dict(r))
        prev_t = t
    if cur:
        sessions.append(cur)

    out: List[StageSession] = []
    for sess in sessions:
        start = parse_time_utc(sess[0][time_key])

        total = 0.0
        for rr in sess:
            d = rr.get(dur_key)
            if d is None:
                continue
            try:
                total += float(d)
            except Exception:
                pass

        last = sess[-1]
        last_t = parse_time_utc(last[time_key])
        try:
            last_d_s = float(last.get(dur_key) or 240.0)
        except Exception:
            last_d_s = 240.0
        end = last_t + timedelta(seconds=last_d_s)

        out.append(StageSession(points=sess, start_utc=start, end_utc=end, total_stage_seconds=total))
    return out
