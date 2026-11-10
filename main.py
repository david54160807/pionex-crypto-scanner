from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from pionex_api import PionexClient, RateLimitError
from strategy import analyze_symbol
from telegram_bot import TelegramBot

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("scanner")
TAIPEI = ZoneInfo("Asia/Taipei")


def fmt_price(value: float) -> str:
    return f"{value:,.10f}".rstrip("0").rstrip(".")


def format_signal(item: dict) -> str:
    lines = [
        "🟢 PIONEX 4H 型態掃描｜策略符合",
        f"幣種：{item['symbol'].replace('_', '/')}",
        "判斷：四項策略條件全部符合",
        "",
        "【三個波段高點】",
    ]

    for idx, point in enumerate(item["highs"], 1):
        lines.append(
            f"H{idx} {fmt_price(point['price'])}"
            f"｜成交量 {point['volume']:,.4f}"
            f"｜RSI {point['rsi']:.2f}"
            f"｜{point['time_local']}"
        )

    lines.extend(["", "【三個波段低點】"])

    for idx, point in enumerate(item["lows"], 1):
        lines.append(
            f"L{idx} {fmt_price(point['price'])}"
            f"｜{point['time_local']}"
        )

    lines.extend([
        "",
        f"最新已收盤價：{fmt_price(item['last_close'])}",
        f"最新 RSI(14)：{item['last_rsi']:.2f}",
        f"掃描時間：{datetime.now(TAIPEI).strftime('%Y-%m-%d %H:%M:%S')} 台灣時間",
        "",
        "⚠️ 此為型態篩選通知，不代表買進、做多或做空建議。",
    ])
    return "\n".join(lines)


def main() -> int:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat_id:
        log.error("缺少 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID GitHub Secrets")
        return 2

    client = PionexClient()
    bot = TelegramBot(token, chat_id)

    try:
        symbols = client.get_trading_perpetual_symbols()
    except Exception:
        log.exception("取得 Pionex USDT 永續合約清單失敗")
        return 1

    if not symbols:
        log.error("Pionex 回傳的可交易 USDT 永續合約清單為空")
        return 1

    log.info("開始掃描 %d 個 USDT 永續合約", len(symbols))

    now_ms = int(time.time() * 1000)
    found: list[dict] = []
    errors = 0
    scanned = 0

    # 單線程逐一請求，沿用先前已驗證的限流保護。
    for symbol in symbols:
        try:
            klines = client.get_4h_klines(symbol)
            scanned += 1

            result = analyze_symbol(symbol, klines, now_ms=now_ms)
            if result is not None:
                found.append(result)

            if scanned % 25 == 0:
                log.info(
                    "掃描進度：%d/%d，符合策略：%d",
                    scanned, len(symbols), len(found)
                )

        except RateLimitError:
            log.exception("Pionex 持續 HTTP 429，停止本輪掃描")
            return 1
        except Exception as exc:
            errors += 1
            log.warning("%s 掃描失敗：%s", symbol, exc)

    found.sort(key=lambda item: item["symbol"])

    log.info(
        "掃描完成：市場 %d、成功取得K線 %d、符合 %d、錯誤 %d",
        len(symbols), scanned, len(found), errors
    )

    # V2.0：完全不做去重。每次掃描符合條件的幣種都重新通知。
    sent_count = 0
    send_errors = 0

    for item in found:
        try:
            bot.send_message(format_signal(item))
            sent_count += 1
            log.info("Telegram 通知成功：%s", item["symbol"])
            time.sleep(0.2)
        except Exception:
            send_errors += 1
            log.exception("Telegram 通知失敗：%s", item["symbol"])

    if not found:
        log.info("本輪沒有符合策略的幣種")

    if os.getenv("SEND_SCAN_SUMMARY", "false").lower() == "true":
        summary = (
            "🔎 Pionex 4H 全市場掃描完成\n"
            f"掃描合約：{len(symbols)}\n"
            f"成功取得K線：{scanned}\n"
            f"符合策略：{len(found)}\n"
            f"通知成功：{sent_count}\n"
            f"通知失敗：{send_errors}\n"
            f"掃描錯誤：{errors}"
        )
        try:
            bot.send_message(summary)
        except Exception:
            send_errors += 1
            log.exception("Telegram 掃描統計通知失敗")

    log.info(
        "本輪結束：符合 %d 個，通知成功 %d 個，通知失敗 %d 個",
        len(found), sent_count, send_errors
    )

    return 1 if send_errors else 0


if __name__ == "__main__":
    sys.exit(main())
