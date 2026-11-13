"""盤前第 5 段上線：08:45 台指期日盤開盤後，用開盤價重估 09:01 加權指數（pmestspec VER 1 過關；docs/lab_premarket_plan.md 第 16 節）。

  E2＝前一天加權指數收盤 C＋（台指期當天 08:45 開盤 − 同一契約前一天 13:45 收盤）；契約＝夜盤那一口（data/lab/premkt.json 的 night.sym）。
  八成範圍＝研究裡 E2 的 |誤差|/正常波動 80 百分位 × 今天的正常波動；平常差＝中位數 × 正常波動。
  研究檔不是這一版、或判定沒過 → 不出數字（頁面照舊用清晨的估計）。

  estimate(pm, quotes, research, now_hms) → {d, t, sym, open, ref, ref_src, est, typ, p80, early} 或 None
  apply(pm, e, log)                       → 把重估掛到 pm["e850"]、記到 log（{日期: 重估}），只留最近 KEEP 筆
  restore(pm, log, research)              → premkt 重算時從 log 把今天的重估掛回去（不然白天其他排程一重算就洗掉）
scripts/pm_0850.py 叫它（.github/workflows/fut_preopen.yml 在 08:58 取樣之前那一步）；這裡不連網。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / "data" / "lab" / "fut" / "e850.json"
RES = ROOT / "data" / "lab" / "pmest_research.json"
KEEP = 120
OPEN_HMS = "084500"


def _f(x) -> float | None:
    try:
        v = float(x) if x not in (None, "", "-") else None
    except (TypeError, ValueError):
        return None
    return v if v and v > 0 else None


def month_sym(exp: str | None) -> str | None:
    """'202611' → 'TXFK6'（期交所 MIS 的月份字母 A＝1 月…L＝12 月、年份最後一位）。"""
    if not exp or not re.fullmatch(r"\d{6}", str(exp)):
        return None
    y, m = int(exp[:4]), int(exp[4:])
    return f"TXF{chr(ord('A') + m - 1)}{y % 10}" if 1 <= m <= 12 else None


def pick(quotes: list[dict], pm: dict) -> dict | None:
    """夜盤那一口的日盤報價（'TXFK6-M' → 'TXFK6-F'）；找不到就用日盤成交量最大的近月。"""
    rows = {q.get("SymbolID"): q for q in quotes or [] if re.fullmatch(r"TXF[A-L]\d-F", str(q.get("SymbolID") or ""))}
    ns = str((pm.get("night") or {}).get("sym") or "")
    if ns.endswith("-M") and ns[:-2] + "-F" in rows:
        return rows[ns[:-2] + "-F"]
    best = max(rows.values(), key=lambda q: _f(q.get("CTotalVolume")) or 0, default=None)
    return best if best is not None and _f(best.get("CTotalVolume")) else None


def ok_research(research: dict | None) -> dict | None:
    from . import pmestspec as S
    if not research or research.get("ver") != S.VER or (research.get("judge") or {}).get("verdict") != "過關":
        return None
    e2 = (research.get("full") or {}).get("e2") or {}
    return e2 if e2.get("p80_em") and e2.get("med_em") else None


def estimate(pm: dict, quotes: list[dict], research: dict | None, now_hms: str, today: str) -> dict | None:
    """now_hms＝現在台北時間 'HHMMSS'；today＝'YYYY-MM-DD'。開盤價要是今天 08:45 之後的那一筆（擋掉前一天留在 MIS 上的報價）。"""
    e2 = ok_research(research)
    if not e2 or pm.get("next") != today:
        return None
    q = pick(quotes, pm)
    if not q:
        return None
    cd = str(q.get("CDate") or "")
    if cd and cd != today.replace("-", ""):
        return None
    ct = str(q.get("CTime") or "")
    o = _f(q.get("COpenPrice"))
    if not o or not re.fullmatch(r"\d{6}", ct) or not (OPEN_HMS <= ct <= now_hms):
        return None
    sym = str(q.get("SymbolID"))
    tx = pm.get("tx") or {}
    if month_sym(tx.get("sym")) == sym[:5] and _f(tx.get("close")):
        ref, src = float(tx["close"]), "昨天 13:45 收盤"
    else:
        ref, src = _f(q.get("CRefPrice")), "期交所參考價"
    if not ref:
        return None
    em = pm.get("em")
    est = round(float(pm["close"]) + o - ref)
    return {"d": today, "t": f"{now_hms[:2]}:{now_hms[2:4]}", "sym": sym, "open": o, "ref": ref, "ref_src": src, "est": est,
            "typ": round(e2["med_em"] * em) if em else None, "p80": round(e2["p80_em"] * em) if em else None, "early": pm.get("est")}


def apply(pm: dict, e: dict, log: dict) -> bool:
    """重估是 pm 那一天的才掛上；log 只留最近 KEEP 筆。回傳有沒有掛上。"""
    if not e or e.get("d") != pm.get("next"):
        return False
    pm["e850"] = e
    log[e["d"]] = {k: e[k] for k in ("t", "sym", "open", "ref", "ref_src", "est", "early")}
    for k in sorted(log)[:-KEEP]:
        del log[k]
    return True


def restore(pm: dict, log: dict, research: dict | None) -> bool:
    """premkt.build 重算時把今天（pm["next"]）記過的重估掛回去：2026-11-13 08:46 重估寫進 premkt.json 之後，
    09 點多 daily.yml 等排程重算盤前作戰圖，整份重寫、e850 不見，頁面又變回清晨的估計。紀錄檔 e850.json 不會被重算洗掉，從它還原。"""
    r = (log or {}).get(pm.get("next") or "")
    e2 = ok_research(research)
    if not r or not e2 or r.get("est") is None:
        return False
    em = pm.get("em")
    pm["e850"] = {"d": pm["next"], **{k: r[k] for k in ("t", "sym", "open", "ref", "ref_src", "est") if k in r},
                  "early": r.get("early", pm.get("est")),
                  "typ": round(e2["med_em"] * em) if em else None, "p80": round(e2["p80_em"] * em) if em else None}
    return True


def cur(pm: dict) -> dict | None:
    """頁面要用的重估：是這一份（next 那天）的才算。"""
    e = pm.get("e850")
    return e if e and e.get("d") == pm.get("next") and e.get("est") is not None else None
