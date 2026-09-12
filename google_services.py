"""Google OAuth, Drive uploads, and Sheets rows for RSA."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from config import (
    APP_NAME,
    DRIVE_FOLDER_NAME,
    SCOPES,
    SHEET_TITLE,
    require,
)
from storage import load_user, save_user

SHEET_HEADERS = [
    "Name",
    "Date",
    "Category",
    "Amount",
    "Currency",
    "Merchant",
    "File link",
    "Created",
]


def public_base_url() -> str:
    return require("PUBLIC_BASE_URL").rstrip("/")


def redirect_uri() -> str:
    return f"{public_base_url()}/oauth/callback"


def _client_config() -> dict[str, Any]:
    return {
        "web": {
            "client_id": require("GOOGLE_CLIENT_ID"),
            "client_secret": require("GOOGLE_CLIENT_SECRET"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri()],
        }
    }


def authorization_url(telegram_id: int) -> str:
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES)
    flow.redirect_uri = redirect_uri()
    url, _state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=str(telegram_id),
    )
    return url


def credentials_from_record(record: dict[str, Any]) -> Credentials | None:
    data = record.get("google")
    if not data:
        return None
    creds = Credentials.from_authorized_user_info(data, scopes=SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        record["google"] = json_credentials(creds)
        save_user(record)
    return creds


def json_credentials(creds: Credentials) -> dict[str, Any]:
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or SCOPES),
    }


def finish_oauth(telegram_id: int, callback_url: str) -> dict[str, Any]:
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES)
    flow.redirect_uri = redirect_uri()
    flow.fetch_token(authorization_response=callback_url)
    record = load_user(telegram_id)
    record["google"] = json_credentials(flow.credentials)
    save_user(record)
    ensure_google_workspace(telegram_id)
    return load_user(telegram_id)


def _services(record: dict[str, Any]):
    creds = credentials_from_record(record)
    if creds is None:
        raise RuntimeError("Google account is not connected.")
    return build("drive", "v3", credentials=creds), build(
        "sheets", "v4", credentials=creds
    )


def ensure_google_workspace(telegram_id: int) -> dict[str, Any]:
    record = load_user(telegram_id)
    drive, sheets = _services(record)
    if not record.get("folder_id"):
        created = (
            drive.files()
            .create(
                body={"name": DRIVE_FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder"},
                fields="id",
            )
            .execute()
        )
        record["folder_id"] = created["id"]
    if not record.get("spreadsheet_id"):
        created = (
            sheets.spreadsheets()
            .create(
                body={"properties": {"title": SHEET_TITLE}},
                fields="spreadsheetId,spreadsheetUrl",
            )
            .execute()
        )
        record["spreadsheet_id"] = created["spreadsheetId"]
        record["spreadsheet_url"] = created.get("spreadsheetUrl")
        sheets.spreadsheets().values().update(
            spreadsheetId=record["spreadsheet_id"],
            range="A1:H1",
            valueInputOption="RAW",
            body={"values": [SHEET_HEADERS]},
        ).execute()
        drive.files().update(
            fileId=record["spreadsheet_id"],
            addParents=record["folder_id"],
            fields="id,parents",
        ).execute()
    save_user(record)
    return record


def receipt_name(number: int, date_text: str | None) -> str:
    month, year = _month_year(date_text)
    return f"{number}-{month}-{year}"


def _month_year(date_text: str | None) -> tuple[str, str]:
    if date_text:
        match = re.search(r"(\d{4})-(\d{2})", date_text)
        if match:
            return match.group(2), match.group(1)
        match = re.search(r"(\d{2})[./](\d{4})", date_text)
        if match:
            return match.group(1), match.group(2)
    now = datetime.now()
    return f"{now.month:02d}", str(now.year)


def next_receipt_name(telegram_id: int, date_text: str | None) -> str:
    record = load_user(telegram_id)
    number = int(record.get("next_number") or 1)
    return receipt_name(number, date_text)


def allocate_receipt_name(telegram_id: int, date_text: str | None) -> str:
    record = load_user(telegram_id)
    number = int(record.get("next_number") or 1)
    name = receipt_name(number, date_text)
    record["next_number"] = number + 1
    save_user(record)
    return name


def upload_receipt_file(telegram_id: int, path: Path, name: str) -> str:
    record = ensure_google_workspace(telegram_id)
    drive, _sheets = _services(record)
    media = MediaFileUpload(str(path), mimetype="image/jpeg", resumable=True)
    uploaded = (
        drive.files()
        .create(
            body={"name": f"{name}{path.suffix or '.jpg'}", "parents": [record["folder_id"]]},
            media_body=media,
            fields="id,webViewLink,webContentLink",
        )
        .execute()
    )
    drive.permissions().create(
        fileId=uploaded["id"],
        body={"type": "anyone", "role": "reader"},
    ).execute()
    return uploaded.get("webViewLink") or uploaded.get("webContentLink") or ""


def append_sheet_row(
    telegram_id: int,
    *,
    name: str,
    date: str | None,
    category: str | None,
    amount: float | None,
    currency: str | None,
    merchant: str | None,
    file_link: str,
) -> None:
    record = ensure_google_workspace(telegram_id)
    _drive, sheets = _services(record)
    created = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    sheets.spreadsheets().values().append(
        spreadsheetId=record["spreadsheet_id"],
        range="A:H",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={
            "values": [
                [
                    name,
                    date or "",
                    category or "",
                    amount if amount is not None else "",
                    currency or "",
                    merchant or "",
                    file_link,
                    created,
                ]
            ]
        },
    ).execute()


def list_records(telegram_id: int) -> list[list[str]]:
    record = ensure_google_workspace(telegram_id)
    _drive, sheets = _services(record)
    result = (
        sheets.spreadsheets()
        .values()
        .get(spreadsheetId=record["spreadsheet_id"], range="A2:H")
        .execute()
    )
    return result.get("values") or []


def delete_record(telegram_id: int, name: str) -> bool:
    record = ensure_google_workspace(telegram_id)
    drive, sheets = _services(record)
    rows = list_records(telegram_id)
    row_index = None
    file_link = ""
    for offset, row in enumerate(rows, start=2):
        if row and row[0] == name:
            row_index = offset
            file_link = row[6] if len(row) > 6 else ""
            break
    if row_index is None:
        return False
    meta = sheets.spreadsheets().get(spreadsheetId=record["spreadsheet_id"]).execute()
    sheet_id = meta["sheets"][0]["properties"]["sheetId"]
    sheets.spreadsheets().batchUpdate(
        spreadsheetId=record["spreadsheet_id"],
        body={
            "requests": [
                {
                    "deleteDimension": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "ROWS",
                            "startIndex": row_index - 1,
                            "endIndex": row_index,
                        }
                    }
                }
            ]
        },
    ).execute()
    if file_link or name:
        query = (
            f"name contains '{name}' and '{record['folder_id']}' in parents "
            "and trashed = false"
        )
        found = drive.files().list(q=query, fields="files(id,name)").execute()
        for item in found.get("files") or []:
            drive.files().delete(fileId=item["id"]).execute()
    return True
