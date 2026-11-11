from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")
LOOKBACK_MS = 31 * 24 * 60 * 60 * 1000
PIVOT_LEFT = 3
PIVOT_RIGHT = 3
RSI_PERIOD = 14
CANDLE_MS = 4 * 60 * 60 * 1000


def wilder_rsi(closes: list[float], period: int = RSI_PERIOD) -> list[float | None]:
    output: list[float | None] = [None] * len(closes)
    if len(closes) <= period:
        return output

    gains, losses = [], []
    for index in range(1, period + 1):
        change = closes[index] - closes[index - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    def calculate(gain: float, loss: float) -> float:
        if loss == 0:
            return 100.0 if gain > 0 else 50.0
        rs = gain / loss
        return 100.0 - 100.0 / (1.0 + rs)

    output[period] = calculate(avg_gain, avg_loss)
    for index in range(period + 1, len(closes)):
        change = closes[index] - closes[index - 1]
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        output[index] = calculate(avg_gain, avg_loss)
    return output


def is_pivot_high(bars: list[dict], index: int) -> bool:
    center = bars[index]["high"]
    left = bars[index - PIVOT_LEFT:index]
    right = bars[index + 1:index + PIVOT_RIGHT + 1]
    return (
        len(left) == PIVOT_LEFT
        and len(right) == PIVOT_RIGHT
        and all(center > bar["high"] for bar in left)
        and all(center > bar["high"] for bar in right)
    )


def is_pivot_low(bars: list[dict], index: int) -> bool:
    center = bars[index]["low"]
    left = bars[index - PIVOT_LEFT:index]
    right = bars[index + 1:index + PIVOT_RIGHT + 1]
    return (
        len(left) == PIVOT_LEFT
        and len(right) == PIVOT_RIGHT
        and all(center < bar["low"] for bar in left)
        and all(center < bar["low"] for bar in right)
    )


def to_taipei_time(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(
        timestamp_ms / 1000, tz=timezone.utc
    ).astimezone(TAIPEI).strftime("%m-%d %H:%M")


def analyze_symbol(symbol: str, raw_bars: list[dict], now_ms: int | None = None) -> dict | None:
    if now_ms is None:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    bars = [
        bar for bar in raw_bars
        if int(bar["time"]) + CANDLE_MS <= now_ms
    ]
    bars.sort(key=lambda bar: int(bar["time"]))
    if len(bars) < RSI_PERIOD + PIVOT_LEFT + PIVOT_RIGHT + 3:
        return None

    cutoff_ms = now_ms - LOOKBACK_MS
    rsi_values = wilder_rsi([float(bar["close"]) for bar in bars], RSI_PERIOD)

    eligible = [i for i, bar in enumerate(bars) if int(bar["time"]) >= cutoff_ms]
    if not eligible:
        return None

    first_index = eligible[0]
    last_index = len(bars) - 1
    highs, lows = [], []

    for index in range(max(first_index, PIVOT_LEFT), last_index - PIVOT_RIGHT + 1):
        bar = bars[index]
        if rsi_values[index] is None:
            continue
        if is_pivot_high(bars, index):
            highs.append({
                "index": index,
                "time": int(bar["time"]),
                "price": float(bar["high"]),
                "volume": float(bar["volume"]),
                "rsi": float(rsi_values[index]),
            })
        if is_pivot_low(bars, index):
            lows.append({
                "index": index,
                "time": int(bar["time"]),
                "price": float(bar["low"]),
            })

    if len(highs) < 3 or len(lows) < 3:
        return None

    h3, l3 = highs[-3:], lows[-3:]
    hp = [point["price"] for point in h3]
    lp = [point["price"] for point in l3]
    vols = [point["volume"] for point in h3]
    rsis = [point["rsi"] for point in h3]

    if not (hp[0] < hp[1] < hp[2]):
        return None
    if not (lp[0] < lp[1] < lp[2]):
        return None
    if not (vols[0] > vols[1] > vols[2]):
        return None
    if not (rsis[0] > rsis[1] > rsis[2]):
        return None

    latest_rsi = rsi_values[-1]
    if latest_rsi is None:
        return None

    return {
        "symbol": symbol,
        "highs": [{
            "price": p["price"],
            "volume": p["volume"],
            "rsi": p["rsi"],
            "time_local": to_taipei_time(p["time"]),
            "time": p["time"],
        } for p in h3],
        "lows": [{
            "price": p["price"],
            "time_local": to_taipei_time(p["time"]),
            "time": p["time"],
        } for p in l3],
        "last_close": float(bars[-1]["close"]),
        "last_rsi": float(latest_rsi),
    }
