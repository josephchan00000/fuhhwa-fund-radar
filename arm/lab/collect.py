"""籌碼雷達：落檔驅動（ETF 部位快照＋官方市場分片＋集保週表）。

冪等：每輪只抓「缺的部件」，資料齊的日子零請求——多班次重跑不放大來源站請求。
"""
from __future__ import annotations

import json
import subprocess
import time
from datetime import date, timedelta

from .. import clock, twholidays
from . import market, store

HOLD_FP = store.ROOT / "data" / "etf_holdings.json"
NODATA = "mkt_nodata.json"         # {date: [part,…]}：官方明示查無（休市／早於資料起點）→ 不再重試


# ── ETF 部位快照（pos） ─────────────────────────────────────────────

def _bond_etfs() -> set[str]:
    try:
        from .. import etfwatch
        return {t[0] for t in etfwatch.watch_tuples() if "債" in (t[3] or "")}
    except Exception:                                     # noqa: BLE001
        return {"00986D", "00987D"}


def snaps_from_holdings(doc: dict, *, skip: set[str] | None = None) -> dict:
    """etf_holdings.json → {date: {etf: {"src", "h": {code: [股數, 權重]}, "px": {code: [收盤, 幣別]}}}}。
    當期快照記 cur=True；前一揭露日（prev）只用來補缺、不覆蓋（cur=False）。"""
    skip = skip if skip is not None else _bond_etfs()
    out: dict[str, dict] = {}
    for etf, e in (doc.get("etfs") or {}).items():
        if etf in skip or not isinstance(e, dict):
            continue
        d = e.get("date")
        if d and e.get("holdings"):
            h = {}
            for r in e["holdings"]:
                sid = str(r.get("stock_id") or "").strip()
                if sid and r.get("shares") is not None:
                    h[sid] = [r.get("shares"), r.get("weight")]
            px = {}
            det = e.get("detail") or {}
            if det.get("date") == d:
                for r in det.get("all") or []:
                    sid = str(r.get("stock_id") or "").strip()
                    if sid and r.get("close") is not None:
                        px[sid] = [r.get("close"), r.get("ccy")]
            if h:
                out.setdefault(d, {})[etf] = {"src": e.get("src"), "h": h, "px": px, "cur": True}
        pd, prev = e.get("prev_date"), e.get("prev") or {}
        if pd and prev:
            h = {sid: [v.get("shares"), v.get("weight")] for sid, v in prev.items()
                 if isinstance(v, dict) and v.get("shares") is not None}
            if h:
                out.setdefault(pd, {}).setdefault(etf, {"src": e.get("prev_src"), "h": h,
                                                        "px": {}, "cur": False})
    return out


def names_from_holdings(doc: dict) -> dict[str, str]:
    out = {}
    for e in (doc.get("etfs") or {}).values():
        for r in (e or {}).get("holdings") or []:
            sid, nm = str(r.get("stock_id") or "").strip(), r.get("name")
            if sid and nm and nm != sid:
                out[sid] = nm
        for sid, v in ((e or {}).get("prev") or {}).items():
            if isinstance(v, dict) and v.get("name") and sid not in out:
                out[sid] = v["name"]
    return out


def merge_snaps(snaps: dict) -> int:
    """寫進 pos 分片：當期快照覆蓋同日同 ETF；prev 只補缺。回傳變動分片數。"""
    n = 0
    for d, etfs in sorted(snaps.items()):
        doc = store.read("pos", d) or {"date": d, "etf": {}}
        cur = doc.setdefault("etf", {})
        for etf, ent in etfs.items():
            is_cur = ent.pop("cur", False)
            if is_cur or etf not in cur:
                if not ent.get("px") and etf in cur and cur[etf].get("px"):
                    ent["px"] = cur[etf]["px"]            # 重抓時沒報價 → 沿用既有
                cur[etf] = ent
        if store.write("pos", d, doc):
            n += 1
    return n


def merge_names(new: dict[str, str]) -> None:
    old = store.read_json("names.json", {}) or {}
    old.update(new)
    store.write_json("names.json", old)


def update_pos_from_current() -> int:
    try:
        doc = json.loads(HOLD_FP.read_text(encoding="utf-8"))
    except Exception as e:                                # noqa: BLE001
        market.log(f"讀 etf_holdings.json 失敗：{e}")
        return 0
    merge_names(names_from_holdings(doc))
    return merge_snaps(snaps_from_holdings(doc))


def backfill_pos_from_git() -> int:
    """走 git 歷史裡每一版 etf_holdings.json 回補 pos 分片（CI 需 fetch-depth: 0）。"""
    try:
        shas = subprocess.run(["git", "log", "--reverse", "--format=%H", "--",
                               "data/etf_holdings.json"], cwd=store.ROOT, check=True,
                              capture_output=True, text=True).stdout.split()
    except Exception as e:                                # noqa: BLE001
        market.log(f"git log 失敗：{e}")
        return 0
    market.log(f"git 歷史 etf_holdings.json 共 {len(shas)} 版")
    acc: dict[str, dict] = {}
    names: dict[str, str] = {}
    skip = _bond_etfs()
    for sha in shas:
        try:
            txt = subprocess.run(["git", "show", f"{sha}:data/etf_holdings.json"],
                                 cwd=store.ROOT, check=True, capture_output=True,
                                 text=True).stdout
            doc = json.loads(txt)
        except Exception:                                 # noqa: BLE001
            continue
        names.update(names_from_holdings(doc))
        for d, etfs in snaps_from_holdings(doc, skip=skip).items():
            slot = acc.setdefault(d, {})
            for etf, ent in etfs.items():
                if ent["cur"] or etf not in slot:
                    if not ent.get("px") and etf in slot and slot[etf].get("px"):
                        ent["px"] = slot[etf]["px"]
                    slot[etf] = ent
    merge_names(names)
    n = merge_snaps(acc)
    market.log(f"pos 回補：{len(acc)} 個揭露日、更新 {n} 個分片")
    return n


# ── 官方市場分片（mkt） ─────────────────────────────────────────────

def candidate_days(today: date, n_cal: int) -> list[str]:
    """往回 n_cal 個日曆天內的「可能交易日」（平日、且官方表沒判休市）。新到舊。"""
    out = []
    for i in range(n_cal + 1):
        d = today - timedelta(days=i)
        if d.weekday() >= 5:
            continue
        if twholidays.is_closed(d) is True:
            continue
        out.append(d.isoformat())
    return out


def fill_market(days: list[str], parts_for, *, budget_s: float, today: date,
                verbose: bool = False) -> dict:
    """逐日補缺部件。parts_for(day)->要的部件清單。回傳統計。"""
    t0 = time.time()
    nod = store.read_json(NODATA, {}) or {}
    stat = {"fetched": 0, "nodata": 0, "err": 0, "days": 0}
    recent_cut = (today - timedelta(days=3)).isoformat()   # 近 3 天的查無＝可能尚未公布，不登記
    for d in days:
        if time.time() - t0 > budget_s:
            market.log(f"時間預算用完，停在 {d}（下輪續補）")
            break
        if "q_tw" in (nod.get(d) or []):                     # 主檔查無＝休市日，整天跳過
            continue
        want = [p for p in parts_for(d) if p not in (nod.get(d) or [])]
        doc = store.read("mkt", d) or {"date": d}
        miss = [p for p in want if p not in doc]
        if not miss:
            continue
        stat["days"] += 1
        changed = False
        for p in miss:
            data, st, extra = market.fetch_part(p, d)
            if data:
                doc[p] = data
                if extra:
                    doc.setdefault("idx", {}).update(extra)
                changed = True
                stat["fetched"] += 1
                if verbose:
                    market.log(f"{d} {p} ✓ {len(data)} 檔")
            elif st.startswith("nodata"):
                stat["nodata"] += 1
                if d < recent_cut:
                    nod.setdefault(d, [])
                    if p not in nod[d]:
                        nod[d].append(p)
                if verbose:
                    market.log(f"{d} {p} 查無（{st}）")
                # 主檔查無＝當天休市（或尚未公布）→ 同日其他部件不必再打
                if p in ("q_tw", "i_tw"):
                    break
            else:
                stat["err"] += 1
                market.log(f"{d} {p} ✗ {st}")
        if changed:
            store.write("mkt", d, doc)
    store.write_json(NODATA, {k: sorted(v) for k, v in sorted(nod.items())})
    return stat


def update_tdcc() -> bool:
    last = store.dates("tdcc")
    if last and (clock.today_tw() - date.fromisoformat(last[-1])).days < 6:
        return False
    iso, data = market.fetch_tdcc()
    if not iso or len(data) < 1000:
        return False
    store.write("tdcc", iso, {"date": iso, "s": data})
    market.log(f"TDCC 股權分散表 {iso}：{len(data)} 檔")
    return True


def prune_all(today: date) -> None:
    for k in ("mkt", "pos", "tdcc"):
        store.prune(k, today=today)
