from pathlib import Path
import textwrap

path = Path("app.py")
lines = path.read_text().splitlines()
for idx, line in enumerate(lines):
    if line.strip().startswith("def _build_trade_explanation"):
        start = idx
        break
else:
    raise SystemExit("function not found")
end = start
while end < len(lines) and lines[end].strip() != "":
    end += 1
new_block = textwrap.dedent(
    """
    def _build_trade_explanation(trade: pd.Series) -> str:
        side = trade.get("side", "").title()
        trigger_name = _format_level_label(trade.get("trigger_level_name"))
        trigger_price = trade.get("trigger_level")
        trigger_text = f" ({trigger_price:.2f})" if _is_valid(trigger_price) else ""
        outcome = trade.get("outcome", "none").upper()
        holding = trade.get("holding_minutes")
        holding_text = f"{holding:.1f} min" if _is_valid(holding) else "N/A"

        dist_sup = trade.get("dist_support_ticks")
        dist_res = trade.get("dist_resistance_ticks")
        dist_sup_text = f"{dist_sup:.1f}" if _is_valid(dist_sup) else "N/A"
        dist_res_text = f"{dist_res:.1f}" if _is_valid(dist_res) else "N/A"
        pnl_ticks = trade.get("pnl_ticks")
        pnl_ticks_text = f"{pnl_ticks:.1f}" if _is_valid(pnl_ticks) else "N/A"

        entry_ts = trade.get("entry_ts")
        exit_ts = trade.get("exit_ts")
        entry_price = trade.get("entry_price")
        entry_price_text = f"{entry_price:.2f}" if _is_valid(entry_price) else "N/A"
        exit_price_text = _format_currency(trade.get("exit_price"))
        nearest_support_text = _format_currency(trade.get("nearest_support"))
        nearest_resistance_text = _format_currency(trade.get("nearest_resistance"))
        stop_text = _format_currency(trade.get("stop"))
        target_text = _format_currency(trade.get("target"))
        pnl_text = _format_currency(trade.get("pnl_dollars"))

        lines = [
            f"- **Setup**: {side} sweep + retrace off {trigger_name}{trigger_text}.",
            f"- **Execution**: Entered at {entry_ts} ({entry_price_text}); exit {outcome} at {exit_ts} ({exit_price_text}).",
            f"- **Risk**: Stop {stop_text} - Target {target_text} - Hold time {holding_text}.",
            f"- **Key distances**: Nearest support {nearest_support_text} ({dist_sup_text} ticks), Nearest resistance {nearest_resistance_text} ({dist_res_text} ticks).",
            f"- **Result**: P&L {pnl_text} ({pnl_ticks_text} ticks) with confluence score {trade.get('confluence_score')}.",
        ]
        return "\n".join(lines)
    """
).strip("\n").splitlines()
lines[start:end] = new_block
path.write_text("\n".join(lines) + "\n")
