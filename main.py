from __future__ import annotations

import logging
from html import escape
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
    symbol = escape(item["symbol"].replace("_", "/"))
    lines = [
        "🟢 <b>PIONEX CRYPTO SCANNER</b>",
        "<code>4H TRADING SIGNAL · USDT PERPETUAL</code>",
        "━━━━━━━━━━━━━━━━━━",
        f"🚀 <b>{symbol}</b>",
        "<b>策略狀態</b>　<code>ALL CONDITIONS PASSED</code>",
        "",
        "📈 <b>SWING HIGH｜三個波段高點</b>",
    ]
    for idx, point in enumerate(item["highs"], 1):
        lines.append(
            f"<b>H{idx}</b>　<code>{fmt_price(point['price'])}</code>\n"
            f"　　成交量 <code>{point['volume']:,.4f}</code>"
            f"　｜ RSI <code>{point['rsi']:.2f}</code>\n"
            f"　　<i>{point['time_local']}（台灣）</i>"
        )

    lines.extend(["", "📉 <b>SWING LOW｜三個波段低點</b>"])
    for idx, point in enumerate(item["lows"], 1):
        lines.append(
            f"<b>L{idx}</b>　<code>{fmt_price(point['price'])}</code>"
            f"　｜ <i>{point['time_local']}（台灣）</i>"
        )

    lines.extend([
        "━━━━━━━━━━━━━━━━━━",
        "📍 <b>最新市場數據</b>",
        f"最新已收盤價　<code>{fmt_price(item['last_close'])}</code>",
        f"最新 RSI(14)　 <code>{item['last_rsi']:.2f}</code>",
        f"🕒 掃描時間　<i>{datetime.now(TAIPEI).strftime('%Y-%m-%d %H:%M:%S')} 台灣時間</i>",
        "",
        "⚠️ <i>此為技術型態篩選通知，不構成買賣建議。</i>",
        "<code>PIONEX SCANNER · V2.0</code>",
    ])
    return "\n".join(lines)


def format_scan_summary(
    market_count: int,
    scanned: int,
    found_count: int,
    sent_count: int,
    send_errors: int,
    scan_errors: int,
) -> str:
    now_text = datetime.now(TAIPEI).strftime("%Y-%m-%d %H:%M:%S")
    scan_status = "🟢 正常完成" if scan_errors == 0 else "🟡 完成，部分合約有錯誤"
    notify_status = "🟢 正常" if send_errors == 0 else "🔴 有發送失敗"
    return "\n".join([
        "🔎 <b>PIONEX CRYPTO SCANNER</b>",
        "<code>4H MARKET SCAN · USDT PERPETUAL</code>",
        "━━━━━━━━━━━━━━━━━━",
        f"🟢 <b>全市場掃描完成</b>　<code>{now_text} 台灣時間</code>",
        "",
        "📊 <b>市場掃描統計</b>",
        f"├ 掃描合約　　<code>{market_count:,}</code>",
        f"├ 成功取得 K 線　<code>{scanned:,}</code>",
        f"├ 符合策略　　<code>{found_count:,}</code>",
        f"└ 掃描錯誤　　<code>{scan_errors:,}</code>",
        "",
        "📨 <b>Telegram 通知統計</b>",
        f"├ 通知成功　　<code>{sent_count:,}</code>",
        f"└ 通知失敗　　<code>{send_errors:,}</code>",
        "",
        "🛠 <b>系統狀態</b>",
        f"├ 掃描狀態　{scan_status}",
        f"└ 通知狀態　{notify_status}",
        "━━━━━━━━━━━━━━━━━━",
        "<i>本工具僅進行型態篩選與訊息通知，不會自動下單。</i>",
        "<code>PIONEX SCANNER · V2.0</code>",
    ])


def main() -> int:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        log.error("缺少 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID GitHub Secrets")
        return 2

    client = PionexClient()
    bot = TelegramBot(token, chat_id)

    # 每次 workflow 執行時輪詢 Telegram 的 TEST 指令。
    # GitHub Actions 每 30 分鐘執行，因此不是即時 webhook 回覆。
    try:
        test_count = bot.handle_test_commands()
        if test_count:
            log.info("本輪處理 %d 個 Telegram TEST 指令", test_count)
    except Exception:
        log.exception("讀取或回覆 Telegram TEST 指令失敗")

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

    # 不做去重：每輪掃描符合條件的幣種都重新通知。
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

    if os.getenv("SEND_SCAN_SUMMARY", "true").lower() == "true":
        try:
            bot.send_message(
                format_scan_summary(
                    market_count=len(symbols),
                    scanned=scanned,
                    found_count=len(found),
                    sent_count=sent_count,
                    send_errors=send_errors,
                    scan_errors=errors,
                )
            )
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
