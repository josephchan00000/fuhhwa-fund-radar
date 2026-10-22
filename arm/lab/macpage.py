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
  '判定（總經）':`照書上、論文裡的規則在指數上做一遍，看過去照做的成績（扣成本）。交易型（短線、月底月初）：至少 ${R.n} 筆、勝率 ≥ ${R.win}%、比隨便挑同樣天數高 ${R.edge} 個百分點以上、平均每筆賺錢。落底型：至少 ${R.dn} 次、抱完賺錢 ≥ ${R.dwin}%，而且賺錢的比例比隨便挑一天高 ${R.dedge} 個百分點以上（中位數賺錢），或中位數至少是隨便挑一天的 ${R.dmx} 倍、而且多 ${R.dadd} 個百分點。進出型（風險控制、Halloween）：最大回撤比一直持有少 ${R.mdd}% 以上，而且年化 ÷ 最大回撤不輸一直持有。★ 好策略＝全期間、近 10 年、換附近的參數（${R.grid} 以上也過關）都過；● 可參考＝全期間過、後兩項沒過；○ 不推薦＝全期間沒過；— 次數不夠。`,
  '隱含獲利（總經）':'同一套規則過去照做的實際報酬（扣成本）：每筆（交易型）、每次（落底型，抱固定天數）、每段（進出型，一次持有到賣出）。對照＝隨便挑一天、抱一樣久（交易型、落底型），或一直持有（進出型）。價格是指數本身、不含股息。是歷史統計，不是預測。',
  '隨便挑一天':'每一個交易日都當成買進日、抱一樣多天，賺錢的比例（或報酬中位數）：不用這條規則、隨便買的成績。和它比，才看得出規則有沒有多賺。',
  '全部資金照做':'全部資金只照這條策略操作的年化報酬：有訊號才持有，其他時間放現金（不算利息）；買進持有＝同一段期間一直抱著指數（不含股息）。'});
  GLG.push(['總經策略',['推薦順序（總經）','判定（總經）','隱含獲利（總經）','隨便挑一天','全部資金照做']]);})();
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
/* 卡片四行：做法／隱含獲利／現在／下一次（同個股策略的做法／隱含獲利／現在／下一批） */
function xmExp(c){const e=c.exp||{},span=`${ym(e.d0)}～${ym(e.d1)}`;
  if(c.kind==='alloc'){const sp=e.n?`每段平均 ${pctT(e.avg)}、${e.win}% 賺錢，最差一段 ${pctT(e.lo)}・`:'';
    return `全部資金照做年化 <b>${pctT(e.cagr)}</b>（買進持有 ${pctT(e.bcagr)}）${gi('全部資金照做')}，最大回撤 <b>${xmPc(e.mdd)}</b>（買進持有 ${xmPc(e.bmdd)}）`+
      `<div class=sm2>有部位的時間 ${xmPc(e.expo)}${e.sw!=null?`、一年進出約 ${f(e.sw,1)} 次`:''}；${sp}${span}，${e.n||0} 段</div>`;}
  if(!e.n)return `<span class=mu>評估期間（${span}）沒有${c.kind==='dip'?'出現過':'交易'}。</span>`;
  if(c.kind==='dip')return `每次平均 <b>${pctT(e.avg)}</b>、中位 <b>${pctT(e.med)}</b>，<b>${e.win}%</b> 賺錢（隨便挑一天抱一樣久${gi('隨便挑一天')} ${e.base}%、中位 ${pctT(e.bmed)}），最差一次 ${pctT(e.lo)}`+
    `<div class=sm2>抱 ${esc(e.hn||'')}，中途最多跌中位 ${f(e.mae,1)}%；全部資金照做年化 ${pctT(e.cagr)}（買進持有 ${pctT(e.bcagr)}），有部位的時間 ${xmPc(e.expo)}・${span}，${e.n} 次</div>`;
  return `每筆平均 <b>${pctT(e.avg,2)}</b>、中位 <b>${pctT(e.med,2)}</b>，<b>${e.win}%</b> 賺錢（隨便挑同樣天數${gi('隨便挑一天')} ${e.base}%），最差一筆 ${pctT(e.lo)}`+
    `<div class=sm2>平均抱 ${f(e.hold,1)} 天；全部資金照做年化 ${pctT(e.cagr)}（買進持有 ${pctT(e.bcagr)}），有部位的時間 ${xmPc(e.expo)}・${span}，${e.n} 筆</div>`;}
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
    `<div class="card stc">${rows.map(([a,b])=>sq(a,b)).join('')}<div class=vlk><a data-go="macst" data-at="mb-${esc(c.k)}">規則與過去成績 →</a></div></div>`);}
function xmBind(){$$('#main [data-to]').forEach(a=>a.onclick=e=>{e.preventDefault();jump(a.dataset.to);});}
function vMac(){const M=xmM();
  let h=`<div class=intro>大盤指數照書上、論文裡的固定規則買賣（總經策略）：先選市場，看照規則哪天買賣、現在持有什麼，以及同樣做法過去照做的實際報酬（扣成本）。只列 ★ 好策略、● 可參考${gi('判定（總經）')}，依推薦順序${gi('推薦順序（總經）')}；報酬是歷史統計，不是預測。</div>`+xmHead('mac');
  if(!M){$('#main').innerHTML=h+'<div class=st>總經策略的資料還沒產生。</div>';return;}
  h+=sec('m-sum','摘要',`${esc(M.name)}・這一期`,`${md(M.d)} 收盤後更新`,xmSum(M)+xmNextDay(M)+xmTlSec()+`<details class=mr><summary>時間表（文字）</summary>${xmCalTxt(M)}</details>`);
  h+=(M.cards||[]).map(xmCard).join('');
  const lo=(M.book||[]).filter(b=>b.rank==null);
  if(lo.length)h+=`<div class=note>判定沒過（○ 不推薦、— 次數不夠）的 ${lo.length} 條不列在這頁：${lo.map(b=>`<a data-go="macst" data-at="mb-${esc(b.k)}">${esc(b.name)}</a>`).join('、')}，在「規則與成績」灰字列出。</div>`;
  $('#main').innerHTML=h;tlDraw(TLM);xmBind();}
/* 規則與成績：比較表（同個股策略的策略比較）＋判定方式 */
function xmBook(M){const B=M.book||[];
  const row=b=>{const e=b.exp||{},rec=b.rank!=null,u=e.unit,d=b.kind==='trade'?2:1;
    const per=e.n?`${pctT(e.avg,d)}<div class=sm2>中位 ${pctT(e.med,d)}</div>`:'<span class=mu>—</span>';
    const win=e.n?`${e.win}%<div class=sm2>${e.base!=null?`隨便挑 ${e.base}%`:`最差 ${pctT(e.lo)}`}</div>`:'<span class=mu>—</span>';
    return `<tr class="${rec?'':'grey'}" id="mb-${esc(b.k)}"><td class=l><span class=nm>${rec?`<span class="orank sm">${b.rank}</span>`:''}${esc(b.name)}</span><span class=bkg>${tBadge(b.tier)}</span><span class=cd>${esc(b.why)}</span><span class=cd>${esc(b.gname)}・每${esc(u)}</span></td>`+
      `<td>${per}<div class="sm2 om">年化 ${pctT(e.cagr)}（買進持有 ${pctT(e.bcagr)}）</div></td><td>${win}</td>`+
      `<td class=hm>${pctT(e.cagr)}<div class=sm2>買進持有 ${pctT(e.bcagr)}</div></td><td class=hm>${xmPc(e.mdd)}<div class=sm2>買進持有 ${xmPc(e.bmdd)}</div></td>`+
      `<td class=hm>${ym(e.d0)}～${ym(e.d1)}<div class=sm2>${e.n||0} ${esc(u)}</div></td></tr>`;};
  return sec('mb-book','比較','策略比較',`${esc(M.name)}：★、● 依推薦順序；每筆（每次、每段）從買進到賣出、扣成本後的報酬`,
    `<div class=tw><table class=bkt><thead><tr><th class=l>推薦順序${gi('推薦順序（總經）')}・策略・判定${gi('判定（總經）')}</th><th>平均報酬${gi('隱含獲利（總經）')}</th><th>賺錢比例${gi('隨便挑一天')}</th><th class=hm>年化${gi('全部資金照做')}</th><th class=hm>最大回撤</th><th class=hm>資料期間</th></tr></thead><tbody>${B.map(row).join('')}</tbody></table></div>`+
    `<div class=note>平均報酬與賺錢比例：交易型、落底型是每一筆（每一次），旁邊是隨便挑一天抱一樣久的賺錢比例；進出型是每一段持有。年化＝全部資金照這條策略操作（沒有部位時放現金、不算利息）；買進持有＝同一段期間一直抱著指數。價格是指數本身、不含股息。</div>`);}
function xmMethod(){const R=MAC.rule||{};
  return sec('mb-mth','判定方式','判定方式','','<details class=mr><summary>★ 好策略、● 可參考怎麼判定</summary><div class=rls>'+ruleRows([
    `交易型：短線、月底月初。至少 ${R.n} 筆、勝率 ≥ ${R.win}%、比隨便挑同樣天數高 ${R.edge} 個百分點以上、扣成本後平均每筆賺錢`,
    `落底型：至少 ${R.dn} 次、抱完賺錢 ≥ ${R.dwin}%，而且兩條過一條：賺錢的比例比隨便挑一天高 ${R.dedge} 個百分點以上、中位數賺錢；或報酬中位數至少是隨便挑一天的 ${R.dmx} 倍、而且多 ${R.dadd} 個百分點`,
    `進出型：風險控制、Halloween。最大回撤比一直持有少 ${R.mdd}% 以上，而且年化 ÷ 最大回撤不輸一直持有`,
    `判定：★ 好策略＝全期間、近 10 年、參數鄰近（換附近的參數，${R.grid} 以上也過關）都過；● 可參考＝全期間過、後兩項沒過；○ 不推薦＝全期間沒過；— 次數不夠。打亂測試只標示、不影響判定`,
    '買賣時點：看收盤才知道的訊號一律隔天收盤買賣（看網頁做得到的最早時點）；台股 RSI(2) 用台指期在訊號當天收盤前買賣；月底月初、Halloween 照排定的日子收盤',
    '成本：台股 ETF 每買或賣一次 0.1%（台指期約 0.005%）、美股 0.025%。價格是指數本身、不含股息，空手不算利息',
    `規格：arm/lab/xstratspec.py（VER ${MAC.ver}），在算正式成績之前寫定；改規則要升版本`])+'</div></details>');}
function vMacSt(){const M=xmM();
  let h=`<div class=intro>每條總經策略的規則與過去照做的成績（扣成本），和隨便挑一天或買進持有比。推薦順序${gi('推薦順序（總經）')}：★ 好策略在前；○ 不推薦、— 次數不夠灰字放後面。價格是指數本身、不含股息。</div>`+xmHead('macst');
  if(!M){$('#main').innerHTML=h+'<div class=st>總經策略的資料還沒產生。</div>';return;}
  h+=xmBook(M)+xmMethod();
  $('#main').innerHTML=h;xmBind();}
"""
