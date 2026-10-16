"""超級飆股觀察名單（tw-superstock-lab/reports/W1_plan.md v2；2026-10-16 使用者：「機率不大但名單裡會出現超級飆股的也可以保留，
我還會有自己的主觀判斷」「我要可以翻 2 倍 3 倍甚至是 10–20 倍的股票」）。

名單＝研究選中的合併名單 S9：現行飆股候選（superx A 規則）∪ VCP＋趨勢樣板 ∪ 月營收創歷史新高＋趨勢樣板。
每日名單在 company.market_table 算（只用當天收盤以前的資料）；過去成績來自 data/lab/watch_research.json
（tw-superstock-lab/scripts/run_watch.py → export_watch.py，資料或規格改了才重跑）。只列名單與過去統計，不是買賣訊號。"""
from __future__ import annotations

from . import store
from . import vcp as VC

RES_FILE = "watch_research.json"
TAGS = {"A": "飆股候選", "VCP": "VCP＋樣板", "REV": "營收創新高＋樣板"}


def tags_for(c: str, f: dict, hits: dict, px, i: int) -> list[str]:
    """一檔股票今天屬於合併名單的哪幾份（合格股票才算；f＝superx.feats_on 的特徵）。"""
    if not f.get("el"):
        return []
    out = []
    if hits.get(c):
        out.append("A")
    if f.get("tt_all"):
        r = VC.check(px.h, px.l, px.c, px.v, i)
        if r and r["ok"]:
            out.append("VCP")
        if f.get("rnha") is True:
            out.append("REV")
    return out


def load_res() -> dict | None:
    res = store.read_json(RES_FILE, None)
    return res if res and res.get("v") == 2 else None


def page_data(res: dict | None, watch: dict | None, feats: dict | None = None, names: dict | None = None) -> dict:
    """頁面用：過去成績（合併名單 S9 與對照）、今天名單（[代號, 名稱, 標籤, 收盤, RS, 近 3 月營收年增, 距 52 週高點, 市值]）。"""
    if not res:
        return {}
    cand = []
    for c, tg in sorted((watch or {}).items()):
        r = (feats or {}).get(c) or {}
        cand.append([c, (names or {}).get(c, c), tg, r.get("px"), r.get("rs"), r.get("ry3"), r.get("d52h"), r.get("cap")])
    cand.sort(key=lambda x: (-len(x[2]), -(x[4] or 0)))
    L = res.get("lists") or {}
    return {"v": res.get("v"), "asof": res.get("asof"), "chosen": res.get("chosen"), "missing": res.get("missing") or [],
            "lists": L, "cand": cand, "tags": TAGS}
