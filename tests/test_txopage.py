"""選擇權計算機頁 x9op.html（arm/lab/txopage.py；docs/lab_txo_plan.md 第 17 節）與各頁右下角的「選」字入口。"""
import json
from pathlib import Path

from arm.lab import appnav
from arm.lab import txopage as P

DOC = {"ver": 1, "asof": "2026-11-04", "next": "2026-11-05", "close": 42948.91, "atm": 42950, "atm_iv": 0.3488, "em": 943.7,
       "mult": 50, "fee": 25, "tax": 0.001, "slip": 1, "caps": {"O1": 0.02, "O2": 0.03, "O3": 0.05}, "step": 50,
       "exps": [{"code": "202611F1", "date": "2026-11-06", "n": 2, "tomorrow": False,
                 "rows": [[42950, 560, 0.37, 505, 0.33, 41, 25]]}]}


def test_page_embeds_data_and_facts(tmp_path):
    out = tmp_path / "x9op.html"
    assert P.build(out, DOC) is True and P.build(out, DOC) is False
    t = out.read_text(encoding="utf-8")
    blob = t.split('<script type="application/json" id="opd">', 1)[1].split("</script>", 1)[0]
    assert json.loads(blob)["close"] == 42948.91
    assert "42,949" in t and "±944（2.2%）" in t and "11/5" in t
    assert 'class="opq"' not in t                       # 自己這頁不放入口
    assert "不是買賣建議" in t


def test_page_without_data_still_builds(tmp_path):
    out = tmp_path / "x9op.html"
    P.build(out, None) if not P.DATA.exists() else P.build(out, {})
    assert "選擇權計算機" in out.read_text(encoding="utf-8")


def test_other_lab_pages_get_entry():
    page = "<html><head><style>a{}</style></head><body>" + appnav.BACK + "x</body></html>"
    t = appnav.finish(page)
    assert t.count(appnav.OP_ENTRY) == 1 and ".opq{" in t and 'href="x9op.html"' in t


def test_workflows_commit_page():
    root = Path(__file__).resolve().parent.parent
    for f in ("daily.yml", "afterhours_refresh.yml", "txo_data.yml"):
        assert "dashboard/x9op.html" in (root / ".github/workflows" / f).read_text(encoding="utf-8"), f
