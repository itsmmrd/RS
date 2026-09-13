"""
Extract purchase date, category, and amount from a receipt photo with Gemini.

Usage:
    python extract_receipt.py output/receipt.jpeg

Set GEMINI_API_KEY in .env or the environment.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
DEFAULT_IMAGE = ROOT / "output" / "sample.jpeg"
OUTPUT_DIR = ROOT / "output"

MODELS = (
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.5-flash-lite",
)

MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


class ReceiptInfo(BaseModel):
    date: str | None = Field(
        default=None,
        description="Purchase date in YYYY-MM-DD. Use null if not visible.",
    )
    category: str | None = Field(
        default=None,
        description=(
            "One purchase category such as groceries, drugstore, pharmacy, "
            "health, beauty, household, dining, transport, electronics, "
            "clothing, entertainment, or other."
        ),
    )
    amount: float | None = Field(
        default=None,
        description="Total amount paid as a number, e.g. 9.95. Use null if unknown.",
    )
    currency: str | None = Field(
        default=None,
        description="ISO currency code such as EUR or USD.",
    )
    merchant: str | None = Field(
        default=None,
        description="Store or merchant name if visible.",
    )
    purchase_time: str | None = Field(
        default=None,
        description="Purchase time in HH:MM 24-hour format if visible on the receipt.",
    )
    meal: str | None = Field(
        default=None,
        description=(
            "For food or grocery purchases only: breakfast, lunch, or dinner "
            "based on items and time if inferable."
        ),
    )


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def get_api_key() -> str:
    load_env_file(ROOT / ".env")
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError(
            "Missing Gemini API key. Add GEMINI_API_KEY to a .env file "
            "or export it, then retry.\n"
            "Create a key at https://aistudio.google.com/apikey"
        )
    return key


def extract_receipt(image_path: Path, api_key: str | None = None) -> ReceiptInfo:
    if not image_path.is_file():
        raise FileNotFoundError(f"Image not found: {image_path}")

    mime = MIME_TYPES.get(image_path.suffix.lower())
    if mime is None:
        raise ValueError(f"Unsupported image type: {image_path.suffix}")

    client = genai.Client(api_key=api_key or get_api_key())
    prompt = (
        "Read this receipt photo and extract the purchase details. "
        "Use the printed total, do not add line items yourself. "
        "If the date is written as DD.MM.YYYY or DD/MM/YYYY, convert it to YYYY-MM-DD. "
        "Choose a single category that best matches the store and items. "
        "If a purchase time is printed, return it as HH:MM. "
        "For groceries, dining, or food stores, infer breakfast, lunch, or dinner "
        "from the items and time when possible. "
        "If a field is unreadable, return null for that field."
    )
    image_part = types.Part.from_bytes(data=image_path.read_bytes(), mime_type=mime)
    last_error: Exception | None = None

    for model in MODELS:
        try:
            response = client.models.generate_content(
                model=model,
                contents=[image_part, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ReceiptInfo,
                ),
            )
            if response.parsed is not None:
                return response.parsed
            if response.text:
                return ReceiptInfo.model_validate_json(response.text)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue

    raise RuntimeError(f"Gemini could not extract receipt data: {last_error}")


def extract_receipt_from_text(text: str, api_key: str | None = None) -> ReceiptInfo:
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("Receipt text is empty.")
    client = genai.Client(api_key=api_key or get_api_key())
    prompt = (
        "Parse this receipt note into structured purchase details. "
        "The user may write freely in any language or format. "
        "Extract date, category, amount, currency, merchant, purchase time, and meal "
        "when possible. Convert dates to YYYY-MM-DD. Choose one best category. "
        "For food or grocery purchases, infer breakfast, lunch, or dinner when possible. "
        "Use null for unknown fields.\n\n"
        f"User text:\n{cleaned}"
    )
    last_error: Exception | None = None
    for model in MODELS:
        try:
            response = client.models.generate_content(
                model=model,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ReceiptInfo,
                ),
            )
            if response.parsed is not None:
                return response.parsed
            if response.text:
                return ReceiptInfo.model_validate_json(response.text)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
    raise RuntimeError(f"Gemini could not parse receipt text: {last_error}")


class NormalizedField(BaseModel):
    value: str | None = Field(
        default=None,
        description="Cleaned canonical value for the field, or null if invalid.",
    )


EDIT_FIELD_PROMPTS = {
    "date": (
        "Normalize this purchase date to YYYY-MM-DD. "
        "Accept formats like DD.MM.YYYY, DD MM YYYY, '1 sep 2026', or 'yesterday'."
    ),
    "category": (
        "Fix spelling and return one short purchase category in lowercase English, "
        "such as groceries, dining, drugstore, transport, or other."
    ),
    "amount": (
        "Extract the total amount as a plain decimal number without currency symbols "
        "(use a dot for decimals)."
    ),
    "currency": "Return the ISO 4217 currency code such as EUR, USD, or GBP.",
    "merchant": "Fix spelling and return the proper store or merchant name.",
    "time": "Normalize this purchase time to 24-hour HH:MM format.",
}


def _parse_amount_local(raw: str) -> float | None:
    cleaned = raw.strip().replace(",", ".")
    for token in cleaned.replace("€", " ").replace("$", " ").split():
        try:
            return float(token)
        except ValueError:
            continue
    return None


def normalize_edit_field(field: str, raw: str, api_key: str | None = None) -> str | float | None:
    cleaned = raw.strip()
    if not cleaned or cleaned == "-":
        return None
    if field not in EDIT_FIELD_PROMPTS:
        raise ValueError(f"Unknown field: {field}")

    if field == "amount":
        local = _parse_amount_local(cleaned)
        if local is not None:
            return local

    client = genai.Client(api_key=api_key or get_api_key())
    prompt = (
        f"{EDIT_FIELD_PROMPTS[field]}\n"
        "Return JSON with a single 'value' field.\n\n"
        f"User input: {cleaned}"
    )
    last_error: Exception | None = None
    for model in MODELS:
        try:
            response = client.models.generate_content(
                model=model,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=NormalizedField,
                ),
            )
            parsed = response.parsed
            if parsed is None and response.text:
                parsed = NormalizedField.model_validate_json(response.text)
            if parsed is None or parsed.value is None:
                raise ValueError(f"Could not normalize {field}.")
            if field == "amount":
                amount = _parse_amount_local(parsed.value)
                if amount is None:
                    raise ValueError(f"Could not normalize amount: {parsed.value}")
                return amount
            return parsed.value.strip()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue

    if field == "amount":
        local = _parse_amount_local(cleaned)
        if local is not None:
            return local
    raise RuntimeError(f"Gemini could not normalize {field}: {last_error}")


def save_receipt(info: ReceiptInfo, image_path: Path) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / f"{image_path.stem}.json"
    json_path.write_text(
        json.dumps(info.model_dump(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return json_path


def print_receipt(info: ReceiptInfo) -> None:
    print("Extracted receipt")
    print(f"  date:     {info.date or 'unknown'}")
    print(f"  category: {info.category or 'unknown'}")
    print(f"  amount:   {info.amount if info.amount is not None else 'unknown'}")
    if info.currency:
        print(f"  currency: {info.currency}")
    if info.merchant:
        print(f"  merchant: {info.merchant}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract date, category, and amount from a receipt image with Gemini."
    )
    parser.add_argument(
        "image",
        nargs="?",
        type=Path,
        default=DEFAULT_IMAGE,
        help="Processed receipt image (defaults to output/sample.jpeg)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    image = args.image if args.image.is_absolute() else ROOT / args.image
    info = extract_receipt(image)
    json_path = save_receipt(info, image)
    print_receipt(info)
    print(f"Saved {json_path}")


if __name__ == "__main__":
    main()
