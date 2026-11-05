"""盤前作戰圖的畫面（選擇權頁 x9op.html 最上面；資料 data/lab/premkt.json，arm/lab/premkt.py 算）。

伺服器端畫好；只有「可買幾口」由頁面用計算機的帳戶與每筆上限設定算（設定只存在使用者瀏覽器，localStorage 'txoCalc'）。
CSS class 一律 op 開頭（txopage 的命名空間）。
"""
from __future__ import annotations

import html

CSS = (".oplad td{vertical-align:top}.oplad td.opsrc{text-align:left;white-space:normal;color:var(--ink2);font-size:12.5px}.oplad th:last-child{text-align:left;white-space:normal}"
       ".oplad tr.opest td{background:var(--accbg);font-weight:700}.opdist{color:var(--mut);font-size:12.5px;font-weight:400}"
       ".opdot{color:var(--acc);letter-spacing:1px}"
       ".opsc{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:10px;margin:8px 0}"
       ".opsc>div{border:1px solid var(--line);border-radius:12px;padding:10px 12px;font-size:13.5px;line-height:1.6}"
       ".opsc h3{font-size:15px;margin:0 0 4px}.opsc .opsch{color:var(--mut);font-size:12.5px;margin:0 0 6px}"
       ".opsc dl{display:grid;grid-template-columns:auto 1fr;gap:2px 10px;margin:0}.opsc dt{color:var(--mut)}"
       ".opsc dd{margin:0;font-variant-numeric:tabular-nums}"
       ".opfx td:nth-child(2){text-align:left;white-space:normal}.opfx td:nth-child(3){color:var(--mut);font-size:12px}"
       ".opwarn{margin:8px 0;padding:7px 12px;border-radius:8px;background:var(--sbg);font-size:13.5px}"
       ".opmore{margin:10px 0;font-size:13px;color:var(--ink2);line-height:1.7}.opmore summary{cursor:pointer;color:var(--acc)}")

JS = r"""<script>(function(){
var w=document.getElementById('pmstale');var t=new Date(Date.now()+8*3600e3).toISOString().slice(0,10);
if(w&&t>w.dataset.next)w.hidden=false;
var st={acct:1000000,cap:'O1'};try{Object.assign(st,JSON.parse(localStorage.getItem('txoCalc')||'{}'))}catch(e){}
var cap={O1:0.02,O2:0.03,O3:0.05}[st.cap]||0.02;
document.querySelectorAll('.oplots').forEach(function(d){var one=+d.dataset.one;var n=one>0?Math.floor(st.acct*cap/one):0;
d.textContent=n>0?('帳戶 '+Math.round(st.acct).toLocaleString('zh-TW')+' 元、每筆 '+Math.round(cap*100)+'%：最多 '+n+' 口')
:'帳戶 '+Math.round(st.acct).toLocaleString('zh-TW')+' 元、每筆 '+Math.round(cap*100)+'%：買不到 1 口';});
})();</script>"""


def _n(x, sign: bool = False) -> str:
    if x is None:
        return "—"
    v = f"{abs(x):,.0f}"
    if sign:
        return ("+" if x > 0 else "−" if x < 0 else "") + v
    return ("−" if x < 0 else "") + v


def block(pm: dict | None) -> str:
    from .premkt import KINDS, md, wd
    e = html.escape
    if not pm:
        return ('<h1>盤前作戰圖</h1><p class="oplead">盤前作戰圖還沒準備好：每個交易日收盤後先算一版，'
                '清晨 05:10 用夜盤更新。</p>')
    em = pm.get("em")
    out = [f'<h1>盤前作戰圖 {md(pm["next"])}（{wd(pm["next"])}）</h1>',
           '<p class="oplead">以加權指數為準：預估開盤、正常會動多少、上下的壓力支撐（每個價位寫來源，幾種來源擠在同一帶＝較強）、'
           '籌碼期貨指標的事實、在這些價位做的風險報酬。只是整理與試算，不是買賣建議；'
           '哪些價位、哪些籌碼真的有用，要等第 3 段用歷史驗證過才標。</p>',
           f'<div class="opwarn" id="pmstale" hidden data-next="{e(pm["next"])}">這份是 {md(pm["next"])} 開盤前的，已經過期；'
           '下一份收盤後會更新。</div>']
    for w in pm.get("warn") or []:
        out.append(f'<div class="opwarn">{e(w)}</div>')
    nt = pm.get("night") or {}
    items = [(_n(pm["est"]), "預估開盤（" + pm["est_src"] + "）"),
             (f"±{_n(em)}" if em else "—", f"正常波動（極端 ±{_n(2 * em) if em else '—'}）"),
             (_n(pm["close"]), f"{md(pm['d'])} 收盤（高 {_n(pm['hi'])}、低 {_n(pm['lo'])}）")]
    if nt.get("c") is not None:
        items.append((_n(nt["c"]), "夜盤台指期" + ("收盤" if nt.get("done") else f"（到 {nt.get('t')}）")))
    out.append('<div class="opfacts">' + "".join(f"<div><b>{e(a)}</b><span>{e(b)}</span></div>" for a, b in items) + "</div>")
    chk = pm.get("check") or []
    note = ("預估開盤＝前一天加權指數收盤＋（夜盤台指期收盤 − 台指期 13:30 的價格）。清晨 05:00 到 08:45 之間的消息也會動，"
            "這個估法平均差幾點要等第 3 段量。")
    if chk:
        note += "最近：" + "；".join(f"{md(c['d'])} 估 {_n(c['est'])}、實際開 {_n(c['open'])}（差 {_n(c['open'] - c['est'], True)}）"
                                    for c in chk) + "。"
    out.append(f'<p class="opnote">{e(note)}</p>')
    # 價位梯
    out.append('<h2>壓力與支撐</h2><div class="optw"><table class="opt oplad"><thead><tr><th>價位</th>'
               '<th>來源（● 越多＝來源越多種）</th></tr></thead><tbody>')
    rows = sorted(pm.get("bands") or [], key=lambda b: -b["mid"])
    est_done = False
    for b in rows + [None]:
        if not est_done and (b is None or b["side"] != "up"):
            rng = f'正常波動 {_n(pm["est"] - em)}～{_n(pm["est"] + em)}' if em else ""
            out.append(f'<tr class="opest"><td>{_n(pm["est"])}<br><span class="opdist">預估開盤</span></td>'
                       f'<td class="opsrc">{rng}</td></tr>')
            est_done = True
        if b is None:
            break
        rng = _n(b["lo"]) if b["lo"] == b["hi"] else f"{_n(b['lo'])}～{_n(b['hi'])}"
        dist = b["mid"] - pm["est"]
        k = f"（{abs(dist) / em:.1f} 倍）" if em else ""
        tag = {"up": "壓力", "dn": "支撐", "at": "開盤在這帶裡"}[b["side"]]
        src = "、".join(f"{n} {_n(v)}" for n, v in b["src"])
        out.append(f'<tr><td>{rng}<br><span class="opdist">{tag} {_n(dist, True)}{k}</span></td>'
                   f'<td class="opsrc"><span class="opdot">{"●" * min(b["n"], 4)}</span> {e(src)}</td></tr>')
    out.append("</tbody></table></div>")
    out.append('<p class="opnote">強度＝這一帶裡有幾種來源（' + "、".join(KINDS.values()) + '）；價位相差 0.25% 以內併成一帶，'
               '只列預估開盤上下各 3 帶、2 倍正常波動以內；括號裡是離預估開盤幾倍正常波動。期貨與夜盤的價位已經扣掉期現價差，換成加權指數。</p>')
    for t in pm.get("oi_note") or []:
        out.append(f'<p class="opnote">選擇權未平倉（全部履約價）：{e(t)}</p>')
    # 情境
    sc = pm.get("sc") or []
    if sc:
        out.append('<h2>風險報酬試算</h2><div class="opsc">')
        for c in sc:
            o, mt = c.get("opt"), c["mtx"]
            out.append(f'<div><h3>{e(c["name"])}</h3><p class="opsch">{e(c["why"])}</p><dl>'
                       f'<dt>進場</dt><dd>{_n(c["entry"])}</dd><dt>停損</dt><dd>{_n(c["stop"])}（{c["risk"]:,} 點）</dd>'
                       f'<dt>目標</dt><dd>{_n(c["target"])}（{c["reward"]:,} 點）</dd>'
                       f'<dt>報酬÷風險</dt><dd><b>{c["rr"]:.1f}</b></dd>'
                       f'<dt>小台一口</dt><dd>停損賠 {mt["loss"]:,} 元、到目標賺 {mt["gain"]:,} 元</dd>')
            if o:
                cpn = "買權" if o["cp"] == "C" else "賣權"
                rr = "—" if o.get("rr") is None else f"{o['rr']:.1f}"
                out.append(f'<dt>選擇權</dt><dd>買 {md(o["xd"])} 到期 {o["k"]:,} {cpn}：估 {o["pe"]:,.1f} 點進'
                           f'（假設 10:30、波動率 {o["iv"] * 100:.0f}%），停損時約 {o["ps"]:,.1f}、目標時約 {o["pt"]:,.1f}</dd>'
                           f'<dt>一口</dt><dd>停損賠 {o["loss"]:,} 元、到目標賺 {o["gain"]:,} 元（報酬÷風險 {rr}）；'
                           f'權利金歸零最多賠 {o["max"]:,} 元</dd><dt>可買</dt><dd class="oplots" data-one="{o["max"]}">—</dd>')
            out.append("</dl></div>")
        out.append("</div>")
        out.append('<p class="opnote">小台每點 50 元，成本算手續費 25 元、期交稅、1 點滑價（每邊）。選擇權用今天的隱含波動率估，'
                   '實際成交還有買賣價差。「可買」照下面計算機設定的帳戶與每筆上限算。</p>')
    # 事實
    fx = pm.get("facts") or []
    if fx:
        out.append('<h2>籌碼、期貨、指標</h2><div class="optw"><table class="opt opfx"><thead><tr><th>項目</th><th>數字</th>'
                   '<th>資料日</th></tr></thead><tbody>')
        for f in fx:
            nt2 = f'<br><span class="opdist">{e(f["note"])}</span>' if f.get("note") else ""
            out.append(f'<tr><td>{e(f["t"])}</td><td>{e(f["v"])}{nt2}</td><td>{md(f["d"]) if f.get("d") else ""}</td></tr>')
        out.append("</tbody></table></div>")
        out.append('<p class="opnote">只列數字、不標偏多偏空：常見說法（外資空單多＝偏空、P/C 比高＝偏多）在台股不一定成立，'
                   '第 3 段驗證過才標。</p>')
    out.append('<details class="opmore"><summary>價位怎麼算</summary>'
               '昨天價格＝加權指數日盤最高、最低、收盤；夜盤＝台指期夜盤最高、最低（扣掉 13:30 的期現價差）；'
               '樞紐點 P＝(高＋低＋收)÷3，壓力 1＝2P−低、支撐 1＝2P−高、壓力 2＝P＋(高−低)、支撐 2＝P−(高−低)；'
               '均線通道＝5、20、60 日均線、布林通道（20 日 ± 2 個標準差）、近 20 日收盤最高與最低；'
               '選擇權未平倉＝最近兩批（不含當天到期）在 2 倍正常波動內，買權未平倉最多（壓力）、賣權最多（支撐）與最大痛點；'
               '期貨成交量＝昨天台指期成交量最多的價位與包住 70% 成交量的上下緣；整數關卡＝每 500 點。'
               '情境：回測支撐＝在支撐帶上緣進、跌破下緣 0.1 倍正常波動停損、目標上方第一個壓力帶；'
               '突破＝站上壓力帶上緣 0.1 倍正常波動才進、回到帶子中間停損、目標再上一個壓力帶（空方對稱）。'
               f'更新：{e(pm.get("made") or "")}。</details>')
    out.append(JS)
    return "".join(out)
