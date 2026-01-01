
#!/usr/bin/env python3
"""
image_summary.py

What this file does:
  - PURE rendering. Given:
      1) a single SleepSummary record for the night
      2) ONE intraday StageSession for that same night
      3) pre-computed baseline mean/std for each metric
    it creates a nice PNG "sleep report" graphic.

What this file does NOT do:
  - Query InfluxDB
  - Decide which night is current
  - Compute baseline mean/std (that happens upstream)

Why this is useful:
  - You can change your data plumbing (Influx, JSONL, API, etc.) without touching plotting.
  - You can iterate on visuals without risking database logic.
"""

from __future__ import annotations

import math
from datetime import timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence, Tuple, Dict

import matplotlib
matplotlib.use("Agg")  # headless-safe

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgba
from matplotlib.patches import FancyBboxPatch, Patch, Rectangle
from zoneinfo import ZoneInfo

from sleep_report.stages import StageSession
from sleep_report.time_utils import parse_time_utc


# (metric, higher_is_better)
METRICS = [
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

# SleepStageLevel mapping (commonly: 0=Deep, 1=Light, 2=REM, 3=Awake)
STAGE_MAP = {
    0: {"name": "Deep", "level": 1, "color": "#0B3D91"},
    1: {"name": "Light", "level": 2, "color": "#6FA8FF"},
    2: {"name": "REM", "level": 3, "color": "#A352CC"},
    3: {"name": "Awake", "level": 4, "color": "#FF6B6B"},
}

BG_COLOR = "#0B1020"
STAT_TEXT_COLOR = "#6FA8FF"

# --- Balanced diverging palette (bad → neutral → good), binned by sigma ---
NEUTRAL_HEX = "#a1a38c"
SIGMA_CAP = 2.5
GAMMA = 1.6  # >1 compresses extremes so dark ends show mainly at very high σ

NEG_SIGMA_HEXES = [
    NEUTRAL_HEX,
    "#ac9886",
    "#b88c80",
    "#cf7673",
    "#bf4945",
    "#af1c17",
]

POS_SIGMA_HEXES = [
    NEUTRAL_HEX,
    "#9cb096",
    "#90caa9",
    "#8bd7b3",
    "#51c38d",
    "#17af68",
]
def metric_label(metric: str) -> str:
    labels = {
        "avgSleepStress": "avg sleep stress",
        "awakeCount": "awakenings",
        "awakeSleepSeconds": "awake time",
        "deepSleepSeconds": "deep sleep",
        "remSleepSeconds": "REM sleep",
        "restingHeartRate": "resting HR",
        "restlessMomentsCount": "restless moments",
        "sleepScore": "sleep score",
        "sleepTimeSeconds": "total sleep time",
    }
    return labels.get(metric, metric)


def format_seconds(seconds: float, *, style: str = "hm") -> str:
    seconds = max(0, float(seconds))
    mins = int(round(seconds / 60.0))
    h = mins // 60
    m = mins % 60
    if style == "min":
        return f"{mins}min"
    if h <= 0:
        return f"{m}min"
    return f"{h}h {m}m" if m else f"{h}h"


def format_metric_value(metric: str, value: Any) -> str:
    if value is None:
        return "—"
    try:
        v = float(value)
    except Exception:
        return "—"

    if metric == "awakeSleepSeconds":
        return format_seconds(v, style="min")
    if metric in ("deepSleepSeconds", "remSleepSeconds", "sleepTimeSeconds"):
        return format_seconds(v, style="hm")
    if metric == "restingHeartRate":
        return f"{int(round(v))} bpm"
    if metric == "sleepScore":
        return f"{int(round(v))}"
    if metric.endswith("Count"):
        return f"{int(round(v))}"
    return f"{v:.0f}" if abs(v) >= 10 else f"{v:.1f}"


def card_color_from_score_sigma(score: float, sigma: float, *, cap: float = SIGMA_CAP) -> Tuple[float, float, float, float]:
    """
    Discrete, sigma-binned diverging colors.
      - score selects side: >=0 uses POS (green), <0 uses NEG (red)
      - sigma selects intensity bin (0..cap)
    """
    sigma = max(0.0, min(float(sigma), cap))
    ramp = POS_SIGMA_HEXES if score >= 0 else NEG_SIGMA_HEXES

    # Ease sigma so extremes are reserved for very high σ
    t = (sigma / cap) ** GAMMA if cap > 0 else 0.0
    idx = int(round(t * (len(ramp) - 1)))
    idx = max(0, min(idx, len(ramp) - 1))

    # Slight translucency looks closer to Garmin
    alpha = 0.35 + 0.60 * (sigma / cap) if cap > 0 else 0.35
    return to_rgba(ramp[idx], alpha=alpha)


def render_sleep_stage_axis(
    ax: plt.Axes,
    session: StageSession,
    *,
    display_tz: ZoneInfo,
    legend_below_y: float = -0.12,
) -> None:
    """
    Render the sleep-stage timeline.

    Key detail:
      - We draw geometry in UTC (matplotlib date numbers behave like UTC)
      - We *label* ticks in local time (display_tz) using manual ticks for reliability
    """
    ax.set_facecolor("none")

    pts = sorted(session.points, key=lambda p: parse_time_utc(p["time"]))
    times_utc = [parse_time_utc(p["time"]) for p in pts]
    stages = [int(float(p["SleepStageLevel"])) for p in pts]

    # Duration per segment (seconds)
    durations = []
    for i, p in enumerate(pts):
        d = p.get("SleepStageSeconds")
        if d is not None:
            try:
                durations.append(float(d))
                continue
            except Exception:
                pass
        if i < len(pts) - 1:
            durations.append((parse_time_utc(pts[i + 1]["time"]) - parse_time_utc(p["time"])).total_seconds())
        else:
            durations.append(240.0)

    ends_utc = [times_utc[i] + timedelta(seconds=durations[i]) for i in range(len(times_utc))]

    # Draw stage rectangles
    for t0, t1, s in zip(times_utc, ends_utc, stages):
        if s not in STAGE_MAP:
            continue
        meta = STAGE_MAP[s]
        x0 = mdates.date2num(t0)
        x1 = mdates.date2num(t1)
        ax.add_patch(
            Rectangle((x0, 0.0), x1 - x0, meta["level"], facecolor=meta["color"], edgecolor="none")
        )

    ax.set_ylim(0.0, 4.25)
    ax.set_yticks([])
    ax.set_title("Sleep Stages", fontsize=18, color="white", pad=10)

    # X limits in UTC (geometry)
    ax.set_xlim(mdates.date2num(times_utc[0]), mdates.date2num(ends_utc[-1]))
    ax.xaxis_date()

    # ----- Manual local-time ticks (robust across matplotlib versions) -----
    start_local = times_utc[0].astimezone(display_tz)
    end_local = ends_utc[-1].astimezone(display_tz)

    tick_local = start_local.replace(minute=0, second=0, microsecond=0)
    if tick_local < start_local:
        tick_local += timedelta(hours=1)

    tick_positions = []
    tick_labels = []
    while tick_local <= end_local:
        tick_positions.append(mdates.date2num(tick_local.astimezone(ZoneInfo("UTC"))))
        tick_labels.append(tick_local.strftime("%H:%M"))
        tick_local += timedelta(hours=1)

    if not tick_positions:
        tick_positions = [mdates.date2num(times_utc[0]), mdates.date2num(ends_utc[-1])]
        tick_labels = [start_local.strftime("%H:%M"), end_local.strftime("%H:%M")]

    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, color="white")
    ax.tick_params(axis="x", colors="white")

    ax.set_xlabel(f"Time ({display_tz.key})", color="#B7BCC7", fontsize=11)

    # Legend (below axis)
    handles = [
        Patch(facecolor=STAGE_MAP[1]["color"], label="Deep"),
        Patch(facecolor=STAGE_MAP[2]["color"], label="Light"),
        Patch(facecolor=STAGE_MAP[3]["color"], label="REM"),
        Patch(facecolor=STAGE_MAP[0]["color"], label="Awake"),
    ]
    leg = ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, legend_below_y),
        ncol=4,
        frameon=False,
        fontsize=10,
    )
    for t in leg.get_texts():
        t.set_color("white")

    # ---- Sleep / Wake annotation (below stages, beside legend) ----
    sleep_str = start_local.strftime("%H:%M")
    wake_str = end_local.strftime("%H:%M")

    # Place at the same vertical band as the legend, but left/right so it won't overlap.
    y = legend_below_y
    ax.text(
        0.01,
        y,
        f"Sleep= {sleep_str}",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=12,
        color="white",
        clip_on=False,
    )
    ax.text(
        0.99,
        y,
        f"Wake= {wake_str}",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=12,
        color="white",
        clip_on=False,
    )


def draw_metric_cards(

    ax: plt.Axes,
    current_row: Mapping[str, Any],
    baselines: Mapping[str, Tuple[float, float]],
    *,
    cols: int = 3,
    show_mean: bool = True,
) -> None:
    """
    Cards are colored by signed z-score in the 'good direction'.
      - red/green side determined by z-sign after applying higher_is_better
      - intensity uses sigma = |z| with binned palette
    """
    ax.set_facecolor("none")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    n = len(METRICS)
    rows = math.ceil(n / cols)

    pad = 0.03
    gap_x = 0.03
    gap_y = 0.05
    card_w = (1 - 2 * pad - (cols - 1) * gap_x) / cols
    card_h = (1 - 2 * pad - (rows - 1) * gap_y) / rows

    right_pad = 0.022
    sigma_top_offset = 0.020
    mean_top_offset = 0.060

    for i, (metric, higher_is_better) in enumerate(METRICS):
        rr = i // cols
        cc = i % cols
        x = pad + cc * (card_w + gap_x)
        y = 1 - pad - (rr + 1) * card_h - rr * gap_y

        current_raw = current_row.get(metric)
        try:
            current_v = float(current_raw) if current_raw is not None else float("nan")
        except Exception:
            current_v = float("nan")

        mu, sd = baselines.get(metric, (0.0, 0.0))

        z = 0.0
        if sd > 1e-12 and current_v == current_v:
            z = (current_v - mu) / sd

        sigma = abs(z)
        score = z if higher_is_better else -z
        card_rgba = card_color_from_score_sigma(score, sigma)
        ax.add_patch(
            FancyBboxPatch(
                (x, y),
                card_w,
                card_h,
                boxstyle="round,pad=0.012,rounding_size=0.02",
                facecolor=card_rgba,
                edgecolor=(1, 1, 1, 0.08),
                linewidth=1.0,
            )
        )

        ax.text(
            x + card_w - right_pad,
            y + card_h - sigma_top_offset,
            f"σ = {sigma:.2f}",
            ha="right",
            va="top",
            fontsize=11,
            color="white",
            clip_on=False,
            zorder=20,
        )

        if show_mean:
            ax.text(
                x + card_w - right_pad,
                y + card_h - mean_top_offset,
                f"μ = {format_metric_value(metric, mu)}",
                ha="right",
                va="top",
                fontsize=10,
                color="white",
                clip_on=False,
                zorder=20,
            )

        value_y = 0.48 if show_mean else 0.58
        ax.text(
            x + card_w / 2,
            y + card_h * value_y,
            format_metric_value(metric, current_raw),
            ha="center",
            va="center",
            fontsize=28,
            color="white",
            fontweight="bold",
            zorder=10,
        )
        ax.text(
            x + card_w / 2,
            y + card_h * 0.24,
            metric_label(metric),
            ha="center",
            va="center",
            fontsize=14,
            color="white",
            zorder=10,
        )


def render_sleep_report_png(
    *,
    current_summary: Mapping[str, Any],
    session: StageSession,
    baselines: Mapping[str, Tuple[float, float]],
    output_path: str | Path,
    show_mean: bool = True,
    display_tz: str = "America/Toronto",
    legend_below_y: float = -0.12,
) -> Path:
    """
    Public API: pure renderer.

    Args:
      current_summary: one SleepSummary dict
      session: one StageSession (intraday points for that sleep)
      baselines: {metric: (mean, std)} for metrics you care about
      output_path: where to write the PNG
    """
    tz_out = ZoneInfo(display_tz)

    fig = plt.figure(figsize=(14, 9), facecolor=BG_COLOR)
    gs = fig.add_gridspec(nrows=2, ncols=1, height_ratios=[1.1, 1.3], hspace=0.22)

    # Extra breathing room so x-axis labels + legend (below) don't get clipped
    fig.subplots_adjust(bottom=0.10, top=0.94, left=0.06, right=0.98)

    ax_stage = fig.add_subplot(gs[0, 0])
    ax_cards = fig.add_subplot(gs[1, 0])

    render_sleep_stage_axis(ax_stage, session, display_tz=tz_out, legend_below_y=legend_below_y)
    draw_metric_cards(ax_cards, current_summary, baselines, cols=3, show_mean=show_mean)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=200, transparent=False, facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    return output_path
