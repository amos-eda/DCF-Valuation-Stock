"""Fetch 1-minute NQ futures bars from Databento for the past year."""
from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict

from databento import Historical


ENV_FILE = Path(__file__).with_name(".env")


def _load_local_env(env_path: Path = ENV_FILE) -> None:
    """Populate os.environ with key/value pairs from a simple .env file."""
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        os.environ.setdefault(key, value)


_load_local_env()

DEFAULT_DATASET = os.getenv("DATABENTO_DATASET", "GLBX.MDP3")
DEFAULT_SCHEMA = os.getenv("DATABENTO_SCHEMA", "ohlcv-1m")
DEFAULT_SYMBOL = os.getenv("DATABENTO_SYMBOL", "NQ.c.0")
DEFAULT_DAYS = int(os.getenv("DATABENTO_DAYS", "365"))
DEFAULT_STYPE_IN = os.getenv("DATABENTO_STYPE_IN", "continuous")
DEFAULT_STYPE_OUT = os.getenv("DATABENTO_STYPE_OUT", "instrument_id")
DEFAULT_MIN_ROWS = int(os.getenv("DATABENTO_MIN_ROWS", "5"))
DEFAULT_END_MARGIN_MINUTES = int(os.getenv("DATABENTO_END_MARGIN_MINUTES", "10"))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        default=DEFAULT_DATASET,
        help=f"Databento dataset code (default: {DEFAULT_DATASET})",
    )
    parser.add_argument(
        "--schema",
        default=DEFAULT_SCHEMA,
        help=f"Databento schema (default: {DEFAULT_SCHEMA})",
    )
    parser.add_argument(
        "--symbol",
        default=DEFAULT_SYMBOL,
        help=(
            "Symbol or symbol pattern to request (default: NQ.c.0 continuous contract)."
            " For continuous symbols use '[ROOT].[ROLL_RULE].[RANK]'."
        ),
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help=f"Number of days back from today to request (default: {DEFAULT_DAYS})",
    )
    parser.add_argument(
        "--stype-in",
        default=DEFAULT_STYPE_IN,
        help=f"Input symbology type (default: {DEFAULT_STYPE_IN})",
    )
    parser.add_argument(
        "--stype-out",
        default=DEFAULT_STYPE_OUT,
        help=f"Output symbology type (default: {DEFAULT_STYPE_OUT})",
    )
    parser.add_argument(
        "--end-margin",
        type=int,
        default=DEFAULT_END_MARGIN_MINUTES,
        help=(
            "Minutes to subtract from current UTC time when setting the end of the range "
            f"(default: {DEFAULT_END_MARGIN_MINUTES})."
        ),
    )
    parser.add_argument(
        "--min-rows",
        type=int,
        default=DEFAULT_MIN_ROWS,
        help=f"Minimum rows expected before writing output (default: {DEFAULT_MIN_ROWS})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data") / "databento_nq_ohlcv_1m.parquet",
        help="Path to write the results (default: data/databento_nq_ohlcv_1m.parquet)",
    )
    return parser


def _ensure_api_key() -> str:
    api_key = os.getenv("DATABENTO_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Set DATABENTO_API_KEY in .env or environment before running this script."
        )
    return api_key


def _build_time_range(days: int, end_margin_minutes: int) -> Dict[str, datetime]:
    now = datetime.now(timezone.utc)
    end = now - timedelta(minutes=max(end_margin_minutes, 0))
    start = end - timedelta(days=days)
    if start >= end:
        start = end - timedelta(minutes=1)
    return {"start": start, "end": end}


def _validate_rows(df, min_rows: int) -> None:
    if len(df) < min_rows:
        raise RuntimeError(
            f"Databento response contained {len(df)} rows, expected at least {min_rows}."
        )


def fetch_databento(
    dataset: str,
    schema: str,
    symbol: str,
    days: int,
    stype_in: str,
    stype_out: str,
    end_margin: int,
    min_rows: int,
    output: Path,
) -> Path:
    api_key = _ensure_api_key()
    client = Historical(key=api_key)

    time_range = _build_time_range(days, end_margin)

    response = client.timeseries.get_range(
        dataset=dataset,
        schema=schema,
        symbols=symbol,
        start=time_range["start"],
        end=time_range["end"],
        stype_in=stype_in,
        stype_out=stype_out,
    )

    df = response.to_df()
    _validate_rows(df, min_rows)

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() == ".csv":
        df.to_csv(output, index=False)
    else:
        df.to_parquet(output, index=False)

    preview = df.head(min(5, len(df)))
    preview_path = output.with_name(output.stem + "_preview.csv")
    preview.to_csv(preview_path, index=False)

    return output


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    destination = fetch_databento(
        dataset=args.dataset,
        schema=args.schema,
        symbol=args.symbol,
        days=args.days,
        stype_in=args.stype_in,
        stype_out=args.stype_out,
        end_margin=args.end_margin,
        min_rows=args.min_rows,
        output=args.output,
    )
    print(f"Saved {args.schema} data for {args.symbol} to {destination}")
    print(f"Preview written to {destination.with_name(destination.stem + '_preview.csv')}")


if __name__ == "__main__":
    main()
