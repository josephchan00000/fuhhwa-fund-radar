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

import functools
import html
import json
import re
from datetime import date, timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

from . import (clock, etfdiscover, etfholdings, etfwatch, fund_insights, fund_intro, fundnews, twholidays,
               macrochips, macronews, treemap, twnews, usnews)


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


# ── 卡片欄位的「層次斷行」（2026-09-01 使用者：「不只是速覽，整個新聞卡也要套用」）──
# 純呈現層：不改一個字，只把欄內已經寫成層次的敘述斷成獨立行——實測當日卡片單句最長
# 146 字、每卡 5~10 句超過 60 字，整欄擠成一塊是「讀不下去」的主因之一。
# 只認**明確的列舉標記**（第N層／其N／①…）與句末的「後續觀察：」，句號一律不亂斷：
# 亂斷會把「甲公司。乙公司」這種連續敘述切碎，比不斷更難讀。
_LAYER_RE = re.compile(
    r"(?<=[。；;])\s*(?=(?:後續觀察|第[一二三四五六]層|其[一二三四五六][，、：:]|[①②③④⑤⑥]))")


def _lines(html_txt: str) -> str:
    """欄內文字（已是 inline HTML）→ 層次斷行；沒有列舉標記就原樣回傳。"""
    parts = [x for x in _LAYER_RE.split(html_txt) if x.strip()]
    if len(parts) < 2:
        return html_txt
    out = [parts[0]]
    for x in parts[1:]:
        cls = "nwatch" if x.startswith("後續觀察") else "nln"
        out.append(f'<div class="{cls}">{x}</div>')
    return "".join(out)


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


def _pct_span(v: float | None, digits: int = 2, chip: bool = False, unit: str = "%") -> str:
    """紅漲綠跌的漲跌幅（台灣慣例）。None → 灰 —。
    chip=True 時漲跌加淡底色塊（詳情卡摘要列用，掃讀落點）；持平／缺值維持純文字。
    unit＝顯示單位（ETF 持股貢獻用 'pp' 百分點，避免與 % 漲跌混淆）。"""
    if v is None:
        return '<span class="na">—</span>'
    cls = "gain" if v > 0 else ("loss" if v < 0 else "flat")
    if chip and cls != "flat":
        cls += " pchip"
    sign = "+" if v > 0 else ""
    return f'<span class="{cls}">{sign}{v:.{digits}f}{_esc(unit)}</span>'


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
    <button type="button" class="tb-print" id="pbtn" title="列印或另存 PDF——列印版只含五組重點：本週行事曆・市場數據・盤勢總覽・8分以上新聞（總經台股全球各至少一則）・基金ETF報酬率（A4 直式）">{_ic("printer", plain=True)}<span class="tb-pl">列印／PDF</span></button><button type="button" class="tb-print tb-pv" data-pv="1" title="在螢幕預覽列印版的版面（Esc 或「返回網頁版」關閉）">預覽</button>
    <nav class="tb-nav tb-nav-fund">
      <label class="sl" for="sec-brief">今日重點</label><label class="sl" for="sec-news">新聞</label>
      <label class="sl" for="sec-fnews">復華新聞</label>
      <label class="sl" for="sec-over">基金總覽</label>
      <label class="sl" for="sec-det">基金詳情</label>
    </nav>
    <nav class="tb-nav tb-nav-macro">
      <label class="sl" for="sec-mcal">本週行事曆</label><label class="sl" for="sec-mov">政策總覽</label><label class="sl" for="sec-mnews">政策新聞</label><label class="sl" for="sec-mdata">市場數據</label>
    </nav>
    <nav class="tb-nav tb-nav-etf">
      <label class="sl" for="sec-eup">即將登場</label><label class="sl" for="sec-ewatch">ETF 數據追蹤</label><label class="sl" for="sec-edet">ETF 持股詳情&amp;異動</label>
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


# ── 台股交易日（2026-09-28 誤報：9/25 中秋＋週末＋9/28 教師節，資料停在 9/24 是對的，
#    以日曆天計卻被判「ETF 持股揭露／多期報酬逾期」）──
# 休市日取自行事曆報告（每天由晨間 Routine 產出，週表列「台股休市」、市況段寫「台股 M/D 因〇〇休市」）
# ——重用既有事實、不另建假日表（同 check_afterhours_fresh.py）。行事曆沒寫到的休市日只會讓判定
# 偏嚴（多報一天逾期），不會漏報。
_MC_ROW = re.compile(r"^\|\s*(\d{1,2})/(\d{1,2})\s*\|([^|]*)\|", re.M)
_MC_MD = re.compile(r"(\d{1,2})/(\d{1,2})")


def _mc_date(y: int, fm: int, m: int, d: int):
    """行事曆內的 M/D 補年份（跨年：12 月檔提到 1 月＝明年、1 月檔提到 12 月＝去年）。"""
    yy = y + 1 if (fm == 12 and m == 1) else (y - 1 if (fm == 1 and m == 12) else y)
    try:
        return date(yy, m, d)
    except ValueError:
        return None


@functools.lru_cache(maxsize=1)
def _tw_closed_days() -> frozenset:
    """台股休市平日＝**證交所官方表**（arm/twholidays，2026-10-13 起）；官方表未涵蓋的年份才退回
    讀行事曆文字（子代理每天重寫的市況段，漏寫或誤寫都會讓交易日口徑的鮮度判定失準）。
    證交所隔年表公告前，人事行政總處辦公日曆的放假日（暫代層，一定休市）照樣計入，
    其餘仍由行事曆文字補。"""
    years = twholidays.load()
    official = set(twholidays.closed_days(years, with_provisional=True))
    out = set(official)
    for fp in sorted((ROOT_DIR / "reports" / "macrocal").glob("*.md"))[-90:]:
        fm_ = re.match(r"(\d{4})-(\d{2})-(\d{2})\.md$", fp.name)
        if not fm_:
            continue
        y, fm = int(fm_.group(1)), int(fm_.group(2))
        try:
            txt = fp.read_text(encoding="utf-8")
        except OSError:
            continue
        for m in _MC_ROW.finditer(txt):
            if "台股" in m.group(3) and "休市" in m.group(3):
                out.add(_mc_date(y, fm, int(m.group(1)), int(m.group(2))))
        # 市況段「台股 M/D 因〇〇休市」：只取寫明的日期——前一天的檔會預告隔天休市，
        # 不可把檔案日期本身當休市
        seg = re.search(r"市況：\s*台股\s*([^｜|；;]*)", txt)
        if seg and "休市" in seg.group(1):
            for md in _MC_MD.finditer(seg.group(1)):
                out.add(_mc_date(y, fm, int(md.group(1)), int(md.group(2))))
    out.discard(None)
    return frozenset(d for d in out if d in official or d.year not in years)


def _trade_age(value: str | None, today=None) -> int | None:
    """資料日之後到今天（含）經過幾個台股交易日——週末與行事曆載明的休市日不計。"""
    age = _age_days(value, today)
    if age is None:
        return None
    t = today or clock.today_tw()
    closed = _tw_closed_days()
    return sum(1 for i in range(age) if (x := t - timedelta(days=i)).weekday() < 5
               and x not in closed)


def _is_stale(value: str | None, tol: int | None, today=None, trading: bool = False) -> bool:
    """時戳超過容忍天數（或缺值）視為逾期；tol=None 永不逾期。
    trading=True：tol 以「台股交易日」計（跟著交易日產生的資料——NAV、持股揭露、報酬），
    否則以日曆天計（新聞、抓取時戳等每天都該動的）。"""
    if tol is None:
        return False
    age = _trade_age(value, today) if trading else _age_days(value, today)
    return age is None or age > tol


def _fresh_chip(label: str, value: str | None, tol: int | None = None,
                today=None, gen: bool = False, trading: bool = False) -> str:
    """單一鮮度徽章：逾期標紅 ⚠；gen=True 帶 data-gen 供瀏覽器端逾期偵測。"""
    stale = _is_stale(value, tol, today, trading)
    age = _trade_age(value, today) if trading else _age_days(value, today)
    unit = "個交易日" if trading else "天"
    warn = f"　⚠ {age} {unit}未更新" if (stale and age is not None) else ("　⚠ 缺資料" if stale else "")
    attr = f' data-gen="{_esc(value)}"' if (gen and value) else ""
    cls = " stale" if stale else ("" if value else " dim")
    return (f'<span class="chip fresh{cls}"{attr}><b>{_esc(label)}</b>　'
            f'{_esc(value or "—")}{_esc(warn)}</span>')


_FC_KIND = {"index_close": "加權指數收盤", "index_chg": "大盤漲跌點數",
            "inst_total": "三大法人合計買賣超", "inst_foreign": "外資及陸資買賣超",
            "tx_net": "外資台指期淨部位"}
_FC_UNIT = {"index_close": "點", "index_chg": "點", "inst_total": "億",
            "inst_foreign": "億", "tx_net": "口"}


def _fc_num(v) -> str:
    """核對值顯示：千分位、至多兩位小數並去尾零；非數值原樣輸出。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return _esc(str(v))
    s = f"{f:,.2f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


def _factcheck_chip(today=None) -> str:
    """數字核對狀態章（讀 data/factcheck.json；CI 端與官方 API 比對的結果）。
    🔴＝報告數字與官方不符（照常發佈但標紅警示、主會話會立即修正重推——
    2026-07-20 使用者指示：防線不可硬到什麼都沒更新）。無檔／**非今日**＝不顯示
    （2026-07-23 修：昨日殘留檔曾把過期 25 🔴 顯示在今日板上）。
    🔴 章可點展開明細（2026-08-07 使用者需求：「我要知道是哪個東西不符，讀的時候
    可以排除，但不要佔版面」）——收合時同一顆 chip 大小，點開列每筆
    「指標（日期）：報告值 → 官方值」，閱讀時以官方值為準。"""
    fp = ROOT_DIR / "data" / "factcheck.json"
    try:
        doc = json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return ""
    d = today or clock.today_tw()
    if doc.get("date") != f"{d:%Y-%m-%d}":
        return ""
    # 計數以 items 為準、表頭 green/red 只當沒有 items 時的後備：表頭是去正規化的
    # 冗餘欄位，跨 run 競態下曾與明細不一致（2026-07-28：兩個 daily.yml run 因
    # concurrency 依 event_name 分組而同時 commit，rebase 的三方文字合併把「表頭」
    # 與「items」湊成不同 run 的版本 → 明細 0 紅、表頭卻寫 red 2，儀表板掛出假警示章）。
    items = doc.get("items")
    if isinstance(items, list) and items:
        red = sum(1 for i in items if i.get("status") == "🔴")
        green = sum(1 for i in items if i.get("status") == "🟢")
    else:
        red, green = doc.get("red") or 0, doc.get("green") or 0
    if red:
        reds = [i for i in items if i.get("status") == "🔴"] if isinstance(items, list) else []
        rows = "".join(
            f'<div class="fcrow">{_esc(_FC_KIND.get(i.get("kind"), i.get("kind") or "—"))}'
            f'（{_esc(i.get("day") or "")}）：報告 {_fc_num(i.get("claimed"))} → '
            f'官方 <b>{_fc_num(i.get("official"))}</b> {_FC_UNIT.get(i.get("kind"), "")}</div>'
            for i in reds[:8] if i.get("claimed") is not None or i.get("official") is not None)
        more = (f'<div class="fcrow">…等共 {len(reds)} 項</div>' if len(reds) > 8 else "")
        head = (f'<b>數字核對</b>　🔴 {red} 項與官方不符'
                f'（{_esc(doc.get("as_of") or "")}核對，修正中）')
        if not rows:
            return f'<span class="chip fresh stale">{head}</span>'
        return (f'<details class="fcd"><summary>{head}</summary>'
                f'<div class="fcdl">{rows}{more}'
                f'<div class="fcnote">閱讀時請以官方值為準；報告端多為媒體初報值，'
                f'主會話核對後會自動修正重推。</div></div></details>')
    if green:
        return (f'<span class="chip fresh"><b>數字核對</b>　🟢 {green} 項與官方相符'
                f'（{_esc(doc.get("as_of") or "")}）</span>')
    return ""


def _intro_gap_chip() -> str:
    """持股簡介缺口警示章（讀 data/holdings_intro_gap.json；scripts/check_holdings_intro.py 產）。
    2026-07-23 使用者需求：前十大簡介一再漏掉——缺口>0 時在網頁更新時間列顯示紅色 ⚠，
    列出缺簡介的持股名，15:33 盤後班見到即 WebSearch 補進 holding_profiles.json。
    2026-10-21 起缺口檔也含 ETF 持股（items 的 src＝"etf"）；2026-10-24 起也含配置頁美股列的股票（src＝"usqm"）。
    全覆蓋（count=0）或無檔＝不顯示。"""
    fp = ROOT_DIR / "data" / "holdings_intro_gap.json"
    try:
        doc = json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return ""
    items = doc.get("items") or []
    if not items:
        return ""
    n_etf = sum(1 for i in items if i.get("src") == "etf")
    n_us = sum(1 for i in items if i.get("src") == "usqm")
    nz = [(n, t) for n, t in ((len(items) - n_etf - n_us, "基金前十大"), (n_etf, "ETF 持股"), (n_us, "美股三成")) if n]
    label = ("持股簡介" if n_etf or n_us else "前十大簡介")
    split = ("・".join(f"{t} {n}" for n, t in nz) + "；" if len(nz) > 1
             else (f"{nz[0][1]}；" if nz and nz[0][1] != "基金前十大" else ""))
    names = "、".join(_esc(i.get("name") or "") for i in items[:8])
    more = f" 等 {len(items)} 檔" if len(items) > 8 else ""
    return (f'<span class="chip fresh stale"><b>{label}</b>　🔴 {len(items)} 檔缺簡介'
            f'（{split}{names}{more}）</span>')


def _new_etf_chip() -> str:
    """漏網新 ETF 警示章（讀 data/etf_upcoming_gap.json；scripts/check_new_etfs.py 產）。

    2026-08-10 使用者：「你是怎麼確保之後都抓得到的呢？」——既有守門只認得「已登錄」
    的條目，從沒登錄過的檔不會讓任何測試變紅。此章由 CI 端的市場首見台帳／募集頁
    掃描產出。**警示分級（同日使用者：紅章 13 檔長名稱「很躁」）**：
      · 🔴 紅＝**已掛牌**卻沒登錄——真漏網，每日 SOP 立即補（附代碼，可直接查）；
      · ⚠ 琥珀＝募集頁上已核准／募集中、待登錄——**週一募集週掃自動查證補登**，
        只給檔數不列名稱清單（清單在 gap 檔，週掃讀得到；長名稱堆在版頭只是噪音）；
      · 申請中（審查未過）在資料層就進 pipeline 欄、不在 items——**不進本警示章**，
        但自 2026-08-28 起於「即將登場」區以「已送件・審查中」精簡列展示（純展示、
        不登錄不逼補，見 _applied_row）。
    無缺口／無檔＝不顯示。"""
    doc = etfdiscover.load_gap()
    items = doc.get("items") or []
    if not items:
        return ""
    listed = [i for i in items if i.get("kind") == "listed"]
    offering = [i for i in items if i.get("kind") != "listed"]
    parts = []
    if listed:
        names = "、".join(
            _esc(" ".join(x for x in (i.get("code"), i.get("name")) if x)) or "？"
            for i in listed[:6])
        more = f" 等 {len(listed)} 檔" if len(listed) > 6 else ""
        parts.append(f'<span class="chip fresh stale"><b>新 ETF 未登錄</b>　🔴 已掛牌 '
                     f'{len(listed)} 檔（{names}{more}）</span>')
    if offering:
        n_r = sum(1 for i in offering if i.get("stage") == "raising")
        n_a = sum(1 for i in offering if i.get("stage") == "approved")
        n_u = len(offering) - n_r - n_a
        bits = "・".join(b for b in (f"募集中 {n_r}" if n_r else "",
                                     f"已核准 {n_a}" if n_a else "",
                                     f"待查 {n_u}" if n_u else "") if b)
        parts.append(f'<span class="chip fresh warn"><b>新 ETF 待登錄</b>　⚠ {len(offering)} 檔'
                     f'（{bits}・週一募集週掃自動補）</span>')
    return " ".join(parts)


def _yt_watch_chip(today=None) -> str:
    """社群 YouTube 全空警示章（2026-08-07 使用者需求：「每次更新都順便查一下 YouTube」）。
    讀 data/fund_news.json：**今日的**檔、social 段存在、卻無任何 youtube 項＝抓取異常
    （金鑰沒帶到 CI env／API 失敗且 _carry_social 沿用款也耗盡）——三層清單
    （官方頻道＋相關搜尋＋同業熱門）正常日不會是 0。無檔／舊 schema 無 social 鍵／
    非今日檔皆不警（昨日檔＝鮮度問題，「逾期清單」自己會標，同 factcheck 章
    2026-07-23「非今日不顯示」教訓）。"""
    fp = ROOT_DIR / "data" / "fund_news.json"
    try:
        doc = json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return ""
    d = today or clock.today_tw()
    if "social" not in doc or not str(doc.get("as_of") or "").startswith(f"{d:%Y/%m/%d}"):
        return ""
    if any((s.get("platform") or "") == "youtube" for s in doc.get("social") or []):
        return ""
    return ('<span class="chip fresh stale"><b>社群 YouTube</b>　🔴 0 支'
            '（金鑰未帶到或抓取失敗——查 CI 日誌 [fundnews]）</span>')


def _afterhours_chip(today=None) -> str:
    """盤後當日完整性警示章（讀 data/afterhours_alert.json；check_afterhours_fresh.py 產）。
    2026-08-03 使用者踩坑：當日三大法人沒上線、無任何警示，自己打開網頁才發現——
    盤後看門狗把「時間到了該在而不在」的數據寫進警示檔，這裡標紅。
    非今日（昨日殘留檔，隔日早上 daily 會補齊資料）不顯示，同 factcheck 章的教訓。"""
    fp = ROOT_DIR / "data" / "afterhours_alert.json"
    try:
        doc = json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return ""
    d = today or clock.today_tw()
    if doc.get("date") != f"{d:%Y-%m-%d}" or not doc.get("missing"):
        return ""
    items = "、".join(_esc(x) for x in doc["missing"])
    return (f'<span class="chip fresh stale"><b>盤後更新</b>　🔴 未到：{items}'
            f'（CI 補抓中；遲逾 1 小時請查 GitHub Actions）</span>')


def _freshness_view(gen_stamp: str, sources: list[tuple[str, str | None, int | None]],
                    today=None) -> str:
    """最上方只標「網頁更新時間」；各來源時戳分散標於各自區塊標題列，這裡只彙總逾期警示。"""
    stale = [k for k, v, tol, *tr in sources if _is_stale(v, tol, today, bool(tr and tr[0]))]
    sub = (f'<span class="stale-note">⚠ {len(stale)} 項資料逾期未更新（{"、".join(stale)}），'
           f'請跑「全部更新」或檢查 CI</span>' if stale
           else "")
    return (f'<div class="section freshbar" id="freshness"><div class="st">{_ic("clock", plain=True)}網頁更新時間　'
            f'{_fresh_chip("網頁更新", gen_stamp, None, today, gen=True)} '
            f'{_factcheck_chip(today)} {_intro_gap_chip()} {_afterhours_chip(today)} '
            f'{_yt_watch_chip(today)} {_new_etf_chip()} '
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
        idx_cards = ""
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


# 市況（休市）chips：行事曆引言「市況：台股 …｜美股 …｜日股 …」段（arm/macronews.SPEC_CAL 固定格式）
_MKT_STAT_RE = re.compile(r"(台股|美股|日股|韓股|陸股|港股)\s*[：:]?\s*([^｜|；;。]+)")


def _market_status(note: str) -> tuple[str, str]:
    """行事曆引言 → (台股視圖休市句, 全球視圖休市句)。

    新格式（2026-07-22）：解析「市況」段——台股視圖只列「台股」本身
    （使用者指示：一樣的區塊、說這週台股有沒有休市）、全球視圖列
    美股＋日韓陸港（不能只有美股）。舊格式（無市況段）→ 沿用舊行為：
    取含「休市」短句（去括注），兩視圖同句。無休市資訊回 ("", "")、
    不出空 chip。"""
    seg = next((p for p in re.split(r"[；;]", note or "") if p.strip().startswith("市況")), "")
    if seg:
        pairs = {m: d.strip("，、 ") for m, d in _MKT_STAT_RE.findall(seg)}

        def _line(markets: tuple[str, ...]) -> str:
            got = [(m, pairs[m]) for m in markets if pairs.get(m)]
            closed = [f"{m} {d}" for m, d in got if "休市" in d]
            normal = [m for m, d in got if "休市" not in d]
            parts = ([ "、".join(closed)] if closed else []) + \
                    (["、".join(normal) + "正常交易"] if normal else [])
            if not parts:
                return ""
            txt = "本週" + "；".join(parts)
            return txt if closed else txt + "、無國定假日休市"   # 全正常時比照原美股句式

        return _line(("台股",)), _line(("美股", "日股", "韓股", "陸股", "港股"))
    if "休市" in (note or ""):
        _seg = next((p for p in re.split(r"[；;]", note) if "休市" in p), note)
        hol = re.sub(r"（[^）]*）", "", _seg).strip()
        return hol, hol
    return "", ""


def _extract_premarket(md: str) -> tuple[str, str]:
    """抽出台股新聞的「🔹盤前速覽／盤後速覽」段（改置今日重點），回 (段落內文, 移除後全文)。
    （2026-07-19 踩坑：週末/盤後版標題是「盤後速覽」，只認盤前會讓今日重點整段空白。）
    標籤行寫法交 usnews.find_section 統一認（## 標題／🔹**粗體行**／### 皆收——2026-08 有
    22 天子代理寫成「### 🔹盤前速覽」「🔹**盤前速覽**」，舊版只認 ## 而整張卡消失）。
    無此段 → 回 ("", 原文)，今日重點不多出空卡。"""
    sec = usnews.find_section(md or "", usnews.PREMKT_KEY)
    return (sec[1], sec[2]) if sec else ("", md or "")


def _premarket_title(md: str) -> str:
    """速覽卡標題跟著報告實際的段名走（盤前速覽／盤後速覽）。"""
    sec = usnews.find_section(md or "", usnews.PREMKT_KEY)
    return "盤後速覽" if sec and sec[0].startswith("盤後") else "盤前速覽"


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


def _extract_overview(head_md: str) -> str:
    """從新聞頭段抽「…總覽」小節內文（供置頂可見卡與列印版 ③）；無此節回空字串。
    標籤行寫法交 usnews.find_section 統一認——美股報 09-19 起寫成「🔹**…總覽**」整行粗體，
    舊版只認 ## 標題，螢幕版總覽卡與列印版全球欄因此空了三週（2026-10-13 使用者抓包）。"""
    sec = usnews.find_section(head_md or "", usnews.OVERVIEW_KEY)
    return sec[1] if sec else ""


_META_DUP = re.compile(r"[｜|]?\s*(?:【[^】]*】|重要度\s*\d{1,2}\s*/\s*10)\s*")


def _meta_clean(meta: str) -> str:
    """卡標題括注去掉【新事件／延伸／深度】與「重要度 N/10」——兩者已由徽章呈現，
    灰字只留來源＋日期（＋TST）。"""
    return _META_DUP.sub("", meta or "").strip(" ｜|，,")


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
    # 只留重要度 6 分以上（有標分者）；依重要度高→低排序（未標分者維持原序、殿後）。
    # 【深度】精選一律排在當日事件卡之後（同報告原檔的「深度報告精選」置於卡片群之後）——
    # 依分數混排會把深度文插在事件卡中間，讀起來像插隊（2026-08-16 使用者：順序很奇怪）。
    cards = [c for c in cards
             if not (isinstance(c.get("importance"), int) and c["importance"] < 6)]
    cards = sorted(cards, key=lambda c: (c.get("etype") == "deep",
                                         -(c.get("importance") or 0)))
    items = []
    ov = _extract_overview(head) if overview else ""
    if ov:
        label, sub = overview
        items.append(f'<div class="ngc"><div class="ngt">{label} '
                     f'<span class="stsub">{sub}</span></div>'
                     f'<div class="ndoc premkt">{_md(ov)}</div></div>')
    for c in cards:
        badges = _news_badges(c.get("etype"), c.get("importance"))
        mtxt = _meta_clean(c.get("meta") or "")
        meta = f'<span class="nim">{_esc(mtxt)}</span>' if mtxt else ""
        one = f'<div class="nlone">{_esc(c["oneline"])}</div>' if c.get("oneline") else ""
        summ = f'<div class="ngs">{_lines(_inline(c["summary"]))}</div>' if c.get("summary") else ""
        # 漲跌分析（2026-08-19 起每卡必填：實際漲跌幅＋大漲大跌歸因）；舊報告無此欄不顯示
        mv = (f'<div class="ngmv"><span class="mvtag">漲跌分析</span>{_lines(_inline(c["move"]))}</div>'
              if c.get("move") else "")
        # 【深度】精選的「為什麼值得讀」：2026-08-19 前寫在報告裡卻沒被解析、整行消失
        why = (f'<div class="ngwhy"><span class="whytag">為什麼值得讀</span>{_inline(c["why"])}</div>'
               if c.get("why") else "")
        pts = "".join(f'<li><span class="klabel">{_esc(lab)}</span>{_lines(_inline(txt))}</li>'
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
            f'<div class="ndoc nibody">{summ}{why}{mv}{pts}{links}</div></details>')
    if not cards and (md or "").strip():   # 版型異常（無卡）→ 整篇可見呈現當保底
        items.append(f'<div class="ndoc">{_md(md)}</div>')
    return "".join(items) or f'<div class="muted">{empty_hint}</div>'


# ── 總經：本週重點財經行事曆（美歐中日＋台股公司法說・財報＋海外財報） ──────────────────

# 地區徽章的 CSS class 對照（美／歐／中／日；台股與海外財報各自獨立子表、不掛徽章）
_CAL_REGION_CLS = {"美": "us", "歐": "eu", "中": "cn", "日": "jp"}


def _cal_hold_chip(item: str, held: dict | None) -> str:
    """台股列的「復華持股」章：項目內任一代碼在復華基金前十大／本家 ETF 前十大即掛，
    tooltip 列出各自的持有來源（macronews.tw_watch 同一份清單，與提示包必查清單一致）。"""
    if not held:
        return ""
    tips = []
    for c in macronews.tw_codes(item):
        r = held.get(c)
        if r:
            src = ([f"基金前十大 {r['funds']} 檔"] if r["funds"] else []) + r["etfs"]
            tips.append(f"{r['name']}（{c}）：{'、'.join(src)}")
    return (f'<span class="chold" title="{_esc("；".join(tips))}">復華持股</span>' if tips else "")


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


def _cal_rows_html(rows: list[dict], with_region: bool, held: dict | None = None) -> str:
    """行事曆列 → <tr>…；with_region＝在項目前掛地區小徽章（財報子表免掛）；
    held＝復華持股 {代碼: 清單列}（只有台股子表傳入，掛「復華持股」章）。"""
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
            f'<td class="ci">{reg_html}{_esc(r.get("item"))}{_cal_hold_chip(r.get("item"), held)}</td>'
            f'<td>{_cal_cons_cell(r.get("cons"))}</td><td class="cav">{actual}</td>'
            f'<td class="cpv">{_esc(r.get("prev"))}</td>'
            f'<td><span class="cst {cls}">{badge}</span></td></tr>')
    return "".join(trs)


def _cal_table_html(rows: list[dict], with_region: bool, held: dict | None = None) -> str:
    return (f'<div class="ovwrap"><table class="caltbl">'
            f'<thead><tr><th class="l">日期</th><th class="l">項目</th><th>預期</th>'
            f'<th>實際</th><th>前值</th><th>狀態</th></tr></thead>'
            f'<tbody>{_cal_rows_html(rows, with_region, held)}</tbody></table></div>')


def _macro_cal_view(cal: dict | None, held: dict | None = None) -> str:
    """本週重點財經行事曆：經濟數據表（美歐中日，地區以彩色小徽章標示）＋
    「台灣」子表（台：官方經濟數據＋台股：公司法說財報合一張，復華持股掛章）＋「海外財報／法說」子表。
    台灣資訊集中一處、不拆兩張（2026-10-13 使用者：「不要讓資訊過於複雜零散」）。"""
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
    data_rows = [r for r in cal["rows"] if r.get("region") not in ("財報",) + macronews.TW_REGIONS]
    tw_rows = [r for r in cal["rows"] if r.get("region") in macronews.TW_REGIONS]
    earn_rows = [r for r in cal["rows"] if r.get("region") == "財報"]
    html = note_html + _cal_table_html(data_rows, with_region=True)
    if tw_rows:
        n_held = sum(1 for r in tw_rows if _cal_hold_chip(r.get("item"), held))
        sub = f'<span class="stsub">{n_held} 項為復華持股</span>' if n_held else ""
        html += (f'<div class="calsub tw">{_ic("chart", plain=True)} 台灣：經濟數據・法說財報 {sub}</div>'
                 + _cal_table_html(tw_rows, with_region=False, held=held))
    if earn_rows:
        html += (f'<div class="calsub">{_ic("chart", plain=True)} 海外財報／法說</div>'
                 + _cal_table_html(earn_rows, with_region=False))
    if any(str(r.get("cons") or "").strip().endswith("*") for r in cal["rows"]):
        html += ('<div class="calfoot">預期欄標 <sup class="estmk">*</sup> 者為'
                 '<b>市場共識預估值</b>（取自 Trading Economics／Investing.com 等第三方彙整之'
                 '經濟學家共識，非官方數據）；未標星者為官方前瞻或已知初值，「—」為查無一致共識'
                 '或屬會議／談話等無預期值項目。實際數據一律以官方公布為準。</div>')
    return html


# ── 總經：市場溫度計（全球指標＋台股籌碼；讀 data/macro_chips.json） ──────────

# 列規格：(key, 顯示名, kind, 小數位, 單位)
#   kind：lvl＝水準值（日變化/近5日＝差值）；yield＝殖利率（日變化以 bp 顯示）；
#         flow＝當日流量（買賣超——「日變化」欄改列前一日值、「近5日」＝累計）；
#         lots＝口數水準值（負＝淨空單，另以「淨空/淨多」呈現）
_MD_GLOBAL_ROWS = [
    ("vix",    "VIX 恐慌指數",        "lvl",   2, " 點"),
    ("us10y",  "10年期美債殖利率",     "yield", 2, "%"),
    ("dxy",    "美元指數 DXY",        "lvl",   2, " 點"),
    ("usdtwd", "美元兌新台幣",        "lvl",   3, " 元"),
    ("brent",  "布蘭特原油",          "lvl",   2, " 美元/桶"),
    ("gold",   "黃金期貨",            "lvl",   0, " 美元/盎司"),
]
# 三大法人＝可展開群組：合計主列＋外資／投信／自營商分項子列（點名稱旁的 ▸ 展開）
_MD_INST_MAIN = ("inst_total", "三大法人買賣超", "flow", 1, " 億")
_MD_INST_SUBS = [
    ("inst_foreign", "外資及陸資", "flow", 1, " 億"),
    ("inst_trust",   "投信",       "flow", 1, " 億"),
    ("inst_dealer",  "自營商",     "flow", 1, " 億"),
]
_MD_TW_ROWS = [
    # 名稱標明「大台」＝口徑防混淆（2026-07-29 使用者回報數字對不上）：本列為臺股期貨 TX 單一契約，
    # 彙整站常見的「大台＋小台＋微台合計」會得出明顯較大的口數，兩者不可互相驗證。
    ("tx_foreign_net", "外資台指期淨部位（大台）", "lots", 0, " 口"),
    ("margin_bal",     "融資餘額",       "lvl",  1, " 億"),
    ("short_bal",      "融券餘額",       "lvl",  0, " 張"),
    ("pc_ratio",       "選擇權 P/C 比",   "lvl",  2, "%"),
]


def _spark(vals: list[float], w: int = 110, h: int = 26) -> str:
    """近 30 日走勢 sparkline（inline SVG、無外部依賴）；紅漲綠跌以期末對期初。
    點數 <2 不畫（回灰 —）；min==max（純平）畫中線。"""
    if len(vals) < 2:
        return '<span class="na">—</span>'
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    n = len(vals)
    pts = " ".join(f"{2 + i * (w - 4) / (n - 1):.1f},{h - 3 - (v - lo) * (h - 6) / rng:.1f}"
                   for i, v in enumerate(vals))
    cls = "gain" if vals[-1] >= vals[0] else "loss"
    return (f'<span class="spark {cls}" title="近 {n} 筆走勢（縮放至區間高低）：{vals[0]:g} → {vals[-1]:g}">'
            f'<svg viewBox="0 0 {w} {h}" aria-hidden="true">'
            f'<polyline points="{pts}" fill="none" stroke="currentColor" '
            f'stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/></svg></span>')


def _spark_bars(vals: list[float], w: int = 110, h: int = 26) -> str:
    """流量（買賣超）用長條迷你圖：以 0 為基準線，正值向上綠、負值向下紅——比折線更能
    如實呈現「哪天買超哪天賣超」，且單日爆量不會把整條線拉歪（2026-07-23 使用者反映折線怪）。"""
    if not vals:
        return '<span class="na">—</span>'
    mag = max((abs(v) for v in vals), default=0) or 1.0
    n = len(vals)
    bw = (w - 4) / n
    mid = h / 2
    bars = []
    for i, v in enumerate(vals):
        x = 2 + i * bw
        bh = abs(v) / mag * (h / 2 - 2)
        y = mid - bh if v >= 0 else mid
        cls = "up" if v >= 0 else "dn"
        bars.append(f'<rect class="{cls}" x="{x:.1f}" y="{y:.1f}" width="{max(bw - 1, 1):.1f}" height="{bh:.1f}"/>')
    return (f'<span class="spark bars" title="近 {n} 日買賣超（綠買超／紅賣超，0 為基準）">'
            f'<svg viewBox="0 0 {w} {h}" aria-hidden="true">'
            f'<line x1="2" y1="{mid}" x2="{w - 2}" y2="{mid}" class="base"/>{"".join(bars)}</svg></span>')


def _md_num(v: float, digits: int) -> str:
    return f"{v:,.{digits}f}"


def _md_delta(v: float | None, digits: int, unit: str = "", bp: bool = False) -> str:
    """差值欄：紅正綠負（台灣慣例）；yield 以 bp 呈現。None → 灰 —。"""
    if v is None:
        return '<span class="na">—</span>'
    if bp:
        v, digits, unit = v * 100, 1, " bp"
    cls = "gain" if v > 0 else ("loss" if v < 0 else "flat")
    sign = "+" if v > 0 else ""
    return f'<span class="{cls}">{sign}{_md_num(v, digits)}{_esc(unit)}</span>'


_MD_STALE_SESSIONS = 2      # 資料日落後超過 N 個交易日 → 視為過期、掛 ⚠ 章


def _trading_days_between(d_iso: str, today: date) -> int | None:
    """兩個日期間的平日數（粗略交易日，不扣國定假日——寧可少報過期，不誤掛警示）。"""
    try:
        d = date.fromisoformat(d_iso)
    except (ValueError, TypeError):
        return None
    n, cur = 0, d
    while cur < today:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            n += 1
    return n


def _md_stale_badge(d_iso: str, today: date | None = None) -> str:
    """資料日過期警示章。

    為什麼需要（2026-07-29 使用者回報「外資淨空單數字是錯的」的真正教訓）：
    合併鐵則「抓不到就保留舊序列」保護了資料不被洗空，但儀表板把最後一點當最新值渲染、
    沒有任何過期提示 —— 外資台指期淨部位自 7/23 起停更，卻連續 6 天以現值姿態上線，
    只有 CI 日誌一行「不可得」。這一章把靜默凍結變成看得見的紅字。"""
    n = _trading_days_between(d_iso, today or clock.today_tw())
    if n is None or n <= _MD_STALE_SESSIONS:
        return ""
    tip = (f"此指標官方資料日為 {d_iso}，已落後約 {n} 個交易日未更新"
           "（來源暫時抓不到時沿用最近可得值，不會以舊值假裝新值）")
    return f'<span class="mdstale" title="{_esc(tip)}">⚠ 過期</span>'


def _md_name_cell(key: str, label: str, *, caret: str | None = None, sub: bool = False,
                  datestr: str = "", stale: str = "") -> str:
    """指標名稱欄（2026-07-23 使用者：全部統一——名稱不粗體、每列都標「官方↗」來源連結）。
    每列＝純文字名稱（非粗體、非連結）＋下方小字「資料日 · ⚠過期 · 官方↗」；官方↗ 才是可點的來源連結。
    可展開主列（caret 且非 sub）：名稱包在大範圍展開鈕內（點名稱展開分項），仍非粗體。"""
    src = _MD_SRC.get(key)
    url = src[2] if src else None
    srclink = (f'<a class="mdslsm" href="{_safe_url(url)}" target="_blank" rel="noopener" '
               f'title="開官方揭露頁">官方↗</a>' if url else "")
    sep = "　" if (srclink and datestr) else ""
    # 2026-08-03 使用者：「也沒有數值日期」——日期其實一直都在，但只印「8/3」、
    # 又緊貼「官方↗」，看起來像連結的一部分。加「資料日」前綴讓它自我說明。
    dt_html = f'資料日 {_esc(datestr)}' if datestr else ""
    meta = (f'<span class="mddt">{dt_html}{stale}{sep}{srclink}</span>'
            if (datestr or srclink) else "")
    if caret and not sub:                             # ── 可展開主列：名稱＝展開鈕（非粗體）──
        btn = (f'<button type="button" class="mdtogbtn" data-grp="{_esc(caret)}" '
               f'aria-label="展開／收合外資投信自營商分項">'
               f'<span class="mdcaret" data-grp="{_esc(caret)}">▸</span>'
               f'<span class="mdgname">{_esc(label)}</span></button>')
        return f'<td class="l mdlab mdgrouplab">{btn}{meta}</td>'
    cls = "l mdlab" + (" mdsublab" if sub else "")    # ── 一般列／子列：純文字名稱 ──
    return f'<td class="{cls}"><span class="mdgname">{_esc(label)}</span>{meta}</td>'


def _md_row_html(mc: dict, key: str, label: str, kind: str, digits: int, unit: str,
                 *, caret: str | None = None, sub: bool = False) -> str:
    last = macrochips.latest(mc, key)
    if not last:
        if sub:                                     # 分項無資料：仍列出、值顯示 —（維持群組完整）
            return (f'<tr class="mdsub" data-grp="{_esc(caret or "")}">'
                    f'{_md_name_cell(key, label, sub=True)}'
                    f'<td class="mdval"><span class="na">—</span></td>'
                    f'<td class="mdchg"><span class="na">—</span></td>'
                    f'<td class="mdspark"><span class="na">—</span></td></tr>')
        return ""                                   # 主列無資料整列不列（不留空格）
    d, v = last
    # 最新值
    if kind == "lots":
        side = "淨空" if v < 0 else "淨多"
        val_html = f'<b>{side} {_md_num(abs(v), digits)}{_esc(unit)}</b>'
    elif kind == "flow":
        val_html = f"<b>{_md_delta(v, digits, unit)}</b>"    # 流量：當日買賣超本身紅買綠賣
    else:
        val_html = f"<b>{_md_num(v, digits)}{_esc(unit)}</b>"
    if key == "vix":
        lv = macrochips.vix_level(v)
        if lv:
            val_html += f' <span class="mdlv {lv[1]}">{lv[0]}</span>'
    # 日變化／前日、近5日／累計、走勢
    bp = kind == "yield"
    # 日變化／近5日欄不再重複帶單位（單位在「最新值」與表註；殖利率保留 bp）
    if kind == "flow":
        # 買賣超＝當日流量，與水準值語意不同 → 2026-08-03 使用者定案：**拆成獨立表**。
        # 流量表欄位＝「當日買賣超｜近5日累計｜走勢」——欄頭直接說清楚，儲存格不再堆標籤；
        # 「前日」值整個拿掉（走勢長條圖本來就看得到前幾天，並排只會跟當日值搶焦點——
        # 08/03 實例：當日 −165.2 旁邊擺著紅色的「前日 +873.1」，第一眼會誤讀成今天買超）。
        s5 = macrochips.sum_n(mc, key, 5)
        chg_html = _md_delta(s5, digits, "") if s5 is not None else '<span class="na">—</span>'
        spark = _spark_bars(macrochips.points(mc, key, 20))
    else:
        chg_html = _md_delta(macrochips.day_change(mc, key), digits, "", bp=bp)
        spark = _spark(macrochips.points(mc, key, 30))
    date_html = f"{int(d[5:7])}/{int(d[8:10])}" if len(d) == 10 else d
    stale = _md_stale_badge(d)
    tr_cls = ' class="mdsub" data-grp="' + _esc(caret) + '"' if sub else ""
    if kind == "flow":
        chg_cell = f'<td class="mdchg">{chg_html}</td>'          # 單值：近5日累計（欄頭已標明）
    else:
        n5_html = _md_delta(macrochips.change_n(mc, key, 5), digits, "", bp=bp)
        # 日變化與近5日併一欄（上下疊）以省寬、讓走勢圖在手機也進得了畫面
        chg_cell = f'<td class="mdchg">{chg_html}<span class="mdn5">{n5_html}</span></td>'
    return (f'<tr{tr_cls}>'
            f'{_md_name_cell(key, label, caret=(caret if not sub else None), sub=sub, datestr=date_html, stale=stale)}'
            f'<td class="mdval">{val_html}</td>{chg_cell}'
            f'<td class="mdspark">{spark}</td></tr>')


# 各指標官方來源可點連結（機構, 連結文字, 官方揭露頁 URL）；同機構同頁的指標共用一條連結（去重）
_MD_SRC = {
    "vix":            ("Yahoo Finance", "VIX",              "https://finance.yahoo.com/quote/%5EVIX"),
    "us10y":          ("Yahoo Finance", "美國 10 年期公債", "https://finance.yahoo.com/quote/%5ETNX"),
    "dxy":            ("Yahoo Finance", "美元指數 DXY",     "https://finance.yahoo.com/quote/DX-Y.NYB"),
    "usdtwd":         ("Yahoo Finance", "美元兌新台幣",     "https://finance.yahoo.com/quote/TWD=X"),
    "brent":          ("Yahoo Finance", "布蘭特原油",       "https://finance.yahoo.com/quote/BZ%3DF"),
    "gold":           ("Yahoo Finance", "黃金",             "https://finance.yahoo.com/quote/GC%3DF"),
    "inst_total":     ("證交所", "三大法人買賣金額(BFI82U)", "https://www.twse.com.tw/zh/trading/foreign/bfi82u.html"),
    "inst_foreign":   ("證交所", "三大法人買賣金額(BFI82U)", "https://www.twse.com.tw/zh/trading/foreign/bfi82u.html"),
    "inst_trust":     ("證交所", "三大法人買賣金額(BFI82U)", "https://www.twse.com.tw/zh/trading/foreign/bfi82u.html"),
    "inst_dealer":    ("證交所", "三大法人買賣金額(BFI82U)", "https://www.twse.com.tw/zh/trading/foreign/bfi82u.html"),
    "margin_bal":     ("證交所", "融資融券餘額(MI_MARGN)",   "https://www.twse.com.tw/zh/trading/margin/mi-margn.html"),
    "short_bal":      ("證交所", "融資融券餘額(MI_MARGN)",   "https://www.twse.com.tw/zh/trading/margin/mi-margn.html"),
    "tx_foreign_net": ("期交所", "三大法人-區分各契約",       "https://www.taifex.com.tw/cht/3/futContractsDate"),
    "pc_ratio":       ("期交所", "選擇權買賣權未平倉比",       "https://www.taifex.com.tw/cht/3/pcRatio"),
}


def _md_table(mc: dict, body_rows: str, flow: bool = False) -> str:
    """flow=True＝流量表（法人買賣超）：欄頭「當日買賣超｜近5日累計｜近20日走勢」；
    否則水準值表：「最新值｜日變化／近5日｜近30日走勢」。2026-08-03 使用者定案拆表，
    讓「近5日」在每張表內只有一種意思（流量＝累計、水準＝變化），欄頭即說明。"""
    if not body_rows:
        return '<div class="muted">（本組指標暫無資料——CI 接上官方來源後自動補齊）</div>'
    if flow:
        head = ('<th class="l">指標</th><th>當日買賣超</th>'
                '<th class="mdchg">近5日累計</th><th>近20日走勢</th>')
    else:
        head = ('<th class="l">指標</th><th>最新值</th>'
                '<th class="mdchg">日變化<span class="mdn5">／近5日</span></th>'
                '<th>近30日走勢</th>')
    return (f'<div class="ovwrap"><table class="ovtbl mdtbl">'
            f'<thead><tr>{head}</tr></thead>'
            f'<tbody>{body_rows}</tbody></table></div>')


def _md_inst_group_html(mc: dict) -> str:
    """三大法人＝合計主列（可點 ▸ 展開）＋外資／投信／自營商分項子列（預設收合）。"""
    main = _md_row_html(mc, *_MD_INST_MAIN, caret="inst")
    if not main:
        return ""                                    # 合計無資料 → 整組不列
    subs = "".join(_md_row_html(mc, *s, caret="inst", sub=True) for s in _MD_INST_SUBS)
    return main + subs


def _macro_data_view(mc: dict | None) -> str:
    """市場溫度計：全球指標（Yahoo 官方序列）＋台股籌碼（TWSE／期交所官方）。
    指標名稱本身＝可點的官方揭露頁連結；三大法人可展開外資／投信／自營商分項。"""
    if not mc or not any((mc.get("series") or {}).values()):
        return ('<div class="muted">尚無市場數據。正式區 CI 會執行 '
                '<code>scripts/fetch_macro_chips.py</code> 抓官方來源自動補齊。</div>')
    gl_body = "".join(_md_row_html(mc, *r) for r in _MD_GLOBAL_ROWS)
    flow_body = _md_inst_group_html(mc)
    lvl_body = "".join(_md_row_html(mc, *r) for r in _MD_TW_ROWS)
    html = (f'<div class="calsub">{_ic("globe", plain=True)} 全球市場溫度計</div>'
            + _md_table(mc, gl_body)
            + f'<div class="calsub">{_ic("layers", plain=True)} 台股籌碼——法人買賣超（當日流量）</div>'
            + _md_table(mc, flow_body, flow=True)
            + f'<div class="calsub">{_ic("layers", plain=True)} 台股籌碼——期貨・融資券・選擇權（水準值）</div>'
            + _md_table(mc, lvl_body))
    html += ('<div class="etfnote">'
             '各列點下方<b>「官方↗」</b>可開該指標官方揭露頁對照；<b>三大法人買賣超</b>列點整個名稱可展開外資／投信／自營商分項。'
             '<br>單位：VIX／美元指數 DXY＝指數點；殖利率＝%（日變化以 bp 計）；美元兌新台幣＝新台幣元；'
             '原油＝美元/桶；黃金＝美元/盎司；法人買賣超／融資餘額＝億元；融券＝張；台指期＝口。'
             '<br>欄位讀法：各列名稱下方小字為<b>資料日</b>（各指標公布時點不同，日期可能不一樣）。'
             '<b>法人買賣超表</b>＝當日流量：欄位為當日買賣超｜近5日累計（正＝買超、負＝賣超）。'
             '<b>水準值表</b>（期貨／融資券／選擇權與全球指標）：欄位為最新值｜日變化（與前一資料日的差）'
             '／近5日變化。'
             '<br>口徑：全球指標＝最近收盤（Yahoo Finance 官方序列）。台股籌碼＝證交所／期交所盤後官方數據；'
             '買賣超走勢為近 20 日長條（綠買超／紅賣超、0 為基準）；'
             '外資台指期淨部位為<b>臺股期貨(TX，大台) 單一契約</b>的未平倉多空淨額口數（淨空＝空單較多）——'
             '<b>不含小型／微型台指</b>，與部分彙整站的「大台＋小台＋微台合計」口徑不同、數字本就不會一致，'
             '請以本列標示的期交所官方揭露頁對照；P/C 比＝台指選擇權買賣權未平倉量比率。'
             '走勢折線縮放至各指標自身高低區間（看相對形狀、非絕對幅度）。紅＝上升／買超、綠＝下降／賣超（僅標方向非多空判斷）。'
             '資料日為官方數據所屬交易日；週末與休市日沿用最近交易日。</div>')
    return html


# ── ETF 數據追蹤（第四分頁：被動／主動台股 ETF 週績效表） ─────────

# 欄序（2026-07-29 使用者需求）：價格與績效欄靠左（每天在看的），
# 規模／成立日期屬「不常變的靜態資料」→ 移到最右。
_ETF_COLS = [("close_px", "最新收盤價"),
             ("chg_pct", "當日漲跌"),
             ("ret_1w", "過去一週報酬"),
             ("ret_1m", "過去一月報酬"),
             ("last_div", "最近一次配息金額"), ("yield_pct", "換算年化配息率"),
             ("freq", "收益分配頻率"),
             ("aum_e8", "規模(億)"), ("inception", "成立日期")]

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


def chg_trust(i: dict) -> tuple[str, str]:
    """當日漲跌可信度 →（狀態, 說明）。狀態＝ok／lag／bad。

    **為何要把「落後」和「日期不可能」分開（2026-09-21 使用者回報）**：首版防呆一律印
    `⚠ 基準 {日期}`，結果假 bar 那輪整張表 36 列都掛「⚠ 基準 **2026-09-20**」——那是**週日**。
    使用者的話：「週末當然沒有，你這樣不就全部都是錯誤了嗎」——完全正確：
    ①把一個不可能的日期當「基準」印給讀者，等於宣告系統把週日當交易日，
      產品看起來比顯示錯數字還糟；②讀者無從判斷這是「資料晚一天」還是「壞了」。
    · **lag（chg_asof < as_of）＝有意義**：數字確實是某個較早交易日的，印出那個日期
      讀者就知道「這格晚一天」，保留原本的 ⚠ 基準 章。
    · **bad（chg_asof > as_of，或落在週末）＝無意義**：來源給了未收盤或根本不存在的
      交易日，那個日期對讀者沒有任何資訊價值，只會製造「全表壞掉」的錯覺 →
      一律退成 `—`＋tooltip，**不印該日期**。
    （根因端的修法是 etfwatch._sane_series 濾掉假 bar＋L1／L2 自癒；這裡只管
      「萬一落檔仍帶髒值、又還沒成功重抓」時怎麼誠實呈現——重建型的 CI 班次
      不會重抓 etf_watch，那個時窗確實存在。）
    """
    ao, pa = i.get("as_of"), (i.get("chg_asof") or i.get("perf_asof"))
    if not (ao and pa):
        return "ok", ""                                  # 缺日期資訊 → fail-open 照顯示
    # 前一點不是前一個交易日＝兩天合計的漲跌（2026-10-21：Yahoo 下午「有今天、少昨天」，0050 顯示 −0.0%、
    # 官方 +0.84%）。日期看起來對，最容易誤導——只重建、不重抓的班次也不可把落檔裡的這種值顯示出來。
    pd_ = i.get("prev_date")
    if pd_ and i.get("chg_asof"):
        from . import dayquotes
        try:
            want = dayquotes.prev_trading_day(date.fromisoformat(str(i["chg_asof"])[:10])).isoformat()
        except (TypeError, ValueError):
            want = None
        if want and str(pd_)[:10] != want:
            return "bad", (f"這格是 {str(pd_)[:10]} 到 {str(i['chg_asof'])[:10]} 的漲跌（中間少了 {want}），"
                           f"不是當日漲跌，暫不顯示；下一次更新會重算")
    # 除息日沒扣配息＝把配息算成跌幅（2026-10-21 00986D：−0.77%，對除息參考價是 −0.14%）。
    # etfinfo 的 last_div_date 就是除息日（7/22 起 67 次除息與 Yahoo 事件日期、金額全同）。
    ca = str(i.get("chg_asof") or "")[:10]
    if ca and i.get("last_div") and str(i.get("last_div_date") or "")[:10] == ca and not i.get("chg_ex_div"):
        return "bad", (f"{ca} 除息（每單位 {i['last_div']:g} 元），這格的漲跌沒有扣配息，"
                       f"暫不顯示；下一次更新會重算")
    if pa == ao:
        return "ok", ""
    try:
        wknd = date.fromisoformat(str(pa)[:10]).weekday() >= 5
    except (TypeError, ValueError):
        wknd = True                                      # 日期解析不了＝髒值，當 bad
    if pa > ao or wknd:
        return "bad", (f"來源回報的漲跌日 {pa} 不是可用的收盤交易日"
                       f"（{'週末' if wknd else '比收盤價 ' + str(ao) + ' 還新、當日尚未收盤'}），"
                       f"暫不顯示以免誤導；來源補上 {ao} 的日線後自動恢復")
    return "lag", (f"報酬序列最新只到 {pa}，收盤價已是 {ao}——當日漲跌需兩者同日才算得準，"
                   f"暫不顯示以免與收盤價差一天（來源補上 {ao} 的日線後自動恢復）")


def _chg_cell(i: dict) -> str:
    """當日漲跌格：只顯示紅漲綠跌 ±%（2026-07-30 使用者：底下灰字看不懂，都刪掉）。

    漲跌額／前收／除息細節全部收進 tooltip 供查證——不再另起一行：
    ①灰字行與「最新收盤價」欄並排時，close_px（etfinfo 時點）與序列前收可能對不上
    （實例：0056 顯示收 48.19、前收 48.19 卻 -4.11%），視覺上必然矛盾；
    ②除息日仍以「除息參考價＝前收 − 每單位配息」為基準（2026-07-22 總報酬坑），
    只是說明改進 tooltip。"""
    v = i.get("chg_pct")
    if v is None:
        return _pct_span(v)
    # ── 序列落後 → 不以舊漲跌冒充「當日」（2026-09-03 使用者回報「當日漲跌是不是沒更新」）──
    # 當日漲跌取自報酬序列末兩點（perf_asof＝序列末日），收盤價卻走 etfinfo 市價（as_of）：
    # 兩條線不同源。序列缺當日 bar 時末兩點會退成「前一交易日 vs 再前一日」，與同列的收盤價
    # 差一天並排，而且方向可能完全相反——2026-09-02 實例：0050 收 106.80（9/2、台股當天大跌），
    # 表上卻顯示 +2.07%，那是 9/1 相對 8/31 的漲幅，9/2 實為約 -1.5%。當時全表 31 檔皆如此，
    # 而 gen 端「算不出就保留既有值」與 CI 完整性斷言都不覆蓋此型，是完全靜默的錯位。
    # 寧缺勿錯：不顯示會誤導的數字，改標序列基準日讓落後看得見（同 _md_stale_badge 的教訓）。
    # 判準用 chg_asof（漲跌所屬交易日）而非 perf_asof（序列末日）：兩者在 L1 備案下會不同
    # ——序列落後但 etfinfo 前收自算成功時，漲跌其實是當日的，不該被誤標過期。
    # 舊落檔沒有 chg_asof → 退回 perf_asof（與本防呆上線前的行為一致）。
    state, tip = chg_trust(i)
    if state == "lag":          # 落後＝印出基準日，讀者據此知道「這格晚一天」（有資訊價值）
        return (f'{_pct_span(None)}<span class="mdstale" title="{_esc(tip)}">'
                f'⚠ 基準 {i.get("chg_asof") or i.get("perf_asof")}</span>')
    if state == "bad":          # 日期不可能（週末／未收盤）＝那個日期對讀者沒有意義，不印
        return f'<span class="na" title="{_esc(tip)}">—<sup class="estmk">⚠</sup></span>'
    amt, pc, pd_ = i.get("chg_amt"), i.get("prev_close"), i.get("prev_date")
    exd = i.get("chg_ex_div")
    parts = [f"{'+' if (amt or 0) > 0 else ''}{amt:g} 元" if amt is not None else "",
             f"前收（{pd_ or '前一交易日'}）{pc:g}" if pc is not None else ""]
    if exd:
        ref = round((pc or 0) - exd, 4)
        parts.append(f"除息 {exd:g}／基準為除息參考價 {ref:g}")
    tip = "當日漲跌：" + "，".join(x for x in parts if x) if any(parts) else ""
    cls = "gain" if v > 0 else ("loss" if v < 0 else "flat")
    sign = "+" if v > 0 else ""
    return (f'<span class="{cls}"' + (f' title="{_esc(tip)}"' if tip else "")
            + f'>{sign}{v:.2f}%</span>')


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


# ── ETF 詳情（底部專屬區塊；2026-07-30 使用者需求，比照使用者提供的版面架構） ──
#
# 舊版把明細塞在 ETF 表的隱藏列（tr.hdrow）裡，先後被使用者指出兩個問題：整寬 colspan
# 列「展開後超空」、泡泡卡也仍嫌零碎。改為「上表 → 底部詳情」兩層：ETF 表點代碼＝
# 選定該檔並跳到底部 #etf-detail，詳情區三段——
#   ① 持股異動方塊圖（squarify treemap：外層產業／內層個股，面積 ∝ |金額|，
#      加碼·新增紅系、減碼·出清綠系）
#   ② 異動明細表（股票｜張數＋金額｜類型 pill，張數／金額可點排序）
#   ③ 完整持股明細（搜尋代號或名稱、代號/名稱｜漲跌幅/收盤價｜權重/股數｜貢獻度，
#      可排序、每頁 15 筆分頁）
#
# 版面由前端以內嵌資料渲染（切換 ETF 不重載頁面）；**treemap 座標仍在 Python 算好**
# （arm/treemap.py，輸出百分比座標）——同專案「算在產表端、前端純渲染」慣例，
# 前端不必再實作一次 squarify。

# 方塊圖色票（2026-07-30 重新設計）：深色畫布上的雙向色階。
# 紅＝加碼／新增、綠松＝減碼／出清——**綠色刻意偏青**：純紅×純綠在色盲模擬下
# 分離度只有 ΔE 5.9（不及格），紅 #e6504c × 綠松 #159c94 為 12.1（通過），
# 且台股慣例的「紅漲綠跌」語意完全不受影響。兩色在 #14171b 畫布上皆 ≥3:1 對比。
_TM_SURFACE = "#14171b"
_TM_UP = "#e6504c"
_TM_DN = "#159c94"

_ED_TM_ITEMS = 7          # 方塊圖個股格數上限＝**7 格＋其他**（2026-07-30 使用者指定的基本
                          # 格式）。格數少 → 每格夠大 → 放得下完整資料（代碼＋簡稱＋金額）。
# 註：曾有「至少保留 3 格」的規則，2026-07-30 移除——它與「畫得出標籤才單獨一格」相牴觸：
# 異動極度集中時（單檔佔 95%），硬留的那 3 格必然是讀不出來的細條。退化情形交給前端
# 「少於 3 格就不畫圖」處理，看明細表更快。
# 「畫得出標籤才值得單獨一格」的量尺（2026-07-30 使用者定案：顯示不出來＝沒那麼重要
# ＝歸到其他；反過來說，佔比還行的變動不可以因為排版被擠成細條而顯示不完整）。
# 參考寬取**手機內容寬**：在最窄的版面放得下，寬螢幕只會更大——單一判準、不必兩處各算一次。
_TM_W_REF = 280.0         # 參考版面寬（px，取手機內容寬並留餘裕）
# 每格都必須放得下**完整資料：代碼＋公司簡稱＋金額**（2026-07-30 使用者明確要求）。
# 允許兩種標籤幾何，通過任一種即可——squarify 產生的格子有方有扁，只認一種會白白折疊掉
# 放得下的格（實測只認寬版時 0050 從 7 格掉到 4 格）：
#   · 堆疊版（窄而高）：代碼／簡稱／金額各一行
#   · 寬版（寬而矮）：代碼＋簡稱同一行，金額第二行
_TM_MIN_W, _TM_MIN_H = 54.0, 58.0      # 堆疊版最小格寬／格高
_TM_WIDE_W, _TM_WIDE_H = 76.0, 40.0    # 寬版最小格寬／格高


def _tm_fits(w_px: float, h_px: float) -> bool:
    """這個格子放得下完整三項資料嗎（堆疊版或寬版任一）。"""
    return ((w_px >= _TM_MIN_W and h_px >= _TM_MIN_H)
            or (w_px >= _TM_WIDE_W and h_px >= _TM_WIDE_H))
# 圖高：**在「每格都放得下完整資料」的前提下，能多矮就多矮**——兼顧使用者兩個要求
# （「沒有變動／格數少就要收斂，不然好大一塊空的」＋「圖還是要畫」）。
# 折疊判定一律用最大高度 `_TM_H_MAX`（先盡量留格），確定格數後再往下找最矮可行高度。
_TM_H_MIN, _TM_H_MAX, _TM_H_STEP = 132, 300, 18
# 面積壓縮指數（2026-07-30 使用者要「畫的時候平均一點」＋「7 格＋其他、每格都要有完整
# 數據」）：面積嚴格 ∝ 金額時，單檔佔 61% 的日子（0050 的台積電）就注定把其餘擠成細條，
# 7 格根本放不下三行標籤。改 **面積 ∝ |金額|^0.5**：排序與相對大小保留，極端值被壓平。
# 精確數字沒有損失——每格都印著金額、下方明細表逐檔列出——但面積不再是等比，
# 圖註必須寫明（`_TM_AREA_NOTE`）。要改回等比就得放棄「7 格都完整」，兩者不可兼得。
_TM_AREA_GAMMA = 0.5
_TM_AREA_NOTE = "格子大小為相對比較（面積依金額平方根壓縮，避免單一大單把其餘擠成細條）"


def _tm_fit_height(rects: list[dict]) -> int:
    """能讓**每一格**都放得下完整資料的最矮圖高（px）。

    版面座標是百分比，改高度只縮放各格的實際像素高——所以由矮往高試、第一個全數通過的
    就是答案。全部試完都不行時回最大高度（此時折疊迴圈已經把放不下的格降級掉了）。
    """
    if not rects:
        return 0
    for h in range(_TM_H_MIN, _TM_H_MAX + 1, _TM_H_STEP):
        if all(_tm_fits(r["w"] / 100 * _TM_W_REF, r["h"] / 100 * h) for r in rects):
            return h
    return _TM_H_MAX


def _eh_verify_chip(vf: dict) -> list:
    """跨源驗證章 → [樣式類別, 章面文字, tooltip]（供前端渲染；文案沿用舊版）。"""
    other = str((vf or {}).get("other") or "第二來源")
    st = (vf or {}).get("status")
    hit, n = (vf or {}).get("top_hit"), (vf or {}).get("top_n")
    dw = (vf or {}).get("max_dw")
    if st == "match" and vf.get("weights_compared"):
        return ["hvok", "🟢 雙源相符",
                f"與 {other} 交叉驗證：前十大重合 {hit}/{n}、共同持股權重差 ≤"
                f"{dw if dw is not None else '—'}pp"]
    if st == "match":
        return ["hvok", "🟢 構成相符",
                f"與 {other} 構成交叉驗證：前十大重合 {hit}/{n}"
                "（副源為月度基準，權重時點不同不予比對）"]
    if st == "weak":
        return ["hvone", "副源過舊・未能驗證",
                f"副源（{other}）持股為月度基準、與每日快照構成重合僅 {hit}/{n}"
                "——多為月內調倉所致，非主來源錯誤的證據；本次未能有效交叉驗證"]
    if st == "mismatch":
        return ["hvbad", "⚠ 兩源不符",
                f"與 {other} 不符：前十大僅重合 {hit}/{n}、權重差最大 {dw}pp"
                "——本表照用主來源，數字請以官方揭露為準"]
    if st == "single":
        return ["hvone", "單源未驗證", "僅單一來源可得，本次未經第二站交叉驗證"]
    return ["", "", ""]


def _tm_dir(kind: str) -> str:
    """方向（顏色）只有兩個：加碼側（含新增）與減碼側（含出清）。"""
    return "add" if kind in ("add", "new") else "cut"


def _eh_treemap(moves: list[dict], basis: str) -> dict:
    """異動清單 → **單層** treemap（百分比座標，前端直接當 % 用）。

    2026-07-30 使用者定案的兩條規則：
      · **不分產業**——產業別對照抓不齊（海外持股、部分上櫃檔沒有），分層後常出現
        「未分類」群組或小群組拿不到標籤被誤讀成隔壁產業，資訊價值輸給版面代價。
        產業名仍留在每格 tooltip（`ind`），資料層照樣入庫，日後覆蓋率夠了可再分層
        （`arm/treemap.grouped()` 保留）。
      · **「畫得出標籤才值得單獨一格」**——排完版後逐格檢查在參考寬（手機內容寬）下
        放不放得下兩行標籤（代碼＋金額）；放不下的**一次降級一格**再重排，直到每格都讀得完整。
        降級者依方向併成「其他 N 檔」（顏色語意不混），逐檔數字在下方明細表照樣列。
        這比「固定佔比門檻」正確：門檻是猜的，能不能顯示才是使用者真正在意的事。

    面積依據：有報價時用 |金額|，否則退回 |股數|（`basis`，說明文會標明）。
    回傳 {"blocks": [每格], "hidden": 未入圖檔數}。
    """
    def val(m):
        return abs((m.get("amount") if basis == "amount" else m.get("m_shares")) or 0)

    # 面積算不出來者（全球型 ETF 的海外持股沒有台股報價 → amount 為 None）不能靜靜消失，
    # 必須回報檔數：否則 00990A 的 18 檔異動只畫 1 格、看板上卻沒交代其餘 17 檔去哪了。
    rows = sorted((m for m in moves if val(m) > 0), key=val, reverse=True)
    unpriced = len(moves) - len(rows)
    if not rows:
        return {"blocks": [], "hidden": 0, "unpriced": unpriced, "height": 0}
    keep, rest = rows[:_ED_TM_ITEMS], rows[_ED_TM_ITEMS:]
    off: set = set()          # 連「其他 N 檔」併格自己都畫不出標籤的方向 → 整格不入圖

    def build(keep_, rest_):
        items = [{"s": m["stock_id"], "n": m.get("name") or m["stock_id"],
                  "a": m.get("amount"), "sh": m.get("m_shares"),
                  "k": m.get("kind"), "ind": m.get("industry"), "v": val(m)}
                 for m in keep_]
        for d in ("add", "cut"):
            grp = [m for m in rest_ if _tm_dir(m.get("kind") or "") == d]
            if not grp or d in off:
                continue
            items.append({"s": "", "n": f"其他 {len(grp)} 檔", "k": d, "agg": True,
                          "a": (sum(m["amount"] for m in grp)
                                if all(m.get("amount") is not None for m in grp) else None),
                          "sh": sum(m.get("m_shares") or 0 for m in grp),
                          "v": sum(val(m) for m in grp)})
        return items

    for _ in range(len(rows) + 4):
        items = build(keep, rest)
        # keep_order：個股依金額遞減、**併格固定排最後** → squarify 由左上往右下填，
        # 「其他」自然落在右下角（2026-07-30 使用者：既然都叫其他就不要太明顯）
        rects = treemap.layout([(i, it["v"] ** _TM_AREA_GAMMA) for i, it in enumerate(items)],
                               w=100.0, h=100.0, keep_order=True)
        h_px = _TM_H_MAX          # 折疊判定用最大高度：先盡量留格，之後再收斂圖高
        bad = [r for r in rects
               if not _tm_fits(r["w"] / 100 * _TM_W_REF, r["h"] / 100 * h_px)]
        if not bad:
            break
        drop = min(bad, key=lambda r: items[r["key"]]["v"])
        it = items[drop["key"]]
        if it.get("agg"):
            off.add(it["k"])                              # 併格畫不出來 → 不入圖（明細表照樣列）
            continue
        if len(keep) <= 1:
            break
        rest.append(keep.pop(next(i for i, m in enumerate(keep)
                                  if m["stock_id"] == it["s"])))
    out = []
    for r in rects:
        it = items[r["key"]]
        out.append({**{k: v for k, v in it.items() if k != "v"},
                    "x": round(r["x"], 2), "y": round(r["y"], 2),
                    "w": round(r["w"], 2), "h": round(r["h"], 2)})
    # 未入圖的檔數（併格被剔除的方向）——說明文要誠實交代，不能悄悄消失
    return {"blocks": out, "unpriced": unpriced, "height": _tm_fit_height(out),
            "hidden": sum(1 for m in rest if _tm_dir(m.get("kind") or "") in off)}


def _eh_intros(payload: dict) -> dict:
    """全體 ETF 持股的「標的簡介」對照表 {代號: 簡介}——共用一份，避免逐檔重複。

    先用代號查（profile 的 `ticker`；原樣與「剝掉交易所字尾」各試一次，見
    `fund_intro.norm_ticker`），再用名稱查（profile 的鍵）。庫是為基金前十大而建，
    ETF 持股覆蓋率有限——有就顯示、沒有就不留空位，卡片標題另標「N 檔附標的簡介」。
    """
    by_tk, by_nm = fund_intro.intro_lookup()
    out = {}
    for p in payload.values():
        for r in p.get("al") or []:
            sid = str(r[0] or "").strip()
            if sid in out:
                continue
            nm = str(r[1] or "").strip()
            got = (by_tk.get(sid) or by_tk.get(fund_intro.norm_ticker(sid))
                   or by_nm.get(nm) or by_nm.get(nm.upper()))
            if got:
                out[sid] = got
    return out


def _eh_payload(detail: dict | None, name: str = "") -> dict | None:
    """單檔 ETF 的詳情資料（內嵌 JSON 用）。

    列一律用**緊湊陣列**而非物件：完整持股明細全 23 檔合計逾千列，物件鍵名會讓
    內嵌 JSON 膨脹一倍以上（欄序定義見前端 `AL`／`MV` 註解）。
    """
    if not detail:
        return None
    basis = detail.get("amount_basis") or "shares"
    fig = _eh_treemap(detail.get("moves") or [], basis)
    tm, hidden, unpriced = fig["blocks"], fig["hidden"], fig["unpriced"]
    # 只放「這列報價日＝報價日 pd」的漲跌／收盤／貢獻（2026-10-21 錯日事故：晚上那幾班上市＝前一天、
    # 上櫃＝當天，39% 的列錯日）。舊格式（沒有 pd）一律不顯示——下一班 ETF 持股更新就會補上。
    pd = detail.get("pd")
    al, tc, cw, n_ok = [], 0.0, 0.0, 0
    for r in detail.get("all") or []:
        ok = bool(pd) and r.get("qd") == pd and r.get("chg_pct") is not None
        if ok:
            n_ok += 1
            if r.get("contrib") is not None:
                tc += r["contrib"]
                cw += r.get("weight") or 0.0
        al.append([r["stock_id"], r.get("name") or r["stock_id"], r.get("weight"),
                   r.get("shares"), r.get("close") if ok else None,
                   r.get("chg_pct") if ok else None, r.get("contrib") if ok else None,
                   1 if (r.get("pend") and not ok) else 0])
    out = {
        "nm": name, "d": detail.get("date"), "p": detail.get("prev_date"),
        "pd": pd, "np": sum(1 for a in al if a[7]),
        "n": detail.get("n_holdings"), "sw": detail.get("sum_weight"),
        "src": detail.get("src"), "basis": basis,
        "tc": round(tc, 2) if n_ok else None, "cw": round(cw, 1),
        "vf": _eh_verify_chip(detail.get("verify") or {}),
        "mn": detail.get("moves_n"), "mr": detail.get("moves_rest_n"),
        # xsrc＝本次與前一揭露日的來源不同 → 只比共同持股，新增／出清不予判定
        "xs": detail.get("xsrc"),
        "tm": tm, "th": fig["height"], "hid": hidden, "nq": unpriced,
        "an": _TM_AREA_NOTE,
        # MV：[代號, 名稱, 異動股數, 金額, 類型]
        "mv": [[m["stock_id"], m.get("name") or m["stock_id"], m.get("m_shares"),
                m.get("amount"), m.get("kind")] for m in (detail.get("moves") or [])],
        # AL：[代號, 名稱, 權重, 股數, 收盤價, 漲跌%（報價日 pd）, 貢獻pp, 待收盤(1/0)]
        # 標的簡介**不放在列裡**：同一檔股票會出現在多檔 ETF，逐檔各存一份會讓內嵌 JSON
        # 多出約 200KB（實測 494→695KB）。改成全體共用 {代號: 簡介} 一份，前端依代號查。
        "al": al,
    }
    fu = _eh_fut(detail.get("fut"))
    if fu:
        out["fu"] = fu
        out["fc"] = 1 if any(r[5] or r[7] for r in fu["r"]) else 0
    return out


def _eh_fut(fv: dict | None) -> dict | None:
    """「期貨部位」區塊資料（etfholdings.fut_view → 緊湊陣列）。沒有期貨 → None（不出區塊）。

    FU.r：[商品代號, 名稱, 口數（空單為負）, 名目曝險%, 月份, 比前一揭露日加減口數, 動作, 轉倉（舊月份 → 新月份）]
    期貨只付保證金、權重是名目曝險，所以不進持股權重、方塊圖與貢獻度（2026-10-21 使用者同意另列）。"""
    if not fv or not fv.get("rows"):
        return None
    rows = [[r["root"], r.get("name") or "", r.get("qty"), r.get("w"), "、".join(r.get("ym") or []),
             r.get("dq"), r.get("act") or "",
             ("、".join(r["pym"]) + " → " + "、".join(r["ym"])) if r.get("roll") else ""]
            for r in fv["rows"]]
    return {"r": rows, "nw": fv.get("net_w"), "pdd": fv.get("prev_date"),
            "cmp": 1 if fv.get("cmp") else 0, "xs": fv.get("xsrc")}


def _eh_fut_sub(fu: dict | None) -> str:
    """卡片標題列的期貨變動摘要（例「・期貨 +10 口」）；沒有可比的前一揭露日或沒變動 → 空字串。"""
    if not fu or not fu.get("cmp"):
        return ""
    ch = [r for r in fu["r"] if r[5] or r[7]]
    if not ch:
        return ""
    if len(ch) > 1:
        return "・期貨有變動"
    return f"・期貨 {ch[0][5]:+,} 口" if ch[0][5] else "・期貨轉倉"


def _etf_detail_view(doc: dict | None, holdings_doc: dict | None) -> str:
    """ETF 持股詳情＆異動——**比照基金詳情**的版面（2026-07-31 使用者指示）：
    工具列（搜尋＋分類 chips＋全部展開／收合）＋ 每檔一張可收合 `<details>` 卡。

    卡片內容**延遲渲染**：23 檔各含方塊圖＋兩張表，一次全塞進 DOM 會讓頁面又大又慢；
    改成第一次展開時才由前端依內嵌資料建出來（同 `.fund` 卡的收合體驗，但更省）。
    """
    items = (doc or {}).get("items") or []
    labels = {"passive": "被動", "active": "主動式", "other": "其他"}
    payload, cards, picks = {}, [], {}
    for i in items:
        code = i.get("code")
        det = etfholdings.view(holdings_doc, code)
        p = _eh_payload(det, i.get("name") or "")
        if not p:
            continue
        payload[code] = p
        kind = i.get("kind") or "passive"
        nm = _short(i.get("name") or "")
        # 泡泡標籤去掉「主動」前綴——那排的標籤已經寫著「主動式」，重複只是把泡泡撐寬，
        # 15 顆主動式擠成十幾行；搜尋比對仍用完整名稱（data-name）。
        picks.setdefault(kind, []).append(
            f'<button class="edchip" data-c="{_esc(code)}" '
            f'data-name="{_esc(code)} {_esc(nm)}" data-group="{kind}">'
            f'<b>{_esc(code)}</b><span>{_esc(nm.removeprefix("主動"))}</span></button>')
        mv = p.get("mn") or 0
        sub = (f'異動 {mv} 檔' if mv else
               ('無異動' if p.get("p") else '首次揭露')) + _eh_fut_sub(p.get("fu"))
        cards.append(
            f'<details class="etfd" id="etfd-{_esc(code)}" '
            f'data-c="{_esc(code)}" data-name="{_esc(code)} {_esc(nm)}" data-group="{kind}">'
            f'<summary class="fsum"><span class="fsum-l"><b>{_esc(code)}</b> {_esc(nm)}</span>'
            f'<span class="gl">{labels.get(kind, kind)}</span>'
            f'<span class="fsum-r"><span class="edmeta">揭露 {_esc(p.get("d") or "—")}｜{sub}</span>'
            f'<span class="openbtn2"></span></span></summary>'
            f'<div class="etfd-body"></div></details>')
    if not payload:
        return ""
    js = json.dumps({"etfs": payload, "intro": _eh_intros(payload)},
                    ensure_ascii=False, separators=(",", ":"))
    # </script> 不可原樣出現在 inline script 內（HTML 解析器會提前結束腳本）
    js = js.replace("</", "<\\/")
    # 分類 chips 只列「有成員」的分組（2026-08-28 上櫃檔併入主動式後「其他」常態為空，
    # 空分組的 chip 點了毫無反應、看起來像壞掉）
    chips = "".join(f'<button class="eg" data-g="{k}">{v}</button>'
                    for k, v in labels.items() if picks.get(k))
    # ETF 代碼「泡泡」（2026-07-31 使用者：搜尋的地方也要有泡泡可以直接點，比打字方便）。
    # 照上方績效表分被動／主動式／其他三排；點一顆＝展開該檔並捲過去。
    pick = "".join(
        f'<div class="edprow" data-group="{k}"><span class="edplab">{v}</span>'
        f'<span class="edpset">{"".join(picks[k])}</span></div>'
        for k, v in labels.items() if picks.get(k))
    return (
        f'<div class="section" id="etf-detail"><div class="st">{_ic("layers", tone="teal")}'
        f'ETF 持股詳情＆異動 '
        f'<span class="stsub">預設收合・點卡片展開；每檔含持股異動方塊圖、異動明細與'
        f'完整持股（含當日漲跌貢獻與標的簡介）</span></div>'
        f'<div class="fundbar">{_ic("search", plain=True)}'
        f'<input id="esearch" type="search" placeholder="輸入 ETF 代碼或名稱篩選…">'
        f'<span class="fgchips"><button class="eg on" data-g="">全部</button>{chips}</span>'
        f'<button class="fexp" id="eexp">全部展開</button>'
        f'<button class="fexp" id="ecol">全部收合</button></div>'
        f'<div class="edpick" id="edpick">{pick}</div>'
        f'{"".join(cards)}'
        f'<script>window.__EH={js};</script></div>')


def _etf_table(items: list[dict], holdings_doc: dict | None = None) -> str:
    """單組 ETF 表（沿用 ovtbl 樣式與點欄排序）；有每日持股揭露者，列下方可展開明細。"""
    trs = []
    for i in items:
        code = i.get("code")
        vurl = f"https://tw.stock.yahoo.com/quote/{_esc(code)}"
        rsrc = i.get("ret_src") or "seed"
        srctag = (f'<span class="rsrc" title="過去一週／一月報酬取自此來源自算">'
                  f'{_esc(_RET_SRC_LABEL[rsrc])}</span>'
                  if rsrc in _RET_SRC_LABEL else "")
        # 產品名內「復華」以品牌色標示；代碼自成一行，避免名稱首字被擠上代碼列
        name_html = _esc(i.get("name") or "").replace("復華", '<span class="fh">復華</span>')
        has_det = bool(etfholdings.view(holdings_doc, code))
        if has_det:
            # 代碼與「詳情」同一行、名稱緊接下一行（2026-07-30 使用者：每一檔都好長）——
            # 原本是代碼／名稱／詳情鈕／Yahoo 連結四行堆疊，列高近 180px
            id_cell = (f'<td class="nm"><button type="button" class="edjump" '
                       f'data-c="{_esc(code)}" '
                       f'aria-label="看 {_esc(code)} 的持股異動與完整持股明細">'
                       f'<span class="etline"><b class="etcode">{_esc(code)}</b>'
                       f'<span class="edjt">詳情 ↓</span></span>'
                       f'<span class="etname">{name_html}{srctag}</span></button></td>')
        else:
            id_cell = (f'<td class="nm"><span class="etline">'
                       f'<b class="etcode">{_esc(code)}</b></span>'
                       f'<span class="etname">{name_html}{srctag}</span></td>')
        # Yahoo 對照連結移到「性質」欄（2026-07-30 使用者指示）——該欄原本只有一顆分類 chip、
        # 大片空白，識別欄則被四行內容撐長；連結放這裡剛好把兩邊的空間都用對
        tds = [f'<td class="nm"><span class="etcat">{_esc(i.get("cat") or "—")}</span>'
               f'<a class="etyh" href="{vurl}" target="_blank" rel="noopener" '
               f'title="開 Yahoo奇摩股市對照驗證">Yahoo↗</a></td>', id_cell]
        for k, _ in _ETF_COLS:
            v = _etf_sortv(k, i)
            if k in ("ret_1w", "ret_1m"):
                cell = _ret_cell(i, k)
            elif k == "chg_pct":
                cell = _chg_cell(i)
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


def _upcoming_etf_card(it: dict) -> str:
    """單張「即將登場」ETF 卡片：代碼／名稱／投信＋狀態章＋主題＋活動介紹連結。

    狀態章依 etfwatch.upcoming() 的 stat：募集中(now)／即將募集(soon)／掛牌 MM/DD(list)／
    募集結束・待掛牌(pend)；募集組若已公告掛牌日，加「預定掛牌 MM/DD」副標（2026-08-10 改版）。
    「已核准・時程未定」不走卡片——用 _upcoming_hint_row() 精簡列（同日使用者指示分類）。"""
    code = _esc(it.get("code") or "")
    name = _esc(it.get("name") or "").replace("復華", '<span class="fh">復華</span>')
    issuer = _esc(it.get("issuer") or "")
    theme = _esc(it.get("theme") or "")
    stat = it.get("stat") or ("list" if it.get("list_date") else "soon")

    def _md(s):
        s = str(s or "")
        return s[5:].replace("-", "/") if len(s) >= 10 else s

    tags = []
    if stat == "list":
        status = f'<span class="upstat list">掛牌 {_esc(_md(it.get("list_date")))}</span>'
    elif stat == "pend":
        status = '<span class="upstat pend">募集結束・待掛牌</span>'
        tags.append('<span class="uptag">掛牌日待公告</span>')
    else:                                   # now／soon：募集期間為主，掛牌日當副標
        rs_md, re_md = _md(it.get("raise_start")), _md(it.get("raise_end"))
        span = f'{rs_md}–{re_md}' if re_md else f'{rs_md} 起'
        status = (f'<span class="upstat now">募集中 {_esc(span)}</span>' if stat == "now"
                  else f'<span class="upstat raise">募集 {_esc(span)}</span>')
        if it.get("list_date"):
            tags.append(f'<span class="uptag ld">預定掛牌 {_esc(_md(it["list_date"]))}</span>')
    freq = it.get("freq")
    if freq and freq != "—":
        tags.append(f'<span class="uptag">{_esc(freq)}</span>')
    url = it.get("url")
    link = (f'<a class="uplink" href="{_esc(url)}" target="_blank" rel="noopener">'
            f'活動介紹 ↗</a>' if url else "")
    return (f'<div class="upcard">'
            f'<div class="uptop"><span class="upcode">{code}</span>'
            f'<span class="upname">{name}</span>'
            f'<span class="upissuer">{issuer}</span></div>'
            f'<div class="upmeta">{status}{"".join(tags)}</div>'
            f'<div class="uptheme">{theme}</div>{link}</div>')


def _upcoming_hint_row(it: dict) -> str:
    """「已核准・募集時程未定」精簡列（2026-08-10 使用者：「太長記得分類一下」）。

    這類條目常一掛一個多月、又只有『核准了』一個資訊點——整張卡太佔版面，
    一列帶完：代號（未派碼顯示「代號未定」）＋名稱＋投信＋時程 hint＋介紹連結。"""
    code = it.get("code")
    code_html = (f'<span class="upcode">{_esc(code)}</span>' if code
                 else '<span class="upnc">代號未定</span>')
    name = _esc(it.get("name") or "").replace("復華", '<span class="fh">復華</span>')
    issuer = _esc(it.get("issuer") or "")
    hint = _esc(it.get("raise_hint") or "時程未公告")
    url = it.get("url")
    link = (f'<a class="uprlink" href="{_esc(url)}" target="_blank" rel="noopener">介紹 ↗</a>'
            if url else "")
    return (f'<div class="uprow">{code_html}<span class="upname">{name}</span>'
            f'<span class="upissuer">{issuer}</span>'
            f'<span class="uphintt">{hint}</span>{link}</div>')


def _applied_row(it: dict) -> str:
    """「已送件・審查中」精簡列（2026-08-28 使用者：「有送件的 ETF 就可以更新上去即將登場了」）。

    資料源＝CI 發現層 gap 檔的 pipeline 欄（鉅亨 IPO 頁申請列自動彙整，非人工登錄）——
    只有基金名稱／類別／審核狀態三個資訊點，走 uprow 精簡列；核准（申報生效）後
    發現層自動升進 items、週掃／每日 SOP 查證登錄，即移入上方正式分組。"""
    name = _esc(it.get("name") or "").replace("復華", '<span class="fh">復華</span>')
    cat = _esc(it.get("cat") or "")
    approve = _esc(it.get("approve") or "審查中")
    return (f'<div class="uprow"><span class="upnc">申請中</span>'
            f'<span class="upname">{name}</span>'
            f'<span class="upissuer">{cat}</span>'
            f'<span class="uphintt">{approve}</span></div>')


def _upcoming_etf_view(up: dict | None, applied: list | None = None) -> str:
    """「即將登場的新 ETF」——四組分類（2026-08-10 使用者：「太長記得分類一下，尤其是
    只有核准還沒確定募集時間的」；2026-08-28 補第四組「已送件・審查中」）：
      ① 募集中・即將募集（卡片；可申購、時效最高，在前）
      ② 即將掛牌・待掛牌（卡片；募集結束的檔以「待掛牌」續留，舊版會直接消失）
      ③ 已核准・募集時程未定（精簡列；資訊量只有「核准了」，不佔卡片版面）
      ④ 已送件・審查中（精簡列；發現層 pipeline 自動彙整，未生效前不登錄不警示，僅展示）
    置於「ETF 數據追蹤」表格上方；無任何在窗項目時顯示精簡提示、不佔版面。"""
    up = up or {}
    raising = up.get("raising") or []
    listing = up.get("listing") or []
    approved = up.get("approved") or []
    seen, applied_rows = set(), []
    for it in applied or []:                    # 同名去重＋本家優先排序（復華在前）
        nm = str((it or {}).get("name") or "").strip()
        if nm and nm not in seen:
            seen.add(nm)
            applied_rows.append(it)
    applied_rows.sort(key=lambda x: (0 if "復華" in (x.get("name") or "") else 1,
                                     str(x.get("name") or "")))
    if not listing and not raising and not approved and not applied_rows:
        return ('<div class="upnone">近期無「募集中／即將掛牌／已核准」的新 ETF 待登場'
                '（本區列：募集開始或已公告掛牌日在未來約一個半月內、募集剛結束待掛牌、'
                '或已核准待定時程者，過期自動移除）。</div>')
    parts = ['<div class="upwrap">']
    if raising:
        parts.append(f'<div class="upgrp">{_ic("coin", plain=True)} 募集中・即將募集 '
                     f'<span class="upwin">（{len(raising)} 檔）</span></div>'
                     f'<div class="upgrid">'
                     + "".join(_upcoming_etf_card(it) for it in raising)
                     + '</div>')
    if listing:
        parts.append(f'<div class="upgrp">{_ic("zap", plain=True)} 即將掛牌・待掛牌 '
                     f'<span class="upwin">（已公告掛牌日、或募集結束待掛牌・{len(listing)} 檔）</span></div>'
                     f'<div class="upgrid">'
                     + "".join(_upcoming_etf_card(it) for it in listing)
                     + '</div>')
    if approved:
        parts.append(f'<div class="upgrp">{_ic("clipboard", plain=True)} 已核准・募集時程未定 '
                     f'<span class="upwin">（{len(approved)} 檔・時程公告後自動移入上方分組）</span></div>'
                     f'<div class="uplist">'
                     + "".join(_upcoming_hint_row(it) for it in approved)
                     + '</div>')
    if applied_rows:
        parts.append(f'<div class="upgrp">{_ic("clipboard", plain=True)} 已送件・審查中 '
                     f'<span class="upwin">（{len(applied_rows)} 檔・鉅亨 IPO 頁申請列自動彙整，'
                     f'核准後自動移入上方分組）</span></div>'
                     f'<div class="uplist">'
                     + "".join(_applied_row(it) for it in applied_rows)
                     + '</div>')
    parts.append(
        '<div class="upfoot">新 ETF 前瞻資訊為人工彙整（來源：各投信官方募集頁／公開資訊觀測站／'
        '經濟日報・工商時報・MoneyDJ 新基金頁等，點「活動介紹」看原始說明）；日期以各投信公告為準，'
        '僅供參考、非投資建議或招攬。募集期間、掛牌日期可能因主管機關核准進度調整。海外被動指數'
        '新檔僅在本區前瞻展示，掛牌後不列入下方追蹤表。「已送件・審查中」為主管機關申請資訊之'
        '自動彙整，送件內容可能修改或撤件，核准前僅供前瞻參考。</div></div>')
    return "".join(parts)


def _etfwatch_view(doc: dict | None, holdings_doc: dict | None = None) -> str:
    """ETF 數據追蹤分頁：被動（高股息／市值型）與主動式兩張週績效表。
    有每日持股揭露（data/etf_holdings.json）者，列下方多一條可展開的持股變化／當日貢獻明細。"""
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
                     + _etf_table(passive, holdings_doc))
    if active:
        # 2026-08-28 使用者指示：分組照投資型態走——上櫃主動檔（原「其他」組）併入主動式表，
        # 掛牌地改在性質欄以「・上櫃」註記；債券型主動檔同表、性質欄標「主動式債券」。
        parts.append(f'<div class="ovg" id="etf-active">{_ic("zap", plain=True)} 主動式 ETF（股票／債券・{len(active)} 檔）</div>'
                     + _etf_table(active, holdings_doc))
    if other:                                   # 目前無成員（機制保留：未來真無法歸類的檔）
        parts.append(f'<div class="ovg" id="etf-other">{_ic("coin", plain=True)} 其他（{len(other)} 檔）</div>'
                     + _etf_table(other, holdings_doc))
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
        '（Tier B 第三方彙整；規模為該站揭露之基金淨資產，各站因揭露時點可能差一個交易日，'
        '與投信官網／其他行情站同日數字容有 1～3% 落差）；'
        '過去一週／一月報酬 ← <a href="https://stooq.com" target="_blank" rel="noopener">stooq</a>／'
        '<a href="https://finance.yahoo.com" target="_blank" rel="noopener">Yahoo</a>／FinMind／'
        '<a href="https://www.twse.com.tw/zh/trading/historical/stock-day.html" target="_blank" '
        'rel="noopener">TWSE 官方</a>依序取乾淨日線自算（以最新交易日收盤對回推 7／30 日曆日前最後交易日計算；'
        '區間內有除息時把息加回──總報酬口徑，報酬格下方標「＋息」）；'
        '<b>「當日漲跌」與「過去一週／一月報酬」皆為市價（收盤價）口徑</b>；當日漲跌若逢除息日，'
        '以「除息參考價＝前收 − 配息」為基準（滑鼠移到數字上可見前收與漲跌額）。'
        '投信官網與 Yahoo奇摩股市 ETF 頁揭露的績效多為'
        '<b>「淨值（NAV）」口徑</b>，兩者因折溢價每日變動，同一檔同一期間通常會差 0.1～0.8 個百分點，'
        '屬正常口徑差異而非數據有誤；欲與投信文宣逐欄對齊請以各投信官網淨值報酬為準。'
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
        # 組合型（*_fof）十大持有為基金／ETF；官網有揭露（2026-08-12 起解析支援），
        # 空值＝本次抓取暫時失敗，非「官網不揭露」（舊訊息曾如此誤標）
        if str(doc.get("group") or "").endswith("_fof"):
            return ('<div class="muted">本基金為組合型（fund-of-funds），持有標的為基金／ETF；'
                    '本次暫未取得十大持有明細，成分亦可見基金月報。</div>')
        return '<div class="muted">十大持有標的暫無資料。</div>'
    rows = []
    for i, h in enumerate(hs, 1):
        # 每檔持股都可點進外部行情頁（Yahoo Finance，涵蓋台／美／日／韓／中 A 股）——
        # 標的名即連結，代碼旁再掛統一「↗」外部連結標；不再「有些有圖標、有些沒有」。
        # 連結優先序：profile 指定的資訊頁（基金型持有 → 鉅亨/MoneyDJ）→ 依代號/國別產 Yahoo 行情頁。
        # _safe_url 對空值回 "#"（truthy）——先確認欄位有值再過安全檢查，否則會蓋掉 Yahoo 連結
        purl = _safe_url(h["url"]) if h.get("url") else ""
        purl = "" if purl == "#" else purl
        su = purl or fund_insights.stock_url(h.get("ticker"), h.get("country"), h.get("name"))
        site = "基金資訊頁（Anue鉅亨）" if purl else "外部行情（Yahoo Finance）"
        cname = _esc(fund_insights.full_company_name(h.get("name")))
        name_html = (f'<a class="hnm" href="{_esc(su)}" target="_blank" rel="noopener" '
                     f'title="查看 {cname} {site}">{cname}</a>'
                     if su else f'<b>{cname}</b>')
        tk = ""
        if h.get("ticker"):
            tk = (f' <a class="tk" href="{_esc(su)}" target="_blank" rel="noopener" '
                  f'title="查看{site}">{_esc(h["ticker"])} ↗</a>' if su else
                  f' <span class="tk">{_esc(h["ticker"])}</span>')
        ct = f'<span class="pill">{_esc(h["country"])}</span>' if h.get("country") else ""
        intro = f'<div class="hintro">{_esc(h["intro"])}</div>' if h.get("intro") else ""
        hl = h.get("name") in linked_names
        link = ' <span class="hlk" title="今日新聞連動">🔗</span>' if hl else ""
        trcls = ' class="hl"' if hl else ""
        rows.append(
            f'<tr{trcls}><td class="rk">{i}</td>'
            f'<td class="nm">{name_html}{tk}{link} '
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
    # 配置欄三段依序：資產配置（組合型）→ 國家配置（海外）→ 產業配置；
    # 有資料的段才渲染標題，避免懸空「—」（國內基金無國家配置、組合型只有資產配置）。
    ast = doc.get("asset_alloc") or []
    cty = doc.get("country_alloc") or []
    sec = doc.get("sector_alloc") or []
    _blocks: list[tuple[str, str, list, str]] = []
    if ast:
        _blocks.append(("chart", "資產配置", ast, "var(--c1)"))
    if cty:
        _blocks.append(("globe", "國家配置", cty, "var(--c1)"))
    if sec or not _blocks:     # 全空時仍留產業配置示「—」，維持既有版面
        _blocks.append(("layers", "產業配置", sec, "var(--c2)"))
    _mt = ' style="margin-top:14px"'
    alloc_html = "".join(
        f'<div class="ctitle"{_mt if k else ""}>'
        f'{_ic(icon, plain=True)} {title}</div>{_bars(items, color)}'
        for k, (icon, title, items, color) in enumerate(_blocks))
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
      {alloc_html}
    </div>
    <div class="col">
      <div class="ctitle">{_ic("clipboard", plain=True)} 十大持有標的　<span class="asof">持股基準 {_esc(doc.get('as_of') or '—')}｜前十大合計 {_esc(conc_s)}</span></div>
      {_holdings_table(doc, linked_names)}
    </div>
  </div>
</details>"""


def _pending_card(p: dict) -> str:
    note = ("本基金為組合型（fund-of-funds），十大持有標的為基金／ETF；"
            if str(p.get("group") or "").endswith("_fof") else "")
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


# ── ⑥ 復華新聞・社群（2026-08-12 使用者指示改名；讀 data/fund_news.json；無檔顯示提示不壞版） ──

def _fundnews_item(i: dict, tags: str = "", cats: str = "") -> str:
    """單則新聞列：標題（可點）＋摘要（有才顯示）＋日期・來源・關聯基金標籤 meta 列。
    cats＝data-ncat 分組鍵（空白分隔，同稿可屬多組：brand/fund/etf），供新聞篩選列用。"""
    summ = f'<div class="fnsum">{_esc(i["summary"])}</div>' if i.get("summary") else ""
    return (f'<div class="fnit fnnews" data-ncat="{_esc(cats or "other")}">'
            f'<a class="fnt" href="{_esc(i.get("url") or "#")}" target="_blank" rel="noopener">'
            f'{_esc(i.get("title"))}</a>{summ}'
            f'<div class="fnmeta"><span class="fnd">{_esc((i.get("date") or "")[:10])}</span>'
            f'<span class="fnsrc">{_esc(i.get("source") or "—")}</span>{tags}</div></div>')


def _fund_tag_label(base: str | None) -> str:
    """關聯基金標籤短名：去「復華」前綴與「基金」尾綴（標籤空間小、品牌名不必重複）。"""
    s = re.sub(r"^復華", "", (base or "").strip())
    return re.sub(r"基金$", "", s) or (base or "")


def _fmt_views(n) -> str:
    """觀看數：1 萬以上以「萬」計（1.2萬）、以下千分位；0／缺值誠實顯示 —。"""
    try:
        n = int(n or 0)
    except (TypeError, ValueError):
        n = 0
    if n <= 0:
        return "—"
    if n >= 10000:
        return f"{n / 10000:.1f}".rstrip("0").rstrip(".") + "萬"
    return f"{n:,}"


def _fundnews_view(doc: dict | None) -> str:
    if not doc:
        return ('<div class="muted">尚無復華新聞資料。請執行 '
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

    def _add(item: dict, tag: str, cat: str = "") -> None:
        key = (item.get("title") or "")[:24]     # 同 fundnews.merge_news 的去重鍵
        if not key:
            return
        e = index.get(key)
        if e is None:
            e = {"item": item, "tags": [], "cats": []}
            index[key] = e
            entries.append(e)
        if tag and tag not in e["tags"]:
            e["tags"].append(tag)
        if cat and cat not in e["cats"]:         # 同稿可屬多組（投信動態＋某基金）
            e["cats"].append(cat)

    for i in doc.get("brand") or []:
        _add(i, '<span class="fntag fnbrand">投信動態</span>', "brand")
    for g in doc.get("funds") or []:
        fid = (g.get("fund_ids") or [""])[0]
        if fid:
            tag = (f'<a class="fntag" href="#fund-{_esc(fid)}" title="{_esc(g.get("base"))}">'
                   f'{_esc(_fund_tag_label(g.get("base")))}</a>')
        else:   # 自家 ETF 產品群組（2026-08-12 新增；無基金詳情卡可跳）：代碼章
            lab = g.get("code") or _fund_tag_label(g.get("base"))
            tag = f'<span class="fntag" title="{_esc(g.get("base"))}">{_esc(lab)}</span>'
        for i in g.get("items") or []:
            _add(i, tag, "fund" if fid else "etf")
    entries.sort(key=lambda e: e["item"].get("datetime") or e["item"].get("date") or "",
                 reverse=True)

    parts.append(f'<div class="fng">{_ic("news", plain=True)} 復華新聞（近 {win} 天）</div>')
    if entries:
        # 新聞篩選列（2026-08-15 使用者核可「社群列＋新聞列都做」）：同 .fundbar 版式
        ncnt: dict[str, int] = {}
        for e in entries:
            for c in e["cats"] or ["other"]:
                ncnt[c] = ncnt.get(c, 0) + 1
        nchips = ['<button class="sg on" data-f="all">全部</button>']
        for key, lab in (("brand", "投信動態"), ("fund", "基金"), ("etf", "ETF")):
            if ncnt.get(key):
                nchips.append(f'<button class="sg" data-f="{key}">{lab}</button>')
        parts.append(f'<div class="fundbar" id="newsbar">{_ic("search", plain=True)}'
                     f'<input id="nsearch" type="search" placeholder="搜尋標題、來源或關鍵字…"'
                     f' autocomplete="off">{"".join(nchips)}</div>')
        parts.append('<div class="fnlist">' + "".join(
            _fundnews_item(e["item"], "".join(e["tags"]), " ".join(e["cats"]))
            for e in entries) + '</div>')
    else:
        parts.append(f'<div class="muted">近 {win} 天無相關新聞（或來源暫不可達）。</div>')

    soc = doc.get("social") or []
    parts.append(f'<div class="fng">{_ic("chat", plain=True)} 社群討論（PTT・強基金・YouTube）</div>')
    if soc:
        rows = []
        gcnt: dict[str, int] = {}
        for s in soc:
            grp = fundnews.social_group(s)   # 2026-08-15 分類篩選：每列掛 data-fcat
            gcnt[grp] = gcnt.get(grp, 0) + 1
            pill = ""
            if (s.get("platform") or "ptt") == "youtube":   # 2026-08-06 使用者需求：社群加 YouTube
                badge = f'<span class="fnpush fnyt">▶ {_fmt_views(s.get("views"))}</span>'
                plat = "YouTube Shorts" if s.get("short") else "YouTube"
                src = (f'{_esc(s.get("channel"))}・{plat}' if s.get("channel") else plat)
                if s.get("official"):            # 三層標籤：官方／市場熱門（相關層不掛章）
                    pill = '<span class="fntag fnbrand">官方</span>'
                elif s.get("peer"):              # 2026-08-14 擴編：章帶主題分類（熱門・高股息）
                    cat = (s.get("cat") or "").strip()
                    lab = ("同業熱門" if not cat else
                           "熱門" if cat == "綜合" else f"熱門・{cat}")
                    pill = f'<span class="fntag">{_esc(lab)}</span>'
            elif (s.get("platform") or "") == "fundhot":    # 2026-08-12 使用者需求：加強基金
                n = s.get("replies")
                badge = (f'<span class="fnpush">💬 {int(n)}</span>' if n
                         else '<span class="fnpush">💬</span>')
                src = "強基金" + (f"・{_esc(s.get('board'))}" if s.get("board") else "")
            else:
                badge = f'<span class="fnpush">{int(s.get("push") or 0)} 推</span>'
                # 舊落檔項目無 board 欄＝雙板改版前抓的股票板（2026-08-07 起帶 board）
                bname = {"Stock": "股票板", "Fund": "基金板"}.get(s.get("board") or "Stock")
                src = f"PTT {bname}" if bname else "PTT"
            # 日期：來源沒給發文日時改標「首見 M/D」（強基金新站列表頁無 <time>）——
            # 2026-09-01 使用者「強基金都沒有在更新」：舊版那欄整片空白，站上長掛的
            # 舊討論看起來就像今天的新討論，缺口完全看不出來。
            when = s.get("date") or ""
            if not when and s.get("first_seen"):
                when = "首見 " + s["first_seen"][5:].replace("-", "/")
            rows.append(
                f'<div class="fnit fnsoc" data-fcat="{grp}">{badge}'
                f'<div class="fnsocb"><a class="fnt" href="{_esc(s.get("url") or "#")}" '
                f'target="_blank" rel="noopener">{_esc(s.get("title"))}</a>'
                f'<div class="fnmeta"><span class="fnd">{_esc(when)}</span>'
                f'<span class="fnsrc">{src}</span>{pill}</div></div></div>')
        # 分類篩選列（2026-08-15 使用者：「太長了…有分類可以點然後就可以篩選」；同日再指示
        # 「比照其他地方」＝沿用基金詳情/ETF 詳情的 .fundbar 版式：🔍 搜尋框＋標準尺寸 chips、
        # 不帶數量）。只渲染有項目的分組；other 組不設 chip、僅「全部」可見。
        chips = ['<button class="sg on" data-f="all">全部</button>']
        for key, lab in (("etf", "ETF"), ("active", "主動ETF"),
                         ("fund", "基金"), ("trend", "市場趨勢")):
            if gcnt.get(key):
                chips.append(f'<button class="sg" data-f="{key}">{lab}</button>')
        bar = (f'<div class="fundbar" id="socbar">{_ic("search", plain=True)}'
               f'<input id="ssearch" type="search" placeholder="搜尋標題、頻道或來源…"'
               f' autocomplete="off">{"".join(chips)}</div>')
        parts.append(bar + '<div class="fnlist">' + "".join(rows) + '</div>')
    else:
        parts.append('<div class="muted">近期無相關討論（或來源暫不可達）。</div>')
    parts.append(f'<div class="fnfoot">來源：{_esc(doc.get("source") or "自動擷取")}・'
                 f'更新 {_esc(doc.get("as_of") or "—")}。公開標題彙編、教育用途，非投資建議。</div>')
    return "".join(parts)


# ── 樣式與腳本（非 f-string，避免大括號跳脫） ─────────────────

_CSS = """
/* 2026-07-22 富途式扁平版：整站單一白色平面、無卡片框，區塊靠細分隔線＋留白分層 */
:root{--bg:#ffffff;--card:#ffffff;--card2:#f4f6fa;--ink:#1f2733;--mut:#727e8c;
--line:#e8ebf1;--c1:#3b82f6;--c2:#c2740e;--gain:#d33a34;--loss:#1f9d57;--acc:#2563c9;
--accd:#1c4fa8;--ink2:#44505f;--inset:#eef2f8;--hl:#153a7a;--hlbg:#dce7fa;--gold:#a16207;
--pad:#f7f9fc}
*{box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:var(--tbh,64px)}
body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.7 -apple-system,"PingFang TC","Noto Sans TC",Segoe UI,sans-serif}
/* 抓重點段落小標（新聞卡「對持股／族群影響」式標籤，全站統一） */
.klabel{display:inline-block;color:var(--accd);font-weight:700;letter-spacing:.02em;margin-right:8px}
a{color:var(--acc)} code{background:var(--inset);padding:1px 6px;border-radius:5px;color:var(--accd)}
.wrap{max-width:1240px;margin:0 auto;padding:10px 18px 60px}
/* SVG 圖標：區塊標題彩色圖標磚（雲學堂式模組色）＋行內 plain */
.ic{display:inline-flex;align-items:center;justify-content:center;width:29px;height:29px;
  border-radius:9px;background:rgba(47,111,208,.11);color:var(--accd);flex:0 0 auto}
.ic.t-amber{background:rgba(224,150,25,.15);color:#a16207}
.ic.t-green{background:rgba(22,163,74,.12);color:#15803d}
.ic.t-purple{background:rgba(124,58,237,.11);color:#6d28d9}
.ic.t-teal{background:rgba(13,148,136,.12);color:#0f766e}
.ic.t-navy{background:rgba(23,52,96,.12);color:#173460}
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
/* ── 分頁內各段（2026-09-24 使用者：「要點才會出現對應資訊不好用」）──
   同一分頁的各段一律由上往下全部顯示；頂欄那排標籤＝跳段目錄，點了捲到該段，
   捲動時由 JS 自動標亮目前所在段。radio 只當「目前段」的標記（標亮用），不再控制顯示。
   （2026-09-01～09-23 曾改為「一次只顯示一段」，使用者用過後決定改回整頁顯示。） */
.secradio{position:fixed;opacity:0;pointer-events:none}
.sec[data-sec]{scroll-margin-top:var(--tbh,64px)}
.tb-nav .sl{color:var(--ink2);font-size:13.5px;padding:5px 9px;border-radius:8px;cursor:pointer;
  white-space:nowrap;transition:color .15s,background .15s}
.tb-nav .sl:hover{color:var(--acc);background:var(--card2)}
#sec-brief:checked ~ .topbar .sl[for="sec-brief"],
#sec-news:checked ~ .topbar .sl[for="sec-news"],
#sec-fnews:checked ~ .topbar .sl[for="sec-fnews"],
#sec-over:checked ~ .topbar .sl[for="sec-over"],
#sec-det:checked ~ .topbar .sl[for="sec-det"],
#sec-mcal:checked ~ .topbar .sl[for="sec-mcal"],
#sec-mov:checked ~ .topbar .sl[for="sec-mov"],
#sec-mnews:checked ~ .topbar .sl[for="sec-mnews"],
#sec-mdata:checked ~ .topbar .sl[for="sec-mdata"],
#sec-eup:checked ~ .topbar .sl[for="sec-eup"],
#sec-ewatch:checked ~ .topbar .sl[for="sec-ewatch"],
#sec-edet:checked ~ .topbar .sl[for="sec-edet"]{color:var(--acc);background:var(--card2);font-weight:700}
/* 閱讀進度（黏頂目錄的配套）：整頁捲到哪 */
.rprog{position:fixed;left:0;top:0;height:3px;width:0;background:var(--acc);z-index:60;
  transition:width .12s linear;border-radius:0 3px 3px 0}
@media(max-width:820px){
  /* 手機：目錄改單行橫捲，段名不換行、不佔掉整個頂欄高度 */
  .tb-nav{margin-left:0;width:100%;flex-wrap:nowrap;overflow-x:auto;gap:2px;
    -webkit-overflow-scrolling:touch;scrollbar-width:none}
  .tb-nav::-webkit-scrollbar{display:none}
  .tb-nav .sl{font-size:13px;padding:6px 10px}
}
@media(min-width:1100px){
  /* 桌機：清單型區塊排成兩欄（新聞卡／社群列本來就是等寬卡） */
  .sec[data-sec="fnews"] .fnlist{column-count:2;column-gap:16px}
  .sec[data-sec="fnews"] .fnit{break-inside:avoid}
}
/* ① brief */
.ixrow{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px}
.ixc{flex:1;min-width:150px;background:var(--card2);border:0;border-radius:10px;padding:10px 14px}
.ixl{font-size:12px;color:var(--mut)} .ixv{font-size:21px;font-weight:800;letter-spacing:.01em}
.ixp{font-size:13px}
.chips{display:flex;gap:8px;flex-wrap:wrap}
.chip{display:inline-flex;align-items:center;gap:6px;background:var(--card2);border:0;border-radius:8px;padding:6px 12px;font-size:14px;color:var(--ink);text-decoration:none}
.chip b{font-weight:700} .chip.hot{background:rgba(47,111,208,.12);color:var(--accd)}
.chip.dim{color:var(--mut)}
.chip.stale{border-color:#c62828;background:rgba(198,40,40,.08);color:#c62828;font-weight:700}
.chip.warn{border-color:#b26a00;background:rgba(224,146,0,.10);color:#a35b00;font-weight:700}
.st .chip.fresh{font-size:11.5px;padding:2px 10px;margin-left:4px;font-weight:400;vertical-align:middle}
.st .chip.fresh b{font-weight:600}
.stale-note{color:#c62828;font-weight:700}
/* 網頁更新時間＝細條（2026-09-24 使用者：頁首太佔版面）——各區塊標題列另有自己的鮮度章 */
.freshbar{padding:8px 0 6px}
.freshbar>.st{font-size:13px;font-weight:700;color:var(--ink2);margin-bottom:0;gap:6px}
/* 數字核對 🔴 可展開明細（2026-08-07）：收合＝一顆 chip 大小，點開才佔版面 */
.st details.fcd{display:inline-block;vertical-align:middle;margin-left:4px;background:rgba(198,40,40,.08);border-radius:8px;padding:2px 10px;font-size:11.5px;color:#c62828;font-weight:700}
.st details.fcd summary{list-style:none;cursor:pointer;display:inline}
.st details.fcd summary::-webkit-details-marker{display:none}
.st details.fcd summary b{font-weight:600}
.st details.fcd summary::after{content:" ▾";font-weight:400;opacity:.8}
.st details.fcd[open] summary::after{content:" ▴";font-weight:400;opacity:.8}
.fcdl{margin:4px 0 2px;font-weight:400;color:var(--ink);text-align:left}
.fcrow{padding:1px 0}
.fcrow b{color:#c62828;font-weight:700}
.fcnote{color:var(--mut);margin-top:3px;white-space:normal}
.stale-banner{background:#c62828;color:#fff;text-align:center;padding:8px 14px;font-size:13.5px;font-weight:700}
a.chip{background:rgba(47,111,208,.08);color:var(--accd);cursor:pointer}
a.chip::after{content:"›";color:var(--acc);font-weight:800;font-size:16px}
a.chip:hover{background:rgba(47,111,208,.16)}
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
.nibody .ngs{padding:2px 0 2px 13px;border-left:3px solid rgba(47,111,208,.4);font-weight:500}
.nibody .ngpts{margin-top:14px}
.nibody .ngpts li{margin:14px 0;padding:3px 0 3px 15px;font-size:16.5px;line-height:1.9;
  color:var(--ink);border-left:2px solid rgba(47,111,208,.22)}
.nibody .ngpts li:before{display:none}
/* 漲跌分析塊（2026-08-19 每卡新增欄）：金色左框＋淡金底，與影響分析（藍系）視覺區隔 */
/* 層次斷行（2026-09-01）：第N層／其N／① 各自成行，「後續觀察」另起一行並壓低對比 */
.nln{margin-top:7px}
.nwatch{margin-top:9px;padding-top:7px;border-top:1px dashed var(--line);color:var(--ink2);font-size:14.5px}
.nwatch:before{content:"";display:inline-block}
.ngmv{margin:2px 0 6px;padding:8px 12px;border-left:3px solid var(--gold);border-radius:0 10px 10px 0;
  background:rgba(200,134,15,.07);font-size:15.5px;line-height:1.85;color:var(--ink)}
.ngmv .mvtag{display:inline-block;font-weight:700;font-size:12.5px;color:var(--gold);
  margin-right:8px;letter-spacing:.5px}
/* 【深度】精選的「為什麼值得讀」：紫色系（同深度徽章），置於摘要之後、漲跌分析之前 */
.ngwhy{margin:2px 0 6px;padding:8px 12px;border-left:3px solid #7b4fa0;border-radius:0 10px 10px 0;
  background:rgba(123,79,160,.07);font-size:15.5px;line-height:1.85;color:var(--ink)}
.ngwhy .whytag{display:inline-block;font-weight:700;font-size:12.5px;color:#7b4fa0;
  margin-right:8px;letter-spacing:.5px}
.nglinks{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.nglink{display:inline-block;background:rgba(47,111,208,.08);border:0;border-radius:8px;padding:4px 12px;font-size:13.5px;color:var(--accd);text-decoration:none}
.nglink:hover{background:rgba(47,111,208,.16);color:var(--acc)}
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
.ovtbl tr:hover td{background:rgba(47,111,208,.06)}
/* ETF 表：只凍結「代碼／名稱」一欄（識別欄），手機橫向捲動時恆可見；
   性質欄隨捲動移出（分兩張表已按性質分組，捲動時不需重複顯示），省空間好閱讀 */
.etftbl td:nth-child(2),.etftbl th:nth-child(2){position:sticky;left:0;z-index:2;background:var(--card);min-width:112px;max-width:150px;white-space:normal;box-shadow:1px 0 0 var(--line)}
.etftbl thead th:nth-child(2){z-index:3}
/* 代碼與「詳情」同一行由 .etline 排（2026-07-30 縮列高）；名稱在第二行整段換行 */
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
.netype.new{color:var(--acc);background:rgba(47,111,208,.12);border-color:rgba(47,111,208,.4)}
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
.ndoc h3{font-size:17.5px;color:var(--ink);font-weight:700;line-height:1.55;margin:26px 0 10px;padding:12px 16px;background:linear-gradient(90deg,rgba(47,111,208,.12),rgba(47,111,208,.02));border-left:3px solid var(--acc);border-radius:0 10px 10px 0}
.ndoc h4{font-size:14.5px;color:var(--accd);margin:18px 0 6px}
.ndoc p{margin:12px 0}
.ndoc ul,.ndoc ol{margin:12px 0;padding-left:0;list-style:none;counter-reset:n}
.ndoc ul li{position:relative;margin:10px 0;padding-left:20px}
.ndoc ul li:before{content:"";position:absolute;left:4px;top:12px;width:5px;height:5px;border-radius:50%;background:var(--acc)}
.ndoc ol li{position:relative;margin:14px 0;padding-left:36px;counter-increment:n}
.ndoc ol li:before{content:counter(n);position:absolute;left:0;top:2px;width:23px;height:23px;border-radius:50%;background:var(--acc);color:#fff;font-size:12px;font-weight:700;text-align:center;line-height:23px}
/* 關鍵句標記（粗體＋半透明藍底）——2026-07-18 使用者指示套用到所有內容區的重點 */
.ndoc b,.ngpts li b,.calnote b,.premkt b{color:var(--hl);background:rgba(47,111,208,.13);font-weight:700;padding:0 4px;border-radius:4px;box-decoration-break:clone;-webkit-box-decoration-break:clone}
.ndoc h2 b,.ndoc h3 b,.ndoc h4 b{color:inherit;background:none;padding:0}
.fnhl .ngpts li b{background:rgba(255,255,255,.8)}   /* 看點框本身是淺藍底——標記改半透明白保持對比 */
.ndoc a{text-decoration:none;border-bottom:1px dashed var(--acc);word-break:break-all}
.ndoc hr{border:0;border-top:1px solid var(--line);margin:22px 0}
.ndoc small,.ndoc i{color:var(--mut);font-style:normal}
.tag{display:inline-block;font-size:12px;font-weight:700;padding:1px 9px;border-radius:20px;background:rgba(47,111,208,.12);color:var(--accd);border:0;white-space:nowrap}
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
.cst.wait{color:var(--accd);background:rgba(47,111,208,.1);border-color:rgba(47,111,208,.35)}
.cst.halt{color:#8a5410;background:rgba(200,118,15,.14);border-color:rgba(200,118,15,.45)}
.creg{display:inline-block;font-size:10.5px;font-weight:800;padding:1px 6px;margin-right:6px;border-radius:5px;border:0;vertical-align:1px;white-space:nowrap}
.creg.us{color:#1d4f9c;background:rgba(47,111,208,.13);border-color:rgba(47,111,208,.4)}
.creg.eu{color:#5b3ea8;background:rgba(122,92,219,.14);border-color:rgba(122,92,219,.42)}
.creg.cn{color:#a02c2c;background:rgba(206,66,66,.13);border-color:rgba(206,66,66,.4)}
.creg.jp{color:#0f6f6b;background:rgba(23,146,140,.13);border-color:rgba(23,146,140,.42)}
.calsub{margin:16px 0 6px;font-size:14px;font-weight:800;color:var(--ink);padding-left:9px;border-left:4px solid #2f9d57}
.calsub.tw{border-left-color:#3a8a2a}
.chold{display:inline-block;font-size:10.5px;font-weight:800;padding:1px 6px;margin-left:6px;border-radius:5px;vertical-align:1px;white-space:nowrap;color:#8a5a00;background:rgba(214,158,46,.18)}
.chip.halt{color:#8a5410;background:rgba(200,118,15,.12);border-color:rgba(200,118,15,.5);font-weight:700}
/* 總經：市場溫度計（全球指標＋台股籌碼）——第一欄（指標）凍結，數值欄手機可左右捲 */
.mdtbl{font-size:14px}
.mdtbl th,.mdtbl td{padding:9px 9px;white-space:nowrap}
.mdtbl td.mdlab,.mdtbl th:first-child{position:sticky;left:0;z-index:2;background:var(--card);
  min-width:104px;max-width:150px;white-space:normal;line-height:1.3;box-shadow:1px 0 0 var(--line)}
.mdtbl thead th:first-child{z-index:3}
.mdtbl td.mdval{font-weight:700}
.mddt{display:block;font-size:11px;color:var(--mut);font-weight:400;margin-top:1px}  /* 名稱下方資料日 */
/* 資料日過期章：來源暫時抓不到、序列停在舊日期時現形（不再以舊值假裝新值） */
.mdstale{margin-left:4px;color:#c62828;font-weight:700;white-space:nowrap}  /* 同警示章紅（非漲跌色） */
.mdtbl td.mdchg,.mdtbl th.mdchg{text-align:right}
.mdn5{display:block;font-size:11.5px;font-weight:400;opacity:.85;margin-top:1px}
.mdcl{color:var(--mut);font-size:10.5px;font-weight:400;margin-right:3px}  /* 買賣超列：儲存格內自帶「前日／近5日累計」標籤（欄頭的日變化對它不適用）*/  /* 近5日疊在日變化下 */
.mdtbl th.mdchg .mdn5{color:var(--mut);opacity:1}
.mdtbl td.mdspark{padding-top:4px;padding-bottom:4px}
.spark{display:inline-block;vertical-align:middle}
.spark svg{width:86px;height:24px;display:block}
.spark.bars rect.up{fill:var(--gain)} .spark.bars rect.dn{fill:var(--loss)}
.spark.bars line.base{stroke:var(--line);stroke-width:1}
/* 指標名稱：統一純文字、非粗體（2026-07-23 使用者）；來源連結一律為下方小「官方↗」 */
.mdgname{font-weight:400;color:var(--ink)}
/* 三大法人：名稱包在大範圍展開鈕內（好按），仍非粗體 */
.mdtogbtn{display:flex;align-items:flex-start;gap:4px;width:100%;background:none;border:0;margin:0;
  padding:9px 4px 9px 0;cursor:pointer;font:inherit;font-weight:400;color:var(--ink);text-align:left;
  line-height:1.3;border-radius:7px;min-height:40px;-webkit-tap-highlight-color:rgba(47,111,208,.18)}
.mdtogbtn:hover,.mdtogbtn:active{background:rgba(47,111,208,.08)}
.mdtogbtn .mdcaret{flex:0 0 auto;color:var(--accd);font-size:14px;font-weight:800;line-height:1;
  margin-top:2px;transition:transform .15s}
.mdcaret.open{transform:rotate(90deg)}
.mdtogbtn .mdgname{flex:1 1 auto}
.mdslsm{display:inline-block;font-size:11.5px;color:var(--accd);text-decoration:none;
  border-bottom:1px dotted var(--accd);padding:1px 0}
.mdslsm:hover{color:var(--acc);border-bottom-style:solid}
tr.mdsub{display:none} tr.mdsub.show{display:table-row}
tr.mdsub td{background:#f6f9fe;border-bottom:1px solid var(--line)}
.mdtbl tr.mdsub td.mdlab{background:#f6f9fe}          /* 凍結首格用不透明底、蓋住捲動內容 */
td.mdsublab{padding-left:24px;color:var(--ink2);font-size:13px}
td.mdsublab a.mdsl{color:var(--ink2)}
.mdlv{display:inline-block;font-size:11px;font-weight:800;padding:1px 7px;border-radius:6px;
  margin-left:5px;vertical-align:1px;white-space:nowrap}
.mdlv.calm{color:#1d4f9c;background:rgba(47,111,208,.12)}
.mdlv.norm{color:#1d6b3a;background:rgba(31,157,87,.13)}
.mdlv.elev{color:#8a5410;background:rgba(200,118,15,.15)}
.mdlv.panic{color:#a02c2c;background:rgba(206,66,66,.15)}
.mdsrc{color:var(--mut);font-size:12.5px;margin:8px 0 4px;line-height:1.9}
.mdsrc b{color:var(--ink2);font-weight:700;margin-right:2px}
.mdsrc a{color:var(--accd);text-decoration:none;border-bottom:1px dotted var(--accd);padding-bottom:1px}
.mdsrc a:hover{color:var(--acc);border-bottom-style:solid}
.mdsrc .ic.plain{margin-right:3px}
/* 即將登場的新 ETF（募集／掛牌） */
.upwrap{margin-bottom:6px}
.upgrp{font-weight:700;font-size:13.5px;color:var(--accd);margin:12px 0 8px;display:flex;align-items:center;gap:5px}
.upwin{font-weight:400;font-size:12px;color:var(--mut)}
.upgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:10px}
.upcard{background:var(--pad);border:1px solid var(--line);border-radius:11px;padding:11px 13px}
.uptop{display:flex;align-items:baseline;flex-wrap:wrap;gap:6px}
.upcode{font-weight:800;font-size:14px;color:var(--ink);font-variant-numeric:tabular-nums}
.upname{font-weight:700;font-size:14.5px;color:var(--ink)}
.upname .fh{color:var(--gold);font-weight:800}
.upissuer{font-size:11.5px;color:var(--mut);background:var(--card2);border-radius:5px;padding:1px 6px}
.upmeta{margin:7px 0 5px;display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.upstat{display:inline-block;font-size:12px;font-weight:700;border-radius:7px;padding:2px 9px;white-space:nowrap}
.upstat.list{color:#1d6b3a;background:rgba(31,157,87,.14)}
.upstat.raise{color:#1d4f9c;background:rgba(47,111,208,.13)}
.upstat.now{color:#a35b00;background:rgba(224,146,0,.16)}
.upstat.pend{color:#5b6672;background:rgba(120,132,148,.14)}
.uptag{display:inline-block;font-size:11px;color:var(--mut);background:var(--card2);border-radius:5px;padding:1px 7px}
.uptag.ld{color:#1d6b3a;background:rgba(31,157,87,.09)}
/* 已核准・募集時程未定＝精簡列（2026-08-10 使用者：太長要分類；只有核准訊息不佔卡片） */
.uplist{background:var(--pad);border:1px solid var(--line);border-radius:11px;padding:3px 13px}
.uprow{display:flex;align-items:baseline;flex-wrap:wrap;gap:6px 8px;padding:8px 0;border-bottom:1px dashed var(--line)}
.uprow:last-child{border-bottom:0}
.uprow .upname{font-size:13.5px}
.upnc{font-size:11px;font-weight:700;color:#6d28a8;background:rgba(139,84,208,.12);border-radius:5px;padding:1px 7px;white-space:nowrap}
.uphintt{font-size:12px;color:var(--mut)}
.uprlink{font-size:12px;font-weight:700;color:var(--accd);text-decoration:none;white-space:nowrap;margin-left:auto}
.uprlink:hover{color:var(--acc)}
.uptheme{font-size:12.5px;color:var(--ink2);line-height:1.65;margin-bottom:8px}
.uplink{display:inline-block;font-size:12.5px;font-weight:700;color:var(--accd);background:rgba(47,111,208,.09);border-radius:8px;padding:4px 12px;text-decoration:none}
.uplink:hover{color:#fff;background:var(--acc)}
.upfoot{color:var(--mut);font-size:12px;line-height:1.75;margin:12px 0 4px}
.upnone{color:var(--mut);font-size:13px;background:var(--pad);border-radius:10px;padding:11px 14px;margin-bottom:6px}
/* ETF 詳情（底部區塊：產業分層方塊圖＋異動明細＋完整持股明細）——2026-07-30 使用者
   提供的版面架構。取代舊的「表內隱藏列展開」：整寬 colspan 列本質上就會「展開後超空」，
   且 23 檔各一份明細會把表格拉長；改成底部單一詳情區、由上表點「詳情」選定該檔。 */
.edjump{display:block;width:100%;text-align:left;background:none;border:0;padding:6px 2px 6px 0;
  cursor:pointer;font:inherit;color:inherit}
.edjump .etcode{display:block;font-weight:800;color:var(--accd)}
.edjt{display:inline-block;margin-top:2px;font-size:10.5px;color:var(--acc);
  background:rgba(47,111,208,.1);border-radius:5px;padding:1px 5px;white-space:nowrap}
.edjump:hover .edjt{color:#fff;background:var(--acc)}
.edpick{margin:2px 0 10px}
.edprow{display:flex;align-items:flex-start;gap:8px;margin-bottom:5px}
.edplab{flex:0 0 auto;min-width:3.6em;font-size:11px;color:var(--mut);padding-top:7px;
  text-align:right}
.edpset{display:flex;flex-wrap:wrap;gap:5px}
.edchip{display:flex;align-items:baseline;gap:5px;background:var(--card);border:1px solid var(--line);
  border-radius:9px;padding:5px 9px;font:inherit;font-size:12px;color:var(--ink2);cursor:pointer}
.edchip b{color:var(--accd);font-size:12.5px}
.edchip>span{color:var(--mut);font-size:11px;max-width:10em;overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap}
.edchip.on{border-color:var(--acc);background:rgba(47,111,208,.08);box-shadow:inset 0 0 0 1px var(--acc)}
.edhead{font-size:12px;color:var(--mut);line-height:1.85;margin-bottom:9px}
.edhead b{color:var(--accd);font-size:13.5px}
.edblk{background:var(--card);border:1px solid var(--line);border-radius:13px;padding:11px 12px 12px;
  margin-bottom:10px}
.edblk.tbl{max-width:820px}
.edt{font-size:13.5px;font-weight:800;color:var(--ink);margin-bottom:2px}
.edtsub{font-size:11.5px;font-weight:400;color:var(--mut);margin-left:2px}
.edfoot{font-size:11.5px;color:var(--mut);line-height:1.75;margin-top:8px}
/* 無異動：整張深色圖與明細表都收掉，只留一句話——3 格撐 370px 或空圖佔一大塊都很醜
   （2026-07-30 使用者：「沒有變動就要讓比例感覺收斂一些」） */
.edempty{font-size:12.5px;color:var(--mut);background:var(--pad);border-radius:9px;
  padding:10px 12px;margin-top:8px}
/* 期貨部位：持股＋期貨名目的合計一行（2026-10-21；00987D 看多時把美債曝險拉到 120%～130%） */
.futexp{font-size:12.5px;color:var(--ink);background:var(--pad);border-radius:9px;
  padding:7px 11px;margin-top:8px;line-height:1.6}
.futexp b{color:var(--accd);font-size:13.5px}
/* 期貨只有一兩列：名稱與轉倉月份允許換行（手機 390px 時「美國三十年期政府公債」與
   「2026-09 → 2026-12」會把最右欄擠出畫面） */
.futtbl .edname{max-width:none;white-space:normal}
.futtbl .futroll{white-space:normal}
/* 方塊圖：容器固定高度，方塊以百分比絕對定位（座標由 Python squarify 算好） */
/* 方塊圖＝深色「圖表卡」（2026-07-30 使用者：淺底粉紅粉綠一片好醜）。
   深底的好處是同一組色階不必靠高飽和也能拉出層次、文字一律白色即可讀，
   雜訊（灰色產業底板、每格外框線）全部拿掉：產業以間距＋一行小標區隔，
   格與格之間留「畫布色」縫（同色 border 吃進格內），不畫任何線。 */
.tmfig{background:#14171b;border-radius:12px;padding:11px 11px 12px;margin-top:9px}
.tmleg{display:flex;flex-wrap:wrap;align-items:center;gap:4px 14px;margin-bottom:9px}
.tmlg{display:inline-flex;align-items:center;gap:6px;font-size:11px;color:rgba(255,255,255,.78)}
.tmlg>i{width:10px;height:10px;border-radius:3px;display:inline-block}
.tmlgn{font-size:10.5px;color:rgba(255,255,255,.42)}
.tmap{position:relative;width:100%;height:240px;overflow:hidden}  /* 實際高度由 JS 依格數收斂 */
.tmi.agg i,.tmi.agg u{font-weight:600;color:rgba(255,255,255,.62)}
/* 亮度 ∝ 加減碼幅度：色相只表方向、亮度只表幅度，兩者不會互相冒充
   （若把亮度挪去表示個股當日漲跌就會衝突，別改）。rgba 由前端逐格算成 inline style。 */
.tmi{position:absolute;border-radius:5px;overflow:hidden;padding:2px;display:flex;
  flex-direction:column;align-items:center;justify-content:center;text-align:center;
  line-height:1.32;border:1.5px solid #14171b;box-sizing:border-box}
.tmi.new,.tmi.out{outline:1px dashed rgba(255,255,255,.5);outline-offset:-4px}
.tmi i,.tmi em,.tmi u,.tmi s{text-shadow:0 1px 2px rgba(0,0,0,.35)}
.tmi i{font-style:normal;font-size:11px;font-weight:700;color:#fff;max-width:100%;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tmi em{font-style:normal;font-size:10.5px;color:rgba(255,255,255,.84);max-width:100%;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tmi u{text-decoration:none;font-size:11px;font-weight:600;color:rgba(255,255,255,.92);
  white-space:nowrap}
.tmi s{text-decoration:none;font-size:9.5px;color:rgba(255,255,255,.62);white-space:nowrap}
.tmnone{display:flex;align-items:center;justify-content:center;height:100%;padding:0 18px;
  color:rgba(255,255,255,.55);font-size:12.5px;text-align:center}
/* 異動表／完整持股表：兩行式儲存格（主值在上、副值灰字在下），手機也塞得下四欄 */
.edscroll{overflow-x:auto;margin-top:9px}
.edscroll.tbl{max-width:820px}
.chgtbl,.hldtbl{width:100%;border-collapse:collapse;font-size:12.5px}
.chgtbl th,.hldtbl th{font-size:11.5px;color:var(--mut);font-weight:700;text-align:left;
  padding:5px 6px;border-bottom:1px solid var(--line);white-space:nowrap;vertical-align:top}
.chgtbl th.num,.hldtbl th.num{text-align:right}
.chgtbl td,.hldtbl td{padding:7px 6px;border-bottom:1px solid var(--line);vertical-align:middle}
.chgtbl td.num,.hldtbl td.num{text-align:right;white-space:nowrap}
.chgtbl tbody tr:hover,.hldtbl tbody tr:hover{background:var(--pad)}
th.csk,th.hsk{cursor:pointer}
th.csk:hover,th.hsk:hover,th.csk.on,th.hsk.on{color:var(--acc)}
.ski{font-size:9.5px;color:var(--mut);font-weight:400}
th .sub{display:block;font-weight:400;color:var(--mut);font-size:10.5px}
.edcode{font-weight:800;color:var(--accd);font-size:13px}
.edname{display:block;font-size:11px;color:var(--mut);max-width:8.5em;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.edmain{font-weight:800;font-size:13.5px}
.edsub2{display:block;font-size:11px;color:var(--mut);font-weight:400}
/* 標的簡介：獨立整寬一列（塞在識別欄裡會把列高撐爆），與其上的資料列視為同一列 */
.hldtbl tr.hasintro>td{border-bottom:0;padding-bottom:2px}
.hldtbl tr.introw>td{padding:0 6px 8px}
.hldtbl tr.introw .hintro{margin:0}
.kpill{display:inline-block;font-size:11px;font-weight:700;border-radius:999px;padding:2px 9px;
  white-space:nowrap}
.kpill.add,.kpill.new{color:#b3312c;background:rgba(211,58,52,.12)}
.kpill.cut,.kpill.out{color:#1f7a43;background:rgba(31,157,87,.12)}
.edsearch{width:min(100%,290px);margin-top:6px;padding:7px 11px;font:inherit;font-size:12.5px;
  border:1px solid var(--line);border-radius:9px;background:var(--pad);color:var(--ink)}
.edpg{display:flex;align-items:center;gap:12px;justify-content:center;margin-top:10px;
  font-size:12px;color:var(--mut)}
.edpg button{font:inherit;font-size:12px;color:var(--accd);background:var(--pad);
  border:1px solid var(--line);border-radius:8px;padding:5px 12px;cursor:pointer}
.edpg button:disabled{color:var(--mut);opacity:.5;cursor:default}
.etftbl .edjump{padding:4px 2px;min-height:0;line-height:1.3}
.etline{display:flex;align-items:baseline;gap:5px;white-space:nowrap}
.etline .etcode{font-weight:800;color:var(--accd);font-size:13.5px}
.etftbl .etname{display:block;font-size:11.5px;color:var(--ink2);line-height:1.35;
  margin-top:1px;white-space:normal;min-width:104px}
.etftbl .edjt{margin-top:0}
/* Yahoo 連結移到「性質」欄（原本疊在識別欄第四行，把每一列撐到近 180px 高） */
.etyh{display:block;margin-top:4px;font-size:10.5px;color:var(--acc);text-decoration:none;
  white-space:nowrap}
.etyh:hover{text-decoration:underline}
.hnew{color:#8a5410;background:rgba(200,118,15,.14);margin-left:5px;font-size:10px;border-radius:5px;padding:0 4px}
/* 全球型 ETF：本表僅台股部位（權重合計遠低於 100%）——橘標誠實揭露，避免被讀成完整清單 */
.hpartial{margin-left:6px;font-size:10.5px;color:#8a5410;background:rgba(200,118,15,.14);border-radius:5px;padding:1px 5px;white-space:nowrap;cursor:help}
/* 海外持股當地還沒收盤（2026-10-21：只用已收盤的價格，盤中價一律不用） */
.hpend{color:var(--mut);font-size:11px;font-weight:400;cursor:help}
/* 跨源驗證章：🟢 雙源相符／單源未驗證／⚠ 兩源不符（詳情在 tooltip） */
.hvok{margin-left:5px;font-size:10.5px;color:#1f7a43;background:rgba(31,157,87,.12);border-radius:5px;padding:1px 5px;white-space:nowrap;cursor:help}
.hvone{margin-left:5px;font-size:10.5px;color:var(--mut);background:rgba(120,120,120,.12);border-radius:5px;padding:1px 5px;white-space:nowrap;cursor:help}
.hvbad{margin-left:5px;font-size:10.5px;color:#c62828;background:rgba(198,40,40,.1);border-radius:5px;padding:1px 5px;white-space:nowrap;cursor:help;font-weight:700}
.hgone{color:var(--mut);background:rgba(120,120,120,.12)}

/* ETF 數據追蹤 */
.etcat{display:inline-block;white-space:nowrap;font-size:11px;color:var(--accd);border:0;background:rgba(47,111,208,.1);border-radius:5px;padding:1px 6px}
.etfnote{color:var(--mut);font-size:12.5px;margin-top:12px;line-height:1.8;border-top:1px solid var(--line);padding-top:8px}
/* 欄位口徑小標（市價 vs 淨值）——2026-07-27 使用者對 Yahoo 淨值報酬時發現差異，於欄名直接標明 */
.colq{display:block;font-size:9.5px;font-weight:400;opacity:.72;letter-spacing:.02em;margin-top:1px}
.estdivln{margin-top:3px}                       /* 「預估 X*」另起一行，與實際配息金額分開更清楚 */
.estdiv{display:inline-block;font-size:11.5px;color:#8a5410;background:rgba(200,118,15,.14);border:0;border-radius:6px;padding:1px 6px;white-space:nowrap}
.estdiv sup{font-weight:800}
.estmk{color:#c8760f;font-weight:800;cursor:help}
.rbase{font-size:10.5px;color:var(--mut);font-weight:400;margin-top:2px;white-space:nowrap;cursor:help}
/* 當日漲跌格的「除息」標記：該日基準為除息參考價（非前收），避免配息被讀成跌幅 */
.exdiv{margin-left:4px;font-size:10px;color:#8a5410;background:rgba(200,118,15,.14);border-radius:5px;padding:0 4px}
.rsrc{display:inline-block;font-size:10.5px;padding:1px 5px;margin-left:6px;border-radius:5px;border:0;
  color:var(--mut);background:rgba(138,127,107,.12);vertical-align:1px}
/* ⑤ details：基金卡去框 → 全寬清單項＋細分隔線 */
#details .st{margin-bottom:0}
.pendcard .sub{line-height:1.9}
/* 詳情卡輕色塊卡墊（2026-07-22 使用者指示：全平面細線列直式難掃讀 → 每檔一個極淺灰圓角色塊） */
.fund{background:var(--pad);border:0;border-radius:12px;padding:0 14px;margin:0 0 8px;box-shadow:none}
.fund:last-of-type{margin-bottom:0}
.fund:target{background:#e9f1fc}
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
/* 2026-07-31 踩坑：隱藏規則原本只寫 `.fund.fhide`，ETF 卡是 `.etfd`——分類 chips
   與搜尋照樣加了 fhide class，畫面卻毫無反應，使用者回報「按鈕都不能按」。
   同理 `.eg`（ETF 分類 chip）當初沒併進 `.fg` 的樣式，連選中狀態都看不出來。
   新增這類工具列時，**三處都要一起加**：隱藏規則、chip 樣式、搜尋框樣式。 */
.fund.fhide,.etfd.fhide,.edchip.fhide,.fnit.fhide{display:none}
/* 詳情篩選列 */
.fundbar{display:flex;gap:9px;align-items:center;flex-wrap:wrap;margin-top:12px}
.fundbar #fsearch,.fundbar #esearch,.fundbar #ssearch,.fundbar #nsearch{flex:1;min-width:170px;max-width:330px;
  border:1px solid var(--line);border-radius:9px;-webkit-appearance:none;appearance:none;
  padding:7px 12px;font-size:14.5px;background:var(--card2);color:var(--ink)}
.fundbar #fsearch:focus,.fundbar #esearch:focus,.fundbar #ssearch:focus,.fundbar #nsearch:focus{outline:none;border-color:var(--acc)}
.fgchips{display:flex;gap:5px}
.fg,.eg,.sg,.fexp{background:var(--card2);color:var(--accd);border:0;border-radius:18px;
  padding:6px 13px;cursor:pointer;font-size:13.5px;font-weight:700}
.fg:hover,.eg:hover,.sg:hover,.fexp:hover{background:rgba(47,111,208,.12)}
.fg.on,.eg.on,.sg.on{background:var(--acc);color:#fff}
/* 新聞・社群篩選列（2026-08-15）＝比照基金/ETF 詳情的 .fundbar 版式，僅收斂底距 */
#socbar,#newsbar{margin:2px 0 12px}
.fhead{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;align-items:flex-start}
.fhead h2{font-size:19px;margin:0 0 4px} .gl{display:inline-block;white-space:nowrap;font-size:12px;color:#fff;background:var(--acc);padding:2px 8px;border-radius:20px;vertical-align:middle}
.sub{color:var(--mut);font-size:12.5px}
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
a.hnm{font-weight:700;color:var(--accd);text-decoration:underline;text-underline-offset:3px;text-decoration-color:rgba(43,95,176,.4)}
a.hnm:hover{color:var(--acc);text-decoration-color:var(--acc)}
a.tk{text-decoration:none} a.tk:hover{color:var(--acc)}
.tk{font-size:11px;color:var(--accd)} .pill{display:inline-block;white-space:nowrap;font-size:11px;color:var(--mut);background:var(--card2);border:0;border-radius:5px;padding:1px 5px;margin-left:4px}
.hintro{color:var(--mut);font-size:12.5px;margin-top:3px}
.foot{color:var(--mut);font-size:12.5px;line-height:1.8;margin-top:22px;border-top:1px solid var(--line);padding-top:12px}
/* 籌碼雷達入口（2026-10-14 使用者：放在不顯眼的角落、不用密語）——頁尾右下角淡色小點 */
.fx{float:right;color:#d5dae2;text-decoration:none;font-size:16px;line-height:1;padding:8px 2px 8px 18px}
.backtop{position:fixed;right:18px;bottom:18px;z-index:40;background:#fff;color:var(--accd);border:0;border-radius:22px;padding:9px 15px;font-size:13.5px;text-decoration:none;box-shadow:0 2px 10px rgba(30,50,90,.22)}
.backtop:hover{color:var(--acc)}
@media(max-width:720px){.wrap{padding:6px 14px 46px}.cols{grid-template-columns:1fr}.rets{grid-template-columns:repeat(3,1fr)}.navbox{text-align:left}
  .tb-meta,.tb-lamp{display:none}.ixc{min-width:110px}.section{padding:20px 0 12px}
  .tb-in{padding:7px 14px}.mk{padding:6px 8px 8px;font-size:15.5px}body{font-size:16.5px}
  #overview .st::after,#macro-cal .st::after,#etfwatch .st::after,#macro-data .st::after{content:"↔ 表格可左右滑動";font-weight:400;font-size:12px;color:var(--mut)}
  .backtop{right:10px;bottom:10px;padding:7px 12px;font-size:12.5px}}
/* ⑥ 復華新聞・社群 */
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
.fnpush.fnyt{flex-basis:auto;min-width:48px;padding:3px 7px;color:#e6504c;
  background:rgba(230,80,76,.10);border-color:rgba(230,80,76,.35)}
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
// 分頁內各段（2026-09-24 起全部顯示）：頂欄標籤＝跳段目錄。JS 負責三件事——
// ①點標籤捲到該段；②捲動時自動標亮目前所在段（手機橫捲目錄同步捲到可見）；③閱讀進度條。
function tbh(){return parseInt(getComputedStyle(document.documentElement).getPropertyValue('--tbh'))||64}
function visSecs(){return [...document.querySelectorAll('.sec[data-sec]')].filter(e=>e.offsetParent)}
let spyLock=0;
function markSec(name){const r=name&&document.getElementById('sec-'+name);
  if(!r||r.checked)return;r.checked=true;
  const l=document.querySelector('.tb-nav .sl[for="sec-'+name+'"]'),nav=l&&l.parentElement;
  if(nav&&nav.scrollWidth>nav.clientWidth)
    nav.scrollTo({left:Math.max(0,l.offsetLeft-nav.clientWidth/2+l.offsetWidth/2),behavior:'smooth'})}
function spy(){if(Date.now()<spyLock)return;const secs=visSecs();if(!secs.length)return;
  const y=tbh()+40;let cur=secs[0];
  for(const e of secs){if(e.getBoundingClientRect().top<=y)cur=e}
  if(innerHeight+scrollY>=document.documentElement.scrollHeight-4)cur=secs[secs.length-1];
  markSec(cur.dataset.sec)}
document.querySelectorAll('.tb-nav .sl').forEach(l=>l.addEventListener('click',()=>{
  const n=(l.getAttribute('for')||'').replace('sec-','');
  const el=visSecs().find(e=>e.dataset.sec===n);if(!el)return;
  spyLock=Date.now()+900;
  scrollTo({top:Math.max(0,el.getBoundingClientRect().top+scrollY-tbh()+4),behavior:'smooth'})}));
addEventListener('scroll',spy,{passive:true});addEventListener('resize',spy);
document.querySelectorAll('.mkradio').forEach(r=>r.addEventListener('change',()=>{
  scrollTo({top:0,behavior:'instant'});setTimeout(spy,80)}));   // 換主分頁＝從該頁頂端讀起
setTimeout(spy,0);
(function(){const bar=document.getElementById('rprog');if(!bar)return;
  const upd=()=>{const h=document.documentElement.scrollHeight-innerHeight;
    bar.style.width=(h>40?Math.min(100,Math.max(0,scrollY/h*100)):0)+'%';};
  upd();addEventListener('scroll',upd,{passive:true});addEventListener('resize',upd);})();
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
// 新聞・社群篩選列（2026-08-15）：比照基金/ETF 詳情工具列＝關鍵字＋分類 chips 共用 apply
//（新聞列 data-ncat 可多組：空白分隔；社群列 data-fcat 單組）
[['newsbar','nsearch','.fnnews',(r,f)=>((r.dataset.ncat||'').split(' ').includes(f))],
 ['socbar','ssearch','.fnsoc',(r,f)=>r.dataset.fcat===f]].forEach(([bid,qid,sel,hit])=>{
  const bar=document.getElementById(bid);if(!bar)return;
  const q=document.getElementById(qid);let f='all';
  const apply=()=>{const kw=q?q.value.trim().toLowerCase():'';
    document.querySelectorAll(sel).forEach(r=>{
      const okKw=!kw||(r.textContent||'').toLowerCase().includes(kw);
      const okF=f==='all'||hit(r,f);
      r.classList.toggle('fhide',!(okKw&&okF));});};
  if(q)q.addEventListener('input',apply);
  bar.querySelectorAll('.sg').forEach(b=>b.onclick=()=>{
    bar.querySelectorAll('.sg').forEach(x=>x.classList.remove('on'));
    b.classList.add('on');f=b.dataset.f||'all';apply();});});
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
  // 附屬展開列（總經三大法人的 .mdsub）是「跟著前一列走」的整寬列：不可獨立參與排序
  //（否則會與母列脫鉤；且它只有一個 colspan 欄，cells[i] 為 undefined 會讓整個排序爆掉）
  const main=Array.from(tb.rows).filter(r=>!r.classList.contains('mdsub'));
  const det=new Map(); main.forEach(r=>{const n=r.nextElementSibling;
    if(n&&n.classList.contains('mdsub'))det.set(r,n);});
  main.sort((a,b)=>{
    const ac=a.cells[i],bc=b.cells[i];
    const av=parseFloat(ac&&ac.dataset.v),bv=parseFloat(bc&&bc.dataset.v);
    const an=isNaN(av),bn=isNaN(bv);
    if(an&&bn)return 0; if(an)return 1; if(bn)return -1;
    return desc?bv-av:av-bv;
  }).forEach(r=>{tb.appendChild(r);const d=det.get(r);if(d)tb.appendChild(d);});
});
// 投資策略兩行截斷 ↔ 展開
document.querySelectorAll('.strat').forEach(s=>s.onclick=()=>s.classList.toggle('open'));
// 市場溫度計「三大法人」名稱＝大範圍展開鈕，展開/收合外資／投信／自營商分項
document.querySelectorAll('.mdtogbtn').forEach(b=>b.addEventListener('click',e=>{
  e.stopPropagation();const g=b.dataset.grp;
  const open=b.querySelector('.mdcaret').classList.toggle('open');
  b.setAttribute('aria-expanded',open?'true':'false');
  document.querySelectorAll('tr.mdsub[data-grp="'+g+'"]').forEach(r=>r.classList.toggle('show'));
}));
// 儀表板逾期未重建警告——CI 全停擺時 HTML 不會再重生、上面的 ⚠ 也不會更新，
// 由瀏覽器端比對「產表時間 vs 現在」補上最後一道防線。
// 2026-08-03 加「盤後時窗」細分：GitHub cron 實測遲 1~3 小時、偶爾整班消失——
// 平日 16:40 後頁面仍是 15:40 前產的（或 22:50 後仍是 22:00 前產的）就直說
// 「盤後更新未生效」。伺服器端紅章要有新建表才進得了頁面，CI 整晚沒跑時只有這裡看得到。
(function(){const g=document.querySelector('[data-gen]');if(!g)return;
  const warn=function(t){const b=document.createElement('div');b.className='stale-banner';
    b.textContent=t;document.body.prepend(b)};
  const d=new Date(g.dataset.gen.slice(0,10).replace(/\//g,'-')+'T00:00:00+08:00');
  const days=Math.floor((Date.now()-d)/864e5);
  if(days>2){warn('⚠ 本儀表板已 '+days+' 天未重建（每日 CI 可能停擺），以下資料可能過期——請跑「全部更新」或檢查 GitHub Actions');return}
  // 盤後時窗（台北牆鐘＝UTC+8 固定，台灣無日光節約：+8h 後取 getUTC* 欄位）
  const gen=new Date(g.dataset.gen.replace(/\//g,'-').replace(' ','T')+':00+08:00');
  if(isNaN(gen))return;
  const tw=new Date(Date.now()+288e5), gtw=new Date(gen.getTime()+288e5);
  if(tw.getUTCDay()===0||tw.getUTCDay()===6)return;               // 週末不警示
  const hm=tw.getUTCHours()*60+tw.getUTCMinutes();
  const sameDay=tw.getUTCFullYear()===gtw.getUTCFullYear()&&tw.getUTCMonth()===gtw.getUTCMonth()&&tw.getUTCDate()===gtw.getUTCDate();
  const ghm=sameDay?gtw.getUTCHours()*60+gtw.getUTCMinutes():-1;  // 非今日產表＝早於任何時窗
  if(hm>=1000&&ghm<940)                                           // 16:40 後 vs 產表早於 15:40
    warn('⚠ 今日 15:40 盤後數據（三大法人・ETF 當日漲跌）尚未上線——本頁產表於 '+g.dataset.gen+'，GitHub CI 可能延遲，稍後重新整理；若今日台股休市請忽略');
  else if(hm>=1370&&ghm<1320)                                     // 22:50 後 vs 產表早於 22:00
    warn('⚠ 今晚夜間數據（融資融券・基金NAV）尚未上線——本頁產表於 '+g.dataset.gen+'，GitHub CI 可能延遲；若今日台股休市請忽略');
})();
// 長開分頁提示（2026-08-14 多人化 Phase 1-⑤）：上面各種逾期橫幅只在「載入當下」算一次，
// 分頁開著不關的人（多人使用必有）永遠看不到後續警示——每 30 分自查「載入至今」時長，
// 逾 6 小時提示重新整理。用 Date.now() 差值（裝置睡醒後下一輪 tick 即補判）；只提示一次、
// 不自動 reload（避免打斷閱讀），樣式沿用 .stale-banner。
(function(){const t0=Date.now();let shown=false;
  setInterval(function(){if(shown)return;
    const h=(Date.now()-t0)/36e5;
    if(h>=6){shown=true;const b=document.createElement('div');b.className='stale-banner';
      b.textContent='ℹ️ 本頁已開啟超過 '+Math.floor(h)+' 小時，資料可能已更新——請重新整理取得最新內容';
      document.body.prepend(b)}},18e5);
})();
// ── ETF 持股詳情＆異動：每檔一張可收合卡片（比照基金詳情；2026-07-31 使用者指示） ──
// 內容延遲渲染——23 檔各含方塊圖＋兩張表，一次全建進 DOM 會讓頁面又大又慢；
// 第一次展開才建，之後保留。每張卡各自保有搜尋／排序／分頁狀態（存在 ST[code]）。
(function(){
  var EH=((window.__EH||{}).etfs)||{}, INTRO=((window.__EH||{}).intro)||{};
  var root=document.getElementById('etf-detail');
  if(!root||!Object.keys(EH).length)return;
  var KIND={add:'加碼',cut:'減碼',new:'新增',out:'出清'}, PER=15, MVN=15, ST={};
  function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
  function grp(x){return String(x).replace(/\B(?=(\d{3})+(?!\d))/g,',')}
  function amt(v){if(v==null)return '—';var a=Math.abs(v),s=v>0?'+':'-';
    if(a>=1e8)return s+(a/1e8).toFixed(1)+' 億';
    if(a>=1e4)return s+grp(Math.round(a/1e4))+' 萬';
    return s+grp(Math.round(a))+' 元'}
  function lots(v){if(v==null)return '—';var a=Math.abs(v),s=v>0?'+':'-';
    if(a>=1000)return s+grp(Math.round(a/1000))+' 張';
    return s+grp(Math.round(a))+' 股'}
  function pct(v,d,u){if(v==null)return '<span class="na">—</span>';
    var c=v>0?'gain':(v<0?'loss':'flat');
    return '<span class="'+c+'">'+(v>0?'+':(v<0?'-':''))+Math.abs(v).toFixed(d)+(u||'')+'</span>'}
  function num(v,d){return v==null?'—':grp(v.toFixed(d==null?2:d))}
  function st(c){return ST[c]||(ST[c]={msk:'lots',msd:-1,hsk:'w',hsd:-1,pg:1,q:'',mvall:false})}
  // 漲跌的報價日（2026-10-21 使用者決定：一律用最新交易日；與持股快照日不同時兩個日期都標）
  function pdTag(e){
    if(!e.pd)return '・漲跌更新中';
    if(e.pd===e.d)return '・漲跌為同日收盤';
    return '・漲跌為 '+esc(e.pd)+' 收盤 <span class="hpartial" title="持股是 '+esc(e.d)
      +' 的揭露，漲跌與收盤價是 '+esc(e.pd)+' 的收盤；貢獻度＝'+esc(e.d)+' 的權重 × '
      +esc(e.pd)+' 的漲跌">不同日</span>'}

  function shell(){return ''
    +'<div class="edblk"><div class="edt">持股異動 <span class="edtsub mvsub"></span></div>'
    +'<div class="tmfig"><div class="tmleg">'
    +'<span class="tmlg"><i style="background:#e6504c"></i>加碼／新增</span>'
    +'<span class="tmlg"><i style="background:#159c94"></i>減碼／出清</span>'
    +'<span class="tmlgn">色塊越亮＝幅度越大・虛線框＝新增或出清</span></div>'
    +'<div class="tmap"></div></div>'
    +'<div class="edfoot basis"></div>'
    +'<div class="edempty" hidden></div>'
    +'<div class="edscroll tbl mvtbl"><table class="chgtbl"><thead><tr><th>股票</th>'
    +'<th class="num csk" data-k="lots">張數 <span class="ski">⇅</span></th>'
    +'<th class="num csk" data-k="amt">金額 <span class="ski">⇅</span></th>'
    +'<th class="num">類型</th></tr></thead><tbody class="mvb"></tbody></table></div>'
    +'<div class="edpg"><button type="button" class="mvmore" hidden></button></div>'
    +'<div class="edfoot mvfoot"></div></div>'
    // 期貨部位（2026-10-21）：期貨只付保證金、權重是名目曝險，不混進持股；有期貨的 ETF 才出現
    +'<div class="edblk tbl futblk" hidden><div class="edt">期貨部位 <span class="edtsub fusub"></span></div>'
    +'<div class="futexp" hidden></div>'
    +'<div class="edscroll tbl"><table class="chgtbl futtbl"><thead><tr>'
    +'<th>合約<span class="sub">月份</span></th>'
    +'<th class="num">口數<span class="sub">多單／空單</span></th>'
    +'<th class="num">名目曝險<span class="sub">占淨值</span></th>'
    +'<th class="num">比上次<span class="sub">加減口數</span></th></tr></thead>'
    +'<tbody class="fub"></tbody></table></div>'
    +'<div class="edfoot fufoot"></div></div>'
    +'<div class="edblk tbl"><div class="edt">完整持股明細</div>'
    +'<div class="edtsub hsub"></div>'
    +'<input class="edsearch hq" type="search" placeholder="搜尋代號或名稱" aria-label="搜尋代號或名稱">'
    +'<div class="edscroll tbl"><table class="hldtbl"><thead><tr>'
    +'<th>代號<span class="sub">名稱</span></th>'
    +'<th class="num hsk" data-k="chg">漲跌幅<span class="sub">收盤價</span> <span class="ski">⇅</span></th>'
    +'<th class="num hsk" data-k="w">權重<span class="sub">股數</span> <span class="ski">⇅</span></th>'
    +'<th class="num hsk" data-k="c">貢獻度<span class="sub" title="貢獻度＝權重 × 個股當日漲跌 ÷ 100，'
    +'單位為百分點；合計不會剛好等於 ETF 市價漲跌（現金／期貨部位、費用、揭露時點差在殘差）">ⓘ pp</span>'
    +' <span class="ski">⇅</span></th></tr></thead><tbody class="hb"></tbody></table></div>'
    +'<div class="edpg"><button type="button" class="hprev">« 上一頁</button>'
    +'<span class="hpgn">1 / 1</span><button type="button" class="hnext">下一頁 »</button></div>'
    +'<div class="edfoot hfoot"></div></div>'}

  function markSort(box,sel,k,d){
    box.querySelectorAll(sel).forEach(function(th){
      var on=th.dataset.k===k; th.classList.toggle('on',on);
      var i=th.querySelector('.ski'); if(i)i.textContent=on?(d<0?'↓':'↑'):'⇅'})}

  function paintTmap(box,e){
    var wrap=box.querySelector('.tmfig'), map=box.querySelector('.tmap'),
        none=box.querySelector('.edempty'), tbl=box.querySelector('.mvtbl'),
        fo=box.querySelector('.basis'), tm=e.tm||[];
    var msg=e.mn?(e.nq>=(e.mn/2)
        ?'本次異動多為海外持股（無台股報價），方塊圖無法計算面積——請看下方明細表。'
        :'本次異動集中在少數標的，其餘幅度過小、方塊圖呈現不出比例——請看下方明細表。')
      :(e.p?'本次揭露與前一揭露日相比，持股股數沒有變化。'
             +(e.fc?'期貨部位有變動，見下方「期貨部位」。':'')
           :'首次揭露，尚無可對比的前一揭露日——明日起可看加減碼。');
    wrap.hidden=!tm.length; tbl.hidden=!tm.length;
    fo.style.display=tm.length?'':'none';
    none.hidden=!!tm.length; none.textContent=msg;
    if(!tm.length){map.innerHTML='';return}
    var H=e.th||240; map.style.height=H+'px';
    var W=map.clientWidth||300, h='', maxv=0;
    tm.forEach(function(it){var v=Math.abs((e.basis==='amount'?it.a:it.sh)||0);if(v>maxv)maxv=v});
    tm.forEach(function(it){
      var pw=it.w/100*W, ph=it.h/100*H, lab='';
      var val=e.basis==='amount'?amt(it.a):lots(it.sh);
      var mag=Math.abs((e.basis==='amount'?it.a:it.sh)||0);
      // 亮度上限 0.80：白字對比紅 5.2:1／綠松 4.7:1（AA 正文 4.5:1）；併格固定壓低不搶眼
      var al=it.agg?0.20:(0.28+0.52*(maxv?Math.pow(mag/maxv,0.55):0));
      var dir=(it.k==='add'||it.k==='new')?'add':'cut';
      var rgb=dir==='add'?'230,80,76':'21,156,148';
      var tint='background:rgba('+rgb+','+al.toFixed(3)+');'
        +'border-color:rgba('+rgb+','+Math.min(1,al+0.17).toFixed(3)+');';
      var nm=esc((it.n&&it.n!==it.s)?it.n:''), cd=esc(it.s||'');
      var tag=(it.k==='new'||it.k==='out')?'<s>'+KIND[it.k]+'</s>':'';
      if(it.agg)lab='<i>'+esc(it.n||'')+'</i><u>'+val+'</u>';
      else if(pw>=54&&ph>=58)lab='<i>'+cd+'</i>'+(nm?'<em>'+nm+'</em>':'')+'<u>'+val+'</u>'+tag;
      else if(pw>=76&&ph>=40)lab='<i>'+cd+(nm?' '+nm:'')+'</i><u>'+val+'</u>';
      else if(pw>=48&&ph>=26)lab='<i>'+cd+'</i>'+(nm?'<em>'+nm+'</em>':'');
      else lab='<i>'+cd+'</i>';
      h+='<div class="tmi '+(it.agg?'agg ':'')+it.k+'" style="'+tint
        +'left:'+it.x+'%;top:'+it.y+'%;width:'+it.w+'%;height:'+it.h+'%"'
        +' title="'+esc((it.agg?it.n:it.s+' '+it.n)+'　'+KIND[it.k]+' '+val
          +(it.ind?'（'+it.ind+'）':''))+'">'+lab+'</div>'});
    map.innerHTML=h;
    fo.textContent=(e.basis==='amount'
      ?'面積與亮度依異動金額（Δ股數 × '+(e.pd?e.pd+' ':'')+'收盤）。'
      :'本檔含無台股報價的持股（海外／債券），面積與亮度改以 Δ股數計，跨市場不宜直接比大小；'
       +'金額欄僅台股部位有值。')+'　'+(e.an||'')}

  function paintMoves(box,e){
    var s=st(box.dataset.c), tb=box.querySelector('.mvb'), rows=(e.mv||[]).slice();
    rows.sort(function(a,b){var i=s.msk==='amt'?3:2,av=a[i],bv=b[i];
      if(av==null&&bv==null)return 0; if(av==null)return 1; if(bv==null)return -1;
      return s.msd*(av-bv)});
    var shown=s.mvall?rows:rows.slice(0,MVN), more=box.querySelector('.mvmore');
    if(rows.length>MVN){more.hidden=false;
      more.textContent=s.mvall?('收合，只看前 '+MVN+' 檔 ▴'):('展開全部 '+rows.length+' 檔異動 ▾')}
    else more.hidden=true;
    tb.innerHTML=shown.map(function(r){
      return '<tr><td><span class="edcode">'+esc(r[0])+'</span>'
        +'<span class="edname">'+esc(r[1]===r[0]?'':r[1])+'</span></td>'
        +'<td class="num"><span class="edmain '+(r[2]>0?'gain':'loss')+'">'+lots(r[2])+'</span></td>'
        +'<td class="num"><span class="edsub2">'+amt(r[3])+'</span></td>'
        +'<td class="num"><span class="kpill '+r[4]+'">'+KIND[r[4]]+'</span></td></tr>'}).join('')
      ||'<tr><td colspan="4" class="na">本次無持股異動。</td></tr>';
    var kc={}; (e.mv||[]).forEach(function(r){kc[r[4]]=(kc[r[4]]||0)+1});
    var bits=[]; ['add','cut','new','out'].forEach(function(k){if(kc[k])bits.push(KIND[k]+' '+kc[k])});
    box.querySelector('.mvsub').textContent=e.mn
      ?('共 '+e.mn+' 檔異動'+(bits.length?'（'+bits.join('／')+'）':'')):'本次無異動';
    var notes=[];
    if(e.hid)notes.push('另有 '+e.hid+' 檔幅度過小、方塊圖畫不出標籤，未入圖');
    if(e.nq)notes.push('另有 '+e.nq+' 檔海外持股無台股報價，無法計入方塊圖');
    if(e.mr)notes.push('異動檔數超過清單上限，另有 '+e.mr+' 檔小額異動未列於本表');
    if(e.xs)notes.push('本次揭露來源（'+e.xs[1]+'）與前一揭露日（'+e.xs[0]
      +'）不同，兩者揭露範圍未必一致 → 僅比對共同持股的加減碼，新增／出清不予判定');
    box.querySelector('.mvfoot').textContent=notes.length?(notes.join('；')+'。'):'';
    markSort(box,'.chgtbl th.csk',s.msk,s.msd)}

  function paintHold(box,e){
    var s=st(box.dataset.c), tb=box.querySelector('.hb'), KI={w:2,chg:5,c:6};
    var rows=(e.al||[]).filter(function(r){
      return !s.q||(String(r[0])+' '+String(r[1])).toLowerCase().indexOf(s.q)>=0});
    var i=KI[s.hsk];
    rows.sort(function(a,b){var av=a[i],bv=b[i];
      if(av==null&&bv==null)return 0; if(av==null)return 1; if(bv==null)return -1;
      return s.hsd*(av-bv)});
    var tot=Math.max(1,Math.ceil(rows.length/PER));
    if(s.pg>tot)s.pg=tot; if(s.pg<1)s.pg=1;
    tb.innerHTML=rows.slice((s.pg-1)*PER,s.pg*PER).map(function(r){
      // 簡介獨立成整寬一列——塞在窄窄的識別欄裡會把列高撐成五、六行
      var tx=INTRO[r[0]];
      return '<tr'+(tx?' class="hasintro"':'')+'><td><span class="edcode">'+esc(r[0])+'</span>'
        +'<span class="edname">'+esc(r[1]===r[0]?'':r[1])+'</span></td>'
        +'<td class="num"><span class="edmain">'+(r[7]
          ?'<span class="hpend" title="當地市場這一天還沒收盤（美股約台北隔天清晨收盤），下一班自動補上">待收盤</span>'
          :pct(r[5],2,'%'))+'</span>'
        +'<span class="edsub2">'+num(r[4],2)+'</span></td>'
        +'<td class="num"><span class="edmain">'+num(r[2],2)+'%</span>'
        +'<span class="edsub2">'+(r[3]==null?'—':grp(r[3]))+'</span></td>'
        +'<td class="num"><span class="edmain">'+pct(r[6],2)+'</span></td></tr>'
        +(tx?'<tr class="introw"><td colspan="4"><div class="hintro">'+esc(tx)+'</div></td></tr>':'')
      }).join('')
      ||'<tr><td colspan="4" class="na">找不到符合的持股。</td></tr>';
    box.querySelector('.hpgn').textContent=s.pg+' / '+tot;
    box.querySelector('.hprev').disabled=s.pg<=1;
    box.querySelector('.hnext').disabled=s.pg>=tot;
    var ni=(e.al||[]).filter(function(r){return INTRO[r[0]]}).length;
    box.querySelector('.hsub').innerHTML='共 '+(e.n||rows.length)+' 檔持股・快照 '+esc(e.d||'—')
      +pdTag(e)
      +(s.q?('・符合搜尋 '+rows.length+' 檔'):'')
      +(ni?('・'+ni+' 檔附標的簡介'):'')
      +(e.sw!=null&&e.sw>0&&e.sw<60
        ?' <span class="hpartial" title="本表僅列臺股掛牌部位（權重合計 '+e.sw
          +'%）；海外持股與現金部位不在本表，貢獻合計亦僅反映臺股部位">僅台股部位 '+e.sw+'%</span>':'');
    box.querySelector('.hfoot').innerHTML='貢獻度＝權重 × 個股漲跌 ÷ 100（單位：百分點 pp）'
      +(e.pd&&e.pd!==e.d?'；權重為 '+esc(e.d)+' 揭露、漲跌為 '+esc(e.pd)+' 收盤':'')+'。'
      +'已涵蓋權重 '+num(e.cw,1)+'%，合計貢獻 '+(e.tc==null?'—':pct(e.tc,2,'pp'))+'。'
      +'<b>合計與 ETF 市價漲跌不會完全相等</b>——現金／期貨部位、費用、以及持股揭露時點與'
      +'收盤的時間差都落在差額裡，此處不作湊平調整。'
      +(e.pd?'台股漲跌取證交所／櫃買 '+esc(e.pd)+' 官方收盤（除權息日對參考價）；'
        +'海外持股取當地市場 '+esc(e.pd)+' <b>已收盤</b>的價格（Yahoo Finance，原幣別），'
        +'當地還沒收盤的標「待收盤」，下一班自動補上'+(e.np?'（目前 '+e.np+' 檔）':'')+'。'
       :'漲跌資料更新中，下一班 ETF 持股更新後顯示。')
      +(e.src==='fhtrust'?'資料來源：復華官網 assetsExcel（發行投信第一手揭露）。'
        :'資料來源：'+esc(e.src||'投信每日揭露')+'（Tier B 彙整站，取自投信每日揭露；'
         +'正式對外前以各投信官網核對）。');
    markSort(box,'.hldtbl th.hsk',s.hsk,s.hsd)}

  // 期貨部位：FU.r＝[商品代號, 名稱, 口數(空單為負), 名目曝險%, 月份, 比上次加減口數, 動作, 轉倉]
  function paintFut(box,e){
    var blk=box.querySelector('.futblk'), f=e.fu;
    if(!f||!(f.r||[]).length){blk.hidden=true;return}
    blk.hidden=false;
    box.querySelector('.fusub').textContent='揭露 '+(e.d||'—')+(f.cmp&&f.pdd?'・比 '+f.pdd:'');
    var ex=box.querySelector('.futexp'), sw=e.sw;
    // 期貨比例照揭露的兩位小數（toFixed(1) 會把 36.55 捨成 36.5，和下表對不上）
    if(f.nw!=null&&sw!=null&&sw>=60){
      ex.innerHTML='持股 '+sw.toFixed(1)+'% '+(f.nw<0?'－':'＋')+' 期貨名目 '+Math.abs(f.nw).toFixed(2)
        +'% ＝ 合計約淨值的 <b>'+(sw+f.nw).toFixed(0)+'%</b>';
      ex.hidden=false}
    else if(f.nw!=null){ex.innerHTML='期貨名目曝險合計 <b>'+(f.nw<0?'-':'+')+Math.abs(f.nw).toFixed(2)+'%</b>';
      ex.hidden=false}
    else ex.hidden=true;
    box.querySelector('.fub').innerHTML=f.r.map(function(r){
      var q=r[2], dq=r[5];
      var chg=dq==null?'<span class="na">—</span>'
        :'<span class="edmain '+(dq>0?'gain':(dq<0?'loss':''))+'">'+(dq>0?'+':(dq<0?'-':''))
          +grp(Math.abs(dq))+' 口</span><span class="edsub2">'+esc(r[6])+'</span>'
          +(r[7]?'<span class="edsub2 futroll">'+esc(r[7]).replace('→','→<wbr>')+'</span>':'');
      return '<tr><td><span class="edcode">'+esc(r[0])+'</span>'
        +'<span class="edname">'+esc(r[1])+'</span>'
        +(r[4]?'<span class="edsub2">'+esc(r[4])+' 合約</span>':'')+'</td>'
        +'<td class="num"><span class="edmain">'+(q==null?'—':grp(Math.abs(q))+' 口')+'</span>'
        +'<span class="edsub2">'+(q>0?'多單':(q<0?'空單':'已平倉'))+'</span></td>'
        +'<td class="num"><span class="edmain">'+(r[3]==null?'—':(r[3]<0?'-':'')+Math.abs(r[3]).toFixed(2)+'%')
        +'</span></td><td class="num">'+chg+'</td></tr>'}).join('');
    box.querySelector('.fufoot').innerHTML='名目曝險＝合約價值 ÷ 基金淨值。期貨只付保證金，這個比例不是投入的金額，'
      +'所以持股權重加上期貨可以超過 100%；空單記為負。合計只是兩個比例相加，期貨與持股的標的不同時'
      +'（例如公司債搭配公債期貨）只能粗看。同一商品換月份（例如 12 月合約換成 3 月）算轉倉，不算平倉再新建。'
      +'期貨不算進上面的持股異動、方塊圖與貢獻度。'
      +(f.cmp?'':'尚無前一揭露日的期貨資料，下一個揭露日起可看加減口數。')
      +(f.xs?'本次揭露來源（'+esc(f.xs[1])+'）與前一揭露日（'+esc(f.xs[0])+'）不同，只比兩邊都有的合約。':'')}

  function render(card){
    var code=card.dataset.c, e=EH[code], box=card.querySelector('.etfd-body');
    if(!e||!box||box.dataset.done)return;
    box.dataset.c=code;
    box.innerHTML=shell();
    box.dataset.done='1';
    paintTmap(box,e);paintMoves(box,e);paintFut(box,e);paintHold(box,e)}

  root.querySelectorAll('details.etfd').forEach(function(card){
    card.addEventListener('toggle',function(){if(card.open)render(card)})});

  // 事件委派：卡片內容是延遲建出來的，不能在初始化時逐一綁事件
  root.addEventListener('click',function(ev){
    var card=ev.target.closest('details.etfd'); if(!card)return;
    var box=card.querySelector('.etfd-body'), e=EH[card.dataset.c], s=st(card.dataset.c);
    var th=ev.target.closest('.chgtbl th.csk');
    if(th){s.msd=(th.dataset.k===s.msk)?-s.msd:-1;s.msk=th.dataset.k;paintMoves(box,e);return}
    var th2=ev.target.closest('.hldtbl th.hsk');
    if(th2){s.hsd=(th2.dataset.k===s.hsk)?-s.hsd:-1;s.hsk=th2.dataset.k;s.pg=1;paintHold(box,e);return}
    if(ev.target.closest('.mvmore')){s.mvall=!s.mvall;paintMoves(box,e);return}
    if(ev.target.closest('.hprev')){s.pg--;paintHold(box,e);return}
    if(ev.target.closest('.hnext')){s.pg++;paintHold(box,e);return}
  });
  root.addEventListener('input',function(ev){
    if(!ev.target.classList.contains('hq'))return;
    var card=ev.target.closest('details.etfd'), s=st(card.dataset.c);
    s.q=ev.target.value.trim().toLowerCase(); s.pg=1;
    paintHold(card.querySelector('.etfd-body'),EH[card.dataset.c])});

  // 工具列：搜尋（代碼或名稱）／分類 chips／全部展開・收合——比照基金詳情
  var q=document.getElementById('esearch'), g='';
  function hit(el,kw){return (!kw||(el.dataset.name||'').toLowerCase().indexOf(kw)>=0)
    &&(!g||el.dataset.group===g)}
  function apply(){var kw=(q&&q.value||'').trim().toLowerCase();
    root.querySelectorAll('details.etfd').forEach(function(c){
      c.classList.toggle('fhide',!hit(c,kw))});
    // 代碼泡泡跟著篩；整排都被篩掉時連標籤一起收（否則只剩「被動」兩個字孤零零）
    root.querySelectorAll('#edpick .edchip').forEach(function(b){
      b.classList.toggle('fhide',!hit(b,kw))});
    root.querySelectorAll('#edpick .edprow').forEach(function(r){
      r.style.display=r.querySelector('.edchip:not(.fhide)')?'':'none'})}
  if(q)q.addEventListener('input',apply);
  root.querySelectorAll('.eg').forEach(function(b){b.onclick=function(){
    root.querySelectorAll('.eg').forEach(function(x){x.classList.remove('on')});
    b.classList.add('on');g=b.dataset.g||'';apply()}});
  // 代碼泡泡：點一顆＝展開該檔並捲過去（比打搜尋快；使用者 2026-07-31 指定）
  root.querySelectorAll('#edpick .edchip').forEach(function(b){b.onclick=function(){
    var card=document.getElementById('etfd-'+b.dataset.c); if(!card)return;
    card.classList.remove('fhide'); card.open=true; render(card); syncPick();
    card.scrollIntoView({behavior:'smooth',block:'start'})}});
  // 泡泡的選中狀態＝該檔卡片是否展開（開合來源不只泡泡，故集中同步一次）
  function syncPick(){root.querySelectorAll('#edpick .edchip').forEach(function(b){
    var c=document.getElementById('etfd-'+b.dataset.c);
    b.classList.toggle('on',!!(c&&c.open))})}
  root.querySelectorAll('details.etfd').forEach(function(c){
    c.addEventListener('toggle',syncPick)});
  var ex=document.getElementById('eexp'), co=document.getElementById('ecol');
  if(ex)ex.onclick=function(){root.querySelectorAll('details.etfd:not(.fhide)').forEach(function(c){
    c.open=true;render(c)})};
  if(co)co.onclick=function(){root.querySelectorAll('details.etfd').forEach(function(c){c.open=false})};
  // 方塊圖標籤依像素大小決定層級 → 視窗尺寸變了要重畫（只重畫已展開的卡）
  var t=null;
  window.addEventListener('resize',function(){clearTimeout(t);t=setTimeout(function(){
    root.querySelectorAll('details.etfd[open] .etfd-body[data-done]').forEach(function(b){
      paintTmap(b,EH[b.dataset.c])})},160)});
  // 上方 ETF 表「詳情 ↓」：展開該檔並捲過來
  document.querySelectorAll('.edjump').forEach(function(b){b.onclick=function(){
    var card=document.getElementById('etfd-'+b.dataset.c); if(!card)return;
    card.classList.remove('fhide'); card.open=true; render(card);
    card.scrollIntoView({behavior:'smooth',block:'start'})}});
})();
// （逾期未重建警告只保留上方那一份——此處原有一份重複的同樣 IIFE，逾期時會 prepend 兩條橫幅，2026-08-03 去重）
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
    tw_held = macronews.tw_held(macronews.tw_watch())   # 行事曆台股列「復華持股」章（同提示包必查清單）
    us_md = (news or {}).get("v1") or (news or {}).get("v2") or ""
    tw_md = (tw or {}).get("md") or ""
    macro_md = (macro or {}).get("md") or ""
    # 市況提示（取自行事曆引言「市況」段；台股視圖只列台股、全球視圖列美＋日韓陸港；
    # 總經頁行事曆用完整引言）
    hol_tw, hol_gl = _market_status((cal or {}).get("note") or "")

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
    eh_doc = etfholdings.load()          # ETF 每日持股揭露（展開明細用；無檔＝不展開）
    mc_doc = macrochips.load()
    mc_asof = (mc_doc or {}).get("as_of")
    # 多期報酬（鉅亨每日基準）鮮度：CI 接上前為 None——不列警示、總覽區顯示過渡註記
    ret_asof = max((d.get("returns_daily_asof") or "" for d in funds), default="") or None
    sec_fresh = _freshness_view(now, [
        ("NAV 日", nav_date, 3, True), ("持股基準", hold_asof, 45), ("持股快照抓取", fetched_at, 3),
        ("美股新聞", us_date, 3), ("台股新聞", tw_date, 3),
        ("總經・政策", mac_date, 3), ("經濟行事曆", cal_date, 8),
        ("復華新聞・社群", fn_asof, 3), ("ETF 數據追蹤", etf_asof, 6, True),
        # ETF 持股揭露＝展開明細資料層（etf_holdings.yml 台北週一~五 17:40 抓）——
        # 停更超過 2 個交易日代表該 workflow 掛了，要列進逾期警示（同其他來源慣例）
        ("ETF 持股揭露", max(((v.get("date") or "") for v in ((eh_doc or {}).get("etfs") or {}).values()),
                             default="") or None, 2, True),
        ("總經・籌碼數據", mc_asof, 4),
    ] + ([("多期報酬(鉅亨)", ret_asof, 3, True)] if ret_asof else []))

    # ① 今日重點（雙視圖）；台股盤前速覽自新聞頭段抽出、直接顯示於此（不再埋於收合塊）
    premkt_md, tw_md_news = _extract_premarket(tw_md)
    pm_title = _premarket_title(tw_md)
    b_tw = _brief_view(twnews.extract_indices(tw_md), *fund_insights.movers(tw_funds),
                       fund_insights.upcoming_distributions(tw_funds), hol_tw)
    b_tw += _premarket_card(premkt_md, pm_title)
    # 全球今日重點不列任何指數點位/漲跌幅卡（公開搜尋之收盤數據不可靠；
    # 使用者指示 2026-07-04：全球重點不要出現數據漲跌幅——一律於下方新聞以官方為準呈現）
    b_gl = _brief_view([], *fund_insights.movers(gl_funds),
                       fund_insights.upcoming_distributions(gl_funds), hol_gl)
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
                     f'{_macro_cal_view(cal, tw_held)}</div>')
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
    # 市場溫度計（全球指標＋台股籌碼；官方數據序列，2026-07-23 使用者需求：置於行事曆與新聞之後）
    sec_macro_data = (f'<div class="section" id="macro-data"><div class="st">{_ic("activity", tone="amber")}市場溫度計 '
                      f'{_fresh_chip("抓取", mc_asof, 4)} '
                      f'<span class="stsub">VIX／美債／美元／油金＋台股法人・期權籌碼・融資融券・'
                      f'官方數據（TWSE／期交所／Yahoo Finance）每日更新</span></div>'
                      f'{_macro_data_view(mc_doc)}</div>')

    # ETF 分頁：先「即將登場的新 ETF」（募集中・即將募集＋即將掛牌・待掛牌，附活動介紹連結），
    # 再「ETF 數據追蹤」週績效表（左上「ETF」分頁專屬視圖）
    etf_up = etfwatch.upcoming()
    # 申請中（已送件）檔＝發現層 gap 檔 pipeline 欄（2026-08-28 使用者：送件的也要上「即將登場」；
    # 仍不登錄不警示，純展示——load_gap 無檔 fail-open 回空、區塊自動不渲染）
    etf_applied = etfdiscover.load_gap().get("pipeline") or []
    sec_etf_up = (f'<div class="section" id="etf-upcoming"><div class="st">{_ic("zap", tone="amber")}即將登場的新 ETF '
                  f'<span class="stsub">募集中・待掛牌・已核准待定・已送件審查中 分組一次看・點「活動介紹」看投信說明</span></div>'
                  f'{_upcoming_etf_view(etf_up, applied=etf_applied)}</div>')
    # 持股揭露鮮度另立 chip（2026-07-30）：`_freshness_view()` 只彙總「逾期」項目，
    # 資料正常時整個字串不會出現在頁面上——各來源的正常時戳一律標在自己區塊標題列。
    eh_date = max(((v.get("date") or "") for v in ((eh_doc or {}).get("etfs") or {}).values()),
                  default="") or None
    sec_etf = (f'<div class="section" id="etfwatch"><div class="st">{_ic("activity", tone="teal")}ETF 數據追蹤 '
               f'{_fresh_chip("資料基準", etf_asof, 6, trading=True)} '
               f'{_fresh_chip("持股揭露", eh_date, 2, trading=True) if eh_date else ""} '
               f'<span class="stsub">台股被動（高股息／市值型）＋主動式 ETF・收盤／規模／成立／週月報酬／'
               f'最近一次配息金額／換算年化配息率／分配頻率・點欄位標題可排序</span></div>'
               f'{_etfwatch_view(etf_doc, eh_doc)}</div>')
    # ETF 詳情（底部）：持股異動方塊圖＋異動明細＋完整持股明細（2026-07-30 使用者需求）
    sec_etf_det = _etf_detail_view(etf_doc, eh_doc)

    # ②b 復華新聞・社群（品牌＋產品＋各基金合併單一清單＋社群聲量；讀 data/fund_news.json）
    fn_sub = (f'近 {fn_doc.get("window_days") or 7} 天・Google News＋財經RSS＋PTT 自動擷取'
              if fn_doc else '復華新聞／社群聲量')
    sec_fnews = (f'<div class="section" id="fundnews"><div class="st">{_ic("megaphone", tone="purple")}復華新聞・社群 '
                 f'{_fresh_chip("更新", fn_asof, 3)} '
                 f'<span class="stsub">{_esc(fn_sub)}</span></div>'
                 f'{_fundnews_view(fn_doc)}</div>')

    # ③ 當日焦點個股區已移除（2026-07-15 使用者指示）；
    #    新聞連動資料仍餵基金詳情卡的持股 🔗 高亮（linked_by_fund）

    # ④ 基金總覽（多期報酬＝鉅亨每日基準優先；未接上前 ret_asof 為 None、不顯示 chip）
    ret_chip = _fresh_chip("多期報酬", ret_asof, 3, trading=True) if ret_asof else ""
    ret_note = ("報酬欄＝鉅亨每日基準（缺值回退官網月底值）" if ret_asof else
                "多期報酬暫為官網月底基準（鉅亨每日覆蓋待 CI 接上）")
    o_tw = _overview_view(rows_tw, leaders, tw_pend)
    o_gl = _overview_view(rows_gl, leaders, gl_pend)
    sec_over = (f'<div class="section" id="overview"><div class="st">{_ic("chart", tone="green")}基金總覽 '
                f'{_fresh_chip("NAV 日", nav_date, 3, trading=True)}{_fresh_chip("持股基準", hold_asof, 45)}'
                f'{_fresh_chip("快照抓取", fetched_at, 3)}{ret_chip} '
                f'<span class="stsub">色塊＝各組各欄漲跌極值（見下方圖例）・點欄位標題可排序・{ret_note}・'
                f'1週/1月＝往回滾動7/30日曆日（非月初起算，缺值以自建NAV序列自算，'
                f'1月自算須史料滿30天）</span></div>'
                f'{_mkt(o_tw, o_gl)}</div>')

    # ⑤ 基金詳情
    c_tw = _details_block(tw_funds, gavg, linked_by_fund, tw_pend)
    c_gl = _details_block(gl_funds, gavg, linked_by_fund, gl_pend)
    sec_det = (f'<div class="section" id="details"><div class="st">{_ic("book", tone="navy")}基金詳情 '
               f'{_fresh_chip("NAV 日", nav_date, 3, trading=True)}{_fresh_chip("持股基準", hold_asof, 45)} '
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

    # ⑥ 列印版（2026-09-07 使用者需求：每天早上可列印／存 PDF）——獨立的 #print 樹，只放五組重點
    #    （行事曆・市場數據・盤勢總覽・8 分以上新聞每報至少一則・基金 ETF 報酬率），A4 直式、每塊不可切頁；
    #    資料全部沿用上面已載入的物件（見 arm/printview.py 模組說明）。函式內匯入：printview
    #    依賴本模組的渲染小工具，頂層互相 import 會成環。
    from . import printview
    us_head, _, _ = usnews.split_doc(us_md or "")
    sec_print = printview.render({
        "today": clock.today_tw(), "now": now, "nav_date": nav_date, "as_of": hold_asof,
        "cal": cal, "mc": mc_doc, "tw_held": tw_held,
        "overviews": [("總經・政策總覽", mac_ov, mac_date),
                      (f"台股{pm_title}", premkt_md, tw_date),
                      ("全球・昨夜美股總覽", _extract_overview(us_head), us_date,
                       printview.us_trade_note(us_md))],
        "lanes": [("macro", "總經", macro_md), ("tw", "台股", tw_md), ("us", "美股", us_md)],
        "rows_tw": rows_tw, "rows_gl": rows_gl, "marks": leaders, "etf_doc": etf_doc,
    })
    pvbar = ('<div class="pvbar"><span class="pvt">列印版預覽（A4 直式；實際分頁以列印對話框為準）</span>'
             f'<button type="button" id="pvprint">{_ic("printer", plain=True)} 列印／存 PDF</button>'
             '<button type="button" class="ghost" data-pv="0">返回網頁版</button></div>')

    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>復華基金雷達 · 台股/全球雙視圖</title>
<style>{_CSS}{printview.CSS}</style></head>
<body>
<input class="mkradio" type="radio" name="mkt" id="mkt-macro">
<input class="mkradio" type="radio" name="mkt" id="mkt-tw" checked>
<input class="mkradio" type="radio" name="mkt" id="mkt-gl">
<input class="mkradio" type="radio" name="mkt" id="mkt-etf">
<input class="secradio" type="radio" name="secf" id="sec-brief" checked>
<input class="secradio" type="radio" name="secf" id="sec-news">
<input class="secradio" type="radio" name="secf" id="sec-fnews">
<input class="secradio" type="radio" name="secf" id="sec-over">
<input class="secradio" type="radio" name="secf" id="sec-det">
<input class="secradio" type="radio" name="secm" id="sec-mcal" checked>
<input class="secradio" type="radio" name="secm" id="sec-mov">
<input class="secradio" type="radio" name="secm" id="sec-mnews">
<input class="secradio" type="radio" name="secm" id="sec-mdata">
<input class="secradio" type="radio" name="sece" id="sec-eup" checked>
<input class="secradio" type="radio" name="sece" id="sec-ewatch">
<input class="secradio" type="radio" name="sece" id="sec-edet">
<div class="rprog" id="rprog"></div>
{_topbar(banned, bool(news or tw or macro), as_of, now)}
<div class="wrap">
{sec_fresh}
<div class="macroview">
<div class="sec" data-sec="mcal">{sec_macro_cal}</div>
<div class="sec" data-sec="mov">{sec_macro_ov}</div>
<div class="sec" data-sec="mnews">{sec_macro}</div>
<div class="sec" data-sec="mdata">{sec_macro_data}</div></div>
<div class="etfview">
<div class="sec" data-sec="eup">{sec_etf_up}</div>
<div class="sec" data-sec="ewatch">{sec_etf}</div>
<div class="sec" data-sec="edet">{sec_etf_det}</div></div>
<div class="fundview">
<div class="sec" data-sec="brief">{sec_brief}</div>
<div class="sec" data-sec="news">{sec_news}</div>
<div class="sec" data-sec="fnews">{sec_fnews}</div>
<div class="sec" data-sec="over">{sec_over}</div>
<div class="sec" data-sec="det">{sec_det}</div>
</div>
<div class="foot">
  資料來源：復華投信官網（fhtrust.com.tw）基金淨值／持股揭露（月度）；新聞／政策／行事曆為公開來源彙編（出處連結見各則新聞卡），僅為市場資訊彙編／教育用途；重點標的簡介為中性事實敘述、非投資建議。<br>
  本資料僅供參考，非屬投資建議或招攬；本文所載資料多引自公開來源，本公司不保證其完整、即時或正確，亦不負損益責任。
  基金投資有風險，申購前應詳閱公開說明書／投資人須知；過去績效不代表未來表現，淨值可能因市場變動而上下。
  境外基金涉及匯率與國際市場風險；使用衍生性商品者另涉及槓桿、流動性與對手風險。
  投資人申購本基金係持有基金受益憑證，非本文提及之投資資產或標的。
  本版本不呈現「每天持股變化」（共同基金無逐日持股張數）。<a class="fx" href="x9m.html" aria-label="·">·</a>
</div>
</div>
{sec_print}
{pvbar}
<a class="backtop" href="#" onclick="window.scrollTo({{top:0,behavior:'smooth'}});return false;">↑ 回頂端</a>
<script>{_JS}{printview.JS}</script>
</body></html>"""
