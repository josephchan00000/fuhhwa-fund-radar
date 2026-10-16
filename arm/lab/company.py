"""公司分析（docs/lab_company_plan.md 第 3.3、3.4、5 節）。

使用者 2026-10-16：「變成點進去公司後可以跑公司的分析（可以不用先跑好這樣太浪費用量）」。
  · 每檔一個資料檔 dashboard/co/{代號}.json：每季財報、每月營收與月底股價、股利（每月、每季才變；內容沒變不改寫）。
  · 全市場每日小表 dashboard/x9t.json：五面向的全市場百分位、飆股體質檢查的技術面、飆股候選。
  · 分析本身（比率、走勢、估值位置、拆解、檢查表）在瀏覽器打開那一檔時才算（page.py 的 co* 函式）。
"""
from __future__ import annotations

import json
from pathlib import Path

from . import store

ROOT = Path(__file__).resolve().parents[2]
CO_DIR = ROOT / "dashboard" / "co"
OUT_T = ROOT / "dashboard" / "x9t.json"
CO_VER = 1
# 每季欄位（損益為單季）：金額存百萬元一位小數、EPS 與每股淨值兩位
QK = ("rev", "gp", "opex", "op", "nonop", "pti", "nip", "eps", "ca", "ta", "cl", "tl", "eqp", "bvps", "ocf", "icf", "cash")
PER_SHARE = {"eps", "bvps"}


def is_stock(c: str) -> bool:
    return len(c) == 4 and c.isdigit() and not c.startswith("0")


def _amt(v):
    return None if v is None else round(v / 1000, 1)


def _trim(row: list) -> list:
    while row and row[-1] is None:
        row.pop()
    return row


def listed_now() -> dict[str, str]:
    """最新月底快照裡的上市（tw）／上櫃（tp）普通股 → 市場。"""
    out: dict[str, str] = {}
    for kind, mk in (("v3me_tw", "tw"), ("v3me_tp", "tp")):
        got = store.load(kind, last=1)
        if got:
            for c in (got[-1][1].get("s") or {}):
                if is_stock(c):
                    out[c] = mk
    return out


def month_px() -> dict[str, dict[str, tuple]]:
    """{代號: {YYYY-MM: (月底收盤, 股數)}}（上市＋上櫃，2013 起）。"""
    out: dict[str, dict] = {}
    for kind in ("v3me_tw", "v3me_tp"):
        for ym, doc in store.load(kind):
            for c, v in (doc.get("s") or {}).items():
                if v and v[0]:
                    out.setdefault(c, {})[ym] = (v[0], v[1] if len(v) > 1 else None)
    return out


def _fm_cash() -> dict[str, dict[str, float]]:
    """FinMind 股利政策（data/lab/fin，高股息研究抓過的約 470 檔）→ {代號: {現金除息日: 現金股利}}。"""
    out: dict[str, dict] = {}
    for c, doc in store.load("fin"):
        for r in (doc or {}).get("div") or []:
            if len(r) >= 2 and r[0] and r[1]:
                out.setdefault(c, {})[r[0]] = r[1]
    return out


def dividends() -> dict[str, list]:
    """{代號: [[除權息日, 現金股利(元/股) 或 None, 類型]]}：上市＝證交所除權息計算結果表（息／權／權息；權息的
    金額含配股價值、現金部分表上沒有 → 用 FinMind 股利政策補，沒有就 None），上櫃＝櫃買除權息（現金欄）。"""
    out: dict[str, list] = {}
    fm = _fm_cash()
    for y, doc in store.load("divtw"):
        for r in doc.get("rows") or []:
            if len(r) >= 4 and is_stock(r[1]):
                cash = (round(r[2], 4) if r[3] == "息" and r[2] is not None else 0 if r[3] == "權"
                        else (fm.get(r[1]) or {}).get(r[0]))
                out.setdefault(r[1], []).append([r[0], cash, r[3]])
    for y, doc in store.load("v3div"):
        for r in doc.get("rows") or []:
            if len(r) >= 6 and is_stock(r[1]):
                cash, stk = r[4], r[5]
                out.setdefault(r[1], []).append([r[0], round(cash, 4) if cash is not None else None, "權息" if cash and stk else ("權" if stk else "息")])
    return {c: sorted(v) for c, v in out.items()}


def names() -> dict[str, str]:
    return {**(store.read_json("names_hist.json", {}) or {}), **(store.read_json("names_mkt.json", {}) or {}),
            **(store.read_json("names.json", {}) or {})}


def quarters(fs: dict, eps_fb: dict) -> dict[str, dict]:
    """單季財報（fsq）；fsq 沒有的季用 v3isq 的 EPS 補（舊資料只有 EPS）。"""
    out = {q: dict(v) for q, v in (fs or {}).items()}
    for q, e in (eps_fb or {}).items():
        out.setdefault(q, {}).setdefault("eps", e)
    return out


def fy_eps() -> dict[str, dict[str, float]]:
    """全年 EPS（年報第四季累計值，不用四季相加——各季的累計值事後可能重編）：fsq 為主、v3isq 補。"""
    out: dict[str, dict] = {}
    for key, doc in store.load("v3isq"):
        if key.endswith("Q4"):
            for m in ("sii", "otc"):
                for c, v in (doc.get(m) or {}).items():
                    out.setdefault(c, {})[key[:4]] = v
    for key, doc in store.load("fsq"):
        if key.endswith("Q4"):
            for m in ("sii", "otc"):
                for c, d in (doc.get(f"is_{m}") or {}).items():
                    if d.get("eps") is not None:
                        out.setdefault(c, {})[key[:4]] = d["eps"]
    return out


def co_doc(c: str, mk: str, nm: str, ind: str, qs: dict, rv: dict, mp: dict, dv: list, ye: dict | None = None) -> dict:
    qrows = []
    for q in sorted(qs):
        d = qs[q]
        row = [q] + [(round(d[k], 2) if k in PER_SHARE else _amt(d[k])) if d.get(k) is not None else None for k in QK]
        if any(x is not None for x in row[1:]):
            qrows.append(_trim(row))
    yms = sorted(set(rv) | set(mp))
    mo = []
    for ym in yms:
        px, sh = mp.get(ym, (None, None))
        mo.append(_trim([ym, _amt(rv.get(ym)), px, round(sh / 1000) if sh else None]))
    return {"v": CO_VER, "c": c, "n": nm, "mk": mk, "ind": ind, "qk": list(QK), "q": qrows, "mo": mo,
            "dv": dv[-40:], "ye": {y: round(v, 2) for y, v in sorted((ye or {}).items())},
            "asof": {"q": qrows[-1][0] if qrows else None, "mo": yms[-1] if yms else None}}


def build_co(out_dir: Path = CO_DIR) -> dict:
    """寫 dashboard/co/{代號}.json（內容沒變不改寫）＋ co/index.json（代號、名稱、市場，給「查公司」搜尋用）。"""
    from .. import stockmeta
    from . import bt3d, v3data
    from . import packtest as PT
    lst = listed_now()
    if not lst:
        return {"err": "沒有月底快照"}
    fs = v3data.load_fs()
    eps = bt3d.mops_quarterly()
    rev = PT.load_rev()
    mp = month_px()
    dv = dividends()
    nm = names()
    ind = stockmeta.industry_map()
    ye = fy_eps()
    out_dir.mkdir(parents=True, exist_ok=True)
    st = {"n": 0, "write": 0}
    idx = []
    for c in sorted(lst):
        doc = co_doc(c, lst[c], nm.get(c, c), ind.get(c, ""), quarters(fs.get(c), eps.get(c)), rev.get(c) or {},
                     mp.get(c) or {}, dv.get(c) or [], ye.get(c))
        st["n"] += 1
        idx.append([c, nm.get(c, c), lst[c]])
        if _write_if_changed(out_dir / f"{c}.json", _dump(doc)):
            st["write"] += 1
    _write_if_changed(out_dir / "index.json", _dump({"v": CO_VER, "s": idx}))
    keep = {f"{c}.json" for c in lst} | {"index.json"}
    for p in out_dir.glob("*.json"):                       # 已下市的移除
        if p.name not in keep:
            p.unlink()
    return st


def _dump(x) -> str:
    return json.dumps(x, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _write_if_changed(path: Path, text: str) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


# ── 全市場每日小表 x9t.json ──────────────────────────────────────────────────
# 頁面依 cols 的名稱取值；頁面用到的欄位都要在這裡（tests/test_company.py 守）
TCOLS = ("px", "ch", "cap", "tt", "rs", "d52h", "r120", "ry", "ry3", "racc", "rnh", "ey", "eacc", "gm", "gmd",
         "om", "omd", "c33", "roe", "pe", "pb", "yld", "dr", "cr", "liq", "el", "ttb")


def _pct(x, d=1):
    return None if x is None else round(x * 100, d)


def market_table(DL, today_ix: int | None = None, rules: list | None = None) -> dict:
    """最新交易日全市場：飆股特徵（superx，與研究同一套）＋估值與體質 → {"d", "cols", "rows": {代號: [...]}}。
    rules＝研究定案的規則（[(代號, [條件…])]）→ 另回 "hits"：{代號: [規則序號]}（只算研究樣本條件內的股票）。
    市值：合格判斷用最近月底快照（同研究）；表上的市值欄用當天收盤 × 發行股數。
    一年價格不夠算技術面的股票（多半是 40 億以下的小股票）只放基本面欄位。"""
    import bisect
    from . import bt3d, v3data
    from . import packtest as PT
    from . import superx as SX
    lst = listed_now()
    iss = DL.issued()
    P = PT.Px(DL, [c for c in sorted(lst) if c in iss], iss)
    cal = P.cal
    i = len(cal) - 1 if today_ix is None else today_ix
    while i > 0 and not any((P.s[c]["c"][i] for c in P.codes[:200])):
        i -= 1                                           # 最後一天還沒有官方收盤 → 往前一天
    snaps = bt3d.month_end_caps()
    sd = [d for d, _ in snaps]
    k_me = bisect.bisect_right(sd, cal[i]) - 1
    for c in P.codes:                                    # 合格判斷的市值口徑同研究（最近月底快照）
        P.cap[c] = [None] * len(cal)
        P.cap[c][i] = snaps[k_me][1].get(c) if k_me >= 0 else None
    pxs = {c: SX.Px(P.s[c], cal) for c in P.codes}
    fs = v3data.load_fs()
    eps = bt3d.mops_quarterly()
    rev = PT.load_rev()
    funds = {c: SX.Fund(quarters(fs.get(c), eps.get(c)), rev.get(c) or {}) for c in P.codes}
    qs, rf = SX.avail_index(cal)
    qitems = sorted((t, q) for q, t in qs.items())
    F = SX.feats_on(i, P, pxs, funds, qitems, rf, all_rows=True)
    q = SX.latest_q(qitems, i)
    kr = bisect.bisect_right([t for t, _ in rf], i) - 1
    ym = rf[kr][1] if kr >= 0 else None
    for c in P.codes:                                    # 技術面算不出來的：只放基本面
        if c in F:
            continue
        fd = funds[c]
        f = {"cap": P.cap[c][i], "liq": P.liq[c][i], "el": False}
        f.update(fd.m_feats(ym if ym in fd.rv else None))
        f.update(fd.q_feats(q if q in fd.fq else None))
        F[c] = f
    dv = dividends()
    from datetime import date, timedelta
    d0 = (date.fromisoformat(cal[i]) - timedelta(days=365)).isoformat()
    rows = {}
    for c, f in F.items():
        s = P.s[c]
        px, p0 = s["c"][i], s["c"][i - 1] if i > 0 else None
        fq = funds[c].fq
        qq = sorted(x for x in fq if q is None or x <= q)
        e4 = [fq[x].get("eps") for x in qq[-4:]] if len(qq) >= 4 else []
        ttm = sum(e4) if len(e4) == 4 and all(v is not None for v in e4) else None
        last = fq[qq[-1]] if qq else {}
        bv, ta, tl, ca, cl = (last.get(k) for k in ("bvps", "ta", "tl", "ca", "cl"))
        cash = sum(x[1] for x in dv.get(c, []) if x[0] >= d0 and x[0] <= cal[i] and x[1])
        cap_now = px * iss[c] if px and iss.get(c) else None
        rows[c] = [round(px, 2) if px else None, _pct(px / p0 - 1, 2) if px and p0 else None,
                   round(cap_now / 1e8, 1) if cap_now else None, f.get("tt_n"), f.get("rs"),
                   _pct(f.get("d52h")), _pct(f.get("r120")), _pct(f.get("ry")), _pct(f.get("ry3")),
                   _pct(f.get("racc")), f.get("rnh12"), _pct(f.get("ey")), _pct(f.get("eacc")), _pct(f.get("gm")),
                   _pct(f.get("gmd")), _pct(f.get("om")), _pct(f.get("omd")), f.get("c33"), _pct(f.get("roe")),
                   round(px / ttm, 1) if px and ttm and ttm > 0 else None,
                   round(px / bv, 2) if px and bv and bv > 0 else None,
                   _pct(cash / px, 2) if px and cash else None,
                   _pct(tl / ta) if tl is not None and ta else None,
                   round(ca / cl, 2) if ca is not None and cl else None,
                   round(f["liq"] / 1e8, 2) if f.get("liq") else None, f.get("el"),
                   "".join("1" if x else "0" for x in f.get("tt") or [])]
    hits: dict = {}
    for n, conds in enumerate(rules or []):
        pr = SX.rule_pred([tuple(x) for x in conds])
        for c, f in F.items():
            if f.get("el") and pr(f):
                hits.setdefault(c, []).append(n)
    return {"d": cal[i], "cols": list(TCOLS), "rows": rows, "q": q, "ym": ym, "hits": hits}


def write_table(tab: dict, out: Path = OUT_T) -> bool:
    out.parent.mkdir(parents=True, exist_ok=True)
    return _write_if_changed(out, _dump(tab))
