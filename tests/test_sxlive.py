"""飆股前瞻記錄（arm/lab/sxlive.py；規格 sxlivespec VER 1）。"""
import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import sxlive as L  # noqa: E402
from arm.lab import sxlivespec as S  # noqa: E402


def _synthetic(seed: int, n: int = 160, m: int = 30):
    """合成的價格：有停牌、下市、一價到底漲跌停、除權息（f 變動）、高價股（買不到一張）、成交量很小（受 5% 限制）。"""
    np = pytest.importorskip("numpy")
    pd = pytest.importorskip("pandas")
    rng = np.random.default_rng(seed)
    c = 30 * np.exp(np.cumsum(rng.normal(0, 0.03, (n, m)), axis=0)) * rng.choice([1, 1, 1, 8, 60], m)
    o = c * np.exp(rng.normal(0, 0.01, (n, m)))
    o[0] = c[0]
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.01, (n, m))))
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.01, (n, m))))
    for _ in range(25):                                # 一價到底漲停／跌停
        i, j = int(rng.integers(1, n)), int(rng.integers(m))
        x = c[i - 1, j] * (1.095 if rng.random() < 0.5 else 0.905)
        o[i, j] = h[i, j] = l[i, j] = c[i, j] = x
    gone = rng.random((n, m)) < 0.03                   # 停牌
    for a in (o, h, l, c):
        a[gone] = np.nan
    for a in (o, h, l, c):                             # 第 0 檔在第 100 天後下市
        a[100:, 0] = np.nan
    f = np.ones((n, m))
    for j in range(m):                                 # 除權息：f＝含息價 ÷ 成交價，除權息日之前比較小
        for d in rng.choice(np.arange(5, n), 2, replace=False):
            f[:d, j] *= 0.96
    val = np.exp(rng.normal(np.log(1e8), 1.6, (n, m)))
    vol = val / np.nan_to_num(c / f, nan=50.0) * rng.choice([1, 1, 0.01], m)
    val[np.isnan(c)] = np.nan
    vol[np.isnan(c)] = np.nan
    dates = pd.bdate_range("2024-01-01", periods=n)
    codes = [f"{1101 + j}" for j in range(m)]
    sig = {}
    for i in range(3, n - 1, 5):                       # 每 5 天一批訊號，分數有同分
        js = rng.choice(m, int(rng.integers(3, 14)), replace=False)
        sig[i] = [(codes[j], int(rng.integers(60, 99))) for j in sorted(js)]
    return np, pd, dates, codes, o, h, l, c, f, val, vol, sig


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_book_matches_the_w7_engine(seed):
    """同一份價格、同一批訊號：sxlive.Book 和 tw-superstock-lab 的引擎每天的資產、每一筆交易都相同。"""
    np, pd, dates, codes, o, h, l, c, f, val, vol, sig = _synthetic(seed)
    sys.path.insert(0, str(ROOT / "tw-superstock-lab" / "src"))
    from dataclasses import replace
    from superstock import engine as EN
    n, hold = len(dates), 12
    av = pd.DataFrame(val).rolling(20, min_periods=1).mean().to_numpy()
    avv = pd.DataFrame(vol).rolling(20, min_periods=1).mean().to_numpy()
    lst = lambda a, j: [None if x != x else float(x) for x in a[:, j]]  # noqa: E731
    px = {code: L.series(lst(o, j), lst(h, j), lst(l, j), lst(c, j), lst(f, j), lst(av, j), lst(avv, j))
          for j, code in enumerate(codes)}
    lu = np.array([px[k]["lu"] for k in codes]).T
    ld = np.array([px[k]["ld"] for k in codes]).T
    assert lu.any() and ld.any()
    mk = EN.Market(dates, codes, o, h, l, c, factor=f, value=val, volume=vol, locked_up=lu, locked_down=ld)
    cfg = replace(EN.EngineConfig(costs=EN.Costs()), breakeven_r=None, market_filter=False, block_disposition=False,
                  max_hold_days=hold, liquidate_at_end=False)
    col = {k: j for j, k in enumerate(codes)}
    by = {i: [EN.Order(col[k], "open", weight=S.TRADE["weight"], score=float(s)) for k, s in xs] for i, xs in sig.items()}
    sim = EN.Simulator(mk, cfg, mf=np.ones(n, dtype=bool))
    res = sim.run(lambda i, _s: [EN.Order(x.s, x.kind, weight=x.weight, score=x.score) for x in by.get(i, [])])
    bk = L.Book(px, n, None, {**S.TRADE, "hold": hold})
    eq = [bk.step(i, sig.get(i)) for i in range(n)]
    assert np.allclose(eq, res.equity.to_numpy(), rtol=1e-12, atol=1e-6)
    t = res.trades
    ref = sorted((str(r.stock_id), dates.get_loc(r.entry_date), dates.get_loc(r.exit_date), r.reason, float(r.shares))
                 for r in t.itertuples())
    got = sorted((k, ei, xi, why, sh) for k, si, ei, xi, r, why, sh, pnl in bk.trades)
    assert got == ref and len(got) > 20
    assert "time" in {x[3] for x in got}
    assert sorted(bk.pos) == sorted(codes[s] for s in sim.pos)


def test_book_matches_the_engine_when_a_held_stock_stops_trading():
    """持有中的股票沒有資料了：下市（不在上市名單）→ 用最後收盤賣，和引擎相同；還在上市（停牌）→ 繼續抱著。"""
    np = pytest.importorskip("numpy")
    pd = pytest.importorskip("pandas")
    sys.path.insert(0, str(ROOT / "tw-superstock-lab" / "src"))
    from dataclasses import replace
    from superstock import engine as EN
    n, codes = 40, ["2330", "2454"]
    c = np.array([[100 + i, 50 + 0.5 * i] for i in range(n)], dtype=float)
    o, h, l = c * 0.99, c * 1.01, c * 0.98
    for a in (o, h, l, c):
        a[25:, 0] = np.nan                              # 2330 第 25 天起沒有資料
    f = np.ones((n, 2))
    val = np.where(np.isnan(c), np.nan, 5e8)
    vol = val / np.nan_to_num(c, nan=1.0)
    dates = pd.bdate_range("2025-01-01", periods=n)
    sig = {5: [("2330", 90), ("2454", 80)]}
    lst = lambda a, j: [None if x != x else float(x) for x in a[:, j]]  # noqa: E731
    av = pd.DataFrame(val).rolling(20, min_periods=1).mean().to_numpy()
    avv = pd.DataFrame(vol).rolling(20, min_periods=1).mean().to_numpy()
    px = {k: L.series(lst(o, j), lst(h, j), lst(l, j), lst(c, j), lst(f, j), lst(av, j), lst(avv, j)) for j, k in enumerate(codes)}
    mk = EN.Market(dates, codes, o, h, l, c, factor=f, value=val, volume=vol)
    cfg = replace(EN.EngineConfig(costs=EN.Costs()), breakeven_r=None, market_filter=False, block_disposition=False,
                  max_hold_days=60, liquidate_at_end=False)
    by = {5: [EN.Order(0, "open", weight=0.125, score=90.0), EN.Order(1, "open", weight=0.125, score=80.0)]}
    res = EN.Simulator(mk, cfg, mf=np.ones(n, dtype=bool)).run(lambda i, _s: list(by.get(i, [])))
    bk = L.Book(px, n)
    eq = [bk.step(i, sig.get(i)) for i in range(n)]
    assert np.allclose(eq, res.equity.to_numpy(), rtol=1e-12)
    assert [t[5] for t in bk.trades] == ["delisted"] and list(res.trades["reason"]) == ["delisted"]
    kept = L.Book(px, n, listed={"2330", "2454"})
    for i in range(n):
        kept.step(i, sig.get(i))
    assert kept.trades == [] and sorted(kept.pos) == codes


def test_week_ends_follow_the_official_holidays():
    # 9/25（五）中秋、9/28（一）教師節、10/9（五）國慶補假、10/23（五）薔琵颱風都休市
    assert L.week_ends("2026-09-21", "2026-10-23") == ["2026-09-24", "2026-10-02", "2026-10-08", "2026-10-16", "2026-10-22"]
    assert L.week_ends("2026-10-26", "2026-10-29") == []            # 這一週還沒結束
    assert L.week_ends("2026-10-30", "2026-10-30") == ["2026-10-30"]
    assert L.week_ends(S.START, S.START) == []                      # START 當天颱風休市：那一週不記（第一筆 10/30）


def test_add_week_is_append_only_and_marks_late_books():
    W = {}
    assert L.add_week(W, "2027-01-08", {"R1": [["2330", 95]]}, "2027-01-08 15:40", "abc")
    assert W["2027-01-08"] == {"t": "2027-01-08 15:40", "R1": [["2330", 95]], "r1v": "abc"}
    # 已經記過的本不改；後來才補上的本標 late
    assert L.add_week(W, "2027-01-08", {"R1": [["9999", 99]], "R60": [["3017", 91]], "A": []}, "2027-01-12 06:40")
    w = W["2027-01-08"]
    assert w["R1"] == [["2330", 95]] and w["R60"] == [["3017", 91]] and w["A"] == [] and w["late"] == ["A", "R60"]
    assert w["t"] == "2027-01-08 15:40"
    assert not L.add_week(W, "2027-01-08", {"R60": [["1111", 99]]}, "2027-01-15 06:40")
    assert W["2027-01-08"]["R60"] == [["3017", 91]]


def test_rules_for_tells_missing_from_empty():
    R = {"2026": {"R60": {"rules": [{"conds": [["rs", ">=", 90], ["lu20", ">=", 1]]}]}, "A": {"thr": None, "rules": []}}}
    assert L.rules_for(2026, "R60", R) == [[("rs", ">=", 90), ("lu20", ">=", 1)]]
    assert L.rules_for(2026, "A", R) == []
    assert L.rules_for(2027, "R60", R) is None
    real = L.load_rules()
    assert len(L.rules_for(2026, "R60", real)) == 5 and len(L.rules_for(2026, "A", real)) == 5


def test_dump_is_valid_json_with_one_line_per_entry():
    rec = {"ver": 1, "spec": S.SPEC_DATE, "start": S.START, "last": "2026-10-27",
           "weeks": {"2026-10-23": {"t": "x", "R60": [["2330", 99]], "A": [], "R1": []}},
           "nav": {"2026-10-23": [100, 100, 100, 100, 100], "2026-10-26": [100.5, 99.8, 100, 101.2, 100.9]},
           "trades": {"R60": [["2330", "2026-10-23", "2026-10-26", "2027-01-23", 5.2, "time"]], "A": [], "R1": []},
           "open": {"R60": []}, "stats": {"R60": {"ret": 0.5}}}
    txt = L.dump(rec)
    assert json.loads(txt) == rec
    lines = txt.splitlines()
    assert sum(1 for x in lines if x.startswith('"2026-10-2')) == 3
    assert json.loads(L.dump({"ver": 1, "spec": "s", "start": "s", "weeks": {}})) == \
        {"ver": 1, "spec": "s", "start": "s", "weeks": {}, "nav": {}, "trades": {}, "open": {}, "stats": {}}


def test_review_dates_and_missing_year():
    assert L.due("2027-04-22") is None and L.due("2027-04-23") == "half" and L.due("2027-12-01") == "year"
    R = {"2026": {"R60": {"rules": []}}}
    assert L.missing_year("2026-12-31", R) is None
    assert L.missing_year("2027-01-05", R) is None                 # 2027 年第一個訊號日（1/8）還沒到
    assert L.missing_year("2027-01-08", R) == 2027
    assert L.missing_year("2027-01-08", {**R, "2027": {"R60": {"rules": []}}}) is None


def test_valog_reminds_on_review_dates_and_missing_rules():
    from arm.lab import valog as V
    L0 = {"d": "2027-04-22", "start": S.START, "due": None, "miss": None,
          "v": {"R60": 5.2, "A": 1.0, "R1": -2.0, "TR": 3.0, "EW": 1.1}}
    assert V.sx_events(L0, None) == [] and V.sx_state({}) is None
    L1 = {**L0, "d": "2027-04-23", "due": "half"}
    ev = V.sx_events(L1, V.sx_state(L0))
    assert len(ev) == 1 and ev[0]["ty"] == "sxl"
    assert "飆股觀察滿半年（10/23 起照做 100 萬）：新飆股 105.2 萬、舊目標 101.0 萬、頁面飆股 98.0 萬、大盤 103.0 萬" in ev[0]["txt"]
    assert V.sx_events(L1, V.sx_state(L1)) == []                     # 只在第一次到的那天提醒
    assert "事前寫好的門檻" in V.sx_events({**L1, "due": "year"}, V.sx_state(L1))[0]["txt"]
    assert "2027 年的規則還沒找" in V.sx_events({**L0, "d": "2027-01-08", "miss": 2027}, V.sx_state(L0))[0]["txt"]
    line = V.push_lines({"todo": {}, "ev": ev})[1]
    assert line.startswith("策略驗證：飆股觀察滿半年")


def test_this_years_rules_exist_after_mid_january():
    """每年 1 月 20 日以後還沒有今年的規則 → 紅：dispatch lab_opt.yml（會先補長歷史股價再找規則）。"""
    from arm import clock
    today = clock.today_tw()
    if today.year <= S.SEED_YEAR or today < date(today.year, 1, 20):
        return
    assert str(today.year) in L.load_rules(), (
        f"飆股前瞻記錄缺 {today.year} 年的規則：dispatch lab_opt.yml，或跑 scripts/run_sxlive_rules.py --auto --refresh-min 40")


def test_record_never_reaches_a_page():
    """不上頁面：建頁的程式都不讀紀錄；只有 analyze.run 呼叫 update、valog 讀摘要發提醒。"""
    for f in ("page.py", "sigpage.py", "findings.py", "corepage.py", "heatpage.py", "macpage.py", "copage.py",
              "xspage.py", "stockviz.py", "printview.py"):
        p = ROOT / "arm" / "lab" / f
        if p.exists():
            assert "sxlive" not in p.read_text(encoding="utf-8"), f
    assert "sxlive.update(" in (ROOT / "arm" / "lab" / "analyze.py").read_text(encoding="utf-8")


def test_lab_opt_finds_this_years_rules():
    y = (ROOT / ".github" / "workflows" / "lab_opt.yml").read_text(encoding="utf-8")
    assert "scripts/run_sxlive_rules.py --auto" in y and "pandas" in y
    assert "data/lab/sxlive_rules.json" in y or "git add -f data/lab" in y
