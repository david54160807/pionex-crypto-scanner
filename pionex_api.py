from __future__ import annotations

import logging
import time
from typing import Any

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://api.pionex.com"
TIMEOUT = 15
KLINE_LIMIT = 220  # RSI 14 暖機 + 186 根策略回溯，仍低於官方 500 根上限。


class PionexClient:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "pionex-4h-pattern-scanner/1.0"})

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        url = f"{BASE_URL}{path}"
        last_error = None
        for attempt in range(4):
            try:
                response = self.session.get(url, params=params, timeout=TIMEOUT)
                if response.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f"暫時性 HTTP {response.status_code}")
                response.raise_for_status()
                payload = response.json()
                if payload.get("result") is False:
                    raise RuntimeError(
                        f"Pionex API 錯誤：{payload.get('code')} {payload.get('message')}"
                    )
                return payload
            except Exception as exc:
                last_error = exc
                if attempt < 3:
                    time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"API 請求失敗 {path}: {last_error}") from last_error

    def get_trading_perpetual_symbols(self) -> list[str]:
        payload = self._get(
            "/api/v1/common/symbols",
            {"type": "PERP", "status": "TRADING"},
        )
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
        payload = self._get(
            "/api/v1/market/klines",
            {"symbol": symbol, "interval": "4H", "limit": KLINE_LIMIT},
        )
        rows = payload.get("data", {}).get("klines", [])
        # 官方文件回傳依時間倒序；統一轉成由舊到新。
        parsed = []
        for row in rows:
            try:
                parsed.append({
                    "time": int(row["time"]),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                })
            except (KeyError, TypeError, ValueError):
                continue
        parsed.sort(key=lambda x: x["time"])
        return parsed
