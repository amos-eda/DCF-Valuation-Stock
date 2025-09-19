from __future__ import annotations

from typing import Optional


def stop_loss(
    entry_price: float,
    nearest_support: Optional[float],
    nearest_resistance: Optional[float],
    cfg,
    side: str,
) -> Optional[float]:
    tick_size = cfg.get("market", {}).get("tick_size", 0.25)
    pad_ticks = cfg.get("risk", {}).get("stop_padding_ticks", 0)
    pad_value = pad_ticks * tick_size

    if side == "long" and nearest_support is not None:
        return nearest_support - pad_value
    if side == "short" and nearest_resistance is not None:
        return nearest_resistance + pad_value
    return None


def take_profit(entry_price: float, stop_price: Optional[float], cfg, side: str) -> Optional[float]:
    if stop_price is None:
        return None
    risk_cfg = cfg.get("risk", {}).get("take_profit", {})
    mode = risk_cfg.get("mode", "rr")
    if mode != "rr":  # other modes can be added later
        return None

    rr_multiple = risk_cfg.get("rr_multiple", 2.0)
    risk = abs(entry_price - stop_price)
    if side == "long":
        return entry_price + rr_multiple * risk
    return entry_price - rr_multiple * risk
