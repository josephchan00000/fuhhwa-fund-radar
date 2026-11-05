"""盤前戰情（選擇權頁 x9op.html 最上面；資料 data/lab/premkt.json，arm/lab/premkt.py 算；驗證 docs/lab_premarket_plan.md 第 12、13 節）。

使用者 2026-11-05：「我要一眼可以知道買賣點的互動式網頁，要很炫砲的方式呈現」。版面：
  ① 深色戰情卡：預估 09:01 指數（平常差多少、八成在多少內）＋三個驗證過的籌碼風向
  ② 今天的買賣點：四張卡（做多、做空、追多、追空：進場、停損、目標、報酬÷風險、碰到進場價的比例），
     點一張，右邊（手機在下面）的價位圖畫出那筆的進場線、停損區、目標區
  ③ 收起來：全部籌碼期貨數字（標明過去有沒有用）、這些數字怎麼來的
伺服器端畫好（含 SVG）；瀏覽器只負責切換卡片、點價位帶看來源、開頭數字跳動、「可買幾口」
（帳戶與每筆上限只存在使用者瀏覽器，localStorage 'txoCalc'）。CSS class 一律 pz 開頭。
"""
from __future__ import annotations

import html
import json

KIND_LEAN = {  # 事實表的項目 → 驗證過的因素（premktspec.FACTORS）
    "fx_fut": ("fx_fut_chg", "fx_fut_lvl"), "retail": ("retail",), "fx_opt": ("fx_opt_chg",), "pcr": ("pcr",),
    "inst_total": ("inst",), "margin": ("margin",), "basis": ("basis",), "night": ("night",), "sox": ("sox",),
    "tech": ("rsi", "ma20", "kd", "macd"),
}
SC_TAG = {"long": ("做多", "回測支撐", "u"), "short": ("做空", "反彈壓力", "d"), "break": ("追多", "突破壓力", "u"),
          "breakdown": ("追空", "跌破支撐", "d")}

CSS = (
    ".pz{--zt:#eef2ff;--zm:#a3aecb;--zl:rgba(148,163,255,.2);--zg:#fbbf24;--zu:#22d3ee;--zd:#fb7185;--zs:#f43f5e;--zw:#34d399;"
    "position:relative;margin:10px 0 14px;padding:16px;border-radius:18px;color:var(--zt);overflow:hidden;isolation:isolate;"
    "background:radial-gradient(120% 80% at 0% 0%,rgba(34,211,238,.16),transparent 55%),"
    "radial-gradient(120% 90% at 100% 0%,rgba(168,85,247,.22),transparent 60%),linear-gradient(160deg,#0a0f22,#111634 55%,#1a0f35);"
    "box-shadow:0 12px 32px rgba(10,15,40,.32),inset 0 0 0 1px rgba(148,163,255,.16)}"
    ".pz::before{content:'';position:absolute;inset:0;z-index:-1;pointer-events:none;"
    "background-image:linear-gradient(rgba(148,163,255,.07) 1px,transparent 1px),linear-gradient(90deg,rgba(148,163,255,.07) 1px,transparent 1px);"
    "background-size:22px 22px;-webkit-mask-image:linear-gradient(#000,transparent 75%);mask-image:linear-gradient(#000,transparent 75%)}"
    ".pz a{color:var(--zu)}"
    ".pz-hd{display:flex;flex-wrap:wrap;align-items:center;gap:6px 12px;font-size:13px;color:var(--zm)}"
    ".pz .pz-live{margin:0;display:inline-flex;align-items:center;gap:6px;font-weight:700;letter-spacing:2px;color:var(--zt);font-size:13px}"
    ".pz-live i{width:8px;height:8px;border-radius:50%;background:var(--zw);box-shadow:0 0 0 0 rgba(52,211,153,.6);animation:pzp 2s infinite}"
    "@keyframes pzp{0%{box-shadow:0 0 0 0 rgba(52,211,153,.55)}70%{box-shadow:0 0 0 9px rgba(52,211,153,0)}100%{box-shadow:0 0 0 0 rgba(52,211,153,0)}}"
    ".pz-date{color:var(--zt);font-weight:600}.pz-upd{margin-left:auto}"
    ".pz-warn{margin:10px 0 0;padding:7px 11px;border-radius:10px;background:rgba(251,113,133,.14);border:1px solid rgba(251,113,133,.35);font-size:13px}"
    ".pz-top{display:grid;grid-template-columns:1fr;gap:12px;margin-top:10px}"
    ".pz-est small{display:block;font-size:13px;color:var(--zm);letter-spacing:1px}"
    ".pz-num{display:block;font-size:50px;line-height:1.08;font-weight:800;font-variant-numeric:tabular-nums;letter-spacing:.5px;"
    "background:linear-gradient(92deg,#fff7d6,#fbbf24 45%,#f59e0b);-webkit-background-clip:text;background-clip:text;color:transparent;"
    "filter:drop-shadow(0 0 14px rgba(251,191,36,.35))}"
    ".pz-chg{font-size:14px;color:var(--zm)}.pz-chg em{font-style:normal;font-weight:700}"
    ".pz-uc{color:var(--zu)}.pz-dc{color:var(--zd)}"
    ".pz-rng{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}.pz-rng span{padding:4px 10px;border-radius:999px;font-size:13px;"
    "background:rgba(251,191,36,.12);border:1px solid rgba(251,191,36,.35)}.pz-rng b{color:#fde68a;font-variant-numeric:tabular-nums}"
    ".pz-kv{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;margin:0}"
    ".pz-kv div{padding:8px 10px;border-radius:12px;background:rgba(255,255,255,.05);border:1px solid var(--zl)}"
    ".pz-kv dt{font-size:11.5px;color:var(--zm)}.pz-kv dd{margin:0;font-size:16px;font-weight:700;font-variant-numeric:tabular-nums}"
    ".pz-kv dd small{display:block;font-size:11.5px;font-weight:500}"
    ".pz-wind{margin-top:14px}.pz .pz-wind h3{margin:0 0 6px;font-size:15px;letter-spacing:1px;color:var(--zt)}"
    ".pz-wind h3 span{display:block;font-size:12.5px;font-weight:500;color:var(--zm);letter-spacing:0}"
    ".pz-gauge{display:flex;height:6px;border-radius:99px;overflow:hidden;background:rgba(255,255,255,.08);margin:0 0 8px}"
    ".pz-gauge i{display:block}.pz-gauge .gu{background:linear-gradient(90deg,#0891b2,var(--zu))}.pz-gauge .gd{background:linear-gradient(90deg,var(--zd),#e11d48)}"
    ".pz-gauge .gn{background:rgba(255,255,255,.18)}"
    ".pz-ws{display:grid;grid-template-columns:1fr;gap:6px}"
    ".pz-w{display:flex;gap:10px;align-items:flex-start;padding:8px 10px;border-radius:12px;background:rgba(255,255,255,.04);border:1px solid var(--zl)}"
    ".pz-wi{flex:none;width:30px;height:30px;border-radius:9px;display:flex;align-items:center;justify-content:center}.pz-wi svg{width:14px;height:14px}"
    ".pz-w.wu .pz-wi{color:#04131a;background:var(--zu);box-shadow:0 0 14px rgba(34,211,238,.45)}"
    ".pz-w.wd .pz-wi{color:#25040a;background:var(--zd);box-shadow:0 0 14px rgba(251,113,133,.45)}"
    ".pz-w.wn .pz-wi{color:var(--zm);background:rgba(255,255,255,.1)}"
    ".pz-w div>b{display:block;font-size:14px}.pz-w div>span{display:block;font-size:12.5px;color:var(--zm);line-height:1.5}"
    ".pz-w .pz-wh{color:var(--zt);opacity:.85}"
    ".pz-chk{margin:12px 0 0;font-size:12.5px;color:var(--zm)}"
    ".pz .pz-h{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 8px;margin:0 0 10px;font-size:19px;letter-spacing:1px;color:var(--zt)}"
    ".pz-h small{font-size:12.5px;font-weight:500;color:var(--zm);letter-spacing:0}"
    ".pz-grid{display:grid;grid-template-columns:1fr;gap:12px}"
    ".pz-cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;align-content:start}"
    ".pz-c{position:relative;display:flex;flex-direction:column;gap:2px;padding:10px 11px 9px;border-radius:14px;text-align:left;color:inherit;"
    "font:inherit;cursor:pointer;background:rgba(255,255,255,.045);border:1px solid var(--zl);transition:transform .15s,box-shadow .2s,border-color .2s}"
    ".pz-c:hover{transform:translateY(-2px)}.pz-c:focus-visible{outline:2px solid var(--zg);outline-offset:2px}"
    ".pz-c.cu.on{border-color:var(--zu);box-shadow:0 0 0 1px var(--zu),0 0 22px rgba(34,211,238,.35)}"
    ".pz-c.cd.on{border-color:var(--zd);box-shadow:0 0 0 1px var(--zd),0 0 22px rgba(251,113,133,.35)}"
    ".pz-ck{display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--zm)}"
    ".pz-ck b{padding:1px 8px;border-radius:7px;font-size:13px;letter-spacing:1px}"
    ".pz-c.cu .pz-ck b{background:var(--zu);color:#04131a}.pz-c.cd .pz-ck b{background:var(--zd);color:#25040a}"
    ".pz-ce{font-size:27px;font-weight:800;font-variant-numeric:tabular-nums;line-height:1.2}"
    ".pz-ce small{font-size:12px;font-weight:500;color:var(--zm);margin-left:4px;white-space:nowrap}"
    ".pz-cl{display:flex;justify-content:space-between;gap:6px;font-size:12.5px;font-variant-numeric:tabular-nums}"
    ".pz-cl .s{color:#fda4af}.pz-cl .t{color:#6ee7b7}"
    ".pz-rr{display:flex;align-items:center;gap:6px;margin-top:3px;font-size:12px;color:var(--zm)}"
    ".pz-rr i{flex:1;display:flex;height:6px;border-radius:99px;overflow:hidden;background:rgba(255,255,255,.08)}"
    ".pz-rr i s{display:block;background:var(--zs)}.pz-rr i u{display:block;background:var(--zw)}.pz-rr b{color:var(--zt);font-size:13px}"
    ".pz-hit{font-size:12px;color:var(--zm)}.pz-hit b{color:var(--zg);font-size:13px}"
    ".pz-chart{min-width:0}.pz-svg{display:block;width:100%;height:auto;border-radius:14px;touch-action:manipulation}"
    ".pz-svg text{font-family:inherit;font-variant-numeric:tabular-nums}"
    ".pz-svg .pz-s{opacity:0;transition:opacity .35s;pointer-events:none}.pz-svg .pz-s.on{opacity:1}"
    ".pz-svg .pz-b{cursor:pointer;transition:opacity .25s}.pz-svg.act .pz-b{opacity:.55}.pz-svg .pz-b.sel{opacity:1}"
    ".pz-svg .pz-el{animation:pzg 2.4s ease-in-out infinite}@keyframes pzg{50%{opacity:.55}}"
    ".pz-svg .pz-s.on .pz-ar{stroke-dasharray:6 5;animation:pzd 1.1s linear infinite}@keyframes pzd{to{stroke-dashoffset:-22}}"
    ".pz-info{min-height:20px;margin:6px 2px 0;font-size:12.5px;color:var(--zm);line-height:1.6}"
    ".pz-det{margin-top:8px;padding:10px 12px;border-radius:12px;background:rgba(255,255,255,.045);border:1px solid var(--zl);font-size:13.5px;line-height:1.7}"
    ".pz-det b{font-variant-numeric:tabular-nums}.pz-det .why{color:var(--zm);font-size:12.5px}"
    ".pz-det .mny{display:grid;grid-template-columns:auto 1fr;gap:2px 10px;margin:4px 0 0}.pz-det .mny dt{color:var(--zm)}.pz-det .mny dd{margin:0}"
    ".pz-det .l{color:#fda4af}.pz-det .g{color:#6ee7b7}"
    ".pz-fine{margin:10px 0 0;font-size:12px;color:var(--zm);line-height:1.6}"
    ".pz-more{margin:10px 0;border:1px solid var(--line);border-radius:12px;padding:0 12px}"
    ".pz-more>summary{cursor:pointer;padding:10px 0;font-weight:600;color:var(--ink)}.pz-more[open]>summary{border-bottom:1px solid var(--line)}"
    ".pz-more .pzt td:nth-child(2){text-align:left;white-space:normal}.pz-more .pzt td:nth-child(3){text-align:left;white-space:normal;font-size:12.5px}"
    ".pz-ok{color:var(--t0);font-weight:600}.pz-no{color:var(--mut)}"
    ".pz-more p,.pz-more li{font-size:13px;color:var(--ink2);line-height:1.7}"
    "@media (min-width:860px){.pz-top{grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);align-items:end}"
    ".pz-grid{grid-template-columns:minmax(0,1fr) minmax(0,1.05fr)}.pz-num{font-size:60px}.pz-ws{grid-template-columns:repeat(3,minmax(0,1fr))}}"
    "@media (max-width:380px){.pz{padding:14px 12px}.pz-num{font-size:42px}.pz-ce{font-size:21px}.pz-ce small{font-size:11px}"
    ".pz-cl{font-size:11.5px}.pz-kv dd{font-size:14px}.pz-c{padding:9px 9px 8px}}"
    "@media (prefers-reduced-motion:reduce){.pz-live i,.pz-svg .pz-el,.pz-svg .pz-s.on .pz-ar{animation:none}.pz-c,.pz-svg .pz-s{transition:none}}"
)

JS = r"""<script>(function(){
var w=document.getElementById('pmstale');var t=new Date(Date.now()+8*3600e3).toISOString().slice(0,10);
if(w&&t>w.dataset.next)w.hidden=false;
var D=null;try{D=JSON.parse((document.getElementById('pzd')||{}).textContent||'null')}catch(e){}
var nf=function(x){return Math.round(x).toLocaleString('zh-TW')};
var n=document.querySelector('.pz-num');
if(n&&!(window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches)){var to=+n.dataset.to,fr=to-Math.max(60,Math.round(to*0.006)),t0=null;
 var step=function(ts){if(!t0)t0=ts;var p=Math.min(1,(ts-t0)/700),e=1-Math.pow(1-p,3);n.textContent=nf(fr+(to-fr)*e);if(p<1)requestAnimationFrame(step)};requestAnimationFrame(step);}
if(!D)return;
var st={acct:1000000,cap:'O1'};try{Object.assign(st,JSON.parse(localStorage.getItem('txoCalc')||'{}'))}catch(e){}
var cap={O1:0.02,O2:0.03,O3:0.05}[st.cap]||0.02;
var svg=document.querySelector('.pz-svg'),det=document.getElementById('pzdet'),info=document.getElementById('pzinfo');
function md(d){return +d.slice(5,7)+'/'+ +d.slice(8,10)}
function show(i){var c=D.sc[i];if(!c)return;
 document.querySelectorAll('.pz-c').forEach(function(b){b.classList.toggle('on',+b.dataset.s===i);b.setAttribute('aria-pressed',+b.dataset.s===i)});
 if(svg)svg.querySelectorAll('.pz-s').forEach(function(g){g.classList.toggle('on',+g.dataset.s===i)});
 var o=c.opt,h='<div class="why">'+c.why+'</div><dl class="mny"><dt>小台一口</dt><dd>停損賠 <b class="l">'+nf(c.mtx.loss)+'</b> 元、到目標賺 <b class="g">'+nf(c.mtx.gain)+'</b> 元</dd>';
 if(o){var one=o.max,lots=one>0?Math.floor(st.acct*cap/one):0;
  h+='<dt>選擇權</dt><dd>買 '+md(o.xd)+' 到期 '+nf(o.k)+' '+(o.cp==='C'?'買權':'賣權')+'，約 <b>'+o.pe.toFixed(1)+'</b> 點（停損時約 '+o.ps.toFixed(1)+'、目標時約 '+o.pt.toFixed(1)+'）</dd>'+
   '<dt>一口</dt><dd>停損賠 <b class="l">'+nf(o.loss)+'</b>、到目標賺 <b class="g">'+nf(o.gain)+'</b> 元；權利金歸零最多賠 '+nf(o.max)+' 元</dd>'+
   '<dt>可買</dt><dd>帳戶 '+nf(st.acct)+' 元、每筆 '+Math.round(cap*100)+'%：'+(lots>0?'最多 <b>'+lots+'</b> 口':'買不到 1 口')+'</dd>';}
 det.innerHTML=h+'</dl>';}
document.querySelectorAll('.pz-c').forEach(function(b){b.addEventListener('click',function(){show(+b.dataset.s)})});
if(svg){svg.classList.add('act');svg.querySelectorAll('.pz-b').forEach(function(r){r.addEventListener('click',function(){
 svg.querySelectorAll('.pz-b.sel').forEach(function(x){x.classList.remove('sel')});r.classList.add('sel');
 var b=D.bands[+r.dataset.b];if(b&&info)info.innerHTML='<b>'+(b.lo===b.hi?nf(b.lo):nf(b.lo)+'～'+nf(b.hi))+'</b>：'+b.src.map(function(s){return s[0]+' '+nf(s[1])}).join('、');});});}
show(0);
})();</script>"""


def _n(x, sign: bool = False) -> str:
    if x is None:
        return "—"
    v = f"{abs(x):,.0f}"
    if sign:
        return ("+" if x > 0 else "−" if x < 0 else "") + v
    return ("−" if x < 0 else "") + v


def _sp(x: float) -> str:
    return ("+" if x > 0 else "−" if x < 0 else "") + f"{abs(x):.2f}"


def _pct(p) -> str:
    return "—" if p is None else ("<1%" if p < 0.01 else f"{p * 100:.0f}%")


# ── 價位圖（SVG） ────────────────────────────────────────────────────────────

W, H, TOP, BOT, X0, X1 = 360, 470, 16, 16, 80, 298


def _spread(ys: list[float], gap: float, lo: float, hi: float) -> list[float]:
    """由上往下排好的標籤 y，彼此至少差 gap（往下推，超出底再整體往上推）。"""
    out = []
    for y in ys:
        out.append(max(y, out[-1] + gap) if out else max(y, lo))
    over = out[-1] - hi if out else 0
    if over > 0:
        out = [y - over for y in out]
        for i in range(len(out) - 2, -1, -1):
            out[i] = min(out[i], out[i + 1] - gap)
    return out


def ladder(pm: dict) -> str:
    e = html.escape
    est, em, v = pm["est"], pm.get("em") or 0, pm.get("v") or {}
    bands, sc = pm.get("bands") or [], pm.get("sc") or []
    band80 = v.get("p80") or (em * 0.5 if em else 0)
    typ = v.get("typ") or 0
    ps = [est + band80, est - band80, pm["close"]] + [x for b in bands for x in (b["lo"], b["hi"])]
    ps += [x for c in sc for x in (c["entry"], c["stop"], c["target"])]
    pmax, pmin = max(ps), min(ps)
    pad = max((pmax - pmin) * 0.05, 5)
    pmax, pmin = pmax + pad, pmin - pad

    def y(p):
        return round(TOP + (pmax - p) / (pmax - pmin) * (H - TOP - BOT), 1)
    o = [f'<svg class="pz-svg" viewBox="0 0 {W} {H}" role="img" aria-label="今天的價位圖：預估開盤、壓力、支撐與買賣點">',
         '<defs><linearGradient id="pzbg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1a1240"/><stop offset=".5" stop-color="#0d1330"/>'
         '<stop offset="1" stop-color="#062027"/></linearGradient>'
         '<filter id="pzgl" x="-20%" y="-200%" width="140%" height="500%"><feGaussianBlur stdDeviation="3"/></filter>'
         '<marker id="pzah" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
         '<path d="M0 0L10 5L0 10z" fill="#34d399"/></marker></defs>',
         f'<rect x="0" y="0" width="{W}" height="{H}" rx="14" fill="url(#pzbg)"/>',
         f'<text x="{X1}" y="{TOP + 10}" text-anchor="end" font-size="10.5" fill="#fb7185" opacity=".8">↑ 壓力</text>',
         f'<text x="{X1}" y="{H - BOT - 2}" text-anchor="end" font-size="10.5" fill="#22d3ee" opacity=".8">↓ 支撐</text>']
    # 預估開盤：八成範圍、平常範圍、中線
    if band80:
        o.append(f'<rect x="{X0}" y="{y(est + band80)}" width="{X1 - X0}" height="{y(est - band80) - y(est + band80)}" fill="#fbbf24" opacity=".08"/>')
    if typ:
        o.append(f'<rect x="{X0}" y="{y(est + typ)}" width="{X1 - X0}" height="{y(est - typ) - y(est + typ)}" fill="#fbbf24" opacity=".14"/>')
    o.append(f'<line class="pz-el" x1="{X0}" x2="{X1}" y1="{y(est)}" y2="{y(est)}" stroke="#fbbf24" stroke-width="6" opacity=".55" filter="url(#pzgl)"/>'
             f'<line x1="{X0}" x2="{X1}" y1="{y(est)}" y2="{y(est)}" stroke="#fde68a" stroke-width="2"/>')
    # 昨收
    o.append(f'<line x1="{X0}" x2="{X1}" y1="{y(pm["close"])}" y2="{y(pm["close"])}" stroke="#a3aecb" stroke-width="1" stroke-dasharray="3 4" opacity=".7"/>')
    left, right = [], []                                 # (y, 文字, 顏色)
    left.append((y(est), f"預估 {_n(est)}", "#fde68a", True))
    right.append((y(pm["close"]), f"昨收 {_n(pm['close'])}", "#a3aecb"))
    for i, b in enumerate(bands):
        col = "#fb7185" if b["side"] == "up" else "#22d3ee" if b["side"] == "dn" else "#fbbf24"
        y1, y2 = y(b["hi"]), y(b["lo"])
        hgt = max(y2 - y1, 5)
        yc = (y1 + y2) / 2
        src = "、".join(f"{s[0]} {_n(s[1])}" for s in b["src"])
        o.append(f'<g class="pz-b" data-b="{i}"><title>{e(src)}</title>'
                 f'<rect x="{X0}" y="{round(yc - hgt / 2, 1)}" width="{X1 - X0}" height="{round(hgt, 1)}" rx="3" fill="{col}" opacity=".26"/>'
                 f'<rect x="{X0}" y="{round(yc - hgt / 2, 1)}" width="3" height="{round(hgt, 1)}" fill="{col}"/>'
                 f'<rect x="0" y="{round(yc - 11, 1)}" width="{W}" height="22" fill="transparent"/></g>')
        left.append((yc, _n(b["lo"]) if b["lo"] == b["hi"] else _n(b["mid"]), col, False))
        if b.get("touch") is not None and b["side"] != "at":
            right.append((yc, f"碰 {_pct(b['touch'])}", col))
    # 買賣點（一筆一組，點卡片才出現）
    BX0, BX1 = 196, X1
    for i, c in enumerate(sc):
        up = c["target"] > c["entry"]
        ye, ys, yt = y(c["entry"]), y(c["stop"]), y(c["target"])
        col = "#22d3ee" if up else "#fb7185"
        o.append(f'<g class="pz-s" data-s="{i}">'
                 f'<rect x="{BX0}" y="{min(ye, ys)}" width="{BX1 - BX0}" height="{max(abs(ys - ye), 2)}" fill="#f43f5e" opacity=".32"/>'
                 f'<rect x="{BX0}" y="{min(ye, yt)}" width="{BX1 - BX0}" height="{max(abs(yt - ye), 2)}" fill="#34d399" opacity=".26"/>'
                 f'<line x1="{X0}" x2="{BX1}" y1="{ye}" y2="{ye}" stroke="{col}" stroke-width="2.5"/>'
                 f'<line x1="{BX0}" x2="{BX1}" y1="{ys}" y2="{ys}" stroke="#f43f5e" stroke-width="1.5" stroke-dasharray="4 3"/>'
                 f'<line x1="{BX0}" x2="{BX1}" y1="{yt}" y2="{yt}" stroke="#34d399" stroke-width="1.5" stroke-dasharray="4 3"/>'
                 f'<line class="pz-ar" x1="{BX0 + 14}" x2="{BX0 + 14}" y1="{ye}" y2="{yt + (6 if up else -6)}" stroke="#34d399" stroke-width="2" marker-end="url(#pzah)"/>'
                 f'<text x="{BX1 - 4}" y="{yt + (12 if up else -4)}" text-anchor="end" font-size="11" font-weight="700" fill="#6ee7b7">目標 {_n(c["target"])}</text>'
                 f'<text x="{BX1 - 4}" y="{ys + (-4 if up else 12)}" text-anchor="end" font-size="11" font-weight="700" fill="#fda4af">停損 {_n(c["stop"])}</text>'
                 f'<rect x="{BX0 - 76}" y="{ye - 10}" width="72" height="20" rx="6" fill="{col}"/>'
                 f'<text x="{BX0 - 40}" y="{ye + 4.5}" text-anchor="middle" font-size="11.5" font-weight="800" fill="#06101a">進 {_n(c["entry"])}</text></g>')
    ly = _spread([t[0] for t in sorted(left)], 13, TOP + 6, H - BOT - 4)
    for (yy, txt, col, bold), y2 in zip(sorted(left), ly):
        o.append(f'<text x="{X0 - 6}" y="{round(y2 + 4, 1)}" text-anchor="end" font-size="{11.5 if bold else 11}" '
                 f'font-weight="{800 if bold else 600}" fill="{col}">{e(txt)}</text>')
    ry = _spread([t[0] for t in sorted(right)], 13, TOP + 18, H - BOT - 16)
    for (yy, txt, col), y2 in zip(sorted(right), ry):
        o.append(f'<text x="{W - 4}" y="{round(y2 + 4, 1)}" text-anchor="end" font-size="10.5" fill="{col}" opacity=".9">{e(txt)}</text>')
    o.append("</svg>")
    return "".join(o)


# ── 區塊 ─────────────────────────────────────────────────────────────────────

def _wind(v: dict) -> str:
    leans = v.get("leans") or []
    if not leans:
        return ""
    nu = sum(1 for x in leans if x["lean"] > 0)
    nd = sum(1 for x in leans if x["lean"] < 0)
    nn = len(leans) - nu - nd
    tot = len(leans)
    g = (f'<div class="pz-gauge" aria-hidden="true"><i class="gu" style="width:{nu / tot * 100:.0f}%"></i>'
         f'<i class="gn" style="width:{nn / tot * 100:.0f}%"></i><i class="gd" style="width:{nd / tot * 100:.0f}%"></i></div>')
    out = []
    for x in leans:
        cls, ic, word = (("wu", '<path d="M7 2l6 10H1z" fill="currentColor"/>', "偏多") if x["lean"] > 0 else
                         ("wd", '<path d="M7 12L1 2h12z" fill="currentColor"/>', "偏空") if x["lean"] < 0 else
                         ("wn", '<rect x="2" y="6" width="10" height="2.4" rx="1" fill="currentColor"/>', "中間"))
        hist = ""
        if x.get("mean") is not None:
            hist = (f'<span class="pz-wh">過去這種隔天 09:01→收盤：平均 {x["mean"] / 100:+.2f}%、上漲 {_pct(x["up"])}</span>').replace("-", "−")
        out.append(f'<div class="pz-w {cls}"><span class="pz-wi"><svg viewBox="0 0 14 14" aria-hidden="true">{ic}</svg></span><div><b>{html.escape(x["t"])}　{word}</b>'
                   f'<span>{html.escape(x["txt"])}（{x["d"][5:7].lstrip("0")}/{x["d"][8:].lstrip("0")}）</span>{hist}</div></div>')
    return (f'<div class="pz-wind"><h3>籌碼風向<span>14 個常見說法裡，過去比隨便猜好的 {tot} 項：{nd} 項偏空、{nu} 項偏多'
            + (f"、{nn} 項中間" if nn else "") + f'</span></h3>{g}<div class="pz-ws">{"".join(out)}</div></div>')


def _card(i: int, c: dict) -> str:
    k, nm, side = SC_TAG.get(c.get("k"), (c["name"][-2:], c["name"][:-2], "u"))
    risk, rew = c["risk"], c["reward"]
    rp = risk / (risk + rew) * 100 if risk + rew else 50
    hit = f'<span class="pz-hit">今天碰到進場價的機會 <b>{_pct(c["hit"])}</b></span>' if c.get("hit") is not None else ""
    sg = 1 if c["target"] > c["entry"] else -1
    return (f'<button type="button" class="pz-c c{side}" data-s="{i}" aria-pressed="false">'
            f'<span class="pz-ck"><b>{k}</b>{html.escape(nm)}</span>'
            f'<span class="pz-ce">{_n(c["entry"])}<small>進場</small></span>'
            f'<span class="pz-cl"><span class="s">停損 {_n(c["stop"])}（{_n(-sg * risk, True)}）</span></span>'
            f'<span class="pz-cl"><span class="t">目標 {_n(c["target"])}（{_n(sg * rew, True)}）</span></span>'
            f'<span class="pz-rr"><i><s style="width:{rp:.0f}%"></s><u style="width:{100 - rp:.0f}%"></u></i>1 : <b>{c["rr"]:.1f}</b></span>{hit}</button>')


def _facts(pm: dict) -> str:
    v = pm.get("v") or {}
    ok = set(v.get("chips_ok") or [])
    rows = []
    for f in pm.get("facts") or []:
        fs = KIND_LEAN.get(f["k"])
        if not v:
            tag = ""
        elif not fs:
            tag = '<span class="pz-no">沒驗證</span>'
        elif any(x in ok for x in fs):
            tag = '<span class="pz-ok">過去有用（今天偏多偏空見上面「籌碼風向」）</span>'
        else:
            tag = '<span class="pz-no">過去沒有比隨便猜好</span>'
        if f["k"] in ("night", "sox") and v:
            tag = '<span class="pz-no">已反映在開盤，開盤後沒有順勢</span>'
        note = f'<br><span class="opdist">{html.escape(f["note"])}</span>' if f.get("note") else ""
        d = f'{int(f["d"][5:7])}/{int(f["d"][8:10])}' if f.get("d") else ""
        rows.append(f"<tr><td>{html.escape(f['t'])}<br><span class=\"opdist\">{d}</span></td><td>{html.escape(f['v'])}{note}</td><td>{tag}</td></tr>")
    if not rows:
        return ""
    return ('<details class="pz-more"><summary>全部籌碼、期貨、指標的數字</summary><div class="optw"><table class="opt pzt"><thead><tr><th>項目</th>'
            '<th>數字</th><th>過去驗證</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div></details>")


def _method(pm: dict) -> str:
    from .premkt import KINDS
    v = pm.get("v") or {}
    q2 = v.get("q2") or {}
    li = []
    if v:
        li.append(f'<li><b>預估開盤</b>＝前一天加權指數收盤＋（夜盤台指期收盤 − 台指期 13:30 的價格），對的是 <b>09:01</b> 的指數'
                  f'（09:00:05 那一點還有很多股票是前一天的價格，不能當開盤）。過去 {v.get("n1") or 0:,} 天，誤差中位數是正常波動的 0.23 倍、'
                  f'八成在 0.46 倍內，是「直接用昨天收盤」的一半。清晨 05:00 到 08:45 的消息也會動。</li>')
        if q2.get("x"):
            cells = "".join(f"<td>{x:g} 倍</td>" for x in q2["x"])
            up = "".join(f"<td>{_pct(p)}</td>" for p in q2["up"])
            dn = "".join(f"<td>{_pct(p)}</td>" for p in q2["dn"])
            li.append(f'<li><b>碰到的機會</b>：過去 {v.get("n2") or 0:,} 天，離 09:01 開盤 x 倍正常波動的價位，當天碰到的比例（價位圖右邊、卡片上的數字照這張表內插）：'
                      f'<div class="optw"><table class="opt"><thead><tr><th>距離</th>{cells}</tr></thead><tbody>'
                      f'<tr><td>往上</td>{up}</tr><tr><td>往下</td>{dn}</tr></tbody></table></div></li>')
        li.append(f'<li><b>壓力支撐</b>：價位來自{"、".join(KINDS.values())}，相差 0.25% 以內併成一帶。'
                  f'過去 10 年碰到之後先彈回 0.25 倍正常波動的比例約 {v.get("hold_base", 0.45) * 100:.0f}%，'
                  + ("跟同樣距離的任意價位差不多，<b>沒有一種價位比較擋得住</b>，幾種來源擠在一起也一樣。" if not v.get("lv_ok") else "有過的：" + "、".join(v["lv_ok"]) + "。")
                  + "所以買賣點只是把點數、賺賠算好，進場前自己看盤。</li>")
        li.append('<li><b>籌碼風向</b>：14 個常見說法（外資期貨、散戶小台、外資選擇權、P/C 比、法人、融資、期現價差、夜盤、費半、RSI、均線、KD、MACD）'
                  '逐一測過，只有上面 3 個比隨便猜好；每天差 4～10 個基點，只能當傾向。</li>')
    li.append('<li><b>買賣點</b>：回測支撐＝在支撐帶上緣進、跌破下緣 0.1 倍正常波動停損、目標上方第一個壓力帶；突破＝站上壓力帶上緣 0.1 倍正常波動才進、'
              '回到帶子中間停損、目標再上一個壓力帶（空方對稱）。小台每點 50 元，成本算手續費 25 元、期交稅、1 點滑價（每邊）；'
              '選擇權用今天的隱含波動率估（假設 10:30），實際成交還有買賣價差。</li>')
    for t in pm.get("oi_note") or []:
        li.append(f"<li>選擇權未平倉（全部履約價）：{html.escape(t)}</li>")
    li.append(f'<li>規劃與驗證：docs/lab_premarket_plan.md 第 11～13 節。更新：{html.escape(pm.get("made") or "")}。這裡只是整理與試算，不是買賣建議。</li>')
    return '<details class="pz-more"><summary>這些數字怎麼來的、可信度</summary><ul>' + "".join(li) + "</ul></details>"


def block(pm: dict | None) -> str:
    from .premkt import md, wd
    e = html.escape
    if not pm:
        return ('<section class="pz"><div class="pz-hd"><span class="pz-live"><i></i>盤前戰情</span></div>'
                '<p class="pz-chk">還沒準備好：每個交易日收盤後先算一版，清晨 05:10 用夜盤更新。</p></section>')
    v = pm.get("v") or {}
    em, est, close = pm.get("em"), pm["est"], pm["close"]
    nt = pm.get("night") or {}
    out = ['<section class="pz" id="pz">',
           f'<div class="pz-hd"><h1 class="pz-live"><i></i>盤前戰情</h1><span class="pz-date">{md(pm["next"])}（{wd(pm["next"])}）開盤前</span>'
           f'<span class="pz-upd">{e((pm.get("made") or "")[5:].replace("-", "/"))} 更新</span></div>',
           f'<div class="pz-warn" id="pmstale" hidden data-next="{e(pm["next"])}">這份是 {md(pm["next"])} 開盤前的，已經過期；下一份收盤後會更新。</div>']
    for w in pm.get("warn") or []:
        out.append(f'<div class="pz-warn">{e(w)}</div>')
    ch = est - close
    rng = ""
    if v.get("typ"):
        rng = (f'<div class="pz-rng"><span>平常差 <b>±{_n(v["typ"])}</b></span><span>十次有八次在 <b>±{_n(v["p80"])}</b> 內</span></div>')
    out.append('<div class="pz-top"><div class="pz-est"><small>預估 09:01 加權指數</small>'
               f'<b class="pz-num" data-to="{est}">{_n(est)}</b>'
               f'<div class="pz-chg">比昨收 <em class="{"pz-uc" if ch >= 0 else "pz-dc"}">{_n(ch, True)}（{_sp(ch / close * 100)}%）</em>'
               f'・{e(pm.get("est_src") or "")}</div>' + rng + "</div>")
    nch = (nt.get("c") - nt.get("ref")) if nt.get("c") is not None and nt.get("ref") else None
    out.append('<dl class="pz-kv">'
               f'<div><dt>{md(pm["d"])} 收盤</dt><dd>{_n(close)}<small>高 {_n(pm["hi"])}・低 {_n(pm["lo"])}</small></dd></div>'
               f'<div><dt>夜盤台指期</dt><dd>{_n(nt.get("c"))}<small class="{"pz-uc" if (nch or 0) >= 0 else "pz-dc"}">'
               f'{_n(nch, True) if nch is not None else "—"}{"" if nt.get("done") else "（" + e(str(nt.get("t") or "進行中")) + "）"}</small></dd></div>'
               f'<div><dt>正常波動</dt><dd>±{_n(em)}<small>極端 ±{_n(2 * em) if em else "—"}</small></dd></div></dl></div>')
    out.append(_wind(v))
    chk = pm.get("check") or []
    if chk:
        out.append('<p class="pz-chk">最近幾天：' + "；".join(
            f"{md(c['d'])} 估 {_n(c['est'])}、09:01 實際 {_n(c['open'])}（{_n(c['open'] - c['est'], True)}）" for c in chk) + "</p>")
    out.append("</section>")
    sc = pm.get("sc") or []
    out.append('<section class="pz pz2"><h2 class="pz-h">今天的買賣點<small>點一張，價位圖畫出進場、停損、目標</small></h2><div class="pz-grid">')
    out.append('<div><div class="pz-cards">' + "".join(_card(i, c) for i, c in enumerate(sc)) + '</div><div class="pz-det" id="pzdet"></div></div>')
    out.append(f'<div class="pz-chart">{ladder(pm)}<div class="pz-info" id="pzinfo">點價位帶看它是怎麼來的；右邊「碰」＝過去離開盤這麼遠，當天碰到的比例。</div></div></div>')
    out.append('<p class="pz-fine">價位照公式算：過去 10 年碰到這些價位之後擋住的比例，跟任意價位差不多；報酬÷風險高的卡，目標也比較遠、碰到的機會比較低。'
               '這裡只是把點數與賺賠算好，不是買賣建議。</p></section>')
    out.append(_facts(pm))
    out.append(_method(pm))
    data = {"sc": [{k: c.get(k) for k in ("name", "why", "entry", "stop", "target", "mtx", "opt")} for c in sc],
            "bands": [{"lo": b["lo"], "hi": b["hi"], "src": b["src"]} for b in pm.get("bands") or []]}
    out.append('<script type="application/json" id="pzd">' + json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + "</script>")
    out.append(JS)
    return "".join(out)
