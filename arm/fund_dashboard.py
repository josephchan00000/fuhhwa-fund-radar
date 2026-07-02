"""復華基金追蹤版本 · 零安裝儀表板 —— 讀 data/funds/*.json + config/holding_profiles.json
+ reports/usnews/{最新}_v1/_v2.md → 產單一 dashboard/index.html。

主秀兩件事（正是本追蹤版本的重點）：
  ① 每檔基金「持股介紹」：基本資料 / NAV / 多期報酬 / 國家・產業配置 / 十大持有標的＋重點標的簡介。
  ② 「昨夜美股重大新聞」：最新一份兩版型（Top3 速寫包＋精簡版），附合規燈。

純 vanilla HTML＋少量 JS（只做分頁切換），零外部請求、雙擊即開，無 npm/node。
不做「每天持股變化」（共同基金無逐日持股張數）。
"""
from __future__ import annotations

import html
import re
from datetime import datetime

from . import config, fund_intro, fund_mentions, indicators, markets, twnews, usnews

_NEWS_MODULES = {"us": usnews, "tw": twnews}


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


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


def _fof_note(doc: dict) -> str:
    """組合型（fof）持股抓不到時的說明（D4）：導向月報，並說明揭露結構不同。"""
    mr = (f'　<a href="{_esc(doc["monthly_report"])}" target="_blank" rel="noopener">📄 基金月報</a>'
          if doc.get("monthly_report") else "")
    return ('<div class="muted">本基金為<b>組合型（fund-of-funds）</b>，主要投資於其他基金／ETF，'
            f'官網詳情頁未提供標準「十大持有標的」表；完整持有標的請參基金月報。{mr}</div>')


def _holdings_table(doc: dict) -> str:
    hs = doc.get("top_holdings") or []
    if not hs:
        if doc.get("group") == "fof" or doc.get("holdings_kind") == "fund":
            return _fof_note(doc)
        return '<div class="muted">十大持有標的暫無資料。</div>'
    is_fund = doc.get("holdings_kind") == "fund"
    rows = []
    for i, h in enumerate(hs, 1):
        tk = f' <span class="tk">{_esc(h["ticker"])}</span>' if h.get("ticker") else ""
        ct = f'<span class="pill">{_esc(h["country"])}</span>' if h.get("country") else ""
        sec = f' <span class="sec">{_esc(h.get("sector"))}</span>' if h.get("sector") else ""
        intro = f'<div class="hintro">{_esc(h["intro"])}</div>' if h.get("intro") else ""
        more = (f'<details class="hmore"><summary>更多介紹</summary>{_esc(h["detail"])}</details>'
                if h.get("detail") else "")
        rows.append(
            f'<tr><td class="rk">{i}</td>'
            f'<td class="nm"><b>{_esc(h.get("name"))}</b>{tk}{sec} {ct}{intro}{more}</td>'
            f'<td class="wt">{(h.get("weight") or 0):.2f}%</td></tr>')
    label = "投資標的（基金／ETF）" if is_fund else "標的（重點標的簡介）"
    return (f'<table class="htbl"><thead><tr><th></th>'
            f'<th class="l">{label}</th><th>投資比例</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


def _fund_card(doc: dict, idx: int) -> str:
    ret = doc.get("returns") or {}
    ret_cells = "".join(
        f'<div class="rc"><div class="rk2">{lab}</div><div class="rv">{_esc(ret.get(k) or "—")}</div></div>'
        for k, lab in [("ytd", "今年以來"), ("3m", "3月"), ("6m", "6月"),
                       ("1y", "1年"), ("3y", "3年"), ("since", "成立以來")])
    size = doc.get("size_twd")
    size_s = f"{size / 1e8:.1f} 億元" if size else "—"
    mr = (f'<a class="mrpt" href="{_esc(doc["monthly_report"])}" target="_blank" rel="noopener">📄 基金月報</a>'
          if doc.get("monthly_report") else "")
    strat = doc.get("strategy") or ""
    strat_s = (strat[:140] + "…") if len(strat) > 140 else strat
    return f"""
<section class="fund" data-fund="{_esc(doc.get('fund_id'))}">
  <div class="fhead">
    <div>
      <h2>{_esc(doc.get('name'))} <span class="gl">{_esc(doc.get('group_label'))}</span></h2>
      <div class="sub">{_esc(doc.get('category'))}｜主要區域 {_esc(doc.get('region') or '—')}｜
        風險 {_esc(doc.get('risk_level') or '—')}｜經理人 {_esc('、'.join(doc.get('managers') or []) or '—')}</div>
      <div class="oneline">{_esc(fund_intro.summary_line(doc))}</div>
    </div>
    <div class="navbox">
      <div class="nav">{_esc(doc.get('nav') if doc.get('nav') is not None else '—')}</div>
      <div class="navd">NAV · {_esc(doc.get('nav_date') or '—')} <span class="{ 'up' if (doc.get('nav_change') or 0) >= 0 else 'dn'}">{_esc(doc.get('nav_change_pct') or '')}</span></div>
      <div class="size">規模 {size_s}　{mr}</div>
    </div>
  </div>
  {f'<div class="strat">{_esc(strat_s)}</div>' if strat_s else ''}
  <div class="rets">{ret_cells}</div>
  <div class="cols">
    <div class="col">
      <div class="ctitle">🌏 國家配置</div>{_bars(doc.get('country_alloc') or [], 'var(--c1)')}
      <div class="ctitle" style="margin-top:14px">🏭 產業配置</div>{_bars(doc.get('sector_alloc') or [], 'var(--c2)')}
    </div>
    <div class="col">
      <div class="ctitle">📋 {'十大投資標的' if doc.get('holdings_kind') == 'fund' else '十大持有標的'}　<span class="asof">持股基準 {_esc(doc.get('as_of') or '—')}｜前十大合計 {_esc(fund_intro.top_concentration(doc) if fund_intro.top_concentration(doc) is not None else '—')}%</span></div>
      {_holdings_table(doc)}
    </div>
  </div>
</section>"""


# ── 新聞結構感知渲染（重點置頂卡片）────────────────────────────
# 新聞卡樣式：「### 卡 1｜標題（來源｜日期｜【屬性】）」＋ 底下 1.~6. 之「**標籤**：內文」。
# 解析成功→卡片版型（一句話重點置頂、細節成標籤列、參考資料摺疊）；失敗→回退 _md 整段渲染。
_ITEM_RE = re.compile(r"^\s*\d+\.\s*\*\*(.+?)\*\*\s*[：:]\s*(.*)$")
_FINEPRINT_HEADS = ("資料侷限", "合規揭露", "盤後對照")


def _card_html(head: str, body_lines: list[str]) -> str | None:
    """把一張新聞卡渲染成重點置頂版型；結構不符回 None（回退 _md）。"""
    items: list[tuple[str, str]] = []
    for ln in body_lines:
        m = _ITEM_RE.match(ln)
        if m:
            items.append((m.group(1).strip(), m.group(2).strip()))
        elif items and ln.strip():
            items[-1] = (items[-1][0], items[-1][1] + " " + ln.strip())
    if len(items) < 2:
        return None

    title = re.sub(r"^(卡\s*\d+|\d+)\s*[｜|]\s*", "", head).strip()
    badges = ""
    m = re.search(r"（([^（）]*)）\s*$", title)
    if m:                                        # 標題尾端（來源｜日期｜【屬性】）→ 徽章列
        title = title[:m.start()].strip()
        parts = [p.strip() for p in m.group(1).split("｜") if p.strip()]
        badges = "".join(f'<span class="tag">{_esc(p.strip("【】"))}</span>' for p in parts)

    lead, refs, rows = "", "", []
    for lab, val in items:
        if "一句話" in lab:
            lead = val
        elif "參考資料" in lab:
            refs = val
        else:
            lab_s = (lab.replace("新聞摘要", "摘要").replace("昨夜美股摘要", "摘要")
                        .replace("對競爭者／合作方影響", "競合影響")
                        .replace("對供應鏈／競爭者影響", "供應鏈")
                        .replace("對市場情緒與股價影響", "市場情緒")
                        .replace("對盤面情緒與股價影響", "盤面情緒")
                        .replace("對應台股受惠／受壓族群", "台股族群")
                        .replace("台廠 ADR 與盤前氛圍", "ADR 氛圍")
                        .replace("今日台股盤前觀察（中性描述，非買賣建議）", "盤前觀察")
                        .replace("今日台股盤前觀察（中性描述）", "盤前觀察")
                        .replace("對公司影響", "公司影響"))
            rows.append(f'<div class="nrow"><span class="nlab">{_esc(lab_s)}</span>'
                        f'<span class="nval">{_inline(val)}</span></div>')
    lead_html = f'<div class="nlead">{_inline(lead)}</div>' if lead else ""
    refs_html = (f'<details class="nrefs"><summary>參考資料</summary>'
                 f'<div>{_inline(refs)}</div></details>' if refs else "")
    return (f'<div class="ncard"><div class="nhead"><span class="ntitle">{_inline(title)}</span>'
            f'<span class="badges">{badges}</span></div>{lead_html}{"".join(rows)}{refs_html}</div>')


def _render_news_doc(text: str) -> str:
    """整份新聞 md → 卡片化 HTML：### 卡→重點置頂卡片、資料侷限/合規/盤後對照→摺疊、
    其餘段落照 _md；並在最上方彙整各卡「一句話重點」為速覽框。無卡可解析→整段 _md。"""
    if not text:
        return ""
    lines = text.splitlines()
    out: list[str] = []
    md_buf: list[str] = []
    leads: list[str] = []
    n_cards = 0

    def flush_md():
        if md_buf:
            out.append(_md("\n".join(md_buf)))
            md_buf.clear()

    i = 0
    while i < len(lines):
        ln = lines[i]
        m3 = re.match(r"^###\s+(.*)$", ln)
        m2 = re.match(r"^##\s+(.*)$", ln)
        if m3:                                   # 新聞卡：吃到下一個標題/水平線為止
            body: list[str] = []
            i += 1
            while i < len(lines) and not re.match(r"^(##|###)\s|^\s*---\s*$", lines[i]):
                body.append(lines[i]); i += 1
            card = _card_html(m3.group(1), body)
            if card:
                flush_md(); out.append(card); n_cards += 1
                lm = next((v for l, v in
                           (_ITEM_RE.match(b).groups() for b in body if _ITEM_RE.match(b))
                           if "一句話" in l), None)
                if lm:                                   # 速覽項附各卡日期（資料時間可追溯）
                    dm = re.search(r"\d{4}/\d{2}/\d{2}", m3.group(1))
                    leads.append(f"{lm.strip()}〔{dm.group()}〕" if dm else lm.strip())
            else:                                # 結構不符 → 整卡回退 md
                md_buf.extend([ln, *body])
            continue
        if m2 and any(k in m2.group(1) for k in _FINEPRINT_HEADS):   # 雜訊段 → 摺疊
            body = []
            i += 1
            while i < len(lines) and not re.match(r"^##\s", lines[i]):
                if not re.match(r"^\s*---\s*$", lines[i]):
                    body.append(lines[i])
                i += 1
            flush_md()
            out.append(f'<details class="fineprint"><summary>{_inline(m2.group(1))}</summary>'
                       f'<div>{_md(chr(10).join(body))}</div></details>')
            continue
        md_buf.append(ln); i += 1
    flush_md()
    if not n_cards:                              # 無卡可解析 → 整段回退現行 markdown 渲染
        return _md(text)
    quick = ""
    if len(leads) >= 2:                          # ⚡ 本日重點速覽（各卡一句話重點彙整）
        quick = ('<div class="quick"><div class="qt">⚡ 本日重點</div><ol>'
                 + "".join(f"<li>{_inline(s)}</li>" for s in leads) + "</ol></div>")
    return quick + "".join(out)


def _news_section(news: str = "us", market: str = "global") -> str:
    """依市場新聞來源分派（"us"→usnews、"tw"→twnews），兩模組介面對稱。
    版型切換為純 CSS（radio+label），不依賴 JS——沙箱預覽/禁 script 環境也能按。"""
    mod = _NEWS_MODULES.get(news, usnews)
    n = mod.load_latest()
    if not n:
        return f'<div class="muted">{mod.EMPTY_HINT}</div>'
    lamp = ("🟢 合規掃描通過" if not n["banned_hits"]
            else f'🔴 出現禁用詞：{"、".join(n["banned_hits"])}')
    v1 = _render_news_doc(n.get("v1") or "") or '<div class="muted">（無版型一）</div>'
    v2 = _render_news_doc(n.get("v2") or "") or '<div class="muted">（無版型二）</div>'
    mid = _esc(market)
    return f"""
  <input class="vh" type="radio" name="nv-{mid}" id="nv-{mid}-v1" checked>
  <input class="vh" type="radio" name="nv-{mid}" id="nv-{mid}-v2">
  <div class="newsbar">
    <span class="ndate">📅 {_esc(n['date'])}</span>
    <span class="lamp">{_esc(lamp)}</span>
    <span class="nswitch"><label class="nb" for="nv-{mid}-v1">{_esc(mod.V1_LABEL)}</label>
      <label class="nb" for="nv-{mid}-v2">{_esc(mod.V2_LABEL)}</label></span>
  </div>
  <div class="ndoc" data-nv="v1">{v1}</div>
  <div class="ndoc" data-nv="v2">{v2}</div>"""


_ON = "background:var(--acc);color:#fff;border-color:var(--acc)"


def _indicators_section(market: str) -> str:
    """📈 重點觀察數據速覽格（總經／籌碼／產業報價）；無資料回空字串（區塊不顯示）。"""
    doc = indicators.load_latest()
    items = indicators.for_market(doc, market)
    if not items:
        return ""
    chips = []
    for it in items:
        chg = it.get("change") or ""
        cls = "up" if chg[:1] in "▲＋+" else ("dn" if chg[:1] in "▼－-" else "")
        tip = "｜".join(filter(None, [f"基準 {it.get('as_of')}", f"來源 {it.get('source')}",
                                     it.get("note")]))
        chips.append(
            f'<div class="ind" title="{_esc(tip)}"><div class="ik">{_esc(it.get("name"))}</div>'
            f'<div class="iv">{_esc(it.get("value"))}</div>'
            f'<div class="ic {cls}">{_esc(chg)}</div>'
            f'<div class="ia">{_esc(it.get("as_of"))}</div></div>')
    return f"""<div class="section">
  <div class="st">📈 重點觀察數據　<span class="asof">{_esc(doc.get('date'))}｜滑鼠停留看來源與備註；數據皆可追溯、查不到者不列</span></div>
  <div class="igrid">{''.join(chips)}</div>
</div>"""


def _mention_item(it: dict) -> str:
    """單筆提及：kind 徽章＋標題（連結）＋來源＋發文時間（每筆必附資料時間）。"""
    kind = fund_mentions.KIND_LABEL.get(it.get("kind"), it.get("kind") or "—")
    title = _esc(it.get("title") or "")
    if it.get("url"):
        title = f'<a href="{_esc(it["url"])}" target="_blank" rel="noopener">{title}</a>'
    meta = "｜".join(filter(None, [_esc(it.get("source") or ""), _esc(it.get("date") or "")]))
    return (f'<li class="mit"><span class="mk k-{_esc(it.get("kind") or "news")}">{_esc(kind)}</span>'
            f'<span class="mtt">{title}<span class="mmeta">{meta}</span></span></li>')


def _mentions_section(market: str) -> str:
    """🔎 基金動態雷達：公司層＋逐檔基金的新聞/社群/廣告提及（缺資料顯示啟用提示）。"""
    doc = fund_mentions.merged(market, config.funds(market))
    total = len(doc["company"]) + sum(len(f["items"]) for f in doc["funds"])
    if not total:
        hint = ('<div class="muted">尚無提及資料。新聞：<code>python scripts/fetch_mentions.py '
                f'--market {_esc(market)}</code>（CI 每日自動）；社群/廣告：'
                '<code>python scripts/gen_mentions.py</code> 產提示包後由 LLM 查證回填。</div>')
        body = hint
    else:
        parts = []
        if doc["company"]:
            parts.append('<div class="mgrp"><div class="mgt">🏢 復華投信（公司/品牌層）</div><ul class="mlist">'
                         + "".join(_mention_item(i) for i in doc["company"][:6]) + "</ul></div>")
        for f in doc["funds"]:
            if not f["items"]:
                continue
            nm = _esc((f.get("name") or "").replace("-新臺幣", ""))
            latest = _esc(f["items"][0].get("date") or "")
            parts.append(
                f'<details class="mgrp"><summary class="mgt">{nm}'
                f'<span class="mcnt">{len(f["items"])} 則｜最新 {latest}</span></summary>'
                f'<ul class="mlist">{"".join(_mention_item(i) for i in f["items"][:5])}</ul></details>')
        body = "".join(parts) or '<div class="muted">近 7 天無各檔基金之提及。</div>'
    as_of = _esc(doc.get("as_of") or "—")
    return f"""<div class="section">
  <div class="st">🔎 基金動態雷達　<span class="asof">新聞/社群/廣告提及｜資料時間 {as_of}｜近 7 天</span></div>
  {body}
</div>"""


def _market_panel(market: str, single: bool) -> tuple[str, str, str, int]:
    """單一市場面板（新聞區塊 ＋ 基金分頁 ＋ 卡片），供 render / render_combined 共用。

    分頁切換為純 CSS（radio+label，`:checked ~`），不依賴 JS。
    回傳 (panel_html, css_rules, as_of, n_funds)。"""
    mk = markets.get(market)
    mid = _esc(market)
    funds = fund_intro.all_funds(market)
    radios, tabs, css = [], [], []
    for i, d in enumerate(funds):
        fid = _esc(str(d.get("fund_id")))
        rid = f"fund-{mid}-{fid}"
        radios.append(f'<input class="vh" type="radio" name="fund-{mid}" id="{rid}"'
                      f'{" checked" if i == 0 else ""}>')
        tabs.append(f'<label class="tab" for="{rid}">'
                    f'{_esc((d.get("name") or "").replace("復華", "").replace("-新臺幣", ""))}</label>')
        css.append(f'#{rid}:checked~.fund[data-fund="{fid}"]{{display:block}}')
        css.append(f'#{rid}:checked~.section .tabs label[for="{rid}"]{{{_ON}}}')
    css.append(f'#nv-{mid}-v1:checked~.ndoc[data-nv="v1"]{{display:block}}')
    css.append(f'#nv-{mid}-v2:checked~.ndoc[data-nv="v2"]{{display:block}}')
    css.append(f'#nv-{mid}-v1:checked~.newsbar label[for="nv-{mid}-v1"]{{{_ON}}}')
    css.append(f'#nv-{mid}-v2:checked~.newsbar label[for="nv-{mid}-v2"]{{{_ON}}}')
    cards = "".join(_fund_card(d, i) for i, d in enumerate(funds))
    as_of = funds[0].get("as_of") if funds else "—"
    empty = "" if funds else '<div class="muted">尚無持股快照；請先執行 fetch_holdings。</div>'
    panel = f"""<div class="market{' on' if single else ''}" data-market="{mid}">
{_indicators_section(market)}
<div class="section">
  <div class="st">🗞️ {_esc(mk['news_label'])}</div>
  {_news_section(mk['news'], market)}
</div>
{_mentions_section(market)}
{''.join(radios)}
<div class="section">
  <div class="st">📊 基金持股介紹　<span class="asof">持股基準 {_esc(as_of)}｜共 {len(funds)} 檔</span></div>
  <div class="tabs">{''.join(tabs)}</div>
</div>
{cards}{empty}
</div>"""
    return panel, "\n".join(css), as_of, len(funds)


def render(market: str = "global") -> str:
    """單一市場整頁（向後相容；CI 單市場 artifact 與測試用）。"""
    mk = markets.get(market)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    panel, css, as_of, n = _market_panel(market, single=True)
    lede = (f"持股介紹（月度快照，基準 {_esc(as_of)}）＋ {_esc(mk['news_label'])}"
            f"　·　產表 {_esc(now)}　·　共 {n} 檔追蹤基金")
    return _page(mk["title"], mk["subtitle"], lede, "", panel, css)


def render_combined(market_keys: tuple[str, ...] = ("global", "tw")) -> str:
    """整合頁（D2(b)）：同一頁上層「海外／台股」切換（純 CSS radio+label），
    各市場自帶新聞區塊與基金分頁。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    mradios, mtabs, panels, parts, css = [], [], [], [], []
    for i, key in enumerate(market_keys):
        mk = markets.get(key)
        mid = _esc(key)
        mradios.append(f'<input class="vh" type="radio" name="mkt" id="mkt-{mid}"'
                       f'{" checked" if i == 0 else ""}>')
        mtabs.append(f'<label class="mtab" for="mkt-{mid}">{_esc(mk["tab_label"])}</label>')
        css.append(f'#mkt-{mid}:checked~.market[data-market="{mid}"]{{display:block}}')
        css.append(f'#mkt-{mid}:checked~.mtabs label[for="mkt-{mid}"]{{{_ON}}}')
        panel, pcss, _as_of, n = _market_panel(key, single=False)
        panels.append(panel)
        css.append(pcss)
        parts.append(f"{_esc(mk['tab_label'])} {n} 檔")
    top_switch = "".join(mradios) + f'<div class="mtabs">{"".join(mtabs)}</div>'
    lede = (f"持股介紹（月度官方揭露快照）＋ 昨夜美股／台股新聞　·　產表 {_esc(now)}"
            f"　·　{_esc(' · '.join(parts))}")
    title = "復華基金追蹤版本"
    subtitle = "Fuh Hwa Fund Radar｜海外＋台股"
    return _page(title, subtitle, lede, top_switch, "".join(panels), "\n".join(css))


def _page(title: str, subtitle: str, lede: str, top_switch: str, body: str,
          dyn_css: str = "") -> str:
    """整頁 HTML 外殼（CSS ＋ 頁首 ＋ 市場切換 ＋ body ＋ 頁尾）。

    零 JS：所有分頁切換（市場/基金/新聞版型）以 radio+label 純 CSS 實現，
    dyn_css 為依基金清單動態產生的 `:checked ~` 顯示規則。"""
    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)} · 持股介紹＋昨夜美股／台股新聞</title>
<style>
:root{{--bg:#0e1116;--card:#161b22;--card2:#1c232d;--ink:#e6edf3;--mut:#9aa7b4;
--line:#2a323c;--red:#e5484d;--c1:#3b82f6;--c2:#f59e0b;--up:#3fb950;--dn:#e5484d;--acc:#5b8def}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 -apple-system,"PingFang TC","Noto Sans TC",Segoe UI,sans-serif}}
a{{color:var(--acc)}} code{{background:#0b0e13;padding:1px 6px;border-radius:5px;color:#9ecbff}}
.wrap{{max-width:1080px;margin:0 auto;padding:22px 18px 60px}}
header h1{{font-size:22px;margin:0 0 3px}} .lede{{color:var(--mut);font-size:13px;margin-bottom:16px}}
.section{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin:16px 0}}
.section>.st{{font-weight:700;font-size:16px;margin-bottom:10px;display:flex;align-items:center;gap:8px}}
.muted{{color:var(--mut)}}
/* news */
.newsbar{{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin-bottom:12px}}
.ndate{{font-weight:700;font-size:15px}} .lamp{{color:var(--mut);font-size:13px}}
.nswitch{{margin-left:auto;display:flex;gap:6px}}
.nb{{display:inline-block;background:var(--card2);color:var(--mut);border:1px solid var(--line);border-radius:20px;padding:6px 14px;cursor:pointer;font-size:13px;user-select:none}}
/* 重點觀察數據：手機橫向滑動速覽列、桌機格狀 */
.igrid{{display:flex;gap:10px;overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:thin;padding-bottom:4px}}
.ind{{flex:0 0 176px;background:var(--card2);border:1px solid var(--line);border-radius:11px;padding:10px 12px;cursor:help}}
@media(min-width:721px){{.igrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(196px,1fr));overflow:visible}}.ind{{flex:none}}}}
.ik{{font-size:12px;color:var(--mut);line-height:1.4}}
.iv{{font-size:17px;font-weight:800;margin:3px 0 1px;color:#fff}}
.ic{{font-size:12px;color:var(--mut);line-height:1.45}}
.ic.up{{color:var(--up)}} .ic.dn{{color:var(--dn)}}
.ia{{font-size:10.5px;color:var(--mut);opacity:.7;margin-top:3px}}
/* 基金動態雷達（新聞/社群/廣告提及） */
.mgrp{{border:1px solid var(--line);border-radius:11px;padding:10px 14px;margin:10px 0;background:var(--card2)}}
.mgt{{font-weight:700;font-size:14px;cursor:pointer;display:flex;flex-wrap:wrap;align-items:center;gap:8px}}
.mcnt{{font-weight:400;font-size:11.5px;color:var(--mut)}}
.mlist{{list-style:none;margin:8px 0 2px;padding:0}}
.mit{{display:flex;gap:8px;align-items:flex-start;margin:8px 0;font-size:13.5px;line-height:1.55}}
.mk{{flex:0 0 auto;font-size:11px;font-weight:700;padding:1px 8px;border-radius:20px;border:1px solid var(--line);color:var(--mut);margin-top:2px}}
.mk.k-news{{color:#9ecbff;border-color:rgba(91,141,239,.4);background:rgba(91,141,239,.12)}}
.mk.k-social{{color:#7ee2a8;border-color:rgba(63,185,80,.4);background:rgba(63,185,80,.1)}}
.mk.k-ad{{color:#ffd479;border-color:rgba(245,158,11,.4);background:rgba(245,158,11,.1)}}
.mtt{{flex:1;min-width:0;word-break:break-word}}
.mmeta{{display:block;font-size:11.5px;color:var(--mut);margin-top:1px}}
/* 新聞卡片版型（重點置頂） */
.quick{{border:1px dashed var(--acc);border-radius:12px;padding:10px 16px;margin:14px 0;background:rgba(91,141,239,.06)}}
.quick .qt{{font-weight:800;font-size:14px;color:#9ecbff;margin-bottom:4px}}
.quick ol{{margin:4px 0 2px;padding-left:22px}} .quick li{{margin:5px 0;font-size:14px;color:#dbe4ee}}
.ncard{{background:var(--card2);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:12px 0}}
.nhead{{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px;margin-bottom:8px}}
.ntitle{{font-size:15.5px;font-weight:700;color:#fff;line-height:1.5}}
.badges{{display:inline-flex;flex-wrap:wrap;gap:5px}}
.nlead{{font-size:16px;font-weight:700;color:#cfe0ff;line-height:1.6;margin:8px 0 12px;padding:9px 14px;background:linear-gradient(90deg,rgba(91,141,239,.16),rgba(91,141,239,.03));border-left:3px solid var(--acc);border-radius:0 10px 10px 0}}
.nrow{{display:flex;gap:10px;margin:7px 0;font-size:13.5px;line-height:1.65}}
.nlab{{flex:0 0 74px;color:var(--mut);font-size:12px;text-align:right;padding-top:2px}}
.nval{{flex:1;color:#dbe4ee}}
.nrefs{{margin-top:8px;font-size:12px;color:var(--mut)}}
.nrefs summary{{cursor:pointer;color:var(--mut)}} .nrefs div{{margin-top:6px;line-height:1.7}}
details.fineprint{{margin:14px 0;font-size:12.5px;color:var(--mut)}}
details.fineprint summary{{cursor:pointer;font-weight:600;color:var(--mut)}}
details.fineprint>div{{margin-top:6px;border-left:2px solid var(--line);padding-left:12px}}
@media(max-width:560px){{.nrow{{flex-direction:column;gap:2px}}.nlab{{text-align:left;flex:none}}}}
.ndoc{{background:var(--card2);border:1px solid var(--line);border-radius:12px;padding:8px 30px 24px;line-height:1.85;font-size:15px;color:#dbe4ee}}
.ndoc>*:first-child{{margin-top:14px}}
.ndoc h2{{font-size:14.5px;color:var(--mut);font-weight:600;letter-spacing:.02em;margin:30px 0 12px;padding-bottom:8px;border-bottom:1px solid var(--line)}}
.ndoc h3{{font-size:16.5px;color:#fff;font-weight:700;line-height:1.55;margin:26px 0 10px;padding:12px 16px;background:linear-gradient(90deg,rgba(91,141,239,.16),rgba(91,141,239,.03));border-left:3px solid var(--acc);border-radius:0 10px 10px 0}}
.ndoc h4{{font-size:14.5px;color:#cfe0ff;margin:18px 0 6px}}
.ndoc p{{margin:9px 0}}
.ndoc ul,.ndoc ol{{margin:10px 0;padding-left:0;list-style:none;counter-reset:n}}
.ndoc ul li{{position:relative;margin:8px 0;padding-left:20px}}
.ndoc ul li:before{{content:"";position:absolute;left:4px;top:12px;width:5px;height:5px;border-radius:50%;background:var(--acc)}}
.ndoc ol li{{position:relative;margin:11px 0;padding-left:36px;counter-increment:n}}
.ndoc ol li:before{{content:counter(n);position:absolute;left:0;top:2px;width:23px;height:23px;border-radius:50%;background:var(--acc);color:#fff;font-size:12px;font-weight:700;text-align:center;line-height:23px}}
.ndoc b{{color:#fff}} .ndoc a{{text-decoration:none;border-bottom:1px dashed var(--acc);word-break:break-all}}
.ndoc hr{{border:0;border-top:1px solid var(--line);margin:22px 0}}
.ndoc small,.ndoc i{{color:var(--mut);font-style:normal}}
.tag{{display:inline-block;font-size:12px;font-weight:700;padding:1px 9px;border-radius:20px;background:rgba(91,141,239,.18);color:#9ecbff;border:1px solid rgba(91,141,239,.35);white-space:nowrap}}
/* 純 CSS 分頁（radio+label）：隱藏 radio、:checked 規則見檔尾動態區 */
.vh{{position:absolute;opacity:0;pointer-events:none;width:0;height:0}}
.market,.fund,.ndoc{{display:none}}
.market.on{{display:block}}
/* 上層市場切換（海外／台股）：黏性置頂 segmented control，手機好按 */
.mtabs{{position:sticky;top:0;z-index:9;display:flex;gap:8px;padding:10px 0 8px;margin:0 0 4px;background:var(--bg)}}
.mtab{{flex:1;text-align:center;background:var(--card2);color:var(--mut);border:1px solid var(--line);border-radius:11px;padding:11px 10px;cursor:pointer;font-size:15px;font-weight:700;user-select:none}}
/* 基金分頁：手機橫向滑動（不佔高度）、桌機換行 */
.tabs{{display:flex;flex-wrap:nowrap;gap:6px;margin:6px 0 2px;overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:thin;padding-bottom:4px}}
.tab{{flex:0 0 auto;white-space:nowrap;background:var(--card2);color:var(--mut);border:1px solid var(--line);border-radius:20px;padding:8px 14px;cursor:pointer;font-size:13px;user-select:none}}
@media(min-width:721px){{.tabs{{flex-wrap:wrap;overflow:visible}}}}
/* fund card */
.fund{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;margin-top:12px}}
.fhead{{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;align-items:flex-start}}
.fhead h2{{font-size:19px;margin:0 0 4px}} .gl{{font-size:12px;color:#fff;background:var(--acc);padding:2px 8px;border-radius:20px;vertical-align:middle}}
.sub{{color:var(--mut);font-size:12.5px}} .oneline{{margin-top:6px;font-size:13.5px;color:#cfe0ff}}
.navbox{{text-align:right;min-width:180px}} .nav{{font-size:26px;font-weight:800}}
.navd{{font-size:12px;color:var(--mut)}} .size{{font-size:12px;color:var(--mut);margin-top:4px}}
.up{{color:var(--up)}} .dn{{color:var(--dn)}}
.mrpt{{display:inline-block;margin-left:6px}}
.strat{{margin:12px 0 4px;color:var(--mut);font-size:13px;border-left:3px solid var(--line);padding-left:10px}}
.rets{{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin:14px 0}}
.rc{{background:var(--card2);border:1px solid var(--line);border-radius:9px;padding:8px;text-align:center}}
.rk2{{font-size:11px;color:var(--mut)}} .rv{{font-weight:700;font-size:14px}}
.cols{{display:grid;grid-template-columns:1fr 1.25fr;gap:18px;margin-top:8px}}
.ctitle{{font-weight:700;font-size:14px;margin-bottom:8px}} .asof{{font-weight:400;font-size:11.5px;color:var(--mut)}}
.barrow{{display:flex;align-items:center;gap:8px;margin:5px 0;font-size:12.5px}}
.blab{{width:78px;flex:0 0 78px;color:var(--mut)}} .btrack{{flex:1;height:9px;background:#0b0e13;border-radius:6px;overflow:hidden}}
.bfill{{display:block;height:100%}} .bval{{width:48px;text-align:right}}
.htbl{{width:100%;border-collapse:collapse}} .htbl th{{text-align:right;color:var(--mut);font-size:11.5px;font-weight:600;padding:4px 6px;border-bottom:1px solid var(--line)}}
.htbl th.l{{text-align:left}} .htbl td{{padding:7px 6px;border-bottom:1px solid var(--line);vertical-align:top}}
.htbl .rk{{color:var(--mut);width:22px}} .htbl .wt{{text-align:right;font-weight:700;white-space:nowrap}}
.htbl .sec{{font-size:11px;color:var(--mut);border:1px solid var(--line);border-radius:5px;padding:0 5px;margin-left:4px}}
.tk{{font-size:11px;color:#9ecbff}} .pill{{font-size:11px;color:var(--mut);border:1px solid var(--line);border-radius:5px;padding:0 5px;margin-left:4px}}
.hintro{{color:var(--mut);font-size:12px;margin-top:3px}}
.hmore{{margin-top:3px;font-size:12px;color:var(--mut)}}
.hmore summary{{cursor:pointer;color:var(--acc);font-size:11.5px}}
.hmore[open]{{background:rgba(91,141,239,.05);border-radius:6px;padding:4px 8px;line-height:1.7}}
.foot{{color:var(--mut);font-size:11.5px;margin-top:22px;border-top:1px solid var(--line);padding-top:12px}}
/* ── 行動版（≤720px）：單欄、緊湊間距、可讀字級 ── */
@media(max-width:720px){{
.wrap{{padding:0 12px 44px}}
header{{padding-top:12px}} header h1{{font-size:18px}} .lede{{font-size:12px;line-height:1.55}}
.section{{padding:12px 12px;margin:12px 0;border-radius:12px}}
.section>.st{{font-size:15px;flex-wrap:wrap;row-gap:2px}}
.cols{{grid-template-columns:1fr;gap:14px}}
.rets{{grid-template-columns:repeat(3,1fr);gap:6px}} .rv{{font-size:13px}}
.fhead{{flex-direction:column;gap:8px}}
.navbox{{text-align:left;min-width:0;display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 12px}}
.nav{{font-size:22px}}
.fund{{padding:13px 12px}} .fhead h2{{font-size:16.5px}}
.ndoc{{padding:6px 14px 18px;font-size:14.5px}}
.ndoc h3{{font-size:15px;padding:10px 12px}}
.ncard{{padding:12px 12px}} .ntitle{{font-size:14.5px}} .nlead{{font-size:15px;padding:8px 12px}}
.quick{{padding:9px 12px}} .quick li{{font-size:13.5px}}
.htbl td{{padding:6px 3px;font-size:13px}} .htbl .rk{{width:16px}}
.blab{{width:64px;flex:0 0 64px;font-size:11.5px}}
.newsbar{{gap:6px}} .nswitch{{margin-left:0;width:100%}} .nswitch .nb{{flex:1;text-align:center}}
.foot{{font-size:11px}}
}}
/* ── 動態分頁規則（依基金清單產生的 :checked 顯示規則）── */
{dyn_css}
</style></head>
<body><div class="wrap">
<header>
  <h1>{_esc(title)}　<span style="font-size:13px;color:var(--mut)">{_esc(subtitle)}</span></h1>
  <div class="lede">{lede}</div>
</header>
{top_switch}
{body}

<div class="foot">
  資料來源：復華投信官網（fhtrust.com.tw）基金淨值／持股揭露（月度）；重點標的簡介為中性事實敘述、非投資建議。
  昨夜美股／台股新聞為公開來源彙編、教育用途，非投資建議或招攬；過去績效不代表未來表現，淨值可能因市場變動而上下；
  境外基金涉及匯率與國際市場風險，國內平衡型基金另涉債券之利率與信用風險。投資人申購本基金係持有基金受益憑證，
  非本文提及之投資資產或標的。申購前應詳閱公開說明書／投資人須知。本版本不呈現「每天持股變化」（共同基金無逐日持股張數）。
</div>
</div>
</body></html>"""
