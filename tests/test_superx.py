"""飆股研究（arm/lab/superx.py；docs/lab_company_plan.md 第 4 節）：事前寫定的規格與核心計算。"""
from arm.lab import superx as SX


def test_spec_locked():
    """第 4 節的定義與門檻事前寫定；要改＝ VER＋1 並在文件寫日期與原因。"""
    assert SX.VER == 2                                  # v2：加市值下限與體質檢查（文件第 4.2、4.6 節）
    assert SX.LABELS == {"A": (60, 0.5), "B": (250, 1.0)}
    assert (SX.LIQ_MIN, SX.AGE_MIN, SX.CAP_MIN) == (1e7, 60, 40e8)
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


def _rows(n=2000):
    """合成樣本：rs ≥ 80 且 ry ≥ 0.5 的有八成是飆股，其餘一成。"""
    import random
    rnd = random.Random(7)
    rows = []
    for k in range(n):
        f = {"rs": rnd.randint(1, 99), "ry": rnd.random(), "tt_all": rnd.random() < 0.5, "ey": rnd.random() - 0.2}
        hot = f["rs"] >= 80 and f["ry"] >= 0.5
        y = rnd.random() < (0.8 if hot else 0.1)
        d = f"{2014 + k % 6}-0{1 + k % 9}-1{k % 10}"
        rows.append({"c": str(k % 300), "d": d, "f": f,
                     "y": {"A": {"y": y, "mx": 0.6 if y else 0.1, "dd": -0.1, "fr": 0.2}, "B": None if k % 50 == 0 else
                           {"y": y, "mx": 1.1 if y else 0.2, "dd": -0.2, "fr": 0.3}}})
    return rows


def test_bitsets_match_row_by_row():
    """位元集合版本和逐列計算結果一樣。"""
    rows = _rows()
    conds = [("rs", ">=", 80), ("ry", ">=", 0.5)]
    pr = SX.rule_pred(conds)
    sel = [r for r in rows if r["y"]["B"] is not None and pr(r["f"])]
    ev = SX.eval_rule(rows, "B", conds)
    assert ev["n"] == len(sel) and ev["pos"] == sum(1 for r in sel if r["y"]["B"]["y"])
    valid = [r for r in rows if r["y"]["B"] is not None]
    assert abs(SX.base_rate(rows, "B") - sum(1 for r in valid if r["y"]["B"]["y"]) / len(valid)) < 1e-12
    assert list(SX.ones(SX.pack([True, False, True, True]))) == [0, 2, 3]


def test_mine_rules_finds_planted_rule_and_select_dedups():
    rows = _rows(6000)
    ft = SX.feature_table(rows, "A")
    assert ft["feats"]["rs"]["groups"][-1]["lift"] > 1.5
    conds = SX.candidate_conds(ft)
    rules, tried = SX.mine_rules(rows, "A", conds)
    assert tried > 0 and rules
    best = max(rules, key=lambda r: r["is"]["lift"])
    assert {c[0] for c in best["conds"]} >= {"rs", "ry"}
    fin = SX.select_final(rules, rows, "A")
    assert 1 <= len(fin) <= SX.KEEP_FINAL
    assert "mx_med" in fin[0]["val"]


def test_checks_match_page_and_stats():
    """體質檢查 11 項：研究（CHECKS）與頁面（copage.SXCK）同一份；統計含每項與「符合幾項」。"""
    import re
    from arm.lab import copage
    page = re.findall(r"\['(\w+)','([^']+)',r=>", copage.JS)
    assert page == [(k, t) for k, t, *_ in SX.CHECKS]
    rows = _rows(600)
    for r in rows:
        r["f"].update({"tt_all": True, "d52h": -0.1})
    st = SX.check_stats(rows)
    assert st["items"]["h25"]["A"]["n"] == len(rows) and st["items"]["tt8"]["B"]["n"] == len(rows) - 12
    assert sum(x["n"] for x in st["count"]["A"]["rows"]) == len(rows)
