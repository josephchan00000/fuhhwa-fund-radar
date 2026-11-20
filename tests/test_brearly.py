"""台股廣度往前補（arm/lab/heatdata.EarlyPanel／early_counts／splice／splice_check；規格 brearlyspec VER 1）。"""
from arm.lab import brearlyspec as S
from arm.lab import heatdata as HD


def _doc(days, codes, shares=1e9):
    """每檔每天漲 1%（第 3 天除息：收盤 99、參考價 98＝漲跌價差 +1，實際報酬 +1.02%）。"""
    c, g = {}, {}
    for k, code in enumerate(codes):
        px, cs, gs = 100.0 + k, [], []
        for i, _ in enumerate(days):
            if i == 0:
                cs.append(px); gs.append(0.0); continue
            if i == 3:
                ref = px * 0.98                                   # 除息 2%
                x = round(ref * 1.0102, 4)
                cs.append(x); gs.append(round(x - ref, 4)); px = x; continue
            x = round(px * 1.01, 4)
            cs.append(x); gs.append(round(x - px, 4)); px = x
        c[code], g[code] = cs, gs
    me = {d: {code: int(shares) for code in codes} for d in days if d.endswith("-28")}
    return {"t": list(days), "c": c, "g": g, "sh": me, "miss": [], "err": {}}


def test_adjusted_series_uses_reference_price():
    days = [f"2004-02-{d:02d}" for d in range(11, 29)]
    P = HD.EarlyPanel([_doc(days, ["2330"])])
    a = P.s["2330"]["c"]
    assert abs(a[3] / a[2] - 1.0102) < 1e-6                         # 除息那天的報酬＝收盤 ÷ 參考價，不是 −1%
    assert abs(a[4] / a[3] - 1.01) < 1e-6
    assert P.cap["2330"][0] is None and P.cap["2330"][days.index("2004-02-28")] is not None    # 第一個月底以前沒有市值


def test_counts_splice_and_check():
    days = [f"2004-{m:02d}-{d:02d}" for m in range(2, 13) for d in range(1, 29)]
    codes = [f"{1100 + k}" for k in range(150)]
    early = HD.early_counts(HD.EarlyPanel([_doc(days, codes, shares=1e10)]))
    d0 = min(early)
    assert early[d0][0] + early[d0][1] > 0 and all(v[1] == 0 for v in early.values() if v[0] + v[1] > 0)   # 每天都漲＝沒有下跌
    now = {"2013-12-30": [1, 2, 3, 4, 5, 6, 7], "2014-01-02": [9, 9, 9, 9, 9, 9, 9]}
    sp = HD.splice({**early, "2013-12-30": [0] * 7, "2014-01-02": [0] * 7}, now)
    assert sp["2013-12-30"] == [0] * 7 and sp["2014-01-02"] == [9] * 7 and d0 in sp
    chk = HD.splice_check({}, {})
    assert chk["ok"] is False and chk["T5"]["n"] == 0


def test_check_passes_when_both_sides_agree():
    cal = [f"2013-{m:02d}-{d:02d}" for m in range(1, 13) for d in range(1, 29)]
    rows = {d: [60 + (i % 7), 40, 300, 500, 20, 5, 450] for i, d in enumerate(cal)}
    chk = HD.splice_check(rows, dict(rows))
    assert chk["ok"] and chk["T5"]["mean"] == 0 and chk["T6"]["maxabs"] == 0
    off = {d: [v[0] + 30, v[1]] + v[2:] for d, v in rows.items()}
    assert HD.splice_check(off, rows)["ok"] is False and S.CHECK_MAX == 3.0
