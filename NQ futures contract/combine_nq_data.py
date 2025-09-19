"""Combine NQ futures data and metadata CSV files into a single timeline."""
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIRECTORIES = [
    (BASE_DIR / "data", 0),
    (BASE_DIR / "NQ Meta data", 1),
]
OUTPUT_COMBINED = BASE_DIR / "data" / "nq_combined_5min.csv"
OUTPUT_GAPS = BASE_DIR / "data" / "nq_combined_5min_gaps.csv"
OUTPUT_OVERLAPS = BASE_DIR / "data" / "nq_combined_overlaps.csv"


def _normalize_time(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        time_utc = pd.to_datetime(series, unit="s", utc=True)
    else:
        sample = series.dropna().astype(str)
        if not sample.empty and sample.str.fullmatch(r"\d+").all():
            numeric = pd.to_numeric(series, errors="coerce")
            time_utc = pd.to_datetime(numeric, unit="s", utc=True)
        else:
            time_utc = pd.to_datetime(series, utc=True, errors="coerce")
            if time_utc.isna().any():
                numeric = pd.to_numeric(series, errors="coerce")
                if numeric.notna().all():
                    time_utc = pd.to_datetime(numeric, unit="s", utc=True)
                else:
                    missing = series[time_utc.isna()].unique()
                    raise ValueError(f"Unparsable timestamps: {missing}")
    if time_utc.dt.tz is None:
        return time_utc.dt.tz_localize("America/New_York")
    return time_utc.dt.tz_convert("America/New_York")


def _load_csv(path: Path, priority: int) -> pd.DataFrame:
    df = pd.read_csv(path, usecols=[0, 1, 2, 3, 4])
    df.columns = ["time", "open", "high", "low", "close"]
    df = df.assign(
        time=_normalize_time(df["time"]),
        source_file=path.name,
        source_priority=priority,
    )
    return df


def main() -> None:
    frames = []
    for directory, priority in DATA_DIRECTORIES:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.csv")):
            frames.append(_load_csv(path, priority))
    if not frames:
        raise SystemExit("No CSV files found to combine.")
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(["time", "source_priority"]).reset_index(drop=True)
    overlap_mask = combined.duplicated("time", keep=False)
    overlaps = combined.loc[overlap_mask].copy()
    deduped = combined.drop_duplicates("time", keep="first").sort_values("time").reset_index(drop=True)

    combined_output = deduped.drop(columns=["source_priority"])
    combined_output.to_csv(OUTPUT_COMBINED, index=False)

    if overlaps.empty:
        if OUTPUT_OVERLAPS.exists():
            OUTPUT_OVERLAPS.unlink()
    else:
        overlaps.drop(columns=["source_priority"]).to_csv(OUTPUT_OVERLAPS, index=False)

    deduped["prev_time"] = deduped["time"].shift(1)
    deduped["gap"] = deduped["time"] - deduped["prev_time"]
    gap_mode = deduped["gap"].dropna().mode()
    expected_gap = gap_mode.iloc[0] if not gap_mode.empty else pd.Timedelta(minutes=5)
    gap_report = deduped.loc[deduped["gap"] > expected_gap].copy()
    if gap_report.empty:
        if OUTPUT_GAPS.exists():
            OUTPUT_GAPS.unlink()
    else:
        gap_report["missing_bars"] = (gap_report["gap"] / expected_gap).round().astype(int) - 1
        gap_report = gap_report.loc[:, ["prev_time", "time", "gap", "missing_bars", "source_file"]]
        gap_report.to_csv(OUTPUT_GAPS, index=False)

    summary = {
        "rows_combined": len(combined),
        "rows_deduplicated": len(deduped),
        "overlap_rows": int(overlap_mask.sum()),
        "overlap_timestamp_count": int(overlaps["time"].nunique()),
        "gap_count": int(len(gap_report)),
        "time_start": deduped["time"].min().isoformat(),
        "time_end": deduped["time"].max().isoformat(),
        "expected_gap_minutes": float(expected_gap / pd.Timedelta(minutes=1)),
    }
    print(pd.Series(summary))


if __name__ == "__main__":
    main()
