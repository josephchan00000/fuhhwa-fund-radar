"""個股策略防守研究的程式（arm/lab/defres.py；docs/lab_stock_page_plan.md 第 10 節）：只用假資料測規則照規格做。"""
import json

from arm.lab import defres as D


def test_ma_gate():
    px = [10, 10, 10, 9, 12, None, 8]
    g = D.ma_gate(px, 3)
    assert g == [True, True, True, False, True, True, False]          # 9 < 平均 9.67；12 ≥ 10.33；None 不擋；8 < 9.67


class _Ind:
    def __init__(self, m):
        self.m = m

    def at(self, c, d):
        return self.m.get(c)


def test_cap_pick_skips_third_of_same_industry():
    sc = {f"S{i}": 100 - i for i in range(25)}
    ind = _Ind({"S0": "半導體", "S1": "半導體", "S2": "半導體", "S3": "航運", "S4": "半導體", "S5": "金融"})
    rows = [(10, 70, sc), (80, 140, {"A": 1})]                        # 第二期有分數的不到 20 檔 → 不選
    out = D.cap_pick(rows, 2, ind, ["d"] * 200)
    assert out == [(10, 70, ["S0", "S1", "S3", "S5", "S6"])]           # S2、S4 第三、第四檔半導體跳過；S6 查不到類別＝不限


def test_tw_ind_snapshot_then_current(tmp_path, monkeypatch):
    p = tmp_path / "indsnap.json"
    p.write_text(json.dumps({"twse": {"2020-01-02": {"24": ["2330"]}, "2025-01-02": {"24": ["2330"], "25": ["2454"]}},
                             "tpex": {"2020-01-02": {"26": ["3105"]}}}), encoding="utf-8")
    t = D.TwInd(p)
    assert t.at("2330", "2021-06-01") == "半導體業" and t.at("3105", "2021-06-01") == "光電業"
    assert t.at("2454", "2021-06-01") == t.cur.get("2454")              # 那一年的快照沒有 → 現在的分類
    assert t.at("2454", "2025-03-01") == "電腦及週邊設備業"


def test_ks_overlay_pause_and_resume():
    # 大盤不動；策略 100 天緩漲、然後跌 30%、再漲回去
    nav = [1 + 0.001 * i for i in range(100)] + [1.099 * (1 - 0.01 * k) for k in range(1, 31)] + \
          [1.099 * 0.7 * (1 + 0.02 * k) for k in range(1, 40)]
    bench = [1.0] * len(nav)
    flat, ev = D.ks_overlay(nav, bench, fixed=0.10, warm=0)
    ks = [e["k"] for e in ev]
    assert ks[0] == "pause" and "resume" in ks
    p = ev[0]["i"]
    assert abs(1 - nav[p] / max(nav[:p + 1]) - 0.10) < 0.02                 # 落後剛超過 10% 那天觸發
    assert flat[p + 2] == flat[p + 1] and flat[p + 1] != flat[p]             # 下一天收盤換現金、之後不動
    same, ev2 = D.ks_overlay(nav, bench, mult=1.0, warm=len(nav))           # 全部在熱身期 → 不熔斷、淨值一樣
    assert ev2 == [] and same == [float(nav[0])] + [x for x in [same[i] for i in range(1, len(nav))]]
    assert abs(same[-1] - nav[-1]) < 1e-9


def test_ks_overlay_walk_forward_bound_uses_only_past():
    nav = [1.0, 0.9, 1.0, 0.85, 0.86]
    bench = [1.0] * 5
    _, ev = D.ks_overlay(nav, bench, mult=1.0, warm=0)
    assert ev and ev[0]["i"] == 1                                        # 第 1 天以前最大落後 0 → 門檻 0，落後 10% 就觸發
    _, ev = D.ks_overlay(nav, bench, mult=1.0, warm=2)
    assert ev and ev[0]["i"] == 3                                        # 熱身期後：以前最大落後 10%，第 3 天落後 15% 超過
