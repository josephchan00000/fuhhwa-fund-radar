"""美股個股卡的季報摘要（arm/lab/usfin.py；docs/lab_review_plan.md 第 4 節 (b)(c)）：單季（第四季＝全年 − 前三季）、
營收取最早公布的項目、毛利沒有就用營收減成本、時點項目（股東權益）和季底差幾天也對得上、流通股數、這一批的代號、沒變不寫。"""
import json

from arm.lab import usfin as UF


def _doc():
    rev = [["2024-01-01", "2024-03-31", 100e6, "2024-05-01", "10-Q"], ["2024-01-01", "2024-06-30", 210e6, "2024-08-01", "10-Q"],
           ["2024-04-01", "2024-06-30", 110e6, "2024-08-01", "10-Q"], ["2024-01-01", "2024-09-30", 330e6, "2024-11-01", "10-Q"],
           ["2024-07-01", "2024-09-30", 120e6, "2024-11-01", "10-Q"], ["2024-01-01", "2024-12-31", 460e6, "2025-02-20", "10-K"],
           ["2025-01-01", "2025-03-31", 140e6, "2025-05-01", "10-Q"]]
    cost = [[s, e, v * 0.6, fd, fm] for s, e, v, fd, fm in rev]
    eps = [[s, e, v / 100e6, fd, fm] for s, e, v, fd, fm in rev]
    ni = [[s, e, v * 0.1, fd, fm] for s, e, v, fd, fm in rev]
    oi = [[s, e, v * 0.2, fd, fm] for s, e, v, fd, fm in rev]
    eq = [["", "2024-03-30", 500e6, "2024-05-01", "10-Q"], ["", "2024-06-29", 510e6, "2024-08-01", "10-Q"],
          ["", "2024-09-28", 520e6, "2024-11-01", "10-Q"], ["", "2024-12-31", 530e6, "2025-02-20", "10-K"],
          ["", "2025-03-29", 540e6, "2025-05-01", "10-Q"]]
    sh = [["", "2024-04-25", 50e6, "2024-05-01", "10-Q"], ["", "2025-04-25", 49e6, "2025-05-01", "10-Q"]]
    return {"cik": 1, "f": {"Revenues": rev, "CostOfRevenue": cost, "EarningsPerShareDiluted": eps, "NetIncomeLoss": ni,
                            "OperatingIncomeLoss": oi, "StockholdersEquity": eq, "EntityCommonStockSharesOutstanding": sh}}


def test_summary_quarters_q4_gross_profit_and_equity():
    x = UF.summary(_doc())
    q = {r[0]: r for r in x["q"]}
    assert [r[0] for r in x["q"]] == ["2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31", "2025-03-31"]
    assert q["2024-12-31"][2] == 130.0 and q["2024-12-31"][1] == "2025-02-20"          # 第四季＝全年 460 − 前三季 330
    assert q["2024-12-31"][3] == 52.0                                                   # 毛利＝營收 − 成本（130 × 0.4）
    assert q["2024-12-31"][6] == 1.3 and q["2024-12-31"][4] == 26.0 and q["2024-12-31"][5] == 13.0
    assert q["2024-03-31"][7] == 500.0 and q["2025-03-31"][7] == 540.0                 # 股東權益：季底差幾天也對得上
    assert x["sh"] == [["2024-04-25", "2024-05-01", 50.0], ["2025-04-25", "2025-05-01", 49.0]]
    assert UF.summary({"f": {}}) is None and UF.summary(None) is None


def test_codes_for_and_save_only_when_changed(tmp_path):
    L = {"now": {"hold": [{"c": "VLO"}], "buy": ["FTNT"], "list": [{"c": c} for c in ("VLO", "FTNT", "A", "B", "C", "D", "E", "F")]}}
    cs = UF.codes_for(L)
    assert cs[:2] == ["VLO", "FTNT"] and len(cs) == 8 and len(set(cs)) == 8
    p = tmp_path / "fin.json"
    doc = {"ver": UF.VER, "made": "2026-10-24", "sec": "2026-10-24", "codes": cs, "s": {"VLO": UF.summary(_doc())}}
    assert UF.save(doc, p) and UF.load(p)["s"]["VLO"]["q"][0][0] == "2024-03-31"
    assert not UF.save({**doc, "made": "2026-10-31"}, p)                                # 只有日期變＝不寫
    assert UF.save({**doc, "sec": "2026-10-31"}, p)
    p.write_text(json.dumps({"ver": 0}), encoding="utf-8")
    assert UF.load(p) == {}


def test_committed_file_matches_live_record():
    """入庫的季報涵蓋配置頁美股會出現的每一檔（每週六跟著每週紀錄更新）。"""
    from arm import fund_intro as FI
    from arm.lab import ussxqm as QM
    doc = UF.load()
    L = QM.load_live()
    if not doc or not L.get("now"):
        return
    want, _ = FI.qm_codes(L)
    assert set(want) <= set(doc["codes"])
