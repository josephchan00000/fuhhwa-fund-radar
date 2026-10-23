"""資料與訊號盤查（docs/lab_audit_plan.md；sigspec VER 20、heatspec VER 10、heatspec_us VER 2）：和直接算的版本比對。

①月資料補缺月（連續缺 ≤ 2 個月內插）與資料過期；②狀態型的一段遇到相反的極端就切開；③最新的讀數取代舊的事件；
④出現了但沒算進次數的日子；⑤照規則的那一筆交易（哪天進場、持有到哪天）。"""
from datetime import date, timedelta

import numpy as np

from arm.lab import heat as H
from arm.lab import heatspec as HS
from arm.lab import heatcalc_us as HU
from arm.lab import sigcat as G
from arm.lab import sigluck as LK
from arm.lab import sigpage as SP
from arm.lab import sigspec as S
from arm.lab import thermocal as TC


def _cal(T, start=date(2001, 1, 2)):
    out, d = [], start
    while len(out) < T:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


# ── ① 補缺月、資料過期 ─────────────────────────────────────────────────────────

def test_fill_gaps_only_short_interior_gaps():
    ser = {"2025-08": 4.3, "2025-09": 4.4, "2025-11": 4.5, "2026-03": 4.0, "2026-04": None}
    out = H.fill_gaps(ser, 2)
    assert abs(out["2025-10"] - 4.45) < 1e-12                       # 只缺一個月＝前後兩個月平均
    assert not any(k in out for k in ("2025-12", "2026-01", "2026-02"))   # 缺 3 個月不補
    assert "2026-04" not in out                                      # 最後一個有值的月份之後不補（None 當成缺）
    assert H.fill_gaps({"2025-01": 100.0, "2025-05": 146.41}, 2, geo=True) == {"2025-01": 100.0, "2025-05": 146.41}   # 缺 3 個月不補
    g = H.fill_gaps({"2025-01": 100.0, "2025-03": 121.0}, 2, geo=True)
    assert abs(g["2025-02"] - 110.0) < 1e-9                          # 幾何平均
    g2 = H.fill_gaps({"2024-12": 100.0, "2025-03": 133.1}, 2, geo=True)
    assert abs(g2["2025-01"] - 110.0) < 1e-9 and abs(g2["2025-02"] - 121.0) < 1e-9   # 缺 2 個月：幾何內插
    assert list(H.fill_gaps(ser, 2)) == sorted(H.fill_gaps(ser, 2))


def test_fill_bls_three_columns():
    bls = {"2025-09": [4.4, 324.8, 330.8], "2025-11": [4.5, 324.1, 330.4], "2025-12": [4.4, None, 330.5]}
    out = HU.fill_bls(bls)
    assert abs(out["2025-10"][0] - 4.45) < 1e-12                     # 失業率：算術
    assert abs(out["2025-10"][1] - (324.8 * 324.1) ** 0.5) < 1e-9    # CPI：幾何
    assert abs(out["2025-10"][2] - (330.8 * 330.4) ** 0.5) < 1e-9
    assert out["2025-12"] == [4.4, None, 330.5] and out["2025-09"] == [4.4, 324.8, 330.8]


def test_stale_info_monthly_quarterly_and_fresh():
    ms = [f"2024-{m:02d}" for m in range(1, 13)] + [f"2025-{m:02d}" for m in range(1, 10)]
    last, due = H.stale_info(ms, (1, 8), "2026-10-21")
    assert last == "2025-09" and due[0] == "2025-10" and due[-1] == "2026-09" and len(due) == 12
    assert H.stale_info(["2025-06", "2025-09", "2025-12", "2026-03", "2026-06"], (3, 15), "2026-10-21") == ("2026-06", [])
    assert H.stale_info(["2026-07", "2026-08", "2026-09"], (1, 21), "2026-10-21") == ("2026-09", [])
    assert H.stale_info(["2026-07", "2026-08"], (1, 21), "2026-10-21") == ("2026-08", ["2026-09"])   # 晚一期：還不算過期
    assert len(H.stale_info(["2026-07", "2026-08"], (1, 21), "2026-10-21")[1]) < HS.STALE_M <= len(due)
    assert H.stale_info([], (1, 1), "2026-10-21") == (None, [])


# ── ② 分段遇到相反的極端就切開 ───────────────────────────────────────────────────

def test_episodes_break_at_opposite_extreme():
    pos = [0, 1, 2, 10, 11]
    brk = np.zeros(20, dtype=bool)
    assert G.episodes(pos, 20) == [[0, 1, 2, 10, 11]]
    assert G.episodes(pos, 20, brk) == [[0, 1, 2, 10, 11]]
    brk[5] = True                                                   # 中斷的日子裡到過相反的極端
    assert G.episodes(pos, 20, brk) == [[0, 1, 2], [10, 11]]
    brk2 = np.zeros(20, dtype=bool)
    brk2[15] = True                                                 # 在這一段之後才出現：不影響
    assert G.episodes(pos, 20, brk2) == [[0, 1, 2, 10, 11]]
    assert G.episodes([0, 1, 30], 20, brk) == [[0, 1], [30]]        # 本來就超過 gap


def _frame_one_var(x, mk="tw"):
    T = len(x)
    cal = _cal(T)
    we = [i for i in range(T) if i == T - 1 or date.fromisoformat(cal[i + 1]).isocalendar()[1] != date.fromisoformat(cal[i]).isocalendar()[1]]
    F = {"mk": mk, "cal": cal, "we": we}
    v = {"key": "K", "name": "測試", "grp": "tech", "H": 20, "x": np.asarray(x, dtype=float)}
    return F, v


def test_var_signals_attach_break_flags_and_expiry():
    """過冷 → 過熱 → 過冷：過冷中切成兩段；進入過熱之後到過過冷 → 不再算現在有效。"""
    x = [50.0] * 30 + [10.0] * 3 + [50.0] * 5 + [90.0] * 3 + [50.0] * 5 + [10.0] * 3
    F, v = _frame_one_var(x)
    sds = {sd["sig"]: sd for sd in G._var_signals(F, v, "heat")}
    cold, hot_in = sds["cold"], sds["hot_in"]
    assert list(cold["brk"]) == [a >= S.HOT for a in x]
    st = np.asarray(cold["state"], bool)
    eps = G.episodes([i for i in range(len(st)) if st[i]], S.EP_GAP, cold["brk"])
    assert [[int(cold["samp"][e[0]]), int(cold["samp"][e[-1]])] for e in eps] == [[30, 32], [46, 48]]
    assert len(G.episodes([i for i in range(len(st)) if st[i]], S.EP_GAP)) == 1   # 沒有 VER 20 的規則：一段
    assert hot_in["days"] == [38]
    assert set(int(t) for t in hot_in["exp"]) >= {46, 47, 48} and all(int(t) not in (38,) for t in hot_in["exp"])
    assert "exp" not in cold and "brk" not in hot_in
    assert set(int(t) for t in sds["cold_in"]["exp"]) >= {38, 39, 40}   # 進入過冷之後出現過熱
    # crash 也套用；其他類別不套用
    assert "brk" in {sd["sig"]: sd for sd in G._var_signals(F, v, "crash")}["cold"]


def test_exp_end_activity_and_thermocal_active():
    sd = {"kind": "event", "days": [5, 30], "exp": np.array([10, 31]), "H": 20, "samp": np.arange(100)}
    assert list(G.exp_end(sd, [5, 30], 20)) == [10, 31]
    a = G.activity(sd, 100)
    assert list(np.nonzero(a)[0]) == list(range(5, 10)) + [30]
    assert list(np.nonzero(TC.active(sd, 100, 20))[0]) == list(range(5, 10)) + [30]
    sd2 = {"kind": "event", "days": [5, 30], "H": 20, "samp": np.arange(100)}           # 沒有 exp：照 H
    assert list(G.exp_end(sd2, [5, 30], 20)) == [25, 50]


def test_now_market_newest_reading_wins(monkeypatch):
    T = 120
    cal = _cal(T)
    samp = np.arange(T)
    st = np.zeros(T, dtype=bool)
    st[[90, 91, 92, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119]] = True
    brk = np.zeros(T, dtype=bool)
    brk[100] = True                                                 # 過冷 → 中間有一天過熱 → 又過冷
    sds = [{"id": "stale", "cat": "heat", "var": "F5", "kind": "state", "H": 20, "samp": samp, "state": st},
           {"id": "d_stale", "cat": "deriv", "var": "F5", "kind": "state", "H": 60, "samp": samp, "state": st},
           {"id": "cold", "cat": "heat", "var": "K", "kind": "state", "H": 20, "samp": samp, "state": st, "brk": brk},
           {"id": "hot_in", "cat": "heat", "var": "K", "kind": "event", "H": 20, "samp": samp, "days": [105], "exp": np.array([110])},
           {"id": "fresh", "cat": "tech", "var": "ma20_up", "kind": "event", "H": 20, "samp": samp, "days": [112], "exp": np.array([50])},
           {"id": "dead", "cat": "tech", "var": "ma20_dn", "kind": "event", "H": 20, "samp": samp, "days": [108], "exp": np.array([112])}]
    monkeypatch.setattr(G, "signals", lambda F: sds)
    on = G.now_market({"cal": cal, "mk": "spx", "stale": ["F5"]})
    assert set(on) == {"cold", "fresh"}                              # 資料過期、被相反讀數取代的都不算
    assert on["cold"]["since"] == cal[110] and on["cold"]["n"] == 10   # 現在這一段從 110 起（不是 90）
    f = on["fresh"]
    assert f["since"] == cal[112] and f["buy"] == cal[113] and f["left"] == 20 - (T - 1 - 112)
    assert f["sell"] == G.trade_dates("spx", cal, 112, 20)["sell"] and f["rem"] == 112 + 1 + 20 - (T - 1)
    on2 = G.now_market({"cal": cal})                                # 沒有市場代號：不排交易日、資料過期照算
    assert "buy" not in on2["fresh"] and "stale" in on2


def test_trade_dates_calendar_then_holidays():
    cal = _cal(40, start=date(2026, 9, 1))
    t = len(cal) - 4
    tr = G.trade_dates("tw", cal, t, 2)
    assert tr["buy"] == cal[t + 1] and tr["rem"] == 0 and tr["sell"] == cal[t + 3] == cal[-1]   # 都在資料裡
    tr = G.trade_dates("tw", cal, len(cal) - 3, 2)
    assert tr["buy"] == cal[-2] and tr["rem"] == 1 and tr["sell"] > cal[-1]                     # 出場日要往後推一天
    tr = G.trade_dates("tw", cal, len(cal) - 1, 5)                  # 狀態型：今天看到 → 下一個交易日收盤進場
    from arm.lab import xstrat as XS
    fut = XS.future_days("tw", cal[-1], 6)
    assert tr == {"buy": fut[0], "sell": fut[5], "rem": 6}


def test_shift_occ_matches_state_stat_with_breaks():
    """打亂測試平移時，相反極端的日子跟著一起平移：每一次平移的分段＝把狀態和 brk 一起 roll 之後 st_stat 的分段。"""
    rng = np.random.default_rng(3)
    T = 800
    px = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, T)))
    Yu, Yw, _ = G.outcomes(px, 20, 0.08)
    samp = np.arange(T)
    st = rng.random(T) < 0.15
    brk = (~st) & (rng.random(T) < 0.05)
    sd = {"kind": "state", "H": 20, "samp": samp, "state": st, "brk": brk}
    sh = LK.Shift(sd, Yu, Yw)
    for o in (0, 37, 301):
        f, u, w, _ = sh.occ(o)
        R = G.st_stat(np.roll(st, o), samp, Yu, Yw, S.EP_GAP, 0, brk=np.roll(brk, o))
        assert [int(x) for x in f] == [o_[0] for o_ in R["occ"]]
        assert np.allclose(u, [o_[3] for o_ in R["occ"]]) and np.allclose(w, [o_[4] for o_ in R["occ"]])


# ── ④ 出現了但沒算進次數的 ─────────────────────────────────────────────────────

def test_skipped_lists_overlapping_and_unfinished():
    cal = _cal(120)
    Yu = np.zeros(120)
    Yu[100:] = np.nan                                               # 最後 20 天窗口還沒走完
    out = G.skipped([0, 5, 30, 60, 75, 105, 117], set(range(120)), 20, Yu, cal)
    assert out == [[cal[5], "d", cal[0]], [cal[75], "d", cal[60]], [cal[105], "i", None], [cal[117], "d", cal[105]]]
    assert G.skipped([3], {1, 2}, 20, Yu, cal) == []                # 輸入沒有值的日子不列


def test_research_rows_have_consistent_skip_lists():
    R = G.load_research()
    assert R and R["ver"] >= S.RES_VER
    rows = {r["id"]: r for r in R["rows"]}
    r = rows["tw:heat:B7:hot_out"]                                  # 盤查的例子：台灣 CPI 過熱結束 18 次＝9 次算進去＋8 次重疊＋1 次還沒走完
    occ = [o[0] for o in r["occ"]]
    sk = r.get("skip") or []
    assert len(occ) + len(sk) == 18 and sum(1 for k in sk if k[1] == "d") == 8
    assert all(k[2] in occ for k in sk if k[1] == "d")
    for x in R["rows"]:
        for k in x.get("skip") or []:
            assert k[1] in ("d", "i") and (k[2] is None) == (k[1] == "i")


# ── ⑤ 頁面的那一筆交易 ─────────────────────────────────────────────────────────

def test_since_text_spells_out_the_trade():
    """2026-10-23 起（docs/lab_ia_v5_plan.md 第 8 節第 5 條）動作寫日期、一行寫完：哪天收盤進場、持有到哪天。"""
    ev = {"since": "2026-10-05", "n": 11, "left": 9, "buy": "2026-10-06", "sell": "2026-11-03", "rem": 9}
    assert SP._since(ev, "2026-10-21") == "10/6 收盤進場・持有到 11/3"
    stt = {"since": "2026-10-15", "n": 5, "buy": "2026-10-22", "sell": "2027-11-01", "rem": 251}
    assert SP._since(stt, "2026-10-21") == "10/22 收盤進場・持有到 2027/11/1"
    assert SP._since({"since": "2026-10-05", "n": 11, "left": 9}, "2026-10-21") == "10/5 出現・還有 9 天"
    assert SP._since({"since": "2026-10-15", "n": 5}, "2026-10-21") == "10/15 起成立"
