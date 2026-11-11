from __future__ import annotations

import logging
import json
import base64
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
    """正式訊號：依使用者指定的固定版面輸出，不增加其他欄位。"""
    symbol = escape(item["symbol"].replace("_", " / ").replace("/", " / "))
    # 正規化常見的 BTC_USDT / BTC/USDT，避免斜線重複。
    symbol = " / ".join(part.strip() for part in symbol.split("/"))
    lines = [
        "🤖派網加密貨幣掃描器",
        "━━━━━━━━━━━━━━━━━━",
        f"⭐️ <b>{symbol}</b>",
        "",
        "🟢 策略判斷：全部條件符合",
        "",
        "📈 波段高點",
    ]
    for idx, point in enumerate(item["highs"], 1):
        lines.append(
            f"🔺 H{idx}｜{fmt_price(point['price'])}｜"
            f"量 {point['volume']:,.2f}｜RSI {point['rsi']:.2f}"
        )

    lines.extend(["", "📉 波段低點"])
    for idx, point in enumerate(item["lows"], 1):
        lines.append(f"🔻 L{idx}｜{fmt_price(point['price'])}")

    lines.extend([
        "━━━━━━━━━━━━━━━━━━",
        "⚙️ 版本 2.1",
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
        "<code>PIONEX SCANNER · V2.1</code>",
    ])



def log_github_run_diagnostics() -> dict:
    """記錄 GitHub Actions 觸發方式與排隊時間；診斷失敗不影響掃描。"""
    import requests
    from datetime import timezone

    info = {
        "event": os.getenv("GITHUB_EVENT_NAME", "local"),
        "run_id": os.getenv("GITHUB_RUN_ID", ""),
        "run_number": os.getenv("GITHUB_RUN_NUMBER", ""),
        "run_attempt": os.getenv("GITHUB_RUN_ATTEMPT", ""),
        "queue_seconds": None,
    }
    log.info(
        "GitHub 執行資訊：event=%s run_id=%s run_number=%s attempt=%s",
        info["event"], info["run_id"], info["run_number"], info["run_attempt"]
    )

    token = os.getenv("GITHUB_TOKEN", "").strip()
    repository = os.getenv("GITHUB_REPOSITORY", "").strip()
    run_id = info["run_id"]
    if not (token and repository and run_id):
        log.info("未提供 GitHub Actions 診斷憑證，略過 Queue Time 查詢。")
        return info

    try:
        response = requests.get(
            f"https://api.github.com/repos/{repository}/actions/runs/{run_id}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=10,
        )
        response.raise_for_status()
        run = response.json()
        created = run.get("created_at")
        started = run.get("run_started_at")
        if created and started:
            created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            started_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
            queue_seconds = max(0, int((started_dt - created_dt).total_seconds()))
            info["queue_seconds"] = queue_seconds
            log.info(
                "GitHub Queue Time：%d 秒；建立時間=%s；開始時間=%s；狀態=%s",
                queue_seconds, created, started, run.get("status")
            )
            if queue_seconds >= 300:
                log.warning("GitHub 工作排隊超過 5 分鐘，可能是 Runner 或平台負載延遲。")
        else:
            log.warning("GitHub API 未提供完整 created_at/run_started_at，無法計算 Queue Time。")
    except Exception as exc:
        log.warning("讀取 GitHub Queue Time 失敗（不影響掃描）：%s", exc)
    return info


SCAN_INTERVAL_MINUTES = int(os.getenv("SCAN_INTERVAL_MINUTES", "20"))
STATE_FILE = "state.json"


def _github_headers(token: str) -> dict:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def load_scan_state() -> dict:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def should_run_full_scan(state: dict, event_name: str) -> tuple[bool, str]:
    """Manual dispatch forces a scan; scheduled runs scan only when due."""
    if event_name == "workflow_dispatch":
        return True, "手動啟動，強制執行完整掃描"

    last_text = state.get("last_successful_scan_utc")
    if not last_text:
        return True, "尚無完整成功紀錄，執行首次掃描"

    try:
        last_dt = datetime.fromisoformat(str(last_text).replace("Z", "+00:00"))
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=ZoneInfo("UTC"))
    except (TypeError, ValueError):
        return True, "成功紀錄格式異常，執行完整掃描"

    now_dt = datetime.now(ZoneInfo("UTC"))
    elapsed = (now_dt - last_dt).total_seconds()
    threshold = SCAN_INTERVAL_MINUTES * 60
    if elapsed >= threshold:
        return True, f"距離上次完整成功掃描 {elapsed / 60:.1f} 分鐘，啟動補掃"
    return False, f"距離上次完整成功掃描僅 {elapsed / 60:.1f} 分鐘，未達 {SCAN_INTERVAL_MINUTES} 分鐘，略過"


def persist_success_state(token: str, repository: str, branch: str, run_id: str) -> bool:
    """Persist the last fully successful scan in state.json via GitHub Contents API."""
    if not (token and repository and branch):
        log.error("缺少 GitHub token/repository/branch，無法保存成功掃描時間。")
        return False

    import requests
    api_url = f"https://api.github.com/repos/{repository}/contents/{STATE_FILE}"
    headers = _github_headers(token)
    try:
        response = requests.get(
            api_url, headers=headers, params={"ref": branch}, timeout=15
        )
        existing = {}
        sha = None
        if response.status_code == 200:
            payload = response.json()
            sha = payload.get("sha")
            try:
                raw = base64.b64decode(payload.get("content", "")).decode("utf-8")
                existing = json.loads(raw) if raw.strip() else {}
            except Exception:
                existing = {}
        elif response.status_code != 404:
            response.raise_for_status()

        if not isinstance(existing, dict):
            existing = {}
        existing["last_successful_scan_utc"] = datetime.now(
            ZoneInfo("UTC")
        ).isoformat(timespec="seconds")
        existing["last_successful_run_id"] = str(run_id or "")
        existing["last_successful_branch"] = branch
        content = json.dumps(existing, ensure_ascii=False, indent=2) + "\n"
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        body = {
            "message": f"chore(scanner): record successful scan {run_id or 'manual'}",
            "content": encoded,
            "branch": branch,
        }
        if sha:
            body["sha"] = sha

        saved = requests.put(api_url, headers=headers, json=body, timeout=20)
        saved.raise_for_status()
        with open(STATE_FILE, "w", encoding="utf-8") as handle:
            handle.write(content)
        log.info(
            "已保存完整成功掃描時間：%s",
            existing["last_successful_scan_utc"]
        )
        return True
    except Exception as exc:
        log.exception("保存完整成功掃描時間失敗：%s", exc)
        return False


def send_overdue_alert(bot: "TelegramBot", elapsed_minutes: float) -> None:
    """Notify when a scheduled run starts and the last full scan is overdue."""
    try:
        bot.send_message(
            "⚠️ <b>PIONEX SCANNER 排程異常提醒</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"距離上次完整成功掃描已超過 30 分鐘（目前約 {elapsed_minutes:.1f} 分鐘）。\n"
            "系統已啟動補掃；若持續發生，請檢查 GitHub Actions 排程與執行紀錄。"
        )
    except Exception:
        log.exception("發送排程異常提醒失敗")

def main() -> int:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        log.error("缺少 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID GitHub Secrets")
        return 2

    run_info = log_github_run_diagnostics()
    client = PionexClient()
    bot = TelegramBot(token, chat_id)

    event_name = os.getenv("GITHUB_EVENT_NAME", "local")
    state = load_scan_state()
    last_text = state.get("last_successful_scan_utc")
    overdue_minutes = None
    if last_text:
        try:
            last_dt = datetime.fromisoformat(str(last_text).replace("Z", "+00:00"))
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=ZoneInfo("UTC"))
            overdue_minutes = max(
                0.0,
                (datetime.now(ZoneInfo("UTC")) - last_dt).total_seconds() / 60,
            )
        except (TypeError, ValueError):
            pass

    # 每次 5 分鐘檢查都輪詢 Telegram TEST 指令，即使本輪不需要完整掃描。
    try:
        test_count = bot.handle_test_commands()
        if test_count:
            log.info("本輪處理 %d 個 Telegram TEST 指令", test_count)
    except Exception:
        log.exception("讀取或回覆 Telegram TEST 指令失敗")

    should_scan, scan_reason = should_run_full_scan(state, event_name)
    log.info("排程判斷：%s", scan_reason)
    if not should_scan:
        log.info("本輪為輕量檢查，不執行市場掃描。")
        return 0

    if overdue_minutes is not None and overdue_minutes > 30:
        send_overdue_alert(bot, overdue_minutes)

    try:
        symbols = client.get_trading_perpetual_symbols()
    except Exception:
        log.exception("取得 Pionex USDT 永續合約清單失敗")
        return 1

    if not symbols:
        log.error("Pionex 回傳的可交易 USDT 永續合約清單為空")
        return 1

    scan_started = time.monotonic()
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
    scan_elapsed = time.monotonic() - scan_started
    log.info(
        "掃描完成：市場 %d、成功取得K線 %d、符合 %d、錯誤 %d、耗時 %.1f 秒",
        len(symbols), scanned, len(found), errors, scan_elapsed
    )

    # 只有所有市場合約均成功取得 K 線、且沒有掃描錯誤，才更新成功時間。
    full_scan_success = scanned == len(symbols) and errors == 0
    state_saved = False
    if full_scan_success:
        state_saved = persist_success_state(
            os.getenv("GITHUB_TOKEN", "").strip(),
            os.getenv("GITHUB_REPOSITORY", "").strip(),
            os.getenv("GITHUB_REF_NAME", "main").strip() or "main",
            os.getenv("GITHUB_RUN_ID", ""),
        )
    else:
        log.warning(
            "本輪不是完整成功掃描（成功 %d/%d、錯誤 %d），不更新成功時間；下輪將重試。",
            scanned, len(symbols), errors
        )

    # 不做去重：每輪符合條件的幣種都重新通知。
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
    if not full_scan_success:
        return 1
    if not state_saved:
        log.error("掃描本身完整，但成功時間未能保存；下一輪可能再次執行補掃。")
        return 1
    return 1 if send_errors else 0


if __name__ == "__main__":
    sys.exit(main())
