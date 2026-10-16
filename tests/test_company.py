"""公司分析（docs/lab_company_plan.md 第 3.3、3.4、5 節）：每檔資料檔、全市場小表、頁面接線。
使用者 2026-10-16：「點進去公司後可以跑公司的分析（可以不用先跑好這樣太浪費用量）」——
所以伺服器端只放原始數字，比率與圖在瀏覽器打開那一檔才算。"""
import json
import re
from pathlib import Path

from arm.lab import company, copage, page

ROOT = Path(__file__).resolve().parents[1]


def test_co_doc_units_rounding_and_trim():
    qs = {"2026-06-30": {"rev": 89239090.0, "gp": 7535246.0, "eps": 1.6812, "bvps": 90.214, "ta": 780961318.0},
          "2026-03-31": {"eps": 0.51}}
    doc = company.co_doc("1301", "tw", "台塑", "塑膠工業", qs, {"2026-09": 15020000.0},
                         {"2026-09": (81.7, 6365740800)}, [["2026-07-20", 0.5, "息"]], {"2025": -1.576})
    assert doc["qk"] == list(company.QK)
    row = dict(zip(["q"] + doc["qk"], doc["q"][-1]))
    assert row["rev"] == 89239.1 and row["gp"] == 7535.2           # 仟元 → 百萬元一位小數
    assert row["eps"] == 1.68 and row["bvps"] == 90.21               # 每股數字兩位
    assert doc["q"][0] == ["2026-03-31", None, None, None, None, None, None, None, 0.51]   # 尾端空值省略
    assert doc["mo"] == [["2026-09", 15020.0, 81.7, 6365741]]       # 月營收百萬、股數千股
    assert doc["ye"] == {"2025": -1.58} and doc["asof"] == {"q": "2026-06-30", "mo": "2026-09"}


def test_build_co_writes_only_changed_and_removes_delisted(monkeypatch, tmp_path):
    from arm import stockmeta
    from arm.lab import bt3d, v3data
    from arm.lab import packtest as PT
    lst = {"1301": "tw", "6488": "tp"}
    monkeypatch.setattr(company, "listed_now", lambda: dict(lst))
    monkeypatch.setattr(v3data, "load_fs", lambda: {"1301": {"2026-06-30": {"rev": 1000.0, "eps": 1.0}}})
    monkeypatch.setattr(bt3d, "mops_quarterly", lambda: {"6488": {"2026-06-30": 3.2}})
    monkeypatch.setattr(PT, "load_rev", lambda: {"1301": {"2026-09": 5000.0}})
    monkeypatch.setattr(company, "month_px", lambda: {"1301": {"2026-09": (81.7, 1000000)}})
    monkeypatch.setattr(company, "dividends", lambda: {})
    monkeypatch.setattr(company, "names", lambda: {"1301": "台塑", "6488": "環球晶"})
    monkeypatch.setattr(company, "fy_eps", lambda: {})
    monkeypatch.setattr(stockmeta, "industry_map", lambda: {"1301": "塑膠工業"})
    (tmp_path / "9999.json").write_text("{}", encoding="utf-8")   # 已下市
    st = company.build_co(tmp_path)
    assert st == {"n": 2, "write": 2}
    assert not (tmp_path / "9999.json").exists()
    assert json.loads((tmp_path / "index.json").read_text("utf-8"))["s"] == [["1301", "台塑", "tw"], ["6488", "環球晶", "tp"]]
    assert json.loads((tmp_path / "6488.json").read_text("utf-8"))["q"] == [["2026-06-30", None, None, None, None, None, None, None, 3.2]]
    assert company.build_co(tmp_path)["write"] == 0                  # 內容沒變不改寫


def test_market_table_columns_cover_page_keys():
    """頁面依 cols 名稱取值；頁面用到的每個欄位都要在小表裡。"""
    keys = set(re.findall(r"\br\.([a-z0-9]+)\b", copage.JS)) - {"ok", "status", "json"}   # 後三個是 fetch 回應
    keys |= {k for k, *_ in re.findall(r"\['([a-z0-9]+)',(-?1),'", copage.JS)}
    assert keys and keys <= set(company.TCOLS), keys - set(company.TCOLS)
    assert len(company.TCOLS) == len(set(company.TCOLS))


def test_workflows_commit_company_files():
    """三支會重建頁面的 workflow 都要帶 co/ 與 x9t.json；各自一行，缺檔不連累其他檔。"""
    for wf in ("daily.yml", "afterhours_refresh.yml", "etf_holdings.yml"):
        t = (ROOT / ".github/workflows" / wf).read_text("utf-8")
        assert "git add -f dashboard/x9t.json 2>/dev/null || true" in t, wf
        assert "git add -f dashboard/co 2>/dev/null || true" in t, wf


def test_page_wires_company_analysis_on_demand():
    """公司分析在個股卡與「查公司」；資料點進去才抓（co/{代號}.json、x9t.json、co/index.json）。"""
    assert "{{SEARCH}}" in page._HTML and 'id="coq"' in copage.SEARCH_HTML
    assert "h+=coSec(c,W,()=>reStock(c));" in page._JS and "coAfterStock(c);" in page._JS
    assert "['co-sum','公司']" in page._JS
    for u in ("co/${encodeURIComponent(c)}.json", "'x9t.json?v='", "'co/index.json?v='"):
        assert u in copage.JS
    ids = re.findall(r"id=(co-[a-z]+)>", copage.JS)
    assert {i for i, _ in re.findall(r"\['(co-[a-z]+)','([^']+)'\]", copage.JS)} <= set(ids) | {"co-sum"}


def test_company_text_has_no_banned_words():
    banned = ("保證", "穩賺", "必賺", "包賺", "必漲", "必跌", "一定會", "建議買賣", "建議買",
              "建議賣", "目標價", "零風險", "無風險", "穩賺不賠")
    text = copage.JS + copage.CSS + copage.SEARCH_HTML
    assert not [w for w in banned if w in text]
