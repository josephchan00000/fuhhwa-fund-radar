"""景氣溫度頁第五版：對照圖資料 dashboard/x9mh.json（arm/lab/heatchart.py；規劃文件第 14.14 節第 3 點）。"""
import json
from datetime import date, timedelta

from arm.lab import heat as H
from arm.lab import heatchart as HC
from arm.lab import heatpos as P
from arm.lab import heatspec as S


def _days(a: date, n: int):
    d, out = a, []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _B(n=700):
    cal = _days(date(2023, 1, 2), n)
    px = [10000.0 * (1.0005 ** i) for i in range(n)]
    heat = {k: [None] * 50 + [float(i % 100) for i in range(n - 50)] for k in S.KEYS}
    raw = {k: [None] * 50 + [1234.5678 + i for i in range(n - 50)] for k in S.KEYS}
    comp = {d: [None] * 100 + [55.55] * (n - 100) for d in S.DIMS}
    yms = [f"{y}-{m:02d}" for y in range(2021, 2026) for m in range(1, 13)]
    mraw = {k: {ym: float((j * 7) % 11) for j, ym in enumerate(yms)} for k in S.DERIV if S.FREQ_OF[k] == "m"}
    nat = {k: {d: 100.0 + (i * 13) % 17 for i, d in enumerate(cal)} for k in S.DERIV if S.FREQ_OF[k] != "m"}
    return {"cal": cal, "px": px, "heat": heat, "raw": raw, "comp": comp, "mraw": mraw, "nat": nat}


def test_number_formats_and_trim():
    assert HC.sig(1234.5678) == 1235 and HC.sig(0.012345) == 0.01235 and HC.sig(-94077.75) == -94080 and HC.sig(0) == 0
    assert HC.sig(None) is None and HC.sig(float("nan")) is None
    assert HC.r1(55.55) == 55.5 or HC.r1(55.55) == 55.6
    assert HC.r1(80.0) == 80 and isinstance(HC.r1(80.0), int)
    assert HC.trim([None, None, 1, None, 2]) == {"o": 2, "v": [1, None, 2]}
    assert HC.trim([None]) == {"o": 1, "v": []}


def test_build_data_weekly_daily_and_forward_returns():
    B = _B()
    we = P.week_ends(B["cal"])
    R = {"ver": S.VER, "wk": [B["cal"][i] for i in we], "rel": {"B1": {"roll": [[0, 0.1], [3, -0.2], [10 ** 6, 0.3]]}},
         "deriv": {"B5": {"first": "2023-01-02"}}}
    D = HC.build_data(B, R)
    assert D["w"]["d"] == [B["cal"][i] for i in we] and len(D["d"]["d"]) == S.CH_DAILY
    h = 60
    i = we[10]
    assert D["w"]["fw"][str(h)][10] == round(100 * H.fwd(B["px"], i, h)[0], 2)   # t＋1 收盤起算
    assert D["w"]["fw"][str(h)][-1] is None
    assert D["s"]["fund"]["h"]["o"] > 0 and set(D["s"]["fund"]) == {"h", "hd"}
    assert set(D["s"]["C1"]) == {"h", "r", "hd", "rd"} and D["s"]["C1"]["r"]["v"][0] == HC.sig(B["raw"]["C1"][we[D["s"]["C1"]["r"]["o"]]])
    assert D["an"]["B1"]["roll"] == [[R["wk"][0], 0.1], [R["wk"][3], -0.2]]          # 週序號換成日期；超出範圍的丟掉
    assert D["dv"] == R["deriv"]
    acc = HC.acc_lines(B)                                                             # 第六版：三組「幾成在加速」
    for g in S.M6_GROUPS:
        e = D["s"][f"A_{g}"]
        assert set(e) == {"h", "hd"} and e["h"]["v"] == [HC.r1(acc[f"A_{g}"][i]) for i in we][e["h"]["o"]:]
        assert any(v is not None for v in e["h"]["v"]) and all(0 <= v <= 100 for v in e["h"]["v"] if v is not None)
    s1, s2 = HC.dumps(D), HC.dumps(HC.build_data(B, R))
    assert s1 == s2 and json.loads(s1)["ver"] == S.VER                                # 同資料同位元組


def test_old_research_is_ignored():
    B = _B()
    D = HC.build_data(B, {"ver": 4, "rel": {"B1": {"roll": []}}})
    assert D["an"] == {} and D["dv"] == {} and D["m6"] == {}
