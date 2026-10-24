"""美股三成營益率的一次性收入修法研究（omfixspec VER 1；docs/lab_us_sleeve_plan.md 第 14 節）。研究用，不上頁面。

  block(f, spec)  → 那個候選「多擋掉」的列（bool；QM 五個條件之外）
  research(C)     → data/lab/ussx_omfix.json（scripts/run_ussx.py --omfix；資料分支的資料）：
                    VER 6（同一份資料重算）、候選 A／B／C／D、只描述的 A10／A30／D10／D30／T，各自的判定、錢、少買與多買的股票、現在的持股；
                    建議（VER 2）＝D 兩條都過就 D，否則 ORDER 裡第一個「擋得到 CareDx、兩個計畫的判定都過」的候選。
C＝ussxqm.context(..., extra=omfixspec.KEYS)。"""
from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

import numpy as np

from . import omfixspec as S
from . import ussxqm as QM
from . import ussxspec as X

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "data" / "lab" / "ussx_omfix.json"


def block(f: dict, spec: dict | None) -> np.ndarray:
    """候選多擋掉的列。沒有值的比較＝不成立：A 不擋（照原本）、B／C／T 擋（同 qm_mask「沒有值＝不成立」）。"""
    om = np.asarray(f["om"], dtype=float)
    n = len(om)
    if spec is None:
        return np.zeros(n, dtype=bool)
    k = spec["kind"]
    with np.errstate(invalid="ignore"):
        if k in ("spike", "spike_ox"):
            om1, omd, th = np.asarray(f["om1"], dtype=float), np.asarray(f["omd"], dtype=float), spec["spike"]
            b = (om1 < S.OM_MIN) & (om - om1 >= th) & (omd >= th)
            if k == "spike_ox":                                   # VER 2 D：營業利益增加的比營收增加的多（不是賣得多）
                b &= np.asarray(f["oxr"], dtype=float) > 0
            return b
        if k == "prev":
            return ~(np.asarray(f["om1"], dtype=float) >= S.OM_MIN)
        if k == "median":
            return ~(np.asarray(f["omm"], dtype=float) >= S.OM_MIN)
        if k == "ttm":
            return ~(np.asarray(f["om4"], dtype=float) >= S.OM_MIN)
    raise ValueError(f"未知的候選 {k}")


def target_listed(C: dict, sig: dict) -> bool | None:
    """TARGET（那一週的 CareDx）在不在名單上；那一週不是週訊號日或沒有那檔股票＝None。"""
    sym, d = S.TARGET
    j = C["P"]["col"].get(sym)
    try:
        i = C["cal"].index(d)
    except ValueError:
        return None
    if j is None or i not in set(int(x) for x in C["cols"]["wk"]):
        return None
    return any(jj == j for jj, _ in sig.get(i, []))


def _trades(C: dict, r: dict) -> list[list]:
    """spx 主成本那一本帳的每一筆：[代號, 買進日, 賣出日, 報酬, 原因]（還沒賣＝open）。"""
    cal = C["cal"]
    return [[C["P"]["sym"][t[0]], cal[t[2]], cal[t[3]], round(float(t[4]), 6), t[5]] for t in r["trades"]]


def _brief(R: dict) -> dict:
    s, v = R["sleeve"]["main"], R["verdict"]
    out = {"sleeve": {"cagr": s["cagr"], "mdd": s["mdd"], "halves": [h["cagr"] for h in s["halves"]]},
           "sleeve_alt": {"cagr": R["sleeve"]["alt"]["cagr"]},
           "plans": {k: {"m": p["new"]["plan"]["m"], "mdd": p["new"]["plan"]["mdd"], "cagr": p["new"]["plan"]["cagr"],
                         "halves": [h["plan"]["m"] for h in p["new"]["halves"]],
                         "base_m": p["base"]["plan"]["m"], "base_mdd": p["base"]["plan"]["mdd"],
                         "base_halves": [h["plan"]["m"] for h in p["base"]["halves"]], "judge": p["judge"]}
                     for k, p in R["plans"].items()},
           "verdict": {"c1": v["c1"], "c2": v["c2"], "c3": v["c3"], "c4": v["c4"], "pass": v["pass"]},
           "trades": {k: R["trades"].get(k) for k in ("n", "open", "win", "avg", "med", "hold")},
           "top": R["top"], "weeks": R["weeks"], "signals": R["signals"], "exposure": R["exposure"],
           "now": {k: R["now"].get(k) for k in ("d", "hold", "buy", "sell") if k in R["now"]}}
    return out


def research(C: dict, log=print) -> dict:
    t0 = time.time()
    f = C["cols"]["f"]
    base = QM.qm_mask(f)
    sel = base & (C["yr"] >= X.QM_Y0)
    variants = {"V6": None, **S.CANDS, **S.DESC}
    out = {"ver": S.VER, "spec": S.SPEC_DATE, "rule_ver": X.VER, "made": date.today().isoformat(), "last": C["cal"][-1],
           "rows": int(sel.sum()), "runs": {}}
    tr0 = None
    for k, sp in variants.items():
        blk = block(f, sp)
        m = base & ~blk
        R = QM.research(C, log=lambda *a: None, mask=m, desc=False)
        rs = R.pop("_rs")
        sig = QM.signals(C, m)
        trs = _trades(C, rs)
        row = {"spec": sp, "blocked": int((sel & blk).sum()), "blocked_syms": int(len({C["cols"]["c"][i] for i in np.nonzero(sel & blk)[0]})),
               "target_listed": target_listed(C, sig), **_brief(R)}
        if k == "V6":
            tr0 = trs
            row["trades_list"] = trs
        else:
            a = {(t[0], t[1]) for t in tr0}
            b = {(t[0], t[1]) for t in trs}
            row["only_v6"] = [t for t in tr0 if (t[0], t[1]) not in b]
            row["only_new"] = [t for t in trs if (t[0], t[1]) not in a]
        out["runs"][k] = row
        log(f"[omfix] {k}：擋掉 {row['blocked']:,} 列；三成本身 {row['sleeve']['cagr'] * 100:.2f}%、"
            f"S&P 500 計畫 {row['plans']['spx_main']['m'] * 100:,.0f} 萬；判定 {row['verdict']['pass']}；"
            f"CDNA 在名單 {row['target_listed']}（{time.time() - t0:.0f}s）")
    # 判定（omfixspec：① 擋得到、② 兩個計畫都過；順序 A、B、C）
    judge = {}
    for k in list(S.CANDS):
        r = out["runs"][k]
        ok1 = r["target_listed"] is False
        ok2 = all(bool(r["verdict"]["pass"].get(mk)) for mk in S.PLANS)
        judge[k] = {"target": ok1, "rule": ok2, "pass": bool(ok1 and ok2)}
    out["judge"] = judge
    out["pick_v1"] = next((k for k in S.ORDER if judge[k]["pass"]), None)          # VER 1 的建議（A、B、C 的順序）
    out["pick"] = S.PREFER if judge[S.PREFER]["pass"] else out["pick_v1"]          # VER 2：D 兩條都過就建議 D
    log(f"[omfix] 判定 {judge}；建議 {out['pick']}（{time.time() - t0:.0f}s）")
    return out


def _clean(x):
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, (np.floating, float)):
        v = float(x)
        return None if not np.isfinite(v) else round(v, 6)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, np.str_):
        return str(x)
    return x


def save(R: dict, path: Path | None = None) -> None:
    p = path or RES
    p.write_text(json.dumps(_clean(R), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
