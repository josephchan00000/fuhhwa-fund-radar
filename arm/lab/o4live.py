"""O4 結算均價的紙上紀錄（txospec VER 2 第 19 節「② 不到之前只列、記紙上紀錄（每週更新）」；使用者 2026-11-13 回「好」）。

  紀錄只增不改：每個結算日第一次算出來就記下（結算價、候選數、照規則挑到的單，一口的格式），之後不再改；
  規格（txospec 指紋）改了就不再往這一本加，要另開一本。
  帳戶、口數、損益、判定每次從整本紀錄用 txo1.sim／metrics／o4_judge 重算（同回測的規則），存在 "sum"，頁面只讀這個檔。

  update(root, led, today) → 新記的結算日（資料分支要有那天的分 K 和 5 秒指數）
  summarize(led)           → led["sum"]
scripts/run_o4live.py 叫它（.github/workflows/txo_data.yml 每週五晚上那一班）；這裡不連網。
"""
from __future__ import annotations

from pathlib import Path

from . import txospec as S

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / "data" / "lab" / "txo_o4_live.json"


def new_book() -> dict:
    return {"ver": S.VER, "spec_fp": S.fingerprint(), "spec_date": S.SPEC_DATE, "from": S.O4_FROM, "days": {}}


def same_spec(led: dict) -> bool:
    return led.get("spec_fp") in (None, S.fingerprint())


def update(root: Path, led: dict, today: str, log=print) -> list[str]:
    from . import txo1 as X
    if not same_spec(led):
        log(f"[O4 紙上紀錄] 規格改了（紀錄 {led.get('spec_fp')}、現在 {S.fingerprint()}），這一本不再加；要另開一本")
        return []
    root = Path(root)
    idx = X.load_idx(root)
    days, book, last = X.load_book(root)
    sett = X.settle_days(days, last, idx)
    m = X.Mkt(idx, days, book, sett)
    led.setdefault("days", {})
    new = []
    for d in sorted(sett):
        if d < S.O4_FROM or d > today or d in led["days"] or d not in idx or X.load_bars(root, d) is None:
            continue
        picks, cands = X.o4_day(m, root, d)
        led["days"][d] = {"F": round(float(S.settle_price([float(x) for x in idx[d]])), 2), "cands": len(cands),
                          "picks": picks, "rec": today}
        new.append(d)
    led.update({"ver": S.VER, "spec_fp": S.fingerprint(), "spec_date": S.SPEC_DATE, "from": S.O4_FROM,
                "asof": max(idx) if idx else led.get("asof")})
    log(f"[O4 紙上紀錄] 新記 {len(new)} 個結算日：{'、'.join(new) or '沒有'}（共 {len(led['days'])} 個）")
    return new


def summarize(led: dict) -> dict:
    from . import txo1 as X
    ds = sorted(led.get("days") or {})
    picks = [p for d in ds for p in led["days"][d]["picks"]]
    res = X.sim(picks, S.O4_CAP_EACH)
    mt = X.metrics(res)
    led["sum"] = {"metrics": mt, "judge": X.o4_judge(mt, res["rows"], None),
                  "days": [{"d": d, "F": led["days"][d]["F"], "cands": led["days"][d]["cands"], "picks": len(led["days"][d]["picks"])}
                           for d in ds],
                  "trades": [{k: r[k] for k in ("d", "k", "cp", "kx", "p0", "floor", "lots", "pnl", "ret") if k in r} for r in res["rows"]],
                  "after_spec": sum(1 for d in ds if d >= S.SPEC_DATE)}
    return led["sum"]
