"""個股報告格式、估值重算、檢查、頁面（arm/lab/eqreport.py、eqpage.py、eqsite.py）。"""
import json
from pathlib import Path

from arm.lab import eqpage as P
from arm.lab import eqreport as R
from arm.lab import eqsite
from arm.lab import eqspec as S

ROOT = Path(__file__).resolve().parents[1]


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


def test_markdown_links_escape_once():
    h = P.md("見[來源](https://example.com/a?x=1&y=2)。<script>")
    assert 'href="https://example.com/a?x=1&amp;y=2"' in h and "&amp;amp;" not in h and "<script>" not in h


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


def _site(tmp_path):
    src = tmp_path / "eq"
    d = src / "tw" / "9999"
    d.mkdir(parents=True)
    (d / "2026-10-30.facts.json").write_text(json.dumps(_pack(), ensure_ascii=False), encoding="utf-8")
    (d / "2026-10-30.md").write_text(_md(made="2026-10-30"), encoding="utf-8")
    i = src / "ind" / "tw-L000"
    i.mkdir(parents=True)
    (i / "2026-10-30.facts.json").write_text(json.dumps({"kind": "ind", "key": "tw-L000", "name": "印刷電路板", "n_members": 77}), encoding="utf-8")
    (i / "2026-10-30.md").write_text("---\nkey: tw-L000\n---\n## 重點\n", encoding="utf-8")
    return src


def test_links_and_research_list(tmp_path):
    """卡片上的一行只帶報告日與評等（不寫目標價）；研究紀錄頁的清單帶目標價、最新收盤、產業報告連結（content-rules 第三個例外）。"""
    import inspect
    src = _site(tmp_path)
    assert eqsite.links(src) == {"tw:9999": ["2026-10-30", "買進"]}
    h = eqsite.research_body(src)
    assert 'href="rp/tw-9999.html"' in h and "目標價" in h and 'href="rp/ind-tw-L000.html">印刷電路板</a>' in h
    assert "台灣上市櫃成員 77 家" in h
    assert eqsite.research_body(tmp_path / "none") == '<p class="rnote">還沒有報告。</p>'
    assert "目標價" not in inspect.getsource(eqsite.links).split('"""', 2)[2]          # 函式本體不寫目標價


def test_cards_research_page_and_build_are_wired():
    from arm.lab import copage, research_page, uscardpage
    from arm.lab import page as lab_page
    J = lab_page._JS
    fn = J[J.index("function eqRepLine("):J.index("function renderStock(")]
    assert "目標價" not in fn and 'href="rp/${' in fn                                    # 卡片只寫「個股報告」＋日期＋評等
    assert "h+=eqRepLine('tw:'+c)+stCardSec(c);" in J
    assert "eqRepLine('tw:'+c)+stCardSec(c)+coSec(" in copage.JS
    assert "eqRepLine('us:'+c)+`<section" in uscardpage.JS
    assert 'data["eq"] = eqsite.links()' in (ROOT / "arm" / "lab" / "page.py").read_text(encoding="utf-8")
    assert [g[0] for g in research_page.GROUPS].index("eq") == 1
    gen = (ROOT / "scripts" / "gen_fund_dashboard.py").read_text(encoding="utf-8")
    assert gen.index("lab_page.finish()") < gen.index("eqsite.build()") < gen.index("research_page.build()")
    for wf in ("daily.yml", "afterhours_refresh.yml", "etf_holdings.yml"):
        t = (ROOT / ".github" / "workflows" / wf).read_text(encoding="utf-8")
        assert t.count("git add -f dashboard/rp 2>/dev/null || true") == 2, wf
    assert (ROOT / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8").count("git add -f reports/eq 2>/dev/null || true") == 2


def _channel() -> str:
    """daily.yml 併檔段裡個股報告那一段（if [ -f scripts/check_eq.py ] … 對應的 fi）。"""
    import textwrap
    lines = (ROOT / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8").splitlines()
    s = next(k for k, ln in enumerate(lines) if ln.strip() == "if [ -f scripts/check_eq.py ]; then")
    ind = lines[s][:len(lines[s]) - len(lines[s].lstrip())]
    e = next(k for k in range(s + 1, len(lines)) if lines[k] == ind + "fi")
    return textwrap.dedent("\n".join(lines[s:e + 1]))


def test_daily_channel_merges_only_new_checked_reports(tmp_path):
    """併檔通道：只收 main 沒有的報告、要有資料包、檔名合格、main 的檢查要過；同一天的舊檔不覆蓋。"""
    import subprocess
    r = tmp_path / "repo"
    r.mkdir()

    def sh(cmd, **kw):
        return subprocess.run(cmd, cwd=r, shell=True, check=True, capture_output=True, text=True, **kw)

    def put(path, text):
        p = r / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    sh("git init -q -b main && git config user.email t@example.com && git config user.name t")
    put("scripts/check_eq.py", "import sys\nsys.exit(0 if 'OK' in open(sys.argv[1]).read() else 1)\n")
    put("reports/eq/tw/1111/2026-01-01.md", "OK old")
    put("reports/eq/tw/1111/2026-01-01.facts.json", "{}")
    sh("git add -A && git commit -qm main && git checkout -qb feat")
    put("reports/eq/tw/1111/2026-01-01.md", "OK changed")                       # 舊檔：不覆蓋
    for code, text in (("2222", "OK"), ("3333", "BAD"), ("4444", "OK")):
        put(f"reports/eq/tw/{code}/2026-02-01.md", text)
        if code != "4444":                                                     # 4444 沒有資料包
            put(f"reports/eq/tw/{code}/2026-02-01.facts.json", "{}")
    put("reports/eq/tw/5555/notes.md", "OK")                                   # 檔名不是日期：不理
    put("reports/eq/tw/5555/notes.facts.json", "{}")
    put("reports/eq/ind/tw-L000/2026-02-01.md", "OK")
    put("reports/eq/ind/tw-L000/2026-02-01.facts.json", "{}")
    sh("git add -A && git commit -qm feat && git checkout -q main")
    out = sh(_channel(), env={"REF": "feat", "PATH": "/usr/bin:/bin:/usr/local/bin"}, executable="/bin/bash").stdout
    eqd = r / "reports" / "eq"
    assert (eqd / "tw/1111/2026-01-01.md").read_text(encoding="utf-8") == "OK old"
    assert (eqd / "tw/2222/2026-02-01.md").exists() and (eqd / "tw/2222/2026-02-01.facts.json").exists()
    assert (eqd / "ind/tw-L000/2026-02-01.md").exists()
    assert not (eqd / "tw/3333").exists() or not any((eqd / "tw/3333").iterdir())
    assert not (eqd / "tw/4444").exists() and not (eqd / "tw/5555").exists()
    assert "檢查沒過" in out and "沒有資料包" in out


def test_checker_runs_without_third_party_packages():
    """併檔段在 setup-python 之前跑（runner 自帶的 python3）：檢查程式只能用標準庫。"""
    import subprocess
    import sys
    code = ("import sys; sys.path.insert(0, %r); import arm.lab.eqreport, arm.lab.eqfacts; "
            "bad=[m for m in ('numpy','pandas','yaml','requests') if m in sys.modules]; print(bad); sys.exit(1 if bad else 0)") % str(ROOT)
    subprocess.run([sys.executable, "-I", "-c", code], check=True)


def test_us_page_uses_us_units_sources_and_sections():
    """美股報告頁：美元、SEC 與 Yahoo 的來源、財報和法人預估分兩列、分析師與做空段；不出現台股的張、加權指數、月營收。"""
    pk = _pack()
    for q in pk["q"]:
        q.update(ocf=None, icf=None, fcf=None, sh=50.0, ni4=8.0)
    pk.update(mk="us", code="ME", name="Test Inc", fy_end=12, mo=[], ind="Application Software", sector="Information Technology",
              index="500", peer_n=8, shares=50.0,
              y=[dict(pk["y"][0], ocf=None, icf=None, fcf=None)],
              ser={"d": ["2026-10-28", "2026-10-29"], "c": [199.0, 200.0], "ix": [7700.0, 7720.0], "ix_name": "S&P 500"},
              us_chips={"rc": [1, 5, 10, 1, 0], "rm": 2.4, "sh": [0.05, 3.2, 1e6, 9e5, "2026-10-15"], "mh": [0.02, 0.9, 800], "ns": ["6m", 3, 1, 5, 2, -1000, -0.01]},
              pick={"list": "美股強勢品質股", "d": "2026-10-23", "rank": 3, "n": 50, "rs": 97, "d52h": -1.0, "om": 30, "roe": 40, "cap": 120,
                    "rule": {"rs": 80, "d52h": -25, "om": 10, "roe": 15, "cap": 20}, "buy": True, "buyd": "2026-10-26", "slots": 8, "exit_ma": 50})
    pk["cons"].update(src="Yahoo Finance", stat="平均", tp={"v": 250.0, "med": 245.0, "hi": 300.0, "lo": 200.0, "n": 17},
                      ev=[{"d": "2026-10-27", "firm": "X", "from": "Hold", "to": "Buy", "tp_from": 200.0, "tp_to": 260.0}])
    html = P.render(_md(code='"ME"', mk="us"), pk, {})
    assert "240 美元" in html and "S&amp;P 500" in html and "SEC 財報" in html
    assert "EPS（財報，美元）" in html and "EPS（法人預估，美元）" in html            # 財報和預估分兩列
    assert "分析師評等與目標價" in html and "做空股數占流通股" in html and "強度 97" in html
    assert "淨值比 × 每股淨值" not in html and "淨值比區間" not in html          # 本益比法只畫本益比那把尺
    assert "加權指數" not in html and "張" not in html.split("<body>", 1)[1].split("免責")[0] and "每月營收" not in html


def test_us_industry_sections():
    ip = {"kind": "ind", "mk": "us", "key": "us-x", "name": "X", "members": [], "n_members": 0}
    md = "---\nkey: us-x\nname: X\nmk: us\nmade: 2026-10-30\nasof: 2026-10-30\ntitle: t\n---\n" + "".join(
        f"## {s}\n" + ("■ 一\n■ 二\n■ 三\n" if s == "重點" else "文字\n") for s in R.IND_SECTIONS_US)
    errs = R.check_ind(md, ip)
    assert not any("段落缺" in e or "不認得" in e for e in errs)
    assert any("台灣成員營收與估值" in e for e in R.check_ind(md.replace("美股成員與估值", "台灣成員營收與估值"), ip))


def test_us_industry_page_renders_members_without_tw_fields():
    from arm.lab import eqpage as P
    ip = {"kind": "ind", "mk": "us", "key": "us-x", "name": "X", "n_members": 2, "asof": "2026-10-30",
          "pe": {"p25": 20.0, "p50": 25.0, "p75": 30.0, "n": 2}, "fpe": {},
          "members": [{"c": "ADP", "n": "Automatic Data Processing", "ix": "500", "cap": 1128.8, "cap_src": "fwd", "fpe": 22.4,
                       "pe": None, "rq": None, "om": None, "roe": None, "r1y": None},
                      {"c": "PAYX", "n": "Paychex", "ix": "500", "cap": 422.9, "cap_src": "fin", "fpe": 17.7, "pe": 23.4,
                       "rq": 5.9, "om": 39.2, "roe": 47.1, "r1y": -5.0}]}
    md = "---\nkey: us-x\nname: X\nmk: us\nmade: 2026-10-30\nasof: 2026-10-30\ntitle: t\n---\n" + "".join(
        f"## {s}\n文字\n" for s in R.IND_SECTIONS_US)
    html = P.ind_render(md, ip, {"cos": []})
    assert "S&amp;P 1500 的同細產業成員" in html and "&amp;amp;" not in html and "1,129＊" in html and "台灣成員" not in html


def test_page_escapes_pack_strings_and_blocks_non_http_links():
    """資料包經 daily.yml 併檔通道進 main，檢查只看 .md；頁面要自己防：日期欄跳脫、連結只放行 http(s)（2026-10-30 資安檢查）。"""
    pk = _pack()
    bad = "<img src=x onerror=alert(1)>"
    pk["cons"]["ev"] = [{"d": bad, "k": "EPS", "y": 2026, "from": 1.0, "to": 2.0, "url": "javascript:alert(1)"},
                        {"d": "2026-10-01", "k": "TP", "from": 10.0, "to": 12.0, "url": "https://example.com/a"}]
    html = P.render(_md(), pk, {})
    assert bad not in html and "&lt;img src=x onerror=alert(1)&gt;" in html
    assert "javascript:" not in html and 'href="https://example.com/a"' in html
    assert P._safe_url("data:text/html,x") == "" and P._safe_url(" HTTPS://a.b ") == "HTTPS://a.b"
