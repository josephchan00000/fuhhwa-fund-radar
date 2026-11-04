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
    # 或改成長 max-age（會回到「線上停舊版」惡夢——wiki/ops/deploy.md 明文不建議）。
    for p in ("vercel.json", "dashboard/vercel.json"):
        vals = [kv["value"] for h in _load(p)["headers"] for kv in h["headers"] if kv["key"] == "Cache-Control"]
        assert vals, f"{p} 缺 Cache-Control"
        for v in vals:
            assert "no-cache" in v and "no-store" not in v and "max-age=3" not in v, f"{p}: {v}"


def test_兩支_vercel_json_停掉工作分支預覽部署_正式站照常():
    # 2026-10-15：工作分支每推一次就多一次預覽部署，撞到 Vercel 免費方案每日上限、正式站停更一天。
    # 使用者同意後停掉 claude/** 的自動部署；main（正式站）不得被關掉，否則只剩 Deploy Hook。
    for p in ("vercel.json", "dashboard/vercel.json"):
        dep = _load(p).get("git", {}).get("deploymentEnabled")
        assert isinstance(dep, dict), f"{p} 缺 git.deploymentEnabled"
        assert dep.get("claude/**") is False, f"{p}: {dep}"
        assert dep.get("main", True) is True and all(v is False for v in dep.values()), f"{p}: {dep}"


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


def test_兩支_vercel_json_網頁沒變就不部署():
    # 2026-11-04：Vercel 部署儲存超過免費 10 GB（每次部署存一份 dashboard/，約 55 MB）。ignoreCommand 只在
    # 「dashboard/ 跟上次成功部署的那筆一模一樣」時略過（exit 0）；拿不到上次那筆、或比對失敗，一律照常部署（exit 1），
    # 不可硬到什麼都沒更新。Root Directory 是 dashboard/，所以兩個工作目錄都要對。
    import os
    import shutil
    import tempfile

    cmds = {p: _load(p).get("ignoreCommand") for p in ("vercel.json", "dashboard/vercel.json")}
    cmd = cmds["dashboard/vercel.json"]
    assert cmd and cmds["vercel.json"] == cmd, cmds
    assert len(cmd) <= 256, len(cmd)                       # Vercel 的長度上限
    if not shutil.which("git") or not shutil.which("sh"):
        return
    with tempfile.TemporaryDirectory() as td:
        def git(*a):
            return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *a], cwd=td,
                                  capture_output=True, text=True, check=True).stdout.strip()

        def put(rel, text):
            f = pathlib.Path(td, rel)
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(text, encoding="utf-8")
            git("add", "-A")
            git("commit", "-q", "-m", rel)
            return git("rev-parse", "HEAD")

        git("init", "-q")
        c1 = put("dashboard/index.html", "v1")
        c2 = put("data/x.json", "1")                          # 只動 data/：網頁沒變
        c3 = put("dashboard/index.html", "v2")                # 網頁變了
        c4 = put("dashboard/vercel.json", "{}")               # 設定檔在 dashboard/ 裡，也算網頁變了

        def run(head, prev, sub):
            git("checkout", "-q", head)
            env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
            if prev is not None:
                env["VERCEL_GIT_PREVIOUS_SHA"] = prev
            return subprocess.run(["sh", "-c", cmd], cwd=pathlib.Path(td, sub), env=env,
                                  capture_output=True, text=True).returncode

        for sub in ("dashboard", "."):
            assert run(c2, c1, sub) == 0, sub                 # 只動 data/ → 略過
            assert run(c3, c3, sub) == 0, sub                 # 同一筆又被 Deploy Hook 打一次 → 略過
            assert run(c3, c1, sub) == 1, sub                 # 網頁變了 → 部署
            assert run(c3, c2, sub) == 1, sub
            assert run(c4, c3, sub) == 1, sub                 # vercel.json 變了 → 部署
            assert run(c3, None, sub) == 1, sub               # 沒有上次的紀錄 → 部署
            assert run(c3, "", sub) == 1, sub
            assert run(c3, "0" * 40, sub) == 1, sub           # 上次那筆不在淺層 clone 裡 → 部署
            assert run(c3, "not-a-sha", sub) == 1, sub
