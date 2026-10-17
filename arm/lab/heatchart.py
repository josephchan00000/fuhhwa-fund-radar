"""景氣溫度頁第五版：對照圖與交互分析的資料 dashboard/x9mh.json（docs/lab_heat_plan.md 第 14.14 節第 3 點）。

打開頁面後才下載。內容：
  · w：全期間每週一點（每週最後一個交易日）的日期、加權指數、之後 20／60／120／250 日漲跌（t＋1 收盤起算，%）；
  · d：近 260 個交易日每天一點的日期與加權指數；
  · s：5 個面向分數與 44 項的 0～100（取到小數一位）、原始值（4 位有效數字），每週與每天各一份；開頭沒有值的部分不存；
  · an：研究檔的單項分析（滾動相關的週序號換成日期）；dv：邊際變化的驗證結果。
輸出決定性：資料沒變時位元組相同。
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from . import heat as H
from . import heatpos as P
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


def build_data(B: dict, R: dict | None = None) -> dict:
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
    for dim in S.DIMS:
        c = B["comp"][dim]
        s[dim] = {"h": trim([r1(c[i]) for i in we]), "hd": trim([r1(c[i]) for i in dl])}
    for k in S.KEYS:
        h, raw = B["heat"][k], B["raw"][k]
        s[k] = {"h": trim([r1(h[i]) for i in we]), "r": trim([sig(raw[i]) for i in we]),
                "hd": trim([r1(h[i]) for i in dl]), "rd": trim([sig(raw[i]) for i in dl])}
    an = {}
    wk = R.get("wk") or []
    for sid, a in ((R.get("rel") or {}).items()):
        a = dict(a)
        a["roll"] = [[wk[j], v] for j, v in a.get("roll") or [] if j < len(wk)]
        an[sid] = a
    return {"ver": S.VER, "asof": cal[-1] if cal else None, "w": w, "d": d, "s": s, "an": an,
            "dv": R.get("deriv") or {}}


def dumps(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def write(data: dict, out: Path = OUT) -> bool:
    text = dumps(data)
    if out.exists() and out.read_text(encoding="utf-8") == text:
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return True
