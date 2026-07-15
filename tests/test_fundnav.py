"""arm/fundnav —— 基金 NAV 歷史與 1週/1月報酬計算。"""
import json

from arm import fundnav


# ── ret_pct ──────────────────────────────────────────────────

def test_ret_pct_exact_7d():
    ser = {"2026/07/07": 100.0, "2026/07/14": 103.0}
    assert fundnav.ret_pct(ser, "2026/07/14", 103.0, 7, tol=5) == 3.0


def test_ret_pct_weekend_fallback_within_tol():
    # 目標日 07/07 無值 → 退到 07/04（差 3 天，tol=5 內）
    ser = {"2026/07/04": 100.0, "2026/07/14": 102.0}
    assert fundnav.ret_pct(ser, "2026/07/14", 102.0, 7, tol=5) == 2.0


def test_ret_pct_sparse_series_returns_none():
    # 基準日早於目標日超過 tol → 不硬算
    ser = {"2026/06/20": 100.0, "2026/07/14": 110.0}
    assert fundnav.ret_pct(ser, "2026/07/14", 110.0, 7, tol=5) is None


def test_ret_pct_insufficient_history_returns_none():
    ser = {"2026/07/10": 100.0, "2026/07/14": 101.0}   # 30 日前無史料
    assert fundnav.ret_pct(ser, "2026/07/14", 101.0, 30, tol=10) is None


def test_ret_pct_none_safety():
    assert fundnav.ret_pct(None, "2026/07/14", 100.0, 7, tol=5) is None
    assert fundnav.ret_pct({}, "2026/07/14", 100.0, 7, tol=5) is None
    assert fundnav.ret_pct({"2026/07/07": 100.0}, None, 100.0, 7, tol=5) is None
    assert fundnav.ret_pct({"2026/07/07": 100.0}, "2026/07/14", None, 7, tol=5) is None
    assert fundnav.ret_pct({"2026/07/07": 100.0}, "bad-date", 100.0, 7, tol=5) is None


def test_ret_pct_negative_return():
    ser = {"2026/06/14": 100.0, "2026/07/14": 97.5}
    assert fundnav.ret_pct(ser, "2026/07/14", 97.5, 30, tol=10) == -2.5


# ── record（落檔累積＋防清史） ────────────────────────────────

def test_record_merges_and_preserves(tmp_path, monkeypatch):
    monkeypatch.setattr(fundnav, "PATH", tmp_path / "hist.json")
    n = fundnav.record([{"fund_id": "01", "nav": 100.0, "nav_date": "2026/07/13"},
                        {"fund_id": "01", "nav": 101.0, "nav_date": "2026/07/14"},
                        {"fund_id": "02", "nav": 50.0, "nav_date": "2026-07-14"}])
    assert n == 3
    hist = fundnav.load()
    assert hist["01"]["2026/07/14"] == 101.0
    assert hist["02"]["2026/07/14"] == 50.0            # 連字號日期也可解析
    # 全空輸入不動既有落檔（抓取全失敗防呆）
    assert fundnav.record([]) == 0
    assert fundnav.record([{"fund_id": "03", "nav": None, "nav_date": "2026/07/14"}]) == 0
    assert fundnav.load() == hist
    # 同日同值冪等、同日新值覆蓋
    assert fundnav.record([{"fund_id": "01", "nav": 101.0, "nav_date": "2026/07/14"}]) == 0
    assert fundnav.record([{"fund_id": "01", "nav": 101.5, "nav_date": "2026/07/14"}]) == 1
    assert fundnav.load()["01"]["2026/07/14"] == 101.5


def test_saved_file_sorted_and_valid_json(tmp_path, monkeypatch):
    monkeypatch.setattr(fundnav, "PATH", tmp_path / "hist.json")
    fundnav.record([{"fund_id": "02", "nav": 2.0, "nav_date": "2026/07/14"},
                    {"fund_id": "01", "nav": 1.0, "nav_date": "2026/07/14"},
                    {"fund_id": "01", "nav": 0.9, "nav_date": "2026/07/13"}])
    d = json.loads((tmp_path / "hist.json").read_text(encoding="utf-8"))
    assert list(d) == ["01", "02"]
    assert list(d["01"]) == ["2026/07/13", "2026/07/14"]
