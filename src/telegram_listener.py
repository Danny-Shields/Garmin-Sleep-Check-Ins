#!/usr/bin/env python3
"""
Long-poll Telegram listener:
- Reads updates via getUpdates (long polling)
- Only processes messages from TELEGRAM_CHAT_ID set in the .env
- Sanitizes inbound text (defense-in-depth)
- Stores message in Influx measurement SleepJournal
- Sends a short confirmation back using telegram_client.send_message()

Env required:
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID

Optional set in the .addon.yml:
- TELEGRAM_LONGPOLL_TIMEOUT_SECONDS (default 50)
- TELEGRAM_POLL_SLEEP_SECONDS       (default 1)

State to know if it is a new message:
- /app/data/telegram_listener_state.json (bind mount ./data -> /app/data)
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

from journal_store import connect_influx, write_telegram_journal_entry
from telegram_client import send_message


BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN", "") or "").strip()
CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID", "") or "").strip()

STATE_PATH = Path("/app/data/telegram_listener_state.json")

LONGPOLL_TIMEOUT = int(os.getenv("TELEGRAM_LONGPOLL_TIMEOUT_SECONDS", "50"))
POLL_SLEEP = float(os.getenv("TELEGRAM_POLL_SLEEP_SECONDS", "1"))

# Remove control chars; then normalize whitespace.
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
WHITESPACE = re.compile(r"\s+")


def _api_url(method: str) -> str:
    return f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"


def sanitize_text(s: str, max_len: int = 512) -> str:
    s = s.strip()
    s = CONTROL.sub("", s)
    s = WHITESPACE.sub(" ", s).strip()
    if len(s) > max_len:
        s = s[:max_len]
    return s


def load_offset() -> int:
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return int(data.get("offset", 0))
    except Exception:
        return 0


def save_offset(offset: int) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({"offset": offset}), encoding="utf-8")


def get_updates(offset: int) -> List[Dict[str, Any]]:
    resp = requests.get(
        _api_url("getUpdates"),
        params={"offset": offset, "timeout": LONGPOLL_TIMEOUT},
        timeout=LONGPOLL_TIMEOUT + 10,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Telegram getUpdates failed: HTTP {resp.status_code} {resp.text}")

    payload = resp.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram getUpdates returned ok=false: {payload}")

    results = payload.get("result") or []
    return results if isinstance(results, list) else []


def extract_message(update: Dict[str, Any]) -> Optional[Tuple[int, Dict[str, Any]]]:
    upd_id = update.get("update_id")
    msg = update.get("message")
    if isinstance(upd_id, int) and isinstance(msg, dict):
        return upd_id, msg
    return None


def handle_message(influx_client, update_id: int, msg: Dict[str, Any]) -> None:
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None:
        return

    # Only accept messages from TELEGRAM_CHAT_ID
    if str(chat_id) != str(CHAT_ID):
        return

    from_obj = msg.get("from") or {}
    from_id = str(from_obj.get("id", ""))
    from_username = str(from_obj.get("username", "") or "")
    from_name = " ".join(
        [str(from_obj.get("first_name", "") or "").strip(), str(from_obj.get("last_name", "") or "").strip()]
    ).strip()

    message_id = msg.get("message_id")
    raw_text = msg.get("text")

    if isinstance(raw_text, str) and raw_text.strip():
        text = sanitize_text(raw_text)
        msg_type = "text"
    else:
        text = "[non-text message]"
        msg_type = "non_text"

    write_telegram_journal_entry(
        influx_client,
        chat_id=str(chat_id),
        from_id=from_id,
        text=text,
        msg_type=msg_type,
        from_username=from_username,
        from_name=from_name,
        message_id=message_id if isinstance(message_id, int) else None,
        update_id=update_id,
        ts_utc=datetime.now(timezone.utc),
    )

    # short confirmation, avoids reflecting user input
    send_message("Thanks we saved your response")


def run_listener_forever() -> None:
    if not BOT_TOKEN:
        raise SystemExit("Missing TELEGRAM_BOT_TOKEN.")
    if not CHAT_ID:
        raise SystemExit("Missing TELEGRAM_CHAT_ID.")

    influx = connect_influx()
    offset = load_offset()

    while True:
        try:
            updates = get_updates(offset)
            for upd in updates:
                upd_id = upd.get("update_id")
                if isinstance(upd_id, int):
                    offset = max(offset, upd_id + 1)

                extracted = extract_message(upd)
                if extracted:
                    u_id, msg = extracted
                    handle_message(influx, u_id, msg)

            save_offset(offset)
        except Exception as e:
            print(f"[telegram_listener] error: {e}", flush=True)
            time.sleep(5)

        time.sleep(POLL_SLEEP)


if __name__ == "__main__":
    run_listener_forever()

