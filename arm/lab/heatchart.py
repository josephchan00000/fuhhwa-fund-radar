"""景氣溫度頁第五版：對照圖與交互分析的資料 dashboard/x9mh.json（docs/lab_heat_plan.md 第 14.14 節第 3 點）。

打開頁面後才下載。內容：
  · w：全期間每週一點（每週最後一個交易日）的日期、加權指數、之後 20／60／120／250 日漲跌（t＋1 收盤起算，%）；
  · d：近 260 個交易日每天一點的日期與加權指數；
  · s：5 個面向分數與 44 項的 0～100（取到小數一位）、原始值（4 位有效數字），每週與每天各一份；開頭沒有值的部分不存；
  · an：研究檔的單項分析（滾動相關的週序號換成日期）；dv：邊際變化的驗證結果。
第六版（第 15.11 節）再加：
  · s 的 A_grow、A_rate、A_lev：三組「幾成在加速」（0～100，組內原始二階 > 0 的比例）；
  · m6：13 項與三條組線的延遲反應（L1 係數與重抽區間、判定）與樣本外摘要。
輸出決定性：資料沒變時位元組相同。
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from . import heat as H
from . import heatpos as P
from . import heatreg as RG
from . import heatspec as S

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dashboard" / "x9mh.json"


def sig(v, n: int = 4):
    """4 位有效數字；整數就寫成整數。"""
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return None
    if v == 0:
        return 0
    r = float(f"{v:.{n}g}")
    return int(r) if r.is_integer() and abs(r) < 1e15 else r


def r1(v):
    if v is None:
        return None
    x = round(v, 1)
    return int(x) if x.is_integer() else x


def trim(vals: list) -> dict:
    """開頭沒有值的部分不存：{"o": 第一個有值的位置, "v": 之後的值}；全部沒有值回 {"o": 0, "v": []}。"""
    o = next((i for i, v in enumerate(vals) if v is not None), len(vals))
    return {"o": o, "v": vals[o:]}


def acc_lines(B: dict, d2: dict | None = None) -> dict:
    """三組「幾成在加速」（逐日 0～100）：組內原始二階（第五版 v0，當天拿得到的）> 0 的比例，
    至少 M6_GROUP_MIN 項有值（第 15.11 節第 11 點；和研究的 SH_* 同一個量）。"""
    T = len(B["cal"])
    d2 = d2 if d2 is not None else {k: P.deriv(B, k)["d2"] for k in S.DERIV}
    out = {}
    for g, keys in S.M6_GROUPS.items():
        col = []
        for i in range(T):
            v = [d2[k][i] for k in keys if d2[k][i] is not None]
            col.append(None if len(v) < S.M6_GROUP_MIN[g] else 100.0 * sum(1 for x in v if x > 0) / len(v))
        out[f"A_{g}"] = col
    return out


def _m6_curve(l1: dict) -> dict:
    """L1 → {"d": [[k, b, lo, hi, 判定], ...], "c": [[m, ...], ...]}（係數換成百分點，取到小數兩位）。"""
    pp = lambda x: None if x is None else round(100 * x, 2)                       # noqa: E731
    out = {}
    for part, idx in (("d", 0), ("c", 1)):
        rows = []
        for ws, e in (l1.get(part) or {}).items():
            k = int(ws.split(",")[idx])
            rows.append([k, pp(e.get("b")), pp(e.get("lo")), pp(e.get("hi")), e.get("v"), e.get("n")])
        out[part] = sorted(rows)
    return out


def m6_data(R: dict) -> dict:
    """研究檔的第六版結果 → 對照圖單項分析用的精簡格式。"""
    m6 = R.get("m6") or {}
    out = {}
    for k, e in (m6.get("items") or {}).items():
        oo = {}
        for ws, o in (e.get("oos") or {}).items():
            c = (o.get("cw") or {}).get("m2>m1") or {}
            oo[ws] = [o.get("n"), None if c.get("r2") is None else round(100 * c["r2"], 2),
                      None if c.get("p") is None else round(c["p"], 4), bool(o.get("few"))]
        out[k] = {"first": e.get("first"), "sum": e.get("sum"), "oos": oo, **_m6_curve(e.get("l1") or {})}
    for g in S.M6_GROUPS:
        e = (m6.get("groups") or {}).get(f"SH_{g}")
        if e:
            out[f"A_{g}"] = {"first": e.get("first"), "sum": e.get("sum"), "oos": {}, **_m6_curve(e.get("l1") or {})}
    for v in out.values():
        v["txt"] = RG.react_text(((v.get("sum") or {}).get("react")) or [])
    return out


def build_data(B: dict, R: dict | None = None) -> dict:
    from . import heatpage as HPG                 # 頁面模組也匯入這支；放在函式裡避免循環匯入
    R = R or {}
    if R.get("ver") != S.VER:
        R = {}
    cal, px = B["cal"], B["px"]
    T = len(cal)
    we = P.week_ends(cal)
    dl = list(range(max(0, T - S.CH_DAILY), T))
    w = {"d": [cal[i] for i in we], "px": [r1(px[i]) for i in we],
         "fw": {str(h): [None if (r := H.fwd(px, i, h)[0]) is None else round(100 * r, 2) for i in we] for h in S.REL_H}}
    d = {"d": [cal[i] for i in dl], "px": [r1(px[i]) for i in dl]}
    s = {}
    shown = HPG.shown_dims()                      # 泡沫面向不在景氣頁（另放泡沫頁）
    for dim in shown:
        c = B["comp"][dim]
        s[dim] = {"h": trim([r1(c[i]) for i in we]), "hd": trim([r1(c[i]) for i in dl])}
    for k in [k for d in shown for k in S.ITEMS[d]]:
        h, raw = B["heat"][k], B["raw"][k]
        s[k] = {"h": trim([r1(h[i]) for i in we]), "r": trim([sig(raw[i]) for i in we]),
                "hd": trim([r1(h[i]) for i in dl]), "rd": trim([sig(raw[i]) for i in dl])}
    for sid, col in acc_lines(B).items():
        s[sid] = {"h": trim([r1(col[i]) for i in we]), "hd": trim([r1(col[i]) for i in dl])}
    an = {}
    wk = R.get("wk") or []
    for sid, a in ((R.get("rel") or {}).items()):
        if sid not in s:                          # 不在景氣頁的線（泡沫面向與它的項目）不帶分析
            continue
        a = dict(a)
        a["roll"] = [[wk[j], v] for j, v in a.get("roll") or [] if j < len(wk)]
        an[sid] = a
    return {"ver": S.VER, "asof": cal[-1] if cal else None, "w": w, "d": d, "s": s, "an": an,
            "dv": R.get("deriv") or {}, "m6": m6_data(R)}


def dumps(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def write(data: dict, out: Path = OUT) -> bool:
    text = dumps(data)
    if out.exists() and out.read_text(encoding="utf-8") == text:
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return True
