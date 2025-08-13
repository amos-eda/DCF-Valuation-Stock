import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import sec_screener as ss


def test_detect_quarter():
    assert ss.detect_quarter("2024-01-15") == "Q1"
    assert ss.detect_quarter("2024-04-02") == "Q2"
    assert ss.detect_quarter("2024-07-19") == "Q3"


def test_build_10q_url():
    url = ss.build_10q_url("0000123456", "0001234567-24-000045", "doc.txt")
    assert url == "https://www.sec.gov/Archives/edgar/data/123456/000123456724000045/doc.txt"


def test_session_has_user_agent():
    assert ss.session.headers["User-Agent"] == "Jerry Mcguire"


import pytest
import requests
import pandas as pd


def test_download_file_error(monkeypatch, tmp_path):
    """download_file should propagate request errors."""

    def fake_make_request(url):  # noqa: ARG001
        raise requests.HTTPError("bad url")

    monkeypatch.setattr(ss, "make_request", fake_make_request)
    with pytest.raises(requests.HTTPError):
        ss.download_file("http://example.com/file.txt", tmp_path / "file.txt")


def test_main_handles_download_error(monkeypatch):
    """main() records ERROR status when download fails."""

    monkeypatch.setattr(
        ss,
        "WATCHLIST",
        [{"name": "Test", "ticker": "TEST"}],
    )

    def fake_load_ticker_map(cache_dir):  # noqa: ARG001
        return pd.DataFrame([
            {"ticker": "TEST", "cik_str": "0000000000"}
        ])

    def fake_get_latest_10q(cik):  # noqa: ARG001
        return {
            "filingDate": "2024-05-01",
            "reportDate": "2024-03-31",
            "accessionNumber": "0000000000-24-000001",
            "primaryDocument": "test.htm",
            "amended": False,
        }

    def fake_download_file(url, out_path):  # noqa: ARG001
        raise requests.HTTPError("download failed")

    captured = {}

    def fake_write_excel(rows, path):  # noqa: ARG001
        captured["rows"] = rows

    monkeypatch.setattr(ss, "load_ticker_map", fake_load_ticker_map)
    monkeypatch.setattr(ss, "get_latest_10q", fake_get_latest_10q)
    monkeypatch.setattr(ss, "download_file", fake_download_file)
    monkeypatch.setattr(ss, "write_excel", fake_write_excel)

    ss.main()

    rows = captured["rows"]
    assert rows[0]["Status"] == "ERROR"
    assert "download failed" in rows[0]["Notes"]
