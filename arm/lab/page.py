"""籌碼雷達獨立頁 → dashboard/x9.html（主頁頁尾右下角小點進入；刻意不放導覽列）。

全頁由內嵌 JSON 在瀏覽器端渲染（表格排序／篩選、個股卡、SVG K 線）。輸出決定性：
不寫入任何牆鐘時間，資料沒變時位元組相同 → git 無 diff、不產生空 commit。

版面（2026-10-14 改版，規劃與定案見 docs/lab_ui_plan.md）：
今日｜個股｜投信｜訊號｜策略｜指數 六個分頁，一打開是「今日」重點；每頁頂端先給白話結論，
分頁內各段全部展開、第二排是跳段目錄（同主頁慣例）。術語旁的 ⓘ 讀同一份辭典 GL，
原「說明」分頁改為頂欄「ⓘ 名詞」。
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


def _md(d) -> str:
    """'2026-10-13' → '10/13'。"""
    d = str(d or "")
    return f"{int(d[5:7])}/{int(d[8:10])}" if len(d) >= 10 and d[5:7].isdigit() and d[8:10].isdigit() else "—"


def asof_line(data: dict) -> str:
    """頂欄資料日：多數來源同一天只寫一次，落後的另外標；集保是週資料；ETF 揭露未到齊時標檔數。"""
    a = data.get("asof") or {}
    keys = (("ETF 持股", "pos"), ("價量", "px"), ("法人", "chip"), ("融資券", "margin"))
    ds = [a[k] for _, k in keys if a.get(k)]
    if not ds:
        return "尚無資料"
    main = max(sorted(set(ds), reverse=True), key=ds.count)     # 同票數取較新的一天
    parts = [f"資料日 {_md(main)}"]
    parts += [f"{lbl} {_md(a[k])}" for lbl, k in keys if a.get(k) and a[k] != main]
    if a.get("tdcc"):
        parts.append(f"集保 {_md(a['tdcc'])}（每週）")
    etfs = data.get("etfs") or {}
    if etfs and a.get("pos"):
        n = sum(1 for m in etfs.values() if m.get("d") == a["pos"])
        if n < len(etfs):
            parts.append(f"ETF 揭露 {n}/{len(etfs)} 檔到 {_md(a['pos'])}")
    return " · ".join(html.escape(p) for p in parts)


def render(data: dict) -> str:
    blob = json.dumps(_slim(data), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    blob = blob.replace("</", "<\\/")
    return (_HTML.replace("{{SUB}}", asof_line(data)).replace("{{CSS}}", _CSS)
            .replace("{{DATA}}", blob).replace("{{JS}}", _JS))


_HTML = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>籌碼雷達</title>
<style>{{CSS}}</style></head>
<body>
<div class="top"><b>籌碼雷達</b><span class="asof">{{SUB}}</span><a class="back" href="./">返回主頁</a></div>
<header class="hd"><div class="hdi">
  <nav class="tabs" id="tabs">
    <a data-t="today">今日</a><a data-t="stk">個股</a><a data-t="iss">投信</a><a data-t="sig">訊號</a><a data-t="st">策略</a><a data-t="idx">指數</a>
    <a class="glb" id="glb"><i class="gi">i</i>名詞</a>
  </nav>
  <nav class="snav" id="snav"></nav>
</div></header>
<main id="main"></main>
<div id="dv" class="dv" hidden><div class="dvin" id="dvin"></div></div>
<div id="gl" class="dv" hidden><div class="dvin" id="glin"></div></div>
<div id="pop" class="pop" hidden></div>
<script type="application/json" id="labdata">{{DATA}}</script>
<script>{{JS}}</script>
</body></html>
"""

_CSS = """
:root{--bg:#fff;--card2:#f4f6fa;--ink:#1f2733;--ink2:#44505f;--mut:#727e8c;--line:#e8ebf1;--acc:#2563c9;
--accd:#1c4fa8;--gain:#d33a34;--loss:#1f9d57;--gold:#a16207;--inset:#eef2f8;--warn:#b45309;--hlbg:#dce7fa;
--gainbg:#fdecea;--lossbg:#e6f5ec}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 -apple-system,"PingFang TC","Noto Sans TC",Segoe UI,sans-serif;-webkit-text-size-adjust:100%}
a{color:var(--acc);text-decoration:none;cursor:pointer}
table,.fv,.num{font-variant-numeric:tabular-nums}
.top{display:flex;align-items:baseline;gap:4px 12px;flex-wrap:wrap;padding:10px 16px 4px;max-width:1180px;margin:0 auto}
.top b{font-size:18px}.asof{color:var(--mut);font-size:12.5px;flex:1;min-width:0}
.back{font-size:13px;color:var(--mut);white-space:nowrap}
.hd{position:sticky;top:0;z-index:20;background:var(--bg);border-bottom:1px solid var(--line)}
.hdi{max-width:1180px;margin:0 auto;padding:0 16px}
.tabs{display:flex;gap:2px;overflow-x:auto;scrollbar-width:none}
.tabs::-webkit-scrollbar,.snav::-webkit-scrollbar{display:none}
.tabs a{padding:9px 12px 7px;color:var(--mut);font-weight:700;white-space:nowrap;border-bottom:3px solid transparent}
.tabs a.on{color:var(--ink);border-bottom-color:var(--acc)}
.tabs .glb{margin-left:auto;font-weight:600;color:var(--accd);display:inline-flex;align-items:center;gap:2px}
.tabs .glb .gi{margin:0 2px 0 0;border-color:var(--acc);color:var(--acc)}
.snav{display:flex;gap:4px;overflow-x:auto;scrollbar-width:none;padding:6px 0 7px;border-top:1px solid var(--line)}
.snav:empty{display:none}
.snav a{padding:2px 10px;border-radius:12px;color:var(--ink2);font-size:13px;white-space:nowrap}
.snav a.on{background:var(--hlbg);color:var(--accd);font-weight:700}
main{padding:16px 16px 90px;max-width:1180px;margin:0 auto}
.sec{margin:0 0 34px}
.sec>h2{display:flex;align-items:baseline;flex-wrap:wrap;gap:2px 10px;font-size:17px;margin:0 0 10px;line-height:1.45}
.sec>h2 .sub{font-size:12.5px;font-weight:400;color:var(--mut)}
.sec>h2 .rt{margin-left:auto;font-size:13px;font-weight:600}
.intro{color:var(--ink2);font-size:13.5px;margin:0 0 18px;line-height:1.8}
.lead{background:var(--card2);border-radius:12px;padding:10px 16px 10px 12px}
.lead ul{margin:0;padding-left:20px}.lead li{margin:7px 0;line-height:1.75}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:14px 32px}
.g2 h3{font-size:14px;margin:0 0 2px;padding-bottom:4px;border-bottom:2px solid var(--line)}
.fl,.nb{display:grid;grid-template-columns:minmax(0,1.15fr) 64px minmax(36px,1fr) 74px;align-items:center;gap:8px;padding:6px 4px;border-bottom:1px solid var(--line);cursor:pointer}
.nb{grid-template-columns:minmax(0,1fr) minmax(0,2.2fr) 70px}
.fl:hover,.nb:hover{background:#f8fafd}
.fn{min-width:0;display:flex;flex-direction:column;line-height:1.3}
.fn b{font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.fn i{font-style:normal;color:var(--mut);font-size:12px}
.fv{text-align:right;font-weight:700;white-space:nowrap}
.fb{height:8px;background:var(--inset);border-radius:4px;overflow:hidden}
.fb i{display:block;height:100%;border-radius:4px}.fb .bu{background:var(--gain)}.fb .bd{background:var(--loss)}
.fi{font-size:12px;color:var(--mut);text-align:right;white-space:nowrap}
.flh{cursor:default;padding:2px 4px;border-bottom:0;font-size:11.5px;color:var(--mut)}.flh:hover{background:none}
.flh span:nth-child(2),.flh span:nth-child(4){text-align:right}
.nbs{display:grid;grid-auto-flow:column;grid-template-columns:1fr 1fr;column-gap:32px}
.cr{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1.4fr) 110px;gap:2px 14px;align-items:center;padding:8px 4px;border-bottom:1px solid var(--line);cursor:pointer}
.cr:hover{background:#f8fafd}.crc{font-weight:600}.crs{text-align:right;line-height:1.35}.crs .st{display:block;font-size:11.5px}
.rk2{padding:10px 0;border-bottom:1px solid var(--line)}.rk2>b{font-size:14.5px}.rk2>.st{margin-left:8px}.rk2 .inl{margin-top:4px}
.tg{display:inline-block;font-size:12px;padding:0 7px;border-radius:9px;background:var(--card2);color:var(--ink2);margin:1px 4px 1px 0;line-height:1.75;white-space:nowrap}
.tg.hot{background:var(--hlbg);color:var(--accd)}.tg.rk{background:var(--gainbg);color:var(--gain)}
.evs{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px}
.ev{border:1px solid var(--line);border-radius:12px;padding:10px 14px}
.ev .cdn{font-size:24px;font-weight:800;color:var(--accd);line-height:1.2}.ev .cdn small{font-size:13px;font-weight:600;margin-left:2px}
.ev .evn{font-weight:700;margin-top:2px}.ev .evm{font-size:12.5px;color:var(--mut)}
.sgs{display:flex;flex-wrap:wrap;gap:8px}
.sgc{display:inline-flex;align-items:center;gap:8px;padding:7px 12px;border-radius:10px;background:var(--card2);color:var(--ink);font-size:14px}
.sgc b{color:var(--accd)}.sgc.rk{background:var(--gainbg)}.sgc.rk b{color:var(--gain)}.sgc.z{opacity:.55}
.gi{display:inline-flex;align-items:center;justify-content:center;width:15px;height:15px;border-radius:50%;border:1px solid #b6bfcb;color:var(--mut);font:italic 700 10px/1 Georgia,"Times New Roman",serif;margin:0 2px 0 4px;cursor:help;vertical-align:1px;user-select:none;flex:0 0 auto}
.gi:hover{border-color:var(--acc);color:var(--acc)}
.pop{position:fixed;z-index:80;background:#1f2733;color:#fff;font-size:13px;line-height:1.7;padding:9px 12px;border-radius:10px;box-shadow:0 6px 24px rgba(15,23,42,.25)}
.pop b{display:block;margin-bottom:2px;font-size:13.5px}
.bar{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:4px 0 10px}
.bar input[type=search]{flex:1 1 180px;min-width:150px;padding:7px 10px;border:1px solid var(--line);border-radius:8px;font:inherit;background:var(--card2)}
.ch{display:inline-flex;align-items:center;gap:4px;padding:4px 10px;border-radius:14px;background:var(--card2);color:var(--ink);font-size:13px;cursor:pointer;user-select:none;border:0}
.ch.on{background:var(--acc);color:#fff}.ch.rk{background:var(--gainbg);color:var(--gain)}.ch.rk.on{background:var(--gain);color:#fff}
.ch i{font-style:normal;opacity:.7;font-size:12px}
.fbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 10px}
.fbar input[type=search]{flex:1 1 220px;min-width:160px;padding:8px 12px;border:1px solid var(--line);border-radius:10px;font:inherit;background:var(--card2)}
.fbar select{padding:7px 30px 7px 10px;border:1px solid var(--line);border-radius:10px;font:inherit;font-size:14px;color:var(--ink);background:var(--bg) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23727e8c'/%3E%3C/svg%3E") no-repeat right 11px center;-webkit-appearance:none;appearance:none;max-width:100%}
.tgl{display:inline-flex;align-items:center;gap:6px;font-size:14px;color:var(--ink2);cursor:pointer;user-select:none;white-space:nowrap}
.tgl input{width:16px;height:16px;margin:0;accent-color:var(--acc)}
.vbar{display:flex;align-items:center;gap:10px;margin:0 0 8px;flex-wrap:wrap}
.seg{display:inline-flex;background:var(--card2);border-radius:10px;padding:3px}
.seg a{padding:5px 14px;border-radius:8px;color:var(--ink2);font-size:14px;font-weight:600;white-space:nowrap}
.seg a.on{background:var(--bg);color:var(--accd);box-shadow:0 1px 3px rgba(15,23,42,.14)}
.cnt{margin-left:auto;color:var(--mut);font-size:13px}
th small{font-weight:400;margin-left:2px;font-size:11px}
.db{display:block;position:relative;height:5px;margin:4px 0 1px;min-width:64px;background:linear-gradient(var(--line),var(--line)) center/1px 100% no-repeat}
.db i{position:absolute;top:0;height:100%;border-radius:3px}.db .bu{left:50%;background:var(--gain)}.db .bd{right:50%;background:var(--loss)}
.stk td:first-child{min-width:104px;max-width:170px;white-space:normal}
.stk .nm,.stk .cd{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:160px}
a.sm{font-size:12.5px;font-weight:600;margin-left:6px}
.tw{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap;vertical-align:middle}
th{background:var(--card2);color:var(--mut);font-weight:600;font-size:12.5px}
th[data-k]{cursor:pointer}th.on{color:var(--accd)}
td:first-child,th:first-child{text-align:left;position:sticky;left:0;background:var(--bg);z-index:1}
th:first-child{background:var(--card2);z-index:2}
td.l,th.l{text-align:left}td.wr{white-space:normal;min-width:140px}
tr[data-c]{cursor:pointer}tr[data-c]:hover td{background:#f8fafd}
.nm{display:block;font-weight:600}.cd{color:var(--mut);font-size:12px}
.up{color:var(--gain)}.dn{color:var(--loss)}.mu{color:var(--mut)}
.sg{display:inline-block;font-size:11.5px;padding:1px 7px;border-radius:9px;background:rgba(37,99,201,.1);color:var(--accd);margin:1px 2px 1px 0}
.sg.rk{background:var(--gainbg);color:var(--gain)}
.more{display:block;margin:12px auto;padding:8px 18px;border:0;border-radius:8px;background:var(--card2);font:inherit;cursor:pointer}
details.mr{margin:8px 0 0}
details.mr>summary{cursor:pointer;color:var(--acc);font-size:13.5px;list-style:none;padding:4px 0}
details.mr>summary::-webkit-details-marker{display:none}
details.mr>summary:before{content:"▸ "}details.mr[open]>summary:before{content:"▾ "}
.inl{line-height:2;font-size:14px}.inl .mu{font-size:12px;margin-left:2px}.inl .it{white-space:nowrap}
.card{border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin:0 0 16px}
.card h4{margin:0 0 4px;font-size:15.5px}
.st{font-size:12.5px;color:var(--mut)}
.pill{display:inline-block;font-size:11.5px;padding:0 6px;border-radius:7px;background:var(--card2);color:var(--mut);font-weight:600}
.k-new{color:var(--gain);font-weight:700}.k-add{color:var(--gain)}.k-cut{color:var(--loss)}.k-exit{color:var(--loss);font-weight:700}
.grey td{color:#a0a8b3}
.dv{position:fixed;inset:0;z-index:50;background:rgba(15,23,42,.35);overflow-y:auto;overscroll-behavior:contain}
.dvin{background:var(--bg);max-width:980px;margin:0 auto;min-height:100%;padding:12px 16px 60px}
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
ul.doc{padding-left:18px}ul.doc li{margin:4px 0}
.tip{position:absolute;pointer-events:none;background:rgba(31,39,51,.92);color:#fff;font-size:12px;padding:4px 8px;border-radius:6px;white-space:nowrap}
.cw{position:relative}
.glh{font-size:15px;color:var(--accd);margin:20px 0 6px}
.gll{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:0 22px}
.gll div{padding:8px 0;border-bottom:1px solid var(--line)}
.gll b{display:block;font-size:14px}.gll span{font-size:13px;color:var(--ink2);line-height:1.7}
@media(min-width:760px){.dvin{margin:24px auto;min-height:auto;border-radius:12px}}
@media(max-width:760px){.g2{grid-template-columns:1fr}.nbs{grid-auto-flow:row;grid-template-columns:1fr;grid-template-rows:none!important}}
@media(max-width:600px){
 .top{padding:8px 12px 2px}.asof{flex-basis:100%;order:3;font-size:12px}
 .hdi{padding:0 6px}.tabs a{padding:9px 9px 7px;font-size:14.5px}
 main{padding:14px 12px 90px}
 .fl{grid-template-columns:minmax(0,1fr) 58px 52px 62px;gap:6px}
 .nb{grid-template-columns:minmax(0,1fr) minmax(0,1.6fr) 56px;gap:6px}
 .cr{grid-template-columns:minmax(0,1fr) 96px}.cr .crc{grid-column:1/-1;grid-row:2}.cr .crs{grid-column:2;grid-row:1}
 .rk2>.st{display:block;margin:2px 0 0}
 .fbar input[type=search]{flex-basis:100%}.fbar select{flex:1 1 0;min-width:0}
 .seg a{padding:5px 11px}
 .stk td:first-child{min-width:92px;max-width:118px}.stk .nm,.stk .cd{max-width:108px}
}
"""

_JS = r"""
const D=JSON.parse(document.getElementById('labdata').textContent);
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const E=D.etfs||{},SD=D.sigdef||{},RISK=new Set(D.risk||[]);
const ROWS=D.rows||[],BY={};ROWS.forEach(r=>BY[r.c]=r);
const KN={new:'新建倉',add:'加碼',cut:'減碼',exit:'出清',hold:'—'};
function f(x,d=1){if(x===null||x===undefined||Number.isNaN(x))return '—';const v=Number(x);return v.toLocaleString('zh-TW',{minimumFractionDigits:d,maximumFractionDigits:d});}
function sgn(x,d=1,suf=''){if(x===null||x===undefined)return '<span class=mu>—</span>';const c=x>0?'up':x<0?'dn':'mu';return `<span class=${c}>${x>0?'+':''}${f(x,d)}${suf}</span>`;}
function esc(s){return String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function md(d){d=String(d||'');return d.length>=10?esc(`${+d.slice(5,7)}/${+d.slice(8,10)}`):(d?esc(d):'—');}
function fp(x){return x==null?'—':f(x,x>=500?0:x>=50?1:2);}
function sgChips(arr){return (arr||[]).map(k=>`<span class="sg${RISK.has(k)?' rk':''}">${esc((SD[k]||[k])[0])}</span>`).join('');}
function issOf(etfs){return [...new Set((etfs||[]).map(e=>(E[e]||{}).is||e))];}
function sec(id,nav,title,sub,body,rt=''){return `<section class=sec id="${id}" data-nav="${esc(nav)}"><h2>${title}${sub?`<span class=sub>${sub}</span>`:''}${rt?`<span class=rt>${rt}</span>`:''}</h2>${body}</section>`;}
const MK={tw:'上市',tp:'上櫃',os:'海外'};const MKF={twall:'台股',tw:'上市',tp:'上櫃',os:'海外',all:'全部'};
const S={tab:'today',q:'',mk:'twall',sig:'',liq:false,sort:'a5v',dir:-1,n:60,vw:'etf'};let STK=[];
try{const z=JSON.parse(localStorage.getItem('lab.s')||'{}');for(const k of ['mk','sort','dir','liq','vw'])if(k in z)S[k]=z[k];}catch(e){}
if(!({etf:1,chip:1,ta:1})[S.vw])S.vw='etf';
function save(){try{localStorage.setItem('lab.s',JSON.stringify({mk:S.mk,sort:S.sort,dir:S.dir,liq:S.liq,vw:S.vw}));}catch(e){}}

/* ---------- 名詞辭典（ⓘ 與「名詞」頁共用） ---------- */
const GL={
'真加碼':'ETF 有人申購時，所有持股會照比例一起增加，那不代表看好。扣掉這個「申購帶來的等比例增加」後剩下的部分，才算經理人主動加碼（真減碼同理）。',
'申贖倍率':'同一檔 ETF 兩次揭露之間，共同持股股數比值的中位數；大於 1＝有申購、小於 1＝有贖回。',
'主動 5 日淨買':'近 5 個交易日，所有主動式 ETF 對這檔的真加碼減掉真減碼，乘以現價換算成金額（億元）。正＝淨買、負＝淨賣。',
'加碼／減碼家數':'近 5 個交易日有真加碼或新建倉的投信家數／有真減碼或出清的投信家數。同一家投信旗下不同 ETF 方向相反時，兩邊都會算到。',
'持有 ETF':'目前持有這檔股票的追蹤 ETF 檔數（主動式／被動式）。',
'新建倉':'主動 ETF 在觀測期內第一次持有這檔股票。',
'建倉日':'觀測期內第一次出現在該 ETF 持股的日期；標「≤」代表觀測起點前就已持有。',
'主動成本':'主動 ETF 的估計平均持有成本：每次加碼按當日成交均價入帳、減碼按平均成本沖銷。未計配息。',
'成本乖離':'現價比主動 ETF 估計成本高（正）或低（負）多少 %。',
'成本品質':'A＝觀測期內才建倉，成本逐筆入帳算出；B＝觀測起點前就已持有，成本以第一次觀測日的均價代入，只是近似值。',
'超配':'主動 ETF 給這檔的平均權重，減去它占台股（上市＋上櫃普通股）總市值的比重，單位百分點。正＝比市值權重更看好。台積電在主動 ETF 約占一成、市值占比卻近四成，所以是負的。',
'ETF 持股率':'所有追蹤 ETF 合計持股 ÷ 發行股數。',
'消化天數':'ETF 合計持股 ÷ 20 日均量：如果這些 ETF 一起出清，大約要賣幾天。',
'投信 5 日':'官方三大法人資料：投信近 5 個交易日買賣超（張）。',
'外資 5 日':'官方三大法人資料：外資近 5 個交易日買賣超（張）。',
'連買':'連續買超（正）或連續賣超（負）的天數。',
'60 日買超均價':'近 60 個交易日中，該法人買超那幾天的成交均價（以買超張數加權），可當作它近期進場成本的參考。',
'融資':'融資餘額的變化：增加代表散戶用槓桿買進的部位變多。',
'借券賣出':'借券賣出餘額（張），屬放空部位的一種；只有上市股票有資料。',
'千張大戶':'集保股權分散表中持有超過 1,000 張的股東，合計持股占比；每週公布一次。',
'趨勢':'依收盤價與 5／20／60 日均線排列：收盤＞5 日＞20 日＞60 日線＝多頭，反過來＝空頭，其餘＝整理。',
'乖離':'收盤價比 20 日（或 60 日）均線高出或低於多少 %。',
'量比':'今日成交量 ÷ 20 日均量；大於 1.5 代表明顯放量。',
'RSI':'14 日相對強弱指標，0～100；70 以上偏熱、30 以下偏冷。',
'KD':'9 日隨機指標，0～100；80 以上偏熱、20 以下偏冷。',
'MACD':'MACD 柱狀體：正＝短期動能強於長期；「剛翻正／翻負」代表剛轉向。',
'一年區間位置':'現價落在近一年最低價到最高價之間的哪裡：0%＝一年低點、100%＝一年高點。',
'相對大盤':'近 20 日漲跌減去加權指數同期漲跌（百分點）。',
'ATR':'平均真實區間（14 日）÷ 股價：每天正常的波動幅度。停損常設在 2～3 倍 ATR。',
'日均成交':'近 20 日平均成交金額（億元）。',
'超額':'報酬減去同期加權指數報酬；正＝贏大盤。成績已扣來回交易成本 0.585%。',
'勝率':'超額報酬為正的次數比例。',
'隔夜跳空':'訊號出現後隔天的開盤價，相對訊號日收盤的漲跌。跟單的人多時，好處常在隔夜就被反映掉。',
'樣本':'歷史上符合條件的次數。少於 30 次時結果容易受單一段行情左右，只能當參考。',
'紙上交易':'照寫死的規則自動記帳、不實際下單，用來驗證策略在「規則訂好之後」的真實表現。',
'樣本內':'規則訂定前的歷史資料。規則本來就是看這段資料挑出來的，成績會偏好看，只能當參考。',
'前瞻':'規則起算日之後才發生的訊號；這部分的成績才算數。',
'驗證期滿':'累積 30 筆交易或 30 個交易日（先到者）。平均超額＞0 且勝率＞50% 才算達標。',
};
const GLG=[['ETF 面',['真加碼','申贖倍率','主動 5 日淨買','加碼／減碼家數','持有 ETF','新建倉','建倉日','主動成本','成本乖離','成本品質','超配','ETF 持股率','消化天數']],
 ['法人籌碼',['投信 5 日','外資 5 日','連買','60 日買超均價','融資','借券賣出','千張大戶']],
 ['技術面',['趨勢','乖離','量比','RSI','KD','MACD','一年區間位置','相對大盤','ATR','日均成交']],
 ['成績與策略',['超額','勝率','隔夜跳空','樣本','紙上交易','樣本內','前瞻','驗證期滿']]];
function gi(k){return (GL[k]||SD[k])?`<i class=gi data-g="${esc(k)}" role=button tabindex=0 aria-label="說明">i</i>`:'';}
const POP=$('#pop');let popFor=null,popPin=false;
function showPop(el,pin){const k=el.dataset.g;const t=GL[k]||(SD[k]||[])[1];if(!t)return;
  POP.innerHTML=`<b>${esc(SD[k]?SD[k][0]:k)}</b>${esc(t)}`;POP.hidden=false;popFor=el;popPin=!!pin;
  const r=el.getBoundingClientRect(),w=Math.min(300,innerWidth-24);POP.style.width=w+'px';
  POP.style.left=Math.min(Math.max(12,r.left+r.width/2-w/2),innerWidth-w-12)+'px';POP.style.top=(r.bottom+8)+'px';
  const ph=POP.offsetHeight;if(r.bottom+8+ph>innerHeight-8)POP.style.top=Math.max(8,r.top-ph-8)+'px';}
function hidePop(){POP.hidden=true;popFor=null;popPin=false;}
document.addEventListener('click',e=>{const g=e.target.closest&&e.target.closest('.gi[data-g]');
  if(g){e.stopPropagation();e.preventDefault();if(popFor===g&&popPin)hidePop();else showPop(g,true);return;}
  if(!e.target.closest||!e.target.closest('#pop'))hidePop();},true);
document.addEventListener('keydown',e=>{const g=e.target.closest&&e.target.closest('.gi[data-g]');if(g&&(e.key==='Enter'||e.key===' ')){e.preventDefault();showPop(g,true);}});
if(matchMedia('(hover:hover)').matches){
  document.addEventListener('mouseover',e=>{const g=e.target.closest&&e.target.closest('.gi[data-g]');if(g&&!popPin)showPop(g,false);});
  document.addEventListener('mouseout',e=>{const g=e.target.closest&&e.target.closest('.gi[data-g]');if(g&&!popPin)hidePop();});}
addEventListener('scroll',()=>{if(!POP.hidden)hidePop();},true);

/* ---------- 共用：點代號開個股卡 ---------- */
document.addEventListener('click',e=>{if(e.defaultPrevented)return;const a=e.target.closest&&e.target.closest('[data-c]');
  if(a&&BY[a.dataset.c]){e.preventDefault();openStock(a.dataset.c);}});

/* ---------- 今日 ---------- */
function nmL(r){return `<a data-c="${esc(r.c)}">${esc(r.n)}</a>`;}
function cntGroup(list){const out=[];let i=0;while(i<list.length){let j=i;while(j+1<list.length&&list[j+1][1]===list[i][1])j++;
  out.push(list.slice(i,j+1).map(x=>x[0]).join('、')+`（${j>i?'各 ':''}${list[i][1]} 家）`);i=j+1;}return out.join('、');}
function allCands(){const out=[];
  for(const s of ((D.strat||{}).list||[]))for(const c of (s.cands||[]))out.push({...c,st:s.name,cond:c.gap_max===0?`開盤低於 ${f(c.px,2)} 才進`:'隔日開盤價進場'});
  const s5=(D.grow||{}).s5;if(s5)for(const t of (s5.fwd||[]))if(t.st==='cand')out.push({c:t.c,n:t.n,d:t.d,st:s5.name,cond:'隔日開盤買；開高 ≥3% 不追（最多等 5 日）',stop:null});
  return out;}
function idxEvents(){const out=[];for(const r of ((D.idx||{}).cal||[])){if(r[6]&&r[10]!=null&&r[10]>=0)out.push({n:r[1],etf:(r[2]||[]).join(' '),cut:r[4],ann:r[5],eff:r[6],tr:r[7],stt:r[8],conf:r[9],days:r[10],pred:r[12]});}
  return out.sort((a,b)=>a.days-b.days);}
function chgI(x){return x==null?'':` · <span class=${x>0?'up':x<0?'dn':''}>${x>0?'+':''}${f(x,1)}%</span>`;}
function flowRows(rs,m,side){if(!rs.length)return '<div class=st>無</div>';
  return `<div class="fl flh"><span>股票・今日漲跌</span><span>億元</span><span></span><span>投信家數${gi('加碼／減碼家數')}</span></div>`+rs.map(r=>{const w=Math.max(3,Math.abs(r.a5v)/m*100);
  return `<div class=fl data-c="${esc(r.c)}"><span class=fn><b>${esc(r.n)}</b><i>${esc(r.c)}${chgI(r.ch)}</i></span><span class="fv ${r.a5v>0?'up':'dn'}">${r.a5v>0?'+':''}${f(r.a5v,1)}</span><span class=fb><i class=${r.a5v>0?'bu':'bd'} style="width:${w.toFixed(0)}%"></i></span><span class=fi>${side==='sell'?`${(r.ic5||[]).length} 減・${(r.ia5||[]).length} 加`:`${(r.ia5||[]).length} 加・${(r.ic5||[]).length} 減`}</span></div>`;}).join('');}
function candRows(cs){return cs.map(c=>`<div class=cr data-c="${esc(c.c)}"><div class=fn><b>${esc(c.n)}</b><i>${esc(c.c)} · ${esc(c.st)} · 訊號日 ${md(c.d)}</i></div><div class=crc>${esc(c.cond)}</div><div class=crs><span class=st>停損參考</span><b>${c.stop==null?'—':f(c.stop,2)}</b></div></div>`).join('');}
function vToday(){
  const tw=ROWS.filter(r=>r.m!=='os');
  const buys=tw.filter(r=>r.a5v>0).sort((a,b)=>b.a5v-a.a5v),sells=tw.filter(r=>r.a5v<0).sort((a,b)=>a.a5v-b.a5v);
  const bs=buys.reduce((s,r)=>s+r.a5v,0),ss=-sells.reduce((s,r)=>s+r.a5v,0),net=bs-ss;
  const has=k=>ROWS.filter(r=>(r.sg||[]).includes(k));
  const cons=has('cons').sort((a,b)=>(b.ia5||[]).length-(a.ia5||[]).length||(b.a5v||0)-(a.a5v||0));
  const exits=has('exit').filter(r=>r.m!=='os').sort((a,b)=>(a.a5v||0)-(b.a5v||0));
  const nbAll=ROWS.filter(r=>(r.nb10||[]).length).map(r=>({r,is:issOf(r.nb10)}));
  const nbs=nbAll.filter(x=>x.r.m!=='os').sort((a,b)=>b.is.length-a.is.length||(b.r.a5v||0)-(a.r.a5v||0));
  const nbOs=nbAll.length-nbs.length;
  const cands=allCands(),evs=idxEvents(),t50=(D.idx||{}).tw50||{};
  const d5=(D.dates||[]).slice(-5);const win=d5.length?`${md(d5[0])}～${md(d5[d5.length-1])}`:'';
  const L=[];
  if(bs||ss){const tone=Math.abs(net)<=0.15*Math.max(bs,ss)?'買賣金額相近，以換股為主':net>0?'整體偏向加碼':'整體偏向減碼';
    L.push(`主動 ETF 近 5 日：淨買的股票合計 <b class=up>${f(bs,0)} 億</b>、淨賣的合計 <b class=dn>${f(ss,0)} 億</b>——${tone}。${gi('主動 5 日淨買')}`);}
  if(cons.length)L.push(`<b>${cons.length} 檔</b>有 3 家以上投信同時加碼${gi('cons')}，最多的是 ${cntGroup(cons.slice(0,3).map(r=>[nmL(r),(r.ia5||[]).length]))}。`);
  if(exits.length)L.push(`<b>${exits.length} 檔</b>被 3 家以上投信同時減碼${gi('exit')}，賣最多的是 ${exits.slice(0,3).map(r=>`${nmL(r)}（${f(r.a5v,1)} 億）`).join('、')}。`);
  if(nbs.length)L.push(`10 日內主動 ETF 新建倉的台股 <b>${nbs.length} 檔</b>${gi('新建倉')}，最多家同時進場的是 ${cntGroup(nbs.slice(0,3).map(x=>[nmL(x.r),x.is.length]))}。`);
  L.push(cands.length?`明日開盤前候選 <b>${cands.length} 檔</b>：${cands.map(c=>`${BY[c.c]?nmL(c):esc(c.n)}（${esc(c.st)}）`).join('、')}。`:'明日開盤前沒有策略候選。');
  if(evs.length){const e=evs[0];L.push(`最近的指數換股：<b>${esc(e.n)}</b>（${esc(e.etf)}）${md(e.eff)} 生效，還有 ${e.days} 天${e.stt==='推算'?'（日期為推算）':''}。`);}
  let h=sec('t-lead','重點','今日重點','',`<div class=lead><ul>${L.map(x=>`<li>${x}</li>`).join('')}</ul></div>`);
  const m=Math.max(1,...buys.slice(0,8).map(r=>r.a5v),...sells.slice(0,8).map(r=>-r.a5v));
  h+=sec('t-flow','買賣',`主動 ETF 買最多／賣最多${gi('主動 5 日淨買')}`,`近 5 個交易日（${win}）淨買金額・已扣申贖${gi('真加碼')}`,
    `<div class=g2><div><h3 class=up>淨買最多</h3>${flowRows(buys.slice(0,8),m,'buy')}</div><div><h3 class=dn>淨賣最多</h3>${flowRows(sells.slice(0,8),m,'sell')}</div></div>`,
    `<a data-go="stk" data-fsig="" data-sort="a5v">看全部 →</a>`);
  const nbTop=nbs.slice(0,10);
  h+=sec('t-new','新建倉',`新建倉${gi('新建倉')}`,`10 個交易日內主動 ETF 第一次買進的台股，依同時進場的投信家數排序；右側＝主動 5 日淨買（億）${nbOs?`。另有海外股 ${nbOs} 檔`:''}`,
    (nbTop.length?`<div class=nbs style="grid-template-rows:repeat(${Math.ceil(nbTop.length/2)},auto)">${nbTop.map(x=>`<div class=nb data-c="${esc(x.r.c)}"><span class=fn><b>${esc(x.r.n)}</b><i>${esc(x.r.c)}</i></span><span>${x.is.map(i=>`<span class="tg${x.is.length>=2?' hot':''}">${esc(i)}</span>`).join('')}</span><span class=fv>${x.r.a5v==null?'':sgn(x.r.a5v,1)}</span></div>`).join('')}</div>`:'<div class=st>10 日內無新建倉</div>')+
    (nbs.length>10?`<details class=mr><summary>其餘 ${nbs.length-10} 檔</summary><div class=inl>${nbs.slice(10).map(x=>`<span class=it><a data-c="${esc(x.r.c)}">${esc(x.r.n)}</a><span class=mu>${x.is.map(esc).join(' ')}</span></span>`).join('　')}</div></details>`:''),
    nbs.length?`<a data-go="stk" data-fsig="nb" data-sort="a5v">全部 ${nbs.length} 檔 →</a>`:'');
  h+=sec('t-cand','候選','明日開盤前候選','策略規則寫死、照規則自動記紙上交易',
    cands.length?candRows(cands):'<div class=st>今日沒有策略候選。</div>',`<a data-go="st">看策略 →</a>`);
  const al=(D.strat||{}).alerts||[];
  h+=sec('t-risk','風險',`風險提醒`,'',
    `<div class=rk2><b>集體撤退 ${exits.length} 檔</b>${gi('exit')}${exits.length?` <a class=sm data-go="stk" data-fsig="exit" data-sort="a5v" data-dir="1">看表格 →</a>`:''}<span class=st>近 5 日 3 家以上投信同時減碼、主動合計淨賣（億元）</span><div class=inl>`+
      (exits.length?exits.map(r=>`<span class=it><a data-c="${esc(r.c)}">${esc(r.n)}</a>${r.a5v!=null?`<span class=dn> ${f(r.a5v,1)}</span>`:''}</span>`).join('　'):'<span class=st>今日無</span>')+`</div></div>`+
    `<div class=rk2><b>跳空減碼提醒</b><span class=st>前一日「共識加碼」、今日開盤跳空 ≥3%：樣本內之後每個持有期平均都輸大盤</span><div class=inl>`+
      (al.length?al.map(a=>`<span class=it><a data-c="${esc(a.c)}">${esc(a.n)}</a> <span class=mu>開盤</span> ${sgn(a.gap,1,'%')}</span>`).join('　'):'<span class=st>今日無</span>')+`</div></div>`);
  const tw50=t50.ok?`<div class=lead style="margin-top:12px"><b>臺灣50 預測</b>：預估納入 ${(t50.adds||[]).length?(t50.adds||[]).map(r=>`<a data-c="${esc(r[0])}">${esc(r[1])}</a>`).join('、'):'無'}；預估刪除 ${(t50.dels||[]).length?(t50.dels||[]).map(r=>`<a data-c="${esc(r[0])}">${esc(r[1])}</a>`).join('、'):'無'}<span class=st>（排名基準 ${md(t50.asof)}${t50.frozen?'＝資料截止日，結果近乎確定':`，距資料截止 ${md(t50.cutoff)} 還有 ${t50.n_days} 個交易日`}）</span></div>`:'';
  h+=sec('t-ev','事件','近期指數換股','被動 ETF 追蹤的指數定期換股，生效日被動資金集中買賣',
    (evs.length?`<div class=evs>${evs.map(e=>`<div class=ev><div class=cdn>${e.days}<small>天後</small></div><div class=evn>${esc(e.n)} <span class=mu style="font-weight:400">${esc(e.etf)}</span></div><div class=evm>${e.ann?`公告 ${md(e.ann)}・`:''}生效 ${md(e.eff)}${e.tr?`・分 ${e.tr} 日`:''}${e.stt==='推算'?'・日期推算':''}</div></div>`).join('')}</div>`:'<div class=st>尚無排定</div>')+tw50,
    `<a data-go="idx">看指數 →</a>`);
  const cnt={};ROWS.forEach(r=>(r.sg||[]).forEach(k=>cnt[k]=(cnt[k]||0)+1));
  h+=sec('t-sig','訊號','今日訊號','點一下看名單與歷史成績',
    `<div class=sgs>${Object.keys(SD).map(k=>`<a class="sgc${RISK.has(k)?' rk':''}${cnt[k]?'':' z'}" data-sg="${k}">${esc(SD[k][0])}<b>${cnt[k]||0}</b></a>`).join('')}</div>`,
    `<a data-go="sig">看訊號 →</a>`);
  $('#main').innerHTML=h;
  $$('#main [data-sg]').forEach(e=>e.onclick=()=>go('sig','sig-'+e.dataset.sg));
}

/* ---------- 個股（篩選表：三個視角） ---------- */
const VW={etf:'ETF 動向',chip:'法人籌碼',ta:'技術面'},VW0={etf:'a5v',chip:'t5',ta:'rs20'};
const MKF2={twall:'台股（上市＋上櫃）',tw:'上市',tp:'上櫃',os:'海外',all:'全部市場'};
let AMX=1;const HASBD=ROWS.some(r=>r.bigd!=null);
function dbar(v){if(v==null||!AMX)return '';const w=Math.min(50,Math.abs(v)/AMX*50);return `<span class=db><i class=${v>0?'bu':'bd'} style="width:${w.toFixed(1)}%"></i></span>`;}
function streak(x){return !x?'<span class=mu>—</span>':x>0?`<span class=up>買 ${x}</span>`:`<span class=dn>賣 ${-x}</span>`;}
function tcd(r){return r.tc&&r.px?(r.px/r.tc-1)*100:null;}
function trend(r){const b=r.h60?'創 60 日高':r.h20?'創 20 日高':r.l20?'破 20 日低':'';
  return (r.al?`<span class=${r.al==='多頭'?'up':r.al==='空頭'?'dn':'mu'}>${r.al}</span>`:'—')+(b?`<br><span class="sg${r.l20&&!r.h20&&!r.h60?' rk':''}">${b}</span>`:'');}
function sigScore(r){const s=r.sg||[];return s.filter(k=>!RISK.has(k)).length-2*s.filter(k=>RISK.has(k)).length;}
function sgShort(arr){const s=(arr||[]).slice().sort((a,b)=>RISK.has(b)-RISK.has(a));return s.slice(0,2).map(k=>`<span class="sg${RISK.has(k)?' rk':''}">${esc((SD[k]||[k])[0])}</span>`).join('')+(s.length>2?`<span class=mu> +${s.length-2}</span>`:'');}
const C0=[
 {k:'c',t:'股票',l:1,v:r=>r.c,h:r=>`<span class=nm>${esc(r.n)}</span><span class=cd>${esc(r.c)}${r.m==='tp'?' · 櫃':r.m==='os'?' · 海外':''}${r.ind?' · '+esc(r.ind):''}</span>`},
 {k:'ch',t:'收盤',v:r=>r.ch,h:r=>`${fp(r.px)}<br>${sgn(r.ch,2,'%')}`},
];
const CV={
 etf:[
  {k:'a5v',t:'主動 5 日淨買',u:'億',g:'主動 5 日淨買',v:r=>r.a5v,h:r=>r.a5v==null?'<span class=mu>—</span>':`${sgn(r.a5v,1)}${dbar(r.a5v)}`},
  {k:'iac',t:'加／減家數',g:'加碼／減碼家數',v:r=>(r.ia5||[]).length-(r.ic5||[]).length,h:r=>`<span class=up>${(r.ia5||[]).length}</span><span class=mu>／</span><span class=dn>${(r.ic5||[]).length}</span>`},
  {k:'ne',t:'持有 ETF',u:'檔',g:'持有 ETF',v:r=>r.ne,h:r=>`${r.ne}<br><span class=mu>主動 ${r.na}</span>`},
  {k:'dev',t:'成本乖離',g:'成本乖離',v:r=>r.dev,h:r=>sgn(r.dev,1,'%')},
  {k:'ow',t:'超配',u:'pp',g:'超配',v:r=>r.ow,h:r=>sgn(r.ow,2)},
  {k:'hp',t:'ETF 持股率',g:'ETF 持股率',v:r=>r.hp,h:r=>r.hp==null?'<span class=mu>—</span>':f(r.hp,2)+'%'},
  {k:'sg',t:'訊號',l:1,v:sigScore,h:r=>sgShort(r.sg)},
 ],
 chip:[
  {k:'t5',t:'投信 5 日',u:'張',g:'投信 5 日',v:r=>r.t5,h:r=>sgn(r.t5,0)},
  {k:'ts',t:'投信連續',u:'日',g:'連買',v:r=>r.ts,h:r=>streak(r.ts)},
  {k:'f5',t:'外資 5 日',u:'張',g:'外資 5 日',v:r=>r.f5,h:r=>sgn(r.f5,0)},
  {k:'fs',t:'外資連續',u:'日',g:'連買',v:r=>r.fs,h:r=>streak(r.fs)},
  {k:'tcd',t:'現價 vs 投信成本',g:'60 日買超均價',v:tcd,h:r=>sgn(tcd(r),1,'%')},
  {k:'mb5',t:'融資 5 日',g:'融資',v:r=>r.mb5,h:r=>sgn(r.mb5,1,'%')},
  {k:'big',t:'千張大戶',g:'千張大戶',v:r=>HASBD?r.bigd:r.big,h:r=>r.big==null?'<span class=mu>—</span>':`${f(r.big,1)}%${r.bigd!=null?`<br>${sgn(r.bigd,2,'pp')}`:''}`},
 ],
 ta:[
  {k:'al',t:'趨勢',l:1,g:'趨勢',v:r=>({多頭:2,整理:1,空頭:0}[r.al]??-1)+(r.h60?.2:r.h20?.1:0),h:trend},
  {k:'b20',t:'20 日乖離',g:'乖離',v:r=>r.b20,h:r=>sgn(r.b20,1,'%')},
  {k:'vr',t:'量比',u:'倍',g:'量比',v:r=>r.vr,h:r=>r.vr==null?'<span class=mu>—</span>':f(r.vr,2)},
  {k:'rsi',t:'RSI',g:'RSI',v:r=>r.rsi,h:r=>r.rsi==null?'<span class=mu>—</span>':`<span class=${r.rsi>=70?'up':r.rsi<=30?'dn':''}>${f(r.rsi,0)}</span>`},
  {k:'p52',t:'一年位置',g:'一年區間位置',v:r=>r.p52,h:r=>r.p52==null?'<span class=mu>—</span>':f(r.p52,0)+'%'},
  {k:'rs20',t:'20 日相對大盤',u:'pp',g:'相對大盤',v:r=>r.rs20,h:r=>sgn(r.rs20,1)},
  {k:'liq',t:'日均成交',u:'億',g:'日均成交',v:r=>r.liq,h:r=>r.liq==null?'<span class=mu>—</span>':f(r.liq,1)},
 ]};
function cols(){return [...C0,...CV[S.vw]];}
function rowsFiltered(){
  const q=S.q.trim().toLowerCase();
  let rs=ROWS.filter(r=>(S.mk==='all'||r.m===S.mk||(S.mk==='twall'&&r.m!=='os'))&&(!S.sig||(S.sig==='nb'?(r.nb10||[]).length>0:(r.sg||[]).includes(S.sig)))&&(!S.liq||(r.liq||0)>=1)
    &&(!q||r.c.toLowerCase().includes(q)||String(r.n).toLowerCase().includes(q)||String(r.ind||'').includes(q)));
  const col=cols().find(c=>c.k===S.sort)||cols().find(c=>c.k===VW0[S.vw]);
  rs.sort((a,b)=>{const x=col.v(a),y=col.v(b);if(x==null&&y==null)return 0;if(x==null)return 1;if(y==null)return -1;return (x<y?-1:x>y?1:0)*S.dir;});
  return rs;
}
function vStk(){
  if(!cols().some(c=>c.k===S.sort)){S.sort=VW0[S.vw];S.dir=-1;}
  const cnt={};ROWS.forEach(r=>(r.sg||[]).forEach(k=>cnt[k]=(cnt[k]||0)+1));
  const nbN=ROWS.filter(r=>(r.nb10||[]).length&&r.m!=='os').length;
  $('#main').innerHTML=`<div class=fbar><input type=search id=q placeholder="搜尋代號、名稱或產業" value="${esc(S.q)}">`+
   `<select id=mk aria-label="市場">${Object.entries(MKF2).map(([m,t])=>`<option value=${m}${S.mk===m?' selected':''}>${t}</option>`).join('')}</select>`+
   `<select id=sgf aria-label="訊號"><option value="">全部訊號</option>${Object.keys(SD).filter(k=>cnt[k]).map(k=>`<option value=${k}${S.sig===k?' selected':''}>${RISK.has(k)?'⚠ ':''}${esc(SD[k][0])}（${cnt[k]}）</option>`).join('')}<option value=nb${S.sig==='nb'?' selected':''}>10 日內新建倉（台股 ${nbN}）</option></select>`+
   `</div><div class=vbar><span class=seg>${Object.entries(VW).map(([k,t])=>`<a data-vw=${k} class="${S.vw===k?'on':''}">${t}</a>`).join('')}</span>`+
   `<label class=tgl title="20 日平均成交金額 ≥ 1 億元"><input type=checkbox id=liq${S.liq?' checked':''}>成交 ≥1 億</label><span class=cnt id=cnt></span></div><div id=stkt></div>`;
  $('#q').oninput=e=>{S.q=e.target.value;S.n=60;drawStk();};
  $('#mk').onchange=e=>{S.mk=e.target.value;S.n=60;save();drawStk();};
  $('#sgf').onchange=e=>{S.sig=e.target.value;S.n=60;drawStk();};
  $('#liq').onchange=e=>{S.liq=e.target.checked;S.n=60;save();drawStk();};
  $$('[data-vw]').forEach(a=>a.onclick=()=>{S.vw=a.dataset.vw;if(!cols().some(c=>c.k===S.sort)){S.sort=VW0[S.vw];S.dir=-1;}
    $$('[data-vw]').forEach(x=>x.classList.toggle('on',x===a));save();drawStk();});
  drawStk();
}
function drawStk(){
  const rs=rowsFiltered(),cs=cols();STK=rs.map(r=>r.c);
  AMX=Math.max(1,...rs.map(r=>Math.abs(r.a5v||0)));
  $('#cnt').textContent=`共 ${rs.length} 檔`;
  $('#stkt').innerHTML=(S.mk==='os'&&S.vw!=='etf'?'<div class=note>海外持股只有 ETF 面資料，法人籌碼與技術面無官方資料。</div>':'')+
   `<div class="tw stk"><table><thead><tr>`+cs.map(c=>`<th data-k=${c.k} class="${S.sort===c.k?'on':''}${c.l?' l':''}">${c.t}${c.u?`<small>${c.u}</small>`:''}${c.g?gi(c.g):''}${S.sort===c.k?(S.dir<0?' ↓':' ↑'):''}</th>`).join('')+`</tr></thead><tbody>`+
   (rs.slice(0,S.n).map(r=>`<tr data-c="${esc(r.c)}">`+cs.map(c=>`<td${c.l?' class=l':''}>${c.h(r)}</td>`).join('')+`</tr>`).join('')||`<tr><td colspan=${cs.length} class=l><span class=st>沒有符合條件的股票</span></td></tr>`)+`</tbody></table></div>`+
   (rs.length>S.n?`<button class=more id=more>再顯示 ${Math.min(60,rs.length-S.n)} 檔（剩 ${rs.length-S.n}）</button>`:'');
  $$('#stkt th[data-k]').forEach(e=>e.onclick=()=>{if(S.sort===e.dataset.k)S.dir*=-1;else{S.sort=e.dataset.k;S.dir=e.dataset.k==='c'?1:-1;}save();drawStk();});
  const m=$('#more');if(m)m.onclick=()=>{S.n+=60;drawStk();};
}

/* ---------- 訊號 ---------- */
function statLine(k){const st=(D.stats||{})[k];if(!st)return '<span class=st>尚無歷史樣本</span>';
  const a=st['5']||{},b=st['20']||{};if(!a.n)return '<span class=st>尚無歷史樣本</span>';
  return `<span class=st>${st.ok?'':'⚠ 樣本不足 · '}5 日：平均超額 ${sgn(a.x,2,'%')}、勝率 ${f(a.w,0)}%、隔夜跳空 ${sgn(a.g,2,'%')}（${a.n} 次）`+(b.n?` · 20 日：超額 ${sgn(b.x,2,'%')}、勝率 ${f(b.w,0)}%（${b.n} 次）`:'')+`</span>`;}
function readSig(st){const a=st['5']||{},b=st['20']||{};if(!a.n)return '<span class=mu>尚無樣本</span>';
  const p=[];p.push(`5 日${a.x<0?'輸':'贏'}大盤`);if(b.n)p.push(`20 日${b.x<0?'輸':'贏'}大盤`);
  return (st.ok?'':'<span class="tg">樣本不足</span>')+`<span class=${a.x<0&&(!b.n||b.x<0)?'mu':''}>${p.join('、')}</span>`;}
function vSig(){
  const ks=Object.keys(SD),cnt={};ROWS.forEach(r=>(r.sg||[]).forEach(k=>cnt[k]=(cnt[k]||0)+1));
  const neg=ks.filter(k=>(((D.stats||{})[k]||{})['5']||{}).x<0).length;
  let h=`<div class=intro>訊號＝系統每天收盤後自動標記的現象（例如 3 家以上投信同時加碼）。下表是它們在我們自己資料上的歷史成績：訊號隔日開盤進場、扣來回成本、和加權指數比。<b>${ks.length} 種訊號中有 ${neg} 種「隔日開盤跟進、持有 5 日」平均輸大盤</b>——它們是觀察線索、不是買點；加上條件的版本在「策略」頁驗證。</div>`;
  h+=sec('sig-all','總覽','訊號總覽',`樣本期 ${md((D.asof||{}).start)} 起・同一檔 5 日內重複只算一次`,
    `<div class=tw><table><thead><tr><th>訊號</th><th>今日</th><th>5 日平均超額${gi('超額')}</th><th>勝率${gi('勝率')}</th><th>隔夜跳空${gi('隔夜跳空')}</th><th>樣本${gi('樣本')}</th><th>20 日平均超額</th><th>勝率</th><th>樣本</th><th class=l>判讀</th></tr></thead><tbody>`+
    ks.map(k=>{const st=(D.stats||{})[k]||{};const x=st['5']||{},y=st['20']||{};
      return `<tr class="${st.ok?'':'grey'}"><td><a data-to="sig-${k}">${RISK.has(k)?'⚠ ':''}${esc(SD[k][0])}</a>${gi(k)}</td><td><b>${cnt[k]||0}</b></td><td>${sgn(x.x,2,'%')}</td><td>${x.n?f(x.w,0)+'%':'—'}</td><td>${sgn(x.g,2,'%')}</td><td>${x.n||0}</td><td>${sgn(y.x,2,'%')}</td><td>${y.n?f(y.w,0)+'%':'—'}</td><td>${y.n||0}</td><td class=l>${readSig(st)}</td></tr>`;}).join('')+
    `</tbody></table></div><div class=note>灰字＝樣本不足 30 次，不宜採信。</div>`);
  for(const k of ks){
    const risk=RISK.has(k);const rs=ROWS.filter(r=>(r.sg||[]).includes(k));
    rs.sort((a,b)=>risk?(a.a5||0)-(b.a5||0):(b.a5||0)-(a.a5||0));
    const row=r=>`<tr data-c="${esc(r.c)}"><td><span class=nm>${esc(r.n)}</span><span class=cd>${esc(r.c)}</span></td><td>${f(r.px,2)}<br>${sgn(r.ch,2,'%')}</td><td>${sgn(r.a5,0)} 張<br><span class=mu>${r.a5v==null?'':f(r.a5v,1)+' 億'}</span></td><td class="l wr">${(r.ia5||[]).length?`<span class=up>加</span> ${esc((r.ia5||[]).join('、'))}`:''}${(r.ic5||[]).length?`<br><span class=dn>減</span> ${esc((r.ic5||[]).join('、'))}`:''}</td><td>${sgn(r.dev,1,'%')}</td><td>${sgn(r.t5,0)}</td></tr>`;
    const head=`<thead><tr><th>股票</th><th>收盤</th><th>主動 5 日</th><th class=l>投信（5 日）</th><th>成本乖離</th><th>投信 5 日</th></tr></thead>`;
    h+=sec('sig-'+k,SD[k][0],`${risk?'⚠ ':''}${esc(SD[k][0])} <span class=pill>${rs.length} 檔</span>`,esc(SD[k][1]),
      `<div style="margin:-4px 0 8px">${statLine(k)}</div>`+(rs.length?`<div class=tw><table>${head}<tbody>${rs.slice(0,12).map(row).join('')}</tbody></table></div>`+
      (rs.length>12?`<details class=mr><summary>其餘 ${rs.length-12} 檔</summary><div class=tw><table>${head}<tbody>${rs.slice(12).map(row).join('')}</tbody></table></div></details>`:''):'<div class=st>今日無</div>'));
  }
  $('#main').innerHTML=h;
  $$('#main [data-to]').forEach(a=>a.onclick=()=>jump(a.dataset.to));
}

/* ---------- 投信 ---------- */
function vIss(){
  const iss={};for(const [c,m] of Object.entries(E)){(iss[m.is]=iss[m.is]||[]).push([c,m]);}
  const names=Object.keys(iss).filter(nm=>iss[nm].some(([c,m])=>m.k==='a')).sort((a,b)=>((D.iev||{})[b]||[]).length-((D.iev||{})[a]||[]).length);
  let h=`<div class=intro>各投信主動 ETF 近 5 個交易日的真加減碼${gi('真加碼')}（已扣申贖）、超配${gi('超配')}最多的個股，以及「新建倉後」的歷史表現。</div>`;
  const ist=Object.entries(D.iss||{}).sort((a,b)=>((b[1]['20']||{}).x??-99)-((a[1]['20']||{}).x??-99));
  h+=sec('iss-all','總覽','投信選股成績','主動 ETF 新建倉後的表現（對加權指數）',
    `<div class=tw><table><thead><tr><th>投信</th><th>新建倉次數</th><th>5 日超額${gi('超額')}</th><th>20 日超額</th><th>勝率${gi('勝率')}</th><th>樣本${gi('樣本')}</th><th>先買</th><th>跟進</th></tr></thead><tbody>`+
    ist.map(([nm,st])=>{const x=st['5']||{},y=st['20']||{};return `<tr class="${(y.n||0)>=30?'':'grey'}"><td><a data-to="iss-${esc(nm)}">${esc(nm)}</a></td><td>${st.new||0}</td><td>${sgn(x.x,2,'%')}</td><td>${sgn(y.x,2,'%')}</td><td>${y.n?f(y.w,0)+'%':'—'}</td><td>${y.n||0}</td><td>${st.lead||0}</td><td>${st.follow||0}</td></tr>`;}).join('')+
    `</tbody></table></div><div class=note>先買＝同一檔股票由這家投信最先建倉的次數；跟進＝別家先建倉、這家後來才買的次數。灰字＝20 日樣本不足 30 次。</div>`);
  for(const nm of names){
    const etfs=iss[nm];const ev=(D.iev||{})[nm]||[];const ow=(D.iow||{})[nm]||[];const st=(D.iss||{})[nm]||{};
    const s20=st['20']||{};
    let b=`<div class=st>${etfs.map(([c,m])=>c+(m.k==='p'?'（被動）':'')).join(' ')} · 新建倉後 20 日：${s20.n?`平均超額 ${sgn(s20.x,2,'%')}、勝率 ${f(s20.w,0)}%（${s20.n} 次）`:'樣本不足'}</div>`;
    if(ev.length)b+=`<div class=tw><table><tbody>`+ev.slice(0,15).map(e=>`<tr data-c="${esc(e[2])}"><td><span class=nm>${esc(e[3])}</span><span class=cd>${esc(e[2])} · ${esc(e[4])}</span></td><td class="k-${e[1]}">${KN[e[1]]}</td><td>${sgn(e[5],1)} 張</td><td class=mu>${md(e[0])}</td></tr>`).join('')+`</tbody></table></div>`;
    else b+='<div class=st>近 5 日無主動真加減碼</div>';
    if(ow.length)b+=`<div class=st style="margin-top:6px">超配最多：`+ow.map(o=>`<a data-c="${esc(o[0])}">${esc(o[1])}</a> ${sgn(o[4],2)}pp`).join('、')+`</div>`;
    h+=sec('iss-'+nm,nm,esc(nm),'',`<div class=card>${b}</div>`);
  }
  $('#main').innerHTML=h;
  $$('#main [data-to]').forEach(a=>a.onclick=()=>jump(a.dataset.to));
}

/* ---------- 指數調整 ---------- */
function nmOf(c){const r=BY[c];return r?r.n:(((D.idx||{}).names||{})[c]||c);}
function idxTbl(title,rows,side){
  if(!rows||!rows.length)return `<div class=st style="margin:6px 0">${esc(title)}：無</div>`;
  return `<h4 style="margin:12px 0 4px">${esc(title)}</h4><div class=tw><table><thead><tr><th>代號／名稱</th><th>市值排名</th><th>市值(億)</th><th>${side==='add'?'距第 40 名':'距跌出 60 名'}</th><th>機率</th><th>被動${side==='add'?'買進':'賣出'}(張)</th><th>約幾日量</th><th>收盤</th></tr></thead><tbody>`+
   rows.map(r=>`<tr data-c="${esc(r[0])}"><td><span class=nm>${esc(r[1])}</span><span class=cd>${esc(r[0])}</span></td><td>${r[2]??'—'}</td><td>${f(r[3],0)}</td><td>${r[4]==null?'—':(r[4]===0?'已跨線':sgn(r[4],1,'%'))}</td><td>${r[5]==null?'—':r[5]+'%'}</td><td>${sgn(r[6],0)}</td><td>${r[7]==null?'—':f(r[7],1)}</td><td>${f(r[8],2)}</td></tr>`).join('')+`</tbody></table></div>`;}
function vIdx(){
  const X=D.idx||{};
  let h=`<div class=intro>被動 ETF 追蹤的指數定期換股，生效日被動資金會集中買賣。<b>預測</b>只對規則可複製的指數做（目前：臺灣50）；其他指數先看每日持股揭露裡已經發生的換股。日期標「推算」者官方尚未公告。</div>`;
  if(X.err)h+=`<div class=st>指數區塊錯誤：${esc(X.err)}</div>`;
  h+=sec('idx-cal','時程','審核行事曆','',`<div class=tw><table><thead><tr><th>指數</th><th>ETF</th><th>資料截止</th><th>公告</th><th>生效／被動交易</th><th>過渡</th><th>狀態</th><th>預測</th></tr></thead><tbody>`+
   (X.cal||[]).map(r=>`<tr><td><span class=nm>${esc(r[1])}</span></td><td>${esc((r[2]||[]).join(' '))}</td><td>${md(r[4])}</td><td>${md(r[5])}</td><td>${md(r[6])}${r[10]!=null&&r[10]>=0?` <span class=pill>${r[10]} 天後</span>`:''}</td><td>${r[7]==null?'—':(r[7]?r[7]+' 日':'一次')}</td><td>${esc(r[8]||'')}</td><td>${r[12]?'信心 '+esc(r[9]||''):'<span class=mu>未預測（信心 '+esc(r[9]||'')+'）</span>'}</td></tr>`).join('')+`</tbody></table></div>`);
  const t=X.tw50||{};
  let b='';
  if(!t.ok)b+=`<div class=st>${esc(t.why||'尚無資料')}</div>`;
  else{
    b+=`<div class=note>排名基準 ${md(t.asof)}${t.frozen?'（＝資料截止日，指數公司用的就是這天，結果近乎確定）':`；距資料截止 ${md(t.cutoff)} 還有 ${t.n_days} 個交易日，機率依個股 60 日波動估計`}。被動部位：${Object.entries(t.eq||{}).map(([e,v])=>esc(e)+' '+f(v,0)+' 億').join('、')}。刪除股的賣出量＝兩檔 ETF 目前實際持股；納入股的買進量＝規模 × 預估權重（以現有成分股反推自由流通比例）。</div>`;
    b+=idxTbl('預估納入',t.adds,'add')+idxTbl('預估刪除',t.dels,'del')+idxTbl('邊緣觀察：可能升入前 40 名',t.watch_in,'add')+idxTbl('邊緣觀察：可能跌出 60 名',t.watch_out,'del');
    const rp=t.replay||[];
    if(rp.length){b+=`<h4 style="margin:14px 0 4px">回測：用當次資料截止日的價量重跑規則</h4><div class=tw><table><thead><tr><th>審核</th><th>資料日</th><th>實際納入</th><th>預測納入</th><th>命中</th><th>實際刪除</th><th>預測刪除</th><th>命中</th></tr></thead><tbody>`+
      rp.map(r=>`<tr><td>${esc(r.review)}</td><td>${md(r.data)}</td><td>${(r.act_add||[]).map(nmOf).map(esc).join('、')}</td><td>${r.pred_add?(r.pred_add.map(nmOf).map(esc).join('、')||'—'):'<span class=mu>資料不足</span>'}</td><td>${r.pred_add?`${r.hit_add}／${(r.act_add||[]).length}`:'—'}</td><td>${(r.act_del||[]).map(nmOf).map(esc).join('、')}</td><td>${r.pred_del?(r.pred_del.map(nmOf).map(esc).join('、')||'—'):'—'}</td><td>${r.pred_del?`${r.hit_del}／${(r.act_del||[]).length}`:'—'}</td></tr>`).join('')+`</tbody></table></div><div class=note>發行股數用最新值（股本變動會造成少量誤差）；臺灣50 實際依富時自由流通與流動性細則，邊界 ±2 名內可能不同。</div>`;}
  }
  h+=sec('idx-tw50','臺灣50','臺灣50（0050／006208）換股預測','',b);
  let o='';
  for(const r of (X.cal||[])){if(r[12])continue;const hi=(r[13]||[])[0];
    o+=`<div class=card><h4>${esc(r[1])} <span class=pill>${esc((r[2]||[]).join(' '))}</span> <span class=pill>信心 ${esc(r[9]||'')}</span></h4><div class=st>${esc(r[11]||'')}</div>`+
     (hi?`<div class=st style="margin-top:4px">上次（${esc(hi.review||'')}）納入：${esc((hi.adds_names||(hi.adds||[]).map(nmOf)).join('、')||'—')}；刪除：${esc((hi.dels_names||(hi.dels||[]).map(nmOf)).join('、')||'—')}</div>`:'')+
     `<div class=st style="margin-top:4px">公告前預測：${r[0]==='msci_esg30'?'ESG 評分為付費資料，不做；公告後看持股揭露追蹤提前建倉':r[0]==='tw_div'?'第三階段（以公開殖利率代理分析師預估，信心中低）':'第二階段（需股利、EPS 資料）'}</div></div>`;}
  if(o)h+=sec('idx-oth','其他指數','其他指數','',o);
  const pf=X.pflow||[];
  h+=sec('idx-pf','被動換股','被動 ETF 近 10 個交易日換股動作','所有被動 ETF（含規模前段擴充檔）已發生的新進、出清與真加減碼，依個股彙整；換股期間這裡會先反映',
    pf.length?`<div class=tw><table><thead><tr><th>代號／名稱</th><th>被動淨買賣(張)</th><th>約幾日量</th><th>新進</th><th>出清</th><th>涉及 ETF</th></tr></thead><tbody>`+pf.map(r=>`<tr data-c="${esc(r[0])}"><td><span class=nm>${esc(r[1])}</span><span class=cd>${esc(r[0])}</span></td><td>${sgn(r[2],0)}</td><td>${r[3]==null?'—':sgn(r[3],2)}</td><td>${esc((r[4]||[]).join(' '))}</td><td>${esc((r[5]||[]).join(' '))}</td><td class=mu>${esc((r[6]||[]).join(' '))}</td></tr>`).join('')+`</tbody></table></div>`:'<div class=st>近 10 日無被動換股動作</div>');
  $('#main').innerHTML=h;
}

/* ---------- 策略＋紙上交易 ---------- */
function stStat(g){return g&&g.n?`平均超額 ${sgn(g.x,2,'%')}、中位 ${sgn(g.xm,2,'%')}、勝率 ${f(g.w,0)}%（${g.n} 筆）`:'尚無已出場交易';}
function vSt(){
  const X=D.strat||{};const P=X.pass||[30,30];
  let h=`<div class=intro>規則寫死、從起算日之後的訊號才記入紙上交易${gi('紙上交易')}（起算日前只當樣本內參考${gi('樣本內')}，因為規則就是看那段資料挑的）。每天收盤後自動以「隔日開盤進場、到期或停損出場」記帳，扣來回成本 0.585%，超額對加權指數。驗證期滿（${P[0]} 筆或 ${P[1]} 個交易日，先到者）：平均超額＞0 且勝率＞50% 才算達標。</div>`;
  if(X.err)h+=`<div class=st>策略區塊錯誤：${esc(X.err)}</div>`;
  for(const s of (X.list||[])){
    const badge=s.status==='達標'?'<span class=pill style="background:#fdecea;color:#d33a34">達標</span>':s.status==='不達標'?'<span class=pill>不達標</span>':`<span class=pill style="background:rgba(37,99,201,.1);color:#1c4fa8">驗證中 ${s.event?`${s.days}／2 次審核`:`${(s.fwd_stats||{}).n||0}／${P[0]} 筆・${s.days}／${P[1]} 日`}</span>`;
    let b=`<ul class=doc style="margin:4px 0">${(s.rule||[]).map(x=>`<li class=st>${esc(x)}</li>`).join('')}</ul>`+
      `<div class=st><b>前瞻紙上交易：</b>${stStat(s.fwd_stats)}</div><div class=st>樣本內參考（起算日前、同規則）：${stStat(s.ins_stats)}</div>`;
    const cs=s.cands||[];
    b+=`<h4 style="margin:10px 0 4px">明日開盤前候選（${cs.length}）</h4>`+(cs.length?`<div class=tw><table><thead><tr><th>代號／名稱</th><th>訊號日</th><th>訊號日收盤</th><th>${s.cands[0].gap_max===0?'開盤低於此價才買':'進場'}</th><th>停損參考</th></tr></thead><tbody>`+
      cs.map(c=>`<tr data-c="${esc(c.c)}"><td><span class=nm>${esc(c.n)}</span><span class=cd>${esc(c.c)}</span></td><td>${md(c.d)}</td><td>${f(c.px,2)}</td><td>${c.gap_max===0?f(c.px,2):'開盤價'}</td><td>${c.stop==null?'—':f(c.stop,2)}</td></tr>`).join('')+`</tbody></table></div>`:'<div class=st>無</div>');
    const fw=(s.fwd||[]).slice().reverse();
    if(fw.length)b+=`<h4 style="margin:10px 0 4px">紙上交易紀錄</h4><div class=tw><table><thead><tr><th>代號／名稱</th><th>訊號日</th><th>狀態</th><th>跳空</th><th>進場</th><th>出場／現價</th><th>持有</th><th>報酬</th><th>超額</th></tr></thead><tbody>`+
      fw.map(t=>`<tr data-c="${esc(t.c)}" class="${t.st==='skip'?'grey':''}"><td><span class=nm>${esc(t.n)}</span><span class=cd>${esc(t.c)}</span></td><td>${md(t.d)}</td><td>${t.st==='skip'?'放棄：'+esc(t.why||''):t.st==='open'?'持有中':esc(t.why||'')}${t.review?` <span class=pill>${esc(t.review)}</span>`:''}</td><td>${t.gap==null?'—':sgn(t.gap,1,'%')}</td><td>${t.entry==null?'—':f(t.entry,2)}</td><td>${t.exit!=null?f(t.exit,2):t.now!=null?f(t.now,2):'—'}</td><td>${t.held==null?'—':t.held+' 日'}</td><td>${sgn(t.r,2,'%')}</td><td>${t.x==null?'—':sgn(t.x,2,'%')}</td></tr>`).join('')+`</tbody></table></div>`;
    h+=sec('st-'+s.key,s.name.split(/[（・(]/)[0],`${esc(s.name)} <span class=pill>v${s.ver}・${md(s.since)} 起</span> ${badge}`,'',`<div class=card>${b}</div>`);
  }
  h+=vGrow();
  const al=X.alerts||[];
  h+=sec('st-al','跳空提醒',`跳空減碼提醒 <span class=pill>${al.length}</span>`,'',`<div class=card><div class=st>前一交易日「共識加碼」、今日開盤跳空 ≥3% 的股票。樣本內（7/27～10/13，約 19 筆，大盤基準與進場同一時窗）：之後持有 1～10 日的每一個持有期平均超額都為負（−1.9%～−3.6%），是目前最穩定的結果之一。給已持有者參考，不做放空。</div>`+
    (al.length?`<div class=tw><table><tbody>`+al.map(a=>`<tr data-c="${esc(a.c)}"><td><span class=nm>${esc(a.n)}</span><span class=cd>${esc(a.c)}</span></td><td>${md(a.d)}</td><td>開盤 ${sgn(a.gap,1,'%')}</td></tr>`).join('')+`</tbody></table></div>`:'<div class=st>今日無</div>')+`</div>`);
  h+=sec('st-obs','換股觀察','換股期間觀察','',`<div class=card><h4>臺灣50 下次審核</h4><div class=st>12 月時程：資料截止 11/23、公告 12/4、生效 12/18 收盤（推算）。截止日後「指數」頁的預估就是用截止日排名（三次回測 19／20 命中），公告後即依官方名單執行「臺灣50 換股」策略。</div></div>`+
    `<div class=card><h4>0056／00919／00929 換股過渡期</h4><div class=st>12 月首次觀察：公告後被動資金分 5～8 個交易日買賣，「指數」頁的被動換股表會先反映。只考慮被動買盤 ≥1 日成交量的個股，先紙上觀察。</div></div>`);
  h+=`<div class=note>部位與風控（所有策略共用）：單筆虧損（停損距離×張數）≤ 總資金 0.5%、單筆 ≤ 5%；只做 20 日均成交值 ≥1 億、張數 ≤ 20 日均量 2%；同時 ≤8 檔、同產業 ≤3 檔；注意股／處置股不碰。持有少於 3 天時優勢容易被成本吃掉。</div>`;
  $('#main').innerHTML=h;
}

/* ---------- 長線：投信動能成長股 ---------- */
function gRow(lbl,g){if(!g||!g.n)return `<tr><td>${lbl}</td><td colspan=8 class=mu>無樣本</td></tr>`;
  const r=(x)=>x&&x[0]!=null?`${f(x[0],1)}%<span class=mu>（${x[1]}）</span>`:'—';
  return `<tr><td>${lbl}</td><td>${g.n}</td><td>${r(g.dbl6)}</td><td>${r(g.dbl12)}</td><td>${g.end6&&g.end6[0]!=null?sgn(g.end6[0],1,'%')+'／'+sgn(g.end6[1],1,'%'):'—'}</td><td>${g.rule?sgn(g.rule[0],1,'%')+'／'+sgn(g.rule[1],1,'%'):'—'}</td><td>${g.rule_w==null?'—':g.rule_w+'%'}</td><td>${g.rule_aw==null?'—':sgn(g.rule_aw,1,'%')+'／'+sgn(g.rule_al,1,'%')}</td><td>${g.rule_big==null?'—':f(g.rule_big,1)+'%'}</td></tr>`;}
function vGrow(){
  const G=D.grow||{};if(G.err)return sec('st-grow','長線','長線：投信動能成長股','',`<div class=card><div class=st>錯誤：${esc(G.err)}</div></div>`);
  const B=G.bt||{};const ms=B.months||[];
  let h=`<div class=card><h4>回測 <span class=pill>${ms.length} 個月${ms.length?`（${md(ms[0])}～${md(ms[ms.length-1])}）`:''}</span></h4>
<ul class=doc style="margin:4px 0">
<li class=st><b>投信關</b>：投信 20 日買超 ≥ 股本 0.5%，且 20 天中 ≥12 天買超（今日篩選另認：主動 ETF 20 日內 ≥2 家投信新建倉、且投信整體 20 日未淨賣）</li>
<li class=st><b>成長關</b>：最新月營收年增 ≥20%、累計年增 ≥15%</li>
<li class=st><b>動能關</b>：收盤 > 60 日線 > 120 日線、60 日線上揚、距 120 日高點 20% 內、比低點高 30% 以上、120 日報酬全市場前 30%</li>
<li class=st><b>空間關</b>：市值 50～1,500 億、20 日均成交值 ≥1 億</li>
<li class=st><b>照規則操作（上表「照規則」欄）</b>：原規則——隔日開盤進；停損 −10%；曾漲 30% 後停損拉到成本；之後收盤跌破 60 日線出場。下方出場比較顯示它太緊，S5 已改用「−20% 停損・高點回落 30%」</li></ul>
<div class=note>「曾翻倍」＝進場後 6／12 個月內最高價曾達進場價 2 倍（括號＝前瞻期完整的樣本數）；「照規則操作」＝真的照上面停損／移動出場做出來的報酬（已扣成本）。基準＝同期所有通過「空間關」的股票。宇宙只含現存上市櫃股，結果偏樂觀；兩年資料大致是多頭。</div>
<div class=tw><table><thead><tr><th>組別</th><th>篩出檔次</th><th>6 個月內曾翻倍</th><th>12 個月內曾翻倍</th><th>6 個月期末 平均／中位</th><th>照規則 平均／中位</th><th>勝率</th><th>平均賺／平均賠</th><th>照規則翻倍比例</th></tr></thead><tbody>`+
    gRow('基準（空間關）',B.base)+gRow('只看動能',B.mom)+gRow('只看投信',B.trust)+gRow('投信＋動能',B.trust_mom)+gRow('四關全過',B.all4)+`</tbody></table></div>`;
  const EX=B.exits||{},EL=B.exit_lbl||{};
  if(EX.trust_mom){h+=`<h4 style="margin:12px 0 4px">出場方式比較（同一檔 6 個月內只算一次、只計前瞻滿 6 個月者）</h4><div class=tw><table><thead><tr><th>出場方式</th><th>組別</th><th>筆數</th><th>平均</th><th>中位</th><th>勝率</th><th>平均賺／賠</th><th>翻倍比例</th><th>平均持有</th></tr></thead><tbody>`;
    for(const ek of Object.keys(EL)){for(const [gk,gl] of [['trust_mom','投信＋動能'],['mom','只看動能'],['base','基準']]){const x=(EX[gk]||{})[ek]||{};if(!x.n)continue;
      h+=`<tr class="${gk==='trust_mom'?'':'grey'}"><td>${gk==='trust_mom'?esc(EL[ek]):''}</td><td>${gl}</td><td>${x.n}</td><td>${sgn(x.avg,1,'%')}</td><td>${sgn(x.med,1,'%')}</td><td>${x.win}%</td><td>${x.aw==null?'—':sgn(x.aw,1,'%')}／${x.al==null?'—':sgn(x.al,1,'%')}</td><td>${f(x.dbl,1)}%</td><td>${x.days} 日</td></tr>`;}}
    h+=`</tbody></table></div>`;}
  if((B.top||[]).length)h+=`<div class=st style="margin-top:6px">歷史篩出、漲最多的：`+B.top.slice(0,8).map(x=>`${esc(x[1])}（${md(x[2])} 篩出，最高 +${x[3]}%${x[4]!=null?'，照規則 '+(x[4]>0?'+':'')+x[4]+'%':''}）`).join('、')+`</div>`;
  const S5=G.s5;
  if(S5){const st5=(g)=>g&&g.n?`平均 ${sgn(g.avg,1,'%')}、中位 ${sgn(g.med,1,'%')}、勝率 ${g.win}%、翻倍 ${f(g.dbl,1)}%、平均超額 ${sgn(g.x,1,'%')}（${g.n} 筆，持有中 ${g.open}）`:'尚無';
    h+=`<h4 style="margin:12px 0 4px">${esc(S5.name)} <span class=pill>v${S5.ver}・${md(S5.since)} 起</span> <span class=pill style="background:rgba(37,99,201,.1);color:#1c4fa8">驗證中</span></h4><ul class=doc style="margin:4px 0">${(S5.rule||[]).map(x=>`<li class=st>${esc(x)}</li>`).join('')}<li class=st>驗證：${esc(S5.pass)}</li></ul>`+
      `<div class=st><b>前瞻紙上交易：</b>${st5(S5.fwd_stats)}</div><div class=st>樣本內參考（同規則、2025-04 起）：${st5(S5.ins_stats)}。成績集中在趨勢明確的月份（2025/10～2026/2），盤整月份多為 −20% 停損——這是動能策略的常態，不是例外。</div>`;
    const rows=[...(S5.fwd||[]).map(x=>({...x,f:1})),...(S5.ins||[]).slice().reverse()];
    if(rows.length)h+=`<div class=tw><table><thead><tr><th>代號／名稱</th><th>篩選月</th><th>狀態</th><th>進場</th><th>出場／現價</th><th>持有</th><th>報酬</th><th>超額</th></tr></thead><tbody>`+
      rows.slice(0,40).map(t=>`<tr data-c="${esc(t.c)}" class="${t.f?'':'grey'}"><td><span class=nm>${esc(t.n)}</span><span class=cd>${esc(t.c)}${t.f?'':'・樣本內'}</span></td><td>${esc((t.d||'').slice(0,7))}</td><td>${t.st==='open'?'持有中':t.st==='skip'?'放棄：'+esc(t.why||''):t.st==='cand'?'待進場':esc(t.why||'')}</td><td>${t.entry==null?'—':f(t.entry,2)}</td><td>${t.exit!=null?f(t.exit,2):t.now!=null?f(t.now,2):'—'}</td><td>${t.held==null?'—':t.held+' 日'}</td><td>${sgn(t.r,1,'%')}</td><td>${t.x==null?'—':sgn(t.x,1,'%')}</td></tr>`).join('')+`</tbody></table></div>`;}
  const sc=G.screen||[];const ok=sc.filter(x=>x.pass);
  h+=`<h4 style="margin:12px 0 4px">今日篩選 <span class=pill>四關全過 ${ok.length}</span> <span class=pill>差一關 ${sc.length-ok.length}</span></h4><div class=note>月營收：${esc(G.rev_ym||'尚無')}；宇宙 ${G.n_uni||0} 檔。進場仍照短線研究的結論：不追開高 3% 以上，等突破隔日或回測 20 日線。</div>`;
  const ck=b=>b?'<span class=up>✓</span>':'<span class=mu>✗</span>';
  h+=sc.length?`<div class=tw><table><thead><tr><th>代號／名稱</th><th>投信</th><th>成長</th><th>動能</th><th>市值(億)</th><th>日均成交(億)</th></tr></thead><tbody>`+
    sc.map(x=>`<tr data-c="${esc(x.c)}" class="${x.pass?'':'grey'}"><td><span class=nm>${esc(x.n)}</span><span class=cd>${esc(x.c)}</span></td><td>${ck(x.g_trust)} ${x.trust==null?'':f(x.trust,2)+'%股本'}${x.tdays!=null?'・買 '+x.tdays+' 日':''}${x.etf2?' <span class=sg>主動ETF多家建倉</span>':''}</td><td>${ck(x.g_grow)} ${x.yoy==null?'':'年增 '+f(x.yoy,0)+'%'}${x.cyoy==null?'':'・累計 '+f(x.cyoy,0)+'%'}</td><td>${ck(x.g_mom)} ${x.rs==null?'':'強度前 '+(100-x.rs)+'%'}</td><td>${f(x.cap,0)}</td><td>${f(x.liq,1)}</td></tr>`).join('')+`</tbody></table></div>`:'<div class=st>今日無</div>';
  return sec('st-grow','長線','長線：投信動能成長股','',h+'</div>');
}

/* ---------- 個股卡 ---------- */
function kv(lbl,val,extra=''){return `<div><span>${lbl}</span><b>${val}</b>${extra?`<em>${extra}</em>`:''}</div>`;}
function openStock(c){if(location.hash!=='#s='+c)location.hash='s='+c;else renderStock(c);}
function lockBody(on){document.body.style.overflow=on?'hidden':'';}
function closeStock(){if(location.hash.startsWith('#s='))history.back();$('#dv').hidden=true;lockBody(!$('#gl').hidden);}
window.addEventListener('hashchange',()=>{const m=location.hash.match(/^#s=(.+)$/);if(m)renderStock(decodeURIComponent(m[1]));else{$('#dv').hidden=true;lockBody(!$('#gl').hidden);}});
document.addEventListener('keydown',e=>{if(e.key!=='Escape')return;if(!POP.hidden){hidePop();return;}if(!$('#dv').hidden)closeStock();else if(!$('#gl').hidden)closeGl();});
$('#dv').addEventListener('click',e=>{if(e.target.id==='dv')closeStock();});

function renderStock(c){
  const r=BY[c];if(!r)return;const s=(D.ser||{})[c]||{};const tw=r.m!=='os';const u=tw?'張':'股';
  let h=`<div class=dvh><b>${esc(r.n)}</b><span class=cd>${esc(r.c)} · ${MK[r.m]||''}${r.ind?' · '+esc(r.ind):''}</span><span class=px>${f(r.px,2)}</span>${sgn(r.ch,2,'%')}<a class=x id=x>×</a></div>`;
  h+=`<div style="margin:8px 0">${sgChips(r.sg)||'<span class=st>今日無觸發訊號</span>'}</div>`;
  h+=`<h3>ETF 面</h3><div class=kv>`+
   kv('持有 ETF',`${r.ne} 檔`,`主動 ${r.na}／被動 ${r.np} · ${r.ni} 家投信`)+
   kv('ETF 合計持股',`${f(r.sh,0)} ${u}`)+
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
   (r.hd||[]).slice().sort((a,b)=>(b[1]||0)-(a[1]||0)).map(x=>{const m=E[x[0]]||{};return `<tr><td><span class=nm>${esc(x[0])}</span><span class=cd>${esc(m.is||'')}${m.k==='p'?' · 被動':''}</span></td><td>${f(x[1],2)}%</td><td>${f(x[2],tw?1:0)}</td><td>${x[3]?(x[4]?'':'≤')+md(x[3]):'—'}</td><td>${x[5]==null?'—':x[5]+' 日'}</td><td>${x[6]==null?'—':f(x[6],2)}${x[12]==='B'?'<sup class=mu>B</sup>':''}</td><td>${sgn(x[7],1,'%')}</td><td>${sgn(x[8],tw?1:0)}</td><td>${x[9]?`<span class="k-${x[9]}">${KN[x[9]]}</span> <span class=mu>${md(x[10])}</span>${Math.abs(x[11])>=2?` <span class=pill>連${Math.abs(x[11])}</span>`:''}`:'—'}</td></tr>`;}).join('')+
   (r.ex||[]).map(x=>`<tr class=grey><td>${esc(x[0])}</td><td colspan=7>已出清 ${f(x[2],1)} ${u}</td><td>${md(x[1])}</td></tr>`).join('')+`</tbody></table></div>`;
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
  $('#dvin').innerHTML=h;$('#dv').hidden=false;lockBody(true);$('#dv').scrollTop=0;
  $('#x').onclick=closeStock;bindTip();
}
function idxCard(c){
  const t=(D.idx||{}).tw50||{};const hits=[];
  const lab={adds:'預估納入臺灣50',dels:'預估自臺灣50 刪除',watch_in:'臺灣50 邊緣（可能升入）',watch_out:'臺灣50 邊緣（可能跌出）'};
  for(const k of Object.keys(lab)){const r=(t[k]||[]).find(x=>x[0]===c);if(r)hits.push(kv(lab[k],`第 ${r[2]} 名`,`${r[4]===0?'已跨線':'還差 '+f(r[4],1)+'%'}${r[5]!=null?' · 機率 '+r[5]+'%':''}${r[6]!=null?' · 被動 '+(r[6]>0?'+':'')+f(r[6],0)+' 張（約 '+f(r[7],1)+' 日量）':''}`));}
  const pf=((D.idx||{}).pflow||[]).find(x=>x[0]===c);
  if(pf)hits.push(kv('被動 ETF 近 10 日淨買賣',sgn(pf[2],0)+' 張',`${pf[3]!=null?'約 '+f(pf[3],2)+' 日量 · ':''}${(pf[4]||[]).length?'新進 '+pf[4].join(' '):''}${(pf[5]||[]).length?' 出清 '+pf[5].join(' '):''}`));
  return hits.length?`<h3>指數調整</h3><div class=kv>${hits.join('')}</div>`:'';
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
function bindTip(){const kc=document.getElementById('kc');if(!kc)return;const svg=kc.querySelector('svg');
  let tip=kc.querySelector('.tip');if(!tip){tip=document.createElement('div');tip.className='tip';tip.hidden=true;kc.appendChild(tip);}
  const code=decodeURIComponent((location.hash.match(/^#s=(.+)$/)||[])[1]||'');const s=(D.ser||{})[code]||{};const n=+svg.dataset.n,W=+svg.dataset.w;const ds=D.dates||[];
  const mv=e=>{const rc=svg.getBoundingClientRect();const px=((e.touches?e.touches[0].clientX:e.clientX)-rc.left)/rc.width*W;const i=Math.max(0,Math.min(n-1,Math.floor((px-4)/((W-8)/n))));
    if(s.c[i]==null){tip.hidden=true;return;}tip.hidden=false;
    tip.innerHTML=`${esc((ds[ds.length-n+i]||''))}　收 ${f(s.c[i],2)}${s.o?`　開 ${f(s.o[i],2)} 高 ${f(s.h[i],2)} 低 ${f(s.l[i],2)}`:''}${s.v?`　量 ${f(s.v[i],0)} 張`:''}${s.ac&&s.ac[i]?`　ETF 成本 ${f(s.ac[i],2)}`:''}`;
    const left=Math.min(rc.width-tip.offsetWidth-4,Math.max(0,(px/W)*rc.width+8));tip.style.left=left+'px';tip.style.top='4px';};
  svg.onmousemove=mv;svg.ontouchmove=mv;svg.onmouseleave=()=>tip.hidden=true;}

/* ---------- 名詞頁 ---------- */
function openGl(){
  const st=(D.asof||{}).start;
  let h=`<div class=dvh><b>名詞與方法</b><a class=x id=glx>×</a></div>`;
  for(const [g,ks] of GLG)h+=`<div class=glh>${esc(g)}</div><div class=gll>${ks.map(k=>`<div><b>${esc(k)}</b><span>${esc(GL[k])}</span></div>`).join('')}</div>`;
  h+=`<div class=glh>訊號</div><div class=gll>${Object.keys(SD).map(k=>`<div><b>${RISK.has(k)?'⚠ ':''}${esc(SD[k][0])}</b><span>${esc(SD[k][1])}</span></div>`).join('')}</div>`;
  h+=`<div class=glh>方法</div><ul class=doc>
<li>把追蹤中 ETF（被動 6 檔＋主動式＋規模前段擴充檔；債券型除外）持有的所有個股，逐檔建「ETF 部位帳本」，再疊上官方籌碼與技術面。</li>
<li><b>時點</b>：ETF 揭露日的持股＝當日收盤後部位（成交在當日）；任何訊號最早只能在次一交易日開盤進場，成績一律以此計算。</li>
<li><b>公司行動</b>：減資、股票股利、面額變更造成的股數跳動，若股價同步反向變動，視為公司行動、不當成交易。</li>
<li><b>法人成本</b>：投信／外資「60 日買超均價」＝近 60 日買超日的買超股數 × 當日均價加權。</li></ul>
<div class=glh>限制</div><ul class=doc>
<li>ETF 持股史自 ${md(st)} 起，樣本短、行情單一；成績會隨每日累積自動更新，樣本 &lt;30 的結果不宜採信。</li>
<li>主動 ETF 持股每日公開，抄作業的人多時，效果可能已反映在隔夜跳空——成績把「隔夜跳空」與「進場後」分開列。</li>
<li>海外持股只有 ETF 面（無官方籌碼、技術面）；櫃買無借券與外資持股比欄位。</li>
<li>資料：ETF 持股＝etfinfo／復華官網；價量與籌碼＝證交所、櫃買中心、集保結算所公開資料。本頁為資料整理與統計，不構成任何投資建議。</li></ul>`;
  $('#glin').innerHTML=h;$('#gl').hidden=false;lockBody(true);$('#gl').scrollTop=0;$('#glx').onclick=closeGl;}
function closeGl(){$('#gl').hidden=true;lockBody(!$('#dv').hidden);}
$('#glb').onclick=e=>{e.preventDefault();openGl();};
$('#gl').addEventListener('click',e=>{if(e.target.id==='gl')closeGl();});

/* ---------- 分頁＋跳段目錄 ---------- */
const VIEWS={today:vToday,stk:vStk,iss:vIss,sig:vSig,st:vSt,idx:vIdx};
function hdh(){return $('.hd').offsetHeight;}
function jump(id){const t=document.getElementById(id);if(t)window.scrollTo({top:t.getBoundingClientRect().top+scrollY-hdh()-8,behavior:'smooth'});}
function buildNav(){const secs=$$('#main .sec[data-nav]');
  $('#snav').innerHTML=secs.length>1?secs.map(s=>`<a data-to="${s.id}">${esc(s.dataset.nav)}</a>`).join(''):'';
  $$('#snav a').forEach(a=>a.onclick=()=>jump(a.dataset.to));spy();}
let spyRaf=0;
function spy(){const secs=$$('#main .sec[data-nav]');const nav=$('#snav');if(secs.length<2)return;const y=hdh()+16;let cur=secs[0].id;
  for(const s of secs){if(s.getBoundingClientRect().top<=y)cur=s.id;else break;}
  if(innerHeight+scrollY>=document.documentElement.scrollHeight-4)cur=secs[secs.length-1].id;
  nav.querySelectorAll('a').forEach(a=>{const on=a.dataset.to===cur;if(on===a.classList.contains('on'))return;a.classList.toggle('on',on);
    if(on){const l=a.offsetLeft-nav.offsetLeft;if(l<nav.scrollLeft||l+a.offsetWidth>nav.scrollLeft+nav.clientWidth)nav.scrollLeft=Math.max(0,l-24);}});}
addEventListener('scroll',()=>{if(!spyRaf)spyRaf=requestAnimationFrame(()=>{spyRaf=0;spy();});},{passive:true});
function go(t,anchor){S.tab=t;$$('#tabs a[data-t]').forEach(a=>a.classList.toggle('on',a.dataset.t===t));VIEWS[t]();buildNav();
  $$('#main [data-go]').forEach(a=>a.onclick=e=>{e.preventDefault();const d=a.dataset;
    if(d.fsig!==undefined){S.sig=d.fsig;S.q='';S.n=60;}if(d.sort){S.vw='etf';S.sort=d.sort;S.dir=+(d.dir||-1);}go(d.go);});
  window.scrollTo(0,0);if(anchor)requestAnimationFrame(()=>jump(anchor));}
$$('#tabs a[data-t]').forEach(a=>a.onclick=()=>go(a.dataset.t));
go('today');
{const m=location.hash.match(/^#s=(.+)$/);if(m)renderStock(decodeURIComponent(m[1]));}
"""
