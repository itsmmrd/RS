"""Per-user JSON storage for Google tokens and receipt counters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import USERS_DIR


def user_path(telegram_id: int) -> Path:
    return USERS_DIR / f"{telegram_id}.json"


def load_user(telegram_id: int) -> dict[str, Any]:
    path = user_path(telegram_id)
    if not path.is_file():
        return {
            "telegram_id": telegram_id,
            "google": None,
            "folder_id": None,
            "spreadsheet_id": None,
            "spreadsheet_url": None,
            "next_number": 1,
        }
    return json.loads(path.read_text(encoding="utf-8"))


def save_user(record: dict[str, Any]) -> None:
    path = user_path(int(record["telegram_id"]))
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def is_google_connected(telegram_id: int) -> bool:
    record = load_user(telegram_id)
    google = record.get("google") or {}
    return bool(google.get("refresh_token") or google.get("token"))
