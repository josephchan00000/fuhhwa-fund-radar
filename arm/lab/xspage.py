"""大神策略頁（dashboard/x9x.html＋淨值與每一筆 x9xh.json；docs/lab_nav_plan.md）。

2026-10-21 使用者：「大神策略是放在訊號那邊而已嗎？這樣很難找欸」→ 頂欄多一頁（規劃第 2.1 節）。由上而下：
  接下來要做的（★ 好策略、● 可參考：兩週內照規則要買賣的、現在有部位的；判定沒過的收起來）
  → 全部策略（每列一條策略、每欄一個市場：判定＋現在的狀態）→ 判定方式 → 其他買賣規則的連結。
點一條打開右側面板（xstratpage.PANEL_JS，和訊號總覽同一個）；網址 #i=xs:市場:策略 直接打開。
成績與現在的狀態每天建頁時算（xstrat.run_all，程序內快取）。只描述照規則做過去的成績，不寫建議。
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from . import xstratpage as XSP
from . import xstratspec as S
from .heatpage import _e

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dashboard" / "x9x.html"
OUT_DATA = ROOT / "dashboard" / "x9xh.json"
SOON = 14                                                 # 「接下來要做的」列幾天內排定的買賣（日曆天）
GRP_TXT = {"short": "急跌之後買、反彈就賣，一次抱幾天。",
           "bottom": "大跌之後出現訊號就買，抱原作者說的期間（1 個月～1 年）。",
           "season": "照日曆買賣：月底月初、每年 11～4 月。",
           "risk": "照均線或動能決定持有或空手，大跌時少跌。"}
MK_SHORT = {"tw": "台股", "spx": "S&P", "ixic": "那指", "ndx": "那100", "sox": "費半"}   # 手機的欄名
WHO = {"rsi2": "Connors", "vixs": "Connors", "tom": "Lakonishok、Smidt", "coppock": "Coppock", "vix40": "常見的恐慌買點",
       "zweig": "Zweig", "ftd": "O'Neil", "dev60": "台股常用", "mmr": "台股常用", "mflush": "台股常用", "lowry": "Lowry Research",
       "hal": "Bouman、Jacobsen", "faber": "Faber", "ma200": "Gordon、Siegel", "mom12": "Antonacci"}   # 總表的小字（出處的簡稱）
WD = "一二三四五六日"


def view(R: dict | None = None) -> dict:
    R = XSP.results() if R is None else R
    asof = {mk: max(r["now"]["d"] for r in M.values()) for mk, M in R.items() if M}
    return {"R": R, "asof": asof}


def _md(d: str | None) -> str:
    return f"{int(d[5:7])}/{int(d[8:10])}" if d else ""


def _mdw(d: str) -> str:
    return f"{_md(d)}（{WD[date.fromisoformat(d).weekday()]}）"


def kind_of(st: str) -> str:
    """狀態的三種：a＝要動作、h＝有部位、f＝沒有部位（顏色用）。"""
    if st in XSP.ACT:
        return "a"
    return "h" if st in XSP.HELD else "f"


def due(r: dict) -> tuple[str, str] | None:
    """下一個照規則要做的事：(日期, 買／賣／可能買)。沒有排定、也沒有訊號 → None。"""
    n, k = r["now"], r["k"]
    st = n["st"]
    if k == "tom":
        if st in ("buy", "wait"):
            return (n["ed"], "買") if n.get("ed") else None
        return (n["qd"], "賣") if n.get("qd") else None
    if k == "hal":
        if not n.get("sw"):
            return None
        return n["sw"], ("買" if st in ("turn_in", "out") else "賣")
    if not n.get("nx"):
        return None
    if r["kind"] == "dip":
        if st == "buy":
            return n["nx"], "買"
        return (n["qd"], "賣") if st == "hold" and n.get("qd") else None
    if st in ("buy", "turn_in"):
        return n["nx"], "買"
    if st in ("sell", "turn_out"):
        return n["nx"], "賣"
    if st == "near":
        return n["nx"], "可能買"
    return None


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def plan(R: dict) -> dict:
    """接下來要做的：{"todo": [(日期, 動作, 市場, 策略, r)], "held": {市場: [(策略, r)]}, "low": [(市場, 策略, r, 日期或 None)]}。
    todo＝★、● 而且（現在有訊號，或 SOON 天內排定要買賣）；held＝★、● 現在有部位、沒有列在 todo 的；
    low＝判定沒過（○、—）而且現在有訊號或有部位的（收起來）。"""
    todo, held, low = [], {}, []
    for mk in S.MARKETS:
        M = R.get(mk) or {}
        for s in S.STRATS:
            r = M.get(s["k"])
            if not r:
                continue
            st, d0 = r["now"]["st"], r["now"]["d"]
            q = due(r)
            soon = q is not None and q[0] and (st in XSP.ACT or _days(d0, q[0]) <= SOON)
            if r["tier"] not in ("good", "ref"):
                if st in XSP.ACT or st in XSP.HELD:
                    low.append((mk, s["k"], r, q[0] if soon else None))
                continue
            if soon:
                todo.append((q[0], q[1], mk, s["k"], r))
            elif st in XSP.HELD:
                held.setdefault(mk, []).append((s["k"], r))
    order = {k: i for i, k in enumerate(s["k"] for s in S.STRATS)}
    mko = {mk: i for i, mk in enumerate(S.MARKETS)}
    todo.sort(key=lambda t: (t[0], mko[t[2]], order[t[3]]))
    return {"todo": todo, "held": held, "low": low}


def _tag(st: str) -> str:
    return f'<span class="xpt xpt-{kind_of(st)}">{_e(XSP.TAG[st])}</span>'


def _mark(t: str) -> str:
    return f'<span class="sgtk sgtk-{t}" title="{_e(S.TIER_NAMES[t])}">{S.TIER_MARK[t]}</span>'


def _item(mk: str, k: str, r: dict, d: str | None = None, verb: str = "", mkt: bool = True, res: bool = True) -> str:
    """一條策略一列：（日期與動作）市場、判定、名稱、狀態，下面一行現在的說明（res＝再加一行過去的成績）。"""
    sid = f"xs:{mk}:{k}"
    sp = S.BY_KEY[k]
    head = (f'<span class="xpd">{_e(_mdw(d))}{_e(verb)}</span>' if d else "") + \
           (f'<span class="xpmk">{_e(XSP.MK_NAMES[mk])}</span>' if mkt else "")
    rl = f'<span class="sgs">{_e(XSP.result_line(r))}</span>' if res else ""
    return (f'<li><a class="xpi" href="#i={_e(sid)}" data-k="{_e(sid)}">{head}{_mark(r["tier"])}<b>{_e(sp["name"])}</b>'
            f'{_tag(r["now"]["st"])}<span class="xpl">{_e(XSP.now_text(r))}{rl}</span></a></li>')


def next_html(V: dict) -> str:
    R = V["R"]
    P = plan(R)
    if P["todo"]:
        todo = '<ul class="xpn">' + "".join(_item(mk, k, r, d, verb) for d, verb, mk, k, r in P["todo"]) + "</ul>"
    else:
        todo = f'<p class="note">★ 好策略、● 可參考的策略，下一個交易日都沒有訊號，{SOON} 天內也沒有排定的買賣。</p>'
    cards = []
    for mk in S.MARKETS:
        if mk not in V["asof"]:
            continue
        it = P["held"].get(mk) or []
        body = ('<ul class="xpn">' + "".join(_item(mk, k, r, mkt=False, res=False) for k, r in it) + "</ul>") if it else \
            '<p class="note">沒有部位。</p>'
        cards.append(f'<div class="sgk xpk"><h3>{_e(XSP.MK_NAMES[mk])}<span class="sub">資料到 {_e(_md(V["asof"][mk]))}</span></h3>{body}</div>')
    low = ""
    if P["low"]:
        lis = "".join(_item(mk, k, r, d, (due(r) or ("", ""))[1] if d else "") for mk, k, r, d in P["low"])
        low = (f'<details class="xplo"><summary>判定沒過（○ 不推薦、— 次數不夠）的策略，現在有訊號或有部位的 {len(P["low"])} 條</summary>'
               f'<p class="note">照規則過去的成績沒有過關，只列出來對照。</p><ul class="xpn">{lis}</ul></details>')
    return ('<section class="sec" id="next"><h2>接下來要做的<span class="sub">★ 好策略、● 可參考；日期是照規則買賣的那一天（收盤）</span></h2>'
            f'<h3 class="xph">要做的<span class="sub">下一個交易日有訊號，或 {SOON} 天內排定要買賣</span></h3>{todo}'
            '<h3 class="xph">現在的部位<span class="sub">照規則現在抱著的（上面已經列的不重複）</span></h3>'
            f'<div class="sgt">{"".join(cards)}</div>{low}</section>')


def _cell(mk: str, k: str, r: dict | None) -> str:
    h = f' data-h="{_e(MK_SHORT[mk])}"'
    if not r:
        return f'<td class="xpc xpna"{h}><span>不適用</span></td>'
    sid = f"xs:{mk}:{k}"
    st, t = r["now"]["st"], r["tier"]
    lo = "" if t in ("good", "ref") else " xplow"
    return (f'<td class="xpc{lo}"{h} data-k="{_e(sid)}"><a href="#i={_e(sid)}" title="{_e(XSP.now_text(r))}">'
            f'{_mark(t)}{_tag(st)}<small>{_e(XSP.now_short(r))}</small></a></td>')


def matrix_html(V: dict) -> str:
    R = V["R"]
    mks = [mk for mk in S.MARKETS if mk in V["asof"]]
    head = '<thead><tr><th class="l">策略</th>' + "".join(
        f'<th>{_e(XSP.MK_NAMES[mk])}<small>{_e(_md(V["asof"][mk]))}</small></th>' for mk in mks) + "</tr></thead>"
    body = []
    for g in S.GROUP_ORDER:
        ss = [s for s in S.STRATS if s["grp"] == g and any(s["k"] in (R.get(mk) or {}) for mk in mks)]
        if not ss:
            continue
        body.append(f'<tbody><tr class="xpg"><th colspan="{len(mks) + 1}">{_e(S.GROUPS[g])}<span>{_e(GRP_TXT[g])}</span></th></tr>')
        for s in ss:
            who = WHO.get(s["k"]) or s["who"]
            body.append(f'<tr><th class="l xpsn"><b>{_e(s["name"])}</b><small>{_e(who)}・{_e(S.KINDS[s["kind"]])}</small></th>'
                        + "".join(_cell(mk, s["k"], (R.get(mk) or {}).get(s["k"])) for mk in mks) + "</tr>")
        body.append("</tbody>")
    legend = ('<p class="note xpleg">' + "　".join(f'{_mark(t)} {_e(S.TIER_NAMES[t])}' for t in S.TIERS)
              + '　｜　<span class="xpt xpt-a">要動作</span> 下一個交易日照規則買賣或接近訊號'
              '　<span class="xpt xpt-h">有部位</span> 現在照規則抱著　<span class="xpt xpt-f">沒有部位</span> 沒有訊號、空手</p>')
    return ('<section class="sec" id="all"><h2>全部策略<span class="sub">每列一條策略、每欄一個市場；點一格看規則、現在、過去的成績與每一筆</span></h2>'
            f'{legend}<div class="sgwrap xpw"><table class="xpm">{head}{"".join(body)}</table></div>'
            '<p class="note">「不適用」＝那個市場沒有這種資料（例：VIX 是美股的波動指數、融資維持率只有台股）。'
            '格子裡的小字是現在的關鍵數字（手機上不顯示），點一格看完整的說明。</p></section>')


def method_html() -> str:
    return ('<section class="sec" id="mth"><details class="sgmth"><summary>判定方式</summary><dl class="sgdl2">'
            '<dt>大神策略是什麼</dt><dd>寫在書上、論文裡的買賣規則，照原作者的規則與參數在指數上做一遍，看過去照做的交易成績。'
            '參數沒有調（少數原作者沒寫的地方，面板裡「出處」那一行會寫是這裡定的）。</dd>'
            f'<dt>交易型（短線、月底月初）</dt><dd>至少 {S.TR_N_MIN} 筆、勝率 ≥ {S.TR_WIN * 100:.0f}%、比「隨便挑一天、抱一樣多天」'
            f'高 {S.TR_EDGE * 100:.0f} 個百分點以上、扣成本後平均每筆賺錢。</dd>'
            f'<dt>落底型</dt><dd>訊號出現隔天收盤買、抱原作者說的期間（1 個月～1 年）：至少 {S.DIP_N_MIN} 次、抱完賺錢的比例 ≥ {S.DIP_WIN * 100:.0f}%，'
            f'而且兩條過一條：賺錢的比例比隨便挑一天高 {S.DIP_EDGE * 100:.0f} 個百分點以上、中位數扣成本後賺錢；或報酬中位數至少是隨便挑一天的 '
            f'{S.DIP_MED_X:g} 倍、而且多 {S.DIP_MED_ADD * 100:.0f} 個百分點（2026-10-22 起：落底訊號常常強在賺得多，'
            '台股隨便挑一天抱一年就有七成會賺，只看賺錢機率比不出來）。</dd>'
            '<dt>進出型（風險控制、Halloween）</dt><dd>最大回撤比一直持有少三分之一以上，而且年化 ÷ 最大回撤不輸一直持有。</dd>'
            '<dt>★ 好策略、● 可參考</dt><dd>★＝全期間、近 10 年、參數鄰近（換附近的參數，三分之二以上也過關）都過；●＝全期間過、後兩項沒過；'
            '○ 不推薦＝全期間沒過；— 次數不夠。打亂測試（把買進日整段挪開，看做不做得到一樣好）只標示、不影響判定（使用者 2026-10-20 選定）。</dd>'
            '<dt>什麼時候買賣</dt><dd>看收盤才知道的訊號一律隔天收盤買賣（看網頁做得到的最早時點），原作者的當天收盤另列參考；'
            '台股 RSI(2) 用台指期在訊號當天收盤前買賣（現貨 13:30 收盤、台指期 13:45 收盤），頁面每天寫下一個交易日的買進、出場價位。'
            '月底月初、Halloween 是日曆排定的，照那天收盤。</dd>'
            '<dt>成本與價格</dt><dd>台股 ETF 每買或賣一次 0.1%（台股 RSI(2)、月底月初用台指期約 0.005%），美股 0.025%。'
            '價格是指數本身、不含股息，空手不算利息。</dd>'
            f'<dt>規格</dt><dd>arm/lab/xstratspec.py（VER {S.VER}），在算正式成績之前寫定；改規則要升版本。</dd></dl></details></section>')


def links_html() -> str:
    return ('<section class="sec" id="more"><h2>其他買賣規則</h2><ul class="xpln">'
            '<li><a href="x9o.html#r=tw:bottom">大跌之後怎麼買（我們自己的落底規則：大跌後檢查）→</a></li>'
            '<li><a href="x9.html">個股策略（財報驚喜、月營收驚喜、共識加碼…）：個股頁「機會」→</a></li>'
            '<li><a href="x9o.html">訊號（某個狀態出現之後，上漲或大跌的機率）：訊號總覽 →</a></li></ul></section>')


_HTML = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<link rel="icon" href="data:,">
<title>大神策略</title>
<style>{{CSS}}</style></head>
<body>
<div class="top">{{APPTAB}}<span class="asof">{{ASOF}}</span><a class="back" href="./">返回主頁</a></div>
<div class="vbar"><details class="purp"><summary>這頁怎麼看</summary><p>大神策略＝寫在書上、論文裡的買賣規則（RSI(2)、Coppock 曲線、10 個月均線…），
照原作者的參數在五個指數上做一遍，看過去照做的成績。上面是接下來照規則要買賣的、現在有部位的；下面的總表每列一條策略、每欄一個市場，
點一格看規則、現在、過去的成績、照做的淨值與每一筆。★ 好策略＝成績過關、近 10 年與附近的參數也成立；● 可參考＝全期間過關、後兩項沒過。
這些是照規則在歷史上做一遍的結果，只描述過去。</p></details></div>
<main>{{BODY}}</main>
<div class="sgpv" id="sgpv" hidden><div class="sgpb" id="sgpb"></div><aside class="sgp" id="sgp" role="dialog" aria-labelledby="sgpt" tabindex="-1"></aside></div>
<script type="application/json" id="xsd">{{DATA}}</script>
<script>{{JS}}</script>
</body></html>
"""

CSS = """
.xph{font-size:15px;margin:14px 0 6px}.xph .sub{font-weight:400;font-size:12px;color:var(--mut);margin-left:6px}
.xpn{list-style:none;margin:0;padding:0}.xpn li+li{border-top:1px solid var(--line)}
.xpi{display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 6px;padding:7px 0;color:var(--ink);text-decoration:none}
.xpi:hover b{text-decoration:underline}.xpi b{font-weight:600;font-size:14px}
.xpd{font-weight:700;font-size:13px;color:var(--acc);white-space:nowrap}
.xpmk{font-size:12px;color:var(--ink2);padding:0 7px;border-radius:6px;background:var(--card2);white-space:nowrap}
.xpl{flex:1 1 100%;font-size:12.5px;line-height:1.6;color:var(--ink2);padding-left:20px}.xpl .sgs{display:block;margin-left:0;font-size:11.5px}
.xpt{font-size:11.5px;padding:0 7px;border-radius:999px;border:1px solid var(--line2);white-space:nowrap;line-height:1.5}
.xpt-a{color:var(--acc);border-color:var(--acc);background:var(--accbg);font-weight:600}
.xpt-h{color:var(--ink);background:var(--card2)}.xpt-f{color:var(--mut);border-color:var(--line)}
.xpk .xpn li{padding:0}.xpk .xpl{padding-left:20px}
.xplo{margin:12px 0 0}.xplo>summary{cursor:pointer;color:var(--acc);font-size:13px}
.xpleg{line-height:2}
.xpm{width:100%;border-collapse:collapse;font-size:13px}
.xpm thead th{font-weight:600;color:var(--ink2);padding:5px 6px;border-bottom:1px solid var(--line2);text-align:center;white-space:nowrap}
.xpm thead th small{display:block;font-weight:400;font-size:11px;color:var(--mut)}
.xpm th.l{text-align:left}
.xpm tr.xpg th{text-align:left;font-size:13.5px;padding:12px 6px 5px;border-bottom:1px solid var(--line2)}
.xpm tr.xpg th span{font-weight:400;font-size:12px;color:var(--mut);margin-left:8px}
.xpm th.xpsn{padding:6px;border-bottom:1px solid var(--line);vertical-align:middle;min-width:150px;font-weight:400}
.xpm th.xpsn b{display:block;font-size:13.5px}.xpm th.xpsn small{display:block;font-size:11px;color:var(--mut)}
.xpc{border-bottom:1px solid var(--line);text-align:center;padding:0;vertical-align:middle;min-width:104px}
.xpc a{display:flex;flex-wrap:wrap;justify-content:center;align-items:center;gap:1px 3px;padding:6px 4px;color:var(--ink);text-decoration:none}
.xpc a:hover{background:var(--card2)}.xpc small{flex:1 1 100%;font-size:11px;color:var(--ink2);line-height:1.35}
.xpc.xplow .xpt,.xpc.xplow small{color:var(--mut)}.xpc.xplow .xpt-a{background:transparent;border-color:var(--line2)}
.xpc.xpna{color:var(--mut);font-size:11.5px}
.xpc.xon a,.xpi.xon{background:var(--accbg)}
.xpln{margin:4px 0;padding-left:20px;font-size:13.5px;line-height:1.9}
@media (max-width:640px){
 .xpw{overflow-x:visible}.xpm,.xpm tbody{display:block}.xpm thead{display:none}
 .xpm tr{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));column-gap:2px;border-bottom:1px solid var(--line);padding:3px 0 5px}
 .xpm tr.xpg{display:block;border-bottom:0}.xpm tr.xpg th{display:block;padding:12px 2px 4px}.xpm tr.xpg th span{display:block;margin-left:0}
 .xpm th.xpsn{grid-column:1/-1;border-bottom:0;padding:3px 2px 2px;min-width:0}.xpm th.xpsn b,.xpm th.xpsn small{display:inline;margin-right:6px}
 .xpc{border-bottom:0;min-width:0}.xpc::before{content:attr(data-h);display:block;font-size:10px;color:var(--mut);line-height:1.3}
 .xpc a{padding:2px 1px;flex-direction:column;gap:1px}.xpc small{display:none}.xpc .xpt{padding:0 3px;font-size:10.5px}
 .xpl{padding-left:0}.xpk .xpl{padding-left:0}}
"""

_JS = r"""
(function(){
const XS = JSON.parse(document.getElementById('xsd').textContent);
const XSV = {span: 'all', all: false}, XSHOME = true;
const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const md = d => d ? (+d.slice(5,7)) + '/' + (+d.slice(8,10)) : '';
const ymd = d => !d ? '' : d.length === 7 ? d.slice(0,4) + '/' + (+d.slice(5,7)) : d.slice(0,4) + '/' + (+d.slice(5,7)) + '/' + (+d.slice(8,10));
const PV = document.getElementById('sgpv'), PB = document.getElementById('sgp');
let CUR = null, PUSHED = false;
const BYK = {};
Object.entries(XS.m || {}).forEach(([mk, M]) => Object.entries(M).forEach(([k, r]) => { const sp = XS.spec[k], id = 'xs:' + mk + ':' + k;
  BYK[id] = {k: id, mk, name: sp.name, grp: sp.grp, xs: r, sp, xk: k}; }));
/*@@XSPANEL@@*/
function hilite(x){ document.querySelectorAll('.xon').forEach(e => e.classList.remove('xon'));
  if (x) document.querySelectorAll('[data-k="' + CSS.escape(x.k) + '"]').forEach(e => e.classList.add('xon')); }
function openX(x, push){
  const first = PV.hidden;
  CUR = x; XSV.all = false;
  if (push) { const u = '#i=' + encodeURIComponent(x.k);
    if (first && !PUSHED) { history.pushState({xs: 1}, '', u); PUSHED = true; } else history.replaceState(history.state, '', u); }
  PB.innerHTML = xsPanel(x); xsSeg();
  PV.hidden = false; document.body.classList.add('sgopen');
  PB.scrollTop = 0; if (first) PB.focus({preventScroll: true});
  hilite(x); xsFill(x); }
function closeX(fromHash){
  if (PV.hidden) return;
  PV.hidden = true; document.body.classList.remove('sgopen'); CUR = null; hilite(null);
  if (!fromHash) { if (PUSHED) { PUSHED = false; history.back(); } else history.replaceState(null, '', location.pathname + location.search); }
  else PUSHED = false; }
document.addEventListener('click', e => { const a = e.target.closest && e.target.closest('a[href^="#i=xs:"]'); if (!a) return;
  const x = BYK[decodeURIComponent(a.getAttribute('href').slice(3))]; if (!x) return; e.preventDefault(); openX(x, true); });
PB.addEventListener('click', e => { if (e.target.closest('#sgx')) { closeX(); return; } if (CUR) xsClick(e); });
document.getElementById('sgpb').addEventListener('click', () => closeX());
document.addEventListener('keydown', e => { if (e.key === 'Escape' && !PV.hidden) closeX(); });
let rzT = null;
window.addEventListener('resize', () => { clearTimeout(rzT); rzT = setTimeout(() => { if (CUR) xsEq(CUR); }, 200); });
function fromHash(ev){
  const m = location.hash.match(/^#i=([^&]+)$/);
  if (m) { const x = BYK[decodeURIComponent(m[1])]; if (x) { if (ev) PUSHED = true; if (CUR !== x) openX(x, false); return; } }
  closeX(true); }
window.addEventListener('hashchange', fromHash);
fromHash();
})();
"""
JS = _JS.replace("/*@@XSPANEL@@*/", XSP.PANEL_JS)


def render(V: dict) -> str:
    from . import appnav
    from . import sigpage as SP
    from .heatpage import _CSS as HCSS
    grp: dict = {}
    for mk, d in V["asof"].items():
        grp.setdefault("台股" if mk == "tw" else "美股", set()).add(d)
    asof = "、".join(f'{k} {"／".join(_md(x) for x in sorted(v))}' for k, v in grp.items())
    if V["R"]:
        body = next_html(V) + matrix_html(V) + method_html() + links_html()
    else:
        body = '<p class="warn">大神策略算不出來（xstrat.run_all）。</p>'
    data = json.dumps(XSP.payload(V["R"]), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return appnav.finish(_HTML.replace("{{APPTAB}}", appnav.bar("xs")).replace("{{CSS}}", HCSS + appnav.CSS + SP.CSS + CSS)
                         .replace("{{ASOF}}", _e(("資料到 " + asof) if asof else "")).replace("{{BODY}}", body)
                         .replace("{{DATA}}", data).replace("{{JS}}", JS))


def detail_json(V: dict) -> str:
    """點開才下載的淨值與每一筆（訊號總覽的面板也讀這一份）。"""
    return json.dumps(XSP.detail(V["R"]), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build(out: Path = OUT, data_out: Path = OUT_DATA) -> bool:
    V = view()
    if not V["R"]:                                        # 算不出來就留著上一版，不拿空的蓋掉
        print("[大神策略] 沒有結果，不改寫")
        return False
    changed = False
    for path, text in ((data_out, detail_json(V)), (out, render(V))):
        if path.exists() and path.read_text(encoding="utf-8") == text:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        changed = True
    return changed
