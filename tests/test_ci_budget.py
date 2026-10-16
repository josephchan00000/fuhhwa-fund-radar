"""GitHub Actions 額度（私有 repo 免費 2,000 分／月）與建頁效率的防呆（2026-10-16）。

使用者問「會不會超過免費用量」時實測：10 月前半就用了約 1,670 分——開發分支推送觸發整輪 daily.yml、
抓取程式卡住等到 job 逾時（每次 20～30 分）、建頁每次白跑一遍資料包回測。這裡守住修法不退回。"""
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_daily_push_without_new_content_skips_whole_run():
    """推送的分支沒有 main 還沒有的今日新聞或通道檔 → 併檔步驟之後的每一步都跳過。"""
    wf = yaml.safe_load((ROOT / ".github/workflows/daily.yml").read_text("utf-8"))
    steps = wf["jobs"]["routine"]["steps"]
    k = next(i for i, s in enumerate(steps) if s.get("id") == "merge")
    run = steps[k]["run"]
    assert 'echo "skip=true" >> "$GITHUB_OUTPUT"' in run
    assert '[ "$GITHUB_EVENT_NAME" = "push" ]' in run              # 只有推送觸發才跳過；cron／手動照跑
    paths = re.search(r"git status --porcelain -- ([^)]*)\)", run).group(1).split()
    trig = wf[True]["push"]["paths"] if True in wf else wf["on"]["push"]["paths"]
    assert {p.rstrip("/*") for p in trig} == {p.rstrip("/*") for p in paths}   # 比對範圍＝觸發範圍
    for s in steps[k + 1:]:
        assert s.get("if") == "steps.merge.outputs.skip != 'true'", s.get("name") or s.get("uses")


def test_parallel_fetches_have_time_limits():
    """卡住的抓取不可再讓整輪等到 job 逾時（10/13、10/15 各卡滿 30 分鐘）。"""
    sh = (ROOT / "scripts/daily_fund.sh").read_text("utf-8")
    for f in ("fetch_holdings.py", "fetch_fund_news.py", "fetch_etf_watch.py", "fetch_macro_chips.py", "fetch_lab.py"):
        line = next(l for l in sh.splitlines() if f in l and "python3" in l)
        assert re.search(r"\btimeout\b", line), line
    ah = (ROOT / ".github/workflows/afterhours_refresh.yml").read_text("utf-8")
    for f in ("fetch_macro_chips.py", "fetch_etf_watch.py", "fetch_holdings.py", "fetch_lab.py"):
        line = next(l for l in ah.splitlines() if f in l and "python3" in l)
        assert re.search(r"\btimeout\b", line), line


def test_page_build_does_not_rerun_pack_backtests():
    """資料包 P1–P7 回測（約 17 秒）頁面用不到，不在每次建頁重跑。"""
    src = (ROOT / "arm/lab/analyze.py").read_text("utf-8")
    assert "packtest.run(" not in src.replace("packtest.summary(packtest.run(Data(long=True)), reg)", "")


def test_store_memo_reuses_until_shards_change(tmp_path, monkeypatch):
    from arm.lab import store
    monkeypatch.setattr(store, "LAB", tmp_path)
    store.write("k1", "2026-01-01", {"a": 1})
    calls = []

    @store.memo("k1")
    def load():
        calls.append(1)
        return {d: doc for d, doc in store.load("k1")}

    a = load()
    assert load() is a and len(calls) == 1                       # 分片沒變：同一個物件、不重讀
    store.write("k1", "2026-01-02", {"a": 2})
    b = load()
    assert len(calls) == 2 and set(b) == {"2026-01-01", "2026-01-02"}   # 新增分片：重讀
    store.write("k1", "2026-01-02", {"a": 3, "b": 4})
    assert load()["2026-01-02"] == {"a": 3, "b": 4} and len(calls) == 3  # 改寫分片：重讀


_DET = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
from arm.lab import hdpredict, indexes
cons = {f"{1000 + i}" for i in range(52)}
ranked = [(f"{2000 + i}", 0, 0) for i in range(30)] + [(c, 0, 0) for c in sorted(cons)[:20]]
a = indexes.tw50_select(ranked, cons)
b = hdpredict.buffer_select([f"{2000 + i}" for i in range(10)], set(f"{3000 + i}" for i in range(12)), 12, 5, 8)
print(json.dumps([a, b]))
"""


def test_set_based_selection_is_deterministic_across_hash_seeds():
    """成分股是集合：同名次（例：不合格、沒名次）時的順序與取捨不可隨每次執行的雜湊種子改變——
    否則同樣的資料每次建頁結果都不同，每班 CI 都多一筆 commit 與部署（2026-10-16 實測找到 3 處）。"""
    outs = set()
    for seed in ("1", "2", "3"):
        r = subprocess.run([sys.executable, "-c", _DET, str(ROOT)], capture_output=True, text=True,
                           env={**os.environ, "PYTHONHASHSEED": seed}, check=True)
        outs.add(r.stdout)
    assert len(outs) == 1, outs
