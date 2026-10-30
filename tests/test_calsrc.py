"""行事曆官方來源（arm/calsrc.py；docs/macrocal_fill_plan.md 第三段）：解析與對帳，不連網。

格式照 2026-10-30 CI 探針實際拿到的回應（scripts/probe_calsrc.py）：勞工統計局 API v1、歐洲央行新聞稿與存款利率序列、
主計總處國民所得 XML。歐洲央行要新聞稿和序列對得上才算（維持卻和會前不同、方向不符、不是 1 碼倍數 → 不收）。"""
from datetime import date

from arm import calsrc as C
from arm.lab import heatfetch_us as U


def test_parse_bls_months_and_quarters():
    doc = {"status": "REQUEST_SUCCEEDED", "Results": {"series": [
        {"seriesID": "CES0000000001", "data": [{"year": "2026", "period": "M09", "value": "159044"},
                                               {"year": "2026", "period": "M13", "value": "1"}]},
        {"seriesID": "CIS1010000000000Q", "data": [{"year": "2026", "period": "Q02", "value": "0.9"}]},
        {"seriesID": "LNS14000000", "data": [{"year": "2026", "period": "M09", "value": "4.2"}]}]}}
    assert C.parse_bls(doc) == {"2026-09": {"CES0000000001": 159044.0}, "2026-Q2": {"CIS1010000000000Q": 0.9}}


HOLD = ("Monetary policy decisions 29 October 2026 Key ECB interest rates The interest rates on the deposit facility, "
        "the main refinancing operations and the marginal lending facility will remain unchanged at 2.50%, 2.65% and "
        "2.90% respectively.")
CUT_2024 = ("Accordingly, the interest rates on the main refinancing operations, the marginal lending facility and the "
            "deposit facility will be decreased to 4.25%, 4.50% and 3.75% respectively, with effect from 12 June 2024.")


def test_parse_ecb_text_follows_the_sentence_order():
    assert C.parse_ecb_text(HOLD) == (2.5, "hold")
    assert C.parse_ecb_text(CUT_2024) == (3.75, "down")                      # 2024 年以前存款利率寫在最後
    assert C.parse_ecb_text("Key ECB interest rates Euro short-term rate") is None


def test_ecb_decision_needs_text_and_series_to_agree():
    dfr = {"2026-09-15": 2.25, "2026-09-16": 2.5, "2026-10-29": 2.5}
    assert C.ecb_decision(HOLD, "2026-10-29", dfr) == [2.5, 0.0]
    assert C.ecb_decision(HOLD, "2026-09-10", {"2026-09-10": 2.25}) is None  # 說維持、會前卻是 2.25 → 不收
    up = HOLD.replace("will remain unchanged at", "will be increased to")
    assert C.ecb_decision(up, "2026-09-10", {"2026-09-10": 2.25}) == [2.5, 0.25]
    assert C.ecb_decision(up, "2026-09-10", {"2026-09-10": 2.75}) is None    # 說升息、數字卻變低
    assert C.ecb_decision(up, "2026-09-10", {"2026-09-10": 2.4}) is None     # 不是 1 碼倍數
    assert C.ecb_decision(HOLD, "2026-10-29", {}) is None


def test_parse_dfr_csv():
    csv = "KEY,FREQ,TIME_PERIOD,OBS_VALUE\nFM.D,D,2026-10-29,2.5\nFM.D,D,2026-10-30,2.5\n"
    assert C.parse_dfr(csv) == {"2026-10-29": 2.5, "2026-10-30": 2.5}


def test_dgbas_real_gdp_yoy_from_the_same_xml():
    def obs(item, tp, t, v):
        return f"<Obs><Item>{item}</Item><TYPE>{tp}</TYPE><TIME_PERIOD>{t}</TIME_PERIOD><Item_VALUE>{v}</Item_VALUE></Obs>"
    xml = (obs("國內生產毛額_連鎖實質值(2021為參考年_新臺幣百萬元)、GDP", "年增率(%)", "2026Q2", "12.93")
           + obs("國內生產毛額_連鎖實質值(2021為參考年_新臺幣百萬元)、GDP", "原始值", "2026Q2", "7066942")
           + obs("國內生產毛額_連鎖實質值(2021為參考年_新臺幣百萬元)、合計", "年增率(%)", "2026Q2", "12.6")
           + obs("國內生產毛額_當期價格(新臺幣百萬元)、GDP", "年增率(%)", "2026Q2", "17.46")
           + obs("國內生產毛額_連鎖實質值(2026為參考年_新臺幣百萬元)、GDP", "年增率(%)", "2026Q3", ""))
    assert U.parse_dgbas_real_yoy(xml) == {"2026-06": 12.93}


def test_fetch_logs_errors_and_respects_the_budget(monkeypatch):
    monkeypatch.setitem(C.FETCH, "bls_cal", lambda d: 3)
    monkeypatch.setitem(C.FETCH, "ecb", lambda d: 1 / 0)
    out = C.fetch({"bls_cal", "ecb"}, date(2026, 10, 30))
    assert out[0] == "bls_cal ✓ 3 筆更新" and out[1].startswith("ecb ✗ ZeroDivisionError")
    t = iter([0, 0, C.BUDGET_S + 1])
    monkeypatch.setattr(C.time, "time", lambda: next(t))
    monkeypatch.setitem(C.FETCH, "ecb", lambda d: 0)
    out = C.fetch({"bls_cal", "ecb"}, date(2026, 10, 30))
    assert out[1] == "ecb 略過（時間到，下一班再抓）"
