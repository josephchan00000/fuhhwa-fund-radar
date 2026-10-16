"""P4.0 診斷：SPEC VCP（固定 3% 轉折）各條件卡掉多少個樣板全過的股票日——只數次數，不看報酬（reports/P4_S01_plan.md 第 9 節 v2 的依據）。"""
import sys, time, collections
from collections import deque
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import numpy as np, pandas as pd
from superstock import features as FT, labpanel as LP, strategies as ST, engine as EN
t0 = time.time()
m, extra = LP.load()
el = FT.eligible(m, extra["cap"])
tr = FT.trend(m, el)
vo = FT.volume(m)
print("loaded", round(time.time()-t0))
sp = FT.VCP
T, N = m.c.shape
cnt = collections.Counter()
first_fail = collections.Counter()
nseg = collections.Counter()
tt = tr["tt_pass"]
for j in range(N):
    if not tt[:, j].any():
        continue
    h, l, c = m.h[:, j], m.l[:, j], m.c[:, j]
    dq = deque(); zz = None
    for t in range(T):
        x = h[t]
        if x == x:
            while dq and h[dq[-1]] < x: dq.pop()
            dq.append(t)
        while dq and dq[0] <= t - sp["win"]: dq.popleft()
        if not dq: continue
        s = dq[0]
        if zz is None or zz.s != s: zz = FT.ZigZag(h, l, s, sp["thr"])
        if not tt[t, j]: continue
        cnt["tt"] += 1
        if t - s < sp["base_min"]:
            first_fail["base<30"] += 1; continue
        zz.advance(t)
        pairs, pv = zz.contractions()
        n = len(pairs); nseg[min(n, 12)] += 1
        ds = [1 - lo / hi for hi, lo, _, _ in pairs]
        fails = []
        if n < 2: fails.append("n<2")
        if n > 6: fails.append("n>6")
        if n >= 1 and ds[0] > sp["d1_max"]: fails.append("d1>35%")
        if n >= 1 and ds[-1] > sp["dn_max"]: fails.append("dn>10%")
        if n >= 2 and any(ds[k] >= sp["grow"] * ds[k-1] for k in range(1, n)): fails.append("grow")
        if pv == pv and c[t] == c[t] and c[t] < sp["near"] * pv: fails.append("close<0.9pivot")
        d = vo["dry"][t, j]
        if not (d == d and d <= sp["dry"]): fails.append("dry>0.7")
        for f in fails: cnt[f] += 1
        if not fails: cnt["valid"] += 1
        if len(fails) == 1: cnt["only:" + fails[0]] += 1
        if fails: first_fail[fails[0]] += 1
print("TT-pass days", cnt["tt"])
for k, v in sorted(cnt.items(), key=lambda x: -x[1]): print(f"  {k:22s} {v:9,d}  {v/cnt['tt']:.1%}")
print("segments n distribution:", dict(sorted(nseg.items())))
print("elapsed", round(time.time()-t0))
