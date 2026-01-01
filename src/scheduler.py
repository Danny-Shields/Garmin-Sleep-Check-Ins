#!/usr/bin/env python3
"""
Runs a one-shot task on a fixed interval to send a summary to the telegram chat.
The one-shot task should handle dedupe (only send once per new sleep).

Env vars:
- CHECK_INTERVAL_SECONDS (default 600)
- JITTER_SECONDS (default 30)
- SUMMARY_OUTPUT or summary_output: "text" or "image" (default "text")
    - text  -> fixed_message:run_once
    - image -> fixed_image_summary:run_once
- SCHEDULER_TARGET: module:function (overrides SUMMARY_OUTPUT)

CLI:
- --once              run a single iteration then exit
- --interval SECONDS  override interval
- --target MOD:FUNC   override target (highest priority)
"""

from __future__ import annotations

import argparse
import importlib
import os
import random
import signal
import threading
import traceback
from datetime import datetime
from typing import Callable


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[scheduler {ts}] {msg}", flush=True)


def get_int_env(name: str, default: int) -> int:
    raw = (os.getenv(name, "") or "").strip()
    if not raw:
        return default
    try:
        v = int(raw)
        return v if v > 0 else default
    except ValueError:
        return default


def load_target(spec: str) -> Callable[[], object]:
    if ":" not in spec:
        raise ValueError(f"Invalid target '{spec}'. Use 'module:function'.")
    mod_name, func_name = spec.split(":", 1)
    mod = importlib.import_module(mod_name)
    fn = getattr(mod, func_name, None)
    if fn is None or not callable(fn):
        raise ValueError(f"Target '{spec}' not found or not callable.")
    return fn  # type: ignore[return-value]


def _default_target_from_summary_output() -> str:
    # Support both SUMMARY_OUTPUT and summary_output (your wording)
    summary_output = (
        (os.getenv("SUMMARY_OUTPUT", "") or "").strip()
        or (os.getenv("summary_output", "") or "").strip()
        or "text"
    ).lower()

    if summary_output == "image":
        return "fixed_image_summary:run_once"
    if summary_output != "text":
        log(f"WARNING: summary_output='{summary_output}' invalid; defaulting to 'text'.")
    return "fixed_message:run_once"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run one iteration and exit.")
    parser.add_argument("--interval", type=int, default=None, help="Override interval seconds.")
    parser.add_argument("--target", type=str, default=None, help="Override module:function target.")
    args = parser.parse_args()

    interval = args.interval or get_int_env("CHECK_INTERVAL_SECONDS", 600)
    jitter = get_int_env("JITTER_SECONDS", 30)

    # Priority: CLI --target > env SCHEDULER_TARGET > SUMMARY_OUTPUT-derived default
    target_spec = (
        args.target
        or (os.getenv("SCHEDULER_TARGET", "") or "").strip()
        or _default_target_from_summary_output()
    )

    try:
        target = load_target(target_spec)
    except Exception as e:
        log(f"ERROR loading target: {e}")
        return 2

    # Graceful stop support (so docker compose stop is fast)
    stop_event = threading.Event()

    def _handle_stop(signum, frame) -> None:  # noqa: ARG001
        stop_event.set()

    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    log(f"Starting. target={target_spec} interval={interval}s jitter=0..{jitter}s")

    while not stop_event.is_set():
        try:
            result = target()
            if isinstance(result, bool):
                log("Run complete: SENT" if result else "Run complete: SKIPPED (no new sleep)")
            else:
                log("Run complete.")
        except SystemExit as e:
            log(f"FATAL: {e}")
            return 1
        except Exception:
            log("ERROR: exception during run:")
            traceback.print_exc()

        if args.once:
            return 0

        sleep_for = interval + (random.randint(0, jitter) if jitter > 0 else 0)
        log(f"Sleeping {sleep_for}s")
        stop_event.wait(sleep_for)

    log("Stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

