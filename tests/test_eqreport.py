"""個股報告格式、估值重算、檢查、頁面（arm/lab/eqreport.py、eqpage.py、eqsite.py）。"""
import json

from arm.lab import eqpage as P
from arm.lab import eqreport as R
from arm.lab import eqsite
from arm.lab import eqspec as S


def _pack():
    q = [{"q": f"2025-{m}", "rev": 400.0 + i, "gp": 90.0, "op": 30.0, "nip": 20.0, "eps": 2.0, "ocf": 50.0, "icf": -40.0, "fcf": 10.0,
          "cash": 100.0, "ta": 1000.0, "tl": 400.0, "ca": 500.0, "cl": 300.0, "eqp": 600.0, "bvps": 60.0, "gm": 22.5, "om": 7.5,
          "nm": 5.0, "rev_yoy": 12.3, "dl": "2026-01-01", "eps_yoy": 10.0, "dr": 40.0, "cr": 166.7, "roe4": 13.3, "eps4": 8.0}
         for i, m in enumerate(("03-31", "06-30", "09-30", "12-31"))]
    return {"ver": 1, "mk": "tw", "code": "9999", "name": "測試", "asof": "2026-10-29", "ind": "半導體業",
            "px": {"c": 200.0, "d": "2026-10-29", "hi52": 250.0, "lo52": 120.0, "ret": {}, "ixret": {}}, "cap": 1234.5,
            "q": q, "y": [{"y": "2025", "rev": 1606.0, "gp": 360.0, "op": 120.0, "nip": 80.0, "eps": 8.0, "ocf": 200.0, "icf": -160.0,
                           "fcf": 40.0, "gm": 22.4, "om": 7.5, "nm": 5.0, "roe": 13.3, "bvps": 60.0, "dps": 4.0, "rev_yoy": 9.1, "eps_yoy": 5.0}],
            "mo": [{"ym": "2026-09", "rev": 150.0, "px": 190.0, "rev_yoy": 36.4}], "ytd": {},
            "val": {"px": 200.0, "method": "pe", "base": 10.0, "f12m": {"eps": 10.0, "src": "cons", "w": 0.1667, "eps_y": 8.0,
                                                                       "eps_y1": 10.4, "y": 2026, "n": 5},
                    "range": {"lo": 15.0, "hi": 30.0, "dflt": 22.0}, "tp_dflt": 220.0, "rating_dflt": "中立",
                    "band": {"rows": [["2026-09", 190.0, 8.0, 60.0]], "pe": {"p25": 15.0, "p50": 20.0, "p75": 25.0, "n": 60, "ser": []},
                             "pb": {"p25": 2.0, "p50": 2.5, "p75": 3.0, "n": 60, "ser": []}},
                    "peer_pe": {"p25": 18.0, "p50": 24.0, "p75": 30.0, "n": 6}, "bvps": 60.0},
            "cons": {"src": "FactSet（鉅亨網）", "n": 5, "eps": {"2026": {"med": 8.0}, "2027": {"med": 10.4}},
                     "tp": {"v": 250.0, "n": 5}, "ev": []},
            "peers": [{"c": "1111", "n": "甲"}, {"c": "2222", "n": "乙"}], "peers_auto": ["1111", "2222"],
            "peer_me": {"c": "9999", "n": "測試"}, "peer_med": {}, "peer_how": "產業鏈", "chain": [], "pick": {},
            "chips": {}, "chip_sum": {}, "etf": {}, "src_d": {}}


LINKS = "\n".join(f"- [公司法說會簡報 {i}](https://example.com/{i})（2026-10-0{i}）" for i in range(1, 9))


def _md(**kw):
    fm = {"code": '"9999"', "name": "測試", "mk": "tw", "made": "2026-10-30", "asof": "2026-10-29", "title": "測試論點",
          "rating": "買進", "tp": 240, "method": "pe", "mult": 24, "mult_why": "成長比過去五年快，用同業中位數與本公司上緣之間",
          "peers": '["1111", "2222"]', "ind": "tw-L000"}
    fm.update(kw)
    head = "---\n" + "\n".join(f"{k}: {v}" for k, v in fm.items()) + "\n---\n"
    para = "營收 400 億元，毛利率 22.5%，EPS 2.00 元。" * 40
    th = "\n".join(f"### 論點{i}\n{para}" for i in range(3))
    body = (f"## 重點\n■ **一。** 毛利率 22.5%。\n■ **二。** 年增 12.3%。\n■ **三。** 本益比 24 倍。\n## 投資論點\n{th}\n"
            "## 風險\n" + "\n".join(f"- **風險{i}**：影響毛利率；觀察：月營收" for i in range(4)) +
            f"\n## 公司概況\n{para}\n## 產業與競爭\n{para}\n## 財務分析\n{para}\n## 同業比較\n文字\n## 估值\n目標價 240 元，上檔空間 20%。\n"
            "## 催化劑與籌碼\n- 2026-11-10：10 月營收\n- 2026-11-14：第三季財報\n- 2026-12-10：11 月營收\n"
            f"## 為什麼被選上\n文字\n## 資料來源\n{LINKS}\n")
    return head + body


def test_spec_rating_and_tp_recomputed():
    v = R.valuation(_pack(), {"mult": 24})
    assert v["tp"] == S.round_tp(10.0 * 24) == 240 and v["rating"] == "買進" and v["up"] == 20.0
    assert v["vs_cons"] == -4.0 and v["tp_pe"] == 24.0
    assert v["scen"] == {"bear": S.round_tp(10 * 0.85 * 15), "base": 240, "bull": S.round_tp(10 * 1.15 * 30)}


def test_clean_report_passes():
    assert R.check(_md(), _pack()) == []


def test_checker_catches_each_problem():
    pk = _pack()
    errs = R.check(_md(rating="中立"), pk)
    assert any("評等要照門檻" in e for e in errs)
    assert any("不在可用範圍" in e for e in R.check(_md(mult=40, tp=400, rating="買進"), pk))
    assert any("目標價要等於" in e for e in R.check(_md(tp=250), pk))
    assert any("mult_why" in e for e in R.check(_md(mult_why='""'), pk))
    assert any("同業要和資料包一致" in e for e in R.check(_md(peers='["1111"]'), pk))
    bad = _md().replace("文字\n## 估值", "營收年增 77.7%，穩賺。\n## 估值")
    errs = R.check(bad, pk)
    assert any("77.7%" in e for e in errs) and any("禁用詞" in e for e in errs)
    assert any("填充語" in e for e in R.check(_md().replace("## 同業比較\n文字", "## 同業比較\n值得注意的是"), pk))
    assert any("檔名" in e for e in R.check(_md().replace("## 同業比較\n文字", "## 同業比較\n依資料包"), pk))
    old = _md().replace("2026-11-10：", "2026-10-10：")
    assert any("早於報告日" in e for e in R.check(old, pk))


def test_numbers_with_links_and_percentage_points_pass():
    pk = _pack()
    ok = _md().replace("## 同業比較\n文字", "## 同業比較\n市占 31.2%（[來源](https://example.com/x)）。毛利率比營益率高 15 個百分點。")
    assert R.check(ok, pk) == []
    assert R.check(_md().replace("## 同業比較\n文字", "## 同業比較\n市值約 1,200 億元。"), pk) == []   # 約＝3% 內
    assert R.check(_md().replace("## 同業比較\n文字", "## 同業比較\n本益比不超過 80 倍才用本益比法。"), pk) == []   # 規則門檻


def test_page_has_rating_box_figures_and_disclaimer():
    html = P.render(_md(), _pack(), {"live": {"px": 210.0, "d": "2026-10-30"}})
    assert 'class="rbox"' in html and "買進" in html and "240 元" in html
    assert "最新收盤 210" in html and P.DISCLAIMER in html
    assert html.count('<base href="../">') == 1
    assert "#thesis" in html and 'href="rp/tw-9999.html#thesis"' in html          # base 底下的錨點要帶頁面路徑


def test_site_build_history_and_industry(tmp_path):
    src, out = tmp_path / "eq", tmp_path / "rp"
    for made, mult, tp in (("2026-07-30", 20, 200), ("2026-10-30", 24, 240)):
        d = src / "tw" / "9999"
        d.mkdir(parents=True, exist_ok=True)
        pk = _pack()
        (d / f"{made}.facts.json").write_text(json.dumps(pk, ensure_ascii=False), encoding="utf-8")
        (d / f"{made}.md").write_text(_md(made=made, mult=mult, tp=tp, rating=S.rating(tp, 200.0)), encoding="utf-8")
    r = eqsite.build(out, src)
    assert [x["code"] for x in r["companies"]] == ["9999"] and r["companies"][0]["tp"] == 240
    html = (out / "tw-9999.html").read_text(encoding="utf-8")
    assert "2026-07-30" in html and "評等歷史" in html
    (out / "tw-0000.html").write_text("old", encoding="utf-8")
    eqsite.build(out, src)
    assert not (out / "tw-0000.html").exists()                                     # 沒有報告的舊頁拿掉
