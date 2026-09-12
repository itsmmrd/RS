"""Telegram bot for ReciptscannerAtuoamtiion RSA."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from aiohttp import web
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from config import APP_NAME, TMP_DIR, load_env_file, require
from extract_receipt import ReceiptInfo, extract_receipt
from google_services import (
    allocate_receipt_name,
    append_sheet_row,
    authorization_url,
    delete_record,
    finish_oauth,
    list_records,
    next_receipt_name,
    public_base_url,
    upload_receipt_file,
)
from scan_document import scan_image
from storage import is_google_connected, load_user

load_env_file()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("rsa")

REVIEW, EDIT_FIELD, ADD_DATE, ADD_CATEGORY, ADD_AMOUNT, ADD_NOTE, DELETE_NAME = range(7)


def require_google(handler):
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user is None:
            return ConversationHandler.END
        if not is_google_connected(user.id):
            url = authorization_url(user.id)
            text = (
                f"Welcome to {APP_NAME}.\n\n"
                "Connect your Google account first. RSA will save receipts to "
                "your Drive and add rows to a Google Sheet."
            )
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("Connect Google account", url=url)]]
            )
            target = update.effective_message
            if target:
                await target.reply_text(text, reply_markup=keyboard)
            return ConversationHandler.END
        return await handler(update, context)

    return wrapped


def format_info(info: ReceiptInfo, name: str | None = None) -> str:
    lines = []
    if name:
        lines.append(f"Name: {name}")
    lines.extend(
        [
            f"Date: {info.date or 'unknown'}",
            f"Category: {info.category or 'unknown'}",
            f"Amount: {info.amount if info.amount is not None else 'unknown'}",
            f"Currency: {info.currency or ''}".rstrip(),
            f"Merchant: {info.merchant or 'unknown'}",
        ]
    )
    return "\n".join(line for line in lines if line)


def review_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Save result", callback_data="save_result"),
                InlineKeyboardButton("Save original photo", callback_data="save_original"),
            ],
            [
                InlineKeyboardButton("Edit text", callback_data="edit_text"),
                InlineKeyboardButton("Cancel", callback_data="cancel"),
            ],
        ]
    )


def edit_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Date", callback_data="edit:date"),
                InlineKeyboardButton("Category", callback_data="edit:category"),
            ],
            [
                InlineKeyboardButton("Amount", callback_data="edit:amount"),
                InlineKeyboardButton("Merchant", callback_data="edit:merchant"),
            ],
            [InlineKeyboardButton("Back", callback_data="edit:back")],
        ]
    )


def info_from_context(context: ContextTypes.DEFAULT_TYPE) -> ReceiptInfo:
    data = context.user_data.get("info") or {}
    return ReceiptInfo.model_validate(data)


def store_info(context: ContextTypes.DEFAULT_TYPE, info: ReceiptInfo) -> None:
    context.user_data["info"] = info.model_dump()


@require_google
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record = load_user(update.effective_user.id)
    sheet = record.get("spreadsheet_url") or "your RSA Google Sheet"
    await update.message.reply_text(
        f"{APP_NAME} is ready.\n\n"
        "Send a receipt photo to scan it.\n"
        "/add — add a receipt manually\n"
        "/text — save text only, no photo\n"
        "/delete — remove a saved record\n"
        "/list — show recent records\n"
        "/connect — reconnect Google\n\n"
        f"Sheet: {sheet}"
    )


async def connect_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    url = authorization_url(update.effective_user.id)
    await update.message.reply_text(
        "Open this link to connect or refresh your Google account:",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Connect Google account", url=url)]]
        ),
    )


@require_google
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message
    photo = message.photo[-1]
    user_dir = TMP_DIR / str(update.effective_user.id)
    user_dir.mkdir(parents=True, exist_ok=True)
    original = user_dir / "original.jpg"
    processed = user_dir / "processed.jpg"

    await message.reply_text("Scanning the receipt...")
    file = await photo.get_file()
    await file.download_to_drive(original)

    try:
        await asyncio.to_thread(scan_image, original, False, processed)
        info = await asyncio.to_thread(extract_receipt, processed)
    except Exception as exc:  # noqa: BLE001
        log.exception("Scan/extract failed")
        await message.reply_text(f"Could not process this photo: {exc}")
        return ConversationHandler.END

    store_info(context, info)
    context.user_data["original"] = str(original)
    context.user_data["processed"] = str(processed)
    name = next_receipt_name(update.effective_user.id, info.date)
    await message.reply_photo(
        photo=processed.read_bytes(),
        caption=f"Processed result\n\n{format_info(info, name)}\n\nIs this result OK?",
        reply_markup=review_keyboard(),
    )
    return REVIEW


async def review_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    action = query.data
    if action == "cancel":
        await query.edit_message_caption(caption="Cancelled. Nothing was saved.")
        return ConversationHandler.END
    if action == "edit_text":
        await query.message.reply_text("What do you want to edit?", reply_markup=edit_keyboard())
        return EDIT_FIELD
    if action in {"save_result", "save_original"}:
        use_original = action == "save_original"
        await save_current(update, context, use_original=use_original, photo_required=True)
        return ConversationHandler.END
    return REVIEW


async def edit_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    field = query.data.split(":", 1)[1]
    if field == "back":
        info = info_from_context(context)
        name = next_receipt_name(update.effective_user.id, info.date)
        await query.message.reply_text(
            f"{format_info(info, name)}\n\nIs this result OK?",
            reply_markup=review_keyboard(),
        )
        return REVIEW
    context.user_data["edit_field"] = field
    await query.message.reply_text(f"Send the new {field}.")
    return EDIT_FIELD


async def edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    field = context.user_data.get("edit_field")
    if not field:
        await update.message.reply_text("Choose a field first.", reply_markup=edit_keyboard())
        return EDIT_FIELD
    info = info_from_context(context)
    text = update.message.text.strip()
    if field == "amount":
        cleaned = text.replace(",", ".")
        info.amount = float(cleaned) if cleaned else None
    else:
        setattr(info, field, text or None)
    store_info(context, info)
    context.user_data.pop("edit_field", None)
    name = next_receipt_name(update.effective_user.id, info.date)
    await update.message.reply_text(
        f"Updated.\n\n{format_info(info, name)}\n\nIs this result OK?",
        reply_markup=review_keyboard(),
    )
    return REVIEW


async def save_current(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    use_original: bool,
    photo_required: bool,
) -> None:
    user_id = update.effective_user.id
    info = info_from_context(context)
    name = allocate_receipt_name(user_id, info.date)
    file_link = ""
    image_path = None
    if photo_required:
        key = "original" if use_original else "processed"
        image_path = Path(context.user_data[key])
        file_link = await asyncio.to_thread(upload_receipt_file, user_id, image_path, name)
    await asyncio.to_thread(
        append_sheet_row,
        user_id,
        name=name,
        date=info.date,
        category=info.category,
        amount=info.amount,
        currency=info.currency,
        merchant=info.merchant,
        file_link=file_link,
    )
    record = load_user(user_id)
    kind = "original photo" if use_original else "processed result"
    if not photo_required:
        kind = "text only"
    text = (
        f"Saved {name} ({kind}).\n\n"
        f"{format_info(info, name)}\n"
        f"File: {file_link or 'none'}\n"
        f"Sheet: {record.get('spreadsheet_url') or ''}"
    )
    message = update.effective_message
    if update.callback_query:
        await update.callback_query.edit_message_caption(caption=text)
    elif message:
        await message.reply_text(text)


@require_google
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    context.user_data["manual"] = True
    context.user_data["text_only"] = False
    store_info(context, ReceiptInfo())
    await update.message.reply_text("Manual add. Send the date as YYYY-MM-DD, or - to skip.")
    return ADD_DATE


@require_google
async def text_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    context.user_data["manual"] = True
    context.user_data["text_only"] = True
    store_info(context, ReceiptInfo())
    await update.message.reply_text("Text only. Send the date as YYYY-MM-DD, or - to skip.")
    return ADD_DATE


async def add_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    info = info_from_context(context)
    text = update.message.text.strip()
    info.date = None if text == "-" else text
    store_info(context, info)
    await update.message.reply_text("Category? For example groceries, drugstore, dining.")
    return ADD_CATEGORY


async def add_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    info = info_from_context(context)
    info.category = update.message.text.strip()
    store_info(context, info)
    await update.message.reply_text("Amount? Use a number like 9.95")
    return ADD_AMOUNT


async def add_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    info = info_from_context(context)
    raw = update.message.text.strip().replace(",", ".")
    try:
        info.amount = float(raw)
    except ValueError:
        await update.message.reply_text("That is not a number. Try again, for example 12.50")
        return ADD_AMOUNT
    store_info(context, info)
    await update.message.reply_text("Merchant name? Or - to skip.")
    return ADD_NOTE


async def add_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    info = info_from_context(context)
    text = update.message.text.strip()
    info.merchant = None if text == "-" else text
    store_info(context, info)
    if context.user_data.get("text_only"):
        await save_current(update, context, use_original=False, photo_required=False)
        return ConversationHandler.END
    await update.message.reply_text(
        f"{format_info(info)}\n\nSend a photo now, or tap Save text only.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Save text only", callback_data="save_text_only")]]
        ),
    )
    return REVIEW


async def attach_manual_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not context.user_data.get("manual"):
        return await handle_photo(update, context)
    user_dir = TMP_DIR / str(update.effective_user.id)
    user_dir.mkdir(parents=True, exist_ok=True)
    original = user_dir / "original.jpg"
    file = await update.message.photo[-1].get_file()
    await file.download_to_drive(original)
    context.user_data["original"] = str(original)
    context.user_data["processed"] = str(original)
    await save_current(update, context, use_original=True, photo_required=True)
    return ConversationHandler.END


async def save_text_only_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await save_current(update, context, use_original=False, photo_required=False)
    return ConversationHandler.END


@require_google
async def delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    rows = await asyncio.to_thread(list_records, update.effective_user.id)
    if not rows:
        await update.message.reply_text("There are no records yet.")
        return ConversationHandler.END
    preview = "\n".join(f"- {row[0]} | {row[1] if len(row) > 1 else ''} | {row[3] if len(row) > 3 else ''}" for row in rows[-10:])
    await update.message.reply_text(
        f"Recent records:\n{preview}\n\nSend the record name to delete, for example 1-09-2026"
    )
    return DELETE_NAME


async def delete_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    removed = await asyncio.to_thread(delete_record, update.effective_user.id, name)
    if removed:
        await update.message.reply_text(f"Removed {name} from the sheet and Drive.")
    else:
        await update.message.reply_text(f"No record named {name} was found.")
    return ConversationHandler.END


@require_google
async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rows = await asyncio.to_thread(list_records, update.effective_user.id)
    if not rows:
        await update.message.reply_text("There are no records yet.")
        return
    preview = "\n".join(
        f"{row[0]} | {row[1] if len(row) > 1 else ''} | {row[2] if len(row) > 2 else ''} | {row[3] if len(row) > 3 else ''}"
        for row in rows[-15:]
    )
    record = load_user(update.effective_user.id)
    await update.message.reply_text(f"{preview}\n\nSheet: {record.get('spreadsheet_url') or ''}")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


async def oauth_start(request: web.Request) -> web.Response:
    uid = request.query.get("uid")
    if not uid:
        return web.Response(text="Missing uid", status=400)
    raise web.HTTPFound(authorization_url(int(uid)))


async def oauth_callback(request: web.Request) -> web.Response:
    parsed = urlparse(str(request.url))
    state = parse_qs(parsed.query).get("state", [""])[0]
    if not state.isdigit():
        return web.Response(text="Invalid OAuth state", status=400)
    finish_oauth(int(state), str(request.url))
    return web.Response(
        text=(
            f"{APP_NAME} is connected. You can close this tab and return to Telegram. "
            "Send /start to the bot."
        ),
        content_type="text/plain",
    )


async def start_oauth_site(app: Application) -> None:
    base = public_base_url()
    parsed = urlparse(base)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    host = "0.0.0.0"
    site = web.Application()
    site.router.add_get("/oauth/start", oauth_start)
    site.router.add_get("/oauth/callback", oauth_callback)
    runner = web.AppRunner(site)
    await runner.setup()
    listener = web.TCPSite(runner, host=host, port=int(os_port(port)))
    await listener.start()
    log.info("OAuth server listening on %s:%s", host, port)
    app.bot_data["oauth_runner"] = runner


def os_port(port: int) -> int:
    return int(os.environ.get("OAUTH_PORT", port if port not in {80, 443} else 8080))


def build_application() -> Application:
    token = require("TELEGRAM_BOT_TOKEN")
    application = Application.builder().token(token).post_init(start_oauth_site).build()

    review_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.PHOTO, handle_photo),
            CommandHandler("add", add_start),
            CommandHandler("text", text_start),
            CommandHandler("delete", delete_start),
        ],
        states={
            REVIEW: [
                CallbackQueryHandler(save_text_only_callback, pattern="^save_text_only$"),
                CallbackQueryHandler(review_callback),
                MessageHandler(filters.PHOTO, attach_manual_photo),
            ],
            EDIT_FIELD: [
                CallbackQueryHandler(edit_choice, pattern="^edit:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_value),
            ],
            ADD_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_date)],
            ADD_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_category)],
            ADD_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_amount)],
            ADD_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_note)],
            DELETE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("connect", connect_cmd))
    application.add_handler(CommandHandler("list", list_cmd))
    application.add_handler(review_conv)
    return application


def main() -> None:
    application = build_application()
    log.info("Starting %s", APP_NAME)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
