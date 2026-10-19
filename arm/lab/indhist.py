"""已下市公司的產業別（bubindspec VER 2 第 1b 節；docs/lab_crash_plan.md 第 21.2 節）。

官方歷史分類行情快照：證交所 MI_INDEX（日期＋type＝產業代碼）、櫃買中心 stk_wn1430（日期＋se＝產業代碼）
→ data/lab/indsnap.json {"twse"|"tpex": {日期: {產業代碼: [代號…]}}}（有產業代碼這個鍵＝那一頁抓過了，空清單＝官方查無）。
抓取只在 CI（scripts/backfill_lab.py --ind-hist，可重跑續補）；delisted_map() 只讀檔。
"""
from __future__ import annotations

import re
import threading
import time

from . import bubindspec as BI
from . import store

MARKETS = ("twse", "tpex")
TWSE_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={ymd}&type={t}&response=json"
TPEX_URL = ("https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php"
            "?l=zh-tw&d={roc}&se={t}")
_CODE = re.compile(r"^[1-9]\d{3}$")             # 普通股（00 開頭的 ETF 不收）


def _log(msg: str) -> None:
    print(f"  [indhist] {msg}", flush=True)


def codes_twse(doc) -> list[str]:
    """MI_INDEX 某產業的回應 → 代號（4 碼數字；指數、漲跌統計等表的第一欄不是代號，自然濾掉）。"""
    out = []
    for t in (doc or {}).get("tables") or []:
        for r in t.get("data") or []:
            c = str(r[0]).strip() if r else ""
            if _CODE.match(c) and c not in out:
                out.append(c)
    return sorted(out)


def codes_tpex(doc) -> list[str]:
    rows = (doc or {}).get("aaData") or [r for t in ((doc or {}).get("tables") or []) for r in (t.get("data") or [])]
    out = []
    for r in rows:
        c = str(r[0]).strip() if r else ""
        if _CODE.match(c) and c not in out:
            out.append(c)
    return sorted(out)


def year_firsts(cal: list[str], start: int = BI.IND_HIST_START) -> list[str]:
    """每年第一個交易日（cal 有的年份、start 年起）。"""
    out, seen = [], set()
    for d in cal:
        y = int(d[:4])
        if y >= start and y not in seen:
            seen.add(y)
            out.append(d)
    return out


def month_before_last(cal: list[str], last: str) -> str | None:
    """last 那天之前那個月的最後一個交易日（cal 裡的）。"""
    ym = last[:7]
    prev = [d for d in cal if d[:7] < ym]
    return prev[-1] if prev else None


def load() -> dict:
    S = store.read_json(BI.IND_HIST_FILE, {}) or {}
    return {mk: dict(S.get(mk) or {}) for mk in MARKETS}


def delisted_map(cur: dict) -> dict[str, str]:
    """現在產業表（cur）沒有的代號 → 快照裡最後一次出現的產業別名稱（stockmeta.IND_CODE）。"""
    from arm import stockmeta
    S = load()
    best: dict[str, tuple[str, str]] = {}
    for mk in MARKETS:
        for d, types in S[mk].items():
            for t, codes in types.items():
                name = stockmeta.IND_CODE.get(t)
                if not name or t in BI.IND_HIST_AGG:
                    continue
                for c in codes:
                    if c in cur:
                        continue
                    if c not in best or d > best[c][0]:
                        best[c] = (d, name)
    return {c: v[1] for c, v in sorted(best.items())}


def seen_codes(S: dict | None = None) -> set[str]:
    S = S if S is not None else load()
    return {c for mk in MARKETS for types in S[mk].values() for codes in types.values() for c in codes}


# ── 抓取（CI） ──────────────────────────────────────────────────────────────

def _fetch_one(mk: str, d: str, t: str):
    """→ (代號清單, 狀態)；狀態 ok／nodata／err。"""
    from . import market as M
    if mk == "twse":
        doc, st = M._get(TWSE_URL.format(ymd=M.ymd(d), t=t), sleep=M.UA_SLEEP_TWSE)
        return (codes_twse(doc) if st == "ok" else []), st
    doc, st = M._get(TPEX_URL.format(roc=M.roc(d), t=t), sleep=M.UA_SLEEP_TPEX)
    if st != "ok":
        return [], st
    rd = re.sub(r"\D", "", str((doc or {}).get("date") or ""))
    if len(rd) == 7:
        rd = f"{int(rd[:3]) + 1911}{rd[3:]}"
    if len(rd) == 8 and rd != M.ymd(d):
        return [], "nodata"
    return codes_tpex(doc), "ok"


def _fill(mk: str, dates: list[str], S: dict, lock: threading.Lock, deadline: float, stat: dict) -> None:
    for d in dates:
        with lock:
            types = S[mk].setdefault(d, {})
        for t in BI.IND_HIST_TYPES:
            if t in types:
                continue
            if time.time() > deadline:
                return
            codes, st = _fetch_one(mk, d, t)
            if st in ("ok", "nodata"):
                with lock:
                    types[t] = codes
                    stat[mk] += 1
            else:
                stat[mk + "_err"] += 1
                _log(f"{mk} {d} {t} {st[:120]}")
        with lock:
            store.write_json(BI.IND_HIST_FILE, S)
        _log(f"{mk} {d}：{sum(len(v) for v in types.values())} 檔、{len(types)} 個產業代碼")


def backfill(budget_s: float = 48 * 60) -> dict:
    """年度快照（兩個市場平行、各自的頻率限制）→ 年度快照都找不到的已下市公司補一次快照。可重跑續補。"""
    from arm import stockmeta
    deadline = time.time() + budget_s
    cal = sorted((store.read_json("v3_tr.json", {}) or {}).get("q") or {})
    S = load()
    lock = threading.Lock()
    stat = {"twse": 0, "tpex": 0, "twse_err": 0, "tpex_err": 0}

    def run(dates: list[str]) -> None:
        th = [threading.Thread(target=_fill, args=(mk, dates, S, lock, deadline, stat)) for mk in MARKETS]
        for x in th:
            x.start()
        for x in th:
            x.join()

    run(year_firsts(cal))
    extra = []
    if time.time() < deadline:
        from . import bt3d
        P = bt3d.Panel(start=BI.TW_START)
        cur = stockmeta.industry_map()
        seen = seen_codes(S)
        for c in P.codes:
            caps = [x for x in P.cap[c] if x]
            if not caps or max(caps) < BI.TW_CAP_MIN or c in cur or c in seen:
                continue
            last = max(i for i, x in enumerate(P.s[c]["c"]) if x)
            d = month_before_last(cal, P.cal[last])
            if d and d not in extra:
                extra.append(d)
        _log(f"年度快照找不到的已下市公司要補 {len(extra)} 個日期：{sorted(extra)}")
        run(sorted(extra))
    store.write_json(BI.IND_HIST_FILE, S)
    left = sum(1 for mk in MARKETS for d in S[mk] for t in BI.IND_HIST_TYPES if t not in S[mk][d])
    out = {**stat, "dates": {mk: len(S[mk]) for mk in MARKETS}, "extra": len(extra), "left": left,
           "delisted": len(delisted_map(stockmeta.industry_map()))}
    _log(f"結果 {out}")
    return out
