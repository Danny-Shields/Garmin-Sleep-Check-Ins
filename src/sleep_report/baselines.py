
"""
baselines.py

What this file does:
  - Computes baseline mean/std for each metric from a list of SleepSummary points.
  - Returns a dict suitable to be passed into image_summary.draw_metric_cards().

Notes:
  - Population std-dev (divide by N) for stability.
  - If a metric has < min_count points or zero std, std is set to 0.0.

This file does NOT:
  - Query databases
  - Render images
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple


def _mean_std(values: Sequence[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    mu = sum(values) / len(values)
    var = sum((v - mu) ** 2 for v in values) / len(values)  # population
    return mu, math.sqrt(var)


def compute_metric_baselines(
    summaries: Sequence[Mapping[str, Any]],
    metrics: Iterable[str],
    *,
    min_count: int = 5,
    exclude_summary: Mapping[str, Any] | None = None,
) -> Dict[str, Tuple[float, float]]:
    """
    Build {metric: (mean, std)} from many SleepSummary dicts.

    exclude_summary:
      - if provided, we'll skip that exact record (by its 'time' value) so the
        current night doesn't affect its own baseline.
    """
    exclude_time = None
    if exclude_summary is not None:
        exclude_time = exclude_summary.get("time")

    out: Dict[str, Tuple[float, float]] = {}
    for metric in metrics:
        vals: List[float] = []
        for s in summaries:
            if exclude_time is not None and s.get("time") == exclude_time:
                continue
            v = s.get(metric)
            if v is None:
                continue
            try:
                vals.append(float(v))
            except Exception:
                continue

        if len(vals) < min_count:
            out[metric] = (0.0, 0.0)
            continue

        mu, sd = _mean_std(vals)
        if sd < 1e-12:
            sd = 0.0
        out[metric] = (mu, sd)

    return out
