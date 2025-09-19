from __future__ import annotations

from typing import Iterable, Optional, Tuple

import numpy as np


def ticks(distance: float, tick_size: float) -> float:
    return distance / tick_size if tick_size else np.nan


def nearest_levels(
    price: float,
    supports: Iterable[Optional[float]],
    resistances: Iterable[Optional[float]],
    tick_size: float,
) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    """Return nearest support/resistance and their distances in ticks."""
    supports = [s for s in supports if s is not None]
    resistances = [r for r in resistances if r is not None]

    nearest_support = None
    dist_support = None
    diffs = [price - s for s in supports if s <= price]
    if diffs:
        delta = min(diffs)
        nearest_support = price - delta
        dist_support = ticks(delta, tick_size)

    nearest_resistance = None
    dist_resistance = None
    diffr = [r - price for r in resistances if r >= price]
    if diffr:
        delta = min(diffr)
        nearest_resistance = price + delta
        dist_resistance = ticks(delta, tick_size)

    return nearest_support, nearest_resistance, dist_support, dist_resistance
