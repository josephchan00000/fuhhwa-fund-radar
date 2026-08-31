"""高風險數字事實核對：抽取／比對／降級三路徑離線測試（不打網路）。"""
import pytest
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


def test_multi_number_sentence_not_false_red():
    """CI 首輪實測誤判案例：同句含增量與水位——任一候選相符即 🟢，不得抓增量誤殺。"""
    txt = ("期貨端，外資台指期淨空單 7/17 盤後單日再增 1,736 口、**升至 86,189 口**"
           "（7/16 為 84,453 口）。")
    claims = factcheck.extract_claims(txt, year=2026)
    assert len(claims) == 1 and claims[0].alts == [1736.0, 86189.0, 84453.0]
    res = factcheck.check_claims(claims, fetchers=_OFFICIAL)
    assert res[0].status == "🟢"


def test_tolerance_allows_rounding():
    txt = "台股 7/17 收 42,671.3 點、下跌 2,954 點；7/17 三大法人賣超 2,617 億元。"
    claims = factcheck.extract_claims(txt, year=2026)
    res = factcheck.check_claims(claims, fetchers=_OFFICIAL)
    assert all(r.status == "🟢" for r in res)


def test_us_index_claims_anchor_and_verdicts():
    """美股指數：句內無日期以對應交易日為錨；漲跌%與點位分開驗；矛盾值 🔴。"""
    txt = ("- **費城半導體指數（SOX）**：**大漲 3.7%**（點位以前收約 11,744 推算約 12,178）。\n"
           "- **標普 500 指數**：上漲 0.89% 收 7,509.20。\n")
    day = date(2026, 7, 21)
    claims = factcheck.extract_us_index_claims(txt, day)
    kinds = sorted(c.kind for c in claims)
    # 「前收約 11,744 推算」句：07-23 起前收防呆刻意不抽 close，只驗漲跌%
    assert kinds == ["us_sox_chg", "us_spx_chg", "us_spx_close"]
    official = {"us": lambda k: {"sox": {"2026-07-21": (12356.0, 5.21)},
                                 "spx": {"2026-07-21": (7509.20, 0.89)}}[k]}
    res = factcheck.check_claims(claims, fetchers={**_OFFICIAL, **official})
    by = {r.claim.kind: r.status for r in res}
    assert by["us_sox_chg"] == "🔴"                                  # 3.7% vs 官方 5.21%
    assert by["us_spx_chg"] == "🟢" and by["us_spx_close"] == "🟢"
    # 官方序列不可得 → ⚪ 不誤殺
    down = {"us": lambda k: None}
    res2 = factcheck.check_claims(claims, fetchers={**_OFFICIAL, **down})
    assert all(r.status == "⚪" for r in res2)


def test_us_index_hardening_no_false_positives():
    """CI 首輪誤判案例鎖定：連結句跳過／個股漲幅不錯掛／逾字寬容差。"""
    official = {"us": lambda k: {"sox": {"2026-07-21": (12356.16, 5.21)},
                                 "dji": {"2026-07-21": (52224.64, 0.74)}}.get(k)}
    day = date(2026, 7, 21)
    # 連結句（URL 數字＋Nasdaq 100 標題）→ 不抽
    assert factcheck.extract_us_index_claims(
        "6. **參考連結**：[Benzinga: Nasdaq 100 Tops 29,000](https://x.com/a/60589094/b)。", day) == []
    # 個股漲幅不掛到道瓊（視窗內無漲跌+%緊鄰）
    c = factcheck.extract_us_index_claims("股價盤中漲 5.24% 至 79.82 美元，助攻道瓊領漲 385 點。", day)
    assert not [x for x in c if x.kind == "us_dji_chg"]
    # 「大漲逾 5%」對官方 5.21 → 🟢
    c2 = factcheck.extract_us_index_claims("費半昨夜大漲逾 5%，記憶體領軍。", day)
    r = factcheck.check_claims(c2, fetchers={**_OFFICIAL, **official})
    assert [x.status for x in r] == ["🟢"]


def test_intraday_and_prevclose_not_extracted():
    """07-23 誤殺案例：盤中口徑（盤初/一度）與「前收」不可當收盤驗。"""
    day = date(2026, 7, 22)
    c = factcheck.extract_us_index_claims("費半盤初一度跌近 2%、盤中偏弱。", day)
    assert not [x for x in c if x.kind == "us_sox_chg"]
    c2 = factcheck.extract_us_index_claims("費半僅知盤中區間 12,086–12,404（前收 12,356.16）。", day)
    assert not [x for x in c2 if x.kind == "us_sox_close"]
    c3 = factcheck.extract_us_index_claims("費半終場收漲 0.44% 收 12,410.67。", day)
    assert sorted(x.kind for x in c3) == ["us_sox_chg", "us_sox_close"]


def test_drawdown_and_stock_and_us_context_not_false_red():
    """07-24 誤殺三型：累計跌幅/個股盤中/美股句被台股撈——全不抽。"""
    day = date(2026, 7, 23)
    # 自 6/22 高點跌逾 20%（累計回落）→ 不抽 SOX chg
    assert not [c for c in factcheck.extract_us_index_claims(
        "費城半導體指數自 6/22 高點跌逾 20% 進入技術性熊市。", day) if c.kind == "us_sox_chg"]
    # 英特爾日盤跌約 6%（個股＋盤中）→ 不抽
    assert not [c for c in factcheck.extract_us_index_claims(
        "英特爾日盤先隨費半殺盤跌約 6%、盤後大漲。", day) if c.kind == "us_sox_chg"]
    # 台股報告句「道瓊下跌 506.93 點」→ 台股 index_chg 不抽（美股句）
    tw = "1. 昨夜 7/23 美股：道瓊下跌 506.93 點、那指 −2.15%。"
    assert not [c for c in factcheck.extract_claims(tw, year=2026) if c.kind == "index_chg"]
    # 真台股句仍抽
    tw2 = "加權指數 7/23 下跌 221.57 點收 42,449。"
    assert [c for c in factcheck.extract_claims(tw2, year=2026) if c.kind == "index_chg"]


def test_historical_high_close_not_taken_as_session_close():
    """07-31 誤殺：「歷史收盤高點 14,634.72」是他日高點、非本日收盤。

    同型於 07-24 的 drawdown 防呆（那次只修了 chg，close 漏掉）——但這裡刻意
    不用整句判定：「自高點回落…，收 X」的真收盤仍必須驗得到。
    """
    day = date(2026, 7, 31)
    sent = ("此波修正起於中國業者傳出量產 DUV 微影設備的報導，費半指數曾於 7 月 29 日"
            "自 6 月 22 日歷史收盤高點 14,634.72 回落逾 20%、正式落入熊市。")
    assert not [c for c in factcheck.extract_us_index_claims(sent, day)
                if c.kind == "us_sox_close"]
    # 同句同時有「自高點回落」與真收盤時，真收盤仍要抽得到（不可整句封殺）
    both = factcheck.extract_us_index_claims(
        "費半自 6 月 22 日高點回落逾 20%，7/31 收 11,311.08。", day)
    assert [c.value for c in both if c.kind == "us_sox_close"] == [11311.08]
    # 「創歷史新高」句的真收盤照樣抽
    hi = factcheck.extract_us_index_claims("道瓊工業指數收 52,485.03，改寫歷史新高。", day)
    assert [c.value for c in hi if c.kind == "us_dji_close"] == [52485.03]


def test_futures_and_night_session_not_extracted():
    """07-27 誤殺：期貨／夜盤非現貨口徑，拿日線驗必紅——整段不抽。"""
    day = date(2026, 7, 24)
    # 那指 100 期貨 +1.2%（夜盤期貨）→ 不抽那指現貨 chg
    sent = "週日夜盤美股期貨反彈：道瓊期貨漲 294 點、那指 100 期貨漲 1.2%。"
    assert not [c for c in factcheck.extract_us_index_claims(sent, day)
                if c.kind == "us_ndq_chg"]
    # 期貨收盤點位亦不抽
    assert not [c for c in factcheck.extract_us_index_claims(
        "那指 100 期貨收 25,180。", day) if c.kind == "us_ndq_close"]
    # 台指期夜盤收 X、跌 X 點 → 台股現貨 index_close/index_chg 皆不抽
    tw = "台股期指夜盤 7/24 再跌 445 點收 43,369.00。"
    assert not [c for c in factcheck.extract_claims(tw, year=2026)
                if c.kind in ("index_close", "index_chg")]
    # 現貨句不受影響（回歸保護）
    assert [c for c in factcheck.extract_claims(
        "加權指數 7/24 下跌 1195.97 點收 43,654.84。", year=2026)
        if c.kind == "index_chg"]
    assert [c for c in factcheck.extract_us_index_claims(
        "那斯達克終場收跌 0.64% 收 24,975.82。", day) if c.kind == "us_ndq_chg"]


def test_index_series_skips_chg_when_a_session_bar_is_missing(monkeypatch):
    """Yahoo 日線漏棒時，日變動% 不可拿非相鄰前一筆硬算成「多日累計」。

    2026-07-28 實際誤判：^IXIC／^SOX 序列都缺 07/24 那根，07/27 被拿去跟 07/23 比，
    正確的單日 −2.23%（費半）與 −0.18%（那指）被判成 🔴，官方值實為兩日累計。
    漏棒時應回 None → 上層以 ⚪「無前日收盤可算漲跌%」誠實跳過（設計原則 1 絕不誤殺）。
    """
    from datetime import datetime, timezone

    def _ts(y, m, d):                       # Yahoo 日線時戳＝美東開盤 13:30 UTC
        return int(datetime(y, m, d, 13, 30, tzinfo=timezone.utc).timestamp())

    def _series(stamps, closes):
        monkeypatch.setattr(factcheck, "_get_json", lambda url: {
            "chart": {"result": [{"timestamp": stamps,
                                  "indicators": {"quote": [{"close": closes}]}}]}})
        return factcheck.yahoo_index_series("sox")

    day = date(2026, 7, 27)
    txt = "- **費城半導體指數（SOX）**：收盤 **下跌 2.23%**。"
    claims = factcheck.extract_us_index_claims(txt, day)

    # 缺 07/24（週五）→ 07/27 無相鄰前一交易日，chg 為 None、判定 ⚪
    gapped = _series([_ts(2026, 7, 23), _ts(2026, 7, 27)], [12631.0, 11824.5])
    assert gapped["2026-07-27"][1] is None
    res = factcheck.check_claims(claims, fetchers={**_OFFICIAL, "us": lambda k: gapped})
    assert [r.status for r in res] == ["⚪"]

    # 序列完整 → 仍照常算單日變動，正確值 🟢、錯誤值 🔴（防呆不得關掉偵測能力）
    full = _series([_ts(2026, 7, 23), _ts(2026, 7, 24), _ts(2026, 7, 27)],
                   [12631.0, 12094.2, 11824.5])
    assert full["2026-07-24"][1] == pytest.approx(-4.25, abs=0.01)
    assert full["2026-07-27"][1] == pytest.approx(-2.23, abs=0.01)
    ok = factcheck.check_claims(claims, fetchers={**_OFFICIAL, "us": lambda k: full})
    assert [r.status for r in ok] == ["🟢"]
    wrong = factcheck.extract_us_index_claims(
        "- **費城半導體指數（SOX）**：收盤 **下跌 6.39%**。", day)
    bad = factcheck.check_claims(wrong, fetchers={**_OFFICIAL, "us": lambda k: full})
    assert [r.status for r in bad] == ["🔴"]


def test_adjacent_session_rules():
    """相鄰交易日判定：連續平日與週五→週一為真；漏棒／跨假日一律為假（寧缺勿錯）。"""
    adj = factcheck._adjacent_session
    assert adj(date(2026, 7, 23), date(2026, 7, 24))        # 週四 → 週五
    assert adj(date(2026, 7, 24), date(2026, 7, 27))        # 週五 → 週一
    assert not adj(date(2026, 7, 23), date(2026, 7, 27))    # 漏了週五
    assert not adj(date(2026, 7, 24), date(2026, 7, 28))    # 跨假日，與漏棒不可區分
    assert not adj(date(2026, 7, 20), date(2026, 7, 27))    # 相隔一週


def test_markdown_links_do_not_produce_claims():
    """2026-08-05 踩坑：「參考連結」列的媒體標題（「三大法人買超1.09億元」）被抽成本報告
    的聲明，日期還從 URL 片段（…/2026-08-04/1051304 → 「04/10」）誤配——拿 4/10 官方值
    對媒體標題 → 假 🔴。連結（標題＋URL）一律先剝掉再抽。"""
    text = ("5. **參考連結**：[外資續砍57億、投信狂掃252億 三大法人買超1.09億元｜鉅亨網]"
            "(https://news.cnyes.com/news/id/6558608)、[台股震盪千點終場小跌25點｜Newtalk新聞]"
            "(https://newtalk.tw/news/view/2026-08-04/1051304)")
    assert factcheck.extract_claims(text, year=2026) == []
    # 正文聲明不受影響
    real = "8/4 三大法人合計買超 20.0 億元"
    got = factcheck.extract_claims(real, year=2026)
    assert len(got) == 1 and got[0].kind == "inst_total" and got[0].value == 20.0


def test_inst_flows_foreign_row_identified_by_luzi():
    """「外資及陸資(不含外資自營商)」列名本身含「自營」——舊判斷 `自營 not in name` 把整列
    誤殺，inst_foreign 永遠 ⚪ 沒在核。改以獨有「陸資」辨識（同 macrochips 修法）；
    「外資自營商」列不含「陸資」→ 不誤收進 foreign。"""
    doc = {"stat": "OK", "data": [
        ["自營商(自行買賣)", "1", "2", "-5000000000"],
        ["自營商(避險)", "1", "2", "-14430000000"],
        ["投信", "1", "2", "25270000000"],
        ["外資及陸資(不含外資自營商)", "1", "2", "-5730000000"],
        ["外資自營商", "1", "2", "1894900000"],
        ["合計", "1", "2", "2004890525"],
    ]}
    import unittest.mock as mock
    with mock.patch.object(factcheck, "_get_json", return_value=doc):
        from datetime import date as _date
        out = factcheck.twse_inst_flows(_date(2026, 8, 4))
    assert round(out["foreign"], 1) == -57.3               # 不含外資自營商（官方列原值）
    assert round(out["total"], 2) == 20.05                 # 合計列直取（含外資自營商）


def test_inst_total_tolerance_accepts_rounded_claim():
    """報告寫 20.0（落檔 round 1 位）對官方 20.0489 → 容忍帶過（abs ≤ max(2%, 3億)）。"""
    assert factcheck._tol_ok("inst_total", 20.0, 20.0489)
    assert not factcheck._tol_ok("inst_total", 1.1, 20.0489)   # 早期快照值就該紅


def test_foreign_dealer_row_not_extracted_as_inst_foreign():
    """「外資自營商買超 X 億」是 BFI82U 另一列——不得抽成 inst_foreign（比對基準是
    「外資及陸資(不含外資自營商)」，抽了必然假 🔴）。一般外資句照常抽。"""
    t1 = "8/4 證交所後補外資自營商分項（買超 18.9 億元）"
    assert not [c for c in factcheck.extract_claims(t1, year=2026) if c.kind == "inst_foreign"]
    t2 = "8/4 外資及陸資（不含外資自營商）賣超 57.3 億元"
    got = [c for c in factcheck.extract_claims(t2, year=2026) if c.kind == "inst_foreign"]
    assert len(got) == 1 and got[0].value == 57.3


def test_index_chg_skips_intraday_context():
    """盤中口徑（開盤／盤中最低／一度重挫）的漲跌點不是收盤漲跌。

    2026-09-01 假 🔴：台股報「8/31 開盤 46,224.69 點、下跌 106.76 點」被抽成當日
    index_chg，官方收盤 -202.98 → 🔴，但報告沒寫錯（標題已寫「終場跌 202 點」）。
    美股 chg 早有 intraday 防呆，台股這條沒接上。
    """
    def chg(sent):
        return [c.value for c in factcheck.extract_claims(sent, year=2026)
                if c.kind == "index_chg"]

    # 開盤／盤中／一度 的點數一律不抽
    assert chg("台股 8/31 開盤 46,224.69 點、下跌 106.76 點，盤中最低下探 45,450.21 點、"
               "一度重挫 881 點") == []
    # 同句盤中在前、終場在後 → 仍要抽得到終場那個（逐個匹配、非只看第一個）
    assert chg("台股 8/31 盤中一度重挫 881 點，終場下跌 202.98 點") == [202.98]
    assert chg("台股 8/31 開低 106 點，收盤下跌 202.98 點") == [202.98]
    # 回歸保護：純收盤句、盤中詞在數字之後，照抽
    assert chg("台股 8/31 終場下跌 202.98 點，收 46,021.00 點") == [202.98]
    assert chg("台股 8/31 終場下跌 202.98 點，盤中最低下探 45,450.21 點") == [202.98]
