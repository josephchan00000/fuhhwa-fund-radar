"""盤前・選擇權分頁 x9op.html。不在頂欄，籌碼雷達各頁最底下右邊的「.」進來（appnav.OP_ENTRY）。

2026-11-12 起分四個分頁（使用者：「幫我把個股頁挪到選擇權頁的分頁裡面」；docs/lab_txo_plan.md 第 20 節）：
  盤前（#pm）＝盤前戰情（arm/lab/premkpage.py；docs/lab_premarket_plan.md）
  策略（#st）＝測過的四條選擇權策略（arm/lab/txostrat.py）
  計算機（#calc）＝風險／報酬計算機（docs/lab_txo_plan.md 第 17 節）
  個股（#stk）＝選股頁 x9.html 整頁放在框裡（點到才載入；框裡的選股頁收起自己的頂欄，見 appnav.EMBED_JS）
網址的 # 決定開哪一格（沒有或認不得＝盤前），舊連結 x9op.html#calc 照樣開到計算機。

作戰表資料 data/lab/txo_calc.json（arm/lab/txocalc.py，每晚 CI 寫）整份嵌進頁面；計算全部在瀏覽器裡（Black-Scholes、r＝0，
和 txocalc.bs 同一個公式）：使用者只要輸入成交價，口數、最多賠、占帳戶、損益兩平、情境表就重算。帳戶金額與手續費只存在使用者自己的瀏覽器。
只做買方；不是買賣建議。
"""
from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dashboard" / "x9op.html"
DATA = ROOT / "data" / "lab" / "txo_calc.json"
PM = ROOT / "data" / "lab" / "premkt.json"

CSS = (".opm{max-width:1000px;margin:0 auto;padding:12px 16px 80px}"
       ".opm h1{font-size:21px;margin:6px 0 4px}.opm h2{font-size:16.5px;margin:22px 0 8px}"
       ".oplead{color:var(--ink2);font-size:14px;line-height:1.65;margin:0 0 6px}"
       ".opfacts{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}"
       ".opfacts div{background:var(--card2);border-radius:10px;padding:8px 12px;min-width:120px}"
       ".opfacts b{display:block;font-size:17px;font-variant-numeric:tabular-nums}.opfacts span{font-size:12px;color:var(--mut)}"
       ".opform{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin:8px 0}"
       ".opform label{display:flex;flex-direction:column;gap:3px;font-size:12.5px;color:var(--mut)}"
       ".opform input,.opform select{font:inherit;font-size:16px;padding:7px 9px;border:1px solid var(--line2);border-radius:8px;"
       "background:var(--bg);color:var(--ink);min-width:0}"
       ".opseg{display:flex;gap:4px}.opseg button{flex:1;font:inherit;font-size:15px;padding:7px 0;border:1px solid var(--line2);"
       "border-radius:8px;background:var(--bg);color:var(--ink2);cursor:pointer}"
       ".opseg button.on{background:var(--acc);border-color:var(--acc);color:#fff;font-weight:600}"
       ".opres{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px;margin:12px 0}"
       ".opres div{border:1px solid var(--line);border-radius:10px;padding:9px 12px}"
       ".opres b{display:block;font-size:19px;font-variant-numeric:tabular-nums}.opres span{font-size:12px;color:var(--mut)}"
       ".opres .opbad{border-color:var(--c4);background:var(--sbg)}"
       ".optw{overflow-x:auto}.opt{border-collapse:collapse;font-size:13.5px;font-variant-numeric:tabular-nums;min-width:100%}"
       ".opt th,.opt td{padding:6px 8px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}"
       ".opt th{color:var(--mut);font-weight:600;font-size:12.5px}.opt td:first-child,.opt th:first-child{text-align:left}"
       ".opt .opup{color:var(--t0)}.opt .opdn{color:var(--t4)}.opt .oploss{background:var(--zh)}"
       ".opt tr.opatm td{font-weight:700}.opt tr.oppick td{background:var(--accbg)}.opt tbody tr[data-k]{cursor:pointer}"
       ".opstale{margin:10px 0;padding:8px 12px;border-radius:8px;border-left:4px solid var(--c4);background:var(--sbg);font-size:14px}"
       ".opnote{font-size:12.5px;color:var(--mut);line-height:1.6;margin:6px 0}"
       ".opexp{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0}.opexp button{font:inherit;font-size:13px;padding:4px 10px;"
       "border:1px solid var(--line2);border-radius:999px;background:var(--bg);color:var(--ink2);cursor:pointer}"
       ".opexp button.on{border-color:var(--acc);color:var(--acc);font-weight:600}"
       # 分頁（2026-11-12）
       ".optab{display:flex;gap:2px;max-width:1000px;margin:6px auto 0;padding:0 16px;overflow-x:auto;scrollbar-width:none}"
       ".optab::-webkit-scrollbar{display:none}"
       ".optab a{flex:1 0 auto;text-align:center;padding:8px 16px;border-radius:10px 10px 0 0;font-size:15px;font-weight:600;"
       "color:var(--ink2);text-decoration:none;border-bottom:3px solid transparent;white-space:nowrap}"
       ".optab a:hover{color:var(--ink)}.optab a.on{color:var(--ink);border-bottom-color:var(--acc);background:var(--card2)}"
       ".optab a:focus-visible{outline:2px solid var(--acc);outline-offset:-2px}"
       ".optabline{max-width:1000px;margin:0 auto;border-bottom:1px solid var(--line)}"
       ".oppane[hidden]{display:none}"
       ".opstk iframe{display:block;width:100%;border:0;min-height:60vh;background:var(--bg)}"
       "body.stkon{overflow:hidden}body.stkon .opm{display:none}body.stkon .top .applk{visibility:hidden}"   # 框裡的選股頁自己有那一排
       "@media (max-width:640px){.optab{padding:0 8px}.optab a{padding:8px 10px;font-size:14.5px}}")

JS = r"""
(function () {
  const D = JSON.parse(document.getElementById('opd').textContent || 'null');
  const box = document.getElementById('opapp');
  if (!D || !D.exps || !D.exps.length) { box.innerHTML = '<p class="oplead">作戰表還沒準備好：每個交易日晚上自動更新。</p>'; return; }
  const today = new Date(Date.now() + 8 * 3600e3).toISOString().slice(0, 10);   // 台北日期
  const stale = today > D.next;
  const KEY = 'txoCalc';
  let st = {acct: 1000000, fee: D.fee, cap: 'O1'};
  try { Object.assign(st, JSON.parse(localStorage.getItem(KEY) || '{}')); } catch (e) {}
  const save = () => { try { localStorage.setItem(KEY, JSON.stringify({acct: st.acct, fee: st.fee, cap: st.cap})); } catch (e) {} };
  const nf = (x, d = 0) => x == null || !isFinite(x) ? '—' : x.toLocaleString('zh-TW', {minimumFractionDigits: d, maximumFractionDigits: d});
  const sgn = x => (x > 0 ? '+' : x < 0 ? '−' : '') + nf(Math.abs(x));
  const ncdf = x => { const t = 1 / (1 + 0.2316419 * Math.abs(x)), y = Math.exp(-x * x / 2) / Math.sqrt(2 * Math.PI);
    const p = y * t * (0.31938153 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))));
    return x >= 0 ? 1 - p : p; };
  const bs = (cp, s, k, t, v) => { const iv = cp === 'C' ? Math.max(0, s - k) : Math.max(0, k - s);
    if (t <= 0 || !(v > 0)) return iv; const sd = v * Math.sqrt(t), d1 = (Math.log(s / k) + sd * sd / 2) / sd, d2 = d1 - sd;
    return cp === 'C' ? s * ncdf(d1) - k * ncdf(d2) : k * ncdf(-d2) - s * ncdf(-d1); };
  const tick = p => p < 10 ? 0.1 : p < 50 ? 0.5 : p < 500 ? 1 : p < 1000 ? 5 : 10;
  const side = p => st.fee + D.tax * p * D.mult + D.slip * tick(p) * D.mult;
  let ei = Math.max(0, D.exps.findIndex(e => e.tomorrow)); if (D.exps[ei] && !D.exps[ei].tomorrow) ei = 0;
  let cp = 'P', k = D.atm, prem = null, lots = null;
  const E = () => D.exps[ei];
  const row = () => E().rows.find(r => r[0] === k) || E().rows[Math.floor(E().rows.length / 2)];
  const volOf = r => (cp === 'C' ? r[2] : r[4]) || D.atm_iv || 0.25;
  const settle = r => cp === 'C' ? r[1] : r[3];
  const h = s => s.replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const md = d => +d.slice(5, 7) + '/' + +d.slice(8, 10);
  const CAPN = {O1: '每筆 2%', O2: '每筆 3%', O3: '每筆 5%'};
  function render() {
    const e = E(), r = row(); k = r[0];
    if (prem == null) prem = settle(r) || 0;
    const cap = D.caps[st.cap], one = prem * D.mult + 2 * side(prem), maxLots = one > 0 ? Math.floor(st.acct * cap / one) : 0;
    if (lots == null) lots = Math.max(1, maxLots);
    const risk = lots * one, pct = st.acct > 0 ? risk / st.acct : 0;
    const be = cp === 'C' ? k + prem : k - prem, v = volOf(r);
    const half = lots * ((prem / 2) * D.mult + side(prem) + side(prem / 2));      // 買進一邊＋停損賣出一邊
    const em = D.em || 0, cl = D.close;
    const moves = [[-3, cl * -0.03], [-2, cl * -0.02], [-1, cl * -0.01], ['正常下緣', -em], [0, 0], ['正常上緣', em], [1, cl * 0.01], [2, cl * 0.02], [3, cl * 0.03]];
    const n = e.n;                                         // 從作戰表那天到到期的交易日數（下一個交易日算第 1 天）
    const times = [['10:00', 75], ['11:30', 165], ['13:00', 255], ['到期結算', null]];
    const basis = (e.f || cl) - cl;                       // 選擇權隱含的指數水準比收盤高（低）多少；越接近到期越收斂到 0
    const cell = (s, mins) => { const t = mins == null ? 0 : Math.max(0, n - mins / 300) / 252;
      const val = bs(cp, s + basis * (t * 252 / n), k, t, v); const pl = lots * (val - prem) * D.mult - 2 * lots * side(prem);
      const x = prem > 0 ? val / prem : 0;
      return '<td class="' + (pl < 0 ? 'opdn oploss' : 'opup') + '">' + sgn(pl) + '<br><small>' + nf(x, 1) + ' 倍</small></td>'; };
    let tb = '';
    for (const [lab, dm] of moves) {
      const s = cl + dm, l = typeof lab === 'number' ? (lab === 0 ? '不動' : (lab > 0 ? '+' : '−') + Math.abs(lab) + '%') : lab;
      tb += '<tr><td>' + l + '<br><small>' + nf(s) + '</small></td>' + times.map(([, m]) => cell(s, m)).join('') + '</tr>';
    }
    const chain = e.rows.map(x => '<tr data-k="' + x[0] + '" class="' + (x[0] === D.atm ? 'opatm ' : '') + (x[0] === k ? 'oppick' : '') + '">' +
      '<td>' + nf(x[0]) + '</td><td>' + nf(x[1], x[1] < 10 ? 1 : 0) + '</td><td>' + (x[2] ? nf(x[2] * 100, 0) + '%' : '—') + '</td>' +
      '<td>' + nf(x[3], x[3] < 10 ? 1 : 0) + '</td><td>' + (x[4] ? nf(x[4] * 100, 0) + '%' : '—') + '</td><td>' + nf(x[5]) + '／' + nf(x[6]) + '</td></tr>').join('');
    box.innerHTML = (stale ? '<p class="opstale">作戰表停在 ' + md(D.asof) + ' 收盤，還沒更新到今天：下面的價格與波動只能參考，成交價一定要改成券商現在的價格。</p>' : '') +
      '<h2>1. 你的帳戶</h2><div class="opform">' +
      '<label>選擇權帳戶（元）<input id="acct" inputmode="numeric" value="' + st.acct + '"></label>' +
      '<label>每口每邊手續費<select id="fee"><option' + (st.fee == 25 ? ' selected' : '') + '>25</option><option' + (st.fee == 50 ? ' selected' : '') + '>50</option></select></label>' +
      '<label>每筆上限<select id="cap">' + Object.keys(D.caps).map(c => '<option value="' + c + '"' + (c === st.cap ? ' selected' : '') + '>' + CAPN[c] + '</option>').join('') + '</select></label></div>' +
      '<h2>2. 要買哪一口</h2><div class="opexp">' + D.exps.map((x, i) => '<button data-e="' + i + '" class="' + (i === ei ? 'on' : '') + '">' + md(x.date) + ' 到期' + (x.tomorrow ? '（明天）' : '') + '</button>').join('') + '</div>' +
      '<div class="opform"><div><div class="opseg"><button data-cp="C" class="' + (cp === 'C' ? 'on' : '') + '">買權（看漲）</button><button data-cp="P" class="' + (cp === 'P' ? 'on' : '') + '">賣權（看跌）</button></div></div>' +
      '<label>履約價<select id="k">' + e.rows.map(x => '<option' + (x[0] === k ? ' selected' : '') + '>' + x[0] + '</option>').join('') + '</select></label>' +
      '<label>成交價（點）<input id="prem" inputmode="decimal" value="' + prem + '"></label>' +
      '<label>口數（上限內最多 ' + maxLots + '）<input id="lots" inputmode="numeric" value="' + lots + '"></label></div>' +
      '<p class="opnote">成交價先帶入 ' + md(D.asof) + ' 結算價 ' + nf(settle(r), 1) + ' 點；盤中請改成券商看到的價格。</p>' +
      '<div class="opres">' +
      '<div class="' + (pct > cap ? 'opbad' : '') + '"><b>' + nf(risk) + ' 元</b><span>最多賠（權利金＋兩邊成本）</span></div>' +
      '<div class="' + (pct > cap ? 'opbad' : '') + '"><b>' + nf(pct * 100, 2) + '%</b><span>占帳戶（上限 ' + nf(cap * 100, 0) + '%）</span></div>' +
      '<div><b>' + nf(be) + '</b><span>到期損益兩平（指數）</span></div>' +
      '<div><b>' + nf(half) + ' 元</b><span>跌一半就停損時賠</span></div></div>' +
      '<h2>3. 情境：指數走到哪、什麼時候，這筆賺賠多少</h2>' +
      '<p class="opnote">「正常」＝依市場目前的預期波動，明天大約三分之二的機會落在 ±' + nf(em) + ' 點（' + nf(em / cl * 100, 1) + '%）以內。時間＝下一個交易日（' + md(D.next) + '）；到期結算＝指數停在那裡直到到期。已扣兩邊成本。</p>' +
      '<div class="optw"><table class="opt"><thead><tr><th>指數</th>' + times.map(([t]) => '<th>' + t + '</th>').join('') + '</tr></thead><tbody>' + tb + '</tbody></table></div>' +
      '<h2>4. 作戰表：' + md(e.date) + ' 到期（' + e.code + '）</h2>' +
      '<p class="opnote">' + md(D.asof) + ' 結算價與反推的波動率；點一列帶入計算機。粗體＝價平。</p>' +
      '<div class="optw"><table class="opt"><thead><tr><th>履約價</th><th>買權</th><th>波動</th><th>賣權</th><th>波動</th><th>未平倉 買／賣</th></tr></thead><tbody>' + chain + '</tbody></table></div>';
    const num = (id, f) => { const el = document.getElementById(id); el.addEventListener('change', () => { f(parseFloat(el.value.replace(/,/g, ''))); render(); }); };
    num('acct', x => { if (x > 0) { st.acct = x; lots = null; save(); } });
    num('prem', x => { if (x >= 0) { prem = x; lots = null; } });
    num('lots', x => { if (x >= 1) lots = Math.floor(x); });
    document.getElementById('fee').addEventListener('change', ev => { st.fee = +ev.target.value; lots = null; save(); render(); });
    document.getElementById('cap').addEventListener('change', ev => { st.cap = ev.target.value; lots = null; save(); render(); });
    document.getElementById('k').addEventListener('change', ev => { k = +ev.target.value; prem = null; lots = null; render(); });
    box.querySelectorAll('[data-cp]').forEach(b => b.addEventListener('click', () => { cp = b.dataset.cp; prem = null; lots = null; render(); }));
    box.querySelectorAll('[data-e]').forEach(b => b.addEventListener('click', () => { ei = +b.dataset.e; prem = null; lots = null; render(); }));
    box.querySelectorAll('tr[data-k]').forEach(t => t.addEventListener('click', () => { k = +t.dataset.k; prem = null; lots = null; render(); window.scrollTo({top: 0, behavior: 'smooth'}); }));
  }
  render();
})();
"""

_HTML = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<link rel="icon" href="data:,">
<title>盤前・選擇權</title>
<style>{{CSS}}</style></head>
<body>
<div class="top">{{APPTAB}}<a class="back" href="./"><span class="bk1">返回</span>主頁</a></div>
<nav class="optab" role="tablist" aria-label="盤前・選擇權分頁">{{TABS}}</nav><div class="optabline"></div>
<main class="opm">
<section class="oppane" id="pm" role="tabpanel">{{PM}}</section>
<section class="oppane" id="st" role="tabpanel" hidden>{{ST}}</section>
<section class="oppane" id="calc" role="tabpanel" hidden><h2>選擇權計算機</h2>
<p class="oplead">輸入成交價：最多賠多少、可買幾口、指數走到哪賺賠多少。只算「買方」：最多賠的就是付出去的權利金加成本。數字每天晚上自動更新，盤中只要改成交價。這裡只是計算，不是買賣建議。</p>
{{FACTS}}
<div id="opapp"></div></section>
</main>
<section class="oppane opstk" id="stk" role="tabpanel" hidden><iframe id="stkf" title="選股" data-src="x9.html"></iframe></section>
<script type="application/json" id="opd">{{DATA}}</script>
<script>{{JS}}</script>
<script>{{TABJS}}</script>
</body></html>
"""


TABS = (("pm", "盤前"), ("st", "策略"), ("calc", "計算機"), ("stk", "個股"))

# 分頁切換：網址的 # 決定開哪一格；個股＝第一次點到才載入 x9.html，框的高度＝視窗剩下的高度（框裡自己捲，選股頁的固定列、捲到個股卡都照原樣）
TAB_JS = r"""(function(){
var T=['pm','st','calc','stk'],tabs=document.querySelectorAll('.optab a'),f=document.getElementById('stkf');
function fit(){if(!f||document.getElementById('stk').hidden)return;var top=f.getBoundingClientRect().top;f.style.height=Math.max(320,window.innerHeight-Math.max(0,top))+'px'}
function show(k,push){if(T.indexOf(k)<0)k='pm';
 T.forEach(function(t){var p=document.getElementById(t);if(p)p.hidden=t!==k});
 for(var i=0;i<tabs.length;i++){var on=tabs[i].dataset.t===k;tabs[i].classList.toggle('on',on);tabs[i].setAttribute('aria-selected',on?'true':'false')}
 document.body.classList.toggle('stkon',k==='stk');
 if(k==='stk'&&f&&!f.getAttribute('src')){f.setAttribute('src',f.dataset.src)}
 if(push&&location.hash!=='#'+k){try{history.replaceState(null,'','#'+k)}catch(e){location.hash=k}}
 if(k==='stk'){window.scrollTo(0,0);fit()}}
for(var i=0;i<tabs.length;i++)tabs[i].addEventListener('click',function(e){e.preventDefault();show(this.dataset.t,true)});
window.addEventListener('hashchange',function(){show(location.hash.slice(1),false)});
window.addEventListener('resize',fit);
show(location.hash.slice(1),false);
})();"""


def _tabs() -> str:
    return "".join(f'<a href="#{k}" data-t="{k}" role="tab" aria-controls="{k}"' + (' class="on" aria-selected="true"' if k == "pm" else ' aria-selected="false"')
                   + f">{label}</a>" for k, label in TABS)


def _facts(d: dict | None) -> str:
    if not d:
        return ""
    def md(s):
        return f"{int(s[5:7])}/{int(s[8:10])}"
    em = d.get("em")
    pct = f"（{em / d['close'] * 100:.1f}%）" if em else ""
    items = [(f"{d['close']:,.0f}", f"{md(d['asof'])} 加權指數收盤"),
             (md(d["next"]), "下一個交易日"),
             (f"±{em:,.0f}{pct}" if em else "—", "明天的正常波動"),
             (f"{d['atm_iv'] * 100:.0f}%" if d.get("atm_iv") else "—", "市場預期年化波動")]
    tm = [e for e in d.get("exps", []) if e.get("tomorrow")]
    items.append(("是" if tm else "否", "明天是結算日"))
    return '<div class="opfacts">' + "".join(f"<div><b>{html.escape(a)}</b><span>{html.escape(b)}</span></div>" for a, b in items) + "</div>"


def render(data: dict | None = None, pm: dict | None = None) -> str:
    from . import appnav
    from . import premkpage
    from . import txostrat
    from .heatpage import _CSS as HCSS
    if data is None and DATA.exists():
        data = json.loads(DATA.read_text(encoding="utf-8"))
    if pm is None and PM.exists():
        pm = json.loads(PM.read_text(encoding="utf-8"))
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    page = (_HTML.replace("{{CSS}}", HCSS + appnav.CSS + CSS + premkpage.CSS + txostrat.CSS).replace("{{APPTAB}}", appnav.bar(""))
            .replace("{{TABS}}", _tabs()).replace("{{PM}}", premkpage.block(pm)).replace("{{ST}}", txostrat.block())
            .replace("{{FACTS}}", _facts(data)).replace("{{DATA}}", blob).replace("{{JS}}", JS).replace("{{TABJS}}", TAB_JS))
    return appnav.finish(page)


def build(out: Path = OUT, data: dict | None = None, pm: dict | None = None) -> bool:
    text = render(data, pm)
    if out.exists() and out.read_text(encoding="utf-8") == text:
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return True
