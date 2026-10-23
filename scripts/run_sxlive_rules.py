"""飆股前瞻記錄：找某一年的規則（規格 arm/lab/sxlivespec.py；docs/lab_core70_plan.md 第 14 節）。

和 W7 同一個函式（tw-superstock-lab/scripts/run_w7.py 的 samples＋mine：superfixspec.fold_periods、superx VER 2 的門檻與備用門檻）；
要 numpy、pandas。y 年的規則只用 y−1 年底以前已經走完的資料，所以長歷史股價（data/lab/v3px）要先涵蓋到 y−1 年最後一個交易日。

    python3 scripts/run_sxlive_rules.py --year 2027                  找 2027 年的規則、寫進 data/lab/sxlive_rules.json
    python3 scripts/run_sxlive_rules.py --auto [--refresh-min 40]    今年的有了就結束；沒有就先補股價（最多 N 分鐘）、夠新了才找
    python3 scripts/run_sxlive_rules.py --check 2026                 用同一個流程重找、和存檔逐字比對（驗證用，不寫檔）
每週一 lab_opt.yml 跑 --auto：平常秒退，只有每年 1 月第一次會真的補股價、找規則（約 20～40 分鐘）。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm import clock, twholidays  # noqa: E402
from arm.lab import store  # noqa: E402
from arm.lab import sxlivespec as S  # noqa: E402

COVER_MIN = 0.98          # 最近 40 天還有交易的股票，至少這個比例要到 y−1 年最後一個交易日


def last_td(y: int) -> str:
    d = date(y, 12, 31)
    while d.weekday() >= 5 or twholidays.is_closed(d) is True:
        d -= timedelta(days=1)
    return d.isoformat()


def coverage(y: int) -> tuple[bool, str]:
    """長歷史股價夠不夠找 y 年的規則（加權指數與幾乎所有股票都到 y−1 年最後一個交易日）。"""
    from arm.lab.v3data import stock
    target = last_td(y - 1)
    tw = (store.read("v3px", "TWII") or {}).get("t") or []
    if not tw or tw[-1] < target:
        return False, f"加權指數只到 {tw[-1] if tw else '—'}，要到 {target}"
    lo = (date.fromisoformat(target) - timedelta(days=40)).isoformat()
    act = ok = 0
    for c in store.dates("v3px"):
        if not stock(c):
            continue
        t = (store.read("v3px", c) or {}).get("t") or []
        if not t or t[-1] < lo:
            continue
        act += 1
        ok += t[-1] >= target
    good = act > 0 and ok / act >= COVER_MIN
    return good, f"{ok}/{act} 檔到 {target}"


def mine(y: int) -> dict:
    """y 年 R60、A 的規則（和 W7 同一個函式）。"""
    sys.path.insert(0, str(ROOT / "tw-superstock-lab" / "scripts"))
    import run_w7 as W                                  # noqa: E402 —— 要 numpy、pandas
    t0 = time.time()
    rows = W.samples()
    cal = [d for d in (store.read("v3px", "TWII") or {}).get("t") or [] if d >= "2013-01-01"]
    W.G.update(rows=rows, ix={d: i for i, d in enumerate(cal)}, cal=cal)
    out = {"src": "scripts/run_sxlive_rules.py", "made": clock.today_tw().isoformat(), "data_last": cal[-1]}
    for lab in S.RULE_BOOKS:
        f = W.mine((lab, y))
        out[lab] = {k: f[k] for k in ("thr", "rules", "n_is", "n_val", "base_is", "base_val", "try")}
        print(f"[sxlive] {y} {lab}：{f['thr'] or '沒有規則'}，{len(f['rules'])} 條（{time.time() - t0:.0f} 秒）")
        for r in f["rules"]:
            print(f"    {r['txt']}")
    return out


def save(y: int, rec: dict) -> None:
    p = store.LAB / S.RULES_FILE
    doc = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"ver": 1, "years": {}}
    doc.setdefault("years", {})[str(y)] = rec
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int)
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--refresh-min", type=float, default=0.0)
    ap.add_argument("--check", type=int)
    a = ap.parse_args()
    years = (json.loads((store.LAB / S.RULES_FILE).read_text(encoding="utf-8")).get("years") or {}) \
        if (store.LAB / S.RULES_FILE).exists() else {}
    if a.check:
        got = mine(a.check)
        bad = [b for b in S.RULE_BOOKS if got[b]["rules"] != ((years.get(str(a.check)) or {}).get(b) or {}).get("rules")]
        print("[sxlive] 重找結果和存檔" + ("相同" if not bad else f"不同：{bad}"))
        return 1 if bad else 0
    y = a.year or clock.today_tw().year
    if str(y) in years:
        print(f"[sxlive] 已有 {y} 年的規則")
        return 0
    if a.auto and y <= S.SEED_YEAR:
        return 0
    ok, msg = coverage(y)
    if not ok and a.refresh_min > 0:
        from arm.lab import v3data
        print(f"[sxlive] 長歷史股價不夠新（{msg}），先補 {a.refresh_min:.0f} 分鐘")
        v3data.run(budget_s=a.refresh_min * 60)
        ok, msg = coverage(y)
    if not ok:
        print(f"[sxlive] {y} 年的規則還沒找：長歷史股價不夠新（{msg}）")
        return 0 if a.auto else 1
    save(y, mine(y))
    print(f"[sxlive] {y} 年的規則已寫進 data/lab/{S.RULES_FILE}（{msg}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
