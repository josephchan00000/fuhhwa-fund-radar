"""選擇權頁（隱藏頁 x9op.html）的「財報」分頁：台股財報季（資料 data/lab/earn_tw.json，arm/lab/earntw.py 算；規格 ernspec）。

由上而下：季彙總一列 → 篩選與分組 → 基金與自家 ETF 的持股成績（選一檔）→ 每家一張卡。伺服器端畫好；瀏覽器只做篩選、分組、選基金、我的清單（存在瀏覽器）。
CSS class 一律 ern 開頭。只寫已經發生的數字，不寫之後會怎樣。
"""
from __future__ import annotations

import html
import json
from pathlib import Path

from . import ernspec as S

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "lab" / "earn_tw.json"
QN = {"03-31": "第一季", "06-30": "第二季", "09-30": "第三季", "12-31": "第四季"}
FYW = {"lo": "全年預估看起來偏低", "ok": "全年預估看起來合理", "hi": "全年預估看起來偏高"}

CSS = (
    ".ern-h{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 12px;margin:4px 0 10px}.ern-h h2{margin:0;font-size:20px}"
    ".ern-h small{color:var(--mut);font-size:12.5px}"
    ".ern-sum{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;background:var(--panel);border:1px solid var(--line);"
    "border-radius:12px;padding:12px 14px;margin-bottom:12px}"
    ".ern-k{font-size:12px;color:var(--mut)}.ern-big{font-size:24px;font-weight:800;font-variant-numeric:tabular-nums}"
    ".ern-note{font-size:12px;color:var(--mut);margin-top:2px;line-height:1.5}"
    ".ern-sb{display:flex;height:10px;border-radius:5px;overflow:hidden;margin:6px 0 4px;gap:2px}.ern-sb i{display:block}"
    ".ern-u{background:var(--t4)}.ern-d{background:var(--t0)}.ern-f{background:var(--line2)}.ern-hi{background:var(--warn)}.ern-ok{background:var(--c2)}"
    ".ern-lo{background:var(--t4)}.ern-na{background:var(--line)}"
    ".ern-sl{font-size:12px;color:var(--ink2)}.ern-sl .u{color:var(--t4)}.ern-sl .d{color:var(--t0)}.ern-sl .w{color:var(--warn)}"
    ".ern-ctl{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:8px 0 10px}"
    ".ern-ctl select,.ern-ctl input{font:inherit;font-size:13px;padding:4px 8px;border-radius:8px;border:1px solid var(--line2);background:var(--panel);color:var(--ink)}"
    ".ern-chip{border:1px solid var(--line2);border-radius:999px;padding:3px 10px;font-size:13px;color:var(--ink2);background:none;cursor:pointer;font-family:inherit}"
    ".ern-chip.on{background:var(--accbg);color:var(--acc);border-color:var(--acc)}"
    ".ern-fund{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:10px 12px;margin-bottom:12px;overflow-x:auto}"
    ".ern-fund h3{margin:0 0 6px;font-size:15px;display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center}"
    ".ern-t{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}"
    ".ern-t th{text-align:right;color:var(--mut);font-weight:500;padding:4px 6px;border-bottom:1px solid var(--line);white-space:nowrap}"
    ".ern-t th:first-child,.ern-t td:first-child{text-align:left}.ern-t td{text-align:right;padding:5px 6px;border-bottom:1px solid var(--line);white-space:nowrap}"
    ".ern-t td small{color:var(--mut);margin-left:4px}.ern-t .u{color:var(--t4)}.ern-t .d{color:var(--t0)}"
    ".ern-g{margin:14px 0 6px;font-size:15px}.ern-g small{color:var(--mut);font-weight:400;font-size:12px;margin-left:6px}"
    ".ern-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:10px}"
    ".ern-c{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:10px 12px}"
    ".ern-c header{display:flex;align-items:baseline;gap:8px}.ern-c header b{font-size:16px}.ern-c header small{color:var(--mut)}"
    ".ern-my{margin-left:auto;border:0;background:none;color:var(--mut);font-size:17px;cursor:pointer;padding:0 2px}.ern-my.on{color:var(--warn)}"
    ".ern-who{font-size:12px;color:var(--mut);margin:2px 0 6px}"
    ".ern-tags{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:6px}"
    ".ern-tg{font-size:12px;border-radius:6px;padding:1px 7px;background:var(--card2);color:var(--ink2);white-space:nowrap}"
    ".ern-tg.u{background:var(--sbg);color:var(--t4)}.ern-tg.d{background:var(--zc);color:var(--t0)}.ern-tg.w{background:var(--curbg);color:var(--warn)}"
    ".ern-box{background:var(--card2);border-radius:8px;padding:6px 10px;font-size:13px}"
    ".ern-hb{display:grid;grid-template-columns:4.2em 1fr 5.2em;align-items:center;gap:8px;padding:2px 0}"
    ".ern-hb em{position:relative;height:9px;display:block}.ern-hb em:before{content:'';position:absolute;left:50%;top:-2px;bottom:-2px;border-left:1px solid var(--line2)}"
    ".ern-hb em i{position:absolute;top:1px;height:7px;border-radius:2px}.ern-hb em i.u{background:var(--t4)}.ern-hb em i.d{background:var(--t0)}"
    ".ern-hb b{text-align:right;font-variant-numeric:tabular-nums}.ern-hb b.u{color:var(--t4)}.ern-hb b.d{color:var(--t0)}"
    ".ern-ln{font-size:12.5px;color:var(--ink2);margin-top:6px;line-height:1.6}.ern-ln b{color:var(--ink);font-variant-numeric:tabular-nums}"
    ".ern-sp{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--mut);margin-top:4px}.ern-sp svg{height:24px;width:88px}"
    ".ern-sp .bu{fill:var(--t4)}.ern-sp .bd{fill:var(--t0)}.ern-sp .bl{stroke:var(--line2)}"
    ".ern-none{color:var(--mut);font-size:13px;padding:8px 2px}"
    "@media (max-width:760px){.ern-sum{grid-template-columns:1fr 1fr}.ern-cards{grid-template-columns:1fr}}"
)

JS = r"""(function(){
var R=document.getElementById('ern-root');if(!R||!R.querySelector('#ern-grp'))return;
var my={};try{my=JSON.parse(localStorage.getItem('ernMy')||'{}')||{}}catch(e){}
function save(){try{localStorage.setItem('ernMy',JSON.stringify(my))}catch(e){}}
var cards=[].slice.call(R.querySelectorAll('.ern-c')),box=R.querySelector('.ern-cards'),f=null,q='';
cards.forEach(function(c){var b=c.querySelector('.ern-my');if(my[c.dataset.c])b.classList.add('on');
 b.addEventListener('click',function(){var k=c.dataset.c;if(my[k])delete my[k];else my[k]=1;save();b.classList.toggle('on',!!my[k]);apply()})});
function ok(c){if(q&&(c.dataset.c+c.dataset.n).toLowerCase().indexOf(q)<0)return false;
 if(!f)return true;if(f==='my')return!!my[c.dataset.c];return(' '+c.dataset.f+' ').indexOf(' '+f+' ')>=0}
function apply(){var g=R.querySelector('#ern-grp').value,n=0;
 cards.sort(function(a,b){if(g==='ind'){var x=a.dataset.i.localeCompare(b.dataset.i,'zh-Hant');if(x)return x}return(+b.dataset.w)-(+a.dataset.w)||a.dataset.c.localeCompare(b.dataset.c)});
 var last=null;R.querySelectorAll('.ern-g2').forEach(function(h){h.remove()});
 cards.forEach(function(c){var s=ok(c);c.hidden=!s;if(s)n++;
  if(g==='ind'&&s&&c.dataset.i!==last){var h=document.createElement('h3');h.className='ern-g ern-g2';h.textContent=c.dataset.i||'其他';box.appendChild(h);last=c.dataset.i}
  box.appendChild(c)});
 R.querySelector('#ern-n').textContent=n+' 家'}
R.querySelectorAll('.ern-chip').forEach(function(b){b.addEventListener('click',function(){var k=b.dataset.f;f=(f===k)?null:k;
 R.querySelectorAll('.ern-chip').forEach(function(x){x.classList.toggle('on',x.dataset.f===f)});apply()})});
R.querySelector('#ern-grp').addEventListener('change',apply);
R.querySelector('#ern-q').addEventListener('input',function(){q=this.value.trim().toLowerCase();apply()});
var fs=R.querySelector('#ern-fs');if(fs)fs.addEventListener('change',function(){R.querySelectorAll('.ern-ft').forEach(function(t){t.hidden=t.dataset.k!==fs.value})});
apply();
})();"""


def _md(d: str) -> str:
    return f"{int(d[5:7])}/{int(d[8:10])}"


def _p(x, sign=True) -> str:
    if x is None:
        return "—"
    if sign:
        return (">+999%" if x > 999 else f"{x:+.0f}%").replace("-", "−")
    return f"{x:.1f}%"


def _cls(x) -> str:
    return "" if x is None else "u" if x > 0 else "d" if x < 0 else ""


def _bar(label: str, v, scale=150) -> str:
    if v is None:
        return f'<div class="ern-hb"><span>{label}</span><em></em><b>—</b></div>'
    w = min(abs(v) / scale * 50, 50)
    side = f"left:50%;width:{w:.1f}%" if v >= 0 else f"right:50%;width:{w:.1f}%"
    return f'<div class="ern-hb"><span>{label}</span><em><i class="{_cls(v)}" style="{side}"></i></em><b class="{_cls(v)}">{_p(v)}</b></div>'


def _spark(vals: list) -> str:
    vs = [v for v in vals if v is not None]
    if not vs:
        return ""
    mx, w, h = max(max(abs(v) for v in vs), 1), 8, 24
    o = []
    for i, v in enumerate(vals):
        if v is None:
            continue
        hh = abs(v) / mx * (h / 2 - 1)
        y = h / 2 - hh if v >= 0 else h / 2
        o.append(f'<rect x="{i * (w + 3)}" y="{y:.1f}" width="{w}" height="{max(hh, 1):.1f}" rx="1.5" class="{"bu" if v >= 0 else "bd"}"/>')
    return (f'<svg viewBox="0 0 {len(vals) * (w + 3)} {h}" aria-hidden="true">' + "".join(o)
            + f'<line x1="0" x2="{len(vals) * (w + 3)}" y1="{h / 2}" y2="{h / 2}" class="bl"/></svg>')


def _who(who: list) -> tuple[str, int]:
    funds = [w for w, _ in who if not w.startswith("00") and not w.startswith("選股頁")]
    etfs = [w for w, _ in who if w.startswith("00")]
    picks = [w.replace("選股頁：", "") for w, _ in who if w.startswith("選股頁")]
    parts = []
    if funds:
        parts.append(f"復華基金 {len(funds)} 檔")
    if etfs:
        parts.append("、".join(etfs))
    if picks:
        parts.append("選股頁：" + "、".join(picks))
    return "・".join(parts), len(funds) + len(etfs) + len(picks)


def card(c: str, r: dict) -> str:
    e = html.escape
    who, nw = _who(r.get("who") or [])
    head = (f'<header><b>{e(r.get("n") or c)}</b><small>{c}・{e(r.get("ind") or "")}</small>'
            f'<button type="button" class="ern-my" aria-label="加入我的清單" title="我的清單">☆</button></header>'
            f'<div class="ern-who">{e(who)}</div>')
    attrs = f'data-c="{c}" data-n="{e(r.get("n") or "")}" data-i="{e(r.get("ind") or "其他")}" data-w="{nw}"'
    if not r.get("in"):
        why = "沒有這家的財報資料" if r.get("nodata") else f"{QN.get(r['q'][5:], '')}資料還沒進來（期限後補抓）"
        return f'<article class="ern-c" {attrs} data-f="out">{head}<p class="ern-none">{why}</p></article>'
    fl, tags = [], []
    ni = r.get("ni_yoy")
    if r.get("suspect"):
        tags.append('<span class="ern-tg w">待查：營收大增、獲利卻轉虧</span>')
        fl.append("sus")
    elif ni is not None:
        k = "up" if ni > S.FLAT else "dn" if ni < -S.FLAT else "flat"
        fl.append(k)
        tags.append(f'<span class="ern-tg {"u" if k == "up" else "d" if k == "dn" else ""}">獲利比去年同季 {_p(ni)}</span>')
    fy = r.get("fy") or {}
    if fy.get("k") in FYW:
        fl.append("fy" + fy["k"])
        tags.append(f'<span class="ern-tg {"w" if fy["k"] == "hi" else "u" if fy["k"] == "lo" else ""}">{FYW[fy["k"]]}</span>')
    if fy.get("stale"):
        fl.append("stale")
        tags.append('<span class="ern-tg">預估可能還沒反映這一季</span>')
    if r.get("decel"):
        fl.append("decel")
        tags.append('<span class="ern-tg w">營收降速</span>')
    if r.get("eps_note"):
        tags.append(f'<span class="ern-tg">{e(r["eps_note"])}</span>')
    gm = r.get("gm")
    gml = ("毛利率 " + (f"{gm:.1f}%" if gm is not None else "—")
           + f"（上季 {r['gm_q']:.1f}%、去年同季 {r['gm_ly']:.1f}%）" if gm is not None and r.get("gm_q") is not None and r.get("gm_ly") is not None
           else "毛利率 " + (f"{gm:.1f}%" if gm is not None else "—"))
    lines = [f'<div class="ern-ln">每股盈餘 <b>{r["eps"]:.2f}</b> 元（去年同季 {r["eps_ly"]:.2f}）；{gml}</div>'
             if r.get("eps") is not None and r.get("eps_ly") is not None else f'<div class="ern-ln">{gml}</div>']
    cv = (r.get("cons") or {}).get("v")
    if fy.get("k") in FYW:
        lines.append(f'<div class="ern-ln">要達到全年預估 {cv:.2f} 元，剩下要賺 <b>{fy["need"]:.2f}</b> 元；'
                     f'照去年的季節大約 <b>{fy["exp"]:.2f}</b> 元（{e(r["cons"].get("src") or "")}・{_md(r["cons"]["d"]) if r["cons"].get("d") else "—"}）。</div>')
    elif fy.get("why"):
        lines.append(f'<div class="ern-ln">全年預估：{e(fy["why"])}。</div>')
    mo = "、".join(f'{int(m[0][5:])} 月 {_p(m[1])}' for m in r.get("mo3") or [] if m[1] is not None)
    px = r.get("px1m")
    lines.append(f'<div class="ern-sp"><span>營收年增 8 季</span>{_spark([x[1] for x in r.get("rev8") or []])}</div>'
                 f'<div class="ern-ln">月營收比去年：{mo or "—"}；近 1 個月股價 <b class="{_cls(px)}">{_p(px)}</b></div>')
    return (f'<article class="ern-c" {attrs} data-f="{" ".join(fl)}">{head}<div class="ern-tags">{"".join(tags)}</div>'
            f'<div class="ern-box">{_bar("營收", r.get("rev_yoy"))}{_bar("獲利", ni)}</div>{"".join(lines)}</article>')


def _funds(doc: dict) -> str:
    rows = doc.get("rows") or {}
    by: dict[str, list] = {}
    for c, r in rows.items():
        for w, wt in r.get("who") or []:
            if not w.startswith("選股頁"):
                by.setdefault(w, []).append((c, wt))
    if not by:
        return ""
    keys = sorted(by, key=lambda k: (k.startswith("00"), -len(by[k]), k))
    first = "復華" if "復華" in by else keys[0]
    opts = "".join(f'<option value="{html.escape(k)}"{" selected" if k == first else ""}>{html.escape(k)}（{len(by[k])} 家）</option>' for k in keys)
    tabs = []
    for k in keys:
        trs = []
        for c, wt in sorted(by[k], key=lambda x: -(x[1] or 0)):
            r = rows[c]
            fy = (r.get("fy") or {}).get("k")
            trs.append(f'<tr><td>{html.escape(r.get("n") or c)}<small>{c}</small></td><td>{"—" if wt is None else f"{wt:.1f}%"}</td>'
                       + (f'<td class="{_cls(r.get("ni_yoy"))}">{_p(r.get("ni_yoy"))}</td><td class="{_cls(r.get("rev_yoy"))}">{_p(r.get("rev_yoy"))}</td>'
                          f'<td>{ {"lo": "偏低", "ok": "合理", "hi": "偏高"}.get(fy, "—") }</td>' if r.get("in") else '<td colspan="3">資料還沒進來</td>')
                       + f'<td class="{_cls(r.get("px1m"))}">{_p(r.get("px1m"))}</td></tr>')
        tabs.append(f'<table class="ern-t ern-ft" data-k="{html.escape(k)}"{"" if k == first else " hidden"}><thead><tr><th>持股</th><th>比重</th>'
                    f'<th>獲利年增</th><th>營收年增</th><th>全年預估</th><th>近 1 個月股價</th></tr></thead><tbody>{"".join(trs)}</tbody></table>')
    return (f'<section class="ern-fund"><h3>基金與自家 ETF 的持股成績<select id="ern-fs" aria-label="選一檔基金或 ETF">{opts}</select></h3>'
            + "".join(tabs) + "</section>")


def block(doc: dict | None = None) -> str:
    if doc is None:
        try:
            doc = json.loads(DATA.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            doc = None
    if not doc or not doc.get("rows"):
        return '<p class="oplead">財報季的資料還沒準備好（每天建頁時更新）。</p>'
    e = html.escape
    s, rows, q = doc["sum"], doc["rows"], doc["q"]
    title = f"{q[:4]} {QN.get(q[5:], '')}"
    out_names = "、".join(e(rows[c].get("n") or c) for c in s.get("out") or [])

    def sb(parts):
        tot = sum(n for n, _, _ in parts) or 1
        return ('<div class="ern-sb">' + "".join(f'<i class="{k}" style="flex:{n}"></i>' for n, k, _ in parts if n) + "</div>"
                + '<div class="ern-sl">' + "・".join(f'<span class="{t[1]}">{t[0]} {n}</span>' for n, _, t in parts) + "</div>") if tot else ""
    E, F = s["eps"], s["fy"]
    summ = (f'<section class="ern-sum"><div><div class="ern-k">清單（復華基金前十大、自家 ETF、選股頁拿著的）</div>'
            f'<div class="ern-big">{s["n"]} 家</div><div class="ern-note">{title}已進資料 {s["in"]} 家'
            + (f'；還沒進來 {len(s["out"])} 家：{out_names}（期限後補抓）' if s.get("out") else "") + '</div></div>'
            f'<div><div class="ern-k">獲利比去年同季</div>{sb([(E["up"], "ern-u", ("成長", "u")), (E["flat"], "ern-f", ("差不多", "")), (E["dn"], "ern-d", ("衰退", "d"))])}</div>'
            f'<div><div class="ern-k">全年預估看起來</div>{sb([(F["lo"], "ern-lo", ("偏低", "u")), (F["ok"], "ern-ok", ("合理", "")), (F["hi"], "ern-hi", ("偏高", "w")), (F["na"], "ern-na", ("算不了", ""))])}</div>'
            f'<div><div class="ern-k">要留意</div><div class="ern-note">營收降速 {s["decel"]} 家・預估可能還沒反映這一季 {s["stale"]} 家'
            + (f'・待查 {len(s["suspect"])} 家' if s.get("suspect") else "") + (f'・營收年增中位數 {_p(s["med_rev"])}' if s.get("med_rev") is not None else "")
            + "</div></div></section>")
    chips = [("up", "比去年好"), ("dn", "比去年差"), ("fyhi", "全年預估偏高"), ("fylo", "全年預估偏低"), ("stale", "預估太舊"),
             ("decel", "營收降速"), ("out", "資料還沒進來"), ("my", "我的清單")]
    ctl = ('<div class="ern-ctl"><select id="ern-grp" aria-label="分組"><option value="who">誰持有最多</option><option value="ind">產業</option></select>'
           + "".join(f'<button type="button" class="ern-chip" data-f="{k}">{t}</button>' for k, t in chips)
           + '<input id="ern-q" type="search" placeholder="代號或名稱" aria-label="搜尋代號或名稱"><span id="ern-n" class="ern-k"></span></div>')
    cards = "".join(card(c, rows[c]) for c in sorted(rows))
    hint = ("全年預估看起來偏高／偏低＝剩下要賺的，比照去年的季節大約能賺的多或少 15% 以上；"
            "獲利＝母公司淨利；股數有變的公司每股盈餘用淨利比例換算。")
    return (f'<div id="ern-root"><div class="ern-h"><h2 title="{e(hint)}">財報季・{title}</h2>'
            f'<small>{_md(doc["made"])} 更新・法定期限過了才算進來</small></div>{summ}{_funds(doc)}{ctl}'
            f'<div class="ern-cards">{cards}</div></div>')
