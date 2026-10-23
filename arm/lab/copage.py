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
.seg.s5 i,.seg.s4 i:nth-child(-n+4){background:var(--gain)}.seg.s3 i:nth-child(-n+3){background:var(--mut2)}
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
.vband .bd{position:absolute;top:10px;height:8px;background:var(--band);border-radius:4px}.vband .md{position:absolute;top:6px;width:2px;height:16px;background:var(--accd)}
.vband .now{position:absolute;top:2px;width:2px;height:24px;background:var(--ink)}
.vlab{display:flex;justify-content:space-between;font-size:12px;color:var(--mut)}
.qt td,.qt th{padding:5px 7px;font-size:13px}.qt td:first-child,.qt th:first-child{text-align:left}
.sxt td,.sxt th{padding:6px 8px;font-size:13.5px;vertical-align:top}.chkt{width:100%}.chkt td,.chkt th{padding:6px 8px;font-size:13.5px;vertical-align:top;white-space:normal}.chkt td.l,.chkt th.l{text-align:left}.chkt .ok{color:var(--gain);font-weight:700}.chkt .no{color:var(--mut)}.chkt .na{color:var(--mut)}.chkt td:not(.l),.chkt th:not(.l){white-space:nowrap;width:1%}.sxt td.l,.sxt th.l{text-align:left}
.sxt .sm2{font-size:12px;color:var(--mut)}.wlst{display:inline-block;padding:0 6px;border-radius:8px;font-size:12px;background:var(--card2);color:var(--ink2);white-space:nowrap}.wlst.s1,.wlst.s2{background:var(--gainbg);color:var(--gain);font-weight:700}.wlst.s3{background:var(--hlbg);color:var(--accd);font-weight:700}.wlst.s4,.wlst.s5{color:var(--mut)}.sxt td.l{white-space:normal;min-width:150px}.sxt .wlp{text-align:left;white-space:normal;min-width:86px}.sxt .wlb{text-align:left;white-space:normal;min-width:118px}.sxt .mo{display:none}.sxt .wlp .mo{margin-top:3px;font-size:12.5px}.sxall{display:inline-block;margin-top:6px;cursor:pointer}.sxi{display:inline-block;padding:0 6px;border-radius:8px;background:var(--hlbg);font-size:12px;margin:1px 2px 1px 0}
.fcev{list-style:none;margin:6px 0 0;padding:0}.fcev li{padding:5px 0;border-bottom:1px solid var(--line);font-size:13px}.fcev li span:first-child{display:inline-block;min-width:3.6em;color:var(--mut)}
.qt tr.me td{background:var(--hlbg)}.qt .sm2{font-size:12px;color:var(--mut)}.sxt a.fcl{display:block;color:var(--ink2);cursor:pointer}.sxt a.fcl:hover{color:var(--acc);text-decoration:underline}
.fcev a{margin-left:4px;font-size:12px}
@media (max-width:640px){.cgrid{grid-template-columns:minmax(0,1fr)}.co5 .r{grid-template-columns:2.6em 2.8em 54px minmax(0,1fr)}.cos{flex-basis:100%;order:4}
  .chk li{grid-template-columns:1.4em minmax(0,1fr)}.chk .hr{grid-column:2;text-align:left;white-space:normal}
  .sxt .hm{display:none}.sxt .mo{display:block}}
"""

JS = r"""
/* ===== 公司分析（docs/lab_company_plan.md 第 5 節）：點進去才下載 co/{代號}.json；第一次另抓全市場小表 x9t.json ===== */
const CO={},COP={},MTS={};let MT=null,MTP=null,MTERR=false,COIX=null,COIXP=null,COJ=null,COSEC=null,FC=null,FCP=null,FCERR=false,COIXM=null;
function getJ(u){return fetch(u).then(r=>{if(!r.ok)throw new Error('HTTP '+r.status);return r.json();});}
function coLoad(c){if(CO[c])return Promise.resolve(CO[c]);if(!COP[c])COP[c]=getJ(`co/${encodeURIComponent(c)}.json?v=${encodeURIComponent(D.mtv||'')}`).then(j=>(CO[c]=coParse(j)),e=>{COP[c]=null;throw e;});return COP[c];}
function mtLoad(){if(MT)return Promise.resolve(MT);if(!MTP)MTP=getJ('x9t.json?v='+encodeURIComponent(D.mtv||'')).then(j=>(MT=j),e=>{MTP=null;MTERR=true;throw e;});return MTP;}
function coIdx(){if(COIX)return Promise.resolve(COIX);if(!COIXP)COIXP=getJ('co/index.json?v='+encodeURIComponent(D.mtv||'')).then(j=>(COIX=j.s||[]),e=>{COIXP=null;throw e;});return COIXP;}
function fcLoad(){if(FC)return Promise.resolve(FC);if(!FCP)FCP=getJ('x9f.json?v='+encodeURIComponent(D.fcv||'')).then(j=>(FC=j),e=>{FCP=null;FCERR=true;throw e;});return FCP;}
function coNm(c){if(!COIXM&&COIX){COIXM={};COIX.forEach(x=>COIXM[x[0]]=x[1]);}return (COIXM&&COIXM[c])||((D.names||{})[c])||c;}
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
function divYears(C){const y={};for(const [d,cash,t] of C.DV){const yr=d.slice(0,4);y[yr]=y[yr]||{c:0,n:0,unk:0,nn:0};if(cash!=null)y[yr].c+=cash;else y[yr].nn++;if(t!=='息')y[yr].unk++;y[yr].n++;}return y;}
function quantile(a,p){if(!a.length)return null;const s=[...a].sort((x,y)=>x-y);const i=(s.length-1)*p,lo=Math.floor(i),hi=Math.ceil(i);return s[lo]+(s[hi]-s[lo])*(i-lo);}
const yi=x=>x==null?'—':f(x/100,x>=1e5?0:1);   /* 百萬元 → 億 */
const pc=(x,d=1)=>x==null?'—':f(x*100,d)+'%';
const psg=(x,d=1)=>x==null?'<span class=mu>—</span>':x==='轉盈'?'<span class=up>轉盈</span>':sgn(x*100,d,'%');

/* ---- 小圖（SVG） ---- */
function svgBars(vals,labs,o={}){const W=o.W||520,H=o.H||140,pt=16,pl=4,pr=4,n=vals.length;if(!n)return '';
  const xs=vals.filter(v=>v!=null);const mx=Math.max(0,...xs),mn=Math.min(0,...xs);
  const pb=mn<0&&n<=12&&o.vt!==false?30:18;          /* 負值的數字標在柱子下方，留位置給它，不壓到 X 軸標籤 */const rg=(mx-mn)||1;const y=v=>pt+(mx-v)/rg*(H-pt-pb);
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
  for(let i=0;i<n-1;i+=step){const p=pos(i);if(p.l<pr+10||p.r>last.l-10)continue;out.push(p);pr=p.r;}
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
function coDims(r,fin){return CODIM.map(([nm,ms])=>{const ps=[],txt=[];
  if(fin&&nm==='體質')return {nm,lv:0,t:'金融業的負債主要是存款與保單，負債比天生高，不和一般公司比'};
  for(const [k,dir,lab,u] of ms){const v=r?r[k]:null;const p=mtPct(k,v);if(p==null)continue;const q=dir>0?p:100-p;ps.push(q);
    txt.push(`${lab} ${dimFmt(k,v,u)}，${dir>0?'高':'低'}於全市場 ${dir>0?p:100-p}%`);}
  if(!ps.length)return {nm,lv:0,t:'資料不足'};const a=ps.reduce((x,y)=>x+y,0)/ps.length;const lv=a>=80?5:a>=60?4:a>=40?3:a>=20?2:1;return {nm,lv,t:txt.join('；')};});}
function dimLead(ds){const good=ds.filter(d=>d.lv>=4).map(d=>d.nm+(d.nm==='估值'?LVV[d.lv]:LVN[d.lv])),bad=ds.filter(d=>d.lv&&d.lv<=2).map(d=>d.nm+(d.nm==='估值'?LVV[d.lv]:LVN[d.lv]));
  return (good.length?good.join('、'):'')+(good.length&&bad.length?'；':'')+(bad.length?bad.join('、'):'')+(good.length||bad.length?'。':'各面向都在中間。');}
const TTN=['股價在 150 日與 200 日線之上','150 日線高於 200 日線','200 日線上揚（比 20 日前高）','50 日線高於 150、200 日線','股價在 50 日線之上','股價比 52 週低點高 30% 以上','股價在 52 週高點 25% 以內','RS ≥ 70'];
const SXCK=[['ey25','最新一季 EPS 比去年同季多 25% 以上',r=>r.ey==null?null:r.ey>=25],['eacc','EPS 成長在加速（這一季的成長率比上一季高）',r=>r.eacc==null?null:r.eacc>0],
  ['ry25','近 3 個月營收比去年同期多 25% 以上',r=>r.ry3==null?null:r.ry3>=25],['racc','營收成長在加速（近 3 個月的成長率比前 3 個月高）',r=>r.racc==null?null:r.racc>0],
  ['rnh','月營收創 12 個月新高',r=>r.rnh==null?null:r.rnh===true],['gmd','毛利率比去年同季高',r=>r.gmd==null?null:r.gmd>0],
  ['c33','連三季變好：EPS 成長率、營收成長率、毛利率都一季比一季高',r=>r.c33==null?null:r.c33===true],['roe15','近四季 ROE（股東權益報酬率）15% 以上',r=>r.roe==null?null:r.roe>=15],
  ['tt8','股價趨勢 8 項全過（長期上升趨勢）',r=>r.tt==null?null:r.tt===8],['rs80','股價強度 RS 80 以上（近一年漲幅勝過八成股票）',r=>r.rs==null?null:r.rs>=80],['h25','股價離 52 週高點 25% 以內',r=>r.d52h==null?null:r.d52h>=-25]];
function ckHit(k){const x=(((D.sx||{}).ck)||{})[k];if(!x||!x.A||x.A.p==null)return '—';const P=Math.round(x.A.p*100),B=Math.round((x.A.base||0)*100);return P>B?`<b>${P}%</b>`:`${P}%`;}
function ckBase(){const xs=Object.values(((D.sx||{}).ck)||{}).map(x=>x&&x.A&&x.A.base).filter(x=>x!=null);return xs.length?xs[0]:null;}

/* ---- 主體 ---- */
function coBody(c,W){const C=CO[c],r=mtRow(c);if(!C)return '';const Q=C.Q,M=C.M;const w=Math.max(260,W);const w2=isPane()||w>700?Math.floor((w-12)/2):w;
  const lq=lastQ(C,'eps'),lm=[...M].reverse().find(o=>o.rev!=null),lp=[...M].reverse().find(o=>o.px!=null);
  const px=r&&r.px!=null?r.px:(lp?lp.px:null);const ttm=lastQ(C,'ttm');const bvq=lastQ(C,'bvps');
  const pe=r&&r.pe!=null?r.pe:(px&&ttm&&ttm.ttm>0?px/ttm.ttm:null),pb=r&&r.pb!=null?r.pb:(px&&bvq&&bvq.bvps>0?px/bvq.bvps:null);
  const sh=lp&&lp.sh?lp.sh:null;const cap=r&&r.cap!=null?r.cap:(px&&sh?px*sh*1000/1e8:null);
  let h='';
  /* 1 摘要 */
  const fin=/金融/.test(C.doc.ind||''),ds=r?coDims(r,fin):[];
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
    const kb=ckBase();
    h+=`<section class=csec id=co-sx><h3>飆股體質檢查<span class=sub>符合 ${ok}／${av} 項${gi('飆股體質檢查')}</span></h3>`+
      (kb!=null?`<div class=st>右欄＝過去符合這一條的股票，3 個月內漲到五成的比例；一般股票是 ${f(kb*100,0)}%，比它高的標粗體。</div>`:'')+
      `<div class=tw><table class=chkt><thead><tr><th class=l>條件</th><th>這檔</th>${kb!=null?'<th>3 個月內漲五成</th>':''}</tr></thead><tbody>`+
      it.map(x=>`<tr><td class=l>${esc(x.t)}</td><td><span class=${x.v===true?'ok':x.v===false?'no':'na'}>${x.v===true?'✓ 符合':x.v===false?'✗':'—'}</span></td>${kb!=null?`<td>${ckHit(x.k)}</td>`:''}</tr>`).join('')+`</tbody></table></div>`;
    if(r.ttb)h+=`<details class=mr><summary>趨勢樣板 8 項明細（${r.tt}／8）${gi('趨勢樣板')}</summary><ul class=chk>${TTN.map((t,i)=>`<li><span class=${r.ttb[i]==='1'?'ok':'no'}>${r.ttb[i]==='1'?'✓':'✗'}</span><span>${esc(t)}</span><span></span></li>`).join('')}</ul></details>`;
    const cb=((((D.sx||{}).cnt)||{}).A)||{},cr=(cb.rows||[])[ok];
    if(cr&&cr.p!=null&&cr.n>=30)h+=`<div class=note style="margin-top:8px">過去同樣符合 ${ok} 項的股票，3 個月內漲到五成的比例是 <b>${f(cr.p*100,0)}%</b>（一般股票 ${f((cb.base||0)*100,0)}%）。</div>`;
    const hit=(((D.sx||{}).hits)||{})[c];if(hit&&hit.length)h+=`<div class=note style="margin-top:8px">今天符合飆股規則 ${hit.map(i=>{const u=(D.sx.rules||[])[i]||{};return `<span class=sxi title="${esc(u.txt||'')}">${esc(u.lab||'')}${i+1}</span>`;}).join('')}（${hit.length===1?esc(((D.sx.rules||[])[hit[0]]||{}).txt||''):'共 '+hit.length+' 條'}；<a data-go="opp" data-at="o-sx">看規則與過去成績</a>）</div>`;
    h+=`</section>`;}
  h+=fcSec(c,C,px)+indSec(c,r);
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
  if(qp.length){const ms=[['gm','#a16207','毛利率','毛利率'],['om','#2563c9','營益率','營益率'],['nm','#d33a34','淨利率','淨利率（歸屬母公司）']]
      .filter(([k])=>qp.some(o=>o[k]!=null));          /* 金融業沒有毛利、營業利益：沒資料的線和圖例都不畫 */
    h+=`<div class=cgrid><div class=cbox><h4>${ms.map(m=>m[2]).join('・')}（單季）</h4>${svgLines(ms.map(([k,c,n])=>({v:qp.map(o=>o[k]==null?null:o[k]*100),c,n})),qp.map(o=>qLab(o.q)),{W:w2,H:140,fmt:v=>f(v,0)+'%'})}`+
      lg(ms.map(([,c,,t])=>[c,t]))+`</div>`;
    const qr=Q.filter(o=>o.roe!=null).slice(-12);
    h+=`<div class=cbox><h4>近四季 ROE・ROA</h4>${svgLines([{v:qr.map(o=>o.roe*100),c:'#d33a34',n:'ROE'},{v:qr.map(o=>o.roa==null?null:o.roa*100),c:'#727e8c',n:'ROA'}],qr.map(o=>qLab(o.q)),{W:w2,H:140,zero:1,fmt:v=>f(v,0)+'%'})}`+lg([['#d33a34','ROE'],['#727e8c','ROA']])+`</div></div>`;
    if(lr&&lr.dpm!=null)h+=`<div class=note style="margin-top:8px">ROE 拆解（近四季）：淨利率 <b>${pc(lr.dpm)}</b> × 資產週轉 <b>${f(lr.dat,lr.dat<0.1?3:2)}</b> 次 × 權益乘數 <b>${f(lr.dem,lr.dem>=10?1:2)}</b> 倍 ＝ ROE <b>${pc(lr.roe)}</b></div>`;}
  else h+=`<div class=st>這檔的完整損益表資料還沒補齊（目前只有 EPS）。</div>`;
  h+=`</section>`;
  /* 5 財務體質 */
  const qb=Q.filter(o=>o.ta!=null).slice(-12);const lb=lastQ(C,'ta');
  h+=`<section class=csec id=co-bs><h3>財務體質<span class=sub>資產負債與現金流量</span></h3>`;
  if(lb){h+=`<div class="kpis kps">`+kp('負債比','負債比',pc(lb.dr),`總負債 ${yi(lb.tl)} 億`)+kp('流動比','流動比',lb.cr==null?'—':f(lb.cr*100,0)+'%','流動資產 ÷ 流動負債')+
      kp('每股淨值','',f(lb.bvps,2)+' 元',`股東權益 ${yi(lb.eqp)} 億`)+`</div>`;
    h+=`<div class=cbox style="margin-top:10px"><h4>負債比與每股淨值</h4>${svgLines([{v:qb.map(o=>o.dr==null?null:o.dr*100),c:'#b45309',n:'負債比'}],qb.map(o=>qLab(o.q)),{W:w,H:110,fmt:v=>f(v,0)+'%'})}${svgBars(qb.map(o=>o.bvps),qb.map(o=>qLab(o.q)),{W:w,H:100,fmt:v=>f(v,1),col:()=>'#8fa6c8',al:'每股淨值'})}<div class=st>上：負債比；下：每股淨值（元）</div></div>`;}
  else h+=`<div class=st>這檔的資產負債資料還沒補齊。</div>`;
  const lc=fin?null:lastQ(C,'ocf4');                   /* 金融業的營業現金流主要是存放款進出，不看 */
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
      ys.slice().reverse().map(y=>{const d=dy[y],e=aeM[String(+y-1)],cc=d.nn&&!d.c?'<span class=mu>現金部分未知</span>':f(d.c,2)+(d.nn?' <span class=mu>＋未知</span>':'');return `<tr><td>${y}</td><td>${cc}${d.unk?` <span class=mu>＋配股${d.unk>1?' '+d.unk+' 次':''}</span>`:''}</td><td>${e==null?'—':f(e,2)}</td><td>${e>0&&d.c&&!d.nn?f(d.c/e*100,0)+'%':'—'}</td></tr>`;}).join('')+`</tbody></table></div>`;}
  else h+=`<div class=st>2013 年以來沒有除權息紀錄。</div>`;
  h+=`</section>`;
  /* 8 季報明細 */
  const qt=Q.filter(o=>o.rev!=null||o.eps!=null).slice(-12).reverse();
  h+=`<section class=csec id=co-qt><h3>季報明細<span class=sub>單季、金額單位億元</span></h3><details class=mr${isPane()?' open':''}><summary>近 ${qt.length} 季</summary><div class=tw><table class=qt><thead><tr><th>季別</th><th>營收</th><th>年增</th><th>毛利率</th><th>營益率</th><th>淨利率</th><th>EPS</th><th>EPS 年增</th><th>業外</th></tr></thead><tbody>`+
    qt.map(o=>`<tr><td>${qLab(o.q)}</td><td>${yi(o.rev)}</td><td>${psg(o.ry)}</td><td>${pc(o.gm)}</td><td>${pc(o.om)}</td><td>${pc(o.nm)}</td><td>${o.eps==null?'—':f(o.eps,2)}</td><td>${psg(o.ey)}</td><td>${yi(o.nonop)}</td></tr>`).join('')+`</tbody></table></div></details>`+
    `<div class=st style="margin-top:6px">資料：公開資訊觀測站綜合損益表、資產負債表彙總（2013 年起）、月營收彙總；單季數字＝當年累計相減，可能和公司公告的單季數差一點。財報以法定公告期限後才算進本益比。本段整理數據現況，不構成投資建議。</div></section>`;
  return h;}
/* 法人預估（docs/lab_forward_plan.md；使用者 2026-10-16：只顯示當參考；2026-10-17：直接寫出券商估的股價、要能點到來源與是哪些法人）。
   來源怎麼挑在 fcst.view 決定（FactSet 120 天內用 FactSet，否則 Yahoo）：pe＝EPS／營收預估、pt＝券商估的股價 */
function fcGr(cur,prev){if(cur==null||prev==null)return '<span class=mu>—</span>';if(prev>0.05)return sgn((cur/prev-1)*100,0,'%');return cur>0.05&&prev<=0?'<span class=up>轉盈</span>':'<span class=mu>—</span>';}
function fcVs(tp,px){if(!tp||!px)return '';const u=(tp/px-1)*100;return Math.abs(u)<0.5?'和現價差不多':`比現價${u>0?'高':'低'} ${f(Math.abs(u),0)}%`;}
/* 來源連結：FactSet＝鉅亨網那則快訊；Yahoo＝分析師頁。「是哪些法人」＝這檔的券商報告新聞（各家券商的數字在新聞裡） */
function fcSrc(c,C,src,id,txt){const sym=c+(C&&C.doc.mk==='tp'?'.TWO':'.TW');if(src==='fs'&&!id)return txt;
  return src==='fs'?`<a href="https://news.cnyes.com/news/id/${encodeURIComponent(id)}" target=_blank rel=noopener>${txt}</a>`:
    `<a href="https://finance.yahoo.com/quote/${encodeURIComponent(sym)}/analysis/" target=_blank rel=noopener>${txt}</a>`;}
function fcWho(c,C){const nm=C?C.doc.n:coNm(c);
  return `<a href="https://news.google.com/search?q=${encodeURIComponent(nm+' 目標價')}&hl=zh-TW&gl=TW&ceid=TW%3Azh-Hant" target=_blank rel=noopener>是哪些法人（目標價新聞）</a>`;}
function fcSec(c,C,px){let h=`<section class=csec id=co-fc><h3>法人預估<span class=sub>分析師的預估${gi('法人預估')}</span></h3>`;
  if(!FC)return h+`<div class=st>${FCERR?'法人預估資料暫時無法載入。':'載入中…'}</div></section>`;
  const v=(FC.s||{})[c];if(!v||(!v.pe&&!v.pt))return h+`<div class=st>沒有分析師追蹤這檔（FactSet 調查與 Yahoo Finance 都沒有資料），多半是中小型股。</div></section>`;
  const pe=v.pe,pt=v.pt,t=v.t,y=v.y||{},ae={},ar={};annualEps(C).forEach(([yr,x])=>ae[yr]=x);
  for(const o of C.M){if(o.rev==null)continue;const yr=o.ym.slice(0,4);ar[yr]=ar[yr]||{s:0,n:0};ar[yr].s+=o.rev/100;ar[yr].n++;}   /* 億 */
  const old=x=>x&&x.old?`<span class=mu>（${md(x.d)} 的資料，之後沒有更新）</span>`:'';
  /* 目標價放最上面：一句話講清楚高還是低；只有 1 位分析師就不說中位數 */
  if(pt){const k=pt.n>1?`${pt.n} 位分析師的${pt.avg?'平均':'中位數'}`:pt.n===1?'1 位分析師':'';
    h+=`<div class=colead style="font-weight:400">目標價 <b>${fp(pt.v)}</b> 元${px?`，<b>${fcVs(pt.v,px)}</b>`:''}${k?`（${k}）`:''}${old(pt)}</div>`+
    `<div class=st>${pt.hi!=null&&pt.lo!=null&&pt.hi!==pt.lo?`最高 ${fp(pt.hi)}、最低 ${fp(pt.lo)}。`:''}來源：${fcSrc(c,C,pt.src,pt.id,pt.src==='fs'?`FactSet 調查 ${md(pt.d)}`:`Yahoo Finance ${md(FC.yd)}`)}・${fcWho(c,C)}</div>`;}
  if(pe&&(pe.rows||[]).length){const rows=pe.rows.slice(0,3),HM=k=>k>1?' class=hm':'';   /* 手機只列前兩年 */
    h+=`<div class=tw style="margin-top:8px"><table class=qt><thead><tr><th></th>${rows.map((o,k)=>`<th${HM(k)}>${o[0]} 年</th>`).join('')}</tr></thead><tbody>`+
      `<tr><td>EPS 預估（元）</td>${rows.map((o,k)=>`<td${HM(k)}><b>${o[1]==null?'—':f(o[1],2)}</b>${o[2]!=null&&o[3]!=null&&o[2]!==o[3]?`<div class=sm2>${f(o[2],2)}～${f(o[3],2)}</div>`:''}</td>`).join('')}</tr>`+
      `<tr><td>比前一年</td>${rows.map((o,k)=>`<td${HM(k)}>${fcGr(o[1],k?rows[k-1][1]:ae[String(o[0]-1)])}</td>`).join('')}</tr>`+
      `<tr><td>本益比</td>${rows.map((o,k)=>`<td${HM(k)}>${px&&o[1]>0?f(px/o[1],1)+' 倍':'—'}</td>`).join('')}</tr>`+
      (rows.some(o=>o[4]!=null)?`<tr><td>營收預估（億）</td>${rows.map((o,k)=>`<td${HM(k)}>${o[4]==null?'—':f(o[4],o[4]>=1000?0:1)}</td>`).join('')}</tr>`+
        `<tr><td>比前一年</td>${rows.map((o,k)=>{const prev=k?rows[k-1][4]:((ar[String(o[0]-1)]||{}).n===12?ar[String(o[0]-1)].s:null);return `<td${HM(k)}>${o[4]!=null&&prev>0?sgn((o[4]/prev-1)*100,0,'%'):'<span class=mu>—</span>'}</td>`;}).join('')}</tr>`:'')+
      `</tbody></table></div><div class=st>${fcSrc(c,C,pe.src,pe.id,(pe.src==='fs'?'FactSet 調查':'Yahoo Finance')+(pe.n===1?'':pe.src==='fs'?'中位數':'平均'))}（${md(pe.src==='fs'?pe.d:FC.yd)}${pe.n?`，${pe.n} 位分析師`:''}）${old(pe)}；`+
      `第一年的「比前一年」和實際 EPS、營收比，之後和前一年的預估比。${pt?'':fcWho(c,C)}</div>`;
    const cy=String(rows[0][0]),R0=rows[0][4],ms=C.M.filter(o=>o.ym.slice(0,4)===cy&&o.rev!=null);
    if(R0&&ms.length&&ms.length<12){const S=ms.reduce((a,o)=>a+o.rev/100,0),n=ms.length,lm=C.M.filter(o=>o.ym.slice(0,4)===String(cy-1)&&o.rev!=null);
      const ly=lm.filter(o=>+o.ym.slice(5,7)<=n).reduce((a,o)=>a+o.rev/100,0),LY=lm.length===12?lm.reduce((a,o)=>a+o.rev/100,0):null;
      h+=`<div class=note style="margin-top:8px">今年 1–${n} 月營收 ${f(S,S>=1000?0:1)} 億，是全年預估 ${f(R0,R0>=1000?0:1)} 億的 <b>${f(S/R0*100,0)}%</b>${LY?`（去年 1–${n} 月占全年 ${f(ly/LY*100,0)}%）`:''}。</div>`;}}
  if(t&&t.rt)h+=`<div class=st style="margin-top:6px">評等（FactSet，${md(t.d)}）：積極樂觀 ${t.rt[0]} 位、保持中立 ${t.rt[1]} 位、保守悲觀 ${t.rt[2]} 位。</div>`;
  else if(y.rc)h+=`<div class=st style="margin-top:6px">評等（Yahoo Finance）：看好 ${y.rc[0]+y.rc[1]} 位、中立 ${y.rc[2]} 位、看淡 ${y.rc[3]+y.rc[4]} 位。</div>`;
  const y0=y.y0;if(y0&&y0.t&&y0.t[0]!=null&&y0.t[2]){const tt=y0.t,rv=y0.rv||[];
    const ch=tt[2]>0&&tt[0]>0?`（${pctT((tt[0]/tt[2]-1)*100,1)}）`:`（${tt[0]>=tt[2]?'+':'−'}${f(Math.abs(tt[0]-tt[2]),2)} 元）`;
    h+=`<div class=st style="margin-top:4px">近期修正（Yahoo Finance，${md(FC.yd)}）：${String(y0.end).slice(0,4)} 年 EPS 預估平均 ${f(tt[0],2)} 元，30 天前 ${f(tt[2],2)}${ch}${tt[4]?`、90 天前 ${f(tt[4],2)}`:''}；近 30 天上修 ${rv[1]||0} 位、下修 ${rv[3]||0} 位。</div>`;}
  const ev=v.ev||[];if(ev.length)h+=`<details class=mr><summary>FactSet 最近 ${ev.length} 次調整</summary><ul class=fcev>${ev.map(x=>{const lk=x[5]?` <a href="https://news.cnyes.com/news/id/${encodeURIComponent(x[5])}" target=_blank rel=noopener>原文</a>`:'';return x[1]==='e'?
      `<li><span>${md(x[0])}</span>${x[4]} 年 EPS 中位數 ${f(x[2],2)} 調到 <b>${f(x[3],2)}</b> 元 ${x[2]>0&&x[3]>0?sgn((x[3]/x[2]-1)*100,1,'%'):''}${lk}</li>`:
      `<li><span>${md(x[0])}</span>目標價中位數 ${fp(x[2])} 調到 <b>${fp(x[3])}</b> 元 ${sgn(x[4],1,'%')}${lk}</li>`;}).join('')}</ul></details>`;
  h+=`<div class=st style="margin-top:6px">目標價、EPS 都是券商分析師的預估：FactSet 調查是多位分析師的中位數（鉅亨網「台股預估」快訊，預估有變動才發一則${FC.fs_from?`，${esc(FC.fs_from.slice(0,4))} 年起`:''}）；FactSet 超過 4 個月沒有新快訊就改用 Yahoo Finance（每天更新）。「是哪些法人」連到這檔的目標價新聞，各家券商的數字在新聞裡。分析師常常修正預估，實際數字可能差很多；不構成投資建議。</div></section>`;
  return h;}
/* 產業比較：產業別＝證交所／櫃買中心分類；產業數字由建頁算（D.ind），同業名次用 x9t 在瀏覽器排 */
function indSec(c,r){let h=`<section class=csec id=co-ind><h3>產業比較<span class=sub>同產業的公司${gi('產業比較')}</span></h3>`;
  const ii=MT?MT.cols.indexOf('ii'):-1;if(!MT||!r||ii<0||r.ii==null)return h+`<div class=st>${MT?'這檔沒有產業分類資料。':'載入中…'}</div></section>`;
  const nm=(MT.inds||[])[r.ii],I=((D.ind||{}).rows||[]).find(x=>x[0]===nm),IC=(D.ind||{}).cols||[],io=I?Object.fromEntries(IC.map((k,i)=>[k,I[i]])):null;
  const peers=Object.keys(MT.rows).filter(k=>MT.rows[k][ii]===r.ii).map(k=>Object.assign({c:k},mtRow(k))),N=peers.length,nR=((D.ind||{}).rows||[]).filter(x=>x[8]!=null).length;
  h+=`<div class=colead style="font-weight:400"><b>${esc(nm)}</b>（${N} 檔）`;
  if(io){if(io.ry3!=null)h+=`：整個產業近 3 個月營收比去年同期 ${sgn(io.ry3,1,'%')}，一般公司（中位數）${sgn(io.med3,1,'%')}${io.racc!=null?`，成長比前 3 個月${io.racc>=0?'快':'慢'} ${f(Math.abs(io.racc),1)} 個百分點`:''}。`;else h+='。';
    if(io.r60!=null)h+=`產業股價近 3 個月中位數 ${sgn(io.r60,1,'%')}${io.rk?`，在 ${nR} 個產業中排第 ${io.rk}`:''}。`;}
  h+=`</div>`;
  const M=[['ry3','營收成長',0],['gm','毛利率',0],['roe','ROE',0],['pe','本益比（由低到高）',1],['rs','股價強度',0]];
  const rk=(k,asc)=>{if(r[k]==null||(asc&&r[k]<=0))return null;const s=peers.filter(p=>p[k]!=null&&(!asc||p[k]>0)).sort((a,b)=>asc?a[k]-b[k]:b[k]-a[k]);const i=s.findIndex(p=>p.c===c);return i<0?null:[i+1,s.length];};
  const rs=M.map(([k,t,a])=>{const x=rk(k,a);return x?`${t} 第 <b>${x[0]}</b>／${x[1]}`:null;}).filter(Boolean);
  if(rs.length)h+=`<div class=st>這檔在同業的名次：${rs.join('、')}</div>`;
  const top=peers.filter(p=>p.cap!=null).sort((a,b)=>b.cap-a.cap).slice(0,6);if(!top.some(p=>p.c===c))top.push(Object.assign({c},r));
  const cell=(x,d,suf)=>x==null?'—':f(x,d)+suf;
  h+=`<div class=tw style="margin-top:6px"><table class=qt><thead><tr><th>市值前 6 大</th><th>營收成長</th><th>毛利率</th><th>ROE</th><th>本益比</th><th class=hm>RS</th></tr></thead><tbody>`+
    top.map(p=>`<tr${p.c===c?' class=me':''}><td><a data-co="${esc(p.c)}">${esc(coNm(p.c))}</a> <span class=cd>${esc(p.c)}</span><div class=sm2>${p.cap==null?'':f(p.cap,p.cap>=1000?0:1)+' 億'}</div></td><td>${p.ry3==null?'—':sgn(p.ry3,0,'%')}</td><td>${cell(p.gm,1,'%')}</td><td>${cell(p.roe,1,'%')}</td><td>${p.pe==null?'—':f(p.pe,1)}</td><td class=hm>${p.rs==null?'—':p.rs}</td></tr>`).join('')+
    `</tbody></table></div><div class=st style="margin-top:6px">營收成長＝近 3 個月營收比去年同期（到 ${esc((D.ind||{}).ym||'—')}）；毛利率、ROE、本益比用最新財報。產業別用證交所／櫃買中心的分類，範圍比較大（例如「電子零組件業」包含很多不同產品）。</div></section>`;
  return h;}
function coNav(){return [['co-sum','公司分析'],['co-sx','飆股檢查'],['co-fc','法人預估'],['co-ind','產業'],['co-gr','成長'],['co-pf','獲利'],['co-bs','體質'],['co-val','估值'],['co-dv','股利'],['co-qt','季報']];}
/* 個股卡裡的一段（page.py renderStock 呼叫）：資料還沒到就先放「載入中」、到了重畫 */
function coSec(c,W,re){if(CO[c]&&(MT||MTERR)&&(FC||FCERR)&&COIX)return coBody(c,W);
  Promise.all([coLoad(c),mtLoad().catch(()=>null),fcLoad().catch(()=>null),coIdx().catch(()=>(COIX=COIX||[]))]).then(()=>re&&re(),()=>{CO[c]=CO[c]||null;const el=$('#co-ld');if(el)el.innerHTML='公司資料暫時無法載入　<a id=co-rt>重試</a>';const b=$('#co-rt');if(b)b.onclick=()=>{COP[c]=null;re&&re();};});
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
  if(COSEC&&CO[c]&&(FC||FCERR)&&coJump(COSEC))COSEC=null;
  cspy();}
function openCo(c,sec){COSEC=sec||null;if(BY[c]){COJ=c;openStock(c);return;}location.hash='co='+encodeURIComponent(c);}
function coJump(id){const t=document.getElementById(id),dv=$('#dv');if(!t)return false;
  dv.scrollTo({top:dv.scrollTop+t.getBoundingClientRect().top-dv.getBoundingClientRect().top-$('#dvin .dvh').offsetHeight+2});return true;}
window.addEventListener('hashchange',()=>{const m=location.hash.match(/^#co=(.+)$/);if(m)renderCo(decodeURIComponent(m[1]));});
{const m=location.hash.match(/^#co=(.+)$/);if(m)renderCo(decodeURIComponent(m[1]));}
/* 個股卡渲染後：從「查公司」來的就捲到公司分析 */
function coAfterStock(c){if(COJ!==c)return;const done=CO[c]&&(MT||MTERR)&&(FC||FCERR);if(!coJump(done?(COSEC||'co-sum'):'co-sum'))return;
  if(done){COJ=null;COSEC=null;}}

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
/* ---- 機會頁「飆股候選」（superx 研究規則；docs/lab_company_plan.md 第 4.6 節） ---- */
/* 注意：機會頁一打開就會呼叫 sxSec，這段 JS 接在頁面主程式後面——頂層 const 那時還沒初始化，常數一律放函式裡 */
function sxRate(x){return x&&x.p!=null?`<b>${f(x.p*100,0)}%</b><div class=sm2>全體 ${f((x.base||0)*100,0)}%・${f(x.n,0)} 次</div>`:'<span class=mu>—</span>';}
function sxBody(full=true){const S=D.sx||{};if(!S.v)return '';const R=S.rules||[],C=S.cand||[],L=S.labs||{},A=L.A||{},Bl=L.B||{};let b='';
  const SXLB={A:'60 個交易日（約 3 個月）內最高漲 50%',B:'250 個交易日（約 1 年）內最高漲一倍'};
  const p0=x=>x==null?'—':f(x*100,0)+'%';
  if(!R.length){const sum=k=>['A','B'].reduce((t,l)=>t+(((L[l]||{})[k])||0),0);
    b+=`<div class=st>研究沒有找到夠穩的規則：試了 ${f(sum('tried'),0)} 個條件組合，樣本內通過 ${f(sum('is_pass'),0)} 個、驗證期通過 ${f(sum('val_pass'),0)} 個。改看各公司的「飆股體質檢查」。</div>`;}
  else{const u=(A.union||{}).ho||{},bd=(A.base_dist||{}).ho||{},bp=(A.base||{}).ho;
    if(u.p!=null)b+=`<div class=colead style="font-weight:400">2023 年起（規則定案之後才算）：符合任一條規則的股票，<b>${p0(u.p)}</b> 在 3 個月內最高漲到 50%，全體只有 ${p0(bp)}（${f(u.p/bp,1)} 倍）。`+
      `3 個月後平均報酬 <b>${pctT(u.fr_avg*100,1)}</b>（全體 ${pctT(bd.fr_avg*100,1)}），但只有 ${p0(u.fr_win)} 到期是賺的、中途最大跌幅中位數 ${pctT(u.dd_med*100,0)}——平均好看是靠少數大漲的股票。</div>`;
    b+=`<div class=tw><table class=sxt><thead><tr><th class=l>規則（目標：${SXLB.A}）</th><th>2023 年起符合時${gi('飆股命中率')}</th><th class=hm>2020–2022</th><th class=hm>2014–2019</th><th>今天</th></tr></thead><tbody>`+
      R.map((rr,i)=>{const h=rr.ho||{};return `<tr><td class=l><span class=sxi>${rr.lab}${i+1}</span>${esc(rr.txt)}${h.fr_avg!=null?`<div class=sm2>2023 年起符合後 3 個月：平均 ${pctT(h.fr_avg*100,0)}、${p0(h.fr_win)} 賺錢、最大跌幅中位數 ${pctT(h.dd_med*100,0)}</div>`:''}</td><td>${sxRate(rr.ho)}</td><td class=hm>${sxRate(rr.val)}</td><td class=hm>${sxRate(rr.is)}</td><td>${C.filter(x=>x[2].includes(i)).length} 檔</td></tr>`;}).join('')+`</tbody></table></div>`;
    if(full&&C.length){const N=20,row=(x,k)=>`<tr class="${k>=N?'sxmore':''}"${k>=N?' hidden':''}><td class=l><a data-co="${esc(x[0])}"><b>${esc(x[1])}</b></a> <span class=cd>${esc(x[0])}</span></td><td>${x[2].map(i=>`<span class=sxi title="${esc((R[i]||{}).txt||'')}">${R[i]?R[i].lab+(i+1):''}</span>`).join('')}</td><td>${fp(x[3])}</td><td>${x[4]==null?'—':x[4]}</td><td class=hm>${sgn(x[5],0,'%')}</td><td class=hm>${sgn(x[6],0,'%')}</td><td class=hm>${x[7]==null?'—':f(x[7],0)+'%'}</td><td class=hm>${x[8]==null?'—':f(x[8],0)+' 億'}</td></tr>`;
      b+=`<h4 class=sh>今天符合的股票（${C.length} 檔，符合條數多的在前）</h4><div class=tw><table class=sxt id=sxc><thead><tr><th class=l>股票</th><th>符合</th><th>收盤</th><th>RS${gi('RS 百分位')}</th><th class=hm>近 3 月營收年增</th><th class=hm>最新季 EPS 年增</th><th class=hm>距 52 週高點</th><th class=hm>市值</th></tr></thead><tbody>`+
        C.map(row).join('')+`</tbody></table></div>`+(C.length>N?`<a class=sxall>顯示全部 ${C.length} 檔</a>`:'');}
    else if(full)b+=`<div class=st style="margin-top:8px">今天沒有股票符合。</div>`;
    b+=`<div class=note>這 ${R.length} 條規則都要求「近四季 ROE 偏低」：過去一年賺得少或虧損，但月營收創歷史新高、股價已經轉強——獲利剛要翻轉的轉機股。研究裡 ROE 15% 以上的績優股，之後 3 個月漲 50% 的比例反而比全體低。</div>`;
    const Y=A.yearly||[];if(Y.length)b+=`<details class=mr><summary>逐年看（任一條規則 vs 全體）</summary><div class=tw><table class=sxt><thead><tr><th class=l>年</th><th>符合（股票週）</th><th>3 個月內漲 50%</th><th>全體</th></tr></thead><tbody>${Y.map(y=>`<tr><td class=l>${esc(y[0])}${y[0]>='2023'?' <span class=mu>保留期</span>':''}</td><td>${f(y[1],0)}</td><td>${y[3]==null?'—':p0(y[3])}</td><td>${p0(y[4])}</td></tr>`).join('')}</tbody></table></div></details>`;}
  const ub=(Bl.union||{}).ho||{},bb=(Bl.base_dist||{}).ho||{};
  if(Bl.n_rules&&!Bl.use&&ub.p!=null)b+=`<div class=note>另有 ${Bl.n_rules} 條「${SXLB.B}」的規則，2023 年起轉弱：命中 ${p0(ub.p)}、全體 ${p0((Bl.base||{}).ho)}（只有 ${f(ub.p/(Bl.base||{}).ho,1)} 倍），一年後報酬中位數 ${pctT(ub.fr_med*100,0)}（全體 ${pctT(bb.fr_med*100,0)}），只有 ${p0(ub.fr_win)} 賺錢——不列入候選。</div>`;
  b+=`<div class=note>規則用 2014–2019 年的資料找、2020–2022 年挑選；2023 年起的成績是規則定案之後才算的，沒有參與挑選。「符合時」＝符合那一週之後，最高價曾漲到目標的比例，期間也可能先跌；不代表之後一定漲。只看月底市值 40 億以上、日均成交值 1,000 萬以上的股票，不含大盤與總經。</div>`;
  return b;}
function sxSec(){const S=D.sx||{};if(!S.v)return '';return sec('o-sx','飆股','飆股候選',`${S.d?md(S.d)+' 收盤':''}`,sxBody());}
/* 飆股（tw-superstock-lab W1 名單、W3 交叉比對、W4 價格強度與大盤時機）：只列名單與過去統計，買哪一檔由使用者自己判斷 */
const WLST={'-1':'—',0:'打底中',1:'今天突破',2:'突破後仍在買點',3:'準備好',4:'突破失敗',5:'漲太遠'};
/* 每檔的參考價位：到買點的寫買點～追價上限與停損；還沒到的寫突破哪裡才算（52 週高點）或拉回參考（50 日線） */
function wlBuy(s,cl){const p=(s||{}).p||{},st=p.st==null?-1:p.st,K={vcp:'標準 VCP',tight:'緊密整理',pp:'爆發型'};
  if(st>=1&&st<=3&&p.piv)return `${st===3?'突破 ':''}<b>${fp(p.piv)}</b>～${fp(p.piv*1.05)}<div class=sm2>停損 ${fp(p.stop)}（${pctT((p.stop/p.piv-1)*100,1)}）・${K[p.kind]||''}</div>`;
  if(st===0&&p.hi&&cl)return `突破 ${fp(p.hi)} 才算<div class=sm2>52 週高點，還差 ${pctT((p.hi/cl-1)*100,1)}</div>`;
  if(st===5&&p.m50&&cl)return `等拉回 ${fp(p.m50)}<div class=sm2>50 日線，現價高 ${pctT((cl/p.m50-1)*100,0)}</div>`;
  if(st===4)return `等重新整理<div class=sm2>跌回樞紐下</div>`;
  return '—';}
/* 法人預估一行小字（fcst.brief：[分析師人數, 今年 EPS 比去年%, 近 30 天方向, 估價比現價%, 估價]；點了開公司卡的法人預估段） */
function fcLine(c){const b=((D.wl||{}).fc||{})[c];if(!b)return '';const [n,eg,dr,up,tp]=b,it=[];
  if(eg!=null)it.push(`今年 EPS ${eg>0?'+':''}${f(eg,0)}%`);if(dr===1)it.push('30 天上修');else if(dr===-1)it.push('30 天下修');
  if(tp)it.push(`目標價 ${fp(tp)}${up==null?'':Math.abs(up)<0.5?'（和現價差不多）':`（比現價${up>0?'高':'低'} ${f(Math.abs(up),0)}%）`}`);
  return `<a class="sm2 fcl" data-co="${esc(c)}" data-cs="co-fc">${n?`${n} 位分析師`:'分析師'}${it.length?'：'+it.join('・'):''}</a>`;}
function wlRows(L,ST,T){return L.map(x=>{const s=ST[x[0]]||{},p=s.p||{},st=p.st==null?-1:p.st;
  return `<tr><td class=l><a data-co="${esc(x[0])}"><b>${esc(x[1])}</b></a> <span class=cd>${esc(x[0])}</span>`+
    `<div class=sm2>${x[2].map(t=>esc(T[t]||t)).join('・')}</div>${fcLine(x[0])}${PK[x[0]]?`<span class=stgs>${stTags(x[0])}</span>`:''}</td>`+
    `<td class=wlp><span class="wlst s${st}">${WLST[st]}</span><div class=mo>${wlBuy(s,x[3])}</div></td>`+
    `<td>${fp(x[3])}<div class="sm2 mo">RS ${x[4]==null?'—':x[4]}</div></td><td class="wlb hm">${wlBuy(s,x[3])}</td>`+
    `<td class=hm>${x[4]==null?'—':x[4]}</td><td class=hm>${sgn(x[5],0,'%')}</td></tr>`;}).join('');}
function wlTable(L,ST,T,id,h){return `<div class=tw><table class=sxt${id?` id=${id}`:''}><thead><tr><th class=l>股票</th><th class=wlp>位置${gi('書上的買點與停損')}</th><th>收盤</th><th class="wlb hm">${h}</th><th class=hm>RS${gi('RS 百分位')}</th><th class=hm>近 3 月營收年增</th></tr></thead><tbody>${wlRows(L,ST,T)}</tbody></table></div>`;}
function wlSec(){const W=D.wl||{};if(!W.v)return sxSec();const Y=W.lay||{},ST=Y.stocks||{},C=W.cand||[],T=W.tags||{},R=Y.ps||{},MK=Y.mkt||{},MS=Y.mnow||{},YR=Y.years||[],W5=Y.w5||{};
  const CK=(Y.ck||[]).map(x=>x[0]),bit=(c,k)=>{const s=ST[c],i=CK.indexOf(k);return !!(s&&i>=0&&((s.x>>>i)&1));};
  const stOf=c=>{const p=(ST[c]||{}).p||{};return p.st==null?-1:p.st;},hiGap=x=>{const p=(ST[x[0]]||{}).p||{};return p.hi&&x[3]?p.hi/x[3]-1:9;};
  const strong=c=>bit(c,'rs90')||bit(c,'mom10'),byRs=(a,b)=>(b[4]||0)-(a[4]||0),ORD={0:0,5:1,4:2},NEAR=0.10;
  const A=C.filter(x=>{const t=stOf(x[0]);return t>=1&&t<=3;}).sort((a,b)=>stOf(a[0])-stOf(b[0])||byRs(a,b));
  const inA=new Set(A.map(x=>x[0])),wait=(a,b)=>((ORD[stOf(a[0])]??3)-(ORD[stOf(b[0])]??3))||(stOf(a[0])===0?hiGap(a)-hiGap(b):byRs(a,b));
  const S2=C.filter(x=>!inA.has(x[0])&&strong(x[0])),B=S2.filter(x=>stOf(x[0])===0&&hiGap(x)<=NEAR).sort(wait);
  const inB=new Set(B.map(x=>x[0])),B2=S2.filter(x=>!inB.has(x[0])).sort(wait),Rr=C.filter(x=>!inA.has(x[0])&&!strong(x[0])).sort(wait);
  const p0=x=>x==null?'—':f(x*100,0)+'%',per=R.per||{},P=(k,t)=>((per[k]||{})[t]||{}).B||{};
  const yr=YR.filter(y=>y.ps!=null&&y.s9!=null),win=yr.filter(y=>y.ps>y.s9).length;
  const rg=t=>{const xs=['IS','VAL','HO'].map(k=>P(k,t).p).filter(x=>x!=null);return xs.length?p0(Math.min(...xs))+'～'+p0(Math.max(...xs)):'—';};
  let b=`<div class=colead style="font-weight:400">今天名單 ${C.length} 檔：<b>到買點 ${A.length} 檔</b>、<b>快到買點 ${B.length} 檔</b>；其他強勢 ${B2.length} 檔、其餘 ${Rr.length} 檔收起來。`+
    (per.IS?`強勢的這一段過去一年內翻倍 ${rg('t1')}，名單其餘 ${rg('t2')}。`:'')+`</div>`;
  b+=spotSec();                                       /* 位置圖（stockviz.py） */
  if(MK.pass&&MS.m2!=null){const a=(MK.all||{}).s9||{},bs=(MK.all||{}).base||{},on=a[1]||{},off=a[0]||{};
    b+=`<div class=note>目前大盤：加權指數 50 日線<b>在 200 日線之${MS.m2?'上':'下'}</b>${gi('大盤 50 日線')}。2014–2022 年，50 日線在上時名單一年內翻倍 ${p0(on.p)}，在下時 ${p0(off.p)}（全部股票 ${p0(bs[1])} 對 ${p0(bs[0])}）：大盤轉弱之後一年反而比較容易翻倍，主要是大跌後全部股票一起反彈；50 日線在下的時候 9 年只出現過 ${off.runs||'—'} 段。</div>`;}
  b+=`<h4 class=sh>到買點（${A.length} 檔）</h4>`+(A.length?wlTable(A,ST,T,'wla','買點～追價上限'):`<div class=st>今天沒有股票在書上的買點。</div>`);
  b+=`<h4 class=sh>快到買點（${B.length} 檔，強勢、離 52 週高點 ${f(NEAR*100,0)}% 內）</h4>`+(B.length?wlTable(B,ST,T,'wlc','等什麼'):`<div class=st>今天沒有。</div>`);
  if(B2.length)b+=`<details class=mr><summary>其他強勢 ${B2.length} 檔（離高點較遠或已漲太遠）</summary>${wlTable(B2,ST,T,'wlb2','等什麼')}</details>`;
  if(Rr.length)b+=`<details class=mr><summary>其他 ${Rr.length} 檔（價格強度沒到前段）</summary>${wlTable(Rr,ST,T,'','等什麼')}</details>`;
  const IR=((D.ind||{}).rows||[]).filter(x=>x[8]!=null);
  if(IR.length){const th=`<thead><tr><th class=l>產業</th><th>股價</th><th>營收成長</th><th class=hm>成長加快</th></tr></thead>`;
    const row=x=>`<tr><td class=l>${esc(x[0])}<div class=sm2>${x[1]} 檔${x[9]?`・名單 ${x[9]} 檔`:''}</div></td><td>${sgn(x[7],1,'%')}</td><td>${x[3]==null?'—':sgn(x[3],0,'%')}</td><td class=hm>${x[4]==null?'—':(x[4]>0?'+':'')+f(x[4],1)+' 個百分點'}</td></tr>`;
    b+=`<h4 class=sh>產業熱度${gi('產業比較')}</h4><div class=st>股價＝產業內股票近 3 個月（60 個交易日）漲跌的中位數，列最強的 5 個產業；營收成長＝近 3 個月營收比去年同期（到 ${esc((D.ind||{}).ym||'—')}）。</div>`+
      `<div class=tw><table class=sxt>${th}<tbody>${IR.slice(0,5).map(row).join('')}</tbody></table></div>`+
      (IR.length>5?`<details class=mr><summary>全部 ${IR.length} 個產業</summary><div class=tw><table class=sxt>${th}<tbody>${IR.map(row).join('')}</tbody></table></div></details>`:'');}
  const sp=Y.specs||{},v1=sp.v1||{},v2=sp.v2||{};
  let d=`<div class=note>名單＝三份名單合併：${Object.values(T).map(esc).join('、')}（每週約 ${f(((W.lists||{})[W.chosen]||{}).ALL?.size,0)} 檔）。`+
    `強勢＝RS ≥ 90 或相對強勢前 10%；這個條件是看過 2020–2022 年的結果後才選的，能看的是每一段、每一年是不是都比較準。</div>`;
  if(per.IS)d+=`<div class=tw><table class=sxt><thead><tr><th class=l>一年內翻倍的比例</th><th>強勢</th><th>名單其餘</th><th>全部股票</th></tr></thead><tbody>`+
    [['IS','2014–2019'],['VAL','2020–2022'],['HO','2023 起']].map(([k,t])=>`<tr><td class=l>${t}</td><td>${p0(P(k,'t1').p)}<div class=sm2>每週 ${f(P(k,'t1').per_week,1)} 檔</div></td><td>${p0(P(k,'t2').p)}</td><td>${p0(((per[k]||{}).base||{}).B)}</td></tr>`).join('')+`</tbody></table></div>`;
  if(YR.length)d+=`<div class=tw><table class=sxt><thead><tr><th class=l>年</th><th>強勢</th><th>整份名單</th><th>全部股票</th><th>加權指數</th></tr></thead><tbody>${YR.map(y=>`<tr><td class=l>${esc(y.y)}</td><td>${p0(y.ps)}</td><td>${p0(y.s9)}</td><td>${p0(y.base)}</td><td>${y.taiex==null?'—':pctT(y.taiex*100,0)}</td></tr>`).join('')}</tbody></table></div>`+
    `<div class=note>一年內翻倍要等一年才知道：最近一年只算已經滿一年的週，今年還沒有結果。加權指數＝當年漲跌。</div>`;
  if(v1.lift!=null)d+=`<div class=note>交叉比對（月營收、獲利、價格強度、技術線型、階段、量價、族群 7 類，各 1 分）：分數最高的一層，2020–2022 年命中率是名單的 ${f(v1.lift,2)} 倍；`+
    `最好的兩條件組合（${esc(v2.desc||'—')}）是 ${v2.lift==null?'—':f(v2.lift,2)} 倍——都沒有比名單準，所以表上不列分數。</div>`;
  const w3=W5.v3||{},wt=W5.tt||{};
  if(w3.IS&&w3.VAL)d+=`<div class=note>《超級績效》的 VCP：照書的型態（每段回檔變小、低點逐段墊高、最後一段在整理區上半部）在台股很少見，2014–2019 年 ${w3.IS.stocks} 檔、2020–2022 年 ${w3.VAL.stocks} 檔。`+
    `一年內翻倍 ${p0(w3.IS.B)}、${p0(w3.VAL.B)}，樣板股 ${p0((wt.IS||{}).B)}、${p0((wt.VAL||{}).B)}——兩段方向相反，案例太少，無法證明比較容易翻倍。位置欄的買點用照書的判斷。</div>`;
  d+=`<div class=note>只看月底市值 40 億以上的股票；過去的比例不代表之後也一樣。</div>`;
  b+=`<details class=mr><summary>過去成績與研究結論</summary>${d}${D.sx&&D.sx.v?`<details class=mr><summary>飆股候選規則</summary>${sxBody(false)}</details>`:''}</details>`;
  return sec('o-sx','飆股','飆股',`${W.d?md(W.d)+' 收盤':''}`,b);}
document.addEventListener('click',e=>{if(e.defaultPrevented)return;const a=e.target.closest&&e.target.closest('[data-co]');if(a){e.preventDefault();openCo(a.dataset.co,a.dataset.cs);return;}
  const m=e.target.closest&&e.target.closest('.sxall');if(m){e.preventDefault();$$('#sxc tr.sxmore').forEach(t=>t.hidden=false);m.remove();}});
Object.assign(GL,{'五面向':'成長（近 3 月營收年增、最新季 EPS 年增）、獲利（近四季 ROE、營益率）、體質（負債比、流動比）、估值（本益比、淨值比，越便宜分數越高）、動能（RS、距 52 週高點）。每項先算在全市場的百分位，兩項平均後分 5 格：80 以上頂尖、60 以上良好、40 以上中性、20 以上偏弱、其餘落後。',
  '飆股體質檢查':'《超級績效》（Minervini）找飆股看的條件：獲利與營收高成長而且在加速、毛利率變好、股價在長期上升趨勢、股價強度高。右欄是過去符合這一條的股票，之後 3 個月內漲到五成的比例（2014 年起、月底市值 40 億以上的股票每週算：符合的那一週之後 60 個交易日內，最高價曾經漲到五成就算），和一般股票的比例一起看。過去的比例不代表之後也一樣。',
  '趨勢樣板':'Minervini 的 8 項：股價在 150 與 200 日線之上、150 日線高於 200 日線、200 日線上揚、50 日線高於 150 與 200 日線、股價在 50 日線之上、比 52 週低點高 30% 以上、在 52 週高點 25% 以內、RS ≥ 70。',
  'RS 百分位':'相對強度：0.4×近 3 個月＋0.2×近 6 個月＋0.2×近 9 個月＋0.2×近 12 個月報酬，在全市場排名（1～99，越高越強）。',
  '營收加速':'近 3 個月營收年增率比再前 3 個月的年增率高。連三季變好＝EPS 成長率、營收成長率、毛利率連續三季都一季比一季高（《超級績效》叫它 Code 33）。',
  'ROE 拆解':'ROE＝淨利率 × 資產週轉 × 權益乘數：賺錢的效率、資產用得多勤、用了多少槓桿。三者都用近四季。',
  '自由現金流':'營業活動現金流＋投資活動現金流（近四季）。投資活動含資本支出與買賣金融資產，所以是粗略的自由現金流。',
  '現金流 ÷ 淨利':'近四季營業現金流 ÷ 近四季淨利。長期低於 100% 代表帳上獲利沒有變成現金（應收帳款或存貨堆高）。',
  '飆股命中率':'符合規則的那一週之後，60 個交易日（約 3 個月）內最高價曾漲到 50% 的比例。「全體」＝同一段期間所有合格股票（月底市值 40 億以上、日均成交值 1,000 萬以上）的比例。2023 年起的數字是規則定案之後才算的。',
  '書上的買點與停損':'《超級績效》的算法。樞紐＝整理區的高點：標準 VCP（照書：每段回檔比前一段小、低點逐段墊高、最後一段在整理區上半部、量縮）、10 日高低 8% 以內的緊密整理，或急漲一倍後的橫盤。準備好＝收在樞紐下方 5% 內；今天突破＝昨天準備好、今天收盤站上樞紐（不超過 5%）、成交量是 50 日均量 1.5 倍以上；突破後仍在買點＝突破後 5 天內還在樞紐到樞紐 × 1.05 之間；突破失敗＝突破後 5 天內跌回樞紐 × 0.97 以下；漲太遠＝收盤高於 50 日線 25% 以上，或 60 天內突破過、已漲超過樞紐 5%；其餘＝打底中。停損＝樞紐下 8% 與整理期間最低價取較高者。還沒到買點的：打底中看突破 52 週高點，漲太遠看拉回 50 日線。只標位置與書上的算法，不是買賣訊號。',
  '大盤 50 日線':'加權指數 50 日均線在不在 200 日均線之上。2014–2019 年選出、2020–2022 年驗證：在下的時候之後一年名單比較容易翻倍，但全部股票也一樣（大跌後的反彈），而且這種狀態出現的次數很少。',
  '法人預估':'券商分析師對公司今年、明年的 EPS、營收的預估與目標價。FactSet 調查（鉅亨網「台股預估」快訊，預估有變動才發一則）取多位分析師的中位數；超過 4 個月沒有新快訊就改用 Yahoo Finance（每天更新）。「比現價高 36%」＝目標價比今天收盤高 36%。各家券商的數字在新聞裡，點「是哪些法人」看。分析師常常修正預估，實際數字可能差很多；只供參考，沒有驗證過能不能用來挑股票。',
  '產業比較':'產業別用證交所／櫃買中心的分類，範圍比較大（例如「電子零組件業」包含很多不同產品）。產業營收＝同一批公司（這段期間和去年同期都有營收）加總後相比；一般公司＝各公司年增率的中位數；加速＝近 3 個月年增減去再前 3 個月年增。股價＝成員近 60 個交易日漲跌的中位數。金融業的月營收含投資損益，不算營收年增。只供參考。',
  '本益比位置':'每個月底的股價 ÷ 當時已公告的近四季 EPS，和這檔自己過去的本益比比。百分位越高代表以自己的歷史來看越貴；換算價位只是估值位置，不是價格預測。'});
GLG.push(['公司分析',['五面向','飆股體質檢查','法人預估','產業比較','飆股命中率','書上的買點與停損','大盤 50 日線','趨勢樣板','RS 百分位','營收加速','ROE 拆解','自由現金流','現金流 ÷ 淨利','本益比位置']]);
"""

SEARCH_HTML = ('<div class="cos"><input type="search" id="coq" placeholder="查公司：代號或名稱" autocomplete="off" '
               'aria-label="查公司"><div id="coqd" class="coqd" hidden></div></div>')
