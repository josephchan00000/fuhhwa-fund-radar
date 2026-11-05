"""盤前作戰圖（arm/lab/premkt.py）：樞紐點、共振帶、上下各幾帶、成交量分布、情境試算、指標、推播一行、夜盤解析。"""
from __future__ import annotations

import pytest

from arm.lab import futdata as F
from arm.lab import premkt as P


def test_pivots_formula():
    pv = P.pivots(110.0, 90.0, 100.0)
    assert pv["P"] == pytest.approx(100.0)
    assert pv["R1"] == pytest.approx(110.0) and pv["S1"] == pytest.approx(90.0)
    assert pv["R2"] == pytest.approx(120.0) and pv["S2"] == pytest.approx(80.0)


def _lv(px, kind, name="x"):
    return {"px": px, "kind": kind, "name": name}


def test_cluster_merges_within_threshold_and_counts_kinds():
    ref = 40000.0                       # 0.25% ＝ 100 點
    bands = P.cluster([_lv(40000, "round"), _lv(40080, "pivot"), _lv(40090, "pivot"), _lv(40150, "ma"), _lv(40300, "opt")], ref)
    assert [(b["lo"], b["hi"], b["n"]) for b in bands] == [(40000, 40090, 2), (40150, 40150, 1), (40300, 40300, 1)]
    assert bands[0]["kinds"] == ["pivot", "round"]


def test_pick_bands_nearest_each_side_and_far_cut():
    bands = P.cluster([_lv(x, "pivot") for x in (39000, 39500, 39800, 39900, 40200, 40400, 40600, 40800, 43000)], 40000)
    got = P.pick_bands(bands, 40000.0, 500.0)
    up = [b["lo"] for b in got if b["side"] == "up"]
    dn = [b["hi"] for b in got if b["side"] == "dn"]
    assert up == [40600, 40400, 40200]            # 由高到低排；只留最近 3 帶（40800 是第 4 近）
    assert dn == [39900, 39500, 39000]            # 39800、39900 相差 100 點（0.25%）併成一帶；39000 剛好 2 倍正常波動
    assert all(b["lo"] != 43000 for b in got)     # 超過 2 倍正常波動不列


def test_vprofile_poc_and_area():
    ticks = [(0, 100, 2, False)] * 10 + [(0, 110, 2, False)] * 3 + [(0, 90, 2, False)] * 2 + [(0, 150, 2, False)]
    vp = P.vprofile(ticks, step=10, area=0.7)
    assert vp["poc"] == 105                       # 100～110 那一格的中間
    assert vp["val"] <= 100 and vp["vah"] >= 110 and vp["lots"] == 16


def test_scenarios_targets_beyond_entry_and_rr():
    bands = P.pick_bands(P.cluster([_lv(x, "pivot") for x in (40400, 40420, 40700, 39600, 39650, 39300)], 40000), 40000.0, 500.0)
    sc = {s["k"]: s for s in P.scenarios(bands, 40000.0, 500.0, None, 40000.0)}
    lg, sh, br, bd = sc["long"], sc["short"], sc["break"], sc["breakdown"]
    assert lg["entry"] == 39650 and lg["stop"] == 39550 and lg["target"] == 40400
    assert sh["entry"] == 40400 and sh["stop"] == 40470 and sh["target"] == 39650
    assert br["entry"] == 40470 and br["target"] == 40700 and br["target"] > br["entry"] > br["stop"]
    assert bd["entry"] == 39550 and bd["target"] == 39300 and bd["target"] < bd["entry"] < bd["stop"]
    assert lg["rr"] == pytest.approx((40400 - 39650) / 100, abs=0.01)
    assert lg["mtx"]["loss"] == round(100 * 50 + P.fut_cost(39650) + P.fut_cost(39550))
    assert lg["opt"] is None                      # 沒有作戰表就不估選擇權


def test_scenario_option_estimate_uses_calc():
    bands = P.pick_bands(P.cluster([_lv(40400, "pivot"), _lv(39600, "pivot")], 40000), 40000.0, 500.0)
    calc = {"atm_iv": 0.2, "exps": [{"code": "X", "date": "2026-01-10", "n": 1, "f": 40000, "rows": []},
                                    {"code": "Y", "date": "2026-01-14", "n": 4, "f": 40010, "rows": [[39600, 300, 0.22, 250, 0.21]]}]}
    lg = next(s for s in P.scenarios(bands, 40000.0, 500.0, calc, 40000.0) if s["k"] == "long")
    o = lg["opt"]
    assert o["exp"] == "Y" and o["k"] == 39600 and o["cp"] == "C" and o["iv"] == 0.22   # 跳過只剩 1 天的那批
    assert o["pt"] > o["pe"] > o["ps"] > 0 and o["loss"] > 0 and o["gain"] > 0


def test_rsi_kd_macd_ranges():
    up = [100 + i for i in range(80)]
    assert P.rsi(up) == pytest.approx(100.0)
    zig = [100 + (i % 2) for i in range(80)]
    assert 40 < P.rsi(zig) < 60
    k, d = P.kd([(x + 1, x - 1, x) for x in up])
    assert k > 80 and d > 80
    h, h0 = P.macd(up)
    assert h is not None and h0 is not None
    assert P.rsi([1, 2]) is None and P.kd([(1, 0, 1)] * 5) is None and P.macd(up[:30]) is None


def test_push_line_nearest_bands():
    pm = {"next": "2026-11-06", "est": 43000, "est_src": "夜盤收盤", "em": 900,
          "bands": [{"lo": 44000, "hi": 44000, "side": "up"}, {"lo": 43200, "hi": 43300, "side": "up"},
                    {"lo": 42700, "hi": 42800, "side": "dn"}, {"lo": 42000, "hi": 42000, "side": "dn"}]}
    s = P.push_line(pm)
    assert s.startswith("盤前 11/6（五）：預估開 43,000（夜盤收盤）")
    assert "壓力 43,200～43,300" in s and "支撐 42,700～42,800" in s and "正常波動 ±900" in s


def test_night_rec_picks_near_month_and_session_date():
    q = [{"SymbolID": "TXF-P", "CLastPrice": "", "CDate": "20261104"},
         {"SymbolID": "TXFK6-M", "CLastPrice": "43404.00", "COpenPrice": "43430.00", "CHighPrice": "44274.00",
          "CLowPrice": "43141.00", "CRefPrice": "43203.00", "CTime": "045953", "CDate": "20261104", "CTotalVolume": "66754",
          "Status": "TC"},
         {"SymbolID": "TXFL6-M", "CLastPrice": "43434.00", "CDate": "20261104"}]
    d, r = F.night_rec(q)
    assert d == "2026-11-04" and r["sym"] == "TXFK6-M" and r["c"] == 43404.0 and r["done"] and r["t"] == "04:59:53"
    assert F.night_rec([{"SymbolID": "TXFK6-M", "CLastPrice": ""}]) is None


def test_valog_pm_line_only_for_same_data_day(tmp_path, monkeypatch):
    import json

    from arm.lab import valog
    f = tmp_path / "premkt.json"
    f.write_text(json.dumps({"d": "2026-11-04", "push": "盤前 11/5（四）：預估開 43,321。"}), encoding="utf-8")
    monkeypatch.setattr(P, "OUT", f)
    assert valog.pm_line("2026-11-04") == "盤前 11/5（四）：預估開 43,321。"
    assert valog.pm_line("2026-11-05") is None
    lines = valog.push_lines({"todo": {"d": "2026-11-05", "items": []}, "pm": "盤前 X"})
    assert lines[1] == "盤前 X"


def test_page_block_renders_and_fits(tmp_path):
    from arm.lab import premkpage, txopage
    pm = {"d": "2026-11-04", "next": "2026-11-05", "close": 42948.91, "hi": 43741.5, "lo": 41855.8, "prev": 43307.5,
          "est": 43321, "est_src": "夜盤收盤", "em": 942, "night": {"c": 43404.0, "done": True}, "made": "2026-11-05 05:12",
          "bands": [{"lo": 43500, "hi": 43507, "mid": 43504, "n": 2, "side": "up", "src": [["整數關卡", 43500]]},
                    {"lo": 43000, "hi": 43084, "mid": 43042, "n": 3, "side": "dn", "src": [["布林下緣", 43084]]}],
          "sc": [], "facts": [{"k": "x", "t": "外資台指期", "v": "淨空 1 口", "d": "2026-11-04"}], "warn": ["夜盤還沒抓到"],
          "check": [{"d": "2026-11-05", "est": 43321, "open": 42666}]}
    h = premkpage.block(pm)
    assert "盤前作戰圖 11/5（四）" in h and "43,321" in h and "夜盤還沒抓到" in h and "實際開 42,666（差 −655）" in h
    assert h.index("43,500～43,507") < h.index("預估開盤</span>") < h.index("43,000～43,084")   # 壓力在上、預估開盤、支撐在下
    out = tmp_path / "x9op.html"
    txopage.build(out=out, data=None, pm=pm)
    assert "盤前作戰圖" in out.read_text(encoding="utf-8")
    assert "盤前作戰圖還沒準備好" in premkpage.block(None)


def test_write_keeps_file_when_only_timestamp_changes(tmp_path, monkeypatch):
    import json
    out = tmp_path / "pm.json"
    seq = iter([{"d": "a", "made": "1", "x": 1}, {"d": "a", "made": "2", "x": 1}, {"d": "a", "made": "3", "x": 2}])
    monkeypatch.setattr(P, "build", lambda asof=None: next(seq))
    P.write(out)
    b1 = out.read_bytes()
    P.write(out)
    assert out.read_bytes() == b1                 # 只有時間戳不同 → 不動檔
    P.write(out)
    assert json.loads(out.read_text())["x"] == 2


def test_parse_futday_keeps_single_month_rows_and_sessions():
    from arm.lab import txodata as T
    txt = ("交易日期,契約,到期月份(週別),開盤價,最高價,最低價,收盤價,漲跌價,漲跌%,成交量,結算價,未沖銷契約數,最後最佳買價,"
           "最後最佳賣價,歷史最高價,歷史最低價,是否因訊息面暫停交易,交易時段,價差對單式委託成交量\n"
           "2026/11/04,TX,202611  ,43450,43774,42050,43204,-149,-0.34%,113674,43203,122629,43195,43205,50440,42050,,一般,,\n"
           "2026/11/05,TX,202611  ,43430,44274,43141,43404,201,0.47%,66939,-,-,43383,43400,50440,42050,,盤後,,\n"
           "2026/11/04,TX,202611/202612    ,85,87,71,76,-,-,115,-,-,74,76,170,71,,一般,494,\n"
           "2026/11/04,MTX,202611  ,1,1,1,1,-,-,1,-,-,1,1,1,1,,一般,,\n")
    rows = T.parse_futday(txt)
    assert rows == [["2026-11-04", "202611", "D", 43450, 43774, 42050, 43204, 113674, 43203, 122629],
                    ["2026-11-05", "202611", "N", 43430, 44274, 43141, 43404, 66939, None, None]]
