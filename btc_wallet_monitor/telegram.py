from __future__ import annotations

import requests


class TelegramNotifier:
    def __init__(self, bot_token: str | None, chat_id: str | None, timeout_seconds: int = 15):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.timeout_seconds = timeout_seconds
        self.enabled = bool(bot_token and chat_id)

    def send_balance_alert(self, address: str, balance_sat: int, derivation_path: str) -> bool:
        if not self.enabled:
            return False

        btc = balance_sat / 100_000_000
        text = (
            "🟢 BTC wallet balance detected\n\n"
            f"Address: {address}\n"
            f"Balance: {btc:.8f} BTC ({balance_sat} sat)\n"
            f"Path: {derivation_path}"
        )
        response = requests.post(
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            json={"chat_id": self.chat_id, "text": text, "disable_web_page_preview": True},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return True
