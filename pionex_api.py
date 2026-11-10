from __future__ import annotations
import logging, time
from typing import Any
import requests

log = logging.getLogger(__name__)
BASE_URL = "https://api.pionex.com"
TIMEOUT = 20
KLINE_LIMIT = 220
MIN_REQUEST_INTERVAL = 1.15

class RateLimitError(RuntimeError):
    pass

class PionexClient:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "pionex-4h-pattern-scanner/1.0"})
        self._last_request_at = 0.0

    def _pace(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        url = f"{BASE_URL}{path}"
        transient_attempts = 3
        rate_limit_retried = False
        while True:
            self._pace()
            try:
                response = self.session.get(url, params=params, timeout=TIMEOUT)
                self._last_request_at = time.monotonic()
                if response.status_code == 429:
                    if rate_limit_retried:
                        raise RateLimitError("冷卻後仍收到 HTTP 429，停止本輪掃描以避免延長限流。")
                    retry_after = response.headers.get("Retry-After")
                    try:
                        wait_seconds = max(60, float(retry_after)) if retry_after else 60
                    except ValueError:
                        wait_seconds = 60
                    log.warning("Pionex HTTP 429，暫停 %.0f 秒後只重試一次。", wait_seconds)
                    time.sleep(wait_seconds)
                    rate_limit_retried = True
                    continue
                if response.status_code in (500, 502, 503, 504):
                    raise requests.HTTPError(f"暫時性 HTTP {response.status_code}")
                response.raise_for_status()
                payload = response.json()
                if payload.get("result") is False:
                    raise RuntimeError(f"Pionex API 錯誤：{payload.get('code')} {payload.get('message')}")
                return payload
            except RateLimitError:
                raise
            except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
                self._last_request_at = time.monotonic()
                transient_attempts -= 1
                if transient_attempts <= 0:
                    raise RuntimeError(f"API 請求失敗 {path}: {exc}") from exc
                wait_seconds = 3 * (4 - transient_attempts)
                log.warning("API 暫時錯誤，%.0f 秒後重試：%s", wait_seconds, exc)
                time.sleep(wait_seconds)

    def get_trading_perpetual_symbols(self) -> list[str]:
        payload = self._get("/api/v1/common/symbols", {"type": "PERP", "status": "TRADING"})
        rows = payload.get("data", {}).get("symbols", [])
        symbols = []
        for row in rows:
            symbol = str(row.get("symbol", "")).upper()
            quote = str(row.get("quoteCurrency", "")).upper()
            status = str(row.get("status", "TRADING")).upper()
            if symbol.endswith("_USDT_PERP") and quote in ("", "USDT") and status == "TRADING":
                symbols.append(symbol)
        return sorted(set(symbols))

    def get_4h_klines(self, symbol: str) -> list[dict]:
        payload = self._get("/api/v1/market/klines", {"symbol": symbol, "interval": "4H", "limit": KLINE_LIMIT})
        rows = payload.get("data", {}).get("klines", [])
        parsed = []
        for row in rows:
            try:
                parsed.append({
                    "time": int(row["time"]), "open": float(row["open"]),
                    "high": float(row["high"]), "low": float(row["low"]),
                    "close": float(row["close"]), "volume": float(row["volume"]),
                })
            except (KeyError, TypeError, ValueError):
                continue
        parsed.sort(key=lambda x: x["time"])
        return parsed
