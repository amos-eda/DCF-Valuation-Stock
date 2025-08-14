#!/usr/bin/env python3
"""Backtest ICT Liquidity Sweep + FVG strategy.

This script fetches intraday data from Polygon.io, computes the required
indicators and runs a strict set of pattern detectors to identify potential
setups.  Results are exported to parquet and Excel reports.

The implementation focuses on clarity and testability rather than raw
performance.  Only the core detection rules are implemented here; advanced
optimisations (such as vectorisation of every step) can be added later without
changing the public API.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import argparse
import os
import time
from typing import List, Optional, Tuple, Dict

import numpy as np
import pandas as pd
import requests
try:
    import yaml
except ImportError:  # pragma: no cover - handled in tests
    yaml = None

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def load_config(path: str | Path) -> Dict:
    """Load YAML configuration file."""
    if yaml is None:
        raise ImportError("pyyaml is required to load configuration")
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

POLYGON_URL = "https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/minute/{start}/{end}?adjusted=true&sort=asc&limit=50000"


def _retry_request(url: str, *, max_tries: int = 5, backoff: float = 1.0) -> Dict:
    for attempt in range(max_tries):
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 429:
                # simple rate limit backoff
                time.sleep(backoff * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException:
            if attempt == max_tries - 1:
                raise
            time.sleep(backoff * (attempt + 1))
    raise RuntimeError("Unreachable")


def fetch_polygon_1m(symbol: str, start: datetime, end: datetime, api_key: str) -> pd.DataFrame:
    """Fetch 1m bars from Polygon.io between ``start`` and ``end``.

    The function handles pagination via the ``next_url`` field.
    """
    url = POLYGON_URL.format(
        ticker=symbol,
        start=int(start.timestamp() * 1000),
        end=int(end.timestamp() * 1000),
    ) + f"&apiKey={api_key}"
    all_results: List[Dict] = []
    while url:
        data = _retry_request(url)
        all_results.extend(data.get("results", []))
        url = data.get("next_url")
        if url:
            url = f"{url}&apiKey={api_key}"
    if not all_results:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume", "vwap"])
    df = pd.DataFrame(all_results)
    df.rename(
        columns={
            "t": "timestamp",
            "o": "open",
            "h": "high",
            "l": "low",
            "c": "close",
            "v": "volume",
            "vw": "vwap",
        },
        inplace=True,
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    return df


# ---------------------------------------------------------------------------
# Indicator helpers
# ---------------------------------------------------------------------------


def filter_session(df: pd.DataFrame, tz: str = "America/New_York") -> pd.DataFrame:
    """Filter dataframe to regular US equity session (09:30-16:00 ET).

    The input DataFrame must have a ``DatetimeIndex``.  The function converts the
    index to the desired timezone and drops any rows outside regular trading
    hours.
    """
    df = df.copy()
    df.index = df.index.tz_convert(tz)
    return df.between_time("09:30", "16:00")


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"].values
    low = df["low"].values
    close = df["close"].shift(1).fillna(df["close"])
    tr = np.maximum(high - low, np.maximum(abs(high - close), abs(low - close)))
    atr = pd.Series(tr, index=df.index).rolling(period).mean()
    return atr


def compute_rvol(df: pd.DataFrame, period: int = 20) -> pd.Series:
    return df["volume"] / df["volume"].rolling(period).mean()


def compute_session_vwap(df: pd.DataFrame) -> pd.Series:
    vwap = []
    for _, group in df.groupby(df.index.date):
        pv = (group["close"] * group["volume"]).cumsum()
        cv = group["volume"].cumsum()
        vwap.append(pv / cv)
    return pd.concat(vwap)


def add_session_markers(df: pd.DataFrame) -> pd.DataFrame:
    session_labels = []
    times = df.index.time
    for t in times:
        if t >= datetime.strptime("09:30", "%H:%M").time() and t < datetime.strptime("11:00", "%H:%M").time():
            session_labels.append("AM")
        elif t >= datetime.strptime("11:30", "%H:%M").time() and t < datetime.strptime("13:00", "%H:%M").time():
            session_labels.append("LUNCH")
        elif t >= datetime.strptime("13:30", "%H:%M").time() and t < datetime.strptime("15:30", "%H:%M").time():
            session_labels.append("PM")
        else:
            session_labels.append("OTHER")
    df["session"] = session_labels
    return df


# ---------------------------------------------------------------------------
# Structure detection
# ---------------------------------------------------------------------------


@dataclass
class Pivot:
    index: int
    price: float
    kind: str  # 'high' or 'low'


def detect_pivots(df: pd.DataFrame) -> List[Pivot]:
    pivots: List[Pivot] = []
    for i in range(2, len(df) - 2):
        high = df.iloc[i].high
        low = df.iloc[i].low
        if high > df.iloc[i - 1].high and high > df.iloc[i - 2].high and high > df.iloc[i + 1].high and high > df.iloc[i + 2].high:
            pivots.append(Pivot(i, high, "high"))
        if low < df.iloc[i - 1].low and low < df.iloc[i - 2].low and low < df.iloc[i + 1].low and low < df.iloc[i + 2].low:
            pivots.append(Pivot(i, low, "low"))
    return pivots


def detect_liquidity_sweeps(df: pd.DataFrame, pivots: List[Pivot]) -> List[int]:
    """Return indices where price swept a previous pivot high/low.

    A sweep occurs when a bar wicks beyond a prior pivot but closes back within
    its range.
    """
    indices: List[int] = []
    pivot_highs = [p for p in pivots if p.kind == "high"]
    pivot_lows = [p for p in pivots if p.kind == "low"]
    for i in range(1, len(df)):
        bar = df.iloc[i]
        for p in pivot_highs:
            if i <= p.index:
                continue
            if bar.high > p.price and bar.close < p.price:
                indices.append(i)
                break
        for p in pivot_lows:
            if i <= p.index:
                continue
            if bar.low < p.price and bar.close > p.price:
                indices.append(i)
                break
    return sorted(set(indices))


def detect_bos(df: pd.DataFrame, pivots: List[Pivot], atr: pd.Series, buffer: float) -> List[int]:
    """Detect simple Break of Structure events.

    A bullish BOS occurs when the close exceeds the last pivot high by
    ``buffer * ATR``.  The bearish case mirrors this logic.
    """
    bos_indices: List[int] = []
    last_high: Optional[Pivot] = None
    last_low: Optional[Pivot] = None
    for p in pivots:
        if p.kind == "high":
            last_high = p
        else:
            last_low = p
    for i in range(len(df)):
        bar = df.iloc[i]
        buff = atr.iloc[i] * buffer
        if last_high and bar.close > last_high.price + buff:
            bos_indices.append(i)
            last_high = None
        if last_low and bar.close < last_low.price - buff:
            bos_indices.append(i)
            last_low = None
    return bos_indices


def detect_fvg(df: pd.DataFrame) -> pd.DataFrame:
    """Return dataframe of detected FVGs.

    The detection is strict: requires 3 candles of the same colour and a gap
    between the first and third candle.
    """
    records = []
    for i in range(2, len(df)):
        c1, c2, c3 = df.iloc[i - 2], df.iloc[i - 1], df.iloc[i]
        up = c1.close > c1.open and c2.close > c2.open and c3.close > c3.open
        down = c1.close < c1.open and c2.close < c2.open and c3.close < c3.open
        if not (up or down):
            continue
        if up and c1.high < c3.low and c2.low > c1.high and c2.high < c3.low:
            fvg_low, fvg_high, direction = c1.high, c3.low, "bullish"
        elif down and c1.low > c3.high and c2.high < c1.low and c2.low > c3.high:
            fvg_low, fvg_high, direction = c3.high, c1.low, "bearish"
        else:
            continue
        size = (fvg_high - fvg_low) / df.iloc[i - 1]["atr"]
        records.append(
            {
                "index": i,
                "direction": direction,
                "low": fvg_low,
                "high": fvg_high,
                "size_atr": size,
            }
        )
    return pd.DataFrame(records)


def fvg_clean(df: pd.DataFrame, fvg_row: pd.Series) -> bool:
    idx = fvg_row["index"]
    low, high = fvg_row["low"], fvg_row["high"]
    post = df.iloc[idx + 1 :]
    for _, row in post.iterrows():
        if row.low <= high and row.high >= low:
            return False
    return True


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def score_fvg(fvg_row: pd.Series, df: pd.DataFrame, config: Dict) -> int:
    score = 0
    weights = config.get("weights", {})
    if fvg_row.get("clean", False):
        score += weights.get("clean_fvg", 0)
    size = fvg_row["size_atr"]
    if 0.2 <= size <= 0.8:
        score += weights.get("fvg_size", 0)
    elif 0.1 <= size < 0.2 or 0.8 < size <= 1.2:
        score += weights.get("fvg_size", 0) / 2
    session = df.iloc[fvg_row["index"]]["session"]
    if session in {"AM", "PM"}:
        score += weights.get("session_quality", 0)
    return int(score)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def process_symbol(
    symbol: str,
    config: Dict,
    start: datetime,
    end: datetime,
    session_only: bool,
    outdir: Path,
) -> pd.DataFrame:
    api_key = os.environ.get("POLYGON_API_KEY", "")
    df = fetch_polygon_1m(symbol, start, end, api_key)
    raw_path = outdir / "data" / "raw" / f"{symbol}.parquet"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(raw_path)

    df.set_index("timestamp", inplace=True)
    if session_only:
        df = filter_session(df)
    df["date"] = df.index.date
    df["atr"] = compute_atr(df)
    df["rvol"] = compute_rvol(df)
    df["vwap"] = compute_session_vwap(df)
    df = add_session_markers(df)
    clean_path = outdir / "data" / "clean" / f"{symbol}.parquet"
    clean_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(clean_path)

    fvgs = detect_fvg(df)
    if not fvgs.empty:
        fvgs["clean"] = fvgs.apply(lambda r: fvg_clean(df, r), axis=1)
        fvgs["score"] = fvgs.apply(lambda r: score_fvg(r, df, config), axis=1)
        report_path = outdir / "reports" / f"{symbol}_signals.xlsx"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(report_path) as writer:
            fvgs.to_excel(writer, sheet_name="signals", index=False)
        return fvgs
    return pd.DataFrame()


# ---------------------------------------------------------------------------
# Command line interface
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ICT Liquidity Sweep + FVG backtest")
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--months", type=int, default=3)
    parser.add_argument("--tf", default="1m")
    parser.add_argument("--session-only", action="store_true")
    parser.add_argument("--start", type=str, default=None)
    parser.add_argument("--end", type=str, default=None)
    parser.add_argument("--config", type=str, default="config.yaml")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    end = datetime.fromisoformat(args.end) if args.end else datetime.now(timezone.utc)
    if args.start:
        start = datetime.fromisoformat(args.start)
    else:
        start = end - timedelta(days=30 * args.months)
    outdir = Path.cwd()
    all_results = []
    for sym in args.symbols:
        fvgs = process_symbol(sym, config, start, end, args.session_only, outdir)
        if not fvgs.empty:
            fvgs["symbol"] = sym
            all_results.append(fvgs)
    if all_results:
        summary = pd.concat(all_results)
        summary.sort_values("score", ascending=False, inplace=True)
        summary_path = outdir / "reports" / "summary.xlsx"
        summary.to_excel(summary_path, index=False)


if __name__ == "__main__":
    main()
