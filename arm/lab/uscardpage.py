"""美股個股卡（配置頁 v2 第 4 步；docs/lab_cfg_v2_plan.md 第 3.3 節）：配置頁美股列的股票（手上的、要買的、名單前 5 名裡
手上沒有的）點了打開的卡片——配置、為什麼選它、走勢、分析師、公司。

資料：每週紀錄（ussx_qm_live.json：持股、名單、met／met0＝五個條件）＋每天的 50 日線檢查（ussx_qm_watch.json）＋
每天的卡片資料（ussx_card.json：近一年收盤與 50 日線、Yahoo 分析師預估、財報日；uscard.py）＋簡介庫。
配置、為什麼選它、公司三段在這裡組好（持股、比重、賣出日都用 cfgpage.us_state 的結果，和配置頁那一列一致）；
走勢、分析師兩段由瀏覽器畫（JS 函式一律 uc 開頭；「目標價」只准出現在 ucAn，引述分析師的數字、附 Yahoo 的來源連結，
同台股公司卡「法人預估」的例外，tests/test_uscardpage.py 守）。
頁面資料：D.cfg.us.uc＝{"o": [代號（配置頁的順序）], "cal": [近一年交易日], "d": 卡片資料要的美股收盤日, "s": {代號: {...}}}。
網址 #us=代號。
"""
from __future__ import annotations

import html
import math

from .. import fund_intro as FI
from . import corepage as CPG
from . import ussxspec as QX

YF = "https://finance.yahoo.com/quote/"
SEC = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&owner=include&count=40&CIK="


def _e(x) -> str:
    return html.escape(str(x if x is not None else ""))


def ysym(c: str) -> str:
    """Yahoo 的代號寫法（BRK.B → BRK-B）。"""
    return str(c).replace(".", "-").replace("/", "-")


def _num(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _px(x: float | None) -> str:
    """美股股價：兩位小數、千分位。"""
    return "—" if x is None else f"{x:,.2f}"


# ── 為什麼選它：五個條件（順序同 ussxqm.KEYS） ──────────────────────────────────

def five_rows() -> list[tuple[str, str, str]]:
    """[(鍵, 名稱, 要多少)]；要多少照 ussxspec.QM 寫（規則改了這裡跟著改）。"""
    q = QX.QM
    return [("rs", "強度", f"要 {q['rs']:.0f} 以上"),
            ("d52h", "離 52 週高點", f"要在 {-q['d52h'] * 100:.0f}% 以內"),
            ("om", "營益率", f"要 {q['om'] * 100:.0f}% 以上"),
            ("roe", "近四季 ROE", f"要 {q['roe'] * 100:.0f}% 以上"),
            ("cap", "市值", f"要 {q['cap'] / 1e8:,.0f} 億美元以上")]


def five_ok(k: str, v: float | None) -> bool | None:
    """這一個數字有沒有過（沒有值＝None）。"""
    if v is None:
        return None
    q = QX.QM
    return v >= q[k]


def five_txt(k: str, v: float | None) -> str:
    if v is None:
        return "—"
    if k == "rs":
        return f"{v:.0f}"
    if k == "d52h":
        return "在高點" if v >= -0.0005 else f"低 {-v * 100:.1f}%"
    if k == "cap":                                            # 單位寫在「要 20 億美元以上」那一行（手機 320px 表格才放得下）
        b = v / 1e8
        return f"{b:,.0f} 億" if b >= 100 else f"{b:.1f} 億"
    return f"{v * 100:.1f}%"


def _vals(v) -> dict[str, float | None]:
    keys = [k for k, _, _ in five_rows()]
    v = list(v or [])
    return {k: _num(v[i]) if i < len(v) else None for i, k in enumerate(keys)}


def _cell(k: str, v: float | None) -> str:
    ok = five_ok(k, v)
    mk = "" if ok is None else ('<i class="ucok">✓</i>' if ok else '<i class="ucno">✗</i>')
    return f"<td>{mk}{_e(five_txt(k, v))}</td>"


def why_html(c: str, n: dict, rank: tuple | None, hold: bool) -> str:
    """為什麼選它：五個條件的數字和要多少。拿著的股票兩欄＝買進那一週（met0，帳戶記的訊號日，那時五個都過）與這一週（met）；
    還沒買的只有這一週。下面一行講每個數字是什麼、買進以後只看 50 日線。"""
    met, met0 = (n.get("met") or {}).get(c), (n.get("met0") or {}).get(c)
    wk = n.get("wk")
    cols = []
    if hold and met0:
        cols.append((f'買進時<span>{_e(CPG._md(met0.get("wk")))} 那週</span>', _vals(met0.get("v"))))
    if met or not cols:
        cols.append((f'{"現在" if hold else "這週"}<span>{_e(CPG._md(wk))} 那週</span>', _vals(met)))
    if rank:
        sub = f'{CPG._md(wk)} 那週的名單第 {rank[0]} 名（共 {n.get("n_list", 0)} 檔）'
    elif hold:
        sub = f'{CPG._md(wk)} 那週不在名單上（拿著的只看 50 日線）'
    else:
        sub = ""
    head = "<tr><th></th>" + "".join(f"<th>{h}</th>" for h, _ in cols) + "</tr>"
    body = "".join(f'<tr><td class="l"><b>{_e(nm)}</b><span>{_e(req)}</span></td>' + "".join(_cell(k, v[k]) for _, v in cols) + "</tr>"
                   for k, nm, req in five_rows())
    empty = not met and not met0
    note = ("強度＝近 3、6、9、12 個月的漲幅（近 3 個月算兩倍）勝過幾 % 的美股（1～99）；營益率＝最近一季的營業利益 ÷ 營收；"
            "近四季 ROE＝近四季淨利 ÷ 股東權益；市值＝那週最後一個交易日的收盤 × 流通股數。")
    if hold:
        note += "買進以後只看 50 日線，這幾個數字變差也照樣拿著。"
    return (f'<h3>為什麼選它' + (f'<span class="sub">{_e(sub)}</span>' if sub else "") + "</h3>"
            + ('<p class="st">這週的五個數字還沒有（每週六更新）。</p>' if empty else
               f'<div class="tw"><table class="ucfv">{head}{body}</table></div><p class="note">{_e(note)}</p>'))


# ── 配置 ─────────────────────────────────────────────────────────────────────

def _last_px(cs: list) -> tuple[float | None, float | None]:
    """卡片資料的最後一個收盤與漲跌（%）。"""
    xs = [x for x in cs or [] if x is not None]
    if not xs:
        return None, None
    return xs[-1], (xs[-1] / xs[-2] - 1) * 100 if len(xs) > 1 and xs[-2] else None


def cfg_html(c: str, G: dict, h0: dict | None, W0: dict | None, px: float | None, cash: bool, rank: tuple | None = None) -> str:
    """配置：持有中（哪天買、買進價、現在、占全部資金、跌破 50 日線就賣；已經跌破＝哪天開盤賣）、待買進、這週賣掉了、
    名單上手上沒有的（有空位時照名單順序買）。數字都用 us_state 的結果（G），和配置頁那一列一樣。"""
    rows = {r["c"]: r for r in G["rows"]}
    todo = {x["c"]: x for x in G["todo"]}
    gone = {x["c"]: x for x in G["gone"]}
    lines = []
    if cash:
        lines.append("警訊：全部持股放現金中；下面是照規則該有的股票，警訊解除後照這樣買回。")
    if c in rows:
        r = rows[c]
        if r.get("new"):
            lines.append(f'持有中：{CPG._mdw(r["ent"])}開盤買進；買進價和漲跌等這週六的持股紀錄。占全部資金約 {CPG._wp(r["w"])}。')
        else:
            epx = _num((h0 or {}).get("epx"))
            rr = r.get("r")
            hp = _num((h0 or {}).get("px"))
            if px is not None and hp and (h0 or {}).get("r") is not None:   # 漲跌照卡片的最新收盤（和標題的股價一致）
                rr = (1 + h0["r"]) * px / hp - 1
            now = f'，現在 <b>{_px(px)}</b>（<span class="{"up" if (rr or 0) >= 0 else "dn"}">{CPG._pc(rr)}</span>）' if px is not None and rr is not None else ""
            lines.append(f'持有中：{CPG._mdw(r["ent"])}買進 {_px(epx)}{now}；占全部資金 {CPG._wp(r["w"])}。')
        if r.get("sell"):
            lines.append(f'<b>{CPG._mdw(r["sell"])}開盤賣</b>（{CPG._md(r["trig"])} 收盤跌破 50 日線）。')
        else:
            ma, pct = _num((W0 or {}).get("ma")), _num((W0 or {}).get("pct"))
            if ma is None:
                ma, pct = _num((h0 or {}).get("ma")), r.get("pct")
            t = "收盤跌破 50 日線，就在下一個交易日開盤賣"
            if ma is not None:
                t += f"：50 日線現在 <b>{_px(ma)}</b>"
                if pct is not None:
                    t += f'（收盤比它{"高" if pct >= 0 else "低"} {abs(pct) * 100:.1f}%）'
            lines.append(t + "。")
    elif c in todo:
        x = todo[c]
        if x["w"] > 1e-3:
            lines.append(f'待買進：<b>{CPG._mdw(x["d"])}開盤買</b>，約占全部資金 {CPG._wp(x["w"])}。')
        else:
            lines.append(f'排在名單上，但現金不夠，{CPG._mdw(x["d"])}先不買。')
        lines.append("買了以後，收盤跌破 50 日線就在下一個交易日開盤賣。")
    elif c in gone:
        x = gone[c]
        lines.append(f'{CPG._mdw(x["on"])}開盤賣掉了' + (f'（{CPG._md(x["trig"])} 收盤跌破 50 日線）' if x.get("trig") else "") + "。")
    else:
        nf = G.get("nf")
        wk = (G.get("n") or {}).get("wk")
        lines.append("手上沒有" + (f"：{CPG._md(wk)} 那週名單第 {rank[0]} 名" if rank and wk else "") + "。有空位時照名單順序買。")
        if G.get("free"):
            lines.append(f'現在有 {G["free"]} 個空位' + (f'，{CPG._mdw(nf)}收盤看下一份名單，下一個交易日開盤買' if nf else "") + "。")
        else:
            lines.append(f'現在 {QX.QM_SLOTS} 個位子都滿，有空位才買' + (f'（{CPG._mdw(nf)}收盤看下一份名單）' if nf else "") + "。")
    return (f'<h3>配置<span class="sub">{_e(CPG.QM_NAME)}</span></h3>'
            + "".join(f'<p class="ucl">{t}</p>' for t in lines))


# ── 公司 ─────────────────────────────────────────────────────────────────────

def co_html(c: str, intro: str) -> str:
    y = ysym(c)
    return ('<h3>公司</h3>' + (f'<p class="ucl">{_e(intro)}</p>' if intro else '<p class="st">簡介還沒有（每天下午補）。</p>')
            + f'<p class="uclk"><a href="{YF}{_e(y)}" target="_blank" rel="noopener">Yahoo Finance</a>'
            f'<a href="{SEC}{_e(y)}" target="_blank" rel="noopener">SEC 申報文件</a></p>')


# ── 分析師（數字給瀏覽器排；文字在 JS 的 ucAn） ──────────────────────────────────

def _an(a: dict | None) -> dict | None:
    """uscard 的分析師紀錄 → 頁面用的精簡版：家數、tp＝分析師的價位 [平均, 中位, 最高, 最低]、評等 5 格、
    今年／明年 {end, e: [平均, 家數, 去年], t90: 90 天前, r: [營收, 去年營收]（億美元）}、財報日。"""
    if not a:
        return None
    out = {"n": a.get("n"), "tp": a.get("tp"), "rc": a.get("rc"), "ed": a.get("ed"), "ede": a.get("ede")}
    for k in ("y0", "y1"):
        y = a.get(k)
        if not y:
            continue
        e, r, t = y.get("e") or [], y.get("r") or [], y.get("t") or []
        out[k] = {"end": y.get("end"),
                  "e": [e[0], e[3], e[4]] if len(e) >= 5 else None,
                  "t90": t[4] if len(t) >= 5 else None,
                  "r": [r[0], r[4]] if len(r) >= 5 else None}
    return {k: v for k, v in out.items() if v is not None}


# ── 組起來 ─────────────────────────────────────────────────────────────────────

def order(G: dict) -> list[str]:
    """配置頁的順序：持有中、待買進、這週賣掉的、名單前幾名（手上沒有的，同 cfgpage._qm_cands）。"""
    n = G.get("n") or {}
    out = [r["c"] for r in G["rows"]] + [x["c"] for x in G["todo"]] + [x["c"] for x in G["gone"]]
    have = set(out)
    out += [x["c"] for x in n.get("list") or [] if x["c"] not in have][:FI.US_QM_SHOW]
    seen, res = set(), []
    for c in out:
        if c not in seen:
            seen.add(c)
            res.append(c)
    return res


def build(G: dict, card: dict | None, cash: bool = False) -> dict | None:
    """→ D.cfg.us.uc；美股強勢品質股沒有在用（判定沒過、還沒有每週紀錄）＝None（配置頁的列照舊連 Yahoo Finance）。
    card＝uscard.load()（沒有＝走勢、分析師兩段寫「還沒有」）。"""
    if not G.get("on") or not G.get("n"):
        return None
    n, W, nms = G["n"], G.get("W") or {}, G.get("nms") or {}
    card = card or {}
    cal = card.get("cal") or []
    S = card.get("s") or {}
    hold0 = {h["c"]: h for h in n.get("hold") or []}
    W0 = {h["c"]: h for h in W.get("hold") or []}
    rank = {x["c"]: (i + 1, x.get("rs")) for i, x in enumerate(n.get("list") or [])}
    held = {r["c"] for r in G["rows"]} | {x["c"] for x in G["gone"]}
    intros = CPG._us_intros()
    rows = {r["c"]: r for r in G["rows"]}
    out = {}
    for c in order(G):
        s = S.get(c) or {}
        cs = s.get("c") if len(s.get("c") or []) == len(cal) else None
        ms = s.get("m") if len(s.get("m") or []) == len(cal) else None
        px, ch = _last_px(cs or [])
        if px is None:                                         # 卡片資料還沒有這一檔：股價用每天的檢查或每週紀錄
            px = _num((W0.get(c) or {}).get("px")) or _num((hold0.get(c) or {}).get("px"))
        nm, what = CPG.us_label(c, nms)
        h0 = hold0.get(c)
        ent = None
        if c in rows and not rows[c].get("new") and h0 and h0.get("ent"):
            ent = [h0["ent"], _num(h0.get("epx"))]
        elif c in rows and rows[c].get("new"):
            ent = [rows[c]["ent"], None]
        g = next((x for x in G["gone"] if x["c"] == c), None)
        if g and h0 and h0.get("ent"):
            ent = [h0["ent"], _num(h0.get("epx"))]
        x = {"nm": nm, "en": str(nms.get(c) or ""), "what": what,
             "st": cfg_html(c, G, h0, W0.get(c), px, cash, rank.get(c)),
             "why": why_html(c, n, rank.get(c), c in held),
             "co": co_html(c, intros.get(c.upper(), "")),
             "px": px, "ch": None if ch is None else round(ch, 2), "pd": s.get("at") or (W0.get(c) or {}).get("d") or n.get("d"),
             "an": _an(s.get("an")), "an_at": s.get("an_at"), "ent": ent,
             "out": (g or {}).get("on") or (rows.get(c) or {}).get("sell")}
        if cs:
            x["c"], x["m"] = cs, ms
            if s.get("spl"):
                x["spl"] = s["spl"]
        out[c] = x
    return {"o": list(out), "cal": cal if any("c" in v for v in out.values()) else [], "d": card.get("d"), "s": out}


JS = r"""
/* ---------- 美股個股卡（uscardpage.py；docs/lab_cfg_v2_plan.md 第 3.3 節）：配置頁美股列點了打開，網址 #us=代號。
   配置、為什麼選它、公司三段是 Python 組好的；走勢、分析師兩段在這裡畫。用同一個右側面板（#dv；電腦右側、手機全螢幕）。 ---------- */
const UCD=((CFG.us||{}).uc)||null;
function ucOn(){return !!(UCD&&UCD.s);}
function ucOpen(c){if(!ucOn()||!UCD.s[c])return false;if(!$('#dv').hidden&&/^#us=/.test(location.hash)){history.replaceState(null,'','#us='+encodeURIComponent(c));ucRender(c);return true;}
  PUSHED=true;location.hash='us='+encodeURIComponent(c);return true;}
function ucCur(){return decodeURIComponent((location.hash.match(/^#us=(.+)$/)||[])[1]||'');}
function ucStep(d){if(!ucOn())return;const o=UCD.o||[],i=o.indexOf(ucCur()),t=o[i+d];if(i>=0&&t)ucOpen(t);}
function ucMd(d){return d?`${+d.slice(5,7)}/${+d.slice(8,10)}`:'—';}
function ucPx(x){return x==null?'—':x.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});}
function ucRender(c,keep){const S=ucOn()&&UCD.s[c];if(!S){hideStock();return;}
  const dv=$('#dv'),pane=isPane(),st0=keep?dv.scrollTop:0;
  dv.classList.toggle('pane',pane);document.body.classList.toggle('pane',pane);dv.hidden=false;lockBody(!pane);
  const o=UCD.o||[],i=o.indexOf(c),pv=i>0,nx=i>=0&&i<o.length-1;
  const secs=[['uc-st','配置'],['uc-why','為什麼選它'],['uc-px','走勢'],['uc-an','分析師'],['uc-co','公司']];
  const sub=[`${i+1}／${o.length}`,c].concat(S.what?[S.what]:[]);
  let h=`<div class=dvh><div class=dvt><a class="nv${pv?'':' off'}" id=pv title="上一檔（←）">‹</a>`+
   `<div class=ttl><b>${esc(S.nm)}</b><span class=cd>${sub.map(esc).join(' · ')}</span></div>`+
   `<div class=pxw><b>${ucPx(S.px)}</b>${S.ch!=null?sgn(S.ch,2,'%'):''}</div><a class="nv${nx?'':' off'}" id=nx title="下一檔（→）">›</a><a class=x id=x title="關閉（Esc）">×</a></div>`+
   `<nav class=cnav>${secs.map(([id,t])=>`<a data-cto=${id}>${t}</a>`).join('')}</nav></div>`;
  h+=`<section class="csec uc" id=uc-st>${S.st}</section><section class="csec uc" id=uc-why>${S.why}</section>`;
  h+=`<section class="csec uc" id=uc-px>${ucPxSec(c,S)}</section><section class="csec uc" id=uc-an>${ucAn(c,S)}</section>`;
  h+=`<section class="csec uc" id=uc-co>${S.co}</section>`;
  $('#dvin').innerHTML=h;dv.scrollTop=st0;
  $('#x').onclick=closeStock;$('#pv').onclick=()=>ucStep(-1);$('#nx').onclick=()=>ucStep(1);
  $$('#dvin [data-cto]').forEach(a=>a.onclick=()=>{const t=document.getElementById(a.dataset.cto);if(t)dv.scrollTo({top:dv.scrollTop+t.getBoundingClientRect().top-dv.getBoundingClientRect().top-$('#dvin .dvh').offsetHeight+2,behavior:'smooth'});});
  ucBind(c,S);cspy();}
/* 走勢：近一年收盤（分割還原）、50 日線（虛線）、買進點 ▲、賣出點 ▼；游標移上去看每天的數字 */
function ucPxSec(c,S){if(!S.c)return `<h3>走勢</h3><p class=st>走勢資料還沒有（每天美股收盤後更新）。</p>`;
  const W=Math.max(280,Math.floor($('#dvin').clientWidth-32));
  const lg=`<div class=lg><span><i style="background:#2563c9"></i>收盤</span><span><i class=ucdsh></i>50 日線</span>`+
    (S.ent?`<span><b class=up>▲</b>${ucMd(S.ent[0])} 買進</span>`:'')+(S.out&&S.out<=(UCD.cal||[]).slice(-1)[0]?`<span><b class=dn>▼</b>${ucMd(S.out)} 賣出</span>`:'')+`</div>`;
  const spl=(S.spl||[]).length?`<p class=note>近一年有分割（${S.spl.map(x=>`${ucMd(x[0])} 一股變 ${x[1]} 股`).join('、')}），之前的股價已經換算成分割後的價格。</p>`:'';
  return `<h3>走勢<span class=sub>近一年・${ucMd((UCD.cal||[]).slice(-1)[0])} 收盤</span></h3><div class=ucw id=ucw>${ucSvg(S,W)}<div class=uctip id=uctip hidden></div></div>${lg}${spl}`;}
function ucSvg(S,W){const cal=UCD.cal||[],n=cal.length,HH=200,pl=6,pr=48,pt=10,pb=22;
  const vs=[...S.c,...(S.m||[])].filter(v=>v!=null);if(S.ent&&S.ent[1]!=null)vs.push(S.ent[1]);
  let lo=Math.min(...vs),hi=Math.max(...vs);const pad=(hi-lo)*.06||hi*.05;lo-=pad;hi+=pad;
  const x=i=>pl+(W-pl-pr)*(n>1?i/(n-1):.5),y=v=>pt+(HH-pt-pb)*(1-(v-lo)/(hi-lo));
  const st=(()=>{const r=(hi-lo)/4,p=Math.pow(10,Math.floor(Math.log10(r))),m=r/p;return (m<1.5?1:m<3?2:m<7?5:10)*p;})();
  let s='';for(let t=Math.ceil(lo/st)*st;t<=hi;t+=st){const yy=y(t).toFixed(1);
    s+=`<line x1=${pl} x2=${W-pr} y1=${yy} y2=${yy} stroke="#e3e7ec"/><text x=${W-pr+6} y=${(+yy+4).toFixed(0)} font-size=11 fill="#727e8c">${t.toLocaleString('en-US',{maximumFractionDigits:st<1?2:0})}</text>`;}
  let pm='';cal.forEach((d,i)=>{const m=+d.slice(5,7);if(d.slice(0,7)===pm)return;pm=d.slice(0,7);
    if(i>4&&i<n-6&&(m-1)%3===0)s+=`<text x=${x(i).toFixed(1)} y=${HH-6} font-size=11 fill="#727e8c" text-anchor=middle>${m} 月</text>`;});
  const path=a=>{let p='',up=false;a.forEach((v,i)=>{if(v==null){up=false;return;}p+=`${up?'L':'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`;up=true;});return p;};
  if(S.m)s+=`<path d="${path(S.m)}" fill=none stroke="#f59e0b" stroke-width=1.5 stroke-dasharray="4 3"/>`;
  s+=`<path d="${path(S.c)}" fill=none stroke="#2563c9" stroke-width=1.8 />`;
  const last=S.c.length-1-[...S.c].reverse().findIndex(v=>v!=null);
  if(last>=0&&last<n)s+=`<circle cx=${x(last).toFixed(1)} cy=${y(S.c[last]).toFixed(1)} r=3 fill="#2563c9"/>`;
  const tri=(d,v,up)=>{const i=cal.indexOf(d);if(i<0)return '';const xx=x(i),yy=y(v!=null?v:S.c[i]);if(!isFinite(yy))return '';
    return up?`<path d="M${xx.toFixed(1)},${(yy+4).toFixed(1)}l-5,9h10z" fill="#d33a34"/>`:`<path d="M${xx.toFixed(1)},${(yy-4).toFixed(1)}l-5,-9h10z" fill="#1f9d57"/>`;};
  if(S.ent)s+=tri(S.ent[0],S.ent[1],true);
  if(S.out)s+=tri(S.out,null,false);
  return `<svg width=${W} height=${HH} viewBox="0 0 ${W} ${HH}" data-pl=${pl} data-pr=${pr}>${s}<line class=uccx x1=0 x2=0 y1=${pt} y2=${HH-pb} stroke="#9aa5b1" stroke-dasharray="2 2" visibility=hidden /></svg>`;}
function ucBind(c,S){const w=$('#ucw');if(!w||!S.c)return;const sv=w.querySelector('svg'),tip=$('#uctip'),cx=sv.querySelector('.uccx');
  const cal=UCD.cal||[],n=cal.length,pl=+sv.dataset.pl,pr=+sv.dataset.pr,W=+sv.getAttribute('width');
  const show=ev=>{const r=sv.getBoundingClientRect(),px=(ev.touches?ev.touches[0].clientX:ev.clientX)-r.left;
    let i=Math.round((px-pl)/(W-pl-pr)*(n-1));i=Math.max(0,Math.min(n-1,i));while(i>0&&S.c[i]==null)i--;if(S.c[i]==null)return;
    const xx=pl+(W-pl-pr)*(n>1?i/(n-1):.5);cx.setAttribute('x1',xx);cx.setAttribute('x2',xx);cx.setAttribute('visibility','visible');
    const m=S.m?S.m[i]:null;tip.innerHTML=`<b>${mdw(cal[i])}</b><div>收盤 ${ucPx(S.c[i])}</div>`+(m!=null?`<div>50 日線 ${ucPx(m)}（收盤${S.c[i]>=m?'高':'低'} ${Math.abs(S.c[i]/m*100-100).toFixed(1)}%）</div>`:'');
    tip.hidden=false;const tw=tip.offsetWidth;tip.style.left=Math.max(0,Math.min(W-tw,xx+(xx>W/2?-tw-8:8)))+'px';};
  const hide=()=>{tip.hidden=true;cx.setAttribute('visibility','hidden');};
  sv.addEventListener('mousemove',show);sv.addEventListener('mouseleave',hide);sv.addEventListener('touchstart',show,{passive:true});sv.addEventListener('touchmove',show,{passive:true});}
/* 分析師（Yahoo Finance）：今年、明年 EPS 預估與 90 天前、營收預估、分析師的價位（引述分析師的數字，附 Yahoo 的來源連結）、評等、財報日 */
function ucAn(c,S){const A=S.an,src=`https://finance.yahoo.com/quote/${encodeURIComponent(c.replace(/[./]/g,'-'))}/analysis/`;
  if(!A)return `<h3>分析師</h3><p class=st>分析師資料還沒有（每天美股收盤後更新）。</p>`;
  const fy=y=>{if(!y||!y.end)return '';const m=+y.end.slice(5,7),yr=+y.end.slice(0,4);return m===12?`${yr} 年`:`到 ${yr} 年 ${m} 月的年度`;};
  const L=[];
  [['y0',null],['y1','y0']].forEach(([k,pk])=>{const y=A[k];if(!y||!y.e||y.e[0]==null)return;const e=y.e[0],nn=y.e[1],ya=y.e[2],t=y.t90;
    let s=`${fy(y)} EPS 預估 <b>${f(e,2)}</b>（${nn?nn+' 位':''}`;
    const p=[];if(t!=null&&t!==0&&Math.abs(e-t)/Math.abs(t)>=0.005)p.push(`90 天前 ${f(t,2)}，<span class=${e>t?'up':'dn'}>${e>t?'上修':'下修'}</span>`);
    else if(t!=null)p.push('和 90 天前差不多');
    const yl=pk?'前一年':'去年';
    if(ya!=null&&ya>0)p.push(`比${yl} ${sgn((e/ya-1)*100,0,'%')}`);
    else if(ya!=null&&ya<0)p.push(e>=0?`${yl}虧損、轉盈`:e>ya?'虧損縮小':'虧損擴大');
    s+=(nn&&p.length?'；':'')+p.join('；')+'）';
    if(y.r&&y.r[0]!=null)s+=`<div class=st>營收預估 ${f(y.r[0],y.r[0]>=100?0:1)} 億美元${y.r[1]?`（${pk?'比前一年':'比去年'} ${sgn((y.r[0]/y.r[1]-1)*100,0,'%')}）`:''}</div>`;
    L.push(`<p class=ucl>${s}</p>`);});
  const tp=A.tp;if(tp&&(tp[1]!=null||tp[0]!=null)){const v=tp[1]!=null?tp[1]:tp[0],pr=S.px?(v/S.px-1)*100:null;
    L.push(`<p class=ucl>目標價 <b>${ucPx(v)}</b>${pr!=null?`，比現價${pr>=0?'高':'低'} ${f(Math.abs(pr),1)}%`:''}（${A.n?A.n+' 位分析師的':''}${tp[1]!=null?'中位數':'平均'}）`+
      (tp[2]!=null&&tp[3]!=null?`<span class="st ucb">最高 ${ucPx(tp[2])}、最低 ${ucPx(tp[3])}</span>`:'')+`</p>`);}
  const rc=A.rc;if(rc&&rc.some(v=>v)){const nm=['強力看好','看好','中立','看淡','強力看淡'];
    L.push(`<p class=st>評等：${rc.map((v,i)=>v?`${nm[i]} ${v}`:'').filter(Boolean).join('、')}</p>`);}
  const ed=A.ed||[],last=(UCD.cal||[]).slice(-1)[0]||'';
  if(ed.length){const d0=ed[0],d1=ed[ed.length-1];
    if(d1<=last)L.push(`<p class=ucl>上次財報 ${mdw(d1)}（下次的日期還沒公布）</p>`);
    else L.push(`<p class=ucl>下次財報 <b>${ed.length>1?`${ucMd(d0)}～${ucMd(d1)}`:mdw(d0)}</b>${A.ede?'（公司還沒公布，Yahoo 估的日期）':''}</p>`);}
  return `<h3>分析師<span class=sub><a href="${src}" target=_blank rel=noopener>Yahoo Finance</a>${S.an_at?`・${ucMd(S.an_at)} 收盤後`:''}</span></h3>${L.join('')||'<p class=st>沒有分析師的預估。</p>'}`;}
/* 配置頁美股列、名單、接下來的買賣裡的股票名：點了開卡片（data-us） */
document.addEventListener('click',e=>{if(e.defaultPrevented)return;const a=e.target.closest&&e.target.closest('[data-us]');if(!a||!ucOn())return;
  if(ucOpen(a.dataset.us))e.preventDefault();});
window.addEventListener('hashchange',()=>{const c=ucCur();if(c)ucRender(c);});
let UCR=0;addEventListener('resize',()=>{clearTimeout(UCR);UCR=setTimeout(()=>{const c=ucCur();if(c&&!$('#dv').hidden)ucRender(c,true);},250);});
"""

CSS = r"""
/* 美股個股卡（uscardpage.py） */
.csec.uc h3 .sub a{color:var(--acc)}
.ucl{margin:4px 0;font-size:14px;line-height:1.7}.ucl b{font-weight:700}.ucl .ucb{display:block;line-height:1.5}
.uclk{display:flex;flex-wrap:wrap;gap:6px 18px;margin:8px 0 0;font-size:13.5px}.uclk a{color:var(--acc)}
.ucfv{border-collapse:collapse;font-size:13.5px;min-width:0}
.ucfv th{font-weight:600;color:var(--ink2);font-size:12px;padding:4px 10px 4px 0;text-align:left;white-space:nowrap}
.ucfv th span{display:block;font-weight:400;color:var(--mut)}
.ucfv td{padding:5px 10px 5px 0;border-top:1px solid var(--line);text-align:left;white-space:nowrap;font-variant-numeric:tabular-nums}
.ucfv td.l{white-space:normal}.ucfv td.l b{font-weight:600;margin-right:6px}.ucfv td.l span{font-size:12px;color:var(--mut);white-space:nowrap}
.ucfv i{font-style:normal;font-weight:700;margin-right:5px}.ucfv i.ucok{color:var(--loss)}.ucfv i.ucno{color:var(--gain)}
.ucw{position:relative;margin-top:4px}
.uctip{position:absolute;top:4px;background:var(--ink);color:var(--bg);font-size:12px;line-height:1.5;padding:5px 8px;border-radius:6px;pointer-events:none;white-space:nowrap;z-index:2}
.lg .ucdsh{width:16px;height:0;border-top:2px dashed var(--amber);background:none}
"""
