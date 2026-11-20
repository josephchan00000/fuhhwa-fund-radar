"""台股財報季（arm/lab/earntw.py、arm/lab/earnpage.py；規格 arm/lab/ernspec.py VER 2；docs/lab_earnings_plan.md 第 10 節）。"""
import json

from arm.lab import earnpage as P
from arm.lab import earntw as E

QK = ["rev", "gp", "op", "nip", "eps"]


def _co(rows, n="測試", ind="電子零組件業"):
    return {"n": n, "ind": ind, "qk": QK, "q": [[q] + v for q, v in rows], "mo": [["2026-08", 1.0], ["2026-09", 1.0], ["2026-10", 1.0]]}


def _rows(eps24, eps25, eps26, nip26=None):
    out = []
    for y, eps in ((2024, eps24), (2025, eps25), (2026, eps26)):
        for i, e in enumerate(eps):
            q = f"{y}-{E.QEND[i]}"
            ni = (nip26[i] if nip26 and y == 2026 else e * 1e5)
            out.append((q, [1e7 * (y - 2023) * (1 + i / 10), 3e6, 2e6, ni, e]))
    return out


def test_target_quarter():
    assert E.target("2026-11-20") == "2026-09-30" and E.target("2026-11-10") == "2026-06-30" and E.target("2026-04-01") == "2025-12-31"


def test_share_change_eps_and_full_year():
    co = _co(_rows([1, 1, 1, 1], [2, 2, 2, 2], [70, 86.38, -62.34], nip26=[1.2e7, 1.708e7, 2.336e7]))
    cons = {"src": "FactSet（鉅亨網）", "d": "2026-11-12", "n": 16, "eps": {"2026": {"med": 135.82}}}
    r = E.company("6669", co, cons, "2026-09-30")
    assert r["in"] and r["eps_note"] == "股數有變，用淨利比例換算"
    assert r["eps"] == round(94.04 * 2.336e7 / (1.2e7 + 1.708e7 + 2.336e7), 2)
    fy = r["fy"]
    assert fy["ytd"] == 94.04 and fy["need"] == round(135.82 - 94.04, 2)              # 今年累計＝公布的累計，不用換算過的數
    assert fy["k"] in ("lo", "ok", "hi") and fy["exp"] == round(r["eps"] * 2 / 2, 2)
    assert r["ni_yoy"] is not None and r["ni_yoy"] > 0                                  # 成長看淨利，不看股數變了的每股盈餘


def test_full_year_buckets_and_reasons():
    co = _co(_rows([1, 1, 1, 1], [1, 1, 1, 1], [1, 1, 1]))
    def fy(med, d="2026-11-10"):
        return E.company("1111", co, {"eps": {"2026": {"med": med}}, "d": d, "src": "Yahoo Finance"}, "2026-09-30")["fy"]
    assert fy(4.0)["k"] == "ok" and fy(3.5)["k"] == "lo" and fy(4.5)["k"] == "hi"
    assert fy(4.0, d="2026-10-01")["stale"] and not fy(4.0)["stale"]
    assert E.company("1111", co, {}, "2026-09-30")["fy"] == {"k": "na", "why": "沒有全年預估"}
    loss = _co(_rows([1, 1, 1, -1], [1, 1, 1, -1], [1, 1, 1]))
    assert E.company("1111", loss, {"eps": {"2026": {"med": 3}}}, "2026-09-30")["fy"]["why"] == "有一季虧損，照季節算不準"
    q4 = E.company("1111", _co(_rows([1] * 4, [1] * 4, [1] * 4)), {"eps": {"2026": {"med": 4}}}, "2026-12-31")
    assert q4["fy"]["k"] == "na"


def test_not_in_yet_and_decel():
    co = _co(_rows([1] * 4, [1] * 4, [1, 1]))
    r = E.company("2881", co, {}, "2026-09-30")
    assert r["in"] is False and r["last"] == "2026-06-30"
    rows = _rows([1] * 4, [1] * 4, [1, 1, 1])
    rows[-2] = (rows[-2][0], [rows[-2][1][0] * 3] + rows[-2][1][1:])                     # 第二季營收大增 → 第三季年增掉很多
    assert E.company("1111", _co(rows), {}, "2026-09-30")["decel"] is True


def test_members(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "holding_profiles.json").write_text(json.dumps({"profiles": {
        "台光電": {"ticker": "2383", "country": "台灣"}, "元大台灣50": {"ticker": "0050", "country": "台灣"},
        "APPLE INC": {"ticker": "AAPL", "country": "美國"}}}, ensure_ascii=False))
    (tmp_path / "data" / "funds").mkdir(parents=True)
    (tmp_path / "data" / "funds" / "01.json").write_text(json.dumps({"short_name": "復華", "top_holdings": [
        {"name": "台光電", "weight": 11.6}, {"name": "元大台灣50", "weight": 3}, {"name": "APPLE INC", "weight": 2}]}, ensure_ascii=False))
    (tmp_path / "data" / "etf_holdings.json").write_text(json.dumps({"etfs": {"00991A": {"holdings": [
        {"stock_id": "2330", "name": "台積電", "weight": 13.2}]}, "0050": {"holdings": [{"stock_id": "2317", "name": "鴻海"}]}}}, ensure_ascii=False))
    (tmp_path / "dashboard").mkdir()
    (tmp_path / "dashboard" / "x9.html").write_text('<script>var D={"pick":{"tw":{"pos":{"4958":[{"k":"boom"}]},"names":{"boom":"新飆股"}}}}</script>')
    M = E.members(tmp_path)
    assert set(M) == {"2383", "2330", "4958"}                                            # 0050（ETF）、美股、別家的 ETF 都不算
    assert M["2383"]["who"] == [["復華", 11.6]] and M["2330"]["who"] == [["00991A", 13.2]] and M["4958"]["who"] == [["選股頁：新飆股", None]]


def test_summary_and_page():
    co = _co(_rows([1] * 4, [1] * 4, [1, 1, 2]))
    rows = {"1111": E.company("1111", co, {"eps": {"2026": {"med": 6}}, "d": "2026-11-10", "src": "Yahoo Finance"}, "2026-09-30", px1m=-12.3),
            "2881": {"n": "富邦金", "q": "2026-09-30", "in": False, "last": "2026-06-30"}}
    rows["1111"]["who"] = [["復華", 5.0], ["00991A", 1.2]]
    rows["2881"]["who"] = [["復華", 3.0]]
    s = E.summary(rows)
    assert s["n"] == 2 and s["in"] == 1 and s["out"] == ["2881"] and s["eps"]["up"] == 1
    doc = {"q": "2026-09-30", "made": "2026-11-20", "rows": rows, "sum": s}
    h = P.block(doc)
    assert "財報季・2026 第三季" in h and "已進資料 1 家" in h and "還沒進來 1 家：富邦金" in h
    assert 'data-c="1111"' in h and "獲利比去年同季 +100%" in h and "近 1 個月股價" in h and 'id="ern-fs"' in h
    assert "第三季資料還沒進來（期限後補抓）" in h and 'data-f="out"' in h
    assert 'id="ern-root"' in h and 'id="ern"' not in h                                # 分頁本身是 id="ern"，裡面不能再用同一個 id
    assert P.block({}) == '<p class="oplead">財報季的資料還沒準備好（每天建頁時更新）。</p>' and "#ern-grp" in P.JS


def test_options_page_has_tab():
    from arm.lab import txopage
    assert ("ern", "財報") in txopage.TABS and "'ern'" in txopage.TAB_JS
