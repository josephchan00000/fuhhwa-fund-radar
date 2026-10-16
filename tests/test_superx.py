"""飆股研究（arm/lab/superx.py；docs/lab_company_plan.md 第 4 節）：事前寫定的規格與核心計算。"""
from arm.lab import superx as SX


def test_spec_locked():
    """第 4 節的定義與門檻事前寫定；要改＝ VER＋1 並在文件寫日期與原因。"""
    assert SX.VER == 1
    assert SX.LABELS == {"A": (60, 0.5), "B": (250, 1.0)}
    assert (SX.LIQ_MIN, SX.AGE_MIN) == (1e7, 60)
    assert (SX.IS, SX.VAL, SX.HO) == (("2014-01-01", "2019-12-31"), ("2020-01-01", "2022-12-31"),
                                      ("2023-01-01", "9999-12-31"))
    assert SX.RULE == {"lift": 2.0, "n": 300, "pos": 50, "sub_lift": 1.5, "val_lift": 1.5, "max_k": 3,
                       "top_feats": 12}
    assert SX.QS == (0.1, 0.2, 0.3) and SX.KEEP_FINAL == 5
    assert len(SX.FK) == len(set(SX.FK)) == 22
    assert "mkt" not in " ".join(SX.FK)                 # 使用者：大盤、總經先不放


def test_week_ends():
    cal = ["2026-10-05", "2026-10-06", "2026-10-08", "2026-10-12", "2026-10-13"]
    assert SX.week_ends(cal) == [2, 4]


def test_qprev():
    assert SX.qprev("2026-03-31") == "2025-12-31"
    assert SX.qprev("2026-06-30", 4) == "2025-06-30"
    assert SX.qprev("2026-03-31", 2) == "2025-09-30"


def _fund():
    fq = {}
    eps = {"2024-03-31": 1.0, "2024-06-30": 1.0, "2024-09-30": 1.0, "2024-12-31": 1.0,
           "2025-03-31": 1.1, "2025-06-30": 1.3, "2025-09-30": 1.6, "2025-12-31": 2.0}
    rev = {"2024-03-31": 100, "2024-06-30": 100, "2024-09-30": 100, "2024-12-31": 100,
           "2025-03-31": 105, "2025-06-30": 115, "2025-09-30": 130, "2025-12-31": 150}
    gm = {"2024-03-31": .30, "2024-06-30": .30, "2024-09-30": .30, "2024-12-31": .30,
          "2025-03-31": .30, "2025-06-30": .31, "2025-09-30": .33, "2025-12-31": .36}
    for q in eps:
        fq[q] = {"eps": eps[q], "rev": rev[q], "gp": rev[q] * gm[q], "op": rev[q] * 0.1, "nip": eps[q] * 10,
                 "eqp": 400.0}
    rv = {}
    for k in range(36):
        y, m = 2023 + k // 12, k % 12 + 1
        rv[f"{y:04d}-{m:02d}"] = 100.0 + k * 3
    return SX.Fund(fq, rv)


def test_fund_quarter_features_code33():
    f = _fund().q_feats("2025-12-31")
    assert round(f["ey"], 4) == 1.0                     # 2.0 對 1.0
    assert round(f["eacc"], 4) == round(1.0 - 0.6, 4)
    assert round(f["gm"], 4) == 0.36 and round(f["gmd"], 4) == 0.06
    assert f["c33"] is True                             # EPS、營收、毛利率連三季加速
    assert round(f["roe"], 4) == round((1.1 + 1.3 + 1.6 + 2.0) * 10 / 400, 4)


def test_fund_eps_turnaround_and_loss():
    fd = SX.Fund({"2025-03-31": {"eps": 0.5}, "2024-03-31": {"eps": -0.2}}, {})
    assert fd.ey("2025-03-31") == 3.0                   # 轉盈記 300%
    fd2 = SX.Fund({"2025-03-31": {"eps": -0.1}, "2024-03-31": {"eps": -0.2}}, {})
    assert fd2.ey("2025-03-31") is None                 # 續虧不算


def test_fund_month_features():
    fd = _fund()
    f = fd.m_feats("2025-12")
    assert f["rnh12"] is True and f["rnha"] is True     # 一路成長
    assert f["ry"] is not None and f["ry"] > 0
    assert SX.Fund({}, {}).m_feats(None) == {}


def test_px_raw_and_label():
    cal = [f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(330)]
    c = [10 + 0.02 * i for i in range(330)]
    s = {"c": c, "h": [x * 1.01 for x in c], "l": [x * 0.99 for x in c], "v": [1000.0] * 330}
    px = SX.Px(s, cal)
    assert px.raw(200) is None                          # 不到 252 天
    r = px.raw(300)
    assert r and all(r["tt7"][:5]) and r["d52h"] <= 0
    lab = px.label(250, 60, 0.5)
    assert lab["y"] is False and lab["mx"] > 0
    assert px.label(300, 60, 0.5) is None               # 尾端未來還沒發生


def test_rs_pct_and_rules():
    rs = SX.rs_pct({"a": 0.1, "b": 0.5, "c": -0.2})
    assert rs["b"] > rs["a"] > rs["c"]
    rows = []
    for k in range(400):
        f = {"rs": k % 100, "ry": (k % 10) / 10, "tt_all": k % 2 == 0}
        y = f["rs"] >= 80 and f["ry"] >= 0.5
        rows.append({"c": str(k), "d": "2015-01-0%d" % (1 + k % 9), "f": f,
                     "y": {"A": {"y": y, "mx": 0.6 if y else 0.1, "dd": -0.1, "fr": 0.2}}})
    ev = SX.eval_rule(rows, "A", [("rs", ">=", 80), ("ry", ">=", 0.5)])
    assert ev["p"] == 1.0 and ev["lift"] > 2
    assert SX.cond_text(("ry", ">=", 0.25)) == "最新月營收年增 ≥ +25.0%"
    assert SX.cond_text(("tt_all", "=", True)) == "趨勢樣板 8 項全過"
