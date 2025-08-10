import streamlit as st
import pandas as pd
from datetime import date, timedelta

st.set_page_config(page_title="Stock Watchlist", layout="wide")

def init_state():
    if "watchlist" not in st.session_state:
        st.session_state.watchlist = [
            {
                "symbol": "MCD",
                "name": "McDonald's Corporation",
                "fair_value": 150.0,
                "fair_asof": date(2025, 7, 1),
                "price_close": 120.0,
                "price_asof": date(2025, 8, 10),
                "earnings_next": date(2025, 10, 25),
                "notes": "",
            },
            {
                "symbol": "AAPL",
                "name": "Apple Inc.",
                "fair_value": 180.0,
                "fair_asof": date(2025, 7, 2),
                "price_close": 195.0,
                "price_asof": date(2025, 8, 10),
                "earnings_next": date(2025, 10, 30),
                "notes": "",
            },
        ]
    st.session_state.setdefault("edit_index", None)
    st.session_state.setdefault("drawer_open", False)
    st.session_state.setdefault("show_export", False)

init_state()


def compute_fields(row):
    fair = row.get("fair_value")
    price = row.get("price_close")
    if fair in (None, 0) or price in (None, 0):
        row["upside_pct"] = None
        row["status"] = "INCOMPLETE"
    else:
        upside = (fair - price) / price * 100
        row["upside_pct"] = upside
        if upside >= 20:
            row["status"] = "UNDERVALUED"
        elif upside <= -10:
            row["status"] = "OVERVALUED"
        else:
            row["status"] = "FAIR"
    return row


def build_dataframe():
    df = pd.DataFrame([compute_fields(dict(r)) for r in st.session_state.watchlist])
    if df.empty:
        return df
    df["fair_asof"] = pd.to_datetime(df["fair_asof"]).dt.date
    df["price_asof"] = pd.to_datetime(df["price_asof"]).dt.date
    df["earnings_next"] = pd.to_datetime(df["earnings_next"]).dt.date
    today = date.today()
    df["soon_flag"] = df["earnings_next"].apply(
        lambda d: (d - today).days <= 21 and (d - today).days >= 0
    )
    return df


def render_top_bar():
    top_left, top_right = st.columns([1, 3])
    with top_left:
        st.markdown("## Stock Watchlist")
    with top_right:
        c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
        if c1.button("Add Ticker"):
            st.session_state.edit_index = None
            st.session_state.drawer_open = True
        if c2.button("Export CSV"):
            st.session_state.show_export = True
        price_filter = c3.date_input("Price As-Of", value=date.today())
        search_query = c4.text_input("Search", "")
    return price_filter, search_query


def render_table(df, price_filter, search_query):
    filtered = df.copy()
    if not df.empty:
        if search_query:
            mask = (
                filtered["symbol"].str.contains(search_query, case=False)
                | filtered["name"].str.contains(search_query, case=False)
            )
            filtered = filtered[mask]
        if price_filter:
            filtered = filtered[filtered["price_asof"] == price_filter]

    table_container = st.container()
    if filtered.empty:
        st.info("No tickers yet. Click Add Ticker to begin.")
        return

    header_cols = table_container.columns([1, 2, 1, 1, 1, 1, 1, 1, 1])
    headers = [
        "Symbol",
        "Name",
        "Fair Value",
        "Fair As-Of",
        "Price Close",
        "Price As-Of",
        "Upcoming Earnings",
        "Upside %",
        "Status",
    ]
    for col, label in zip(header_cols, headers):
        col.markdown(f"**{label}**")

    for idx, row in filtered.iterrows():
        cols = table_container.columns([1, 2, 1, 1, 1, 1, 1, 1, 1])
        if cols[0].button(f"{row['symbol']}", key=f"edit_{idx}"):
            st.session_state.edit_index = int(idx)
            st.session_state.drawer_open = True
        cols[1].markdown(
            f"<span style='color:#6B7280'>{row['name']}</span>",
            unsafe_allow_html=True,
        )
        cols[2].write(f"${row['fair_value']:.2f}")
        cols[3].write(row["fair_asof"])
        cols[4].write(f"${row['price_close']:.2f}")
        cols[5].write(row["price_asof"])
        badge = ""
        if row["soon_flag"]:
            badge = (
                " <span style='background-color:#FFF7ED;color:#C2410C;"
                "padding:2px 4px;border-radius:4px;font-size:0.8em;'>Soon</span>"
            )
        cols[6].markdown(f"{row['earnings_next']}{badge}", unsafe_allow_html=True)
        upside = row["upside_pct"]
        if upside is None:
            cols[7].markdown("<span style='color:#6B7280'>—</span>", unsafe_allow_html=True)
        else:
            color = "#6B7280"
            if upside >= 20:
                color = "#16A34A"
            elif upside <= -10:
                color = "#DC2626"
            cols[7].markdown(
                f"<span title='(Fair - Price) / Price' style='color:{color};'>{upside:+.1f}%</span>",
                unsafe_allow_html=True,
            )
        status_color = {
            "UNDERVALUED": "#16A34A",
            "OVERVALUED": "#DC2626",
            "FAIR": "#6B7280",
            "INCOMPLETE": "#6B7280",
        }[row["status"]]
        cols[8].markdown(
            f"<span style='background-color:{status_color};color:white;padding:2px 6px;"
            "border-radius:4px;font-size:0.8em;'>{row['status']}</span>",
            unsafe_allow_html=True,
        )


def render_drawer():
    if not st.session_state.drawer_open:
        return
    if st.session_state.edit_index is None:
        initial = {
            "symbol": "",
            "name": "",
            "fair_value": 0.0,
            "fair_asof": date.today(),
            "price_close": 0.0,
            "price_asof": date.today(),
            "earnings_next": date.today(),
            "notes": "",
        }
        title = "Add Ticker"
    else:
        initial = st.session_state.watchlist[st.session_state.edit_index]
        title = f"Edit {initial['symbol']}"
    with st.sidebar:
        st.markdown(f"### {title}")
        with st.form("edit_form"):
            symbol = st.text_input("Symbol", value=initial["symbol"])
            name = st.text_input("Name", value=initial["name"])
            fair_value = st.number_input(
                "Fair Value", value=initial["fair_value"], step=0.01, format="%.2f"
            )
            fair_asof = st.date_input("Fair As-Of", value=initial["fair_asof"])
            price_close = st.number_input(
                "Price Close", value=initial["price_close"], step=0.01, format="%.2f"
            )
            price_asof = st.date_input("Price As-Of", value=initial["price_asof"])
            earnings_next = st.date_input(
                "Upcoming Earnings", value=initial["earnings_next"]
            )
            notes = st.text_area("Notes", value=initial["notes"], height=100)
            save = st.form_submit_button("Save")
            cancel = st.form_submit_button("Cancel")
        if save:
            data = {
                "symbol": symbol.upper(),
                "name": name,
                "fair_value": fair_value,
                "fair_asof": fair_asof,
                "price_close": price_close,
                "price_asof": price_asof,
                "earnings_next": earnings_next,
                "notes": notes,
            }
            if st.session_state.edit_index is None:
                st.session_state.watchlist.append(data)
            else:
                st.session_state.watchlist[st.session_state.edit_index] = data
            st.session_state.drawer_open = False
        if cancel:
            st.session_state.drawer_open = False


def render_export_modal():
    if not st.session_state.show_export:
        return
    with st.modal("Export"):
        st.write("Export as CSV")
        if st.button("Close"):
            st.session_state.show_export = False


def main():
    price_filter, search_query = render_top_bar()
    df = build_dataframe()
    render_table(df, price_filter, search_query)
    render_drawer()
    render_export_modal()


if __name__ == "__main__":
    main()
