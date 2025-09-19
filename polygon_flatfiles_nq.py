"""Fetch NQ futures 1-minute bars from Polygon Flat Files (S3-compatible).

This module connects to Polygon's flat files bucket via an S3-compatible
endpoint (https://files.polygon.io) using your Access Key ID and Secret.
It locates the futures minute-aggregate dataset, downloads daily partitions
within a date range, filters for NQ contracts (CME:NQ*), and returns a
normalized pandas DataFrame of OHLCV bars in UTC.

Environment variables
---------------------
- POLYGON_S3_ACCESS_KEY_ID
- POLYGON_S3_SECRET_ACCESS_KEY
- POLYGON_S3_ENDPOINT  (default: https://files.polygon.io)
- POLYGON_S3_BUCKET    (default: flatfiles)

Dependencies
------------
- boto3, pandas, pyarrow (for parquet), python-dotenv (optional)

Notes
-----
- This relies on the current bucket layout. The code attempts a few
  common patterns used by Polygon flat files for minute aggregates and
  is defensive, probing multiple directory/date layouts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from io import BytesIO
import gzip
import os
import re
from typing import Iterable, List, Optional, Tuple

import boto3
import pandas as pd
import pyarrow.parquet as pq


# ------------- Configuration -------------


@dataclass(frozen=True)
class S3Config:
    access_key_id: str
    secret_access_key: str
    endpoint_url: str = "https://files.polygon.io"
    bucket: str = "flatfiles"
    region_name: str = "us-east-1"  # often ignored for S3-compatible endpoints


def load_config_from_env() -> S3Config:
    # Optional dotenv support if user has python-dotenv installed
    try:  # pragma: no cover - best-effort
        from dotenv import load_dotenv  # type: ignore

        load_dotenv()  # load .env if present
    except Exception:
        pass

    ak = os.environ.get("POLYGON_S3_ACCESS_KEY_ID")
    sk = os.environ.get("POLYGON_S3_SECRET_ACCESS_KEY")
    if not ak or not sk:
        raise RuntimeError(
            "Missing POLYGON_S3_ACCESS_KEY_ID or POLYGON_S3_SECRET_ACCESS_KEY in environment"
        )

    endpoint = os.environ.get("POLYGON_S3_ENDPOINT", "https://files.polygon.io")
    bucket = os.environ.get("POLYGON_S3_BUCKET", "flatfiles")
    region = os.environ.get("POLYGON_S3_REGION", "us-east-1")
    return S3Config(access_key_id=ak, secret_access_key=sk, endpoint_url=endpoint, bucket=bucket, region_name=region)


def make_s3_client(cfg: S3Config):
    session = boto3.session.Session()
    return session.client(
        "s3",
        region_name=cfg.region_name,
        endpoint_url=cfg.endpoint_url,
        aws_access_key_id=cfg.access_key_id,
        aws_secret_access_key=cfg.secret_access_key,
    )


# ------------- Discovery helpers -------------


def _list_common_prefixes(client, bucket: str, prefix: str) -> List[str]:
    """List 'directories' one level below prefix using Delimiter='/'"""
    paginator = client.get_paginator("list_objects_v2")
    prefixes: List[str] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter="/"):
        for cp in page.get("CommonPrefixes", []) or []:
            p = cp.get("Prefix")
            if p:
                prefixes.append(p)
    return prefixes


def discover_minute_aggregates_prefix(client, bucket: str) -> str:
    """Try to locate the futures minute aggregates dataset root prefix.

    Returns a prefix that should contain date partitions, e.g.:
    - "futures/aggregates/minute/"
    - or similar structures like "futures/aggs/minute/"
    """
    candidate_roots = [
        "futures/aggregates/",
        "futures/aggs/",
        "futures/",  # fallback to search inside
    ]
    minute_names = ["minute/", "1minute/", "1min/"]

    # First try the obvious ones directly
    for root in candidate_roots:
        for mn in minute_names:
            prefix = root + mn
            # Probe existence by asking for one page with this prefix
            resp = client.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=1)
            if resp.get("KeyCount", 0) > 0:
                return prefix

    # Otherwise, try to discover by listing and matching a minute-like subdir
    for root in candidate_roots:
        for sub in _list_common_prefixes(client, bucket, root):
            if any(sub.endswith(mn) for mn in minute_names):
                return sub
            # One more level deep
            for sub2 in _list_common_prefixes(client, bucket, sub):
                if any(sub2.endswith(mn) for mn in minute_names):
                    return sub2

    # Fallback to the most likely default
    return "futures/aggregates/minute/"


# ------------- Date partition probing -------------


def _date_layout_candidates(d: date) -> List[str]:
    """Generate date layouts under a base prefix for a given date."""
    ymd_dash = d.strftime("%Y-%m-%d")
    return [
        f"{ymd_dash}/",
        f"dt={ymd_dash}/",
        f"{d:%Y/%m/%d}/",
    ]


def list_objects_for_date(client, bucket: str, base_prefix: str, d: date) -> List[dict]:
    """List objects for a specific date trying a set of common layouts."""
    for layout in _date_layout_candidates(d):
        prefix = base_prefix + layout
        resp = client.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=2)
        if resp.get("KeyCount", 0) > 0:
            # Fetch full listing for that prefix
            paginator = client.get_paginator("list_objects_v2")
            objs: List[dict] = []
            for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                objs.extend(page.get("Contents", []) or [])
            return objs
    return []


# ------------- Data loading and normalization -------------


CSV_LIKE = (".csv", ".csv.gz")
PARQUET_LIKE = (".parquet", ".parq")


def _read_object_to_dataframe(client, bucket: str, key: str) -> pd.DataFrame:
    obj = client.get_object(Bucket=bucket, Key=key)
    body = obj["Body"].read()

    key_lower = key.lower()
    if key_lower.endswith(PARQUET_LIKE):
        table = pq.read_table(BytesIO(body))
        df = table.to_pandas()
    elif key_lower.endswith(".csv.gz"):
        with gzip.GzipFile(fileobj=BytesIO(body)) as gz:
            df = pd.read_csv(gz)
    elif key_lower.endswith(".csv"):
        df = pd.read_csv(BytesIO(body))
    else:
        raise ValueError(f"Unsupported file type for key: {key}")
    return df


def _standardize_agg_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename Polygon aggregate columns to a standard schema.

    Expected raw columns often include: v, vw, o, c, h, l, t, n, s
    This returns: timestamp, open, high, low, close, volume, vwap, count, symbol
    """
    rename_map = {
        "v": "volume",
        "vw": "vwap",
        "o": "open",
        "c": "close",
        "h": "high",
        "l": "low",
        "t": "t",
        "n": "count",
        "s": "symbol",
        # Alternate spellings some datasets use
        "timestamp": "t",
        "time": "t",
        "Symbol": "symbol",
    }
    cols = {c: rename_map.get(c, c) for c in df.columns}
    df = df.rename(columns=cols)

    # Ensure required fields exist
    required = ["t", "open", "high", "low", "close", "volume", "symbol"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing expected columns: {missing}")

    # Convert timestamp to UTC datetime index
    # Polygon timestamps are usually in milliseconds since epoch
    ts = pd.to_datetime(df["t"], unit="ms", utc=True, errors="coerce")
    df = df.assign(timestamp=ts)
    df = df.dropna(subset=["timestamp"])  # drop bad rows if any
    df = df.set_index("timestamp").sort_index()
    # Keep a clean set of columns
    ordered_cols = ["open", "high", "low", "close", "volume", "vwap", "count", "symbol"]
    for col in ordered_cols:
        if col not in df.columns:
            df[col] = pd.NA
    return df[ordered_cols]


def _filter_symbol_nq(df: pd.DataFrame) -> pd.DataFrame:
    # Symbol usually like "CME:NQZ24". Keep those starting with CME:NQ
    sym = df["symbol"].astype(str)
    return df[sym.str.startswith("CME:NQ")]


def _concat_nonempty(dfs: Iterable[pd.DataFrame]) -> pd.DataFrame:
    arr = [d for d in dfs if d is not None and not d.empty]
    if not arr:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "vwap", "count", "symbol"]).astype({})
    return pd.concat(arr).sort_index()


# ------------- Public API -------------


def fetch_nq_minute_range(
    start: date,
    end: date,
    *,
    cfg: Optional[S3Config] = None,
    verbose: bool = False,
) -> pd.DataFrame:
    """Fetch 1-minute aggregates for CME NQ contracts within [start, end].

    Returns a DataFrame indexed by UTC timestamp with columns
    [open, high, low, close, volume, vwap, count, symbol].
    """
    if start > end:
        raise ValueError("start date must be <= end date")

    cfg = cfg or load_config_from_env()
    s3 = make_s3_client(cfg)
    base_prefix = discover_minute_aggregates_prefix(s3, cfg.bucket)
    if verbose:
        print(f"Using minute aggregates prefix: {base_prefix}")

    cur = start
    frames: List[pd.DataFrame] = []
    while cur <= end:
        objs = list_objects_for_date(s3, cfg.bucket, base_prefix, cur)
        if verbose:
            print(f"{cur}: found {len(objs)} objects")
        for o in objs:
            key = o.get("Key")
            if not key:
                continue
            # Process only parquet/csv-like files
            kl = key.lower()
            if not (kl.endswith(PARQUET_LIKE) or kl.endswith(CSV_LIKE)):
                continue
            try:
                df_raw = _read_object_to_dataframe(s3, cfg.bucket, key)
                df_std = _standardize_agg_columns(df_raw)
                df_nq = _filter_symbol_nq(df_std)
                frames.append(df_nq)
            except Exception as exc:  # pragma: no cover - robust fetch loop
                if verbose:
                    print(f"Failed to process {key}: {exc}")
                continue
        cur += timedelta(days=1)

    return _concat_nonempty(frames)


def fetch_nq_minute_single_day(d: date, *, cfg: Optional[S3Config] = None, verbose: bool = False) -> pd.DataFrame:
    """Convenience: fetch 1-minute NQ futures for a single day."""
    return fetch_nq_minute_range(d, d, cfg=cfg, verbose=verbose)


if __name__ == "__main__":  # simple CLI for quick checks
    import argparse

    parser = argparse.ArgumentParser(description="Fetch NQ 1-minute bars from Polygon flat files (S3).")
    parser.add_argument("start", help="Start date YYYY-MM-DD")
    parser.add_argument("end", nargs="?", help="End date YYYY-MM-DD (defaults to start)")
    parser.add_argument("--verbose", action="store_true", help="Print discovery and progress info")
    args = parser.parse_args()

    start_d = datetime.strptime(args.start, "%Y-%m-%d").date()
    end_d = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else start_d

    df = fetch_nq_minute_range(start_d, end_d, verbose=args.verbose)
    print(df.tail())

