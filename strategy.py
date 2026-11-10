from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")

LOOKBACK_DAYS = 31
LOOKBACK_MS = LOOKBACK_DAYS * 24 * 60 * 60 * 1000
LOOKBACK_BARS = 186
PIVOT_LEFT = 3
PIVOT_RIGHT = 3
RSI_PERIOD = 14
CANDLE_MS = 4 * 60 * 60 * 1000


def wilder_rsi(
    closes: list[float],
    period: int = RSI_PERIOD,
) -> list[float | None]:
    """以 Wilder 平滑法計算 RSI。"""
    output: list[float | None] = [None] * len(closes)

    if len(closes) <= period:
        return output

    gains: list[float] = []
    losses: list[float] = []

    for index in range(1, period + 1):
        change = closes[index] - closes[index - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    average_gain = sum(gains) / period
    average_loss = sum(losses) / period

    def calculate(gain: float, loss: float) -> float:
        if loss == 0:
            return 100.0 if gain > 0 else 50.0
        relative_strength = gain / loss
        return 100.0 - (100.0 / (1.0 + relative_strength))

    output[period] = calculate(average_gain, average_loss)

    for index in range(period + 1, len(closes)):
        change = closes[index] - closes[index - 1]
        gain = max(change, 0.0)
        loss = max(-change, 0.0)

        average_gain = (
            average_gain * (period - 1) + gain
        ) / period
        average_loss = (
            average_loss * (period - 1) + loss
        ) / period

        output[index] = calculate(average_gain, average_loss)

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
        timestamp_ms / 1000,
        tz=timezone.utc,
    ).astimezone(TAIPEI).strftime("%m-%d %H:%M")


def analyze_symbol(
    symbol: str,
    raw_bars: list[dict],
    now_ms: int | None = None,
) -> dict | None:
    """
    V2.0 A級單一訊號條件：
    1. 只分析最近 31 天的已收盤 4H K 線。
    2. 最近三個確認 Swing High 價格逐次抬高。
    3. 最近三個確認 Swing Low 價格逐次抬高。
    4. 三個高點所在 K 線成交量逐次縮小。
    5. 三個高點對應 RSI(14) 逐次下降。

    不包含 B 級階段，不執行通知去重。
    """

    if now_ms is None:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 排除尚未收盤的 4H K 線。
    closed_bars = [
        bar for bar in raw_bars
        if int(bar["time"]) + CANDLE_MS <= now_ms
    ]
    closed_bars.sort(key=lambda bar: int(bar["time"]))

    if len(closed_bars) < RSI_PERIOD + PIVOT_LEFT + PIVOT_RIGHT + 3:
        return None

    # 以目前時間往前 31 天定義觀察區間。
    cutoff_ms = now_ms - LOOKBACK_MS

    # RSI 先使用較長的歷史序列計算，避免只用 31 天資料暖機。
    closes = [float(bar["close"]) for bar in closed_bars]
    rsi_values = wilder_rsi(closes, RSI_PERIOD)

    # 只在最近 31 天內尋找波段點。
    candidate_indices = [
        index for index, bar in enumerate(closed_bars)
        if int(bar["time"]) >= cutoff_ms
    ]

    if not candidate_indices:
        return None

    first_index = candidate_indices[0]
    last_index = len(closed_bars) - 1

    highs: list[dict] = []
    lows: list[dict] = []

    # 轉折點需有右側 3 根已收盤 K 線確認。
    start_index = max(first_index, PIVOT_LEFT)
    end_index = last_index - PIVOT_RIGHT

    for index in range(start_index, end_index + 1):
        bar = closed_bars[index]

        if rsi_values[index] is None:
            continue

        if is_pivot_high(closed_bars, index):
            highs.append({
                "index": index,
                "time": int(bar["time"]),
                "price": float(bar["high"]),
                "volume": float(bar["volume"]),
                "rsi": float(rsi_values[index]),
            })

        if is_pivot_low(closed_bars, index):
            lows.append({
                "index": index,
                "time": int(bar["time"]),
                "price": float(bar["low"]),
            })

    if len(highs) < 3 or len(lows) < 3:
        return None

    # 取觀察區間內最近三個已確認高點與低點。
    selected_highs = highs[-3:]
    selected_lows = lows[-3:]

    # 條件 1：三個高點持續抬高。
    high_prices = [point["price"] for point in selected_highs]
    if not (high_prices[0] < high_prices[1] < high_prices[2]):
        return None

    # 條件 2：三個低點持續抬高。
    low_prices = [point["price"] for point in selected_lows]
    if not (low_prices[0] < low_prices[1] < low_prices[2]):
        return None

    # 條件 3：三個高點對應 K 線成交量持續縮小。
    volumes = [point["volume"] for point in selected_highs]
    if not (volumes[0] > volumes[1] > volumes[2]):
        return None

    # 條件 4：三個高點對應 RSI(14) 持續下降。
    rsi_at_highs = [point["rsi"] for point in selected_highs]
    if not (
        rsi_at_highs[0] > rsi_at_highs[1] > rsi_at_highs[2]
    ):
        return None

    latest_bar = closed_bars[-1]
    latest_rsi = rsi_values[-1]

    if latest_rsi is None:
        return None

    highs_output = [
        {
            "price": point["price"],
            "volume": point["volume"],
            "rsi": point["rsi"],
            "time_local": to_taipei_time(point["time"]),
            "time": point["time"],
        }
        for point in selected_highs
    ]

    lows_output = [
        {
            "price": point["price"],
            "time_local": to_taipei_time(point["time"]),
            "time": point["time"],
        }
        for point in selected_lows
    ]

    return {
        "symbol": symbol,
        "highs": highs_output,
        "lows": lows_output,
        "last_close": float(latest_bar["close"]),
        "last_rsi": float(latest_rsi),
    }
