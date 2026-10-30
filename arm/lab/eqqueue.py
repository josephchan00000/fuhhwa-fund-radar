"""個股報告每週的名單（docs/lab_equity_report_plan.md 第 12 節；每週六排程照這份做，每家一個子代理照技能 equity-report）。

順序：①美股強勢品質股下週一要買的、②新飆股（台股）下週一要買的（名單名次），③已經有報告、而且之後出了新一季財報的（季更新）。
扣掉 90 天內做過、之後也沒有新一季財報的。最多 EQ_WEEKLY_MAX 家，超過的列在「這週排不到」。只讀 repo 裡的資料。
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "reports" / "eq"
EQ_WEEKLY_MAX = 4
FRESH_DAYS = 90


def _read(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def last_report(mk: str, code: str, src: Path = SRC) -> tuple[str, str] | None:
    """最新一份報告的（報告日, 那份資料包最後一季的季底）。"""
    d = src / mk / code
    fs = sorted(d.glob("*.facts.json")) if d.exists() else []
    if not fs:
        return None
    pk = _read(fs[-1], {}) or {}
    q = (pk.get("q") or [{}])[-1].get("q")
    return fs[-1].name[:10], q


def latest_quarter(mk: str, code: str) -> str | None:
    """現在資料裡這家最新一季的季底（台股 dashboard/co/{代號}.json；美股 data/lab/ussx_fin.json）。"""
    if mk == "tw":
        co = _read(ROOT / "dashboard" / "co" / f"{code}.json", {}) or {}
        q = co.get("q") or []
        return q[-1][0] if q else None
    fin = _read(ROOT / "data" / "lab" / "ussx_fin.json", {}) or {}
    q = (((fin.get("s") or {}).get(code)) or {}).get("q") or []
    return q[-1][0] if q else None


def need(mk: str, code: str, today: str, src: Path = SRC) -> tuple[bool, str]:
    """要不要做：沒做過、或做過但出了新一季財報、或超過 FRESH_DAYS 天。"""
    lr = last_report(mk, code, src)
    if not lr:
        return True, "第一份"
    made, q = lr
    nq = latest_quarter(mk, code)
    if nq and q and nq > q:
        return True, f"{made} 做過，之後出了 {nq} 的財報"
    if (date.fromisoformat(today) - date.fromisoformat(made)).days > FRESH_DAYS:
        return True, f"{made} 做過，已超過 {FRESH_DAYS} 天"
    return False, f"{made} 做過，還沒有新一季財報"


def candidates(x9_html: str | None = None, qm: dict | None = None) -> list[dict]:
    """這週要買的：美股強勢品質股（ussx_qm.json now.buy）、新飆股（選股頁 D.pick.tw.bx 標 b 的，照名次）。"""
    from . import eqfacts as E
    out = []
    qm = qm if qm is not None else (_read(ROOT / "data" / "lab" / "ussx_qm.json", {}) or {})
    now = qm.get("now") or {}
    for c in now.get("buy") or []:
        out.append({"mk": "us", "code": c, "why": f"美股強勢品質股 {now.get('next') or ''} 開盤買進"})
    text = x9_html if x9_html is not None else ((ROOT / "dashboard" / "x9.html").read_text(encoding="utf-8")
                                                if (ROOT / "dashboard" / "x9.html").exists() else "")
    bx = E._json_obj(text, "bx") or {}
    for i, r in enumerate(bx.get("rows") or []):
        if r and r[-1] == "b":                             # 列的最後一欄＝現況（b 會買／h 拿著／w 等空位；pickpage.boom_box）
            out.append({"mk": "tw", "code": r[0], "name": r[1], "why": f"新飆股名單第 {i + 1} 名，{bx.get('buyd') or ''} 開盤買進"})
    return out


def updates(today: str, src: Path = SRC) -> list[dict]:
    """已經有報告、之後出了新一季財報的（季更新）。"""
    out = []
    for mk in ("tw", "us"):
        for d in sorted((src / mk).glob("*")) if (src / mk).exists() else []:
            ok, why = need(mk, d.name, today, src)
            if ok and "財報" in why:
                out.append({"mk": mk, "code": d.name, "why": why})
    return out


def queue(today: str, maxn: int = EQ_WEEKLY_MAX, src: Path = SRC, cands: list[dict] | None = None) -> dict:
    todo, skip, seen = [], [], set()
    for c in (cands if cands is not None else candidates()) + updates(today, src):
        k = (c["mk"], c["code"])
        if k in seen:
            continue
        seen.add(k)
        ok, why = need(c["mk"], c["code"], today, src)
        if not ok:
            skip.append({**c, "skip": why})
            continue
        (todo if len(todo) < maxn else skip).append({**c, "state": why} if len(todo) < maxn else {**c, "skip": "這週排不到（每週最多 %d 家）" % maxn})
    return {"d": today, "max": maxn, "todo": todo, "skip": skip}
