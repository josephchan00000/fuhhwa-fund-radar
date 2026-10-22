"""策略頁・總經策略的兩頁（docs/lab_strategy_ia_plan.md）：「這一期」「規則與成績」，比照個股策略的這一期（原機會頁）與規則與成績（原策略頁）。

2026-10-22 使用者：「你的策略頁面好亂，應該是策略點進去，分成總經策略跟個股策略，然後你的總經策略的排版設計要比照個股策略那邊的方式跟呈現邏輯」；
選了「先選市場」「兩頁跟個股一樣」。資料＝D.mac（xsadvice.build，page.build 內嵌），這裡只呈現。
JS 由 page.render 插在頁面初始化之前（同 stockviz、copage），沿用 page.py 的小工具（sec、sq、kp、tBadge、mdw、pctT、gi…）、
樣式（卡片、摘要、比較表）與時間軸（stockviz.tlDraw，設定 TLM）。三支 JS 串在同一個 <script>：名字不可和 page／stockviz／copage 重複
（tests/test_stockviz.py 檢查）；總經的函式一律 xm 開頭。只描述照規則做過去的成績，不寫建議。
"""
from __future__ import annotations

CSS = r"""
/* 策略頁：市場與兩頁的切換（macpage.py） */
.xmbar{display:flex;flex-wrap:wrap;align-items:center;gap:8px 14px;margin:0 0 18px}
.xmbar .seg a{cursor:pointer}
.xmmk a small{font-size:11px;font-weight:600;color:var(--acc);margin-left:5px}
.xmmk a.on small{color:var(--accd)}
.tabs a[hidden]{display:none}
/* 說明卡（規則與成績）：過去成績兩欄在手機縮得下（表格自己橫捲）；參數鄰近表；抱多久比較 */
.pst>div{min-width:0}
table.xmg td{text-align:left;white-space:nowrap}table.xmg td.xmmn{outline:2px solid var(--acc);outline-offset:-3px}
table.xmg .ck{margin-right:4px}table.xmg th{white-space:nowrap}
table.yrt.xmhs{max-width:440px}table.yrt tr.xmon td{font-weight:600}
table.yrt:not(.yall) tr.yo{display:none}table.yrt tr.yrx td{text-align:left;padding:5px 8px}table.yrt tr.yrx a{cursor:pointer;font-size:13px}
.xmtl{margin-top:6px}
.xmsrc{margin-top:6px}
/* 交易計畫（planspec；docs/lab_practical_plan.md 第 13 節）：防守、進攻兩欄 */
.xpli{color:var(--ink2);font-size:13.5px;margin:0 0 10px;line-height:1.7}
.xpl{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:0 0 6px}
.xplc{border:1px solid var(--line);border-radius:12px;padding:10px 14px 6px;min-width:0}
.xplh{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}.xplh b{font-size:15px}
.xplb{flex:none;font-size:11.5px;font-weight:700;color:var(--accd);background:var(--accbg);border-radius:10px;padding:1px 8px;white-space:nowrap}
.xplb.bad{color:var(--warn);background:var(--gbbg)}
.xplnow{font-size:14px;margin:6px 0 0}.xplnow b{font-size:24px;margin:0 2px}
.xplsub{color:var(--mut);font-size:12.5px;margin:0 0 4px}
.xplc .sq{grid-template-columns:5.4em minmax(0,1fr);font-size:13.5px;padding:8px 0}.xplc .sq .sqk{font-size:13px}
.xplf{color:var(--warn);font-weight:700;margin-top:3px}
.xplna{align-self:start}.xplna p{font-size:13px;margin:8px 0 6px;color:var(--ink2)}
.xplno{margin:0;font-size:14px;line-height:1.7}
.xplhow p{font-size:13.5px;margin:6px 0;line-height:1.75}
.xplm{margin:2px 0 4px}.xplm p{font-size:13px;margin:6px 0;line-height:1.7;color:var(--ink2)}
@media (max-width:760px){.xpl{grid-template-columns:1fr}}
@media (max-width:600px){.xplc .sq{grid-template-columns:1fr;gap:2px}.xplc{padding:9px 12px 5px}}
@media (max-width:600px){.xmbar{gap:8px}.xmmk{display:flex;flex-wrap:wrap;width:100%}.xmmk a{flex:1 1 auto;text-align:center;padding:5px 7px}
 .xmmk a small{display:block;margin:0;line-height:1.2}}
"""

JS = r"""
/* ---------- 總經策略（macpage.py；docs/lab_strategy_ia_plan.md）：先選市場；「這一期」「規則與成績」比照個股策略 ---------- */
const MAC=D.mac||{},MCM=MAC.m||{};
const XMS={rsi2:'RSI(2)',vixs:'VIX 衝刺',tom:'月底月初',coppock:'Coppock',vix40:'VIX 衝上 40',zweig:'Zweig',ftd:'跟進日',dev60:'季線乖離',
  mmr:'融資維持率',mflush:'融資去化',lowry:'Lowry 90%',hal:'Halloween',faber:'10 個月均線',ma200:'200 日均線',mom12:'12 個月動能'};
const XMI={tw:'加權指數',spx:'S&P 500',ixic:'那斯達克',ndx:'那斯達克 100',sox:'費半'};
const XMA={'買進':'b','賣出':'s','可能買進':'a'};
(function(){const R=MAC.rule||{};
  Object.assign(GL,{
  '推薦順序（總經）':'總經策略只排 ★ 好策略與 ● 可參考：★ 在前；同一級照類型（短線、落底、季節性、風險控制），同類型依比對照好多少（交易型、落底型看賺錢的比例多幾個百分點，進出型看最大回撤少多少）。',
  '判定（總經）':`照書上、論文裡的規則在指數上做一遍，看過去照做的成績（扣成本）。交易型（短線、月底月初）：至少 ${R.n} 筆、勝率 ≥ ${R.win}%、比隨便挑同樣天數高 ${R.edge} 個百分點以上、平均每筆賺錢。落底型：至少 ${R.dn} 次、抱完賺錢 ≥ ${R.dwin}% 而且不比隨便挑一天差，扣成本後的報酬中位數與排除極端（去掉最好和最差各 ${R.dtq}%）的平均都賺錢（2026-10-22 起看絕對成績）。進出型（風險控制、Halloween）：最大回撤比一直持有少 ${R.mdd}% 以上，而且年化 ÷ 最大回撤不輸一直持有。★ 好策略＝全期間、近 10 年、換附近的參數（${R.grid} 以上也過關）都過；● 可參考＝全期間過、後兩項沒過；○ 不推薦＝全期間沒過；— 次數不夠。`,
  '隱含獲利（總經）':'同一套規則過去照做的實際報酬（扣成本）：每筆（交易型）、每次（落底型，抱固定天數）、每段（進出型，一次持有到賣出）。對照＝隨便挑一天、抱一樣久（交易型、落底型），或一直持有（進出型）。價格是指數本身、不含股息。是歷史統計，不是預測。',
  '隨便挑一天':'每一個交易日都當成買進日、抱一樣多天，賺錢的比例（或報酬中位數）：不用這條規則、隨便買的成績。和它比，才看得出規則有沒有多賺。',
  '全部資金照做':'全部資金只照這條策略操作的年化報酬：有訊號才持有，其他時間放現金（不算利息）；買進持有＝同一段期間一直抱著指數（不含股息）。',
  '參數鄰近（總經）':'把規則裡的數字換成附近的值（例如 RSI 門檻 10 換成 5、15、20），每一組都照做一遍。★ 好策略要 2/3 以上的組合全期間也過關：換附近的數字成績差不多，才不是剛好挑到的參數。',
  });
  GLG.push(['總經策略',['推薦順序（總經）','判定（總經）','隱含獲利（總經）','隨便挑一天','全部資金照做','參數鄰近（總經）']]);})();
function xmM(){if(!MCM[S.mmk])S.mmk=(MAC.mks||[])[0]||'tw';return MCM[S.mmk]||null;}
function xmNm(k){return XMS[k]||k;}
function xmYmd(d){return d?`${d.slice(0,4)}/${+d.slice(5,7)}/${+d.slice(8,10)}`:'';}
function xmPc(x){return x==null?'—':f(x,0)+'%';}
function xmDw(d){const M=xmM()||{};return d&&M.d&&d.slice(0,4)!==M.d.slice(0,4)?xmYmd(d):mdw(d);}   // 不是今年的日期寫年份
/* 兩頁的切換（個股策略也用）：這一期｜規則與成績 */
function pgSeg(t,a,b){return `<div class="seg xmpg" role=group aria-label="這一期或規則與成績"><a data-go="${a}"${t===a?' class=on':''}>這一期</a><a data-go="${b}"${t===b?' class=on':''}>規則與成績</a></div>`;}
/* 頁首：市場（旁邊標要動作、持有中幾條）＋兩頁 */
function xmHead(t){const ch=(MAC.mks||[]).map(k=>{const s=(MCM[k]||{}).sum||{},n=s.act?`要動作 ${s.act}`:s.held?`持有 ${s.held}`:'';
    return `<a data-mmk="${esc(k)}"${k===S.mmk?' class=on':''}>${esc((MAC.mkn||{})[k]||k)}${n?`<small>${n}</small>`:''}</a>`;}).join('');
  return `<div class=xmbar><div class="seg xmmk" role=group aria-label="市場">${ch}</div>${pgSeg(t,'mac','macst')}</div>`;}
/* 摘要：推薦幾條、下一個交易日要動作幾條、持有中幾條、下一次排定 */
function xmSum(M){const s=M.sum||{},nxt=s.next;
  let k4;if(nxt)k4=kp('下一次排定','',md(nxt.d),`${esc(xmNm(nxt.k))}・收盤${esc(nxt.act)}`);
  else{const A=(M.cards||[]).map(c=>[((c.tl||{}).adj||[])[0],c]).filter(a=>a[0]).sort((a,b)=>a[0].d<b[0].d?-1:1),d=A.length?A[0][0].d:null;
    k4=kp('下一次排定','',d?md(d):'—',d?`月底看 ${A.filter(a=>a[0].d===d).length} 條`:'沒有排定的買賣');}
  return `<div class="kpis osum">`+kp('推薦策略','推薦順序（總經）',`${s.n||0} 條`,`★ 好策略 ${s.ng||0}、● 可參考 ${s.nr||0}`)+
    kp('下一個交易日','',`${s.act||0} 條要動作`,M.nx?`${mdw(M.nx)} 收盤`:'')+kp('持有中','',`${s.held||0} 條`,'照規則買進、還沒賣出')+k4+`</div>`;}
function xmNextDay(M){if(!M.nx)return '';const E=(M.cal||[]).filter(e=>e.d===M.nx);
  return `<div class=tlnx><div class=tlnd><b>${mdw(M.nx)}</b><span>下一個交易日要做的事</span></div><div class=tlna>`+
    (E.length?E.map(e=>`<div class=tlnr><span class="kact ka-${XMA[e.act]||'a'}">收盤${esc(e.act)}</span><a data-to="m-${esc(e.k)}">${esc(e.name)}</a></div>`).join('')
      :'<div class=tlnr><span class=mu>沒有照規則要買賣的</span></div>')+`</div></div>`;}
function xmCalTxt(M){const C=M.cal||[];return C.length?`<div class="klines otl">${C.map(e=>`<div class=kline><b>${mdw(e.d)} 收盤</b><span><span class="kact ka-${XMA[e.act]||'a'}">${esc(e.act)}</span> <a data-to="m-${esc(e.k)}">${esc(e.name)}</a></span><span class=mu></span></div>`).join('')}</div>`
  :'<div class=st>目前沒有排定的買賣。</div>';}
/* 時間軸（stockviz.tlDraw，同個股策略的畫法）：一條策略一列；持有中＝實心條（還沒有排定賣出日的畫到右邊、寫「依規則賣出」） */
const TLM={box:'xmtlbox',tip:'xmtltip',rk:'mtl',back:150,
  cards:()=>((xmM()||{}).cards||[]).map(c=>({k:c.k,rank:c.rank,tier:c.tier,name:c.name,gname:c.gname,held:(c.tl||{}).held||[],buy:(c.tl||{}).buy||[],next:(c.tl||{}).next||null,adj:(c.tl||{}).adj||[]})),
  last:()=>(xmM()||{}).d||'2026-01-01',dl:()=>(xmM()||{}).d,nx:()=>(xmM()||{}).nx,
  lb:x=>{const e=x.e,M=xmM()||{};if(x.k==='held')return `${e.ent&&M.d&&vzDay(M.d)-vzDay(e.ent)>TLM.back?xmYmd(e.ent)+' 起 ':''}${pctT(e.r)}`;return x.k==='buy'?`${md(e.d)} 買`+(e.out?`、${md(e.out)} 賣`:''):x.k==='next'?'可能買進':'';},
  nm:c=>`${c.rank}. ${xmNm(c.k)}`,sub:c=>`${TMK[c.tier]||''} ${TN[c.tier]||''}・${c.gname||''}`,avg:e=>e.r,tipf:(x,pin)=>xmTip(x,pin)};
function xmTip(x,pin){const c=x.c,e=x.e,M=xmM()||{},nm=esc(c.name),ix=esc(XMI[S.mmk]||'');let h='';
  if(x.k==='held')h=`<b>${nm}・持有中</b><div class=vzs>${e.ent?`${xmDw(e.ent)} 收盤買進`:''}${e.px0!=null?`（${ix} ${fp(e.px0)}）`:''}，到 ${md(M.d)} 收盤 <span class=${(e.r||0)>=0?'up':'dn'}>${pctT(e.r)}</span></div><div class=vzs>${e.d?`${mdw(e.d)} 收盤賣出`:esc(e.how||'')}</div>`;
  else if(x.k==='buy')h=`<b>${mdw(e.d)} 收盤買進・${nm}</b><div class=vzs>${e.out?`${mdw(e.out)} 收盤賣出`:esc(e.how||'')}</div>`;
  else if(x.k==='next')h=`<b>${nm}</b><div class=vzs>接近訊號：${mdw(e.d)} 收盤可能買進</div>`;
  else h=`<b>${mdw(e.d)}・${nm}</b><div class=vzs>${esc(e.note||'')}</div>`;
  return h+(pin?`<a class=vzgo data-to="m-${esc(c.k)}">看這條策略 →</a>`:'');}
function xmTlSec(){return `<div class=tlx><div class=tlhd><div class="seg tlrg"><a data-tlr=all${VZS.mtl==='m1'?'':' class=on'}>全部</a><a data-tlr=m1${VZS.mtl==='m1'?' class=on':''}>接下來 5 週</a></div>`+
  `<span class=tllg><span><span class="tlk b">▲</span>買進</span><span><span class="tlk s">▼</span>賣出</span><span><span class="tlk a">●</span>月底看</span>`+
  `<span class=tlsw><i class=tlsh></i>持有中（顏色＝目前漲跌）</span><span class=tlsw><i class=tlsb></i>排定的買進</span></span></div>`+
  `<div class=tlbox id=xmtlbox></div><div class=vztip id=xmtltip hidden></div></div>`;}
/* 排除極端、去掉最好一筆（xstratspec VER 6；e＝xsadvice.stats，和逐筆交易同一份）；去掉最好一筆剩不到平均的一半＝靠少數幾筆 */
function xmRob(e,d){if(e.trim==null)return '';const u=e.unit||'筆';
  return `排除極端${gi('排除極端')} ${pctT(e.trim,d)}、去掉最好一${u} ${pctT(e.lbo,d)}`+(e.avg>0&&e.lbo!=null&&e.lbo<e.avg/2?`（<b class=dn>靠少數幾${u}</b>）`:'')+'；';}
/* 卡片四行：做法／隱含獲利／現在／下一次（同個股策略的做法／隱含獲利／現在／下一批） */
function xmExp(c){const e=c.exp||{},span=`${ym(e.d0)}～${ym(e.d1)}`;
  if(c.kind==='alloc'){const sp=e.n?`每段平均 ${pctT(e.avg)}、${e.win}% 賺錢，最差一段 ${pctT(e.lo)}・`:'';
    return `全部資金照做年化 <b>${pctT(e.cagr)}</b>（買進持有 ${pctT(e.bcagr)}）${gi('全部資金照做')}，最大回撤 <b>${xmPc(e.mdd)}</b>（買進持有 ${xmPc(e.bmdd)}）`+
      `<div class=sm2>有部位的時間 ${xmPc(e.expo)}${e.sw!=null?`、一年進出約 ${f(e.sw,1)} 次`:''}；${sp}${span}，${e.n||0} 段</div>`;}
  if(!e.n)return `<span class=mu>評估期間（${span}）沒有${c.kind==='dip'?'出現過':'交易'}。</span>`;
  if(c.kind==='dip')return `每次平均 <b>${pctT(e.avg)}</b>、中位 <b>${pctT(e.med)}</b>，<b>${e.win}%</b> 賺錢（隨便挑一天抱一樣久${gi('隨便挑一天')} ${e.base}%、中位 ${pctT(e.bmed)}），最差一次 ${pctT(e.lo)}`+
    `<div class=sm2>${xmRob(e,1)}抱 ${esc(e.hn||'')}，中途最多跌中位 ${f(e.mae,1)}%；全部資金照做年化 ${pctT(e.cagr)}（買進持有 ${pctT(e.bcagr)}），有部位的時間 ${xmPc(e.expo)}・${span}，${e.n} 次</div>`;
  return `每筆平均 <b>${pctT(e.avg,2)}</b>、中位 <b>${pctT(e.med,2)}</b>，<b>${e.win}%</b> 賺錢（隨便挑同樣天數${gi('隨便挑一天')} ${e.base}%），最差一筆 ${pctT(e.lo)}`+
    `<div class=sm2>${xmRob(e,2)}平均抱 ${f(e.hold,1)} 天；全部資金照做年化 ${pctT(e.cagr)}（買進持有 ${pctT(e.bcagr)}），有部位的時間 ${xmPc(e.expo)}・${span}，${e.n} 筆</div>`;}
function xmNow(c){const T=c.tl||{},ix=XMI[S.mmk]||'';
  const ka=c.sk==='a'?((c.st==='sell'||c.st==='turn_out')?'s':c.st==='near'?'a':'b'):c.sk==='h'?'w':'a';
  let top=`<span class="kact ka-${ka}">${esc(c.tag)}</span>`;
  for(const e of T.held||[])top+=`${e.ent?`<b>${xmDw(e.ent)} 買進</b>`:''}${e.d?`<b>${mdw(e.d)} 收盤賣出</b>`:`<span class=kcap>${esc(e.how||'')}</span>`}`;
  for(const e of T.buy||[])top+=`<b>${mdw(e.d)} 收盤買進</b>${e.out?`<b>${mdw(e.out)} 收盤賣出</b>`:`<span class=kcap>${esc(e.how||'')}</span>`}`;
  if(T.next)top+=`<b>${mdw(T.next.d)} 收盤可能買進</b>`;
  let h=`<div class=onb><div class=onh>${top}</div>`;
  for(const e of T.held||[])if(e.px0!=null)h+=`<div class=kst><span class=kci>${esc(ix)} <span class=mu>${fp(e.px0)} → ${fp(e.px)}</span> ${sgn(e.r,1,'%')}</span></div>`;
  return h+`<div class=kln2>${esc(c.now)}</div></div>`;}
function xmNext(c){const T=c.tl||{};
  if((T.adj||[]).length)return `每個月最後一個交易日看，下一次 <b>${mdw(T.adj[0].d)}</b>`;
  if(c.k==='ma200')return '每天收盤後看';
  if(c.k==='tom'||c.k==='hal'||(T.held||[]).length||(T.buy||[]).length)return '';     // 日子已經寫在「現在」
  return '出現訊號才動作（每天收盤後看）';}
function xmCard(c){const nx=xmNext(c),rows=[['做法',esc(c.how)],[`隱含獲利${gi('隱含獲利（總經）')}`,xmExp(c)],['現在',xmNow(c)]];
  if(nx)rows.push(['下一次',nx]);
  return sec('m-'+c.k,xmNm(c.k),`<span class=orank>${c.rank}</span>${esc(c.name)} ${tBadge(c.tier)}`,`推薦順序 ${c.rank}：${esc(c.why)}`,
    `<div class="card stc">${rows.map(([a,b])=>sq(a,b)).join('')}<div class=vlk><a data-go="macst" data-at="ms-${esc(c.k)}">規則與過去成績 →</a></div></div>`);}
function xmBind(){$$('#main [data-to]').forEach(a=>a.onclick=e=>{e.preventDefault();jump(a.dataset.to);});
  $$('#main [data-yr]').forEach(a=>a.onclick=e=>{e.preventDefault();const t=a.closest('table');t.classList.toggle('yall');a.textContent=t.classList.contains('yall')?'收起較早的年份':a.dataset.lb;});}
/* ---------- 交易計畫（planspec VER 1；docs/lab_practical_plan.md 第 13 節）：上網頁條件過了的兩條寫成照著做的規則＋事先定好的前瞻檢查。
   數字全部由 plan.py 算（研究檔、前瞻紀錄、價格），這裡只排版；只描述照規則做的結果。 ---------- */
const XPN={wait:'累積中',ok:'和過去同樣行情差不多',bad:'比過去同樣行情差很多',good:'比過去同樣行情好很多',dd:'跌得比過去最慘的一次還深',fut:'期貨部位虧得比過去最多的一次還多'};
function xpP(x,d=1){return x==null?'—':pctT(x*100,d);}           // 比例 → +4.7%
function xpA(x,d=0){return x==null?'—':f(Math.abs(x)*100,d)+'%';}  // 比例 → 21%（不帶正負）
function xpW(m){return m==null?'—':f(m*100,0)+' 萬';}             // 100 萬的倍數 → 311 萬
function xpYr(Y){if(!Y||!Y.q)return '<span class=mu>—</span>';const q=Y.q,b=Y.bq;
  return `一半的時候在 <b>${xpP(q[1])}～${xpP(q[3])}</b>（中位 ${xpP(q[2])}）；最差的 5% 低於 ${xpP(q[0])}；賠錢的一年占 ${xpA(Y.loss)}`+
    `<div class=sm2>一直抱著：一半在 ${xpP(b[1])}～${xpP(b[3])}（中位 ${xpP(b[2])}）、最差的 5% 低於 ${xpP(b[0])}、賠錢占 ${xpA(Y.bloss)}。研究期間每一週起算的 ${f(Y.n,0)} 個一年。</div>`;}
function xpLive(L){if(!L||!L.a)return '<span class=mu>還沒開始記錄。</span>';
  const C=L.chk||[],nx=L.next?`${C.length?'下一次':'第一次'}檢查 ${xmYmd(L.next.d)}（滿 ${L.next.n} 個交易日）`:'';
  let h;
  if(!C.length)h=`${xmYmd(L.a)} 起照規則記錄，還在累積（不到 3 個月不寫成績）${nx?'；'+nx:''}。`;
  else{const c=C[C.length-1];
    h=`${xmYmd(L.a)} 起照做 <b>${xpP(L.ret)}</b>（一直抱著 ${xpP(L.bh)}），最大回撤 ${xpA(L.mdd,1)}。`;
    h+=c.st?`<div class=sm2>第 ${c.n} 個交易日（${md(c.d)}）檢查：<b class="${c.st==='bad'?'xplf':''}">${XPN[c.st]}</b>——過去一直抱著漲跌 ${xpP(c.nx[0])}～${xpP(c.nx[1])} 的 ${c.k} 段同樣長的期間，照做一半落在 ${xpP(c.nq[0])}～${xpP(c.nq[2])}；這次 ${xpP(c.y)}，排在 ${f(c.p*100,0)}%。${nx}</div>`
      :`<div class=sm2>第 ${c.n} 個交易日：過去同樣長的期間不夠，沒有比。${nx}</div>`;}
  for(const g of L.flags||[])h+=`<div class=xplf>⚠ ${XPN[g]}</div>`;
  return h;}
function xpBad(L){return !!L&&((L.flags||[]).length>0||((L.chk||[]).slice(-1)[0]||{}).st==='bad');}
function xpHead(nm,L){const b=xpBad(L);return `<div class=xplh><b>${esc(nm)}</b><span class="xplb${b?' bad':''}">${b?'偏離過去':'前瞻驗證中'}</span></div>`;}
function xpDef(X,nm){const n=X.now||{},p=X.past||{},bh=p.bh||{},A=n.acts||[],H=n.held||[];
  let nxt=!n.nx?'<span class=mu>—</span>':!A.length?`照規則沒有要動的，維持 ${xpA(n.w)}`
    :A.map(a=>`<span class="kact ka-${XMA[a.act]||'a'}">收盤${esc(a.act)}</span> ${esc(xmNm(a.k))}`).join('　')+(n.wn!=null?` → 合計 <b>${xpA(n.wn)}</b>`:'')
      +((n.maybe||[]).length?'<div class=sm2>「可能買進」要看那天收盤才知道，合計沒有算進去。</div>':'');
  const rows=[['下一個交易日',`${n.nx?mdw(n.nx)+' 收盤：':''}${nxt}`],
    ['過去',`${(p.a||'').slice(0,4)} 年起 100 萬變 <b>${xpW(p.man)}</b>（一直抱著 ${xpW(p.bman)}）；最慘時跌 <b>${xpA(p.mdd)}</b>（${xpA(bh.mdd)}）`],
    ['前瞻',xpLive(X.live)]];
  const more=`<p>年化 ${xpP(p.cagr)}（一直抱著 ${xpP(bh.cagr)}）；最差一年 ${xpP(p.worst,0)}（${xpP(bh.worst,0)}）。平均只拿 ${xpA(p.w)} 股票，多頭的年份賺得少很多；一年調整約 ${f(p.adj,0)} 次（多半一次只動一份）。</p>`+
    `<p><b>照做一年</b>：${xpYr(p.yr)}</p>`;
  return `<div class=xplc>${xpHead(nm,X.live)}<div class=xplnow>現在拿<b>${xpA(n.w)}</b>股票</div>`+
    `<div class=xplsub>今年選到的 ${n.n||0} 條裡 ${H.length} 條持有中${H.length?`（${H.map(k=>esc(xmNm(k))).join('、')}）`:''}，每條一份、平均分</div>`+
    rows.map(([a,b])=>sq(a,b)).join('')+`<details class="mr xplm"><summary>過去的細節與照做一年的範圍</summary>${more}</details></div>`;}
function xpAtk(X,nm){const n=X.now||{},p=X.past||{},bh=p.bh||{},fu=p.fut||{},ep=p.ep||{},cur=n.cur||'',L=n.lots||[];
  const gap=n.px&&n.ma?n.px/n.ma-1:null,fl=`<b>${fp(n.flip)}</b>`;
  const nxt=n.act==='加碼'?'照規則收盤<b>加碼</b>（用期貨多拿帳戶 5 成）':n.act==='平掉'?'照規則收盤<b>平掉加碼</b>'
    :n.on?`維持加碼；那天收盤若低於 ${fl}（那天的 200 日均線），再下一個交易日收盤平掉`:`維持不加碼；那天收盤若高於 ${fl}（那天的 200 日均線），再下一個交易日收盤加碼`;
  const money=v=>cur==='元'?`${f(v/1e4,v>=1e5?0:1)} 萬元`:`${f(v,0)} 美元`;
  let lots='';
  if(L.length&&n.cap)lots=`本金 ${money(n.cap)}時，加碼的名目約 ${money(n.cap*(n.add||0.5))}：`+
    L.map(([k,m,per,x,c,sh])=>c>0?`${esc(k)} 約 ${c} 口（一口 ${money(per)}，帳戶的 ${xpA(sh)}）`:`${esc(k)} 一口就 ${money(per)}`).join('；')+'。';
  if(fu.day!=null)lots+=`<div class=sm2>過去最差的一天，期貨部位虧掉帳戶的 <b>${xpA(fu.day,1)}</b>（${xmYmd(fu.dday)}）；交易所與期貨商要求放在期貨帳戶的金額另計。</div>`;
  const rows=[['下一個交易日',`${n.nx?mdw(n.nx)+' 收盤：':''}${nxt}`],['期貨',lots],
    ['過去',`${(p.a||'').slice(0,4)} 年起 100 萬變 <b>${xpW(p.man)}</b>（一直抱著 ${xpW(p.bman)}）；最慘時跌 <b>${xpA(p.mdd)}</b>（${xpA(bh.mdd)}）`],
    ['前瞻',xpLive(X.live)]];
  const more=`<p>年化 ${xpP(p.cagr)}（一直抱著 ${xpP(bh.cagr)}）；最差一年 ${xpP(p.worst,0)}（${xpP(bh.worst,0)}）。加碼的時間 ${xpA(p.share)}，一年開始加碼約 ${f(p.starts,1)} 次；每一段加碼只有 ${xpA(ep.win)} 賺錢（多數小賠出場、少數長多頭賺很多）。`+
    `每天固定多拿同樣多，100 萬也會變 ${xpW(p.fman)}：多賺的大部分來自多拿股票（訊號總覽・研究結論第 2 則）。</p>`+
    (fu.n?`<p><b>期貨帳戶</b>：過去 ${fu.n} 段加碼，賺的錢留在期貨帳戶的話，期貨部位比那一段開始時最多虧掉帳戶的 ${xpA(fu.worst,1)}（${xmYmd(fu.wa)}～${fu.wz?xmYmd(fu.wz):'還在加碼中'}）：加碼從剛站上 200 日均線開始、收盤跌破就平掉，開始和平倉多半都在均線附近，多數是小賠出場；虧最多的是急跌的單日（上面那一天，收盤跌破之後隔天才平得掉）。一口的名目＝指數 × 每點金額（${L.map(([k,m])=>`${esc(k)} ${m} ${esc(cur)}`).join('、')}），以 ${md(n.d)} 收盤計。</p>`:'')+
    `<p><b>照做一年</b>：${xpYr(p.yr)}</p>`;
  return `<div class=xplc>${xpHead(nm,X.live)}<div class=xplnow>現在<b>${n.on?'加碼中':'不加碼'}</b>${n.on?'（股票 100%＋期貨 50%）':'（只有股票 100%）'}</div>`+
    `<div class=xplsub>收盤 ${fp(n.px)}，比 200 日均線（${fp(n.ma)}）${(gap||0)>=0?'高':'低'} ${xpA(gap,1)}；${xmYmd(n.since)} 起在均線${n.up?'上':'下'}</div>`+
    rows.map(([a,b])=>sq(a,b)).join('')+`<details class="mr xplm"><summary>過去的細節、期貨帳戶與照做一年的範圍</summary>${more}</details></div>`;}
function xpHow(X,mk){const d=X.def,a=X.atk,n=(d||{}).now||{},P=MAC.plan||{};let h='';
  if(d)h+=`<p><b>${esc(P.plans.def)}</b>：每年 1 月 1 日只用之前的資料判定，★ 好策略與 ● 可參考的每一條分一份、平均分（今年 ${n.n||'—'} 條，每條約 ${n.n?xpA(1/n.n):'—'}）。每個交易日收盤後看，每一份照那條策略自己的規則買賣（多半是下一個交易日收盤${mk==='tw'?'；RSI(2)、月底月初用台指期在訊號當天收盤前下單':''}）；持有中的份數 ÷ 條數＝要拿幾成股票，其餘放現金。每一條的規則與現在的狀態在下面的策略卡。</p>`;
  if(a)h+=`<p><b>${esc(P.plans.atk)}</b>：股票一直抱著（本金 100%）。收盤在 200 日均線上，下一個交易日收盤用期貨加碼到帳戶的 5 成（名目）；收盤跌破，下一個交易日收盤平掉。`+
    `${mk==='tw'?'台指期每個月第三個星期三':'期貨每季（3、6、9、12 月第三個星期五）'}換月，換月的成本已算。研究用期貨的理論價（含息報酬減利率），實際價格會偏離${mk==='tw'?'（台指期在空頭時常比理論價便宜）':''}。</p>`;
  h+=`<p class=note>研究的成本：ETF 每一邊 ${mk==='tw'?'0.1%':'0.025%'}、期貨每一邊 0.005%。股票部分是指數本身（不含股息，現金沒有利息）。只描述照規則做過去的成績。</p>`;
  return `<details class="mr xplhow"><summary>照著做的說明（時點、工具、成本）</summary>${h}</details>`;}
function xpChk(){return `<details class="mr xplhow"><summary>上線後怎麼檢查（事先定好的）</summary>`+
  `<p>從上線那天起照規則記錄，滿 3、6、12、24、36 個月各檢查一次：這段期間一直抱著漲跌多少，就找過去一直抱著漲跌最接近的兩成同樣長的期間，看照做的成績排在哪裡——排在最差的 5% 以內＝<b>比過去同樣行情差很多</b>，最好的 5% 以內＝好很多。</p>`+
  `<p>另外每天看兩件事：照做的最大回撤有沒有比過去最慘的一次還深；進攻的期貨部位有沒有虧得比過去最多的一次還多。出現這些會標在這裡（「偏離過去」），不會自動停用，要不要停你決定。只檢查五次也可能碰巧差，所以一次「差很多」是警訊、不是結論。</p></details>`;}
function xpSec(){const P=MAC.plan||{},X=(P.mk||{})[S.mmk];if(!X)return '';
  const mk=S.mmk,nm=esc((MAC.mkn||{})[mk]||mk),pl=P.plans||{};
  if(!X.def&&!X.atk){const b=X.bh||{};
    return sec('m-plan','交易計畫',`${nm}・照著做：交易計畫`,'',`<div class=card><p class=xplno>${nm} 沒有比一直抱著穩定好的照做方法：總經策略全部照做、200 日均線上加碼，過去都和「每天固定拿一樣多」差不多（訊號總覽・研究結論第 1、2 則）。`+
      (b.cagr!=null?`一直抱著：${(b.a||'').slice(0,4)} 年起年化 ${xpP(b.cagr)}、最慘時跌 ${xpA(b.mdd)}、最差一年 ${xpP(b.worst,0)}。`:'')+`</p></div>`);}
  const cols=(X.def?xpDef(X.def,pl.def):'')+(X.atk?xpAtk(X.atk,pl.atk)
    :`<div class="xplc xplna"><div class=xplh><b>${esc(pl.atk)}</b></div><p>這個指數沒有對應的期貨，要加碼只能融資買 ETF（成本比期貨高），沒有放進交易計畫。</p></div>`);
  return sec('m-plan','交易計畫',`${nm}・照著做：交易計畫`,'前瞻驗證中',
    `<p class=xpli>過去驗證過、每年只用當時的資料決定的照做方式（各自事先定好上網頁的條件，過了才列）。防守少跌也少賺，進攻多賺也多跌。</p>`+
    `<div class=xpl>${cols}</div>`+xpHow(X,mk)+xpChk());}
function vMac(){const M=xmM();
  let h=`<div class=intro>大盤指數照書上、論文裡的固定規則買賣（總經策略）：先選市場，看照規則哪天買賣、現在持有什麼，以及同樣做法過去照做的實際報酬（扣成本）。只列 ★ 好策略、● 可參考${gi('判定（總經）')}，依推薦順序${gi('推薦順序（總經）')}；報酬是歷史統計，不是預測。</div>`+xmHead('mac');
  if(!M){$('#main').innerHTML=h+'<div class=st>總經策略的資料還沒產生。</div>';return;}
  h+=xpSec();
  h+=sec('m-sum','摘要',`${esc(M.name)}・這一期`,`${md(M.d)} 收盤後更新`,xmSum(M)+xmNextDay(M)+xmTlSec()+`<details class=mr><summary>時間表（文字）</summary>${xmCalTxt(M)}</details>`);
  h+=(M.cards||[]).map(xmCard).join('');
  const lo=(M.book||[]).filter(b=>b.rank==null);
  if(lo.length)h+=`<div class=note>判定沒過（○ 不推薦、— 次數不夠）的 ${lo.length} 條不列在這頁：${lo.map(b=>`<a data-go="macst" data-at="ms-${esc(b.k)}">${esc(b.name)}</a>`).join('、')}，在「規則與成績」列出（比較表灰字、說明卡在後面）。</div>`;
  $('#main').innerHTML=h;tlDraw(TLM);xmBind();}
/* 規則與成績：比較表（同個股策略的策略比較）＋判定方式 */
function xmBook(M){const B=M.book||[];
  const row=b=>{const e=b.exp||{},rec=b.rank!=null,u=e.unit,d=b.kind==='trade'?2:1;
    const per=e.n?`${pctT(e.avg,d)}<div class=sm2>中位 ${pctT(e.med,d)}</div>`:'<span class=mu>—</span>';
    const win=e.n?`${e.win}%<div class=sm2>${e.base!=null?`隨便挑 ${e.base}%`:`最差 ${pctT(e.lo)}`}</div>`:'<span class=mu>—</span>';
    return `<tr class="${rec?'':'grey'}" id="mb-${esc(b.k)}"><td class=l><a data-to="ms-${esc(b.k)}"><span class=nm>${rec?`<span class="orank sm">${b.rank}</span>`:''}${esc(b.name)}</span></a><span class=bkg>${tBadge(b.tier)}</span><span class=cd>${esc(b.why)}</span><span class=cd>${esc(b.gname)}・每${esc(u)}</span></td>`+
      `<td>${per}<div class="sm2 om">年化 ${pctT(e.cagr)}（買進持有 ${pctT(e.bcagr)}）</div></td><td>${win}</td>`+
      `<td class=hm>${pctT(e.cagr)}<div class=sm2>買進持有 ${pctT(e.bcagr)}</div></td><td class=hm>${xmPc(e.mdd)}<div class=sm2>買進持有 ${xmPc(e.bmdd)}</div></td>`+
      `<td class=hm>${ym(e.d0)}～${ym(e.d1)}<div class=sm2>${e.n||0} ${esc(u)}</div></td></tr>`;};
  return sec('mb-book','比較','策略比較',`${esc(M.name)}：★、● 依推薦順序；每筆（每次、每段）從買進到賣出、扣成本後的報酬`,
    `<div class=tw><table class=bkt><thead><tr><th class=l>推薦順序${gi('推薦順序（總經）')}・策略・判定${gi('判定（總經）')}</th><th>平均報酬${gi('隱含獲利（總經）')}</th><th>賺錢比例${gi('隨便挑一天')}</th><th class=hm>年化${gi('全部資金照做')}</th><th class=hm>最大回撤</th><th class=hm>資料期間</th></tr></thead><tbody>${B.map(row).join('')}</tbody></table></div>`+
    `<div class=note>平均報酬與賺錢比例：交易型、落底型是每一筆（每一次），旁邊是隨便挑一天抱一樣久的賺錢比例；進出型是每一段持有。年化＝全部資金照這條策略操作（沒有部位時放現金、不算利息）；買進持有＝同一段期間一直抱著指數。價格是指數本身、不含股息。</div>`);}
function xmMethod(){const R=MAC.rule||{};
  return sec('mb-mth','判定方式','判定方式','','<details class=mr><summary>★ 好策略、● 可參考怎麼判定</summary><div class=rls>'+ruleRows([
    `交易型：短線、月底月初。至少 ${R.n} 筆、勝率 ≥ ${R.win}%、比隨便挑同樣天數高 ${R.edge} 個百分點以上、扣成本後平均每筆賺錢`,
    `落底型：至少 ${R.dn} 次、抱完賺錢 ≥ ${R.dwin}% 而且不比隨便挑一天差，扣成本後的報酬中位數與排除極端（去掉最好和最差各 ${R.dtq}%，不到 ${R.dtn} 次各去掉一次）的平均都賺錢（2026-10-22 起；之前要比隨便挑一天高 10 個百分點，或報酬中位數夠大）`,
    `進出型：風險控制、Halloween。最大回撤比一直持有少 ${R.mdd}% 以上，而且年化 ÷ 最大回撤不輸一直持有`,
    `判定：★ 好策略＝全期間、近 10 年、參數鄰近（換附近的參數，${R.grid} 以上也過關）都過；● 可參考＝全期間過、後兩項沒過；○ 不推薦＝全期間沒過；— 次數不夠。打亂測試只標示、不影響判定`,
    '買賣時點：看收盤才知道的訊號一律隔天收盤買賣（看網頁做得到的最早時點）；台股 RSI(2) 用台指期在訊號當天收盤前買賣；月底月初、Halloween 照排定的日子收盤',
    '成本：台股 ETF 每買或賣一次 0.1%（台指期約 0.005%）、美股 0.025%。價格是指數本身、不含股息，空手不算利息',
    `規格：arm/lab/xstratspec.py（VER ${MAC.ver}），在算正式成績之前寫定；改規則要升版本`])+'</div></details>');}
/* ---------- 說明卡（2026-10-22 第三段；比照個股策略的 stCard：結論／怎麼做／過去成績／逐筆交易／風險，判定依據收起來）
   內嵌（D.mac）：結論、規則、逐年報酬（落底型＝抱多久比較）、風險；出處每條策略一份（MAC.spec）。
   x9xh.json（打開規則與成績才下載，XMD）：1 元變多少的淨值、逐筆交易、判定依據（xspage.detail_json）。 ---------- */
let XMD=null,XMDP=null;
function xmLoad(){if(XMDP)return XMDP;
  XMDP=fetch('x9xh.json').then(r=>{if(!r.ok)throw new Error('HTTP '+r.status);return r.json();}).then(j=>{XMD=j;return j;},e=>{XMDP=null;throw e;});
  return XMDP;}
function xmKey(k){return `xs:${S.mmk}:${k}`;}
function xmBk(k){return ((xmM()||{}).book||[]).find(b=>b.k===k)||{};}
function xmYr(b){const Y=(b.ex||{}).yr;if(!Y)return '';const rows=Y.s.map((v,i)=>[String(+Y.y0+i),v,Y.b[i]]);if(Y.to)rows[rows.length-1].push(Y.to);
  return yearTbl({yearly:rows,all:{d0:(b.exp||{}).d0}},'買進持有',Y.to||'',10);}
function xmHs(b){const H=(b.ex||{}).hs||[];if(!H.length)return '';
  return `<h4 class=sh style="margin-top:0">抱多久比較（只列，不判定）</h4><div class=tw><table class="yrt xmhs"><thead><tr><th>抱多久</th><th>次數</th><th>賺錢</th><th>隨便挑一天</th><th>中位數</th></tr></thead><tbody>`+
    H.map(r=>`<tr${r[5]?' class=xmon':''}><td>${esc(r[0])}</td><td>${r[1]}</td><td>${xmPc(r[2])}</td><td>${xmPc(r[4])}</td><td>${sgn(r[3],1,'%')}</td></tr>`).join('')+
    `</tbody></table></div><div class=note>粗體＝判定看的期間。賺錢＝扣成本後抱完還賺的比例；隨便挑一天＝同一段期間每一天都當買進日、抱一樣久；中位數扣成本。</div>`;}
/* 1 元變多少：x9xh.json 到了才畫；之前先放一樣大的佔位（同寬同高、圖例的倍數已知），捲到某一張卡時不會跳位 */
const XMLB='買進持有（指數，不含股息）';
function xmCvSlot(b){const cv=(b.ex||{}).cv,W=acW();
  return `<div class=xmcv data-xk="${esc(b.k)}"><h4 class=sh style="margin-top:0">1 元變多少（對數刻度）</h4><svg width=${W} height=200 viewBox="0 0 ${W} 200"><text x=${Math.round(W/2)} y=104 font-size=12 fill="#727e8c" text-anchor=middle>載入中…</text></svg>`+
    (cv?acLg(cv[0],cv[1],(b.exp||{}).d0||'',XMLB):'')+`</div>`;}
function xmCvFill(){if(!XMD)return;$$('#main .xmcv').forEach(el=>{const k=el.dataset.xk,E=((XMD[xmKey(k)]||{}).eq)||null,b=xmBk(k);
  if(!E||!(E.d||[]).length){el.innerHTML='<div class=mu>沒有淨值資料。</div>';return;}
  el.innerHTML=acurveChart({d:[(b.exp||{}).d0||E.d[0],...E.d],s:[1,...E.s],t:[1,...E.b]},XMLB);});}
function xmPast(b){const ex=b.ex||{},L=b.kind==='dip'?xmHs(b):xmYr(b);
  return `<div class=pst><div>${L}${ex.season?`<div class=note>${esc(ex.season)}</div>`:''}</div><div>${xmCvSlot(b)}</div></div>`;}
/* 逐筆交易（同個股策略：預設收起、年份、下載 CSV）；每一筆＝[買進日, 買價, 賣出日（持有中＝null）, 賣價, 交易日數, 報酬, 中途最多跌, 訊號日] */
const XMTS={};
function xmTrBox(b){const e=b.exp||{};if(!e.nt)return '';
  return `<details class="mr trb xmtrb" data-xk="${esc(b.k)}"><summary>${e.nt} ${esc(e.unit||'筆')}（${ym(e.d0)}～${ym(e.d1)}）</summary><div class=trin></div></details>`;}
function xmTrCheck(b,T){const e=b.exp||{},u=e.unit||'筆',dd=b.kind==='trade'?2:1,cl=T.filter(t=>t[2]&&t[5]!=null).map(t=>t[5]*100),op=T.filter(t=>!t[2]);
  let s=cl.length?`已賣出：${cl.length} ${u}，平均 <b>${pctT(avgOf(cl),dd)}</b>、中位 ${pctT(medOf(cl),dd)}，${winOf(cl)}% 賺錢，就是上方結論與比較表的數字。`:'還沒有賣出的。';
  if(op.length)s+=`<br>持有中：${xmDw(op[0][0])} 買進，到最新收盤 ${pctT(op[0][5]*100)}，還沒賣出、不算進上面的數字。`;
  else if(b.kind!=='alloc')s+=`<br>還沒賣出的${b.kind==='dip'?'（還在抱的期間裡）':''}不在表上，也不算進上面的數字。`;
  const ix=XMI[S.mmk]||'指數';
  return `<div class=trn>${s}</div><div class="sm2 trf">報酬＝賣出價 ÷ 買進價 ×（1 − 成本）÷（1 ＋ 成本）− 1，成本＝${esc((b.ex||{}).cost||'')}；價格是${esc(ix)}收盤（不含股息）。${b.kind==='alloc'?'持有中的那一段算到最新收盤、不扣成本。':''}</div>`;}
function xmTrRows(b,rows,mob){const dp=b.kind==='dip',al=b.kind==='alloc',ix=XMI[S.mmk]||'',dt=d=>d?esc(xmYmd(d)):'';
  const ret=t=>`<b>${sgn(t[5]*100,1,'%')}</b>`,mae=t=>t[6]?'−'+f(t[6]*100,1)+'%':'0%';
  if(mob)return rows.map(t=>`<div class=trl><div class=trh><span>${dt(t[0])} 買 → ${t[2]?dt(t[2])+' 賣':'<b>持有中</b>'}</span><span class=trr>${ret(t)}</span></div>`+
    `<div class=sm2>${dp?`訊號 ${dt(t[7])}｜`:''}${esc(ix)} ${fp(t[1])} → ${fp(t[3])}${t[2]?'':'（最新）'}｜${al?'交易日數':'抱'} ${t[4]} 天${dp?`｜中途最多跌 ${mae(t)}`:''}</div></div>`).join('');
  return `<div class=tw><table class=trt><thead><tr>${dp?'<th class=l>訊號</th>':''}<th class=l>買進（${esc(ix)}收盤）</th><th class=l>賣出</th><th>${al?'交易日數':'抱幾天'}</th><th>${al?'這一段':'報酬'}</th>${dp?'<th>中途最多跌</th>':''}</tr></thead><tbody>`+
    rows.map(t=>`<tr>${dp?`<td class=l>${dt(t[7])}</td>`:''}<td class=l>${dt(t[0])}<div class=sm2>${fp(t[1])}</div></td><td class=l>${t[2]?dt(t[2]):'<b>持有中</b>'}<div class=sm2>${fp(t[3])}${t[2]?'':'（最新）'}</div></td><td>${t[4]}</td><td>${ret(t)}</td>${dp?`<td>${mae(t)}</td>`:''}</tr>`).join('')+`</tbody></table></div>`;}
function xmTrRender(k){const d=document.querySelector(`#main details.xmtrb[data-xk="${k}"]`);if(!d)return;const box=d.querySelector('.trin'),j=(XMD||{})[xmKey(k)],b=xmBk(k);
  if(!j||!(j.tr||[]).length){box.innerHTML='<div class=mu>沒有資料。</div>';return;}
  const Q=XMTS[xmKey(k)]=XMTS[xmKey(k)]||{y:'',n:0},T=j.tr.slice().reverse(),u=(b.exp||{}).unit||'筆';
  const yrs=[...new Set(T.map(t=>t[0].slice(0,4)))],mob=innerWidth<640,step=mob?15:25;
  const all=T.filter(t=>!Q.y||t[0].startsWith(Q.y)),n=Q.n||step,rows=all.slice(0,n);
  const sub=all.filter(t=>t[2]&&t[5]!=null).map(t=>t[5]*100);
  box.innerHTML=xmTrCheck(b,j.tr)+`<div class=trc><select data-xty>${['',...yrs].map(y=>`<option value="${y}"${Q.y===y?' selected':''}>${y?y+' 年':'全部年份'}</option>`).join('')}</select><a class=trcsv data-xtcsv>下載 CSV</a></div>`+
    (Q.y?`<div class=sm2>${Q.y} 年買進的 ${all.length} ${u}${sub.length?`，平均 ${pctT(avgOf(sub))}、${winOf(sub)}% 賺錢`:''}</div>`:'')+
    (all.length?xmTrRows(b,rows,mob):'<div class=st>這一年沒有買進。</div>')+(all.length>n?`<a class=trm data-xtm>再顯示 ${Math.min(step,all.length-n)} ${u}（共 ${all.length}）</a>`:'');
  box.querySelector('[data-xty]').onchange=e=>{Q.y=e.target.value;Q.n=0;xmTrRender(k);};
  const m=box.querySelector('[data-xtm]');if(m)m.onclick=()=>{Q.n=n+step;xmTrRender(k);};
  box.querySelector('[data-xtcsv]').onclick=()=>xmTrCsv(k);}
function xmTrCsv(k){const j=(XMD||{})[xmKey(k)];if(!j)return;const b=xmBk(k),dp=b.kind==='dip';
  const H=dp?['訊號日','買進日','買進收盤','賣出日','賣出收盤','交易日數','報酬%','中途最多跌%']:['買進日','買進收盤','賣出日','賣出收盤','交易日數','報酬%'];
  const R=(j.tr||[]).map(t=>dp?[t[7],t[0],t[1],t[2],t[3],t[4],(t[5]*100).toFixed(2),((t[6]||0)*100).toFixed(2)]:[t[0],t[1],t[2]||'持有中',t[3],t[4],(t[5]*100).toFixed(2)]);
  const q=x=>{x=x==null?'':String(x);return /[",\n]/.test(x)?'"'+x.replace(/"/g,'""')+'"':x;};
  const txt='\ufeff'+[H,...R].map(r=>r.map(q).join(',')).join('\r\n');
  const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([txt],{type:'text/csv;charset=utf-8'}));
  a.download=`總經策略_${(MAC.mkn||{})[S.mmk]||S.mmk}_${b.name||k}_${(xmM()||{}).d||''}.csv`;document.body.appendChild(a);a.click();
  setTimeout(()=>{URL.revokeObjectURL(a.href);a.remove();},800);}
/* 判定依據（收起來；打開才畫）：每一項過了沒、對照（不判定）、參數鄰近表 */
function xmJdBox(b){return `<details class="mr xmjd" data-xk="${esc(b.k)}"><summary>${tBadge(b.tier)} 每一項過了沒、換附近的參數</summary><div class=xmjdin></div></details>`;}
function xmGrid(G){const td=c=>!c?'<td>—</td>':`<td class="${c[1]?'xmmn':''}"><span class="ck ${c[0]?'up':'dn'}">${c[0]?'✓':'✗'}</span>${esc(c[2])}<div class=sm2>${esc(c[3])}</div></td>`;
  const tb=G.b.length?`<thead><tr><th>${esc(G.pn[0])}＼${esc(G.pn[1])}</th>${G.b.map(x=>`<th>${esc(x)}</th>`).join('')}</tr></thead><tbody>${G.c.map((r,i)=>`<tr><th>${esc(G.a[i])}</th>${r.map(td).join('')}</tr>`).join('')}</tbody>`
    :`<thead><tr><th>${esc(G.pn[0])}</th>${G.a.map(x=>`<th>${esc(x)}</th>`).join('')}</tr></thead><tbody><tr><th>全期間</th>${(G.c[0]||[]).map(td).join('')}</tr></tbody>`;
  return `<div class=tw><table class="nbg xmg">${tb}</table></div><div class=note>框起來的是原作者的參數；✓＝這組參數全期間也過關。</div>`;}
function xmJd(k){const j=((XMD||{})[xmKey(k)]||{}).jd;if(!j)return '<div class=mu>沒有資料。</div>';
  const ck=ok=>ok==null?'<span class=ck>·</span>':ok?'<span class="ck up">✓</span>':'<span class="ck dn">✗</span>';
  let h=`<div class=rbl>${(j.why||[]).map(([ok,t])=>{const i=t.indexOf('：'),lb=i>0&&i<=30?t.slice(0,i):'';return `<div class=rbr><div class=rbk>${ck(ok)}${esc(lb)}</div><div>${esc(lb?t.slice(i+1):t)}</div></div>`;}).join('')}</div>`;
  if(j.ref)h+=`<div class=note>對照（不判定）：${esc(j.ref)}</div>`;
  const G=j.grid;if(G&&(G.c||[]).length)h+=`<h4 class=sh>參數鄰近${gi('參數鄰近（總經）')}：${G.n} 組有 ${G.ok} 組過關</h4>${xmGrid(G)}`;
  return h;}
function xmLazy(sel,fill){$$('#main '+sel).forEach(d=>d.addEventListener('toggle',()=>{if(!d.open||d.dataset.done)return;d.dataset.done=1;
  const box=d.querySelector('.trin,.xmjdin');box.innerHTML='<div class=mu>載入中…</div>';
  xmLoad().then(()=>fill(d,box),()=>{box.innerHTML='<div class=st>載入失敗，請重新整理。</div>';d.dataset.done='';});}));}
function xmStCard(b){const k=b.k,ex=b.ex||{},sp=(MAC.spec||{})[k]||{},tb=xmTrBox(b);
  const how=`<div class=rls>${ruleRows(ex.rules||[])}</div><div class="note xmsrc">${esc(sp.logic||'')}出處：${esc(sp.src||'')}。${esc(sp.pnote||'參數照原作者，沒有調。')}</div>`;
  const parts=[['結論',`<div>${esc(ex.concl||'')}</div><div class=xmtl>${tBadge(b.tier)} ${esc(ex.tl||'')}</div>`],['怎麼做',how],['過去成績',xmPast(b)]];
  if(tb)parts.push(['逐筆交易',tb]);
  parts.push(['風險',riskList(ex.risk)],['判定依據',xmJdBox(b)]);
  return sec('ms-'+k,xmNm(k),`${b.rank?`<span class=orank>${b.rank}</span>`:''}${esc(b.name)} ${tBadge(b.tier)}`,esc(b.how||''),
    `<div class="card stc">${parts.map(([a,c])=>sq(a,c)).join('')}`+(b.rank?`<div class=vlk><a data-go="mac" data-at="m-${esc(k)}">這一期：現在持有還是空手、哪天買賣 →</a></div>`:'')+`</div>`);}
function vMacSt(){const M=xmM();
  let h=`<div class=intro>每條總經策略的規則與過去照做的成績（扣成本），和隨便挑一天或買進持有比。推薦順序${gi('推薦順序（總經）')}：★ 好策略在前；○ 不推薦、— 次數不夠灰字放後面。比較表下面一條一張說明卡（結論、怎麼做、過去成績、逐筆交易、風險、判定依據）。價格是指數本身、不含股息。</div>`+xmHead('macst');
  if(!M){$('#main').innerHTML=h+'<div class=st>總經策略的資料還沒產生。</div>';return;}
  h+=xmBook(M)+(M.book||[]).map(xmStCard).join('')+xmMethod();
  $('#main').innerHTML=h;xmBind();
  xmLazy('details.xmtrb',d=>xmTrRender(d.dataset.xk));xmLazy('details.xmjd',(d,box)=>{box.innerHTML=xmJd(d.dataset.xk);});
  xmLoad().then(xmCvFill,()=>{$$('#main .xmcv text').forEach(e=>e.textContent='載入失敗，請重新整理。');});}
"""
