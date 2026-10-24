"""新策略候選（規格 arm/lab/candspec.py；docs/lab_ia_v5_plan.md 第 24 節）。

  TZ=Asia/Taipei python3 scripts/run_cands.py --check                 規格與程式的格式、sha（容器裡也可以跑；不回測）
  python3 scripts/run_cands.py --merge-from <資料夾>                  合併通道：<資料夾>＝分支的 config/strategy_candidates.json
                                                                       與 arm/lab/cands/；只拿這兩個地方，用 main 的檢查
  python3 scripts/run_cands.py --need-us                              這一輪要不要美股資料（寫進 GITHUB_OUTPUT 的 us=true／false）
  USSX_DIR=… python3 scripts/run_cands.py --compute [--force] [--ids c001,c002] [--new c005]
                                                                       回測還沒有結果的候選 → data/lab/cands_research.json；
                                                                       --new 的候選沒算完或用到未來資料 → exit 1（合併通道不合併）
  USSX_DIR=… python3 scripts/run_cands.py --forward                   試用中的候選補每週紀錄 → data/lab/cands_live.json
回測與試用紀錄只在 CI 跑（.github/workflows/strategy_cands.yml）；本容器擋資料來源，也不必在這裡算。
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arm import clock  # noqa: E402
from arm.lab import candrun as R  # noqa: E402
from arm.lab import candspec as CS  # noqa: E402


def _out(**kv) -> None:
    """寫進 GitHub Actions 的輸出（直接寫檔，不經 stdout）。"""
    p = os.environ.get("GITHUB_OUTPUT")
    if not p:
        return
    with open(p, "a", encoding="utf-8") as f:
        for k, v in kv.items():
            f.write(f"{k}={v}\n")


def check() -> int:
    errs = R.check_spec(R.load_spec(), R.PROG, clock.today_tw().isoformat())
    for e in errs:
        print(f"✗ {e}")
    doc = R.load_spec()
    dec = R.decisions()
    print(f"規格 {len(doc['items'])} 條、還沒決定 {len(R.open_ids(doc, dec))} 條（最多 {CS.MAX_OPEN}）："
          + ("🟢 格式與 sha 都對" if not errs else f"🔴 {len(errs)} 個問題"))
    return 1 if errs else 0


def merge_from(src: str) -> int:
    """分支的規格與程式放進 main 的工作目錄，用 main 的規則檢查；不過就不合併（exit 1，工作目錄不 commit）。"""
    base = Path(src)
    sp = base / CS.SPEC_FILE
    if not sp.exists():
        print("分支上沒有規格檔：沒有要合併的")
        _out(new="")
        return 0
    old = R.load_spec()
    new = R.load_spec(sp)
    pd = base / CS.PROG_DIR
    for f in sorted(pd.glob("c*.py")) if pd.exists() else []:
        if f.stem[1:].isdigit() and len(f.stem) == 4:
            shutil.copyfile(f, R.PROG / f.name)
    R.SPEC.write_bytes(sp.read_bytes())
    errs, fresh = R.merge_check(old, new, R.PROG, R.decisions(), clock.today_tw().isoformat())
    for e in errs:
        print(f"✗ {e}")
    if errs:
        print(f"🔴 不合併：{len(errs)} 個問題")
        return 1
    print("🟢 可以合併" + (f"：新的 {', '.join(fresh)}" if fresh else "（沒有新的候選）"))
    _out(new=",".join(fresh))
    return 0


def need_us(forward: bool) -> int:
    doc, res = R.load_spec(), R.load_res()
    us = any(it.get("mk") in ("spx", "ndx", "us") and it.get("need") is None and not R.fresh(res, it) for it in doc["items"])
    if forward:
        dec = R.decisions()
        us = us or any(it.get("engine") == "us_stock" and (dec.get(it["id"]) or {}).get("dec") == "trial" for it in doc["items"])
    print(f"美股資料：{'要' if us else '不用'}")
    _out(us="true" if us else "false")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--merge-from")
    ap.add_argument("--need-us", action="store_true")
    ap.add_argument("--compute", action="store_true")
    ap.add_argument("--forward", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--ids")
    ap.add_argument("--new", default="", help="合併通道這一次的新候選（逗號隔開）：其中有沒算出來或用到未來資料的就不合併")
    a = ap.parse_args()
    if a.check:
        return check()
    if a.merge_from:
        return merge_from(a.merge_from)
    if a.need_us:
        return need_us(a.forward)
    rc = 0
    X = R.Ctx()
    if a.compute:
        res, done = R.compute(a.ids.split(",") if a.ids else None, force=a.force, X=X)
        changed = R.save_res(res)
        print(f"回測：{len(done)} 條（{', '.join(done) or '沒有要算的'}）；研究檔{'更新' if changed else '沒變'}")
        _out(computed=",".join(done))
        bad = [k for k in a.new.split(",") if k and (res["items"].get(k) or {}).get("v") in ("err", "peek", None)]
        if bad:
            print(f"🔴 新的候選沒有乾淨地算完，不合併：{', '.join(bad)}（修好程式再推；還沒進 main 的候選可以改）")
            rc = 1
    if a.forward:
        L, touched = R.forward(X)
        changed = R.save_live(L)
        print(f"試用紀錄：{', '.join(touched) or '沒有新的日子'}；紀錄{'更新' if changed else '沒變'}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
