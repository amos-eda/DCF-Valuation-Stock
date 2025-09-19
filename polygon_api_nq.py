"""Fetch NQ futures 1-minute bars using Polygon REST API (v2 aggregates).

Environment
-----------
- POLYGON_API_KEY  (required)

Optional: A `.env` file may be used if `python-dotenv` is installed.

Usage example
-------------
from datetime import date
from polygon_api_nq import fetch_polygon_api_intraday, fetch_nq_minute_api

# single symbol
df = fetch_polygon_api_intraday("CME:NQZ24", date(2024,8,1), date(2024,8,2))

# multiple symbols
df_all = fetch_nq_minute_api(["CME:NQZ24", "CME:NQH25"], date(2024,8,1), date(2024,8,2))
"""

from __future__ import annotations

from datetime import date
from typing import Iterable, List, Optional, Tuple

import os
import requests
import pandas as pd


BASE_URL = "https://api.polygon.io/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{start}/{end}"


def _load_api_key() -> str:
    # Optional dotenv support
    try:  # pragma: no cover
        from dotenv import load_dotenv  # type: ignore

        load_dotenv()
    except Exception:
        pass
    api_key = os.environ.get("POLYGON_API_KEY")
    if not api_key:
        raise RuntimeError("Missing POLYGON_API_KEY in environment or .env")
    return api_key


def _standardize_agg_columns(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    rename_map = {
        "v": "volume",
        "vw": "vwap",
        "o": "open",
        "c": "close",
        "h": "high",
        "l": "low",
        "t": "t",
        "n": "count",
    }
    df = df.rename(columns=rename_map)
    req = ["t", "open", "high", "low", "close", "volume"]
    missing = [c for c in req if c not in df.columns]
    if missing:
        raise ValueError(f"Polygon API returned unexpected schema, missing: {missing}")
    ts = pd.to_datetime(df["t"], unit="ms", utc=True, errors="coerce")
    df = df.assign(timestamp=ts, symbol=symbol)
    df = df.dropna(subset=["timestamp"]).set_index("timestamp").sort_index()
    ordered = ["open", "high", "low", "close", "volume", "vwap", "count", "symbol"]
    for col in ordered:
        if col not in df.columns:
            df[col] = pd.NA
    return df[ordered]


def fetch_polygon_api_intraday(
    symbol: str,
    start: date,
    end: date,
    *,
    multiplier: int = 1,
    timespan: str = "minute",
    adjusted: bool = True,
    limit: int = 50000,
    sort: str = "asc",
    api_key: Optional[str] = None,
    session: Optional[requests.Session] = None,
    verbose: bool = False,
) -> pd.DataFrame:
    """Fetch intraday aggregates for a given Polygon futures symbol.

    Handles pagination via `next_url` when present.
    """
    api_key = api_key or _load_api_key()
    sess = session or requests.Session()

    start_s = start.strftime("%Y-%m-%d")
    end_s = end.strftime("%Y-%m-%d")
    base_params = {
        "adjusted": str(adjusted).lower(),
        "sort": sort,
        "limit": limit,
        "apiKey": api_key,
    }
    
    def try_fetch(sym: str) -> Tuple[pd.DataFrame, Optional[int]]:
        url = BASE_URL.format(symbol=sym, multiplier=multiplier, timespan=timespan, start=start_s, end=end_s)
        all_rows: List[dict] = []
        next_url: Optional[str] = None
        while True:
            if verbose:
                print(f"GET {next_url or url}")
            if next_url:
                resp = sess.get(next_url, timeout=30)
            else:
                resp = sess.get(url, params=base_params, timeout=30)
            status_code = resp.status_code
            try:
                resp.raise_for_status()
            except requests.HTTPError:
                return (pd.DataFrame(), status_code)
            payload = resp.json()

            # Surface API-level errors early
            status = payload.get("status")
            if status and status != "OK":
                message = payload.get("error") or payload.get("message") or str(payload)[:200]
                raise RuntimeError(f"Polygon API error: {message}")

            results = payload.get("results") or []
            all_rows.extend(results)

            next_url = payload.get("next_url")
            if not next_url:
                break
            # Attach apiKey to next_url if not present
            if "apiKey=" not in next_url:
                sep = "&" if "?" in next_url else "?"
                next_url = f"{next_url}{sep}apiKey={api_key}"

        if not all_rows:
            return (pd.DataFrame(), None)
        df_local = pd.DataFrame(all_rows)
        return (_standardize_agg_columns(df_local, sym), None)

    # Try requested symbol, then a few fallbacks (year width and quarter month for start date)
    def month_code_for(d: date) -> str:
        # H=Mar(3), M=Jun(6), U=Sep(9), Z=Dec(12)
        q_month = ((d.month - 1) // 3 + 1) * 3
        return {3: "H", 6: "M", 9: "U", 12: "Z"}[q_month]

    def variants(sym: str) -> List[str]:
        # If already a contract like CME:NQZ24 or CME:NQZ2024, generate alt year width
        base = sym
        out = [base]
        import re as _re
        m = _re.match(r"^(?P<exch>[^:]+):(?P<root>[A-Z]+)(?P<mon>[HMUZ])(?P<yy>\d{2})(?P<rest>.*)$", base)
        if m:
            exch, root, mon, yy, rest = m.group("exch", "root", "mon", "yy", "rest")
            out.append(f"{exch}:{root}{mon}20{yy}{rest}")
            return out
        m = _re.match(r"^(?P<exch>[^:]+):(?P<root>[A-Z]+)(?P<mon>[HMUZ])(?P<yyyy>\d{4})(?P<rest>.*)$", base)
        if m:
            exch, root, mon, yyyy, rest = m.group("exch", "root", "mon", "yyyy", "rest")
            out.append(f"{exch}:{root}{mon}{yyyy[-2:]}{rest}")
            return out
        # If just root provided like CME:NQ, build contract for start date
        m = _re.match(r"^(?P<exch>[^:]+):(?P<root>[A-Z]+)$", base)
        if m:
            exch, root = m.group("exch", "root")
            mon = month_code_for(start)
            yy = start.strftime("%y")
            yyyy = start.strftime("%Y")
            out.extend([f"{exch}:{root}{mon}{yy}", f"{exch}:{root}{mon}{yyyy}"])
        return out

    tried: List[str] = []
    for sym in variants(symbol):
        if sym in tried:
            continue
        tried.append(sym)
        df, status_code = try_fetch(sym)
        if not df.empty:
            return df
        if status_code and status_code != 404 and status_code != 400:
            # Non-not-found error: raise for visibility
            raise requests.HTTPError(f"Polygon returned HTTP {status_code} for symbol {sym}")

    # If all variants failed/empty, return a typed empty frame
    if verbose:
        print(f"No data for variants: {', '.join(tried)}")
    return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "vwap", "count", "symbol"]).astype({})


def fetch_nq_minute_api(symbols: Iterable[str], start: date, end: date, *, verbose: bool = False) -> pd.DataFrame:
    frames: List[pd.DataFrame] = []
    for sym in symbols:
        try:
            df = fetch_polygon_api_intraday(sym, start, end, verbose=verbose)
            frames.append(df)
        except Exception as exc:  # pragma: no cover
            if verbose:
                print(f"Failed for {sym}: {exc}")
    if not frames:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "vwap", "count", "symbol"]).astype({})
    return pd.concat(frames).sort_index()
