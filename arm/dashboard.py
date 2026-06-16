"""M7 零安裝靜態儀表板 —— 把每日想法報告 + 文案層轉成一頁 self-contained HTML。

設計：延續專案「零安裝」DNA。純標準庫讀 `reports/*.md`（經 `arm.copy` 解析、生成文案、合規/數字
把關），組成資料模型 → 內嵌進單一 `dashboard/index.html`（vanilla JS 渲染，無 npm/node/server，
雙擊即開）。與 M6 同樣**只讀已發布報告**，零碰 pipeline/ideas/brokers/chips/etfinfo。

亮點：**今日 5 大創意切角**——從當日想法挑 5 個**不同面向**、附創意框架與最佳文案，天天有變化。
若該檔當日有 prompt-pack 回灌（responses/{date}_{etf}.json），自動顯示 ✨ Claude 創意升級版。
"""
from __future__ import annotations

import json
from datetime import datetime

from . import copy as cp
from .copy import baseline, prompt_pack

# 面向 → (創意框架標題, 一句創意定調)；讓每個切角有記憶點、不只是分類名。
CREATIVE_ANGLE = {
    "績效": ("翻倍實證", "用時間軸證明主動操作的價值"),
    "資金流": ("錢往哪裡流", "資金用腳投票，人氣即風向"),
    "同類排名": ("同類榜上的位置", "把對手放同一把尺上比"),
    "籌碼": ("經理人在想什麼", "從換股動作讀操盤思路"),
    "分點推敲": ("聰明錢的腳步", "跟著法人/外資的籌碼走"),
    "持股差異化": ("別人沒有的牌", "獨門卡位才是 Alpha 來源"),
    "題材": ("風口上的卡位", "把當日熱題接到本檔持股"),
    "配息時程": ("倒數現金流", "用時間壓力催出布局動機"),
    "逆向誠實": ("把弱點變理由", "先承認短空，再轉成進場點"),
    "同業招數": ("對手的招、我們的解", "借鏡同業話術反向操作"),
    "社群KOL": ("KOL 在聊什麼", "借社群熱度與輿論風向"),
    "成交量": ("量能說話", "爆量是資金的表態"),
    "量能": ("量能說話", "爆量是資金的表態"),
}
_DEFAULT_ANGLE = ("今日切角", "從這個角度切入本檔")


def _flag_model(f) -> dict:
    return {"sev": f.severity, "emoji": f.emoji, "name": f.name, "fix": f.fix,
            "disclosures": list(f.disclosures)}


def _idea_model(r) -> dict:
    idea = r.idea
    label, tagline = CREATIVE_ANGLE.get(idea.category, _DEFAULT_ANGLE)
    channels = {}
    for ch in baseline.CHANNELS:
        c = r.channels[ch]
        channels[ch] = {
            "text": c.text, "source": c.source,
            "fabricated": list(c.fabricated),
            "flags": [_flag_model(f) for f in c.flags],
        }
    return {
        "idx": idea.idx, "category": idea.category, "conf": idea.conf,
        "angle_label": label, "angle_tagline": tagline,
        "headline": idea.headline, "evidence": idea.evidence,
        "content_format": idea.content_format,
        "allowed": sorted(r.allowed),
        "channels": channels,
        "enhanced": any(c.source == "llm" for c in r.channels.values()),
    }


def top5_angles(idea_models: list[dict]) -> list[int]:
    """挑 5 個『不同面向』的想法 idx：依報告排序貪婪取首見面向，不足 5 再補。"""
    picked, seen = [], set()
    for m in idea_models:
        if m["category"] not in seen:
            picked.append(m["idx"])
            seen.add(m["category"])
        if len(picked) == 5:
            return picked
    for m in idea_models:                          # 面向不足 5 種 → 補滿
        if m["idx"] not in picked:
            picked.append(m["idx"])
        if len(picked) == 5:
            break
    return picked


def build_etf_model(etf_id: str, *, date=None) -> dict:
    doc = cp.parse_file(cp.latest_report(etf_id, date=date))
    llm, enhanced_src = None, "baseline"
    rp = prompt_pack.response_path(doc)
    if rp.exists():
        resp = prompt_pack.load_response(rp)
        if resp:
            llm = prompt_pack.as_llm(resp)
            enhanced_src = "prompt-pack"
    if llm is None and cp.default_llm() is not None:
        llm, enhanced_src = cp.default_llm(), "api"
    results = cp.generate_doc(doc, llm=llm)
    ideas = [_idea_model(r) for r in results]
    fab = sum(len(c["fabricated"]) for m in ideas for c in m["channels"].values())
    banned = sum(1 for m in ideas for c in m["channels"].values()
                 for f in c["flags"] if f["sev"] == "高")
    return {
        "id": doc.etf_id, "name": doc.name, "short_name": baseline.short_name(doc.name),
        "date": doc.date, "header": doc.header,
        "ideas": ideas, "top5": top5_angles(ideas),
        "enhanced_src": enhanced_src,
        "stats": {"ideas": len(ideas), "fabricated": fab, "banned": banned},
    }


def build_model(*, date=None) -> dict:
    etfs = []
    for etf_id in cp.list_etf_ids():
        try:
            etfs.append(build_etf_model(etf_id, date=date))
        except FileNotFoundError:
            continue
    return {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "etfs": etfs}


# ───────────────────────── HTML 渲染（自含、零依賴） ─────────────────────────
def render_html(model: dict) -> str:
    data = json.dumps(model, ensure_ascii=False).replace("</", "<\\/")
    return _SHELL.replace("/*__DATA__*/", data)


_SHELL = r"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FH-ARM 每日行銷情報雷達</title>
<style>
:root{--bg:#0f1220;--card:#1a1f33;--card2:#222942;--ink:#eef1f8;--mut:#9aa3bd;
--acc:#6ea8fe;--teal:#4fd1c5;--amber:#f6c453;--red:#ff6b6b;--green:#51cf66;--line:#2c3350}
*{box-sizing:border-box}
body{margin:0;font-family:"PingFang TC","Noto Sans TC","Microsoft JhengHei",system-ui,sans-serif;
background:linear-gradient(180deg,#0b0e1a,#0f1220);color:var(--ink);line-height:1.55}
.wrap{max-width:1180px;margin:0 auto;padding:18px 20px 60px}
header.top{display:flex;flex-wrap:wrap;align-items:baseline;gap:10px 16px;margin-bottom:6px}
header.top h1{font-size:20px;margin:0;letter-spacing:.5px}
header.top .gen{color:var(--mut);font-size:12px}
.tabs{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0 6px}
.tab{padding:8px 16px;border:1px solid var(--line);border-radius:999px;background:var(--card);
color:var(--mut);cursor:pointer;font-size:14px;font-weight:600;transition:.15s}
.tab:hover{color:var(--ink);border-color:var(--acc)}
.tab.on{background:var(--acc);color:#0b0e1a;border-color:var(--acc)}
.etfhead{margin:14px 0 4px}
.etfhead h2{margin:0 0 4px;font-size:22px}
.etfhead .hdr{color:var(--mut);font-size:13px;margin-bottom:10px}
.badges{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:6px}
.badge{font-size:12px;padding:3px 10px;border-radius:8px;background:var(--card2);color:var(--mut);border:1px solid var(--line)}
.badge.ok{color:var(--green)} .badge.warn{color:var(--red)} .badge.src{color:var(--teal)}
.sec{margin:26px 0 10px;font-size:15px;font-weight:700;letter-spacing:.5px;color:var(--ink);
display:flex;align-items:center;gap:8px}
.sec .pill{font-size:11px;color:var(--mut);font-weight:500}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;position:relative}
.card .alabel{font-size:18px;font-weight:800;color:var(--teal);margin-bottom:2px}
.card .tagline{font-size:12px;color:var(--mut);margin-bottom:10px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}
.chip{font-size:11px;padding:2px 8px;border-radius:6px;background:var(--card2);color:var(--mut)}
.chip.cat{color:var(--acc)}
.hl{font-size:14.5px;font-weight:600;margin:6px 0}
.ev{font-size:12.5px;color:var(--mut);margin-bottom:10px}
.hook{background:linear-gradient(90deg,#1f2742,#1a1f33);border-left:3px solid var(--teal);
padding:8px 12px;border-radius:6px;font-size:14px;margin-bottom:10px}
.chtabs{display:flex;gap:6px;margin:6px 0}
.chtab{font-size:12px;padding:4px 10px;border-radius:7px;border:1px solid var(--line);
background:transparent;color:var(--mut);cursor:pointer}
.chtab.on{background:var(--card2);color:var(--ink);border-color:var(--acc)}
.chbody{background:#10142433;border:1px solid var(--line);border-radius:8px;padding:10px;font-size:13px;white-space:pre-wrap}
.copybtn{float:right;font-size:11px;color:var(--acc);background:none;border:1px solid var(--line);
border-radius:6px;padding:2px 8px;cursor:pointer}
.copybtn:hover{border-color:var(--acc)}
.fab{color:var(--red);font-size:12px;margin-top:6px}
.flag{font-size:12px;margin-top:5px;color:var(--mut)}
.flag .e{margin-right:4px}
.sev-高{color:var(--red)} .sev-中{color:var(--amber)} .sev-低{color:var(--green)}
.enh{position:absolute;top:12px;right:14px;font-size:11px;color:var(--teal)}
details.idea{background:var(--card);border:1px solid var(--line);border-radius:12px;margin-bottom:10px;padding:0 14px}
details.idea summary{cursor:pointer;padding:13px 0;font-size:14px;font-weight:600;list-style:none;display:flex;gap:8px;align-items:center}
details.idea summary::-webkit-details-marker{display:none}
details.idea[open]{padding-bottom:14px}
.note{color:var(--mut);font-size:12px;margin-top:24px;border-top:1px solid var(--line);padding-top:14px}
.up{background:#172033;border:1px solid var(--line);border-radius:12px;padding:14px;margin:14px 0;font-size:13px;color:var(--mut)}
.up b{color:var(--teal)}
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <h1>📡 FH-ARM 每日行銷情報雷達</h1>
    <span class="gen" id="gen"></span>
  </header>
  <div class="tabs" id="tabs"></div>
  <div id="panel"></div>
  <div class="note" id="note"></div>
</div>
<script>
const DATA = /*__DATA__*/;
const CH = [["punchy","Hook"],["line","LINE 推播"],["ig","IG 貼文"],["sales","理專話術"]];
const SRC = {baseline:"baseline 模板（未接 LLM）","prompt-pack":"prompt-pack 回灌（Claude 創意升級）",api:"Claude 自動 API 潤稿"};
const esc = s => (s||"").replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
let cur = 0;

function copyText(t,btn){navigator.clipboard&&navigator.clipboard.writeText(t).then(()=>{btn.textContent="已複製✓";setTimeout(()=>btn.textContent="複製",1200)});}

function channelBlock(idea, idprefix){
  const tabs = CH.map(([k,l],i)=>`<button class="chtab${i===0?' on':''}" data-t="${idprefix}-${k}">${l}${idea.channels[k].source==='llm'?' ✨':''}</button>`).join("");
  const bodies = CH.map(([k,l],i)=>{
    const c = idea.channels[k];
    const fab = c.fabricated.length?`<div class="fab">🔴 疑似杜撰數字：${c.fabricated.join("、")} → 請改回證據數字</div>`:"";
    const flags = c.flags.map(f=>`<div class="flag sev-${f.sev}"><span class="e">${f.emoji}</span>合規[${f.sev}] ${esc(f.name)} → ${esc(f.fix)}</div>`).join("");
    return `<div id="${idprefix}-${k}" class="chbody" style="display:${i===0?'block':'none'}">
      <button class="copybtn" data-copy="${idprefix}-raw-${k}">複製</button>
      <span id="${idprefix}-raw-${k}">${esc(c.text)}</span>${fab}${flags}</div>`;
  }).join("");
  return `<div class="chtabs">${tabs}</div>${bodies}`;
}

function heroCard(idea){
  const p = "h"+idea.idx;
  return `<div class="card">
    ${idea.enhanced?'<span class="enh">✨ 創意升級</span>':''}
    <div class="alabel">${esc(idea.angle_label)}</div>
    <div class="tagline">${esc(idea.angle_tagline)}</div>
    <div class="chips"><span class="chip cat">${esc(idea.category)}</span><span class="chip">${idea.conf}</span><span class="chip">可用數字 ${idea.allowed.length}</span></div>
    <div class="hl">${esc(idea.headline)}</div>
    <div class="ev">📊 ${esc(idea.evidence)}</div>
    <div class="hook">「${esc(idea.channels.punchy.text.split("\n")[0])}」</div>
    ${channelBlock(idea,p)}
  </div>`;
}

function ideaRow(idea){
  const p = "i"+idea.idx;
  return `<details class="idea"><summary><span class="chip cat">${esc(idea.category)}</span>${idea.conf} ${esc(idea.headline)}</summary>
    <div class="ev">📊 ${esc(idea.evidence)}　·　可用數字：${idea.allowed.join("、")||"—"}</div>
    ${channelBlock(idea,p)}</details>`;
}

function renderETF(etf){
  const top = etf.ideas.filter(m=>etf.top5.includes(m.idx));
  const s = etf.stats;
  const html = `
   <div class="etfhead">
     <h2>${esc(etf.name)}（${etf.id}）</h2>
     <div class="hdr">資料日 ${etf.date}　·　${esc(etf.header)}</div>
     <div class="badges">
       <span class="badge">${s.ideas} 則想法</span>
       <span class="badge ${s.fabricated?'warn':'ok'}">疑似杜撰數字 ${s.fabricated}</span>
       <span class="badge ${s.banned?'warn':'ok'}">禁用字眼 ${s.banned}</span>
       <span class="badge src">文案來源：${SRC[etf.enhanced_src]||etf.enhanced_src}</span>
     </div>
   </div>
   <div class="up">💡 <b>想更有創意？</b>baseline 是合規骨架；要 Claude 創意潤稿又不接 API key，跑
     <code>python3 scripts/gen_copy.py ${etf.id}</code> 產 prompt-pack，貼進你的 Claude、回覆存到
     <code>reports/copy/responses/${etf.date}_${etf.id}.json</code>，重跑本儀表板即顯示 ✨ 升級版（數字/合規照樣把關）。</div>
   <div class="sec">🎯 今日 5 大創意切角 <span class="pill">每天挑 5 個不同面向、自動換</span></div>
   <div class="grid">${top.map(heroCard).join("")}</div>
   <div class="sec">📋 全部想法 <span class="pill">${etf.ideas.length} 則 · 點開看四通路文案</span></div>
   <div>${etf.ideas.map(ideaRow).join("")}</div>`;
  document.getElementById("panel").innerHTML = html;
  bindChannel();
}

function bindChannel(){
  document.querySelectorAll(".chtab").forEach(b=>b.onclick=()=>{
    const id=b.dataset.t, group=id.replace(/-(punchy|line|ig|sales)$/,"");
    b.parentElement.querySelectorAll(".chtab").forEach(x=>x.classList.remove("on"));
    b.classList.add("on");
    CH.forEach(([k])=>{const el=document.getElementById(group+"-"+k); if(el) el.style.display="none";});
    const tgt=document.getElementById(id); if(tgt) tgt.style.display="block";
  });
  document.querySelectorAll(".copybtn").forEach(b=>b.onclick=()=>{
    const el=document.getElementById(b.dataset.copy); if(el) copyText(el.textContent,b);
  });
}

function init(){
  document.getElementById("gen").textContent = "產出時間 "+DATA.generated_at;
  if(!DATA.etfs.length){document.getElementById("panel").innerHTML="<p>尚無報告，請先跑 scripts/run_daily.py 與 scripts/gen_copy.py。</p>";return;}
  document.getElementById("tabs").innerHTML = DATA.etfs.map((e,i)=>
    `<div class="tab${i===0?' on':''}" data-i="${i}">${esc(e.short_name)}<small> ${e.id}</small></div>`).join("");
  document.querySelectorAll(".tab").forEach(t=>t.onclick=()=>{
    cur=+t.dataset.i;
    document.querySelectorAll(".tab").forEach(x=>x.classList.remove("on"));
    t.classList.add("on"); renderETF(DATA.etfs[cur]);
  });
  document.getElementById("note").innerHTML =
    "想法引擎自動產出；合規為事後標注、<b>不阻擋</b>發想；文案數字僅取自當日證據，疑似杜撰標 🔴。對外發布前請法遵複核。";
  renderETF(DATA.etfs[0]);
}
init();
</script>
</body>
</html>"""
