"""美股個股報告的官方文件包（arm/lab/eqdocs_us.py、scripts/fetch_eqdocs.py 的 us: 那一段；docs/lab_eq_docs_plan.md 第 6 節）。
SEC 的格式用手寫的最小 HTML／JSON 測：目錄與正文都有「Item N」、隱藏的 XBRL 表頭、8-K 索引頁的附件表。"""
import importlib.util
import json
import re
from argparse import Namespace
from datetime import date
from pathlib import Path

from arm.lab import eqdocs_us as U

ROOT = Path(__file__).resolve().parents[1]
CIK = 1234567
ARC = f"https://www.sec.gov/Archives/edgar/data/{CIK}"

K10 = ("<html><head><title>10-K</title><script>var x='Item 1A. fake'</script></head><body>"
       "<div style='display:none'><ix:header>hidden xbrl header</ix:header></div>"
       "<p>Table of Contents</p><table><tr><td>Item 1.</td><td>Business</td><td>3</td></tr>"
       "<tr><td>Item 1A.</td><td>Risk Factors</td><td>9</td></tr><tr><td>Item 7.</td><td>MD&amp;A</td><td>30</td></tr></table>"
       "<p>Item 1. Business</p><p>We make payroll software for mid-sized companies.</p>" + "<p>More business text.</p>" * 30 +
       "<p>Item 1A. Risk Factors</p><p>Competition may reduce our prices.</p>" + "<p>More risk text.</p>" * 20 +
       "<p>Item 1B. Unresolved Staff Comments</p><p>None.</p>"
       "<p>Item 7. Management&#8217;s Discussion and Analysis</p><p>Revenue grew 10% to $2.0 billion.</p>" + "<p>More MD&amp;A.</p>" * 25 +
       "<p>Item 7A. Quantitative and Qualitative Disclosures</p><p>Rates.</p><p>Item 8. Financial Statements</p><p>Tables.</p></body></html>")
Q10 = ("<html><body><p>PART I</p><p>Item 1. Financial Statements</p><p>Balance sheet.</p>"
       "<p>Item 2. Management's Discussion and Analysis</p><p>Recurring revenue rose 9% in the quarter.</p>" + "<p>More quarter text.</p>" * 20 +
       "<p>Item 3. Quantitative</p><p>x</p><p>Item 4. Controls</p><p>y</p><p>PART II</p><p>Item 1. Legal Proceedings</p><p>z</p>"
       "<p>Item 2. Unregistered Sales</p><p>None.</p></body></html>")
EX_IDX = ("<table class='tableFile'><tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th></tr>"
          f"<tr><td>1</td><td>8-K</td><td><a href='/ix?doc=/Archives/edgar/data/{CIK}/000123456726000028/x8k.htm'>x8k.htm</a></td><td>8-K</td><td>9 KB</td></tr>"
          f"<tr><td>2</td><td>Press release</td><td><a href='/Archives/edgar/data/{CIK}/000123456726000028/ex991.htm'>ex991.htm</a></td><td>EX-99.1</td><td>50 KB</td></tr>"
          f"<tr><td>3</td><td>Logo</td><td><a href='/Archives/edgar/data/{CIK}/000123456726000028/g1.jpg'>g1.jpg</a></td><td>GRAPHIC</td><td>5 KB</td></tr></table>")


def _sub(forms=("8-K", "10-Q", "8-K", "10-K", "8-K"), days=("2026-10-30", "2026-08-06", "2026-08-05", "2026-02-19", "2025-01-02")):
    accs = [f"0001234567-26-0000{30 - i:02d}" for i in range(len(forms))]
    docs = {"8-K": "x8k.htm", "10-Q": "q.htm", "10-K": "k.htm"}
    items = {0: "5.02", 2: "2.02,9.01", 4: "8.01"}
    return {"name": "Test Inc", "sicDescription": "Services-Prepackaged Software", "fiscalYearEnd": "1231", "exchanges": ["NYSE"],
            "tickers": ["TST"], "website": "", "investorWebsite": "https://investors.test.com", "stateOfIncorporation": "DE",
            "filings": {"recent": {"form": list(forms), "filingDate": list(days), "reportDate": ["", "2026-06-30", "", "2025-12-31", ""],
                                   "accessionNumber": accs, "primaryDocument": [docs[f] for f in forms],
                                   "items": [items.get(i, "") for i in range(len(forms))]}}}


def _get(sub, fail=()):
    pages = {U.SUB.format(cik=CIK): json.dumps(sub).encode()}
    for f in U.filings(sub):
        url = U.doc_url(CIK, f["acc"], f["doc"])
        pages[url] = {"10-K": K10, "10-Q": Q10}.get(f["form"], "<p>Item 2.02 Results of Operations.</p>").encode()
        pages[U.index_url(CIK, f["acc"])] = (EX_IDX if f["items"].startswith("2.02") else "<table></table>").encode()
    pages[f"https://www.sec.gov/Archives/edgar/data/{CIK}/000123456726000028/ex991.htm"] = b"<p>Revenue was $500 million, up 9%.</p>"
    calls = []

    def get(url):
        calls.append(url)
        if any(x in url for x in fail) or url not in pages:
            return 404, b""
        return 200, pages[url]
    return get, calls


def test_to_text_drops_hidden_xbrl_and_scripts_and_splits_cells():
    t = U.to_text(K10)
    assert "hidden xbrl header" not in t and "fake" not in t
    assert "Item 1. ｜ Business ｜ 3" in t and "Management’s Discussion" in t and "MD&A" in t


def test_sections_take_the_body_not_the_table_of_contents():
    s = U.sections(U.to_text(K10), U.K10_ITEMS)
    assert s["1"].startswith("Item 1. Business") and "payroll software" in s["1"] and "Competition" not in s["1"]
    assert "Competition may reduce" in s["1A"] and "Unresolved" not in s["1A"]
    assert "Revenue grew 10%" in s["7"] and "Rates." not in s["7"]                        # 7A 不算 7
    q = U.sections(U.to_text(Q10), U.Q10_ITEMS)
    assert "Recurring revenue rose 9%" in q["2"] and "Unregistered" not in q["2"]           # 第二部分的 Item 2 比較短
    assert U.cap("a\nb\nc", 3) == ("a", True) and U.cap("abc", 3) == ("abc", False)


def test_exhibits_and_filings():
    ex = U.exhibits(EX_IDX)
    assert [e["type"] for e in ex] == ["8-K", "EX-99.1", "GRAPHIC"]
    assert ex[0]["url"] == f"{ARC}/000123456726000028/x8k.htm" and ex[1]["desc"] == "Press release"     # /ix?doc= 拿掉、補成絕對網址
    fs = U.filings(_sub())
    assert fs[1] == {"form": "10-Q", "d": "2026-08-06", "per": "2026-06-30", "acc": "0001234567-26-000029", "doc": "q.htm", "items": ""}
    assert U.items_text("2.02,9.01") == "2.02 營運成果與財務狀況（財報）、9.01 財務報表與附件"
    assert U.filings({}) == []


def test_build_index_and_markdown():
    get, calls = _get(_sub())
    pk = U.build("TST", CIK, date(2026, 11, 4), get, log=lambda *_: None)
    assert pk["ok"] and pk["st"] == {"sub": "ok", "k10": "ok", "q10": "ok", "8k": "ok"}
    assert pk["basic"]["site"] == "https://investors.test.com" and pk["k10"]["d"] == "2026-02-19" and pk["q10"]["per"] == "2026-06-30"
    assert "payroll software" in pk["k10"]["sec"]["1"]["text"] and "Recurring revenue" in pk["q10"]["sec"]["2"]["text"]
    assert [x["d"] for x in pk["news"]] == ["2026-10-30", "2026-08-05"]                       # 近 6 個月；2025 年那份不抓
    rel = pk["news"][1]
    assert [e["type"] for e in rel["ex"]] == ["EX-99.1"] and "Revenue was $500 million" in rel["ex"][0]["text"]
    assert not any(c.endswith("g1.jpg") for c in calls)                                    # 圖檔不抓
    ix = U.index(pk)
    assert ix["release"] == {"d": "2026-08-05", "url": U.doc_url(CIK, "0001234567-26-000028", "x8k.htm")}
    assert ix["k10"]["url"].endswith("/000123456726000027/k.htm") and ix["mk"] == "us" and ix["site"] == "https://investors.test.com"
    assert "Revenue was" not in json.dumps(ix) and "payroll" not in json.dumps(ix)          # 清單不含全文
    md = U.render_md(pk)
    for s in ("## 最新年報 10-K（申報 2026-02-19", "### Item 1A. Risk Factors", "### Item 2. Management", "#### EX-99.1 Press release",
              "Revenue was $500 million", "2.02 營運成果與財務狀況（財報）"):
        assert s in md, s


def test_build_marks_failures_older_quarterly_and_truncation(monkeypatch):
    get, _ = _get(_sub(), fail=("submissions",))
    pk = U.build("TST", CIK, date(2026, 11, 4), get, log=lambda *_: None)
    assert pk["ok"] is False and pk["st"]["sub"].startswith("err")
    sub = _sub(forms=("10-K", "10-Q"), days=("2026-02-19", "2025-11-01"))                   # 最新的是年報：比它舊的季報不用
    get, _ = _get(sub)
    pk = U.build("TST", CIK, date(2026, 3, 1), get, log=lambda *_: None)
    assert pk["ok"] and pk["st"]["q10"] == "older" and "q10" not in pk and U.index(pk)["q10"] is None and U.index(pk)["release"] is None
    monkeypatch.setitem(U.CAP, "1", 60)
    get, _ = _get(_sub())
    pk = U.build("TST", CIK, date(2026, 11, 4), get, log=lambda *_: None)
    s = pk["k10"]["sec"]["1"]
    assert s["cut"] and len(s["text"]) <= 60 < s["n"] and "（太長，只放前段）" in U.render_md(pk)
    get, _ = _get(_sub(), fail=("/k.htm",))
    pk = U.build("TST", CIK, date(2026, 11, 4), get, log=lambda *_: None)
    assert not pk["ok"] and pk["st"]["k10"].startswith("err")


def _script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_request_accepts_us_codes_and_files_stay_local(tmp_path):
    assert U.CODE_RE.fullmatch("us:PAYC") and U.CODE_RE.fullmatch("us:BRK.B")
    for bad in ("us:payc", "us:", "us:PAYC;rm", "us:../X", "us:A/B", "tw:6870"):
        assert not U.CODE_RE.fullmatch(bad), bad
    F = _script("fetch_eqdocs")
    ping = tmp_path / "eqdocs"
    ping.write_text(json.dumps({"id": "20261104-1200-abcdef", "codes": ["us:PAYC", "tw:6870", "us:PAYC"]}), encoding="utf-8")
    assert F.request(Namespace(ping=str(ping), codes=None)) == ("20261104-1200-abcdef", ["us:PAYC", "tw:6870"], False)
    ping.write_text(json.dumps({"id": "20261104-1200-abcdef", "codes": ["us:PAYC $(x)"]}), encoding="utf-8")
    try:
        F.request(Namespace(ping=str(ping), codes=None))
        raise AssertionError("壞代號要擋")
    except SystemExit:
        pass
    pk = F.us_pack("PAYC", None)                                                          # 沒有 SEC_CONTACT_EMAIL：記成沒抓到，不擋台股
    assert pk["ok"] is False and pk["st"]["sub"].startswith("err") and pk["mk"] == "us"
    R = _script("eq_docs_req")
    for ok in ("us-PAYC.md", "us-BRK.B.json"):
        assert R.KEEP.fullmatch(ok), ok
    for bad in ("us-payc.md", "us-PAYC.py", "us-../x.md"):
        assert not R.KEEP.fullmatch(bad), bad


def test_sec_email_only_from_secret_and_never_printed():
    wf = (ROOT / ".github" / "workflows" / "eq_docs.yml").read_text("utf-8")
    assert "SEC_CONTACT_EMAIL: ${{ secrets.SEC_CONTACT_EMAIL }}" in wf and "echo \"$SEC_CONTACT_EMAIL" not in wf
    src = (ROOT / "scripts" / "fetch_eqdocs.py").read_text("utf-8") + (ROOT / "arm" / "lab" / "eqdocs_us.py").read_text("utf-8")
    assert "print(email" not in src and "SF.contact()" in src and not re.search(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", src)
