from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    db_path: str
    mempool_api_base: str
    scan_interval_seconds: int
    request_timeout_seconds: int
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    master_password_file: str | None


def load_settings() -> Settings:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or None
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip() or None
    secret_file = os.getenv("MASTER_PASSWORD_FILE", "").strip() or None

    return Settings(
        db_path=os.getenv("DB_PATH", "/data/wallet.db"),
        mempool_api_base=os.getenv("MEMPOOL_API_BASE", "https://mempool.space/api").rstrip("/"),
        scan_interval_seconds=max(5, int(os.getenv("SCAN_INTERVAL_SECONDS", "60"))),
        request_timeout_seconds=max(1, int(os.getenv("REQUEST_TIMEOUT_SECONDS", "15"))),
        telegram_bot_token=token,
        telegram_chat_id=chat_id,
        master_password_file=secret_file,
    )


def read_master_password(settings: Settings, allow_env: bool = True) -> str | None:
    if settings.master_password_file:
        path = Path(settings.master_password_file)
        if path.exists():
            value = path.read_text(encoding="utf-8").rstrip("\r\n")
            if value:
                return value

    if allow_env:
        value = os.getenv("MASTER_PASSWORD", "").strip()
        if value:
            return value

    return None
