import pandas as pd
import numpy as np
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from fvg_liquidity_sweep import (
    detect_pivots,
    detect_liquidity_sweeps,
    detect_bos,
    detect_fvg,
    fvg_clean,
)


def _make_df(data):
    df = pd.DataFrame(data)
    df["timestamp"] = pd.date_range("2024-01-01", periods=len(df), freq="T", tz="UTC")
    df.set_index("timestamp", inplace=True)
    df["atr"] = 1.0
    return df


def test_detect_pivots_basic():
    df = _make_df(
        {
            "open": [2, 3, 4, 3, 2, 3, 4],
            "high": [2.5, 3.5, 4.5, 3.5, 2.5, 3.5, 4.5],
            "low": [1.5, 2.5, 3.5, 2.5, 1.5, 2.5, 3.5],
            "close": [2, 3, 4, 3, 2, 3, 4],
            "volume": [1, 1, 1, 1, 1, 1, 1],
        }
    )
    pivots = detect_pivots(df)
    assert any(p.kind == "high" for p in pivots)
    assert any(p.kind == "low" for p in pivots)


def test_liquidity_sweep():
    df = _make_df(
        {
            "open": [1, 2, 3, 2, 1, 2],
            "high": [1.5, 2.5, 3.5, 2.5, 1.5, 4.0],
            "low": [0.5, 1.5, 2.5, 1.5, 0.5, 1.0],
            "close": [1, 2, 3, 2, 1, 2.5],
            "volume": [1] * 6,
        }
    )
    pivots = detect_pivots(df)
    sweeps = detect_liquidity_sweeps(df, pivots)
    assert len(sweeps) == 1
    assert sweeps[0] == 5


def test_bos():
    df = _make_df(
        {
            "open": [1, 2, 3, 2, 1, 2],
            "high": [1.5, 2.5, 3.5, 2.5, 1.5, 4.0],
            "low": [0.5, 1.5, 2.5, 1.5, 0.5, 1.0],
            "close": [1, 2, 3, 2, 1, 4.2],
            "volume": [1] * 6,
        }
    )
    pivots = detect_pivots(df)
    bos = detect_bos(df, pivots, df["atr"], buffer=0.1)
    assert bos[-1] == 5


def test_fvg_detection_and_clean():
    df = _make_df(
        {
            "open": [1.0, 2.2, 3.2, 3.5],
            "high": [2.0, 3.0, 4.0, 3.8],
            "low": [1.0, 2.2, 3.2, 3.4],
            "close": [2.0, 3.0, 4.0, 3.6],
            "volume": [1, 1, 1, 1],
        }
    )
    fvgs = detect_fvg(df)
    assert len(fvgs) == 1
    assert fvgs.iloc[0]["direction"] == "bullish"
    assert fvg_clean(df, fvgs.iloc[0])


def test_fvg_touched_invalidates_clean_flag():
    df = _make_df(
        {
            "open": [1.0, 2.2, 3.2, 3.5, 3.0],
            "high": [2.0, 3.0, 4.0, 3.8, 4.5],
            "low": [1.0, 2.2, 3.2, 3.4, 2.0],
            "close": [2.0, 3.0, 4.0, 3.6, 3.1],
            "volume": [1] * 5,
        }
    )
    fvgs = detect_fvg(df)
    assert len(fvgs) == 1
    assert not fvg_clean(df, fvgs.iloc[0])
