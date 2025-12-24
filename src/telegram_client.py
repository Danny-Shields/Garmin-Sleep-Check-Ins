#!/usr/bin/env python3
"""
telegram_client.py

Handles sending telegram messages

Environment variables required:
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID

Public API:
    send_message(text: str) -> None

"""

from __future__ import annotations

import os

import requests

try:
    # Optional convenience: allows running this module standalone with a local .env
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass


def send_message(text: str, *, disable_web_page_preview: bool = True) -> None:
    """Send a plain text message to a Telegram chat via bot API."""
    bot_token = (os.getenv("TELEGRAM_BOT_TOKEN", "") or "").strip()
    chat_id = (os.getenv("TELEGRAM_CHAT_ID", "") or "").strip()

    if not bot_token or not chat_id:
        raise SystemExit("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID.")

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    resp = requests.post(
        url,
        data={
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true" if disable_web_page_preview else "false",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Telegram send failed: HTTP {resp.status_code} {resp.text}")

