"""美股個股卡的季報摘要（arm/lab/usfin.py；docs/lab_review_plan.md 第 4 節 (b)(c)）：單季（第四季＝全年 − 前三季）、
營收取最早公布的項目、毛利沒有就用營收減成本、時點項目（股東權益）和季底差幾天也對得上、流通股數、這一批的代號、沒變不寫。"""
import json

import pytest

from arm.lab import usfin as UF


def _doc():
    rev = [["2024-01-01", "2024-03-31", 100e6, "2024-05-01", "10-Q"], ["2024-01-01", "2024-06-30", 210e6, "2024-08-01", "10-Q"],
           ["2024-04-01", "2024-06-30", 110e6, "2024-08-01", "10-Q"], ["2024-01-01", "2024-09-30", 330e6, "2024-11-01", "10-Q"],
           ["2024-07-01", "2024-09-30", 120e6, "2024-11-01", "10-Q"], ["2024-01-01", "2024-12-31", 460e6, "2025-02-20", "10-K"],
           ["2025-01-01", "2025-03-31", 140e6, "2025-05-01", "10-Q"]]
    cost = [[s, e, v * 0.6, fd, fm] for s, e, v, fd, fm in rev]
    eps = [[s, e, v / 100e6, fd, fm] for s, e, v, fd, fm in rev]
    ni = [[s, e, v * 0.1, fd, fm] for s, e, v, fd, fm in rev]
    oi = [[s, e, v * 0.2, fd, fm] for s, e, v, fd, fm in rev]
    eq = [["", "2024-03-30", 500e6, "2024-05-01", "10-Q"], ["", "2024-06-29", 510e6, "2024-08-01", "10-Q"],
          ["", "2024-09-28", 520e6, "2024-11-01", "10-Q"], ["", "2024-12-31", 530e6, "2025-02-20", "10-K"],
          ["", "2025-03-29", 540e6, "2025-05-01", "10-Q"]]
    sh = [["", "2024-04-25", 50e6, "2024-05-01", "10-Q"], ["", "2025-04-25", 49e6, "2025-05-01", "10-Q"]]
    return {"cik": 1, "f": {"Revenues": rev, "CostOfRevenue": cost, "EarningsPerShareDiluted": eps, "NetIncomeLoss": ni,
                            "OperatingIncomeLoss": oi, "StockholdersEquity": eq, "EntityCommonStockSharesOutstanding": sh}}


def test_summary_quarters_q4_gross_profit_and_equity():
    x = UF.summary(_doc())
    q = {r[0]: r for r in x["q"]}
    assert [r[0] for r in x["q"]] == ["2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31", "2025-03-31"]
    assert q["2024-12-31"][2] == 130.0 and q["2024-12-31"][1] == "2025-02-20"          # 第四季＝全年 460 − 前三季 330
    assert q["2024-12-31"][3] == 52.0                                                   # 毛利＝營收 − 成本（130 × 0.4）
    assert q["2024-12-31"][6] == 1.3 and q["2024-12-31"][4] == 26.0 and q["2024-12-31"][5] == 13.0
    assert q["2024-03-31"][7] == 500.0 and q["2025-03-31"][7] == 540.0                 # 股東權益：季底差幾天也對得上
    assert x["sh"] == [["2024-04-25", "2024-05-01", 50.0], ["2025-04-25", "2025-05-01", 49.0]]
    assert UF.summary({"f": {}}) is None and UF.summary(None) is None


def test_codes_for_and_save_only_when_changed(tmp_path):
    L = {"now": {"hold": [{"c": "VLO"}], "buy": ["FTNT"], "list": [{"c": c} for c in ("VLO", "FTNT", "A", "B", "C", "D", "E", "F")]}}
    cs = UF.codes_for(L)
    assert cs[:2] == ["VLO", "FTNT"] and len(cs) == 8 and len(set(cs)) == 8
    p = tmp_path / "fin.json"
    doc = {"ver": UF.VER, "made": "2026-10-24", "sec": "2026-10-24", "codes": cs, "s": {"VLO": UF.summary(_doc())}}
    assert UF.save(doc, p) and UF.load(p)["s"]["VLO"]["q"][0][0] == "2024-03-31"
    assert not UF.save({**doc, "made": "2026-10-31"}, p)                                # 只有日期變＝不寫
    assert UF.save({**doc, "sec": "2026-10-31"}, p)
    p.write_text(json.dumps({"ver": 0}), encoding="utf-8")
    assert UF.load(p) == {}


def test_committed_file_matches_live_record():
    """入庫的季報涵蓋配置頁美股會出現的每一檔（每週六跟著每週紀錄更新）。"""
    from arm import fund_intro as FI
    from arm.lab import ussxqm as QM
    doc = UF.load()
    L = QM.load_live()
    if not doc or not L.get("now"):
        return
    want, _ = FI.qm_codes(L)
    assert set(want) <= set(doc["codes"])


# ── 同產業（GICS 細產業；docs/lab_review_plan.md 第 4 節 (e)） ─────────────────────────────────

def _wiki(rows, extra_table=True):
    """假的維基百科成分股頁：前面先放一張不相干的表、表頭照 S&P 500 頁的寫法（含註腳 sup）。"""
    t0 = "<table><tr><th>Date</th><th>Added</th></tr><tr><td>2020</td><td>X</td></tr></table>" if extra_table else ""
    hd = "<tr><th>Symbol</th><th>Security</th><th>GICS Sector</th><th>GICS Sub-Industry<sup>[1]</sup></th><th>HQ</th></tr>"
    body = "".join(f'<tr><td><a href="x">{s}</a></td><td>{n}</td><td>{sec}</td><td>{sub}</td><td>US</td></tr>' for s, n, sec, sub in rows)
    return f"<html>{t0}<table class=wikitable>{hd}{body}</table></html>"


def test_parse_wiki_symbol_cleanup_and_header_columns():
    g = UF.parse_wiki(_wiki([("BRK.B", "Berkshire Hathaway", "Financials", "Multi-Sector Holdings"),
                             ("VLO", "Valero Energy &amp; Co", "Energy", "Oil &amp; Gas Refining &amp; Marketing"),
                             ("bad1", "Junk", "X", "Y")]))
    assert g["BRK-B"] == ["Financials", "Multi-Sector Holdings", "Berkshire Hathaway"]
    assert g["VLO"] == ["Energy", "Oil & Gas Refining & Marketing", "Valero Energy & Co"] and "BAD1" not in g
    assert UF.parse_wiki("<table><tr><th>Symbol</th></tr></table>") == {} and UF.parse_wiki("") == {}


def test_update_gics_keeps_old_page_when_fetch_fails_or_too_few(tmp_path, monkeypatch):
    monkeypatch.setattr(UF, "WIKI_MIN", {"500": 2, "400": 2, "600": 2})
    p = tmp_path / "gics.json"
    pages = {UF.WIKI["500"]: _wiki([("AAA", "A", "Energy", "Oil"), ("BBB", "B", "Energy", "Oil")]),
             UF.WIKI["400"]: _wiki([("CCC", "C", "Energy", "Oil"), ("AAA", "A2", "Energy", "Gas")]),
             UF.WIKI["600"]: _wiki([("DDD", "D", "Utilities", "Water"), ("EEE", "E", "Utilities", "Water")])}
    st = UF.update_gics(fetch=pages.get, path=p, today="2026-10-28")
    g = UF.load_gics(p)
    assert st["500"] == 2 and st["saved"] and g["d"] == "2026-10-28"
    assert g["s"]["AAA"] == ["500", "Energy", "Oil", "A"] and g["s"]["DDD"][0] == "600"          # 兩頁都有：先抓到的那頁
    def bad(u):
        if u == UF.WIKI["600"]:
            raise RuntimeError("HTTP 403")
        return _wiki([("ZZZ", "Z", "Energy", "Oil")]) if u == UF.WIKI["400"] else pages[u]
    st = UF.update_gics(fetch=bad, path=p, today="2026-10-29")
    g2 = UF.load_gics(p)
    assert st["600"].startswith("RuntimeError: HTTP 403") and "只有 1 家" in st["400"] and "saved" not in st
    assert g2 == g                                                                               # 抓不到、家數不夠：沿用舊的、不改檔


def _F(rev0=100.0, g=0.2, om=0.25, ni=0.1, eq=1000.0, n=8):
    """n 季、營收每年成長 g（季營收照年成長換算）、營業利益率 om、淨利率 ni、股東權益 eq（百萬美元）。"""
    ends = [f"{2024 + i // 4}-{('03-31', '06-30', '09-30', '12-31')[i % 4]}" for i in range(n)]
    q = []
    for i, e in enumerate(ends):
        rv = rev0 * (1 + g) ** (i / 4)
        q.append([e, e, rv, rv * 0.5, rv * om, rv * ni, 1.0, eq])
    return {"q": q}


def test_peer_row_metrics():
    from datetime import date, timedelta
    ds = [(date(2025, 10, 1) + timedelta(days=k)).isoformat() for k in range(0, 400, 7)]
    px = {"d": ds, "c": [100.0 + k for k in range(len(ds))]}
    r = UF.peer_row("AAA", _F(), 5e9, px)
    assert r[0] == "AAA" and r[1] == 50.0                                                       # 億美元
    assert r[2] == pytest.approx(0.2, abs=1e-3) and r[3] == pytest.approx(0.25) and r[4] is not None
    ni4 = sum(x[5] for x in _F()["q"][-4:])
    assert r[5] == round(5e9 / (ni4 * 1e6), 1)
    k = max(j for j, d in enumerate(ds) if d <= (date.fromisoformat(ds[-1]) - timedelta(days=365)).isoformat())
    assert r[6] == round(px["c"][-1] / px["c"][k] - 1, 4)
    assert UF.peer_row("X", None, None, None) == ["X", None, None, None, None, None, None]
    f = _F(ni=-0.1)
    assert UF.peer_row("L", f, 5e9, None)[5] is None                                            # 虧損：本益比不算


def test_peers_nearest_market_cap_in_same_sub_industry():
    gics = {c: ["500", "Energy", "Refining", c] for c in ("A", "B", "C", "D", "E", "F", "G", "H")}
    gics["Z"] = ["500", "Energy", "Drilling", "Z"]
    cap = {"A": 100e9, "B": 80e9, "C": 50e9, "D": 30e9, "E": 20e9, "F": 10e9, "G": 5e9, "H": 1e9, "Z": 49e9}
    scr = {c: ["NYSE", "Energy", "x", "US", "2000", v] for c, v in cap.items()}
    nosec = {"F"}
    p = UF.peers("D", gics, scr, lambda k: None if k in nosec else _F(), lambda k: None)
    got = [r[0] for r in p["rows"]]
    assert p["ind"] == "Refining" and p["sec"] == "Energy" and p["n"] == 8 and p["rk"] == 4
    assert "D" in got and "Z" not in got and "F" not in got and len(got) == UF.PEER_N            # 沒有季報的跳過、別的細產業不算
    assert got == sorted(got, key=lambda c: -cap[c])                                             # 依市值大到小
    assert set(got) == {"B", "C", "D", "E", "G", "A"}                                            # 對數市值最接近的 5 家
    assert UF.peers("Q", gics, scr, lambda k: _F(), lambda k: None) is None                      # 不在 S&P 1500
    few = {"D": gics["D"], "E": gics["E"]}
    assert UF.peers("D", few, scr, lambda k: _F(), lambda k: None) is None                       # 不到 PEER_MIN 家
