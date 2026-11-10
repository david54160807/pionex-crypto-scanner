"""一次性工具：先在 Telegram 對自己的 Bot 按 Start 並傳送 /start，再執行本程式。"""
import os
import requests

token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
if not token:
    raise SystemExit("請先設定環境變數 TELEGRAM_BOT_TOKEN")

url = f"https://api.telegram.org/bot{token}/getUpdates"
data = requests.get(url, timeout=20).json()
if not data.get("ok"):
    raise SystemExit(f"Telegram API 錯誤：{data}")

chats = {}
for update in data.get("result", []):
    message = update.get("message") or update.get("channel_post")
    if not message:
        continue
    chat = message.get("chat", {})
    if "id" in chat:
        chats[str(chat["id"])] = {
            "type": chat.get("type"),
            "username": chat.get("username"),
            "first_name": chat.get("first_name"),
        }

if not chats:
    print("尚未取得訊息。請先打開你的 Bot，按 Start 並傳送 /start，再重新執行。")
else:
    print("找到以下 chat_id，請選擇你自己的私人聊天 ID：")
    for chat_id, info in chats.items():
        print(chat_id, info)
