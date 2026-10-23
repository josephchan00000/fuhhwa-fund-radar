"""美股財報（arm/lab/secfin.py）：同一期間只留第一次公布的數字；email 只從環境變數讀、不出現在輸出與存檔。不連網。"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from arm.lab import secfin as SF
from arm.lab import ussxdata as UD

ROOT = Path(__file__).resolve().parents[1]
EMAIL = "tester@example.com"


def _f(start, end, val, filed, form):
    r = {"end": end, "val": val, "filed": filed, "form": form, "fy": 2019, "fp": "Q1"}
    if start:
        r["start"] = start
    return r


DOC = {"cik": 1, "facts": {
    "us-gaap": {
        "Revenues": {"units": {"USD": [
            _f("2019-01-01", "2019-03-31", 100, "2019-05-01", "10-Q"),
            _f("2019-01-01", "2019-03-31", 105, "2020-04-30", "10-Q"),      # 隔年 10-Q 的去年同期（修正過）→ 不收
            _f("2019-01-01", "2019-12-31", 450, "2020-02-15", "10-K"),
            _f("2019-01-01", "2019-12-31", 460, "2020-02-15", "10-K/A"),    # 同一天的修正申報 → 原始優先
            _f("2019-04-01", "2019-06-30", 110, "2019-08-01", "8-K"),       # 8-K 不收
            _f("2005-01-01", "2005-03-31", 50, "2005-05-01", "10-Q"),       # 太早
        ], "EUR": [_f("2019-04-01", "2019-06-30", 1, "2019-08-01", "10-Q")]}},
        "StockholdersEquity": {"units": {"USD": [_f(None, "2019-03-31", 900, "2019-05-01", "10-Q")]}},
        "EarningsPerShareDiluted": {"units": {"USD/shares": [_f("2019-01-01", "2019-03-31", 0.5, "2019-05-01", "10-Q")]}},
        "SomethingElse": {"units": {"USD": [_f("2019-01-01", "2019-03-31", 1, "2019-05-01", "10-Q")]}},
    },
    "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
        _f(None, "2019-04-20", 1000, "2019-05-01", "10-Q")]}}},
}}


def test_extract_keeps_first_filed_per_period():
    f = SF.extract(DOC)
    assert f["Revenues"] == [["2019-01-01", "2019-03-31", 100, "2019-05-01", "10-Q"],
                             ["2019-01-01", "2019-12-31", 450, "2020-02-15", "10-K"]]
    assert f["StockholdersEquity"] == [["", "2019-03-31", 900, "2019-05-01", "10-Q"]]
    assert f["EarningsPerShareDiluted"][0][2] == 0.5
    assert f["EntityCommonStockSharesOutstanding"] == [["", "2019-04-20", 1000, "2019-05-01", "10-Q"]]
    assert "SomethingElse" not in f
    assert SF.extract({}) == {}


def test_ticker_map_normalizes_symbols():
    m = SF.ticker_map({"0": {"cik_str": 320193, "ticker": "AAPL"}, "1": {"cik_str": 1067983, "ticker": "BRK.B"},
                       "2": {"ticker": "BAD"}})
    assert m == {"AAPL": 320193, "BRK-B": 1067983}


def test_contact_reads_env_only(monkeypatch):
    monkeypatch.delenv(SF.ENV, raising=False)
    assert SF.contact() is None
    monkeypatch.setenv(SF.ENV, "not-an-email")
    assert SF.contact() is None
    monkeypatch.setenv(SF.ENV, f"  {EMAIL} ")
    assert SF.contact() == EMAIL


def test_run_skips_without_secret(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("USSX_DIR", str(tmp_path))
    monkeypatch.delenv(SF.ENV, raising=False)
    assert SF.run(["AAPL"]) == {"skip": "no-secret"}
    assert "SEC_CONTACT_EMAIL" in capsys.readouterr().out
    assert not (tmp_path / "sec").exists()


def test_run_writes_files_and_never_leaks_email(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("USSX_DIR", str(tmp_path))
    monkeypatch.setenv(SF.ENV, EMAIL)
    seen_ua = []
    monkeypatch.setattr(SF, "fetch_tickers", lambda e: (seen_ua.append(SF._ua(e)), {"AAA": 1, "BBB": 1, "CCC": 2})[1])

    def fake_bulk(e, path):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("CIK0000000001.json", json.dumps(DOC))
            z.writestr("CIK0000000002.json", json.dumps({"facts": {}}))
            z.writestr("CIK0000000003.json", json.dumps(DOC))     # 不是我們要的
        Path(path).write_bytes(buf.getvalue())
        return len(buf.getvalue())

    monkeypatch.setattr(SF, "download_bulk", fake_bulk)
    st = SF.run(["AAA", "BBB", "CCC", "DDD"])
    assert st["n"] == 1 and st["empty"] == 1 and st["miss"] == 1
    assert SF.load("AAA")["cik"] == 1 and SF.load("BBB")["f"] == SF.load("AAA")["f"]
    assert SF.load("CCC") == {}
    assert SF.run(["AAA"]) == {"skip": "today"}
    assert EMAIL in seen_ua[0]                                    # 只放在 User-Agent
    out = capsys.readouterr().out
    assert EMAIL not in out
    for p in tmp_path.rglob("*"):
        if p.is_file():
            assert EMAIL.encode() not in p.read_bytes()
            assert EMAIL.encode() not in (UD._read(p) and json.dumps(UD._read(p)).encode() or b"")
    assert EMAIL not in SF.status()


def test_no_email_literal_in_source():
    src = (ROOT / "arm" / "lab" / "secfin.py").read_text(encoding="utf-8")
    import re
    assert not re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", src)
