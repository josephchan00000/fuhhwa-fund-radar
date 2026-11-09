"""面向新項目「過關才算分」（heatspec VER 13 GATE；heatspec_us VER 6；docs/lab_dims_plan.md 第 11 節）。

規格用當下的 heatspec（美股在 heatspec.use(heatspec_us.spec_for(idx)) 裡呼叫）：
  inc(dim, adm)  → 這個面向算分的項目：舊項目全部＋adm 裡的新項目（SHOW_ONLY 永遠不算）
  admitted(idx)  → 讀過關檔（GATE_FILE）：版本和規格不同、檔案沒有或壞掉＝空集合（新項目都不算分）
  compute(B)     → 判定（研究時算，B＝新項目都不算分的那一份 build 結果）：
    a. 這一項 heatcalc.evaluate（面向自己的期間與取樣）至少一個期間成立、方向對（EXPECT）；
    b. 那個期間的樣本 ≥ GATE_MIN[取樣]；c. 資料是新的（日、週：最後一筆離研究最後一天 ≤ GATE_FRESH_DAYS；月：不在過期清單）；
    d. 面向加完過關項目後，在新舊分數都有值的日子比，每個期間「方向對且成立」不能從 1 變 0；變差就這個面向一項都不加。
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from . import heat as H
from . import heatspec as S

ROOT = Path(__file__).resolve().parents[2]


def inc(dim: str, adm) -> list[str]:
    adm = adm or ()
    return [k for k in S.ITEMS[dim] if k not in S.CAND or (k in adm and k not in S.SHOW_ONLY)]


def comp_series(hc: dict, keys: list[str], T: int) -> list:
    return [H.composite({k: hc[k][i] for k in keys}, keys) for i in range(T)]


def admitted(idx: str | None = None, path: Path | None = None) -> set[str]:
    p = path or ROOT / S.GATE_FILE
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    if doc.get("ver") != S.VER:
        return set()
    g = (doc.get("idx") or {}).get(idx) if idx else doc
    return set((g or {}).get("admit") or [])


def _ok(e: dict, want: int) -> int:
    v = (e or {}).get("verdict")
    return int((want < 0 and v == "weak") or (want > 0 and v == "strong"))


def _fresh(k: str, B: dict) -> bool:
    if S.FREQ_OF[k] == "m":
        src = (B.get("pre") or {}).get(k) if k in S.PRESCORED else (B.get("mraw") or {}).get(k)
        return bool(src) and k not in (B.get("stale") or {})
    nat = (B.get("nat") or {}).get(k) or {}
    ks = [d for d, v in nat.items() if v is not None]
    if not ks or not B["cal"]:
        return False
    return (date.fromisoformat(B["cal"][-1]) - date.fromisoformat(max(ks))).days <= S.GATE_FRESH_DAYS


def compute(B: dict) -> dict:
    """→ {"ver", "admit": [...], "items": {k: {...}}, "dims": {d: {...}}}。B["hc"] 是逐日 0～100（新項目都有，不管算不算分）。"""
    from .heatcalc import evaluate
    cal, px = B["cal"], B["px"]
    T = len(cal)
    items, dims, admit = {}, {}, []
    for d in S.DIMS:
        cands = [k for k in S.ITEMS[d] if k in S.CAND and k not in S.SHOW_ONLY]
        if not cands:
            continue
        want, freq = S.EXPECT[d], S.DIMS[d]["freq"]
        passed = []
        for k in cands:
            ev = evaluate(B["hc"][k], px, cal, d)
            hs = {str(h): {"n": e["n"], "rho": e["rho"], "verdict": e["verdict"], "ok": _ok(e, want)} for h, e in ev.items()}
            a = any(v["ok"] for v in hs.values())
            b = any(v["ok"] and v["n"] >= S.GATE_MIN[freq] for v in hs.values())
            c = _fresh(k, B)
            items[k] = {"dim": d, "h": hs, "a": a, "b": b, "c": c, "pass": a and b and c}
            if a and b and c:
                passed.append(k)
        old_keys = inc(d, ())
        old = comp_series(B["hc"], old_keys, T)
        res = {"cands": cands, "passed": passed, "admit": []}
        if passed:
            new = comp_series(B["hc"], old_keys + passed, T)
            both = [o is not None and n is not None for o, n in zip(old, new)]
            eo = evaluate([o if m else None for o, m in zip(old, both)], px, cal, d)
            en = evaluate([n if m else None for n, m in zip(new, both)], px, cal, d)
            cmp = {str(h): {"old": {"rho": eo[h]["rho"], "verdict": eo[h]["verdict"], "ok": _ok(eo[h], want)},
                            "new": {"rho": en[h]["rho"], "verdict": en[h]["verdict"], "ok": _ok(en[h], want)},
                            "n": en[h]["n"]} for h in en}
            worse = any(v["new"]["ok"] < v["old"]["ok"] for v in cmp.values())
            res.update({"cmp": cmp, "worse": worse, "common_from": next((cal[i] for i in range(T) if both[i]), None)})
            if not worse:
                res["admit"] = list(passed)
                admit += passed
        dims[d] = res
    return {"ver": S.VER, "spec_date": S.SPEC_DATE, "admit": admit, "items": items, "dims": dims}


def write(doc: dict, path: Path | None = None) -> None:
    p = path or ROOT / S.GATE_FILE
    p.write_text(json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8")
