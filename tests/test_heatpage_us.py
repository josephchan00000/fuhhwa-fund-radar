"""美股景氣頁（arm/lab/heatpage_us.py；docs/lab_heat_us_plan.md 第 3、7 節）：一頁切換四個指數、說法換成美股、頂欄與 workflow。"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from arm.lab import heatcalc_us as CU
from arm.lab import heatpage as HP
from arm.lab import heatpage_us as PU
from arm.lab import heatspec as S
from arm.lab import heatspec_us as U

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_heatcalc_us import fake_D  # noqa: E402

BANNED = ("保證", "穩賺", "必賺", "包賺", "必漲", "必跌", "一定會", "唯一", "建議買賣", "建議買", "建議賣", "目標價",
          "零風險", "無風險", "穩賺不賠")


@pytest.fixture(scope="module")
def page():
    D = fake_D()
    SH = CU.shared(D)
    pages = {k: PU.index_page(k, CU.build(k, D, SH), {}) for k in U.INDEX_ORDER}
    html, panes = PU.assemble(pages)
    return pages, html, panes


def test_market_labels_per_index():
    assert PU.market("spx")["MK"]["cmp"] == "對照 S&P 500" and PU.market("ixic")["MK"]["cmp"] == "對照那斯達克"
    assert PU.market("ndx")["MK"]["cmp"] == "對照那斯達克 100" and PU.market("sox")["MK"]["data"] == "x9muh-sox.json"
    assert PU.market("spx")["MK"]["tab"] == "us" and PU.market("spx")["MK"]["bull"] == "S&P 500 在 10 個月均線之上"
    assert HP.MK["mkt"] == "台股"                                                  # 換完換回台股頁


def test_one_page_switches_four_indices(page):
    pages, html, panes = page
    assert html.count('<div id="ixc" data-ix="spx">') == 1                       # 預設 S&P 500 直接放在頁面
    assert "<template data-ix=" not in html and 'class="dtpl"' not in html         # 其他指數、細項面板都不放在頁面（x9mup）
    assert list(panes) == [f"x9mup-{k}.json" for k in U.INDEX_ORDER]
    for k in U.INDEX_ORDER:
        d = panes[PU.pane_name(k)]
        assert d["tpl"].startswith('<div class="dtpl" hidden>') and 'id="ot-out"' in d["tpl"]
        assert ("main" in d) == (k != "spx") and ("sg" in d) == (k != "spx")
        if k != "spx":
            assert d["main"].startswith("<main>") and 'class="hviz"' in d["main"] and 'class="dtpl"' not in d["main"]
    assert re.findall(r'<button type="button" data-ix="(\w+)">', html) == list(U.INDEX_ORDER)
    metas = re.search(r"window\.HEAT_METAS=(\{.*?\});</script>", html).group(1)
    for k in U.INDEX_ORDER:
        assert f'"data":"x9muh-{k}.json"' in metas
    assert '<a class="on" aria-current="page" data-k="mkt" href="x9mu.html">市場</a>' in html     # 頂欄「市場」亮
    assert "HEAT_ASOF" not in html and 'id="ix-asof"' not in html                  # 資料日不放頂欄（面向標題有）
    assert html.index("window.HEAT_METAS") < html.index("window.heatInit = function")   # 切換程式在對照圖程式之前
    for k, P in pages.items():
        assert P["meta"]["dims"][-1]["id"] == "tech" and len(P["meta"]["dims"]) == 4      # 泡沫另放泡沫頁
        assert ("T14" in P["meta"]["items"]) == (k != "spx") and ("F11" in P["meta"]["items"]) == (k == "sox")
    assert S.MARKET == "tw" and HP.MK["mkt"] == "台股"


def test_us_page_has_no_taiwan_wording_or_banned_words(page):
    _, html, panes = page
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.S)        # 看得到的文字（內嵌資料是面板打開才用）
    assert "加權指數" not in text and "台指 VIX" not in text
    sgd = json.loads(re.search(r'<script type="application/json" id="sgd">(.*?)</script>', html, re.S).group(1).replace("<\\/", "</"))
    assert set(sgd["mk"]) <= {"spx", "ixic", "ndx", "sox", "us"} and "tw" not in sgd["pxn"] and "tw" not in sgd["xs"]["m"]   # 全部指標只放美股
    from arm.lab import appnav
    row = HP.market_row("us")                                                       # 市場列：台股（連到台股頁）＋四個美股指數
    assert appnav.bar("mkt", cur="x9mu.html") in text and row in text
    assert "台股" not in text.replace(row, "")                                    # 只有市場列的「台股」
    for w in BANNED:
        assert w not in html, w
        assert all(w not in json.dumps(d, ensure_ascii=False) for d in panes.values()), w


def test_page_script_reinit_is_safe(page):
    _, html, _ = page
    js = HP._JS
    assert "window.__heatAC.abort()" in js and js.count(", SIG);") == 2          # 換指數時拿掉上一次的 document、window 事件
    assert "fetch(M.data || 'x9mh.json'" in js and "if (AC.signal.aborted) return;" in js
    assert "M.dims.slice(0, M.max)" in js                                           # 台股六個面向：預設只選前 5 條


@pytest.mark.skipif(shutil.which("node") is None, reason="沒有 node")
def test_scripts_parse(page, tmp_path):
    _, html, _ = page
    for i, src in enumerate(re.findall(r"<script>(.*?)</script>", html, flags=re.S)):
        f = tmp_path / f"s{i}.js"
        f.write_text(src, encoding="utf-8")
        r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr[:500]


def test_workflows_add_us_page_files_and_fetch():
    for wf in ("daily.yml", "afterhours_refresh.yml", "etf_holdings.yml"):
        t = (ROOT / ".github" / "workflows" / wf).read_text(encoding="utf-8")
        assert t.count("git add -f dashboard/x9mu.html 2>/dev/null || true") == 2, wf
        assert t.count("git add -f dashboard/x9muh-*.json 2>/dev/null || true") == 2, wf
        assert t.count("git add -f dashboard/x9mup-*.json 2>/dev/null || true") == 2, wf
    ah = (ROOT / ".github" / "workflows" / "afterhours_refresh.yml").read_text(encoding="utf-8")
    assert "python3 scripts/fetch_heat_us.py" in ah and "numpy xlrd openpyxl" in ah
    assert "python3 scripts/fetch_heat_us.py" in (ROOT / "scripts" / "daily_fund.sh").read_text(encoding="utf-8")
    assert "heatpage_us.build()" in (ROOT / "scripts" / "gen_fund_dashboard.py").read_text(encoding="utf-8")


def test_score_rounding_never_crosses_band():
    """79.6 不寫成 80（五區界線 20／40／60／80）；其他照四捨五入。頁面 JS 的 sc0() 同一套規則。"""
    assert HP.n0(79.6) == "79.6" and HP.n0(79.96) == "79.9" and HP.n0(19.5) == "19.5"
    assert HP.n0(74.8) == "75" and HP.n0(80.0) == "80" and HP.n0(99.6) == "100" and HP.n0(0.2) == "0"
    for x in (19.5, 39.7, 59.9, 79.6, 74.8, 80.4, 12.3):
        assert S.band(float(HP.n0(x))) == S.band(x)
    assert "function sc0(v)" in HP._JS and ": sc0(v));" in HP._JS


def _sgd(rows, inds, on=None, it=None, xm=None):
    return json.dumps({"rows": rows, "inds": inds, "on": on or {}, "it": it or {}, "xs": {"m": xm or {}, "spec": {}}, "mk": {}},
                      ensure_ascii=False, separators=(",", ":"))


def test_split_sgd_moves_rows_and_merge_restores_them():
    """全部指標：頁面只留預設指數＋美股產業的列，其他指數的列放 x9mup；指標對到列的位置兩邊各自重新編號，
    併回去（SWITCH_JS 的 sgAdd：列接在後面、位置往後挪）之後每個指標對到的列和原本一樣。"""
    rows = [["spx:a", "spx"], ["ndx:a", "ndx"], ["us:x", "us"], ["ndx:b", "ndx"], ["spx:b", "spx"], ["sox:a", "sox"]]
    inds = [["spx:A", "spx", "heat", "A", "g", [0, 4], None, "fund", None], ["ndx:A", "ndx", "heat", "A", "g", [1, 3], "F1", "fund", None],
            ["us:X", "us", "ind", "X", None, [2], None, "bub", None], ["sox:A", "sox", "heat", "A", "g", [5], None, "tech", None]]
    on = {"spx:a": {"n": 1}, "ndx:b": {"n": 2}, "us:x": {"n": 3}}
    it = {"spx": {"F1": 1}, "ndx": {"F1": 2}}
    xm = {"spx": {"rsi2": 1}, "ndx": {"rsi2": 2}, "sox": {}}
    page_s, sg = PU.split_sgd(_sgd(rows, inds, on, it, xm), "spx")
    P = json.loads(page_s)
    assert [r[0] for r in P["rows"]] == ["spx:a", "us:x", "spx:b"] and [x[0] for x in P["inds"]] == ["spx:A", "us:X"]
    assert P["on"] == {"spx:a": {"n": 1}, "us:x": {"n": 3}} and P["it"] == {"spx": {"F1": 1}} and P["xs"]["m"] == {"spx": {"rsi2": 1}}
    assert sorted(sg) == ["ndx", "sox"] and [r[0] for r in sg["ndx"]["rows"]] == ["ndx:a", "ndx:b"]
    assert sg["ndx"]["on"] == {"ndx:b": {"n": 2}} and sg["ndx"]["it"] == {"F1": 2} and sg["ndx"]["xsm"] == {"rsi2": 2}

    def merged(P, ix):                                    # 照 SWITCH_JS 的 sgAdd 併回去
        off = len(P["rows"])
        P = dict(P, rows=P["rows"] + sg[ix]["rows"],
                 inds=P["inds"] + [x[:5] + [[i + off for i in x[5]]] + x[6:] for x in sg[ix]["inds"]])
        return {x[0]: [P["rows"][i][0] for i in x[5]] for x in P["inds"]}
    orig = {x[0]: [rows[i][0] for i in x[5]] for x in inds}
    m = merged(P, "ndx")
    assert m == {k: v for k, v in orig.items() if not k.startswith("sox")}
    assert merged(P, "sox")["sox:A"] == ["sox:a"]
    assert "sgAdd(ix, sg)" in PU.SWITCH_JS and "x[5].map(i => i + off)" in PU.SWITCH_JS


def test_split_sgd_keeps_everything_when_indicators_cross_markets():
    rows = [["spx:a", "spx"], ["ndx:a", "ndx"]]
    bad = [["spx:A", "spx", "heat", "A", "g", [0, 1], None, "fund", None]]          # 指標對到別的市場的列：不拆
    s0 = _sgd(rows, bad)
    assert PU.split_sgd(s0, "spx") == (s0, {})
    assert PU.split_sgd("not json", "spx") == ("not json", {})


def test_page_waits_for_deep_linked_index():
    """網址指到別的指數（#ix=ndx）：先不畫預設的指數（省下它的對照圖資料），換好內容才初始化；載不到就照預設的指數畫。"""
    assert "window.__heatWait = 1; show(m[1], false);" in PU.SWITCH_JS
    assert HP._JS.rstrip().endswith("if (!window.__heatWait) window.heatInit();   // 美股頁網址指到別的指數：等 heatpage_us.SWITCH_JS 換好內容再畫")
    from arm.lab import sigpage
    assert "if (!window.__heatWait) window.sgInit();" in sigpage.JS
    sw = PU.SWITCH_JS
    assert sw.index("window.__heatWait = 0;") < sw.index("if (window.heatInit) window.heatInit();")
    assert "say('載入失敗，請重新整理頁面');" in sw and "fetch('x9mup-' + ix + '.json', {cache: 'no-cache'})" in sw
