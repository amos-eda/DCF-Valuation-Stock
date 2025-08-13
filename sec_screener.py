# pip install requests pandas openpyxl tenacity python-dateutil
"""SEC 10-Q screener script."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import requests
from dateutil import parser
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

WATCHLIST = [
    {"name": "Bath & Body Works", "ticker": "BBWI"},
    {"name": "Microsoft", "ticker": "MSFT"},
    {"name": "Google (Alphabet)", "ticker": "GOOGL"},
    {"name": "Robinhood", "ticker": "HOOD"},
    {"name": "NVIDIA", "ticker": "NVDA"},
    {"name": "Figma", "ticker": None},  # private; handle gracefully
]

HEADERS = {"User-Agent": "Jerry Mcguire sec-10q-screener (amos@example.com)",
    "Accept": "application/json",
    "Accept-Encoding": "gzip, deflate"}
RATE_LIMIT_SECONDS = 0.21

session = requests.Session()
session.headers.update(HEADERS)


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(requests.RequestException),
    reraise=True,
)
def make_request(
    url: str, *, headers: Dict[str, str] = HEADERS
) -> requests.Response:
    """Make HTTP GET request with retry and rate limiting.

    The SEC requires a User-Agent header to be sent with all requests; callers
    can override the default by providing ``headers``.
    """
    time.sleep(RATE_LIMIT_SECONDS)
    resp = session.get(url, headers=headers, timeout=30)
    if resp.status_code == 429 or 500 <= resp.status_code < 600:
        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            try:
                time.sleep(float(retry_after))
            except ValueError:
                pass
        resp.raise_for_status()
    resp.raise_for_status()
    return resp


def fetch_json(url: str) -> Dict:
    """Fetch JSON from URL."""
    resp = make_request(url, headers=HEADERS)
    return resp.json()


def load_ticker_map(cache_dir: Path) -> pd.DataFrame:
    """Load ticker to CIK mapping."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "company_tickers.json"
    if cache_file.exists():
        data = json.loads(cache_file.read_text())
    else:
        data = fetch_json("https://www.sec.gov/files/company_tickers.json")
        cache_file.write_text(json.dumps(data))
    df = pd.DataFrame(list(data.values()))
    df["ticker"] = df["ticker"].str.upper()
    df["cik_str"] = df["cik_str"].astype(str).str.zfill(10)
    return df


def resolve_cik(ticker: str, mapping_df: pd.DataFrame) -> Optional[str]:
    """Return CIK for ticker if exists."""
    row = mapping_df.loc[mapping_df["ticker"] == ticker.upper()]
    if not row.empty:
        return row.iloc[0]["cik_str"]
    return None


def get_latest_10q(cik: str) -> Optional[Dict]:
    """Fetch latest 10-Q filing metadata for given CIK."""
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    data = fetch_json(url)
    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    if not forms:
        return None
    fields = [
        "filingDate",
        "reportDate",
        "accessionNumber",
        "primaryDocument",
    ]
    for form_type, amended in (("10-Q", False), ("10-Q/A", True)):
        for idx, f in reversed(list(enumerate(forms))):
            if f == form_type:
                info = {k: recent.get(k, [""])[idx] for k in fields}
                info["reportDate"] = info["reportDate"] or info["filingDate"]
                info["amended"] = amended
                return info
    return None


def build_10q_url(cik: str, accession: str, primary_doc: str) -> str:
    """Construct URL to primary 10-Q document."""
    cik_trim = str(int(cik))
    accession_clean = accession.replace("-", "")
    return (
        f"https://www.sec.gov/Archives/edgar/data/{cik_trim}/{accession_clean}/{primary_doc}"
    )


def detect_quarter(report_date_str: str) -> str:
    """Detect quarter from report date."""
    dt = parser.parse(report_date_str)
    if 1 <= dt.month <= 3:
        return "Q1"
    if 4 <= dt.month <= 6:
        return "Q2"
    return "Q3"


def download_file(url: str, out_path: Path) -> None:
    """Download file from URL to output path."""
    resp = make_request(url, headers=HEADERS)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(resp.content)


def write_excel(rows: List[Dict], path: Path) -> None:
    """Write collected rows to an Excel file."""
    df = pd.DataFrame(rows)
    df.sort_values("Ticker", inplace=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Watchlist")
        ws = writer.sheets["Watchlist"]
        for column_cells in ws.columns:
            length = max(len(str(cell.value)) if cell.value is not None else 0 for cell in column_cells)
            ws.column_dimensions[column_cells[0].column_letter].width = length + 2


def main() -> None:
    cache_dir = Path(".cache")
    rows: List[Dict] = []
    mapping_error = None
    try:
        mapping_df = load_ticker_map(cache_dir)
    except Exception as exc:  # pylint: disable=broad-except
        mapping_df = pd.DataFrame(columns=["ticker", "cik_str"])
        mapping_error = str(exc)

    for item in WATCHLIST:
        name = item["name"]
        ticker = item.get("ticker")
        print(f"Processing {ticker or name}...")
        row: Dict[str, Optional[str]] = {
            "Ticker": ticker or "",
            "Name": name,
            "CIK": "",
            "Latest 10Q Filing Date": "",
            "Report Date": "",
            "Quarter": "",
            "Accession Number": "",
            "Primary Document": "",
            "10Q URL": "",
            "Saved File Path": "",
            "Amended": False,
            "Status": "",
            "Notes": "",
            "Company Facts URL": "",
        }
        notes: List[str] = []
        try:
            if mapping_error:
                row["Status"] = "ERROR"
                notes.append(f"Ticker mapping unavailable: {mapping_error}")
            elif not ticker:
                row["Status"] = "NO_SEC_FILINGS"
                notes.append("No ticker provided; company may be private.")
            else:
                cik = resolve_cik(ticker, mapping_df)
                if not cik:
                    row["Status"] = "NO_SEC_FILINGS"
                    notes.append("Ticker not found in SEC mapping.")
                else:
                    row["CIK"] = cik
                    filing = get_latest_10q(cik)
                    if not filing:
                        row["Status"] = "NO_SEC_FILINGS"
                        notes.append("No 10-Q filings found.")
                    else:
                        report_date = filing["reportDate"]
                        quarter = detect_quarter(report_date)
                        if parser.parse(report_date).month >= 10:
                            notes.append("Q4 not applicable for 10-Q")
                        url = build_10q_url(cik, filing["accessionNumber"], filing["primaryDocument"])
                        out_dir = Path("sec_filings") / ticker
                        ext = Path(filing["primaryDocument"]).suffix
                        filename = f"{ticker}_{report_date}_Q{quarter[-1]}_10-Q"
                        if filing["amended"]:
                            filename += "_A"
                        filename += ext
                        out_path = out_dir / filename
                        download_file(url, out_path)
                        row.update(
                            {
                                "Latest 10Q Filing Date": filing["filingDate"],
                                "Report Date": report_date,
                                "Quarter": quarter,
                                "Accession Number": filing["accessionNumber"],
                                "Primary Document": filing["primaryDocument"],
                                "10Q URL": url,
                                "Saved File Path": str(out_path),
                                "Amended": filing["amended"],
                                "Status": "OK",
                                "Company Facts URL": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
                            }
                        )
        except Exception as exc:  # pylint: disable=broad-except
            row["Status"] = "ERROR"
            notes.append(str(exc))
        row["Notes"] = "; ".join(notes)
        print(f"Processed {ticker or name}: {row['Status']}")
        rows.append(row)
    try:
        write_excel(rows, Path("stock_screener.xlsx"))
    except Exception as exc:  # pylint: disable=broad-except
        print(f"Failed to write Excel: {exc}")


if __name__ == "__main__":
    main()
