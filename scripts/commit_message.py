#!/usr/bin/env python3
"""Build a short commit title from the staged git diff."""

from __future__ import annotations

import subprocess
from pathlib import Path


def run(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def staged_files() -> list[str]:
    return [line for line in run("diff", "--cached", "--name-only").splitlines() if line]


def added_lines() -> list[str]:
    lines: list[str] = []
    for raw in run("diff", "--cached").splitlines():
        if raw.startswith("+") and not raw.startswith("+++"):
            text = raw[1:].strip()
            if text:
                lines.append(text)
    return lines


def looks_like_rename(added: list[str]) -> bool:
    return any("Receipt Scanner Automation RSA" in line for line in added)


def title_for_files(files: list[str], added: list[str]) -> str:
    names = {Path(path).name for path in files}

    if names == {"install.sh"}:
        joined = "\n".join(added)
        if "already_installed" in joined or "Uninstall" in joined or "/dev/tty" in joined:
            return "Fix installer token prompts and add reinstall/uninstall"
        if looks_like_rename(added):
            return "Rename installer to Receipt Scanner Automation RSA"
        if "raw.githubusercontent.com" in joined:
            return "Make the Ubuntu installer clone and set up from GitHub"
        return "Update Ubuntu installer"

    if names == {"README.md"}:
        joined = "\n".join(added)
        if "reinstall" in joined.lower() or "uninstall" in joined.lower():
            return "Document installer reinstall and uninstall options"
        if looks_like_rename(added):
            return "Rename README to Receipt Scanner Automation RSA"
        if "curl -fsSL" in joined:
            return "Add one-line Ubuntu install command to the README"
        return "Update project README"

    if names <= {"bot.py", "config.py"} and looks_like_rename(added):
        return "Rename project to Receipt Scanner Automation RSA"

    if names & {"install.sh", "README.md", ".gitignore"} and "curl -fsSL" in "\n".join(added):
        return "Add one-line Ubuntu install and keep tokens out of git"

    if names <= {"commit_message.py", "autocommit.sh", "auto-commit.sh"} or (
        "commit_message.py" in names
    ):
        return "Generate auto-commit messages from the actual changes"

    joined = "\n".join(added)
    if "bot.py" in names:
        if "normalize_edit_field" in joined or "EDIT_FIELD" in joined:
            return "Add AI-normalized button editing for receipt fields"
        if "manual_review_keyboard" in joined or "extract_receipt_from_text" in joined:
            return "Add AI manual text entry and photo attach flows"
        if "persist_review_session" in joined or "attach_photo_to_record" in joined:
            return "Keep photos during edits and link scans to existing rows"
        if "BOT_COMMANDS" in joined or "main_menu_keyboard" in joined:
            return "Add Telegram command menu and reply keyboard"
        if "edit_callback_message" in joined:
            return "Fix save-after-edit for text and photo review messages"
        return "Improve Telegram bot review and save flows"

    if "google_services.py" in names:
        if "code_verifier" in joined or "_pending_oauth" in joined:
            return "Fix Google OAuth PKCE session handling"
        if "attach_photo_to_record" in joined:
            return "Support attaching or replacing receipt photos in Drive"
        if "receipt_number" in joined:
            return "Use numeric receipt names and formatted sheet dates"
        return "Improve Google Drive and Sheets integration"

    if "extract_receipt.py" in names and "normalize_edit_field" in joined:
        return "Add Gemini helpers for text parse and field normalization"

    if names == {".env.example"} or (".env.example" in names and "README.md" in names):
        return "Document env vars and replace real server IP in README"

    if names == {".gitignore"} and ".env.local" in joined:
        return "Tighten gitignore for local env files"

    pretty = ", ".join(sorted(names))
    if len(files) == 1:
        return f"Update {pretty}"
    return f"Update {pretty}"


def main() -> None:
    files = staged_files()
    if not files:
        print("Update project files")
        return
    print(title_for_files(files, added_lines()))


if __name__ == "__main__":
    main()
