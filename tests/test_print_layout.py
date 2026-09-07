"""列印版（arm/printview，2026-09-07）：五區塊齊全、8 分門檻與每報保底、報酬率頁涵蓋全部基金與 ETF、
分頁 CSS 規則、不與螢幕版分頁機制撞名、按鈕與 JS 鉤子。

真正的「有沒有切頁」只有印出來才知道——那在 scripts/check_print_layout.py（headless Chromium 印 PDF
讀回比對）；這裡守的是 pytest 能守的結構與規則。"""
import re
from datetime import date

from arm import etfwatch, fund_dashboard as fd, fund_insights, fund_intro, macrochips
from arm import printview as pv

_SECS = ("p-cal", "p-mkt", "p-ov", "p-news", "p-ret")


def _tree(html: str) -> str:
    """整頁 HTML → #print 樹（到預覽列之前）。"""
    assert '\n<div id="print" class="pr">' in html          # 必須是 body 直屬子節點（print CSS 靠 body>* 藏其餘）
    return html.split('<div id="print" class="pr">', 1)[1].split('<div class="pvbar">', 1)[0]


def _cards_md(cards: list[tuple[str, int, str]]) -> str:
    """造報告檔片段：cards＝[(標題, 重要度, 屬性)]，欄位標籤依版型加 **粗體**。"""
    out = []
    for i, (t, sev, tag) in enumerate(cards, 1):
        out += [f"### 卡 {i}｜{t}（來源：測試，2026/09/07｜【{tag}】｜重要度 {sev}/10）",
                "1. **一句話重點**：一句話", "2. **新聞摘要**：摘要內文", "3. **漲跌分析**：漲 1%",
                "4. **對市場情緒影響**：影響內文", "[原文](https://example.com/a)", ""]
    return "\n".join(out)


def test_render_has_print_tree_button_and_preview_bar():
    html = fd.render()
    tree = _tree(html)
    for sid in _SECS:
        assert f'id="{sid}"' in tree, sid
        assert html.count(f'id="{sid}"') == 1, sid           # 不與螢幕版任何 id 重複
    assert 'id="pbtn"' in html and 'class="tb-pl"' in html   # 頂欄「列印／PDF」（手機只藏文字、留圖標）
    assert 'data-pv="1"' in html and 'data-pv="0"' in html and 'id="pvprint"' in html
    assert pv.CSS in html and pv.JS in html                  # 樣式／腳本真的併進頁面
    assert 'class="pr-sec pr-break" id="p-ret"' in tree      # ⑤ 強制另起一頁
    assert 'class="pr-sec pr-flow" id="p-news"' in tree or 'id="p-news"' in tree


def test_print_tree_avoids_screen_tab_classes():
    """列印樹不得用螢幕版分頁機制或全域樣式的 class——`.mkt/.sec` 會被 radio CSS 藏掉，
    `.sub/.st` 這類無前綴全域規則會把字級改掉（首版 `.sub` 撞名讓法人子列變大字）。"""
    tree = _tree(fd.render())
    banned = {"mkt", "sec", "section", "fundview", "macroview", "etfview", "sub", "st", "wrap", "topbar", "ndoc"}
    used = {c for m in re.finditer(r'class="([^"]*)"', tree) for c in m.group(1).split()}
    assert not (used & banned), used & banned
    assert "class=sub" not in tree


def test_css_print_rules():
    css = pv.CSS
    assert "#print{display:none}" in css                          # 螢幕平常看不到
    assert "@media print" in css and "@page{size:A4" in css
    assert "body>*:not(#print){display:none!important}" in css   # 只印列印樹（含動態插入的橫幅）
    assert "#print{display:block!important}" in css
    assert ".pr-sec{break-inside:avoid" in css and ".pr-card{break-inside:avoid" in css
    assert ".pr-flow{break-inside:auto" in css                   # ④ 卡與卡之間可換頁
    assert ".pr-break{break-before:page" in css                  # ⑤ 獨立一頁
    assert ".tb-print .tb-pl{display:none}" in css               # 手機藏文字不藏圖標
    assert "body.pv>*:not(#print):not(.pvbar):not(script){display:none}" in css


def test_js_hooks():
    assert "window.print()" in pv.JS and "getElementById('pbtn')" in pv.JS
    assert "location.hash==='#print'" in pv.JS and "e.key==='Escape'" in pv.JS


def test_pick_cards_threshold_and_order():
    lanes = [("macro", "總經", _cards_md([("總經甲", 9, "延伸"), ("總經乙", 7, "新事件")])),
             ("tw", "台股", _cards_md([("台股甲", 8, "新事件"), ("台股深", 9, "深度")])),
             ("us", "美股", _cards_md([("美股甲", 10, "新事件"), ("美股乙", 9, "延伸")]))]
    picked, allc = pv.pick_cards(lanes)
    # 門檻 8：分數高→低；同分依總經→台股→美股；【深度】殿後（同螢幕版）；三報都有達標卡 → 無補入
    assert [c["title"] for c in picked] == ["美股甲", "總經甲", "美股乙", "台股甲", "台股深"]
    assert all(c["importance"] >= 8 for c in picked) and not any(c["fill"] for c in picked)
    assert len(allc) == 6 and allc[0]["title"] == "美股甲"
    html = pv.news_block(picked)
    assert html.count('<article class="pr-card">') == 5 and "pr-sev fill" not in html
    assert "pr-lane us" in html and "重要度 10" in html and "新聞摘要" in html and "漲跌分析" in html
    assert 'href="https://example.com/a"' in html               # 原文連結留在 PDF 內可點


def test_lane_without_threshold_card_gets_its_top_card():
    """每報保底（使用者：「總經台股全球的都要涵蓋進去」）：某報當天無 8 分卡 → 補該報最高分事件卡
    （非【深度】優先）並標灰章；報告整份沒有卡就不補；LANE_MIN=0 可關閉。"""
    lanes = [("macro", "總經", ""),
             ("tw", "台股", _cards_md([("台股乙", 6, "延伸"), ("台股深", 7, "深度"), ("台股甲", 7, "新事件")])),
             ("us", "美股", _cards_md([("美股甲", 8, "新事件")]))]
    picked, _ = pv.pick_cards(lanes)
    assert [(c["title"], c["fill"]) for c in picked] == [("美股甲", False), ("台股甲", True)]
    html = pv.news_block(picked)
    assert html.count("本報最高 7 分") == 1 and "重要度 8" in html and "1 則為該報今日未達 8 分" in html
    only, _ = pv.pick_cards(lanes, lane_min=0)
    assert [c["title"] for c in only] == ["美股甲"]
    assert "今日無新聞卡" in pv.news_block([])


def test_returns_block_covers_every_fund_and_etf():
    """⑤ 一頁總表必須把追蹤中的全部基金與 ETF 都列上（少一檔就是漏印）。"""
    html = fd.render()
    ret = _tree(html).split('id="p-ret"', 1)[1].split('class="pr-foot"', 1)[0]
    funds = fund_intro.all_funds()
    for r in fund_insights.overview_rows(funds):
        assert fd._esc(fd._short(r["short_name"])) in ret, r["short_name"]
    for i in (etfwatch.load() or {}).get("items") or []:
        assert f'<b>{i["code"]}</b>' in ret, i["code"]
    assert 'style="--prpt:' in ret                                # 字級由列數決定


def test_fit_pt_monotonic_and_clamped():
    assert pv.fit_pt(30) == 7.5 and pv.fit_pt(40) == 7.5        # 常態列數維持上限字級
    vals = [pv.fit_pt(n) for n in range(10, 130, 5)]
    assert vals == sorted(vals, reverse=True)                    # 列數越多字越小
    assert min(vals) == 5.5 and pv.fit_pt(0) == 7.5


def test_weekday_and_note_parts():
    assert pv.weekday_of("09/07", "2026-09-07") == "一"
    assert pv.weekday_of("01/02", "2026-12-29") == "一二三四五六日"[date(2027, 1, 2).weekday()]   # 跨年往後
    assert pv.weekday_of("12/31", "2027-01-02") == "一二三四五六日"[date(2026, 12, 31).weekday()]  # 跨年往前
    assert pv.weekday_of("13/40", "2026-09-07") == "" and pv.weekday_of("09/07", None) == ""
    stat, focus = pv.note_parts("更新：2026/09/07；市況：台股 正常交易｜美股 9/7 因勞動節休市；本週焦點為 CPI。")
    assert ("台股", "正常交易") in stat and ("美股", "9/7 因勞動節休市") in stat
    assert focus == "本週焦點為 CPI。"                            # 「更新」段不進版面


def test_calendar_block_dedupes_dates_and_marks_status():
    cal = {"date": "2026-09-07",
           "note": "更新：2026/09/07；市況：台股 正常交易｜美股 9/7 因勞動節休市；本週焦點為 CPI。",
           "rows": [{"date": "09/07", "item": "勞動節休市", "region": "美", "cons": "—", "actual": "—", "prev": "—", "status": "休市"},
                    {"date": "09/08", "item": "8月CPI", "region": "美", "cons": "3.4%*", "actual": "3.5%", "prev": "3.2%", "status": "已公布"},
                    {"date": "09/08", "item": "Oracle 財報", "region": "財報", "cons": "EPS 1.3*", "actual": "—", "prev": "—", "status": "未公布"}]}
    html = pv.calendar_block(cal)
    assert html.count("09/08") == 1                              # 同日第二列不重印日期
    assert "（一）" in html and "（二）" in html
    assert 'pr-chip halt">美股 9/7 因勞動節休市' in html and "本週焦點為 CPI" in html
    assert 'pr-st done">已公布' in html and 'pr-st halt">休市' in html and 'pr-reg er">財報' in html
    assert 'estmk' in html and "市場共識預估" in html
    assert "尚無本週行事曆" in pv.calendar_block(None)


def test_market_block_subrows_and_stale_guard():
    html = pv.market_block(macrochips.load())
    assert "全球市場溫度計" in html and "法人買賣超" in html
    if "三大法人買賣超" in html:                                  # 有資料時分項列用 pr- 前綴 class
        assert "class=pr-subr" in html and 'pr-subl' in html
    assert "尚無市場數據" in pv.market_block(None)
    # ETF 當日漲跌：序列落後收盤價 → 不以舊值冒充（同螢幕版 _chg_cell 防呆）
    stale = pv._etf_chg({"chg_pct": 2.07, "as_of": "2026-09-02", "perf_asof": "2026-09-01"})
    assert "⚠" in stale and "2.07" not in stale
    assert "+2.07%" in pv._etf_chg({"chg_pct": 2.07, "as_of": "2026-09-02", "chg_asof": "2026-09-02"})
