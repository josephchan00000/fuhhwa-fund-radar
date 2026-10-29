#!/usr/bin/env python3
"""新飆股上名單週數要用的舊名單（sxlivespec VER 4 ①；docs/lab_boom_v2_plan.md 第 9 節）→ data/lab/sxlive_hist.json（只算一次）。

2026 年 START 以前每個週末（證交所官方休市表的每週最後一個交易日）收盤，照那一年 R60 的規則（sxlive_rules.json）
用頁面同一套資料與特徵（sxlive.day_signals；官方分片 6/3 才開始，之前是頁面同一份 Yahoo 補缺的價量）算出的名單，依強度高到低。紀錄從 START 起才有，N8「新上名單的先買」要知道
一檔股票之前已經連續上了幾週，所以補這一段。只算一次、之後不改。
  TZ=Asia/Taipei python3 scripts/run_sxlive_hist.py          （約 2 分鐘）
  --force   已經有檔也重寫（規格說只算一次；只在程式錯了要重算時用，commit 訊息寫原因）"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm import clock  # noqa: E402
from arm.lab import store  # noqa: E402
from arm.lab import sxlive as L  # noqa: E402
from arm.lab import sxlivespec as S  # noqa: E402

OUT = store.LAB / S.HIST_FILE


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if OUT.exists() and not a.force:
        print(f"{OUT} 已經有了（規格：只算一次）；要重算加 --force")
        return 0
    t0 = time.time()
    from arm.lab.analyze import Data
    DL = Data(long=True)
    ctx = L.context(DL)
    cal = ctx["P"].cal
    R = L.load_rules()
    y = int(L.HIST_FROM[:4])
    rules = L.rules_for(y, S.LIST_BOOK, R)
    if not rules:
        raise SystemExit(f"沒有 {y} 年的規則")
    end = cal[next(i for i in range(len(cal) - 1, -1, -1) if cal[i] < S.START)]
    weeks = {}
    for d in L.week_ends(L.HIST_FROM, end):
        if d not in cal:
            raise SystemExit(f"{d} 不在頁面的日曆裡")
        lst = L.day_signals(cal.index(d), ctx, {S.LIST_BOOK: rules})[S.LIST_BOOK]
        weeks[d] = [[c, round(float(rs), 4)] for c, rs in lst]
        print(f"{d}：{len(lst)} 檔", flush=True)
    seed = L.load_seed() or {}
    chk = {}
    for d, w in sorted((seed.get("weeks") or {}).items()):   # 接手時記的那幾週：10/16、10/22 同一套算法要相同；更早的是長歷史股價算的，差一兩檔
        if d in weeks:
            a_ = {c for c, _ in w.get(S.LIST_BOOK) or []}
            b_ = {c for c, _ in weeks[d]}
            chk[d] = [len(a_), len(b_), len(a_ & b_)]
    doc = {"ver": S.VER, "spec": S.SPEC_DATE, "book": S.LIST_BOOK, "from": L.HIST_FROM, "to": end,
           "made": clock.today_tw().isoformat(), "rules": L.digest(rules), "weeks": weeks, "check_seed": chk}
    J = lambda x: json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"))  # noqa: E731
    lines = ["{"] + [J(k) + ":" + J(doc[k]) + "," for k in ("ver", "spec", "book", "from", "to", "made", "rules", "check_seed")]
    lines.append(J("weeks") + ":{\n" + ",\n".join(J(d) + ":" + J(w) for d, w in sorted(weeks.items())) + "\n}")
    lines.append("}")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"已寫入 {OUT}（{len(weeks)} 週；和接手時記的名單 [接手時, 這裡, 共同]：{chk}），{time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
