"""基金持股快照：持股頁抓不到時不得把前十大與配置寫成空的（docs/code_ponytail_audit.md 第 1 條）。"""
import copy
import importlib.util
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _mod():
    spec = importlib.util.spec_from_file_location("fetch_holdings_t", ROOT / "scripts" / "fetch_holdings.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


OLD = {"fund_id": "47", "name": "復華甲基金", "nav": 10.0, "nav_date": "2026/10/29", "as_of": "2026/09/30",
       "top_holdings": [{"sector": "半導體", "name": "台積電", "weight": 9.1}],
       "asset_alloc": [], "country_alloc": [{"name": "台灣", "weight": 90.0}],
       "sector_alloc": [{"name": "半導體", "weight": 40.0}], "fetched_at": "2026-10-30 07:16"}


def _empty(**kw):
    d = {"fund_id": "47", "name": "復華甲基金", "nav": 10.5, "nav_date": "2026/10/30", "as_of": None,
         "top_holdings": [], "asset_alloc": [], "country_alloc": [], "sector_alloc": []}
    d.update(kw)
    return d


def test_page_error_keeps_previous_holdings(tmp_path):
    m = _mod()
    fp = tmp_path / "47.json"
    fp.write_text(json.dumps(OLD, ensure_ascii=False), encoding="utf-8")
    doc = _empty(holdings_error="HTTPError: 502")
    assert m._keep_holdings(doc, fp) is True
    for k in ("as_of", "top_holdings", "asset_alloc", "country_alloc", "sector_alloc"):
        assert doc[k] == OLD[k]
    assert doc["nav"] == 10.5 and doc["nav_date"] == "2026/10/30"        # 其他欄位照新的
    assert doc["holdings_error"] == "HTTPError: 502"


def test_zero_rows_without_error_also_kept(tmp_path):
    m = _mod()
    fp = tmp_path / "47.json"
    fp.write_text(json.dumps(OLD, ensure_ascii=False), encoding="utf-8")
    doc = _empty()
    assert m._keep_holdings(doc, fp) is True
    assert doc["top_holdings"] == OLD["top_holdings"] and doc["holdings_error"]


def test_normal_fetch_is_untouched(tmp_path):
    m = _mod()
    fp = tmp_path / "47.json"
    fp.write_text(json.dumps(OLD, ensure_ascii=False), encoding="utf-8")
    doc = _empty(as_of="2026/10/31", top_holdings=[{"sector": "半導體", "name": "聯發科", "weight": 8.0}])
    before = copy.deepcopy(doc)
    assert m._keep_holdings(doc, fp) is False
    assert doc == before


def test_no_previous_file_stays_empty(tmp_path):
    m = _mod()
    doc = _empty()
    assert m._keep_holdings(doc, tmp_path / "none.json") is False
    assert doc["top_holdings"] == [] and "holdings_error" not in doc


def test_run_writes_previous_holdings_when_page_fails(tmp_path, monkeypatch):
    m = _mod()
    monkeypatch.setattr(m, "OUT", tmp_path)
    (tmp_path / "47.json").write_text(json.dumps(OLD, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(m.config, "funds", lambda: [{"id": "47", "name": "復華甲基金", "group": "股票"}])
    monkeypatch.setattr(m.fhfund, "fetch_fund", lambda fid: _empty(holdings_error="HTTPError: 502"))
    monkeypatch.setattr(m.fundnav, "record", lambda docs: 0)
    monkeypatch.setattr(m.fundnav, "backfill_official", lambda *a, **k: None)
    stub = types.SimpleNamespace(apply_overlay=lambda docs, out: None)
    import arm.connectors as C
    monkeypatch.setitem(sys.modules, "arm.connectors.cnyesfund", stub)
    monkeypatch.setattr(C, "cnyesfund", stub, raising=False)
    index = m.run(["47"])
    got = json.loads((tmp_path / "47.json").read_text(encoding="utf-8"))
    assert got["top_holdings"] == OLD["top_holdings"] and got["as_of"] == "2026/09/30"
    assert got["nav"] == 10.5
    assert index[0]["n_top"] == 1
