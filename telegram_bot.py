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
        """建立純展示用的虛擬訊號；不讀取行情、不參與正式掃描。"""
        now = datetime.now(ZoneInfo("Asia/Taipei"))
        stamp = now.strftime("%Y-%m-%d %H:%M:%S")
        highs = [
            ("98,500", "1,245.6800", "72.40", "2026-11-10 06:00"),
            ("100,200", "1,018.3500", "68.20", "2026-11-10 18:00"),
            ("102,800", "862.9100", "63.10", "2026-11-11 02:00"),
        ]
        lows = [
            ("91,200", "2026-11-09 06:00"),
            ("93,100", "2026-11-09 18:00"),
            ("95,400", "2026-11-10 10:00"),
        ]
        lines = [
            "🟢 <b>PIONEX CRYPTO SCANNER</b>",
            "<code>4H TRADING SIGNAL · USDT PERPETUAL</code>",
            "━━━━━━━━━━━━━━━━━━",
            "🧪 <b>BTC / USDT</b>",
            "<b>策略狀態</b>　<code>ALL CONDITIONS PASSED</code>",
            "<b>通知類型</b>　<code>SIMULATED TEST SIGNAL</code>",
            "",
            "📈 <b>SWING HIGH｜三個波段高點</b>",
        ]
        for idx, (price, volume, rsi, point_time) in enumerate(highs, 1):
            lines.append(
                f"<b>H{idx}</b>　<code>{price}</code>\n"
                f"　　成交量 <code>{volume}</code>　｜ RSI <code>{rsi}</code>\n"
                f"　　<i>{point_time}（台灣）</i>"
            )
        lines.extend(["", "📉 <b>SWING LOW｜三個波段低點</b>"])
        for idx, (price, point_time) in enumerate(lows, 1):
            lines.append(
                f"<b>L{idx}</b>　<code>{price}</code>　｜ "
                f"<i>{point_time}（台灣）</i>"
            )
        lines.extend([
            "━━━━━━━━━━━━━━━━━━",
            "📍 <b>最新市場數據（虛擬）</b>",
            "最新已收盤價　<code>99,600</code>",
            "最新 RSI(14)　 <code>59.80</code>",
            f"🕒 測試時間　<i>{stamp} 台灣時間</i>",
            "",
            "⚠️ <b>此為虛擬測試訊號</b>",
            "<i>數據純屬示範，非即時行情、非真實交易訊號，不會觸發下單。</i>",
            "<code>PIONEX SCANNER · V2.0</code>",
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
