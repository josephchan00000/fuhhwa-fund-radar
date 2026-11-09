"""新項目過關每年重驗（使用者 2026-11-09：「沒過的指標每年 1 月重驗」＋「先通知、你說好才換」）。

規格不改（heatspec GATE、heatspec_us 同一套條件 a～d）：用現在的資料重算一次過關判定，和現行過關檔比。
只寫 data/lab/heat_gate_review.json——不改現行過關檔（heat_gate.json、heat_us_gate.json）、不改研究檔，頁面不會自己變。
名單有變、還沒換上時：06:35 推播多一行、研究紀錄・後台「今天的驗證」列出；使用者回「好」才重跑整套研究換上
（scripts/run_heat.py、run_heat_us.py 與下游研究；做法見 wiki/lab/heat-tw.md「新項目過關」）。

每年 1 月由 .github/workflows/gate_review.yml 跑（scripts/run_gate_review.py）；手動也可以跑。
過關判定只用「新項目都不算分」的那一份資料（同 heatcalc.research／heatcalc_us.research 的第一步），不必跑完整研究。
"""
from __future__ import annotations

from datetime import date, datetime
from . import heatspec as S
from . import heatspec_us as U
from . import store

REVIEW_FP = "heat_gate_review.json"     # data/lab/ 底下（store.read_json／write_json）
NOTIFY_DAYS = 30          # 重驗後這麼多天內，名單有變、還沒換上才推播（之後只留在後台）


def _diff(live, new) -> dict:
    live, new = set(live or ()), set(new or ())
    return {"live": sorted(live), "new": sorted(new), "add": sorted(new - live), "drop": sorted(live - new)}


def _items(g: dict) -> dict:
    return {k: {"pass": bool(e["pass"]), "a": e["a"], "b": e["b"], "c": e["c"]} for k, e in (g.get("items") or {}).items()}


def review_tw() -> dict:
    from . import heatcalc as C
    from . import heatgate as G
    B = C.build(adm=())
    g = G.compute(C.with_adm(B, ()))
    return {**_diff(G.admitted(), g["admit"]), "items": _items(g)}


def review_us() -> dict:
    from . import heatcalc_us as CU
    from . import heatgate as G
    D = CU.load()
    sh = CU.shared(D)
    out = {}
    for idx in U.INDEX_ORDER:
        B = CU.build(idx, D, sh, adm=())
        with S.use(U.spec_for(idx)):                      # 同 heatcalc_us.research：先截到驗證起點再判定
            g = G.compute(CU.trim(B, S.VAL_START.get(idx)))
            live = G.admitted(idx)
        out[idx] = {**_diff(live, g["admit"]), "items": _items(g)}
    return out


def changed(doc: dict) -> bool:
    tw = doc.get("tw") or {}
    return bool(tw.get("add") or tw.get("drop") or any(r.get("add") or r.get("drop") for r in (doc.get("us") or {}).values()))


def run(now: datetime) -> dict:
    doc = {"made": now.strftime("%Y-%m-%d"), "ver": {"tw": S.VER, "us": U.VER}, "tw": review_tw(), "us": review_us()}
    doc["changed"] = changed(doc)
    return doc


def _live_now() -> dict:
    """現行過關檔的名單（換上了沒，用它比）。"""
    from . import heatgate as G
    out = {"tw": set(G.admitted())}
    for idx in U.INDEX_ORDER:
        with S.use(U.spec_for(idx)):
            out[idx] = set(G.admitted(idx))
    return out


def state(now: datetime, doc: dict | None = None, live: dict | None = None) -> dict | None:
    """後台與推播用。→ {"d": 重驗日, "changed", "pending": 名單有變而且還沒換上, "push": 要不要推播,
    "tw": {"add","drop"}, "us": {指數: {"add","drop"}}}；沒有重驗檔＝None。"""
    doc = store.read_json(REVIEW_FP, None) if doc is None else doc
    if not isinstance(doc, dict) or "tw" not in doc:
        return None
    d = str(doc.get("made") or "")[:10]
    live = _live_now() if live is None else live
    tw = doc.get("tw") or {}
    us = doc.get("us") or {}
    pend = (set(tw.get("new") or ()) != set(live.get("tw") or ()) and bool(tw.get("add") or tw.get("drop"))) or any(
        set(r.get("new") or ()) != set(live.get(ix) or ()) and bool(r.get("add") or r.get("drop")) for ix, r in us.items())
    try:
        recent = (now.date() - date.fromisoformat(d)).days <= NOTIFY_DAYS
    except ValueError:
        recent = False
    out = {"d": d, "changed": bool(doc.get("changed")), "pending": pend, "push": pend and recent,
           "tw": {k: tw.get(k) or [] for k in ("add", "drop")},
           "us": {ix: {k: r.get(k) or [] for k in ("add", "drop")} for ix, r in us.items() if r.get("add") or r.get("drop")}}
    out["sum"] = summary(out)                             # 後台列出的白話句子
    return out


def _names(ks, ind) -> str:
    nm = {k: n for k, _, n, *_ in ind}
    return "、".join(nm.get(k, k) for k in ks)


def summary(st: dict) -> list[str]:
    """名單變動的白話句子（每個市場一句，例「台股：營收擴散 這次過關」）。"""
    def one(label, r, ind):
        bits = ([f"{_names(r['add'], ind)} 這次過關"] if r["add"] else []) + ([f"{_names(r['drop'], ind)} 不再過關"] if r["drop"] else [])
        return f"{label}：" + "，".join(bits) if bits else None
    out = [one("台股", st["tw"], S.IND)] + [one(U.INDICES.get(ix, {}).get("name", ix), r, U.IND) for ix, r in st["us"].items()]
    return [x for x in out if x]


def push_line(st: dict | None) -> str | None:
    """06:35 推播多一行：重驗後 NOTIFY_DAYS 天內、名單有變而且還沒換上。"""
    if not st or not st.get("push"):
        return None
    m, d = int(st["d"][5:7]), int(st["d"][8:10])
    return (f"新指標年度重驗（{m}/{d}）：" + "；".join(summary(st)) +
            "。回「好」才重跑整套研究換上（明細在研究紀錄・後台）。")
