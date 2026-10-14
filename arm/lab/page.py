"""籌碼雷達獨立頁 → dashboard/x9.html（主頁頁尾右下角小點進入；刻意不放導覽列）。

全頁由內嵌 JSON 在瀏覽器端渲染（表格排序／篩選、個股卡、SVG K 線）。輸出決定性：
不寫入任何牆鐘時間，資料沒變時位元組相同 → git 無 diff、不產生空 commit。
"""
from __future__ import annotations

import html
import json
from pathlib import Path

from . import analyze

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dashboard" / "x9.html"
SLUG = "x9.html"


def build(out: Path = OUT) -> bool:
    data = analyze.run()
    page = render(data)
    if out.exists() and out.read_text(encoding="utf-8") == page:
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return True


def _slim(x):
    """整數值的浮點數輸出成整數（2490.0 → 2490），價量序列可省約兩成體積。"""
    if isinstance(x, float):
        return int(x) if x.is_integer() and abs(x) < 1e15 else x
    if isinstance(x, list):
        return [_slim(v) for v in x]
    if isinstance(x, dict):
        return {k: _slim(v) for k, v in x.items()}
    return x


def render(data: dict) -> str:
    blob = json.dumps(_slim(data), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    blob = blob.replace("</", "<\\/")
    a = data.get("asof") or {}
    sub = " · ".join(f"{k} {html.escape(str(v)[5:] if v else '—')}" for k, v in (
        ("ETF 持股", a.get("pos")), ("價量", a.get("px")), ("法人", a.get("chip")),
        ("融資券", a.get("margin")), ("集保", a.get("tdcc"))))
    return (_HTML.replace("{{SUB}}", sub).replace("{{CSS}}", _CSS)
            .replace("{{DATA}}", blob).replace("{{JS}}", _JS))


_HTML = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>籌碼雷達</title>
<style>{{CSS}}</style></head>
<body>
<header class="hd">
  <div class="hdt"><b>籌碼雷達</b><span class="hds">ETF 持股個股 · 量／成本／加入日／投信動向／籌碼／技術</span>
  <a class="back" href="./">返回主頁</a></div>
  <div class="asof">{{SUB}}</div>
  <nav class="tabs" id="tabs">
    <a data-t="tbl" class="on">總表</a><a data-t="sig">訊號榜</a><a data-t="iss">投信動向</a>
    <a data-t="idx">指數調整</a><a data-t="bt">成績單</a><a data-t="doc">說明</a>
  </nav>
</header>
<main id="main"></main>
<div id="dv" class="dv" hidden><div class="dvin" id="dvin"></div></div>
<script type="application/json" id="labdata">{{DATA}}</script>
<script>{{JS}}</script>
</body></html>
"""

_CSS = """
:root{--bg:#fff;--card2:#f4f6fa;--ink:#1f2733;--mut:#727e8c;--line:#e8ebf1;--acc:#2563c9;
--accd:#1c4fa8;--gain:#d33a34;--loss:#1f9d57;--gold:#a16207;--inset:#eef2f8;--warn:#b45309}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 -apple-system,"PingFang TC","Noto Sans TC",Segoe UI,sans-serif}
a{color:var(--acc);text-decoration:none;cursor:pointer}
.hd{position:sticky;top:0;z-index:20;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 16px 0}
.hdt{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.hdt b{font-size:18px}.hds{color:var(--mut);font-size:12.5px;flex:1}
@media(max-width:600px){.hds{display:none}.hdt{justify-content:space-between}}
.back{font-size:13px;color:var(--mut)}
.asof{color:var(--mut);font-size:12px;margin:2px 0 6px}
.tabs{display:flex;gap:2px;overflow-x:auto}
.tabs a{padding:8px 12px;color:var(--mut);font-weight:600;white-space:nowrap;border-bottom:3px solid transparent}
.tabs a.on{color:var(--ink);border-bottom-color:var(--acc)}
main{padding:12px 16px 60px;max-width:1280px;margin:0 auto}
.bar{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:4px 0 10px}
.bar input[type=search]{flex:1 1 180px;min-width:150px;padding:7px 10px;border:1px solid var(--line);border-radius:8px;font:inherit;background:var(--card2)}
.ch{display:inline-flex;align-items:center;gap:4px;padding:4px 10px;border-radius:14px;background:var(--card2);color:var(--ink);font-size:13px;cursor:pointer;user-select:none;border:0}
.ch.on{background:var(--acc);color:#fff}.ch.rk{background:#fdecea;color:var(--gain)}.ch.rk.on{background:var(--gain);color:#fff}
.ch i{font-style:normal;opacity:.7;font-size:12px}
.tw{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap;vertical-align:top}
th{position:sticky;top:0;background:var(--card2);color:var(--mut);font-weight:600;font-size:12.5px;cursor:pointer}
th.on{color:var(--accd)}
td:first-child,th:first-child{text-align:left;position:sticky;left:0;background:var(--bg);z-index:1;white-space:normal;min-width:96px;max-width:150px}
.nm{overflow:hidden;text-overflow:ellipsis;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
th:first-child{background:var(--card2);z-index:2}
tbody tr{cursor:pointer}tbody tr:hover td{background:#f8fafd}
.nm{display:block;font-weight:600}.cd{color:var(--mut);font-size:12px}
.up{color:var(--gain)}.dn{color:var(--loss)}.mu{color:var(--mut)}
.sg{display:inline-block;font-size:11.5px;padding:1px 7px;border-radius:9px;background:rgba(37,99,201,.1);color:var(--accd);margin:1px 2px 1px 0}
.sg.rk{background:#fdecea;color:var(--gain)}
.more{display:block;margin:12px auto;padding:8px 18px;border:0;border-radius:8px;background:var(--card2);font:inherit;cursor:pointer}
.dv{position:fixed;inset:0;z-index:50;background:rgba(15,23,42,.35);overflow-y:auto}
.dvin{background:var(--bg);max-width:980px;margin:0 auto;min-height:100%;padding:12px 16px 60px}
@media(min-width:760px){.dvin{margin:24px auto;min-height:auto;border-radius:12px}}
.dvh{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;border-bottom:1px solid var(--line);padding-bottom:8px;position:sticky;top:0;background:var(--bg);z-index:3}
.dvh b{font-size:19px}.dvh .px{font-size:17px;font-weight:700}
.x{margin-left:auto;font-size:22px;color:var(--mut);padding:0 4px}
h3{font-size:14.5px;margin:18px 0 6px;color:var(--accd)}
.kv{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:6px 10px}
.kv div{background:var(--card2);border-radius:8px;padding:6px 10px}
.kv>div>span{display:block;color:var(--mut);font-size:11.5px}.kv b{font-size:14.5px}
.kv em{font-style:normal;font-size:12px;margin-left:4px}
.note{color:var(--mut);font-size:12px;margin:4px 0}
svg{display:block;width:100%;height:auto}
.lg{display:flex;flex-wrap:wrap;gap:10px;font-size:12px;color:var(--mut)}.lg i{display:inline-block;width:14px;height:3px;vertical-align:middle;margin-right:4px}
.card{border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin:10px 0}
.card h4{margin:0 0 4px;font-size:15px}
.st{font-size:12.5px;color:var(--mut)}
.pill{display:inline-block;font-size:11.5px;padding:0 6px;border-radius:7px;background:var(--card2);color:var(--mut)}
.k-new{color:var(--gain);font-weight:700}.k-add{color:var(--gain)}.k-cut{color:var(--loss)}.k-exit{color:var(--loss);font-weight:700}
.grey td{color:#a0a8b3}
ul.doc{padding-left:18px}ul.doc li{margin:4px 0}
.tip{position:absolute;pointer-events:none;background:rgba(31,39,51,.92);color:#fff;font-size:12px;padding:4px 8px;border-radius:6px;white-space:nowrap}
.cw{position:relative}
"""

_JS = r"""
const D=JSON.parse(document.getElementById('labdata').textContent);
const $=s=>document.querySelector(s);
const E=D.etfs||{},SD=D.sigdef||{},RISK=new Set(D.risk||[]);
const KN={new:'新建倉',add:'加碼',cut:'減碼',exit:'出清',hold:'—'};
function f(x,d=1){if(x===null||x===undefined||Number.isNaN(x))return '—';const v=Number(x);return v.toLocaleString('zh-TW',{minimumFractionDigits:d,maximumFractionDigits:d});}
function sgn(x,d=1,suf=''){if(x===null||x===undefined)return '<span class=mu>—</span>';const c=x>0?'up':x<0?'dn':'mu';return `<span class=${c}>${x>0?'+':''}${f(x,d)}${suf}</span>`;}
function esc(s){return String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function sgChips(arr){return (arr||[]).map(k=>`<span class="sg${RISK.has(k)?' rk':''}">${esc((SD[k]||[k])[0])}</span>`).join('');}
const MK={tw:'上市',tp:'上櫃',os:'海外'};const MKF={twall:'台股',tw:'上市',tp:'上櫃',os:'海外',all:'全部'};
const S={tab:'tbl',q:'',mk:'twall',sig:'',liq:false,sort:'a5v',dir:-1,n:60};
try{const z=JSON.parse(localStorage.getItem('lab.s')||'{}');Object.assign(S,z,{n:60});}catch(e){}
function save(){try{localStorage.setItem('lab.s',JSON.stringify({tab:S.tab,mk:S.mk,sort:S.sort,dir:S.dir,liq:S.liq}));}catch(e){}}

const COLS=[
 ['c','代號／名稱',r=>`<span class=nm>${esc(r.n)}</span><span class=cd>${esc(r.c)} · ${MK[r.m]||''}${r.ind?' · '+esc(r.ind):''}</span>`,r=>r.c],
 ['px','收盤',r=>`${f(r.px,2)}<br>${sgn(r.ch,2,'%')}`,r=>r.ch],
 ['ne','ETF 數<br>主／被',r=>`${r.ne}<br><span class=mu>${r.na}／${r.np}</span>`,r=>r.ne],
 ['hp','ETF<br>持股率',r=>r.hp==null?'—':f(r.hp,2)+'%',r=>r.hp],
 ['a5v','主動 5 日真加碼<br>金額(億)／張',r=>`${sgn(r.a5v,2)}<br><span class=mu>${r.a5==null?'—':(r.a5>0?'+':'')+f(r.a5,0)} 張</span>`,r=>r.a5v],
 ['ia5','加碼／減碼<br>投信家數',r=>`<span class=up>${(r.ia5||[]).length}</span>／<span class=dn>${(r.ic5||[]).length}</span>`,r=>(r.ia5||[]).length-(r.ic5||[]).length],
 ['ow','主動超配<br>(百分點)',r=>sgn(r.ow,2),r=>r.ow],
 ['dev','主動成本<br>乖離',r=>sgn(r.dev,1,'%'),r=>r.dev],
 ['t5','投信<br>5 日(張)',r=>sgn(r.t5,0),r=>r.t5],
 ['f5','外資<br>5 日(張)',r=>sgn(r.f5,0),r=>r.f5],
 ['al','技術',r=>(r.al?`<span class=${r.al==='多頭'?'up':r.al==='空頭'?'dn':'mu'}>${r.al}</span>`:'—')+(r.h20?' <span class=sg>創20日高</span>':''),r=>({多頭:2,整理:1,空頭:0}[r.al]??-1)],
 ['sg','訊號',r=>sgChips(r.sg),r=>(r.sg||[]).filter(k=>!RISK.has(k)).length-(r.sg||[]).filter(k=>RISK.has(k)).length],
];

function rowsFiltered(){
  const q=S.q.trim().toLowerCase();
  let rs=D.rows.filter(r=>(S.mk==='all'||r.m===S.mk||(S.mk==='twall'&&r.m!=='os'))&&(!S.sig||(r.sg||[]).includes(S.sig))&&(!S.liq||(r.liq||0)>=1)
    &&(!q||r.c.toLowerCase().includes(q)||String(r.n).toLowerCase().includes(q)||String(r.ind||'').includes(q)));
  const col=COLS.find(c=>c[0]===S.sort)||COLS.find(c=>c[0]==='a5v');
  rs.sort((a,b)=>{const x=col[3](a),y=col[3](b);if(x==null&&y==null)return 0;if(x==null)return 1;if(y==null)return -1;return (x<y?-1:x>y?1:0)*S.dir;});
  return rs;
}

function vTbl(){
  const cnt={};D.rows.forEach(r=>(r.sg||[]).forEach(k=>cnt[k]=(cnt[k]||0)+1));
  const sigs=Object.keys(SD).filter(k=>cnt[k]);
  const rs=rowsFiltered();
  let h=`<div class=bar><input type=search id=q placeholder="代號、名稱或產業" value="${esc(S.q)}">`+
   ['twall','tw','tp','os','all'].map(m=>`<span class="ch${S.mk===m?' on':''}" data-mk=${m}>${MKF[m]}</span>`).join('')+
   `<span class="ch${S.liq?' on':''}" id=liq>日均成交 ≥1 億</span></div>`+
   `<div class=bar>`+sigs.map(k=>`<span class="ch${RISK.has(k)?' rk':''}${S.sig===k?' on':''}" data-sig=${k}>${esc(SD[k][0])}<i>${cnt[k]}</i></span>`).join('')+`</div>`+
   `<div class=note>共 ${rs.length} 檔 · 點欄位排序、點列看個股卡 · 「真加碼」已扣除申贖帶來的等比例增減</div>`+
   `<div class=tw><table><thead><tr>`+COLS.map(c=>`<th data-k=${c[0]} class="${S.sort===c[0]?'on':''}">${c[1]}${S.sort===c[0]?(S.dir<0?' ↓':' ↑'):''}</th>`).join('')+`</tr></thead><tbody>`+
   rs.slice(0,S.n).map(r=>`<tr data-c="${esc(r.c)}">`+COLS.map(c=>`<td>${c[2](r)}</td>`).join('')+`</tr>`).join('')+`</tbody></table></div>`+
   (rs.length>S.n?`<button class=more id=more>再顯示 ${Math.min(60,rs.length-S.n)} 檔（剩 ${rs.length-S.n}）</button>`:'');
  $('#main').innerHTML=h;
  const qi=$('#q');qi.oninput=()=>{S.q=qi.value;S.n=60;const p=qi.selectionStart;vTbl();const n=$('#q');n.focus();n.setSelectionRange(p,p);};
  document.querySelectorAll('[data-mk]').forEach(e=>e.onclick=()=>{S.mk=e.dataset.mk;S.n=60;save();vTbl();});
  document.querySelectorAll('[data-sig]').forEach(e=>e.onclick=()=>{S.sig=S.sig===e.dataset.sig?'':e.dataset.sig;S.n=60;vTbl();});
  $('#liq').onclick=()=>{S.liq=!S.liq;save();vTbl();};
  document.querySelectorAll('th[data-k]').forEach(e=>e.onclick=()=>{if(S.sort===e.dataset.k)S.dir*=-1;else{S.sort=e.dataset.k;S.dir=-1;}save();vTbl();});
  document.querySelectorAll('tbody tr').forEach(e=>e.onclick=()=>openStock(e.dataset.c));
  const m=$('#more');if(m)m.onclick=()=>{S.n+=60;vTbl();};
}

function statLine(k){const st=(D.stats||{})[k];if(!st)return '<span class=st>尚無歷史樣本</span>';
  const a=st['5']||{},b=st['20']||{};if(!a.n)return '<span class=st>尚無歷史樣本</span>';
  return `<span class=st>${st.ok?'':'⚠ 樣本不足 · '}5 日：平均超額 ${sgn(a.x,2,'%')}、勝率 ${f(a.w,0)}%、隔夜跳空 ${sgn(a.g,2,'%')}（n=${a.n}）`+(b.n?` · 20 日：超額 ${sgn(b.x,2,'%')}、勝率 ${f(b.w,0)}%（n=${b.n}）`:'')+`</span>`;}

function vSig(){
  let h='<div class=note>今天觸發的訊號，與該訊號在我們自己資料上的歷史成績（揭露後次日開盤進場、扣交易成本、對加權指數）。</div>';
  for(const k of Object.keys(SD)){
    const rs=D.rows.filter(r=>(r.sg||[]).includes(k));
    rs.sort((a,b)=>(b.a5||0)-(a.a5||0));
    h+=`<div class=card><h4>${RISK.has(k)?'⚠ ':''}${esc(SD[k][0])} <span class=pill>${rs.length} 檔</span></h4><div class=st>${esc(SD[k][1])}</div>${statLine(k)}`+
      (rs.length?`<div class=tw><table><tbody>`+rs.slice(0,30).map(r=>`<tr data-c="${esc(r.c)}"><td><span class=nm>${esc(r.n)}</span><span class=cd>${esc(r.c)}</span></td><td>${f(r.px,2)}<br>${sgn(r.ch,2,'%')}</td><td>主動5日 ${sgn(r.a5,0)} 張<br><span class=mu>加碼投信 ${(r.ia5||[]).join('、')||'—'}</span></td><td>成本乖離 ${sgn(r.dev,1,'%')}<br>投信5日 ${sgn(r.t5,0)}</td></tr>`).join('')+`</tbody></table></div>`:'<div class=st>今日無</div>')+`</div>`;
  }
  $('#main').innerHTML=h;
  document.querySelectorAll('tr[data-c]').forEach(e=>e.onclick=()=>openStock(e.dataset.c));
}

function vIss(){
  const iss={};for(const [c,m] of Object.entries(E)){(iss[m.is]=iss[m.is]||[]).push([c,m]);}
  const names=Object.keys(iss).sort((a,b)=>((D.iev||{})[b]||[]).length-((D.iev||{})[a]||[]).length);
  let h='<div class=note>各投信主動 ETF 近 5 個交易日的真加減碼（已扣申贖）、超配最多的個股（相對台股市值權重），以及新建倉後的歷史表現。</div>';
  for(const nm of names){
    const etfs=iss[nm];const ev=(D.iev||{})[nm]||[];const ow=(D.iow||{})[nm]||[];const st=(D.iss||{})[nm]||{};
    const s20=st['20']||{};
    h+=`<div class=card><h4>${esc(nm)} <span class=pill>${etfs.map(([c,m])=>c+(m.k==='p'?'(被)':'')).join(' ')}</span></h4>`+
      `<div class=st>新建倉後 20 日：${s20.n?`平均超額 ${sgn(s20.x,2,'%')}、勝率 ${f(s20.w,0)}%（n=${s20.n}）`:'樣本不足'} · 先買 ${st.lead||0} 次／跟進 ${st.follow||0} 次</div>`;
    if(ev.length)h+=`<div class=tw><table><tbody>`+ev.slice(0,15).map(e=>`<tr data-c="${esc(e[2])}"><td><span class=nm>${esc(e[3])}</span><span class=cd>${esc(e[2])} · ${esc(e[4])}</span></td><td class="k-${e[1]}">${KN[e[1]]}</td><td>${sgn(e[5],1)} 張</td><td class=mu>${esc(e[0].slice(5))}</td></tr>`).join('')+`</tbody></table></div>`;
    else h+='<div class=st>近 5 日無主動真加減碼</div>';
    if(ow.length)h+=`<div class=st style="margin-top:6px">超配最多：`+ow.map(o=>`<a data-c="${esc(o[0])}">${esc(o[1])}</a> ${sgn(o[4],2)}pp`).join('、')+`</div>`;
    h+='</div>';
  }
  $('#main').innerHTML=h;
  document.querySelectorAll('[data-c]').forEach(e=>e.onclick=()=>openStock(e.dataset.c));
}

function vBt(){
  const a=D.asof||{};
  let h=`<div class=note>樣本期間 ${esc(a.start||'—')} 起（ETF 持股史）／價量約一年。進場＝揭露後次一交易日開盤；出場＝第 5／20 個交易日收盤；已扣來回成本 0.585%；超額＝對加權指數同期。同一檔 5 日內重複觸發只算一次。樣本 &lt;30 以灰字顯示、不宜採信。</div>`;
  h+=`<div class=tw><table><thead><tr><th>訊號</th><th>5 日 n</th><th>平均報酬</th><th>平均超額</th><th>超額中位</th><th>勝率</th><th>隔夜跳空</th><th>20 日 n</th><th>平均超額</th><th>勝率</th></tr></thead><tbody>`;
  for(const k of Object.keys(SD)){const st=(D.stats||{})[k]||{};const x=st['5']||{},y=st['20']||{};
    h+=`<tr class="${st.ok?'':'grey'}"><td>${RISK.has(k)?'⚠ ':''}${esc(SD[k][0])}</td><td>${x.n||0}</td><td>${sgn(x.r,2,'%')}</td><td>${sgn(x.x,2,'%')}</td><td>${sgn(x.xm,2,'%')}</td><td>${x.n?f(x.w,0)+'%':'—'}</td><td>${sgn(x.g,2,'%')}</td><td>${y.n||0}</td><td>${sgn(y.x,2,'%')}</td><td>${y.n?f(y.w,0)+'%':'—'}</td></tr>`;}
  h+=`</tbody></table></div><h3>投信選股成績（主動 ETF 新建倉後）</h3><div class=tw><table><thead><tr><th>投信</th><th>新建倉次數</th><th>5 日超額</th><th>20 日 n</th><th>20 日超額</th><th>勝率</th><th>先買</th><th>跟進</th></tr></thead><tbody>`;
  const iss=Object.entries(D.iss||{}).sort((a,b)=>((b[1]['20']||{}).x??-99)-((a[1]['20']||{}).x??-99));
  for(const [nm,st] of iss){const x=st['5']||{},y=st['20']||{};h+=`<tr class="${(y.n||0)>=30?'':'grey'}"><td>${esc(nm)}</td><td>${st.new||0}</td><td>${sgn(x.x,2,'%')}</td><td>${y.n||0}</td><td>${sgn(y.x,2,'%')}</td><td>${y.n?f(y.w,0)+'%':'—'}</td><td>${st.lead||0}</td><td>${st.follow||0}</td></tr>`;}
  h+='</tbody></table></div>';
  $('#main').innerHTML=h;
}

function vDoc(){
  $('#main').innerHTML=`<h3>這頁在做什麼</h3><ul class=doc>
<li>把追蹤中 ETF（被動 6 檔＋主動式；債券型除外）持有的所有個股，逐檔建「ETF 部位帳本」，再疊上官方籌碼與技術面。</li>
<li><b>真加碼</b>：ETF 有申購時所有持股會等比例增加，那不代表看好。每次揭露取共同持股股數比的中位數當「申贖倍率」，偏離它的部分才算經理人真的加減碼。被動式 ETF 的真加減碼＝指數機械調整，不計入投信看好度。</li>
<li><b>超配</b>：主動 ETF 平均權重 − 該股占台股（上市＋上櫃普通股）總市值的比重。權重高不等於看好——台積電在主動 ETF 約一成，卻遠低於它的市值占比。</li>
<li><b>估計成本</b>：加碼日按當日均價（成交金額 ÷ 成交股數）入帳、減碼按平均成本沖銷。觀測起點前就持有的部位以首次觀測日均價計（品質 B），觀測期內才建倉者為品質 A。未計配息。</li>
<li><b>加入日</b>：觀測期內首次出現在該 ETF 揭露的日期；觀測起點前已持有者標「≤起點」。</li>
<li><b>ETF 持股率</b>＝所有追蹤 ETF 合計持股 ÷ 發行股數；<b>消化天數</b>＝合計持股 ÷ 20 日均量（集體出清要賣幾天）。</li>
<li><b>籌碼</b>：證交所／櫃買官方三大法人、融資融券、借券賣出餘額（上市）、外資持股比（上市）、集保股權分散表（每週，千張大戶＝持有逾 1,000 張）。投信／外資「60 日成本」＝近 60 日買超日的買超股數 × 當日均價加權。</li>
<li><b>時點</b>：ETF 揭露日的持股＝當日收盤後部位（成交在當日）；任何訊號最早只能在次一交易日開盤進場，成績單一律以此計算。</li>
<li><b>公司行動</b>：減資、股票股利、面額變更造成的股數跳動，若股價同步反向變動，視為公司行動、不當成交易。</li></ul>
<h3>限制</h3><ul class=doc>
<li>ETF 持股史自 ${esc((D.asof||{}).start||'—')} 起，樣本短、行情單一；成績單會隨每日累積自動更新，樣本 &lt;30 的訊號不宜採信。</li>
<li>主動 ETF 持股每日公開，抄作業的人多時，效果可能已反映在隔夜跳空——成績單把「隔夜跳空」與「進場後」分開列。</li>
<li>海外持股只有 ETF 面（無官方籌碼、技術面）；櫃買無借券與外資持股比欄位。</li>
<li>資料：ETF 持股＝etfinfo／復華官網；價量與籌碼＝證交所、櫃買中心、集保結算所公開資料。本頁為資料整理與統計，不構成任何投資建議。</li></ul>`;
}

/* ---------- 個股卡 ---------- */
function kv(lbl,val,extra=''){return `<div><span>${lbl}</span><b>${val}</b>${extra?`<em>${extra}</em>`:''}</div>`;}
function openStock(c){if(location.hash!=='#s='+c)location.hash='s='+c;else renderStock(c);}
function closeStock(){if(location.hash.startsWith('#s='))history.back();$('#dv').hidden=true;document.body.style.overflow='';}
window.addEventListener('hashchange',()=>{const m=location.hash.match(/^#s=(.+)$/);if(m)renderStock(decodeURIComponent(m[1]));else{$('#dv').hidden=true;document.body.style.overflow='';}});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('#dv').hidden)closeStock();});
$('#dv').addEventListener('click',e=>{if(e.target.id==='dv')closeStock();});

function renderStock(c){
  const r=D.rows.find(x=>x.c===c);if(!r)return;const s=(D.ser||{})[c]||{};const tw=r.m!=='os';const u=tw?'張':'股';
  let h=`<div class=dvh><b>${esc(r.n)}</b><span class=cd>${esc(r.c)} · ${MK[r.m]||''}${r.ind?' · '+esc(r.ind):''}</span><span class=px>${f(r.px,2)}</span>${sgn(r.ch,2,'%')}<a class=x id=x>×</a></div>`;
  h+=`<div style="margin:8px 0">${sgChips(r.sg)||'<span class=st>今日無觸發訊號</span>'}</div>`;
  h+=`<h3>ETF 面</h3><div class=kv>`+
   kv('持有 ETF',`${r.ne} 檔`,`主動 ${r.na}／被動 ${r.np} · ${r.ni} 家投信`)+
   kv('ETF 合計持股',`${f(r.sh,tw?0:0)} ${u}`)+
   (tw?kv('ETF 持股率',r.hp==null?'—':f(r.hp,2)+'%','占發行股數'):'')+
   (tw?kv('消化天數',r.dx==null?'—':f(r.dx,1)+' 天','合計持股 ÷ 20 日均量'):'')+
   kv(`主動真加碼 1／5／20 日（${u}）`,`${sgn(r.a1,0)}／${sgn(r.a5,0)}／${sgn(r.a20,0)}`,r.a5v!=null?`5 日約 ${f(r.a5v,2)} 億`:'')+
   kv('全部 ETF 淨增減 5 日',`${sgn(r.r5,0)} ${u}`,r.v5!=null?`占 5 日成交量 ${f(r.v5,1)}%`:'')+
   kv('加碼投信（5 日）',(r.ia5||[]).join('、')||'—')+
   kv('減碼投信（5 日）',(r.ic5||[]).join('、')||'—')+
   kv('10 日內新建倉',(r.nb10||[]).join('、')||'—')+
   kv('主動 ETF 估計成本',r.cost==null?'—':f(r.cost,2),`品質 ${r.cq}`)+
   kv('現價對成本',sgn(r.dev,1,'%'))+
   (tw?kv('超配（主動平均 − 市值權重）',sgn(r.ow,2,'pp'),`主動 ${r.aw==null?'—':f(r.aw,2)}% vs 市值 ${r.mw==null?'—':f(r.mw,2)}%`):'')+
   (tw&&r.now!=null?kv('超配投信家數',`${r.now}／${r.nact}`):'')+`</div>`;
  if(s.c&&s.c.some(x=>x!=null))h+=`<h3>走勢（${(D.dates||[]).length} 個交易日）</h3><div class=cw id=kc>${kline(s,tw)}</div><div class=lg><span><i style="background:#2563c9"></i>20 日線</span><span><i style="background:#f59e0b"></i>60 日線</span><span><i style="background:#a16207;height:2px;border-top:2px dashed #a16207"></i>主動 ETF 成本線</span></div>`;
  if(s.et&&s.et.some(x=>x))h+=`<h3>ETF 合計持股（${u}）</h3>${lineChart(s.et,'#2563c9',90)}`;
  h+=`<h3>持有明細</h3><div class=tw><table><thead><tr><th>ETF</th><th>權重</th><th>${u}數</th><th>建倉日</th><th>持有</th><th>估計成本</th><th>損益</th><th>5 日真加減</th><th>最近動作</th></tr></thead><tbody>`+
   (r.hd||[]).slice().sort((a,b)=>(b[1]||0)-(a[1]||0)).map(x=>{const m=E[x[0]]||{};return `<tr><td><span class=nm>${esc(x[0])}</span><span class=cd>${esc(m.is||'')}${m.k==='p'?' · 被動':''}</span></td><td>${f(x[1],2)}%</td><td>${f(x[2],tw?1:0)}</td><td>${x[3]?(x[4]?'':'≤')+esc(x[3].slice(5).replace('-','/')):'—'}</td><td>${x[5]==null?'—':x[5]+' 日'}</td><td>${x[6]==null?'—':f(x[6],2)}${x[12]==='B'?'<sup class=mu>B</sup>':''}</td><td>${sgn(x[7],1,'%')}</td><td>${sgn(x[8],tw?1:0)}</td><td>${x[9]?`<span class="k-${x[9]}">${KN[x[9]]}</span> <span class=mu>${esc((x[10]||'').slice(5))}</span>${Math.abs(x[11])>=2?` <span class=pill>連${Math.abs(x[11])}</span>`:''}`:'—'}</td></tr>`;}).join('')+
   (r.ex||[]).map(x=>`<tr class=grey><td>${esc(x[0])}</td><td colspan=7>已出清 ${f(x[2],1)} ${u}</td><td>${esc(x[1].slice(5))}</td></tr>`).join('')+`</tbody></table></div>`;
  if(tw&&r.f5!==undefined){
    h+=`<h3>籌碼</h3><div class=kv>`+
     kv('外資 1／5／20 日',`${sgn(r.f1,0)}／${sgn(r.f5,0)}／${sgn(r.f20,0)}`,(r.fs?`連${r.fs>0?'買':'賣'} ${Math.abs(r.fs)} 日`:''))+
     kv('投信 1／5／20 日',`${sgn(r.t1,0)}／${sgn(r.t5,0)}／${sgn(r.t20,0)}`,(r.ts?`連${r.ts>0?'買':'賣'} ${Math.abs(r.ts)} 日`:''))+
     kv('自營商 5 日',sgn(r.d5,0))+
     kv('投信 60 日買超均價',r.tc==null?'—':f(r.tc,2),r.tc&&r.px?`現價 ${sgn((r.px/r.tc-1)*100,1,'%')}`:'')+
     kv('外資 60 日買超均價',r.fc==null?'—':f(r.fc,2),r.fc&&r.px?`現價 ${sgn((r.px/r.fc-1)*100,1,'%')}`:'')+
     kv('投信 20 日買超占股本',r.t20p==null?'—':sgn(r.t20p,3,'%'))+
     (r.fp!=null?kv('外資持股比',f(r.fp,2)+'%',`20 日 ${sgn(r.fpd,2,'pp')}`):'')+
     kv('融資餘額',r.mb==null?'—':f(r.mb,0)+' 張',`5 日 ${sgn(r.mb5,1,'%')}／20 日 ${sgn(r.mb20,1,'%')}`)+
     kv('融券餘額',r.sb==null?'—':f(r.sb,0)+' 張',r.sr!=null?`券資比 ${f(r.sr,1)}%`:'')+
     (r.lb!=null?kv('借券賣出餘額',f(r.lb,0)+' 張',`5 日 ${sgn(r.lb5,0)}`):'')+
     (r.big!=null?kv('千張大戶持股',f(r.big,2)+'%',`週變化 ${sgn(r.bigd,2,'pp')}`):'')+
     (r.hold!=null?kv('股東人數',f(r.hold,0),r.holdd!=null?`週 ${sgn(r.holdd,0)}`:''):'')+`</div>`;
    if(s.qf)h+=`<div class=note>外資（上）／投信（下）每日買賣超（張），近 ${s.qf.length} 日</div>${bars(s.qf,60)}${bars(s.qt,60)}`;
  }
  if(tw&&r.al!==undefined){
    const ma=r.ma||{};
    h+=`<h3>技術面</h3><div class=kv>`+
     kv('均線排列',r.al||'—',Object.entries(ma).map(([k,v])=>`${k}日 ${f(v,1)}`).slice(0,3).join(' '))+
     kv('乖離 20／60 日',`${sgn(r.b20,1,'%')}／${sgn(r.b60,1,'%')}`)+
     kv('量比（今日 ÷ 20 日均量）',r.vr==null?'—':f(r.vr,2)+' 倍')+
     kv('KD(9)',`${f(r.k,0)}／${f(r.d,0)}`)+kv('RSI(14)',f(r.rsi,0))+
     kv('MACD 柱',sgn(r.mh,2),r.mx===1?'剛翻正':r.mx===-1?'剛翻負':'')+
     kv('突破',[r.h20?'創 20 日高':'',r.h60?'創 60 日高':'',r.l20?'破 20 日低':''].filter(Boolean).join('、')||'—')+
     kv('一年區間位置',r.p52==null?'—':f(r.p52,0)+'%',r.n52<240?`僅 ${r.n52} 日資料`:'0%＝一年低、100%＝一年高')+
     kv('20 日相對大盤',sgn(r.rs20,1,'pp'))+
     kv('ATR 波動',r.atrp==null?'—':f(r.atrp,2)+'%','14 日平均真實區間 ÷ 股價')+
     kv('日均成交值',r.liq==null?'—':f(r.liq,2)+' 億','20 日')+`</div>`;
  }
  h+=idxCard(c);
  if((r.sg||[]).length){h+=`<h3>觸發訊號與歷史成績</h3>`+(r.sg||[]).map(k=>`<div class=card><h4>${RISK.has(k)?'⚠ ':''}${esc((SD[k]||[k])[0])}</h4><div class=st>${esc((SD[k]||['',''])[1])}</div>${statLine(k)}</div>`).join('');}
  $('#dvin').innerHTML=h;$('#dv').hidden=false;document.body.style.overflow='hidden';$('#dv').scrollTop=0;
  $('#x').onclick=closeStock;bindTip();
}

/* ---------- 圖 ---------- */
function rng(arrs){let lo=Infinity,hi=-Infinity;arrs.forEach(a=>(a||[]).forEach(v=>{if(v!=null){lo=Math.min(lo,v);hi=Math.max(hi,v);}}));if(lo===Infinity)return [0,1];if(lo===hi){lo*=.98;hi*=1.02;}return [lo,hi];}
function sma(a,n){const o=[];let s=0,q=[];for(const v of a){if(v==null){o.push(null);continue;}q.push(v);s+=v;if(q.length>n)s-=q.shift();o.push(q.length===n?s/n:null);}return o;}
function path(a,x,y){let d='',pen=false;a.forEach((v,i)=>{if(v==null){pen=false;return;}d+=(pen?'L':'M')+x(i).toFixed(1)+' '+y(v).toFixed(1);pen=true;});return d;}
function kline(s,tw){
  const n=s.c.length,W=720,H=260,VH=60,pad=4;const c=s.c,o=s.o||c,hi=s.h||c,lo=s.l||c;
  const [a,b]=rng([hi,lo,s.ac]);const x=i=>pad+(i+.5)*(W-2*pad)/n,y=v=>8+(H-16)*(1-(v-a)/(b-a));
  const cw=Math.max(1,(W-2*pad)/n*.62);let g='';
  for(let i=0;i<n;i++){if(c[i]==null)continue;const up=c[i]>=(o[i]??c[i]);const col=up?'#d33a34':'#1f9d57';
    g+=`<line x1=${x(i).toFixed(1)} x2=${x(i).toFixed(1)} y1=${y(hi[i]??c[i]).toFixed(1)} y2=${y(lo[i]??c[i]).toFixed(1)} stroke="${col}" stroke-width=1 />`;
    const t=y(Math.max(o[i]??c[i],c[i])),bt=y(Math.min(o[i]??c[i],c[i]));g+=`<rect x=${(x(i)-cw/2).toFixed(1)} y=${t.toFixed(1)} width=${cw.toFixed(1)} height=${Math.max(1,bt-t).toFixed(1)} fill="${col}"/>`;}
  g+=`<path d="${path(sma(c,20),x,y)}" fill=none stroke="#2563c9" stroke-width=1.4 />`;
  g+=`<path d="${path(sma(c,60),x,y)}" fill=none stroke="#f59e0b" stroke-width=1.4 />`;
  if(s.ac)g+=`<path d="${path(s.ac,x,y)}" fill=none stroke="#a16207" stroke-width=1.6 stroke-dasharray="5 4" />`;
  let vb='';if(s.v){const vm=Math.max(...s.v.filter(v=>v!=null),1);s.v.forEach((v,i)=>{if(v==null)return;const up=c[i]!=null&&c[i]>=(o[i]??c[i]);const hh=(VH-6)*v/vm;vb+=`<rect x=${(x(i)-cw/2).toFixed(1)} y=${(H+VH-hh).toFixed(1)} width=${cw.toFixed(1)} height=${hh.toFixed(1)} fill="${up?'#d33a34':'#1f9d57'}" opacity=.45 />`;});}
  const ds=D.dates||[];const lab=[0,Math.floor(n/2),n-1].map(i=>`<text x=${x(i).toFixed(0)} y=${H+VH+14} font-size=11 fill="#727e8c" text-anchor=${i===0?'start':i===n-1?'end':'middle'}>${esc((ds[ds.length-n+i]||'').slice(5))}</text>`).join('');
  const yl=[a,(a+b)/2,b].map(v=>`<text x=${W-2} y=${(y(v)-3).toFixed(0)} font-size=11 fill="#727e8c" text-anchor=end>${f(v,v<100?2:0)}</text>`).join('');
  return `<svg viewBox="0 0 ${W} ${H+VH+18}" data-n=${n} data-w=${W}>${g}${vb}${lab}${yl}<rect class=hit x=0 y=0 width=${W} height=${H+VH} fill=transparent /></svg>`;
}
function lineChart(a,col,H){const n=a.length,W=720;const [lo,hi]=rng([a]);const x=i=>(i+.5)*W/n,y=v=>6+(H-12)*(1-(v-lo)/(hi-lo));
  return `<svg viewBox="0 0 ${W} ${H+14}"><path d="${path(a,x,y)}" fill=none stroke="${col}" stroke-width=1.6 /><text x=2 y=12 font-size=11 fill="#727e8c">${f(hi,0)}</text><text x=2 y=${H} font-size=11 fill="#727e8c">${f(lo,0)}</text></svg>`;}
function bars(a,H){if(!a)return '';const n=a.length,W=720;const m=Math.max(...a.filter(v=>v!=null).map(Math.abs),1);const z=H/2,bw=Math.max(1,W/n*.7);
  let g=`<line x1=0 x2=${W} y1=${z} y2=${z} stroke="#e8ebf1"/>`;a.forEach((v,i)=>{if(v==null||v===0)return;const hh=(H/2-2)*Math.abs(v)/m;const xx=(i+.5)*W/n-bw/2;g+=`<rect x=${xx.toFixed(1)} y=${(v>0?z-hh:z).toFixed(1)} width=${bw.toFixed(1)} height=${hh.toFixed(1)} fill="${v>0?'#d33a34':'#1f9d57'}"/>`;});
  return `<svg viewBox="0 0 ${W} ${H}">${g}<text x=${W-2} y=11 font-size=11 fill="#727e8c" text-anchor=end>±${f(m,0)}</text></svg>`;}
function bindTip(){const kc=document.getElementById('kc');if(!kc)return;const svg=kc.querySelector('svg');const c=D.rows&&0;
  let tip=kc.querySelector('.tip');if(!tip){tip=document.createElement('div');tip.className='tip';tip.hidden=true;kc.appendChild(tip);}
  const code=decodeURIComponent((location.hash.match(/^#s=(.+)$/)||[])[1]||'');const s=(D.ser||{})[code]||{};const n=+svg.dataset.n,W=+svg.dataset.w;const ds=D.dates||[];
  const mv=e=>{const rc=svg.getBoundingClientRect();const px=((e.touches?e.touches[0].clientX:e.clientX)-rc.left)/rc.width*W;const i=Math.max(0,Math.min(n-1,Math.floor((px-4)/((W-8)/n))));
    if(s.c[i]==null){tip.hidden=true;return;}tip.hidden=false;
    tip.innerHTML=`${esc((ds[ds.length-n+i]||''))}　收 ${f(s.c[i],2)}${s.o?`　開 ${f(s.o[i],2)} 高 ${f(s.h[i],2)} 低 ${f(s.l[i],2)}`:''}${s.v?`　量 ${f(s.v[i],0)} 張`:''}${s.ac&&s.ac[i]?`　ETF 成本 ${f(s.ac[i],2)}`:''}`;
    const left=Math.min(rc.width-tip.offsetWidth-4,Math.max(0,(px/W)*rc.width+8));tip.style.left=left+'px';tip.style.top='4px';};
  svg.onmousemove=mv;svg.ontouchmove=mv;svg.onmouseleave=()=>tip.hidden=true;}


/* ---------- 指數調整 ---------- */
function md(d){return d?esc(d.slice(5).replace('-','/')):'—';}
function nmOf(c){const r=D.rows.find(x=>x.c===c);return r?r.n:(((D.idx||{}).names||{})[c]||c);}
function idxTbl(title,rows,side){
  if(!rows||!rows.length)return `<div class=st style="margin:6px 0">${esc(title)}：無</div>`;
  return `<h4 style="margin:12px 0 4px">${esc(title)}</h4><div class=tw><table><thead><tr><th>代號／名稱</th><th>市值排名</th><th>市值(億)</th><th>${side==='add'?'距第 40 名':'距跌出 60 名'}</th><th>機率</th><th>被動${side==='add'?'買進':'賣出'}(張)</th><th>約幾日量</th><th>收盤</th></tr></thead><tbody>`+
   rows.map(r=>`<tr data-c="${esc(r[0])}"><td><span class=nm>${esc(r[1])}</span><span class=cd>${esc(r[0])}</span></td><td>${r[2]??'—'}</td><td>${f(r[3],0)}</td><td>${r[4]==null?'—':(r[4]===0?'已跨線':sgn(r[4],1,'%'))}</td><td>${r[5]==null?'—':r[5]+'%'}</td><td>${sgn(r[6],0)}</td><td>${r[7]==null?'—':f(r[7],1)}</td><td>${f(r[8],2)}</td></tr>`).join('')+`</tbody></table></div>`;}
function vIdx(){
  const X=D.idx||{};
  let h=`<div class=note>被動 ETF 追蹤的指數定期換股，生效日被動資金會集中買賣。<b>預測</b>只對規則可複製的指數做（目前：臺灣50）；其他指數先看每日持股揭露裡已經發生的換股。日期標「推算」者官方尚未公告。</div>`;
  if(X.err)h+=`<div class=st>指數區塊錯誤：${esc(X.err)}</div>`;
  h+=`<h3>審核行事曆</h3><div class=tw><table><thead><tr><th>指數</th><th>ETF</th><th>資料截止</th><th>公告</th><th>生效／被動交易</th><th>過渡</th><th>狀態</th><th>預測</th></tr></thead><tbody>`+
   (X.cal||[]).map(r=>`<tr><td><span class=nm>${esc(r[1])}</span></td><td>${esc((r[2]||[]).join(' '))}</td><td>${md(r[4])}</td><td>${md(r[5])}</td><td>${md(r[6])}${r[10]!=null&&r[10]>=0?` <span class=pill>${r[10]} 天後</span>`:''}</td><td>${r[7]==null?'—':(r[7]?r[7]+' 日':'一次')}</td><td>${esc(r[8]||'')}</td><td>${r[12]?'信心 '+esc(r[9]||''):'<span class=mu>未預測（信心 '+esc(r[9]||'')+'）</span>'}</td></tr>`).join('')+`</tbody></table></div>`;
  const t=X.tw50||{};
  h+=`<h3>臺灣50（0050／006208）換股預測</h3>`;
  if(!t.ok)h+=`<div class=st>${esc(t.why||'尚無資料')}</div>`;
  else{
    h+=`<div class=note>排名基準 ${md(t.asof)}${t.frozen?'（＝資料截止日，指數公司用的就是這天，結果近乎確定）':`；距資料截止 ${md(t.cutoff)} 還有 ${t.n_days} 個交易日，機率依個股 60 日波動估計`}。被動部位：${Object.entries(t.eq||{}).map(([e,v])=>esc(e)+' '+f(v,0)+' 億').join('、')}。刪除股的賣出量＝兩檔 ETF 目前實際持股；納入股的買進量＝規模 × 預估權重（以現有成分股反推自由流通比例）。</div>`;
    h+=idxTbl('預估納入',t.adds,'add')+idxTbl('預估刪除',t.dels,'del')+idxTbl('邊緣觀察：可能升入前 40 名',t.watch_in,'add')+idxTbl('邊緣觀察：可能跌出 60 名',t.watch_out,'del');
    const rp=t.replay||[];
    if(rp.length){h+=`<h4 style="margin:14px 0 4px">回測：用當次資料截止日的價量重跑規則</h4><div class=tw><table><thead><tr><th>審核</th><th>資料日</th><th>實際納入</th><th>預測納入</th><th>命中</th><th>實際刪除</th><th>預測刪除</th><th>命中</th></tr></thead><tbody>`+
      rp.map(r=>`<tr><td>${esc(r.review)}</td><td>${md(r.data)}</td><td>${(r.act_add||[]).map(nmOf).map(esc).join('、')}</td><td>${r.pred_add?(r.pred_add.map(nmOf).map(esc).join('、')||'—'):'<span class=mu>資料不足</span>'}</td><td>${r.pred_add?`${r.hit_add}／${(r.act_add||[]).length}`:'—'}</td><td>${(r.act_del||[]).map(nmOf).map(esc).join('、')}</td><td>${r.pred_del?(r.pred_del.map(nmOf).map(esc).join('、')||'—'):'—'}</td><td>${r.pred_del?`${r.hit_del}／${(r.act_del||[]).length}`:'—'}</td></tr>`).join('')+`</tbody></table></div><div class=note>發行股數用最新值（股本變動會造成少量誤差）；臺灣50 實際依富時自由流通與流動性細則，邊界 ±2 名內可能不同。</div>`;}
  }
  for(const r of (X.cal||[])){if(r[12])continue;const hi=(r[13]||[])[0];
    h+=`<div class=card><h4>${esc(r[1])} <span class=pill>${esc((r[2]||[]).join(' '))}</span> <span class=pill>信心 ${esc(r[9]||'')}</span></h4><div class=st>${esc(r[11]||'')}</div>`+
     (hi?`<div class=st style="margin-top:4px">上次（${esc(hi.review||'')}）納入：${esc((hi.adds_names||(hi.adds||[]).map(nmOf)).join('、')||'—')}；刪除：${esc((hi.dels_names||(hi.dels||[]).map(nmOf)).join('、')||'—')}</div>`:'')+
     `<div class=st style="margin-top:4px">公告前預測：${r[0]==='msci_esg30'?'ESG 評分為付費資料，不做；公告後看持股揭露追蹤提前建倉':r[0]==='tw_div'?'第三階段（以公開殖利率代理分析師預估，信心中低）':'第二階段（需股利、EPS 資料）'}</div></div>`;}
  const pf=X.pflow||[];
  h+=`<h3>被動 ETF 近 10 個交易日換股動作</h3><div class=note>所有被動 ETF（含規模前段擴充檔）持股揭露裡已發生的新進、出清與真加減碼（已扣申贖），依個股彙整。換股期間這裡會先反映。</div>`;
  h+=pf.length?`<div class=tw><table><thead><tr><th>代號／名稱</th><th>被動淨買賣(張)</th><th>約幾日量</th><th>新進</th><th>出清</th><th>涉及 ETF</th></tr></thead><tbody>`+pf.map(r=>`<tr data-c="${esc(r[0])}"><td><span class=nm>${esc(r[1])}</span><span class=cd>${esc(r[0])}</span></td><td>${sgn(r[2],0)}</td><td>${r[3]==null?'—':sgn(r[3],2)}</td><td>${esc((r[4]||[]).join(' '))}</td><td>${esc((r[5]||[]).join(' '))}</td><td class=mu>${esc((r[6]||[]).join(' '))}</td></tr>`).join('')+`</tbody></table></div>`:'<div class=st>近 10 日無被動換股動作</div>';
  $('#main').innerHTML=h;
  document.querySelectorAll('tr[data-c]').forEach(e=>e.onclick=()=>{if(D.rows.find(x=>x.c===e.dataset.c))openStock(e.dataset.c);});
}
function idxCard(c){
  const t=(D.idx||{}).tw50||{};const hits=[];
  const lab={adds:'預估納入臺灣50',dels:'預估自臺灣50 刪除',watch_in:'臺灣50 邊緣（可能升入）',watch_out:'臺灣50 邊緣（可能跌出）'};
  for(const k of Object.keys(lab)){const r=(t[k]||[]).find(x=>x[0]===c);if(r)hits.push(kv(lab[k],`第 ${r[2]} 名`,`${r[4]===0?'已跨線':'還差 '+f(r[4],1)+'%'}${r[5]!=null?' · 機率 '+r[5]+'%':''}${r[6]!=null?' · 被動 '+(r[6]>0?'+':'')+f(r[6],0)+' 張（約 '+f(r[7],1)+' 日量）':''}`));}
  const pf=((D.idx||{}).pflow||[]).find(x=>x[0]===c);
  if(pf)hits.push(kv('被動 ETF 近 10 日淨買賣',sgn(pf[2],0)+' 張',`${pf[3]!=null?'約 '+f(pf[3],2)+' 日量 · ':''}${(pf[4]||[]).length?'新進 '+pf[4].join(' '):''}${(pf[5]||[]).length?' 出清 '+pf[5].join(' '):''}`));
  return hits.length?`<h3>指數調整</h3><div class=kv>${hits.join('')}</div>`:'';
}

/* ---------- 分頁 ---------- */
const VIEWS={tbl:vTbl,sig:vSig,iss:vIss,idx:vIdx,bt:vBt,doc:vDoc};
function go(t){S.tab=t;save();document.querySelectorAll('#tabs a').forEach(a=>a.classList.toggle('on',a.dataset.t===t));VIEWS[t]();window.scrollTo(0,0);}
document.querySelectorAll('#tabs a').forEach(a=>a.onclick=()=>go(a.dataset.t));
go(VIEWS[S.tab]?S.tab:'tbl');
{const m=location.hash.match(/^#s=(.+)$/);if(m)renderStock(decodeURIComponent(m[1]));}
"""
