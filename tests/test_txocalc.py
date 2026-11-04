"""選擇權作戰表（arm/lab/txocalc.py；docs/lab_txo_plan.md 第 17 節）：公式、反推波動率、挑到期與履約價。"""
from datetime import date

from arm.lab import txocalc as C
from arm.lab import txodata as T


def test_bs_parity_and_iv_roundtrip():
    s, k, t, v = 43000, 42500, 5 / 252, 0.3
    c, p = C.bs("C", s, k, t, v), C.bs("P", s, k, t, v)
    assert abs((c - p) - (s - k)) < 1e-6                      # r＝0 的買賣權平價
    assert abs(C.iv("C", c, s, k, t) - v) < 1e-3 and abs(C.iv("P", p, s, k, t) - v) < 1e-3
    assert C.bs("C", s, k, 0, v) == 500 and C.bs("P", s, k, 0, v) == 0
    assert C.iv("P", 0.0, s, k, t) is None and C.iv("C", 100, s, k, t) is None   # 低於內含價值


def _row(d, exp, k, cp, s, xd, oi=5):
    r = [None] * len(T.COLS)
    i = {c: n for n, c in enumerate(T.COLS)}
    r[i["d"]], r[i["exp"]], r[i["k"]], r[i["cp"]], r[i["s"]], r[i["c"]], r[i["oi"]], r[i["xd"]] = d, exp, k, cp, s, s, oi, xd
    return r


def test_build_picks_future_expiries_and_atm_window():
    asof = date(2026, 11, 4)
    rows = [_row("2026-11-04", "202611W1", 43000, "C", 5, "2026-11-04")]          # 今天到期 → 不列
    for k in range(42000, 44050, 50):
        for cp in "CP":
            rows.append(_row("2026-11-04", "202611F1", k, cp, C.bs(cp, 43000, k, 2 / 252, 0.3), "2026-11-06"))
    rows.append(_row("2026-11-03", "202611F1", 43000, "C", 999, "2026-11-06"))     # 別天 → 不用
    doc = C.build(rows, 43000.0, asof)
    assert doc["next"] == "2026-11-05" and doc["atm"] == 43000
    assert [e["code"] for e in doc["exps"]] == ["202611F1"]
    e = doc["exps"][0]
    assert e["n"] == 2 and e["tomorrow"] is False
    ks = [r[0] for r in e["rows"]]
    assert ks[0] == 43000 - 10 * 50 and ks[-1] == 43000 + 10 * 50 and len(ks) == 21
    assert abs(doc["atm_iv"] - 0.3) < 2e-3 and doc["em"] > 0
    assert doc["caps"] == {"O1": 0.02, "O2": 0.03, "O3": 0.05}


def test_trading_days_skip_weekend():
    assert C.trading_days(date(2026, 11, 6), date(2026, 11, 9)) == 1              # 週五 → 週一
    assert C.next_trading(date(2026, 11, 6)) == date(2026, 11, 9)
