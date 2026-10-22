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
    assert "h+=xmBook(M)+xmMethod();" in js
    assert "function pgSeg(" in js and "data-go=\"${a}\"" in js                   # 兩頁切換（個股策略也用）
    assert "xmHead('mac')" in js and "xmHead('macst')" in js and 'data-mmk="${esc(k)}"' in js
    assert "Object.assign(GL,{" in js and "GLG.push(['總經策略'," in js
    assert not [w for w in BANNED if w in js + M.CSS]


def test_page_wires_personas_and_both_strategy_families():
    js = page._JS
    assert "pgSeg('opp','opp','st')" in js and "pgSeg('st','opp','st')" in js          # 個股策略：這一期｜規則與成績
    assert "const PERS={opp:'st',st:'st',mac:'st',macst:'st',stk:'stk',chip:'stk',idx:'stk'};" in js
    assert "function setPer(p)" in js and "function urlSet()" in js and "$$('.apptab a')" in js
    assert "if(x&&TABG[v]==='mac')" in js                                               # #v=mac&m=市場&x=策略：卡片或比較表那一列
    assert '<a data-t="mac" data-p="st" hidden>總經策略</a><a data-t="stg" data-p="st" hidden>個股策略</a>' in page._HTML


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
            "function ruleRows(r){return r.join('|');}function jump(){}function tlDraw(){}const VZS={mtl:'all'};function vzDay(){return 0;}")
    prog = (stub + M.JS + "\nconst out={};for(const mk of MAC.mks){S.mmk=mk;vMac();out[mk+':mac']=MAIN.innerHTML;vMacSt();out[mk+':st']=MAIN.innerHTML;}"
            "console.log(JSON.stringify(out));")
    r = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-2000:]
    out = json.loads(r.stdout)
    for mk in D["mac"]["mks"]:
        Mk = D["mac"]["m"][mk]
        h, st = out[mk + ":mac"], out[mk + ":st"]
        assert "<section id=m-sum>" in h and h.count("<section id=m-") == 1 + len(Mk["cards"])
        for c in Mk["cards"]:
            assert f"<section id=m-{c['k']}>" in h and c["how"] in h and c["now"] in h
        assert "<section id=mb-book>" in st and all(f'id="mb-{b["k"]}"' in st for b in Mk["book"])
        assert not [w for w in BANNED if w in re.sub(r"<[^>]+>", "", h + st)]
