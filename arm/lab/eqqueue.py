"""個股報告每天晚上的名單（docs/lab_eq_request_plan.md 第 3.3 節；每天台北 20:47 排程照這份做，每家一個子代理照技能 equity-report）。

順序：①申請的（data/eq_requests.json，照收件匣排好的順序）→ ②接下來 AHEAD 個交易日要買、還沒有新報告的
（台股＝選股頁「這週要做的事」那份事件裡主要策略的買進；美股＝美股強勢品質股下一次要買的）→ ③季更新（已經有報告、
之後出了新一季財報的；只在週六）。每一家做之前都再判一次：90 天內做過、之後也沒有新一季財報的不做；美股只收資料包做得出來的
（eqinbox.known）。每班最多 EQ_RUN_MAX 家，排不到的留到明天。只讀 repo 裡的資料。
（2026-10-29～10-30 是每週六一班、每週最多 4 家；使用者 10-30 選「每晚＋自動補」、申請單「大家都能申請」。）
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "reports" / "eq"
EQ_RUN_MAX = 3                                     # 每天晚上一班最多幾家
AHEAD = 2                                          # 接下來幾個交易日要買的
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


def page_pick(text: str) -> dict:
    """選股頁內嵌的 D.pick（有 "tw" 的那一個；頁面裡還有別的 "pick" 物件）。"""
    dec, i = json.JSONDecoder(), 0
    while True:
        i = text.find('"pick":{', i)
        if i < 0:
            return {}
        try:
            obj, _ = dec.raw_decode(text, i + len('"pick":'))
        except ValueError:
            obj = None
        if isinstance(obj, dict) and "tw" in obj:
            return obj
        i += 1


def _md(d: str) -> str:
    return f"{int(d[5:7])}/{int(d[8:10])}"


def requests(path: Path | None = None) -> list[dict]:
    """①申請的（收件匣排好的順序）。"""
    from . import eqinbox as I
    return [{"mk": x["mk"], "code": x["code"], "name": x.get("name"), "src": f"申請 #{x['issue']}"}
            for x in I.pending(path or I.FILE)]


def upcoming(today: str, x9_html: str | None = None, qm: dict | None = None, n: int = AHEAD) -> list[dict]:
    """②接下來 n 個交易日（today 之後；證交所／NYSE 休市表）要買的：台股＝D.pick.tw.ev 裡主要策略、有名單的「買進」；
    美股＝ussx_qm.json 的 now.buy（now.next 在這幾天裡）。"""
    from . import pickcal as PC
    out = []
    text = x9_html if x9_html is not None else ((ROOT / "dashboard" / "x9.html").read_text(encoding="utf-8")
                                                if (ROOT / "dashboard" / "x9.html").exists() else "")
    tw = page_pick(text).get("tw") or {}
    main = {k[0] for k in tw.get("ks") or [] if len(k) > 3 and k[3]}
    days = set(PC.next_days("tw", today, n))
    for e in tw.get("ev") or []:                       # [日期, 開盤/收盤, 策略, 動作, [[代號, 名稱]], 說明, 推算]
        if e[2] in main and e[3] == "買進" and e[0] in days:
            for c, nm in e[4] or []:
                out.append({"mk": "tw", "code": c, "name": nm, "src": f"{_md(e[0])} 要買（{PC.SHORT.get(e[2], e[2])}）"})
    qm = qm if qm is not None else (_read(ROOT / "data" / "lab" / "ussx_qm.json", {}) or {})
    now = qm.get("now") or {}
    if now.get("next") and now["next"] in set(PC.next_days("spx", today, n)):
        for c in now.get("buy") or []:
            out.append({"mk": "us", "code": c, "name": None, "src": f"{_md(now['next'])} 要買（{PC.SHORT['qm']}）"})
    return out


def updates(today: str, src: Path = SRC) -> list[dict]:
    """③已經有報告、之後出了新一季財報的（季更新）。"""
    out = []
    for mk in ("tw", "us"):
        for d in sorted((src / mk).glob("*")) if (src / mk).exists() else []:
            ok, why = need(mk, d.name, today, src)
            if ok and "財報" in why:
                out.append({"mk": mk, "code": d.name, "name": None, "src": "季更新"})
    return out


def queue(today: str, maxn: int = EQ_RUN_MAX, src: Path = SRC, cands: list[dict] | None = None, root: Path = ROOT) -> dict:
    """→ {"d", "max", "todo": [{mk, code, name, src, state}], "skip": [{…, skip}]}；cands 給定＝測試用（不讀申請、頁面、季更新）。"""
    from . import eqinbox as I
    if cands is None:
        cands = requests() + upcoming(today) + (updates(today, src) if date.fromisoformat(today).weekday() == 5 else [])
    todo, skip, seen = [], [], set()
    for c in cands:
        k = (c["mk"], c["code"])
        if k in seen:
            continue
        seen.add(k)
        if c["mk"] == "us" and not I.known("us", c["code"], root):
            skip.append({**c, "skip": "美股資料包做不出來（只有選股頁上有財報資料的那幾檔）"})
            continue
        ok, why = need(c["mk"], c["code"], today, src)
        if not ok:
            skip.append({**c, "skip": why})
        elif len(todo) < maxn:
            todo.append({**c, "state": why})
        else:
            skip.append({**c, "skip": f"今天排不到（每班最多 {maxn} 家），明天再排"})
    return {"d": today, "max": maxn, "todo": todo, "skip": skip}
