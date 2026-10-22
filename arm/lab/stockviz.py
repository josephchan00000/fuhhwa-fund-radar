"""個股頁（x9.html）的三張圖：機會頁的行動時間軸、籌碼頁的主動 ETF 資金地圖、飆股段的位置圖。

規劃與使用者決定見 docs/lab_visual_plan.md（第 4 節示意圖 F、G、H，第 7 節「三張都採用」，第 10 節實作）。
只改呈現，資料全來自頁面已有的 D（rows、adv、wl），不新增抓取或計算。

- 顏色一律用 CSS 變數（深淺跟系統），SVG 用 class 上色；資金地圖的格子顏色在瀏覽器依變數混色後寫進 style。
- JS 由 page.render 插在 copage.JS 前面（頁面初始化之前）；只放函式宣告與一個狀態物件，執行時才讀 copage 的常數。
"""
from __future__ import annotations

CSS = r"""
/* 個股頁三張圖（stockviz.py） */
.vztip{position:absolute;z-index:6;background:var(--popbg);color:var(--popink);border-radius:10px;padding:8px 11px;font-size:12.5px;line-height:1.65;
 max-width:min(360px,94%);box-shadow:0 8px 24px var(--shadow);pointer-events:none}
.vztip.pin{pointer-events:auto}.vztip b{font-size:13px}.vztip .vzs{opacity:.75;font-size:12px}
.vztip a{color:#9cc3ff;cursor:pointer}.vztip ul{margin:3px 0 2px;padding-left:16px}.vztip li{margin:1px 0}
.vztip .up{color:#fca5a5}.vztip .dn{color:#86efac}.vztip .vzgo{display:block;margin-top:5px;font-weight:600}
.tlx,.mmx,.spotx{position:relative}
.tlhd{display:flex;flex-wrap:wrap;align-items:center;gap:6px 14px;margin:0 0 6px}
.tllg{display:flex;flex-wrap:wrap;gap:2px 12px;font-size:12px;color:var(--ink2)}.tllg span{white-space:nowrap}
.tlk{font-weight:800;margin-right:2px}.tlk.b{color:var(--gain)}.tlk.s{color:var(--loss)}.tlk.w{color:var(--acc)}.tlk.a{color:var(--mut)}
.tlsw i{display:inline-block;width:18px;height:9px;border-radius:3px;margin-right:4px;vertical-align:-1px}
.tlsh{background:var(--gainbg);border:1px solid var(--gain)}.tlsb{border:1.4px dashed var(--acc)}
.tlbox{overflow-x:auto;-webkit-overflow-scrolling:touch;border-radius:10px}.tlbox svg{display:block;max-width:none}
.tl-lane{fill:var(--card2)}.tl-lane.alt{fill:var(--inset2)}
.tl-grid{stroke:var(--line);stroke-width:1}.tl-at{fill:var(--mut);font-size:11px}
.tl-now{stroke:var(--acc);stroke-width:1.5;stroke-dasharray:4 3}.tl-nowt{fill:var(--acc);font-size:11px;font-weight:700}
.tl-nx{fill:var(--accbg)}
.tl-ln{fill:var(--ink);font-size:12.5px;font-weight:700;paint-order:stroke;stroke:var(--card2);stroke-width:4px;stroke-linejoin:round}.tl-ln.alt{stroke:var(--inset2)}.tl-lg{fill:var(--mut);font-size:11px;font-weight:400}
.tl-h{stroke-width:1.2}.tl-h.up{fill:var(--gainbg);stroke:var(--gain)}.tl-h.dn{fill:var(--lossbg);stroke:var(--loss)}
.tl-b{fill:var(--bg);fill-opacity:.55;stroke:var(--acc);stroke-dasharray:5 3;stroke-width:1.4}
.tl-t{fill:var(--ink);font-size:11.5px;pointer-events:none}.tl-t2{fill:var(--ink2);font-size:11px;pointer-events:none}.tl-t.tl-to,.tl-t2.tl-to{pointer-events:auto}
.tl-m circle{fill:var(--bg);stroke-width:1.6}.tl-m text{font-size:9.5px;font-weight:800;text-anchor:middle;dominant-baseline:central;pointer-events:none}
.tl-m.b circle{stroke:var(--gain)}.tl-m.b text{fill:var(--gain)}.tl-m.s circle{stroke:var(--loss)}.tl-m.s text{fill:var(--loss)}
.tl-m.w circle{stroke:var(--acc)}.tl-m.w text{fill:var(--acc)}.tl-m.a circle{stroke:var(--mut)}.tl-m.a text{fill:var(--mut)}
.tl-m.o circle{stroke-dasharray:2 2}
[data-tl],[data-mm],[data-spot]{cursor:pointer}
.tlnx{display:grid;grid-template-columns:auto minmax(0,1fr);gap:4px 18px;align-items:start;background:var(--card2);border-radius:12px;padding:10px 14px;margin:0 0 12px}
.tlnd b{display:block;font-size:20px;line-height:1.25}.tlnd span{font-size:12px;color:var(--mut)}
.tlna{display:flex;flex-direction:column;gap:5px;min-width:0}
.tlnr{display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 8px;font-size:13.5px;line-height:1.6}.tlnr .kact{flex:none}
.tlni{color:var(--ink2)}.tlni .mu{font-size:12px}.tlit{white-space:nowrap}
.mmctl{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;margin:0 0 8px}.mmk{font-size:12.5px;color:var(--mut)}
.mmctl .seg{flex-wrap:wrap;max-width:100%}.mmctl .seg a{padding:4px 11px;font-size:13px;cursor:pointer}
.mmbox{border-radius:10px;overflow:hidden;background:var(--bg)}.mmbox svg{display:block}
.mm-g{fill:var(--ink2);font-size:11px;font-weight:700;pointer-events:none}.mm-gb{fill:none;stroke:var(--bg);stroke-width:3;pointer-events:none}
.mm-t{font-weight:700;pointer-events:none}.mm-c:hover rect{stroke:var(--ink);stroke-width:2}
.mmscale{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;margin:6px 2px 0;font-size:12px;color:var(--mut)}
.mmscale i{display:inline-block;width:150px;height:10px;border-radius:3px}
.spotbox svg{display:block}
.spot-grid{stroke:var(--line);stroke-width:1}.spot-at{fill:var(--mut);font-size:11px}.spot-al{fill:var(--mut);font-size:11.5px}
.spot-zone{fill:var(--accbg)}.spot-zl{stroke:var(--acc);stroke-dasharray:4 4;stroke-width:1.2}.spot-zt{fill:var(--acc);font-size:11.5px;font-weight:700}
.spotp circle{stroke:var(--bg);stroke-width:1.5}.spotp:hover circle{stroke:var(--ink);stroke-width:2}
.spotp.buy circle{fill:var(--gain)}.spotp.near circle{fill:var(--amber)}.spotp.far circle{fill:var(--vio);fill-opacity:.62}.spotp.fail circle{fill:var(--mut);fill-opacity:.7}
.spotp.base circle{fill:var(--mut2);fill-opacity:.5}.spotp.buy circle,.spotp.near circle{stroke:var(--ink);stroke-width:1.6}
.spotl{font-size:11.5px;fill:var(--ink);paint-order:stroke;stroke:var(--bg);stroke-width:3px;stroke-linejoin:round;pointer-events:none}.spotl.buy,.spotl.near{font-weight:700}
.vzlg{display:flex;flex-wrap:wrap;gap:3px 14px;font-size:12px;color:var(--ink2);margin:6px 2px 0}
.vzlg i{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:5px;vertical-align:-1px}
.vzlg .buy{background:var(--gain)}.vzlg .near{background:var(--amber)}.vzlg .far{background:var(--vio)}.vzlg .fail{background:var(--mut)}.vzlg .base{background:var(--mut2)}
@media(max-width:600px){.tlnx{grid-template-columns:1fr;gap:6px}.tlnd b{display:inline;font-size:17px;margin-right:6px}.mmscale i{width:110px}}
"""

JS = r"""
/* ── 個股頁的三張圖（stockviz.py；docs/lab_visual_plan.md 第 10 節）：機會頁的行動時間軸、籌碼頁的主動 ETF 資金地圖、飆股段的位置圖。
   顏色都用 CSS 變數（深淺跟著系統）；點了開個股卡或公司卡。 */
const VZS={tl:'all',mtl:'all',tlpin:null,tle:[],mmsz:'cap',mmcol:'a5v',spote:[]};
function vzDay(d){return Date.UTC(+d.slice(0,4),+d.slice(5,7)-1,+d.slice(8,10))/864e5;}
function vzVar(n){return getComputedStyle(document.documentElement).getPropertyValue(n).trim();}
function vzRgb(c){const m=/^#?([0-9a-f]{6})$/i.exec(c||'');if(!m)return [136,136,136];const n=parseInt(m[1],16);return [n>>16&255,n>>8&255,n&255];}
function vzMix(a,b,t){const A=vzRgb(a),B=vzRgb(b);return A.map((v,i)=>Math.round(v+(B[i]-v)*t));}
function vzFit(s,w,fs){let o='',u=0;for(const ch of String(s||'')){const cw=/[⺀-￿]/.test(ch)?fs:fs*0.6;if(u+cw>w){return o.length?o.slice(0,-1)+'…':'';}o+=ch;u+=cw;}return o;}
function vzPlace(tip,wrap,ev){const b=wrap.getBoundingClientRect(),tw=tip.offsetWidth,th=tip.offsetHeight;let x=ev.clientX-b.left+14,y=ev.clientY-b.top+14;
  if(x+tw>b.width)x=Math.max(4,ev.clientX-b.left-tw-14);if(y+th>b.height)y=Math.max(4,ev.clientY-b.top-th-14);tip.style.left=x+'px';tip.style.top=y+'px';}
function vzBind(box,tip,wrap,attr,html,click){
  box.onmousemove=ev=>{if(tip.classList.contains('pin'))return;const el=ev.target.closest&&ev.target.closest('['+attr+']');if(!el){tip.hidden=true;return;}
    tip.innerHTML=html(el,false);tip.hidden=false;vzPlace(tip,wrap,ev);};
  box.onmouseleave=()=>{if(!tip.classList.contains('pin'))tip.hidden=true;};
  box.onclick=ev=>{const el=ev.target.closest&&ev.target.closest('['+attr+']');if(!el){tip.classList.remove('pin');tip.hidden=true;return;}click(el,ev);};
  tip.onclick=ev=>{const a=ev.target.closest&&ev.target.closest('[data-to]');if(a){ev.preventDefault();tip.classList.remove('pin');tip.hidden=true;jump(a.dataset.to);}};}
document.addEventListener('click',e=>{$$('.vztip.pin').forEach(t=>{if(!t.parentNode.contains(e.target)){t.classList.remove('pin');t.hidden=true;}});});

/* 行動時間軸：每條推薦策略一列；實心條＝持有中（顏色＝到最新收盤的平均漲跌）、虛線＝排定的買進；▲買進 ▼賣出 ◆換股 ●調整 */
function tlNext(){const C=ADV.cal||[];if(!C.length)return '';const d0=C[0].d,E=C.filter(e=>e.d===d0);
  const its=e=>(e.items||[]).map(i=>`<span class=tlit>${BY[i.c]?`<a data-c="${esc(i.c)}">${esc(i.n)}</a>`:esc(i.n)}${i.cond?`<span class=mu>（${esc(i.cond.replace(' 才買',''))}）</span>`:''}</span>`).join('、');
  return `<div class=tlnx><div class=tlnd><b>${mdw(d0)}</b><span>下一個交易日要做的事</span></div><div class=tlna>${E.map(e=>`<div class=tlnr><span class="kact ka-${KA[e.act]||'a'}">${esc(e.at)}${esc(e.act)}</span><a data-to="o-${esc(e.k)}">${esc(STN[e.k]||e.sname)}</a><span class=tlni>${its(e)||(e.pending?`名單 ${md(e.fix)} 收盤產生`:esc(e.note||''))}</span></div>`).join('')}</div></div>`;}
function tlSec(){if(!(OPP.cards||[]).length)return '';
  return `<div class=tlx><div class=tlhd><div class="seg tlrg"><a data-tlr=all class=on>全部</a><a data-tlr=m1>接下來 5 週</a></div>`+
    `<span class=tllg><span><span class="tlk b">▲</span>買進</span><span><span class="tlk s">▼</span>賣出</span><span><span class="tlk w">◆</span>換股</span><span><span class="tlk a">●</span>調整</span>`+
    `<span class=tlsw><i class=tlsh></i>持有中（顏色＝目前漲跌）</span><span class=tlsw><i class=tlsb></i>排定的買進</span></span></div>`+
    `<div class=tlbox id=tlbox></div><div class=vztip id=tltip hidden></div></div>`;}
/* 時間軸設定：個股策略（TLO）；總經策略的在 macpage.py（TLM）。box／tip＝元素 id、rk＝VZS 裡記範圍的鍵、back＝「全部」最多往回幾天 */
const TLO={box:'tlbox',tip:'tltip',rk:'tl',back:0,cards:()=>OPP.cards||[],
  last:()=>ADV.last||((ADV.cal||[])[0]||{d:'2026-01-01'}).d,dl:()=>ADV.last,nx:()=>((ADV.cal||[])[0]||{}).d,
  lb:x=>{const e=x.e,n=(e.items||[]).map(o=>o.n);return x.k==='held'?`${n.length} 檔 ${pctT(tlAvg(e))}`:x.k==='buy'?n.slice(0,4).join('、')+(n.length>4?` 等 ${n.length} 檔`:'')+(e.tent?'（試算）':''):x.k==='next'?`名單 ${md(e.fix)} 產生`:'';},
  nm:c=>`${c.rank?c.rank+'. ':''}${STN[c.k]||c.name}`,
  sub:c=>{const hd=c.hold||'';return `${TMK[c.tier]||''} ${TN[c.tier]||''}・持有${/^\d/.test(hd)?' ':''}${hd}`;},
  avg:e=>tlAvg(e),tipf:(x,pin)=>tlTip(x,pin)};
function tlAvg(e){const r=(e.items||[]).map(i=>i.now_r).filter(v=>v!=null);return r.length?r.reduce((a,b)=>a+b,0)/r.length:null;}
function tlTip(x,pin){const e=x.e,nm=esc(STN[x.c.k]||x.c.name),lk=i=>BY[i.c]?`<a data-c="${esc(i.c)}">${esc(i.n)}</a>`:esc(i.n);let h='';
  if(x.k==='held'){const a=tlAvg(e);h=`<b>${nm}・${md(e.ent)} 買進的 ${(e.items||[]).length} 檔</b><div class=vzs>到 ${md(ADV.last)} 收盤平均 <span class=${a>=0?'up':'dn'}>${pctT(a)}</span>；${mdw(e.d)} ${esc(e.at)}${esc(e.act)}</div>`+
    `<ul>${(e.items||[]).map(i=>`<li>${pin?lk(i):esc(i.n)} <span class=vzs>${fp(i.entry)} → ${fp(i.now)}</span> <span class=${(i.now_r||0)>=0?'up':'dn'}>${pctT(i.now_r)}</span></li>`).join('')}</ul>`;}
  else if(x.k==='buy'){h=`<b>${mdw(e.d)} ${esc(e.at)}買進・${nm}</b>${e.tent?'<div class=vzs>名單是以今天排名試算，定案前可能變動</div>':''}`+
    `<ul>${(e.items||[]).map(i=>`<li>${pin?lk(i):esc(i.n)} <span class=vzs>${i.cond?esc(i.cond):'參考 '+fp(i.px)}${i.stop?`・停損 ${fp(i.stop)}`:''}</span></li>`).join('')}</ul>`+
    `<div class=vzs>${e.out?`${mdw(e.out)} 收盤賣出`:esc(e.sell||'依規則賣出')}</div>`;}
  else if(x.k==='next')h=`<b>${nm}</b><div>名單 ${mdw(e.fix)} 收盤產生，${mdw(e.d)} 開盤買進</div>`;
  else h=`<b>${mdw(e.d)} ${esc(e.at||'開盤')}調整・${nm}</b><div class=vzs>${esc(e.note||'')}</div>`;
  return h+(pin?`<a class=vzgo data-to="o-${esc(x.c.k)}">看這條策略 →</a>`:'<div class=vzs>點一下可以開股票</div>');}
function tlDraw(Q){Q=Q||TLO;const box=$('#'+Q.box);if(!box)return;const C=Q.cards().slice().sort((a,b)=>(a.rank||99)-(b.rank||99));
  const W=box.clientWidth||720,mob=W<560,LB=mob?8:150,HD=mob?22:0,T=30,RH=22,R=W-14,now=vzDay(Q.last());
  const E=[];C.forEach((c,li)=>{(c.held||[]).forEach(e=>E.push({li,c,k:'held',e,a:vzDay(e.ent),b:e.d?vzDay(e.d):null}));
    (c.buy||[]).forEach(e=>E.push({li,c,k:'buy',e,a:vzDay(e.d),b:e.out?vzDay(e.out):null}));
    if(c.next&&c.next.d)E.push({li,c,k:'next',e:c.next,a:vzDay(c.next.d),b:null});(c.adj||[]).forEach(e=>E.push({li,c,k:'adj',e,a:vzDay(e.d),b:null}));});
  let t0,t1;if(VZS[Q.rk]==='m1'){t0=now-6;t1=now+35;}else{t0=Math.min(now,...E.map(x=>x.a))-4;if(Q.back)t0=Math.max(t0,now-Q.back);t1=Math.max(now+21,...E.map(x=>x.b||x.a))+6;}
  const X=n=>LB+(n-t0)/(t1-t0)*(R-LB),cl=v=>Math.max(LB,Math.min(R,v)),tw=(s,fs)=>[...String(s)].reduce((a,ch)=>a+(/[⺀-￿]/.test(ch)?fs:fs*0.6),0);
  /* 每件事的文字與占用寬度：條太短放不下字，字移到條的右邊（靠右邊界就放左邊） */
  const V=E.filter(x=>(x.b==null?(x.k==='held'?t1:x.a):x.b)>=t0&&x.a<=t1);   // 還沒排定賣出日的持有中＝畫到右邊
  V.forEach(x=>{x.lb=Q.lb(x);
    x.x0=cl(X(x.a));x.x1=x.k==='next'||x.k==='adj'?x.x0:x.b!=null?cl(X(x.b)):R;
    const lw=tw(x.lb,11.5),need=lw+(x.k==='held'?16:24);
    x.out=(x.k==='held'||x.k==='next'||(x.k==='buy'&&x.b!=null))&&!!x.lb&&x.x1-x.x0<need;x.outL=x.out&&x.x1+12+lw>R;
    x.rule=(x.k==='buy'||(x.k==='held'&&!V.some(o=>o.li===x.li&&o.k==='adj')))&&x.b==null&&x.x1-x.x0>=tw(x.lb,11)+24+84;   // 同一列有「月底看」就不寫，免得疊在一起
    x.s0=x.outL?x.x0-16-lw:x.x0-12;x.e1=x.out&&!x.outL?x.x1+12+lw:x.x1;});
  /* 同一條策略依時間排：放得下就同一行，重疊才往下；調整（●）疊在包含它的那條上 */
  const rows=C.map((c,li)=>{const ends=[],put=(x,s,e)=>{let r=ends.findIndex(v=>v<s);if(r<0){r=ends.length;ends.push(0);}ends[r]=e;x.r=r;};
    V.filter(x=>x.li===li&&x.k!=='adj').sort((a,b)=>a.s0-b.s0||(a.k==='held'?-1:1)).forEach(x=>put(x,x.s0,x.e1+10));
    V.filter(x=>x.li===li&&x.k==='adj').forEach(x=>{const h=V.find(o=>o.li===li&&(o.k==='buy'||o.k==='held')&&o.a<=x.a&&(o.b==null||o.b>=x.a));if(h)x.r=h.r;else put(x,x.x0-12,x.x0+10);});
    return Math.max(1,ends.length);});
  let y=T;const Y=rows.map(n=>{const y0=y,h=Math.max(mob?0:48,HD+8+n*RH);y+=h+6;return [y0,h];}),H=y+16;
  VZS.tle=V;let s='',m='';
  let ln='';C.forEach((c,i)=>{const [y0,h]=Y[i],nm=Q.nm(c),sub=Q.sub(c),al=i%2?' alt':'';
    s+=`<rect class="tl-lane${al}" x=0 y=${y0} width=${W} height=${h} rx=8 />`;
    ln+=mob?`<text class="tl-ln${al}" x=10 y=${y0+16}>${esc(nm)}<tspan class=tl-lg dx=8>${esc(vzFit(sub,R-24-tw(nm,12.5),11))}</tspan></text>`
      :`<text class="tl-ln${al}" x=10 y=${y0+20}>${esc(vzFit(nm,LB-18,12.5))}</text><text class=tl-lg x=10 y=${y0+37}>${esc(vzFit(sub,LB-18,11))}</text>`;});
  const d=new Date(t0*864e5);d.setUTCDate(1);d.setUTCMonth(d.getUTCMonth()+1);
  for(;d.getTime()/864e5<t1;d.setUTCMonth(d.getUTCMonth()+1)){const x=X(d.getTime()/864e5);if(x<LB)continue;s+=`<line class=tl-grid x1=${x.toFixed(1)} x2=${x.toFixed(1)} y1=${T-8} y2=${H-16} /><text class=tl-at x=${(x+3).toFixed(1)} y=${T-11}>${d.getUTCMonth()+1} 月</text>`;}
  if(VZS.tl==='m1'){for(let n=Math.ceil(t0);n<t1;n++){const dd=new Date(n*864e5);if(dd.getUTCDay()!==1)continue;const x=X(n);s+=`<text class=tl-at x=${(x+3).toFixed(1)} y=${T-1} style="font-size:10px">${dd.getUTCMonth()+1}/${dd.getUTCDate()}</text>`;}}
  const nx=Q.nx();if(nx){const x=X(vzDay(nx));if(x>=LB&&x<=R)s+=`<rect class=tl-nx x=${(x-5).toFixed(1)} y=${T-4} width=10 height=${H-T-12} rx=4 />`;}
  const xn=X(now);if(xn>=LB&&xn<=R)s+=`<line class=tl-now x1=${xn.toFixed(1)} x2=${xn.toFixed(1)} y1=${T-6} y2=${H-14} /><text class=tl-nowt x=${(xn>R-90?xn-4:xn+4).toFixed(1)} y=${H-2}${xn>R-90?' text-anchor=end':''}>資料日 ${md(Q.dl())}</text>`;
  s+=ln;
  const mk=(x,yy,cls,sym,i)=>x<LB-2||x>R+2?'':`<g class="tl-m ${cls}" data-tl=${i} transform="translate(${x.toFixed(1)},${yy.toFixed(1)})"><circle r=8 /><text>${sym}</text></g>`;
  V.forEach((x,i)=>{const [y0,h]=Y[x.li],off=Math.max(0,(h-(HD+8+rows[x.li]*RH))/2),yy=y0+HD+4+off+x.r*RH,w=Math.max(4,x.x1-x.x0);
    const lab=(cls,fs,pad)=>{if(!x.lb)return '';
      if(x.out)return `<text class="${cls} tl-to" data-tl=${i} x=${(x.outL?x.x0-12:x.x1+12).toFixed(1)} y=${yy+13}${x.outL?' text-anchor=end':''}>${esc(x.lb)}</text>`;
      const t=vzFit(x.lb,w-pad-(x.rule?84:0),fs);return t?`<text class=${cls} x=${(x.x0+(x.k==='held'?6:12)).toFixed(1)} y=${yy+13}>${esc(t)}</text>`:'';};
    if(x.k==='held'){const a=Q.avg(x.e);s+=`<rect class="tl-h ${a!=null&&a<0?'dn':'up'}" data-tl=${i} x=${x.x0.toFixed(1)} y=${yy} width=${w.toFixed(1)} height=17 rx=5 />`+lab('tl-t',11.5,16);
      if(x.rule)s+=`<text class=tl-t2 x=${(R-6).toFixed(1)} y=${yy+13} text-anchor=end>依規則賣出 →</text>`;
      if(x.b!=null)m+=mk(X(x.b),yy+8.5,x.e.act==='換股'?'w':'s',x.e.act==='換股'?'◆':'▼',i);}
    else if(x.k==='buy'){s+=`<rect class=tl-b data-tl=${i} x=${x.x0.toFixed(1)} y=${yy} width=${w.toFixed(1)} height=17 rx=5 />`+lab('tl-t2',11,24);
      if(x.rule)s+=`<text class=tl-t2 x=${(R-6).toFixed(1)} y=${yy+13} text-anchor=end>依規則賣出 →</text>`;
      m+=mk(X(x.a),yy+8.5,'b','▲',i);if(x.b!=null)m+=mk(X(x.b),yy+8.5,'s o','▼',i);}
    else if(x.k==='next'){s+=lab('tl-t2',11,22);m+=mk(X(x.a),yy+8.5,'b o','▲',i);}
    else m+=mk(X(x.a),yy+8.5,'a','●',i);});
  box.innerHTML=`<svg viewBox="0 0 ${W} ${H}" width=${W} height=${H} role=img aria-label="行動時間軸">${s}${m}</svg>`;
  const tip=$('#'+Q.tip),wrap=box.closest('.tlx');tip.hidden=true;tip.classList.remove('pin');
  vzBind(box,tip,wrap,'data-tl',(el,pin)=>Q.tipf(VZS.tle[+el.dataset.tl],pin),(el,ev)=>{tip.innerHTML=Q.tipf(VZS.tle[+el.dataset.tl],true);tip.hidden=false;tip.classList.add('pin');vzPlace(tip,wrap,ev);});
  $$('[data-tlr]').forEach(a=>a.onclick=e=>{e.preventDefault();VZS[Q.rk]=a.dataset.tlr;$$('[data-tlr]').forEach(b=>b.classList.toggle('on',b===a));tlDraw(Q);});}

/* 主動 ETF 資金地圖：一格一檔、依產業分區；大小＝市值（開根號）或 5 日買賣金額，顏色＝選的籌碼（紅＝買、綠＝賣，深＝大） */
const MMC={a5v:['主動 ETF 5 日淨買','億'],t5:['投信 5 日','張'],f5:['外資 5 日','張'],rs20:['20 日相對大盤','個百分點']};
function mmSec(){return sec('c-map','資金地圖','主動 ETF 資金地圖','近 5 個交易日；一格一檔、依產業分區，點一格打開個股卡',
  `<div class=mmctl><span class=mmk>大小</span><div class="seg mmsz"><a data-mms=cap class=on>市值</a><a data-mms=amt>5 日買賣金額</a></div>`+
  `<span class=mmk>顏色</span><div class="seg mmcol">${Object.entries(MMC).map(([k,v],i)=>`<a data-mmc=${k}${i?'':' class=on'}>${v[0]}</a>`).join('')}</div></div>`+
  `<div class=mmx><div class=mmbox id=mmbox></div><div class=vztip id=mmtip hidden></div></div><div class=mmscale id=mmscale></div>`);}
function vzSq(items,x,y,w,h){const out=[],tot=items.reduce((a,b)=>a+b.v,0);if(!tot||w<=0||h<=0)return out;const k=w*h/tot;let rest=items.map(o=>({o,a:o.v*k}));
  while(rest.length){const side=Math.min(w,h);let n=1,best=Infinity;
    for(let i=1;i<=rest.length;i++){const r=rest.slice(0,i),s=r.reduce((a,b)=>a+b.a,0),mx=Math.max(...r.map(q=>q.a)),mn=Math.min(...r.map(q=>q.a)),wr=Math.max(side*side*mx/(s*s),s*s/(side*side*mn));if(wr<=best){best=wr;n=i;}else break;}
    const row=rest.slice(0,n),s=row.reduce((a,b)=>a+b.a,0);
    if(w>=h){const cw=s/h;let yy=y;row.forEach(q=>{const ch=q.a/cw;out.push({o:q.o,x,y:yy,w:cw,h:ch});yy+=ch;});x+=cw;w-=cw;}
    else{const rh=s/w;let xx=x;row.forEach(q=>{const cw=q.a/rh;out.push({o:q.o,x:xx,y,w:cw,h:rh});xx+=cw;});y+=rh;h-=rh;}
    rest=rest.slice(n);}
  return out;}
function mmVal(r,k){const v=r[k];if(v==null)return '—';const d=k==='a5v'||k==='rs20'?1:0,q=Math.round(v*10**d)/10**d,t=`${q>0?'+':''}${f(q===0?0:q,d)}`;return k==='a5v'?t+' 億':k==='rs20'?t+' pp':t+' 張';}
function vzLum(c){return c.map(v=>{v/=255;return v<=0.03928?v/12.92:((v+0.055)/1.055)**2.4;}).reduce((a,v,i)=>a+v*[0.2126,0.7152,0.0722][i],0);}
/* 格子上的字：白字或深字，取對比較高的（WCAG 相對亮度；深字 #1f2733 的亮度約 0.0198） */
function vzInk(c){const L=vzLum(c);return 1.05/(L+0.05)>=(L+0.05)/0.0698?'#ffffff':'#1f2733';}
function mmTip(r){const ia=(r.ia5||[]).length,ic=(r.ic5||[]).length;
  return `<b>${esc(r.n)}</b> <span class=vzs>${esc(r.c)}・${esc(r.ind||'')}</span><div>收盤 ${fp(r.px)} <span class=${(r.ch||0)>=0?'up':'dn'}>${pctT(r.ch,2)}</span></div>`+
    `<div>主動 ETF 5 日 <span class=${(r.a5v||0)>=0?'up':'dn'}>${mmVal(r,'a5v')}</span>${ia||ic?`<span class=vzs>（${ia} 家加碼、${ic} 家減碼）</span>`:''}</div>`+
    `<div>投信 5 日 ${mmVal(r,'t5')}・外資 5 日 ${mmVal(r,'f5')}</div><div>20 日相對大盤 ${mmVal(r,'rs20')}・市值占比 ${f(r.mw,2)}%</div><div class=vzs>點一下打開個股卡</div>`;}
function mmDraw(){const box=$('#mmbox');if(!box)return;const W=box.clientWidth||720,mob=W<560,H=Math.round(mob?Math.max(440,W*1.3):Math.max(420,Math.min(660,W*0.56)));
  const amt=VZS.mmsz==='amt',ck=VZS.mmcol,val=r=>amt?Math.abs(r.a5v||0):Math.sqrt(Math.max(0,r.mw||0));
  const use=ROWS.filter(r=>r.m!=='os'&&r.mw>0&&val(r)>0),G={};use.forEach(r=>{const g=r.ind||'其他';(G[g]=G[g]||[]).push(r);});
  const groups=Object.entries(G).map(([k,rs])=>({k,rs:rs.sort((a,b)=>val(b)-val(a)),v:rs.reduce((a,r)=>a+val(r),0)})).sort((a,b)=>b.v-a.v);
  const vs=use.map(r=>Math.abs(r[ck]||0)).filter(v=>v>0).sort((a,b)=>a-b),S=vs.length?vs[Math.min(vs.length-1,Math.floor(vs.length*0.9))]:1;
  const K={g:vzVar('--gain'),l:vzVar('--loss'),z:vzVar('--card2')},col=v=>!v?vzRgb(K.z):vzMix(K.z,v>0?K.g:K.l,0.22+0.78*Math.min(1,Math.abs(v)/S));
  let s='';
  vzSq(groups.map(g=>({v:g.v,g})),0,0,W,H).forEach(q=>{const g=q.o.g,hd=q.h>40&&q.w>44?15:0;
    vzSq(g.rs.map(r=>({v:val(r),r})),q.x+1,q.y+hd+1,Math.max(0,q.w-2),Math.max(0,q.h-hd-2)).forEach(c=>{const r=c.o.r,cc=col(r[ck]),tc=vzInk(cc);
      s+=`<g class=mm-c data-mm="${esc(r.c)}"><rect x=${c.x.toFixed(1)} y=${c.y.toFixed(1)} width=${Math.max(0,c.w-1).toFixed(1)} height=${Math.max(0,c.h-1).toFixed(1)} style="fill:rgb(${cc.join(',')})" />`;
      if(c.w>26&&c.h>15){const fs=Math.max(10,Math.min(16,Math.sqrt(c.w*c.h)/5.6)),t=vzFit(r.n,c.w-6,fs);
        if(t)s+=`<text class=mm-t x=${(c.x+4).toFixed(1)} y=${(c.y+fs+1).toFixed(1)} style="fill:${tc};font-size:${fs.toFixed(1)}px">${esc(t)}</text>`;
        if(t&&c.h>fs*2.4&&c.w>46)s+=`<text class=mm-t x=${(c.x+4).toFixed(1)} y=${(c.y+fs*2.25+1).toFixed(1)} style="fill:${tc};font-size:${(fs*0.76).toFixed(1)}px;font-weight:500">${esc(vzFit(mmVal(r,ck),c.w-6,fs*0.76))}</text>`;}
      s+=`</g>`;});
    if(hd)s+=`<text class=mm-g x=${(q.x+4).toFixed(1)} y=${(q.y+11.5).toFixed(1)}>${esc(vzFit(g.k.replace(/業$/,''),q.w-8,11))}</text>`;
    s+=`<rect class=mm-gb x=${q.x.toFixed(1)} y=${q.y.toFixed(1)} width=${q.w.toFixed(1)} height=${q.h.toFixed(1)} />`;});
  box.innerHTML=`<svg viewBox="0 0 ${W} ${H}" width=${W} height=${H} role=img aria-label="主動 ETF 資金地圖">${s}</svg>`;
  const lo=vzMix(K.z,K.l,1),hi=vzMix(K.z,K.g,1),u=MMC[ck];
  $('#mmscale').innerHTML=`<span>${ck==='rs20'?'弱於大盤':'賣超'}</span><i style="background:linear-gradient(90deg,rgb(${lo}),rgb(${vzRgb(K.z)}) 50%,rgb(${hi}))"></i><span>${ck==='rs20'?'強於大盤':'買超'}</span>`+
    `<span>顏色最深＝${esc(u[0])}前 10% 的大小（約 ${f(S,ck==='a5v'||ck==='rs20'?1:0)} ${esc(u[1])}）・${amt?'面積＝5 日買賣金額':'面積＝市值（開根號，台積電才不會占掉一半）'}・${use.length} 檔</span>`;
  const tip=$('#mmtip');tip.hidden=true;
  vzBind(box,tip,box.closest('.mmx'),'data-mm',el=>mmTip(BY[el.dataset.mm]),el=>{tip.hidden=true;openStock(el.dataset.mm);});
  $$('[data-mms]').forEach(a=>a.onclick=e=>{e.preventDefault();VZS.mmsz=a.dataset.mms;$$('[data-mms]').forEach(b=>b.classList.toggle('on',b===a));mmDraw();});
  $$('[data-mmc]').forEach(a=>a.onclick=e=>{e.preventDefault();VZS.mmcol=a.dataset.mmc;$$('[data-mmc]').forEach(b=>b.classList.toggle('on',b===a));mmDraw();});}

/* 飆股位置圖：橫軸＝離 52 週高點多遠（越右越接近）、縱軸＝RS；顏色＝位置（到買點／快到買點／打底中／漲太遠）、大小＝近 3 月營收年增 */
function spotCls(x,p,strong){const st=p.st==null?-1:p.st,gap=p.hi&&x[3]?(p.hi/x[3]-1)*100:null;
  return st>=1&&st<=3?'buy':st===5?'far':st===4?'fail':strong&&st===0&&gap!=null&&gap<=10?'near':'base';}
function spotSec(){const C=((D.wl||{}).cand)||[];if(!C.length)return '';
  return `<h4 class=sh>位置圖</h4><div class=spotx><div class=spotbox id=spotbox></div><div class=vztip id=spottip hidden></div></div>`+
    `<div class=vzlg><span><i class=buy></i>到買點</span><span><i class=near></i>快到買點（強勢、還差 10% 內到 52 週高點）</span><span><i class=far></i>漲太遠</span><span><i class=fail></i>突破失敗</span><span><i class=base></i>打底中／其他</span>`+
    `<span>泡泡大小＝近 3 月營收年增；點一下打開公司卡</span></div>`;}
function spotDraw(){const box=$('#spotbox');if(!box)return;const W0=D.wl||{},Y=W0.lay||{},ST=Y.stocks||{},CK=(Y.ck||[]).map(x=>x[0]);
  const bit=(c,k)=>{const s=ST[c],i=CK.indexOf(k);return !!(s&&i>=0&&((s.x>>>i)&1));};
  const P=(W0.cand||[]).map(x=>{const p=(ST[x[0]]||{}).p||{},gap=p.hi&&x[3]?(x[3]/p.hi-1)*100:null;return {x,p,gap,rs:x[4],cls:spotCls(x,p,bit(x[0],'rs90')||bit(x[0],'mom10'))};}).filter(o=>o.gap!=null&&o.rs!=null);
  if(!P.length){box.innerHTML='';return;}
  const W=box.clientWidth||720,mob=W<560,H=mob?340:400,ml=mob?34:44,mr=14,mt=26,mb=34,xmin=Math.min(-40,Math.floor(Math.min(...P.map(o=>o.gap))/5)*5-2);
  const y0=Math.min(60,Math.max(0,Math.floor((Math.min(...P.map(o=>o.rs))-3)/10)*10));
  const X=v=>ml+(v-xmin)/(0-xmin)*(W-ml-mr),Yv=v=>mt+(100-Math.max(y0,v))/(100-y0)*(H-mt-mb);
  const R=o=>Math.max(o.cls==='buy'||o.cls==='near'?7:4.5,4.5+Math.sqrt(Math.min(200,Math.max(0,o.x[5]||0))/200)*(mob?9:13));
  /* 淺色帶＝還差 10% 內就到 52 週高點（價格 ≥ 高點 ÷ 1.1，和「快到買點」同一個條件） */
  const zx=X(100/1.1-100);
  let s=`<rect class=spot-zone x=${zx.toFixed(1)} y=${mt} width=${(X(0)-zx).toFixed(1)} height=${H-mb-mt} /><line class=spot-zl x1=${zx.toFixed(1)} x2=${zx.toFixed(1)} y1=${mt} y2=${H-mb} />`+
    `<text class=spot-zt x=${W-mr} y=${mt-9} text-anchor=end>還差 10% 內到 52 週高點</text>`;
  for(let v=y0;v<=100;v+=10)s+=`<line class=spot-grid x1=${ml} x2=${W-mr} y1=${Yv(v).toFixed(1)} y2=${Yv(v).toFixed(1)} /><text class=spot-at x=${ml-6} y=${(Yv(v)+4).toFixed(1)} text-anchor=end>${v}</text>`;
  for(let v=Math.ceil(xmin/10)*10;v<=0;v+=10)s+=`<text class=spot-at x=${X(v).toFixed(1)} y=${H-mb+16} text-anchor=middle>${v===0?'高點':v+'%'}</text>`;
  s+=`<text class=spot-al x=${W-mr} y=${H-4} text-anchor=end>離 52 週高點 →</text><text class=spot-al x=4 y=${mt-9}>RS</text>`;
  const ord={base:0,fail:1,far:2,near:3,buy:4};VZS.spote=P;
  P.map((o,i)=>[o,i]).sort((a,b)=>ord[a[0].cls]-ord[b[0].cls]||(b[0].x[5]||0)-(a[0].x[5]||0)).forEach(([o,i])=>{
    s+=`<g class="spotp ${o.cls}" data-spot=${i}><circle cx=${X(o.gap).toFixed(1)} cy=${Yv(o.rs).toFixed(1)} r=${R(o).toFixed(1)} /></g>`;});
  /* 名字：到買點、快到買點一定標（右邊放不下放左邊）；漲太遠不重疊才標 */
  const used=[],lab=(o,force)=>{const r=R(o),w=[...o.x[1]].length*11.5,cy=Yv(o.rs)+4;
    for(const sd of [1,-1]){const x=sd>0?X(o.gap)+r+3:X(o.gap)-r-3-w;if(x<ml||x+w>W-mr)continue;
      if(!force&&used.some(u=>Math.abs(u[1]-cy)<14&&x<u[0]+u[2]+8&&u[0]<x+w+8))continue;
      used.push([x,cy,w]);return `<text class="spotl ${o.cls}" x=${x.toFixed(1)} y=${cy.toFixed(1)}>${esc(o.x[1])}</text>`;}return '';};
  let L='';P.filter(o=>o.cls==='buy'||o.cls==='near').forEach(o=>L+=lab(o,true));P.filter(o=>o.cls==='far').sort((a,b)=>(b.x[5]||0)-(a.x[5]||0)).forEach(o=>L+=lab(o,false));
  box.innerHTML=`<svg viewBox="0 0 ${W} ${H}" width=${W} height=${H} role=img aria-label="飆股位置圖">${s}${L}</svg>`;
  const tip=$('#spottip');tip.hidden=true;
  vzBind(box,tip,box.closest('.spotx'),'data-spot',el=>{const o=VZS.spote[+el.dataset.spot],st=o.p.st==null?-1:o.p.st;
    return `<b>${esc(o.x[1])}</b> <span class=vzs>${esc(o.x[0])}</span><div>${esc(WLST[st]||'—')}・收盤 ${fp(o.x[3])}・離 52 週高點 ${pctT(o.gap,1)}</div>`+
      `<div>RS ${o.rs}・近 3 月營收年增 ${o.x[5]==null?'—':pctT(o.x[5],0)}</div><div class=vzs>${wlBuy(ST[o.x[0]],o.x[3]).replace(/<[^>]+>/g,' ').replace(/\s+/g,' ').trim()}</div><div class=vzs>點一下打開公司卡</div>`;},
    el=>{tip.hidden=true;openCo(VZS.spote[+el.dataset.spot].x[0]);});}
let VZR=0,VZW=innerWidth;addEventListener('resize',()=>{clearTimeout(VZR);VZR=setTimeout(()=>{if(Math.abs(innerWidth-VZW)<30)return;VZW=innerWidth;tlDraw();if(typeof TLM!=='undefined')tlDraw(TLM);mmDraw();spotDraw();},200);});
function vzTheme(){tlDraw();if(typeof TLM!=='undefined')tlDraw(TLM);mmDraw();spotDraw();}                     // 深淺色換了：資金地圖等用程式算顏色的圖重畫（appnav 的按鈕、系統設定）
addEventListener('labtheme',vzTheme);if(typeof matchMedia==='function')matchMedia('(prefers-color-scheme: dark)').addEventListener('change',vzTheme);
"""
