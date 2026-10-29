"""成分股內部人買賣（heatspec_us VER 3 的 S7）：解析與算法。不碰網路，格式照 CI 探針看到的（docs/lab_us_chip_plan.md 第 7 節）。"""
import io
import zipfile

from arm.lab import heatspec_us as HU
from arm.lab import insider as I


def _zip(sub: list, own: list, tr: list) -> bytes:
    def tsv(head, rows):
        return "\t".join(head) + "\n" + "".join("\t".join(r) + "\n" for r in rows)
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("SUBMISSION.tsv", tsv(["ACCESSION_NUMBER", "FILING_DATE", "PERIOD_OF_REPORT", "DOCUMENT_TYPE",
                                          "ISSUERCIK", "ISSUERNAME", "ISSUERTRADINGSYMBOL"], sub))
        z.writestr("REPORTINGOWNER.tsv", tsv(["ACCESSION_NUMBER", "RPTOWNERCIK", "RPTOWNERNAME",
                                              "RPTOWNER_RELATIONSHIP"], own))
        z.writestr("NONDERIV_TRANS.tsv", tsv(["ACCESSION_NUMBER", "NONDERIV_TRANS_SK", "SECURITY_TITLE", "TRANS_DATE",
                                              "TRANS_CODE", "TRANS_SHARES", "TRANS_ACQUIRED_DISP_CD"], tr))
    return b.getvalue()


def test_parse_dataset_keeps_form4_director_officer_open_market_only():
    zb = _zip(
        [["A1", "31-MAR-2006", "30-MAR-2006", "4", "0000320193", "APPLE", "AAPL"],
         ["A2", "31-MAR-2006", "30-MAR-2006", "4", "0000789019", "MSFT", "MSFT"],
         ["A3", "31-MAR-2006", "30-MAR-2006", "4/A", "0000320193", "APPLE", "AAPL"],     # 修正申報不算
         ["A4", "03-APR-2006", "30-MAR-2006", "4", "0000320193", "APPLE", "AAPL"],
         ["A5", "03-APR-2006", "30-MAR-2006", "4", "0000002488", "AMD", "AMD"]],
        [["A1", "1", "X", "Officer"], ["A2", "2", "Y", "TenPercentOwner"], ["A3", "3", "Z", "Director"],
         ["A4", "4", "W", "Director,TenPercentOwner"], ["A5", "5", "V", "Other"]],
        [["A1", "1", "Common", "29-MAR-2006", "S", "1000", "D"],
         ["A1", "2", "Common", "29-MAR-2006", "P", "300", "A"],
         ["A1", "3", "Common", "29-MAR-2006", "M", "5000", "A"],      # 履約不算
         ["A2", "4", "Common", "29-MAR-2006", "P", "100", "A"],       # 只是大股東
         ["A3", "5", "Common", "29-MAR-2006", "P", "100", "A"],
         ["A4", "6", "Common", "30-MAR-2006", "P", "250.5", "A"],
         ["A5", "7", "Common", "30-MAR-2006", "S", "70", "D"]])
    got = I.parse_dataset(zb)
    assert got == {"A1": ("2006-03-31", 320193, "AAPL", -700.0), "A4": ("2006-04-03", 320193, "AAPL", 250.5)}


def test_parse_form4_xml_from_full_submission():
    xml = """<SEC-DOCUMENT>... <XML>
<ownershipDocument>
  <documentType>4</documentType>
  <issuer><issuerCik>0000001750</issuerCik><issuerName>AAR CORP</issuerName>
  <issuerTradingSymbol>AIR</issuerTradingSymbol></issuer>
  <reportingOwner><reportingOwnerRelationship><isDirector>1</isDirector><isOfficer>true</isOfficer>
  <isTenPercentOwner>0</isTenPercentOwner></reportingOwnerRelationship></reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction><transactionCoding><transactionFormType>4</transactionFormType>
      <transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>35000</value></transactionShares>
      <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode></transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction><transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>1,000</value></transactionShares></transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction><transactionCoding><transactionCode>F</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>9</value></transactionShares></transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument></XML>"""
    assert I.parse_form4(xml) == (1750, "AIR", -34000.0)
    assert I.parse_form4(xml.replace("<documentType>4</documentType>", "<documentType>4/A</documentType>")) is None
    only10 = xml.replace("<isDirector>1</isDirector><isOfficer>true</isOfficer>", "<isDirector>0</isDirector>")
    assert I.parse_form4(only10) is None
    assert I.parse_form4(xml.replace(">S<", ">G<").replace(">P<", ">A<")) is None       # 沒有 P／S
    assert I.parse_form4("no xml") is None


def test_parse_index_and_sic():
    txt = ("Form Type   Company Name   CIK   Date Filed  File Name\n" + "-" * 40 + "\n"
           "4                AAR CORP                                                      1750        20261028    "
           "edgar/data/1750/0000001750-26-000106.txt\n"
           "4/A              ACME UNITED CORP                                              2098        20261028    "
           "edgar/data/2098/0001193125-26-436216.txt\n"
           "4                SMITH JOHN                                                    1234567     20261028    "
           "edgar/data/1234567/0000001750-26-000106.txt\n"
           "10-Q             SOMETHING                                                     99          20261028    "
           "edgar/data/99/0000000099-26-000001.txt\n")
    assert I.parse_index(txt) == [(1750, "edgar/data/1750/0000001750-26-000106.txt"),
                                  (1234567, "edgar/data/1234567/0000001750-26-000106.txt")]
    assert I.parse_sic("<cik>0001025881</cik> x <cik>0000907687</cik>") == [1025881, 907687]
    assert I.iso_date("31-MAR-2006") == "2006-03-31" and I.iso_date("2026-10-28") == "2026-10-28"
    assert I.iso_date("bad") is None


def test_spans_keep_and_shards():
    sp = I.Spans([["BRK-B", "2010-02-16", None], ["XYZ", "2000-01-01", "2010-01-01"]])
    assert sp("BRK.B", "2020-01-01") and sp("BRKB", "2010-02-16") and not sp("BRK.B", "2010-02-15")
    assert sp("XYZ", "2009-12-31") and not sp("XYZ", "2010-01-01")
    G = {"ndx": {11}, "semi": {22}}
    assert I.keep(5, "XYZ", "2005-01-01", sp, G) == 1
    assert I.keep(11, "QQQX", "2005-01-01", sp, G) == 0 and I.keep(22, "", "2005-01-01", sp, G) == 0
    assert I.keep(33, "XYZ", "2011-01-01", sp, G) is None
    rows = [("2009-12-30", 5, "XYZ", 100.0), ("2009-12-30", 5, "XYZ", -40.4), ("2009-12-30", 11, "QQQX", 7.0),
            ("2009-12-31", 99, "NOPE", 3.0), ("2010-01-04", 22, "SEMI", -5.0)]
    assert I.to_shards(rows, sp, G) == {"2009-12": {"2009-12-30": {"5": [60, 1], "11": [7, 0]}},
                                       "2010-01": {"2010-01-04": {"22": [-5, 0]}}}


def test_through_follows_quarters_then_consecutive_days():
    assert I.q_end("2026q3") == "2026-09-30" and I.q_end("2026q4") == "2026-12-31" and I.q_end("2026q1") == "2026-03-31"
    assert I.through({}) is None
    st = {"q": ["2026q2", "2026q3"], "days": ["2026-10-01", "2026-10-02", "2026-10-05", "2026-10-07"]}
    assert I.through(st) == "2026-10-05"                     # 10/6 沒做，10/7 不算
    assert I.through({"q": ["2026q3"], "days": []}) == "2026-09-30"


def test_ratio_series_window_availability_and_minimum(monkeypatch):
    monkeypatch.setattr(HU, "INS_DAYS", 3)
    monkeypatch.setattr(HU, "INS_MIN", {"spx": 2, "ndx": 2, "semi": 1})
    cal = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09", "2026-01-12"]
    D = {"2026-01-05": {"1": [100, 1], "2": [-50, 1], "9": [10, 0]},
         "2026-01-06": {"2": [80, 1]},                       # 2 號公司兩天合計淨買 30
         "2026-01-10": {"3": [-5, 1]}}                       # 週六申報，週一才算
    M = {"ndx": [9], "semi": []}
    st = {"through": "2026-01-10"}
    s = I.ratio_series(cal, "spx", D, M, st)
    # 1/6：只看得到 1/5 的申報（1 淨買、2 淨賣）＝50%；1/7：再加 1/6 的申報，2 號合計淨買＝100%
    assert s["2026-01-06"] == 50.0 and s["2026-01-07"] == 100.0 and s["2026-01-08"] == 100.0
    assert "2026-01-05" not in s                             # 當天還看不到當天的申報
    assert "2026-01-09" not in s                             # 1/5 的申報出了 3 天的窗，只剩 2 號一家（< 2 家）
    assert "2026-01-12" not in s                             # 1/12 只剩週六申報的 3 號一家
    s2 = I.ratio_series(cal, "spx", D, M, {"through": "2026-01-06"})
    assert max(s2) == "2026-01-07"                           # 涵蓋到 1/6：1/8 起前一個交易日還沒涵蓋
    assert I.ratio_series(cal, "ndx", D, M, st) == {}         # 那斯達克 100 只有 1 家（< 2 家）
    monkeypatch.setattr(HU, "INS_MIN", {"spx": 2, "ndx": 1, "semi": 1})
    assert I.ratio_series(cal, "ndx", D, M, st)["2026-01-06"] == 100.0


def test_no_email_anywhere_in_module():
    import inspect
    src = inspect.getsource(I)
    assert "@" not in src.replace("@property", "")         # 聯絡 email 只從 secret 讀，程式裡不出現
