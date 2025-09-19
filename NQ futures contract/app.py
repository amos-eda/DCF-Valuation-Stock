import io
from pathlib import Path
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yaml

from nqlevels.backtest import run_backtest
from nqlevels.confluence import confluence_score
from nqlevels.io import load_bars_from_excel
from nqlevels.levels import most_recent_swing, prev_day_hl, swings_4h
from nqlevels.proximity import nearest_levels
from nqlevels.sessions import daily_session_high_low, most_recent_before


st.set_page_config(page_title="NQ NY-Open Session Levels", layout="wide")

CARD_COLUMNS = 3
LEVEL_LABELS = {
    "asia_high": "Asia session high",
    "asia_low": "Asia session low",
    "london_high": "London session high",
    "london_low": "London session low",
    "prev_high": "Previous day high",
    "prev_low": "Previous day low",
    "swing_high": "4h swing high",
    "swing_low": "4h swing low",
}


@st.cache_data(show_spinner=False)
def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


@st.cache_data(show_spinner=False)
def _load_excel(cfg: dict) -> pd.DataFrame:
    return load_bars_from_excel(cfg)


def _read_uploaded_yaml(file) -> dict:
    if file is None:
        return {}
    content = yaml.safe_load(file)
    return content or {}


def _ensure_timezone(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    if df["timestamp"].dt.tz is None and cfg.get("timezone"):
        tz = cfg["timezone"]
        df["timestamp"] = df["timestamp"].dt.tz_localize(tz)
    return df


def _is_valid(value: Optional[float]) -> bool:
    return value is not None and not pd.isna(value)


def _format_currency(value: Optional[float]) -> str:
    return f"" if _is_valid(value) else "--"


def _format_level_label(name: Optional[str]) -> str:
    if not name:
        return "level"
    return LEVEL_LABELS.get(name, name.replace("_", " "))


def _trade_price_window(bars: pd.DataFrame, entry_ts: pd.Timestamp, cfg: dict) -> pd.DataFrame:
    plot_cfg = cfg.get("plot", {})
    before = plot_cfg.get("snapshot_bars_before", 120)
    after = plot_cfg.get("snapshot_bars_after", 60)
    start = entry_ts - pd.Timedelta(minutes=before)
    end = entry_ts + pd.Timedelta(minutes=after)
    window = bars[(bars["timestamp"] >= start) & (bars["timestamp"] <= end)]
    if window.empty:
        return bars[(bars["timestamp"] >= start) & (bars["timestamp"] <= end)]
    return window


def _build_trade_figure(trade: pd.Series, bars: pd.DataFrame, cfg: dict) -> go.Figure:
    entry_ts = pd.to_datetime(trade["entry_ts"])
    segment = _trade_price_window(bars, entry_ts, cfg)
    fig = go.Figure(
        data=[
            go.Candlestick(
                x=segment["timestamp"],
                open=segment["open"],
                high=segment["high"],
                low=segment["low"],
                close=segment["close"],
                name="Price",
            )
        ]
    )

    def _add_level(value, label, color, position="top left", dash="solid"):
        if _is_valid(value):
            fig.add_hline(
                y=value,
                line_color=color,
                line_dash=dash,
                annotation_text=label,
                annotation_position=position,
            )

    _add_level(trade.get("asia_high"), "Asia H", "#3b82f6", "top left")
    _add_level(trade.get("asia_low"), "Asia L", "#3b82f6", "bottom left")
    _add_level(trade.get("london_high"), "London H", "#a855f7", "top right")
    _add_level(trade.get("london_low"), "London L", "#a855f7", "bottom right")
    _add_level(trade.get("prev_high"), "Prev H", "#f97316", "top left", dash="dash")
    _add_level(trade.get("prev_low"), "Prev L", "#f97316", "bottom left", dash="dash")
    _add_level(trade.get("swing_high"), "4h Swing H", "#22c55e", "top right")
    _add_level(trade.get("swing_low"), "4h Swing L", "#22c55e", "bottom right")
    _add_level(trade.get("trigger_level"), _format_level_label(trade.get("trigger_level_name")).title(), "#eab308", "top right", dash="dot")

    if _is_valid(trade.get("stop")):
        _add_level(trade.get("stop"), "Stop", "#ef4444", "bottom right", dash="dash")
    if _is_valid(trade.get("target")):
        _add_level(trade.get("target"), "Target", "#10b981", "top right", dash="dash")

    entry_color = "#22c55e" if trade.get("side") == "long" else "#ef4444"
    exit_color = {
        "tp": "#14b8a6",
        "sl": "#f43f5e",
        "none": "#94a3b8",
    }.get(trade.get("outcome"), "#94a3b8")

    fig.add_trace(
        go.Scatter(
            x=[trade.get("entry_ts")],
            y=[trade.get("entry_price")],
            mode="markers+text",
            name="Entry",
            marker=dict(size=12, color=entry_color, symbol="triangle-up"),
            text=["Entry"],
            textposition="top center",
        )
    )

    if _is_valid(trade.get("exit_price")) and pd.notnull(trade.get("exit_ts")):
        fig.add_trace(
            go.Scatter(
                x=[trade.get("exit_ts")],
                y=[trade.get("exit_price")],
                mode="markers+text",
                name="Exit",
                marker=dict(size=12, color=exit_color, symbol="triangle-down"),
                text=["Exit"],
                textposition="bottom center",
            )
        )

    fig.update_layout(
        height=520,
        margin=dict(l=40, r=40, t=50, b=40),
        showlegend=False,
    )
    return fig


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


def _render_level_table(trade: pd.Series):
    rows = []
    for label, key in (
        ("Asia High", "asia_high"),
        ("Asia Low", "asia_low"),
        ("London High", "london_high"),
        ("London Low", "london_low"),
        ("Previous Day High", "prev_high"),
        ("Previous Day Low", "prev_low"),
        ("4h Swing High", "swing_high"),
        ("4h Swing Low", "swing_low"),
    ):
        value = trade.get(key)
        if _is_valid(value):
            rows.append({"Level": label, "Price": f"{value:.2f}"})
    if rows:
        st.markdown("##### Key levels in play")
        st.table(pd.DataFrame(rows))


st.sidebar.header("Configuration")
def_cfg_path = Path("config.yaml")
def_cfg = _load_yaml(def_cfg_path) if def_cfg_path.exists() else {}

uploaded_yaml = st.sidebar.file_uploader("Override YAML", type=["yaml", "yml"], key="yaml")
user_cfg = _read_uploaded_yaml(uploaded_yaml)
cfg = def_cfg.copy()
cfg.update(user_cfg)

uploaded_excel = st.sidebar.file_uploader("Excel minute bars", type=["xlsx"], key="xlsx")
if uploaded_excel is not None:
    cfg.setdefault("excel", {})["path"] = io.BytesIO(uploaded_excel.getbuffer())

if "excel" not in cfg or "path" not in cfg.get("excel", {}):
    st.warning("Provide an Excel file via the sidebar to get started.")
    st.stop()

with st.spinner("Loading data..."):
    bars = _load_excel(cfg)
    bars = _ensure_timezone(bars, cfg)

if bars.empty:
    st.error("Loaded dataset is empty.")
    st.stop()

asia_levels = daily_session_high_low(
    bars,
    cfg["sessions"]["asia"]["start"],
    cfg["sessions"]["asia"]["end"],
)
london_levels = daily_session_high_low(
    bars,
    cfg["sessions"]["london"]["start"],
    cfg["sessions"]["london"]["end"],
)
prev_levels = prev_day_hl(
    bars,
    cfg["prev_day"].get("rth_only", True),
    cfg["prev_day"].get("rth_start", "09:30"),
    cfg["prev_day"].get("rth_end", "16:00"),
)
swings = swings_4h(
    bars,
    cfg["swing_4h"].get("left_right_bars", 2),
    cfg["swing_4h"].get("resample", "240T"),
)
swing_high = most_recent_swing(swings, "short")
swing_low = most_recent_swing(swings, "long")

bars_dates = bars["timestamp"].dt.date.unique()
if len(bars_dates) == 0:
    st.error("No valid timestamps found in dataset.")
    st.stop()

st.sidebar.subheader("Date selection")
recent_dates = sorted(bars_dates)
options = recent_dates[-30:] if len(recent_dates) > 30 else recent_dates
selected_date = st.sidebar.selectbox("Session date", options)

ny_cfg = cfg["sessions"]["ny"]
ny_start = pd.Timestamp(f"{selected_date} {ny_cfg['start']}", tz=bars["timestamp"].dt.tz)
ny_end = pd.Timestamp(f"{selected_date} {ny_cfg['end']}", tz=bars["timestamp"].dt.tz)

plot_cfg = cfg.get("plot", {})
pre = pd.Timedelta(minutes=plot_cfg.get("snapshot_bars_before", 120))
post = pd.Timedelta(minutes=plot_cfg.get("snapshot_bars_after", 60))
window = bars[
    (bars["timestamp"] >= ny_start - pre) & (bars["timestamp"] <= ny_end + post)
]

fig = go.Figure(
    data=[
        go.Candlestick(
            x=window["timestamp"],
            open=window["open"],
            high=window["high"],
            low=window["low"],
            close=window["close"],
            name="Price",
        )
    ]
)

asia = most_recent_before(asia_levels, ny_start)
london = most_recent_before(london_levels, ny_start)
prev_row = prev_levels.loc[selected_date] if selected_date in prev_levels.index else None

if asia:
    fig.add_hline(y=asia["high"], line_color="blue", annotation_text="Asia H", annotation_position="top left")
    fig.add_hline(y=asia["low"], line_color="blue", annotation_text="Asia L", annotation_position="bottom left")
if london:
    fig.add_hline(y=london["high"], line_color="purple", annotation_text="London H", annotation_position="top right")
    fig.add_hline(y=london["low"], line_color="purple", annotation_text="London L", annotation_position="bottom right")
if prev_row is not None:
    fig.add_hline(y=prev_row.prev_high, line_color="orange", annotation_text="Prev H", annotation_position="top left", line_dash="dash")
    fig.add_hline(y=prev_row.prev_low, line_color="orange", annotation_text="Prev L", annotation_position="bottom left", line_dash="dash")
if swing_high is not None:
    fig.add_hline(y=swing_high, line_color="green", annotation_text="4h Swing H", annotation_position="top left")
if swing_low is not None:
    fig.add_hline(y=swing_low, line_color="green", annotation_text="4h Swing L", annotation_position="bottom right")

fig.update_layout(height=600, margin=dict(l=40, r=40, t=40, b=40))

ny_slice = bars[
    (bars["timestamp"] >= ny_start)
    & (bars["timestamp"] <= ny_start + pd.Timedelta(minutes=5))
]

with st.spinner("Running backtest..."):
    bt = run_backtest(bars, cfg, asia_levels, london_levels)

snapshot_tab, performance_tab = st.tabs(["Session Snapshot", "Performance Dashboard"])

with snapshot_tab:
    st.plotly_chart(fig, use_container_width=True)
    st.subheader("Nearest levels at NY open")
    if not ny_slice.empty:
        anchor = ny_slice.iloc[0]["close"]
        supports = [
            asia["low"] if asia else None,
            london["low"] if london else None,
            prev_row.prev_low if prev_row is not None else None,
            swing_low,
        ]
        resistances = [
            asia["high"] if asia else None,
            london["high"] if london else None,
            prev_row.prev_high if prev_row is not None else None,
            swing_high,
        ]
        ns, nr, ds, dr = nearest_levels(anchor, supports, resistances, cfg["market"]["tick_size"])
        levels_meta = {
            "asia_low": supports[0],
            "asia_high": resistances[0],
            "london_low": supports[1],
            "london_high": resistances[1],
            "prev_low": supports[2],
            "prev_high": resistances[2],
            "swing_low": supports[3],
            "swing_high": resistances[3],
            "fresh": 1.0,
        }
        score_long = confluence_score(anchor, levels_meta, cfg, side="long")
        score_short = confluence_score(anchor, levels_meta, cfg, side="short")

        table = pd.DataFrame(
            {
                "anchor": [anchor],
                "nearest_support": [ns],
                "dist_support_ticks": [ds],
                "nearest_resistance": [nr],
                "dist_resistance_ticks": [dr],
                "confluence_long": [score_long],
                "confluence_short": [score_short],
            }
        )
        st.table(table)
    else:
        st.info("No NY session bars found for the selected date.")

with performance_tab:
    st.subheader("Strategy performance")
    if bt.empty:
        st.info("No trades generated for the configured period.")
    else:
        bt_sorted = bt.sort_values("entry_ts").reset_index(drop=True)
        bt_sorted["trade_id"] = bt_sorted.index
        bt_sorted["cum_pnl_dollars"] = bt_sorted["pnl_dollars"].cumsum()

        total_pnl = bt_sorted["pnl_dollars"].sum()
        total_trades = len(bt_sorted)
        win_rate = (
            (bt_sorted["outcome"] == "tp").sum() / total_trades * 100.0
            if total_trades
            else 0.0
        )
        avg_ticks = bt_sorted["pnl_ticks"].mean()
        outcome_summary = (
            bt_sorted.groupby("outcome")["pnl_dollars"]
            .agg(count="count", total_pnl="sum", avg_pnl="mean")
            .round(2)
        )

        net_color = "#18c964" if total_pnl >= 0 else "#f25050"
        fill_color = "rgba(24,201,100,0.18)" if total_pnl >= 0 else "rgba(242,80,80,0.18)"

        card_cols = st.columns(4)
        card_cols[0].markdown(
            f"""
            <div style='padding:16px;border-radius:12px;border:1px solid {net_color};background-color:rgba(240,240,240,0.05);'>
                <div style='font-size:0.9rem;color:#9ca3af;'>Net P&L</div>
                <div style='font-size:1.6rem;font-weight:600;color:{net_color};'></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        card_cols[1].metric("Total trades", total_trades)
        card_cols[2].metric("Win rate", f"{win_rate:.1f}%")
        card_cols[3].metric("Avg P&L (ticks)", f"{avg_ticks:.2f}")

        fig_pnl = go.Figure()
        fig_pnl.add_trace(
            go.Scatter(
                x=bt_sorted["entry_ts"],
                y=bt_sorted["cum_pnl_dollars"],
                mode="lines+markers",
                name="Cumulative P&L",
                line=dict(color=net_color, width=2),
                fill="tozeroy",
                fillcolor=fill_color,
            )
        )
        fig_pnl.update_layout(
            title="Cumulative P&L",
            xaxis_title="Entry timestamp",
            yaxis_title="P&L ($)",
            height=380,
            margin=dict(l=40, r=20, t=50, b=40),
        )
        st.plotly_chart(fig_pnl, use_container_width=True)

        if "selected_trade_id" not in st.session_state:
            st.session_state["selected_trade_id"] = 0
        if st.session_state["selected_trade_id"] not in bt_sorted.index:
            st.session_state["selected_trade_id"] = int(bt_sorted.index[0])

        st.markdown("### Trade explorer")
        for start in range(0, len(bt_sorted), CARD_COLUMNS):
            columns = st.columns(CARD_COLUMNS)
            for offset, col in enumerate(columns):
                idx = start + offset
                if idx >= len(bt_sorted):
                    continue
                trade = bt_sorted.iloc[idx]
                trade_id = int(trade["trade_id"])
                selected = trade_id == st.session_state["selected_trade_id"]
                marker = ">>" if selected else "--"
                label_lines = [
                    f"{marker} {trade['date']} - {trade['side'].upper()}",
                    f"P&L: {trade['pnl_dollars']:.2f}",
                    f"Outcome: {trade['outcome'].upper()} | Conf {trade['confluence_score']}",
                ]
                label = "\n".join(label_lines)
                if col.button(label, key=f"trade_card_{trade_id}", use_container_width=True):
                    st.session_state["selected_trade_id"] = trade_id
                hold_minutes = trade.get("holding_minutes")
                hold_text = f"{hold_minutes:.1f}" if _is_valid(hold_minutes) else "N/A"
                pnl_color = "#18c964" if trade["pnl_dollars"] >= 0 else "#f25050"
                caption_html = (
                    "<div style='font-size:0.8rem;color:#94a3b8;'>" 
                    + f"Level: {_format_level_label(trade.get('trigger_level_name'))} | "
                    + f"Hold: {hold_text} min | "
                    + f"P&L: <span style='color:{pnl_color};font-weight:600;'>{_format_currency(trade.get('pnl_dollars'))}</span>"
                    + "</div>"
                )
                col.markdown(caption_html, unsafe_allow_html=True)

        selected_trade = bt_sorted.loc[st.session_state["selected_trade_id"]]
        st.markdown("#### Trade detail")
        detail_cols = st.columns(4)
        detail_cols[0].metric("Entry price", _format_currency(selected_trade.get("entry_price")))
        detail_cols[1].metric("Exit price", _format_currency(selected_trade.get("exit_price")))
        detail_cols[2].metric("Outcome", selected_trade.get("outcome", "").upper())
        hold_text = f"{selected_trade['holding_minutes']:.1f}" if _is_valid(selected_trade.get("holding_minutes")) else "N/A"
        detail_cols[3].metric("Hold (min)", hold_text)

        detail_fig = _build_trade_figure(selected_trade, bars, cfg)
        st.plotly_chart(detail_fig, use_container_width=True)

        _render_level_table(selected_trade)
        st.markdown("##### Explanation")
        st.markdown(_build_trade_explanation(selected_trade))

        st.markdown("#### Outcome breakdown")
        st.dataframe(outcome_summary)

        st.markdown("#### Trade log")
        st.dataframe(bt_sorted)
