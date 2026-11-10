from __future__ import annotations

import json
import logging
import requests

log = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self, token: str, chat_id: str) -> None:
        self.token = token
        self.chat_id = str(chat_id)
        self.base_url = f"https://api.telegram.org/bot{token}"

    def send_message(self, text: str) -> None:
        response = requests.post(
            f"{self.base_url}/sendMessage",
            json={
                "chat_id": self.chat_id,
                "text": text,
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            raise RuntimeError(f"Telegram API 發送失敗：{payload}")

    def get_updates(self, offset: int | None = None) -> list[dict]:
        params = {"timeout": 0, "allowed_updates": json.dumps(["message"])}
        if offset is not None:
            params["offset"] = offset
        response = requests.get(
            f"{self.base_url}/getUpdates",
            params=params,
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            raise RuntimeError(f"Telegram getUpdates 失敗：{payload}")
        return payload.get("result", [])

    def acknowledge_updates(self, next_offset: int) -> None:
        # Telegram 會在收到更大的 offset 時確認先前收到的 updates。
        self.get_updates(offset=next_offset)

    def handle_test_commands(self) -> int:
        """只接受設定的 chat_id 傳送的 TEST 指令。"""
        updates = self.get_updates()
        if not updates:
            return 0

        update_ids = [
            int(update["update_id"])
            for update in updates if "update_id" in update
        ]
        if not update_ids:
            return 0

        highest_update_id = max(update_ids)
        handled = 0

        for update in updates:
            message = update.get("message") or {}
            text = str(message.get("text", "")).strip()
            chat = message.get("chat") or {}
            incoming_chat_id = str(chat.get("id", ""))

            if incoming_chat_id == self.chat_id and text.upper() == "TEST":
                self.send_message(
                    "🧪 PIONEX CRYPTO SCANNER｜TEST 測試通知\\n"
                    "━━━━━━━━━━━━━━━━━━\\n"
                    "✅ Telegram 訊息發送成功！\\n"
                    "✅ Bot 指令接收成功！\\n"
                    "✅ GitHub Actions 與 Telegram 通訊正常。\\n"
                    "━━━━━━━━━━━━━━━━━━\\n"
                    "這是一則測試訊息，不是交易訊號。\\n"
                    "不會觸發任何下單。"
                )
                handled += 1
                log.info("已回覆 Telegram TEST 指令")

        # 確認已讀取的 updates，避免下一輪重複處理相同指令。
        self.acknowledge_updates(highest_update_id + 1)
        return handled
