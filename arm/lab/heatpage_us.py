"""美股景氣頁 → dashboard/x9mu.html ＋ dashboard/x9muh-{指數}.json（docs/lab_heat_us_plan.md 第 3、7、15 節；規格 heatspec_us VER 1）。

一頁、上方切換「S&P 500｜那斯達克｜那斯達克 100｜費半」（使用者選定）。版面和台股頁同一套（heatpage）：
每個指數在 heatspec.use(美股規格) 與 heatpage.use_market(美股說法) 底下各產生一份內容，預設的指數直接放在頁面裡、
其他三個放在 <template>；切換時換上那一份內容、重跑對照圖的程式（heatpage._JS 的 heatInit），對照圖資料各指數一個檔、
點到才下載。基本面、情緒籌碼、資金四個指數共用（同一套資料），技術、泡沫依指數；驗證都用所選指數之後的漲跌。
輸出決定性：資料沒變時位元組相同。
"""
from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path

from . import heatcalc_us as CU
from . import heatchart as HC
from . import heatpage as HP
from . import heatspec as S
from . import heatspec_us as U

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dashboard" / "x9mu.html"
RES = ROOT / "data" / "lab" / "heat_us_research.json"
DEFAULT = "spx"


def data_name(idx: str) -> str:
    return f"x9muh-{idx}.json"


def _closed(d: date) -> bool:
    from ..usnews import _US_MKT_HOLIDAYS
    return d in _US_MKT_HOLIDAYS


# 美股項目的小數位數與正負號（台股頁的 DEC、SIGNED 換成這一份）
DEC = {"F1": 1, "F2": 2, "F3": 2, "F4": 1, "F5": 2, "F6": 1, "F7": 1, "F8": 1, "F9": 1, "F10": 1, "F11": 1,
       "S1": 1, "S2": 1, "S3": 1, "S4": 3, "S5": 1, "R1": 2, "R2": 2, "R3": 2, "R4": 2, "R5": 1, "R6": 2, "R7": 1,
       "R8": 1, "R9": 1, "R10": 3, "T1": 1, "T2": 1, "T3": 1, "T4": 1, "T8": 1, "T9": 1, "T11": 0, "T12": 2,
       "T13": 1, "T14": 1, "X1": 2, "X2": 1, "X3": 1, "X4": 2, "X5": 1, "X6": 1, "X7": 2, "X8": 1, "X9": 1,
       "X10": 2, "X11": 1}
SIGNED = {"F1", "F2", "F4", "F5", "F6", "F7", "F8", "F10", "F11", "S1", "S2", "S3", "S5", "R1", "R2", "R3", "R4",
          "R5", "R6", "R7", "R8", "R9", "T1", "T2", "T3", "T12", "T13", "T14", "X1", "X2", "X3", "X4", "X5", "X7",
          "X8", "X9", "X10", "X11"}
# 邊際變化的寫法：（一階叫什麼, 二階叫什麼, 一階單位, 二階單位）
DLABEL = {
    "F1": ("擴散指數", "比 3 個月前", "", ""),
    "F2": ("ADS 指數（月平均）", "比 3 個月前", "", ""),
    "F3": ("近 3 個月變化", "比前 3 個月的變化", "點", "點"),
    "F4": ("年增率", "比 3 個月前", "%", "個百分點"),
    "F5": ("離 12 個月低點", "比 3 個月前", "個百分點", "個百分點"),
    "F6": ("年增率", "比 3 個月前", "%", "個百分點"), "F7": ("年增率", "比 3 個月前", "%", "個百分點"),
    "F8": ("年增率", "比 3 個月前", "%", "個百分點"),
    "F9": ("近 3 個月變化", "比前 3 個月的變化", "點", "點"),
    "R7": ("年增率", "比 3 個月前", "%", "個百分點"),
    "S1": ("4 週變化", "比前 4 週的變化", "個百分點", "個百分點"),
    "S2": ("4 週變化", "比前 4 週的變化", "個百分點", "個百分點"),
    "R1": ("6 個月變化", "比 63 個交易日前", "個百分點", "個百分點"),
    "R2": ("60 日變化", "比 20 個交易日前", "個百分點", "個百分點"),
}
DVDEC = {"F1": 1, "F2": 2, "F3": 2, "F5": 2, "S1": 1, "S2": 1, "R1": 2, "R2": 2}
WHY: dict = {}

SRC_NOTE = ("指數、VIX、VXN、VIX3M、美元指數、HYG、IEF、RSP、SPY：Yahoo（只收收盤後的日線）；聯邦基金利率、公債殖利率、"
            "聯準會資產負債表、M2、Z.1：聯準會（DBnomics 轉載）與紐約聯準銀行；名目 GDP：BEA（DBnomics）；"
            "期貨部位：CFTC；製造業調查、ADS 每日景氣指數：費城聯準銀行；綜合領先指標：OECD；初領救濟金：美國勞工部（各州加總）；"
            "失業率、CPI：勞工統計局；消費者信心：密西根大學；超額債券溢酬：聯準會；股價、盈餘、股利的長歷史：Shiller（耶魯）；"
            "全球半導體銷售：WSTS；貨幣基金：OFR；台積電營收：公開資訊觀測站月營收。")

METHOD = (
    '<div class="mth"><p><b>分數怎麼來</b>：每一項和自己過去比——今天的值在過去 3 年（月資料 10 年、季資料 40 季、'
    '日資料的泡沫項目 10 年）裡排第幾（只用今天以前的資料），依「熱的方向」換成 0～100；PSY、趨勢偏離、LPPLS 有公認門檻，直接換算。'
    '面向分數＝該面向全部項目的 0～100 平均，有值的項數要有 2/3 以上。</p>'
    '<p><b>驗證只當參考，不拿來刪項目</b>：看分數和之後所選指數漲跌的等級相關（全期間＋95% 信賴區間），再把同一批樣本依日期切成前後兩半各算一次；'
    '全期間信賴區間不含 0、而且兩半方向一樣，才寫「熱了之後較弱」或「熱了之後較強」，其他寫「看不出穩定關係」。'
    '「對照」兩欄是 2000 年以前／以後，只列數字。S&P 500 的驗證從 1950 年起（分數用 1928 年起的資料暖身）。</p>'
    '<p><b>等級相關</b>：負數＝分數越高，之後漲幅越小；正數相反。數字都很小是正常的，這頁是參考讀數。</p>'
    '<p><b>限制</b>：ADS、OECD 領先指標、GDP 只有最新修正版，回測會比當時即時看到的準一些；盈餘、股利用 Shiller 的季報內插，'
    '延後 6 個月才算拿得到；期貨部位從 1986 年（資產管理人、VIX 期貨從 2006 年）、VIX3M 從 2006 年、VXN 從 2001 年、'
    '貨幣基金從 2010 年才有資料，歷史不夠的照樣列出，但要等排名有足夠的歷史才有 0～100。'
    'LPPLS 用網格搜尋、不做連續最佳化，文獻也指出參數範圍是事後挑的、假警報多。</p></div>')

METHOD5 = (
    '<div class="mth"><p><b>第五、六版的分析</b>（只當參考；規格在看結果之前寫定，規劃文件第 15 節）：</p>'
    '<p><b>歷史位置</b>：百分位＝比過去多少比例的日子（月資料是月份）高；近 3 年、近 10 年、有資料以來各算一次，只和今天以前比。</p>'
    '<p><b>跟著走還是領先</b>：每週一個樣本，今天的 0～100 和所選指數「之前」與「之後」5～250 日漲跌的等級相關。'
    '之前的相關明顯比之後大，代表這一項主要在反映指數已經走過的路。</p>'
    '<p><b>Granger 預測力</b>：每月一個樣本，扣掉指數自己過去 3 個月的報酬之後，這一項過去 3 個月的 0～100 能不能幫忙預測下個月的指數'
    '（異質變異穩健的 Wald 檢定）；泡沫以外的項目一起、泡沫項目一組、面向另一組做多重比較校正，q ≤ 0.10、前後兩半方向一樣才算。'
    '這是預測上的先後關係，不等於真正的因果。</p>'
    '<p><b>交互分析</b>：在對照圖選 2～5 條線，瀏覽器用每週的資料算各種組合之後指數的表現；週數 ≥ 26、段數 ≥ 4 才判定。'
    '組合試得越多，越容易碰到巧合。</p></div>')

PURP = ("美國經濟分五個面向看，各一個 0～100（100 最熱）：基本面、情緒籌碼、資金寬裕度、技術、泡沫。"
        "基本面、情緒籌碼、資金四個指數共用；技術、泡沫依所選指數各算一份，驗證都用所選指數之後的漲跌。"
        "每一項都和自己的過去比，面向分數＝該面向全部項目的平均。頁面只描述位置與過去的統計，怎麼操作由你判斷。")


def market(idx: str) -> dict:
    """某個指數的頁面說法（heatpage.use_market 換上）。"""
    nm = U.INDICES[idx]["name"]
    sp = f" {nm} " if nm[:1].isascii() else (f"{nm} " if nm[-1:].isascii() else nm)
    mk = {"tab": "us", "mkt": sp, "px": sp, "cmp": f"對照{sp}".rstrip(), "title": "美股景氣", "data": data_name(idx),
          "res": "data/lab/heat_us_research.json", "bull": f"{sp.lstrip()}在 10 個月均線之上", "hike": "聯準會 6 個月內升息",
          "purp": PURP, "closed": _closed, "pre": "", "switch": idx}
    return {"MK": mk, "DEC": DEC, "SIGNED": SIGNED, "DLABEL": DLABEL, "DVDEC": DVDEC, "WHY": WHY,
            "_SRC_NOTE": SRC_NOTE, "_METHOD": METHOD, "_METHOD5": METHOD5}


def load_research(path: Path = RES) -> dict:
    try:
        R = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return R if R.get("ver") == U.VER else {}


def index_page(idx: str, B: dict, R: dict) -> dict:
    """一個指數：→ {"nav", "body", "asof", "meta"}（在美股規格與說法底下產生）。"""
    with S.use(U.spec_for(idx)), HP.use_market(market(idx)):
        V = HP.view(B, R)
        P = HP.parts(V)
        P["meta"] = HP.meta()
    return P


def chart_data(idx: str, B: dict, R: dict) -> dict:
    """對照圖資料（S&P 500 從 1950 起，和驗證樣本一樣，檔案小一些）。"""
    with S.use(U.spec_for(idx)):
        V = CU.trim(B, S.VAL_START.get(idx))
        return HC.build_data(V, R)


SWITCH = ("<nav class=\"ixsw\" aria-label=\"指數\">" + "".join(
    f'<button type="button" data-ix="{k}">{html.escape(U.INDICES[k]["name"])}</button>' for k in U.INDEX_ORDER) + "</nav>")

SWITCH_JS = r"""
(function () {
'use strict';
const METAS = window.HEAT_METAS || {}, ASOF = window.HEAT_ASOF || {}, BOX = document.getElementById('ixc');
if (!BOX) return;
const live = BOX.dataset.ix, tpl = {};
document.querySelectorAll('template[data-ix]').forEach(t => { tpl[t.dataset.ix] = t; });
const keep = document.createElement('template');              // 預設指數在初始化之前先留一份乾淨的內容
keep.innerHTML = BOX.innerHTML;
tpl[live] = keep;
let cur = live;
function mark() {
  document.querySelectorAll('.ixsw button').forEach(b => {
    const on = b.dataset.ix === cur;
    b.classList.toggle('on', on);
    b.setAttribute('aria-pressed', on ? 'true' : 'false');
  });
  const a = document.getElementById('ix-asof');
  if (a && ASOF[cur]) a.textContent = '資料到 ' + ASOF[cur];
}
function show(ix, scroll) {
  if (!tpl[ix] || !METAS[ix]) return;
  if (ix !== cur) {
    BOX.replaceChildren(tpl[ix].content.cloneNode(true));
    BOX.dataset.ix = ix;
    cur = ix;
    window.HEAT_META = METAS[ix];
    if (window.heatInit) window.heatInit();
  }
  mark();
  if (scroll) window.scrollTo(0, 0);
}
document.querySelectorAll('.ixsw button').forEach(b => b.addEventListener('click', () => {
  show(b.dataset.ix, true);
  const ps = (location.hash || '').replace(/^#/, '').split('&').filter(x => x && x.split('=')[0] !== 'ix');   // 保留 #v=…（視角）
  ps.unshift('ix=' + b.dataset.ix);
  try { history.replaceState(history.state, '', '#' + ps.join('&')); } catch (e) { /* file:// */ }
}));
const m = /ix=(\w+)/.exec(location.hash || '');
window.HEAT_META = METAS[cur];
if (m && m[1] !== cur && tpl[m[1]]) show(m[1], false); else mark();
})();
"""

CSS = (".ixsw{display:flex;flex-wrap:wrap;gap:6px}"
       ".ixsw button{border:1px solid var(--line);background:var(--bg);color:var(--ink2);border-radius:999px;"
       "padding:5px 13px;font-size:13.5px;font-weight:600;cursor:pointer}"
       ".ixsw button.on{background:var(--acc);border-color:var(--acc);color:var(--bg)}"
       "@media (max-width:640px){.ixsw button{padding:5px 10px;font-size:13px}}")

_HTML = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<link rel="icon" href="data:,">
<title>美股景氣</title>
<style>{{CSS}}</style></head>
<body>
<div class="top">{{APPTAB}}<span class="asof" id="ix-asof">資料到 {{ASOF}}</span><a class="back" href="./">返回主頁</a></div>
<div class="vbar">{{SWITCH}}{{VSW}}<details class="purp"><summary>這頁怎麼看</summary><p>{{PURP}}</p></details></div>
<div id="ixc" data-ix="{{IX}}">{{LIVE}}</div>
{{TEMPLATES}}
{{DRAWER}}
<script>window.HEAT_METAS={{METAS}};window.HEAT_ASOF={{ASOFS}};</script>
<script>{{SWITCH_JS}}</script>
<script>{{JS}}</script>
</body></html>
"""


def _content(P: dict) -> str:
    return f'<main>{P["body"]}</main>'


def render(pages: dict, default: str = DEFAULT) -> str:
    """pages＝{指數: index_page(...)} → 整頁。"""
    from . import appnav
    from . import heatviz as VZ
    j = lambda x: json.dumps(x, ensure_ascii=False, separators=(",", ":"), sort_keys=True).replace("</", "<\\/")  # noqa: E731
    tpls = "".join(f'<template data-ix="{k}">{_content(pages[k])}</template>' for k in U.INDEX_ORDER if k != default and k in pages)
    with HP.use_market(market(default)):
        asofs = {k: HP._md(P["asof"]) for k, P in pages.items()}
        purp = HP._e(PURP)
    from . import crashpage as CP
    return (_HTML.replace("{{CSS}}", HP._CSS + appnav.CSS + VZ.CSS + CP.CSS + CSS).replace("{{APPTAB}}", appnav.bar("us"))
            .replace("{{VSW}}", VZ.switch_html()).replace("{{DRAWER}}", VZ.DRAWER)
            .replace("{{ASOF}}", HP._e(asofs.get(default, "—"))).replace("{{PURP}}", purp)
            .replace("{{SWITCH}}", SWITCH).replace("{{IX}}", default).replace("{{LIVE}}", _content(pages[default]))
            .replace("{{TEMPLATES}}", tpls).replace("{{METAS}}", j({k: P["meta"] for k, P in pages.items()}))
            .replace("{{ASOFS}}", j(asofs)).replace("{{SWITCH_JS}}", SWITCH_JS).replace("{{JS}}", VZ.JS + HP._JS))


def build(out: Path = OUT, data_dir: Path | None = None) -> bool:
    """建美股景氣頁與四個對照圖資料檔；內容都沒變時不改寫。"""
    data_dir = data_dir or out.parent
    D = CU.load()
    SH = CU.shared(D)
    RA = load_research()
    pages, changed = {}, False
    for idx in U.INDEX_ORDER:
        B = CU.build(idx, D, SH)
        R = ((RA.get("idx") or {}).get(idx)) or {}
        pages[idx] = index_page(idx, B, R)
        changed = HC.write(chart_data(idx, B, R), data_dir / data_name(idx)) or changed
    return HP._write(out, render(pages)) or changed
