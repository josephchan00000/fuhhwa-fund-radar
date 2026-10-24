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
    assert f"占全部資金 {CPG._wp(G['rows'][0]['w'])}" in st and _has(v["st"], "8/31（一）買進 359.88，現在 419.28（+16.5%）")
    assert "收盤跌破 50 日線，就在下一個交易日開盤賣" in st and "50 日線現在" in st
    assert v["ent"] == ["2026-08-31", pytest.approx(419.26 / 1.165)] and v["out"] is None
    w = v["why"]
    assert "買進時" in w and "8/28 那週" in w and "10/23 那週" in w and w.count('class="ucok"') == 10   # 兩欄、五個都過
    assert "10/23 那週的名單第 1 名（共 4 檔）" in _text(w)
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
    fns = "".join(js[js.index(f"function {n}("):js.index("\n", js.index(f"function {n}("))] + "\n" for n in ("ucMd", "ucPx"))
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
    for s in ("data-us", "#us=", "function ucRender(", "function ucSvg(", "id=uc-st", "id=uc-why", "id=uc-px", "id=uc-an", "id=uc-co"):
        assert s in UCP.JS, s
    for col in ("#2563c9", "#f59e0b", "#d33a34", "#1f9d57", "#e3e7ec", "#727e8c", "#9aa5b1"):   # 深色模式換色（page.THEME_HEX）
        if col in UCP.JS:
            assert col in page.THEME_HEX, col
    if NODE:
        r = subprocess.run([NODE, "--check", "-"], input=UCP.JS, capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr


def test_core_data_carries_card(monkeypatch):
    """配置頁的卡片資料從 sigpage.core_data 的 qm["C"] 來（uscard.load）。"""
    from arm.lab import sigpage
    src = open(sigpage.__file__, encoding="utf-8").read()
    assert '"C": UC.load()' in src
