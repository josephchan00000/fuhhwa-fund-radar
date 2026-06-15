"""M6 文案層測試（離線）：報告解析、數字防杜撰、合規兩層不擋、baseline、LLM 覆寫把關、prompt-pack。"""
from arm import copy as cp
from arm.copy import baseline, compliance, numbers, prompt_pack
from arm.copy.parse import parse_text

_REPORT = """# 每日想法組合 — 復華台灣未來50主動式ETF（00991A）  資料日 2026-06-12
> 主題日加重：逆向誠實　|　收盤 19.05　折溢價 +0.21%　AUM 592億　績效基準：NAV 含息總報酬

### 1. [題材] 🟡
- **想法**：本檔押 19.3%，2/2 檔成分股翻紅
- 佐證：題材熱度 55
- 內容形式：題材連連看
  - ⚠️合規[中] `(績效陳述)`：績效訴求需附免責 → 建議句尾補免責

### 2. [籌碼] 🟢
- **想法**：汰弱留強：加碼 臻鼎-KY、減碼 致茂電子，主動換馬
- 佐證：+2,000張 / -449張
- 內容形式：換股快報

### 5. [績效] 🟡
- **想法**：成立以來淨值含息大漲 97%，身價翻倍故事
- 佐證：成立來 NAV 總報酬 +97%
- 內容形式：戰報卡
"""


# ── 解析 ──
def test_parse_report():
    doc = parse_text(_REPORT)
    assert doc.etf_id == "00991A"
    assert doc.name == "復華台灣未來50主動式ETF"
    assert doc.date == "2026-06-12"
    assert "收盤 19.05" in doc.header
    assert len(doc.ideas) == 3
    i1 = doc.ideas[0]
    assert i1.idx == 1 and i1.category == "題材" and i1.conf == "🟡"
    assert "19.3%" in i1.headline and "題材熱度 55" in i1.evidence
    assert i1.content_format == "題材連連看"
    assert i1.src_compliance                       # 報告既有合規標注被帶入


# ── 數字防杜撰 ──
def test_numbers_extract_and_normalize():
    assert numbers.extract("漲 19.3%，2/2 檔，+2,000張") == {"19.3", "2", "2000"}
    assert numbers._norm("97.0") == "97" and numbers._norm("29.10") == "29.1"


def test_numbers_check_flags_unseen():
    allowed = numbers.allowed_set("成立來 +97%", "規模 592億")
    assert numbers.check("淨值漲 97%、規模 592億", allowed) == []
    assert numbers.check("三年漲 120%", allowed) == ["120"]


# ── 合規兩層、皆不擋 ──
def test_compliance_rules_and_disclosure():
    flags = compliance.annotate("淨值大漲 97%、身價翻倍")
    ids = {f.rule_id for f in flags}
    assert "perf_claim" in ids
    disc = compliance.required_disclosures(flags)
    assert any("過去績效" in d for d in disc)


def test_compliance_unless_suppresses():
    # 已含「過去績效」→ perf_claim 不應再觸發
    assert not any(f.rule_id == "perf_claim"
                   for f in compliance.annotate("績效亮眼，過去績效不代表未來"))


def test_compliance_absolute_word_high_severity():
    flags = compliance.annotate("本檔穩賺不賠")
    hi = [f for f in flags if f.rule_id == "absolute_words"]
    assert hi and hi[0].severity == "高" and hi[0].emoji == "🔴"


def test_compliance_negation_not_flagged():
    # 「非保證」「不保證」是免責語，不應被當成絕對化「保證」誤標（反向誤判）
    assert not any(f.rule_id == "absolute_words"
                   for f in compliance.annotate("近一期配息（官方公告，非保證，可能含本金）"))
    # 但真正的「保證獲利」仍要抓
    assert any(f.rule_id == "absolute_words" for f in compliance.annotate("保證獲利"))


def test_compliance_never_raises_on_junk():
    assert compliance.annotate("") == []           # 不丟例外、不阻擋


# ── baseline（純證據、無 LLM）──
def test_baseline_channels_and_helpers():
    doc = parse_text(_REPORT)
    chans = baseline.render(doc.ideas[1], doc)
    assert set(chans) == set(baseline.CHANNELS)
    assert baseline.short_name("復華台灣未來50主動式ETF") == "復華台灣未來50"
    assert chans["punchy"] == "汰弱留強"            # 取『：』前標語
    assert "00991A" in chans["sales"]


def test_generate_baseline_zero_fabrication():
    doc = parse_text(_REPORT)
    res = cp.generate(doc.ideas[2], doc)            # 績效則
    for c in res.channels.values():
        assert c.fabricated == [], (c.channel, c.fabricated)   # 識別碼 50/00991 不誤判
        assert c.source == "baseline"
    # 績效訴求 → 自動補免責
    assert any("過去績效" in c.text for c in res.channels.values())


# ── LLM 覆寫層仍受把關（回灌不信任輸入）──
def test_llm_overlay_is_policed():
    doc = parse_text(_REPORT)
    perf = doc.ideas[2]                             # 第 3 則（績效）；idx 為循序編號
    resp = {str(perf.idx): {"punchy": "翻倍故事", "line": "三年漲 120%，穩賺！",
                            "ig": "AI 力量", "sales": "成立來 +97% 值得參與"}}
    llm = prompt_pack.as_llm(resp)
    res = cp.generate(perf, doc, llm=llm)
    line = res.channels["line"]
    assert line.source == "llm"
    assert "120" in line.fabricated                # 杜撰數字被抓
    assert any(f.rule_id == "absolute_words" for f in line.flags)   # 禁用字被抓
    assert not line.ok


# ── prompt-pack ──
def test_prompt_pack_build_and_ingest():
    doc = parse_text(_REPORT)
    bundle = [(i, baseline.render(i, doc),
               numbers.allowed_set(i.headline, i.evidence, doc.header)) for i in doc.ideas]
    p = prompt_pack.build_prompt(doc, bundle)
    assert "可用數字" in p and "00991A" in p and "汰弱留強" in p and '"ideas"' in p
    # load_response 容錯兩種形狀
    assert prompt_pack.load_response.__name__ == "load_response"


def test_render_markdown_smoke():
    doc = parse_text(_REPORT)
    md = cp.render_markdown(doc, cp.generate_doc(doc))
    assert "每日文案" in md and "00991A" in md and "疑似杜撰數字 0 處" in md
