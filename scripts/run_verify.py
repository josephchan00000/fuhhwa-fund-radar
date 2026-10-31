#!/usr/bin/env python3
"""計算正確性的核對（docs/lab_signal_quality_plan.md 第 5、8 節，A 段）→ data/lab/verify_status.json。

  TZ=Asia/Taipei python3 scripts/run_verify.py

兩道檢查，只讀資料、不改任何計算與研究檔：
  ① 第二套算法（arm/lab/sigverify.py）：五個市場的每一個市場層級訊號（含型態類技術事件）的出現日、狀態、去重、分段、次數、命中率、平常；
     研究列（之後怎麼走的報酬表、近 10 年、最大跌幅、判定）、大跌後買點、逐年檢查、溫度計每週票數、產業泡沫——都要和網頁用的一樣；
  ② 截斷重建（arm/lab/truncheck.py）：原始資料截到某一天整條重算，那天以前的景氣頁 0～100、泡沫頁每月條件、訊號都要一樣
     （不一樣＝那天其實還拿不到的資料被用到了）。
截斷日＝固定幾天（不同年代、2013 與 2025 政府停擺延後公布的期間）＋資料最新一天往前的最近一個月底、往前 10 個交易日。約 25 分鐘。
每週六 CI（.github/workflows/verify.yml）在 main 上跑、commit 這個檔；不一致時網頁標紅、06:35 推播多一行（arm/lab/valog.py 的 verify_*），
不擋任何發佈（docs/lab_signal_quality_plan.md 第 11 節，使用者決定 D4）。每一類只存前 CAP 個例子，全部的個數記在 nbad。
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
VER = 2                    # 2：例子截到 CAP 個、另記 nbad（2026-10-31，A-3）
CAP = 50
FIXED_DAYS = ("2008-06-30", "2013-10-25", "2016-03-31", "2021-09-30", "2025-11-30", "2025-12-10")


def nbad(r: dict) -> int:
    """一類核對的不一致個數（例子可能只存了一部分）。"""
    return int(r.get("nbad", len(r.get("bad") or [])))


def cap(x):
    """存檔前每一個 bad 清單只留 CAP 個例子、另記 nbad——全部不一致時檔案不會變成幾 MB。"""
    if not isinstance(x, dict):
        return x
    out = {k: cap(v) for k, v in x.items()}
    if isinstance(x.get("bad"), list) and len(x["bad"]) > CAP:
        out["bad"], out["nbad"] = x["bad"][:CAP], nbad(x)
    return out


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
    more = {"rows": {mk: V.check_rows(F[mk]) for mk in F}, "buy": {mk: V.check_buy(F[mk]) for mk in F},
            "oos": {mk: V.check_oos(F[mk]) for mk in F}, "thermo": {mk: V.check_thermo(F[mk]) for mk in F},
            "ind": {"all": V.check_ind()}}
    print(f"[verify] 研究列、買點、逐年檢查、溫度計、產業泡沫 {time.time() - t0:.0f}s：" +
          "、".join(f"{k} 不同 {sum(len(r['bad']) for r in per.values())}" for k, per in more.items()), flush=True)
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
    nb = sum(nbad(r) for r in second.values()) + sum(nbad(r) for per in more.values() for r in per.values()) + \
        sum(nbad(r) for R in (heat, bub, sig) for per in R.values() for r in per.values())
    bad = [["第二套", mk, *b] for mk, r in second.items() for b in r["bad"]]
    bad += [[f"第二套・{k}", mk, *b] for k, per in more.items() for mk, r in per.items() for b in r["bad"]]
    for name, R in (("0～100", heat), ("泡沫", bub), ("訊號", sig)):
        for d, per in R.items():
            for mk, r in per.items():
                bad += [[f"截斷・{name}", d, mk, *b] for b in r["bad"]]
    return {"ver": VER, "asof": F["tw"]["cal"][-1], "made": clock.stamp_tw(), "days": days,
            "second": second, "more": more, "trunc": {"heat": heat, "bub": bub, "sig": sig},
            "n": {"second": sum(r["checked"] for r in second.values()),
                  **{k: sum(int(r.get("n") or 0) for r in per.values()) for k, per in more.items()},
                  "heat": sum(v["items"] for per in heat.values() for v in per.values()),
                  "bub": sum(v["rows"] for per in bub.values() for v in per.values()),
                  "sig": sum(v["n"] for per in sig.values() for v in per.values())},
            "bad": bad, "nbad": nb, "ok": nb == 0}


def main() -> None:
    t0 = time.time()
    R = run()
    OUT.write_text(json.dumps(cap(R), ensure_ascii=False, sort_keys=True, indent=1, default=str) + "\n", encoding="utf-8")
    head = "全部一樣" if R["ok"] else f"不同 {R['nbad']} 項"
    print(f"[verify] {head}；寫入 {OUT}（{OUT.stat().st_size // 1024} KB），共 {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
