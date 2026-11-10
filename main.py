from __future__ import annotations
import json, logging, os, sys, time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from pionex_api import PionexClient, RateLimitError
from strategy import analyze_symbol
from telegram_bot import TelegramBot

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(),
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("scanner")
STATE_PATH = Path("state.json")
TAIPEI = ZoneInfo("Asia/Taipei")

def load_state():
    if not STATE_PATH.exists():
        return {"sent": {}}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"sent": {}}
    except Exception:
        log.exception("state.json 無法讀取，使用空狀態")
        return {"sent": {}}

def save_state(state):
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

def fmt_price(value):
    return f"{value:,.8f}".rstrip("0").rstrip(".")

def format_signal(item):
    lines = ["🟢 PIONEX 4H 型態掃描｜新訊號",
             f"幣種：{item['symbol'].replace('_', '/')}",
             "判斷：四項策略條件全部符合", "", "【三個波段高點】"]
    for idx, p in enumerate(item["highs"], 1):
        lines.append(f"H{idx} {fmt_price(p['price'])}｜量 {p['volume']:,.4f}｜RSI {p['rsi']:.2f}｜{p['time_local']}")
    lines += ["", "【三個波段低點】"]
    for idx, p in enumerate(item["lows"], 1):
        lines.append(f"L{idx} {fmt_price(p['price'])}｜{p['time_local']}")
    lines += ["", f"最新收盤：{fmt_price(item['last_close'])}",
              f"最新 RSI(14)：{item['last_rsi']:.2f}",
              f"掃描時間：{datetime.now(TAIPEI).strftime('%Y-%m-%d %H:%M:%S')} 台灣時間",
              "", "⚠️ 型態篩選訊號，不代表買進/做多建議。"]
    return "\n".join(lines)

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        log.error("缺少 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID Secrets")
        return 2
    client, bot = PionexClient(), TelegramBot(token, chat_id)
    try:
        symbols = client.get_trading_perpetual_symbols()
    except Exception:
        log.exception("取得 Pionex 永續合約清單失敗")
        return 1
    if not symbols:
        log.error("Pionex 回傳的可交易永續合約清單為空")
        return 1

    log.info("開始掃描 %d 個 USDT 永續合約", len(symbols))
    state = load_state()
    sent = state.setdefault("sent", {})
    now_ms = int(time.time() * 1000)
    found, errors, scanned = [], 0, 0

    # 單線程逐一請求；K線 API Weight=5，請求間隔 1.15 秒。
    # 若冷卻後仍持續 429，立即停止，避免延長 IP 限流。
    for symbol in symbols:
        try:
            klines = client.get_4h_klines(symbol)
            scanned += 1
            result = analyze_symbol(symbol, klines, now_ms=now_ms)
            if result:
                found.append(result)
            if scanned % 25 == 0:
                log.info("掃描進度：%d/%d，符合 %d", scanned, len(symbols), len(found))
        except RateLimitError:
            log.exception("Pionex 持續限流，停止本輪掃描；請稍後再執行")
            return 1
        except Exception as exc:
            errors += 1
            log.warning("%s 掃描失敗：%s", symbol, exc)

    found.sort(key=lambda x: x["symbol"])
    new_signals = [x for x in found if sent.get(x["symbol"]) != x["signal_key"]]
    log.info("掃描完成：市場 %d、成功取得K線 %d、符合 %d、新訊號 %d、錯誤 %d",
             len(symbols), scanned, len(found), len(new_signals), errors)

    if new_signals:
        for item in new_signals:
            bot.send_message(format_signal(item))
            sent[item["symbol"]] = item["signal_key"]
            time.sleep(0.15)
        save_state(state)
    else:
        log.info("沒有新訊號，不發送重複通知")

    if os.getenv("SEND_SCAN_SUMMARY", "false").lower() == "true":
        bot.send_message("🔎 Pionex 4H 全市場掃描完成\n"
                         f"掃描合約：{len(symbols)}\n成功取得K線：{scanned}\n"
                         f"目前符合：{len(found)}\n新訊號：{len(new_signals)}\n錯誤：{errors}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
