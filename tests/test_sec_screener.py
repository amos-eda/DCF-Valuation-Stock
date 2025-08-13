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
