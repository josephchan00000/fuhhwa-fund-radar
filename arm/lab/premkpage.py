"""盤前戰情（選擇權頁 x9op.html 的「盤前」分頁；資料 data/lab/premkt.json，arm/lab/premkt.py 算；驗證 docs/lab_premarket_plan.md 第 12、13 節）。

使用者 2026-11-05：「我要一眼可以知道買賣點的互動式網頁」→ 做了四張買賣點卡（做多、做空、追多、追空）。
使用者 2026-11-12：「你選擇權的判斷都很爛欸」→ 照實檢查最近 4 天 16 張卡：碰到進場價的 12 張裡 7 張先停損（多半 0～6 分鐘）；
那些支撐壓力價位擋住的比例跟任意價位一樣（第 13 節 Q3），停損 90～200 點、這個月一天常走 1,200 點以上。
所以拿掉買賣點卡（docs/lab_txo_plan.md 第 20 節），版面改成：
  ⓪ 今日點位（使用者 2026-11-13：「我要一看就知道今天的壓力支撐建議點位」）：壓力 1～3、開盤、支撐 1～3（來源＋今天碰到的比例，
     比例以現在的預估開盤算、有驗證過）＋四個參考點位（沒有驗證過，照實標出來）
  ① 深色戰情卡：預估 09:01 指數（平常差多少、八成在多少內）＋籌碼風向（只是傾向）
  ② 今天可能走多遠（2026-11-13 起併進今日點位的價位圖：開盤上下 1 倍正常波動＋碰到的比例；點參考點位卡畫進場、停損、目標）
  ③ 最近 10 天：估的開盤 vs 09:01 實際、當天最高最低（照實列，估得差也照列）
  ④ 收起來：全部籌碼期貨數字（標明過去有沒有用）、這些數字怎麼來的
伺服器端畫好（含 SVG）；瀏覽器只負責過期提示與開頭數字跳動。CSS class 一律 pz 開頭。
"""
from __future__ import annotations

import html
import json

KIND_LEAN = {  # 事實表的項目 → 驗證過的因素（premktspec.FACTORS）
    "fx_fut": ("fx_fut_chg", "fx_fut_lvl"), "retail": ("retail",), "fx_opt": ("fx_opt_chg",), "pcr": ("pcr",),
    "inst_total": ("inst",), "margin": ("margin",), "basis": ("basis",), "night": ("night",), "sox": ("sox",),
    "tech": ("rsi", "ma20", "kd", "macd"),
}

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
    ".pz-re{margin-top:8px;font-size:13px;color:#fde68a}"
    # 今日點位（2026-11-13 使用者：「我要一看就知道今天的壓力支撐建議點位」）
    ".pzl-hd{display:flex;justify-content:space-between;align-items:baseline;gap:8px;margin-bottom:8px}"
    ".pzl-hd h2{margin:0;font-size:19px;color:var(--zt)}.pzl-hd span{color:var(--zm);font-size:13px;white-space:nowrap}"
    ".pzl-r{display:grid;grid-template-columns:54px minmax(0,1fr) auto;gap:8px;align-items:center;padding:8px 10px;border-radius:12px;margin:5px 0}"
    ".pzl-k{font-size:13px;font-weight:700;border-radius:8px;text-align:center;padding:3px 0}"
    ".pzl-p{font-size:19px;font-weight:800;font-variant-numeric:tabular-nums;min-width:0}"
    ".pzl-p small{display:block;font-size:12px;color:var(--zm);font-weight:400;margin-top:2px}"
    ".pzl-h{font-size:12px;color:var(--zm);text-align:right;line-height:1.25;white-space:nowrap}.pzl-h b{display:block;font-size:17px;color:var(--zt)}"
    ".pzl-u{background:rgba(251,113,133,.08)}.pzl-u .pzl-k{background:rgba(251,113,133,.18);color:var(--zd)}.pzl-u .pzl-p{color:#fda4af}"
    ".pzl-d{background:rgba(34,211,238,.07)}.pzl-d .pzl-k{background:rgba(34,211,238,.16);color:var(--zu)}.pzl-d .pzl-p{color:#67e8f9}"
    ".pzl-o{background:rgba(251,191,36,.12);border:1px solid rgba(251,191,36,.45)}.pzl-o .pzl-k{background:rgba(251,191,36,.25);color:var(--zg)}"
    ".pzl-o .pzl-p{color:#fde68a;font-size:23px}"
    ".pzl-h3{font-size:16px;margin:16px 0 4px;color:var(--zt)}.pzl-h3 small{font-weight:400;color:var(--zm);font-size:12px;margin-left:6px}"
    ".pzl-g{display:grid;grid-template-columns:minmax(0,1fr);gap:10px;grid-template-areas:'rows' 'ch' 'sc' 'det'}"
    ".pzl-rows{grid-area:rows}.pzl-sc{grid-area:sc}.pzl-ch{grid-area:ch;min-width:0}.pzl-g .pz-det{grid-area:det}"
    "@media (min-width:860px){.pzl-g{grid-template-columns:minmax(0,1fr) minmax(0,1fr);grid-template-areas:'rows ch' 'sc ch' 'det ch';align-items:start}"
    ".pzl-ch{position:sticky;top:8px}}"
    ".pz-cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;align-content:start}"
    ".pz-c{position:relative;display:flex;flex-direction:column;gap:2px;padding:10px 11px 9px;border-radius:14px;text-align:left;color:inherit;"
    "font:inherit;cursor:pointer;background:rgba(255,255,255,.045);border:1px solid var(--zl);transition:transform .15s,box-shadow .2s,border-color .2s}"
    ".pz-c:hover{transform:translateY(-2px)}.pz-c:focus-visible{outline:2px solid var(--zg);outline-offset:2px}"
    ".pz-c.cu.on{border-color:var(--zu);box-shadow:0 0 0 1px var(--zu),0 0 22px rgba(34,211,238,.35)}"
    ".pz-c.cd.on{border-color:var(--zd);box-shadow:0 0 0 1px var(--zd),0 0 22px rgba(251,113,133,.35)}"
    ".pz-ck{display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--zm)}"
    ".pz-ck b{padding:1px 8px;border-radius:7px;font-size:13px;letter-spacing:1px}"
    ".pz-c.cu .pz-ck b{background:var(--zu);color:#04131a}.pz-c.cd .pz-ck b{background:var(--zd);color:#25040a}"
    ".pz-ce{font-size:25px;font-weight:800;font-variant-numeric:tabular-nums;line-height:1.2}"
    ".pz-ce small{font-size:12px;font-weight:500;color:var(--zm);margin-left:4px;white-space:nowrap}"
    ".pz-cl{display:flex;justify-content:space-between;gap:6px;font-size:12.5px;font-variant-numeric:tabular-nums}"
    ".pz-cl .s{color:#fda4af}.pz-cl .t{color:#6ee7b7}"
    ".pz-rr{display:flex;align-items:center;gap:6px;margin-top:3px;font-size:12px;color:var(--zm)}"
    ".pz-rr i{flex:1;display:flex;height:6px;border-radius:99px;overflow:hidden;background:rgba(255,255,255,.08)}"
    ".pz-rr i s{display:block;background:var(--zs)}.pz-rr i u{display:block;background:var(--zw)}.pz-rr b{color:var(--zt);font-size:13px}"
    ".pz-hit{font-size:12px;color:var(--zm)}.pz-hit b{color:var(--zg);font-size:13px}"
    ".pz-svg .pz-s{opacity:0;transition:opacity .35s;pointer-events:none}.pz-svg .pz-s.on{opacity:1}"
    ".pz-svg .pz-b{cursor:pointer;transition:opacity .25s}.pz-svg.act .pz-b{opacity:.55}.pz-svg .pz-b.sel{opacity:1}"
    ".pz-svg .pz-el{animation:pzg 2.4s ease-in-out infinite}@keyframes pzg{50%{opacity:.55}}"
    ".pz-svg .pz-s.on .pz-ar{stroke-dasharray:6 5;animation:pzda 1.1s linear infinite}@keyframes pzda{to{stroke-dashoffset:-22}}"
    ".pz-info{min-height:18px;margin:6px 2px 0;font-size:12.5px;color:var(--zm);line-height:1.6}"
    ".pz-det{padding:10px 12px;border-radius:12px;background:rgba(255,255,255,.045);border:1px solid var(--zl);font-size:13.5px;line-height:1.7}"
    ".pz-det:empty{display:none}"
    ".pz-det b{font-variant-numeric:tabular-nums}.pz-det .why{color:var(--zm);font-size:12.5px}"
    ".pz-det .mny{display:grid;grid-template-columns:auto 1fr;gap:2px 10px;margin:4px 0 0}.pz-det .mny dt{color:var(--zm)}.pz-det .mny dd{margin:0}"
    ".pz-det .l{color:#fda4af}.pz-det .g{color:#6ee7b7}"
    "@media (max-width:380px){.pz-ce{font-size:20px}.pz-ce small{font-size:11px}.pz-cl{font-size:11.5px}.pz-c{padding:9px 9px 8px}}"
    ".pzl-w{margin-top:12px;font-size:12px;color:#fcd34d;background:rgba(251,191,36,.08);border-radius:10px;padding:8px 10px;line-height:1.5}"
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
    ".pzr{color:var(--zt)}.pzr th{color:var(--zm);font-weight:600}.pzr td,.pzr th{text-align:right;border-color:rgba(148,163,255,.16)}.pzr td:first-child,.pzr th:first-child{text-align:left}.pzr .pz-bad{color:#e5484d;font-weight:700}"
    ".pz .pz-h{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 8px;margin:0 0 10px;font-size:19px;letter-spacing:1px;color:var(--zt)}"
    ".pz-h small{font-size:12.5px;font-weight:500;color:var(--zm);letter-spacing:0}"
    ".pz-grid{display:grid;grid-template-columns:1fr;gap:12px}"
    ".pz-chart{min-width:0}.pz-svg{display:block;width:100%;height:auto;border-radius:14px;touch-action:manipulation}"
    ".pz-svg text{font-family:inherit;font-variant-numeric:tabular-nums}"
    ".pz-more{margin:10px 0;border:1px solid var(--line);border-radius:12px;padding:0 12px}"
    ".pz-more>summary{cursor:pointer;padding:10px 0;font-weight:600;color:var(--ink)}.pz-more[open]>summary{border-bottom:1px solid var(--line)}"
    ".pz-more .pzt td:nth-child(2){text-align:left;white-space:normal}.pz-more .pzt td:nth-child(3){text-align:left;white-space:normal;font-size:12.5px}"
    ".pz-ok{color:var(--t0);font-weight:600}.pz-no{color:var(--mut)}"
    ".pz-more p,.pz-more li{font-size:13px;color:var(--ink2);line-height:1.7}"
    "@media (min-width:860px){.pz-top{grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);align-items:end}"
    ".pz-grid{grid-template-columns:minmax(0,1fr) minmax(0,1.05fr)}.pz-num{font-size:60px}.pz-ws{grid-template-columns:repeat(3,minmax(0,1fr))}}"
    "@media (max-width:380px){.pz{padding:14px 12px}.pz-num{font-size:42px}.pz-kv dd{font-size:14px}}"
    "@media (prefers-reduced-motion:reduce){.pz-live i,.pz-svg .pz-el,.pz-svg .pz-s.on .pz-ar{animation:none}.pz-c,.pz-svg .pz-s{transition:none}}"
)

JS = r"""<script>(function(){
var w=document.getElementById('pmstale');var t=new Date(Date.now()+8*3600e3).toISOString().slice(0,10);
if(w&&t>w.dataset.next)w.hidden=false;
var nf=function(x){return Math.round(x).toLocaleString('zh-TW')};
var n=document.querySelector('.pz-num');
if(n&&!(window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches)){var to=+n.dataset.to,fr=to-Math.max(60,Math.round(to*0.006)),t0=null;
 var step=function(ts){if(!t0)t0=ts;var p=Math.min(1,(ts-t0)/700),e=1-Math.pow(1-p,3);n.textContent=nf(fr+(to-fr)*e);if(p<1)requestAnimationFrame(step)};requestAnimationFrame(step);}
var D=null;try{D=JSON.parse((document.getElementById('pzd')||{}).textContent||'null')}catch(e){}
if(!D||!D.sc)return;
var st={acct:1000000,cap:'O1'};try{Object.assign(st,JSON.parse(localStorage.getItem('txoCalc')||'{}'))}catch(e){}
var cap={O1:0.02,O2:0.03,O3:0.05}[st.cap]||0.02;
var svg=document.querySelector('#pzl .pz-svg'),det=document.getElementById('pzdet'),info=document.getElementById('pzinfo');
function md(d){return +d.slice(5,7)+'/'+ +d.slice(8,10)}
function show(i){var c=D.sc[i];if(!c)return;
 document.querySelectorAll('#pzl .pz-c').forEach(function(b){b.classList.toggle('on',+b.dataset.s===i);b.setAttribute('aria-pressed',+b.dataset.s===i)});
 if(svg)svg.querySelectorAll('.pz-s').forEach(function(g){g.classList.toggle('on',+g.dataset.s===i)});
 if(!det)return;
 var o=c.opt,h='<div class="why">'+(c.why||'')+'</div><dl class="mny">';
 if(c.mtx)h+='<dt>小台一口</dt><dd>停損賠 <b class="l">'+nf(c.mtx.loss)+'</b> 元、到目標賺 <b class="g">'+nf(c.mtx.gain)+'</b> 元</dd>';
 if(o&&o.k){var one=o.max,lots=one>0?Math.floor(st.acct*cap/one):0;
  h+='<dt>選擇權</dt><dd>買 '+(o.xd?md(o.xd)+' 到期 ':'')+nf(o.k)+' '+(o.cp==='C'?'買權':'賣權')+'，約 <b>'+(+o.pe).toFixed(1)+'</b> 點（停損時約 '+(+o.ps).toFixed(1)+'、目標時約 '+(+o.pt).toFixed(1)+'）</dd>'+
   '<dt>一口</dt><dd>停損賠 <b class="l">'+nf(o.loss)+'</b>、到目標賺 <b class="g">'+nf(o.gain)+'</b> 元；權利金歸零最多賠 '+nf(o.max)+' 元</dd>'+
   '<dt>可買</dt><dd>帳戶 '+nf(st.acct)+' 元、每筆 '+Math.round(cap*100)+'%：'+(lots>0?'最多 <b>'+lots+'</b> 口':'買不到 1 口')+'</dd>';}
 det.innerHTML=h+'</dl>';}
document.querySelectorAll('#pzl .pz-c').forEach(function(b){b.addEventListener('click',function(){show(+b.dataset.s)})});
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



def now(pm: dict) -> dict:
    """頁面用的預估：08:46 用台指期開盤重估過（arm/lab/pm850.py）就用重估的，不然用清晨夜盤的。"""
    from .pm850 import cur
    v = pm.get("v") or {}
    e = cur(pm)
    if e:
        return {"est": e["est"], "typ": e.get("typ"), "p80": e.get("p80"), "early": pm["est"], "t": e.get("t") or "08:46",
                "src": f'{e.get("t") or "08:46"} 用台指期開盤 {_n(e["open"])} 重估'}
    return {"est": pm["est"], "typ": v.get("typ"), "p80": v.get("p80"), "early": None, "t": None, "src": pm.get("est_src") or ""}


_SHORT = (("（換算）", ""), ("成交量 70% 區上緣", "成交量密集區上緣"), ("成交量 70% 區下緣", "成交量密集區下緣"),
          ("台指期成交量最多", "成交量最多"), ("昨天收盤", "昨收"), ("樞紐壓力 1", "樞紐壓力"), ("樞紐壓力 2", "樞紐壓力"),
          ("樞紐支撐 1", "樞紐支撐"), ("樞紐支撐 2", "樞紐支撐"))


def _src_label(name: str) -> str:
    """價位來源的短名字（頁面一眼看得懂）：「11/18 到期最大痛點」→「選擇權最大痛點」、「賣權未平倉最多（1,804 口）」→「賣權未平倉最多」。"""
    import re
    for a, b in _SHORT:
        name = name.replace(a, b)
    name = re.sub(r"^\d+/\d+ 到期", "", name)
    name = re.sub(r"（[\d,]+ 口）$", "", name)
    return "選擇權最大痛點" if name == "最大痛點" else name


SC_TAG = {"long": ("做多", "回測支撐", "u"), "short": ("做空", "反彈壓力", "d"), "break": ("追多", "突破壓力", "u"),
          "breakdown": ("追空", "跌破支撐", "d")}


def _bands_now(pm: dict, cn: dict) -> list[dict]:
    """每一帶依「現在的」預估開盤重新分邊（08:46 重估過，原本的支撐可能變壓力），附今天碰到的比例（Q2 表內插）。
    預估開盤落在帶子裡＝side "at"、碰到 100%。"""
    from .premkt import touch
    q2 = (pm.get("v") or {}).get("q2") or {}
    est, em = cn["est"], pm.get("em") or 0
    out = []
    for b in pm.get("bands") or []:
        if b.get("mid") is None:
            continue
        side = "at" if b["lo"] <= est <= b["hi"] else "up" if b["lo"] > est else "dn"
        t = 1.0 if side == "at" else (touch(abs(b["mid"] - est) / em, side, q2) if em and q2.get("x") else None)
        out.append({**b, "side": side, "touch": t})
    return out


def _sc_now(pm: dict, cn: dict) -> list[dict]:
    """參考點位，「今天碰到進場價的機會」以現在的預估開盤重算。"""
    from .premkt import touch
    q2 = (pm.get("v") or {}).get("q2") or {}
    est, em = cn["est"], pm.get("em") or 0
    out = []
    for c in pm.get("sc") or []:
        hit = (touch(abs(c["entry"] - est) / em, "up" if c["entry"] > est else "dn", q2) if em and q2.get("x") else c.get("hit"))
        out.append({**c, "hit": hit})
    return out


def lvchart(pm: dict, cn: dict, bands: list[dict], sc: list[dict]) -> str:
    """今日點位的價位圖（2026-11-13 使用者：「今天可能走多遠應該要跟上面合併」「本來那種點了之後的示意圖很好」）：
    預估開盤＋八成範圍、壓力支撐帶（右邊＝今天碰到的比例）、開盤上下 1 倍正常波動（今天可能走多遠），
    點參考點位卡，圖上畫出進場、停損、目標（11/5 版的互動圖）。"""
    e = html.escape
    from .premkt import touch
    q2 = (pm.get("v") or {}).get("q2") or {}
    est, em = cn["est"], pm.get("em") or 0
    band80, typ = cn["p80"] or 0, cn["typ"] or 0
    ps = [est + band80, est - band80, pm["close"]] + [x for b in bands for x in (b["lo"], b["hi"])]
    ps += [x for c in sc for x in (c["entry"], c["stop"], c["target"])]
    if em:
        ps += [est + em, est - em]
    pmax, pmin = max(ps), min(ps)
    pad = max((pmax - pmin) * 0.05, 5)
    pmax, pmin = pmax + pad, pmin - pad

    def y(p):
        return round(TOP + (pmax - p) / (pmax - pmin) * (H - TOP - BOT), 1)
    o = [f'<svg class="pz-svg" viewBox="0 0 {W} {H}" role="img" aria-label="今天的價位圖：預估開盤、壓力、支撐、可能走多遠與參考點位">',
         '<defs><linearGradient id="pzbg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1a1240"/><stop offset=".5" stop-color="#0d1330"/>'
         '<stop offset="1" stop-color="#062027"/></linearGradient>'
         '<filter id="pzgl" x="-20%" y="-200%" width="140%" height="500%"><feGaussianBlur stdDeviation="3"/></filter>'
         '<marker id="pzah" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
         '<path d="M0 0L10 5L0 10z" fill="#34d399"/></marker></defs>',
         f'<rect x="0" y="0" width="{W}" height="{H}" rx="14" fill="url(#pzbg)"/>']
    if band80:
        o.append(f'<rect x="{X0}" y="{y(est + band80)}" width="{X1 - X0}" height="{y(est - band80) - y(est + band80)}" fill="#fbbf24" opacity=".08"/>')
    if typ:
        o.append(f'<rect x="{X0}" y="{y(est + typ)}" width="{X1 - X0}" height="{y(est - typ) - y(est + typ)}" fill="#fbbf24" opacity=".14"/>')
    left, right = [(y(est), f"預估 {_n(est)}", "#fde68a", True)], [(y(pm["close"]), f"昨收 {_n(pm['close'])}", "#a3aecb")]
    if em:                                                   # 今天可能走多遠：開盤上下 1 倍正常波動
        for sg, side, col in ((1, "up", "#fb7185"), (-1, "dn", "#22d3ee")):
            p1 = est + sg * em
            t1 = touch(1.0, side, q2) if q2.get("x") else None
            o.append(f'<line x1="{X0}" x2="{X1}" y1="{y(p1)}" y2="{y(p1)}" stroke="{col}" stroke-width="1.2" stroke-dasharray="5 4" opacity=".7"/>')
            left.append((y(p1), _n(p1), col, False))
            right.append((y(p1), f"{'+' if sg > 0 else '−'}1 倍・{_pct(t1)}", col))
    o.append(f'<line class="pz-el" x1="{X0}" x2="{X1}" y1="{y(est)}" y2="{y(est)}" stroke="#fbbf24" stroke-width="6" opacity=".55" filter="url(#pzgl)"/>'
             f'<line x1="{X0}" x2="{X1}" y1="{y(est)}" y2="{y(est)}" stroke="#fde68a" stroke-width="2"/>')
    o.append(f'<line x1="{X0}" x2="{X1}" y1="{y(pm["close"])}" y2="{y(pm["close"])}" stroke="#a3aecb" stroke-width="1" stroke-dasharray="3 4" opacity=".7"/>')
    for i, b in enumerate(bands):
        col = "#fb7185" if b["side"] == "up" else "#22d3ee" if b["side"] == "dn" else "#fbbf24"
        y1, y2 = y(b["hi"]), y(b["lo"])
        hgt = max(y2 - y1, 5)
        yc = (y1 + y2) / 2
        src = "、".join(f"{_src_label(s[0])} {_n(s[1])}" for s in b.get("src") or [])
        o.append(f'<g class="pz-b" data-b="{i}"><title>{e(src)}</title>'
                 f'<rect x="{X0}" y="{round(yc - hgt / 2, 1)}" width="{X1 - X0}" height="{round(hgt, 1)}" rx="3" fill="{col}" opacity=".26"/>'
                 f'<rect x="{X0}" y="{round(yc - hgt / 2, 1)}" width="3" height="{round(hgt, 1)}" fill="{col}"/>'
                 f'<rect x="0" y="{round(yc - 11, 1)}" width="{W}" height="22" fill="transparent"/></g>')
        left.append((yc, _n(b["lo"]) if round(b["lo"]) == round(b["hi"]) else _n(b["mid"]), col, False))
        if b["side"] != "at" and b.get("touch") is not None:
            right.append((yc, f"碰 {_pct(b['touch'])}", col))
    BX0, BX1 = 196, X1
    for i, c in enumerate(sc):                                # 參考點位（點卡片才出現）
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
    ry = _spread([t[0] for t in sorted(right)], 13, TOP + 6, H - BOT - 4)
    for (yy, txt, col), y2 in zip(sorted(right), ry):
        o.append(f'<text x="{W - 4}" y="{round(y2 + 4, 1)}" text-anchor="end" font-size="10.5" fill="{col}" opacity=".9">{e(txt)}</text>')
    o.append("</svg>")
    return "".join(o)


def _card(i: int, c: dict) -> str:
    k, nm, side = SC_TAG.get(c.get("k"), (c["name"][-2:], c["name"][:-2], "u"))
    risk, rew = c.get("risk") or abs(c["entry"] - c["stop"]), c.get("reward") or abs(c["target"] - c["entry"])
    rp = risk / (risk + rew) * 100 if risk + rew else 50
    rr = c.get("rr") or (rew / risk if risk else 0)
    hit = f'<span class="pz-hit">今天碰到進場價 <b>{_pct(c["hit"])}</b></span>' if c.get("hit") is not None else ""
    sg = 1 if c["target"] > c["entry"] else -1
    lab = {"break": "站上", "breakdown": "跌破"}.get(c.get("k"), "進場")
    return (f'<button type="button" class="pz-c c{side}" data-s="{i}" aria-pressed="false">'
            f'<span class="pz-ck"><b>{k}</b>{html.escape(nm)}</span>'
            f'<span class="pz-ce">{_n(c["entry"])}<small>{lab}</small></span>'
            f'<span class="pz-cl"><span class="s">停損 {_n(c["stop"])}（{_n(-sg * risk, True)}）</span></span>'
            f'<span class="pz-cl"><span class="t">目標 {_n(c["target"])}（{_n(sg * rew, True)}）</span></span>'
            f'<span class="pz-rr"><i><s style="width:{rp:.0f}%"></s><u style="width:{100 - rp:.0f}%"></u></i>1 : <b>{rr:.1f}</b></span>{hit}</button>')


def levels(pm: dict) -> str:
    """今日點位（使用者 2026-11-13）：壓力 1～3、預估開盤、支撐 1～3 由上往下，每一格寫價位、來源、今天碰到的比例；
    參考點位四張卡（點一張，價位圖畫出進場、停損、目標，下面寫小台與選擇權一口賺賠）；價位圖同時畫開盤上下 1 倍正常波動（今天可能走多遠）。
    碰到的比例用 Q2 表、以現在的預估開盤（08:46 重估過就用重估的）算；參考點位沒有驗證過，照實標出來。"""
    from .premkt import md, touch, wd
    e = html.escape
    v = pm.get("v") or {}
    q2 = v.get("q2") or {}
    cn = now(pm)
    est, em = cn["est"], pm.get("em") or 0
    bands = _bands_now(pm, cn)
    sc = _sc_now(pm, cn)
    up = sorted((b for b in bands if b["side"] == "up"), key=lambda b: b["lo"])[:3]
    dn = sorted((b for b in bands if b["side"] == "dn"), key=lambda b: -b["hi"])[:3]

    def px(b):
        return _n(b["lo"]) if round(b["lo"]) == round(b["hi"]) else f'{_n(b["lo"])}～{_n(b["hi"])}'

    def src(b):
        seen = []
        for name, _ in b.get("src") or []:
            lb = _src_label(name)
            if lb not in seen:
                seen.append(lb)
        return "・".join(seen)

    def row(cls, k, b):
        return (f'<div class="pzl-r {cls}"><span class="pzl-k">{k}</span><span class="pzl-p">{px(b)}<small>{e(src(b))}</small></span>'
                f'<span class="pzl-h">今天碰到<b>{_pct(b["touch"]) if b.get("touch") is not None else "—"}</b></span></div>')
    upd = (cn["t"] or "08:46") if cn["early"] is not None else (pm.get("made") or "")[11:16]
    rows = []
    for i, b in reversed(list(enumerate(up, 1))):
        rows.append(row("pzl-u", f"壓力 {i}", b))
    lo80, hi80 = (est - cn["p80"], est + cn["p80"]) if cn["p80"] else (None, None)
    rows.append(f'<div class="pzl-r pzl-o"><span class="pzl-k">開盤</span><span class="pzl-p">{_n(est)}'
                + (f'<small>十次有八次開在 {_n(lo80)}～{_n(hi80)}</small>' if lo80 is not None else "")
                + f'</span><span class="pzl-h">比昨收<b>{_n(est - pm["close"], True)}</b></span></div>')
    for i, b in enumerate(dn, 1):
        rows.append(row("pzl-d", f"支撐 {i}", b))
    far = ""
    if em and q2.get("x"):
        far = (f'<p class="pz-info">今天可能走多遠：開盤上下 1 倍正常波動（±{_n(em)}）＝圖上虛線，過去碰到 '
               f'往上 {_pct(touch(1.0, "up", q2))}、往下 {_pct(touch(1.0, "dn", q2))}；'
               f'2 倍（{_n(est + 2 * em)}／{_n(est - 2 * em)}）只有 {_pct(touch(2.0, "up", q2))}／{_pct(touch(2.0, "dn", q2))}。</p>')
    out = ['<section class="pz" id="pzl">',
           f'<div class="pzl-hd"><h2>今日點位　{md(pm["next"])}（{wd(pm["next"])}）</h2><span>{e(upd)} 更新</span></div>',
           '<div class="pzl-g">',
           '<div class="pzl-rows">' + "".join(rows) + "</div>",
           f'<div class="pzl-ch"><div class="pz-chart">{lvchart(pm, cn, bands, sc)}'
           '<div class="pz-info" id="pzinfo">點價位帶看它是怎麼來的；右邊「碰」＝今天碰到的比例。</div>' + far + "</div></div>"]
    if sc:
        out.append('<div class="pzl-sc"><h3 class="pzl-h3">參考點位<small>點一張，價位圖畫出進場、停損、目標</small></h3>'
                   '<div class="pz-cards">' + "".join(_card(i, c) for i, c in enumerate(sc)) + "</div></div>"
                   '<div class="pz-det" id="pzdet"></div>')
    out.append("</div>")
    ok = v.get("lv_ok") or []
    held = ("這些壓力支撐過去 10 年「擋住」的比例跟一般價位差不多" if not ok
            else "過去擋得住的只有：" + "、".join(ok))
    out.append(f'<div class="pzl-w">⚠ 照實說：{held}；11/6～11/11 碰到進場價的 12 張裡 7 張幾分鐘內就停損。'
               '「今天碰到」的比例是驗證過的，參考點位沒有，只能當參考，不是買賣建議。</div>')
    data = {"sc": [{k: c.get(k) for k in ("name", "why", "entry", "stop", "target", "mtx", "opt")} for c in sc],
            "bands": [{"lo": b["lo"], "hi": b["hi"], "src": [[_src_label(n), x] for n, x in b.get("src") or []]} for b in bands]}
    out.append('<script type="application/json" id="pzd">' + json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
               + "</script></section>")
    return "".join(out)


def recent(pm: dict) -> str:
    """最近 10 天：估的開盤 vs 09:01 實際、當天最高最低（照實列，估得差也照列）。"""
    from .premkt import md
    chk = pm.get("check") or []
    if not chk:
        return ""
    rows = []
    has8 = any(c.get("e850") is not None for c in chk)
    for c in reversed(chk):
        miss = c["open"] - c["est"]
        hl = f'{_n(c["hi"])}～{_n(c["lo"])}' if c.get("hi") is not None else "—"
        amp = _n(c["hi"] - c["lo"]) if c.get("hi") is not None else "—"
        e8 = ""
        if has8:
            e8 = (f'<td>{_n(c["e850"])}</td><td>{_n(c["open"] - c["e850"], True)}</td>' if c.get("e850") is not None
                  else '<td>—</td><td>—</td>')
        rows.append(f'<tr><td>{md(c["d"])}</td><td>{_n(c["est"])}</td><td>{_n(c["open"])}</td>'
                    f'<td{" class=\"pz-bad\"" if abs(miss) > ((pm.get("v") or {}).get("p80") or 1e9) else ""}>{_n(miss, True)}</td>'
                    f'{e8}<td>{hl}</td><td>{amp}</td></tr>')
    misses = [abs(c["open"] - c["est"]) for c in chk]
    p80 = (pm.get("v") or {}).get("p80")
    over = sum(1 for m in misses if p80 and m > p80)
    amps = [c["hi"] - c["lo"] for c in chk if c.get("hi") is not None]
    lead = f'最近 {len(chk)} 天，估的開盤平均差 <b>{_n(sum(misses) / len(misses))}</b> 點'
    if p80:
        lead += f'，{over} 天超出「八成在 ±{_n(p80)} 內」'
    m8 = [abs(c["open"] - c["e850"]) for c in chk if c.get("e850") is not None]
    if m8:
        lead += f'；08:46 用台指期開盤重估的 {len(m8)} 天平均差 <b>{_n(sum(m8) / len(m8))}</b> 點'
    if amps:
        lead += f'；當天最高到最低平均 <b>{_n(sum(amps) / len(amps))}</b> 點'
    return ('<section class="pz pz2" id="pzrec"><h2 class="pz-h">最近的成績<small>估的開盤跟實際差多少（照實列）</small></h2>'
            f'<p class="pz-chk">{lead}。</p><div class="optw"><table class="opt pzt pzr"><thead><tr><th>日期</th><th>清晨估</th><th>09:01 實際</th>'
            '<th>差</th>' + ('<th>08:46 重估</th><th>差</th>' if has8 else '') + '<th>當天最高～最低</th><th>振幅</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div></section>")


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
            + (f"、{nn} 項中間" if nn else "") + f'；每項過去只差 0.04～0.1%，只能當傾向、不能當買賣依據</span></h3>{g}<div class="pz-ws">{"".join(out)}</div></div>')


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
                  f'八成在 0.46 倍內，是「直接用昨天收盤」的一半。</li>')
        li.append('<li><b>08:46 重估</b>：台指期 08:45 就開盤，比現貨早 15 分鐘。開盤後改用「前一天加權指數收盤＋（台指期開盤 − 同一口前一天收盤）」重估，'
                  '過去 9 年（2,306 天）誤差中位數從 34 點降到 27 點、八成在 0.36 倍正常波動內（清晨的估是 0.46 倍），'
                  '清晨估錯很大的那幾天，重估把誤差砍半的佔 43%（docs/lab_premarket_plan.md 第 16 節）。'
                  '每個交易日 08:46 左右自動更新這一頁；排程沒跑到就維持清晨的估。</li>')
        if q2.get("x"):
            cells = "".join(f"<td>{x:g} 倍</td>" for x in q2["x"])
            up = "".join(f"<td>{_pct(p)}</td>" for p in q2["up"])
            dn = "".join(f"<td>{_pct(p)}</td>" for p in q2["dn"])
            li.append(f'<li><b>碰到的機會</b>：過去 {v.get("n2") or 0:,} 天，離 09:01 開盤 x 倍正常波動的價位，當天碰到的比例（「今日點位」的「今天碰到」與價位圖右邊的數字照這張表內插）：'
                      f'<div class="optw"><table class="opt"><thead><tr><th>距離</th>{cells}</tr></thead><tbody>'
                      f'<tr><td>往上</td>{up}</tr><tr><td>往下</td>{dn}</tr></tbody></table></div></li>')
        li.append(f'<li><b>壓力支撐</b>：價位來自{"、".join(KINDS.values())}，相差 0.25% 以內併成一帶。'
                  f'過去 10 年碰到之後先彈回 0.25 倍正常波動的比例約 {v.get("hold_base", 0.45) * 100:.0f}%，'
                  + ("跟同樣距離的任意價位差不多，<b>沒有一種價位比較擋得住</b>，幾種來源擠在一起也一樣。" if not v.get("lv_ok") else "有過的：" + "、".join(v["lv_ok"]) + "。")
                  + "所以 2026-11-12 起不再放用這些價位畫的買賣點卡（docs/lab_txo_plan.md 第 20 節）。</li>")
        li.append('<li><b>籌碼風向</b>：14 個常見說法（外資期貨、散戶小台、外資選擇權、P/C 比、法人、融資、期現價差、夜盤、費半、RSI、均線、KD、MACD）'
                  '逐一測過，只有上面 3 個比隨便猜好；每天差 4～10 個基點，只能當傾向。</li>')
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
    cn = now(pm)
    em, est, close = pm.get("em"), cn["est"], pm["close"]
    nt = pm.get("night") or {}
    out = [levels(pm), '<section class="pz" id="pz">',
           f'<div class="pz-hd"><h1 class="pz-live"><i></i>盤前戰情</h1><span class="pz-date">{md(pm["next"])}（{wd(pm["next"])}）開盤前</span>'
           f'<span class="pz-upd">{e((pm.get("made") or "")[5:].replace("-", "/"))} 更新</span></div>',
           f'<div class="pz-warn" id="pmstale" hidden data-next="{e(pm["next"])}">這份是 {md(pm["next"])} 開盤前的，已經過期；下一份收盤後會更新。</div>']
    for w in pm.get("warn") or []:
        out.append(f'<div class="pz-warn">{e(w)}</div>')
    ch = est - close
    rng = ""
    if cn["typ"]:
        rng = (f'<div class="pz-rng"><span>平常差 <b>±{_n(cn["typ"])}</b></span><span>十次有八次在 <b>±{_n(cn["p80"])}</b> 內</span></div>')
    if cn["early"] is not None:
        rng += (f'<div class="pz-re">{e(cn["t"])} 已用台指期開盤重估（清晨估 {_n(cn["early"])}，'
                f'{_n(est - cn["early"], True)}）；過去 9 年這樣估，誤差比清晨小約兩成。</div>')
    out.append('<div class="pz-top"><div class="pz-est"><small>預估 09:01 加權指數</small>'
               f'<b class="pz-num" data-to="{est}">{_n(est)}</b>'
               f'<div class="pz-chg">比昨收 <em class="{"pz-uc" if ch >= 0 else "pz-dc"}">{_n(ch, True)}（{_sp(ch / close * 100)}%）</em>'
               f'・{e(cn["src"])}</div>' + rng + "</div>")
    nch = (nt.get("c") - nt.get("ref")) if nt.get("c") is not None and nt.get("ref") else None
    out.append('<dl class="pz-kv">'
               f'<div><dt>{md(pm["d"])} 收盤</dt><dd>{_n(close)}<small>高 {_n(pm["hi"])}・低 {_n(pm["lo"])}</small></dd></div>'
               f'<div><dt>夜盤台指期</dt><dd>{_n(nt.get("c"))}<small class="{"pz-uc" if (nch or 0) >= 0 else "pz-dc"}">'
               f'{_n(nch, True) if nch is not None else "—"}{"" if nt.get("done") else "（" + e(str(nt.get("t") or "進行中")) + "）"}</small></dd></div>'
               f'<div><dt>正常波動</dt><dd>±{_n(em)}<small>極端 ±{_n(2 * em) if em else "—"}</small></dd></div></dl></div>')
    out.append(_wind(v))
    out.append("</section>")
    out.append(recent(pm))
    out.append(_facts(pm))
    out.append(_method(pm))
    out.append(JS)
    return "".join(out)
