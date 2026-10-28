"""策略頁・總經策略的兩頁（arm/lab/macpage.py；docs/lab_strategy_ia_plan.md）：比照個股策略的這一期、規則與成績。"""
import json
import re
import shutil
import subprocess

import pytest

from arm.lab import macpage as M
from arm.lab import page

BANNED = ("保證", "穩賺", "必賺", "包賺", "必漲", "必跌", "一定會", "唯一", "建議買賣", "建議買", "建議賣", "目標價",
          "零風險", "無風險", "穩賺不賠")


def test_views_reuse_stock_strategy_components():
    """這一期＝摘要（四格數字、下一個交易日、時間軸、文字時間表）→ 一條策略一張卡（做法／隱含獲利／現在／下一次）；
    規則與成績＝比較表＋判定方式。卡片、摘要、比較表用個股策略同一組元件與樣式（sec、sq、kp、tlnx、bkt）。"""
    js = M.JS
    assert "function vMac(" in js and "function vMacSt(" in js
    assert "xmSum(M)+xmNextDay(M)+xmTlSec()+`<details class=mr><summary>時間表（文字）</summary>${xmCalTxt(M)}</details>`" in js
    assert "rows=[['做法',esc(c.how)],[`隱含獲利${gi('隱含獲利（總經）')}`,xmExp(c)],['現在',xmNow(c)]]" in js and "rows.push(['下一次',nx])" in js
    assert "sec('m-'+c.k" in js and "<div class=\"card stc\">" in js and "<span class=orank>" in js and "`<div class=\"kpis osum\">`" in js
    assert "<table class=bkt>" in js and "sec('mb-book'" in js and "sec('mb-mth'" in js
    # 規則與成績：比較表 → 一條一張說明卡（同個股策略 stCard：結論／怎麼做／過去成績／逐筆交易／風險；判定依據收起來）→ 判定方式
    assert "h+=xmBook(M)+(M.book||[]).map(xmStCard).join('')+xmMethod();" in js
    assert "const parts=[['結論'," in js and "['怎麼做',how],['過去成績',xmPast(b)]]" in js and "parts.push(['逐筆交易',tb])" in js
    assert "parts.push(['風險',riskList(ex.risk)],['判定依據',xmJdBox(b)]);" in js and "sec('ms-'+k" in js
    assert 'data-go="macst" data-at="ms-${esc(c.k)}"' in js and '<a data-to="ms-${esc(b.k)}">' in js     # 這一期的卡、比較表 → 說明卡
    assert "yearTbl({yearly:rows,all:{d0:(b.exp||{}).d0}},'買進持有',Y.to||'',10)" in js and "acurveChart({d:" in js   # 個股策略同一個表、同一張圖
    assert "fetch('x9xh.json')" in js and "xmLazy('details.xmtrb'" in js and "xmLazy('details.xmjd'" in js
    assert "function pgSeg(" in js and "data-go=\"${a}\"" in js                   # 兩頁切換（個股策略也用）
    assert "xmHead('mac')" in js and "xmHead('macst')" in js and 'data-mmk="${esc(k)}"' in js
    assert "Object.assign(GL,{" in js and "GLG.push(['總經策略'," in js
    assert not [w for w in BANNED if w in js + M.CSS]


def test_page_wires_personas_and_both_strategy_families():
    js = page._JS
    assert "pgSeg('opp','opp','st')" in js and "pgSeg('st','opp','st')" in js          # 個股策略：這一期｜規則與成績
    assert "const PERS={tw:'pick',us:'pick',stk:'pick',chip:'pick',idx:'pick',opp:'r',st:'r',mac:'r',macst:'r',plan:'r',strat:'r',bo:'r'};" in js
    assert "function setPer(p)" in js and "function urlSet()" in js and "$$('.apptab a[data-k]')" in js
    assert "if(x&&TABG[v]==='mac')" in js and "else{v='macst';at='ms-'+x;}" in js        # #v=mac&m=市場&x=策略：這一期的卡片或說明卡
    # 個股策略的逐年報酬表、1 元變多少：多出來的參數不給就跟原本一樣（總經策略才給）
    assert "function yearTbl(b,lb,last,keep)" in js and "const cut=keep&&n>keep+2?n-keep:0;" in js
    assert "function acurveChart(C,lb)" in js and "W=acW()" in js and "acLg(C.s[n-1],lt,C.d[0],lb)" in js
    assert '<a data-t="stg" data-p="r" hidden>個股策略</a><a data-t="mac" data-p="r" hidden>總經策略</a>' in page._HTML   # 研究紀錄身分


@pytest.mark.skipif(shutil.which("node") is None, reason="沒有 node")
def test_strategy_views_render_in_node():
    """用真的資料在 node 裡畫一次總經策略兩頁（沒有瀏覽器：$('#main') 換成一個物件），看得到卡片、比較表、時間表。"""
    from arm.lab import xsadvice as XA
    D = {"mac": XA.build(), "adv": {}, "rows": []}
    stub = ("const document={querySelector:()=>null,querySelectorAll:()=>[],addEventListener(){},documentElement:{}};"
            "const window={};const MAIN={innerHTML:''};const $=s=>s==='#main'?MAIN:null,$$=()=>[];const localStorage={getItem:()=>null,setItem(){}};"
            "const innerWidth=1200,addEventListener=()=>{},matchMedia=()=>({matches:false,addEventListener(){}});"
            "const D=" + json.dumps(D, ensure_ascii=False) + ";const S={mmk:'tw'};const GL={},GLG=[];"
            "function f(x,d=1){return x==null?'—':Number(x).toFixed(d);}function esc(s){return String(s??'');}"
            "function md(d){return d?`${+d.slice(5,7)}/${+d.slice(8,10)}`:'—';}function mdw(d){return md(d);}function ym(d){return d?d.slice(0,7):'—';}"
            "function pctT(x,d=1){return x==null?'—':(x>0?'+':'')+Number(x).toFixed(d)+'%';}function sgn(x,d,s){return pctT(x,d);}"
            "function fp(x){return String(x);}function gi(){return '';}function kp(a,b,c,d){return `<div class=kp>${a}${c}${d}</div>`;}"
            "function sq(k,v){return `<div class=sq>${k}${v}</div>`;}function tBadge(t){return t;}const TN={},TMK={};"
            "function sec(id,nav,t,sub,body){return `<section id=${id}>${t}${sub}${body}</section>`;}"
            "function ruleRows(r){return r.join('|');}function jump(){}function tlDraw(){}const VZS={mtl:'all'};function vzDay(){return 0;}"
            "function riskList(x){return (x||[]).join('|');}function yearTbl(b){return '<table class=yrt>'+b.yearly.length+'</table>';}"
            "function acW(){return 400;}function acLg(s,t,d,lb){return `<div class=lg>${s}${t}${lb}</div>`;}function acurveChart(){return '';}"
            "function fetch(){return new Promise(()=>{});}")                    # x9xh.json 不會到：只看先畫的部分
    prog = (stub + M.JS + "\nconst out={};for(const mk of MAC.mks){S.mmk=mk;vMac();out[mk+':mac']=MAIN.innerHTML;vMacSt();out[mk+':st']=MAIN.innerHTML;}"
            "console.log(JSON.stringify(out));")
    r = subprocess.run(["node", "-"], input=prog, capture_output=True, text=True, timeout=60)   # 程式太長，用 stdin 給
    assert r.returncode == 0, r.stderr[-2000:]
    out = json.loads(r.stdout)
    for mk in D["mac"]["mks"]:
        Mk = D["mac"]["m"][mk]
        h, st = out[mk + ":mac"], out[mk + ":st"]
        assert "<section id=m-sum>" in h and h.count("<section id=m-") == 1 + len(Mk["cards"])
        for c in Mk["cards"]:
            assert f"<section id=m-{c['k']}>" in h and c["how"] in h and c["now"] in h
        assert "<section id=mb-book>" in st and all(f'id="mb-{b["k"]}"' in st for b in Mk["book"])
        for b in Mk["book"]:                                                     # 說明卡：比較表每一條都有（含 ○、—）
            assert f"<section id=ms-{b['k']}>" in st and b["ex"]["concl"] in st and b["ex"]["tl"] in st
            assert all(x in st for x in b["ex"]["risk"]) and f'data-xk="{b["k"]}"' in st
        assert st.count("class=xmcv") == len(Mk["book"]) and st.count('class="mr xmjd"') == len(Mk["book"])
        assert st.count('class="mr trb xmtrb"') == sum(1 for b in Mk["book"] if b["exp"]["nt"])
        assert st.index("<section id=mb-book>") < st.index("<section id=ms-") < st.index("<section id=mb-mth>")
        assert not [w for w in BANNED if w in re.sub(r"<[^>]+>", "", h + st)]


@pytest.mark.skipif(shutil.which("node") is None, reason="沒有 node")
def test_trade_check_and_judge_render_from_detail_json():
    """說明卡打開之後由 x9xh.json 畫的兩段（真資料、node 實際跑頁面的函式）：
    逐筆交易上方那一句重算的平均、中位、賺錢比例＝卡片上的數字（宣稱「就是上方結論的數字」）；判定依據每一項都列出來、參數鄰近表格數對。"""
    from arm.lab import xsadvice as XA
    from arm.lab import xspage as XP
    from arm.lab import xstrat as X
    R = X.run_all()
    D = {"mac": XA.build(R), "adv": {}, "rows": []}
    XMD = json.loads(XP.detail_json(XP.view(R)))
    pg = page._JS
    helpers = "\n".join(pg[pg.index(f"function {n}("):pg.index("\n", pg.index(f"function {n}("))] for n in ("avgOf", "medOf", "winOf"))
    stub = ("const document={querySelector:()=>null,addEventListener(){},documentElement:{}};const window={};const $=()=>null,$$=()=>[];"
            "const innerWidth=1200,addEventListener=()=>{};const D=" + json.dumps(D, ensure_ascii=False) + ";const S={mmk:'tw'};const GL={},GLG=[];"
            "function f(x,d=1){if(x===null||x===undefined||Number.isNaN(x))return '—';return Number(x).toLocaleString('zh-TW',{minimumFractionDigits:d,maximumFractionDigits:d});}"
            "function esc(s){return String(s??'');}function md(d){return d;}function mdw(d){return d;}function ym(d){return d;}function fp(x){return String(x);}"
            "function pctT(x,d=1){return x==null?'—':(x>0?'+':x<0?'−':'')+f(Math.abs(x),d)+'%';}function sgn(x,d,s){return pctT(x,d);}function gi(){return '';}"
            "function tBadge(t){return t;}const TN={},TMK={};function sec(){return '';}function kp(){return '';}function sq(){return '';}const VZS={};"
            + helpers)
    prog = (stub + M.JS + "\nXMD=" + json.dumps(XMD, ensure_ascii=False) + ";const out={};"
            "for(const mk of MAC.mks){S.mmk=mk;for(const b of MCM[mk].book){const j=XMD['xs:'+mk+':'+b.k];"
            "out[mk+':'+b.k]={chk:xmTrCheck(b,j.tr),jd:xmJd(b.k)};}}console.log(JSON.stringify(out));")
    r = subprocess.run(["node", "-"], input=prog, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    out = json.loads(r.stdout)
    pct = lambda x, d: ("+" if x > 0 else "−" if x < 0 else "") + f"{abs(x):,.{d}f}%"
    for mk, Mk in D["mac"]["m"].items():
        for b in Mk["book"]:
            o, e = out[f"{mk}:{b['k']}"], b["exp"]
            d = 2 if b["kind"] == "trade" else 1
            if e.get("n"):
                assert f"已賣出：{e['n']} {e['unit']}，平均 <b>{pct(e['avg'], d)}</b>、中位 {pct(e['med'], d)}，{e['win']}% 賺錢" in o["chk"], (mk, b["k"])
            jd = XMD[f"xs:{mk}:{b['k']}"]["jd"]
            assert o["jd"].count("class=rbr") == len(jd["why"]) and o["jd"].count("<td") == jd["grid"]["n"]
            assert o["jd"].count('class="xmmn"') == 1 and (jd["ref"] is None or jd["ref"] in o["jd"])


JARGON = ("VER", "候選", "門檻", "夏普", "前後兩半", "95%", "區間", "扣掉波動", "BH", "固定持有", "樣本外")


def test_old_plan_section_is_gone():
    """上一版交易計畫（策略頁・總經策略最上面「照著做」；planspec）2026-10-23 拿掉：使用者說比一直抱著還差。
    新的交易計畫（核心 70%＋衛星 30%，corespec）放在訊號總覽・研究結論（docs/lab_core70_plan.md）。"""
    js = M.JS
    assert "xpSec" not in js and "m-plan" not in js and "xpl" not in M.CSS
    assert "x==='plan'" not in page._JS
    src = (page.Path(page.__file__)).read_text(encoding="utf-8")
    assert "plan.build()" not in src and "stk_from_adv" in src


