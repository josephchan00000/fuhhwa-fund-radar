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

from . import fund_intro, markets, twnews, usnews

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
        rows.append(
            f'<tr><td class="rk">{i}</td>'
            f'<td class="nm"><b>{_esc(h.get("name"))}</b>{tk}{sec} {ct}{intro}</td>'
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
    hide = "" if idx == 0 else "hidden"
    return f"""
<section class="fund {hide}" data-fund="{_esc(doc.get('fund_id'))}">
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


def _news_section(news: str = "us") -> str:
    """依市場新聞來源分派（"us"→usnews、"tw"→twnews），兩模組介面對稱。"""
    mod = _NEWS_MODULES.get(news, usnews)
    n = mod.load_latest()
    if not n:
        return f'<div class="muted">{mod.EMPTY_HINT}</div>'
    lamp = ("🟢 合規掃描通過" if not n["banned_hits"]
            else f'🔴 出現禁用詞：{"、".join(n["banned_hits"])}')
    v1 = _md(n.get("v1") or "") or '<div class="muted">（無版型一）</div>'
    v2 = _md(n.get("v2") or "") or '<div class="muted">（無版型二）</div>'
    return f"""
  <div class="newsbar">
    <span class="ndate">📅 {_esc(n['date'])}</span>
    <span class="lamp">{_esc(lamp)}</span>
    <span class="nswitch"><button class="nb on" data-nv="v1">{_esc(mod.V1_LABEL)}</button>
      <button class="nb" data-nv="v2">{_esc(mod.V2_LABEL)}</button></span>
  </div>
  <div class="ndoc" data-nv="v1">{v1}</div>
  <div class="ndoc hidden" data-nv="v2">{v2}</div>"""


def _market_panel(market: str, active: bool) -> tuple[str, str, int]:
    """單一市場面板（新聞區塊 ＋ 基金分頁 ＋ 卡片），供 render / render_combined 共用。

    回傳 (panel_html, as_of, n_funds)。以 .market 容器包住，整合頁上層切換即以此顯示／隱藏。"""
    mk = markets.get(market)
    funds = fund_intro.all_funds(market)
    tabs = "".join(
        f'<button class="tab{" on" if i == 0 else ""}" data-fund="{_esc(d.get("fund_id"))}">'
        f'{_esc((d.get("name") or "").replace("復華", "").replace("-新臺幣", ""))}</button>'
        for i, d in enumerate(funds))
    cards = "".join(_fund_card(d, i) for i, d in enumerate(funds))
    as_of = funds[0].get("as_of") if funds else "—"
    empty = "" if funds else '<div class="muted">尚無持股快照；請先執行 fetch_holdings。</div>'
    panel = f"""<div class="market{'' if active else ' hidden'}" data-market="{_esc(market)}">
<div class="section">
  <div class="st">🗞️ {_esc(mk['news_label'])}</div>
  {_news_section(mk['news'])}
</div>
<div class="section">
  <div class="st">📊 基金持股介紹　<span class="asof">持股基準 {_esc(as_of)}｜共 {len(funds)} 檔</span></div>
  <div class="tabs">{tabs}</div>
</div>
{cards}{empty}
</div>"""
    return panel, as_of, len(funds)


def render(market: str = "global") -> str:
    """單一市場整頁（向後相容；CI 單市場 artifact 與測試用）。"""
    mk = markets.get(market)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    panel, as_of, n = _market_panel(market, active=True)
    lede = (f"持股介紹（月度快照，基準 {_esc(as_of)}）＋ {_esc(mk['news_label'])}"
            f"　·　產表 {_esc(now)}　·　共 {n} 檔追蹤基金")
    return _page(mk["title"], mk["subtitle"], lede, "", panel)


def render_combined(market_keys: tuple[str, ...] = ("global", "tw")) -> str:
    """整合頁（D2(b)）：同一頁上層「海外／台股」切換，各市場自帶新聞區塊與基金分頁。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    switch_btns, panels, parts = [], [], []
    for i, key in enumerate(market_keys):
        mk = markets.get(key)
        switch_btns.append(
            f'<button class="mtab{" on" if i == 0 else ""}" data-market="{_esc(key)}">'
            f'{_esc(mk["tab_label"])}</button>')
        panel, _as_of, n = _market_panel(key, active=(i == 0))
        panels.append(panel)
        parts.append(f"{_esc(mk['tab_label'])} {n} 檔")
    top_switch = f'<div class="mtabs">{"".join(switch_btns)}</div>'
    lede = (f"持股介紹（月度官方揭露快照）＋ 昨夜美股／台股新聞　·　產表 {_esc(now)}"
            f"　·　{_esc(' · '.join(parts))}")
    title = "復華基金追蹤版本"
    subtitle = "Fuh Hwa Fund Radar｜海外＋台股"
    return _page(title, subtitle, lede, top_switch, "".join(panels))


def _page(title: str, subtitle: str, lede: str, top_switch: str, body: str) -> str:
    """整頁 HTML 外殼（CSS ＋ 頁首 ＋ 市場切換 ＋ body ＋ 頁尾 ＋ 容器內作用域 JS）。"""
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
.nb{{background:var(--card2);color:var(--mut);border:1px solid var(--line);border-radius:20px;padding:6px 14px;cursor:pointer;font-size:13px}}
.nb.on{{background:var(--acc);color:#fff;border-color:var(--acc)}}
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
/* 上層市場切換（海外／台股） */
.mtabs{{display:flex;gap:8px;margin:2px 0 4px}}
.mtab{{background:var(--card2);color:var(--mut);border:1px solid var(--line);border-radius:11px;padding:9px 24px;cursor:pointer;font-size:15px;font-weight:700}}
.mtab.on{{background:var(--acc);color:#fff;border-color:var(--acc)}}
.market.hidden{{display:none}}
/* tabs */
.tabs{{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 2px}}
.tab{{background:var(--card2);color:var(--mut);border:1px solid var(--line);border-radius:9px;padding:6px 11px;cursor:pointer;font-size:13px}}
.tab.on{{background:var(--acc);color:#fff;border-color:var(--acc)}}
/* fund card */
.fund{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;margin-top:12px}}
.fund.hidden,.ndoc.hidden{{display:none}}
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
.foot{{color:var(--mut);font-size:11.5px;margin-top:22px;border-top:1px solid var(--line);padding-top:12px}}
@media(max-width:720px){{.cols{{grid-template-columns:1fr}}.rets{{grid-template-columns:repeat(3,1fr)}}.navbox{{text-align:left}}}}
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
<script>
// 上層市場切換（海外／台股）：顯示對應 .market 面板
document.querySelectorAll('.mtab').forEach(t=>t.onclick=()=>{{
  document.querySelectorAll('.mtab').forEach(x=>x.classList.remove('on'));t.classList.add('on');
  const m=t.dataset.market;
  document.querySelectorAll('.market').forEach(p=>p.classList.toggle('hidden',p.dataset.market!==m));
}});
// 基金分頁與新聞版型切換：作用域限縮於各自的 .market 面板（避免整合頁跨市場互相干擾）
document.querySelectorAll('.market').forEach(mkt=>{{
  mkt.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{{
    mkt.querySelectorAll('.tab').forEach(x=>x.classList.remove('on'));t.classList.add('on');
    const id=t.dataset.fund;
    mkt.querySelectorAll('.fund').forEach(f=>f.classList.toggle('hidden',f.dataset.fund!==id));
  }});
  mkt.querySelectorAll('.nb').forEach(b=>b.onclick=()=>{{
    mkt.querySelectorAll('.nb').forEach(x=>x.classList.remove('on'));b.classList.add('on');
    const v=b.dataset.nv;
    mkt.querySelectorAll('.ndoc').forEach(d=>d.classList.toggle('hidden',d.dataset.nv!==v));
  }});
}});
</script>
</body></html>"""
