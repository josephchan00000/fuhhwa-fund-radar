"""前十大持股簡介覆蓋率防呆（2026-07-23 使用者：前十大簡介一再漏掉）。

守住兩件事：
  1. uncovered_top_holdings() 能正確抓出缺 intro 的持股（單元）。
  2. 已入庫的基金快照，前十大 100% 有簡介（覆蓋率斷言）——容器端一旦看到含新標的的
     CI 快照就會紅，逼在發佈前補齊。
"""
import json

from arm import fund_intro


def test_uncovered_detects_missing(tmp_path, monkeypatch):
    # 造兩檔基金、共用一個缺 intro 的持股「新標的X」
    funds_dir = tmp_path / "funds"
    funds_dir.mkdir()
    (funds_dir / "01.json").write_text(json.dumps({
        "fund_id": "01", "short_name": "甲基金",
        "top_holdings": [{"name": "台積電", "weight": 10.0, "sector": "半導體"},
                         {"name": "新標的X", "weight": 5.0, "sector": "測試"}]}), encoding="utf-8")
    (funds_dir / "02.json").write_text(json.dumps({
        "fund_id": "02", "short_name": "乙基金",
        "top_holdings": [{"name": "新標的X", "weight": 4.0, "sector": "測試"}]}), encoding="utf-8")
    monkeypatch.setattr(fund_intro, "FUNDS_DIR", funds_dir)
    monkeypatch.setattr(fund_intro, "config",
                        type("C", (), {"funds": staticmethod(lambda: [{"id": "01"}, {"id": "02"}])}))
    monkeypatch.setattr(fund_intro, "_profiles",
                        lambda: {"台積電": {"intro": "台灣台積電…"}})   # 新標的X 無 intro

    gaps = fund_intro.uncovered_top_holdings(10)
    names = [g["name"] for g in gaps]
    assert names == ["新標的X"]           # 台積電有 intro、不列
    assert gaps[0]["count"] == 2          # 出現於兩檔
    assert {f["short_name"] for f in gaps[0]["funds"]} == {"甲基金", "乙基金"}


def test_all_committed_funds_top10_have_intro():
    """已入庫的所有基金快照，前十大持股簡介覆蓋率須 100%。

    這是使用者一再反映的「前十大簡介漏掉」的最後防線：CI 抓到新持股後，容器端下一輪
    看到該快照時，此測試會紅，逼在發佈前把缺的標的補進 config/holding_profiles.json。
    """
    gaps = fund_intro.uncovered_top_holdings(10)
    detail = "、".join(f'{g["name"]}（{g["count"]}檔）' for g in gaps)
    assert not gaps, (f"{len(gaps)} 檔前十大持股缺簡介，請補進 config/holding_profiles.json："
                      f"{detail}（跑 scripts/check_holdings_intro.py 看細節）")
