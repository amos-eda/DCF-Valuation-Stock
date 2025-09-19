from __future__ import annotations

from typing import Dict, Optional


def _dist_ticks(price: Optional[float], level: Optional[float], tick_size: float) -> float:
    if price is None or level is None or tick_size == 0:
        return float("inf")
    return abs(price - level) / tick_size


def confluence_score(price: float, levels: Dict[str, Optional[float]], cfg: Dict[str, object], side: str = "long") -> int:
    """Compute a heuristic confluence score (0-100)."""
    prox_cfg = cfg.get("proximity", {})
    tick_size = cfg.get("market", {}).get("tick_size", 0.25)

    near = prox_cfg.get("near", 12)
    very_near = prox_cfg.get("very_near", 6)
    cluster_within = prox_cfg.get("cluster_within_ticks", 10)

    if side == "long":
        candidates = [levels.get(key) for key in ("asia_low", "london_low", "swing_low", "prev_low")]
    else:
        candidates = [levels.get(key) for key in ("asia_high", "london_high", "swing_high", "prev_high")]

    # Proximity points (cap 50)
    prox_pts = 0
    for level in candidates:
        d = _dist_ticks(price, level, tick_size)
        if d <= very_near:
            prox_pts += 20
        elif d <= near:
            prox_pts += 10
    prox_pts = min(prox_pts, 50)

    # Cluster points (max 30)
    vals = [lvl for lvl in candidates if lvl is not None]
    cluster_pts = 0
    for i in range(len(vals)):
        for j in range(i + 1, len(vals)):
            if _dist_ticks(vals[i], vals[j], tick_size) <= cluster_within:
                cluster_pts = 30
                break
        if cluster_pts:
            break

    # Freshness heuristic (max 20)
    freshness_pts = 0
    freshness_flag = levels.get("fresh", 1.0)
    if freshness_flag is not None:
        freshness_pts = min(20, int(20 * float(freshness_flag)))

    return int(min(100, prox_pts + cluster_pts + freshness_pts))
