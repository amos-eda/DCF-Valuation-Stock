from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

import pandas as pd


def prev_day_hl(
    df: pd.DataFrame,
    rth_only: bool = True,
    rth_start: str = "09:30",
    rth_end: str = "16:00",
) -> pd.DataFrame:
    """Return previous-day high/low for each session date."""
    if df.empty:
        return pd.DataFrame(columns=["prev_high", "prev_low"])  # index will be empty

    x = df.copy()
    if rth_only:
        start_time = datetime.strptime(rth_start, "%H:%M").time()
        end_time = datetime.strptime(rth_end, "%H:%M").time()
        mask = (x["timestamp"].dt.time >= start_time) & (x["timestamp"].dt.time < end_time)
        x = x[mask]

    x["date"] = x["timestamp"].dt.date
    grouped = x.groupby("date").agg(prev_high=("high", "max"), prev_low=("low", "min"))
    return grouped.shift(1)


def swings_4h(
    df: pd.DataFrame,
    left_right_bars: int = 2,
    resample: str = "240T",
) -> Dict[str, list[tuple[pd.Timestamp, float]]]:
    """Compute swing highs/lows using fractal logic on resampled data."""
    if df.empty:
        return {"swing_highs": [], "swing_lows": []}

    ohlc = df.set_index("timestamp").resample(resample).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna()

    highs = ohlc["high"].to_numpy()
    lows = ohlc["low"].to_numpy()
    idx = ohlc.index
    swings_high: list[tuple[pd.Timestamp, float]] = []
    swings_low: list[tuple[pd.Timestamp, float]] = []

    k = max(1, int(left_right_bars))
    for i in range(k, len(ohlc) - k):
        if highs[i] > highs[i - k : i].max() and highs[i] > highs[i + 1 : i + k + 1].max():
            swings_high.append((idx[i], highs[i]))
        if lows[i] < lows[i - k : i].min() and lows[i] < lows[i + 1 : i + k + 1].min():
            swings_low.append((idx[i], lows[i]))

    return {"swing_highs": swings_high, "swing_lows": swings_low}


def most_recent_swing(swings: Dict[str, list[tuple[pd.Timestamp, float]]], side: str) -> Optional[float]:
    key = "swing_highs" if side == "short" else "swing_lows"
    values = swings.get(key, [])
    if not values:
        return None
    return values[-1][1]
