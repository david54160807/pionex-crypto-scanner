from __future__ import annotations

import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
import requests

log = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self, token: str, chat_id: str) -> None:
        self.token = token
        self.chat_id = str(chat_id)
        self.base_url = f"https://api.telegram.org/bot{token}"

    def send_message(self, text: str) -> None:
        """Send a Telegram HTML-formatted message."""
        response = requests.post(
            f"{self.base_url}/sendMessage",
            json={
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML",
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

    @staticmethod
    def _format_test_signal() -> str:
        """建立純展示用的虛擬訊號，版面完全比照正式訊號。"""
        highs = [
            (98500.0, 1245.68, 72.40),
            (100200.0, 1018.35, 68.20),
            (102800.0, 862.91, 63.10),
        ]
        lows = [91200.0, 93100.0, 95400.0]
        lines = [
            "🤖派網加密貨幣掃描器",
            "━━━━━━━━━━━━━━━━━━",
            "⭐️ <b>BTC / USDT</b>",
            "",
            "🟢 策略判斷：全部條件符合",
            "",
            "📈 波段高點",
        ]
        for idx, (price, volume, rsi) in enumerate(highs, 1):
            lines.append(
                f"🔺 H{idx}｜{price:,.0f}｜量 {volume:,.2f}｜RSI {rsi:.2f}"
            )
        lines.extend(["", "📉 波段低點"])
        for idx, price in enumerate(lows, 1):
            lines.append(f"🔻 L{idx}｜{price:,.0f}")
        lines.extend([
            "━━━━━━━━━━━━━━━━━━",
            "⚙️ 版本 2.0",
            "⚠️ 此為虛擬測試訊號，非即時行情或真實交易訊號。",
        ])
        return "\n".join(lines)

    def handle_test_commands(self) -> int:
        """只接受設定的 chat_id 傳送的 TEST 指令，回覆完整虛擬交易訊號。"""
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
                self.send_message(self._format_test_signal())
                handled += 1
                log.info("已回覆 Telegram TEST 指令")

        # 確認已讀取的 updates，避免下一輪重複處理相同指令。
        self.acknowledge_updates(highest_update_id + 1)
        return handled
