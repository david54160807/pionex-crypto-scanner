from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")

LOOKBACK_BARS = 186       # 31 天 × 每天 6 根 4H K 線
PIVOT_LEFT = 3
PIVOT_RIGHT = 3
RSI_PERIOD = 14
CANDLE_MS = 4 * 60 * 60 * 1000


def wilder_rsi(closes: list[float], period: int = RSI_PERIOD) -> list[float | None]:
    """Wilder RSI；以第一組 period 漲跌幅作初始平均。"""
    out: list[float | None] = [None] * len(closes)
    if len(closes) <= period:
        return out

    gains = []
    losses = []
    for i in range(1, period + 1):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    def calc(g: float, l: float) -> float:
        if l == 0:
            return 100.0 if g > 0 else 50.0
        rs = g / l
        return 100.0 - (100.0 / (1.0 + rs))

    out[period] = calc(avg_gain, avg_loss)
    for i in range(period + 1, len(closes)):
        change = closes[i] - closes[i - 1]
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
        out[i] = calc(avg_gain, avg_loss)
    return out


def is_pivot_high(bars: list[dict], idx: int) -> bool:
    center = bars[idx]["high"]
    left = bars[idx - PIVOT_LEFT:idx]
    right = bars[idx + 1:idx + PIVOT_RIGHT + 1]
    return (
        len(left) == PIVOT_LEFT
        and len(right) == PIVOT_RIGHT
        and all(center > b["high"] for b in left)
        and all(center > b["high"] for b in right)
    )


def is_pivot_low(bars: list[dict], idx: int) -> bool:
    center = bars[idx]["low"]
    left = bars[idx - PIVOT_LEFT:idx]
    right = bars[idx + 1:idx + PIVOT_RIGHT + 1]
    return (
        len(left) == PIVOT_LEFT
        and len(right) == PIVOT_RIGHT
        and all(center < b["low"] for b in left)
        and all(center < b["low"] for b in right)
    )


def local_time(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone(TAIPEI).strftime(
        "%m-%d %H:%M"
    )


def analyze_symbol(symbol: str, raw_bars: list[dict], now_ms: int | None = None) -> dict | None:
    """
    只用已收盤 K 線。最後 186 根作型態回溯；
    RSI 先用額外歷史 K 線暖機。三個最近確認高點與低點必須各自嚴格遞增。
    """
    if now_ms is None:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    # K線 time 是開盤時間；排除尚未完成的4H K線。
    bars = [b for b in raw_bars if b["time"] + CANDLE_MS <= now_ms]
    bars.sort(key=lambda x: x["time"])
    if len(bars) < LOOKBACK_BARS + RSI_PERIOD + 2:
        return None

    rsi_values = wilder_rsi([b["close"] for b in bars])
    start_idx = max(0, len(bars) - LOOKBACK_BARS)
    end_idx = len(bars) - 1

    highs = []
    lows = []
    # 最後三根右側確認K棒必須已收盤，因此 pivot index 不會超過 end_idx - RIGHT。
    for idx in range(max(start_idx + PIVOT_LEFT, PIVOT_LEFT), end_idx - PIVOT_RIGHT + 1):
        if is_pivot_high(bars, idx) and rsi_values[idx] is not None:
            highs.append({
                "index": idx,
                "time": bars[idx]["time"],
                "price": bars[idx]["high"],
                "volume": bars[idx]["volume"],
                "rsi": float(rsi_values[idx]),
            })
        if is_pivot_low(bars, idx):
            lows.append({
                "index": idx,
                "time": bars[idx]["time"],
                "price": bars[idx]["low"],
            })

    if len(highs) < 3 or len(lows) < 3:
        return None

    h3 = highs[-3:]
    l3 = lows[-3:]

    # 高點：價格嚴格墊高、成交量嚴格遞減、RSI 嚴格遞減。
    if not (h3[0]["price"] < h3[1]["price"] < h3[2]["price"]):
        return None
    if not (h3[0]["volume"] > h3[1]["volume"] > h3[2]["volume"]):
        return None
    if not (h3[0]["rsi"] > h3[1]["rsi"] > h3[2]["rsi"]):
        return None

    # 低點嚴格墊高。
    if not (l3[0]["price"] < l3[1]["price"] < l3[2]["price"]):
        return None

    last = bars[-1]
    # 額外結構風險過濾：最新收盤不能跌破最近一個確認波段低點。
    if last["close"] < l3[-1]["price"]:
        return None

    latest_rsi = rsi_values[-1]
    if latest_rsi is None:
        return None

    highs_out = [
        {
            "price": p["price"],
            "volume": p["volume"],
            "rsi": p["rsi"],
            "time_local": local_time(p["time"]),
            "time": p["time"],
        }
        for p in h3
    ]
    lows_out = [
        {
            "price": p["price"],
            "time_local": local_time(p["time"]),
            "time": p["time"],
        }
        for p in l3
    ]

    signal_key = f"H{h3[-1]['time']}-L{l3[-1]['time']}"
    return {
        "symbol": symbol,
        "highs": highs_out,
        "lows": lows_out,
        "last_close": last["close"],
        "last_rsi": float(latest_rsi),
        "signal_key": signal_key,
    }
