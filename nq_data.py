"""Fetch NQ futures 1-minute data via Yahoo Finance chart API.

Requires: requests, pandas

Examples
--------
- Fetch continuous NQ (E-mini Nasdaq 100) 1-minute for last 5 days:
    df = fetch_nq_1m(range="5d")

- Fetch specific contract by Yahoo symbol (e.g., Dec 2024):
    df = fetch_yahoo_intraday("NQZ24.CME", interval="1m", range="5d")

Notes
-----
- Yahoo's chart API is unofficial and may change without notice.
- Intraday history is limited (e.g., up to ~30 days for 1-minute when using range like "30d").
"""

from __future__ import annotations

from typing import Dict, Optional

import pandas as pd
import requests


YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


def _yahoo_headers() -> Dict[str, str]:
    # A simple desktop-like UA to avoid being blocked by Yahoo's CDN.
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }


def fetch_yahoo_intraday(
    symbol: str,
    *,
    interval: str = "1m",
    range: str = "5d",
    include_prepost: bool = True,
    session: Optional[requests.Session] = None,
) -> pd.DataFrame:
    """Fetch intraday OHLCV data for a Yahoo Finance symbol.

    Parameters
    ----------
    symbol: str
        Yahoo symbol, e.g. "NQ=F" for continuous NQ or "NQZ24.CME" for a contract.
    interval: str
        Bar size, e.g. "1m", "2m", "5m", "15m".
    range: str
        History window, e.g. "1d", "5d", "7d", "30d".
    include_prepost: bool
        Include pre/post trading where applicable.
    session: requests.Session, optional
        Reuse an existing session for connection pooling.

    Returns
    -------
    pandas.DataFrame
        DataFrame indexed by UTC datetime with columns: open, high, low, close, volume.
    """
    sess = session or requests.Session()
    params = {
        "interval": interval,
        "range": range,
        "includePrePost": str(include_prepost).lower(),
        "events": "div,splits",
        "corsDomain": "finance.yahoo.com",
    }
    url = YAHOO_CHART_URL.format(symbol=symbol)
    resp = sess.get(url, params=params, headers=_yahoo_headers(), timeout=30)
    resp.raise_for_status()
    payload = resp.json()

    result = (payload.get("chart") or {}).get("result")
    if not result:
        err = (payload.get("chart") or {}).get("error") or {}
        msg = err.get("description") or "Unknown error from Yahoo chart API"
        raise RuntimeError(f"Yahoo chart error: {msg}")

    result0 = result[0]
    timestamps = result0.get("timestamp") or []
    indicators = (result0.get("indicators") or {}).get("quote") or []
    if not timestamps or not indicators:
        raise RuntimeError("No data returned for symbol/interval/range combination")

    quote = indicators[0]
    # Convert to DataFrame
    df = pd.DataFrame(
        {
            "open": quote.get("open"),
            "high": quote.get("high"),
            "low": quote.get("low"),
            "close": quote.get("close"),
            "volume": quote.get("volume"),
        },
        index=pd.to_datetime(timestamps, unit="s", utc=True),
    )
    # Drop any rows with all-NaN values (occasional missing bars)
    df.dropna(how="all", inplace=True)
    df.sort_index(inplace=True)
    return df


def fetch_nq_1m(*, range: str = "5d", include_prepost: bool = True) -> pd.DataFrame:
    """Fetch 1-minute bars for continuous NQ futures (symbol: "NQ=F")."""
    return fetch_yahoo_intraday(
        "NQ=F", interval="1m", range=range, include_prepost=include_prepost
    )


if __name__ == "__main__":
    # Example: print the latest 5 rows
    try:
        data = fetch_nq_1m(range="5d")
        print(data.tail())
    except Exception as exc:  # pragma: no cover
        print(f"Failed to fetch NQ 1m data: {exc}")

