"""列印版（2026-09-07 使用者需求）：每天早上可列印／另存 PDF 的「精華一份」。

為什麼是獨立的 #print 樹、而不是把螢幕版硬套 @media print：
  螢幕版是四分頁×二級分段的 radio 切換（display:none）、新聞卡 <details> 預設收合、
  表格橫向捲動、方塊圖／社群等大量非列印內容——直接列印只會印出「當下那一段」
  （實測現行頁面 print 只有 2 頁、多半空白）。列印版另建一份精簡 DOM：只放五組重點資訊，
  資料全部沿用 fund_dashboard.render() 已載入的物件，零新增抓取、零外部請求。

版面（A4 直式、邊界 8–10mm；字 7–8.5pt——使用者：「我可以接受字很小只要清楚就好」）：
  第 1 頁      ① 本週行事曆 ＋ ② 市場數據追蹤（兩塊各自 break-inside:avoid；行事曆過長時 ② 整塊順延）
  第 2 頁起    ③ 盤勢總覽（總經／台股／全球三欄並排、一整塊不切）
               ④ 重要度 8 分以上新聞（三報合併；**每報至少 1 則**——該報當天沒有 8 分卡時補其最高分
                 事件卡並標灰章「本報最高 N 分」；每卡不切、卡與卡之間可換頁）
  最後一頁     ⑤ 基金・ETF 報酬率：break-before:page 獨立一頁，基金（左）／ETF（右）並排，
               字級依單側列數自動收斂（fit_pt）確保一頁塞得下（使用者：「這個單獨全部擠在一頁」）。
「同一資訊不可切到兩頁」＝ CSS break-inside:avoid（區塊／卡片／表格）＋ 只在 ⑤ 前強制分頁，
  不靠固定高度；區塊塞不進本頁餘白時整塊順延到下一頁。
輸出 PDF ＝ 頂欄「列印／PDF」→ window.print() → 瀏覽器對話框選「儲存為 PDF」（桌機／Android
  Chrome／iOS Safari 皆走此路，零外掛、CJK 字型由瀏覽器處理）；「預覽」把同一份版面以 A4 寬度
  顯示在螢幕（body.pv），Esc 或「返回網頁版」關閉。
驗證：scripts/check_print_layout.py 以 headless Chromium 真的產 PDF，檢查頁數與每個區塊
  首尾是否落在同一頁（pytest 只守字串與規則；分頁只有真的印才知道）。
"""
from __future__ import annotations

import re
from datetime import date

from . import clock, macrochips, usnews
from . import fund_dashboard as fd

MIN_SEV = 8                        # ④ 新聞門檻（2026-09-07 使用者：先 9 分、同日放寬到 8 分以上）
LANE_MIN = 1                       # 每份報告（總經／台股／美股）至少幾則——使用者：「總經台股全球的都要涵蓋進去」；
                                   # 該報無達門檻卡時補其最高分事件卡並標「本報最高 N 分」；設 0 關閉保底
_WD = "一二三四五六日"
_ETYPE = {"new": "新事件", "ext": "延伸", "deep": "深度"}
# 報告順序＝使用者列舉的「總經、台股、全球」；同分時依此排、同報告內維持原序
LANE_ORDER = ("macro", "tw", "us")


def _esc(s) -> str:
    return fd._esc(s)


# ── 共用 ────────────────────────────────────────────────────────

def weekday_of(mmdd: str, ref_iso: str | None) -> str:
    """行事曆日期 '09/07' ＋ 行事曆檔日期（年份基準，ISO）→ '一'；跨年週修正；解析失敗回 ''。"""
    m = re.match(r"\s*(\d{1,2})/(\d{1,2})", mmdd or "")
    r = re.match(r"(\d{4})-(\d{2})-(\d{2})", ref_iso or "")
    if not (m and r):
        return ""
    y, rm = int(r.group(1)), int(r.group(2))
    mo, d = int(m.group(1)), int(m.group(2))
    if rm == 12 and mo == 1:
        y += 1
    elif rm == 1 and mo == 12:
        y -= 1
    try:
        return _WD[date(y, mo, d).weekday()]
    except ValueError:
        return ""


def _mmdd(iso: str | None) -> str:
    """'2026-09-07'／'2026/09/07 06:59' → '09/07'；解析不到回原字串（或 —）。"""
    m = re.match(r"\d{4}[-/](\d{2})[-/](\d{2})", str(iso or ""))
    return f"{m.group(1)}/{m.group(2)}" if m else (str(iso) if iso else "—")


def _section(sid: str, title: str, sub: str, body: str, flow: bool = False) -> str:
    cls = "pr-sec pr-flow" if flow else "pr-sec"
    sub_html = f'<small>{sub}</small>' if sub else ""
    return f'<section class="{cls}" id="{sid}"><h2>{title}{sub_html}</h2>{body}</section>'


# ── ① 本週行事曆 ────────────────────────────────────────────────

def note_parts(note: str) -> tuple[list[tuple[str, str]], str]:
    """行事曆引言 → (市況 [(市場, 描述)], 焦點句)。「更新：…」段不進版面。
    舊格式（無市況段）→ 市況為空、整句當焦點。"""
    segs = [p.strip() for p in re.split(r"[；;]", note or "") if p.strip()]
    stat: list[tuple[str, str]] = []
    focus: list[str] = []
    for s in segs:
        if s.startswith("市況"):
            stat = [(m, d.strip("，、 ")) for m, d in fd._MKT_STAT_RE.findall(s)]
        elif s.startswith("更新"):
            continue
        else:
            focus.append(s)
    return stat, "；".join(focus)


def calendar_block(cal: dict | None) -> str:
    title = "① 本週重點財經行事曆"
    if not cal or not cal.get("rows"):
        return _section("p-cal", title, "", '<div class="pr-empty">尚無本週行事曆</div>')
    stat, focus = note_parts(cal.get("note") or "")
    chips = "".join(f'<span class="pr-chip{" halt" if "休市" in d else ""}">{_esc(m)} {_esc(d)}</span>'
                    for m, d in stat)
    head = (f'<div class="pr-chips"><b>市況</b>{chips}</div>' if chips else "")
    head += f'<div class="pr-focus">{fd._inline(focus)}</div>' if focus else ""
    trs, prev_d = [], None
    for r in cal["rows"]:
        st = r.get("status") or ""
        cls = "done" if "已公布" in st else ("halt" if "休市" in st else "wait")
        label = {"done": "已公布", "halt": "休市", "wait": "未公布"}[cls]
        d = str(r.get("date") or "")
        wd = weekday_of(d, cal.get("date"))
        # 同一天多列只在首列印日期（掃讀時日期即分組線）
        dcell = "" if d == prev_d else (_esc(d) + (f'<span class="pr-wd">（{wd}）</span>' if wd else ""))
        prev_d = d
        reg = r.get("region") or ""
        rc = fd._CAL_REGION_CLS.get(reg) or ("er" if reg == "財報" else "")
        reg_html = f'<span class="pr-reg {rc}">{_esc(reg)}</span>' if reg else ""
        av = r.get("actual") or ""
        actual = _esc(av) if av and av != "—" else '<span class="na">—</span>'
        trs.append(f'<tr class="cr-{cls}"><td class="l cd">{dcell}</td>'
                   f'<td class="l ci">{reg_html}{_esc(r.get("item"))}</td>'
                   f'<td>{fd._cal_cons_cell(r.get("cons"))}</td><td class="cav">{actual}</td>'
                   f'<td class="cpv">{_esc(r.get("prev") or "—")}</td>'
                   f'<td><span class="pr-st {cls}">{label}</span></td></tr>')
    tbl = (f'<table class="pr-tbl pr-cal"><thead><tr><th class="l">日期</th><th class="l">項目</th>'
           f'<th>預期</th><th>實際</th><th>前值</th><th>狀態</th></tr></thead>'
           f'<tbody>{"".join(trs)}</tbody></table>')
    foot = ('<div class="pr-note">預期欄標 * 者為市場共識預估（非官方）；實際以官方公布為準。</div>'
            if any(str(r.get("cons") or "").strip().endswith("*") for r in cal["rows"]) else "")
    return _section("p-cal", title, f'更新 {_mmdd(cal.get("date"))}・{len(cal["rows"])} 項',
                    head + tbl + foot)


# ── ② 市場數據追蹤（市場溫度計） ────────────────────────────────

def _name_cell(label: str, unit: str, d: str, sub: bool = False) -> str:
    u = unit.strip()
    unit_html = f'<span class="pr-unit">{_esc(u)}</span>' if u else ""
    dstr = f"{int(d[5:7])}/{int(d[8:10])}" if len(d) == 10 else d
    # 子列 class 取名 pr-subl／pr-subr——螢幕版有全域 `.sub{font-size:12.5px}`，撞名會把子列字放大
    return (f'<td class="l{" pr-subl" if sub else ""}">{_esc(label)}{unit_html}'
            f'<span class="pr-dt">{_esc(dstr)}{fd._md_stale_badge(d)}</span></td>')


def _lvl_row(mc: dict, key: str, label: str, kind: str, digits: int, unit: str) -> str:
    last = macrochips.latest(mc, key)
    if not last:
        return ""
    d, v = last
    if kind == "lots":
        val = f'{"淨空" if v < 0 else "淨多"} {fd._md_num(abs(v), digits)}'
    else:
        val = fd._md_num(v, digits)
    if key == "vix":
        lv = macrochips.vix_level(v)
        if lv:
            val += f' <span class="pr-lv {lv[1]}">{_esc(lv[0])}</span>'
    bp = kind == "yield"
    c1 = fd._md_delta(macrochips.day_change(mc, key), digits, "", bp=bp)
    c5 = fd._md_delta(macrochips.change_n(mc, key, 5), digits, "", bp=bp)
    return (f'<tr>{_name_cell(label, unit, d)}<td class="v">{val}</td><td>{c1}</td><td>{c5}</td>'
            f'<td class="sp">{fd._spark(macrochips.points(mc, key, 30))}</td></tr>')


def _flow_row(mc: dict, key: str, label: str, digits: int, unit: str, sub: bool = False) -> str:
    last = macrochips.latest(mc, key)
    if not last:
        return ""
    d, v = last
    s5 = macrochips.sum_n(mc, key, 5)
    c5 = fd._md_delta(s5, digits, "") if s5 is not None else '<span class="na">—</span>'
    return (f'<tr{" class=pr-subr" if sub else ""}>{_name_cell(label, unit, d, sub=sub)}'
            f'<td class="v">{fd._md_delta(v, digits, "")}</td><td>{c5}</td>'
            f'<td class="sp">{fd._spark_bars(macrochips.points(mc, key, 20))}</td></tr>')


def _tbl(head: str, body: str) -> str:
    return f'<table class="pr-tbl pr-md"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def market_block(mc: dict | None) -> str:
    title = "② 市場數據追蹤"
    if not mc or not any((mc.get("series") or {}).values()):
        return _section("p-mkt", title, "", '<div class="pr-empty">尚無市場數據</div>')
    lvl_head = ('<th class="l">指標<span class="pr-unit">單位・資料日</span></th><th>最新值</th>'
                '<th>日變化</th><th>近5日</th><th>近30日走勢</th>')
    flow_head = ('<th class="l">法人（億元）</th><th>當日買賣超</th><th>近5日累計</th><th>近20日走勢</th>')
    gl = "".join(_lvl_row(mc, *r) for r in fd._MD_GLOBAL_ROWS)
    tw = "".join(_lvl_row(mc, *r) for r in fd._MD_TW_ROWS)
    k, lab, _kind, dg, un = fd._MD_INST_MAIN
    flow = _flow_row(mc, k, lab, dg, un)
    if flow:
        flow += "".join(_flow_row(mc, k2, l2, dg2, un2, sub=True) for k2, l2, _k, dg2, un2 in fd._MD_INST_SUBS)
    body = (f'<div class="pr-md2"><div><div class="pr-sub">全球市場溫度計</div>{_tbl(lvl_head, gl)}</div>'
            f'<div><div class="pr-sub">台股籌碼——期貨・融資券・選擇權</div>{_tbl(lvl_head, tw)}'
            f'<div class="pr-sub">台股籌碼——法人買賣超（當日流量）</div>{_tbl(flow_head, flow)}</div></div>'
            '<div class="pr-note">殖利率日變化以 bp 計；外資台指期＝臺股期貨（大台）單一契約未平倉淨額，'
            '不含小型／微型台指；紅＝上升／買超、綠＝下降／賣超；走勢縮放至各自區間、看形狀非幅度。'
            '來源：Yahoo Finance／證交所／期交所官方序列。</div>')
    return _section("p-mkt", title, f'抓取 {_esc(mc.get("as_of") or "—")}', body)


# ── ③ 盤勢總覽（總經／台股／全球三欄） ──────────────────────────

def overview_block(cols: list[tuple[str, str, str | None]]) -> str:
    """cols＝[(欄名, markdown 內文, 日期)]×3；空內文顯示「今日無此段」。"""
    parts = []
    for name, md, d in cols:
        body = f'<div class="pr-doc">{fd._md(md)}</div>' if (md or "").strip() else \
               '<div class="pr-empty">（今日無此段）</div>'
        parts.append(f'<div class="pr-col"><h3>{_esc(name)}<small>{_mmdd(d)}</small></h3>{body}</div>')
    return _section("p-ov", "③ 盤勢總覽", "總經・政策／台股／全球（昨夜美股）・取自各報告總覽段",
                    f'<div class="pr-ov">{"".join(parts)}</div>')


# ── ④ 重要度 8 分以上新聞（每報至少 1 則） ──────────────────────────

def _sort_key(c: dict):
    """重要度高→低；同分依 lanes 順序、同報告內維持原序；【深度】精選殿後（同螢幕版 _news_view）。"""
    return (c.get("etype") == "deep", -c["importance"], c["_o"])


def pick_cards(lanes: list[tuple[str, str, str]], min_sev: int = MIN_SEV,
               lane_min: int = LANE_MIN) -> tuple[list[dict], list[dict]]:
    """lanes＝[(lane_key, lane_label, markdown)]（順序即同分時的排序）→ (入選卡, 全部有分數的卡)。
    入選＝重要度 ≥ min_sev 的全部卡；某報入選不足 lane_min 則時，補該報分數最高的卡
    （非【深度】優先）並標 fill=True——三個視角每天都在版面上
    （使用者 2026-09-07：「記得總經台股全球的都要涵蓋進去」）。"""
    allc: list[dict] = []
    for li, (lk, ll, md) in enumerate(lanes):
        for ci, c in enumerate(usnews.extract_cards(md or "")):
            if isinstance(c.get("importance"), int):
                allc.append({**c, "lane": lk, "lane_label": ll, "_o": (li, ci), "fill": False})
    allc.sort(key=_sort_key)
    picked = [c for c in allc if c["importance"] >= min_sev]
    for lk, _ll, _md in lanes:
        short = lane_min - sum(1 for c in picked if c["lane"] == lk)
        if short > 0:                                   # 該報不足：補未達門檻中分數最高者（allc 已排序）
            pool = [c for c in allc if c["lane"] == lk and c["importance"] < min_sev]
            picked += [{**c, "fill": True} for c in pool[:short]]
    picked.sort(key=_sort_key)
    return picked, allc


def _card(c: dict) -> str:
    ety = f'<span class="pr-ety">{_ETYPE[c["etype"]]}</span>' if c.get("etype") in _ETYPE else ""
    sev = (f'<span class="pr-sev fill" title="本報今日無達門檻新聞，補入該報最高分事件">本報最高 {c["importance"]} 分</span>'
           if c.get("fill") else f'<span class="pr-sev">重要度 {c["importance"]}</span>')
    src = (c.get("meta") or "").split("｜")[0].strip()          # 「CNBC、CNN，2026/09/03」
    src_html = f'<span class="pr-src">{_esc(src)}</span>' if src and "重要度" not in src else ""
    one = f'<div class="pr-one">{fd._inline(c["oneline"])}</div>' if c.get("oneline") else ""
    kv: list[tuple[str, str]] = []
    if c.get("summary"):
        kv.append(("新聞摘要", c["summary"]))
    if c.get("why"):
        kv.append(("為什麼值得讀", c["why"]))
    if c.get("move"):
        kv.append(("漲跌分析", c["move"]))
    kv += [(k, v) for k, v in (c.get("points") or [])]
    kv_html = "".join(f'<dt>{_esc(k)}</dt><dd>{fd._lines(fd._inline(v))}</dd>' for k, v in kv)
    links = sorted(c.get("links") or [], key=lambda tu: 0 if "futunn.com" in tu[1] else 1)[:3]
    links_html = "".join(f'<a href="{fd._safe_url(u)}">↗ {_esc(t[:60])}</a>' for t, u in links)
    return (f'<article class="pr-card"><div class="pr-ch">'
            f'<span class="pr-lane {c["lane"]}">{_esc(c["lane_label"])}</span>{sev}{ety}'
            f'<span class="pr-ct">{_esc(c["title"])}</span>{src_html}</div>{one}'
            f'<dl class="pr-kv">{kv_html}</dl>'
            + (f'<div class="pr-links">{links_html}</div>' if links_html else "") + '</article>')


def news_block(picked: list[dict], min_sev: int = MIN_SEV) -> str:
    title = f"④ 重要度 {min_sev} 分以上新聞"
    if not picked:
        return _section("p-news", title, "今日 0 則", '<div class="pr-empty">今日無新聞卡</div>')
    n_fill = sum(1 for c in picked if c.get("fill"))
    sub = f'{len(picked)} 則・總經／台股／美股三報合併、依重要度排序'
    if n_fill:
        sub += f'・{n_fill} 則為該報今日未達 {min_sev} 分時補入的最高分事件（灰章）'
    sub += '（原文連結在 PDF 內可點）'
    return _section("p-news", title, sub, "".join(_card(c) for c in picked), flow=True)


# ── ⑤ 基金・ETF 報酬率（獨立一頁） ────────────────────────────────

_F_COLS = [("nav", "NAV", 0), ("chg", "日變動", 1), ("w1", "1週", 1), ("m1", "1月", 1),
           ("ytd", "YTD", 1), ("y1", "1年", 1), ("y3", "3年", 1)]
_E_COLS = [("close_px", "收盤"), ("chg_pct", "當日"), ("ret_1w", "1週"), ("ret_1m", "1月"),
           ("last_div", "最近配息"), ("yield_pct", "年化配息率"), ("freq", "頻率")]


def fit_pt(n_rows: int, avail_px: float = 940.0, max_pt: float = 7.5, min_pt: float = 5.5) -> float:
    """⑤ 報酬率頁字級（pt）：依單側最多列數把字縮到一頁塞得下。
    列高 ≈ 字級 px × 1.95（行高 1.3 ＋ 上下 padding，取保守值）；A4 扣邊界／標題／註腳後
    可用約 940px。約 48 列以內維持 7.5pt；列數再增線性收斂、下限 5.5pt（再小就不清楚了，
    寧可讓 check_print_layout 紅、回頭調版面）。"""
    px = avail_px / max(int(n_rows), 1) / 1.95
    return round(max(min_pt, min(max_pt, px * 0.75)), 2)


def _fund_table(rows: list[dict], marks: dict) -> tuple[str, int]:
    """回 (HTML, 列數含分組列)。"""
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["group_label"], []).append(r)
    ths = "".join(f"<th>{lab}</th>" for _, lab, _ in _F_COLS)
    out = [f'<table class="pr-tbl pr-fund"><thead><tr><th class="l">基金</th>{ths}</tr></thead><tbody>']
    n = 0
    for g, rs in groups.items():
        out.append(f'<tr class="g"><td colspan="{len(_F_COLS) + 1}">{_esc(g)}（{len(rs)} 檔）</td></tr>')
        n += 1
        for r in rs:
            tds = [f'<td class="l nm">{_esc(fd._short(r["short_name"]))}</td>']
            for k, _, is_pct in _F_COLS:
                v = r.get(k)
                if v is None:
                    cell = '<span class="na">—</span>'
                elif is_pct:
                    cell = fd._pct_span(v, 2 if k in ("chg", "w1", "m1") else 1)
                else:
                    cell = _esc(v)
                if k == "ytd" and r.get("ytd_est") and v is not None:
                    cell += '<sup class="estmk">*</sup>'
                mk = marks.get((r["fund_id"], k))
                tds.append(f'<td class="{mk}">{cell}</td>' if mk else f'<td>{cell}</td>')
            out.append(f'<tr>{"".join(tds)}</tr>')
            n += 1
    out.append("</tbody></table>")
    return "".join(out), n


def _etf_chg(i: dict) -> str:
    """當日漲跌：序列落後收盤價時不以舊值冒充（同 fund_dashboard._chg_cell 的防呆），印 —⚠。"""
    v = i.get("chg_pct")
    ao, pa = i.get("as_of"), (i.get("chg_asof") or i.get("perf_asof"))
    if v is not None and ao and pa and pa < ao:
        return f'<span class="na" title="報酬序列只到 {_esc(pa)}，收盤價已是 {_esc(ao)}">—<sup>⚠</sup></span>'
    return fd._pct_span(v)


def _etf_table(items: list[dict]) -> tuple[str, int, bool]:
    """回 (HTML, 列數含分組列, 是否有預估配息換算的年化率)。"""
    groups = [("被動 ETF（高股息／市值型）", [i for i in items if i.get("kind") == "passive"]),
              ("主動式 ETF（股票／債券）", [i for i in items if i.get("kind") == "active"]),
              ("其他", [i for i in items if i.get("kind") not in ("passive", "active")])]
    ths = "".join(f"<th>{lab}</th>" for _, lab in _E_COLS)
    out = [f'<table class="pr-tbl pr-etf"><thead><tr><th class="l">代碼／名稱</th>{ths}</tr></thead><tbody>']
    n, has_est = 0, False
    for g, its in groups:
        if not its:
            continue
        out.append(f'<tr class="g"><td colspan="{len(_E_COLS) + 1}">{_esc(g)}・{len(its)} 檔</td></tr>')
        n += 1
        for i in its:
            name = str(i.get("name") or "")
            if i.get("kind") == "active" and name.startswith("主動"):
                name = name[2:]                       # 分組標題已寫主動式，去前綴省寬（同螢幕版泡泡）
            name_html = _esc(name).replace("復華", '<span class="fh">復華</span>')
            otc = '<span class="pr-otc">櫃</span>' if "上櫃" in str(i.get("cat") or "") else ""
            tds = [f'<td class="l nm"><b>{_esc(i.get("code"))}</b> {name_html}{otc}</td>']
            for k, _ in _E_COLS:
                v = i.get(k)
                if k == "chg_pct":
                    cell = _etf_chg(i)
                elif k in ("ret_1w", "ret_1m"):
                    cell = fd._pct_span(v)
                elif k == "close_px":
                    cell = fd._fmt_num(v, 2)
                elif k == "last_div":
                    cell = fd._fmt_num(v, 4)
                elif k == "yield_pct":
                    if v is None:
                        cell = '<span class="na">—</span>'
                    elif i.get("yield_is_est"):
                        cell, has_est = f'{v:.2f}%<sup class="estmk">*</sup>', True
                    else:
                        cell = f"{v:.2f}%"
                else:
                    cell = _esc(v) if v else '<span class="na">—</span>'
                tds.append(f"<td>{cell}</td>")
            out.append(f'<tr>{"".join(tds)}</tr>')
            n += 1
    out.append("</tbody></table>")
    return "".join(out), n, has_est


def returns_block(rows_tw: list[dict], rows_gl: list[dict], marks: dict, etf_doc: dict | None,
                  nav_date: str | None) -> str:
    items = list((etf_doc or {}).get("items") or [])
    f_html, f_n = _fund_table(rows_tw + rows_gl, marks)
    e_html, e_n, has_est = _etf_table(items)
    pt = fit_pt(max(f_n, e_n))
    fnote = (f'基金 NAV 日 {_esc(nav_date or "—")}（海外基金常見 T+1）；報酬＝鉅亨每日基準、缺值回退官網月底值，'
             f'1週／1月＝往回滾動 7／30 日曆日；YTD 標 * 者為新成立基金以發行價 10 元起算。'
             f'色塊＝各組各欄漲最多／漲最少／跌最多／跌最少。')
    enote = (f'ETF 收盤／規模基準 {_esc((etf_doc or {}).get("as_of") or "—")}、報酬序列基準 '
             f'{_esc((etf_doc or {}).get("perf_asof") or "—")}；當日漲跌標 —⚠ 者為序列尚未更新到收盤日、暫不顯示；'
             f'年化配息率＝最近一次實際配息 × 年配息次數 ÷ 收盤價' + ('（標 * 者以本月預估配息換算）' if has_est else "")
             + '；報酬為市價總報酬口徑（區間內除息加回）。')
    leg = ('<div class="pr-leg">各組各欄極值：<span class="ld-up1">漲最多</span><span class="ld-up0">漲最少</span>'
           '<span class="ld-dn1">跌最多</span><span class="ld-dn0">跌最少</span></div>')
    body = (f'<div class="pr-ret" style="--prpt:{pt}pt">'
            f'<div><div class="pr-sub">基金總覽・{len(rows_tw) + len(rows_gl)} 檔（國內 → 全球）</div>{leg}{f_html}'
            f'<div class="pr-note">{fnote}</div></div>'
            f'<div><div class="pr-sub">ETF 數據追蹤・{len(items)} 檔</div>{e_html}'
            f'<div class="pr-note">{enote}</div></div></div>')
    return (f'<section class="pr-sec pr-break" id="p-ret"><h2>⑤ 基金・ETF 報酬率'
            f'<small>單頁總表・字級依列數自動收斂（{pt}pt）</small></h2>{body}</section>')


# ── 組頁 ─────────────────────────────────────────────────────────

_FOOT = ('資料來源：復華投信官網基金淨值／持股揭露（月度）；ETF 數據 etfinfo.tw／Yahoo／TWSE 自算；'
         '市場數據 Yahoo Finance／證交所／期交所；新聞／政策／行事曆為公開來源彙編（出處連結見各卡）。'
         '本資料僅供參考，非屬投資建議或招攬，不保證完整、即時或正確；基金投資有風險，申購前應詳閱'
         '公開說明書／投資人須知；過去績效不代表未來表現。')


def render(ctx: dict) -> str:
    """ctx 由 fund_dashboard.render() 組：today(date)、now、nav_date、as_of、cal、mc、
    overviews=[(名, md, 日期)×3]、lanes=[(key, label, md)×3]、rows_tw、rows_gl、marks、etf_doc。"""
    today = ctx.get("today") or clock.today_tw()
    head = (f'<header class="pr-head"><div class="pr-brand">復華<b>基金雷達</b>'
            f'<small>每日晨報・列印版</small></div>'
            f'<div class="pr-meta">{today:%Y/%m/%d}（週{_WD[today.weekday()]}）　'
            f'產表 {_esc(ctx.get("now") or "—")}　NAV {_esc(ctx.get("nav_date") or "—")}　'
            f'持股基準 {_esc(ctx.get("as_of") or "—")}</div></header>')
    picked, _allc = pick_cards(ctx.get("lanes") or [])
    return (f'<div id="print" class="pr">{head}'
            f'{calendar_block(ctx.get("cal"))}{market_block(ctx.get("mc"))}'
            f'{overview_block(ctx.get("overviews") or [])}{news_block(picked)}'
            f'{returns_block(ctx.get("rows_tw") or [], ctx.get("rows_gl") or [], ctx.get("marks") or {}, ctx.get("etf_doc"), ctx.get("nav_date"))}'
            f'<footer class="pr-foot">{_FOOT}</footer></div>')


# ── 樣式（.pr 規則同時服務螢幕預覽 body.pv 與 @media print；分頁規則只在 print） ──

CSS = """
/* ── 列印版 #print（2026-09-07）：螢幕隱藏；@media print 只印它；body.pv 在螢幕以 A4 寬預覽 ── */
#print{display:none}
.pr{color:#111;font:8.5pt/1.4 -apple-system,"PingFang TC","Noto Sans TC","Microsoft JhengHei",Segoe UI,sans-serif;
  font-variant-numeric:tabular-nums;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.pr *{box-sizing:border-box}
.pr a{color:#1c4fa8;text-decoration:none}
.pr .gain{color:#c62828;font-weight:700}.pr .loss{color:#1b7f47;font-weight:700}
.pr .flat,.pr .na{color:#777;font-weight:400}
.pr .estmk{color:#b45309;font-weight:700}
.pr-head{display:flex;justify-content:space-between;align-items:baseline;gap:8px;flex-wrap:wrap;
  border-bottom:2px solid #0b4f9e;padding-bottom:3px;margin-bottom:8px}
.pr-brand{font-size:13pt;font-weight:800;color:#0b4f9e;letter-spacing:.04em}
.pr-brand b{color:#a16207}
.pr-brand small{font-size:8pt;font-weight:400;color:#555;margin-left:8px;letter-spacing:0}
.pr-meta{font-size:7.5pt;color:#555}
.pr-sec{break-inside:avoid;page-break-inside:avoid;margin:0 0 9px}
.pr-flow{break-inside:auto;page-break-inside:auto}
.pr-sec h2{font-size:10.5pt;font-weight:800;margin:0 0 4px;padding:1px 0 1px 7px;border-left:4px solid #2563c9;
  display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;break-after:avoid;page-break-after:avoid}
.pr-sec h2 small{font-size:7.2pt;font-weight:400;color:#666}
.pr-sub{font-size:8pt;font-weight:800;color:#173460;margin:3px 0 2px;padding-left:5px;border-left:3px solid #2f9d57}
.pr-note{font-size:6.8pt;color:#666;line-height:1.4;margin:3px 0 0}
.pr-empty{font-size:8pt;color:#777;padding:4px 0}
.pr-tbl{width:100%;border-collapse:collapse;font-size:7.5pt;line-height:1.3}
.pr-tbl th{font-weight:700;color:#333;text-align:right;padding:2px 4px;border-bottom:1px solid #8a94a6;
  white-space:nowrap;background:#eef2f8}
.pr-tbl th.l,.pr-tbl td.l{text-align:left}
.pr-tbl td{padding:1.5px 4px;border-bottom:1px solid #e2e6ec;text-align:right;white-space:nowrap;vertical-align:top}
.pr-tbl tr.g td{background:#e6ecf5;font-weight:800;text-align:left;color:#173460;border-bottom:1px solid #c9d3e3}
.pr-tbl td.pr-subl{padding-left:14px;color:#444}
.pr-unit{display:inline-block;font-size:6.5pt;font-weight:400;color:#777;margin-left:4px}
.pr-dt{display:block;font-size:6.5pt;color:#888;line-height:1.1;margin-top:1px}
.pr .mdstale{margin-left:3px;color:#c62828;font-weight:700;font-size:6.5pt}
/* ① 行事曆 */
.pr-chips{display:flex;flex-wrap:wrap;gap:3px 5px;align-items:center;margin:1px 0 3px;font-size:7.5pt}
.pr-chips b{color:#333;margin-right:2px}
.pr-chip{border:1px solid #c9d3e3;border-radius:3px;padding:0 5px;color:#333;background:#f6f8fb;white-space:nowrap}
.pr-chip.halt{border-color:#d9a24a;background:#fff4e0;color:#8a5410;font-weight:700}
.pr-focus{font-size:8pt;color:#222;margin:0 0 4px;line-height:1.45}
.pr-cal td.ci{white-space:normal;line-height:1.3}
.pr-cal td.cd{font-weight:700;white-space:nowrap}
.pr-wd{font-weight:400;color:#666;font-size:6.8pt}
.pr-cal td.cav{font-weight:800}.pr-cal td.cpv{color:#555}
.pr-cal tr.cr-halt td{color:#888}
.pr-reg{display:inline-block;font-size:6.5pt;font-weight:800;padding:0 4px;border-radius:3px;margin-right:3px;
  vertical-align:1px;line-height:1.4}
.pr-reg.us{color:#1d4f9c;background:#dce7fa}.pr-reg.eu{color:#5b3ea8;background:#e9e2fa}
.pr-reg.cn{color:#a02c2c;background:#fbe1e1}.pr-reg.jp{color:#0f6f6b;background:#d9f0ee}
.pr-reg.tw{color:#8a4b00;background:#fbe6cc}.pr-reg.ex{color:#8a2a6a;background:#f7dcee}
.pr-reg.er{color:#7a4b00;background:#fdecc8}
.pr-st{font-size:6.8pt;font-weight:700;white-space:nowrap}
.pr-st.done{color:#1d6b3a}.pr-st.wait{color:#1d4f9c}.pr-st.halt{color:#8a5410}
/* ② 市場數據 */
.pr-md2{display:grid;grid-template-columns:1fr 1fr;gap:0 12px;align-items:start}
.pr-md td.v{font-weight:700;color:#111}
.pr-md td.sp{padding-top:1px;padding-bottom:0;line-height:0}
.pr .spark svg{width:74px;height:15px;display:inline-block;vertical-align:middle}
.pr .spark polyline{stroke-width:1.5}
.pr .spark.bars rect.up{fill:#c62828}.pr .spark.bars rect.dn{fill:#1b7f47}.pr .spark.bars line.base{stroke:#bbb}
.pr-lv{display:inline-block;font-size:6.3pt;font-weight:800;padding:0 4px;border-radius:3px;margin-left:3px;vertical-align:1px}
.pr-lv.calm{color:#1d4f9c;background:#dce7fa}.pr-lv.norm{color:#1d6b3a;background:#dff3e6}
.pr-lv.elev{color:#8a5410;background:#fdecc8}.pr-lv.panic{color:#a02c2c;background:#fbe1e1}
/* ③ 三欄總覽 */
.pr-ov{display:grid;grid-template-columns:1fr 1fr 1fr;gap:0 12px;align-items:start}
.pr-col{border-top:2px solid #2563c9;padding-top:3px}
.pr-col h3{font-size:9pt;margin:0 0 3px;font-weight:800;color:#173460}
.pr-col h3 small{font-weight:400;color:#666;font-size:7pt;margin-left:5px}
.pr-doc{font-size:8pt;line-height:1.5;color:#111}
.pr-doc p{margin:0 0 4px}
.pr-doc ul,.pr-doc ol{margin:0 0 4px;padding-left:13px}
.pr-doc li{margin:0 0 2px}
.pr-doc h2,.pr-doc h3,.pr-doc h4,.pr-doc h5{font-size:8.5pt;margin:4px 0 2px;color:#173460}
.pr-doc hr{border:0;border-top:1px solid #ddd;margin:4px 0}
.pr-doc b,.pr-kv dd b,.pr-one b{color:#153a7a;background:#dce7fa;padding:0 2px;border-radius:2px;
  box-decoration-break:clone;-webkit-box-decoration-break:clone}
/* 螢幕版全域樣式會漏進來（.klabel/.tag/.nln/.nwatch/.sub 都是無前綴的全域規則）——逐一壓回列印字級 */
.pr .klabel{color:#1c4fa8;font-weight:700;margin-right:4px;letter-spacing:0}
.pr .tag{font-size:inherit;font-weight:700;padding:0 3px;border-radius:3px;background:#eef2f8;color:#173460}
/* ④ 新聞卡 */
.pr-card{break-inside:avoid;page-break-inside:avoid;border:1px solid #d5dbe5;border-radius:4px;
  padding:5px 8px 6px;margin:0 0 6px;font-size:8pt;line-height:1.5}
.pr-ch{display:flex;align-items:baseline;gap:5px;flex-wrap:wrap;margin-bottom:1px}
.pr-lane{font-size:6.8pt;font-weight:800;color:#fff;background:#173460;border-radius:3px;padding:0 5px;white-space:nowrap}
.pr-lane.tw{background:#0f766e}.pr-lane.us{background:#1c4fa8}.pr-lane.macro{background:#6d28d9}
.pr-sev{font-size:6.8pt;font-weight:800;color:#a02c2c;background:#fbe1e1;border-radius:3px;padding:0 5px;white-space:nowrap}
.pr-sev.fill{color:#5b6672;background:#e9edf3}   /* 該報未達門檻時補入的最高分卡：灰章，與紅章的達標卡區分 */
.pr-ety{font-size:6.8pt;color:#555;border:1px solid #ccc;border-radius:3px;padding:0 4px;white-space:nowrap}
.pr-ct{font-size:9.5pt;font-weight:800;color:#111}
.pr-src{font-size:6.8pt;color:#777;margin-left:auto;white-space:nowrap}
.pr-one{color:#6b4a1e;font-weight:700;margin:0 0 3px}
.pr-kv{display:grid;grid-template-columns:auto 1fr;gap:1px 6px;margin:0}   /* 標籤欄依最長標籤自適應（「對市場情緒與股價影響」9 字） */
.pr-kv dt{font-weight:700;color:#1c4fa8;white-space:nowrap}
.pr-kv dd{margin:0}
.pr .nln{display:block;margin-top:0}
.pr .nwatch{display:block;color:#444;border-top:1px dotted #ccc;margin-top:1px;padding-top:1px;font-size:inherit}
.pr-links{margin-top:3px;font-size:7pt;line-height:1.5}
.pr-links a{display:inline-block;color:#1c4fa8;border-bottom:1px dotted #1c4fa8;margin-right:9px}
/* ⑤ 報酬率單頁 */
.pr-break{break-before:page;page-break-before:always}
.pr-ret{display:grid;grid-template-columns:1fr 1fr;gap:0 10px;align-items:start;break-inside:avoid;page-break-inside:avoid}
.pr-ret .pr-tbl{font-size:var(--prpt,7.5pt)}
.pr-ret .pr-tbl th,.pr-ret .pr-tbl td{padding-left:3px;padding-right:3px}
.pr-ret td.nm{font-weight:600;max-width:13em;overflow:hidden;text-overflow:ellipsis}
.pr-ret td.nm b{color:#1c4fa8}
.pr-ret .fh{color:#a16207;font-weight:800}
.pr-otc{display:inline-block;font-size:.8em;color:#666;border:1px solid #bbb;border-radius:2px;padding:0 2px;margin-left:3px;line-height:1.2}
.pr-ret .ld-up1{background:rgba(211,58,52,.26)}.pr-ret .ld-up0{background:rgba(211,58,52,.09)}
.pr-ret .ld-dn1{background:rgba(31,157,87,.26)}.pr-ret .ld-dn0{background:rgba(31,157,87,.09)}
.pr-leg{font-size:6.8pt;color:#555;display:flex;gap:5px;flex-wrap:wrap;align-items:center;margin:2px 0 3px}
.pr-leg span{padding:0 5px;border-radius:3px;color:#333}
.pr-foot{font-size:6.6pt;color:#666;line-height:1.45;border-top:1px solid #ccc;margin-top:8px;padding-top:3px;
  break-inside:avoid;page-break-inside:avoid}
/* 頂欄按鈕 */
.tb-print{display:inline-flex;align-items:center;gap:5px;background:var(--card2);color:var(--accd);border:0;
  border-radius:8px;padding:5px 10px;font:inherit;font-size:12.5px;font-weight:700;cursor:pointer;white-space:nowrap}
.tb-print:hover{background:rgba(47,111,208,.12)}
.tb-print .ic.plain{width:14px;height:14px;color:var(--accd)}
.tb-print.tb-pv{font-weight:600;color:var(--ink2)}
/* 手機只留圖標：藏「文字」那顆 span（.tb-pl）——首版寫 `.tb-print span` 連圖標外層的 <span class="ic"> 一起藏掉，
   按鈕剩一顆 16×12 的空底色（Playwright 量 svg 0×0 才抓到）；預覽鈕手機不顯示（列印對話框自帶預覽） */
@media(max-width:720px){.tb-print .tb-pl{display:none}.tb-print{padding:6px 8px}.tb-print.tb-pv{display:none}}
/* 螢幕預覽（body.pv）：只顯示列印樹＋預覽列，寬度模擬 A4 */
.pvbar{display:none;position:fixed;top:0;left:0;right:0;z-index:70;background:#173460;color:#fff;
  padding:8px 14px;font-size:14px;align-items:center;gap:10px;flex-wrap:wrap}
.pvbar .pvt{flex:1 1 auto;font-weight:700}
.pvbar button{background:#fff;color:#173460;border:0;border-radius:8px;padding:6px 12px;font:inherit;font-size:13.5px;
  font-weight:700;cursor:pointer}
.pvbar button.ghost{background:rgba(255,255,255,.18);color:#fff}
body.pv{background:#e9edf3}
body.pv>*:not(#print):not(.pvbar):not(script){display:none}
body.pv .pvbar{display:flex}
body.pv #print{display:block;width:210mm;max-width:100%;margin:56px auto 30px;background:#fff;padding:10mm 8mm;
  box-shadow:0 2px 14px rgba(0,0,0,.18)}
body.pv .pr-break{border-top:2px dashed #b8c2d3;margin-top:16px;padding-top:12px}
/* 真正列印：只印 #print，A4 直式 */
@media print{
  @page{size:A4;margin:10mm 8mm 10mm}
  html,body{background:#fff!important;margin:0!important;padding:0!important;font-size:8.5pt}
  body>*:not(#print){display:none!important}
  #print{display:block!important}
}
"""

JS = r"""
// 列印／存 PDF（2026-09-07）：列印版是獨立的 #print 樹，@media print 只印它；
// 按鈕＝window.print()，瀏覽器對話框選「儲存為 PDF」即輸出；「預覽」在螢幕以 A4 寬度顯示同一份版面。
(function(){const b=document.getElementById('pbtn');if(b)b.addEventListener('click',function(){window.print()});
  const pp=document.getElementById('pvprint');if(pp)pp.addEventListener('click',function(){window.print()});
  const pv=function(on){document.body.classList.toggle('pv',on);if(on)scrollTo(0,0);
    try{if(on)history.replaceState(null,'','#print');
        else if(location.hash==='#print')history.replaceState(null,'',location.pathname+location.search)}catch(e){}};
  document.querySelectorAll('[data-pv]').forEach(function(x){x.addEventListener('click',function(){pv(x.dataset.pv==='1')})});
  addEventListener('keydown',function(e){if(e.key==='Escape'&&document.body.classList.contains('pv'))pv(false)});
  if(location.hash==='#print')pv(true);
})();
"""
