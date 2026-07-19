"""高風險數字事實核對：抽取／比對／降級三路徑離線測試（不打網路）。"""
from datetime import date

from arm import factcheck

_TXT = """### 卡 1｜台股 717 定稿（來源：中央社｜2026/07/17｜【新事件】｜重要度 9/10）
1. **新聞摘要**：台股 7/17 收 42,671.27 點、下跌 2,953.71 點（−6.47%）。
2. **籌碼**：7/17 三大法人賣超 2,617.15 億元，其中外資賣超 1,890.39 億元。
3. **期貨**：外資台指期淨空單 7/17 升至 86,189 口。
4. **無日期句不檢查**：外資淨空單仍有 99,999 口高掛。
"""

_OFFICIAL = {
    "index": lambda d: (42671.27, -2953.71) if d == date(2026, 7, 17) else None,
    "flows": lambda d: {"total": -2617.15, "foreign": -1890.39} if d == date(2026, 7, 17) else None,
    "tx": lambda d: -86189.0 if d == date(2026, 7, 17) else None,
}


def test_extract_claims_date_anchored():
    claims = factcheck.extract_claims(_TXT, year=2026)
    kinds = sorted(c.kind for c in claims)
    assert kinds == ["index_chg", "index_close", "inst_foreign", "inst_total", "tx_net"]
    assert all(c.day == date(2026, 7, 17) for c in claims)
    assert not any(c.value == 99999 for c in claims)          # 句內無日期 → 不抽


def test_check_all_green_when_matching():
    claims = factcheck.extract_claims(_TXT, year=2026)
    res = factcheck.check_claims(claims, fetchers=_OFFICIAL)
    assert [r.status for r in res] == ["🟢"] * 5


def test_check_red_on_mismatch_and_skip_when_unavailable():
    bad = _TXT.replace("86,189 口", "83,605 口")               # 實際踩過的錯值
    claims = factcheck.extract_claims(bad, year=2026)
    res = factcheck.check_claims(claims, fetchers=_OFFICIAL)
    assert "🔴" in [r.status for r in res if r.claim.kind == "tx_net"]
    # 官方全掛（proxy 擋）→ 全 ⚪、絕不誤判 🔴
    down = {"index": lambda d: None, "flows": lambda d: None, "tx": lambda d: None}
    res2 = factcheck.check_claims(claims, fetchers=down)
    assert all(r.status == "⚪" for r in res2)


def test_tolerance_allows_rounding():
    txt = "台股 7/17 收 42,671.3 點、下跌 2,954 點；7/17 三大法人賣超 2,617 億元。"
    claims = factcheck.extract_claims(txt, year=2026)
    res = factcheck.check_claims(claims, fetchers=_OFFICIAL)
    assert all(r.status == "🟢" for r in res)
