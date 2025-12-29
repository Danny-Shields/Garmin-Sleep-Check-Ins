#!/usr/bin/env python3
"""
scheduler loop for Garmin Sleep Check-Ins.

Purpose:
- Run a "one-shot" task (default: fixed_message.run_once) on a fixed interval.
- The one-shot task is responsible for dedupe (i.e., only send once per new sleep).

Config (env vars):
- CHECK_INTERVAL_SECONDS: how often to run (default: 600)
- JITTER_SECONDS: add 0..JITTER_SECONDS random delay after each run (default: 30)
- SCHEDULER_TARGET: module:function to call (default: "fixed_message:run_once")

CLI (optional):
- --once              run a single iteration then exit
- --interval SECONDS  override interval
- --target MOD:FUNC   override SCHEDULER_TARGET
"""

from __future__ import annotations

import argparse
import importlib
import os
import random
import sys
import time
import traceback
from datetime import datetime
from typing import Callable


def load_target(spec: str) -> Callable[[], object]:
    if ":" not in spec:
        raise ValueError(f"Invalid SCHEDULER_TARGET '{spec}'. Use 'module:function'.")
    mod_name, func_name = spec.split(":", 1)
    mod = importlib.import_module(mod_name)
    fn = getattr(mod, func_name, None)
    if fn is None or not callable(fn):
        raise ValueError(f"Target '{spec}' not found or not callable.")
    return fn  # type: ignore[return-value]


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[scheduler {ts}] {msg}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run one iteration and exit.")
    parser.add_argument("--interval", type=int, default=None, help="Override interval seconds.")
    parser.add_argument("--target", type=str, default=None, help="Override module:function target.")
    args = parser.parse_args()

    interval = args.interval or int(os.getenv("CHECK_INTERVAL_SECONDS", "600"))
    jitter = int(os.getenv("JITTER_SECONDS", "30"))
    target_spec = args.target or os.getenv("SCHEDULER_TARGET", "fixed_message:run_once")

    try:
        target = load_target(target_spec)
    except Exception as e:
        log(f"ERROR loading target: {e}")
        return 2

    log(f"Starting. target={target_spec} interval={interval}s jitter=0..{jitter}s")

    while True:
        try:
            result = target()
            # Convention: run_once may return True/False, but we don't require it.
            if isinstance(result, bool):
                log("Run complete: SENT" if result else "Run complete: SKIPPED (no new sleep)")
            else:
                log("Run complete.")
        except SystemExit as e:
            # Treat SystemExit as a hard config/runtime stop (missing env vars etc.)
            log(f"FATAL: {e}")
            return 1
        except Exception:
            log("ERROR: exception during run:")
            traceback.print_exc()
            # keep looping; transient errors shouldn't kill the scheduler

        if args.once:
            return 0

        sleep_for = interval + (random.randint(0, jitter) if jitter > 0 else 0)
        log(f"Sleeping {sleep_for}s")
        time.sleep(sleep_for)


if __name__ == "__main__":
    raise SystemExit(main())
