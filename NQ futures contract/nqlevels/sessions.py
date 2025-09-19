from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Optional

import pandas as pd


def _parse_time(time_str: str) -> datetime.time:
    return datetime.strptime(time_str, "%H:%M").time()


def session_mask(df: pd.DataFrame, start_str: str, end_str: str) -> pd.Series:
    """Return a boolean mask for rows falling inside the session window (time-of-day only)."""
    if "timestamp" not in df.columns:
        raise ValueError("DataFrame must contain a 'timestamp' column")

    start_time = _parse_time(start_str)
    end_time = _parse_time(end_str)
    clock = df["timestamp"].dt.time

    if start_time <= end_time:
        return (clock >= start_time) & (clock < end_time)
    return (clock >= start_time) | (clock < end_time)


def _session_bounds_for_date(
    midnight: pd.Timestamp,
    start_str: str,
    end_str: str,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    start_time = _parse_time(start_str)
    end_time = _parse_time(end_str)
    start_offset = timedelta(hours=start_time.hour, minutes=start_time.minute)
    end_offset = timedelta(hours=end_time.hour, minutes=end_time.minute)

    if start_time <= end_time:
        start = midnight + pd.Timedelta(seconds=start_offset.total_seconds())
        end = midnight + pd.Timedelta(seconds=end_offset.total_seconds())
    else:
        start = midnight - pd.Timedelta(days=1) + pd.Timedelta(seconds=start_offset.total_seconds())
        end = midnight + pd.Timedelta(seconds=end_offset.total_seconds())
    return start, end


def daily_session_high_low(df: pd.DataFrame, start_str: str, end_str: str) -> pd.DataFrame:
    """Aggregate session highs/lows per calendar date (using the session end date)."""
    if df.empty:
        cols = ["session_high", "session_low", "session_start", "session_end"]
        return pd.DataFrame(columns=cols).set_index(pd.Index([], name="date"))

    ts = df["timestamp"]
    if ts.dt.tz is None:
        raise ValueError("Timestamps must be timezone-aware before computing sessions")

    dates = ts.dt.normalize().drop_duplicates().sort_values()
    records = []

    for midnight in dates:
        start, end = _session_bounds_for_date(midnight, start_str, end_str)
        window = df[(ts >= start) & (ts < end)]
        if window.empty:
            continue
        records.append(
            {
                "date": midnight.date(),
                "session_high": window["high"].max(),
                "session_low": window["low"].min(),
                "session_start": start,
                "session_end": end,
            }
        )

    if not records:
        cols = ["session_high", "session_low", "session_start", "session_end"]
        return pd.DataFrame(columns=cols).set_index(pd.Index([], name="date"))

    result = pd.DataFrame(records).set_index("date").sort_index()
    return result


def most_recent_before(levels_df: pd.DataFrame, cutoff_ts: pd.Timestamp) -> Optional[Dict[str, object]]:
    """Return the most recent session row whose end timestamp is at or before cutoff."""
    if levels_df.empty:
        return None
    eligible = levels_df[levels_df["session_end"] <= cutoff_ts]
    if eligible.empty:
        return None
    row = eligible.iloc[-1]
    return {
        "date": eligible.index[-1],
        "high": row["session_high"],
        "low": row["session_low"],
        "session_start": row["session_start"],
        "session_end": row["session_end"],
    }
