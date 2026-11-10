from __future__ import annotations

import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from pionex_api import PionexClient
from strategy import analyze_symbol
from telegram_bot import TelegramBot

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("scanner")

STATE_PATH = Path("state.json")
TAIPEI = ZoneInfo("Asia/Taipei")


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"sent": {}}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"sent": {}}
    except Exception:
        log.exception("state.json 無法讀取，使用空狀態")
        return {"sent": {}}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        log.error("缺少 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID Secrets")
        return 2

    client = PionexClient()
    bot = TelegramBot(token, chat_id)

    try:
        symbols = client.get_trading_perpetual_symbols()
    except Exception:
        log.exception("取得 Pionex 永續合約清單失敗")
        return 1

    if not symbols:
        log.error("Pionex 回傳的可交易永續合約清單為空，停止掃描")
        return 1

    log.info("開始掃描 %s 個 USDT 永續合約", len(symbols))
    state = load_state()
    sent = state.setdefault("sent", {})
    now_ms = int(time.time() * 1000)
    found = []
    errors = 0

    # 保守限制併發數，降低對交易所公開 API 的瞬間請求壓力。
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(client.get_4h_klines, symbol): symbol
            for symbol in symbols
        }
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                klines = future.result()
                result = analyze_symbol(symbol, klines, now_ms=now_ms)
                if result:
                    found.append(result)
            except Exception as exc:
                errors += 1
                log.warning("%s 掃描失敗：%s", symbol, exc)

    found.sort(key=lambda x: x["symbol"])
    new_signals = []
    for item in found:
        key = item["signal_key"]
        if sent.get(item["symbol"]) != key:
            new_signals.append(item)
            sent[item["symbol"]] = key

    # 只有成功推送新訊號後才更新 state.json，避免每30分鐘都產生一次無意義 commit。
    # 若 Telegram 發送失敗，不寫入該訊號的去重狀態，下次掃描會再嘗試通知。
    log.info(
        "掃描完成：市場 %d、符合 %d、新訊號 %d、錯誤 %d",
        len(symbols), len(found), len(new_signals), errors
    )

    if new_signals:
        successfully_sent = []
        for item in new_signals:
            try:
                bot.send_message(format_signal(item))
                successfully_sent.append(item)
                time.sleep(0.15)
            except Exception:
                log.exception("Telegram 通知失敗：%s", item["symbol"])
                return 1
        for item in successfully_sent:
            sent[item["symbol"]] = item["signal_key"]
        save_state(state)
    else:
        log.info("沒有新訊號，不發送重複通知")

    # 每次執行均寫入摘要到 Actions log；不將「符合但已通知」重複推送。
    if os.getenv("SEND_SCAN_SUMMARY", "false").lower() == "true":
        bot.send_message(
            "🔎 Pionex 4H 全市場掃描完成\n"
            f"掃描合約：{len(symbols)}\n"
            f"目前符合：{len(found)}\n"
            f"本次新訊號：{len(new_signals)}\n"
            f"資料錯誤：{errors}\n"
            f"時間：{datetime.now(TAIPEI).strftime('%Y-%m-%d %H:%M:%S')} 台灣時間"
        )

    return 0


def fmt_price(value: float) -> str:
    return f"{value:,.8f}".rstrip("0").rstrip(".")


def format_signal(item: dict) -> str:
    highs = item["highs"]
    lows = item["lows"]
    taipei_time = datetime.now(TAIPEI).strftime("%Y-%m-%d %H:%M")
    lines = [
        "🟢 PIONEX 4H 型態掃描｜新訊號",
        f"幣種：{item['symbol'].replace('_', '/')}",
        "判斷：四項策略條件全部符合",
        "",
        "【三個波段高點】",
    ]
    for idx, p in enumerate(highs, 1):
        lines.append(
            f"H{idx} {fmt_price(p['price'])}｜"
            f"量 {p['volume']:,.4f}｜RSI {p['rsi']:.2f}｜{p['time_local']}"
        )
    lines += ["", "【三個波段低點】"]
    for idx, p in enumerate(lows, 1):
        lines.append(f"L{idx} {fmt_price(p['price'])}｜{p['time_local']}")
    lines += [
        "",
        f"最新收盤：{fmt_price(item['last_close'])}",
        f"最新 RSI(14)：{item['last_rsi']:.2f}",
        f"掃描時間：{taipei_time} 台灣時間",
        "",
        "⚠️ 型態篩選訊號，不代表買進/做多建議；請自行檢查流動性、資金費率及網格風險。",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
