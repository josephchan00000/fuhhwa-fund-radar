#!/usr/bin/env python3
"""計算正確性的核對（docs/lab_signal_quality_plan.md 第 5、8 節，A 段）→ data/lab/verify_status.json。

  TZ=Asia/Taipei python3 scripts/run_verify.py

兩道檢查，只讀資料、不改任何計算與研究檔：
  ① 第二套算法（arm/lab/sigverify.py）：五個市場的每一個市場層級訊號，出現日、狀態、去重、分段、次數、命中率、平常
     都要和網頁用的 sigcat 一樣；
  ② 截斷重建（arm/lab/truncheck.py）：原始資料截到某一天整條重算，那天以前的景氣頁 0～100、泡沫頁每月條件、訊號都要一樣
     （不一樣＝那天其實還拿不到的資料被用到了）。
截斷日＝固定幾天（不同年代、2025-10 美國政府停擺缺一個月）＋資料最新一天往前的最近一個月底、往前 10 個交易日。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm import clock  # noqa: E402
from arm.lab import sigverify as V  # noqa: E402
from arm.lab import truncheck as TC  # noqa: E402

OUT = ROOT / "data" / "lab" / "verify_status.json"
VER = 1
FIXED_DAYS = ("2008-06-30", "2016-03-31", "2021-09-30", "2025-11-30")


def cut_days(cal: list[str]) -> list[str]:
    """固定的截斷日＋資料最新一天往前的最近一個月底、往前 10 個交易日（都要在資料範圍內）。"""
    last = cal[-1]
    me = max(d for d in cal if d[:7] < last[:7])
    days = [d for d in FIXED_DAYS if cal[0] < d < last] + [me, cal[-11]]
    return sorted(set(days))


def run() -> dict:
    from arm.lab import bubble as BU
    from arm.lab import heatcalc as HC
    from arm.lab import heatcalc_us as HU
    from arm.lab import sigcat as G
    t0 = time.time()
    BT, BA, BX = HC.build(), HU.build_all(), BU.compute()
    F = G.frames(BT, BA, BX)
    print(f"[verify] 資料 {time.time() - t0:.0f}s", flush=True)
    second = {mk: V.check_market(F[mk]) for mk in F}
    print(f"[verify] 第二套算法 {time.time() - t0:.0f}s：" +
          "、".join(f"{mk} {r['checked']}/{r['n']} 不同 {len(r['bad'])}" for mk, r in second.items()), flush=True)
    days = cut_days(F["tw"]["cal"])
    full = {"tw": BT, **BA}
    heat, bub, sig = {}, {}, {}
    for d in days:
        heat[d] = TC.check(d, full)
        bub[d] = TC.bub_check(d, BX)
        sig[d] = {mk: TC.sig_check(F[mk], d) for mk in F}
        nb = sum(len(v["bad"]) for v in heat[d].values()) + sum(len(v["bad"]) for v in bub[d].values()) + \
            sum(len(v["bad"]) for v in sig[d].values())
        print(f"[verify] 截斷 {d}：不同 {nb}（{time.time() - t0:.0f}s）", flush=True)
    bad = [["第二套", mk, *b] for mk, r in second.items() for b in r["bad"]]
    for name, R in (("0～100", heat), ("泡沫", bub), ("訊號", sig)):
        for d, per in R.items():
            for mk, r in per.items():
                bad += [[f"截斷・{name}", d, mk, *b] for b in r["bad"]]
    return {"ver": VER, "asof": F["tw"]["cal"][-1], "made": clock.stamp_tw(), "days": days,
            "second": second, "trunc": {"heat": heat, "bub": bub, "sig": sig},
            "n": {"second": sum(r["checked"] for r in second.values()),
                  "heat": sum(v["items"] for per in heat.values() for v in per.values()),
                  "bub": sum(v["rows"] for per in bub.values() for v in per.values()),
                  "sig": sum(v["n"] for per in sig.values() for v in per.values())},
            "bad": bad, "ok": not bad}


def main() -> None:
    t0 = time.time()
    R = run()
    OUT.write_text(json.dumps(R, ensure_ascii=False, sort_keys=True, indent=1, default=str) + "\n", encoding="utf-8")
    head = "全部一樣" if R["ok"] else f"不同 {len(R['bad'])} 項"
    print(f"[verify] {head}；寫入 {OUT}（{OUT.stat().st_size // 1024} KB），共 {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
