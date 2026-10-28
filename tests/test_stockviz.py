"""個股頁（x9.html）視覺化改版：深淺配色、行動時間軸、主動 ETF 資金地圖、飆股位置圖（docs/lab_visual_plan.md 第 10 節）。

只改呈現：資料全來自頁面已有的 D（rows、adv、wl）。這裡守四件事——
①顏色都走主題變數（淺色、深色各一組），圖表程式裡寫死的顏色都在對照表裡；
②三張圖確實接到機會、籌碼、飆股段，而且三支 JS（page、stockviz、copage）沒有同名函式或常數；
③瀏覽器端的小工具（樹狀圖切格、字色、數字格式、位置分類）用 node 實際跑；
④用字不碰禁用詞。
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from arm.lab import copage, page, stockviz

BANNED = ("保證", "穩賺", "必賺", "包賺", "必漲", "必跌", "一定會", "建議買賣", "建議買",
          "建議賣", "目標價", "零風險", "無風險", "穩賺不賠")


def _blocks():
    css = page._CSS
    i = css.index("@media (prefers-color-scheme:dark)")
    light, dark = css[css.index(":root{"):i], css[i:css.index("}}", i)]
    tok = lambda s: dict(re.findall(r"--([a-z0-9]+):([^;}]+)", s))
    return tok(light), tok(dark)


def test_theme_tokens_light_and_dark():
    light, dark = _blocks()
    assert "color-scheme:light dark" in page._CSS
    assert set(dark) <= set(light)                     # 深色只覆蓋淺色已有的變數
    # 三張圖用到的顏色變數，淺色、深色都要有
    used = set(re.findall(r"var\(--([a-z0-9]+)\)", stockviz.CSS)) | set(re.findall(r"vzVar\('--([a-z0-9]+)'\)", stockviz.JS))
    assert used, "stockviz 沒有用主題變數"
    assert not used - set(light), used - set(light)
    assert not used - set(dark), used - set(dark)
    assert light["vio"] == "#7b5ea7" and dark["vio"] == "#997ac9"
    # 整頁（page、copage、appnav、stockviz）引用的變數都有定義
    from arm.lab import appnav
    every = page._CSS + copage.CSS + appnav.CSS + stockviz.CSS + page._JS + copage.JS + stockviz.JS
    refs = set(re.findall(r"var\(--([a-z0-9]+)\)", every))
    assert not refs - set(light), refs - set(light)


def test_hardcoded_colors_are_mapped_to_tokens():
    """圖表程式寫死的顏色：page 與 copage 的都要在 THEME_HEX（換成主題色）或 THEME_KEEP（深色提示框裡的紅綠字）；
    stockviz 只允許資金地圖格子上的白字與深字（依對比挑，深淺模式都一樣）。"""
    hexes = lambda s: {h.lower() for h in re.findall(r"#[0-9a-fA-F]{6}\b", s)}
    known = set(page.THEME_HEX) | set(page.THEME_KEEP)
    assert not hexes(page._JS + copage.JS) - known, hexes(page._JS + copage.JS) - known
    assert hexes(stockviz.JS) <= {"#ffffff", "#1f2733"}
    light, dark = _blocks()
    for h, t in page.THEME_HEX.items():
        assert t in light and t in dark, (h, t)
    css = page.theme_css()
    assert css.count("svg [fill=") == len(page.THEME_HEX) and 'svg [fill="#d33a34"]{fill:var(--gain)}' in css


def _defs(js: str):
    fn = re.findall(r"(?m)(?:^|[;}])\s*function\s+([A-Za-z_$][\w$]*)\s*\(", js)
    top = re.findall(r"(?m)^(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=", js)
    return fn, top


def test_three_scripts_have_no_name_collisions():
    """五支 JS 串成同一個 <script>：同名函式會被後面的蓋掉（2026-10-18 位置圖原本叫 sxSec，和飆股段既有的 sxSec 撞名），
    同名的頂層 const／let 會讓整頁報錯。macpage＝總經策略（2026-10-22，docs/lab_strategy_ia_plan.md）；
    cfgpage＝配置頁（2026-10-23，docs/lab_ia_v5_plan.md 第 18 節）；uscardpage＝美股個股卡（2026-10-24）；pickpage＝選股頁（2026-10-28）。"""
    from arm.lab import macpage
    names = {}
    from arm.lab import cfgpage, pickpage, uscardpage
    for nm, js in (("page", page._JS), ("stockviz", stockviz.JS), ("macpage", macpage.JS), ("cfgpage", cfgpage.JS),
                   ("pickpage", pickpage.JS), ("uscardpage", uscardpage.JS), ("copage", copage.JS)):
        fn, top = _defs(js)
        for n in fn + top:
            names.setdefault(n, []).append(nm)
    dup = {n: w for n, w in names.items() if len(w) > 1}
    assert not dup, dup


def test_charts_wired_into_opp_chip_and_watchlist():
    html = page.render({"rows": [], "asof": {}})
    assert stockviz.CSS in html
    js = html[html.index("<script>"):]
    # stockviz、macpage（總經策略）在 copage 前面、頁面初始化之前（初始化依網址開分頁，這時函式與 VZS、TLM 必須已經定義）
    from arm.lab import macpage
    i_vz, i_mac, i_co, i_init = js.index("const VZS="), js.index("const MAC=D.mac||{}"), js.index(copage.JS[:200]), js.index("go(v,at);")
    assert i_vz < i_mac < i_co < i_init and macpage.CSS in html
    assert "/*@@COPAGE@@*/" not in html
    for f in ("function tlDraw(", "function mmDraw(", "function spotDraw(", "function sxSec(", "function vMac(", "function vMacSt("):
        assert js.count(f) == 1, f
    # 機會：摘要＝四格數字＋下一個交易日＋時間軸，文字版時間表收在展開
    assert "oSum()+tlNext()+tlSec()+`<details class=mr><summary>逐筆時間表（文字）</summary>${oTl()}</details>`" in page._JS
    v_opp = page._JS[page._JS.index("function vOpp("):]
    assert "$('#main').innerHTML=h;tlDraw();spotDraw();" in v_opp[:v_opp.index("\n}\n")]
    # 籌碼：資金地圖在最上面
    v_chip = page._JS[page._JS.index("function vChip("):page._JS.index("function vChip(") + 6000]
    assert v_chip.index("h+=mmSec();") < v_chip.index("sec('c-lead'")
    assert "$('#main').innerHTML=h;mmDraw();" in v_chip
    # 飆股段：一行摘要之後接位置圖
    wl = copage.JS[copage.JS.index("function wlSec("):]
    assert wl.index("b+=spotSec();") < wl.index("<h4 class=sh>到買點")
    # 寬度改變才重畫，三張圖都重畫（總經策略的時間軸也是）
    assert "tlDraw();if(typeof TLM!=='undefined')tlDraw(TLM);mmDraw();spotDraw();" in stockviz.JS
    # 時間軸吃設定：個股策略 TLO（原本寫死的部分）、總經策略 TLM（macpage.py）
    assert "function tlDraw(Q){Q=Q||TLO;" in stockviz.JS and "const TLO={box:'tlbox',tip:'tltip',rk:'tl'" in stockviz.JS
    assert "const TLM={box:'xmtlbox',tip:'xmtltip',rk:'mtl'" in macpage.JS and "tlDraw(TLM);" in macpage.JS


def test_no_banned_words_in_charts():
    text = stockviz.CSS + stockviz.JS
    assert not [w for w in BANNED if w in text]


# ── 瀏覽器端小工具（node 實際跑） ─────────────────────────────────────

_STUB = """globalThis.document={addEventListener(){},documentElement:{}};globalThis.addEventListener=()=>{};globalThis.innerWidth=1200;
globalThis.$$=()=>[];globalThis.$=()=>null;globalThis.f=(v,d)=>Number(v).toFixed(d);"""


def _node(body: str):
    prog = _STUB + stockviz.JS + "\n" + body
    r = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="沒有 node")
def test_squarify_fills_rect_in_proportion():
    out = _node("""const v=[50,30,10,5,5],R=vzSq(v.map(x=>({v:x})),10,20,300,200);
console.log(JSON.stringify(R.map(r=>[r.o.v,r.x,r.y,r.w,r.h])));""")
    assert len(out) == 5
    tot = sum(w * h for _, _, _, w, h in out)
    assert abs(tot - 300 * 200) < 1e-6
    for v, x, y, w, h in out:
        assert abs(w * h / tot - v / 100) < 1e-9
        assert 10 - 1e-9 <= x and x + w <= 310 + 1e-9 and 20 - 1e-9 <= y and y + h <= 220 + 1e-9
    # 格子彼此不重疊
    for i, a in enumerate(out):
        for b in out[i + 1:]:
            ox = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
            oy = min(a[2] + a[4], b[2] + b[4]) - max(a[2], b[2])
            assert ox <= 1e-9 or oy <= 1e-9


@pytest.mark.skipif(shutil.which("node") is None, reason="沒有 node")
def test_cell_ink_value_format_and_position_class():
    out = _node("""console.log(JSON.stringify({
  ink:['#d33a34','#f2665c','#f4f6fa','#182234','#3fbf7a','#1f9d57'].map(h=>vzInk(vzRgb(h))),
  val:[mmVal({a5v:0.04},'a5v'),mmVal({a5v:-0.04},'a5v'),mmVal({a5v:2.36},'a5v'),mmVal({a5v:-42.2},'a5v'),
       mmVal({t5:-0.4},'t5'),mmVal({t5:1234.4},'t5'),mmVal({rs20:3.25},'rs20'),mmVal({},'a5v')],
  cls:[spotCls([0,'',0,100],{st:1,hi:120},false),spotCls([0,'',0,100],{st:3,hi:120},false),spotCls([0,'',0,100],{st:5,hi:100},true),
       spotCls([0,'',0,100],{st:4,hi:110},true),spotCls([0,'',0,100],{st:0,hi:109},true),spotCls([0,'',0,100],{st:0,hi:111},true),
       spotCls([0,'',0,100],{st:0,hi:105},false),spotCls([0,'',0,100],{},true)],
  avg:[tlAvg({items:[{now_r:2},{now_r:-1},{now_r:null}]}),tlAvg({items:[]})]
}));""")
    # 字色取對比較高的一個：Python 獨立照 WCAG 公式算一次對照
    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    ink = lambda h: "#ffffff" if 1.05 / (lum(h) + 0.05) >= (lum(h) + 0.05) / (lum("#1f2733") + 0.05) else "#1f2733"
    cols = ["#d33a34", "#f2665c", "#f4f6fa", "#182234", "#3fbf7a", "#1f9d57"]
    assert out["ink"] == [ink(h) for h in cols]
    assert out["ink"][:2] == ["#ffffff", "#1f2733"]     # 淺色的漲（深紅）白字、深色的漲（亮紅）深字
    # 四捨五入後是 0 不帶正負號（原本會出現「+0.0 億」「-0.0 億」）
    assert out["val"] == ["0.0 億", "0.0 億", "+2.4 億", "-42.2 億", "0 張", "+1234 張", "+3.3 pp", "—"]
    # 到買點（1～3）／漲太遠（5）／突破失敗（4）／快到買點（強勢、打底中、還差 10% 內）／其他
    assert out["cls"] == ["buy", "buy", "far", "fail", "near", "base", "base", "base"]
    assert out["avg"] == [0.5, None]


@pytest.mark.skipif(shutil.which("node") is None, reason="沒有 node")
def test_rendered_page_script_parses():
    html = page.render({"rows": [], "asof": {}})
    js = re.findall(r"<script>(.*?)</script>", html, re.S)[-1]
    r = subprocess.run(["node", "--check", "-"], input=js, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-1500:]
