"""美股景氣頁（arm/lab/heatpage_us.py；docs/lab_heat_us_plan.md 第 3、7 節）：一頁切換四個指數、說法換成美股、頂欄與 workflow。"""
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
    return pages, PU.render(pages)


def test_market_labels_per_index():
    assert PU.market("spx")["MK"]["cmp"] == "對照 S&P 500" and PU.market("ixic")["MK"]["cmp"] == "對照那斯達克"
    assert PU.market("ndx")["MK"]["cmp"] == "對照那斯達克 100" and PU.market("sox")["MK"]["data"] == "x9muh-sox.json"
    assert PU.market("spx")["MK"]["tab"] == "us" and PU.market("spx")["MK"]["bull"] == "S&P 500 在 10 個月均線之上"
    assert HP.MK["mkt"] == "台股"                                                  # 換完換回台股頁


def test_one_page_switches_four_indices(page):
    pages, html = page
    assert html.count('<div id="ixc" data-ix="spx">') == 1                       # 預設 S&P 500 直接放在頁面
    assert [m for m in re.findall(r'<template data-ix="(\w+)">', html)] == ["ixic", "ndx", "sox"]
    assert re.findall(r'<button type="button" data-ix="(\w+)">', html) == list(U.INDEX_ORDER)
    metas = re.search(r"window\.HEAT_METAS=(\{.*?\});window\.HEAT_ASOF", html).group(1)
    for k in U.INDEX_ORDER:
        assert f'"data":"x9muh-{k}.json"' in metas
    assert '<a class="on" aria-current="page" href="x9mu.html"><span class="apl">美股景氣</span>' in html
    assert html.index("window.HEAT_METAS") < html.index("window.heatInit = function")   # 切換程式在對照圖程式之前
    for k, P in pages.items():
        assert P["meta"]["dims"][-1]["id"] == "tech" and len(P["meta"]["dims"]) == 4      # 泡沫另放泡沫頁
        assert ("T14" in P["meta"]["items"]) == (k != "spx") and ("F11" in P["meta"]["items"]) == (k == "sox")
    assert S.MARKET == "tw" and HP.MK["mkt"] == "台股"


def test_us_page_has_no_taiwan_wording_or_banned_words(page):
    _, html = page
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.S)        # 看得到的文字（內嵌資料是面板打開才用）
    assert "加權指數" not in text and "台指 VIX" not in text
    import json
    sgd = json.loads(re.search(r'<script type="application/json" id="sgd">(.*?)</script>', html, re.S).group(1).replace("<\\/", "</"))
    assert set(sgd["mk"]) <= {"spx", "ixic", "ndx", "sox", "us"} and "tw" not in sgd["pxn"] and "tw" not in sgd["xs"]["m"]   # 全部指標只放美股
    from arm.lab import appnav
    row = HP.market_row("us")                                                       # 市場列：台股（連到台股頁）＋四個美股指數
    assert appnav.bar("us") in text and row in text
    assert "台股" not in text.replace(appnav.bar("us"), "").replace(row, "")   # 只有頂欄的「台股景氣」（手機短名「台股」）與市場列的「台股」
    for w in BANNED:
        assert w not in html, w


def test_page_script_reinit_is_safe(page):
    _, html = page
    js = HP._JS
    assert "window.__heatAC.abort()" in js and js.count(", SIG);") == 2          # 換指數時拿掉上一次的 document、window 事件
    assert "fetch(M.data || 'x9mh.json'" in js and "if (AC.signal.aborted) return;" in js
    assert "M.dims.slice(0, M.max)" in js                                           # 台股六個面向：預設只選前 5 條


@pytest.mark.skipif(shutil.which("node") is None, reason="沒有 node")
def test_scripts_parse(page, tmp_path):
    _, html = page
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
