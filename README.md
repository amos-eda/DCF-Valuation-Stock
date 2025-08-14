# ICT Liquidity Sweep + FVG Backtester

`fvg_liquidity_sweep.py` is a standalone script that backtests a simplified
version of the ICT Liquidity Sweep + Fair Value Gap strategy on US equities.
It downloads 1‑minute bars from Polygon.io, computes key indicators (ATR,
relative volume, VWAP) and evaluates strict three‑candle FVG structures.  Each
setup receives a score based on cleanliness, size and session quality.  Results
are saved as parquet files and Excel reports.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set your Polygon API key in the environment:

```bash
export POLYGON_API_KEY="<your key>"
```

## CLI Usage

The script exposes a small CLI.  Example:

```bash
python fvg_liquidity_sweep.py \
  --symbols BBWI MSFT GOOGL HOOD \
  --months 3 --tf 1m --session-only
```

Arguments:

- `--symbols` – list of ticker symbols to process.
- `--months` – number of months of historical data to download (default 3).
- `--start`/`--end` – optional ISO timestamps overriding the rolling window.
- `--config` – path to the YAML config (defaults to `config.yaml`).

Outputs are stored in:

- `data/raw/<SYMBOL>.parquet`
- `data/clean/<SYMBOL>.parquet`
- `reports/<SYMBOL>_signals.xlsx`
- `reports/summary.xlsx`

Optionally, charts may be produced in `charts/` (not implemented in this basic
version).

## Strategy Overview

1. **Indicators** – ATR(14), RVOL(20) and session VWAP are computed on the
   1‑minute data.
2. **Structure Detection** – Swing pivots use a `(2,2)` fractal.  Three‑candle
   Fair Value Gaps with strict gap rules are identified.  A simple "untouched"
   rule ensures no candle overlaps the gap before entry.
3. **Scoring** – Clean FVGs, ideal size in ATR and entries during AM/PM sessions
   receive points.  Weights are configurable in `config.yaml`.

This project is intentionally lightweight to serve as a reproducible starting
point for further experimentation.
