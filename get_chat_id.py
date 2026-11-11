from __future__ import annotations

import os
import requests


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("請先設定 TELEGRAM_BOT_TOKEN 環境變數。")

    response = requests.get(
        f"https://api.telegram.org/bot{token}/getUpdates",
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise SystemExit(f"Telegram API 錯誤：{payload}")

    if not payload.get("result"):
        print("目前沒有收到訊息。請先對 Bot 傳送 /start，再重新執行。")
        return

    for update in payload["result"]:
        message = update.get("message") or update.get("channel_post") or {}
        chat = message.get("chat", {})
        if chat:
            print(
                f"chat_id: {chat.get('id')} | "
                f"type: {chat.get('type')} | "
                f"title: {chat.get('title', '')}"
            )


if __name__ == "__main__":
    main()
