"""美股個股卡（arm/lab/uscardpage.py；配置頁 v2 第 4 步，docs/lab_cfg_v2_plan.md 第 3.3 節）：
配置頁美股列點了打開的卡片——配置、為什麼選它、走勢、分析師、公司；網址 #us=代號。"""
import json
import re
import shutil
import subprocess

import pytest

from arm.lab import cfgpage as CF
from arm.lab import corepage as CPG
from arm.lab import page
from arm.lab import uscardpage as UCP
from arm.lab import ussxspec as QX
from test_cfgpage import QMX, R, _bundle, _data, _h, _qm  # noqa: F401 —— fixture 共用
from test_corepage import BANNED, JARGON, NOT_PLAIN, _text

METHOD = ("只當參考", "看不出", "樣本", "亂排", "打亂", "預估之後", "判定", "對照", "規格", "門檻", "區間", "研究", "注意", "隨便挑一天")


def _card(codes, cal=("2026-10-21", "2026-10-22", "2026-10-23"), an=None, px=None):
    """假的 ussx_card.json：每檔三天收盤與 50 日線（px＝{代號: 最後一天收盤}）。"""
    s = {}
    for k, c in enumerate(codes):
        base = (px or {}).get(c, 102.0 + 10 * k) / 1.02
        s[c] = {"c": [base, base * 1.01, base * 1.02], "m": [None, base * 0.95, base * 0.96], "at": cal[-1],
                "an": (an or {}).get(c), "an_at": cal[-1]}
    return {"ver": 1, "d": cal[-1], "cal": list(cal), "codes": list(codes), "s": s}


def _has(h: str, s: str) -> bool:
    """HTML 看得到的字裡有沒有 s（標籤換成空白會多出空格，比較時不看空白）。"""
    return re.sub(r"\s+", "", s) in re.sub(r"\s+", "", _text(h))


def _qmc(QMX, card, **kw):
    q = _qm(QMX, **kw)
    q["C"] = card
    return q


def test_five_rows_follow_rule_and_format():
    q = QX.QM
    rows = UCP.five_rows()
    assert [k for k, _, _ in rows] == ["rs", "d52h", "om", "roe", "cap"]            # 同 ussxqm.KEYS 的順序
    assert rows[0][2] == f"要 {q['rs']:.0f} 以上" and rows[1][2] == f"要在 {-q['d52h'] * 100:.0f}% 以內"
    assert rows[4][2] == "要 20 億美元以上"
    assert UCP.five_txt("d52h", -0.0915) == "低 9.2%" and UCP.five_txt("d52h", 0.0) == "在高點"
    assert UCP.five_txt("cap", 1.207e11) == "1,207 億" and UCP.five_txt("cap", 2.261e9) == "22.6 億"
    assert UCP.five_txt("rs", 97.6) == "98" and UCP.five_txt("om", 0.1168) == "11.7%" and UCP.five_txt("roe", None) == "—"
    assert UCP.five_ok("rs", 79.0) is False and UCP.five_ok("d52h", -0.25) is True and UCP.five_ok("cap", None) is None


def test_build_order_sections_and_numbers(R, QMX, monkeypatch):
    """順序＝持有中、待買進、名單前幾名（手上沒有的）；每一檔三段 HTML（配置、為什麼選它、公司）＋走勢與分析師的資料。
    持有中的「占全部資金」和配置頁那一列一樣（us_state）。"""
    monkeypatch.setattr(CPG, "qm_on", lambda mk, q: True)
    monkeypatch.setattr(CPG, "_US_INTRO", {"VLO": "美國瓦萊羅能源（Valero Energy），大型煉油商；在美國…"})
    lst = [{"c": c, "rs": 99.0 - i} for i, c in enumerate(["VLO", "F", "P1", "P2"])]
    card = _card(["VLO", "F", "P1"], px={"VLO": 419.28})
    qm = _qmc(QMX, card, hold=[_h("VLO", 0.5, ent="2026-08-31", r=0.165, px=419.26, ma=392.41)], buy=["F"], idle=0.5,
              lst=lst, d="2026-10-23", nxt="2026-10-26")
    qm["L"]["now"]["met"] = {"VLO": [98.0, -0.0915, 0.1168, 0.2939, 1.207e11], "F": [97.0, -0.08, 0.33, 1.17, 1.3e11],
                             "P1": [96.0, -0.3, 0.05, 0.2, 1.5e9]}
    qm["L"]["now"]["met0"] = {"VLO": {"wk": "2026-08-28", "v": [96.0, -0.0017, 0.1168, 0.2939, 1.0146e11]}}
    X = CF.us_parts(_data(), _bundle(R, qm=qm))
    uc = X["uc"]
    assert uc["o"] == ["VLO", "F", "P1", "P2"] and uc["cal"] == card["cal"]
    G = CF.us_state(_bundle(R, qm=qm))
    v = uc["s"]["VLO"]
    assert v["nm"] == "瓦萊羅能源" and v["what"] == "大型煉油商" and v["px"] == card["s"]["VLO"]["c"][-1]
    st = _text(v["st"])
    assert f"占全部資金 {CPG._wp(G['rows'][0]['w'])}" in st and _has(v["st"], "8/31（一）買進 359.88（回測），現在 419.28（+16.5%）")
    assert "上線以來" not in st                                  # 沒有開始照做那一週的紀錄：不寫上線以來
    assert "收盤跌破 50 日線，就在下一個交易日開盤賣" in st and "50 日線現在" in st
    assert v["ent"] == ["2026-08-31", pytest.approx(419.26 / 1.165)] and v["out"] is None
    w = v["why"]
    assert "買進時" in w and "8/28 那週" in w and "10/23 那週" in w and w.count('class="ucok"') == 10   # 兩欄、五個都過
    assert "10/23 那週的名單第 1 名（共 4 檔）" in _text(w)
    assert "營業利益增加的比營收增加的多" in _text(w) and "那一季不算" in _text(w)          # ussxspec VER 7：一次性收入
    f = uc["s"]["F"]
    assert "待買進" in _text(f["st"]) and "10/26（一）開盤買" in _text(f["st"]) and "買進時" not in f["why"]
    p1 = uc["s"]["P1"]
    assert "手上沒有：10/23 那週名單第 3 名" in _text(p1["st"]) and p1["why"].count('class="ucno"') == 3   # 離高點、營益率、市值沒過
    p2 = uc["s"]["P2"]
    assert "c" not in p2 and "這週的五個數字還沒有" in _text(p2["why"])                    # 沒有卡片資料、沒有五個數字
    assert "Yahoo Finance" in v["co"] and "https://www.sec.gov/cgi-bin/browse-edgar?" in v["co"] and "CIK=VLO" in v["co"]
    for c, x in uc["s"].items():
        t = _text(x["st"] + x["why"] + x["co"])
        for wd in BANNED + JARGON + NOT_PLAIN + METHOD:
            assert wd not in t, (c, wd)


def test_rows_open_card_and_fall_back_to_yahoo(R, QMX, monkeypatch):
    """配置頁美股：持股列、名單、接下來的買賣裡的股票名都開卡片（#us=代號）；卡片沒有那一檔才開 Yahoo Finance。"""
    monkeypatch.setattr(CPG, "qm_on", lambda mk, q: True)
    lst = [{"c": "A", "rs": 99.0}, {"c": "F", "rs": 97.0}, {"c": "Q", "rs": 96.0}]
    qm = _qmc(QMX, _card(["A", "F"]), hold=[_h("A", 0.5)], buy=["F"], idle=0.5, lst=lst)
    X = CF.us_parts(_data(), _bundle(R, qm=qm))
    h, s = X["hold"], X["sched"]
    assert '<a class="cfrow" href="#us=A" data-us="A">' in h and '<a class="cfrow todo" href="#us=F" data-us="F">' in h
    assert 'href="#us=Q" data-us="Q"' in h                                                 # 名單前幾名也開卡片
    assert 'data-us="F"' in s and "點股票看個股卡" in _text(s) and "點股票看走勢、為什麼選它、分析師預估" in _text(h)
    G = {"uc": {"A"}, "nms": {}}
    assert CF._ua("A", G) == 'href="#us=A" data-us="A"' and CF._ua("Z", G) == CF._yf("Z")
    monkeypatch.setattr(CPG, "qm_on", lambda mk, q: False)                               # 強勢品質股沒在用：沒有卡片
    X = CF.us_parts(_data(), _bundle(R, qm=None))
    assert X["uc"] is None and "data-us" not in X["hold"]


def test_cfg_line_variants(R, QMX, monkeypatch):
    """配置段：已經跌破 50 日線（哪天開盤賣）、這週賣掉了、警訊放現金中。"""
    monkeypatch.setattr(CPG, "qm_on", lambda mk, q: True)
    W = {"base": "2026-10-22", "d": "2026-10-23", "hold": [{"c": "A", "px": 100.0, "pct": 0.05, "ma": 95.2},
                                                           {"c": "B", "px": 50.0, "pct": -0.02, "ma": 51.0}],
         "sell": [{"c": "B", "trig": "2026-10-23", "on": "2026-10-26"}]}
    qm = _qmc(QMX, _card(["A", "B"]), hold=[_h("A", 0.5), _h("B", 0.25, px=50.0)], idle=0.25, d="2026-10-22", nxt="2026-10-23", W=W)
    uc = CF.us_parts(_data(), _bundle(R, qm=qm))["uc"]
    assert _has(uc["s"]["B"]["st"], "10/26（一）開盤賣（10/23 收盤跌破 50 日線）") and uc["s"]["B"]["out"] == "2026-10-26"
    assert _has(uc["s"]["A"]["st"], "50 日線現在 95.20（收盤比它高 5.0%）")
    from test_corepage import _us
    N = _us()
    N.update(now=0.0, next=0.0, due=False, on=False, ok=False)
    uc = CF.us_parts(_data(), _bundle(R, qm=qm, spx=N))["uc"]
    assert "警訊：全部持股放現金中" in _text(uc["s"]["A"]["st"])
    W2 = {"base": "2026-10-23", "d": "2026-10-27", "hold": [{"c": "A", "px": 110.0, "pct": 0.05}],
          "sell": [{"c": "B", "trig": "2026-10-26", "on": "2026-10-27"}]}
    qm = _qmc(QMX, _card(["A", "B"]), hold=[_h("A", 0.45), _h("B", 0.45, px=50.0)], idle=0.1, W=W2)
    uc = CF.us_parts(_data(), _bundle(R, qm=qm))["uc"]
    assert _has(uc["s"]["B"]["st"], "10/27（二）開盤賣掉了（10/26 收盤跌破 50 日線）")
    assert uc["o"][:2] == ["A", "B"] and uc["s"]["B"]["ent"][0] == "2026-08-03"


def test_target_price_only_in_analyst_function():
    """「目標價」只准出現在分析師那一支（ucAn：引述 Yahoo 的分析師數字、附來源連結；同台股公司卡法人預估的例外）。"""
    js = UCP.JS
    i = js.index("function ucAn(")
    j = js.find("\nfunction ", i + 1)
    j = js.find("\n/*", i + 1) if j < 0 else min(j, js.find("\n/*", i + 1))
    body = js[i:j]
    assert "目標價" in body and "/analysis/" in body and "Yahoo Finance" in body
    assert "目標價" not in js.replace(body, "") + UCP.CSS
    src = open(UCP.__file__, encoding="utf-8").read().replace(js, "")
    assert "目標價" not in src.replace("「目標價」只准出現在 ucAn", "")
    for w in BANNED:
        if w != "目標價":
            assert w not in js + UCP.CSS, w


NODE = shutil.which("node")


def _run_an(S, last="2026-10-23"):
    js = UCP.JS
    i = js.index("function ucMd(")
    fns = "".join(js[js.index(f"function {n}("):js.index("\n", js.index(f"function {n}("))] + "\n" for n in ("ucMd", "ucPx", "ucDt"))
    k = js.index("function ucAn(")
    an = js[k:js.index("\n/*", k)]
    prog = r"""
function f(x,d=1){if(x==null)return '—';return Number(x).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});}
function sgn(x,d=1,suf=''){if(x==null)return '—';const c=x>0?'up':x<0?'dn':'mu';return `<span class=${c}>${x>0?'+':''}${f(x,d)}${suf}</span>`;}
function esc(s){return String(s??'');}
function mdw(d){return d?`${+d.slice(5,7)}/${+d.slice(8,10)}（W）`:'—';}
const UCD={cal:['2026-10-22',%s]};
%s
%s
process.stdout.write(ucAn('VLO',%s));
""" % (json.dumps(last), fns, an, json.dumps(S))
    del i
    r = subprocess.run([NODE, "-e", prog], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return re.sub(r"<[^>]+>", "", r.stdout)


@pytest.mark.skipif(not NODE, reason="沒有 node")
def test_analyst_text_cases():
    a = {"n": 19, "tp": [423.53, 435.0, 530.0, 238.0], "rc": [3, 6, 8, 3, 0], "ed": ["2026-10-22"], "ede": False,
         "y0": {"end": "2026-12-31", "e": [59.644, 15, 10.61], "t90": 35.237, "r": [1622.5, 1226.9]},
         "y1": {"end": "2027-12-31", "e": [51.652, 18, 59.644], "t90": 24.885, "r": [1444.9, 1622.5]}}
    t = _run_an({"px": 419.28, "an": a, "an_at": "2026-10-23"})
    assert "2026 年 EPS 預估 59.64（15 位；90 天前 35.24，上修；比去年 +462%）" in t
    assert "2027 年 EPS 預估 51.65（18 位；90 天前 24.89，上修；比前一年 -13%）" in t
    assert "營收預估 1,623 億美元（比去年 +32%）" in t
    assert "目標價 435.00，比現價高 3.7%（19 位分析師的中位數）最高 530.00、最低 238.00" in t
    assert "評等：強力看好 3、看好 6、中立 8、看淡 3" in t and "強力看淡" not in t
    assert "上次財報 10/22（W）（下次的日期還沒公布）" in t                                   # Yahoo 還沒換成下一次
    b = dict(a, ed=["2026-11-24", "2026-11-28"], ede=True, tp=[50.0, None, 60.0, 40.0])
    b["y0"] = {"end": "2027-01-31", "e": [-0.5, 4, -1.2], "t90": -0.5, "r": [21.9, 20.0]}
    t = _run_an({"px": 55.0, "an": b})
    assert "下次財報 11/24～11/28（公司還沒公布，Yahoo 估的日期）" in t
    assert "到 2027 年 1 月的年度 EPS 預估 -0.50（4 位；和 90 天前差不多；虧損縮小）" in t
    assert "目標價 50.00，比現價低 9.1%（19 位分析師的平均）" in t and "營收預估 21.9 億美元" in t
    assert "分析師資料還沒有" in _run_an({"px": 1.0, "an": None})


def test_page_wiring():
    """頁面：uscardpage 的 JS 在 cfgpage 後面（要用 CFG）、copage 前面、頁面初始化之前；#us= 的網址、關閉、左右鍵。"""
    html = page.render({"rows": [], "asof": {}})
    js = html[html.index("<script>"):]
    i_cf, i_uc, i_co, i_init = js.index("const CFG=D.cfg||{}"), js.index("const UCD="), js.index("/* ---- 查公司"), js.index("go(v,at);")
    assert i_cf < i_uc < i_co < i_init and UCP.CSS in html
    assert "/^#(s|co|us)=/.test(location.hash)" in page._JS                                 # 換分頁時保留 #us=
    assert "/^#us=/.test(location.hash)?'us':'tw'" in page._JS                              # 直接打開 #us= 到配置・美股
    assert "PUSHED&&/^#(s|us)=/.test(location.hash)" in page._JS and "ucStep(d)" in page._JS
    assert "{const m=location.hash.match(/^#us=(.+)$/);if(m)ucRender(decodeURIComponent(m[1]));}" in page._JS
    for s in ("data-us", "#us=", "function ucRender(", "function ucSvg(", "id=uc-st", "id=uc-why", "id=uc-px", "id=uc-an", "id=uc-co",
              "id=uc-gr", "id=uc-pf", "id=uc-val", "data-ucrg", "id=uc-sx", "id=uc-ind", "id=uc-ch"):
        assert s in UCP.JS, s
    for col in set(re.findall(r"#[0-9a-f]{6}\b", UCP.JS)):                                      # 深色模式換色（page.THEME_HEX）
        assert col in page.THEME_HEX, col
    if NODE:
        r = subprocess.run([NODE, "--check", "-"], input=UCP.JS, capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr


def test_core_data_carries_card(monkeypatch):
    """配置頁的卡片資料從 sigpage.core_data 的 qm["C"] 來（uscard.load）。"""
    from arm.lab import sigpage
    src = open(sigpage.__file__, encoding="utf-8").read()
    assert '"C": UC.load()' in src and '"F": UF.load()' in src


def test_us_card_writes_return_since_live_start(R, QMX, monkeypatch):
    """檢討第 1 步：開始照做（QM_LIVE 10/23）以前照規則買的標「回測」，另寫上線以來＝10/23 收盤到卡片上最新的收盤。"""
    monkeypatch.setattr(CPG, "qm_on", lambda mk, q: True)
    card = _card(["VLO"], px={"VLO": 430.0})
    qm = _qmc(QMX, card, hold=[_h("VLO", 0.5, ent="2026-08-31", r=0.165, px=419.26, ma=392.41)], idle=0.5,
              lst=[{"c": "VLO", "rs": 99.0}], d="2026-10-23", nxt="2026-10-26")
    qm["L"]["weeks"] = {"2026-10-23": {"hold": [{"c": "VLO", "px": 400.0}]}}
    v = CF.us_parts(_data(), _bundle(R, qm=qm))["uc"]["s"]["VLO"]
    assert _has(v["st"], "8/31（一）買進 359.88（回測），現在 430.00（+19.5%）；上線以來（10/23 收盤起）+7.5%")


# ── 走勢 5 年、成長、獲利、估值（docs/lab_review_plan.md 第 4 節 (a)(b)(c)） ─────────────────────────

def _wd(a, b):
    from datetime import date, timedelta
    d, out = date.fromisoformat(a), []
    while d <= date.fromisoformat(b):
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def test_weekly_px_merges_boundary_week():
    cal = _wd("2025-10-28", "2026-10-23")                                        # 2025-10-28 是週二
    rec = {"c": [100.0 + i for i in range(len(cal))], "wk": [["2025-10-17", 90.0, 10], ["2025-10-27", 95.0, 3]]}
    w = UCP.weekly_px(rec, cal)
    assert w[0] == ("2025-10-17", 90.0) and w[1] == ("2025-10-31", 103.0)        # 10/27（一）那週併進近一年的那幾天
    assert len({UCP._monday(d) for d, _ in w}) == len(w) and w[-1] == (cal[-1], 100.0 + len(cal) - 1)


def _fin(eps=(1.0, 1.0, 1.0, 1.0, 2.0, 2.0, 2.0, 2.0), filed_lag=40, y0=2024):
    """len(eps) 季（y0 年第一季起）：營收 100、110…、EPS 照給的、股東權益 1000、流通股數 100 百萬股。"""
    from datetime import date, timedelta
    ends = [f"{y0 + i // 4}-{('03-31', '06-30', '09-30', '12-31')[i % 4]}" for i in range(len(eps))]
    q = []
    for i, e in enumerate(ends):
        fd = (date.fromisoformat(e) + timedelta(days=filed_lag)).isoformat()
        rev = 100.0 + 10 * i
        q.append([e, fd, rev, rev * 0.5, rev * 0.2, rev * 0.1, eps[i], 1000.0])
    return {"q": q, "sh": [["2024-04-30", "2024-05-10", 100.0], ["2025-10-30", "2026-02-09", 100.0]]}


def test_growth_rows_yoy_margins_roe():
    g = UCP.growth_rows(_fin())
    last = g[-1]
    assert last[0] == "2025-12-31" and last[2] == 1.7                           # 營收 170 百萬＝1.7 億美元
    assert last[3] == pytest.approx(170 / 130 - 1, abs=1e-4) and last[8] == pytest.approx(1.0)   # 年增；EPS 2 比 1
    assert last[4] == 0.5 and last[5] == 0.2 and last[6] == 0.1
    assert last[9] == pytest.approx((14 + 15 + 16 + 17) / 1000, abs=1e-4)      # 近四季淨利 ÷ 股東權益
    assert g[0][3] is None and g[3][9] is None                                  # 第一年沒有去年同一季；不到五季沒有期初
    f = _fin()
    f["q"][3][6] = -1.0
    assert UCP.growth_rows(f)[-1][8] is None                                    # 去年同一季虧損：EPS 年增不算


def test_valuation_split_and_own_history():
    """分割以前公布的 EPS、股數換算成分割後（股價本來就是分割還原的）；本益比和自己近 5 年每週比。"""
    cal = _wd("2025-10-28", "2026-10-23")
    old = [[d, 50.0, 1000] for d in _wd("2021-10-25", "2025-10-24") if d.endswith(("-03", "-10", "-17", "-24"))]
    rec = {"c": [60.0] * len(cal), "wk": old, "spl": [["2025-03-01", 2.0]],
           "div": [["2020-06-01", 9.0], ["2024-06-03", 0.5], ["2025-06-02", 0.5], ["2026-06-01", 0.6]]}
    f = _fin(eps=(2.0,) * 16 + (1.0,) * 4, y0=2021)                              # 2024 年以前的 EPS 是分割以前公布的（2 → 1）
    v = UCP.valuation(f, rec, cal, 60.0)
    assert v["ttm"] == pytest.approx(4.0) and v["pe"] == 15.0
    assert v["bvps"] == pytest.approx(1000 / 100) and v["pb"] == 6.0           # 2026-02 公布的股數已經是分割後
    assert v["cap"] == pytest.approx(60 * 100 / 100)                             # 億美元
    assert v["yld"] == pytest.approx(0.6 / 60) and v["ndiv"] == 1
    yrs = dict(v["dy"])
    assert "2021" not in yrs and yrs["2022"] == 0.0 and yrs["2024"] == 0.5 and yrs["2026"] == 0.6 and v["dym"] == 10
    ph = v.get("peh")
    assert ph and ph["n"] >= UCP.PE_MIN_N and ph["from"].startswith("2021")
    # 舊的那幾週：股價 50 ÷（四季 EPS 2×4 ÷ 2）＝ 12.5 倍，沒有換算會變 6.25
    assert ph["lo"] == pytest.approx(12.5) and 0 <= ph["pct"] <= 100
    v0 = UCP.valuation(f, {"c": [60.0] * len(cal)}, cal, 60.0)
    assert v0.get("short") and "peh" not in v0                                  # 只有近一年的股價：還不和自己比
    assert UCP.fin_view(None, rec, cal, 60.0, None, {}) is None


@pytest.mark.skipif(not NODE, reason="沒有 node")
def test_js_series_weekly_matches_python():
    """瀏覽器端的 3 年、5 年每週點＝Python 的 weekly_px（同一週併成一點，成交量加總）；6 個月、1 年是每天。"""
    cal = _wd("2025-10-28", "2026-10-23")
    old = [[d, 50.0 + i, 7] for i, d in enumerate(d for d in _wd("2021-10-25", "2025-10-27") if d.endswith(("-03", "-10", "-17", "-24", "-27")))]
    S = {"c": [100.0 + i for i in range(len(cal))], "m": [None] * len(cal), "v": [5] * len(cal), "wk": old}
    js = UCP.JS
    names = ("ucDay", "ucIso", "ucMon", "ucSeries")
    fns = ""
    for n in names:
        i = js.index(f"function {n}(")
        j = js.find("\nfunction ", i + 1)
        fns += js[i:j] + "\n"
    k = js.index("const UCRGS=")
    prog = js[k:js.index("\n", k)] + "\n" + fns + "const UCD={cal:%s};\nconst S=%s;\n" % (json.dumps(cal), json.dumps(S)) + \
        "process.stdout.write(JSON.stringify({y:ucSeries(S,'1y'),f:ucSeries(S,'5y'),h:ucSeries(S,'6m')}));"
    r = subprocess.run([NODE, "-e", prog], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    o = json.loads(r.stdout)
    assert not o["y"]["wk"] and len(o["y"]["d"]) == len(cal) and o["h"]["d"][0] > "2026-04-20"
    py = UCP.weekly_px({"c": S["c"], "wk": old}, cal)
    first = o["f"]["d"][0]
    assert list(zip(o["f"]["d"], o["f"]["c"])) == [x for x in py if x[0] >= first]
    i = o["f"]["d"].index("2025-10-31")                                         # 跨過近一年起點的那週：舊的 7 千股＋四天各 5 千股
    assert o["f"]["v"][i] == 7 + 5 * 4 and o["f"]["m"][i] is None


# ── 籌碼、同產業、飆股檢查（docs/lab_review_plan.md 第 4 節 (d)(e)(f)） ─────────────────────────

def test_tx_text_and_chips():
    assert UCP.tx_text("Sale at price 80.10 - 82.00 per share.") == "賣出，每股 80.10～82.00"
    assert UCP.tx_text("Purchase at price 12.5 per share.") == "買進，每股 12.5"
    assert UCP.tx_text("Conversion of Exercise of derivative security at price 0.00 per share.") == "執行選擇權"
    assert UCP.tx_text("Stock Award(Grant) at price 0.00 per share.") == "公司給股"
    assert UCP.tx_text("Stock Gift at price 0.00 per share.") == "贈與"
    assert UCP.tx_text("") == "（沒有說明）" and UCP.tx_text("Something else") == "Something else"
    a = {"sh": [0.02, 2.4, 1.5e7, 1.2e7, "2026-09-30"], "mh": [0.18, 0.717, 1432.0],
         "tx": [["2026-10-01", "XIE KEN", "CEO", "Sale at price 80.10 per share.", 5e4, 4e6]] * 10}
    c = UCP.chips(a)
    assert c["sh"] == a["sh"] and c["mh"] == a["mh"] and "ns" not in c
    assert len(c["tx"]) == 8 and c["tx"][0][3] == "賣出，每股 80.10"
    assert UCP.chips(None) is None and UCP.chips({"n": 3}) is None


def _sx_rows(eps_yoy, rev_yoy, gm, roe=0.2):
    """growth_rows 形狀的 12 季（只填飆股檢查會看的欄）：EPS 年增、營收年增、毛利率依序給最近 3 季（舊到新）。"""
    ends = [f"{2024 + i // 4}-{('03-31', '06-30', '09-30', '12-31')[i % 4]}" for i in range(12)]
    g = [[e, e, 1.0, 0.1, 0.4, 0.2, 0.1, 1.0, 0.1, roe] for e in ends]
    for k in range(3):
        g[9 + k][8], g[9 + k][3], g[9 + k][4] = eps_yoy[k], rev_yoy[k], gm[k]
    return g


def test_sx_check_conditions_and_trend_template():
    g = _sx_rows((0.3, 0.4, 0.6), (0.2, 0.25, 0.3), (0.40, 0.42, 0.45))
    cal = _wd("2025-10-27", "2026-10-23")
    cs = [50.0 + 0.2 * i for i in range(len(cal))]                                # 一路漲：多頭排列
    x = UCP.sx_check(g, {"c": cs, "m": [None] * len(cal), "hi": ["2026-10-23", cs[-1] * 1.02]}, cal, 92.0)
    ck = {r[0]: r[2] for r in x["ck"]}
    assert ck == {"ey25": True, "eacc": True, "ry25": True, "racc": True, "gmd": True, "c33": True, "roe15": True}
    assert len(x["tt"]) == 8 and all(r[1] is True for r in x["tt"])
    t = x["tech"]
    assert t["px"] == round(cs[-1], 2) and t["m50"] == round(sum(cs[-50:]) / 50, 2) and t["rs"] == 92.0
    assert t["hi"] == round(cs[-1] * 1.02, 2) and t["lo"] == round(min(cs[-252:]), 2)
    g2 = _sx_rows((0.6, 0.4, 0.1), (0.3, 0.2, 0.1), (0.45, 0.42, 0.40), roe=0.05)
    cs2 = list(reversed(cs))                                                        # 一路跌
    y = UCP.sx_check(g2, {"c": cs2, "m": [None] * len(cal)}, cal, None)
    ck2 = {r[0]: r[2] for r in y["ck"]}
    assert ck2["ey25"] is False and ck2["eacc"] is False and ck2["c33"] is False and ck2["roe15"] is False
    assert ck2["gmd"] is False                                                       # 毛利率 0.40 比去年同一季 0.4 沒有高
    tt = dict(y["tt"])
    assert tt["股價在 50 日線之上"] is False and tt["強度 70 以上"] is None
    z = UCP.sx_check(None, {"c": [], "m": []}, cal, None)
    assert all(r[2] is None for r in z["ck"]) and z["tt"] == [] and z["tech"] == {}


def _run_fn(name, S, extra=""):
    """用 node 跑卡片的一段（ucSx／ucInd／ucCh），回純文字。"""
    js = UCP.JS
    names = ("ucMd", "ucPx", "ucPc", "ucDt", "ucMark", name)
    fns = ""
    for n in names:
        i = js.index(f"function {n}(")
        j = js.find("\nfunction ", i + 1)
        k = js.find("\n/*", i + 1)
        j = min(x for x in (j, k) if x > 0)
        fns += js[i:j] + "\n"
    prog = r"""
function f(x,d=1){if(x==null)return '—';return Number(x).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});}
function sgn(x,d=1,suf=''){if(x==null)return '—';const c=x>0?'up':x<0?'dn':'mu';return `<span class=${c}>${x>0?'+':''}${f(x,d)}${suf}</span>`;}
function pctT(x,d=1){return x==null?'—':(x>0?'+':x<0?'−':'')+f(Math.abs(x),d)+'%';}
function esc(s){return String(s??'');}
function mdw(d){return d?`${+d.slice(5,7)}/${+d.slice(8,10)}（W）`:'—';}
function kp(lbl,g,val,sub,c=''){return `[${lbl}:${val}${sub?'／'+sub:''}]`;}
const UCD={cal:['2026-10-23']};
@FNS@
@EXTRA@
process.stdout.write(@NAME@(@ARGS@));
""".replace("@FNS@", fns).replace("@EXTRA@", extra).replace("@NAME@", name).replace("@ARGS@", S)
    r = subprocess.run([NODE, "-e", prog], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.stdout)).replace("&amp;", "&")


@pytest.mark.skipif(not NODE, reason="沒有 node")
def test_sx_peer_chip_sections_text():
    g = _sx_rows((0.3, 0.4, 0.6), (0.2, 0.25, 0.3), (0.40, 0.42, 0.45))
    cal = _wd("2025-10-27", "2026-10-23")
    cs = [50.0 + 0.2 * i for i in range(len(cal))]
    sx = UCP.sx_check(g, {"c": cs, "m": [None] * len(cal)}, cal, 92.0)
    t = _run_fn("ucSx", json.dumps({"sx": sx}))
    assert "符合 8／8 項" in t and "趨勢樣板 8 項都符合（8／8）" in t and "均線多頭排列" in t
    assert "52 週低點" in t and "強度 92" in t
    assert "資料還沒有" in _run_fn("ucSx", "{}")
    peer = {"ind": "Oil & Gas Refining & Marketing", "sec": "Energy", "n": 9, "rk": 2, "d": "2026-10-28",
            "nm": {"MPC": "Marathon Petroleum"},
            "rows": [["MPC", 1289.8, 0.5383, 0.092, 0.4792, 15.1, 1.3333], ["VLO", 1227.4, 0.488, 0.0718, 0.2939, 17.0, 1.4218],
                     ["PBF", 93.9, None, None, None, None, None]]}
    t = _run_fn("ucInd", "'VLO'," + json.dumps({"fin": {"peer": peer}}))
    assert "GICS：Oil & Gas Refining & Marketing" in t and "這個細產業有 9 家，VLO 市值排第 2" in t
    assert "MPC Marathon Petroleum 1,290 +54% 9.2% 48% 15.1 +133%" in t and "PBF 93.9 — — — — —" in t
    assert "不在 S&P 500／400／600 裡" in _run_fn("ucInd", "'CDNA',{fin:{g:[]}}") and "每週六更新" in _run_fn("ucInd", "'X',{}")
    ch = UCP.chips({"sh": [0.0206, 2.4, 1.5e7, 1.2e7, "2026-09-30"], "mh": [0.18, 1.138, 1432.0],
                    "ns": ["6m", 12.0, 3.0e5, 30.0, 9.0e5, -6.0e5, -0.004],
                    "tx": [["2026-10-01", "XIE KEN", "CEO", "Sale at price 80.10 per share.", 5e4, 4.05e6]]})
    t = _run_fn("ucCh", json.dumps({"chip": ch}))
    assert "[做空占流通股:2.1%／回補要 2.4 天]" in t and "[做空股數:1,500 萬股／比上個月 +25%]" in t
    assert "[法人持股:113.8%／1,432 家]" in t and "法人持股超過 100%" in t and "做空資料到 2026/9/30" in t
    assert "取得 12 筆、30.0 萬股" in t and "賣出 30 筆、90.0 萬股；淨減少 60.0 萬股（內部人持股的 0.4%）" in t
    assert "XIE KEN CEO 賣出，每股 80.10 50,000 405.0" in t
    assert "資料還沒有" in _run_fn("ucCh", "{}")


@pytest.mark.skipif(not NODE, reason="沒有 node")
def test_analyst_rating_changes_and_eps_history_text():
    a = {"n": 19, "tp": [423.53, 435.0, 530.0, 238.0],
         "ud": [["2026-10-20", "Morgan Stanley", "main", "Overweight", "Overweight", 200.0, 230.0],
                ["2026-09-02", "Citi", "up", "Neutral", "Buy", 150.0, 210.0],
                ["2026-08-01", "UBS", "init", "", "Buy", None, 220.0]],
         "eh": [["2026-03-31", 1.3, 1.2], ["2026-06-30", 1.5, 1.6]]}
    t = _run_an({"px": 419.28, "an": a})
    assert "10/20 Morgan Stanley：維持 Overweight，目標價 200.00 調到 230.00" in t
    assert "9/2 Citi：調升 Neutral 改成 Buy，目標價 150.00 調到 210.00" in t
    assert "8/1 UBS：首次給評等 Buy，目標價 220.00" in t
    assert "近 2 季 EPS：實際和預估" in t and "2026/6/301.501.60-6%2026/3/311.301.20+8%" in t
