"""Load RSA settings from the environment or a local .env file."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
USERS_DIR = DATA_DIR / "users"
TMP_DIR = DATA_DIR / "tmp"
OAUTH_DIR = DATA_DIR / "oauth"

APP_NAME = "Receipt Scanner Automation RSA"
DRIVE_FOLDER_NAME = "RSA Receipts"
SHEET_TITLE = "RSA Receipts"
SCOPES = (
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets",
)


def load_env_file(path: Path = ROOT / ".env") -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))


def require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing {name}. Run install.sh or add it to .env")
    return value


load_env_file()
for folder in (DATA_DIR, USERS_DIR, TMP_DIR, OAUTH_DIR):
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
