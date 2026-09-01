"""資料更新防呆單測：台北時區單一來源（arm/clock）＋ fundnews 空結果不覆寫。"""
import json
from datetime import date, timedelta, timezone

from arm import clock, fundnews


# ── arm/clock：台北時區 ───────────────────────────────────────
def test_clock_is_taipei_tz():
    assert clock.TW_TZ.utcoffset(None) == timedelta(hours=8)
    n = clock.now_tw()
    assert n.tzinfo is not None and n.utcoffset() == timedelta(hours=8)
    assert isinstance(clock.today_tw(), date)
    # UTC 20:00 = 台北隔日 04:00 → today_tw 必須等於「UTC 時間 +8h」的日期
    assert clock.today_tw() == (n.astimezone(timezone.utc) + timedelta(hours=8)).date()


# ── fundnews：全空結果不得覆寫非空落檔 ───────────────────────
def _doc(brand=None, items=None, social=None):
    return {"as_of": "2026/07/04 05:00", "window_days": 7, "source": "test",
            "brand": brand or [], "social": social or [],
            "funds": [{"fund_id": "47", "items": items or []}], "highlights": []}


def test_fundnews_is_empty():
    assert fundnews.is_empty(None)
    assert fundnews.is_empty(_doc())
    assert not fundnews.is_empty(_doc(brand=[{"title": "x"}]))
    assert not fundnews.is_empty(_doc(items=[{"title": "x"}]))
    assert not fundnews.is_empty(_doc(social=[{"title": "x"}]))


def test_fundnews_save_keeps_previous_when_empty(tmp_path, monkeypatch):
    out = tmp_path / "fund_news.json"
    monkeypatch.setattr(fundnews, "OUT", out)

    # 先落一份非空
    path, saved = fundnews.save(_doc(brand=[{"title": "既有新聞"}]))
    assert saved and json.loads(out.read_text(encoding="utf-8"))["brand"]

    # 全空結果（如網路被擋）→ 不覆寫、舊資料仍在
    path, saved = fundnews.save(_doc())
    assert not saved
    assert json.loads(out.read_text(encoding="utf-8"))["brand"] == [{"title": "既有新聞"}]

    # 非空結果 → 正常覆寫
    path, saved = fundnews.save(_doc(brand=[{"title": "新一批"}]))
    assert saved
    assert json.loads(out.read_text(encoding="utf-8"))["brand"] == [{"title": "新一批"}]


def test_fundnews_save_empty_when_no_previous(tmp_path, monkeypatch):
    """無既有落檔時，全空 doc 仍要落檔（首跑標 as-of、儀表板顯示提示）。"""
    out = tmp_path / "fund_news.json"
    monkeypatch.setattr(fundnews, "OUT", out)
    path, saved = fundnews.save(_doc())
    assert saved and out.exists()


# ── fund_dashboard：鮮度徽章（逾期標紅；頂欄只標網頁更新時間、其餘分散各區塊） ──
def test_age_days_parses_both_formats():
    from arm import fund_dashboard as fd
    t = date(2026, 7, 4)
    assert fd._age_days("2026/07/02", t) == 2
    assert fd._age_days("2026-07-03 08:17", t) == 1
    assert fd._age_days("2026/07/04 11:12", t) == 0
    assert fd._age_days(None, t) is None
    assert fd._age_days("—", t) is None


def test_fresh_chip_marks_stale_and_gen():
    from arm import fund_dashboard as fd
    t = date(2026, 7, 10)
    assert "⚠ 9 天未更新" in fd._fresh_chip("NAV 日", "2026/07/01", 6, today=t)      # 9 > 6 → 標紅
    assert "stale" not in fd._fresh_chip("台股新聞", "2026-07-09", 3, today=t)       # 1 天前 → 正常
    assert "⚠ 缺資料" in fd._fresh_chip("基金新聞", None, 3, today=t)                # 缺值 → 標紅
    chip = fd._fresh_chip("網頁更新", "2026/07/10 06:50", None, today=t, gen=True)   # 帶 data-gen
    assert 'data-gen="2026/07/10 06:50"' in chip and "stale" not in chip


def test_freshness_view_top_shows_gen_and_aggregates_stale():
    from arm import fund_dashboard as fd
    t = date(2026, 7, 10)
    html_out = fd._freshness_view("2026/07/10 06:50", [
        ("NAV 日", "2026/07/01", 6),        # 9 天前 > 6 → 逾期
        ("台股新聞", "2026-07-09", 3),       # 正常
        ("復華新聞・社群", None, 3),          # 缺值 → 逾期
    ], today=t)
    assert "網頁更新時間" in html_out and 'data-gen="2026/07/10 06:50"' in html_out
    assert "2 項資料逾期未更新" in html_out
    assert "NAV 日、復華新聞・社群" in html_out


def test_freshness_view_all_fresh_no_warning():
    from arm import fund_dashboard as fd
    t = date(2026, 7, 4)
    html_out = fd._freshness_view("2026/07/04 11:12", [("NAV 日", "2026/07/03", 6),
                                                       ("台股新聞", "2026-07-04", 3)], today=t)
    assert "stale" not in html_out and "逾期" not in html_out


# ── fundnews：非新聞頁面過濾（2026-07-04 使用者回饋：我要新聞） ──
def test_is_news_title_rejects_non_news_pages():
    # 基金介紹頁（標題就只是基金名，可帶幣別/類別尾綴）
    assert not fundnews.is_news_title("復華傳家二號基金")
    assert not fundnews.is_news_title("復華美國新星基金-新臺幣")
    # 列表頁／平台頁／討論牆／淨值表
    assert not fundnews.is_news_title("最新復華全球大趨勢基金-新臺幣(FHI001)推薦文章、新聞｜投資網誌")
    assert not fundnews.is_news_title("復華亞太平衡基金(98636793)-股票最新新聞資訊與消息")
    assert not fundnews.is_news_title("討論牆 | 復華華人世紀基金，單月規模暴增58億")
    assert not fundnews.is_news_title("全台最大民營線上基金交易平台")
    assert not fundnews.is_news_title("復華投信旗下各基金淨值一覽表")
    assert not fundnews.is_news_title("")


def test_is_news_title_keeps_real_news():
    assert fundnews.is_news_title("復華兩檔ETF配息出爐！00929預估配0.38元創新高")
    assert fundnews.is_news_title("績效翻倍海外基金熱 復華全球物聯網、統一全球新科技等今年表現佳")
    assert fundnews.is_news_title("復華投信獲頒金鑽獎 台股基金團隊肯定")


def test_is_news_title_drops_content_farm(  ):
    # 2026-07 使用者要求：CMoney投資網誌式的「誇飾＋問句／揭密」點閱誘餌一律排除
    # （舊 test 曾把這類當真新聞保留，政策已更新）。
    assert not fundnews.is_news_title("復華華人世紀基金，單月規模暴增58億的背後秘密是什麼？")
    assert not fundnews.is_news_title("復華亞太神龍科技基金-新臺幣，同樣是買科技股，這檔近 1 年漲 240% 憑什麼？")


def test_clean_items_drops_junk_and_blocked_sources():
    items = [
        {"title": "復華傳家二號基金", "source": "鉅亨網"},                    # 介紹頁 → 剔除
        {"title": "全台最大民營線上基金交易平台", "source": "鉅亨買基金"},      # 平台頁標題 → 剔除
        {"title": "復華00929配息創新高", "source": "富聯網"},                 # 黑名單來源 → 剔除
        {"title": "復華00929配息創新高 - 工商時報", "source": "工商時報"},      # 真新聞 → 保留（剝尾綴）
        {"title": "復華全球平衡基金經理人觀點：下半年布局", "source": "鉅亨買基金"},  # 鉅亨新聞稿 → 保留
    ]
    out = fundnews._clean_items(items)
    assert [i["title"] for i in out] == ["復華00929配息創新高",
                                         "復華全球平衡基金經理人觀點：下半年布局"]


# ── 深度報告卡（2026-07-04 使用者需求：更多深度報告、保底 1 篇） ──
def test_card_etype_recognizes_deep():
    from arm import usnews
    assert usnews._card_etype("來源：經濟日報｜2026/07/04｜【深度】｜重要度 7/10") == "deep"
    assert usnews._card_etype("來源：X｜【新事件】｜重要度 6/10") == "new"


def test_news_badges_renders_deep():
    from arm import fund_dashboard as fd
    b = fd._news_badges("deep", 7)
    assert ">深度<" in b and 'netype deep' in b and "重要度 7" in b


def test_specs_require_deep_pick():
    from arm import twnews, usnews
    assert "保底 1 篇" in usnews.SPEC_V1 and "【深度】" in usnews.SPEC_V1
    assert "保底 1 篇" in twnews.SPEC_POST and "保底 1 篇" in twnews.SPEC_PRE


def test_specs_carry_depth_and_move_rules():
    # 2026-08-19 使用者：排程模型內容不夠深入＋每卡加「漲跌分析」欄——
    # 深度與漲跌分析規則須注入五份版型（提示包是子代理唯一輸入，掉了規則＝白改）
    from arm import macronews, twnews, usnews
    for spec in (usnews.SPEC_V1, usnews.SPEC_V2, twnews.SPEC_PRE, twnews.SPEC_POST,
                 macronews.SPEC_MACRO):
        assert "漲跌分析" in spec                      # 欄位＋move_note 規格
        assert "後續觀察" in spec and "因果鏈" in spec   # depth_note 硬性深度要求
        assert "粗體" in spec                          # LABEL_RULE 源頭防呆
    # 版型字數上限已放寬（120–180 是舊的淺層上限，勿改回去）
    assert "200–320 字" in usnews.SPEC_V1 and "180–300 字" in twnews.SPEC_POST


def test_specs_carry_selection_rules():
    # 選題邏輯由上而下（2026-08-19 使用者：「要真的篩到熱門、市場真正重要的新聞」）：
    # 選題五步＋評分校準注入五份版型；「清單外異常照抓」的開放式判準必須在（防閘門限縮選題範圍）
    from arm import macronews, twnews, usnews
    for spec in (usnews.SPEC_V1, usnews.SPEC_V2, twnews.SPEC_PRE, twnews.SPEC_POST,
                 macronews.SPEC_MACRO):
        assert "選題流程" in spec and "補漏自查" in spec       # pick_note 五步
        assert "評分校準" in spec and "湊卡工具" in spec       # SEV_RUBRIC 證據錨定
        # 2026-08-31 使用者定調：重要度＝投資影響本位——聲量不加分、與漲跌分析互鎖、地緣走資產通道
        assert "評分本位＝「對投資的影響」" in spec and "資產通道" in spec
        assert "不能單獨撐起 7 分" in spec and "至多 6 分" in spec
        assert "清單外" in spec                               # 開放式掃描判準（勿刪）
    # 2026-08-31 伊朗案：持續性議題須查最近 24 小時新事件，不可用同題舊稿代替
    assert "持續性議題的最新一手進展" in macronews.SPEC_MACRO
    assert "今晨亞洲盤的國際突發" in twnews.SPEC_PRE
    assert "經濟日報頭版頭條" in twnews.SPEC_PRE               # 台股掃描清單保留頭條必收
    assert "已公布的重大數據" in macronews.SPEC_MACRO          # 總經掃描含行事曆已公布項


def test_market_flags_and_anchor():
    # 市場變動錨定：官方落檔 → 最新一日變動＋大變動旗標；過期序列不旗標；讀不到＝空字串
    from datetime import date
    from arm import usnews
    chips = {"series": {
        "sox": {"2026-08-17": 12621.0, "2026-08-18": 11992.46},      # -4.98% → 旗標
        "gold": {"2026-08-17": 4400.0, "2026-08-18": 4410.0},        # +0.23% → 不旗標
        "us10y": {"2026-08-17": 4.60, "2026-08-18": 4.72},           # +12bp → 旗標
        "inst_total": {"2026-08-18": -420.5},                        # 流量 420.5 億 → 旗標
        "dxy": {"2026-08-01": 99.0, "2026-08-02": 100.5},            # 過期 → 不旗標
    }}
    f = usnews.market_flags(date(2026, 8, 19), chips=chips)
    assert f["sox"]["flag"] and f["sox"]["fresh"] and "-4.98%" in f["sox"]["disp"]
    assert not f["gold"]["flag"]
    assert f["us10y"]["flag"] and "+12bp" in f["us10y"]["disp"]
    assert f["inst_total"]["flag"] and "賣超" in f["inst_total"]["disp"]
    assert not f["dxy"]["fresh"] and not f["dxy"]["flag"]            # 過期＝不旗標（閘門不誤傷）
    # anchor 文案：保底必答題＋「不是選題範圍」原則必須明寫（2026-08-19 使用者要求）
    import unittest.mock as _m
    with _m.patch.object(usnews, "_load_chips", lambda: chips):
        txt = usnews.market_anchor("us", date(2026, 8, 19))
        assert "⚑" in txt and "不是選題範圍" in txt and "費半" in txt
        assert "三大法人" not in txt                                 # us 版不含台股籌碼列
        tw = usnews.market_anchor("tw_pre", date(2026, 8, 19))
        assert "三大法人" in tw and "賣超 420.5 億" in tw
    with _m.patch.object(usnews, "_load_chips", lambda: {}):
        assert usnews.market_anchor("us", date(2026, 8, 19)) == ""   # fail-open


def test_factcheck_chip_counts_from_items_not_header(tmp_path, monkeypatch):
    """數字核對章以 items 為準，表頭去正規化計數只當後備。

    2026-07-28 實例：兩個 daily.yml run 因 concurrency 依 event_name 分組而同時
    commit，rebase 的三方文字合併把「表頭」與「items」湊成不同 run 的版本——明細
    0 紅、表頭卻寫 red 2，儀表板因而掛出假的 🔴 警示章。表頭與明細衝突時，
    明細才是事實來源。
    """
    from arm import fund_dashboard as fd
    t = date(2026, 7, 28)
    monkeypatch.setattr(fd, "ROOT_DIR", tmp_path)
    (tmp_path / "data").mkdir()
    fp = tmp_path / "data" / "factcheck.json"

    def _write(doc):
        fp.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    base = {"date": "2026-07-28", "as_of": "2026-07-28 10:17"}
    green_items = [{"status": "🟢"}, {"status": "🟢"}, {"status": "⚪"}]

    # 表頭謊稱 red 2、明細實為 0 紅 → 不得掛紅章，且綠數以明細為準（2 而非表頭 11）
    _write({**base, "green": 11, "red": 2, "skipped": 0, "items": green_items})
    chip = fd._factcheck_chip(today=t)
    assert "🔴" not in chip and "🟢 2 項與官方相符" in chip

    # 真的有紅 → 照常掛紅章，計數同樣取自明細
    _write({**base, "green": 11, "red": 0, "items": green_items + [{"status": "🔴"}]})
    assert "🔴 1 項與官方不符" in fd._factcheck_chip(today=t)

    # 無 items（舊格式）→ 後備讀表頭，維持相容
    _write({**base, "green": 5, "red": 3})
    assert "🔴 3 項與官方不符" in fd._factcheck_chip(today=t)

    # 非今日檔一律不顯示（沿用既有規則）
    _write({"date": "2026-07-27", "as_of": "x", "items": [{"status": "🔴"}]})
    assert fd._factcheck_chip(today=t) == ""


def test_factcheck_chip_red_expands_detail(tmp_path, monkeypatch):
    """🔴 章可點展開「哪一項不符」明細（2026-08-07 使用者需求：讀的時候可排除、
    不佔版面）：收合 summary 文字不變（既有斷言相容），展開列出
    指標中文名（日期）：報告值 → 官方值；缺明細欄位的舊格式退回純 chip。"""
    from arm import fund_dashboard as fd
    t = date(2026, 8, 7)
    monkeypatch.setattr(fd, "ROOT_DIR", tmp_path)
    (tmp_path / "data").mkdir()
    fp = tmp_path / "data" / "factcheck.json"
    fp.write_text(json.dumps({
        "date": "2026-08-07", "as_of": "2026-08-07 07:10",
        "items": [{"status": "🟢", "kind": "index_chg"},
                  {"status": "🔴", "kind": "inst_total", "claimed": 45.6,
                   "official": 51.15386177, "day": "08/06"}]},
        ensure_ascii=False), encoding="utf-8")
    chip = fd._factcheck_chip(today=t)
    assert "🔴 1 項與官方不符" in chip            # 收合字樣不變
    assert "<details" in chip and "fcd" in chip   # 可展開
    assert "三大法人合計買賣超" in chip and "（08/06）" in chip
    assert "報告 45.6" in chip and "官方 <b>51.15</b> 億" in chip

    # 舊格式（紅項無 claimed/official）→ 沒有明細可列，退回純 chip 不出 <details>
    fp.write_text(json.dumps({"date": "2026-08-07", "as_of": "x",
                              "items": [{"status": "🔴"}]}, ensure_ascii=False),
                  encoding="utf-8")
    chip2 = fd._factcheck_chip(today=t)
    assert "🔴 1 項與官方不符" in chip2 and "<details" not in chip2


def test_yt_watch_chip_flags_zero_youtube(tmp_path, monkeypatch):
    """社群 YouTube 0 支警示章（2026-08-07 使用者：每次更新順帶查 YouTube）：
    「今日」檔、social 段存在而無 youtube 項才警；有影片／舊 schema 無 social 鍵／
    無檔／非今日檔（鮮度問題歸逾期清單）皆不警。"""
    from arm import fund_dashboard as fd
    t = date(2026, 8, 7)
    monkeypatch.setattr(fd, "ROOT_DIR", tmp_path)
    (tmp_path / "data").mkdir()
    fp = tmp_path / "data" / "fund_news.json"
    asof = {"as_of": "2026/08/07 08:07"}

    assert fd._yt_watch_chip(today=t) == ""                # 無檔不警

    fp.write_text(json.dumps({**asof, "brand": []}), encoding="utf-8")
    assert fd._yt_watch_chip(today=t) == ""                # 舊 schema 無 social 鍵不警

    fp.write_text(json.dumps({**asof, "social": [{"platform": "ptt", "title": "x"}]}),
                  encoding="utf-8")
    chip = fd._yt_watch_chip(today=t)
    assert "社群 YouTube" in chip and "🔴 0 支" in chip     # 只剩 PTT＝YouTube 異常

    fp.write_text(json.dumps({**asof, "social": []}), encoding="utf-8")
    assert "🔴 0 支" in fd._yt_watch_chip(today=t)         # 整段空同樣要警

    fp.write_text(json.dumps({"as_of": "2026/08/06 12:28", "social": []}),
                  encoding="utf-8")
    assert fd._yt_watch_chip(today=t) == ""                # 非今日檔＝鮮度問題、不重複警

    fp.write_text(json.dumps({**asof, "social": [{"platform": "youtube", "title": "y"}]}),
                  encoding="utf-8")
    assert fd._yt_watch_chip(today=t) == ""                # 有影片＝正常


def test_brief_style_in_all_five_templates():
    """速覽／總覽文風規格要進五份版型（美股 v1/v2、台股盤前/盤後、總經）——
    生效條件同其他提示包規則：merge 進 main 後做一次「排程搬家」。"""
    from arm import macronews, twnews, usnews
    assert "≤ 220 字" in usnews.BRIEF_STYLE and "粗體要有落點" in usnews.BRIEF_STYLE
    assert "段名與內規說明一律不寫" in usnews.BRIEF_STYLE      # 「一句帶過」那類標籤
    for spec in (usnews.SPEC_V1, usnews.SPEC_V2, twnews.SPEC_PRE, twnews.SPEC_POST,
                 macronews.SPEC_MACRO):
        assert "速覽／總覽段的寫法" in spec


def test_card_read_rule_in_all_five_templates():
    """卡片可讀性規格要進五份版型；同時確認 HILITE_RULE 的粗體上限已放寬
    （原本「每欄至多 2 處」正是台股卡只有 0–3 處粗體的來源）。"""
    from arm import macronews, twnews, usnews
    assert "每句 ≤40 字" in usnews.READ_RULE and "結論詞組也要標" in usnews.READ_RULE
    assert "每欄 **2–3 處**" in usnews.HILITE_RULE
    assert "每欄至多 2 處" not in usnews.HILITE_RULE   # 舊上限指令已移除（註解裡的引述不算）
    for spec in (usnews.SPEC_V1, usnews.SPEC_V2, twnews.SPEC_PRE, twnews.SPEC_POST,
                 macronews.SPEC_MACRO):
        assert "卡片可讀性" in spec


def test_card_field_layer_line_breaks():
    """欄內層次敘述自動斷行（純呈現層，今日既有報告重建即生效）：
    只認明確列舉標記，句號不亂斷——亂斷會把連續敘述切碎、比不斷更難讀。"""
    from arm import fund_dashboard as fd
    out = fd._lines("三層拆開看。第一層是資金：內容甲。第二層是訂單：內容乙。後續觀察：下週法說。")
    assert out.count('<div class="nln">') == 2 and '<div class="nwatch">後續觀察' in out
    assert fd._lines("甲公司公告。乙公司跟進。") == "甲公司公告。乙公司跟進。"   # 無標記不動
    assert ".nwatch{" in fd._CSS and ".nln{" in fd._CSS
