"""Excel Join Inspector - Streamlit app

Allows analysts to upload two Excel files, map join keys, choose a join type,
apply cleaning options, and inspect duplicates, unmatched rows, and join
statistics. Provides downloadable CSV/XLSX outputs and a small metrics chart.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import io
import math

import numpy as np
import pandas as pd
import streamlit as st


# ---------------------------- Utilities ----------------------------


def _uploaded_bytes(file) -> bytes:
    """Return stable bytes for caching from an UploadedFile or pathlike."""
    if file is None:
        return b""
    if hasattr(file, "getvalue"):
        return file.getvalue()
    with open(file, "rb") as f:  # type: ignore[arg-type]
        return f.read()


@st.cache_data(show_spinner=False)
def load_excel_sheets(file_bytes: bytes) -> Dict[str, pd.DataFrame]:
    if not file_bytes:
        return {}
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    sheets: Dict[str, pd.DataFrame] = {}
    for name in xls.sheet_names:
        sheets[name] = xls.parse(name)
    return sheets


def clean_keys(
    df: pd.DataFrame,
    keys: List[str],
    *,
    trim_ws: bool,
    case_norm: Optional[str],  # 'upper' | 'lower' | None
    coerce_type: bool,
    blanks_as_null: bool,
) -> Tuple[pd.DataFrame, List[str]]:
    """Apply cleaning to key columns. Returns a copy and key list.

    Strategy for type coercion: to maximize matching across mixed types while
    minimizing surprises, convert key columns to string after optional trims
    and casing. This handles numeric <-> string mismatches while preserving
    exact values (e.g., leading zeros remain if present in the source string).
    """
    df = df.copy()
    for k in keys:
        if k not in df.columns:
            continue
        col = df[k]
        # Treat blanks as nulls first for object-like dtypes
        if blanks_as_null and col.dtype == object:
            df[k] = col.replace({"": np.nan}).replace(r"^\s+$", np.nan, regex=True)
        if trim_ws and col.dtype == object:
            df[k] = df[k].astype("string").str.strip()
        if case_norm in ("upper", "lower"):
            df[k] = df[k].astype("string").str.upper() if case_norm == "upper" else df[k].astype("string").str.lower()
        if coerce_type:
            # Coerce to pandas "string" dtype which preserves NA and is robust for joins
            df[k] = df[k].astype("string")
    return df, keys


def duplicate_report(df: pd.DataFrame, keys: List[str]) -> Tuple[pd.DataFrame, Dict[str, int]]:
    if not keys:
        return pd.DataFrame(), {"distinct_keys": 0, "duplicate_keys": 0}
    grp = df.groupby(keys, dropna=False).size().rename("__size__").reset_index()
    dup = grp[grp["__size__"] > 1].sort_values("__size__", ascending=False)
    counts = {
        "distinct_keys": int(grp.shape[0]),
        "duplicate_keys": int((grp["__size__"] > 1).sum()),
    }
    return dup, counts


def unmatched_frames(left: pd.DataFrame, right: pd.DataFrame, keys: List[str]) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return outer merge with indicator and subsets for unmatched left/right."""
    merged = left.merge(right, how="outer", on=keys, indicator=True, suffixes=("__left", "__right"))
    left_only = merged[merged["_merge"] == "left_only"]
    right_only = merged[merged["_merge"] == "right_only"]
    return merged, left_only, right_only


def perform_join(
    left: pd.DataFrame,
    right: pd.DataFrame,
    left_keys: List[str],
    right_keys: List[str],
    how: str,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Perform join while preserving a provenance column __match_status__.

    We first align key names by renaming Right's key columns to Left's names
    (order-preserving), then perform an outer merge with indicator. The final
    result is filtered by the requested join type.
    """
    if len(left_keys) != len(right_keys):
        raise ValueError("Left and Right key selections must have the same length (mapping in order).")

    right_renames = {r: l for l, r in zip(left_keys, right_keys)}
    right_aligned = right.rename(columns=right_renames)

    outer = left.merge(right_aligned, how="outer", on=left_keys, indicator=True, suffixes=("__left", "__right"))
    status_map = {"left_only": "left_only", "right_only": "right_only", "both": "both"}
    outer["__match_status__"] = outer["_merge"].map(status_map)

    if how == "left":
        result = outer[outer["_merge"].isin(["left_only", "both"])]
    elif how == "right":
        result = outer[outer["_merge"].isin(["right_only", "both"])]
    elif how == "inner":
        result = outer[outer["_merge"] == "both"]
    else:  # full outer
        result = outer

    result = result.drop(columns=["_merge"]).copy()
    return result, outer


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def to_xlsx_bytes(df: pd.DataFrame, sheet_name: str = "Joined") -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return buf.getvalue()


def dtype_summary(df: pd.DataFrame, keys: List[str]) -> Dict[str, str]:
    return {k: str(df[k].dtype) if k in df.columns else "<missing>" for k in keys}


def warn_key_issues(left: pd.DataFrame, right: pd.DataFrame, left_keys: List[str], right_keys: List[str]):
    issues: List[str] = []
    # Null checks
    for name, df, keys in (("Left", left, left_keys), ("Right", right, right_keys)):
        for k in keys:
            if k in df.columns and df[k].isna().any():
                issues.append(f"{name}: key '{k}' contains nulls")
    # Dtype comparison after cleaning; show side-by-side summaries
    lsum = dtype_summary(left, left_keys)
    rsum = dtype_summary(right, right_keys)
    if len(left_keys) == len(right_keys):
        mismatches = []
        for lk, rk in zip(left_keys, right_keys):
            if lsum.get(lk) != rsum.get(rk):
                mismatches.append((lk, lsum.get(lk), rk, rsum.get(rk)))
        if mismatches:
            for lk, ldt, rk, rdt in mismatches:
                issues.append(f"Dtype mismatch: Left.{lk}={ldt} vs Right.{rk}={rdt} — enable 'Type coerce keys'.")
    if issues:
        st.warning("\n".join(issues))


# ---------------------------- Streamlit UI ----------------------------


st.set_page_config(page_title="Excel Join Inspector", layout="wide")
st.title("Excel Join Inspector")
st.caption("Join two Excel datasets, inspect match quality, and download diagnostics.")

with st.sidebar:
    st.header("Inputs")
    left_file = st.file_uploader("Left.xlsx", type=["xlsx", "xlsm", "xls"], key="left_file")
    right_file = st.file_uploader("Right.xlsx", type=["xlsx", "xlsm", "xls"], key="right_file")

    left_sheets = load_excel_sheets(_uploaded_bytes(left_file))
    right_sheets = load_excel_sheets(_uploaded_bytes(right_file))

    left_sheet = st.selectbox("Left sheet", list(left_sheets) or ["<none>"])
    right_sheet = st.selectbox("Right sheet", list(right_sheets) or ["<none>"])

    left_df = left_sheets.get(left_sheet, pd.DataFrame())
    right_df = right_sheets.get(right_sheet, pd.DataFrame())

    st.divider()
    st.subheader("Join Keys")
    left_cols = list(left_df.columns)
    right_cols = list(right_df.columns)
    left_keys = st.multiselect("Left key columns (in order)", left_cols, default=[])
    right_keys = st.multiselect("Right key columns (in order; mapped to Left order)", right_cols, default=[])

    st.subheader("Join Type")
    how = st.radio("Join type", ["Left", "Right", "Full Outer", "Inner"], horizontal=True)
    how_map = {"Left": "left", "Right": "right", "Full Outer": "outer", "Inner": "inner"}
    how_val = how_map[how]

    st.subheader("Cleaning")
    trim_ws = st.checkbox("Trim whitespace in keys", value=True)
    case_choice = st.selectbox("Case normalize keys", ["None", "UPPER", "lower"], index=0)
    case_norm = {"None": None, "UPPER": "upper", "lower": "lower"}[case_choice]
    coerce_type = st.checkbox("Type coerce keys (to string)", value=True)
    blanks_as_null = st.checkbox("Treat blank strings as nulls", value=True)

    with st.expander("Advanced Filters", expanded=False):
        left_query = st.text_input("Left filter (pandas query)", placeholder="e.g., Country == 'US' and Amount > 0")
        right_query = st.text_input("Right filter (pandas query)", placeholder="e.g., Status != 'Closed'")

    run = st.button("Run Analysis", type="primary")


def apply_optional_filter(df: pd.DataFrame, query: str) -> pd.DataFrame:
    if not query or df.empty:
        return df
    try:
        return df.query(query, engine="python")
    except Exception as exc:
        st.warning(f"Filter ignored due to error: {exc}")
        return df


if run:
    if left_df.empty or right_df.empty:
        st.error("Please upload both Left and Right Excel files and select sheets.")
        st.stop()
    if not left_keys or not right_keys:
        st.error("Please select join keys on both sides.")
        st.stop()
    if len(left_keys) != len(right_keys):
        st.error("Join key counts must match (mapping is positional).")
        st.stop()

    # Apply filters
    left_filt = apply_optional_filter(left_df, left_query)
    right_filt = apply_optional_filter(right_df, right_query)

    # Cleaning
    left_clean, lk = clean_keys(left_filt, left_keys, trim_ws=trim_ws, case_norm=case_norm, coerce_type=coerce_type, blanks_as_null=blanks_as_null)
    right_clean, rk = clean_keys(right_filt, right_keys, trim_ws=trim_ws, case_norm=case_norm, coerce_type=coerce_type, blanks_as_null=blanks_as_null)

    warn_key_issues(left_clean, right_clean, lk, rk)

    # Duplicate analysis before join
    left_dups, left_counts = duplicate_report(left_clean, lk)
    right_dups, right_counts = duplicate_report(right_clean, rk)

    # Join execution + outer lens for unmatched
    result, outer = perform_join(left_clean, right_clean, lk, rk, how=how_val)
    unmatched_left = outer[outer["__match_status__"] == "left_only"]
    unmatched_right = outer[outer["__match_status__"] == "right_only"]
    matched_both = outer[outer["__match_status__"] == "both"]

    # Stats
    left_rows = int(left_clean.shape[0])
    right_rows = int(right_clean.shape[0])
    final_rows = int(result.shape[0])
    both_rows = int(matched_both.shape[0])
    left_only_rows = int(unmatched_left.shape[0])
    right_only_rows = int(unmatched_right.shape[0])
    expansion = (final_rows / max(left_rows, right_rows)) if max(left_rows, right_rows) else math.nan

    # ---------------------------- Layout ----------------------------
    tabs = st.tabs(["Overview", "Join Result", "Duplicates", "Unmatched", "Settings Snapshot"])

    with tabs[0]:
        st.subheader("High-level Counts & Warnings")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Left rows", left_rows)
            st.metric("Left distinct keys", left_counts["distinct_keys"]) 
            st.metric("Left duplicate keys", left_counts["duplicate_keys"]) 
        with c2:
            st.metric("Right rows", right_rows)
            st.metric("Right distinct keys", right_counts["distinct_keys"]) 
            st.metric("Right duplicate keys", right_counts["duplicate_keys"]) 
        with c3:
            st.metric("Matched (both)", both_rows)
            st.metric("Unmatched Left", left_only_rows)
            st.metric("Unmatched Right", right_only_rows)
            st.metric("Final joined rows", final_rows)
        st.write(f"Estimated expansion factor: {expansion:.3f}" if not math.isnan(expansion) else "Expansion factor: n/a")

        # Small bar chart
        chart_df = pd.DataFrame(
            {
                "metric": [
                    "Left rows",
                    "Right rows",
                    "Left distinct keys",
                    "Right distinct keys",
                    "Matched (both)",
                    "Unmatched Left",
                    "Unmatched Right",
                    "Final rows",
                ],
                "value": [
                    left_rows,
                    right_rows,
                    left_counts["distinct_keys"],
                    right_counts["distinct_keys"],
                    both_rows,
                    left_only_rows,
                    right_only_rows,
                    final_rows,
                ],
            }
        )
        st.bar_chart(chart_df.set_index("metric"))

    with tabs[1]:
        st.subheader("Join Result (Preview)")
        st.dataframe(result.head(200), use_container_width=True)
        c1, c2 = st.columns(2)
        with c1:
            st.download_button("Download Joined CSV", data=to_csv_bytes(result), file_name="joined_result.csv", mime="text/csv")
        with c2:
            st.download_button("Download Joined XLSX", data=to_xlsx_bytes(result), file_name="joined_result.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with tabs[2]:
        st.subheader("Duplicates")
        st.markdown("Left duplicates (rows where key multiplicity > 1)")
        st.dataframe(left_dups.head(200), use_container_width=True)
        st.download_button("Download Left Duplicates CSV", data=to_csv_bytes(left_dups), file_name="left_duplicates.csv", mime="text/csv")
        st.markdown("Right duplicates (rows where key multiplicity > 1)")
        st.dataframe(right_dups.head(200), use_container_width=True)
        st.download_button("Download Right Duplicates CSV", data=to_csv_bytes(right_dups), file_name="right_duplicates.csv", mime="text/csv")

    with tabs[3]:
        st.subheader("Unmatched")
        st.caption("Note: 'unmatched' is shown under a full outer lens regardless of the selected join; actual filtered-out rows depend on the chosen join type.")
        st.markdown("Unmatched in Left (no match in Right)")
        st.dataframe(unmatched_left.head(200), use_container_width=True)
        st.download_button("Download Unmatched Left CSV", data=to_csv_bytes(unmatched_left), file_name="unmatched_left.csv", mime="text/csv")
        st.markdown("Unmatched in Right (no match in Left)")
        st.dataframe(unmatched_right.head(200), use_container_width=True)
        st.download_button("Download Unmatched Right CSV", data=to_csv_bytes(unmatched_right), file_name="unmatched_right.csv", mime="text/csv")

    with tabs[4]:
        st.subheader("Settings Snapshot")
        st.json(
            {
                "left_sheet": left_sheet,
                "right_sheet": right_sheet,
                "left_keys": left_keys,
                "right_keys": right_keys,
                "join_type": how,
                "cleaning": {
                    "trim_whitespace": trim_ws,
                    "case_normalize": case_norm,
                    "type_coerce_to_string": coerce_type,
                    "blanks_as_null": blanks_as_null,
                },
                "filters": {
                    "left_query": left_query,
                    "right_query": right_query,
                },
                "notes": {
                    "join_exclusion": (
                        "Left join excludes Right-only rows; Right join excludes Left-only; "
                        "Full outer excludes none; Inner keeps only matches."
                    )
                },
            }
        )
