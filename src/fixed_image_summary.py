#!/usr/bin/env python3
"""
fixed_image_summary.py

Entry-point script for generating a sleep summary PNG (and optionally sending it to Telegram).

What it does:
  1) Pulls SleepSummary + SleepIntraday from InfluxDB
  2) Selects either:
       - the most recent SleepSummary record (default), OR
       - a specific local day via --day YYYY-MM-DD
  3) Computes per-metric baseline mean/std from historical SleepSummary records
  4) Finds the matching intraday sleep session for that night
  5) Calls src/image_summary.py (renderer) to write:
       exports/summary_screenshots/sleep_report_<YYYY-MM-DD>.png
  6) Optionally sends the PNG to Telegram

Required env vars for Telegram send:
  - TELEGRAM_BOT_TOKEN
  - TELEGRAM_CHAT_ID

Influx env vars are the same as fixed_message.py:
  - INFLUXDB_HOST, INFLUXDB_PORT, INFLUXDB_DATABASE
  - INFLUXDB_USERNAME, INFLUXDB_PASSWORD, INFLUXDB_SSL
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sleep_report.baselines import compute_metric_baselines
from sleep_report.influx_fetch import (
    connect_influx,
    fetch_sleep_intraday_range,
    fetch_sleep_summary_last_days,
    fetch_sleep_summary_time_range,
)
from sleep_report.selectors import (
    compute_intraday_fetch_window,
    match_session_to_summary,
    select_current,
)
from sleep_report.stages import build_stage_sessions
from sleep_report.time_utils import parse_time_utc

from image_summary import METRICS, render_sleep_report_png


# Separate state file so text and image sends don't block each other
STATE_PATH = Path("/app/data/last_sleep_image_sent_key.json")


def load_last_sent_key() -> str | None:
    """Return the last sent key from STATE_PATH, or None if missing/unreadable."""
    try:
        return json.loads(STATE_PATH.read_text()).get("last_sent_key")
    except Exception:
        return None


def save_last_sent_key(key: str) -> None:
    """Persist the last sent key to STATE_PATH."""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({"last_sent_key": key}))


def repo_root_from_src_file(src_file: Path) -> Path:
    """Assumes this file lives in <repo>/src/ and returns <repo>."""
    return src_file.resolve().parents[1]


def telegram_send_photo(image_path: Path, caption: str = "") -> bool:
    """
    Minimal Telegram photo sender (stdlib only).

    Returns:
      True  -> Telegram API returned ok=true
      False -> not sent (missing env vars or request failed)
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set; skipping Telegram send.")
        return False

    import mimetypes
    import uuid
    from urllib import request

    boundary = "----WebKitFormBoundary" + uuid.uuid4().hex
    url = f"https://api.telegram.org/bot{token}/sendPhoto"

    def part(name: str, value: str) -> bytes:
        return (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        ).encode("utf-8")

    file_bytes = image_path.read_bytes()
    mime = mimetypes.guess_type(str(image_path))[0] or "image/png"

    file_header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="photo"; filename="{image_path.name}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode("utf-8")

    end = f"--{boundary}--\r\n".encode("utf-8")

    body = b"".join(
        [
            part("chat_id", str(chat_id)),
            part("caption", caption),
            file_header,
            file_bytes,
            b"\r\n",
            end,
        ]
    )

    req = request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("Content-Length", str(len(body)))

    try:
        with request.urlopen(req, timeout=30) as resp:
            payload = resp.read().decode("utf-8", errors="replace")

        try:
            data = json.loads(payload)
        except Exception:
            data = {}

        ok = bool(data.get("ok") is True)
        if ok:
            print("Sent Telegram image.")
        else:
            print("Telegram sendPhoto response (not ok):", payload[:500])
        return ok
    except Exception as e:
        print("Telegram sendPhoto failed:", repr(e))
        return False


def _select_summary_for_day(candidates: list[dict], day: date, tz: ZoneInfo) -> dict:
    """
    Choose a SleepSummary record matching a LOCAL day.

    Preference:
      1) calendarDate == YYYY-MM-DD (if present)
      2) local date derived from 'time'
    """
    day_str = day.isoformat()

    matches = [c for c in candidates if str(c.get("calendarDate") or "").strip() == day_str]
    if not matches:
        matches = []
        for c in candidates:
            t = c.get("time")
            if not t:
                continue
            try:
                if parse_time_utc(t).astimezone(tz).date() == day:
                    matches.append(c)
            except Exception:
                continue

    if not matches:
        raise SystemExit(f"No SleepSummary record found for local day {day_str} in {tz.key}.")

    matches.sort(key=lambda r: parse_time_utc(r["time"]))
    return dict(matches[-1])


def run_once(
    *,
    summary_days: int = 30,
    show_mean: bool = True,
    show_sigma: bool = True,
    send_telegram: bool = True,
    day: str | None = None,
    display_tz: str = "America/Toronto",
) -> bool:
    """
    Generate the sleep report PNG once.

    - If day is provided (YYYY-MM-DD), generate for that local day and ignore skip-check.
    - If day is None, generate for the most recent day and skip if already sent.
    """
    tz = ZoneInfo(display_tz)
    client = connect_influx()

    # --- Select which summary to render ---
    if day:
        target_day = date.fromisoformat(day)

        # Pull a window around that day (widened to handle near-midnight edge cases)
        start_local = datetime(target_day.year, target_day.month, target_day.day, 0, 0, 0, tzinfo=tz)
        end_local = start_local + timedelta(days=1)
        start_utc = (start_local - timedelta(hours=18)).astimezone(timezone.utc)
        end_utc = (end_local + timedelta(hours=18)).astimezone(timezone.utc)

        candidates = fetch_sleep_summary_time_range(client, start_utc, end_utc)
        current = _select_summary_for_day(candidates, target_day, tz)

        current_time = parse_time_utc(current["time"])

        # Baselines relative to that day: last N days prior to current_time
        baseline_start = current_time - timedelta(days=int(summary_days))
        summaries = fetch_sleep_summary_time_range(
            client,
            baseline_start,
            current_time + timedelta(seconds=1),
        )
    else:
        summaries = fetch_sleep_summary_last_days(client, days=summary_days)
        current = select_current(summaries)
        if current is None:
            raise SystemExit(f"No SleepSummary data found in the last {summary_days} days.")

    sleep_key = str(current.get("calendarDate") or current.get("time") or "").strip()
    if not sleep_key:
        raise SystemExit("Could not determine sleep_key (missing calendarDate/time).")

    # Only skip based on last_sent_key for the default "latest" mode.
    if day is None:
        last = load_last_sent_key()
        if last == sleep_key:
            print(f"Already sent image for {sleep_key}; skipping.")
            return False
    else:
        print("Day override active: ignoring last_sent_key skip check.")

    # Compute baselines (exclude current so it doesn't affect itself)
    metric_names = [m for (m, _hib) in METRICS]
    baselines = compute_metric_baselines(summaries, metric_names, exclude_summary=current)

    # Fetch intraday points for a window that should contain the sleep session
    start_utc, end_utc = compute_intraday_fetch_window(current)
    intraday_points = fetch_sleep_intraday_range(client, start_utc, end_utc, measurement="SleepIntraday")

    sessions = build_stage_sessions(intraday_points)
    session = match_session_to_summary(current, sessions)

    root = repo_root_from_src_file(Path(__file__))
    out_dir = root / "exports" / "summary_screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Use calendarDate if present; else ISO date from time (local)
    if current.get("calendarDate"):
        day_key = str(current["calendarDate"])[:10]
    else:
        day_key = parse_time_utc(current["time"]).astimezone(tz).date().isoformat()

    out_path = out_dir / f"sleep_report_{day_key}.png"

    #the main function call to create the image contained in image_summary.py
    render_sleep_report_png(
        current_summary=current,
        session=session,
        baselines=baselines,
        output_path=out_path,
        show_mean=show_mean,
        show_sigma=show_sigma,
        display_tz=display_tz,
    )

    print("Wrote:", out_path)

    #Only update last_sent_key when we actually send to Telegram AND it succeeds.
    if send_telegram:
        sent_ok = telegram_send_photo(out_path, caption=f"Sleep Summary ({day_key}) \nAny thoughts on why your sleep was like this?")
        if sent_ok:
            save_last_sent_key(sleep_key)
        else:
            print("Telegram send failed/not ok; NOT updating last_sent_key so it can retry.")
    else:
        print("Not sending Telegram (--no-telegram); NOT updating last_sent_key.")

    return True

#this currently isn't being used demo.py and scheduler.py use the render_sleep_report_png, but leaving this in here is someone want to call it with arguments.
def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="Generate and optionally send the sleep summary PNG.")
    p.add_argument("--summary-days", type=int, default=30, help="Days of summaries to fetch for baselines.")
    p.add_argument("--hide-mean", action="store_true", help="Hide μ (mean) on each card; default shows it.")
    p.add_argument("--hide-sigma", action="store_true", help="Hide sigma (std dev) on each card; default shows it.")
    p.add_argument("--day", type=str, default=None, help="Generate a specific local day (YYYY-MM-DD) instead of latest.")
    p.add_argument(
        "--display-tz",
        type=str,
        default="America/Toronto",
        help="Timezone for day matching and x-axis labels.",
    )
    p.add_argument("--no-telegram", action="store_true", help="Do not send the image to Telegram.")
    args = p.parse_args()

    run_once(
        summary_days=args.summary_days,
        show_mean=(not args.hide_mean),
        show_sigma=(not args.hide_sigma),
        send_telegram=not args.no_telegram,
        day=args.day,
        display_tz=args.display_tz,
    )


if __name__ == "__main__":
    main()
