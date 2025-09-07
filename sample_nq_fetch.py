"""Sample script: fetch 1-minute NQ futures bars via Polygon flat files.

Reads credentials from `.env` (POLYGON_S3_*) and prints a preview.

Usage
-----
python sample_nq_fetch.py                  # fetch previous weekday
python sample_nq_fetch.py --start 2024-08-01 --end 2024-08-02
python sample_nq_fetch.py --days 3         # fetch last 3 weekdays
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta

import pandas as pd

from polygon_flatfiles_nq import fetch_nq_minute_range


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
    ap = argparse.ArgumentParser(description="Fetch sample NQ 1m bars from Polygon flat files")
    ap.add_argument("--start", help="Start date YYYY-MM-DD", default=None)
    ap.add_argument("--end", help="End date YYYY-MM-DD", default=None)
    ap.add_argument("--days", type=int, help="Fetch last N weekdays", default=None)
    ap.add_argument("--limit", type=int, help="Rows to display per symbol", default=5)
    ap.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    args = ap.parse_args()

    start, end = make_range_from_args(args)
    print(f"Fetching NQ 1m bars from {start} to {end} ...")

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

