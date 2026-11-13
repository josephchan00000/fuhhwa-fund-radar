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


def test_push_line_range_not_levels():
    pm = {"next": "2026-11-06", "est": 43000, "est_src": "夜盤收盤", "em": 900,
          "bands": [{"lo": 43200, "hi": 43300, "side": "up"}, {"lo": 42700, "hi": 42800, "side": "dn"}]}
    s = P.push_line(pm)
    assert s == "盤前 11/6（五）：預估 09:01 約 43,000（夜盤收盤）｜正常波動 ±900。"
    pm["v"] = {"typ": 207, "p80": 420}
    s = P.push_line(pm)
    assert s.startswith("盤前 11/6（五）：預估 09:01 約 43,000（平常差 ±207）") and "開盤八成在 42,580～43,420" in s
    assert "壓力" not in s and "支撐" not in s                  # 2026-11-12 起不推壓力支撐


Q2 = {"x": [0.25, 0.5, 1.0], "up": [0.6, 0.3, 0.1], "dn": [0.7, 0.4, 0.2]}


def test_touch_interpolates_from_one_at_open():
    assert P.touch(0, "up", Q2) == 1.0
    assert abs(P.touch(0.25, "up", Q2) - 0.6) < 1e-9
    assert abs(P.touch(0.375, "dn", Q2) - 0.55) < 1e-9
    assert abs(P.touch(0.125, "up", Q2) - 0.8) < 1e-9
    assert P.touch(3, "dn", Q2) == 0.2                     # 超過表的最遠一格＝最後一格
    assert P.touch(1, "up", {}) is None


def _heat(n=260):
    import datetime as dt
    days = [(dt.date(2025, 1, 1) + dt.timedelta(days=i)).isoformat() for i in range(n)]
    futi = {d: {"TX": {"外資": [100 + i, 50]}, "MTX": {"外資": [10, 10 + (i % 7)], "投信": [0, 0], "自營商": [5, 5]}} for i, d in enumerate(days)}
    mtxoi = {d: 1000 for d in days}
    margin = {d: [1e11 + (i % 5) * 1e8, 0, 0] for i, d in enumerate(days)}
    return days, {"futi": futi, "mtxoi": mtxoi, "margin": margin}


def test_chip_states_same_rules_as_research():
    days, heat = _heat()
    st = P.chip_states(heat, days[-1], 250)
    assert st["fx_fut_chg"][:2] == (days[-1], 1)          # 淨部位每天多 1 口
    assert st["retail"][0] == days[-1] and st["retail"][1] in (-1, 0, 1)
    assert st["margin"][0] == days[-1]
    few = P.chip_states(heat, days[10], 250)
    assert few["retail"][1] == 0 and few["margin"][1] == 0   # 不到 250 天不分三分位


def test_validated_marks_bands_cards_and_leans():
    from arm.lab import premktspec as S
    days, heat = _heat()
    pm = {"d": days[-1], "est": 43000, "em": 1000,
          "bands": [{"lo": 43500, "hi": 43500, "mid": 43500, "side": "up"}, {"lo": 42900, "hi": 43100, "mid": 43000, "side": "at"}],
          "sc": [{"entry": 42750, "stop": 42600, "target": 43500}]}
    res = {"ver": S.VER, "asof": "2026-11-04", "q1": {"n": 10, "use_night": True, "E1_open": {"med_em": 0.2, "p80_em": 0.5}},
           "q2": Q2, "q3": {"kinds": {"pivot_p": {"ok": False, "base": 0.45}}, "strength_ok": False},
           "q4": {"fx_fut_chg": {"oc": {"ok": True, "bull_mean_bp": -3.0, "bull_up": 0.49, "bull_n": 10, "bear_mean_bp": -11.0,
                                        "bear_up": 0.47, "bear_n": 9, "score_bp": 4.4}},
                  "sox": {"oc": {"ok": False}}}}
    v = P.validated(pm, res, heat)
    assert v["typ"] == 200 and v["p80"] == 500 and v["lv_ok"] == [] and v["strength_ok"] is False
    assert abs(pm["bands"][0]["touch"] - 0.3) < 1e-3 and pm["bands"][1]["touch"] == 1.0   # 往上 0.5 倍＝0.3；包住預估開盤＝1
    assert abs(pm["sc"][0]["hit"] - 0.7) < 1e-3          # 0.25 倍往下
    assert [x["k"] for x in v["leans"]] == ["fx_fut_chg"] and v["leans"][0]["lean"] == 1 and v["leans"][0]["mean"] == -3.0
    assert P.validated(dict(pm), {**res, "ver": S.VER - 1}, heat) is None   # 研究版本對不上就不標



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
    assert "盤前戰情" in h and "11/5（四）開盤前" in h and 'data-to="43321"' in h and "夜盤還沒抓到" in h
    assert "最近的成績" in h and "<td>42,666</td><td>−655</td>" in h          # 最近幾天照實列（2026-11-12 起是表格）
    assert 'class="pz-c ' not in h and "今天的買賣點" not in h                 # 四張買賣點卡已拿掉
    out = tmp_path / "x9op.html"
    txopage.build(out=out, data=None, pm=pm)
    assert "盤前戰情" in out.read_text(encoding="utf-8")
    assert "還沒準備好" in premkpage.block(None)


def test_page_levels_chart_and_recent_table():
    """2026-11-12（docs/lab_txo_plan.md 第 20 節）放「今天可能走多遠」與「最近的成績」；2026-11-13（第 22 節）使用者：
    「今天可能走多遠應該要跟上面合併」「本來那種點了之後的示意圖很好」→ 走多遠併進「今日點位」的價位圖（開盤上下 1 倍＝虛線），
    參考點位卡點了圖上畫出進場、停損、目標（11/5 版互動圖）。"""
    from arm.lab import premkpage
    pm = {"d": "2026-11-04", "next": "2026-11-05", "close": 42949, "hi": 43741, "lo": 41856, "est": 43000, "est_src": "夜盤收盤",
          "em": 1000, "night": {"c": 43404.0, "ref": 43203.0, "done": True}, "made": "2026-11-05 05:12",
          "bands": [{"lo": 43500, "hi": 43507, "mid": 43504, "n": 2, "side": "up", "src": [["整數關卡", 43500]], "touch": 0.42}],
          "sc": [{"k": "long", "name": "回測支撐做多", "entry": 43084, "stop": 42906, "target": 43500, "risk": 178, "reward": 416, "rr": 2.33}],
          "facts": [], "warn": [],
          "check": [{"d": "2026-11-04", "est": 43100, "open": 43200, "hi": 43800, "lo": 42600},
                    {"d": "2026-11-05", "est": 43321, "open": 42552, "hi": 42874, "lo": 41514}],
          "v": {"typ": 216, "p80": 434, "leans": [{"k": "retail", "t": "散戶小台", "d": "2026-11-04", "s": 1, "lean": -1, "txt": "t",
                                                    "mean": -13.4, "up": 0.43}], "chips_ok": ["retail"],
                "q2": {"x": [0.25, 0.5, 1.0, 1.5, 2.0], "up": [0.6, 0.3, 0.1, 0.03, 0.01], "dn": [0.7, 0.4, 0.2, 0.05, 0.02]}, "n1": 1, "n2": 1}}
    h = premkpage.block(pm)
    lv = h.split('id="pzl"', 1)[1].split("</section>", 1)[0]
    assert h.count("今天可能走多遠") == 1 and "今天可能走多遠" in lv                       # 不再是另一區，併在今日點位裡
    assert 'class="pz-svg"' in lv and "+1 倍・10%" in lv and "−1 倍・20%" in lv and "44,000" in lv and "42,000" in lv
    assert "開盤上下 1 倍正常波動（±1,000）" in lv and "往上 10%、往下 20%" in lv and "2 倍（45,000／41,000）只有 1%／2%" in lv
    assert "碰 30%" in lv                                                                  # 帶子中間 43,504 離預估 0.504 倍：0.3→0.1 內插
    assert '<button type="button" class="pz-c cu" data-s="0"' in lv and 'class="pz-s" data-s="0"' in lv   # 點卡片 → 圖上畫
    assert "進 43,084" in lv and "目標 43,500" in lv and "停損 42,906" in lv
    assert 'id="pzdet"' in lv and 'id="pzd"' in lv and '"sc":[{"name":"回測支撐做多"' in lv and '"bands":[{"lo":43500' in lv
    assert "平常差 <b>±216</b>" in h and "散戶小台　偏空" in h and "只能當傾向" in h
    rec = h.split('id="pzrec"', 1)[1]
    assert rec.index("11/5") < rec.index("11/4")                                         # 新的在上
    assert '<td class="pz-bad">−769</td>' in rec and "<td>+100</td>" in rec               # 超出八成範圍標紅
    assert "<td>42,874～41,514</td><td>1,360</td>" in rec
    assert "最近 2 天，估的開盤平均差 <b>434</b> 點，1 天超出" in rec


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


def test_levels_card_top_of_page():
    """2026-11-13 使用者：「我要一看就知道今天的壓力支撐建議點位」→ 最上面「今日點位」：壓力 1～3、開盤、支撐 1～3（各附來源與今天碰到的比例，
    以現在的預估開盤算；預估就在某一帶裡的那一帶不列），下面四個參考點位（點了價位圖畫出來），照實標「沒有驗證過」。"""
    from arm.lab import premkpage
    q2 = {"x": [0.25, 0.5, 1.0, 1.5, 2.0], "up": [0.6, 0.3, 0.1, 0.03, 0.01], "dn": [0.7, 0.4, 0.2, 0.05, 0.02]}
    bands = [{"lo": 44000, "hi": 44100, "mid": 44050, "side": "up", "src": [["11/18 到期最大痛點", 44100], ["樞紐壓力 1", 44097], ["整數關卡", 44000]]},
             {"lo": 44500, "hi": 44525, "mid": 44513, "side": "up", "src": [["昨天最高", 44525], ["整數關卡", 44500]]},
             {"lo": 43500, "hi": 43520, "mid": 43510, "side": "dn", "src": [["樞紐中心", 43520], ["整數關卡", 43500]]},
             {"lo": 42944, "hi": 43000, "mid": 42972, "side": "dn",
              "src": [["11/13 到期賣權未平倉最多（1,804 口）", 43000], ["昨天最低", 42944]]},
             {"lo": 43800, "hi": 43900, "mid": 43850, "side": "up", "src": [["成交量 70% 區上緣（換算）", 43800]]}]   # 預估在帶子裡：不列
    sc = [{"k": "long", "name": "回測支撐做多", "entry": 43520, "stop": 43389, "target": 44000,
           "opt": {"cp": "C", "k": 43500, "xd": "2026-11-18", "pe": 890.9}},
          {"k": "breakdown", "name": "跌破支撐追空", "entry": 43389, "stop": 43510, "target": 43109}]
    pm = {"d": "2026-11-12", "next": "2026-11-13", "close": 43091.87, "hi": 44525, "lo": 42944, "est": 43850, "est_src": "夜盤收盤",
          "em": 1000, "made": "2026-11-13 05:23", "bands": bands, "sc": sc, "facts": [], "warn": [], "check": [],
          "v": {"typ": 229, "p80": 463, "q2": q2, "n1": 1, "n2": 1, "lv_ok": []}}
    h = premkpage.block(pm)
    assert h.index('id="pzl"') < h.index('id="pz"')                                     # 放在最上面
    lv = h.split('id="pzl"', 1)[1].split("</section>", 1)[0]
    assert "今日點位　11/13（五）" in lv and "05:23 更新" in lv
    assert lv.index("壓力 2") < lv.index("壓力 1") < lv.index("開盤") < lv.index("支撐 1") < lv.index("支撐 2")
    rows = lv.split('class="pzl-rows"', 1)[1].split('class="pzl-ch"', 1)[0]
    assert "43,800～43,900" not in rows and "成交量密集區上緣" not in rows                # 預估開盤就在這一帶（列表不列，圖上照畫）
    assert "選擇權最大痛點・樞紐壓力・整數關卡" in lv and "賣權未平倉最多・昨天最低" in lv   # 來源用短名字
    assert "44,000～44,100" in lv and "<b>68%</b>" in lv                               # 帶子中間 44,050 離預估 0.2 倍：1→0.6 內插＝68%
    assert "十次有八次開在 43,387～44,313" in lv and "<b>+758</b>" in lv
    assert "<b>做多</b>回測支撐" in lv and "43,520<small>進場</small>" in lv and "43,389<small>跌破</small>" in lv
    assert "停損 43,389（−131）" in lv and "目標 44,000（+480）" in lv
    assert "今天碰到進場價 <b>60%</b>" in lv                                            # 以現在的預估重算：43,520 離 43,850 0.33 倍往下
    assert '"opt":{"cp":"C","k":43500,"xd":"2026-11-18","pe":890.9}' in lv                 # 選擇權一口的賺賠點了才寫（頁面 JS）
    assert "照實說" in lv and "參考點位沒有" in lv and "不是買賣建議" in lv
