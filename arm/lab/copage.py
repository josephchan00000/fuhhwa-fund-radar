"""籌碼雷達頁面：公司分析（docs/lab_company_plan.md 第 5 節）的 CSS 與 JS。

點進去才下載 dashboard/co/{代號}.json（那一檔的財報、月營收、股價、股利），第一次另抓全市場小表 x9t.json；
所有比率、走勢、估值位置、拆解、飆股體質檢查都在瀏覽器算。page.render 把這裡的 CSS／JS 接在原本的後面
（同一個 <script>，函式宣告會提升，page.py 的 renderStock 可以直接呼叫 coSec）。
"""

CSS = r"""
.cos{position:relative;flex:0 1 240px;min-width:150px}
.cos input{width:100%;padding:5px 10px;border:1px solid var(--line);border-radius:9px;font:inherit;font-size:13.5px;background:var(--card2)}
.coqd{position:absolute;right:0;left:0;top:100%;z-index:40;background:var(--bg);border:1px solid var(--line);border-radius:10px;
  box-shadow:0 8px 24px rgba(20,30,50,.12);margin-top:4px;max-height:320px;overflow:auto}
.coqd a{display:flex;gap:8px;padding:7px 12px;color:var(--ink);font-size:14px;border-bottom:1px solid var(--line)}
.coqd a:last-child{border-bottom:0}.coqd a.on,.coqd a:hover{background:var(--hlbg)}.coqd .cd{color:var(--mut);font-size:12.5px;margin-left:auto}
.co5{margin:4px 0 6px}.co5 .r{display:grid;grid-template-columns:2.6em 2.8em 66px minmax(0,1fr);gap:8px;align-items:center;padding:5px 0;border-bottom:1px solid var(--line);font-size:13.5px}
.co5 .r b{font-size:13.5px}.co5 .lv{font-weight:700;font-size:13px}.co5 .lv.s5,.co5 .lv.s4{color:var(--gain)}.co5 .lv.s1,.co5 .lv.s2{color:var(--loss)}
.seg{display:flex;gap:2px}.seg i{display:block;height:7px;flex:1;border-radius:2px;background:var(--line)}
.seg.s5 i,.seg.s4 i:nth-child(-n+4){background:var(--gain)}.seg.s3 i:nth-child(-n+3){background:#94a3b8}
.seg.s2 i:nth-child(-n+2),.seg.s1 i:nth-child(1){background:var(--loss)}
.colead{font-size:15px;margin:2px 0 8px;font-weight:600}
.chk{list-style:none;margin:4px 0 0;padding:0}.chk li{display:grid;grid-template-columns:1.4em minmax(0,1fr) auto;gap:6px;padding:6px 0;border-bottom:1px solid var(--line);font-size:13.5px;align-items:baseline}
.chk .ok{color:var(--gain);font-weight:700}.chk .no{color:var(--mut)}.chk .na{color:var(--mut)}.chk .hr{color:var(--mut);font-size:12px;text-align:right;white-space:nowrap}
.chk .hr b{color:var(--ink2)}
.cgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.cbox{background:var(--card2);border-radius:10px;padding:8px 10px;min-width:0}.cbox h4{margin:0 0 4px;font-size:13px;color:var(--ink2)}
.cbox svg{display:block;width:100%;height:auto}
.colg{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:12px;color:var(--mut);margin-top:2px}.colg i{display:inline-block;width:10px;height:3px;margin-right:4px;vertical-align:middle}
.vband{position:relative;height:30px;margin:8px 4px 2px}.vband .bg{position:absolute;top:10px;left:0;right:0;height:8px;background:var(--line);border-radius:4px}
.vband .bd{position:absolute;top:10px;height:8px;background:#b8c7e0;border-radius:4px}.vband .md{position:absolute;top:6px;width:2px;height:16px;background:var(--accd)}
.vband .now{position:absolute;top:2px;width:2px;height:24px;background:var(--ink)}
.vlab{display:flex;justify-content:space-between;font-size:12px;color:var(--mut)}
.qt td,.qt th{padding:5px 7px;font-size:13px}.qt td:first-child,.qt th:first-child{text-align:left}
@media (max-width:640px){.cgrid{grid-template-columns:minmax(0,1fr)}.co5 .r{grid-template-columns:2.6em 2.8em 54px minmax(0,1fr)}.cos{flex-basis:100%;order:4}}
"""

JS = r"""
/* ===== 公司分析（docs/lab_company_plan.md 第 5 節）：點進去才下載 co/{代號}.json；第一次另抓全市場小表 x9t.json ===== */
const CO={},COP={},MTS={};let MT=null,MTP=null,MTERR=false,COIX=null,COIXP=null,COJ=null;
function getJ(u){return fetch(u).then(r=>{if(!r.ok)throw new Error('HTTP '+r.status);return r.json();});}
function coLoad(c){if(CO[c])return Promise.resolve(CO[c]);if(!COP[c])COP[c]=getJ(`co/${encodeURIComponent(c)}.json?v=${encodeURIComponent(D.mtv||'')}`).then(j=>(CO[c]=coParse(j)),e=>{COP[c]=null;throw e;});return COP[c];}
function mtLoad(){if(MT)return Promise.resolve(MT);if(!MTP)MTP=getJ('x9t.json?v='+encodeURIComponent(D.mtv||'')).then(j=>(MT=j),e=>{MTP=null;MTERR=true;throw e;});return MTP;}
function coIdx(){if(COIX)return Promise.resolve(COIX);if(!COIXP)COIXP=getJ('co/index.json?v='+encodeURIComponent(D.mtv||'')).then(j=>(COIX=j.s||[]),e=>{COIXP=null;throw e;});return COIXP;}
function mtRow(c){if(!MT||!MT.rows||!MT.rows[c])return null;const r=MT.rows[c],o={};MT.cols.forEach((k,i)=>o[k]=r[i]);return o;}
function mtPct(k,v){if(v==null||!MT)return null;
  if(!MTS[k]){const i=MT.cols.indexOf(k);MTS[k]=Object.values(MT.rows).map(r=>r[i]).filter(x=>typeof x==='number').sort((a,b)=>a-b);}
  const a=MTS[k];if(!a.length)return null;let lo=0,hi=a.length;while(lo<hi){const m=(lo+hi)>>1;if(a[m]<v)lo=m+1;else hi=m;}return Math.round(100*lo/a.length);}

/* ---- 資料：每季（損益單季、資產負債季底）＋每月＋股利 → 衍生比率（全部在這裡算） ---- */
const QE=['03-31','06-30','09-30','12-31'],QDL={'03-31':[0,'05-15'],'06-30':[0,'08-14'],'09-30':[0,'11-14'],'12-31':[1,'03-31']};
function qShift(q,k){let y=+q.slice(0,4),j=QE.indexOf(q.slice(5))-k;while(j<0){j+=4;y--;}while(j>3){j-=4;y++;}return `${y}-${QE[j]}`;}
function qAvail(q){const [dy,d]=QDL[q.slice(5)];return `${+q.slice(0,4)+dy}-${d}`;}
function qLab(q){return `${q.slice(2,4)}Q${QE.indexOf(q.slice(5))+1}`;}
function ymShift(ym,k){let y=+ym.slice(0,4),m=+ym.slice(5,7)+k;while(m<=0){m+=12;y--;}while(m>12){m-=12;y++;}return `${y}-${String(m).padStart(2,'0')}`;}
const ratio=(a,b)=>a!=null&&b!=null&&b>0?a/b:null;
function epsYoy(e,b){if(e==null||b==null)return null;if(b>0.05)return Math.max(-1,Math.min(3,e/b-1));return e>0.05?'轉盈':null;}
function coParse(doc){
  const Q=(doc.q||[]).map(r=>{const o={q:r[0]};(doc.qk||[]).forEach((k,i)=>o[k]=r[i+1]??null);return o;});
  const by={};Q.forEach(o=>by[o.q]=o);const g=(q,k)=>(by[q]||{})[k]??null;
  for(const o of Q){const q=o.q,p4=qShift(q,4);
    o.gm=ratio(o.gp,o.rev);o.om=o.op!=null?ratio(o.op,o.rev):null;o.nm=o.nip!=null?ratio(o.nip,o.rev):null;
    if(o.rev!=null&&o.rev<=0){o.gm=o.om=o.nm=null;}
    const r4=g(p4,'rev');o.ry=o.rev!=null&&r4>0?o.rev/r4-1:null;o.ey=epsYoy(o.eps,g(p4,'eps'));
    const e4=[0,1,2,3].map(k=>g(qShift(q,k),'eps'));o.ttm=e4.every(x=>x!=null)?e4.reduce((a,b)=>a+b,0):null;
    const n4=[0,1,2,3].map(k=>g(qShift(q,k),'nip')),v4=[0,1,2,3].map(k=>g(qShift(q,k),'rev'));
    const eq0=o.eqp,eq4=g(p4,'eqp'),ta0=o.ta,ta4=g(p4,'ta');
    const sn=n4.every(x=>x!=null)?n4.reduce((a,b)=>a+b,0):null,sv=v4.every(x=>x!=null)?v4.reduce((a,b)=>a+b,0):null;
    const aeq=eq0>0&&eq4>0?(eq0+eq4)/2:null,ata=ta0>0&&ta4>0?(ta0+ta4)/2:null;
    o.roe=sn!=null&&aeq?sn/aeq:null;o.roa=sn!=null&&ata?sn/ata:null;
    o.dpm=sn!=null&&sv>0?sn/sv:null;o.dat=sv!=null&&ata?sv/ata:null;o.dem=ata&&aeq?ata/aeq:null;
    o.dr=ratio(o.tl,o.ta);o.cr=ratio(o.ca,o.cl);
    const oc4=[0,1,2,3].map(k=>g(qShift(q,k),'ocf')),ic4=[0,1,2,3].map(k=>g(qShift(q,k),'icf'));
    o.ocf4=oc4.every(x=>x!=null)?oc4.reduce((a,b)=>a+b,0):null;o.fcf4=o.ocf4!=null&&ic4.every(x=>x!=null)?o.ocf4+ic4.reduce((a,b)=>a+b,0):null;o.ni4=sn;}
  const M=(doc.mo||[]).map(r=>({ym:r[0],rev:r[1]??null,px:r[2]??null,sh:r[3]??null}));const mb={};M.forEach(o=>mb[o.ym]=o);
  for(const o of M){const p=mb[ymShift(o.ym,-12)];o.ry=o.rev!=null&&p&&p.rev>0?o.rev/p.rev-1:null;
    const s3=[0,1,2].map(k=>(mb[ymShift(o.ym,-k)]||{}).rev),p3=[0,1,2].map(k=>(mb[ymShift(o.ym,-12-k)]||{}).rev);
    o.ry3=s3.every(x=>x!=null)&&p3.every(x=>x!=null)&&p3.reduce((a,b)=>a+b,0)>0?s3.reduce((a,b)=>a+b,0)/p3.reduce((a,b)=>a+b,0)-1:null;
    const pr=[...Array(11)].map((_,k)=>(mb[ymShift(o.ym,-k-1)]||{}).rev);o.nh=o.rev!=null&&pr.every(x=>x!=null)&&o.rev>=Math.max(...pr);}
  /* 每月本益比、淨值比：月底股價 ÷ 那個月底「已過法定公告期限」的近四季 EPS／最新每股淨值 */
  const qs=Q.filter(o=>o.ttm!=null||o.bvps!=null);
  for(const o of M){if(o.px==null)continue;const me=o.ym+'-31';let et=null,bv=null;
    for(const x of qs){if(qAvail(x.q)<=me){if(x.ttm!=null)et=x.ttm;if(x.bvps!=null)bv=x.bvps;}}
    o.pe=et>0?o.px/et:null;o.pb=bv>0?o.px/bv:null;}
  return {doc,Q,M,by,DV:doc.dv||[]};}
function lastQ(C,k){for(let i=C.Q.length-1;i>=0;i--)if(C.Q[i][k]!=null)return C.Q[i];return null;}
function annualEps(C){const ye=C.doc.ye||{};const y={};for(const o of C.Q){const yr=o.q.slice(0,4);(y[yr]=y[yr]||[]).push(o.eps);}
  const out={};for(const [yr,a] of Object.entries(y))if(a.length===4&&a.every(x=>x!=null))out[yr]=a.reduce((s,x)=>s+x,0);
  for(const [yr,v] of Object.entries(ye))out[yr]=v;return Object.entries(out).sort((p,q)=>p[0]<q[0]?-1:1);}
function divYears(C){const y={};for(const [d,cash,t] of C.DV){const yr=d.slice(0,4);y[yr]=y[yr]||{c:0,n:0,unk:0};if(cash!=null)y[yr].c+=cash;if(t!=='息')y[yr].unk++;y[yr].n++;}return y;}
function quantile(a,p){if(!a.length)return null;const s=[...a].sort((x,y)=>x-y);const i=(s.length-1)*p,lo=Math.floor(i),hi=Math.ceil(i);return s[lo]+(s[hi]-s[lo])*(i-lo);}
const yi=x=>x==null?'—':f(x/100,x>=1e5?0:1);   /* 百萬元 → 億 */
const pc=(x,d=1)=>x==null?'—':f(x*100,d)+'%';
const psg=(x,d=1)=>x==null?'<span class=mu>—</span>':x==='轉盈'?'<span class=up>轉盈</span>':sgn(x*100,d,'%');

/* ---- 小圖（SVG） ---- */
function svgBars(vals,labs,o={}){const W=o.W||520,H=o.H||140,pt=16,pb=18,pl=4,pr=4,n=vals.length;if(!n)return '';
  const xs=vals.filter(v=>v!=null);const mx=Math.max(0,...xs),mn=Math.min(0,...xs);const rg=(mx-mn)||1;const y=v=>pt+(mx-v)/rg*(H-pt-pb);
  const bw=(W-pl-pr)/n,z=y(0);let s=`<svg viewBox="0 0 ${W} ${H}" role=img aria-label="${esc(o.al||'')}">`;
  s+=`<line x1=${pl} x2=${W-pr} y1=${z} y2=${z} stroke="#c9d0db" stroke-width=1 />`;
  vals.forEach((v,i)=>{if(v==null)return;const x=pl+i*bw+bw*.15,h=Math.abs(y(v)-z),yy=v>=0?y(v):z;const col=o.col?o.col(v,i):(v>=0?'#d33a34':'#1f9d57');
    s+=`<rect x=${x.toFixed(1)} y=${yy.toFixed(1)} width=${(bw*.7).toFixed(1)} height=${Math.max(.5,h).toFixed(1)} fill="${col}"${o.hi===i?' stroke="#1f2733" stroke-width=1.5':''}><title>${esc(labs[i])}：${esc(o.fmt?o.fmt(v):f(v,1))}</title></rect>`;
    if(n<=12&&o.vt!==false)s+=`<text x=${(x+bw*.35).toFixed(1)} y=${(v>=0?yy-3:yy+h+10).toFixed(1)} font-size=10 text-anchor=middle fill="#44505f">${esc(o.fmt?o.fmt(v):f(v,1))}</text>`;});
  axisLab(labs,i=>pl+i*bw+bw/2,W,H).forEach(t=>s+=t);
  return s+'</svg>';}
function axisLab(labs,xf,W,H){const n=labs.length;if(!n)return [];
  /* 依實際寬度排：最後一個一定顯示，其餘照間隔放、和前後重疊的略過 */
  const wd=t=>String(t).length*6.2,k=Math.max(2,Math.floor(W/56)),step=Math.max(1,Math.ceil(n/k));
  const pos=i=>{const x=xf(i),w=wd(labs[i]);const an=x<w/2+2?'start':x>W-w/2-2?'end':'middle';const l=an==='start'?x:an==='end'?x-w:x-w/2;return {i,x,an,l,r:l+w};};
  const last=pos(n-1),out=[];let pr=-1e9;
  for(let i=0;i<n-1;i+=step){const p=pos(i);if(p.l<pr+4||p.r>last.l-4)continue;out.push(p);pr=p.r;}
  out.push(last);
  return out.map(p=>`<text x=${p.x.toFixed(1)} y=${H-4} font-size=10 text-anchor=${p.an} fill="#727e8c">${esc(labs[p.i])}</text>`);}
function svgLines(ser,labs,o={}){const W=o.W||520,H=o.H||140,pt=10,pb=18,pl=4,pr=34,n=labs.length;if(!n)return '';
  const xs=ser.flatMap(s=>s.v.filter(v=>v!=null));if(!xs.length)return '';let mx=Math.max(...xs),mn=Math.min(...xs);if(o.zero){mx=Math.max(mx,0);mn=Math.min(mn,0);}
  const rg=(mx-mn)||1;const y=v=>pt+(mx-v)/rg*(H-pt-pb),x=i=>pl+(n===1?0:i*(W-pl-pr)/(n-1));
  let s=`<svg viewBox="0 0 ${W} ${H}" role=img aria-label="${esc(o.al||'')}">`;
  [mx,(mx+mn)/2,mn].forEach(v=>{s+=`<line x1=${pl} x2=${W-pr} y1=${y(v).toFixed(1)} y2=${y(v).toFixed(1)} stroke="#eef1f5" /><text x=${W-pr+3} y=${(y(v)+3).toFixed(1)} font-size=10 fill="#727e8c">${esc(o.fmt?o.fmt(v):f(v,1))}</text>`;});
  if(o.zero&&mn<0)s+=`<line x1=${pl} x2=${W-pr} y1=${y(0).toFixed(1)} y2=${y(0).toFixed(1)} stroke="#c9d0db" />`;
  for(const se of ser){let d='',pen=false;se.v.forEach((v,i)=>{if(v==null){pen=false;return;}d+=(pen?'L':'M')+x(i).toFixed(1)+' '+y(v).toFixed(1)+' ';pen=true;});
    s+=`<path d="${d}" fill=none stroke="${se.c}" stroke-width=${se.w||1.8} ${se.dash?'stroke-dasharray="4 3"':''} />`;
    const li=se.v.map((v,i)=>v!=null?i:-1).filter(i=>i>=0).pop();if(li!=null)s+=`<circle cx=${x(li).toFixed(1)} cy=${y(se.v[li]).toFixed(1)} r=2.6 fill="${se.c}"><title>${esc(se.n)} ${esc(labs[li])}：${esc(o.fmt?o.fmt(se.v[li]):f(se.v[li],1))}</title></circle>`;}
  axisLab(labs,x,W-pr+pl,H).forEach(t=>s+=t);
  return s+'</svg>';}
function lg(items){return `<div class=colg>${items.map(([c,t,d])=>`<span><i style="background:${c}${d?';height:2px;border-top:1px dashed '+c:''}"></i>${esc(t)}</span>`).join('')}</div>`;}

/* ---- 五面向（全市場百分位 → 5 格）、飆股體質檢查 ---- */
const CODIM=[['成長',[['ry3',1,'近 3 月營收年增','%'],['ey',1,'最新季 EPS 年增','%']]],
  ['獲利',[['roe',1,'近四季 ROE','%'],['om',1,'營益率','%']]],
  ['體質',[['dr',-1,'負債比','%'],['cr',1,'流動比','']]],
  ['估值',[['pe',-1,'本益比','倍'],['pb',-1,'淨值比','倍']]],
  ['動能',[['rs',1,'RS 百分位',''],['d52h',1,'距 52 週高點','%']]]];
function dimFmt(k,v,u){return k==='cr'?f(v*100,0)+'%':u==='%'?f(v,1)+'%':u==='倍'?f(v,v>=10?1:2)+' 倍':f(v,0);}
const LVN=['','落後','偏弱','中性','良好','頂尖'],LVV=['','昂貴','偏貴','中性','合理','便宜'];
function coDims(r){return CODIM.map(([nm,ms])=>{const ps=[],txt=[];
  for(const [k,dir,lab,u] of ms){const v=r?r[k]:null;const p=mtPct(k,v);if(p==null)continue;const q=dir>0?p:100-p;ps.push(q);
    txt.push(`${lab} ${dimFmt(k,v,u)}，${dir>0?'高':'低'}於全市場 ${dir>0?p:100-p}%`);}
  if(!ps.length)return {nm,lv:0,t:'資料不足'};const a=ps.reduce((x,y)=>x+y,0)/ps.length;const lv=a>=80?5:a>=60?4:a>=40?3:a>=20?2:1;return {nm,lv,t:txt.join('；')};});}
function dimLead(ds){const good=ds.filter(d=>d.lv>=4).map(d=>d.nm+(d.nm==='估值'?LVV[d.lv]:LVN[d.lv])),bad=ds.filter(d=>d.lv&&d.lv<=2).map(d=>d.nm+(d.nm==='估值'?LVV[d.lv]:LVN[d.lv]));
  return (good.length?good.join('、'):'')+(good.length&&bad.length?'；':'')+(bad.length?bad.join('、'):'')+(good.length||bad.length?'。':'各面向都在中間。');}
const TTN=['股價在 150 日與 200 日線之上','150 日線高於 200 日線','200 日線上揚（比 20 日前高）','50 日線高於 150、200 日線','股價在 50 日線之上','股價比 52 週低點高 30% 以上','股價在 52 週高點 25% 以內','RS ≥ 70'];
const SXCK=[['ey25','最新季 EPS 年增 ≥ 25%',r=>r.ey==null?null:r.ey>=25],['eacc','EPS 年增比上一季高（加速）',r=>r.eacc==null?null:r.eacc>0],
  ['ry25','近 3 月營收年增 ≥ 25%',r=>r.ry3==null?null:r.ry3>=25],['racc','營收年增加速',r=>r.racc==null?null:r.racc>0],
  ['rnh','月營收創 12 個月新高',r=>r.rnh==null?null:r.rnh===true],['gmd','毛利率比去年同季高',r=>r.gmd==null?null:r.gmd>0],
  ['c33','Code 33：EPS、營收、毛利率連三季加速',r=>r.c33==null?null:r.c33===true],['roe15','近四季 ROE ≥ 15%',r=>r.roe==null?null:r.roe>=15],
  ['tt8','趨勢樣板 8 項全過',r=>r.tt==null?null:r.tt===8],['rs80','RS ≥ 80',r=>r.rs==null?null:r.rs>=80],['h25','股價在 52 週高點 25% 以內',r=>r.d52h==null?null:r.d52h>=-25]];
function ckHit(k){const x=(((D.sx||{}).ck)||{})[k];if(!x||!x.B||x.B.p==null)return '';return `過去符合時 <b>${f(x.B.p*100,0)}%</b> 一年內翻倍（平常 ${f(x.B.base*100,0)}%）`;}

/* ---- 主體 ---- */
function coBody(c,W){const C=CO[c],r=mtRow(c);if(!C)return '';const Q=C.Q,M=C.M;const w=Math.max(260,W);const w2=isPane()||w>700?Math.floor((w-12)/2):w;
  const lq=lastQ(C,'eps'),lm=[...M].reverse().find(o=>o.rev!=null),lp=[...M].reverse().find(o=>o.px!=null);
  const px=r&&r.px!=null?r.px:(lp?lp.px:null);const ttm=lastQ(C,'ttm');const bvq=lastQ(C,'bvps');
  const pe=r&&r.pe!=null?r.pe:(px&&ttm&&ttm.ttm>0?px/ttm.ttm:null),pb=r&&r.pb!=null?r.pb:(px&&bvq&&bvq.bvps>0?px/bvq.bvps:null);
  const sh=lp&&lp.sh?lp.sh:null;const cap=r&&r.cap!=null?r.cap:(px&&sh?px*sh*1000/1e8:null);
  let h='';
  /* 1 摘要 */
  const ds=r?coDims(r):[];
  h+=`<section class=csec id=co-sum><h3>公司分析<span class=sub>財報至 ${lq?qLab(lq.q):'—'}・營收至 ${lm?lm.ym:'—'}${MT?'・市場資料 '+md(MT.d):''}</span></h3>`;
  h+=`<div class="kpis kps">`+kp('股價','',fp(px),r&&r.ch!=null?pctT(r.ch,2):'',r?cls(r.ch):'')+kp('市值','',cap==null?'—':f(cap,cap>=1000?0:1)+' 億','')+
    kp('本益比','本益比',pe==null?'—':f(pe,1)+' 倍',ttm?`近四季 EPS ${f(ttm.ttm,2)}`:'')+kp('淨值比','淨值比',pb==null?'—':f(pb,2)+' 倍',bvq?`每股淨值 ${f(bvq.bvps,1)}`:'')+
    kp('殖利率','殖利率',r&&r.yld!=null?f(r.yld,2)+'%':'—','近 12 個月現金股利')+kp('最新月營收','',lm?yi(lm.rev)+' 億':'—',lm&&lm.ry!=null?`年增 ${pctT(lm.ry*100,1)}`:'',lm?cls(lm.ry):'')+`</div>`;
  if(ds.length){h+=`<div class=colead style="margin-top:12px">${esc(dimLead(ds))}</div><div class=co5>`+ds.map(d=>{const lab=d.nm==='估值'?LVV[d.lv]:LVN[d.lv];
      return `<div class=r><b>${d.nm}</b><span class="lv s${d.lv}">${lab||'—'}</span><span class="seg s${d.lv}"><i></i><i></i><i></i><i></i><i></i></span><span class=st>${esc(d.t)}</span></div>`;}).join('')+`</div>`+
    `<div class=st>強弱＝和全市場比的百分位（估值：越便宜分數越高）${gi('五面向')}</div>`;}
  else h+=`<div class=st style="margin-top:8px">${MT?'這檔沒有在全市場比較表裡（上市未滿一年或沒有交易資料）。':'全市場比較資料載入中…'}</div>`;
  h+=`</section>`;
  /* 2 飆股體質檢查 */
  if(r){const it=SXCK.map(([k,t,fn])=>{const v=fn(r);return {k,t,v};});const ok=it.filter(x=>x.v===true).length,av=it.filter(x=>x.v!=null).length;
    h+=`<section class=csec id=co-sx><h3>飆股體質檢查<span class=sub>符合 ${ok}／${av} 項${gi('飆股體質檢查')}</span></h3><ul class=chk>`+
      it.map(x=>`<li><span class=${x.v===true?'ok':x.v===false?'no':'na'}>${x.v===true?'✓':x.v===false?'✗':'—'}</span><span>${esc(x.t)}</span><span class=hr>${ckHit(x.k)}</span></li>`).join('')+`</ul>`;
    if(r.ttb)h+=`<details class=mr><summary>趨勢樣板 8 項明細（${r.tt}／8）${gi('趨勢樣板')}</summary><ul class=chk>${TTN.map((t,i)=>`<li><span class=${r.ttb[i]==='1'?'ok':'no'}>${r.ttb[i]==='1'?'✓':'✗'}</span><span>${esc(t)}</span><span></span></li>`).join('')}</ul></details>`;
    const hit=(((D.sx||{}).hits)||{})[c];if(hit&&hit.length)h+=`<div class=note style="margin-top:8px">今天符合飆股研究的規則：${hit.map(i=>esc(((D.sx.rules||[])[i]||{}).txt||'')).join('；')}</div>`;
    h+=`<div class=st style="margin-top:6px">條件取自《超級績效》的基本面與趨勢樣板；「過去符合時」是 2014 年起這個條件成立的股票，之後 250 個交易日內最高價曾達兩倍的比例。</div></section>`;}
  /* 3 成長 */
  const m24=M.filter(o=>o.rev!=null).slice(-24);
  const q12=Q.filter(o=>o.rev!=null||o.eps!=null).slice(-12);
  h+=`<section class=csec id=co-gr><h3>成長<span class=sub>月營收與季報年增${gi('營收加速')}</span></h3><div class=cgrid>`;
  if(m24.length)h+=`<div class=cbox><h4>月營收（億）・年增率</h4>${svgBars(m24.map(o=>o.rev/100),m24.map(o=>o.ym.slice(2).replace('-','/')),{W:w2,H:130,col:(v,i)=>m24[i].nh?'#a16207':'#8fa6c8',fmt:v=>f(v,1)+' 億',vt:false,al:'月營收'})}`+
    `${svgLines([{v:m24.map(o=>o.ry==null?null:o.ry*100),c:'#d33a34',n:'年增'},{v:m24.map(o=>o.ry3==null?null:o.ry3*100),c:'#2563c9',n:'近 3 月年增',dash:1}],m24.map(o=>o.ym.slice(2).replace('-','/')),{W:w2,H:110,zero:1,fmt:v=>f(v,0)+'%'})}`+
    lg([['#a16207','創 12 個月新高'],['#d33a34','單月年增'],['#2563c9','近 3 月年增',1]])+`</div>`;
  if(q12.length)h+=`<div class=cbox><h4>季營收與 EPS 年增</h4>${svgLines([{v:q12.map(o=>o.ry==null?null:o.ry*100),c:'#2563c9',n:'營收年增'},{v:q12.map(o=>typeof o.ey==='number'?o.ey*100:null),c:'#d33a34',n:'EPS 年增'}],q12.map(o=>qLab(o.q)),{W:w2,H:130,zero:1,fmt:v=>f(v,0)+'%'})}`+
    lg([['#2563c9','營收年增'],['#d33a34','EPS 年增（上限 300%）']])+`${svgBars(q12.map(o=>o.eps),q12.map(o=>qLab(o.q)),{W:w2,H:110,fmt:v=>f(v,2),al:'單季 EPS'})}<div class=st>下圖：單季 EPS（元）</div></div>`;
  h+=`</div>`;
  const ae=annualEps(C).slice(-6);if(ae.length)h+=`<div class=st style="margin-top:8px">全年 EPS：${ae.map(([y,e])=>`${y} <b>${f(e,2)}</b>`).join('　')}</div>`;
  h+=`</section>`;
  /* 4 獲利能力 */
  const qp=Q.filter(o=>o.gm!=null||o.nm!=null).slice(-12);const lr=lastQ(C,'roe');
  h+=`<section class=csec id=co-pf><h3>獲利能力<span class=sub>三率與 ROE${gi('ROE 拆解')}</span></h3>`;
  if(qp.length){h+=`<div class=cgrid><div class=cbox><h4>毛利率・營益率・淨利率（單季）</h4>${svgLines([{v:qp.map(o=>o.gm==null?null:o.gm*100),c:'#a16207',n:'毛利率'},{v:qp.map(o=>o.om==null?null:o.om*100),c:'#2563c9',n:'營益率'},{v:qp.map(o=>o.nm==null?null:o.nm*100),c:'#d33a34',n:'淨利率'}],qp.map(o=>qLab(o.q)),{W:w2,H:140,fmt:v=>f(v,0)+'%'})}`+
      lg([['#a16207','毛利率'],['#2563c9','營益率'],['#d33a34','淨利率（歸屬母公司）']])+`</div>`;
    const qr=Q.filter(o=>o.roe!=null).slice(-12);
    h+=`<div class=cbox><h4>近四季 ROE・ROA</h4>${svgLines([{v:qr.map(o=>o.roe*100),c:'#d33a34',n:'ROE'},{v:qr.map(o=>o.roa==null?null:o.roa*100),c:'#727e8c',n:'ROA'}],qr.map(o=>qLab(o.q)),{W:w2,H:140,zero:1,fmt:v=>f(v,0)+'%'})}`+lg([['#d33a34','ROE'],['#727e8c','ROA']])+`</div></div>`;
    if(lr&&lr.dpm!=null)h+=`<div class=note style="margin-top:8px">ROE 拆解（近四季）：淨利率 <b>${pc(lr.dpm)}</b> × 資產週轉 <b>${f(lr.dat,2)}</b> 次 × 權益乘數 <b>${f(lr.dem,2)}</b> 倍 ＝ ROE <b>${pc(lr.roe)}</b></div>`;}
  else h+=`<div class=st>這檔的完整損益表資料還沒補齊（目前只有 EPS）。</div>`;
  h+=`</section>`;
  /* 5 財務體質 */
  const qb=Q.filter(o=>o.ta!=null).slice(-12);const lb=lastQ(C,'ta');
  h+=`<section class=csec id=co-bs><h3>財務體質<span class=sub>資產負債與現金流量</span></h3>`;
  if(lb){h+=`<div class="kpis kps">`+kp('負債比','負債比',pc(lb.dr),`總負債 ${yi(lb.tl)} 億`)+kp('流動比','流動比',lb.cr==null?'—':f(lb.cr*100,0)+'%','流動資產 ÷ 流動負債')+
      kp('每股淨值','',f(lb.bvps,2)+' 元',`股東權益 ${yi(lb.eqp)} 億`)+`</div>`;
    h+=`<div class=cbox style="margin-top:10px"><h4>負債比與每股淨值</h4>${svgLines([{v:qb.map(o=>o.dr==null?null:o.dr*100),c:'#b45309',n:'負債比'}],qb.map(o=>qLab(o.q)),{W:w,H:110,fmt:v=>f(v,0)+'%'})}${svgBars(qb.map(o=>o.bvps),qb.map(o=>qLab(o.q)),{W:w,H:100,fmt:v=>f(v,1),col:()=>'#8fa6c8',al:'每股淨值'})}<div class=st>上：負債比；下：每股淨值（元）</div></div>`;}
  else h+=`<div class=st>這檔的資產負債資料還沒補齊。</div>`;
  const lc=lastQ(C,'ocf4');
  if(lc){const qc=Q.filter(o=>o.ocf4!=null).slice(-12);
    h+=`<div class="kpis kps" style="margin-top:10px">`+kp('營業現金流','',yi(lc.ocf4)+' 億','近四季')+kp('自由現金流','自由現金流',lc.fcf4==null?'—':yi(lc.fcf4)+' 億','營業＋投資現金流，近四季',cls(lc.fcf4))+
      kp('現金流 ÷ 淨利','現金流 ÷ 淨利',lc.ni4>0?f(lc.ocf4/lc.ni4*100,0)+'%':'—','100% 以上＝獲利有收到現金')+`</div>`+
      `<div class=cbox style="margin-top:10px"><h4>近四季營業現金流與淨利（億）</h4>${svgLines([{v:qc.map(o=>o.ocf4/100),c:'#2563c9',n:'營業現金流'},{v:qc.map(o=>o.ni4==null?null:o.ni4/100),c:'#d33a34',n:'淨利'},{v:qc.map(o=>o.fcf4==null?null:o.fcf4/100),c:'#a16207',n:'自由現金流',dash:1}],qc.map(o=>qLab(o.q)),{W:w,H:130,zero:1,fmt:v=>f(v,0)})}`+
      lg([['#2563c9','營業現金流'],['#d33a34','淨利（歸屬母公司）'],['#a16207','自由現金流',1]])+`</div>`;}
  h+=`</section>`;
  /* 6 估值 */
  h+=`<section class=csec id=co-val><h3>估值<span class=sub>和自己的歷史比${gi('本益比位置')}</span></h3>`;
  const pes=M.filter(o=>o.pe!=null&&o.pe>0&&o.pe<300),pe5=pes.slice(-60).map(o=>o.pe);
  if(pe&&pe5.length>=24&&ttm){const p20=quantile(pe5,.2),p50=quantile(pe5,.5),p80=quantile(pe5,.8);const pctl=Math.round(100*pes.filter(o=>o.pe<pe).length/pes.length);
    const a=p20*ttm.ttm,b=p80*ttm.ttm,m=p50*ttm.ttm,lo=Math.min(a,px)*0.8,hi=Math.max(b,px)*1.15;const pos=v=>Math.max(0,Math.min(100,(v-lo)/(hi-lo)*100));
    h+=`<div class=colead>本益比 ${f(pe,1)} 倍，位於自己 ${pes[0].ym.slice(0,4)} 年以來的第 ${pctl} 百分位${pctl>=80?'（偏高）':pctl<=20?'（偏低）':''}。</div>`+
      `<div class=vband><div class=bg></div><div class=bd style="left:${pos(a)}%;width:${Math.max(1,pos(b)-pos(a))}%"></div><div class=md style="left:${pos(m)}%"></div><div class=now style="left:${pos(px)}%" title="現價 ${fp(px)}"></div></div>`+
      `<div class=vlab><span>${fp(lo)}</span><span>現價 ${fp(px)}</span><span>${fp(hi)}</span></div>`+
      `<div class=st style="margin-top:6px">近五年本益比 20／50／80 百分位 ${f(p20,1)}／${f(p50,1)}／${f(p80,1)} 倍，乘上近四季 EPS ${f(ttm.ttm,2)} 元，換算 <b>${fp(a)}</b>／<b>${fp(m)}</b>／<b>${fp(b)}</b> 元（色帶＝20～80 百分位，豎線＝中位數）。這是歷史評價換算的位置，倍數會隨獲利與市場改變。</div>`;}
  else h+=`<div class=st>${ttm&&ttm.ttm<=0?'近四季 EPS 為負，本益比不適用。':'本益比歷史不足兩年，暫不顯示位置。'}</div>`;
  const pbs=M.filter(o=>o.pb!=null);if(pb&&pbs.length>=24){const pp=Math.round(100*pbs.filter(o=>o.pb<pb).length/pbs.length);h+=`<div class=st style="margin-top:4px">淨值比 ${f(pb,2)} 倍，位於自己歷史的第 ${pp} 百分位。</div>`;}
  h+=`</section>`;
  /* 7 股利 */
  const dy=divYears(C),ys=Object.keys(dy).sort().slice(-8);const aeM={};annualEps(C).forEach(([y,e])=>aeM[y]=e);
  h+=`<section class=csec id=co-dv><h3>股利<span class=sub>依除權息日歸年度</span></h3>`;
  if(ys.length){h+=`<div class=tw><table class=qt><thead><tr><th>年度</th><th>現金股利</th><th>前一年 EPS</th><th>配發率</th></tr></thead><tbody>`+
      ys.slice().reverse().map(y=>{const d=dy[y],e=aeM[String(+y-1)];return `<tr><td>${y}</td><td>${f(d.c,2)}${d.unk?` <span class=mu>＋配股${d.unk>1?' '+d.unk+' 次':''}</span>`:''}</td><td>${e==null?'—':f(e,2)}</td><td>${e>0&&d.c?f(d.c/e*100,0)+'%':'—'}</td></tr>`;}).join('')+`</tbody></table></div>`;}
  else h+=`<div class=st>2013 年以來沒有除權息紀錄。</div>`;
  h+=`</section>`;
  /* 8 季報明細 */
  const qt=Q.filter(o=>o.rev!=null||o.eps!=null).slice(-12).reverse();
  h+=`<section class=csec id=co-qt><h3>季報明細<span class=sub>單季、金額單位億元</span></h3><details class=mr${isPane()?' open':''}><summary>近 ${qt.length} 季</summary><div class=tw><table class=qt><thead><tr><th>季別</th><th>營收</th><th>年增</th><th>毛利率</th><th>營益率</th><th>淨利率</th><th>EPS</th><th>EPS 年增</th><th>業外</th></tr></thead><tbody>`+
    qt.map(o=>`<tr><td>${qLab(o.q)}</td><td>${yi(o.rev)}</td><td>${psg(o.ry)}</td><td>${pc(o.gm)}</td><td>${pc(o.om)}</td><td>${pc(o.nm)}</td><td>${o.eps==null?'—':f(o.eps,2)}</td><td>${psg(o.ey)}</td><td>${yi(o.nonop)}</td></tr>`).join('')+`</tbody></table></div></details>`+
    `<div class=st style="margin-top:6px">資料：公開資訊觀測站綜合損益表、資產負債表彙總（2013 年起）、月營收彙總；單季數字＝當年累計相減，可能和公司公告的單季數差一點。財報以法定公告期限後才算進本益比。本段整理數據現況，不構成投資建議。</div></section>`;
  return h;}
function coNav(){return [['co-sum','公司分析'],['co-sx','飆股檢查'],['co-gr','成長'],['co-pf','獲利'],['co-bs','體質'],['co-val','估值'],['co-dv','股利'],['co-qt','季報']];}
/* 個股卡裡的一段（page.py renderStock 呼叫）：資料還沒到就先放「載入中」、到了重畫 */
function coSec(c,W,re){if(CO[c]&&(MT||MTERR))return coBody(c,W);
  Promise.all([coLoad(c),mtLoad().catch(()=>null)]).then(()=>re&&re(),()=>{CO[c]=CO[c]||null;const el=$('#co-ld');if(el)el.innerHTML='公司資料暫時無法載入　<a id=co-rt>重試</a>';const b=$('#co-rt');if(b)b.onclick=()=>{COP[c]=null;re&&re();};});
  return `<section class=csec id=co-sum><h3>公司分析</h3><div class=ld id=co-ld>公司資料載入中…</div></section>`;}
/* 不在籌碼雷達範圍的公司：只有公司分析的卡片 */
function renderCo(c,keep){const dv=$('#dv'),pane=isPane(),st0=keep?dv.scrollTop:0;
  dv.classList.toggle('pane',pane);document.body.classList.toggle('pane',pane);dv.hidden=false;lockBody(!pane);
  const W=Math.max(300,Math.floor($('#dvin').clientWidth-32));const C=CO[c],r=mtRow(c);const nm=C?C.doc.n:((COIX||[]).find(x=>x[0]===c)||[])[1]||c;
  const mk=C?(C.doc.mk==='tp'?'上櫃':'上市'):'';
  let h=`<div class=dvh><div class=dvt><div class=ttl><b>${esc(nm)}</b><span class=cd>${esc(c)}${mk?' · '+mk:''}${C&&C.doc.ind?' · '+esc(C.doc.ind):''}</span></div>`+
    `<div class=pxw><b>${r?fp(r.px):''}</b>${r&&r.ch!=null?sgn(r.ch,2,'%'):''}</div><a class=x id=x title="關閉（Esc）">×</a></div>`+
    `<nav class=cnav>${coNav().map(([id,t])=>`<a data-cto=${id}>${t}</a>`).join('')}</nav></div>`;
  h+=coSec(c,W,()=>renderCo(c,true));
  $('#dvin').innerHTML=h;dv.scrollTop=st0;$('#x').onclick=closeStock;
  $$('#dvin [data-cto]').forEach(a=>a.onclick=()=>{const t=document.getElementById(a.dataset.cto);if(t)dv.scrollTo({top:dv.scrollTop+t.getBoundingClientRect().top-dv.getBoundingClientRect().top-$('#dvin .dvh').offsetHeight+2,behavior:'smooth'});});
  cspy();}
function openCo(c){if(BY[c]){COJ=c;openStock(c);return;}location.hash='co='+encodeURIComponent(c);}
window.addEventListener('hashchange',()=>{const m=location.hash.match(/^#co=(.+)$/);if(m)renderCo(decodeURIComponent(m[1]));});
{const m=location.hash.match(/^#co=(.+)$/);if(m)renderCo(decodeURIComponent(m[1]));}
/* 個股卡渲染後：從「查公司」來的就捲到公司分析 */
function coAfterStock(c){if(COJ!==c)return;const t=document.getElementById('co-sum'),dv=$('#dv');if(!t)return;
  if(CO[c])COJ=null;dv.scrollTo({top:dv.scrollTop+t.getBoundingClientRect().top-dv.getBoundingClientRect().top-$('#dvin .dvh').offsetHeight+2});}

/* ---- 查公司（頂欄）：第一次點才下載代號表 ---- */
(function(){const q=$('#coq'),dd=$('#coqd');if(!q)return;let hits=[],sel=0;
  function show(){const s=q.value.trim();if(!s||!COIX){dd.hidden=true;return;}const sl=s.toLowerCase();
    hits=COIX.filter(x=>x[0].startsWith(s)||String(x[1]).toLowerCase().includes(sl)).slice(0,8);sel=0;
    dd.innerHTML=hits.length?hits.map((x,i)=>`<a data-c="${esc(x[0])}" class="${i===0?'on':''}"><b>${esc(x[1])}</b><span class=cd>${esc(x[0])} · ${x[2]==='tp'?'上櫃':'上市'}</span></a>`).join(''):'<a>查無此公司</a>';
    dd.hidden=false;$$('#coqd a[data-c]').forEach(a=>a.onmousedown=e=>{e.preventDefault();pick(a.dataset.c);});}
  function pick(c){dd.hidden=true;q.value='';q.blur();openCo(c);}
  q.addEventListener('focus',()=>{coIdx().then(show,()=>{dd.innerHTML='<a>代號表暫時無法載入</a>';dd.hidden=false;});mtLoad().catch(()=>{});});
  q.addEventListener('input',show);q.addEventListener('blur',()=>setTimeout(()=>dd.hidden=true,150));
  q.addEventListener('keydown',e=>{if(dd.hidden||!hits.length)return;if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();sel=(sel+(e.key==='ArrowDown'?1:hits.length-1))%hits.length;$$('#coqd a').forEach((a,i)=>a.classList.toggle('on',i===sel));}
    else if(e.key==='Enter'){e.preventDefault();pick(hits[sel][0]);}});})();
Object.assign(GL,{'五面向':'成長（近 3 月營收年增、最新季 EPS 年增）、獲利（近四季 ROE、營益率）、體質（負債比、流動比）、估值（本益比、淨值比，越便宜分數越高）、動能（RS、距 52 週高點）。每項先算在全市場的百分位，兩項平均後分 5 格：80 以上頂尖、60 以上良好、40 以上中性、20 以上偏弱、其餘落後。',
  '飆股體質檢查':'《超級績效》（Minervini）找飆股看的條件：盈餘與營收高成長而且加速、毛利率擴張、股價在上升趨勢（趨勢樣板 8 項）、相對強度高。旁邊的比例是 2014 年起這個條件成立的股票，之後一年內最高價曾達兩倍的比例，和平常相比。',
  '趨勢樣板':'Minervini 的 8 項：股價在 150 與 200 日線之上、150 日線高於 200 日線、200 日線上揚、50 日線高於 150 與 200 日線、股價在 50 日線之上、比 52 週低點高 30% 以上、在 52 週高點 25% 以內、RS ≥ 70。',
  'RS 百分位':'相對強度：0.4×近 3 個月＋0.2×近 6 個月＋0.2×近 9 個月＋0.2×近 12 個月報酬，在全市場排名（1～99，越高越強）。',
  '營收加速':'近 3 個月營收年增率比再前 3 個月的年增率高。Code 33＝EPS 年增、營收年增、毛利率連續三季一起變好。',
  'ROE 拆解':'ROE＝淨利率 × 資產週轉 × 權益乘數：賺錢的效率、資產用得多勤、用了多少槓桿。三者都用近四季。',
  '自由現金流':'營業活動現金流＋投資活動現金流（近四季）。投資活動含資本支出與買賣金融資產，所以是粗略的自由現金流。',
  '現金流 ÷ 淨利':'近四季營業現金流 ÷ 近四季淨利。長期低於 100% 代表帳上獲利沒有變成現金（應收帳款或存貨堆高）。',
  '本益比位置':'每個月底的股價 ÷ 當時已公告的近四季 EPS，和這檔自己過去的本益比比。百分位越高代表以自己的歷史來看越貴；換算價位只是估值位置，不是價格預測。'});
GLG.push(['公司分析',['五面向','飆股體質檢查','趨勢樣板','RS 百分位','營收加速','ROE 拆解','自由現金流','現金流 ÷ 淨利','本益比位置']]);
"""

SEARCH_HTML = ('<div class="cos"><input type="search" id="coq" placeholder="查公司：代號或名稱" autocomplete="off" '
               'aria-label="查公司"><div id="coqd" class="coqd" hidden></div></div>')
