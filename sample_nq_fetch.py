"""Sample script: fetch 1-minute NQ futures bars from Polygon.

Supports two sources selectable at runtime:
- "api": Polygon REST Aggregates v2 (requires POLYGON_API_KEY)
- "flatfile": Polygon flat files via S3-compatible endpoint (requires POLYGON_S3_*)

Usage
-----
# API mode (symbol required)
python sample_nq_fetch.py --source api --symbol CME:NQZ24 --start 2024-08-01 --end 2024-08-02

# Flatfile mode (uses S3 creds from .env)
python sample_nq_fetch.py --source flatfile --days 2
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta

import pandas as pd

from typing import List

from polygon_flatfiles_nq import fetch_nq_minute_range
from polygon_api_nq import fetch_nq_minute_api


def previous_weekday(d: date) -> date:
    d = d - timedelta(days=1)
    while d.weekday() >= 5:  # 5=Sat, 6=Sun
        d -= timedelta(days=1)
    return d


def make_range_from_args(args) -> tuple[date, date]:
    if args.start and args.end:
        return (
            datetime.strptime(args.start, "%Y-%m-%d").date(),
            datetime.strptime(args.end, "%Y-%m-%d").date(),
        )
    if args.start and not args.end:
        d = datetime.strptime(args.start, "%Y-%m-%d").date()
        return (d, d)
    if args.days:
        end = previous_weekday(date.today())
        start = end
        # walk back N-1 additional weekdays
        for _ in range(args.days - 1):
            start = previous_weekday(start + timedelta(days=1))  # go to next day then step back
        return (start, end)
    # default: previous weekday
    d = previous_weekday(date.today())
    return (d, d)


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch sample NQ 1m bars from Polygon (API or flat files)")
    ap.add_argument("--source", choices=["api", "flatfile"], default="api", help="Data source to use")
    ap.add_argument("--symbol", action="append", help="Polygon futures symbol (e.g., CME:NQZ24). Repeat for multiple symbols. Required in api mode.")
    ap.add_argument("--start", help="Start date YYYY-MM-DD", default=None)
    ap.add_argument("--end", help="End date YYYY-MM-DD", default=None)
    ap.add_argument("--days", type=int, help="Fetch last N weekdays", default=None)
    ap.add_argument("--limit", type=int, help="Rows to display per symbol", default=5)
    ap.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    args = ap.parse_args()

    start, end = make_range_from_args(args)
    print(f"Fetching NQ 1m bars from {start} to {end} via {args.source} ...")
    if args.source == "api":
        # Quick check for API key presence to avoid silent empties
        import os
        from dotenv import load_dotenv  # type: ignore
        try:
            load_dotenv()
        except Exception:
            pass
        if not os.environ.get("POLYGON_API_KEY"):
            print("Warning: POLYGON_API_KEY is not set. Set it in .env or your environment.")
            print("Example: POLYGON_API_KEY=YOUR_KEY_HERE")
        if not args.symbol:
            print("Tip: For Aug 2024 dates, try --symbol CME:NQU24 (Sep) or a specific contract like CME:NQZ24 (Dec) if supported by your plan.")

    if args.source == "api":
        if not args.symbol:
            raise SystemExit("--symbol is required for --source api (e.g., --symbol CME:NQZ24)")
        symbols: List[str] = []
        for s in args.symbol:
            symbols.extend([t.strip() for t in s.split(",") if t.strip()])
        df = fetch_nq_minute_api(symbols, start, end, verbose=args.verbose)
    else:
        df = fetch_nq_minute_range(start, end, verbose=args.verbose)
    if df.empty:
        print("No data returned. Check dates, credentials, or dataset availability.")
        return

    print("\nSymbols fetched:")
    symbols = df["symbol"].dropna().unique().tolist()
    for s in symbols:
        cnt = (df["symbol"] == s).sum()
        print(f"- {s}: {cnt} rows")

    print("\nSample rows per symbol:")
    for s in symbols:
        sub = df[df["symbol"] == s].tail(args.limit)
        print(f"\n== {s} ==")
        print(sub)


if __name__ == "__main__":
    main()
