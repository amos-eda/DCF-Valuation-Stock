from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, Optional, Tuple

import numpy as np
import pandas as pd

from .confluence import confluence_score
from .levels import most_recent_swing, prev_day_hl, swings_4h
from .proximity import nearest_levels
from .risk import stop_loss, take_profit
from .sessions import most_recent_before
from .signals import detect_sweep_and_retrace


def _time_from_str(value: str) -> datetime.time:
    return datetime.strptime(value, "%H:%M").time()


def _pick_session(levels_df: pd.DataFrame, date, cutoff_ts, use_recent: bool):
    if levels_df.empty:
        return None
    if use_recent:
        return most_recent_before(levels_df, cutoff_ts)
    if date in levels_df.index:
        row = levels_df.loc[date]
        return {
            "date": date,
            "high": row["session_high"],
            "low": row["session_low"],
            "session_start": row["session_start"],
            "session_end": row["session_end"],
        }
    return most_recent_before(levels_df, cutoff_ts)


def _first_available_bar(day_df: pd.DataFrame, target_time: datetime.time) -> Optional[pd.Timestamp]:
    matches = day_df[day_df["timestamp"].dt.time >= target_time]
    if matches.empty:
        return None
    return matches.iloc[0]["timestamp"]


def _search_level(
    series: Iterable[Tuple[str, Optional[float]]],
    window: pd.DataFrame,
    side: str,
    retrace_bars: int,
) -> Tuple[Optional[int], Optional[float], Optional[str]]:
    best_idx = None
    best_level = None
    best_name = None
    for name, level in series:
        if level is None:
            continue
        idx = detect_sweep_and_retrace(window, level, side, retrace_bars)
        if idx is None:
            continue
        if best_idx is None or idx < best_idx:
            best_idx = idx
            best_level = level
            best_name = name
    return best_idx, best_level, best_name


def _is_valid(value: Optional[float]) -> bool:
    return value is not None and not pd.isna(value)


def _fmt_price(value: Optional[float]) -> str:
    return f"{value:.2f}" if _is_valid(value) else "N/A"


def _fmt_ticks(value: Optional[float]) -> str:
    return f"{value:.1f}" if _is_valid(value) else "N/A"


def _fmt_currency(value: Optional[float]) -> str:
    return f"${value:,.2f}" if _is_valid(value) else "N/A"


def _format_level_label(name: Optional[str]) -> str:
    if not name:
        return "reference level"
    return name.replace("_", " ")


def _build_trade_summary(data: Dict[str, object]) -> str:
    side = str(data.get("side", "")).title()
    trigger_name = _format_level_label(data.get("trigger_level_name"))
    trigger_price = _fmt_price(data.get("trigger_level"))
    entry_ts = data.get("entry_ts")
    exit_ts = data.get("exit_ts")
    entry_price = _fmt_price(data.get("entry_price"))
    exit_price = _fmt_price(data.get("exit_price"))
    stop = _fmt_price(data.get("stop"))
    target = _fmt_price(data.get("target"))
    hold = _fmt_ticks(data.get("holding_minutes"))
    nearest_support = _fmt_price(data.get("nearest_support"))
    nearest_resistance = _fmt_price(data.get("nearest_resistance"))
    dist_sup = _fmt_ticks(data.get("dist_support_ticks"))
    dist_res = _fmt_ticks(data.get("dist_resistance_ticks"))
    pnl_dollars = _fmt_currency(data.get("pnl_dollars"))
    pnl_ticks = _fmt_ticks(data.get("pnl_ticks"))
    confluence = data.get("confluence_score")

    lines = [
        f"Setup: {side} sweep/retrace anchored to {trigger_name} at {trigger_price}.",
        f"Execution: Enter {entry_ts} ({entry_price}), exit {exit_ts} ({exit_price}). Outcome {data.get('outcome', 'N/A').upper()}.",
        f"Risk: Stop {stop}, target {target}, hold {hold} minutes.",
        f"Key levels: Support {nearest_support} ({dist_sup} ticks), resistance {nearest_resistance} ({dist_res} ticks).",
        f"Result: {pnl_dollars} ({pnl_ticks} ticks) - Confluence {confluence}.",
    ]
    return "\n".join(lines)


def run_backtest(
    df: pd.DataFrame,
    cfg: Dict[str, object],
    asia_levels: pd.DataFrame,
    london_levels: pd.DataFrame,
) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    df = df.sort_values("timestamp").copy()
    tz = df["timestamp"].dt.tz
    if tz is None:
        raise ValueError("Input DataFrame must use timezone-aware timestamps")

    df["date"] = df["timestamp"].dt.date

    ny_cfg = cfg.get("sessions", {}).get("ny", {})
    ny_start_time = _time_from_str(ny_cfg.get("start", "09:30"))
    ny_end_time = _time_from_str(ny_cfg.get("end", "16:00"))

    entry_cfg = cfg.get("entry", {})
    direction = entry_cfg.get("direction", "both")
    retrace_bars = entry_cfg.get("retrace_bars", 3)
    time_limit = entry_cfg.get("time_limit_minutes", 90)

    ny_open_cfg = cfg.get("ny_open", {})
    lookback_minutes = ny_open_cfg.get("lookback_minutes", time_limit)
    scan_minutes = min(lookback_minutes, time_limit)
    use_recent_only = ny_open_cfg.get("use_most_recent_sessions_only", True)

    market_cfg = cfg.get("market", {})
    tick_size = market_cfg.get("tick_size", 0.25)
    tick_value = market_cfg.get("tick_value", 5.0)

    risk_cfg = cfg.get("backtest", {})
    slippage_ticks = risk_cfg.get("slippage_ticks", 0)
    commission = risk_cfg.get("commission_per_contract", 0.0)
    contracts = risk_cfg.get("contracts", 1)

    prev_levels = prev_day_hl(
        df,
        cfg.get("prev_day", {}).get("rth_only", True),
        cfg.get("prev_day", {}).get("rth_start", "09:30"),
        cfg.get("prev_day", {}).get("rth_end", "16:00"),
    )

    swings = swings_4h(
        df,
        cfg.get("swing_4h", {}).get("left_right_bars", 2),
        cfg.get("swing_4h", {}).get("resample", "240T"),
    )

    results = []

    for date, day_df in df.groupby("date"):
        mask_ny = (day_df["timestamp"].dt.time >= ny_start_time) & (
            day_df["timestamp"].dt.time < ny_end_time
        )
        day_ny = day_df.loc[mask_ny].reset_index(drop=True)
        if day_ny.empty:
            continue

        ny_open_ts = pd.Timestamp(f"{date} {ny_cfg.get('start', '09:30')}", tz=tz)
        first_bar = _first_available_bar(day_ny, ny_start_time)
        if first_bar is not None:
            ny_open_ts = first_bar

        scan_end = ny_open_ts + pd.Timedelta(minutes=scan_minutes)
        window = day_ny[
            (day_ny["timestamp"] >= ny_open_ts) & (day_ny["timestamp"] <= scan_end)
        ].reset_index(drop=True)
        if window.empty:
            continue

        asia = _pick_session(asia_levels, date, ny_open_ts, use_recent_only)
        london = _pick_session(london_levels, date, ny_open_ts, use_recent_only)
        prev_row = prev_levels.loc[date] if date in prev_levels.index else None

        swing_high = most_recent_swing(swings, "short")
        swing_low = most_recent_swing(swings, "long")

        support_levels = [
            ("asia_low", asia.get("low") if asia else None),
            ("london_low", london.get("low") if london else None),
            ("prev_low", prev_row.prev_low if prev_row is not None else None),
            ("swing_low", swing_low),
        ]
        resistance_levels = [
            ("asia_high", asia.get("high") if asia else None),
            ("london_high", london.get("high") if london else None),
            ("prev_high", prev_row.prev_high if prev_row is not None else None),
            ("swing_high", swing_high),
        ]

        anchor_price = window.iloc[0]["close"]
        ns, nr, dist_sup, dist_res = nearest_levels(
            anchor_price,
            [lvl for _, lvl in support_levels],
            [lvl for _, lvl in resistance_levels],
            tick_size,
        )

        levels_snapshot = {
            name: value
            for name, value in support_levels + resistance_levels
        }
        levels_snapshot["fresh"] = 1.0
        levels_snapshot["anchor_price"] = anchor_price

        idx_long, long_level, long_name = (None, None, None)
        idx_short, short_level, short_name = (None, None, None)

        if direction in ("long", "both"):
            idx_long, long_level, long_name = _search_level(
                support_levels, window, "long", retrace_bars
            )
        if direction in ("short", "both"):
            idx_short, short_level, short_name = _search_level(
                resistance_levels, window, "short", retrace_bars
            )

        candidates = []
        if idx_long is not None:
            candidates.append(("long", idx_long, long_level, long_name))
        if idx_short is not None:
            candidates.append(("short", idx_short, short_level, short_name))

        for side, idx, level, level_name in sorted(candidates, key=lambda x: x[1]):
            bar = window.iloc[idx]
            bar_ts = bar["timestamp"]
            if (bar_ts - ny_open_ts) > pd.Timedelta(minutes=time_limit):
                continue

            entry = bar["open"]
            sl = stop_loss(entry, ns, nr, cfg, side)
            tp = take_profit(entry, sl, cfg, side)

            slippage = slippage_ticks * tick_size
            if side == "long":
                entry += slippage
            else:
                entry -= slippage

            path = window.iloc[idx:]
            outcome = "none"
            exit_price = path.iloc[-1]["close"]
            exit_ts = path.iloc[-1]["timestamp"]
            for _, row in path.iterrows():
                ts = row["timestamp"]
                high = row["high"]
                low = row["low"]
                if side == "long":
                    if sl is not None and low <= sl:
                        outcome = "sl"
                        exit_price = sl
                        exit_ts = ts
                        break
                    if tp is not None and high >= tp:
                        outcome = "tp"
                        exit_price = tp
                        exit_ts = ts
                        break
                else:
                    if sl is not None and high >= sl:
                        outcome = "sl"
                        exit_price = sl
                        exit_ts = ts
                        break
                    if tp is not None and low <= tp:
                        outcome = "tp"
                        exit_price = tp
                        exit_ts = ts
                        break

            pnl_points = exit_price - entry if side == "long" else entry - exit_price
            pnl_ticks = pnl_points / tick_size if tick_size else np.nan
            pnl_dollars = pnl_ticks * tick_value * contracts - commission

            score = confluence_score(anchor_price, levels_snapshot, cfg, side)
            holding_minutes = (
                (exit_ts - bar_ts).total_seconds() / 60.0 if exit_ts is not None else None
            )

            record = {
                "date": date,
                "side": side,
                "entry_ts": bar_ts,
                "exit_ts": exit_ts,
                "entry_price": entry,
                "exit_price": exit_price,
                "stop": sl,
                "target": tp,
                "outcome": outcome,
                "holding_minutes": holding_minutes,
                "trigger_level": level,
                "trigger_level_name": level_name,
                "nearest_support": ns,
                "nearest_resistance": nr,
                "dist_support_ticks": dist_sup,
                "dist_resistance_ticks": dist_res,
                "confluence_score": score,
                "asia_high": levels_snapshot.get("asia_high"),
                "asia_low": levels_snapshot.get("asia_low"),
                "london_high": levels_snapshot.get("london_high"),
                "london_low": levels_snapshot.get("london_low"),
                "prev_high": levels_snapshot.get("prev_high"),
                "prev_low": levels_snapshot.get("prev_low"),
                "swing_high": levels_snapshot.get("swing_high"),
                "swing_low": levels_snapshot.get("swing_low"),
                "anchor_price": anchor_price,
                "pnl_points": pnl_points,
                "pnl_ticks": pnl_ticks,
                "pnl_dollars": pnl_dollars,
            }
            record["summary_of_trade"] = _build_trade_summary(record)

            results.append(record)
            break  # one trade per day (first in time order)

    return pd.DataFrame(results)
