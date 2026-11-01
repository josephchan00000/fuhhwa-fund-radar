"""官方實際公布日的解析（scripts/fetch_reldates.py；docs/lab_signal_quality_plan.md 第 11.2 節）。只測解析，不連網。"""
import importlib.util
from pathlib import Path

_p = Path(__file__).resolve().parents[1] / "scripts" / "fetch_reldates.py"
_s = importlib.util.spec_from_file_location("fetch_reldates", _p)
R = importlib.util.module_from_spec(_s)
_s.loader.exec_module(R)


def test_parse_bls_archive_items():
    page = """<ul>
<li>Consumer Price Index for January 2015 <a href="/news.release/archives/cpi_02262015.htm">HTML</a>
 <a href="/news.release/archives/cpi_02262015.pdf">PDF</a></li>
<li><a href="/news.release/archives/cpi_01162015.htm">December 2014</a></li>
<li>Consumer Price Index for January 2015 (corrected) <a href="/news.release/archives/cpi_03022015.htm">HTML</a></li>
<li>Some other link <a href="/news.release/archives/realer_02262015.htm">Real Earnings</a></li>
</ul>"""
    assert R.parse_bls(page, "cpi") == {"2015-01": "2015-02-26", "2014-12": "2015-01-16"}
    emp = '<li>The Employment Situation - December 2019 <a href="archives/empsit_01102020.htm">HTML</a></li>'
    assert R.parse_bls(emp, "empsit") == {"2019-12": "2020-01-10"}


def test_parse_z1_and_quarter():
    page = '<a href="/releases/z1/20190920/default.htm">Sep 20</a> <a href="/releases/z1/20191212/">x</a> /releases/z1/20190920/'
    assert R.parse_z1(page) == ["2019-09-20", "2019-12-12"]
    assert [R.z1_quarter(d) for d in ("2019-09-20", "2019-12-12", "2020-03-12", "2020-06-11", "2026-01-09")] == \
        ["2019-06", "2019-09", "2019-12", "2020-03", "2025-09"]


def test_parse_cdx_lines():
    txt = ("https://www.bls.gov/news.release/archives/cpi_02262015.htm\n"
           "http://bls.gov:80/news.release/archives/cpi_02262015.pdf\n"
           "https://www.bls.gov/news.release/archives/cpi_01162015.htm\n"
           "https://www.bls.gov/news.release/archives/cpi_toc.htm\n")
    assert R.parse_cdx(txt, "cpi") == ["2015-01-16", "2015-02-26"]


def test_parse_cdx_keeps_only_real_weekday_captures():
    """2026-10-31 第一輪沒過濾：混進沒有公布過的網址（檔案館存到的是 404）、週末日期、公布前就「存到」的。"""
    txt = ("https://www.bls.gov/news.release/archives/empsit_01102020.htm 20200110153000 200\n"
           "https://www.bls.gov/news.release/archives/empsit_01032020.htm 20200103140000 404\n"   # 沒有這一則
           "https://www.bls.gov/news.release/archives/empsit_03052023.htm 20230306000000 200\n"   # 週日
           "https://www.bls.gov/news.release/archives/empsit_02062026.htm 20260201000000 200\n"   # 存檔日早於檔名日
           "https://www.bls.gov/news.release/archives/empsit_02112026.htm 20260211133000 200\n")
    assert R.parse_cdx(txt, "empsit") == ["2020-01-10", "2026-02-11"]



# ── 使用端（arm/lab/reldates.py；heatspec VER 12 補充 ④⑤） ──────────────────────

from arm.lab import reldates as RD  # noqa: E402


def test_official_priority_and_latest_in_month():
    doc = {"cdx_cpi": ["2015-02-26", "2015-03-24", "2015-03-02", "2001-02-21"],
           "hist_cpi": {"2001-01": "2001-02-21", "2000-12": "2001-01-17"},
           "cpi": {"2014-12": "2015-01-16"},
           "z1": ["2003-09-18", "2004-01-15"]}
    t = RD.official("cpi", doc)
    assert t["2015-01"] == "2015-02-26" and t["2000-12"] == "2001-01-17" and t["2014-12"] == "2015-01-16"
    assert t["2015-02"] == "2015-03-24"                         # 索引同一個公布月兩則（03-02、03-24）→ 取晚的
    doc["cpi"]["2015-02"] = "2015-03-02"
    assert RD.official("cpi", doc)["2015-02"] == "2015-03-02"   # 檔案頁寫明資料月份的優先
    assert RD.official("z1", doc) == {"2003-06": "2003-09-18", "2003-09": "2004-01-15"}
    assert RD.official("cpi", {}) == {}


def test_fill_uses_latest_same_month_and_skips_shutdowns():
    t = {"2015-01": "2015-02-26", "2016-01": "2016-02-19", "2015-02": "2015-03-24", "2013-09": "2013-10-30",
         "2014-09": "2014-10-22", "2020-06": "2020-07-14"}
    assert RD.period_latest(t, skip=("2013-09",)) == {"01": (1, 26), "02": (1, 24), "09": (1, 22), "06": (1, 14)}
    f = RD.fill(["1999-01", "1999-09", "2015-01", "2017-02", "2021-01"], t, skip=("2013-09",))
    assert f == {"1999-01": "1999-02-26", "1999-09": "1999-10-22", "2015-01": "2015-02-26", "2017-02": "2017-03-24"}
    assert "2021-01" not in f                                   # 表最後一期之後不補（照 RELEASE）
    assert RD.fill(["1999-01"], {}) == {}
    assert RD.months_between("2024-11", "2025-02") == ["2024-11", "2024-12", "2025-01", "2025-02"]
    assert RD.months_between("1940-03", "1941-03", 3) == ["1940-03", "1940-06", "1940-09", "1940-12", "1941-03"]


def test_quarterly_fill_and_late_beats_rule():
    from arm.lab import heat as H
    t = {"2003-09": "2004-01-15", "2004-09": "2004-12-09", "2025-09": "2026-01-09", "2001-06": "2001-09-18"}
    f = RD.fill(RD.months_between("1990-03", "2025-09", 3), t, skip=("2025-09",))
    assert f["1990-09"] == "1991-01-15" and f["1990-06"] == "1990-09-18" and "1990-03" not in f
    # asof：官方（或保守）日子比公布時間差晚就照晚的
    dates = ["2003-12-16", "2004-01-14", "2004-01-15"]
    got = H.asof_monthly(dates, {"2003-06": 1.0, "2003-09": 2.0}, (3, 15), f)
    assert got == [1.0, 1.0, 2.0]
    assert H.asof_monthly(dates, {"2003-06": 1.0, "2003-09": 2.0}, (3, 15)) == [2.0, 2.0, 2.0]   # 只照 (3,15) 會早用


def test_deriv_uses_late_dates():
    """邊際變化（heatpos.deriv）和分數用同一份實際拿得到的日子（heatspec VER 12 補充 ⑥）。"""
    from arm.lab import heatpos as P
    from arm.lab import heatspec as S
    k = next(x for x in S.DERIV if S.FREQ_OF[x] == "m")
    months = RD.months_between("1990-01", "2004-12")
    mraw = {m: 100.0 + i + (i % 7) for i, m in enumerate(months)}
    mraw["2003-03"] = 1000.0                                    # 那一期跳很大：早用就看得出來
    cal = [f"{m}-{d:02d}" for m in months for d in (5, 20)]
    late_m = "2003-03"
    B0 = {"cal": cal, "mraw": {k: mraw}, "D": {}}
    B1 = {"cal": cal, "mraw": {k: mraw}, "D": {"late": {k: {late_m: "2003-12-31"}}}}
    d0, d1 = P.deriv(B0, k), P.deriv(B1, k)
    i = cal.index(f"{H_add(late_m, S.RELEASE[k][0])}-20")
    assert d0["d1"][i] != d1["d1"][i] or d0["d2"][i] != d1["d2"][i]
    assert P.late(B1, k) == {late_m: "2003-12-31"} and P.late(B0, k) is None


def H_add(ym, k):
    return RD.months_between(ym, "2100-12")[k]


def test_bubble_fund_and_fuel_late():
    from arm.lab import bubble as B
    F = {"2025-09": 1.0, "2025-12": 2.0}
    assert B.fund_asof(F, ["2026-03"], (3, 1))["2026-03"][0] == "2025-12"
    assert B.fund_asof(F, ["2026-03"], (3, 1), {"2025-12": "2026-04-09"})["2026-03"][0] == "2025-09"   # 2025 Q4 企業獲利 4/9 才公布
    assert B._latest({"2025-06": 1, "2025-09": 2}, "2026-01-05", (3, 15)) == ("2025-09", 2)
    assert B._latest({"2025-06": 1, "2025-09": 2}, "2026-01-05", (3, 15), {"2025-09": "2026-01-09"}) == ("2025-06", 1)
