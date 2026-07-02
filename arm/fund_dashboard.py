"""復華基金追蹤版本 · 零安裝儀表板（業務優先三層資訊架構）——
讀 data/funds/*.json + config/holding_profiles.json + config/holding_aliases.json
+ reports/usnews/{最新}_v1/_v2.md → 產單一 dashboard/index.html。

版面邏輯（見 docs/REDESIGN_PLAN.md）：3 秒／30 秒／3 分鐘三層——
  ⓪ Sticky 頂欄：日期｜合規燈｜錨點導覽
  ① 今日重點：三大指數／今日最強最弱／新聞連動計數／配息提醒
  ② 基金總覽表：11 檔一覽（可排序、紅漲綠跌、點列跳詳情）
  ③ 新聞 × 持股連動：受影響持股→持有基金→可複製中性話術（過禁用詞掃描才給複製）
  ④ 昨夜美股新聞全文（預設收合，保留 v1/v2 兩版型切換）
  ⑤ 基金詳情：逐檔卡片（錨點直達、同組平均對照、連動持股高亮、複製基金介紹）

純 vanilla HTML＋少量 JS（排序／複製／版型切換），零外部請求、雙擊即開，無 npm/node。
不做「每天持股變化」（共同基金無逐日持股張數）。
"""
from __future__ import annotations

import html
import re
from datetime import datetime

from . import fund_insights, fund_intro, twnews, usnews


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def _short(doc_or_name) -> str:
    """顯示用簡稱：去『復華』『(-)新臺幣』尾綴。"""
    n = doc_or_name if isinstance(doc_or_name, str) else \
        (doc_or_name.get("short_name") or doc_or_name.get("name") or "")
    n = n.replace("復華", "", 1)             # 只去品牌前綴（「復華復華基金」保留基金名）
    for suf in ("-新臺幣", "新臺幣"):
        if n.endswith(suf):
            n = n[: -len(suf)]
    return n or str(doc_or_name)


def _md(text: str) -> str:
    """極簡 Markdown → HTML（標題/粗體/連結/有序＋無序清單/水平線/段落）；先跳脫再套規則。"""
    if not text:
        return ""
    out: list[str] = []
    listtag: str | None = None

    def close():
        nonlocal listtag
        if listtag:
            out.append(f"</{listtag}>")
            listtag = None

    def open_list(tag):
        nonlocal listtag
        if listtag != tag:
            close()
            out.append(f"<{tag}>")
            listtag = tag

    for raw in text.splitlines():
        line = raw.rstrip()
        if re.match(r"^\s*---\s*$", line):
            close(); out.append("<hr>"); continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            close()
            lvl = min(len(m.group(1)) + 1, 6)
            out.append(f"<h{lvl}>{_inline(m.group(2))}</h{lvl}>"); continue
        m = re.match(r"^\s*[-*]\s+(.*)$", line)                 # 無序清單
        if m:
            open_list("ul"); out.append(f"<li>{_inline(m.group(1))}</li>"); continue
        m = re.match(r"^\s*(\d+)\.\s+(.*)$", line)              # 有序清單（新聞卡 1.~6. 條列）
        if m:
            open_list("ol"); out.append(f"<li>{_inline(m.group(2))}</li>"); continue
        close()
        if line.strip():
            out.append(f"<p>{_inline(line)}</p>")
    close()
    return "\n".join(out)


def _inline(s: str) -> str:
    s = _esc(s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^\s)]+)\)",
               r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)          # 非貪婪：允許粗體內含斜體 **a *b* c**
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", s)
    s = re.sub(r"【([^】]+)】", r'<span class="tag">【\1】</span>', s)   # 消息屬性徽章
    return s


def _pct_span(v: float | None, digits: int = 2) -> str:
    """紅漲綠跌的漲跌幅（台灣慣例）。None → 灰 —。"""
    if v is None:
        return '<span class="na">—</span>'
    cls = "gain" if v > 0 else ("loss" if v < 0 else "flat")
    sign = "+" if v > 0 else ""
    return f'<span class="{cls}">{sign}{v:.{digits}f}%</span>'


# ── ⓪ Sticky 頂欄 ────────────────────────────────────────────

def _topbar(banned_hits: list[str], has_news: bool, as_of: str, now: str) -> str:
    lamp = "⚪ 尚無新聞"
    if has_news:
        lamp = ("🟢 合規掃描通過" if not banned_hits
                else f'🔴 禁用詞：{"、".join(sorted(set(banned_hits)))}')
    return f"""
<div class="topbar">
  <div class="tb-in">
    <span class="tb-brand">復華基金雷達</span>
    <span class="tb-meta">持股基準 {_esc(as_of)}｜產表 {_esc(now)}</span>
    <span class="tb-lamp">{_esc(lamp)}</span>
    <nav class="tb-nav">
      <a href="#brief">今日重點</a><a href="#overview">基金總覽</a>
      <a href="#newslinks">新聞連動</a><a href="#twnews">台股新聞</a>
      <a href="#news">美股新聞</a><a href="#details">基金詳情</a>
    </nav>
    <button class="tb-print" onclick="window.print()">🖨 晨會版</button>
  </div>
</div>"""


# ── ① 今日重點 ───────────────────────────────────────────────

def _brief(indices: list[dict], best: dict | None, worst: dict | None,
           n_linked_cards: int, n_linked_funds: int, dists: list[dict],
           news_date: str | None) -> str:
    idx_cards = "".join(
        f'<div class="ixc"><div class="ixl">{_esc(ix["label"])}</div>'
        f'<div class="ixv">{_esc(ix["close"])}</div>'
        f'<div class="ixp">{_pct_span(ix["pct"] if ix["up"] else -ix["pct"])}</div></div>'
        for ix in indices)
    if not idx_cards:
        idx_cards = '<div class="muted">（尚無指數速覽——先產昨夜美股新聞）</div>'
    chips = []
    if best:
        chips.append(f'<a class="chip" href="#fund-{_esc(best["fund_id"])}">▲ 今日最強：'
                     f'<b>{_esc(_short(best["short_name"]))}</b> {_pct_span(best["chg"])}</a>')
    if worst:
        chips.append(f'<a class="chip" href="#fund-{_esc(worst["fund_id"])}">▼ 今日最弱：'
                     f'<b>{_esc(_short(worst["short_name"]))}</b> {_pct_span(worst["chg"])}</a>')
    if n_linked_cards:
        chips.append(f'<a class="chip hot" href="#newslinks">🔗 昨夜 {n_linked_cards} 則新聞'
                     f'連動 <b>{n_linked_funds}</b> 檔基金</a>')
    else:
        chips.append('<span class="chip dim">🔗 昨夜新聞與前十大持股無直接連動</span>')
    for x in dists:
        chips.append(f'<span class="chip">💰 {_esc(_short(x["short_name"]))} 配息基準日 '
                     f'{_esc(x["dist_date"])}</span>')
    nd = f'（{_esc(news_date)} 更新）' if news_date else ""
    return f"""
<div class="section" id="brief">
  <div class="st">⚡ 今日重點 <span class="stsub">{nd}</span></div>
  <div class="ixrow">{idx_cards}</div>
  <div class="chips">{"".join(chips)}</div>
</div>"""


# ── ② 基金總覽表 ─────────────────────────────────────────────

_OV_COLS = [("nav", "NAV", 0), ("chg", "日變動", 1), ("ytd", "YTD", 1),
            ("y1", "1年", 1), ("y3", "3年", 1), ("size_e8", "規模(億)", 0),
            ("conc", "前十大", 0), ("links", "連動", 0), ("risk", "RR", 0)]


def _overview(rows: list[dict], leaders: set, fund_links: dict[str, int],
              pending: list[dict]) -> str:
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["group_label"], []).append(r)
    for p in pending:                        # 待抓取的基金也整組列出（值全為 —）
        groups.setdefault(p["group_label"], []).append(
            {"fund_id": p["fund_id"], "short_name": p["name"], "pending": True,
             "group_label": p["group_label"], "risk": "—",
             **{k: None for k, _, _ in _OV_COLS if k not in ("links", "risk")}})
    blocks = []
    for g, rs in groups.items():
        trs = []
        for r in rs:
            fid = r["fund_id"]
            pend = ' <span class="pend">⏳ 待抓取</span>' if r.get("pending") else ""
            tds = [f'<td class="nm"><a href="#fund-{_esc(fid)}">{_esc(_short(r["short_name"]))}</a>{pend}</td>']
            for k, _, is_pct in _OV_COLS:
                if k == "links":
                    n = fund_links.get(fid, 0)
                    v, cell = n, (f'<a class="lk" href="#newslinks">🔗{n}</a>' if n else '<span class="na">—</span>')
                elif k == "risk":
                    v, cell = 0, _esc(r["risk"])
                else:
                    v = r.get(k)
                    if v is None:
                        cell = '<span class="na">—</span>'
                    elif is_pct:
                        cell = _pct_span(v, 2 if k == "chg" else 1)
                    else:
                        cell = f"{v:,.1f}" if k in ("size_e8", "conc") else _esc(v)
                        if k == "conc":
                            cell += "%"
                lead = ' class="lead"' if (fid, k) in leaders else ""
                tds.append(f'<td data-v="{v if v is not None else ""}"{lead}>{cell}</td>')
            trs.append(f'<tr data-fund="{_esc(fid)}">{"".join(tds)}</tr>')
        ths = "".join(f'<th class="sk" data-k="{k}">{lab}<span class="arr"></span></th>'
                      for k, lab, _ in _OV_COLS)
        blocks.append(
            f'<div class="ovg">{_esc(g)}（{len(rs)} 檔）</div>'
            f'<div class="ovwrap"><table class="ovtbl"><thead><tr><th class="l">基金</th>{ths}</tr></thead>'
            f'<tbody>{"".join(trs)}</tbody></table></div>')
    if not blocks:
        blocks.append('<div class="muted">尚無基金資料。請先執行 '
                      '<code>python3 scripts/fetch_holdings.py</code>。</div>')
    hint = ""
    if pending:
        hint = (f'<div class="pendhint">⏳ {len(pending)} 檔基金（台股清單）已列入追蹤、數據待抓取：'
                f'雲端環境連不到 fhtrust.com.tw，請在本機執行 '
                f'<code>python3 scripts/fetch_holdings.py</code> 後重產儀表板即會填滿。</div>')
    return f"""
<div class="section" id="overview">
  <div class="st">📊 基金總覽 <span class="stsub">點欄位標題可排序（⇅）｜點基金名稱跳詳情｜紅漲綠跌</span></div>
  {hint}
  {"".join(blocks)}
</div>"""


# ── ③ 新聞 × 持股連動 ────────────────────────────────────────

def _newslinks(linked: list[dict], as_of: str) -> str:
    if not linked:
        body = ('<div class="muted">昨夜新聞與追蹤基金前十大持股無直接連動——'
                '這本身也是可以講的資訊（本波題材非本公司基金主要持倉）。</div>')
        return f'<div class="section" id="newslinks"><div class="st">🔗 新聞 × 持股連動</div>{body}</div>'
    cards = []
    for c in linked:
        rows = []
        for m in c["matched"]:
            fs = "　".join(
                f'<a class="fw" href="#fund-{_esc(f["fund_id"])}">'
                f'{_esc(_short(f["short_name"]))} <b>{f["weight"]:.2f}%</b></a>'
                for f in m["funds"])
            tk = f' <span class="tk">{_esc(m["ticker"])}</span>' if m.get("ticker") else ""
            rows.append(f'<div class="nlrow"><span class="nlco">{_esc(m["display"])}{tk}</span>'
                        f'<span class="nlfs">{fs}</span></div>')
        script, hits = fund_insights.talk_script(c, as_of)
        if hits:
            talk = (f'<div class="talk bad">🔴 話術含禁用詞（{_esc("、".join(hits))}），'
                    f'已停用複製。</div>')
        else:
            talk = (f'<div class="talk"><span class="tlab">💬 可講素材（中性）</span>'
                    f'{_esc(script)} <button class="copy" data-copy="{_esc(script)}">📋 複製</button></div>')
        one = f'<div class="nlone">{_esc(c["oneline"])}</div>' if c.get("oneline") else ""
        mkt = f'<span class="mkt">{_esc(c["market"])}</span>' if c.get("market") else ""
        cards.append(f'<div class="nlcard"><div class="nlt">{mkt}{_esc(c["title"])}</div>{one}'
                     f'{"".join(rows)}{talk}</div>')
    return f"""
<div class="section" id="newslinks">
  <div class="st">🔗 新聞 × 持股連動 <span class="stsub">台股＋美股新聞 ↔ 前十大持股 ↔ 持有基金（權重）</span></div>
  {"".join(cards)}
</div>"""


# ── ④a 台股盤後重點（收合） ──────────────────────────────────

def _twnews_full(tw: dict | None) -> str:
    if not tw:
        body = ('<div class="muted">尚無台股盤後重點。請執行 '
                '<code>python scripts/gen_twnews.py</code> 產提示包，再由 Claude 產出內容。</div>')
        return f'<div class="section" id="twnews"><div class="st">🇹🇼 台股盤後重點</div>{body}</div>'
    heads = usnews.extract_cards(tw["md"])
    headlines = "".join(f'<div class="nh">・{_esc(h["title"])}</div>' for h in heads[:3])
    doc = _md(tw["md"]) or '<div class="muted">（無內容）</div>'
    return f"""
<div class="section" id="twnews">
  <details class="newswrap">
    <summary>
      <span class="st" style="margin:0">📈 台股盤後重點 <span class="stsub">📅 {_esc(tw["date"])}</span>
        <span class="openbtn"></span></span>
      {headlines}
    </summary>
    <div class="ndoc" style="margin-top:14px">{doc}</div>
  </details>
</div>"""


# ── ④b 昨夜美股新聞全文（收合） ───────────────────────────────

def _news_full(news: dict | None) -> str:
    if not news:
        body = ('<div class="muted">尚無昨夜美股新聞。請執行 '
                '<code>python scripts/gen_usnews.py</code> 產提示包，再由 Claude 產出兩版型。</div>')
        return f'<div class="section" id="news"><div class="st">🗞️ 昨夜美股新聞</div>{body}</div>'
    heads = usnews.extract_cards(news.get("v1") or news.get("v2") or "")
    headlines = "".join(f'<div class="nh">・{_esc(h["title"])}</div>' for h in heads[:3])
    v1 = _md(news.get("v1") or "") or '<div class="muted">（無版型一）</div>'
    v2 = _md(news.get("v2") or "") or '<div class="muted">（無版型二）</div>'
    return f"""
<div class="section" id="news">
  <details class="newswrap">
    <summary>
      <span class="st" style="margin:0">🗞️ 昨夜美股新聞 <span class="stsub">📅 {_esc(news["date"])}</span>
        <span class="openbtn"></span></span>
      {headlines}
    </summary>
    <div class="newsbar">
      <span class="nswitch"><button class="nb on" data-nv="v1">Top 3 速寫包</button>
        <button class="nb" data-nv="v2">精簡版</button></span>
    </div>
    <div class="ndoc" data-nv="v1">{v1}</div>
    <div class="ndoc hidden" data-nv="v2">{v2}</div>
  </details>
</div>"""


# ── ⑤ 基金詳情 ───────────────────────────────────────────────

def _bars(items: list[dict], accent: str) -> str:
    if not items:
        return '<div class="muted">—</div>'
    mx = max((i.get("weight") or 0) for i in items) or 1
    rows = []
    for it in items:
        w = it.get("weight") or 0
        rows.append(
            f'<div class="barrow"><span class="blab">{_esc(it.get("name"))}</span>'
            f'<span class="btrack"><span class="bfill" style="width:{w / mx * 100:.0f}%;background:{accent}"></span></span>'
            f'<span class="bval">{w:.1f}%</span></div>')
    return "".join(rows)


def _holdings_table(doc: dict, linked_names: set[str]) -> str:
    hs = doc.get("top_holdings") or []
    if not hs:
        if doc.get("group") == "tw_fof":
            return ('<div class="muted">本基金為組合型（fund-of-funds），主要持有基金／ETF，'
                    '官網不揭露「十大持有標的」表；成分揭露請見基金月報。</div>')
        return '<div class="muted">十大持有標的暫無資料。</div>'
    rows = []
    for i, h in enumerate(hs, 1):
        tk = f' <span class="tk">{_esc(h["ticker"])}</span>' if h.get("ticker") else ""
        ct = f'<span class="pill">{_esc(h["country"])}</span>' if h.get("country") else ""
        intro = f'<div class="hintro">{_esc(h["intro"])}</div>' if h.get("intro") else ""
        hl = h.get("name") in linked_names
        link = ' <a class="hlk" href="#newslinks" title="昨夜新聞連動">🔗</a>' if hl else ""
        trcls = ' class="hl"' if hl else ""
        rows.append(
            f'<tr{trcls}><td class="rk">{i}</td>'
            f'<td class="nm"><b>{_esc(h.get("name"))}</b>{tk}{link} '
            f'<span class="sec">{_esc(h.get("sector"))}</span> {ct}{intro}</td>'
            f'<td class="wt">{(h.get("weight") or 0):.2f}%</td></tr>')
    return (f'<table class="htbl"><thead><tr><th></th>'
            f'<th class="l">標的（重點標的簡介）</th><th>投資比例</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


def _fund_card(doc: dict, gavg: dict, linked_names: set[str]) -> str:
    ret = doc.get("returns") or {}
    ga = gavg.get(doc.get("group_label") or "", {})
    cells = []
    for k, lab in fund_insights.RET_KEYS + [("since", "成立以來")]:
        v = fund_insights.parse_pct(ret.get(k))
        avg = ga.get(k)
        beat = ' <span class="beat" title="高於同組平均">●</span>' \
            if (v is not None and avg is not None and v > avg) else ""
        sub = f'<div class="ga">同組均 {avg:.1f}%</div>' if avg is not None else ""
        cells.append(f'<div class="rc"><div class="rk2">{lab}</div>'
                     f'<div class="rv">{_esc(ret.get(k) or "—")}{beat}</div>{sub}</div>')
    size = doc.get("size_twd")
    size_s = f"{size / 1e8:.1f} 億元" if size else "—"
    mr = (f'<a class="mrpt" href="{_esc(doc["monthly_report"])}" target="_blank" rel="noopener">📄 基金月報</a>'
          if doc.get("monthly_report") else "")
    strat = doc.get("strategy") or ""
    chg = fund_insights.parse_pct(doc.get("nav_change_pct"))
    copy_txt = fund_insights.fund_intro_copy(doc)
    return f"""
<section class="fund" id="fund-{_esc(doc.get('fund_id'))}">
  <div class="fhead">
    <div>
      <h2>{_esc(doc.get('name'))} <span class="gl">{_esc(doc.get('group_label'))}</span></h2>
      <div class="sub">{_esc(doc.get('category'))}｜主要區域 {_esc(doc.get('region') or '—')}｜
        風險 {_esc(doc.get('risk_level') or '—')}｜經理費 {_esc(doc.get('mgmt_fee') or '—')}｜
        經理人 {_esc('、'.join(doc.get('managers') or []) or '—')}</div>
      <div class="oneline">{_esc(fund_intro.summary_line(doc))}</div>
    </div>
    <div class="navbox">
      <div class="nav">{_esc(doc.get('nav') if doc.get('nav') is not None else '—')}</div>
      <div class="navd">NAV · {_esc(doc.get('nav_date') or '—')} {_pct_span(chg)}</div>
      <div class="size">規模 {size_s}　{mr}</div>
      <button class="copy cfund" data-copy="{_esc(copy_txt)}">📋 複製基金介紹</button>
    </div>
  </div>
  {f'<div class="strat" title="點擊展開／收合">{_esc(strat)}</div>' if strat else ''}
  <div class="rets">{"".join(cells)}</div>
  <div class="cols">
    <div class="col">
      <div class="ctitle">🌏 國家配置</div>{_bars(doc.get('country_alloc') or [], 'var(--c1)')}
      <div class="ctitle" style="margin-top:14px">🏭 產業配置</div>{_bars(doc.get('sector_alloc') or [], 'var(--c2)')}
    </div>
    <div class="col">
      <div class="ctitle">📋 十大持有標的　<span class="asof">持股基準 {_esc(doc.get('as_of') or '—')}｜前十大合計 {_esc(fund_intro.top_concentration(doc) if fund_intro.top_concentration(doc) is not None else '—')}%</span></div>
      {_holdings_table(doc, linked_names)}
    </div>
  </div>
</section>"""


def _pending_card(p: dict) -> str:
    note = ("本基金為組合型（fund-of-funds），官網「十大持有標的」揭露結構不同；"
            if p["fund_id"] == "79" else "")
    return f"""
<section class="fund pendcard" id="fund-{_esc(p['fund_id'])}">
  <div class="fhead"><div>
    <h2>{_esc(p['name'])} <span class="gl">{_esc(p['group_label'])}</span></h2>
    <div class="sub">⏳ 已列入追蹤，數據待抓取——{note}雲端環境連不到 fhtrust.com.tw，
      請在本機執行 <code>python3 scripts/fetch_holdings.py {_esc(p['fund_id'])}</code> 後重產儀表板。</div>
  </div></div>
</section>"""


def _details(funds: list[dict], gavg: dict, linked_by_fund: dict[str, set[str]],
             pending: list[dict]) -> str:
    jumps = "".join(f'<a class="jmp" href="#fund-{_esc(d.get("fund_id"))}">{_esc(_short(d))}</a>'
                    for d in funds)
    jumps += "".join(f'<a class="jmp pendjmp" href="#fund-{_esc(p["fund_id"])}">⏳{_esc(_short(p["name"]))}</a>'
                     for p in pending)
    cards = "".join(_fund_card(d, gavg, linked_by_fund.get(str(d.get("fund_id")), set()))
                    for d in funds)
    cards += "".join(_pending_card(p) for p in pending)
    return f"""
<div class="section" id="details">
  <div class="st">📚 基金詳情 <span class="stsub">共 {len(funds) + len(pending)} 檔（{len(funds)} 檔有數據、{len(pending)} 檔待抓取）</span></div>
  <div class="jumps">{jumps}</div>
</div>
{cards}"""


# ── 樣式與腳本（非 f-string，避免大括號跳脫） ─────────────────

_CSS = """
:root{--bg:#0e1116;--card:#161b22;--card2:#1c232d;--ink:#e6edf3;--mut:#9aa7b4;
--line:#2a323c;--c1:#3b82f6;--c2:#f59e0b;--gain:#f0524f;--loss:#2ea94f;--acc:#5b8def}
*{box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:64px}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 -apple-system,"PingFang TC","Noto Sans TC",Segoe UI,sans-serif}
a{color:var(--acc)} code{background:#0b0e13;padding:1px 6px;border-radius:5px;color:#9ecbff}
.wrap{max-width:1240px;margin:0 auto;padding:14px 18px 60px}
.section{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin:16px 0}
.section>.st,.newswrap .st{font-weight:700;font-size:16px;margin-bottom:10px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.stsub{font-weight:400;font-size:12px;color:var(--mut)}
.muted{color:var(--mut)} .na{color:#5c6773}
.gain{color:var(--gain);font-weight:700}.loss{color:var(--loss);font-weight:700}.flat{color:var(--mut)}
/* ⓪ topbar */
.topbar{position:sticky;top:0;z-index:50;background:rgba(14,17,22,.92);backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}
.tb-in{max-width:1240px;margin:0 auto;padding:9px 18px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.tb-brand{font-weight:800;font-size:15px}
.tb-meta{color:var(--mut);font-size:11.5px}
.tb-lamp{font-size:11.5px;color:var(--mut)}
.tb-nav{margin-left:auto;display:flex;gap:5px;flex-wrap:wrap}
.tb-nav a{color:#cfe0ff;text-decoration:none;font-size:14px;padding:5px 12px;border-radius:8px;background:var(--card2);border:1px solid var(--line)}
.tb-nav a:hover{color:#fff;border-color:var(--acc);background:rgba(91,141,239,.18)}
.tb-print{background:var(--card2);color:#cfe0ff;border:1px solid var(--line);border-radius:8px;padding:5px 12px;cursor:pointer;font-size:13.5px}
.tb-print:hover{border-color:var(--acc);color:#fff}
/* ① brief */
.ixrow{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px}
.ixc{flex:1;min-width:150px;background:var(--card2);border:1px solid var(--line);border-radius:11px;padding:10px 14px}
.ixl{font-size:12px;color:var(--mut)} .ixv{font-size:21px;font-weight:800;letter-spacing:.01em}
.ixp{font-size:13px}
.chips{display:flex;gap:8px;flex-wrap:wrap}
.chip{display:inline-flex;align-items:center;gap:6px;background:var(--card2);border:1px solid var(--line);border-radius:20px;padding:8px 15px;font-size:14px;color:var(--ink);text-decoration:none}
.chip b{font-weight:700} .chip.hot{border-color:var(--acc);background:rgba(91,141,239,.12)}
.chip.dim{color:var(--mut)}
a.chip{border-color:rgba(91,141,239,.55);cursor:pointer}
a.chip::after{content:"›";color:var(--acc);font-weight:800;font-size:16px}
a.chip:hover{border-color:var(--acc);background:rgba(91,141,239,.16)}
/* ② overview */
.ovg{font-weight:700;font-size:13.5px;color:#cfe0ff;margin:14px 0 6px}
.ovwrap{overflow-x:auto}
.ovtbl{width:100%;border-collapse:collapse;font-size:14px}
.ovtbl th{color:#b7c3d0;font-size:12.5px;font-weight:700;padding:7px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
.ovtbl th.l{text-align:left}
.ovtbl th.sk{cursor:pointer;user-select:none} .ovtbl th.sk:hover{color:var(--acc)}
.ovtbl th .arr{display:inline-block;width:13px;color:var(--acc)}
.ovtbl th .arr::after{content:"⇅";opacity:.55}
.ovtbl th.sd .arr::after{content:"▼";opacity:1} .ovtbl th.sa .arr::after{content:"▲";opacity:1}
.ovtbl td{padding:8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
.ovtbl td.nm{text-align:left;font-weight:600}
.ovtbl td.nm a{color:#9ecbff;font-size:14.5px;text-decoration:underline;text-underline-offset:3px;text-decoration-color:rgba(158,203,255,.5)}
.ovtbl td.nm a:hover{color:#fff;text-decoration-color:var(--acc)}
.ovtbl td.lead{background:rgba(240,82,79,.13);border-radius:4px}
.ovtbl tr:hover td{background:rgba(91,141,239,.06)}
.lk{text-decoration:none;font-size:12.5px}
/* ③ news links */
.nlcard{background:var(--card2);border:1px solid var(--line);border-left:3px solid var(--acc);border-radius:0 11px 11px 0;padding:12px 16px;margin:10px 0}
.nlt{font-weight:700;font-size:15.5px;color:#fff}
.nlone{display:table;font-size:14px;margin:6px 0 10px;color:#4a2f14;background:#eeddb7;font-weight:700;padding:1px 8px;border-radius:4px}
.nlrow{display:flex;gap:12px;align-items:baseline;flex-wrap:wrap;margin:6px 0;font-size:13.5px}
.nlco{font-weight:700;min-width:110px} .nlfs{color:var(--mut)}
.fw{color:#9ecbff;font-size:14px;text-decoration:underline;text-underline-offset:3px;text-decoration-color:rgba(158,203,255,.5);margin-right:8px;white-space:nowrap}
.fw b{color:#fff} .fw:hover{color:#fff;text-decoration-color:var(--acc)}
.mkt{display:inline-block;font-size:12px;font-weight:700;color:#0e1116;background:#f0b350;border-radius:6px;padding:1px 8px;margin-right:8px;vertical-align:2px}
.talk{margin-top:10px;background:#0b0e13;border:1px solid var(--line);border-radius:9px;padding:9px 12px;font-size:13px;color:#dbe4ee;line-height:1.7}
.talk.bad{color:var(--mut)}
.tlab{display:block;font-size:11.5px;color:var(--mut);margin-bottom:3px}
.copy{background:rgba(91,141,239,.12);color:#9ecbff;border:1px solid rgba(91,141,239,.55);border-radius:8px;padding:5px 13px;cursor:pointer;font-size:13.5px;font-weight:700;margin-left:6px}
.copy:hover{border-color:var(--acc);color:#fff}
.copy.ok{color:#fff;border-color:var(--acc);background:rgba(91,141,239,.3)}
/* ④ news full */
.newswrap summary{cursor:pointer;list-style:none}
.newswrap summary::-webkit-details-marker{display:none}
.newswrap summary:hover .openbtn{border-color:var(--acc);color:#fff}
.openbtn{margin-left:auto;background:rgba(91,141,239,.12);color:#9ecbff;border:1px solid rgba(91,141,239,.55);border-radius:8px;padding:5px 13px;font-size:13.5px;font-weight:700;white-space:nowrap}
.openbtn::after{content:"▼ 點擊展開全文"}
.newswrap[open] .openbtn::after{content:"▲ 收合"}
.nh{color:var(--mut);font-size:13.5px;margin:3px 0 0 4px}
.newswrap[open] .nh{display:none}
.newsbar{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin:14px 0 12px}
.nswitch{display:flex;gap:6px}
.nb{background:var(--card2);color:#cfe0ff;border:1px solid var(--line);border-radius:20px;padding:7px 16px;cursor:pointer;font-size:14.5px;font-weight:700}
.nb:hover{border-color:var(--acc)}
.nb.on{background:var(--acc);color:#fff;border-color:var(--acc)}
.ndoc{background:var(--card2);border:1px solid var(--line);border-radius:12px;padding:8px 30px 24px;line-height:1.85;font-size:15px;color:#dbe4ee}
.ndoc.hidden{display:none}
.ndoc>*:first-child{margin-top:14px}
.ndoc h2{font-size:14.5px;color:var(--mut);font-weight:600;letter-spacing:.02em;margin:30px 0 12px;padding-bottom:8px;border-bottom:1px solid var(--line)}
.ndoc h3{font-size:16.5px;color:#fff;font-weight:700;line-height:1.55;margin:26px 0 10px;padding:12px 16px;background:linear-gradient(90deg,rgba(91,141,239,.16),rgba(91,141,239,.03));border-left:3px solid var(--acc);border-radius:0 10px 10px 0}
.ndoc h4{font-size:14.5px;color:#cfe0ff;margin:18px 0 6px}
.ndoc p{margin:9px 0}
.ndoc ul,.ndoc ol{margin:10px 0;padding-left:0;list-style:none;counter-reset:n}
.ndoc ul li{position:relative;margin:8px 0;padding-left:20px}
.ndoc ul li:before{content:"";position:absolute;left:4px;top:12px;width:5px;height:5px;border-radius:50%;background:var(--acc)}
.ndoc ol li{position:relative;margin:11px 0;padding-left:36px;counter-increment:n}
.ndoc ol li:before{content:counter(n);position:absolute;left:0;top:2px;width:23px;height:23px;border-radius:50%;background:var(--acc);color:#fff;font-size:12px;font-weight:700;text-align:center;line-height:23px}
.ndoc b{color:#4a2f14;background:#eeddb7;font-weight:700;padding:0 4px;border-radius:4px;box-decoration-break:clone;-webkit-box-decoration-break:clone}
.ndoc h2 b,.ndoc h3 b,.ndoc h4 b{color:inherit;background:none;padding:0}
.ndoc a{text-decoration:none;border-bottom:1px dashed var(--acc);word-break:break-all}
.ndoc hr{border:0;border-top:1px solid var(--line);margin:22px 0}
.ndoc small,.ndoc i{color:var(--mut);font-style:normal}
.tag{display:inline-block;font-size:12px;font-weight:700;padding:1px 9px;border-radius:20px;background:rgba(91,141,239,.18);color:#9ecbff;border:1px solid rgba(91,141,239,.35);white-space:nowrap}
/* ⑤ details */
.jumps{display:flex;flex-wrap:wrap;gap:7px}
.jmp{background:var(--card2);color:#cfe0ff;border:1px solid var(--line);border-radius:9px;padding:7px 13px;font-size:14px;text-decoration:none}
.jmp:hover{color:#fff;border-color:var(--acc);background:rgba(91,141,239,.14)}
.pendjmp{color:var(--mut)}
.pend{display:inline-block;font-size:11.5px;color:#f0b350;border:1px solid rgba(240,179,80,.5);border-radius:10px;padding:0 7px;margin-left:6px;vertical-align:1px}
.pendhint{background:rgba(240,179,80,.09);border:1px solid rgba(240,179,80,.35);border-radius:10px;padding:9px 13px;font-size:13.5px;color:#e8c990;margin-bottom:10px}
.pendcard .sub{line-height:1.9}
.fund{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;margin-top:12px}
.fund:target{border-color:var(--acc);box-shadow:0 0 0 2px rgba(91,141,239,.35)}
.fhead{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;align-items:flex-start}
.fhead h2{font-size:19px;margin:0 0 4px} .gl{font-size:12px;color:#fff;background:var(--acc);padding:2px 8px;border-radius:20px;vertical-align:middle}
.sub{color:var(--mut);font-size:12.5px} .oneline{margin-top:6px;font-size:13.5px;color:#cfe0ff}
.navbox{text-align:right;min-width:190px} .nav{font-size:26px;font-weight:800}
.navd{font-size:12px;color:var(--mut)} .size{font-size:12px;color:var(--mut);margin-top:4px}
.cfund{margin:8px 0 0;display:inline-block}
.mrpt{display:inline-block;margin-left:6px}
.strat{margin:12px 0 4px;color:var(--mut);font-size:13px;border-left:3px solid var(--line);padding-left:10px;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;cursor:pointer}
.strat.open{display:block;-webkit-line-clamp:unset}
.rets{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin:14px 0}
.rc{background:var(--card2);border:1px solid var(--line);border-radius:9px;padding:8px;text-align:center}
.rk2{font-size:11px;color:var(--mut)} .rv{font-weight:700;font-size:14px}
.beat{color:var(--gain);font-size:9px;vertical-align:2px}
.ga{font-size:10.5px;color:#5c6773;margin-top:2px}
.cols{display:grid;grid-template-columns:1fr 1.25fr;gap:18px;margin-top:8px}
.ctitle{font-weight:700;font-size:14px;margin-bottom:8px} .asof{font-weight:400;font-size:11.5px;color:var(--mut)}
.barrow{display:flex;align-items:center;gap:8px;margin:5px 0;font-size:12.5px}
.blab{width:78px;flex:0 0 78px;color:var(--mut)} .btrack{flex:1;height:9px;background:#0b0e13;border-radius:6px;overflow:hidden}
.bfill{display:block;height:100%} .bval{width:48px;text-align:right}
.htbl{width:100%;border-collapse:collapse} .htbl th{text-align:right;color:var(--mut);font-size:11.5px;font-weight:600;padding:4px 6px;border-bottom:1px solid var(--line)}
.htbl th.l{text-align:left} .htbl td{padding:7px 6px;border-bottom:1px solid var(--line);vertical-align:top}
.htbl .rk{color:var(--mut);width:22px} .htbl .wt{text-align:right;font-weight:700;white-space:nowrap}
.htbl .sec{font-size:11px;color:var(--mut);border:1px solid var(--line);border-radius:5px;padding:0 5px;margin-left:4px}
.htbl tr.hl td{background:rgba(245,158,11,.08)}
.hlk{text-decoration:none}
.tk{font-size:11px;color:#9ecbff} .pill{font-size:11px;color:var(--mut);border:1px solid var(--line);border-radius:5px;padding:0 5px;margin-left:4px}
.hintro{color:var(--mut);font-size:12px;margin-top:3px}
.foot{color:var(--mut);font-size:11.5px;margin-top:22px;border-top:1px solid var(--line);padding-top:12px}
.backtop{position:fixed;right:18px;bottom:18px;z-index:40;background:var(--card2);color:var(--mut);border:1px solid var(--line);border-radius:22px;padding:8px 14px;font-size:12.5px;text-decoration:none}
.backtop:hover{color:#fff;border-color:var(--acc)}
@media(max-width:720px){.cols{grid-template-columns:1fr}.rets{grid-template-columns:repeat(3,1fr)}.navbox{text-align:left}
  .tb-meta,.tb-lamp{display:none}.ixc{min-width:110px}}
/* 晨會列印版：只留今日重點＋總覽＋新聞連動，白底黑字一頁 A4 */
@media print{
  body{background:#fff;color:#111;font-size:12px}
  .topbar,.backtop,#news,#twnews,#details,.fund,.tb-print,.pendhint{display:none!important}
  .ndoc b,.nlone{color:#4a2f14;background:#f3e8cd}
  .section{background:#fff;border-color:#bbb;break-inside:avoid;margin:8px 0;padding:10px 12px}
  .ixc,.chip,.nlcard,.talk{background:#fff;border-color:#bbb;color:#111}
  .ixv,.nlt,.ovtbl td.nm a,.chip,.fw,.fw b,.talk{color:#111}
  .ovtbl td,.ovtbl th{border-color:#ccc;color:#111}
  .stsub,.muted,.nlfs,.nlone,.tlab{color:#555}
  .ovg,.st,.nlco{color:#111}
  .gain{color:#c62828}.loss{color:#2e7d32}
  .copy{display:none}
  a{text-decoration:none;color:#111}
}
"""

_JS = """
// v1/v2 版型切換
document.querySelectorAll('.nb').forEach(b=>b.onclick=()=>{
  document.querySelectorAll('.nb').forEach(x=>x.classList.remove('on'));b.classList.add('on');
  const v=b.dataset.nv;
  document.querySelectorAll('.ndoc').forEach(d=>d.classList.toggle('hidden',d.dataset.nv!==v));
});
// 總覽表排序（首次點＝大→小；缺值恆沉底）
document.querySelectorAll('.ovtbl th.sk').forEach(th=>th.onclick=()=>{
  const tb=th.closest('table').querySelector('tbody'), i=th.cellIndex;
  const desc=th.dataset.d!=='desc';
  th.closest('tr').querySelectorAll('th').forEach(x=>{delete x.dataset.d;x.classList.remove('sa','sd')});
  th.dataset.d=desc?'desc':'asc';th.classList.add(desc?'sd':'sa');
  Array.from(tb.rows).sort((a,b)=>{
    const av=parseFloat(a.cells[i].dataset.v),bv=parseFloat(b.cells[i].dataset.v);
    const an=isNaN(av),bn=isNaN(bv);
    if(an&&bn)return 0; if(an)return 1; if(bn)return -1;
    return desc?bv-av:av-bv;
  }).forEach(r=>tb.appendChild(r));
});
// 複製（clipboard API＋textarea 後備，file:// 也可用）
function _fb(t,done){const ta=document.createElement('textarea');ta.value=t;ta.style.position='fixed';
  document.body.appendChild(ta);ta.select();try{document.execCommand('copy');done()}catch(e){}ta.remove()}
document.querySelectorAll('.copy').forEach(b=>b.onclick=()=>{
  const t=b.getAttribute('data-copy');
  const done=()=>{const o=b.textContent;b.classList.add('ok');b.textContent='已複製 ✓';
    setTimeout(()=>{b.textContent=o;b.classList.remove('ok')},1400)};
  if(navigator.clipboard&&navigator.clipboard.writeText)
    navigator.clipboard.writeText(t).then(done,()=>_fb(t,done));
  else _fb(t,done);
});
// 投資策略兩行截斷 ↔ 展開
document.querySelectorAll('.strat').forEach(s=>s.onclick=()=>s.classList.toggle('open'));
"""


# ── 組裝 ─────────────────────────────────────────────────────

def render() -> str:
    funds = fund_intro.all_funds()
    pending = fund_intro.pending_funds()
    news = usnews.load_latest()
    tw = twnews.load_latest()
    news_md = (news or {}).get("v1") or (news or {}).get("v2") or ""
    tw_md = (tw or {}).get("md") or ""

    links = []
    for c in fund_insights.news_fund_links(funds, tw_md):
        links.append({**c, "market": "台股"})
    for c in fund_insights.news_fund_links(funds, news_md):
        links.append({**c, "market": "美股"})
    linked = [c for c in links if c["matched"]]
    fund_links: dict[str, int] = {}          # fund_id → 連動的新聞卡數（同卡去重）
    linked_by_fund: dict[str, set[str]] = {}  # fund_id → 連動持股名
    for c in linked:
        fids = set()
        for m in c["matched"]:
            for f in m["funds"]:
                fids.add(f["fund_id"])
                linked_by_fund.setdefault(f["fund_id"], set()).add(m["name"])
        for fid in fids:
            fund_links[fid] = fund_links.get(fid, 0) + 1

    rows = fund_insights.overview_rows(funds)
    leaders = fund_insights.column_leaders(rows)
    gavg = fund_insights.group_averages(funds)
    best, worst = fund_insights.movers(funds)
    indices = twnews.extract_indices(tw_md) + usnews.extract_indices(news_md)
    dists = fund_insights.upcoming_distributions(funds)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    as_of = (funds[0].get("as_of") if funds else None) or "—"
    banned = ((news or {}).get("banned_hits") or []) + ((tw or {}).get("banned_hits") or [])

    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>復華基金雷達 · 今日重點／總覽／新聞連動／持股介紹</title>
<style>{_CSS}</style></head>
<body>
{_topbar(banned, bool(news or tw), as_of, now)}
<div class="wrap">
{_brief(indices, best, worst, len(linked), len(fund_links), dists, (tw or news or {}).get("date"))}
{_overview(rows, leaders, fund_links, pending)}
{_newslinks(linked, as_of)}
{_twnews_full(tw)}
{_news_full(news)}
{_details(funds, gavg, linked_by_fund, pending)}
<div class="foot">
  資料來源：復華投信官網（fhtrust.com.tw）基金淨值／持股揭露（月度）；重點標的簡介為中性事實敘述、非投資建議。
  昨夜美股新聞為公開來源彙編、教育用途，非投資建議或招攬；過去績效不代表未來表現，淨值可能因市場變動而上下；
  境外基金涉及匯率與國際市場風險。投資人申購本基金係持有基金受益憑證，非本文提及之投資資產或標的。
  申購前應詳閱公開說明書／投資人須知。本版本不呈現「每天持股變化」（共同基金無逐日持股張數）。
</div>
</div>
<a class="backtop" href="#overview">↑ 總覽</a>
<script>{_JS}</script>
</body></html>"""
