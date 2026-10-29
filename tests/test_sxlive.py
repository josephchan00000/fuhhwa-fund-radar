"""飆股前瞻記錄（arm/lab/sxlive.py；規格 sxlivespec VER 2：R60 放進交易計畫、上配置頁）。"""
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


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_n8_book_matches_the_w10_engine(seed):
    """VER 4：同一份價格、同一批訊號（分數＝強度 − 1000 ×（週數 − 1））：8 格的 Book 和 W10 的引擎（run_w10.Sim，s8）每天的資產、
    每一筆交易都相同。"""
    np, pd, dates, codes, o, h, l, c, f, val, vol, sig = _synthetic(seed)
    sys.path.insert(0, str(ROOT / "tw-superstock-lab" / "src"))
    sys.path.insert(0, str(ROOT / "tw-superstock-lab" / "scripts"))
    from dataclasses import replace
    from superstock import engine as EN
    import run_w10 as W10
    from arm.lab import sxfixspec as FX
    n, hold = len(dates), 12
    rng = np.random.default_rng(seed + 100)
    sig = {i: [(k, float(s) - 1000.0 * int(rng.integers(0, 3))) for k, s in xs] for i, xs in sig.items()}
    av = pd.DataFrame(val).rolling(20, min_periods=1).mean().to_numpy()
    avv = pd.DataFrame(vol).rolling(20, min_periods=1).mean().to_numpy()
    lst = lambda a, j: [None if x != x else float(x) for x in a[:, j]]  # noqa: E731
    px = {code: L.series(lst(o, j), lst(h, j), lst(l, j), lst(c, j), lst(f, j), lst(av, j), lst(avv, j))
          for j, code in enumerate(codes)}
    lu = np.array([px[k]["lu"] for k in codes]).T
    ld = np.array([px[k]["ld"] for k in codes]).T
    mk = EN.Market(dates, codes, o, h, l, c, factor=f, value=val, volume=vol, locked_up=lu, locked_down=ld)
    size = FX.SIZE["s8"]
    cfg = replace(EN.EngineConfig(costs=EN.Costs()), breakeven_r=None, market_filter=False, block_disposition=False,
                  max_hold_days=hold, liquidate_at_end=False, max_positions=size["max_pos"])
    col = {k: j for j, k in enumerate(codes)}
    by = {i: [EN.Order(col[k], "open", weight=float("nan"), score=float(s)) for k, s in xs] for i, xs in sig.items()}
    sim = W10.Sim(mk, cfg, size)
    res = sim.run(lambda i, _s: [EN.Order(x.s, x.kind, weight=x.weight, score=x.score) for x in by.get(i, [])])
    bk = L.Book(px, n, None, {**S.TRADE_N8, "hold": hold})
    eq = [bk.step(i, sig.get(i)) for i in range(n)]
    assert np.allclose(eq, res.equity.to_numpy(), rtol=1e-12, atol=1e-6)
    ref = sorted((str(r.stock_id), dates.get_loc(r.entry_date), dates.get_loc(r.exit_date), r.reason, float(r.shares))
                 for r in res.trades.itertuples())
    got = sorted((k, ei, xi, why, sh) for k, si, ei, xi, r, why, sh, pnl in bk.trades)
    assert got == ref and len(got) > 10
    assert max(len(bk.pos), 0) <= 8
    assert S.TRADE_N8["min_slot"] == FX.MIN_SLOT and S.TRADE_N8["slots"] == size["slots"]


def test_n8_orders_put_new_names_first():
    """上名單週數：START 以前用 hist、START 起用紀錄，哪一週沒有名單就斷；分數＝強度 − 1000 ×（週數 − 1）。"""
    hist = {"2026-10-16": [["A", 90], ["B", 80]], "2026-10-22": [["A", 91], ["C", 70]]}
    weeks = {"2026-10-30": {"R60": [["A", 95], ["B", 85], ["C", 60], ["D", 50]]}}
    o = L.n8_orders("2026-10-30", weeks, hist)
    wk = {c: (rs - sc) / 1000 + 1 for (c, sc), (_, rs) in zip(o, weeks["2026-10-30"]["R60"])}
    assert wk == {"A": 3, "B": 1, "C": 2, "D": 1}          # B 在 10/16 有、10/22 沒有 → 斷掉
    assert [c for c, _ in sorted(o, key=lambda x: -x[1])] == ["B", "D", "C", "A"]
    lists = L.prior_lists("2026-10-30", weeks, {})          # 沒有 hist：只數紀錄那一週
    assert L.run_len("A", lists) == 1


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


def test_only_the_plan_book_reaches_a_page():
    """VER 4：N8 上選股頁；VER 5（corespec VER 5）：交易計畫也讀 N8（page.py 讀 sxlive.LAST["n8"]），今年逐月表讀 N8B（LAST["ytd"]）。
    紀錄檔、A、R1、R60 不上頁面（R60 的 plan 狀態留給推播與研究）。只有 analyze.run 呼叫 update、valog 讀摘要發提醒。"""
    for f in ("sigpage.py", "findings.py", "corepage.py", "cfgpage.py", "heatpage.py", "macpage.py", "copage.py",
              "xspage.py", "stockviz.py", "printview.py"):
        p = ROOT / "arm" / "lab" / f
        if p.exists():
            assert "sxlive" not in p.read_text(encoding="utf-8"), f
    pg = (ROOT / "arm" / "lab" / "page.py").read_text(encoding="utf-8")
    assert pg.count("sxlive") == (pg.count('sxlive.LAST.get("n8")') + pg.count('sxlive.LAST.get("ytd")')
                                  + pg.count("from . import sxlive")) >= 4
    assert 'sxlive.LAST.get("plan")' not in pg
    assert "sxlive.update(" in (ROOT / "arm" / "lab" / "analyze.py").read_text(encoding="utf-8")
    assert S.TAKE_BOOK == S.LIST_BOOK == S.BOOKS[0] == "R60" and S.PLAN_BOOK == S.BOOKS[-1] == "N8"


def _plan_fixture():
    """合成價格跑一本帳到第 n−1 天，第 n−1 天剛好有一批訊號（明天開盤要買）、有一檔到期（明天開盤要賣）。"""
    np, pd, dates, codes, o, h, l, c, f, val, vol, sig = _synthetic(5, n=90, m=24)
    n, hold = len(dates), 12
    av = pd.DataFrame(val).rolling(20, min_periods=1).mean().to_numpy()
    avv = pd.DataFrame(vol).rolling(20, min_periods=1).mean().to_numpy()
    lst = lambda a, j: [None if x != x else float(x) for x in a[:, j]]  # noqa: E731
    px = {code: L.series(lst(o, j), lst(h, j), lst(l, j), lst(c, j), lst(f, j), lst(av, j), lst(avv, j))
          for j, code in enumerate(codes)}
    sig = {i: v for i, v in sig.items() if i < n - 1}
    sig[n - 1] = [(codes[j], 90 - j) for j in range(10)]
    T = {**S.TRADE, "hold": hold}
    bk = L.Book(px, n, set(codes), T)
    for i in range(n):
        bk.step(i, sig.get(i))
    cal = [str(d.date()) for d in dates]

    class P:
        pass
    P.cal = cal
    wk = {cal[i]: {"R60": [[k, s] for k, s in v]} for i, v in sig.items()}
    rec = {"last": cal[-1], "weeks": wk, "_book": bk, "_px": px}
    return rec, {"P": P}, bk, px, cal, sig, hold


def test_plan_state_lists_holdings_sells_and_buys(monkeypatch):
    rec, ctx, bk, px, cal, sig, hold = _plan_fixture()
    monkeypatch.setitem(S.TRADE, "hold", hold)
    st = L.plan_state(rec, ctx, {"1101": "台泥"})
    i1 = len(cal) - 1
    assert st["book"] == "R60" and st["d"] == cal[-1] and st["wk"] == cal[-1] and st["n_list"] == 10
    assert [h["c"] for h in st["hold"]] == [c for c, q in sorted(bk.pos.items(), key=lambda x: (x[1]["ei"], x[0]))]
    assert sum(h["w"] for h in st["hold"]) + st["cash"] == pytest.approx(1.0, abs=1e-9)
    for h in st["hold"]:
        q = bk.pos[h["c"]]
        assert h["ent"] == cal[q["ei"]] and h["sell"] == bool(q["pend"])
        if q["ei"] + hold < len(cal):
            assert h["due"] == cal[q["ei"] + hold]
        p = px[h["c"]]
        assert h["epx"] == pytest.approx(p["o"][q["ei"]] / p["f"][q["ei"]])
    assert st["sell"] == [h["c"] for h in st["hold"] if h["sell"]]
    # 明天開盤要買的＝最後一天的訊號裡手上沒有的，依 RS 高到低；估計買得到的在前面
    want = [c for c, _ in sorted(sig[i1], key=lambda x: -x[1]) if c not in bk.pos]
    assert [b["c"] for b in st["buy"]] == want
    fills = [b["fill"] for b in st["buy"]]
    assert fills == sorted(fills, reverse=True) and st["n_buy"] == sum(fills)
    assert st["list"][0]["c"] == "1101" and st["list"][0]["n"] == "台泥"


def test_plan_state_before_any_week():
    """還沒有任何一週的紀錄（第一個訊號日之前）：沒有持股、全部現金、下一次看名單的日子照休市表。"""
    class P:
        cal = ["2026-10-20", "2026-10-21", "2026-10-22", "2026-10-26"]
    st = L.plan_state({"last": "2026-10-26", "weeks": {}}, {"P": P})
    assert st["hold"] == [] and st["buy"] == [] and st["cash"] == 1.0 and st["wk"] is None
    assert st["next"] == "2026-10-27" and st["next_wk"] == "2026-10-30" and not st["wk_today"]


def test_start_index_is_the_takeover_day():
    """VER 3：成績從接手那天（TAKE＝10/22，START 10/23 颱風休市前最後一個交易日）收盤起算。"""
    assert L.start_index(["2026-10-21", "2026-10-22", "2026-10-26", "2026-10-27"]) == 1
    assert L.start_index(["2026-10-26", "2026-10-27"]) == 0


def _seed_from(bk, cal: list, t: int, sig_t: list | None) -> dict:
    """一本帳第 t 天收盤（下單之前）的狀態 → 接手檔的格式（sxlivespec VER 3 ⑥）。"""
    return {"ver": 3, "book": "R60", "take": cal[t], "cash": bk.cash,
            "pos": [{"c": c, "sh": q["sh"], "ent": cal[q["ei"]], "sig": cal[q["si"]], "cin": q["cin"], "pend": q["pend"]}
                    for c, q in bk.pos.items()],
            "weeks": {cal[t]: {"R60": [[c, s] for c, s in (sig_t or [])]}}}


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_takeover_continues_the_same_book(seed):
    """接手＝那本帳第 t 天收盤的狀態原封不動放進來、第 t 天的名單照規則下單：之後每天的資產、每一筆交易都和沒中斷的帳相同；
    接手時拿著的那幾筆另記接手以來（÷ 接手那天收盤市值）。"""
    np, pd, dates, codes, o, h, l, c, f, val, vol, sig = _synthetic(seed)
    n, hold = len(dates), 12
    av = pd.DataFrame(val).rolling(20, min_periods=1).mean().to_numpy()
    avv = pd.DataFrame(vol).rolling(20, min_periods=1).mean().to_numpy()
    lst = lambda a, j: [None if x != x else float(x) for x in a[:, j]]  # noqa: E731
    px = {k: L.series(lst(o, j), lst(h, j), lst(l, j), lst(c, j), lst(f, j), lst(av, j), lst(avv, j)) for j, k in enumerate(codes)}
    cal = [str(d.date()) for d in dates]
    T = {**S.TRADE, "hold": hold}
    full = L.Book(px, n, None, T)
    eq_full = [full.step(i, sig.get(i)) for i in range(n)]
    t = next(i for i in sorted(sig) if i > 60)                 # 接手那天剛好有一批訊號
    run = L.Book(px, n, None, T)
    for i in range(t):
        run.step(i, sig.get(i))
    run.step(t, None)                                          # 第 t 天：開盤、收盤照做，不下單
    seed_doc = _seed_from(run, cal, t, sig.get(t))
    held = set(run.pos)
    assert held
    bk = L.Book(px, n, None, T)
    e0 = bk.take(seed_doc, cal, t)
    assert e0 == pytest.approx(eq_full[t], rel=1e-12)
    bk.place(t, seed_doc["weeks"][cal[t]]["R60"])
    eq = [bk.step(i, sig.get(i)) for i in range(t + 1, n)]
    assert np.allclose(eq, eq_full[t + 1:], rtol=1e-12)
    after = [x[:8] for x in full.trades if x[3] > t]
    got = [x[:8] for x in bk.trades]
    assert [x[:6] for x in got] == [x[:6] for x in after] and len(got) > 5
    assert np.allclose([x[4] for x in got], [x[4] for x in after], rtol=1e-12)
    for x in bk.trades:                                        # 接手時拿著的：另記接手以來
        if x[0] in held and x[2] <= t:
            assert len(x) == 10
            v0 = run.pos[x[0]]["k"] * (px[x[0]]["c"][t] if px[x[0]]["c"][t] is not None else px[x[0]]["cff"][t])
            assert x[8] == pytest.approx((x[7] + run.pos[x[0]]["cin"]) / v0 - 1, rel=1e-9)
        else:
            assert len(x) == 8


def test_perf_starts_at_take_and_uses_the_seed(monkeypatch):
    """perf：TAKE 收盤＝100；R60 從接手的狀態開始（第一天就有持股），A、R1 照舊從現金開始；接手那幾筆的統計只算接手以來。"""
    np, pd, dates, codes, o, h, l, c, f, val, vol, sig = _synthetic(7)
    n, hold = len(dates), 12
    av = pd.DataFrame(val).rolling(20, min_periods=1).mean().to_numpy()
    avv = pd.DataFrame(vol).rolling(20, min_periods=1).mean().to_numpy()
    lst = lambda a, j: [None if x != x else float(x) for x in a[:, j]]  # noqa: E731
    px = {k: L.series(lst(o, j), lst(h, j), lst(l, j), lst(c, j), lst(f, j), lst(av, j), lst(avv, j)) for j, k in enumerate(codes)}
    cal = [str(d.date()) for d in dates]
    monkeypatch.setitem(S.TRADE, "hold", hold)
    t = next(i for i in sorted(sig) if i > 60)
    run = L.Book(px, n, None, {**S.TRADE})
    for i in range(t):
        run.step(i, sig.get(i))
    run.step(t, None)
    seed_doc = _seed_from(run, cal, t, sig.get(t))
    later = sorted(i for i in sig if i > t)
    weeks = {cal[i]: {"R60": [[k, s] for k, s in sig[i]], "A": [[k, s] for k, s in sig[i]][:3]} for i in later}
    monkeypatch.setattr(S, "TAKE", cal[t])

    class P:
        pass
    P.cal = cal
    ctx = {"P": P, "listed": None}
    monkeypatch.setattr(L, "panel", lambda ctx, codes, ev=None: px)
    monkeypatch.setattr(L, "tr_series", lambda dates: [1.0] * len(dates))
    monkeypatch.setattr(L, "ew_series", lambda ctx, i0, i1, ev=None: [1.0] * (i1 - i0 + 1))
    out = L.perf(ctx, weeks, cal[-1], ev={}, seed=seed_doc)
    days = sorted(out["nav"])
    assert days[0] == cal[t] and out["nav"][cal[t]][:3] == [100.0, 100.0, 100.0]
    full = L.Book(px, n, None, {**S.TRADE})
    eq_full = [full.step(i, sig.get(i) if i <= t or i in later else None) for i in range(n)]
    assert out["nav"][cal[-1]][0] == pytest.approx(round(eq_full[-1] / eq_full[t] * 100, 2), abs=0.011)
    assert out["stats"]["R60"]["open"] == len(out["_book"].pos) and out["_base"] == pytest.approx(eq_full[t])
    tk = [x for x in out["trades"]["R60"] if len(x) == 7]
    assert tk and all(x[2] <= cal[t] for x in tk)              # 接手的那幾筆：買進日在接手以前，另記接手以來
    assert out["stats"]["A"]["n"] >= 0 and out["nav"][cal[t]][1] == 100.0


def test_perf_n8b_continues_the_n8_book_and_feeds_ytd(monkeypatch):
    """VER 5：N8B＝N8 做法的回測延續——接手那天收盤照 seed_bt 記的順序下單、之後每週照 R60 名單、N8 的順序；
    nav 第 7 欄＝N8B（和沒中斷的 8 格帳相同）；ytd_part 預設讀 N8B。沒有 seed_bt＝第 7 欄空、不算 N8B。"""
    np, pd, dates, codes, o, h, l, c, f, val, vol, sig = _synthetic(9)
    n, hold = len(dates), 12
    av = pd.DataFrame(val).rolling(20, min_periods=1).mean().to_numpy()
    avv = pd.DataFrame(vol).rolling(20, min_periods=1).mean().to_numpy()
    lst = lambda a, j: [None if x != x else float(x) for x in a[:, j]]  # noqa: E731
    px = {k: L.series(lst(o, j), lst(h, j), lst(l, j), lst(c, j), lst(f, j), lst(av, j), lst(avv, j)) for j, k in enumerate(codes)}
    cal = [str(d.date()) for d in dates]
    monkeypatch.setitem(S.TRADE, "hold", hold)
    monkeypatch.setattr(S, "TRADE_N8", {**S.TRADE_N8, "hold": hold})
    monkeypatch.setattr(L, "n8_orders", lambda d, weeks, hist: weeks[d]["R60"])
    t = None
    for t0 in (i for i in sorted(sig) if i > 60):           # 接手那天剛好有一批訊號、8 格帳手上有股票
        n8 = L.Book(px, n, None, {**S.TRADE_N8})
        for i in range(t0):
            n8.step(i, sig.get(i))
        n8.step(t0, None)
        if n8.pos:
            t = t0
            break
    assert t is not None
    run = L.Book(px, n, None, {**S.TRADE})
    for i in range(t):
        run.step(i, sig.get(i))
    run.step(t, None)
    seed_doc = _seed_from(run, cal, t, sig.get(t))
    bt = _seed_from(n8, cal, t, sig.get(t))
    bt.update({"ver": 5, "book": S.BT_BOOK, "orders": {cal[t]: [[k, s] for k, s in sig.get(t) or []]}})
    assert n8.pos
    later = sorted(i for i in sig if i > t)
    weeks = {cal[i]: {"R60": [[k, s] for k, s in sig[i]]} for i in later}
    monkeypatch.setattr(S, "TAKE", cal[t])
    monkeypatch.setattr(S, "START4", cal[-1])                  # N8（選股頁那本）這段期間不下單

    class P:
        pass
    P.cal = cal
    ctx = {"P": P, "listed": None}
    monkeypatch.setattr(L, "panel", lambda ctx, codes, ev=None: px)
    monkeypatch.setattr(L, "tr_series", lambda dates: [1.0] * len(dates))
    monkeypatch.setattr(L, "ew_series", lambda ctx, i0, i1, ev=None: [1.0] * (i1 - i0 + 1))
    out = L.perf(ctx, weeks, cal[-1], ev={}, seed=seed_doc, hist={}, seed_bt=bt)
    full = L.Book(px, n, None, {**S.TRADE_N8})
    eq_full = [full.step(i, sig.get(i) if i <= t or i in later else None) for i in range(n)]
    assert out["nav"][cal[t]][6] == 100.0
    for k in (t + 5, n - 1):
        assert out["nav"][cal[k]][6] == pytest.approx(round(eq_full[k] / eq_full[t] * 100, 2), abs=0.011)
    assert out["_btbase"] == pytest.approx(eq_full[t]) and len(out["_bt"].pos) == len(full.pos)
    yp = L.ytd_part(out, ctx, cal[-1])
    assert yp["book"] == S.BT_BOOK and yp["e0"] == pytest.approx(eq_full[t], abs=0.01)
    assert yp["eq"][cal[-1]] == pytest.approx(out["nav"][cal[-1]][6] / 100 * eq_full[t], abs=0.01)
    assert sorted(r[0] for r in yp["open"]) == sorted(full.pos) and all(len(r) == 8 for r in yp["open"])
    r60 = L.ytd_part(out, ctx, cal[-1], book="R60")
    assert r60["book"] == "R60" and r60["eq"][cal[-1]] == pytest.approx(out["nav"][cal[-1]][0] / 100 * out["_base"], abs=0.01)
    no = L.perf(ctx, weeks, cal[-1], ev={}, seed=seed_doc, hist={})
    assert no["nav"][cal[-1]][6] is None and no["_bt"] is None and L.ytd_part(no, ctx, cal[-1]) is None


def test_plan_state_marks_backtest_buys_and_return_since_takeover(monkeypatch):
    """配置頁：接手時就拿著的持股標 take、買進日在接手以前＝回測（bt）；rl＝接手那天收盤到最後一天收盤（含息）。"""
    np, pd, dates, codes, o, h, l, c, f, val, vol, sig = _synthetic(8)
    n, hold = len(dates), 40
    av = pd.DataFrame(val).rolling(20, min_periods=1).mean().to_numpy()
    avv = pd.DataFrame(vol).rolling(20, min_periods=1).mean().to_numpy()
    lst = lambda a, j: [None if x != x else float(x) for x in a[:, j]]  # noqa: E731
    px = {k: L.series(lst(o, j), lst(h, j), lst(l, j), lst(c, j), lst(f, j), lst(av, j), lst(avv, j)) for j, k in enumerate(codes)}
    cal = [str(d.date()) for d in dates]
    monkeypatch.setitem(S.TRADE, "hold", hold)
    t = next(i for i in sorted(sig) if i > 100)
    run = L.Book(px, n, None, {**S.TRADE})
    for i in range(t):
        run.step(i, sig.get(i))
    run.step(t, None)
    seed_doc = _seed_from(run, cal, t, sig.get(t))
    monkeypatch.setattr(S, "TAKE", cal[t])
    bk = L.Book(px, n, None, {**S.TRADE})
    bk.take(seed_doc, cal, t)
    bk.place(t, seed_doc["weeks"][cal[t]]["R60"])
    last = min(n - 1, t + 6)
    for i in range(t + 1, last + 1):
        bk.step(i, None)

    class P:
        pass
    P.cal = cal[:last + 1]
    rec = {"last": cal[last], "weeks": {}, "_book": bk, "_px": px, "_base": seed_doc["cash"] + 0, "_i0": t}
    st = L.plan_state(rec, {"P": P}, {}, None, None, seed_doc)
    assert st["take"] == cal[t] and st["wk"] == cal[t]          # 最新一週＝接手那一週的名單
    took = {x["c"] for x in seed_doc["pos"]}
    for h in st["hold"]:
        p = px[h["c"]]
        cl = p["c"][last] if p["c"][last] is not None else p["cff"][last]
        if h["c"] in took and h["ent"] <= cal[t]:
            c0 = p["c"][t] if p["c"][t] is not None else p["cff"][t]
            assert h["take"] and h["bt"] and h["rl"] == pytest.approx(cl / c0 - 1)
        else:
            assert not h["take"] and not h["bt"] and h["rl"] == h["r"]
    assert any(h["take"] for h in st["hold"])


def test_lab_opt_finds_this_years_rules():
    y = (ROOT / ".github" / "workflows" / "lab_opt.yml").read_text(encoding="utf-8")
    assert "scripts/run_sxlive_rules.py --auto" in y and "pandas" in y
    assert "data/lab/sxlive_rules.json" in y or "git add -f data/lab" in y


RULES_Y = [[("rs", ">=", 90), ("lu20", ">=", 1), ("rnha", "=", True)], [("liq", ">=", 6.5e8), ("rnha", "=", True)]]


def test_day_signals_records_which_rules_each_stock_matched(monkeypatch):
    """配置頁第 5 步：每週記下每一檔符合今年第幾條規則、那幾條用到的數字（只給頁面顯示，訊號照舊）。"""
    from arm.lab import superx as SX

    class P:
        cal = ["2026-10-30"]
        codes = ["1101", "2330", "9999"]
        cap = {c: [None] for c in codes}
        s = {c: {"c": [10.0]} for c in codes}
    F = {"1101": {"el": True, "rs": 96.4, "lu20": 2, "rnha": True, "liq": 1.2e9},
         "2330": {"el": True, "rs": 91.0, "lu20": 0, "rnha": True, "liq": 9e9},
         "9999": {"el": True, "rs": 99.0, "lu20": 3, "rnha": False, "liq": 1e9}}
    monkeypatch.setattr(SX, "feats_on", lambda *a, **k: F)
    ctx = {"P": P, "snaps": [], "pxs": None, "funds": None, "qitems": None, "rf": None}
    plain = L.day_signals(0, ctx, {"R60": RULES_Y})
    why = {}
    sig = L.day_signals(0, ctx, {"R60": RULES_Y}, why=why)
    assert sig == plain == {"R60": [["1101", 96.4], ["2330", 91.0]]}                  # 訊號不受影響
    assert why["R60"]["1101"] == {"k": [0, 1], "v": {"liq": 1200000000, "lu20": 2, "rnha": True, "rs": 96.4}}
    assert why["R60"]["2330"] == {"k": [1], "v": {"liq": 9000000000, "rnha": True}}
    assert "9999" not in why["R60"]


def test_add_week_keeps_why_only_with_newly_added_books():
    W = {}
    w1 = {"R60": {"3017": {"k": [0], "v": {"rs": 95}}}}
    assert L.add_week(W, "2026-10-30", {"R60": [["3017", 95]], "A": []}, "2026-10-30 15:40", why=w1)
    assert W["2026-10-30"]["why"] == w1
    assert not L.add_week(W, "2026-10-30", {"R60": [["1111", 99]]}, "2026-11-02 06:40", why={"R60": {"1111": {"k": [1]}}})
    assert W["2026-10-30"]["why"] == w1                                             # 已經記過的本不改


def test_why_text_writes_first_matched_rule_with_numbers():
    w = {"k": [0, 1], "v": {"rs": 96.4, "lu20": 2, "rnha": True, "liq": 1.2e9}}
    t, more = L.why_text(RULES_Y, w)
    assert t == "強度 96（要 90 以上）、近 20 日漲停 2 次、月營收創歷史新高" and more == 1
    assert L._why_lines(RULES_Y, w) == ["符合：強度 96（要 90 以上）、近 20 日漲停 2 次、月營收創歷史新高（另外也符合 1 條）"]
    assert L.why_text(RULES_Y, {"k": [1], "v": {"liq": 1.2e9, "rnha": True}}) == ("20 日均成交值 12.0 億（要 6.5 億以上）、月營收創歷史新高", 0)
    assert L.why_text(RULES_Y, None) == (None, 0) and L._why_lines(None, {"k": [0]}) == []
    assert L.why_text(RULES_Y, {"k": [5]}) == (None, 0)                             # 規則清單對不上：不寫


def test_plan_state_explains_list_buys_and_holdings(monkeypatch):
    rec, ctx, bk, px, cal, sig, hold = _plan_fixture()
    monkeypatch.setitem(S.TRADE, "hold", hold)
    i1 = len(cal) - 1
    top = sig[i1][0][0]
    rec["weeks"][cal[i1]]["why"] = {"R60": {top: {"k": [0], "v": {"rs": 96.4, "lu20": 2, "rnha": True}}}}
    held = next(iter(bk.pos))                                                     # 一檔持股：買進那一週記了它符合第 2 條
    sd = cal[bk.pos[held]["si"]]
    rec["weeks"][sd]["why"] = {"R60": {held: {"k": [1], "v": {"liq": 1.2e9, "rnha": True}}}}
    Ry = {cal[i1][:4]: {"R60": {"rules": [{"conds": [list(c) for c in r]} for r in RULES_Y]}}}
    if sd[:4] != cal[i1][:4]:
        Ry[sd[:4]] = Ry[cal[i1][:4]]
    st = L.plan_state(rec, ctx, {}, None, Ry)
    lw = {x["c"]: x["why"] for x in st["list"]}
    assert lw[top] == ["符合：強度 96（要 90 以上）、近 20 日漲停 2 次、月營收創歷史新高"]
    assert all(v == [] for c, v in lw.items() if c != top)
    bw = {x["c"]: x["why"] for x in st["buy"]}
    assert all(v == lw.get(c, []) for c, v in bw.items())
    h = next(x for x in st["hold"] if x["c"] == held)
    rank = [c for c, _ in rec["weeks"][sd]["R60"]].index(held) + 1
    assert h["why"] == [f"{int(sd[5:7])}/{int(sd[8:])} 那週名單第 {rank} 名", "符合：20 日均成交值 12.0 億（要 6.5 億以上）、月營收創歷史新高"]


def test_why_text_uses_plain_words():
    """名單「符合：…」每一種條件的寫法都不得有主頁面不用的字（tests/test_plain.py 的清單）。
    那支測試用今天的資料建頁，10/30 以前名單還沒出來，掃不到這一句，所以這裡逐一條件檢查。"""
    import ast
    from arm.lab import superx as SX
    words = []
    for node in ast.parse((ROOT / "tests" / "test_plain.py").read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") in ("METHOD", "STATUS", "NOT_PLAIN"):
            words += list(ast.literal_eval(node.value))
    assert len(words) > 30
    keys = sorted(set(SX.SHORT) | set(SX.FNAME))
    txt = [SX.cond_value_text((k, op, 0.5), v) for k in keys for op in (">=", "<=", "=") for v in (0.7, 3, None)]
    txt += [L._why_lines([[(k, ">=", 0.5)], [(k, "<=", 0.5)]], {"k": [0, 1], "v": {k: 0.7}})[0] for k in keys]
    hits = [(w, t) for t in txt for w in words if w in t]
    assert not hits, hits[:5]


def test_panel_skips_dividend_events_already_absorbed_by_the_page_basis():
    """大比例配股（相鄰收盤差 1.8 倍以上）頁面價格已經換算成現在的單位；panel 不能再乘一次除權倍數（2026-10-29：緯穎 9/2、世紀 8/14）。"""
    from arm.lab import packtest as PT
    cal = ["2026-08-27", "2026-08-28", "2026-08-31", "2026-09-01", "2026-09-02", "2026-09-03"]
    raw = [7000.0, 7100.0, None, 7800.0, 2610.0, 2700.0]
    F = PT._basis(raw)
    adj = [None if x is None else x / F[i] for i, x in enumerate(raw)]

    class P:
        pass
    P.cal = cal
    P.s = {"6669": {"o": adj, "h": adj, "l": adj, "c": adj, "v": [1.0] * 6}, "1101": {"o": adj, "h": adj, "l": adj, "c": adj,
                                                                                        "v": [1.0] * 6}}
    P.liq = {}
    P.basis = {"6669": F}
    ev = {"6669": [("2026-09-02", 0.3353, None)], "1101": [("2026-09-02", 0.3353, None)]}
    assert L.absorbed(cal, F, adj, "2026-09-02") and not L.absorbed(cal, F, adj, "2026-08-28")
    assert not L.absorbed(cal, None, adj, "2026-09-02")
    px = L.panel({"P": P}, ["6669", "1101"], ev)
    assert px["6669"]["f"][0] == 1.0 and px["6669"]["c"][0] == pytest.approx(7000 * 2610 / 7800)   # 只換算一次
    assert px["1101"]["f"][0] == pytest.approx(0.3353)                                         # 沒有口徑資料的照舊乘
