from __future__ import annotations

from typing import Optional

import pandas as pd


def detect_sweep_and_retrace(
    df: pd.DataFrame,
    level: float,
    side: str,
    retrace_bars: int,
) -> Optional[int]:
    """Return row index (integer position) of the entry trigger, or None."""
    if df.empty or level is None:
        return None

    retrace_bars = max(1, int(retrace_bars))
    closes = df["close"].values
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values

    if side == "long":
        for i in range(1, len(df)):
            if lows[i] < level:  # sweep detected
                end = min(i + retrace_bars, len(df) - 1)
                for j in range(i, end + 1):
                    if closes[j] > opens[j]:  # green retrace bar
                        trigger = highs[j]
                        if j + 1 < len(df) and highs[j + 1] > trigger:
                            return j + 1
                break
    else:
        for i in range(1, len(df)):
            if highs[i] > level:
                end = min(i + retrace_bars, len(df) - 1)
                for j in range(i, end + 1):
                    if closes[j] < opens[j]:  # red retrace bar
                        trigger = lows[j]
                        if j + 1 < len(df) and lows[j + 1] < trigger:
                            return j + 1
                break
    return None
