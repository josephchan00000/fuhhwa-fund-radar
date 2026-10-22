"""報酬的穩健數字（arm/lab/robust.py；sigspec 第 4.11 節 VER 17、xstratspec VER 6；docs/lab_practical_plan.md）。"""
import json
import random
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from arm.lab import robust as RB
from arm.lab import sigcat as G
from arm.lab import sigspec as S

ROOT = Path(__file__).resolve().parents[1]


def test_trim_rules_are_locked():
    """排除極端＝去掉最好和最差各 ⌊5% × 次數⌋（至少 1），次數 < 20 各去掉一次；次數 < 3 不算。去掉最好一次＝去掉最大的那一個。"""
    assert (S.TRIM_Q, S.TRIM_N) == (0.05, 20)
    assert RB.trim_mean([1, 2]) is None and RB.trim_mean([3, 1, 2]) == 2.0
    assert [RB.trim_k(n) for n in (3, 19, 20, 39, 40, 59, 60, 100)] == [1, 1, 1, 1, 2, 2, 3, 5]
    assert RB.trim_mean(list(range(1, 20))) == sum(range(2, 19)) / 17          # 19 次：兩邊各去掉 1
    assert RB.trim_mean(list(range(1, 41))) == sum(range(3, 39)) / 36          # 40 次：兩邊各去掉 2
    assert RB.lbo_mean([5]) is None and RB.lbo_mean([9, 1, 2]) == 1.5
    assert RB.trim_mean([None, 1, 2, 3, float("nan")]) == 2.0 and RB.lbo_mean([None, 4, 2]) == 2.0
    big = [0.01] * 19 + [5.0]                                                  # 一次特別好：平均被拉高，排除極端與去掉最好一次都不會
    assert np.mean(big) > 0.25 and abs(RB.trim_mean(big) - 0.01) < 1e-12 and abs(RB.lbo_mean(big) - 0.01) < 1e-12


def test_ret_cell_last_two_fields_use_each_occurrence():
    """ret_cell 第 10、11 格（VER 17）：狀態型用每一段的平均（occ）、沒給就用每一個值；前 9 格不變。"""
    r = np.array([0.10, 0.12, -0.02, 0.30, 0.05])
    a = np.array([-0.01, -0.02, -0.05, 0.0, -0.03])
    w = np.ones(5)
    c = G.ret_cell(r, a, w, 5)
    assert len(c) == 11 and c[9] == RB.trim_mean(r) and c[10] == RB.lbo_mean(r)
    occ = [0.11, 0.04, 0.30]                                                   # 三段的平均
    c2 = G.ret_cell(r, a, w, 3, occ)
    assert c2[0] == 3 and c2[1:9] == c[1:9] and c2[9] == RB.trim_mean(occ) and c2[10] == RB.lbo_mean(occ)


@pytest.mark.skipif(shutil.which("node") is None, reason="沒有 node")
def test_page_js_trim_matches_python():
    """個股策略的結論與逐筆交易那一句在瀏覽器算（page.py 的 trimOf／lboOf），要和 robust.py 同一套。"""
    src = (ROOT / "arm" / "lab" / "page.py").read_text(encoding="utf-8")
    fns = [re.search(r"^function " + n + r"\(xs\)\{.*?\}$", src, re.M).group(0) for n in ("avgOf", "trimOf", "lboOf")]
    rng = random.Random(20261022)
    cases = [[round(rng.gauss(0.5, 5), 4) for _ in range(n)] for n in (1, 2, 3, 7, 19, 20, 21, 39, 40, 41, 77, 250)]
    prog = "\n".join(fns) + f"\nconst C = {json.dumps(cases)};\nconsole.log(JSON.stringify(C.map(x => [trimOf(x), lboOf(x)])));"
    r = subprocess.run(["node", "-"], input=prog, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    for x, (t, lb) in zip(cases, got):
        et, el = RB.trim_mean(x), RB.lbo_mean(x)
        assert (t is None) == (et is None) and (t is None or abs(t - et) < 1e-9), (len(x), t, et)
        assert (lb is None) == (el is None) and (lb is None or abs(lb - el) < 1e-9), (len(x), lb, el)
