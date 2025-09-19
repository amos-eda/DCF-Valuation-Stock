import io
from pathlib import Path
from typing import Any, Dict, Union

import pandas as pd
import pytz


def _resolve_excel_path(path: Union[str, Path, io.BytesIO]) -> Union[Path, io.BytesIO]:
    """Return a pathlib Path when the config contains a filesystem path, otherwise pass through."""
    if isinstance(path, io.BytesIO):
        path.seek(0)
        return path
    return Path(path)


def load_bars_from_excel(cfg: Dict[str, Any]) -> pd.DataFrame:
    """Load OHLCV minute bars from Excel and normalize column names/timestamps."""
    excel_cfg = cfg.get("excel", {})
    if not excel_cfg:
        raise ValueError("Missing 'excel' section in configuration")

    source = _resolve_excel_path(excel_cfg.get("path"))
    sheet_name = excel_cfg.get("sheet_name", 0)
    ts_col = excel_cfg.get("timestamp_col", "timestamp")
    ohlc = excel_cfg.get("ohlc", {})
    volume_col = excel_cfg.get("volume_col")

    df = pd.read_excel(source, sheet_name=sheet_name)

    rename_map = {
        ts_col: "timestamp",
        ohlc.get("open", "open"): "open",
        ohlc.get("high", "high"): "high",
        ohlc.get("low", "low"): "low",
        ohlc.get("close", "close"): "close",
    }
    if volume_col and volume_col in df.columns:
        rename_map[volume_col] = "volume"

    df = df.rename(columns=rename_map)

    missing = {col for col in ("timestamp", "open", "high", "low", "close") if col not in df.columns}
    if missing:
        raise ValueError(f"Missing expected columns in Excel input: {sorted(missing)}")

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    if df["timestamp"].isna().any():
        raise ValueError("Found invalid timestamps after parsing Excel file")

    tz_name = cfg.get("timezone")
    if tz_name:
        tz = pytz.timezone(tz_name)
        if df["timestamp"].dt.tz is None:
            df["timestamp"] = df["timestamp"].dt.tz_localize(tz)
        else:
            df["timestamp"] = df["timestamp"].dt.tz_convert(tz)

    df = df.sort_values("timestamp").reset_index(drop=True)
    return df
