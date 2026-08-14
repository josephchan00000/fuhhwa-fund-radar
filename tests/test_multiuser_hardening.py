# 多人化 Phase 1（2026-08-14）硬化項目的守門測試：
# 快取設定、對時哨兵解析、煙測 lite 斷言、頁齡提示 JS——任何一項被改壞都在發佈前紅。
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.smoke_dashboard import lite_check  # noqa: E402


def _load(p):
    return json.loads((ROOT / p).read_text(encoding="utf-8"))


def test_兩支_vercel_json_皆為_no_cache():
    # no-store→no-cache（Phase 1-④）：兩支必須一致，且不得回退 no-store（省流歸零）
    # 或改成長 max-age（會回到「線上停舊版」惡夢——CLAUDE.md 明文不建議）。
    for p in ("vercel.json", "dashboard/vercel.json"):
        vals = [kv["value"] for h in _load(p)["headers"] for kv in h["headers"] if kv["key"] == "Cache-Control"]
        assert vals, f"{p} 缺 Cache-Control"
        for v in vals:
            assert "no-cache" in v and "no-store" not in v and "max-age=3" not in v, f"{p}: {v}"


def test_對時哨兵可解析入庫的儀表板時戳():
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_live_deploy.py"), "--parse-only", str(ROOT / "dashboard/index.html")],
        capture_output=True, text=True,
    )
    assert out.returncode == 0, out.stdout + out.stderr
    import re
    assert re.match(r"^\d{4}/\d{2}/\d{2} \d{2}:\d{2}$", out.stdout.strip()), out.stdout


def test_煙測_lite_對入庫儀表板全綠():
    probs = lite_check(str(ROOT / "dashboard/index.html"))
    assert probs == [], probs


def test_煙測_lite_抓得到截斷檔(tmp_path):
    bad = tmp_path / "broken.html"
    bad.write_text('<div id="overview"></div>', encoding="utf-8")
    probs = lite_check(str(bad))
    assert any("截斷" in p or "bytes" in p for p in probs)


def test_三支_workflow_都掛了哨兵與煙測():
    wf = lambda n: (ROOT / ".github/workflows" / n).read_text(encoding="utf-8")
    daily, after, etfh = wf("daily.yml"), wf("afterhours_refresh.yml"), wf("etf_holdings.yml")
    for w in (daily, after, etfh):
        assert "check_live_deploy.py" in w, "對時哨兵步驟被移除"
    assert "smoke_dashboard.py dashboard/index.html" in daily and "SMOKE_ENFORCE" in daily
    for w in (after, etfh):
        assert "smoke_dashboard.py --lite" in w, "輕量結構檢查被移除"


def test_頁齡提示_JS_在渲染端():
    src = (ROOT / "arm/fund_dashboard.py").read_text(encoding="utf-8")
    assert "本頁已開啟超過" in src and "18e5" in src  # 30 分 tick 的長開分頁提示（Phase 1-⑤）
