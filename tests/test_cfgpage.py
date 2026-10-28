"""配置頁（arm/lab/cfgpage.py；docs/lab_ia_v5_plan.md 第 18 節）：台股、美股各一張「時程與水位」卡（四格 → 水位長條 → 警訊
→ 規則 → 成績 → 細節 → 下一個交易日 → 時間軸）、持股細節表（比重合計 100%）、策略一行；策略頁一張表；
x9.html 的分頁、兩次建頁（finish）、用字。"""
import re

import pytest

from arm.lab import board as BD
from arm.lab import cfgpage as CF
from arm.lab import core as CO
from arm.lab import corepage as CPG
from arm.lab import corespec as S
from arm.lab import page
from arm.lab import sigpage as SG
from test_corepage import BANNED, JARGON, NOT_PLAIN, STK, _now, _text, _us


@pytest.fixture(scope="module")
def R():
    R = CO.load()
    assert R is not None, "研究檔 data/lab/core_research.json 要先跑 scripts/run_core.py"
    return R


@pytest.fixture(scope="module")
def QMX():
    from arm.lab import ussxqm as QM
    R = QM.load()
    assert R is not None, "研究檔 data/lab/ussx_qm.json 要先跑 scripts/run_ussx.py --qm"
    return {"R": R, "L": QM.load_live(), "W": None}


def _data():
    cal = [dict(e) for e in STK["ev"]]
    book = [{"k": s["k"], "name": s["name"], "tier": "good", "how": "規則一句", "unit": "次",
             "exp": {"n": 30, "avg": 2.5, "win": 61, "mk": 0.8, "lo": -12.0}, "all": {}} for s in STK["st"]]
    return {"adv": {"last": "2026-10-22", "cal": cal, "book": book,
                    "opp": {"cards": [{"k": "v3l", "name": "財報驚喜（大型股）", "hold": "60 個交易日",
                                       "held": [], "buy": [], "next": None, "adj": []}]}},
            "mac": {"mks": ["tw", "spx"], "m": {"tw": {"cal": [], "cards": [], "book": []}, "spx": {"cal": [], "cards": [], "book": []}}}}


def _bundle(R, qm=None, tw=None, spx=None):
    return {"R": R, "now": {"tw": tw if tw is not None else _now(), "spx": spx if spx is not None else _us()},
            "stk": STK, "fw": {}, "qm": qm}


def _ws(h: str) -> list[float]:
    return [float(x) for x in re.findall(r'<td class="w">(?:約 )?([0-9.]+)%</td>', h)]


def _ems(h: str) -> list[float]:
    return [float(x) for x in re.findall(r"<em>([0-9.]+)%</em>", h)]


def test_tw_v2_money_block(R):
    """配置頁 v2（docs/lab_cfg_v2_plan.md 第 3.1 節；2026-10-24 使用者：「持股只剩40%是為什麼…配置比例在手機版也跑版 字都沒出來」）：
    現在的錢＝實際的錢（長抱＋每條策略手上的股票＋現金），每一段一列寫名字和比例（不再把字藏起來），一句話講現金為什麼多。"""
    X = CF.tw_parts(_data(), _bundle(R))
    assert set(X) >= {"card", "hold", "sched", "warn", "perf", "boom", "pos", "bx", "tl", "d", "nx"}
    c = X["card"]
    t = _text(c)
    assert "現在的錢" in t and "63%" in t and "37%" in t                          # 股票＝20%＋新飆股 2 檔 30%＋財報驚喜 1 檔 13.3%
    lg = re.findall(r'<li><u class="(c\d|cx)"></u><span>([^<]+)</span><em>([0-9.]+)%</em></li>', c)
    assert [(k, n) for k, n, _ in lg] == [("c1", "0050（一直抱著）"), ("c2", "新飆股 2 檔"), ("c3", "財報驚喜 1 檔"), ("cx", "現金")]
    assert abs(sum(float(w) for _, _, w in lg) - 100) < 0.2                       # 圖例合計 100%
    assert len(re.findall(r'<i class="c\d"', c)) == 3 and '<i class="cx"' in c   # 長條：三段股票＋現金
    assert "新飆股 11/9（一）開盤買 1 檔" in t and "臺灣50 卡位這一期沒有要買的" in t
    assert "11/9（一）開盤買進之後股票約 <b>68%</b>" in c                           # 排定的買進之後
    for w in ("待買進", "持有中", "要做的事", "時程與水位", "機動 80%：新飆股 40%"):   # 舊版的四格、計畫比例長條都拿掉了
        assert w not in t, w
    assert "font-size:0" not in CF.CSS                                            # 手機版不再把長條上的字藏起來


def test_tw_v2_hold_grouped_and_clickable(R):
    """持股依策略分組、每一檔可以點（data-co：台股開個股卡、籌碼雷達範圍外的開公司卡）、現金只有一列。"""
    X = CF.tw_parts(_data(), _bundle(R))
    h = X["hold"]
    t = _text(h)
    assert h.count('class="cfgr"') == 5 and h.count('class="cfcash"') == 1        # 長抱、新飆股、三條策略；現金只在最下面一列
    assert t.count("現金") == 1
    rows = re.findall(r'<a class="cfrow( todo)?" data-c="(\d+)" data-co="\2">', h)
    assert rows == [("", "3017"), ("", "2383"), (" todo", "2368"), ("", "2330")]   # 新飆股兩檔＋明天要買的一檔、財報驚喜一檔
    held = [float(x) for x in re.findall(r'<span class="w">([0-9.]+)%</span>', h)]
    cash = float(re.search(r'class="cfcash">.*?<em>([0-9.]+)%</em>', h).group(1))
    assert abs(20 + sum(held) + cash - 100) < 0.3, (held, cash)                    # 長抱＋持有中＋現金＝100%（待買進寫「約」，不算進去）
    assert "11/2 買 1,000，現在 1,100・2/3 開盤賣（2/2 收盤滿 60 個交易日）" in t
    assert "11/9（一）開盤買（11/6 的名單）" in t and "強度 95" in t
    assert "8/17 買・11/12 收盤賣" in t and "+3.1%" in t                           # 財報驚喜：advice 的 now_r 是百分比
    assert t.count("這一期沒有部位") == 2 and "分到 13.3%（買滿）" in t
    assert "第一份名單" not in t                                                   # 新飆股已經有名單
    pos = X["pos"]
    assert {k: [q["k"] for q in v] for k, v in pos.items()} == {"3017": ["boom"], "2383": ["boom"], "2368": ["boom"], "2330": ["v3l"]}
    assert pos["2368"][0]["h"] == 0 and pos["3017"][0]["h"] == 1 and abs(pos["3017"][0]["w"] - 0.2) < 1e-6


def test_tw_v2_sched_only_configured(R):
    """接下來照規則的買賣：依日期、只列配置裡的策略（2026-10-24 使用者決定：觀察中策略的訊號不放配置頁）；股票名可以點。"""
    d = _data()
    d["adv"]["cal"].append({"d": "2026-10-27", "at": "開盤", "act": "買進", "k": "s1", "sname": "共識加碼", "items": [{"c": "3406", "n": "玉晶光"}]})
    X = CF.tw_parts(d, _bundle(R))
    s = X["sched"]
    t = _text(s)
    assert "玉晶光" not in t and "共識加碼" not in t and "觀察中" not in t
    dates = re.findall(r'<div class="cfevd"><b>([0-9/]+)</b>', s)
    assert dates == ["11/9", "11/12", "11/13", "11/16", "11/17", "11/23"], dates   # 依日期；11/16＝新飆股看完名單、有空位的下一個交易日
    assert '新飆股：<a data-c="2368" data-co="2368">金像電</a>' in s and '財報驚喜：<a data-c="2330" data-co="2330">台積電</a>' in s
    assert "新飆股：這一週的名單" in t and "財報驚喜：下一批（11/16 收盤選）" in t
    assert 'data-cfo' not in s and 'class="cftlw"' in s                           # 時間軸收在「看時間軸」裡、沒有「＋觀察中」


def test_tw_v2_warn_thresholds_and_due(R):
    X = CF.tw_parts(_data(), _bundle(R))
    t = _text(X["warn"])
    assert "1／3 成立" in t and "80 分以上算" in t and "跌破才算" in t and "收盤比年線" in t
    assert "0050 那 20% 一直抱著" in t
    X = CF.tw_parts(_data(), _bundle(R, tw=_now(n_lit_extra=True, held=True)))   # 兩個警訊、還拿著 → 下一個交易日收盤換現金
    assert "收盤：把機動 80% 賣掉換成現金" in _text(X["warn"]) and "2／3 成立" in _text(X["warn"])
    assert "機動 80% 換成現金" in _text(X["sched"])
    X = CF.tw_parts(_data(), _bundle(R, tw=_now(held=False)))                    # 警訊解除、機動在現金 → 買回；現在只有長抱是股票
    assert "把機動 80% 買回來" in _text(X["card"]) and "20%" in _text(X["card"]) and "80%" in _text(X["card"])
    assert "警訊：機動 80% 現在放現金" in _text(X["hold"])


def _yhref(c):
    return f'href="https://finance.yahoo.com/quote/{c}" target="_blank" rel="noopener"'


def _uhref(c):
    """美股的股票點了開美股個股卡（配置頁 v2 第 4 步；uscardpage）。"""
    return f'href="#us={c}" data-us="{c}"'


def _qm(QMX, hold, buy=(), sell=(), idle=0.0, d="2026-10-23", nxt="2026-10-26", lst=None, names=None, W=None):
    """假的美股強勢品質股紀錄（每週紀錄 L＋每天的 50 日線檢查 W）。"""
    return {"R": QMX["R"], "W": W, "L": {"names": names or {}, "now": {
        "d": d, "wk": d, "wk_done": True, "next": nxt, "idle": idle, "n_list": len(lst or []), "hold": hold,
        "buy": list(buy), "sell": list(sell), "list": lst or []}}}


def _h(c, w, ent="2026-08-03", r=0.1, px=100.0, ma=95.0, sell=False):
    return {"c": c, "ent": ent, "epx": px / (1 + r), "px": px, "ma": ma, "r": r, "w": w, "sell": sell, "above": True}


def test_us_v2_sections_with_real_data(R, QMX):
    """配置頁 v2 第 2 步（docs/lab_cfg_v2_plan.md 第 3.2 節）：美股同樣五段——現在的錢、持股（每一檔整列點了開美股個股卡，
    第 4 步）、接下來照規則的買賣、警訊、過去照做。比重合計 100%。"""
    X = CF.us_parts(_data(), _bundle(R, qm=QMX))
    assert set(X) >= {"card", "hold", "sched", "warn", "perf", "d", "nx", "tl"}
    c, h, s = X["card"], X["hold"], X["sched"]
    assert "現在的錢" in _text(c) and "長抱" not in _text(c + h) and S.core_of("spx") == 0   # VER 4：美股不留長抱
    lg = [float(w) for w in re.findall(r"<em>([0-9.]+)%</em></li>", c)]
    assert lg and abs(sum(lg) - 100) < 0.2, lg
    if CPG.qm_on("spx", QMX):
        n = CPG._qm_now(QMX)
        for x in n.get("hold") or []:
            assert f'<a class="cfrow" {_uhref(x["c"])}>' in h, x["c"]                      # 整列點了開美股個股卡
        held = [float(x) for x in re.findall(r'<span class="w">([0-9.]+)%</span>', h)]
        cash = float(re.search(r'class="cfcash">.*?<em>([0-9.]+)%</em>', h).group(1))
        assert abs(sum(held) + cash - 100) < 0.3, (held, cash)                          # 持有中＋現金＝100%（待買進寫「約」，不算）
        assert X["tl"]["qm"] and X["tl"]["qm"]["k"] == "qm"
        assert "拿著的股票收盤跌破 50 日線，就在下一個交易日開盤賣" in _text(s) and "強勢品質股：這一週的名單" in _text(s)
    t = _text(X["warn"])
    assert "0／4 成立" in t or "／4 成立" in t
    assert "總經策略" in t and "全部空手才算" in t and "總經策略全部空手" not in t.split("兩個以上")[0]   # 名稱短一點，不折成兩行
    p = _text(X["perf"])
    assert "過去照做" in p and "100 萬變" in p
    if CPG.qm_on("ndx", QMX):
        assert "警訊改看那斯達克 100：同一套規則 100 萬變" in p and "配置照 S&amp;P 500" in X["perf"]
    for w in ("時程與水位", "持股細節", "待買進 0", "要做的事"):                                  # 舊版的四格、表格拿掉了
        assert w not in _text(c + h + s), w


def test_us_v2_rows_open_card_and_explain(R, QMX, monkeypatch):
    """2026-10-24 使用者：「你要我持有的股票我根本沒辦法點進去看」——美股每一列＝公司名＋代號（點了開美股個股卡）、
    本業、哪天買・離 50 日線多遠、為什麼（這一週名單的第幾名）；名單前幾名（手上沒有的）也可以點。"""
    from arm import fund_intro as FI
    monkeypatch.setattr(CPG, "_US_INTRO", {"INSW": "美國 International Seaways，油輪航運公司；船隊…",
                                           "VLO": "美國瓦萊羅能源（Valero Energy），大型煉油商；…"})
    monkeypatch.setattr(CPG, "qm_on", lambda mk, q: True)
    lst = [{"c": c, "rs": 99.0 - i} for i, c in enumerate(["VLO", "CDNA", "PAYC", "QLYS", "HALO", "NTAP", "CON", "CAI"])]
    qm = _qm(QMX, [_h("INSW", 0.4, ent="2026-07-20", r=0.29, px=108.4, ma=105.0), _h("VLO", 0.35, ent="2026-08-31", r=0.18, px=426.0, ma=391.0)],
             idle=0.25, d="2026-10-22", nxt="2026-10-23", lst=lst, names={"CDNA": "CareDx, Inc."})
    X = CF.us_parts(_data(), _bundle(R, qm=qm))
    c, h, s = X["card"], X["hold"], X["sched"]
    lg = re.findall(r'<li><u class="(c\d|cx)"></u><span>([^<]+)</span><em>([0-9.]+)%</em></li>', c)
    assert lg == [("c1", "強勢品質股 2 檔", "75"), ("cx", "現金", "25")]
    assert "現金 25% 是空的位子，10/23（五）收盤看下一份名單，有空位就在下一個交易日開盤買。" in _text(c)
    assert f'<a class="cfrow" {_uhref("INSW")}><span class="cfra"><b>International Seaways</b><span class="cd">INSW</span>' in h
    assert '<span class="cfri">油輪航運公司</span><span class="cfrb">7/20 買（回測）・比 50 日線高 3.2%</span>' in h
    assert "為什麼：10/22 收盤的名單第 1 名，漲勢勝過 99% 的美股" in _text(h)       # VLO 在名單上；INSW 不在、不寫為什麼
    assert _text(h).count("為什麼：") == 1
    assert "分到 100%，現在用到 75%。" in _text(h) and "最多 8 檔、每檔約 12.5%" in _text(h)
    assert re.search(r'class="cfcash"><b>現金</b><span>空的位子</span><em>25%</em>', h)
    top, cand = h.split('class="cfh3"')
    assert "有空位時依序買：名單前 5 名（手上沒有的）" in _text(cand)
    got = re.findall(r'<a href="#us=(\w+)" data-us="\1"', cand)
    assert got == ["CDNA", "PAYC", "QLYS", "HALO", "NTAP"] and FI.US_QM_SHOW == 5        # VLO 手上有，不列；只列前 5
    assert 'CareDx, Inc. <span class="cd">CDNA</span>' in cand                          # 沒有中文簡介：用每週紀錄的英文名
    lane = X["tl"]["qm"]
    its = lane["held"][0]["items"]                                                      # 時間軸的條上寫代號（短）、提示框寫公司名
    assert [i["n"] for i in its] == ["INSW", "VLO"] and [i["nm"] for i in its] == ["International Seaways（INSW）", "瓦萊羅能源（VLO）"]
    assert lane["next"] == {"d": "2026-10-26", "fix": "2026-10-23"} and not lane["buy"]   # 有空位：下一份名單出來後買
    assert "esc(i.nm||i.n)" in CF.JS
    dates = re.findall(r'<div class="cfevd"><b>([^<]+)</b>', s)
    assert dates == ["10/23", "每天", "10/26"], dates                                    # 每天的 50 日線檢查放在第一天後面
    assert "有 6 個空位，名單前面、手上沒有的下一個交易日開盤買" in _text(s) and "名單前面的公司，每檔約 12.5%" in _text(s)
    assert "最接近的是" in _text(s) and f'<a {_uhref("INSW")}>International Seaways</a>，比 50 日線高 3.2%' in s
    assert CF._yf("BRK.B") == _yhref("BRK-B")                                         # Yahoo 的代號寫法


def test_us_v2_buy_tomorrow_fills_all_slots(R, QMX, monkeypatch):
    """同 10/24 的真實情況：7 檔、現金 10.3%、下一個交易日開盤買 1 檔把現金用完。"""
    monkeypatch.setattr(CPG, "qm_on", lambda mk, q: True)
    monkeypatch.setattr(CPG, "_US_INTRO", {"FTNT": "美國 Fortinet，網路資安業者；…"})
    hold = [_h(f"S{i}", 0.128) for i in range(7)]
    lst = [{"c": f"S{i}", "rs": 99.0} for i in range(6)] + [{"c": "FTNT", "rs": 97.0}]
    qm = _qm(QMX, hold, buy=["FTNT"], idle=0.104, lst=lst)
    X = CF.us_parts(_data(), _bundle(R, qm=qm))
    t = _text(X["card"])
    assert "現金 10.4% 是空的位子：10/26（一）開盤買 Fortinet（約 10.4%）之後，8 個位子都滿，股票約" in t and "100%" in t
    h = X["hold"]
    assert f'<a class="cfrow todo" {_uhref("FTNT")}>' in h and "約 10.4%" in h and "10/26（一）開盤買" in _text(h)
    assert "為什麼：10/23 收盤的名單第 7 名（手上還沒有），漲勢勝過 97% 的美股" in _text(h)
    assert "7 檔＋1 檔待買" in _text(h)
    s = X["sched"]
    assert f'強勢品質股：<a {_uhref("FTNT")}>Fortinet</a>（約 10.4%）' in s
    assert "8 個位子都滿，有空位才買" in _text(s)
    assert X["tl"]["qm"]["buy"][0]["d"] == "2026-10-26" and X["tl"]["qm"]["next"] is None


def test_us_v2_daily_check_pending_sell(R, QMX, monkeypatch):
    """每天的檢查：收盤跌破 50 日線、還沒到賣出日 → 持股列寫哪天開盤賣、接下來的買賣列出、現在的錢算賣完之後。"""
    monkeypatch.setattr(CPG, "qm_on", lambda mk, q: True)
    W = {"base": "2026-10-22", "d": "2026-10-23", "hold": [{"c": "A", "px": 100.0, "pct": 0.05}, {"c": "B", "px": 50.0, "pct": -0.02}],
         "sell": [{"c": "B", "trig": "2026-10-23", "on": "2026-10-26"}]}
    qm = _qm(QMX, [_h("A", 0.5), _h("B", 0.25, px=50.0)], idle=0.25, d="2026-10-22", nxt="2026-10-23", W=W)
    X = CF.us_parts(_data(), _bundle(R, qm=qm))
    t = _text(X["card"])
    assert "現金 25% 是空的位子：10/26（一）開盤賣 B 之後，1 檔、空 7 個位子，股票約" in t and "50%" in t   # 英文名後面空一格
    assert "空的位子等 10/30（五）收盤的下一份名單。" in t
    assert "10/26（一）開盤賣（10/23 收盤跌破 50 日線）" in _text(X["hold"])
    s = X["sched"]
    assert re.findall(r'<div class="cfevd"><b>([^<]+)</b>', s) == ["10/26", "每天", "10/30", "11/2"]
    assert "10/23 收盤跌破 50 日線" in _text(s) and "最接近的是" in _text(s)
    assert X["tl"]["qm"]["adj"] == [{"d": "2026-10-26", "at": "開盤", "act": "賣出", "note": "賣掉 B（收盤跌破 50 日線）"}]


def test_us_v2_midweek_sold_and_bought_already(R, QMX, monkeypatch):
    """每週紀錄（週六）之後過了幾天：每天的檢查比較新——賣出日已過的算現金、買進日已過的算持有、漲跌照新的收盤。"""
    monkeypatch.setattr(CPG, "qm_on", lambda mk, q: True)
    W = {"base": "2026-10-23", "d": "2026-10-27", "hold": [{"c": "A", "px": 110.0, "pct": 0.05}, {"c": "B", "px": 45.0, "pct": -0.03}],
         "sell": [{"c": "B", "trig": "2026-10-26", "on": "2026-10-27"}]}
    qm = _qm(QMX, [_h("A", 0.45, r=0.2, px=100.0), _h("B", 0.45, px=50.0)], buy=["F"], idle=0.1,
             lst=[{"c": "A", "rs": 99.0}, {"c": "F", "rs": 97.0}], W=W)
    X = CF.us_parts(_data(), _bundle(R, qm=qm))
    G = CF.us_state(_bundle(R, qm=qm))
    assert [r["c"] for r in G["rows"]] == ["A", "F"] and [x["c"] for x in G["gone"]] == ["B"] and not G["todo"]
    assert abs(sum(r["w"] for r in G["rows"]) + G["idle"] - 1) < 1e-9                    # 比重照新的收盤重算、合計 100%
    assert abs(G["rows"][0]["r"] - 0.32) < 1e-9                                          # (1＋20%) × 110 ÷ 100 − 1
    t = _text(X["card"])
    assert "現金 43.1% 是空的位子（B 10/27 開盤賣掉了），10/30（五）收盤看下一份名單" in t and "57%" in t
    h = _text(X["hold"])
    assert "+32.0%" in h and "10/26 買・漲跌等這週六的持股紀錄" in h and "2 檔" in h and "待買" not in h
    s = _text(X["sched"])
    assert "（約 " not in s and "有 6 個空位" in s                                           # 已經買了，不再列；8 − 2 檔＝6 個空位


def test_us_v2_cash_mode_and_index_fallback(R, QMX, monkeypatch):
    """警訊：全部持股放現金（美股長抱 0%，整個帳戶都是現金）；強勢品質股判定沒過：全部持股買 S&P 500 ETF。"""
    monkeypatch.setattr(CPG, "qm_on", lambda mk, q: True)
    N = _us()
    N.update(now=0.0, next=0.0, due=False, on=False, ok=False)
    qm = _qm(QMX, [_h("A", 0.5)], buy=["F"], idle=0.5, lst=[{"c": "F", "rs": 97.0}])
    X = CF.us_parts(_data(), _bundle(R, qm=qm, spx=N))
    c = X["card"]
    assert re.findall(r'<li><u class="(c\d|cx)"></u><span>([^<]+)</span><em>([0-9.]+)%</em></li>', c) == [("cx", "現金", "100")]
    assert "全部持股放現金中；警訊解除後隔天收盤買回" in _text(c)
    h = _text(X["hold"])
    assert "警訊：全部持股現在放現金；下面是照規則該有的股票，買回時照這樣買。" in h and "警訊：全部持股放現金中" in h
    assert "全部持股放現金中，先不買" in _text(X["sched"])
    monkeypatch.setattr(CPG, "qm_on", lambda mk, q: False)
    X = CF.us_parts(_data(), _bundle(R, qm=None))
    c, h = X["card"], X["hold"]
    assert re.findall(r'<li><u class="(c\d|cx)"></u><span>([^<]+)</span><em>([0-9.]+)%</em></li>', c) == [("c1", "S&amp;P 500 ETF（SPY 或 VOO）", "100")]
    assert f'<a class="cfrow" {_yhref("SPY")}>' in h and "全部持股買 S&amp;P 500 ETF（例如 SPY、VOO），有警訊時換成現金。" in h
    assert "接下來沒有排定的買賣；有警訊時才會換成現金。" in _text(X["sched"]) and X["tl"]["qm"] is None
    assert "有空位時依序買" not in _text(h)


def test_cfg_js_only_v2_and_no_observed_lanes():
    """兩個市場都是 v2 版面；時間軸只畫配置裡的策略（觀察中策略的訊號不放配置頁，2026-10-24 使用者決定）。"""
    js = CF.JS
    for w in ("時程與水位", "data-cfo", "cfo_", "cfMacLb", "MCM", "xmTip", "T.obs"):
        assert w not in js, w
    assert "data-cfo" not in CF.tl_shell("us") and 'id="cftl-us"' in CF.tl_shell("us")
    for f in ("_tiles", "warn_row", "_stack", "_none_row", "_pill", "_us_next", "_us_tiles", "_qm_fill"):   # 舊版的函式拿掉了
        assert not hasattr(CF, f), f


def test_us_label_parses_intro_first_clause(monkeypatch):
    monkeypatch.setattr(CPG, "_US_INTRO", {"AMD": "美國超微（AMD），CPU、GPU 設計廠；EPYC…",
                                           "FTNT": "美國 Fortinet，網路資安業者；產品…", "XX": "美國 某公司"})
    assert CPG.us_label("AMD") == ("超微", "CPU、GPU 設計廠")
    assert CPG.us_label("FTNT") == ("Fortinet", "網路資安業者") and CPG.us_name("FTNT") == "Fortinet（FTNT）"
    assert CPG.us_label("XX") == ("某公司", "")
    assert CPG.us_label("ZZ", {"ZZ": "Zz Corp"}) == ("Zz Corp", "") and CPG.us_label("ZZ") == ("ZZ", "")
    assert CPG.us_name("ZZ") == "ZZ"


def test_tw_page_has_boom_book_section(R):
    """2026-10-24 使用者：「換成新飆股」——台股配置頁的飆股名單換成新飆股（機動的一半）那本帳：每週名單、這一週的試算、
    下一份名單；持股在持股細節。原本的到買點／快到買點名單留在研究紀錄。"""
    X = CF.tw_parts(_data(), _bundle(R))
    b = X["boom"]
    assert 'id="cf-tw-sx" data-nav="新飆股名單"' in b
    t = _text(b)
    assert "占全部資金 40%" in t and "每檔約占全部資金 5%" in t and "抱 60 個交易日" in t
    assert "11/6（五） 收盤的名單（3 檔）" in t
    rows = re.findall(r'<tr><td><a data-c="(\d+)" data-co="\1">([^<]+)</a> <span', b)
    assert [n for _, n in rows] == ["金像電", "台燿", "奇鋐"]                         # 名單的名字可以點
    assert "11/9 開盤買" in t and "現金不夠" in t and "已經有" in t                    # 名單裡：要買的、錢不夠的、手上有的
    bm = R["mk"]["tw"]["sc"]["plan"].get("boom") or {}
    if bm.get("cagr") is not None:
        assert f'每年賺 {CPG._pc(bm["cagr"]).lstrip("+")}' in t and f'最慘時跌 {bm["mdd"] * 100:.0f}%' in t
    assert 'data-go="opp" data-at="o-sx"' in b                                    # 舊的飆股名單在研究紀錄
    js = CF.JS
    assert "(C.boom||'')" in js and "function cfSx()" not in js and "cfSx" not in js
    assert "if(T.boom)L.push(Object.assign({},T.boom,{_src:'boom'}));" in js and "c._src==='boom'" in js
    lane = X["tl"]["boom"]                                                        # 時間軸：持有中依買進日、明天要買、下一次看名單
    assert lane["held"][0]["ent"] == "2026-11-02" and {i["c"] for i in lane["held"][0]["items"]} == {"3017", "2383"}
    assert lane["buy"][0]["d"] == "2026-11-09" and [i["c"] for i in lane["buy"][0]["items"]] == ["2368"]
    assert lane["next"]["fix"] == "2026-11-13"
    stk = dict(STK, boom=None)                                                    # 讀不到新飆股：不出這一段、時間軸沒有那一列
    X = CF.tw_parts(_data(), dict(_bundle(R), stk=stk))
    assert X["boom"] == "" and X["tl"]["boom"] is None


def test_build_shapes_and_survives_missing_pieces(R, QMX):
    out = CF.build(_data(), _bundle(R, qm=QMX))
    assert set(out) >= {"now", "use", "board", "tw", "us"} and out["use"] == ["v3l", "s3", "s5"]
    for mk in ("tw", "us"):
        assert out[mk]["card"] and out[mk]["hold"] and "看全部策略" in out[mk]["line"], mk
    assert out["board"]["n"]["use"] >= 5 and 'class="btbl"' in out["board"]["html"]
    bare = CF.build({}, None)                                                     # 研究檔、讀數都沒有：不出錯、頁面寫還沒算出來
    assert bare["use"] == [] and "tw" in bare and "us" in bare
    assert "今天的讀數還沒算出來" in (bare["tw"].get("warn") or "") or bare["tw"].get("err")
    assert "讀不到各策略的持股" in _text(bare["tw"].get("card") or "") or bare["tw"].get("err")


def test_cfg_text_is_plain(R, QMX):
    out = CF.build(_data(), _bundle(R, qm=QMX))
    for mk in ("tw", "us"):
        t = _text(out[mk]["card"] + out[mk]["hold"])
        for w in BANNED + JARGON + NOT_PLAIN:
            assert w not in t, (mk, w)
        for w in BANNED + NOT_PLAIN:                                              # 策略一行可以寫「候選 0」
            assert w not in _text(out[mk]["line"]), (mk, w)
    tb = _text(out["board"]["html"])
    for w in BANNED + NOT_PLAIN + ("隨便挑", "★", "●", "好策略", "可參考"):
        assert w not in tb, w
    for s in BD.STATUS:
        assert BD.ST_NAMES[s] in tb, s


def test_board_html_groups_and_filters():
    B = {"rows": [{"id": "tw:plan", "name": "兩成長抱＋警訊（台股）", "mk": "台股", "mkk": "tw", "type": "配置", "st": "use", "how": "h",
                   "go": {"go": "tw"}, "perf": "年化 18.0%", "ref": "一直抱著 12.0%", "mdd": "23%", "mddr": "29%", "today": "拿 100%"}]
         + [{"id": f"tw:o{i}", "name": f"觀察 {i}", "mk": "台股", "mkk": "tw", "type": "個股", "st": "obs", "how": "h", "go": {}}
            for i in range(BD.OBS_SHOW + 2)]
         + [{"id": "us:x", "name": "淘汰的", "mk": "美股", "mkk": "us", "type": "個股", "st": "out", "why": "原因一句", "go": {}}],
         "n": {"use": 1, "obs": BD.OBS_SHOW + 2, "cand": 0, "out": 1}, "nm": {}}
    h = CF.board_html(B)
    assert f'<table class="btbl" data-n="{BD.OBS_SHOW}">' in h and 'data-bx="obs"' in h   # 觀察中先列 8 條：依篩選在瀏覽器算
    assert h.count('<tr class="br" data-st="obs" data-mk="tw">') == BD.OBS_SHOW + 2
    assert "目前沒有；第一批在每週日新找之後出現" in h                                  # 候選分組先空著
    assert '<td class="bw" colspan="4">原因一句</td>' in h                           # 淘汰一列一句原因
    assert '<a data-go="tw">兩成長抱＋警訊（台股）</a>' in h
    assert '<a data-bst="out">淘汰 1</a>' in h and '<a data-bst="use" class=on>使用中 1</a>' in h   # 淘汰預設收起


def test_page_tabs_personas_and_script_order():
    html = page.render({"etfs": {}, "asof": {}, "cfg": {"use": []}})
    assert 'id="purp"' not in html and "{{" not in html
    for t in ("tw", "us", "strat", "tool"):
        assert f'data-t="{t}" data-p="cfg"' in html, t
    for t in ("stg", "mac", "bo"):
        assert f'data-t="{t}" data-p="r" hidden' in html, t
    assert '<a class="rbk" href="x9r.html" data-p="r" hidden>‹ 研究紀錄</a>' in html
    from arm.lab import appnav, copage, macpage
    assert appnav.bar("cfg", search=copage.SEARCH_HTML) in html and CF.CSS in html
    from arm.lab import corepage
    assert corepage.CSS.split("\n", 1)[0] in html                                   # 「細節」用 corepage 的圖表與表格，樣式要一起載入
    js = html[html.index("<script>"):]
    i_mac, i_cf, i_co, i_init = js.index("const MAC=D.mac||{}"), js.index("const CFG=D.cfg||{}"), js.index(copage.JS[:200]), js.index("go(v,at);")
    assert i_mac < i_cf < i_co < i_init                                            # 配置的 JS 在初始化之前（頂層 const 已經初始化）
    J = page._JS
    assert "const VIEWS={tw:vCfgTw,us:vCfgUs,strat:vCfgSt,stk:vStk,chip:vChip,idx:vIdx,opp:vOpp,st:vSt,mac:vMac,macst:vMacSt,bo:vBo};" in J
    assert "const LAST={cfg:'tw',r:'bo',tool:'stk',mac:'mac',stg:'opp'};" in J
    assert "if(!VIEWS[v])v=/^#((s|co)=|q$)/.test(location.hash)?'stk':/^#us=/.test(location.hash)?'us':'tw';" in J   # 預設台股；舊的個股卡連結、查公司（#q）先到個股表；美股個股卡（#us=）到配置・美股
    assert "if(d.gm)S.mmk=d.gm;if(d.bmk)S.bmk=d.bmk;" in J
    for v in ("vStk", "vChip", "vIdx"):                                            # 個股（工具）三頁最上面切換
        seg = J[J.index(f"function {v}("):]
        assert "toolSeg('" in seg[:seg.index("\n}\n")], v
    assert "sec('c-sig'" not in J and "sec('c-risk'" not in J and "function sigTodaySec(" not in J   # 籌碼頁的今日訊號、風險提醒拿掉
    assert "function stCardSec(c){const P=PKU[c];" in J and "CFU.has(p.k)" in J    # 個股卡只列配置裡的策略
    assert "S.sig==='sx'?SXC.has(r.c)" in J and "<option value=sx" in J               # 個股表留一個「飆股候選」篩選


def test_cfg_js_names_prefixed():
    names = re.findall(r"^function (\w+)\(|^(?:const|let) (\w+)", CF.JS, re.M)
    flat = [a or b for a, b in names]
    assert flat and all(n.startswith(("cf", "vCfg", "toolSeg", "CF")) for n in flat), flat


def test_finish_rebuilds_with_todays_readings(tmp_path, monkeypatch, R):
    out = tmp_path / "x9.html"
    data = {"etfs": {}, "asof": {}, "adv": _data()["adv"], "mac": _data()["mac"]}
    monkeypatch.setattr(page, "_LAST", {})
    assert page.finish(out) is False                                              # build() 沒跑過：不動
    page._LAST.update(data=data, out=out, ser_v="x")
    monkeypatch.setattr(SG, "CARDS", {})
    assert page.finish() is False and not out.exists()                             # 景氣頁沒有留下讀數：不動
    monkeypatch.setattr(SG, "CARDS", {"tw": {"core": _now(n_lit_extra=True)}, "spx": {"core": _us()}})
    monkeypatch.setattr(CO, "STK", dict(STK))
    assert page.finish() is True and out.exists()
    assert data["cfg"]["now"]["tw"]["n"] == 2                                     # 用今天的讀數
    assert page.finish() is False                                                 # 內容一樣：不改寫


def test_tw_boom_rows_say_which_rule_they_matched(R):
    """配置頁第 5 步：新飆股名單、待買進、持股都寫符合哪一條規則（實際數字＋要多少）。"""
    import copy
    stk = copy.deepcopy(STK)
    B = stk["boom"]
    why = "符合：強度 95（要 90 以上）、近 20 日漲停 2 次、月營收創歷史新高"
    for x in B["list"] + B["buy"]:
        if x["c"] == "2368":
            x["why"] = [why + "（另外也符合 1 條）"]
    B["hold"][0]["why"] = ["10/30 那週名單第 2 名", "符合：20 日均成交值 12.0 億（要 6.5 億以上）、月營收創歷史新高"]
    X = CF.tw_parts(_data(), dict(_bundle(R), stk=stk))
    t = _text(X["boom"])
    assert why + "（另外也符合 1 條）" in t                                            # 名單那一列的名字下面
    assert X["boom"].count('class="cfin"') == 1                                     # 沒有紀錄的不寫
    h = _text(X["hold"])
    assert "為什麼：10/30 那週名單第 2 名；符合：20 日均成交值 12.0 億（要 6.5 億以上）、月營收創歷史新高" in h
    assert "為什麼：強度 95（漲勢勝過 95% 的股票）；" + why in h                      # 待買進：強度＋符合哪一條
    for w in NOT_PLAIN + BANNED:
        assert w not in t and w not in h, w


def test_us_rows_mark_backtest_buys_and_return_since_live_start(R, QMX, monkeypatch):
    """檢討第 1 步（docs/lab_review_plan.md 第 9.1 節）：開始照做（QM_LIVE）那天以前照規則買的標「回測」，
    另寫上線以來＝開始照做那一週週末的收盤到最新的收盤；之後才買的不標。"""
    monkeypatch.setattr(CPG, "qm_on", lambda mk, q: True)
    qm = _qm(QMX, [_h("INSW", 0.4, ent="2026-07-20", r=0.29, px=110.0, ma=105.0), _h("PAYC", 0.12, ent="2026-10-26", r=0.02, px=200.0, ma=190.0)],
             idle=0.48, d="2026-10-30", nxt="2026-11-02", lst=[])
    qm["L"]["weeks"] = {"2026-10-23": {"hold": [{"c": "INSW", "px": 100.0}]}}
    G = CF.us_state(_bundle(R, qm=qm))
    rows = {r["c"]: r for r in G["rows"]}
    assert rows["INSW"]["bt"] and rows["INSW"]["rl"] == pytest.approx(0.10) and rows["INSW"]["p0"] == 100.0
    assert not rows["PAYC"]["bt"] and rows["PAYC"]["rl"] is None
    h = CF.us_parts(_data(), _bundle(R, qm=qm))["hold"]
    assert "7/20 買（回測）・上線以來 +10.0%・比 50 日線高 4.8%" in _text(h)
    assert "10/26 買・比 50 日線高 5.3%" in _text(h)


def test_tw_rows_mark_backtest_buys_and_return_since_live_start():
    """台股持股第二行：開始照做以前照規則買的寫「（回測）」和上線以來；之後才買的照舊。"""
    r = {"ent": "2026-08-24", "epx": 13650.0, "px": 9755.0, "bt": True, "rl": 0.0056, "sell": "11/24 開盤賣"}
    assert CF._row_b(r) == "8/24 買（回測）13,650，現在 9,755・上線以來 +0.6%・11/24 開盤賣"
    r2 = {"ent": "2026-10-27", "epx": 51.2, "px": 50.0, "sell": ""}
    assert CF._row_b(r2) == "10/27 買 51.2，現在 50"
    assert CF._row_b({"ent": "2026-08-24", "bt": True}) == "8/24 買（回測）"


def test_past_note_lists_hindsight_and_live_start_dates():
    """「過去照做」下面兩行：哪些規則是看過資料才訂的；開始照做的日子（新飆股接手、★ 策略的 since、警訊）。"""
    data = {"adv": {"grades3": [{"k": "v3l", "since": "2026-10-15"}, {"k": "s3", "since": "2026-10-14"}],
                    "book": [{"k": "s5", "since": "2026-10-14"}]}}
    bundle = {"stk": {"st": [{"k": "s3", "name": "臺灣50 提前卡位"}, {"k": "v3l", "name": "財報驚喜"}, {"k": "s5", "name": "長線"}],
                      "boom": {"take": "2026-10-22"}}}
    t = _text(CF.past_note("tw", data, bundle))
    assert "個股策略的主要設定也一樣（臺灣50 卡位、長線看過全部的資料，財報驚喜看過 2021 年以後的資料）" in t
    assert "開始照做以後的才是實際成績：新飆股 10/22 收盤、臺灣50 卡位 10/14、財報驚喜 10/15、長線 10/14、警訊 10/27 起" in t
    u = _text(CF.past_note("us", {}, {}))
    assert "從 2,016 種做法裡挑的" in u and "強勢品質股 10/23 收盤、警訊 10/26 起" in u
    assert CF._wp(0.0002) == "不到 0.1%" and CF._wp(0.0) == "0%" and CF._wp(0.125) == "12.5%"
