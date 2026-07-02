"""多市場參數化單測（含 D1b/D2b/D3b/D4 決策）：市場註冊表、台股 config 完整性、
台股新聞模組、整合頁上層切換、fof 持股解析。全離線、零網路。
"""
import json
from datetime import date
from pathlib import Path

import pytest

from arm import (config, fund_dashboard, fund_intro, fund_mentions, indicators,
                 markets, twnews, usnews)
from arm.connectors import fhfund

ROOT = Path(__file__).resolve().parent.parent
# D3(b)：同基金多類別只留主類別（捨 123 台灣科技高股息B、125 全方位TISA）→ 12 檔
TW_IDS = {"08", "117", "122", "15", "03", "01", "06", "11", "13", "04", "07", "79"}


# ── 市場註冊表 ────────────────────────────────────────────────
def test_markets_registry_has_global_and_tw():
    assert "global" in markets.MARKETS and "tw" in markets.MARKETS
    assert markets.DEFAULT == "global"


def test_markets_get_unknown_raises():
    with pytest.raises(KeyError):
        markets.get("nope")


def test_markets_get_none_is_default():
    assert markets.get(None) is markets.MARKETS["global"]


def test_market_fields_present():
    for key in ("global", "tw"):
        m = markets.get(key)
        for f in ("funds", "data", "out", "title", "subtitle", "news",
                  "news_label", "tab_label"):
            assert m.get(f), f"{key} 缺欄位 {f}"


def test_tw_market_outputs_distinct_from_global():
    g, tw = markets.get("global"), markets.get("tw")
    assert g["out"] != tw["out"] and g["data"] != tw["data"] and g["funds"] != tw["funds"]
    assert tw["out"] == "tw.html" and tw["data"] == "funds_tw"
    assert g["news"] == "us" and tw["news"] == "tw"       # D1(b)：台股專用新聞源
    assert g["tab_label"] == "海外" and tw["tab_label"] == "台股"


# ── 台股 config 完整性（D3b）──────────────────────────────────
def test_funds_tw_json_exists_and_valid():
    fp = ROOT / "config" / "funds_tw.json"
    assert fp.exists()
    assert "funds" in json.loads(fp.read_text(encoding="utf-8"))


def test_funds_tw_has_12_expected_ids():
    tw = config.funds("tw")
    assert len(tw) == 12
    assert {str(f["id"]) for f in tw} == TW_IDS


def test_funds_tw_drops_duplicate_classes():
    ids = {str(f["id"]) for f in config.funds("tw")}
    assert "123" not in ids and "125" not in ids       # 捨 B類型/ TISA類型
    assert "122" in ids and "15" in ids                # 留 A類型主類別


def test_funds_tw_ids_unique():
    ids = [str(f["id"]) for f in config.funds("tw")]
    assert len(ids) == len(set(ids))


def test_funds_tw_groups_valid():
    counts = {}
    for f in config.funds("tw"):
        assert f.get("name"), f"{f.get('id')} 缺 name"
        g = f.get("group")
        assert g in {"domestic_equity", "domestic_balanced", "fof"}, g
        counts[g] = counts.get(g, 0) + 1
    assert counts == {"domestic_equity": 7, "domestic_balanced": 4, "fof": 1}


def test_funds_tw_fund_lookup():
    assert config.fund("79", "tw")["group"] == "fof"
    with pytest.raises(KeyError):
        config.fund("999", "tw")


def test_global_funds_unchanged_by_default():
    g = config.funds()
    assert config.funds("global") == g
    assert all(f["group"] in {"global_equity", "global_balanced"} for f in g)


# ── group label / 資料夾 ──────────────────────────────────────
def test_group_labels_cover_tw_groups():
    for g, label in [("domestic_equity", "國內股票型"),
                     ("domestic_balanced", "國內平衡型"), ("fof", "組合型")]:
        assert fund_intro.GROUP_LABEL[g] == label


def test_funds_dir_by_market():
    assert fund_intro.funds_dir("global").name == "funds"
    assert fund_intro.funds_dir("tw").name == "funds_tw"


def test_all_funds_tw_returns_list():
    assert isinstance(fund_intro.all_funds("tw"), list)


def test_load_reads_tw_dir():
    tw_dir = fund_intro.funds_dir("tw")
    tw_dir.mkdir(parents=True, exist_ok=True)
    fp = tw_dir / "999998.json"
    fp.write_text(json.dumps({
        "fund_id": "999998", "group": "domestic_equity", "name": "測試基金",
        "top_holdings": [{"name": "台積電", "weight": 8.72}],
    }, ensure_ascii=False), encoding="utf-8")
    try:
        doc = fund_intro.load("999998", "tw")
        assert doc is not None
        assert doc["group_label"] == "國內股票型"
        assert doc["top_holdings"][0]["intro"] and doc["top_holdings"][0]["ticker"] == "2330"
    finally:
        fp.unlink(missing_ok=True)


# ── 台股新聞模組（D1b）────────────────────────────────────────
def test_twnews_specs_and_labels():
    assert "台股盤後" in twnews.SPEC_V1
    assert "盤前美股" in twnews.SPEC_V2 and "ADR" in twnews.SPEC_V2
    assert twnews.V1_LABEL == "台股盤後重點" and twnews.V2_LABEL == "盤前美股影響"


def test_twnews_reuses_usnews_compliance():
    assert twnews.BANNED is usnews.BANNED
    assert twnews.compliance_scan("目標價 100 元") == ["目標價"]
    assert twnews.compliance_scan("並非保證獲利") == []          # 否定詞不誤判
    assert twnews.compliance_scan(twnews.DISCLOSURE) == []       # 揭露段乾淨


def test_twnews_session_dates():
    assert twnews.tw_session_date(date(2026, 7, 6)) == date(2026, 7, 6)  # Mon
    assert twnews.tw_session_date(date(2026, 7, 5)) == date(2026, 7, 3)  # Sun→Fri
    assert twnews.us_session_date(date(2026, 7, 6)) == date(2026, 7, 3)


def test_twnews_disclosure_is_domestic():
    # 台股（境內）揭露段：談受益憑證與平衡型債券風險，不談境外匯率
    assert "受益憑證" in twnews.DISCLOSURE and "債券" in twnews.DISCLOSURE
    assert "境外" not in twnews.DISCLOSURE


def test_news_modules_have_symmetric_interface():
    for mod in (usnews, twnews):
        assert hasattr(mod, "load_latest") and hasattr(mod, "V1_LABEL")
        assert hasattr(mod, "V2_LABEL") and hasattr(mod, "EMPTY_HINT")


# ── 整合頁上層切換（D2b）─────────────────────────────────────
def test_render_combined_has_market_switch():
    html = fund_dashboard.render_combined(("global", "tw"))
    assert '<!doctype html>' in html.lower()
    assert 'class="mtab' in html
    assert 'data-market="global"' in html and 'data-market="tw"' in html
    assert html.count('class="market') == 2       # 兩個市場面板
    assert "海外" in html and "台股" in html


def test_render_combined_css_only_tabs():
    # 分頁切換為純 CSS（radio+label）：沙箱預覽/禁 script 環境也能按，頁面零 JS
    html = fund_dashboard.render_combined(("global", "tw"))
    assert "<script>" not in html
    assert 'id="mkt-tw"' in html and 'id="mkt-global"' in html
    assert '#mkt-tw:checked~.market[data-market="tw"]{display:block}' in html
    # 每檔基金都有對應的顯示規則與分頁 label
    for m in ("global", "tw"):
        for f in config.funds(m):
            fid = f["id"]
            assert f'#fund-{m}-{fid}:checked~.fund[data-fund="{fid}"]' in html, (m, fid)
            assert f'for="fund-{m}-{fid}"' in html, (m, fid)
    # 新聞版型切換 radio（各市場獨立 name，不互相干擾）
    assert 'name="nv-tw"' in html and 'name="nv-global"' in html


def test_news_doc_card_parse_and_lead():
    md = ("### 卡 1｜台積電法說前震盪（聯合新聞網｜2026/07/02｜【事件更新】）\n"
          "1. **新聞摘要**：ADR 重挫 7%。\n"
          "2. **一句話重點**：ADR 重挫、現股抗跌。\n"
          "3. **對公司影響**：短線評價修正。\n"
          "6. **參考資料**：聯合新聞網（2026/07/02）。\n")
    out = fund_dashboard._render_news_doc(md)
    assert 'class="ncard"' in out
    assert 'class="nlead"' in out and "ADR 重挫、現股抗跌" in out   # 一句話重點置頂
    assert '<span class="tag">事件更新</span>' in out              # 屬性成徽章
    assert "<details" in out and "參考資料" in out                 # 參考資料摺疊


def test_news_doc_fallback_to_md():
    # 無新聞卡結構 → 整段回退 markdown 渲染，不噴錯
    out = fund_dashboard._render_news_doc("## 標題\n\n一般段落而已。")
    assert "ncard" not in out and "一般段落而已" in out


def test_news_doc_fineprint_collapsed():
    md = ("### 卡 1｜X（來源｜2026/07/02｜【新消息】）\n"
          "1. **新聞摘要**：a。\n2. **一句話重點**：b。\n\n"
          "## 資料侷限說明\n- 某數字未及查證。\n\n## I. 合規揭露\n本資料僅供參考。\n")
    out = fund_dashboard._render_news_doc(md)
    assert out.count('class="fineprint"') == 2                     # 兩段雜訊皆摺疊
    assert "某數字未及查證" in out and "本資料僅供參考" in out


def test_render_single_market_has_one_panel():
    assert fund_dashboard.render("global").count('class="market') == 1
    assert fund_dashboard.render("tw").count('class="market') == 1


def test_render_tw_smoke():
    html = fund_dashboard.render("tw")
    assert "復華台股基金追蹤版本" in html
    assert "Fuh Hwa Taiwan Fund Radar" in html


def test_render_global_title_unchanged():
    html = fund_dashboard.render("global")
    assert "復華基金追蹤版本" in html and "Fuh Hwa Fund Radar" in html


def test_news_dispatch_by_market():
    # tw 面板應嵌台股新聞區塊標題；global 面板為昨夜美股標題
    tw = fund_dashboard.render("tw")
    assert "台股盤後重點 ＋ 盤前美股影響" in tw
    g = fund_dashboard.render("global")
    assert "昨夜美股重大新聞" in g


# ── fof 持股解析與呈現（D4）──────────────────────────────────
def test_fof_extract_holdings_two_col():
    rows = [["復華台灣科技優息ETF", "18.20%"], ["元大台灣50", "12.50%"]]
    hs = fhfund._extract_holdings(rows)
    assert hs[0] == {"sector": None, "name": "復華台灣科技優息ETF", "weight": 18.2}
    assert hs[1]["weight"] == 12.5


def test_stock_extract_holdings_three_col():
    rows = [["半導體", "台積電", "8.72%"]]
    assert fhfund._extract_holdings(rows) == [{"sector": "半導體", "name": "台積電", "weight": 8.72}]


def test_kind_of_uses_sector_shape_not_heading():
    # 實測發現：79 台灣智能的持股仍掛在標準「十大持有標的」標題下，但無產業欄
    # （因持有的是其他基金）；判定應看欄位形狀，不能只看抓到哪個標題。
    assert fhfund._kind_of([{"sector": "半導體", "name": "台積電", "weight": 8.72}]) == "stock"
    assert fhfund._kind_of([{"sector": None, "name": "元大台灣50", "weight": 8.59}]) == "fund"
    assert fhfund._kind_of([]) is None


def test_fund79_real_snapshot_labelled_fund_not_stock():
    # 迴歸測試：實抓（GitHub Actions daily.yml 手動觸發）驗證 79 十大持有標的表確實存在，
    # 只是無產業欄；holdings_kind 須為 fund 而非 stock（曾經誤標）。
    fp = ROOT / "data" / "funds_tw" / "79.json"
    if not fp.exists():
        pytest.skip("data/funds_tw/79.json 尚未抓取（需可連外環境）")
    doc = json.loads(fp.read_text(encoding="utf-8"))
    assert doc.get("holdings_kind") == "fund"
    assert doc.get("top_holdings"), "79 應有持股（掛在十大持有標的標題下，僅無產業欄）"
    assert all(h.get("sector") is None for h in doc["top_holdings"])


def test_fof_heading_fallback_parses():
    html = ('<h3>前十大投資標的</h3><table class="fundTable"><tbody>'
            '<tr><td>復華台灣科技優息ETF</td><td><span>18.20%</span></td></tr>'
            '</tbody></table>')
    rows = fhfund._rows_of_table_after(html, "前十大投資標的")
    hs = fhfund._extract_holdings(rows)
    assert hs and hs[0]["name"] == "復華台灣科技優息ETF"


def test_svg_pairs_end_anchor_fallback():
    # fof 頁無「十大持有標的」標題 → sector_alloc 端錨點退用 fof 標的表標題
    html = ('產業配置<text>50.00 %</text><text>ETF</text>前十大投資標的')
    assert fhfund._svg_pairs(html, "產業配置", "十大持有標的") == []          # 單一端錨點缺 → 空
    pairs = fhfund._svg_pairs(html, "產業配置", ["十大持有標的", "前十大投資標的"])
    assert pairs == [{"name": "ETF", "weight": 50.0}]                        # 候選清單退路可抓到
    # 既有 str 介面不變（向後相容）
    html2 = ('國家配置<text>60.76 %</text><text>美國</text>產業配置')
    assert fhfund._svg_pairs(html2, "國家配置", "產業配置") == [{"name": "美國", "weight": 60.76}]


def test_fetch_holdings_market_flag_requires_value():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "fetch_holdings", ROOT / "scripts" / "fetch_holdings.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod._parse_args(["--market", "tw", "06"]) == ("tw", ["06"])
    assert mod._parse_args(["--market=tw"]) == ("tw", [])
    with pytest.raises(SystemExit):
        mod._parse_args(["--market"])          # 缺值 → 明確報錯而非 IndexError


def test_dashboard_fof_note_when_empty():
    doc = {"fund_id": "79", "name": "復華台灣智能基金", "group": "fof",
           "group_label": "組合型", "top_holdings": [], "returns": {},
           "monthly_report": "https://x/m.pdf"}
    card = fund_dashboard._fund_card(doc, 0)
    assert "fund-of-funds" in card and "基金月報" in card


def test_dashboard_fof_fund_holdings_labelled():
    doc = {"fund_id": "79", "name": "復華台灣智能基金", "group": "fof",
           "group_label": "組合型", "holdings_kind": "fund", "returns": {},
           "top_holdings": [{"sector": None, "name": "元大台灣50", "weight": 12.5}]}
    card = fund_dashboard._fund_card(doc, 0)
    assert "投資標的（基金／ETF）" in card and "十大投資標的" in card


# ── 台股個股簡介覆蓋（todo 實測提及的個股）──────────────────
def test_known_tw_holdings_have_profiles():
    profs = fund_intro._profiles()
    for name in ["台積電", "台達電", "欣興", "台光電", "旺矽"]:
        assert profs.get(name) and profs[name].get("intro"), name


# ── 重點觀察數據（indicators）────────────────────────────────
def test_indicators_validate():
    ok = {"date": "2026-07-02", "items": [
        {"market": "tw", "name": "x", "value": "1", "as_of": "2026/07/02", "source": "s"}]}
    assert indicators.validate(ok) == []
    assert indicators.validate({"date": "bad", "items": []})            # 兩項錯誤
    assert any("market" in e for e in indicators.validate(
        {"date": "2026-07-02", "items": [{"market": "xx", "name": "x", "value": "1",
                                          "as_of": "d", "source": "s"}]}))


def test_indicators_for_market_filter():
    doc = {"date": "2026-07-02", "items": [
        {"market": "us", "name": "a", "value": "1", "as_of": "d", "source": "s"},
        {"market": "tw", "name": "b", "value": "2", "as_of": "d", "source": "s"},
        {"market": "both", "name": "c", "value": "3", "as_of": "d", "source": "s"}]}
    assert [i["name"] for i in indicators.for_market(doc, "global")] == ["a", "c"]
    assert [i["name"] for i in indicators.for_market(doc, "tw")] == ["b", "c"]
    assert indicators.for_market(None, "tw") == []


def test_indicators_latest_loads_and_renders():
    doc = indicators.load_latest()
    if not doc:
        pytest.skip("尚無 reports/indicators/{date}.json")
    assert indicators.validate(doc) == []
    html = fund_dashboard._indicators_section("tw")
    assert "重點觀察數據" in html and 'class="ind"' in html


def test_indicators_change_color_class():
    html = fund_dashboard._indicators_section("tw")
    if not html:
        pytest.skip("尚無指標資料")
    assert 'class="ic dn"' in html or 'class="ic up"' in html   # ▲/▼ 有配色


# ── 持股深入介紹（detail）────────────────────────────────────
def test_profiles_detail_on_major_holdings():
    profs = fund_intro._profiles()
    for name in ["台積電", "台達電", "台光電", "群聯", "智邦", "MICRON TECHNOLOGY INC"]:
        assert profs[name].get("detail"), f"{name} 缺 detail"
        assert len(profs[name]["detail"]) > len(profs[name]["intro"]), name


def test_holdings_table_renders_detail_expandable():
    doc = {"fund_id": "x", "group": "domestic_equity", "returns": {},
           "top_holdings": [{"name": "台積電", "weight": 8.72, "sector": "半導體",
                             "intro": "一句話", "detail": "更深入的兩三句介紹。"}]}
    html = fund_dashboard._holdings_table(doc)
    assert '<details class="hmore">' in html and "更深入的兩三句介紹" in html


def test_load_attaches_detail():
    tw_dir = fund_intro.funds_dir("tw")
    tw_dir.mkdir(parents=True, exist_ok=True)
    fp = tw_dir / "999997.json"
    fp.write_text(json.dumps({"fund_id": "999997", "group": "domestic_equity",
                              "top_holdings": [{"name": "台積電", "weight": 1}]},
                             ensure_ascii=False), encoding="utf-8")
    try:
        doc = fund_intro.load("999997", "tw")
        assert doc["top_holdings"][0]["detail"]          # detail 已掛上
    finally:
        fp.unlink(missing_ok=True)


# ── 台股新聞 spec：重大分析（非技術面）──────────────────────
def test_twnews_spec_requires_fundamental_analysis():
    assert "重大分析與基本面觀察" in twnews.SPEC_V1
    assert "非技術面" in twnews.SPEC_V1


# ── 基金動態雷達（fund_mentions）────────────────────────────
def test_query_terms_strips_suffixes():
    assert '"復華中小精選"' in fund_mentions.query_terms("復華中小精選基金")
    assert '"復華台灣科技高股息"' in fund_mentions.query_terms("復華台灣科技高股息基金A類型")
    t = fund_mentions.query_terms("復華美國新星基金-新臺幣")
    assert '"復華美國新星"' in t
    assert fund_mentions.query_terms("") == []


def test_mentions_merged_combines_auto_and_social(tmp_path, monkeypatch):
    auto_dir = tmp_path / "auto"; social_dir = tmp_path / "social"
    auto_dir.mkdir(); social_dir.mkdir()
    monkeypatch.setattr(fund_mentions, "AUTO_DIR", auto_dir)
    monkeypatch.setattr(fund_mentions, "SOCIAL_DIR", social_dir)
    (auto_dir / "tw.json").write_text(json.dumps({
        "fetched_at": "2026-07-02 08:30", "market": "tw",
        "company": [{"title": "復華投信新聞", "source": "經濟日報", "date": "2026-07-02 07:00"}],
        "funds": [{"id": "06", "name": "復華數位經濟基金",
                   "items": [{"title": "數位經濟基金報導", "source": "鉅亨網",
                              "date": "2026-07-01 10:00", "url": "https://x"}]}],
    }, ensure_ascii=False), encoding="utf-8")
    (social_dir / "2026-07-02.json").write_text(json.dumps({
        "date": "2026-07-02", "items": [
            {"fund_id": "06", "kind": "social", "title": "Dcard 討論串",
             "source": "Dcard", "date": "2026-07-02"},
            {"fund_id": "", "kind": "ad", "title": "FB 形象廣告",
             "source": "Facebook", "date": "2026-06-30"}]}, ensure_ascii=False),
        encoding="utf-8")
    cfg = [{"id": "06", "name": "復華數位經濟基金"}, {"id": "11", "name": "復華人生目標基金"}]
    doc = fund_mentions.merged("tw", cfg)
    assert doc["as_of"] == "2026-07-02 08:30"
    assert len(doc["company"]) == 2                      # 公司新聞 + 對不到基金的廣告
    f06 = next(f for f in doc["funds"] if f["id"] == "06")
    assert len(f06["items"]) == 2                        # 自動新聞 + 社群
    assert {i["kind"] for i in f06["items"]} == {"news", "social"}
    assert all(i.get("date") for i in f06["items"])      # 每筆皆有資料時間
    f11 = next(f for f in doc["funds"] if f["id"] == "11")
    assert f11["items"] == []


def test_mentions_merged_empty_is_safe():
    doc = fund_mentions.merged("nope", [{"id": "1", "name": "x"}])
    assert doc["company"] == [] and doc["funds"][0]["items"] == []


def test_mentions_section_renders_or_hints():
    html = fund_dashboard._mentions_section("tw")
    assert "基金動態雷達" in html
    assert "資料時間" in html                              # 區塊標頭附資料時間
    # 無資料時給啟用提示、不崩
    assert ("fetch_mentions" in html) or ('class="mit"' in html)


def test_indicators_no_memory_price():
    # 記憶體報價已依需求移除（indicators 資料與 SPEC 皆不含）
    doc = indicators.load_latest()
    if doc:
        names = " ".join(i["name"] for i in doc["items"])
        assert "DRAM" not in names and "DDR5" not in names
    assert "DRAM" not in indicators.SPEC
