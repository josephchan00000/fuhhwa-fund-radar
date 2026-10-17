"""法人預估（arm/lab/fcst.py；docs/lab_forward_plan.md）：解析鉅亨 FactSet 快訊與 Yahoo 分析師資料。"""
import html
import json
from datetime import date
from pathlib import Path

from arm.lab import fcst

FX = json.loads((Path(__file__).parent / "fixtures" / "fcst_cnyes.json").read_text(encoding="utf-8"))


def _item(k):
    it = dict(FX[k])
    it["content"] = html.escape(it["content"])          # API 回的是跳脫過的 HTML
    return it


def test_parse_eps_article():
    e = fcst.parse_article(_item("e"))
    assert e["k"] == "e" and e["c"] == "4958" and e["nm"] == "臻鼎-KY" and e["d"] == "2026-10-15"
    assert (e["n"], e["y"], e["o"], e["v"], e["hi"], e["lo"], e["tp"]) == (8, 2026, 14.05, 14.23, 16.18, 12.65, 671.5)
    assert e["eps"][0] == [2026, 16.18, 12.65, 14.38, 14.23]          # 括號內的前值不要
    assert e["eps"][2] == [2028, 67.64, 30.78, 47.51, 44.1]
    assert e["rev"][0] == [2026, 2414.9, 2211.5, 2288.5, 2276.5]      # 千元 → 億元
    assert [r[0] for r in e["rev"]] == [2026, 2027, 2028]


def test_parse_target_article():
    t = fcst.parse_article(_item("t"))
    assert t["k"] == "t" and t["c"] == "2455" and t["d"] == "2026-10-15"
    assert (t["n"], t["o"], t["v"], t["pct"], t["hi"], t["lo"]) == (10, 622.5, 710.0, 14.06, 846.0, 268.0)
    assert t["rt"] == [9, 1, 0]
    down = _item("t")
    down["content"] = down["content"].replace("上修", "下修").replace("調升", "調降")
    assert fcst.parse_article(down)["pct"] == -14.06


def test_unknown_format_returns_none():
    assert fcst.parse_article({"newsId": 1, "publishAt": 1792073460, "content": "&lt;p&gt;別的格式&lt;/p&gt;"}) is None


def test_merge_dedupes_and_sorts(tmp_path, monkeypatch):
    monkeypatch.setattr(fcst.store, "LAB", tmp_path)
    doc = fcst.load_fs()
    st: dict = {}
    fcst._merge_fs(doc, [_item("t"), _item("e"), _item("t")], st)
    assert st["new"] == 2 and set(doc["ev"]) == {"4958", "2455"}
    row = doc["ev"]["4958"][0]
    assert dict(zip(fcst.EV_COLS["e"], row))["v"] == 14.23
    assert dict(zip(fcst.EV_COLS["t"], doc["ev"]["2455"][0]))["rt"] == [9, 1, 0]
    fcst._merge_fs(doc, [_item("e")], st)                              # 同一則再進來不重複
    assert len(doc["ev"]["4958"]) == 1
    newer = _item("e")
    newer["newsId"], newer["publishAt"] = 6631999, 1792160000
    fcst._merge_fs(doc, [newer], st)                                   # 舊的 EPS 快訊不留三年表格，最新的留
    assert len(doc["ev"]["4958"][0]) == 10 and len(doc["ev"]["4958"][1]) == 12
    fcst._write_lines(fcst.FS_FILE, doc, "ev")
    assert fcst.load_fs()["ev"] == doc["ev"]                           # 一檔一行的寫法仍是合法 JSON
    assert not fcst._write_lines(fcst.FS_FILE, doc, "ev")              # 內容沒變不改寫
    fcst._merge_fs(doc, [_item("e")], st)
    doc["ev"]["4958"] = doc["ev"]["4958"][:1]
    doc["ev"]["4958"][0][0] = "2015-01-02"
    fcst._prune_fs(doc, date(2026, 10, 16))                            # 超過保留天數的刪掉
    assert "4958" not in doc["ev"]


def _yh(n=35):
    def v(x):
        return {"raw": x, "fmt": str(x)}
    tr = lambda p, end, a, lo, hi, k, ra: {  # noqa: E731
        "period": p, "endDate": end,
        "earningsEstimate": {"avg": v(a), "low": v(lo), "high": v(hi), "numberOfAnalysts": v(k), "yearAgoEps": v(65.9),
                             "growth": v(0.6716)},
        "revenueEstimate": {"avg": v(ra), "low": v(ra * 0.9), "high": v(ra * 1.1), "numberOfAnalysts": v(k + 3),
                            "yearAgoRevenue": v(3.81e12), "growth": v(0.4646)},
        "epsTrend": {"current": v(a), "7daysAgo": v(a), "30daysAgo": v(a * 0.97), "60daysAgo": v(a * 0.96),
                     "90daysAgo": v(a * 0.95)},
        "epsRevisions": {"upLast7days": v(2), "upLast30days": v(9), "downLast7Days": v(0), "downLast30days": v(3)}}
    return {"quoteSummary": {"result": [{
        "financialData": {"numberOfAnalystOpinions": v(n), "targetMeanPrice": v(3374.8), "targetMedianPrice": v(3300.0),
                          "targetHighPrice": v(5000.0), "targetLowPrice": v(2650.0), "recommendationMean": v(1.31429),
                          "financialCurrency": "TWD"},
        "earningsTrend": {"trend": [tr("0q", "2026-12-31", 33.0, 31.9, 33.8, 20, 1.7e12),
                                    tr("0y", "2026-12-31", 110.74562, 107.41, 113.20986, 30, 5.58002e12),
                                    tr("+1y", "2027-12-31", 148.09088, 126.5, 167.12775, 36, 7.60128e12)]},
        "recommendationTrend": {"trend": [{"period": "0m", "strongBuy": 9, "buy": 25, "hold": 1, "sell": 0,
                                           "strongSell": 0}]}}], "error": None}}


def test_parse_yahoo():
    r = fcst.parse_yahoo(_yh())
    assert r["n"] == 35 and r["tp"] == [3374.8, 3300.0, 5000.0, 2650.0] and r["rc"] == [9, 25, 1, 0, 0]
    assert "cur" not in r and r["rm"] == 1.31
    y0 = r["y0"]
    assert y0["end"] == "2026-12-31" and y0["e"][:4] == [110.746, 107.41, 113.21, 30] and y0["eg"] == 0.6716
    assert y0["r"][0] == 55800.2 and y0["r"][3] == 33 and y0["rv"] == [2, 9, 0, 3]
    assert y0["t"][2] == round(110.74562 * 0.97, 3)
    assert r["y1"]["end"] == "2027-12-31"
    assert "y0q" not in r                                              # 季度預估不存


def test_parse_yahoo_no_coverage():
    assert fcst.parse_yahoo({"quoteSummary": {"result": [{"financialData": {}, "earningsTrend": {"trend": []}}]}}) is None
    z = {"raw": 0, "fmt": "0"}                                         # 沒有分析師時 Yahoo 回 0 值（1240 實例）
    none_y = {"period": "0y", "endDate": "2021-12-31", "earningsEstimate": {"avg": {}, "numberOfAnalysts": {}},
              "revenueEstimate": {"avg": z, "low": z, "high": z, "numberOfAnalysts": z}}
    assert fcst.parse_yahoo({"quoteSummary": {"result": [{"financialData": {}, "earningsTrend": {"trend": [none_y]}}]}}) is None
    one = _yh(n=1)                                                     # 只有營收預估、沒有 EPS 預估也算
    one["quoteSummary"]["result"][0]["earningsTrend"]["trend"][1]["earningsEstimate"]["numberOfAnalysts"] = {"raw": 0}
    r = fcst.parse_yahoo(one)
    assert r["y0"]["e"] is None and r["y0"]["r"][0] == 55800.2
    assert fcst.parse_yahoo({"quoteSummary": {"result": None, "error": {"code": "Not Found"}}}) is None
    assert fcst.yahoo_sym("2330", "tw") == "2330.TW" and fcst.yahoo_sym("6274", "tp") == "6274.TWO"


def test_update_yahoo_keeps_old_on_failure(tmp_path, monkeypatch):
    """查到沒有分析師 → 拿掉；請求失敗 → 保留舊值；cover＝有紀錄的公司。"""
    monkeypatch.setattr(fcst.store, "LAB", tmp_path)
    fcst.store.write_json(fcst.YH_FILE, {"v": 1, "d": "2026-10-15", "full": "2026-10-12", "cover": ["1111", "2222", "3333"],
                                         "s": {"1111": {"n": 1}, "2222": {"n": 2}, "3333": {"n": 3}}})
    ans = {"1111.TW": ("ok", {"n": 9}), "2222.TW": ("ok", None), "3333.TWO": ("err", None)}
    monkeypatch.setattr(fcst._Yahoo, "login", lambda self: True)
    monkeypatch.setattr(fcst._Yahoo, "one", lambda self, sym: ans[sym])
    st = fcst.update_yahoo({"1111": "tw", "2222": "tw", "3333": "tp"}, today=date(2026, 10, 16))
    doc = fcst.load_yahoo()
    assert doc["s"] == {"1111": {"n": 9}, "3333": {"n": 3}} and doc["cover"] == ["1111", "3333"]
    assert st["ok"] == 1 and st["none"] == 1 and st["err"] == 1 and not st["full"]
    assert fcst.update_yahoo({"1111": "tw"}, today=date(2026, 10, 16)) == {"skip": "今天已抓過"}
    assert fcst.store.dates(fcst.YH_ARCH) == ["2026-10-16"]          # 每週封存一份


BANNED = ("保證", "穩賺", "必賺", "包賺", "必漲", "必跌", "一定會", "建議買賣", "建議買", "建議賣", "目標價", "零風險",
          "無風險", "穩賺不賠")
FC_FUNCS = ("fcGr", "fcVs", "fcSrc", "fcWho", "fcSec", "fcLine")      # 「目標價」只准出現在法人預估這幾支（2026-10-17 使用者）


def _js_func(js: str, name: str) -> str:
    i = js.index(f"function {name}(")
    j = js.find("\nfunction ", i + 1)
    return js[i:j if j > 0 else len(js)]


def test_page_doc_and_brief(tmp_path, monkeypatch):
    """x9f.json 不帶快訊標題；pe／pt 是頁面直接用的來源；飆股段小字＝[人數, 今年 EPS 比去年%, 30 天方向, 目標價比現價%, 目標價]。"""
    monkeypatch.setattr(fcst.store, "LAB", tmp_path)
    doc = fcst.load_fs()
    fcst._merge_fs(doc, [_item("e"), _item("t")], {})
    fcst._write_lines(fcst.FS_FILE, doc, "ev")
    pd = fcst.page_doc(today=date(2026, 10, 16))
    assert set(pd["s"]) == {"4958", "2455"} and pd["fs_from"] == "2026-10-15"
    assert not [w for w in BANNED if w in json.dumps(pd, ensure_ascii=False)]       # 快訊標題沒有轉載
    v = pd["s"]["4958"]
    assert v["pe"]["src"] == "fs" and v["pe"]["id"] == 6631542 and v["pe"]["n"] == 8
    assert v["pe"]["rows"][0] == [2026, 14.23, 12.65, 16.18, 2276.5]                # [年, EPS 中位數, 最低, 最高, 營收億]
    assert v["pt"] == {"src": "fs", "d": "2026-10-15", "v": 671.5, "n": 8, "id": 6631542}
    assert v["ev"][0] == ["2026-10-15", "e", 14.05, 14.23, 2026, 6631542]          # 每次調整帶 newsId（可點原文）
    t = pd["s"]["2455"]["pt"]
    assert (t["v"], t["hi"], t["lo"], t["n"], t["id"]) == (710.0, 846.0, 268.0, 10, 6631034)
    assert pd["s"]["2455"]["t"]["rt"] == [9, 1, 0]
    assert fcst.brief(v, 500.0, {"2025": 7.0}, date(2026, 10, 16)) == [8, 103.3, 1, 34.0, 671.5]
    assert fcst.brief(v, None, {}, date(2026, 12, 20)) == [8, None, None, None, 671.5]   # 30 天外不算方向


def test_view_prefers_fresh_source():
    """FactSet 超過 120 天沒有新快訊 → 改用 Yahoo（2377 實例：EPS 快訊停在 2025-08，「今年 EPS +94%」其實是一年多前的預估）；
    過去的年度不列；Yahoo 30 天前的 0 值＝沒有資料，不算上修。"""
    e_old = ["2025-08-09", "e", 1, 7, 2025, 10.0, 10.4, 14.17, 7.32, 165.0,
             [[2025, 14.17, 7.32, 10.28, 10.4], [2026, 14.46, 10.82, 12.63, 13.17], [2027, 13.92, 12.37, 13.14, 13.14]],
             [[2025, 1.0, 1.0, 1.0, 2404.2], [2026, 1.0, 1.0, 1.0, 2530.4], [2027, 1.0, 1.0, 1.0, 2550.9]]]
    t_new = ["2026-08-21", "t", 2, 6, 150.0, 155.0, 3.33, 190.0, 118.0, [4, 2, 0]]
    y = fcst.parse_yahoo(_yh(n=9))
    today = date(2026, 10, 17)
    v = fcst.view([e_old, t_new], y, today)
    assert v["pe"]["src"] == "y" and [r[0] for r in v["pe"]["rows"]] == [2026, 2027]
    assert v["pe"]["n"] == 30 and v["pe"]["rows"][0][1] == 110.746
    assert v["pt"]["src"] == "fs" and v["pt"]["v"] == 155.0                         # 目標價快訊 57 天前，還算新
    v2 = fcst.view([e_old], None, today)                                           # 沒有 Yahoo：用舊的、標 old
    assert v2["pe"]["old"] == 1 and [r[0] for r in v2["pe"]["rows"]] == [2026, 2027] and v2["pt"]["old"] == 1
    assert fcst.brief(v2, 160.0, {"2025": 6.79}, today) is None                    # 舊資料不進小字
    y["y0"]["t"] = [10.45, 0.0, 0.0, 0.0, 0.0]
    b = fcst.brief(fcst.view(None, y, today), 197.5, {"2025": 7.9}, today)
    assert b[2] is None and b[4] == 3300.0 and b[3] == round((3300 / 197.5 - 1) * 100, 0)
    assert "avg" not in fcst.view(None, y, today)["pt"]                             # 有中位數就用中位數
    y["tp"] = [3374.8, None, 5000.0, 2650.0]
    assert fcst.view(None, y, today)["pt"]["avg"] == 1 and fcst.view(None, y, today)["pt"]["v"] == 3374.8   # 沒有中位數才用平均、標 avg
    y["y0"]["t"] = [-0.5, 0.0, -1.0, 0.0, 0.0]                                       # 虧損縮小＝上修（不是相除後的 −50%）
    assert fcst.brief(fcst.view(None, y, today), 197.5, {}, today)[2] == 1


def test_company_card_and_wl_wiring():
    from pathlib import Path
    from arm.lab import copage
    js = copage.JS
    for s in ("id=co-fc", "id=co-ind", "'x9f.json?v='", "['co-fc','法人預估']", "['co-ind','產業']", "function fcLine",
              "產業熱度", "'法人預估':", "'產業比較':", 'data-cs="co-fc"', "openCo(a.dataset.co,a.dataset.cs)",
              "https://news.cnyes.com/news/id/", "/analysis/", "news.google.com/search"):
        assert s in js, s
    rest = js
    for fn in FC_FUNCS:
        rest = rest.replace(_js_func(js, fn), "")
    rest = rest.replace(js[js.index("'法人預估':"):js.index("'產業比較':")], "")
    assert "目標價" not in rest                                                     # 只在法人預估那幾支
    assert not [w for w in BANNED if w != "目標價" and w in js + copage.CSS]
    root = Path(__file__).resolve().parents[1]
    for wf in ("daily.yml", "afterhours_refresh.yml", "etf_holdings.yml"):
        t = (root / ".github/workflows" / wf).read_text("utf-8")
        assert t.count("git add -f dashboard/x9f.json 2>/dev/null || true") == 2, wf   # 一般與重試迴圈各一
    t = (root / ".github/workflows/afterhours_refresh.yml").read_text("utf-8")
    assert "timeout 420 python3 scripts/fetch_fcst.py" in t                         # 每班補快訊、Yahoo 一天一次
