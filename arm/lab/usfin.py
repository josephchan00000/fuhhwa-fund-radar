"""美股個股卡的季報（docs/lab_review_plan.md 第 4 節 (b)(c)）：配置頁美股會出現的股票（手上的、要買的、名單前 20 名），
每一季的營收、毛利、營業利益、淨利、EPS、股東權益，以及流通股數——都是 SEC 第一次公布的數字（資料分支 secfin 存的那一份）。

每週六資料分支的 SEC 財報更新以後跑（.github/workflows/ussx_weekly.yml：USSX_DIR 指到資料分支），寫 data/lab/ussx_fin.json 進 main；
每天建頁時 uscardpage 讀它，配上每天的股價算成長、三率、ROE、本益比、淨值比（只是描述這家公司，不參與選股）。

單季的算法和選股用的同一套（ussxfeat.sec_quarters、first_filed：第四季＝全年 − 前三季，營收取最早公布的項目），
所以第四季的 EPS 是全年減前三季，可能和公司公布的第四季 EPS 差一點。

data/lab/ussx_fin.json：
  {"ver", "made": 台北日期, "sec": 資料分支 SEC 財報抓的日期, "codes": [這一批],
   "s": {代號: {"q": [[季底, 營收公布日, 營收, 毛利, 營業利益, 淨利, EPS, 股東權益]]（金額單位百萬美元；沒有＝null；依季底排）,
               "sh": [[日期, 公布日, 流通股數（百萬股）]]}}}
"""
from __future__ import annotations

import json
from pathlib import Path

from .. import fund_intro as FI
from . import ussxspec as X

ROOT = Path(__file__).resolve().parents[2]
FIN = ROOT / "data" / "lab" / "ussx_fin.json"
VER = 1
NQ = 28              # 留近幾季（本益比和自己過去 5 年比：每一天要近四季 EPS → 20 季＋3 季，多留一年）
LIST_N = 20          # 名單前幾名也算（配置頁每週只列前 5 名，但名單一週內不會變；多算幾檔省得換人時缺）


def _m(v) -> float | None:
    return None if v is None else round(float(v) / 1e6, 3)


def summary(doc: dict) -> dict | None:
    """一家公司的 secfin 存檔 → {"q": [...], "sh": [...]}（見檔頭）；沒有任何一季的營收＝None。"""
    from . import ussxfeat as F
    Q = F.sec_quarters((doc or {}).get("f") or {})
    rev = F.first_filed(Q, X.REV_TAGS, X.REV_EXTRA)
    if not rev:
        return None
    cost = F.first_filed(Q, X.COST_TAGS)
    gp = dict(Q.get("GrossProfit") or {})
    for e, (r, fd) in rev.items():
        if e not in gp and e in cost:
            gp[e] = (r - cost[e][0], max(fd, cost[e][1]))
    M = {k: d for k, d in (("gp", gp), ("oi", Q.get("OperatingIncomeLoss") or {}), ("ni", Q.get("NetIncomeLoss") or {}),
                           ("eps", Q.get("EarningsPerShareDiluted") or {}), ("eq", Q.get("StockholdersEquity") or {}))}
    K = {k: F._ko(d) for k, d in M.items()}

    def val(k: str, e: str):
        d = M[k]
        if e in d:
            return d[e][0]
        from datetime import date
        kk = F._near_o(K[k], date.fromisoformat(e).toordinal(), X.SEC_TOL_D)
        return d[kk][0] if kk is not None else None

    q = []
    for e in sorted(rev)[-NQ:]:
        eps = val("eps", e)
        q.append([e, rev[e][1], _m(rev[e][0]), _m(val("gp", e)), _m(val("oi", e)), _m(val("ni", e)),
                  None if eps is None else round(float(eps), 4), _m(val("eq", e))])
    sh = sorted([e, fd, _m(v)] for e, (v, fd) in (Q.get("EntityCommonStockSharesOutstanding") or {}).items() if v)
    return {"q": q, "sh": sh[-NQ:]}


def codes_for(L: dict) -> list[str]:
    """這一批：配置頁美股會出現的（fund_intro.qm_codes）＋名單前 LIST_N 名。"""
    a, _ = FI.qm_codes(L)
    b = [str(x.get("c") or "") for x in ((L or {}).get("now") or {}).get("list") or []][:LIST_N]
    return list(dict.fromkeys(c for c in a + b if c))


def build(L: dict, made: str | None = None) -> dict:
    """每週紀錄 L → 存檔內容（讀 ussxdata.data_dir() 的 sec/，USSX_DIR 指到資料分支）。"""
    from . import secfin as SF
    out = {}
    for c in codes_for(L):
        x = summary(SF.load(c))
        if x:
            out[c] = x
    if made is None:
        from ..clock import today_tw
        made = today_tw().isoformat()
    return {"ver": VER, "made": made, "sec": (SF.load_meta() or {}).get("asof"), "codes": codes_for(L), "s": out}


def load(path: Path | None = None) -> dict:
    """存檔；版本不同＝沒有。"""
    try:
        doc = json.loads((path or FIN).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if doc.get("ver") == VER else {}


def save(doc: dict, path: Path | None = None) -> bool:
    """內容沒變（made 不算）就不寫；回有沒有寫。"""
    p = path or FIN
    old = load(p)
    if old and {k: v for k, v in old.items() if k != "made"} == {k: v for k, v in doc.items() if k != "made"}:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return True
