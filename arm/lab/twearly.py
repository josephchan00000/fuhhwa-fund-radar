"""台股早年官方每日行情（docs/lab_earnings_plan.md 第 14 節第 1 段）：廣度往前補到 2004 年要的原料。只在 CI 抓（本容器擋證交所、櫃買）。

  證交所 MI_INDEX（全部上市股票）：2004-02-11～2013-12-31 每個交易日的收盤與「漲跌價差」（帶正負，和除權息參考價比）
  證交所 MI_QFIIS：每個月最後一個交易日的發行股數（月底市值＝月底收盤 × 發行股數）
  櫃買 dailyQuotes（全部上櫃股票）：2008-01-02～2013-12-31 每個交易日的收盤、漲跌、發行股數（月底那天留發行股數）
參考價＝收盤 − 漲跌價差；和前一天收盤不一樣的那天＝除權息（或減資、分割），還原收盤由這個比例接起來（第 2 段算）。

存檔 data/lab/early/{tw|tp}-{年}.json.gz（store kind "early"，不會被 prune）：
  {"t": [交易日], "c": {代號: [收盤或 null]}, "g": {代號: [漲跌價差或 null（null＝沒有比價，例如 X）]}, "sh": {交易日: {代號: 發行股數}}（只有月底）,
   "ex": {除權息日: {代號: 參考價}}（官方除權息表，每年抓一次；brearlyspec VER 2）,
   "miss": [抓過但查無資料的平日（休市）], "err": {日期: 原因}}
可以重跑續補：已經有的日期跳過；時間到就停，下一輪接著抓。
"""
from __future__ import annotations

import time
from datetime import date, timedelta

from . import market as MK
from . import store

KIND = "early"
TW_START, TP_START, END = "2004-02-11", "2008-01-02", "2013-12-31"     # 2013 年給接上現有廣度用（brearlyspec 第 5 點）


def _num(x) -> float | None:
    s = MK._TAG.sub("", str(x if x is not None else "")).replace(",", "").strip()
    if not s or s in ("--", "---", "X", "除權", "除息", "除權息"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_tw(doc) -> dict:
    """MI_INDEX → {代號: [收盤, 漲跌價差（帶正負）或 None]}。"""
    out: dict[str, list] = {}
    for fields, rows in MK.tables(doc):
        ci, cc = MK.col(fields, "證券代號"), MK.col(fields, "收盤價")
        cs, cd = MK.col(fields, "漲跌(+/-)"), MK.col(fields, "漲跌價差")
        if ci is None or cc is None or cd is None:
            continue
        for r in rows:
            c = MK._TAG.sub("", str(r[ci])).strip()
            if not MK.CODE_RE.match(c):
                continue
            close = _num(r[cc])
            if close is None:
                continue
            sign = MK._TAG.sub("", str(r[cs])).strip() if cs is not None else ""
            dv = _num(r[cd])
            if sign == "X" or dv is None:
                g = None
            elif sign == "-":
                g = -abs(dv)
            elif sign == "+":
                g = abs(dv)
            else:
                g = 0.0 if dv == 0 else None
            out[c] = [close, g]
    return out


def parse_tp(doc) -> dict:
    """櫃買 dailyQuotes → {代號: [收盤, 漲跌（帶正負）或 None, 發行股數或 None]}。"""
    out: dict[str, list] = {}
    for fields, rows in MK.tables(doc):
        if fields:
            ci, cc, cg, cs = MK.col(fields, "代號"), MK.col(fields, "收盤"), MK.col(fields, "漲跌"), MK.col(fields, "發行股數")
        else:
            ci, cc, cg, cs = 0, 2, 3, None
        if ci is None or cc is None:
            continue
        for r in rows:
            c = MK._TAG.sub("", str(r[ci])).strip()
            if not MK.CODE_RE.match(c):
                continue
            close = _num(r[cc])
            if close is None:
                continue
            g = _num(r[cg]) if cg is not None and cg < len(r) else None
            sh = MK._int(r[cs]) if cs is not None and cs < len(r) else None
            out[c] = [close, g, sh]
    return out


def _weekdays(a: str, z: str) -> list[str]:
    d, e, out = date.fromisoformat(a), date.fromisoformat(z), []
    while d <= e:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _load(m: str, y: int) -> dict:
    return store.read(KIND, f"{m}-{y}") or {"t": [], "c": {}, "g": {}, "sh": {}, "miss": [], "err": {}}


def _put(doc: dict, d: str, q: dict) -> None:
    """一天的資料放進欄式（日期照順序插入）。"""
    t = doc["t"]
    k = 0
    while k < len(t) and t[k] < d:
        k += 1
    t.insert(k, d)
    for c in doc["c"]:
        doc["c"][c].insert(k, None)
        doc["g"][c].insert(k, None)
    for c, row in q.items():
        if c not in doc["c"]:
            doc["c"][c] = [None] * len(t)
            doc["g"][c] = [None] * len(t)
        doc["c"][c][k] = row[0]
        doc["g"][c][k] = row[1]


def month_ends(doc: dict, days: list[str]) -> dict[str, str]:
    """資料齊了的月份（那個月每個平日都抓過或查無）→ 那個月最後一個有資料的交易日。"""
    done = set(doc["t"]) | set(doc["miss"])
    out = {}
    for ym in sorted({d[:7] for d in doc["t"]}):
        wk = [d for d in days if d[:7] == ym]
        if wk and all(d in done for d in wk):
            out[ym] = max(d for d in doc["t"] if d[:7] == ym)
    return out


def _finish(m: str, doc: dict, days: list[str], t0: float, budget_s: float) -> bool:
    """收尾：月底發行股數。上市＝月底那天另外抓 MI_QFIIS；上櫃＝行情裡就有，只留月底那天（還沒齊的月份先留著）。"""
    me = month_ends(doc, days)
    keep = set(me.values())
    dirty = False
    if m == "tp":
        open_m = {d[:7] for d in doc["t"]} - set(me)
        for d in list(doc["sh"]):
            if d not in keep and d[:7] not in open_m:
                del doc["sh"][d]
                dirty = True
        return dirty
    for ym, d in me.items():
        if d in doc["sh"] or time.time() - t0 > budget_s:
            continue
        sh, st = fetch_tw_shares(d)
        if sh:
            doc["sh"][d] = sh
            doc["err"].pop(d, None)
        else:
            doc["err"][d] = f"發行股數：{st}"
        dirty = True
    return dirty


def fetch_tw(d: str):
    doc, st = MK._get(MK.TWSE["mi_index"].format(ymd=MK.ymd(d)), sleep=MK.UA_SLEEP_TWSE)
    if st != "ok":
        return None, st
    q = parse_tw(doc)
    return (q, "ok") if len(q) >= 100 else (None, "nodata" if not q else f"err:只有 {len(q)} 檔")


def fetch_tw_shares(d: str):
    q, st, _ = MK.fetch_part("x_tw", d)
    return ({c: v[1] for c, v in (q or {}).items() if v and v[1]}, st)


def fetch_tp(d: str):
    last = "err:無候選"
    for tmpl in MK.TPEX["quotes"]:
        doc, st = MK._get(tmpl.format(roc=MK.roc(d), ad=MK.ad(d)), sleep=MK.UA_SLEEP_TPEX)
        if st != "ok":
            last = st
            continue
        bad = MK.tpex_date_mismatch(doc, d)
        if bad:
            last = bad
            continue
        q = parse_tp(doc)
        if len(q) >= 100:
            return q, "ok"
        last = "err:解析不到"
    return None, ("nodata" if last.startswith("nodata") else last)


def fetch_div(m: str, y: int) -> dict | None:
    """那一年的官方除權息表 → {除權息日: {代號: 參考價}}（brearlyspec VER 2 第 2 點；抓不到＝None，下一輪再抓）。"""
    rows = MK.twse_exright_year(y) if m == "tw" else MK.tpex_exright_year(y)
    if not rows:
        return None
    out: dict[str, dict] = {}
    for r in rows:
        d, c = r[0], r[1]
        ref = r[5] if m == "tw" else r[3]                  # 證交所：[日, 代號, 權值+息值, 權/息, 前收, 參考價]；櫃買：[日, 代號, 前收, 參考價, …]
        if d and c and isinstance(ref, (int, float)) and ref > 0:
            out.setdefault(d, {})[c] = ref
    return out


def run(budget_s: float = 9000, mkts: tuple[str, ...] = ("tw", "tp")) -> dict:
    """抓還沒有的日子；時間到就存檔停下（下一輪接著抓）。回統計。"""
    t0 = time.time()
    stat: dict = {}
    for m in mkts:
        a = TW_START if m == "tw" else TP_START
        days = _weekdays(a, END)
        got = {"ok": 0, "miss": 0, "err": 0, "left": 0}
        for y in range(int(a[:4]), int(END[:4]) + 1):
            doc = _load(m, y)
            have = set(doc["t"]) | set(doc["miss"])
            todo = [d for d in days if d[:4] == str(y) and d not in have]
            dirty = False
            for d in todo:
                if time.time() - t0 > budget_s:
                    got["left"] += 1
                    continue
                q, st = (fetch_tw if m == "tw" else fetch_tp)(d)
                if q:
                    _put(doc, d, {c: v[:2] for c, v in q.items()})
                    if m == "tp":
                        doc["sh"][d] = {c: v[2] for c, v in q.items() if len(v) > 2 and v[2]}
                    doc["err"].pop(d, None)
                    got["ok"] += 1
                elif st.startswith("nodata"):
                    doc["miss"].append(d)
                    got["miss"] += 1
                else:
                    doc["err"][d] = st[:120]
                    got["err"] += 1
                dirty = True
                if q and got["ok"] % 40 == 0:                # 中途存一下（時間到被砍也不會白抓）
                    store.write(KIND, f"{m}-{y}", doc)
            dirty = _finish(m, doc, days, t0, budget_s) or dirty
            if doc["t"] and "ex" not in doc and time.time() - t0 <= budget_s:      # 除權息表（brearlyspec VER 2）
                ex = fetch_div(m, y)
                if ex is not None:
                    doc["ex"] = ex
                    dirty = True
            if dirty:
                doc["miss"] = sorted(set(doc["miss"]))
                store.write(KIND, f"{m}-{y}", doc)
        stat[m] = got
        MK.log(f"[早年行情] {m}：這一輪 {got}")
    return stat


def coverage() -> dict:
    """每年有幾個交易日、幾檔、幾個月底有發行股數、還有幾個錯誤。"""
    out = {}
    for m, a in (("tw", TW_START), ("tp", TP_START)):
        for y in range(int(a[:4]), int(END[:4]) + 1):
            doc = store.read(KIND, f"{m}-{y}")
            if not doc:
                out[f"{m}-{y}"] = None
                continue
            out[f"{m}-{y}"] = {"days": len(doc["t"]), "codes": len(doc["c"]), "me": len(doc["sh"]), "miss": len(doc["miss"]),
                               "err": len(doc["err"]), "first": doc["t"][0] if doc["t"] else None, "last": doc["t"][-1] if doc["t"] else None}
    return out

