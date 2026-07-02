"""復華基金追蹤版本新模組單測：fhfund 解析（純函式）、usnews 合規/日期、fund_intro 組裝。"""
from datetime import date

import pytest

from arm import fund_intro, usnews
from arm.connectors import fhfund


# ── fhfund 純解析 ─────────────────────────────────────────────
def test_pct_and_num():
    assert fhfund._pct("4.58%") == 4.58
    assert fhfund._pct("60.76 %") == 60.76
    assert fhfund._pct("—") is None
    assert fhfund._num("5,296,363,360.00") == 5296363360.0


def test_holdings_table_parse():
    html = """
    <h3>十大持有標的</h3>
    <table class="fundTable"><thead><tr><th>類型</th><th>名稱</th><th>投資比例</th></tr></thead>
    <tbody>
      <tr><td>資訊技術</td><td>SANDISK CORP</td><td><span>4.58%</span></td></tr>
      <tr><td>資訊技術</td><td>聯發科</td><td><span>3.78%</span></td></tr>
    </tbody></table>"""
    rows = fhfund._rows_of_table_after(html, "十大持有標的")
    assert rows[0][1] == "SANDISK CORP"
    assert rows[1][2].startswith("3.78")


def test_svg_alloc_pairs():
    # 值先、標籤後（平行對位），比照官網 server-rendered SVG
    html = ('國家配置'
            '<text>60.76 %​60.76 %</text><text>16.71 %​16.71 %</text>'
            '<text>美國</text><text>臺灣</text>'
            '產業配置 十大持有標的')
    pairs = fhfund._svg_pairs(html, "國家配置", "產業配置")
    assert pairs == [{"name": "美國", "weight": 60.76}, {"name": "臺灣", "weight": 16.71}]


# ── usnews 合規 / 日期 ────────────────────────────────────────
def test_compliance_flags_banned():
    assert "目標價" in usnews.compliance_scan("這檔的目標價很高")
    assert usnews.compliance_scan("績效說明") == []


def test_compliance_allows_disclosure_negation():
    # 強制揭露段含「不保證」不應被判為違規
    assert usnews.compliance_scan(usnews.DISCLOSURE) == []


def test_us_session_skips_weekend():
    # 2026-07-06 是週一 → 昨夜美股對應到上週五 2026-07-03
    assert usnews.us_session_date(date(2026, 7, 6)) == date(2026, 7, 3)
    # 週四 → 前一日週三
    assert usnews.us_session_date(date(2026, 7, 2)) == date(2026, 7, 1)


def test_specs_present():
    assert "Top 3" in usnews.SPEC_V1 and "精簡版" in usnews.SPEC_V2
    assert usnews.BANNED and "保證" in usnews.BANNED


# ── fund_intro 組裝 ──────────────────────────────────────────
def _fake_doc():
    return {
        "fund_id": "99", "group": "global_equity", "category": "跨國投資股票型",
        "nav": 47.58, "nav_date": "2026/07/01",
        "country_alloc": [{"name": "美國", "weight": 60.76}, {"name": "臺灣", "weight": 16.71}],
        "sector_alloc": [{"name": "資訊技術", "weight": 85.97}],
        "top_holdings": [{"name": "A", "weight": 4.58}, {"name": "B", "weight": 3.78}],
    }


def test_summary_line_and_concentration():
    d = _fake_doc()
    s = fund_intro.summary_line(d)
    assert "美國 60.8%" in s and "資訊技術 86.0%" in s and "47.58" in s
    assert fund_intro.top_concentration(d) == 8.4


def test_group_label_mapping():
    assert fund_intro.GROUP_LABEL["global_balanced"] == "全球平衡型"


def test_all_funds_reads_config(tmp_path, monkeypatch):
    # 至少不報錯，且回傳 list（實際內容依 data/funds 是否已抓）
    assert isinstance(fund_intro.all_funds(), list)
