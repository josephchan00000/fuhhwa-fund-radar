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


def test_parse_dates_dedup_sorted():
    assert R.parse_dates("2015-02-26\n2015-01-16\n2015-02-26 x 1999-13-99") == ["1999-13-99", "2015-01-16", "2015-02-26"]
