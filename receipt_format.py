"""Format receipt names, dates, and categories for the bot and Google Sheet."""

from __future__ import annotations

import re
from datetime import datetime

from extract_receipt import ReceiptInfo

FOOD_KEYWORDS = (
    "grocer",
    "dining",
    "restaurant",
    "food",
    "cafe",
    "coffee",
    "bakery",
    "bistro",
    "lunch",
    "breakfast",
    "dinner",
    "supermarket",
    "market",
)


def receipt_number(number: int) -> str:
    return str(number)


def parse_date_parts(date_text: str | None) -> tuple[int, int, int] | None:
    """Return (year, month, day) from common receipt date strings."""
    if not date_text:
        return None
    cleaned = date_text.strip()
    if not cleaned:
        return None
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", cleaned)
    if match:
        return int(match.group(1)), int(match.group(2)), int(match.group(3))
    match = re.match(r"(\d{2})\s+(\d{2})\s+(\d{4})", cleaned)
    if match:
        return int(match.group(3)), int(match.group(2)), int(match.group(1))
    match = re.match(r"(\d{2})[./-](\d{2})[./-](\d{4})", cleaned)
    if match:
        return int(match.group(3)), int(match.group(2)), int(match.group(1))
    return None


def format_display_date(date_text: str | None) -> str:
    if not date_text:
        return "unknown"
    parts = parse_date_parts(date_text)
    if parts:
        y, m, d = parts
        return f"{d:02d}.{m:02d}.{y}"
    return date_text


def _parse_hour(purchase_time: str | None) -> int | None:
    if not purchase_time:
        return None
    match = re.match(r"(\d{1,2})", purchase_time.strip())
    if not match:
        return None
    hour = int(match.group(1))
    if 0 <= hour <= 23:
        return hour
    return None


def is_food_category(category: str | None) -> bool:
    if not category:
        return False
    lowered = category.lower()
    return any(keyword in lowered for keyword in FOOD_KEYWORDS)


def infer_meal(category: str | None, purchase_time: str | None) -> str | None:
    if not is_food_category(category):
        return None
    hour = _parse_hour(purchase_time)
    if hour is None:
        return None
    if 5 <= hour <= 10:
        return "breakfast"
    if 11 <= hour <= 15:
        return "lunch"
    if 16 <= hour <= 22:
        return "dinner"
    return None


def category_display(info: ReceiptInfo) -> str:
    base = (info.category or "other").strip()
    meal = (info.meal or "").strip().lower()
    if meal not in {"breakfast", "lunch", "dinner"}:
        meal = infer_meal(info.category, info.purchase_time) or ""
    if meal and is_food_category(info.category):
        return f"{base} ({meal})"
    return base


def parse_input_date(text: str) -> str | None:
    cleaned = text.strip()
    if not cleaned or cleaned == "-":
        return None
    match = re.match(r"(\d{2})\s+(\d{2})\s+(\d{4})", cleaned)
    if match:
        return f"{match.group(3)}-{match.group(2)}-{match.group(1)}"
    match = re.match(r"(\d{2})[./-](\d{2})[./-](\d{4})", cleaned)
    if match:
        return f"{match.group(3)}-{match.group(2)}-{match.group(1)}"
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", cleaned)
    if match:
        return cleaned
    return cleaned


def format_amount(info: ReceiptInfo) -> str:
    if info.amount is None:
        return "unknown"
    currency = (info.currency or "").strip()
    if currency:
        return f"{info.amount:g} {currency}"
    return f"{info.amount:g}"
