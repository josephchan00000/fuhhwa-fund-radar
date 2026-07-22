"""復華基金追蹤版本 · 零安裝儀表板（業務優先三層資訊架構＋台股/全球雙視圖）——
讀 data/funds/*.json + config/holding_profiles.json + config/holding_aliases.json
+ reports/usnews/{最新}_v1/_v2.md + reports/twnews/{最新}.md → 產單一 dashboard/index.html。

版面邏輯（見 docs/REDESIGN_PLAN.md；左上「台股／全球」切換，各視圖同一順序）：
  ⓪ Sticky 頂欄：市場切換｜日期｜合規燈｜錨點導覽
  ① 今日重點：指數卡（台股＝加權/櫃買、全球＝美股三大）／今日最強最弱／連動計數
  ② 新聞（重點＋全文合併）：每則一個收合塊、預設收合；標題列即顯示一句話重點，
     展開看摘要＋影響分析＋可點原文連結（富途優先）；頭段「總覽」改置頂可見卡，
     資料侷限／合規揭露不上板（合規統一置頁尾小字——2026-07-15 使用者指示）
  ③ （當日焦點個股區已移除——2026-07-15 使用者指示；新聞×持股連動僅保留詳情卡 🔗 高亮）
  ④ 基金總覽表：可排序、紅漲綠跌、點列跳詳情
  ⑤ 基金詳情：逐檔卡片（錨點直達、同組平均對照、連動持股高亮、複製介紹）

純 vanilla HTML＋少量 JS（市場切換／排序／複製／版型切換），零外部請求、雙擊即開。
不做「每天持股變化」（共同基金無逐日持股張數）。
"""
from __future__ import annotations

import html
import json
import re
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

from . import (clock, etfwatch, fund_insights, fund_intro, fundnews, macronews,
               twnews, usnews)


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def _short(doc_or_name) -> str:
    """顯示用簡稱：去『復華』品牌前綴（僅一次）與『(-)新臺幣』尾綴。"""
    n = doc_or_name if isinstance(doc_or_name, str) else \
        (doc_or_name.get("short_name") or doc_or_name.get("name") or "")
    n = n.replace("復華", "", 1)
    for suf in ("-新臺幣", "新臺幣"):
        if n.endswith(suf):
            n = n[: -len(suf)]
    return n or str(doc_or_name)


def _mof(doc: dict) -> str:
    """基金所屬市場：'tw'（國內）或 'gl'（全球/海外）。"""
    return "tw" if str(doc.get("group") or "").startswith("tw") else "gl"


def _mkt(tw_html: str, gl_html: str) -> str:
    """台股/全球雙視圖包裝；CSS 依 body[data-mkt] 顯示其一。"""
    return (f'<div class="mkt" data-mkt="tw">{tw_html}</div>'
            f'<div class="mkt" data-mkt="gl">{gl_html}</div>')



# ── SVG 線性圖標（取代 emoji：專業資訊站質感、列印/跨平台一致） ──
_ICON_PATHS = {
    "zap": '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    "news": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
            '<polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/>'
            '<line x1="16" y1="17" x2="8" y2="17"/>',
    "megaphone": '<path d="m3 11 18-5v12L3 14v-3z"/><path d="M11.6 16.8a3 3 0 1 1-5.8-1.6"/>',
    "chart": '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/>'
             '<line x1="6" y1="20" x2="6" y2="14"/>',
    "activity": '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
    "landmark": '<line x1="3" y1="22" x2="21" y2="22"/><line x1="6" y1="18" x2="6" y2="11"/>'
                '<line x1="10" y1="18" x2="10" y2="11"/><line x1="14" y1="18" x2="14" y2="11"/>'
                '<line x1="18" y1="18" x2="18" y2="11"/><polygon points="12 2 20 7 4 7"/>',
    "clipboard": '<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>'
                 '<rect x="8" y="2" width="8" height="4" rx="1"/>'
                 '<line x1="12" y1="11" x2="16" y2="11"/><line x1="12" y1="16" x2="16" y2="16"/>',
    "calendar": '<rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/>'
                '<line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    "printer": '<polyline points="6 9 6 2 18 2 18 9"/>'
               '<path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/>'
               '<rect x="6" y="14" width="12" height="8"/>',
    "moon": '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>',
    "bell": '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>',
    "coin": '<line x1="12" y1="1" x2="12" y2="23"/>'
            '<path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>',
    "search": '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
    "book": '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>'
            '<path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>',
    "globe": '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/>'
             '<path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10'
             ' 15.3 15.3 0 0 1 4-10z"/>',
    "layers": '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/>'
              '<polyline points="2 12 12 17 22 12"/>',
    "chat": '<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1'
            '-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0'
            ' 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>',
}


def _ic(name: str, plain: bool = False, tone: str = "") -> str:
    """區塊標題用「色底圖標章」（預設藍；tone=amber/green/purple/teal/navy 換模組色，
    雲學堂式各分區一色）；行內/按鈕用 plain（無底、隨文字色）。"""
    svg = (f'<svg viewBox="0 0 24 24" aria-hidden="true">{_ICON_PATHS[name]}</svg>')
    cls = "ic plain" if plain else ("ic" + (f" t-{tone}" if tone else ""))
    return f'<span class="{cls}">{svg}</span>'


def _safe_url(u) -> str:
    """外部餵入的連結只放行 http(s)（審查 #6：RSS/PTT 來源可被污染成 javascript: URL）。"""
    u = str(u or "")
    return u if u.startswith(("http://", "https://")) else "#"


def _md(text: str) -> str:
    """極簡 Markdown → HTML（標題/粗體/連結/有序＋無序清單/水平線/段落）；
    先刷隱形字元、跳脫，再套規則。"""
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

    for raw in usnews.scrub(text).splitlines():
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
            open_list("ul"); out.append(f"<li>{_klabel(_inline(m.group(1)))}</li>"); continue
        m = re.match(r"^\s*(\d+)\.\s+(.*)$", line)              # 有序清單（新聞卡 1.~6. 條列）
        if m:
            open_list("ol"); out.append(f"<li>{_klabel(_inline(m.group(2)))}</li>"); continue
        close()
        if line.strip():
            out.append(f"<p>{_klabel(_inline(line))}</p>")
    close()
    return "\n".join(out)


def _inline(s: str) -> str:
    s = _esc(usnews.scrub(s))
    s = re.sub(r"\[([^\]]+)\]\((https?://[^\s)]+)\)",
               r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)          # 非貪婪：允許粗體內含斜體 **a *b* c**
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", s)
    s = re.sub(r"【([^】]+)】", r'<span class="tag">【\1】</span>', s)   # 消息屬性徽章
    return s


def _klabel(html_line: str) -> str:
    """抓重點小標：行首「<b>短標籤</b>：」→ 藍色段落小標（.klabel），其後粗體維持
    淺藍底關鍵句標記——把新聞卡「對持股／族群影響」式的掃讀版型類比到所有 _md 內容
    （政策總覽／盤前速覽／深度文…，2026-07-18 使用者指示）。標籤上限 14 字防誤傷長句。"""
    return re.sub(r"^<b>([^<>]{1,14})</b>\s*[：:]\s*",
                  r'<span class="klabel">\1</span>', html_line)


def _pct_span(v: float | None, digits: int = 2, chip: bool = False) -> str:
    """紅漲綠跌的漲跌幅（台灣慣例）。None → 灰 —。
    chip=True 時漲跌加淡底色塊（詳情卡摘要列用，掃讀落點）；持平／缺值維持純文字。"""
    if v is None:
        return '<span class="na">—</span>'
    cls = "gain" if v > 0 else ("loss" if v < 0 else "flat")
    if chip and cls != "flat":
        cls += " pchip"
    sign = "+" if v > 0 else ""
    return f'<span class="{cls}">{sign}{v:.{digits}f}%</span>'


# ── ⓪ Sticky 頂欄（含台股/全球切換） ─────────────────────────

def _topbar(banned_hits: list[str], has_news: bool, as_of: str, now: str) -> str:
    if not has_news:
        lamp = '<span class="dot off"></span>尚無新聞'
    elif not banned_hits:
        lamp = '<span class="dot ok"></span>合規掃描通過'
    else:
        lamp = ('<span class="dot err"></span>禁用詞：'
                + _esc("、".join(sorted(set(banned_hits)))))
    return f"""
<div class="topbar">
  <div class="tb-in">
    <span class="tb-brand">復華基金雷達</span>
    <span class="mkswitch"><label class="mk" for="mkt-macro">總經</label><label class="mk" for="mkt-tw">台股</label><label class="mk" for="mkt-gl">全球</label><label class="mk" for="mkt-etf">ETF</label></span>
    <span class="tb-meta">持股基準 {_esc(as_of)}｜產表 {_esc(now)}</span>
    <span class="tb-lamp">{lamp}</span>
    <nav class="tb-nav tb-nav-fund">
      <a href="#brief">今日重點</a><a href="#news">新聞</a>
      <a href="#fundnews">基金新聞</a>
      <a href="#overview">基金總覽</a>
      <a href="#details">基金詳情</a>
    </nav>
    <nav class="tb-nav tb-nav-macro">
      <a href="#macro-cal">本週行事曆</a><a href="#macro-ov">政策總覽</a><a href="#macro">政策新聞</a>
    </nav>
    <nav class="tb-nav tb-nav-etf">
      <a href="#etf-passive">被動 ETF</a><a href="#etf-active">主動股票</a><a href="#etf-other">其他</a>
    </nav>
  </div>
</div>"""


# ── ⓪b 資料更新時間（各資料來源鮮度一覽；台股/全球/總經三頁共用） ──

def _age_days(value: str | None, today=None) -> int | None:
    """時戳字串（YYYY/MM/DD 或 YYYY-MM-DD，可帶 HH:MM）距今天幾天；解析不到回 None。"""
    m = re.match(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", str(value or ""))
    if not m:
        return None
    try:
        d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None
    return ((today or clock.today_tw()) - d).days


def _is_stale(value: str | None, tol: int | None, today=None) -> bool:
    """時戳超過容忍天數（或缺值）視為逾期；tol=None 永不逾期。"""
    if tol is None:
        return False
    age = _age_days(value, today)
    return age is None or age > tol


def _fresh_chip(label: str, value: str | None, tol: int | None = None,
                today=None, gen: bool = False) -> str:
    """單一鮮度徽章：逾期標紅 ⚠；gen=True 帶 data-gen 供瀏覽器端逾期偵測。"""
    stale = _is_stale(value, tol, today)
    age = _age_days(value, today)
    warn = f"　⚠ {age} 天未更新" if (stale and age is not None) else ("　⚠ 缺資料" if stale else "")
    attr = f' data-gen="{_esc(value)}"' if (gen and value) else ""
    cls = " stale" if stale else ("" if value else " dim")
    return (f'<span class="chip fresh{cls}"{attr}><b>{_esc(label)}</b>　'
            f'{_esc(value or "—")}{_esc(warn)}</span>')


def _factcheck_chip() -> str:
    """數字核對狀態章（讀 data/factcheck.json；CI 端與官方 API 比對的結果）。
    🔴＝報告數字與官方不符（照常發佈但標紅警示、主會話會立即修正重推——
    2026-07-20 使用者指示：防線不可硬到什麼都沒更新）。無檔／非今日＝不顯示。"""
    fp = ROOT_DIR / "data" / "factcheck.json"
    try:
        doc = json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if doc.get("red"):
        return (f'<span class="chip fresh stale"><b>數字核對</b>　🔴 {doc["red"]} 項與官方不符'
                f'（{_esc(doc.get("as_of") or "")}核對，修正中）</span>')
    if doc.get("green"):
        return (f'<span class="chip fresh"><b>數字核對</b>　🟢 {doc["green"]} 項與官方相符'
                f'（{_esc(doc.get("as_of") or "")}）</span>')
    return ""


def _freshness_view(gen_stamp: str, sources: list[tuple[str, str | None, int | None]],
                    today=None) -> str:
    """最上方只標「網頁更新時間」；各來源時戳分散標於各自區塊標題列，這裡只彙總逾期警示。"""
    stale = [k for k, v, tol in sources if _is_stale(v, tol, today)]
    sub = (f'<span class="stale-note">⚠ {len(stale)} 項資料逾期未更新（{"、".join(stale)}），'
           f'請跑「全部更新」或檢查 CI</span>' if stale
           else '各資料來源的更新時間標於各區塊標題列（皆台北時間）')
    return (f'<div class="section" id="freshness"><div class="st">{_ic("clock")}網頁更新時間　'
            f'{_fresh_chip("網頁更新", gen_stamp, None, today, gen=True)} '
            f'{_factcheck_chip()} '
            f'<span class="stsub">{sub}</span></div></div>')


# ── ① 今日重點 ───────────────────────────────────────────────

def _brief_view(indices: list[dict], best: dict | None, worst: dict | None,
                dists: list[dict], hol: str = "") -> str:
    idx_cards = "".join(
        f'<div class="ixc"><div class="ixl">{_esc(ix["label"])}</div>'
        f'<div class="ixv">{_esc(ix["close"])}</div>'
        f'<div class="ixp">{_pct_span(ix["pct"] if ix["up"] else -ix["pct"])}</div></div>'
        for ix in indices)
    if not idx_cards:
        idx_cards = '<div class="muted">（指數收盤點位以官方為準——詳見下方新聞）</div>'
    chips = []
    if best:
        chips.append(f'<a class="chip" href="#fund-{_esc(best["fund_id"])}">▲ 今日最強：'
                     f'<b>{_esc(_short(best["short_name"]))}</b> {_pct_span(best["chg"])}</a>')
    if worst:
        chips.append(f'<a class="chip" href="#fund-{_esc(worst["fund_id"])}">▼ 今日最弱：'
                     f'<b>{_esc(_short(worst["short_name"]))}</b> {_pct_span(worst["chg"])}</a>')
    if hol:
        chips.append(f'<span class="chip halt">{_ic("bell", plain=True)} {_esc(hol)}</span>')
    for x in dists:
        chips.append(f'<span class="chip">{_ic("coin", plain=True)} {_esc(_short(x["short_name"]))} 配息基準日 '
                     f'{_esc(x["dist_date"])}</span>')
    return f'<div class="ixrow">{idx_cards}</div><div class="chips">{"".join(chips)}</div>'


_PREMKT_HEAD = re.compile(r"^##\s*🔹?\s*盤[前後]速覽")


def _extract_premarket(md: str) -> tuple[str, str]:
    """抽出台股新聞的「## 🔹盤前速覽／盤後速覽」段（改置今日重點），回 (段落內文, 移除後全文)。
    （2026-07-19 踩坑：週末/盤後版標題是「盤後速覽」，只認盤前會讓今日重點整段空白。）
    無此段 → 回 ("", 原文)，今日重點不多出空卡。"""
    lines = (md or "").splitlines()
    s = next((i for i, l in enumerate(lines) if _PREMKT_HEAD.match(l.strip())), None)
    if s is None:
        return "", md or ""
    e = next((j for j in range(s + 1, len(lines))
              if lines[j].strip().startswith("## ") or lines[j].strip() == "---"), len(lines))
    body = "\n".join(lines[s + 1:e]).strip()
    rest = "\n".join(lines[:s] + lines[e:]).strip()
    return body, rest


def _premarket_card(pre_md: str, title: str = "盤前速覽") -> str:
    """今日重點內的市場速覽卡（盤前／盤後依報告模式）：台指期夜盤／ADR／費半／研判。"""
    if not pre_md:
        return ""
    sub = "昨夜外部訊號・開盤前參考" if title == "盤前速覽" else "收盤定稿與最新價格訊號"
    return (f'<div class="ngc premktc"><div class="ngt">{_ic("clock", plain=True)} {title} '
            f'<span class="stsub">{sub}</span></div>'
            f'<div class="ndoc premkt">{_md(pre_md)}</div></div>')


# ── ② 新聞（重點＋全文合併：逐則收合，標題列顯示一句話重點） ──────

def _news_badges(etype: str | None, importance: int | None) -> str:
    """新聞卡徽章：事件屬性（新事件/延伸/深度）＋重要度（依分數變色）。皆缺回空字串。"""
    out = ""
    if etype in ("new", "ext", "deep"):
        label = {"new": "新事件", "ext": "延伸", "deep": "深度"}[etype]
        out += f'<span class="netype {etype}">{label}</span>'
    if isinstance(importance, int):
        band = "hi" if importance >= 9 else ("mid" if importance >= 7 else "lo")
        out += f'<span class="nsev {band}">重要度 {importance}</span>'
    return f'<span class="nbadges">{out}</span>' if out else ""


_OVERVIEW_HEAD = re.compile(r"^#{2,3}\s*🔹?\s*.*總覽")


def _extract_overview(head_md: str) -> str:
    """從新聞頭段抽「…總覽」小節內文（供置頂可見卡）；無此節回空字串。"""
    lines = (head_md or "").splitlines()
    s = next((i for i, l in enumerate(lines) if _OVERVIEW_HEAD.match(l.strip())), None)
    if s is None:
        return ""
    e = next((j for j in range(s + 1, len(lines))
              if lines[j].strip().startswith("#") or lines[j].strip() == "---"), len(lines))
    # _md 不支援 blockquote：拆掉「> 」前綴讓引言（如【交易確認】）以一般段落呈現
    body = [re.sub(r"^\s*>\s?", "", l) for l in lines[s + 1:e]]
    return "\n".join(body).strip()


def _news_view(md: str, empty_hint: str,
               overview: tuple[str, str] | None = None) -> str:
    """單一新聞區：每則新聞一個 <details>（預設收合）。
    收合時標題列即顯示標題＋一句話重點（深咖啡）；展開顯示摘要＋影響分析＋原文連結。
    overview=(卡標題, 副標)：把頭段「…總覽」小節改為置頂可見卡（同盤前速覽卡版式）。
    頭尾其餘段（標題行／資料侷限／次級觀察／合規揭露）不上板——報告原檔仍保留全文，
    合規揭露統一置於頁尾小字（2026-07-15 使用者指示：拆掉混合收合塊）。"""
    head, cards, _tail = usnews.split_doc(md or "")
    if not cards and not (md or "").strip():
        return f'<div class="muted">{empty_hint}</div>'
    # 只留重要度 6 分以上（有標分者）；依重要度高→低排序（未標分者維持原序、殿後）
    cards = [c for c in cards
             if not (isinstance(c.get("importance"), int) and c["importance"] < 6)]
    cards = sorted(cards, key=lambda c: c.get("importance") or 0, reverse=True)
    items = []
    ov = _extract_overview(head) if overview else ""
    if ov:
        label, sub = overview
        items.append(f'<div class="ngc"><div class="ngt">{label} '
                     f'<span class="stsub">{sub}</span></div>'
                     f'<div class="ndoc premkt">{_md(ov)}</div></div>')
    for c in cards:
        badges = _news_badges(c.get("etype"), c.get("importance"))
        meta = f'<span class="nim">{_esc(c["meta"])}</span>' if c.get("meta") else ""
        one = f'<div class="nlone">{_esc(c["oneline"])}</div>' if c.get("oneline") else ""
        summ = f'<div class="ngs">{_inline(c["summary"])}</div>' if c.get("summary") else ""
        pts = "".join(f'<li><span class="klabel">{_esc(lab)}</span>{_inline(txt)}</li>'
                      for lab, txt in (c.get("points") or []))
        pts = f'<ul class="ngpts">{pts}</ul>' if pts else ""
        ordered = sorted(c.get("links") or [],             # 先排序再截 5（富途優先；審查 #7）
                         key=lambda tu: 0 if "futunn.com" in tu[1] else 1)[:5]
        links = "".join(f'<a class="nglink{" futu1" if "futunn.com" in u else ""}" '
                        f'href="{_esc(u)}" target="_blank" rel="noopener">↗ {_esc(t)}</a>'
                        for t, u in ordered)
        links = (f'<div class="nglinks">{links}</div>' if links else
                 '<div class="nglinks muted">（本則無原文連結）</div>')
        items.append(
            f'<details class="newsone"><summary>'
            f'<span class="nhead">{badges}<span class="nit">{_esc(c["title"])}</span>{one}{meta}</span>'
            f'<span class="openbtn2"></span></summary>'
            f'<div class="ndoc nibody">{summ}{pts}{links}</div></details>')
    if not cards and (md or "").strip():   # 版型異常（無卡）→ 整篇可見呈現當保底
        items.append(f'<div class="ndoc">{_md(md)}</div>')
    return "".join(items) or f'<div class="muted">{empty_hint}</div>'


# ── 總經：本週重點財經行事曆（美歐中日＋重要企業財報） ──────────────────────────────────

# 地區徽章的 CSS class 對照（美／歐／中／日；財報獨立子表不掛徽章）
_CAL_REGION_CLS = {"美": "us", "歐": "eu", "中": "cn", "日": "jp"}


def _cal_cons_cell(cons) -> str:
    """預期欄：值尾標『*』者＝市場共識預估（非官方），把 * 轉成橘色上標＋提示，
    其餘照原樣顯示；空值／— 顯示灰 —。"""
    s = str(cons or "").strip()
    if not s or s == "—":
        return '<span class="na">—</span>'
    if s.endswith("*"):
        base = s[:-1].strip()
        tip = "市場共識預估值（非官方，來源見該列說明），實際以官方公布為準"
        return f'{_esc(base)}<sup class="estmk" title="{_esc(tip)}">*</sup>'
    return _esc(s)


def _cal_rows_html(rows: list[dict], with_region: bool) -> str:
    """行事曆列 → <tr>…；with_region＝在項目前掛地區小徽章（財報子表免掛）。"""
    trs = []
    for r in rows:
        st = r.get("status") or ""
        cls = "done" if "已公布" in st else ("halt" if "休市" in st else "wait")
        badge = {"done": "✔ 已公布", "halt": "🔕 休市", "wait": "◷ 未公布"}[cls]
        av = r.get("actual") or ""
        actual = _esc(av) if av and av != "—" else '<span class="na">—</span>'
        reg = r.get("region") or ""
        reg_html = (f'<span class="creg {_CAL_REGION_CLS[reg]}">{_esc(reg)}</span>'
                    if with_region and reg in _CAL_REGION_CLS else "")
        trs.append(
            f'<tr class="cr-{cls}"><td class="cd">{_esc(r.get("date"))}</td>'
            f'<td class="ci">{reg_html}{_esc(r.get("item"))}</td>'
            f'<td>{_cal_cons_cell(r.get("cons"))}</td><td class="cav">{actual}</td>'
            f'<td class="cpv">{_esc(r.get("prev"))}</td>'
            f'<td><span class="cst {cls}">{badge}</span></td></tr>')
    return "".join(trs)


def _cal_table_html(rows: list[dict], with_region: bool) -> str:
    return (f'<div class="ovwrap"><table class="caltbl">'
            f'<thead><tr><th class="l">日期</th><th class="l">項目</th><th>預期</th>'
            f'<th>實際</th><th>前值</th><th>狀態</th></tr></thead>'
            f'<tbody>{_cal_rows_html(rows, with_region)}</tbody></table></div>')


def _macro_cal_view(cal: dict | None) -> str:
    """本週重點財經行事曆（美歐中日＋財報）：
    經濟數據表（地區以彩色小徽章標示）＋「重要財報／法說」獨立子表。"""
    if not cal or not cal.get("rows"):
        return ('<div class="muted">尚無本週行事曆。請由會上網查證的 Claude 依提示包'
                '產 <code>reports/macrocal/{date}.md</code>。</div>')
    note = cal.get("note") or ""
    note_html = ""
    if note:
        # 長句依「。／；」斷句分行成清單（不動文字、只加視覺分行），避免一整片難讀
        clauses = [c.strip() for c in re.findall(r"[^；。]+[；。]?", note) if c.strip()]
        if len(clauses) >= 3:
            def _cl(c: str) -> str:
                # 前導詞（重點／本週／更新…≤6 字＋「：」）→ 藍色小標，掃讀先看到框架；
                # 其餘走 _inline：**粗體** 得到與新聞卡一致的關鍵句半透明藍底標記
                m = re.match(r"^([^：]{1,6})：\s*(.*)$", c)
                if m:
                    return f'<span class="klabel">{_esc(m.group(1))}</span>{_inline(m.group(2))}'
                return _inline(c)
            lis = "".join(f"<li>{_cl(c)}</li>" for c in clauses)
            note_html = f'<div class="calnote"><ul class="cnlist">{lis}</ul></div>'
        else:
            note_html = f'<div class="calnote">{_ic("bell", plain=True)} {_inline(note)}</div>'
    data_rows = [r for r in cal["rows"] if r.get("region") != "財報"]
    earn_rows = [r for r in cal["rows"] if r.get("region") == "財報"]
    html = note_html + _cal_table_html(data_rows, with_region=True)
    if earn_rows:
        html += (f'<div class="calsub">{_ic("chart", plain=True)} 重要財報／法說</div>'
                 + _cal_table_html(earn_rows, with_region=False))
    if any(str(r.get("cons") or "").strip().endswith("*") for r in cal["rows"]):
        html += ('<div class="calfoot">預期欄標 <sup class="estmk">*</sup> 者為'
                 '<b>市場共識預估值</b>（取自 Trading Economics／Investing.com 等第三方彙整之'
                 '經濟學家共識，非官方數據）；未標星者為官方前瞻或已知初值，「—」為查無一致共識'
                 '或屬會議／談話等無預期值項目。實際數據一律以官方公布為準。</div>')
    return html


# ── ETF 數據追蹤（第四分頁：被動／主動台股 ETF 週績效表） ─────────

_ETF_COLS = [("close_px", "最新收盤價"), ("aum_e8", "規模(億)"), ("inception", "成立日期"),
             ("ret_1w", "過去一週報酬"), ("ret_1m", "過去一月報酬"),
             ("last_div", "最近一次配息金額"), ("yield_pct", "換算年化配息率"),
             ("freq", "收益分配頻率")]

# 報酬來源代碼 → 顯示名（代碼連結本身即 Yahoo，故 yahoo 併入連結不另標；其餘於代碼旁小標）
_RET_SRC_LABEL = {"stooq": "stooq", "finmind": "FinMind", "twse": "TWSE", "seed": "底稿"}


def _etf_sortv(k: str, i: dict):
    """排序用數值（data-v）：日期轉 YYYYMMDD、頻率轉月數；缺值回 None（沉底）。"""
    if k == "inception":
        m = re.match(r"(\d{4})/(\d{1,2})/(\d{1,2})", str(i.get("inception") or ""))
        return int(f"{m.group(1)}{int(m.group(2)):02d}{int(m.group(3)):02d}") if m else None
    if k == "freq":
        return {"月配": 1, "季配": 3, "半年配": 6, "年配": 12}.get(i.get("freq") or "")
    if k == "ret_src":
        return {"yahoo": 3, "finmind": 2, "twse": 1, "seed": 0}.get(i.get("ret_src") or "seed")
    return i.get(k)


def _fmt_num(v, digits: int = 2) -> str:
    """去尾零的數字顯示（配息 0.7200→0.72、收盤 24.50→24.5）；None→—。"""
    if v is None:
        return '<span class="na">—</span>'
    s = f"{v:.{digits}f}".rstrip("0").rstrip(".")
    return _esc(s or "0")


def _div_cell(i: dict) -> str:
    """最近一次配息欄：實際配息金額；若投信已公告當月『預計配息』，加註 X*（非正式）。"""
    ld = i.get("last_div")
    main = _fmt_num(ld, 4) if ld is not None else '<span class="na">—</span>'
    est = i.get("est_div")
    if est is not None:
        tip = "投信於配息月公告之預計配息金額，非正式配息金額（實際以除息公告為準）"
        main += (f'<div class="estdivln"><span class="estdiv" title="{tip}">預估 '
                 f'{_fmt_num(est, 4)}<sup>*</sup></span></div>')
    return main


def _ret_cell(i: dict, k: str) -> str:
    """報酬格：紅漲綠跌％＋下方小字標「基準日＠收盤價」，滑鼠移上顯示完整算式，方便人工驗證。

    ret_1w_base／ret_1m_base 由 arm/etfwatch 記錄（格式 'YYYY-MM-DD=收盤'）。"""
    v = i.get(k)
    span = _pct_span(v)
    base = i.get(f"{k}_base")
    if v is None or not base or "=" not in str(base):
        return span
    bd, bp = str(base).split("=", 1)
    last_d = i.get("perf_asof") or "最新"
    last_px = i.get("close_px")
    last_px_s = f"{last_px:g}" if isinstance(last_px, (int, float)) else "—"
    period = "近一週" if k == "ret_1w" else "近一月"
    dv = i.get(f"{k}_div")                       # 區間內加回的除息（總報酬口徑，arm/etfwatch 記錄）
    dv_tip = f"（含區間內除息 {dv:g} 加回）" if isinstance(dv, (int, float)) and dv else ""
    dv_note = f"＋息{dv:g}" if isinstance(dv, (int, float)) and dv else ""
    tip = f"{period}＝最新 {last_d} 收 {last_px_s}{dv_note} ÷ 基準 {bd} 收 {bp} − 1{dv_tip}"
    md = bd[5:].replace("-", "/") if len(bd) >= 10 else bd
    return (f'{span}<div class="rbase" title="{_esc(tip)}">起算 {_esc(md)} 收 {_esc(bp)}'
            f'{_esc(dv_note)}</div>')


def _etf_table(items: list[dict]) -> str:
    """單組 ETF 表（沿用 ovtbl 樣式與點欄排序）；復華自家檔整列高亮＋標章。"""
    trs = []
    for i in items:
        code = i.get("code")
        # 代碼可點 → Yahoo奇摩股市個股頁（可對照驗證）。報酬來源＝yahoo 時與此連結同源、不另標；
        # 其餘來源（stooq/FinMind/TWSE）於代碼旁掛小標，讓使用者知道報酬取自別處。
        vurl = f"https://tw.stock.yahoo.com/quote/{_esc(code)}"
        rsrc = i.get("ret_src") or "seed"
        srctag = (f'<span class="rsrc" title="過去一週／一月報酬取自此來源自算">'
                  f'{_esc(_RET_SRC_LABEL[rsrc])}</span>'
                  if rsrc in _RET_SRC_LABEL else "")
        # 產品名內「復華」以品牌色標示（不再用整列高亮／徽章）；代碼自成一行，避免名稱首字被擠上代碼列
        name_html = _esc(i.get("name") or "").replace("復華", '<span class="fh">復華</span>')
        tds = [f'<td class="nm"><span class="etcat">{_esc(i.get("cat") or "—")}</span></td>',
               f'<td class="nm"><a class="etcode" href="{vurl}" target="_blank" rel="noopener" '
               f'title="點開 Yahoo奇摩股市對照驗證"><b>{_esc(code)}</b></a>'
               f'<span class="etname">{name_html}{srctag}</span></td>']
        for k, _ in _ETF_COLS:
            v = _etf_sortv(k, i)
            if k in ("ret_1w", "ret_1m"):
                cell = _ret_cell(i, k)
            elif k == "aum_e8":
                cell = f"{v:,.2f}" if v is not None else '<span class="na">—</span>'
            elif k == "close_px":
                cell = _fmt_num(v, 2)
            elif k == "last_div":
                cell = _div_cell(i)
            elif k == "yield_pct":
                if v is None:
                    cell = '<span class="na" title="尚無配息紀錄，無法計算年化配息率">尚無配息</span>'
                elif i.get("yield_is_est"):
                    ed = _fmt_num(i.get("est_div"), 4)
                    tip = f"以本月預估配息 {ed} × 年配息次數 ÷ 最新收盤價換算（投信公告預估，非正式）"
                    cell = f'<span title="{_esc(tip)}">{v:.2f}%<sup class="estmk">*</sup></span>'
                else:
                    cell = f"{v:.2f}%"
            else:
                cell = _esc(i.get(k)) if i.get(k) else '<span class="na">—</span>'
            tds.append(f'<td data-v="{v if v is not None else ""}">{cell}</td>')
        trs.append(f'<tr>{"".join(tds)}</tr>')
    ths = "".join(f'<th class="sk" data-k="{k}" title="點擊排序">{lab}<span class="arr"></span></th>'
                  for k, lab in _ETF_COLS)
    return (f'<div class="ovwrap"><table class="ovtbl etftbl">'
            f'<thead><tr><th class="l">性質</th><th class="l">代碼／名稱</th>{ths}</tr></thead>'
            f'<tbody>{"".join(trs)}</tbody></table></div>')


def _etfwatch_view(doc: dict | None) -> str:
    """ETF 數據追蹤分頁：被動（高股息／市值型）與主動式兩張週績效表。"""
    if not doc or not doc.get("items"):
        return ('<div class="muted">尚無 ETF 追蹤資料。請執行 '
                '<code>python3 scripts/fetch_etf_watch.py</code> 後重產儀表板。</div>')
    items = doc["items"]
    passive = [i for i in items if i.get("kind") == "passive"]
    active = [i for i in items if i.get("kind") == "active"]
    other = [i for i in items if i.get("kind") == "other"]
    parts = []
    if passive:
        parts.append(f'<div class="ovg" id="etf-passive">{_ic("coin", plain=True)} 被動 ETF（高股息／市值型・{len(passive)} 檔）</div>'
                     + _etf_table(passive))
    if active:
        parts.append(f'<div class="ovg" id="etf-active">{_ic("zap", plain=True)} 主動式股票 ETF（{len(active)} 檔）</div>'
                     + _etf_table(active))
    if other:
        parts.append(f'<div class="ovg" id="etf-other">{_ic("coin", plain=True)} 其他（上櫃主動式股票／債券・{len(other)} 檔）</div>'
                     + _etf_table(other))
    has_est = any(i.get("est_div") is not None for i in items)
    est_note = ('　<b>最近一次配息金額</b>為最近一次「實際」除息之每單位配息金額；標 <b>預估 X*</b> 者為'
                '投信於配息月公告之<b>預計配息金額（非正式配息金額）</b>，實際以各投信除息公告為準。<br>'
                if has_est else
                '　<b>最近一次配息金額</b>為最近一次「實際」除息之每單位配息金額；當投信於配息月公告該月'
                '<b>預計配息金額</b>時，會於此欄加註「預估 X*」（非正式配息金額，實際以除息公告為準）。<br>')
    parts.append(
        '<div class="etfnote">'
        '<b>資料來源（可點擊人工驗證）</b>：'
        '規模／換算年化配息率 ← <a href="https://www.etfinfo.tw" target="_blank" rel="noopener">etfinfo.tw</a>'
        '（Tier B 第三方彙整）；'
        '過去一週／一月報酬 ← <a href="https://stooq.com" target="_blank" rel="noopener">stooq</a>／'
        '<a href="https://finance.yahoo.com" target="_blank" rel="noopener">Yahoo</a>／FinMind／'
        '<a href="https://www.twse.com.tw/zh/trading/historical/stock-day.html" target="_blank" '
        'rel="noopener">TWSE 官方</a>依序取乾淨日線自算（以最新交易日收盤對回推 7／30 日曆日前最後交易日計算；'
        '區間內有除息時把息加回──總報酬口徑，報酬格下方標「＋息」）；'
        '每列<b>代碼可點</b>開 <a href="https://tw.stock.yahoo.com/class/etf" target="_blank" '
        'rel="noopener">Yahoo奇摩股市</a>個股頁對照——報酬取自 Yahoo 即與此連結同源，取自其他源則於代碼旁小標；'
        '每格報酬下方「<b>起算 MM/DD 收 價格</b>」標明用哪一天的收盤當基準'
        '（滑鼠移上顯示完整算式），方便逐檔人工驗證。'
        '當月預估配息 ← 投信官方公告／<a href="https://mops.twse.com.tw" target="_blank" '
        'rel="noopener">MOPS 公開資訊觀測站</a>。<br>'
        f'　資料時間：規模／年化配息率抓取基準 {_esc(doc.get("as_of") or "—")}；'
        f'過去一週／一月報酬基準 {_esc(doc.get("perf_asof") or "—")}'
        '（成立日期為固定值；來源當日未更新時沿用最近可得值並標明基準日）・'
        f'抓取時間 {_esc(doc.get("fetched_at") or "—")}。<br>'
        + est_note +
        '　換算年化配息率＝配息金額 ÷ 最新市價 × 年配息次數；<b>標 * 者</b>改用「本月<b>預估</b>配息」換算'
        '（與投信/新聞公告口徑一致，非正式，實際以除息公告為準），其餘用最近一次「實際」配息換算；'
        '「尚無配息」＝新掛牌尚未除息、無配息紀錄可計算。'
        '正式對外請以各投信官網為準；僅為資訊彙編、非投資建議，過去績效不代表未來表現。</div>')
    return "".join(parts)


# ── ④ 基金總覽表 ─────────────────────────────────────────────

_OV_COLS = [("nav", "NAV", 0), ("chg", "日變動", 1), ("w1", "1週", 1), ("m1", "1月", 1),
            ("ytd", "YTD", 1), ("y1", "1年", 1), ("y3", "3年", 1), ("size_e8", "規模(億)", 0),
            ("conc", "前十大", 0), ("risk", "RR", 0)]


def _overview_view(rows: list[dict], marks: dict, pending: list[dict]) -> str:
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["group_label"], []).append(r)
    for p in pending:                        # 待抓取的基金也整組列出（值全為 —）
        groups.setdefault(p["group_label"], []).append(
            {"fund_id": p["fund_id"], "short_name": p["name"], "pending": True,
             "group_label": p["group_label"], "risk": "—",
             **{k: None for k, _, _ in _OV_COLS if k != "risk"}})
    ytd_note = ('<span class="lgnote">＊＝新成立基金，YTD 以發行價 10 元起算（＝成立以來報酬）</span>'
                if any(r.get("ytd_est") for r in rows) else "")
    blocks = [('<div class="ovleg">各組各欄標示：<span class="lgsw ld-up1">漲最多</span>'
               '<span class="lgsw ld-up0">漲最少</span><span class="lgsw ld-dn1">跌最多</span>'
               f'<span class="lgsw ld-dn0">跌最少</span>{ytd_note}</div>')]
    for g, rs in groups.items():
        trs = []
        for r in rs:
            fid = r["fund_id"]
            pend = ' <span class="pend">⏳ 待抓取</span>' if r.get("pending") else ""
            tds = [f'<td class="nm"><a href="#fund-{_esc(fid)}">{_esc(_short(r["short_name"]))}</a>{pend}</td>']
            for k, _, is_pct in _OV_COLS:
                if k == "risk":
                    v, cell = 0, _esc(r["risk"])
                else:
                    v = r.get(k)
                    if v is None:
                        cell = '<span class="na">—</span>'
                    elif is_pct:
                        # 短期欄（日變動/1週/1月）到小數第二位；長期欄（動輒數百%）一位即可
                        cell = _pct_span(v, 2 if k in ("chg", "w1", "m1") else 1)
                    else:
                        cell = f"{v:,.1f}" if k in ("size_e8", "conc") else _esc(v)
                        if k == "conc":
                            cell += "%"
                if k == "ytd" and r.get("ytd_est") and v is not None:
                    cell += ('<sup class="estmk" title="成立未滿一年：以發行價 10 元起算'
                             '之成立以來報酬率（＝當年度 YTD）">*</sup>')
                mk = marks.get((fid, k))
                lead = f' class="{mk}"' if mk else ""
                tds.append(f'<td data-v="{v if v is not None else ""}"{lead}>{cell}</td>')
            trs.append(f'<tr data-fund="{_esc(fid)}">{"".join(tds)}</tr>')
        ths = "".join(f'<th class="sk" data-k="{k}" title="點擊排序">{lab}<span class="arr"></span></th>'
                      for k, lab, _ in _OV_COLS)
        blocks.append(
            f'<div class="ovg">{_esc(g)}（{len(rs)} 檔）</div>'
            f'<div class="ovwrap"><table class="ovtbl"><thead><tr><th class="l">基金</th>{ths}</tr></thead>'
            f'<tbody>{"".join(trs)}</tbody></table></div>')
    if not blocks:
        blocks.append('<div class="muted">尚無基金資料。請先執行 '
                      '<code>python3 scripts/fetch_holdings.py</code>。</div>')
    return "".join(blocks)


# ── ⑤ 基金詳情 ───────────────────────────────────────────────

def _bars(items: list[dict], accent: str) -> str:
    if not items:
        return '<div class="muted">—（暫無資料）</div>'
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
        fu = fund_insights.futu_url(h.get("ticker"), h.get("country"))
        tk = (f' <a class="tk" href="{_esc(fu)}" target="_blank" rel="noopener" '
              f'title="富途牛牛即時行情">{_esc(h["ticker"])} ↗</a>' if fu else
              (f' <span class="tk">{_esc(h["ticker"])}</span>' if h.get("ticker") else ""))
        ct = f'<span class="pill">{_esc(h["country"])}</span>' if h.get("country") else ""
        intro = f'<div class="hintro">{_esc(h["intro"])}</div>' if h.get("intro") else ""
        hl = h.get("name") in linked_names
        link = ' <span class="hlk" title="今日新聞連動">🔗</span>' if hl else ""
        trcls = ' class="hl"' if hl else ""
        rows.append(
            f'<tr{trcls}><td class="rk">{i}</td>'
            f'<td class="nm"><b>{_esc(fund_insights.full_company_name(h.get("name")))}</b>{tk}{link} '
            f'<span class="sec">{_esc(h.get("sector"))}</span> {ct}{intro}</td>'
            f'<td class="wt">{(h.get("weight") or 0):.2f}%</td></tr>')
    return (f'<table class="htbl"><thead><tr><th></th>'
            f'<th class="l">標的（重點標的簡介）</th><th>投資比例</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


def _fund_card(doc: dict, gavg: dict, linked_names: set[str]) -> str:
    ret = doc.get("returns") or {}
    ga = gavg.get(doc.get("group_label") or "", {})
    inc_ret = fund_insights.inception_ret_pct(doc)   # 今年新成立且官網未揭露 → 發行價 10 元起算
    cells = []
    for k, lab in fund_insights.RET_KEYS + [("since", "成立以來")]:
        v = fund_insights.parse_period_pct(ret.get(k))
        est = ""
        if v is not None:
            disp = ret.get(k)
        elif inc_ret is not None and k in ("ytd", "since"):
            v, disp = inc_ret, f"{inc_ret:+.2f}%"
            est = ('<sup class="estmk" title="成立未滿一年：以發行價 10 元起算'
                   '之成立以來報酬率（＝當年度 YTD）">*</sup>')
        else:
            disp = "—"
        avg = ga.get(k)
        beat = ' <span class="beat" title="高於同組平均">●</span>' \
            if (v is not None and avg is not None and v > avg) else ""
        sub = f'<div class="ga">同組均 {avg:.1f}%</div>' if avg is not None else ""
        cells.append(f'<div class="rc"><div class="rk2">{lab}</div>'
                     f'<div class="rv">{_esc(disp)}{est}{beat}</div>{sub}</div>')
    size = doc.get("size_twd")
    size_s = f"{size / 1e8:.1f} 億元" if size else "—"
    mr = (f'<a class="mrpt" href="{_esc(doc["monthly_report"])}" target="_blank" rel="noopener">📄 基金月報</a>'
          if doc.get("monthly_report") else "")
    strat = doc.get("strategy") or ""
    chg = fund_insights.parse_pct(doc.get("nav_change_pct"))
    # 國內基金官網不提供國家配置——整段省略，避免留下懸空的「—」空區塊
    cty = doc.get("country_alloc") or []
    alloc_html = (
        f'<div class="ctitle">{_ic("globe", plain=True)} 國家配置</div>{_bars(cty, "var(--c1)")}'
        f'<div class="ctitle" style="margin-top:14px">{_ic("layers", plain=True)} 產業配置</div>'
        if cty else f'<div class="ctitle">{_ic("layers", plain=True)} 產業配置</div>')
    conc = fund_intro.top_concentration(doc)
    conc_s = f"{conc}%" if conc is not None else "—"
    # 經理人：官網 API manager＝經理人、manager01＝協管經理人（2026-07-22 經 MoneyDJ 經理人
    # 資料交叉驗證：美國新星 manager01 郭俊宏＝協管）。舊快照無 co_managers 鍵時照舊全列不標。
    man_s = "、".join((doc.get("managers") or [])
                     + [f"{c}（協管）" for c in (doc.get("co_managers") or [])]) or "—"
    return f"""
<details class="fund" id="fund-{_esc(doc.get('fund_id'))}" data-name="{_esc(doc.get('name'))}"
  data-group="{_esc(doc.get('group_label'))}">
  <summary class="fsum">
    <span class="fsum-l"><b>{_esc(doc.get('name'))}</b></span>
    <span class="gl">{_esc(doc.get('group_label'))}</span>
    <span class="fsum-r">NAV {_esc(doc.get('nav') if doc.get('nav') is not None else '—')}
      {_pct_span(chg, chip=True)}<span class="openbtn2"></span></span>
  </summary>
  <div class="fhead">
    <div>
      <div class="sub">{_esc(doc.get('category'))}｜主要區域 {_esc(doc.get('region') or '—')}｜
        風險 {_esc(doc.get('risk_level') or '—')}｜經理費 {_esc(doc.get('mgmt_fee') or '—')}｜
        經理人 {_esc(man_s)}</div>
      <div class="oneline">{_esc(fund_intro.summary_line(doc))}</div>
    </div>
    <div class="navbox">
      <div class="nav">{_esc(doc.get('nav') if doc.get('nav') is not None else '—')}</div>
      <div class="navd">NAV · {_esc(doc.get('nav_date') or '—')} {_pct_span(chg)}</div>
      <div class="size">規模 {size_s}　{mr}</div>
    </div>
  </div>
  {f'<div class="strat" title="點擊展開／收合">{_esc(strat)}</div>' if strat else ''}
  <div class="rets">{"".join(cells)}</div>
  <div class="cols">
    <div class="col">
      {alloc_html}{_bars(doc.get('sector_alloc') or [], 'var(--c2)')}
    </div>
    <div class="col">
      <div class="ctitle">{_ic("clipboard", plain=True)} 十大持有標的　<span class="asof">持股基準 {_esc(doc.get('as_of') or '—')}｜前十大合計 {_esc(conc_s)}</span></div>
      {_holdings_table(doc, linked_names)}
    </div>
  </div>
</details>"""


def _pending_card(p: dict) -> str:
    note = ("本基金為組合型（fund-of-funds），官網「十大持有標的」揭露結構不同；"
            if p["fund_id"] == "79" else "")
    return f"""
<details class="fund pendcard" id="fund-{_esc(p['fund_id'])}" data-name="{_esc(p['name'])}"
  data-group="{_esc(p['group_label'])}">
  <summary class="fsum">
    <span class="fsum-l"><b>{_esc(p['name'])}</b></span>
    <span class="gl">{_esc(p['group_label'])}</span>
    <span class="fsum-r"><span class="pend">數據待抓取</span><span class="openbtn2"></span></span>
  </summary>
  <div class="fhead"><div>
    <div class="sub">⏳ 已列入追蹤，數據待抓取——{note}
      請執行 <code>python3 scripts/fetch_holdings.py {_esc(p['fund_id'])}</code> 後重產儀表板。</div>
  </div></div>
</details>"""


def _details_block(funds: list[dict], gavg: dict, linked_by_fund: dict[str, set[str]],
                   pending: list[dict]) -> str:
    """基金詳情卡片群。"""
    cards = "".join(_fund_card(d, gavg, linked_by_fund.get(str(d.get("fund_id")), set()))
                    for d in funds)
    cards += "".join(_pending_card(p) for p in pending)
    return cards


# ── ⑥ 基金相關新聞・社群（讀 data/fund_news.json；無檔顯示提示不壞版） ──

def _fundnews_item(i: dict, tags: str = "") -> str:
    """單則新聞列：標題（可點）＋摘要（有才顯示）＋日期・來源・關聯基金標籤 meta 列。"""
    summ = f'<div class="fnsum">{_esc(i["summary"])}</div>' if i.get("summary") else ""
    return (f'<div class="fnit">'
            f'<a class="fnt" href="{_esc(i.get("url") or "#")}" target="_blank" rel="noopener">'
            f'{_esc(i.get("title"))}</a>{summ}'
            f'<div class="fnmeta"><span class="fnd">{_esc((i.get("date") or "")[:10])}</span>'
            f'<span class="fnsrc">{_esc(i.get("source") or "—")}</span>{tags}</div></div>')


def _fund_tag_label(base: str | None) -> str:
    """關聯基金標籤短名：去「復華」前綴與「基金」尾綴（標籤空間小、品牌名不必重複）。"""
    s = re.sub(r"^復華", "", (base or "").strip())
    return re.sub(r"基金$", "", s) or (base or "")


def _fundnews_view(doc: dict | None) -> str:
    if not doc:
        return ('<div class="muted">尚無基金新聞資料。請執行 '
                '<code>python3 scripts/fetch_fund_news.py</code> 後重產儀表板。</div>')
    win = doc.get("window_days") or 7
    parts = []

    hls = doc.get("highlights") or []
    if hls:
        parts.append(f'<div class="fnhl"><div class="fnhlt">{_ic("search", plain=True)} 本週看點</div><ul class="ngpts">'
                     + "".join(f'<li>{_esc(h)}</li>' for h in hls) + '</ul></div>')

    # 品牌動態＋各基金新聞合併為單一去重清單（2026-07-22 使用者指示：逐檔分卡太冗長——
    # 同稿在多檔基金卡重複出現、無新聞基金整串列名佔版面）。每則以標籤註記關聯：
    # 「投信動態」＝品牌層；基金短名標籤可點、跳該檔詳情卡。無專屬新聞的基金不再列出。
    entries: list[dict] = []
    index: dict[str, dict] = {}

    def _add(item: dict, tag: str) -> None:
        key = (item.get("title") or "")[:24]     # 同 fundnews.merge_news 的去重鍵
        if not key:
            return
        e = index.get(key)
        if e is None:
            e = {"item": item, "tags": []}
            index[key] = e
            entries.append(e)
        if tag and tag not in e["tags"]:
            e["tags"].append(tag)

    for i in doc.get("brand") or []:
        _add(i, '<span class="fntag fnbrand">投信動態</span>')
    for g in doc.get("funds") or []:
        fid = (g.get("fund_ids") or [""])[0]
        tag = (f'<a class="fntag" href="#fund-{_esc(fid)}" title="{_esc(g.get("base"))}">'
               f'{_esc(_fund_tag_label(g.get("base")))}</a>')
        for i in g.get("items") or []:
            _add(i, tag)
    entries.sort(key=lambda e: e["item"].get("datetime") or e["item"].get("date") or "",
                 reverse=True)

    parts.append(f'<div class="fng">{_ic("news", plain=True)} 基金新聞（近 {win} 天）</div>')
    if entries:
        parts.append('<div class="fnlist">' + "".join(
            _fundnews_item(e["item"], "".join(e["tags"])) for e in entries) + '</div>')
    else:
        parts.append(f'<div class="muted">近 {win} 天無相關新聞（或來源暫不可達）。</div>')

    soc = doc.get("social") or []
    parts.append(f'<div class="fng">{_ic("chat", plain=True)} 社群討論（PTT 股票板・依推文數）</div>')
    if soc:
        parts.append('<div class="fnlist">' + "".join(
            f'<div class="fnit fnsoc"><span class="fnpush">{int(s.get("push") or 0)} 推</span>'
            f'<div class="fnsocb"><a class="fnt" href="{_esc(s.get("url") or "#")}" '
            f'target="_blank" rel="noopener">{_esc(s.get("title"))}</a>'
            f'<div class="fnmeta"><span class="fnd">{_esc(s.get("date") or "")}</span>'
            f'<span class="fnsrc">PTT 股票板</span></div></div></div>'
            for s in soc) + '</div>')
    else:
        parts.append('<div class="muted">近期無相關討論（或來源暫不可達）。</div>')
    parts.append(f'<div class="fnfoot">來源：{_esc(doc.get("source") or "自動擷取")}・'
                 f'更新 {_esc(doc.get("as_of") or "—")}。公開標題彙編、教育用途，非投資建議。</div>')
    return "".join(parts)


# ── 樣式與腳本（非 f-string，避免大括號跳脫） ─────────────────

_CSS = """
/* 2026-07-22 富途式扁平版：整站單一白色平面、無卡片框，區塊靠細分隔線＋留白分層 */
:root{--bg:#ffffff;--card:#ffffff;--card2:#f4f6fa;--ink:#1f2733;--mut:#727e8c;
--line:#e8ebf1;--c1:#c05577;--c2:#c2740e;--gain:#d33a34;--loss:#1f9d57;--acc:#9c2447;
--accd:#7e1d3a;--ink2:#44505f;--inset:#eef2f8;--hl:#5c1229;--hlbg:#f7e3ea;--gold:#a16207;
--pad:#f7f9fc}
*{box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:var(--tbh,64px)}
body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.7 -apple-system,"PingFang TC","Noto Sans TC",Segoe UI,sans-serif}
/* 抓重點段落小標（新聞卡「對持股／族群影響」式標籤，全站統一） */
.klabel{display:inline-block;color:var(--accd);font-weight:700;letter-spacing:.02em;margin-right:8px}
a{color:var(--acc)} code{background:var(--inset);padding:1px 6px;border-radius:5px;color:var(--accd)}
.wrap{max-width:1240px;margin:0 auto;padding:10px 18px 60px}
/* 品牌漸層 Hero（瘦身版：識別保留、高度收斂，把空間留給內容） */
.hero{background:linear-gradient(120deg,#4a0f22 0%,#8a1f40 62%,#b4486e 100%);border-radius:14px;
  padding:15px 20px 13px;margin:8px 0 4px;color:#fff;position:relative;overflow:hidden}
.hero:before{content:"";position:absolute;right:-60px;top:-70px;width:230px;height:230px;border-radius:50%;
  background:radial-gradient(circle,rgba(255,255,255,.14),rgba(255,255,255,0) 70%)}
.hero:after{content:"";position:absolute;right:70px;bottom:-90px;width:180px;height:180px;border-radius:50%;
  background:radial-gradient(circle,rgba(224,171,66,.25),rgba(224,171,66,0) 72%)}
.hero-t{font-size:20px;font-weight:800;letter-spacing:.04em}
.hero-t b{color:#f4c15d;background:none;padding:0}
.hero-s{font-size:13px;color:rgba(255,255,255,.85);margin-top:3px;letter-spacing:.02em}
.hero-meta{display:flex;gap:6px;flex-wrap:wrap;margin-top:9px;position:relative;z-index:1}
.hero-chip{background:rgba(255,255,255,.14);border:0;border-radius:7px;
  padding:3px 10px;font-size:12px;color:#fff}
@media(max-width:640px){.hero{padding:12px 14px 11px}.hero-t{font-size:17.5px}.hero-s{display:none}}
/* SVG 圖標：區塊標題彩色圖標磚（雲學堂式模組色）＋行內 plain */
.ic{display:inline-flex;align-items:center;justify-content:center;width:29px;height:29px;
  border-radius:9px;background:rgba(156,36,71,.11);color:var(--accd);flex:0 0 auto}
.ic.t-amber{background:rgba(224,150,25,.15);color:#a16207}
.ic.t-green{background:rgba(22,163,74,.12);color:#15803d}
.ic.t-purple{background:rgba(124,58,237,.11);color:#6d28d9}
.ic.t-teal{background:rgba(13,148,136,.12);color:#0f766e}
.ic.t-navy{background:rgba(74,15,34,.12);color:#4a0f22}
.ic svg{width:15px;height:15px;stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.ic.plain{background:none;width:16px;height:16px;color:inherit;vertical-align:-2px}
.ic.plain svg{width:14px;height:14px}
/* 區塊不再是卡片：無框無陰影、全寬平鋪，區塊間以細分隔線＋留白分層（富途式） */
.section{background:none;border:0;border-radius:0;padding:24px 0 14px;margin:0;box-shadow:none;border-bottom:1px solid var(--line)}
.section>.st,.newswrap .st{font-weight:800;font-size:19px;margin-bottom:12px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.stsub{font-weight:400;font-size:13px;color:var(--mut)}
.muted{color:var(--mut)} .na{color:var(--mut)}
.gain{color:var(--gain);font-weight:700}.loss{color:var(--loss);font-weight:700}.flat{color:var(--mut)}
/* 市場雙視圖（純 CSS radio 切換——JS 被停用也能按） */
.mkradio{position:fixed;opacity:0;pointer-events:none}
#mkt-tw:checked ~ * .mkt[data-mkt="gl"]{display:none}
#mkt-gl:checked ~ * .mkt[data-mkt="tw"]{display:none}
/* 四分頁：總經／台股／全球／ETF——總經顯示 .macroview、ETF 顯示 .etfview、其餘顯示 .fundview */
#mkt-macro:checked ~ * .fundview,#mkt-etf:checked ~ * .fundview{display:none}
#mkt-tw:checked ~ * .macroview,#mkt-gl:checked ~ * .macroview,#mkt-etf:checked ~ * .macroview{display:none}
#mkt-macro:checked ~ * .etfview,#mkt-tw:checked ~ * .etfview,#mkt-gl:checked ~ * .etfview{display:none}
/* 導覽子項隨分頁切換：各分頁顯示各自專屬導覽 */
#mkt-macro:checked ~ .topbar .tb-nav-fund,#mkt-etf:checked ~ .topbar .tb-nav-fund{display:none}
#mkt-tw:checked ~ .topbar .tb-nav-macro,#mkt-gl:checked ~ .topbar .tb-nav-macro,#mkt-etf:checked ~ .topbar .tb-nav-macro{display:none}
#mkt-macro:checked ~ .topbar .tb-nav-etf,#mkt-tw:checked ~ .topbar .tb-nav-etf,#mkt-gl:checked ~ .topbar .tb-nav-etf{display:none}
/* 主分頁＝文字頁籤＋底線（富途式），去掉框與填色 */
.mkswitch{display:flex;gap:4px;border:0;background:none;border-radius:0;padding:0}
.mk{background:transparent;color:var(--mut);border:0;border-radius:0;padding:7px 10px 9px;cursor:pointer;font-size:16px;font-weight:800;user-select:none;transition:color .15s,box-shadow .15s}
.mk:hover{color:var(--accd)}
#mkt-macro:checked ~ .topbar .mk[for="mkt-macro"],
#mkt-tw:checked ~ .topbar .mk[for="mkt-tw"],
#mkt-gl:checked ~ .topbar .mk[for="mkt-gl"],
#mkt-etf:checked ~ .topbar .mk[for="mkt-etf"]{background:none;color:var(--ink);box-shadow:inset 0 -3px 0 var(--acc)}
/* ⓪ topbar */
.topbar{position:sticky;top:0;z-index:50;background:rgba(255,255,255,.95);backdrop-filter:blur(10px);border-bottom:1px solid var(--line);box-shadow:0 1px 8px rgba(20,50,100,.06)}
.tb-in{max-width:1240px;margin:0 auto;padding:9px 18px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.tb-brand{font-weight:800;font-size:16px;color:#0b4f9e;letter-spacing:.02em}
.tb-meta{color:var(--mut);font-size:11.5px}
.tb-lamp{font-size:11.5px;color:var(--mut);display:inline-flex;align-items:center;gap:5px}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block}
.dot.ok{background:#34c07c;box-shadow:0 0 5px rgba(52,192,124,.7)}
.dot.err{background:#e5534b}.dot.off{background:#8fa1bd}
.tb-nav{margin-left:auto;display:flex;gap:2px;flex-wrap:wrap}
.tb-nav a{color:var(--ink2);text-decoration:none;font-size:13.5px;padding:5px 9px;border-radius:0;background:none;border:0;transition:color .15s}
.tb-nav a:hover{color:var(--acc)}
/* ① brief */
.ixrow{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px}
.ixc{flex:1;min-width:150px;background:var(--card2);border:0;border-radius:10px;padding:10px 14px}
.ixl{font-size:12px;color:var(--mut)} .ixv{font-size:21px;font-weight:800;letter-spacing:.01em}
.ixp{font-size:13px}
.chips{display:flex;gap:8px;flex-wrap:wrap}
.chip{display:inline-flex;align-items:center;gap:6px;background:var(--card2);border:0;border-radius:8px;padding:6px 12px;font-size:14px;color:var(--ink);text-decoration:none}
.chip b{font-weight:700} .chip.hot{background:rgba(156,36,71,.12);color:var(--accd)}
.chip.dim{color:var(--mut)}
.chip.stale{border-color:#c62828;background:rgba(198,40,40,.08);color:#c62828;font-weight:700}
.st .chip.fresh{font-size:11.5px;padding:2px 10px;margin-left:4px;font-weight:400;vertical-align:middle}
.st .chip.fresh b{font-weight:600}
.stale-note{color:#c62828;font-weight:700}
.stale-banner{background:#c62828;color:#fff;text-align:center;padding:8px 14px;font-size:13.5px;font-weight:700}
a.chip{background:rgba(156,36,71,.08);color:var(--accd);cursor:pointer}
a.chip::after{content:"›";color:var(--acc);font-weight:800;font-size:16px}
a.chip:hover{background:rgba(156,36,71,.16)}
/* ①b 盤前速覽（今日重點內） */
.premktc{margin-top:12px}
.premkt{border:0;background:none;border-radius:0;padding:0;margin-top:6px;
  font-size:16px;line-height:1.85;color:var(--ink)}
.premkt ul{margin:4px 0} .premkt ul li{margin:9px 0}
/* ② news digest：輕色塊卡墊（2026-07-22 全站套用：取代細分隔線，好掃讀） */
.ngc{background:var(--pad);border:0;border-radius:12px;padding:13px 14px;margin:0 0 8px;border-bottom:0}
.ngc:last-child{margin-bottom:0}
.ngt{font-weight:700;font-size:17px;color:var(--ink);line-height:1.55}
.ngm{color:var(--mut);font-size:13px;margin-top:3px}
.ngs{font-size:17px;color:var(--ink);margin:6px 0 16px;line-height:1.9}
.ngpts{margin:8px 0 0;padding-left:0;list-style:none}
.ngpts li{position:relative;margin:6px 0;padding-left:16px;font-size:15px;color:var(--ink2);line-height:1.75}
.ngpts li:before{content:"";position:absolute;left:3px;top:12px;width:5px;height:5px;border-radius:50%;background:var(--acc)}
/* 新聞卡展開內文：影響分析每維度自成一段、標籤走 .klabel，段內粗體＝淺藍底關鍵句 */
.nibody .ngs{padding:2px 0 2px 13px;border-left:3px solid rgba(156,36,71,.4);font-weight:500}
.nibody .ngpts{margin-top:14px}
.nibody .ngpts li{margin:14px 0;padding:3px 0 3px 15px;font-size:16.5px;line-height:1.9;
  color:var(--ink);border-left:2px solid rgba(156,36,71,.22)}
.nibody .ngpts li:before{display:none}
.nglinks{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.nglink{display:inline-block;background:rgba(156,36,71,.08);border:0;border-radius:8px;padding:4px 12px;font-size:13.5px;color:var(--accd);text-decoration:none}
.nglink:hover{background:rgba(156,36,71,.16);color:var(--acc)}
.nglink.futu1{background:rgba(200,134,15,.1);color:var(--gold)}
.nglink.futu1:hover{color:#fff;background:var(--gold)}
/* ③ news links：同樣扁平化為清單項 */
.nlcard{background:none;border:0;border-radius:0;padding:12px 0;margin:0;border-bottom:1px solid var(--line)}
.nlcard:last-child{border-bottom:0}
.nlt{font-weight:700;font-size:16.5px;color:var(--ink)}
.nlone{display:table;font-size:16px;margin:6px 0 10px;color:var(--hl);background:var(--hlbg);font-weight:700;padding:1px 8px;border-radius:4px}
.nlrow{display:flex;gap:12px;align-items:baseline;flex-wrap:wrap;margin:6px 0;font-size:13.5px}
.nlco{font-weight:700;min-width:110px} .nlfs{color:var(--mut)}
.fw{color:var(--accd);font-size:14px;text-decoration:underline;text-underline-offset:3px;text-decoration-color:rgba(43,95,176,.45);margin-right:8px;white-space:nowrap}
.fw b{color:var(--ink)} .fw:hover{color:var(--acc);text-decoration-color:var(--acc)}
.futu{display:inline-block;font-size:12px;font-weight:700;color:var(--gold);background:rgba(200,134,15,.12);border:0;border-radius:8px;padding:2px 9px;margin-left:6px;text-decoration:none;vertical-align:1px}
.futu:hover{color:#fff;background:var(--gold)}
a.tk{text-decoration:underline;text-underline-offset:2px;text-decoration-color:rgba(43,95,176,.45)}
a.tk:hover{color:var(--acc)}
.talk{margin-top:10px;background:var(--inset);border:0;border-radius:9px;padding:9px 12px;font-size:14px;color:var(--ink2);line-height:1.7}
.talk.bad{color:var(--mut)}
.tlab{display:block;font-size:11.5px;color:var(--mut);margin-bottom:3px}
/* ④ overview */
.ovg{font-weight:700;font-size:13.5px;color:var(--accd);margin:14px 0 6px}
.ovwrap{overflow-x:auto;background:
  linear-gradient(90deg,var(--card) 33%,rgba(255,255,255,0)) left/36px 100%,
  linear-gradient(270deg,var(--card) 33%,rgba(255,255,255,0)) right/36px 100%,
  radial-gradient(farthest-side at 0 50%,rgba(40,60,100,.14),transparent) left/14px 100%,
  radial-gradient(farthest-side at 100% 50%,rgba(40,60,100,.14),transparent) right/14px 100%;
  background-repeat:no-repeat;background-attachment:local,local,scroll,scroll}
.ovtbl{width:100%;border-collapse:collapse;font-size:15px;font-variant-numeric:tabular-nums}
.ovtbl th{color:var(--mut);font-size:13px;font-weight:700;padding:7px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
.ovtbl th.l{text-align:left}
.ovtbl th.sk{cursor:pointer;user-select:none} .ovtbl th.sk:hover{color:var(--acc)}
.ovtbl th .arr{display:inline-block;width:16px;color:var(--acc)}
.ovtbl th .arr::after{content:"↑↓";opacity:.5;font-size:11px;letter-spacing:-2px}
.ovtbl th.sd .arr::after{content:"▼";opacity:1;letter-spacing:0} .ovtbl th.sa .arr::after{content:"▲";opacity:1;letter-spacing:0}
.ovtbl td{padding:8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
.ovtbl td.nm{text-align:left;font-weight:600}
.ovtbl td.nm a{color:var(--accd);font-size:14.5px;text-decoration:underline;text-underline-offset:3px;text-decoration-color:rgba(43,95,176,.45)}
.ovtbl td.nm a:hover{color:var(--acc);text-decoration-color:var(--acc)}
/* 總覽表極值標示（2026-07-22）：深紅=漲最多、淡紅=漲最少、深綠=跌最多、淡綠=跌最少
   （不綁 td——圖例 .lgsw 色塊共用同色票） */
.ld-up1{background:rgba(211,58,52,.22);border-radius:4px}
.ld-up0{background:rgba(211,58,52,.08);border-radius:4px}
.ld-dn1{background:rgba(31,157,87,.22);border-radius:4px}
.ld-dn0{background:rgba(31,157,87,.08);border-radius:4px}
.ovleg{display:flex;gap:6px;align-items:center;flex-wrap:wrap;font-size:12px;color:var(--mut);margin:0 0 8px}
.lgsw{padding:1px 8px;border-radius:5px;color:var(--ink2);white-space:nowrap}
.lgnote{margin-left:4px}
.ovtbl tr:hover td{background:rgba(156,36,71,.06)}
/* ETF 表：只凍結「代碼／名稱」一欄（識別欄），手機橫向捲動時恆可見；
   性質欄隨捲動移出（分兩張表已按性質分組，捲動時不需重複顯示），省空間好閱讀 */
.etftbl td:nth-child(2),.etftbl th:nth-child(2){position:sticky;left:0;z-index:2;background:var(--card);min-width:92px;max-width:128px;white-space:normal;box-shadow:1px 0 0 var(--line)}
.etftbl thead th:nth-child(2){z-index:3}
.etftbl .etcode{display:block}                 /* 代碼自成一行，名稱從下一行整段起，避免首字被擠上代碼列 */
.etftbl .etname{display:block;line-height:1.35} /* 名稱整段換行 */
.etftbl .fh{color:var(--gold);font-weight:800} /* 產品名內「復華」以品牌色標示 */
.pend{display:inline-block;font-size:11.5px;color:var(--gold);background:rgba(200,134,15,.12);border:0;border-radius:10px;padding:1px 7px;margin-left:6px;vertical-align:1px}
.pendhint{background:rgba(200,134,15,.1);border:0;border-radius:10px;padding:9px 13px;font-size:13.5px;color:#8a6a2e;margin-bottom:10px}
/* news full（收合） */
.newswrap summary{cursor:pointer;list-style:none}
.newswrap summary::-webkit-details-marker{display:none}
.newswrap summary:hover .openbtn{border-color:var(--acc);color:var(--acc)}
.openbtn{margin-left:auto;background:none;color:var(--accd);border:0;border-radius:0;padding:5px 0;font-size:13.5px;font-weight:700;white-space:nowrap}
.openbtn::after{content:"▼ 點擊展開全文"}
.newswrap[open] .openbtn::after{content:"▲ 收合"}
/* 逐則新聞收合塊：輕色塊卡墊（2026-07-22 全站套用：每則一個極淺灰圓角色塊） */
.newsone{background:var(--pad);border:0;border-radius:12px;margin:0 0 8px;overflow:visible;padding:0 14px}
.newsone:last-of-type{margin-bottom:0}
.newsone>summary{cursor:pointer;list-style:none;display:flex;align-items:flex-start;gap:12px;padding:14px 0}
.newsone>summary::-webkit-details-marker{display:none}
.newsone>summary:hover .nit{color:var(--accd)}
.newsone[open]>summary{padding-bottom:8px}
.nhead{display:flex;flex-direction:column;gap:4px;min-width:0}
.nit{font-weight:700;font-size:17.5px;color:var(--ink);line-height:1.55}
.nim{color:var(--mut);font-size:13px}
.nhead .nlone{margin:0}
.nbadges{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:1px}
.netype{font-size:11px;font-weight:700;padding:2px 8px;border-radius:5px;white-space:nowrap;border:0;letter-spacing:.03em}
.netype.new{color:var(--acc);background:rgba(156,36,71,.12);border-color:rgba(156,36,71,.4)}
.netype.ext{color:var(--mut);background:rgba(138,127,107,.12);border-color:rgba(138,127,107,.35)}
.netype.deep{color:#7b4fa0;background:rgba(123,79,160,.10);border-color:rgba(123,79,160,.4)}
.nsev{font-size:11px;font-weight:800;padding:2px 8px;border-radius:5px;white-space:nowrap;border:0;letter-spacing:.03em}
.nsev.hi{color:#fff;background:#c8760f;border-color:#c8760f}
.nsev.mid{color:#8a5410;background:rgba(200,118,15,.16);border-color:rgba(200,118,15,.5)}
.nsev.lo{color:var(--mut);background:rgba(138,127,107,.1);border-color:rgba(138,127,107,.3)}
.openbtn2{margin-left:auto;flex:0 0 auto;color:var(--accd);font-size:12.5px;font-weight:700;white-space:nowrap;padding-top:2px}
.openbtn2::after{content:"▼ 展開"}
.newsone[open] .openbtn2::after{content:"▲ 收合"}
.fund[open]>.fsum .openbtn2::after{content:"▲ 收合"}
.nibody{border:0;border-radius:0;margin:0;padding:0 0 18px}
.nibody>*:first-child{margin-top:8px}
.newsbar{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin:6px 0 2px}
.nswitch{display:flex;gap:2px}
/* 報別切換＝文字頁籤＋底線（同主分頁） */
.nb{background:none;color:var(--mut);border:0;border-radius:0;padding:7px 10px 9px;cursor:pointer;font-size:15px;font-weight:700}
.nb:hover{color:var(--accd)}
.nb.on{background:none;color:var(--ink);box-shadow:inset 0 -3px 0 var(--acc)}
.ndoc{background:none;border:0;border-radius:0;padding:0 0 16px;line-height:1.9;font-size:17px;color:var(--ink)}
.ndoc.hidden{display:none}
.ndoc>*:first-child{margin-top:14px}
.ndoc h2{font-size:14.5px;color:var(--mut);font-weight:600;letter-spacing:.02em;margin:30px 0 12px;padding-bottom:8px;border-bottom:1px solid var(--line)}
.ndoc h3{font-size:17.5px;color:var(--ink);font-weight:700;line-height:1.55;margin:26px 0 10px;padding:12px 16px;background:linear-gradient(90deg,rgba(156,36,71,.12),rgba(156,36,71,.02));border-left:3px solid var(--acc);border-radius:0 10px 10px 0}
.ndoc h4{font-size:14.5px;color:var(--accd);margin:18px 0 6px}
.ndoc p{margin:12px 0}
.ndoc ul,.ndoc ol{margin:12px 0;padding-left:0;list-style:none;counter-reset:n}
.ndoc ul li{position:relative;margin:10px 0;padding-left:20px}
.ndoc ul li:before{content:"";position:absolute;left:4px;top:12px;width:5px;height:5px;border-radius:50%;background:var(--acc)}
.ndoc ol li{position:relative;margin:14px 0;padding-left:36px;counter-increment:n}
.ndoc ol li:before{content:counter(n);position:absolute;left:0;top:2px;width:23px;height:23px;border-radius:50%;background:var(--acc);color:#fff;font-size:12px;font-weight:700;text-align:center;line-height:23px}
/* 關鍵句標記（粗體＋半透明藍底）——2026-07-18 使用者指示套用到所有內容區的重點 */
.ndoc b,.ngpts li b,.calnote b,.premkt b{color:var(--hl);background:rgba(156,36,71,.13);font-weight:700;padding:0 4px;border-radius:4px;box-decoration-break:clone;-webkit-box-decoration-break:clone}
.ndoc h2 b,.ndoc h3 b,.ndoc h4 b{color:inherit;background:none;padding:0}
.fnhl .ngpts li b{background:rgba(255,255,255,.8)}   /* 看點框本身是淺藍底——標記改半透明白保持對比 */
.ndoc a{text-decoration:none;border-bottom:1px dashed var(--acc);word-break:break-all}
.ndoc hr{border:0;border-top:1px solid var(--line);margin:22px 0}
.ndoc small,.ndoc i{color:var(--mut);font-style:normal}
.tag{display:inline-block;font-size:12px;font-weight:700;padding:1px 9px;border-radius:20px;background:rgba(156,36,71,.12);color:var(--accd);border:0;white-space:nowrap}
/* 總經：本週行事曆（去框 → 左側細條引導） */
.calnote{background:none;border:0;border-left:3px solid var(--acc);color:#1e3f6e;
  border-radius:0;padding:2px 0 2px 14px;font-size:15.5px;line-height:1.85;font-weight:500;margin-bottom:12px}
.calnote .cnlist{margin:0;padding:0;list-style:none}
.calnote .cnlist li{position:relative;padding-left:17px;margin:7px 0}
.calnote .cnlist li:before{content:"›";position:absolute;left:2px;top:-1px;color:var(--acc);font-weight:800}
.calnote .cnlist li:first-child{font-weight:700}
.caltbl{width:100%;border-collapse:collapse;font-size:15px;font-variant-numeric:tabular-nums}
.caltbl th{color:var(--mut);font-size:13px;font-weight:700;padding:7px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
.caltbl th.l{text-align:left}
.caltbl td{padding:8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap;vertical-align:top}
.caltbl td.cd{text-align:left;font-weight:700;white-space:nowrap} .caltbl td.ci{text-align:left;white-space:normal;min-width:150px}
.caltbl td.cav{font-weight:800;white-space:normal;min-width:120px} .caltbl td.cpv{color:var(--mut)}
.cr-done td.cav{color:var(--ink)} .cr-wait td{color:var(--ink2)} .cr-halt td{color:var(--mut)}
.cst{display:inline-block;font-size:11px;font-weight:700;padding:2px 8px;border-radius:6px;white-space:nowrap;border:0}
.cst.done{color:#1d6b3a;background:rgba(31,157,87,.14);border-color:rgba(31,157,87,.4)}
.cst.wait{color:var(--accd);background:rgba(156,36,71,.1);border-color:rgba(156,36,71,.35)}
.cst.halt{color:#8a5410;background:rgba(200,118,15,.14);border-color:rgba(200,118,15,.45)}
.creg{display:inline-block;font-size:10.5px;font-weight:800;padding:1px 6px;margin-right:6px;border-radius:5px;border:0;vertical-align:1px;white-space:nowrap}
.creg.us{color:#7e1d3a;background:rgba(156,36,71,.13);border-color:rgba(156,36,71,.4)}
.creg.eu{color:#5b3ea8;background:rgba(122,92,219,.14);border-color:rgba(122,92,219,.42)}
.creg.cn{color:#a02c2c;background:rgba(206,66,66,.13);border-color:rgba(206,66,66,.4)}
.creg.jp{color:#0f6f6b;background:rgba(23,146,140,.13);border-color:rgba(23,146,140,.42)}
.calsub{margin:16px 0 6px;font-size:14px;font-weight:800;color:var(--ink);padding-left:9px;border-left:4px solid #2f9d57}
.chip.halt{color:#8a5410;background:rgba(200,118,15,.12);border-color:rgba(200,118,15,.5);font-weight:700}
/* ETF 數據追蹤 */
.etcat{display:inline-block;white-space:nowrap;font-size:11px;color:var(--accd);border:0;background:rgba(156,36,71,.1);border-radius:5px;padding:1px 6px}
.etfnote{color:var(--mut);font-size:12.5px;margin-top:12px;line-height:1.8;border-top:1px solid var(--line);padding-top:8px}
.estdivln{margin-top:3px}                       /* 「預估 X*」另起一行，與實際配息金額分開更清楚 */
.estdiv{display:inline-block;font-size:11.5px;color:#8a5410;background:rgba(200,118,15,.14);border:0;border-radius:6px;padding:1px 6px;white-space:nowrap}
.estdiv sup{font-weight:800}
.estmk{color:#c8760f;font-weight:800;cursor:help}
.rbase{font-size:10.5px;color:var(--mut);font-weight:400;margin-top:2px;white-space:nowrap;cursor:help}
.rsrc{display:inline-block;font-size:10.5px;padding:1px 5px;margin-left:6px;border-radius:5px;border:0;
  color:var(--mut);background:rgba(138,127,107,.12);vertical-align:1px}
/* ⑤ details：基金卡去框 → 全寬清單項＋細分隔線 */
#details .st{margin-bottom:0}
.pendcard .sub{line-height:1.9}
/* 詳情卡輕色塊卡墊（2026-07-22 使用者指示：全平面細線列直式難掃讀 → 每檔一個極淺灰圓角色塊） */
.fund{background:var(--pad);border:0;border-radius:12px;padding:0 14px;margin:0 0 8px;box-shadow:none}
.fund:last-of-type{margin-bottom:0}
.fund:target{background:#f9ecf1}
.fund>*:not(summary){margin-left:0;margin-right:0}
.fund>*:last-child{padding-bottom:18px}
/* 詳情卡預設收合（2026-07-20 使用者指示）：summary 一行＝名稱＋NAV＋漲跌 */
.fsum{cursor:pointer;list-style:none;display:flex;justify-content:space-between;gap:12px;
  align-items:center;padding:14px 0;flex-wrap:wrap}
.fsum::-webkit-details-marker{display:none}
.fsum:hover .fsum-l b{color:var(--accd)}
.fund[open]>.fsum{border-bottom:1px dashed var(--line);margin-bottom:12px}
.fsum-l{flex:1 1 auto;min-width:0}
.fsum-l b{font-size:17px}
/* 排版邏輯：寬幕＝名稱佔左成長填滿、藍標＋NAV＋漲跌＋展開靠右一行；
   窄幕（手機直式）＝名稱獨佔首行，次行藍標靠左、NAV 組靠右（藍標不再懸在行中） */
.fsum>.gl{flex:0 0 auto}
.fsum-r{display:flex;gap:10px;align-items:center;font-size:14.5px;color:var(--ink2);
  white-space:nowrap;font-variant-numeric:tabular-nums;margin-left:auto}
.fsum-r .pend{color:var(--mut)}
.pchip{padding:2px 8px;border-radius:7px;font-size:13.5px}
.pchip.gain{background:rgba(211,58,52,.12)}
.pchip.loss{background:rgba(31,157,87,.12)}
@media(max-width:520px){
  .fsum{row-gap:6px}
  .fsum-l{flex:1 1 100%}
  .fsum>.gl{margin-right:auto}
}
.fund.fhide{display:none}
/* 詳情篩選列 */
.fundbar{display:flex;gap:9px;align-items:center;flex-wrap:wrap;margin-top:12px}
.fundbar #fsearch{flex:1;min-width:170px;max-width:330px;border:1px solid var(--line);border-radius:9px;
  padding:7px 12px;font-size:14.5px;background:var(--card2);color:var(--ink)}
.fundbar #fsearch:focus{outline:none;border-color:var(--acc)}
.fgchips{display:flex;gap:5px}
.fg,.fexp{background:var(--card2);color:var(--accd);border:0;border-radius:18px;
  padding:6px 13px;cursor:pointer;font-size:13.5px;font-weight:700}
.fg:hover,.fexp:hover{background:rgba(156,36,71,.12)}
.fg.on{background:var(--acc);color:#fff}
.fhead{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;align-items:flex-start}
.fhead h2{font-size:19px;margin:0 0 4px} .gl{display:inline-block;white-space:nowrap;font-size:12px;color:#fff;background:var(--acc);padding:2px 8px;border-radius:20px;vertical-align:middle}
.sub{color:var(--mut);font-size:12.5px} .oneline{margin-top:6px;font-size:13.5px;color:var(--accd)}
.navbox{text-align:right;min-width:190px} .nav{font-size:26px;font-weight:800}
.navd{font-size:12px;color:var(--mut)} .size{font-size:12px;color:var(--mut);margin-top:4px}
.mrpt{display:inline-block;margin-left:6px}
.strat{margin:12px 0 4px;color:var(--mut);font-size:13px;border-left:3px solid var(--line);padding-left:10px;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;cursor:pointer}
.strat.open{display:block;-webkit-line-clamp:unset}
.rets{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin:14px 0}
.rc{background:var(--card2);border:0;border-radius:9px;padding:8px;text-align:center}
.rk2{font-size:11px;color:var(--mut)} .rv{font-weight:700;font-size:14px}
.beat{color:var(--gain);font-size:9px;vertical-align:2px}
.ga{font-size:10.5px;color:var(--mut);margin-top:2px}
.cols{display:grid;grid-template-columns:1fr 1.25fr;gap:18px;margin-top:8px}
.ctitle{font-weight:700;font-size:14px;margin-bottom:8px} .asof{font-weight:400;font-size:11.5px;color:var(--mut)}
.barrow{display:flex;align-items:center;gap:8px;margin:5px 0;font-size:12.5px}
.blab{width:92px;flex:0 0 92px;color:var(--mut)} .btrack{flex:1;height:9px;background:var(--inset);border-radius:6px;overflow:hidden}
.bfill{display:block;height:100%} .bval{width:48px;text-align:right}
.htbl{width:100%;border-collapse:collapse} .htbl th{text-align:right;color:var(--mut);font-size:11.5px;font-weight:600;padding:4px 6px;border-bottom:1px solid var(--line);white-space:nowrap}
.htbl th.l{text-align:left} .htbl td{padding:7px 6px;border-bottom:1px solid var(--line);vertical-align:top}
.htbl .rk{color:var(--mut);width:22px} .htbl .wt{text-align:right;font-weight:700;white-space:nowrap}
.htbl .sec{display:inline-block;white-space:nowrap;font-size:11px;color:var(--mut);background:var(--card2);border:0;border-radius:5px;padding:1px 5px;margin-left:4px}
.htbl tr.hl td{background:rgba(224,138,18,.1)}
.hlk{text-decoration:none}
.tk{font-size:11px;color:var(--accd)} .pill{display:inline-block;white-space:nowrap;font-size:11px;color:var(--mut);background:var(--card2);border:0;border-radius:5px;padding:1px 5px;margin-left:4px}
.hintro{color:var(--mut);font-size:12.5px;margin-top:3px}
.foot{color:var(--mut);font-size:12.5px;line-height:1.8;margin-top:22px;border-top:1px solid var(--line);padding-top:12px}
.backtop{position:fixed;right:18px;bottom:18px;z-index:40;background:#fff;color:var(--accd);border:0;border-radius:22px;padding:9px 15px;font-size:13.5px;text-decoration:none;box-shadow:0 2px 10px rgba(30,50,90,.22)}
.backtop:hover{color:var(--acc)}
@media(max-width:720px){.wrap{padding:6px 14px 46px}.cols{grid-template-columns:1fr}.rets{grid-template-columns:repeat(3,1fr)}.navbox{text-align:left}
  .tb-meta,.tb-lamp{display:none}.ixc{min-width:110px}.section{padding:20px 0 12px}
  .tb-in{padding:7px 14px}.mk{padding:6px 8px 8px;font-size:15.5px}body{font-size:16.5px}
  #overview .st::after,#macro-cal .st::after,#etfwatch .st::after{content:"↔ 表格可左右滑動";font-weight:400;font-size:12px;color:var(--mut)}
  .backtop{right:10px;bottom:10px;padding:7px 12px;font-size:12.5px}}
/* ⑥ 基金相關新聞・社群 */
.fng{font-weight:700;font-size:14px;color:var(--accd);margin:18px 0 8px;padding-bottom:5px;border-bottom:1px solid var(--line)}
.fnhl{background:var(--hlbg);border:0;border-radius:10px;padding:11px 16px 13px;margin-bottom:4px}
.fnhlt{font-weight:800;font-size:15px;color:var(--hl)}
.fnhl .ngpts li{color:var(--ink);font-size:15px}
.fnhl .ngpts li:before{background:var(--gold)}
.fnlist{background:none;border:0;border-radius:0;padding:0}
.fnit{padding:10px 14px;background:var(--pad);border-radius:12px;margin-bottom:8px}
.fnit:last-child{margin-bottom:0}
.fnt{display:inline-block;color:var(--ink);font-size:15px;font-weight:600;line-height:1.55;text-decoration:none}
.fnt:hover{color:var(--acc);text-decoration:underline;text-underline-offset:3px}
.fnsum{color:var(--ink2);font-size:12.5px;line-height:1.7;margin-top:3px}
.fnmeta{margin-top:4px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.fnd{color:var(--mut);font-size:11.5px}
.fnsrc{display:inline-block;white-space:nowrap;font-size:11px;color:var(--mut);background:var(--card2);border:0;border-radius:5px;padding:1px 6px}
.fntag{display:inline-block;white-space:nowrap;font-size:11px;color:var(--accd);background:var(--hlbg);border:0;border-radius:5px;padding:1px 6px;text-decoration:none}
a.fntag:hover{color:var(--acc);text-decoration:underline;text-underline-offset:2px}
.fnbrand{color:var(--gold);background:rgba(200,134,15,.12)}
.fnsoc{display:flex;gap:12px;align-items:flex-start}
.fnsocb{min-width:0}
.fnpush{flex:0 0 48px;text-align:center;font-weight:800;font-size:12.5px;color:var(--gold);
  background:rgba(200,134,15,.12);border:1px solid rgba(200,134,15,.4);border-radius:8px;padding:3px 0;margin-top:2px;white-space:nowrap}
.fnfoot{color:var(--mut);font-size:12px;margin-top:14px;border-top:1px solid var(--line);padding-top:8px}
"""

_JS = r"""
// 台股/全球切換本體為純 CSS radio（JS 停用也能按）；JS 只負責記住選擇＋錨點自動切換
function curMkt(){for(const m of['macro','tw','gl','etf']){const r=document.getElementById('mkt-'+m);
  if(r&&r.checked)return m}return 'tw'}
function setMkt(m){document.getElementById('mkt-'+m).checked=true;
  try{localStorage.setItem('mkt',m)}catch(e){}}
document.querySelectorAll('.mkradio').forEach(r=>r.addEventListener('change',()=>{
  try{localStorage.setItem('mkt',curMkt())}catch(e){}}));
(function(){try{const m=localStorage.getItem('mkt');if(m)setMkt(m)}catch(e){}})();
// 錨點捲動精準化：sticky 頂欄在窄幕會折 2~3 行，固定 64px 偏移會蓋住目標——
// 量實際高度寫入 --tbh（載入/縮放/分頁切換都重算）
(function(){const tb=document.querySelector('.topbar');
  const sync=()=>document.documentElement.style.setProperty('--tbh',((tb?tb.offsetHeight:54)+10)+'px');
  sync();addEventListener('resize',sync);
  document.querySelectorAll('.mkradio').forEach(r=>r.addEventListener('change',()=>setTimeout(sync,60)));})();
// 詳情卡預設收合：從總覽/連結點過去（#fund-xx）→ 自動展開該卡（2026-07-20 使用者指示）
function openFund(id){const el=document.getElementById(id);
  if(el&&el.tagName==='DETAILS')el.open=true;return el}
document.querySelectorAll('a[href^="#"]').forEach(a=>a.addEventListener('click',()=>{
  const href=a.getAttribute('href');
  const el=href.startsWith('#fund-')?openFund(href.slice(1)):document.querySelector(href);
  const mv=el&&el.closest('.mkt');
  if(mv&&mv.dataset.mkt!==curMkt())setMkt(mv.dataset.mkt);
}));
if(location.hash.startsWith('#fund-'))openFund(location.hash.slice(1));
addEventListener('hashchange',()=>{if(location.hash.startsWith('#fund-'))openFund(location.hash.slice(1))});
// 詳情篩選列：名稱關鍵字＋類型 chips＋全部展開/收合
(function(){const q=document.getElementById('fsearch');if(!q)return;
  let g='';
  const apply=()=>{const kw=q.value.trim().toLowerCase();
    document.querySelectorAll('.fund').forEach(f=>{
      const okKw=!kw||(f.dataset.name||'').toLowerCase().includes(kw);
      const okG=!g||(f.dataset.group||'').includes(g);
      f.classList.toggle('fhide',!(okKw&&okG));});};
  q.addEventListener('input',apply);
  document.querySelectorAll('.fg').forEach(b=>b.onclick=()=>{
    document.querySelectorAll('.fg').forEach(x=>x.classList.remove('on'));
    b.classList.add('on');g=b.dataset.g||'';apply();});
  const exp=document.getElementById('fexp'),col=document.getElementById('fcol');
  if(exp)exp.onclick=()=>document.querySelectorAll('.fund:not(.fhide)').forEach(f=>f.open=true);
  if(col)col.onclick=()=>document.querySelectorAll('.fund').forEach(f=>f.open=false);})();
// 美股 v1/v2 版型切換
document.querySelectorAll('.nb').forEach(b=>b.onclick=()=>{
  document.querySelectorAll('.nb').forEach(x=>x.classList.remove('on'));b.classList.add('on');
  const v=b.dataset.nv;
  document.querySelectorAll('.ndoc[data-nv]').forEach(d=>d.classList.toggle('hidden',d.dataset.nv!==v));
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
// 投資策略兩行截斷 ↔ 展開
document.querySelectorAll('.strat').forEach(s=>s.onclick=()=>s.classList.toggle('open'));
// 儀表板逾期未重建警告——CI 全停擺時 HTML 不會再重生、上面的 ⚠ 也不會更新，
// 由瀏覽器端比對「產表時間 vs 現在」補上最後一道防線。
(function(){const g=document.querySelector('[data-gen]');if(!g)return;
  const d=new Date(g.dataset.gen.slice(0,10).replace(/\//g,'-')+'T00:00:00+08:00');
  const days=Math.floor((Date.now()-d)/864e5);
  if(days>2){const b=document.createElement('div');b.className='stale-banner';
    b.textContent='⚠ 本儀表板已 '+days+' 天未重建（每日 CI 可能停擺），以下資料可能過期——請跑「全部更新」或檢查 GitHub Actions';
    document.body.prepend(b);}})();
"""


# ── 組裝 ─────────────────────────────────────────────────────

def render() -> str:
    funds = fund_intro.all_funds()
    pending = fund_intro.pending_funds()
    tw_funds = [d for d in funds if _mof(d) == "tw"]
    gl_funds = [d for d in funds if _mof(d) == "gl"]
    tw_pend = [p for p in pending if str(p.get("group") or "").startswith("tw")]
    gl_pend = [p for p in pending if not str(p.get("group") or "").startswith("tw")]

    news = usnews.load_latest()
    tw = twnews.load_latest()
    macro = macronews.load_latest()
    cal = macronews.load_calendar()
    us_md = (news or {}).get("v1") or (news or {}).get("v2") or ""
    tw_md = (tw or {}).get("md") or ""
    macro_md = (macro or {}).get("md") or ""
    # 休市提示（取自行事曆引言，含「休市」才顯示；全球今日重點用精簡句、總經頁行事曆用完整引言）
    _hol_note = (cal or {}).get("note") or ""
    hol = ""
    if "休市" in _hol_note:
        _seg = next((p for p in re.split(r"[；;]", _hol_note) if "休市" in p), _hol_note)
        hol = re.sub(r"（[^）]*）", "", _seg).strip()      # 去括注、取含「休市」的短句

    def _sev(md: str) -> tuple[int, int]:
        """回 (重要度≥6 的新聞則數, 最高分)——供今日重點 chip。"""
        ss = [c["importance"] for c in usnews.extract_cards(md or "")
              if isinstance(c.get("importance"), int) and c["importance"] >= 6]
        return (len(ss), max(ss) if ss else 0)

    tw_links = fund_insights.news_fund_links(funds, tw_md)
    us_links = fund_insights.news_fund_links(funds, us_md)
    linked_tw = [c for c in tw_links if c["matched"]]
    linked_us = [c for c in us_links if c["matched"]]
    linked_by_fund: dict[str, set[str]] = {}  # fund_id → 連動持股名（詳情卡 🔗 標記用）
    for c in linked_tw + linked_us:
        for m in c["matched"]:
            for f in m["funds"]:
                linked_by_fund.setdefault(f["fund_id"], set()).add(m["name"])

    rows = fund_insights.overview_rows(funds)
    leaders = fund_insights.column_extremes(rows)
    mkt_by_id = {str(d.get("fund_id")): _mof(d) for d in funds}
    rows_tw = [r for r in rows if mkt_by_id.get(r["fund_id"]) == "tw"]
    rows_gl = [r for r in rows if mkt_by_id.get(r["fund_id"]) == "gl"]
    gavg = fund_insights.group_averages(funds)

    now = clock.now_tw().strftime("%Y/%m/%d %H:%M")      # 台北時間（UTC 容器防跨日錯置）
    as_of = (funds[0].get("as_of") if funds else None) or "—"
    banned = (((news or {}).get("banned_hits") or []) + ((tw or {}).get("banned_hits") or [])
              + ((macro or {}).get("banned_hits") or []))

    # ⓪b 資料更新時間（各資料來源鮮度一覽）
    nav_date = max((str(d.get("nav_date")) for d in funds if d.get("nav_date")), default=None)
    fetched_at = max((str(d.get("fetched_at")) for d in funds if d.get("fetched_at")), default=None)
    fn_doc = fundnews.load()
    # (標籤, 時戳, 容忍天數)：超過容忍天數標紅 ⚠。容忍值放寬到涵蓋週末與 T+1 海外 NAV，
    # 仍能抓到「CI 停擺／來源長期抓不到／新聞多日未補」的漏更新。
    # 最上方只標網頁更新時間；各來源時戳以 _fresh_chip 分散標於各自區塊標題列。
    hold_asof = as_of if as_of != "—" else None
    us_date, tw_date = (news or {}).get("date"), (tw or {}).get("date")
    mac_date, cal_date = (macro or {}).get("date"), (cal or {}).get("date")
    fn_asof = (fn_doc or {}).get("as_of")
    etf_doc = etfwatch.load()
    etf_asof = (etf_doc or {}).get("as_of")
    # 多期報酬（鉅亨每日基準）鮮度：CI 接上前為 None——不列警示、總覽區顯示過渡註記
    ret_asof = max((d.get("returns_daily_asof") or "" for d in funds), default="") or None
    sec_fresh = _freshness_view(now, [
        ("NAV 日", nav_date, 6), ("持股基準", hold_asof, 45), ("持股快照抓取", fetched_at, 3),
        ("美股新聞", us_date, 3), ("台股新聞", tw_date, 3),
        ("總經・政策", mac_date, 3), ("經濟行事曆", cal_date, 8),
        ("基金新聞・社群", fn_asof, 3), ("ETF 數據追蹤", etf_asof, 10),
    ] + ([("多期報酬(鉅亨)", ret_asof, 4)] if ret_asof else []))

    # ① 今日重點（雙視圖）；台股盤前速覽自新聞頭段抽出、直接顯示於此（不再埋於收合塊）
    premkt_md, tw_md_news = _extract_premarket(tw_md)
    pm_title = "盤後速覽" if re.search(r"^##\s*🔹?\s*盤後速覽", tw_md or "", re.M) else "盤前速覽"
    b_tw = _brief_view(twnews.extract_indices(tw_md), *fund_insights.movers(tw_funds),
                       fund_insights.upcoming_distributions(tw_funds))
    b_tw += _premarket_card(premkt_md, pm_title)
    # 全球今日重點不列任何指數點位/漲跌幅卡（公開搜尋之收盤數據不可靠；
    # 使用者指示 2026-07-04：全球重點不要出現數據漲跌幅——一律於下方新聞以官方為準呈現）
    b_gl = _brief_view([], *fund_insights.movers(gl_funds),
                       fund_insights.upcoming_distributions(gl_funds), hol)
    sec_brief = (f'<div class="section" id="brief"><div class="st">{_ic("zap", tone="amber")}今日重點 '
                 f'<span class="stsub">（{_esc((tw or news or {}).get("date") or "—")} 更新）</span></div>'
                 f'{_mkt(b_tw, b_gl)}</div>')

    # ② 新聞（重點＋全文合併，逐則收合）
    tw_hint = "尚無台股新聞。請執行 <code>python scripts/gen_twnews.py</code>。"
    gl_hint = "尚無昨夜美股新聞。請執行 <code>python scripts/gen_usnews.py</code>。"
    sec_news = (f'<div class="section" id="news"><div class="st">{_ic("news")}新聞 '
                f'{_fresh_chip("台股新聞", tw_date, 3)}{_fresh_chip("美股新聞", us_date, 3)} '
                f'<span class="stsub">點各則展開看摘要／影響分析／原文連結（預設收合）</span></div>'
                f'{_mkt(_news_view(tw_md_news, tw_hint), _news_view(us_md, gl_hint, (_ic("moon", plain=True) + " 昨夜美股總覽", "指數概況與市場解析・點位以官方為準")))}</div>')

    # 總經・政策分頁（川普政策／Fed／國際政策；左上「總經」分頁專屬視圖）
    mac_n, mac_top = _sev(macro_md)
    mac_sub = (f'川普政策／Fed／國際政策・今日 {mac_n} 則政策事件（最高 {mac_top} 分）'
               if mac_n else '川普政策／Fed／國際政策・點各則展開看影響分析')
    mac_hint = "尚無總經／政策新聞。請執行 <code>python scripts/gen_macronews.py</code>。"
    sec_macro_cal = (f'<div class="section" id="macro-cal"><div class="st">{_ic("calendar")}本週重點財經行事曆 '
                     f'{_fresh_chip("更新", cal_date, 8)} '
                     f'<span class="stsub">預期／已公布實際值／未公布・美股休市另標</span></div>'
                     f'{_macro_cal_view(cal)}</div>')
    # 政策總覽與政策新聞拆成兩獨立區塊（2026-07-15 使用者指示：比照台股/全球的
    # 「今日重點」與「新聞」）；總覽卡自新聞頭段抽出、新聞區只留逐則卡
    mac_head, _, _ = usnews.split_doc(macro_md or "")
    mac_ov = _extract_overview(mac_head)
    sec_macro_ov = (f'<div class="section" id="macro-ov"><div class="st">{_ic("clipboard", tone="purple")}政策總覽 '
                    f'{_fresh_chip("更新", mac_date, 3)} '
                    f'<span class="stsub">Fed／美政府／國際政策・前後 24 小時</span></div>'
                    f'<div class="ngc"><div class="ndoc premkt">{_md(mac_ov)}</div></div>'
                    f'</div>') if mac_ov else ""
    sec_macro = (f'<div class="section" id="macro"><div class="st">{_ic("landmark", tone="navy")}政策新聞 '
                 f'{_fresh_chip("更新", mac_date, 3)} '
                 f'<span class="stsub">{mac_sub}</span></div>'
                 f'{_news_view(macro_md, mac_hint)}</div>')

    # ETF 數據追蹤分頁（被動／主動台股 ETF 週績效表；左上「ETF」分頁專屬視圖）
    sec_etf = (f'<div class="section" id="etfwatch"><div class="st">{_ic("activity", tone="teal")}ETF 數據追蹤 '
               f'{_fresh_chip("資料基準", etf_asof, 10)} '
               f'<span class="stsub">台股被動（高股息／市值型）＋主動式 ETF・收盤／規模／成立／週月報酬／'
               f'最近一次配息金額／換算年化配息率／分配頻率・點欄位標題可排序</span></div>'
               f'{_etfwatch_view(etf_doc)}</div>')

    # ②b 基金相關新聞・社群（品牌＋各基金合併單一清單＋PTT 聲量；讀 data/fund_news.json）
    fn_sub = (f'近 {fn_doc.get("window_days") or 7} 天・Google News＋財經RSS＋PTT 自動擷取'
              if fn_doc else '基金新聞／PTT 聲量')
    sec_fnews = (f'<div class="section" id="fundnews"><div class="st">{_ic("megaphone", tone="purple")}基金相關新聞・社群 '
                 f'{_fresh_chip("更新", fn_asof, 3)} '
                 f'<span class="stsub">{_esc(fn_sub)}</span></div>'
                 f'{_fundnews_view(fn_doc)}</div>')

    # ③ 當日焦點個股區已移除（2026-07-15 使用者指示）；
    #    新聞連動資料仍餵基金詳情卡的持股 🔗 高亮（linked_by_fund）

    # ④ 基金總覽（多期報酬＝鉅亨每日基準優先；未接上前 ret_asof 為 None、不顯示 chip）
    ret_chip = _fresh_chip("多期報酬", ret_asof, 4) if ret_asof else ""
    ret_note = ("報酬欄＝鉅亨每日基準（缺值回退官網月底值）" if ret_asof else
                "多期報酬暫為官網月底基準（鉅亨每日覆蓋待 CI 接上）")
    o_tw = _overview_view(rows_tw, leaders, tw_pend)
    o_gl = _overview_view(rows_gl, leaders, gl_pend)
    sec_over = (f'<div class="section" id="overview"><div class="st">{_ic("chart", tone="green")}基金總覽 '
                f'{_fresh_chip("NAV 日", nav_date, 6)}{_fresh_chip("持股基準", hold_asof, 45)}'
                f'{_fresh_chip("快照抓取", fetched_at, 3)}{ret_chip} '
                f'<span class="stsub">色塊＝各組各欄漲跌極值（見下方圖例）・點欄位標題可排序・{ret_note}・'
                f'1週/1月＝往回滾動7/30日曆日（非月初起算，缺值以自建NAV序列自算，'
                f'1月自算須史料滿30天）</span></div>'
                f'{_mkt(o_tw, o_gl)}</div>')

    # ⑤ 基金詳情
    c_tw = _details_block(tw_funds, gavg, linked_by_fund, tw_pend)
    c_gl = _details_block(gl_funds, gavg, linked_by_fund, gl_pend)
    sec_det = (f'<div class="section" id="details"><div class="st">{_ic("book", tone="navy")}基金詳情 '
               f'{_fresh_chip("NAV 日", nav_date, 6)}{_fresh_chip("持股基準", hold_asof, 45)} '
               f'<span class="stsub">預設收合・點卡片展開；績效格「●」＝高於同組平均</span></div>'
               f'<div class="fundbar">{_ic("search", plain=True)}'
               f'<input id="fsearch" type="search" placeholder="輸入基金名稱關鍵字篩選…">'
               f'<span class="fgchips"><button class="fg on" data-g="">全部</button>'
               f'<button class="fg" data-g="股票">股票型</button>'
               f'<button class="fg" data-g="平衡">平衡型</button>'
               f'<button class="fg" data-g="組合">組合型</button></span>'
               f'<button class="fexp" id="fexp">全部展開</button>'
               f'<button class="fexp" id="fcol">全部收合</button></div></div>'
               f'{_mkt(c_tw, c_gl)}')

    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>復華基金雷達 · 台股/全球雙視圖</title>
<style>{_CSS}</style></head>
<body>
<input class="mkradio" type="radio" name="mkt" id="mkt-macro">
<input class="mkradio" type="radio" name="mkt" id="mkt-tw" checked>
<input class="mkradio" type="radio" name="mkt" id="mkt-gl">
<input class="mkradio" type="radio" name="mkt" id="mkt-etf">
{_topbar(banned, bool(news or tw or macro), as_of, now)}
<div class="wrap">
<div class="hero"><div class="hero-t">復華<b>基金雷達</b></div>
<div class="hero-s">每日晨間更新・基金淨值 × 市場新聞 × 總經政策 × ETF 追蹤</div>
<div class="hero-meta"><span class="hero-chip">產表 {now}</span><span class="hero-chip">持股基準 {as_of}</span></div></div>
{sec_fresh}
<div class="macroview">{sec_macro_cal}
{sec_macro_ov}
{sec_macro}</div>
<div class="etfview">{sec_etf}</div>
<div class="fundview">
{sec_brief}
{sec_news}
{sec_fnews}
{sec_over}
{sec_det}
</div>
<div class="foot">
  資料來源：復華投信官網（fhtrust.com.tw）基金淨值／持股揭露（月度）；新聞／政策／行事曆為公開來源彙編（出處連結見各則新聞卡），僅為市場資訊彙編／教育用途；重點標的簡介為中性事實敘述、非投資建議。<br>
  本資料僅供參考，非屬投資建議或招攬；本文所載資料多引自公開來源，本公司不保證其完整、即時或正確，亦不負損益責任。
  基金投資有風險，申購前應詳閱公開說明書／投資人須知；過去績效不代表未來表現，淨值可能因市場變動而上下。
  境外基金涉及匯率與國際市場風險；使用衍生性商品者另涉及槓桿、流動性與對手風險。
  投資人申購本基金係持有基金受益憑證，非本文提及之投資資產或標的。
  本版本不呈現「每天持股變化」（共同基金無逐日持股張數）。
</div>
</div>
<a class="backtop" href="#" onclick="window.scrollTo({{top:0,behavior:'smooth'}});return false;">↑ 回頂端</a>
<script>{_JS}</script>
</body></html>"""
