"""W5：《超級績效》VCP 參數查核——命中率低是不是參數設錯（reports/W5_plan.md，跑之前寫定）。

    .venv/bin/python -u scripts/run_w5.py            讀 W3 快取（週末交易日、名單 S9）＋ lab 面板
                                                     → reports/W5_results.{md,json}＋匯出頁面摘要
    .venv/bin/python -u scripts/run_w5.py --export   只把 W5_results.json 的摘要併進 ../data/lab/layer_research.json
"""

from __future__ import annotations

import json
import math
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from superstock import features as FT  # noqa: E402
from superstock import labpanel as LP  # noqa: E402

REPORTS = ROOT / "reports"
CACHE = ROOT / "data" / "cache" / "w3_table.pkl"
PER = {"IS": ("2014-01-01", "2019-12-31"), "VAL": ("2020-01-01", "2022-12-31"), "HO": ("2023-01-01", "2099-12-31")}
PNAME = {"IS": "2014–2019", "VAL": "2020–2022", "HO": "2023 起（參考）"}
LABS = {"B": (250, 1.0), "A": (60, 0.5)}
VARS = {
    "V2": FT.VCP_V2,
    "V3": FT.VCP_V3,
    "V3s": FT.VCP_V3S,
    "V2+1": {**FT.VCP_V2, "grow": 1.0},
    "V2+2": {**FT.VCP_V2, "rise": True},
    "V2+3": {**FT.VCP_V2, "upper": 0.5},
    "V2+4": {**FT.VCP_V2, "below": True},
}
VNAME = {"TT": "樣板股", "V2": "V2 現行", "V3": "V3 照書修正", "V3s": "V3s（基底 15 日）", "V2+1": "V2＋①嚴格收縮",
         "V2+2": "V2＋②低點墊高", "V2+3": "V2＋③最後一段在上半部", "V2+4": "V2＋④還沒突破"}
FLOOR_STATE, FLOOR_EVENT = 50, 30
DEDUP, BRK_VOL, BUY = 20, 1.5, 0.05
T0 = time.time()


def log(msg: str) -> None:
    print(f"{msg}（{time.time() - T0:.0f} 秒）", flush=True)


def wilson(pos: int, n: int, z: float = 1.96):
    if not n:
        return None, None
    p = pos / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - r) / d, (c + r) / d


def shift1(x: np.ndarray, fill):
    out = np.empty_like(x)
    out[0] = fill
    out[1:] = x[:-1]
    return out


def dedup(E: np.ndarray, gap: int = DEDUP) -> np.ndarray:
    """同一檔 gap 個交易日內只留第一次（相對上一次留下的）。"""
    out = np.zeros_like(E)
    for j in np.flatnonzero(E.any(axis=0)):
        last = -10 ** 9
        for t in np.flatnonzero(E[:, j]):
            if t - last > gap:
                out[t, j] = True
                last = t
    return out


def stat(mask: np.ndarray, Y: dict, und: np.ndarray, weeks: int | None = None) -> dict:
    """mask（列已限定期間）→ 每個標籤的 n、命中、比例、Wilson 區間；檔數；H 的「都沒碰到」比例。"""
    out = {"n": int(mask.sum()), "stocks": int(mask.any(axis=0).sum())}
    if weeks:
        out["per_week"] = out["n"] / weeks
    for L, y in Y.items():
        v = y[mask]
        v = v[~np.isnan(v)]
        pos = int(v.sum())
        lo, hi = wilson(pos, len(v))
        out[L] = {"n": int(len(v)), "pos": pos, "p": pos / len(v) if len(v) else None, "lo": lo, "hi": hi}
    u = und[mask]
    out["H_und"] = float(u.mean()) if u.size else None
    return out


def main() -> None:
    m, extra = LP.load()
    log("[w5] 面板")
    F = FT.compute(m, extra["cap"], FT.VCP_V2)
    log("[w5] 合格、樣板、V2")
    cal = [d.strftime("%Y-%m-%d") for d in m.dates]
    tb = pickle.load(open(CACHE, "rb"))
    assert tb["cal"] == cal and list(tb["stocks"]) == list(m.stocks), "W3 快取和面板對不上"
    W = np.array(tb["W"], dtype=int)
    S9w = tb["S9w"].astype(bool)
    wd = np.array([cal[i] for i in W])
    el, tt = F["elig"], F["tt_pass"] & F["elig"]
    Y = {L: FT.label(m, n, g, F["elig"]) for L, (n, g) in LABS.items()}
    Y["H"], und = FT.race(m, 0.20, 0.08, 120, F["elig"])
    log("[w5] 標籤")
    Yw = {L: y[W] for L, y in Y.items()}
    undw = und[W]
    dates = np.array(cal)
    pr = {k: ((wd >= a) & (wd <= b), (dates >= a) & (dates <= b)) for k, (a, b) in PER.items()}
    nweeks = {k: int(pr[k][0].sum()) for k in PER}

    def state_stats(G: np.ndarray) -> dict:
        return {k: stat(G & pr[k][0][:, None], Yw, undw, nweeks[k]) for k in PER}

    def event_stats(E: np.ndarray) -> dict:
        return {k: stat(E & pr[k][1][:, None], Y, und) for k in PER}

    res = {"plan": "reports/W5_plan.md", "asof": cal[-1], "state": {}, "event": {}}
    res["state"]["ALL"] = state_stats(el[W])
    res["state"]["TT"] = state_stats(tt[W])
    res["state"]["S9"] = state_stats(S9w)
    res["event"]["TT_days"] = event_stats(tt)
    c, vol = m.c, m.vol
    v50p = shift1(F["vol50"], np.nan)
    with np.errstate(invalid="ignore"):
        volok = vol >= BRK_VOL * v50p
        h20 = pd.DataFrame(m.h).rolling(20, min_periods=15).max().shift(1).to_numpy()
        gen = (c > h20) & (c <= h20 * (1 + BUY)) & volok & tt
    res["event"]["GEN"] = event_stats(dedup(gen))
    log("[w5] 對照組")
    for k, sp in VARS.items():
        if k == "V2":
            ok, piv = F["vcp_ok"], F["vcp_pivot"]
        else:
            r = FT.vcp(m, el, F["dry"], sp)
            ok, piv = r["ok"], r["pivot"]
        G = ok[W] & tt[W]
        res["state"][k] = state_stats(G)
        res["state"][k + "_new"] = state_stats(G & ~shift1(G, False))
        okp, pivp = shift1(ok, False), shift1(piv, np.nan)
        with np.errstate(invalid="ignore"):
            E = okp & (c > pivp) & (c <= pivp * (1 + BUY)) & volok & tt
        res["event"][k] = event_stats(dedup(E))
        log(f"[w5] {k}")
    res["judge"] = judge(res)
    (REPORTS / "W5_results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), "utf-8")
    (REPORTS / "W5_results.md").write_text(md(res), "utf-8")
    log("[w5] 完成")


def _p(x: dict, L: str = "B"):
    return (x.get(L) or {}).get("p")


def judge(res: dict) -> dict:
    """W5_plan 第 5 節：(a) 偏離是不是原因；(b) 照書的 VCP 有沒有加分。V3、V3s 各判一次。"""
    S, E = res["state"], res["event"]
    out = {}
    for v in ("V3", "V3s"):
        enough_s = all(S[v][k]["B"]["n"] >= FLOOR_STATE and S["V2"][k]["B"]["n"] >= FLOOR_STATE for k in ("IS", "VAL"))
        enough_e = all(E[v][k]["B"]["n"] >= FLOOR_EVENT for k in ("IS", "VAL"))
        a = all(_p(S[v][k]) > _p(S["V2"][k]) for k in ("IS", "VAL")) if enough_s else None
        b_state = all(_p(S[v][k]) > _p(S["TT"][k]) for k in ("IS", "VAL")) if enough_s else None
        b_event = all(_p(E[v][k]) > _p(E["GEN"][k]) for k in ("IS", "VAL")) if enough_e else None
        b = None if b_state is None or b_event is None else (b_state and b_event)
        out[v] = {"enough_state": enough_s, "enough_event": enough_e, "a": a, "b_state": b_state, "b_event": b_event,
                  "b": b}
    return out


def pct(x, d: int = 1) -> str:
    return "—" if x is None else f"{x * 100:.{d}f}%"


def cell(x: dict, L: str = "B") -> str:
    y = x.get(L) or {}
    if not y.get("n"):
        return "—"
    return f"{pct(y['p'])}（{pct(y['lo'], 0)}～{pct(y['hi'], 0)}，{y['n']:,}）"


def md(res: dict) -> str:
    S, E, J = res["state"], res["event"], res["judge"]
    ks = ("IS", "VAL", "HO")
    o = ["# W5　《超級績效》VCP 參數查核：結果", "",
         "方法：`reports/W5_plan.md`（跑之前 commit）。表格由 `scripts/run_w5.py` 產生。"
         "格子＝命中率（Wilson 95% 區間，樣本數）。2023 起只列參考。", ""]

    def table(title, rows, src, L="B", extra=None):
        o.extend([f"## {title}", "", "| | " + " | ".join(PNAME[k] for k in ks) + (" | " + extra if extra else "") + " |",
                  "| --- | " + " | ".join("---" for _ in ks) + (" | ---" if extra else "") + " |"])
        for key, name in rows:
            x = src[key]
            tail = ""
            if extra == "每週檔數（IS／VAL）":
                tail = f" | {x['IS'].get('per_week', 0):.2f}／{x['VAL'].get('per_week', 0):.2f}"
            o.append(f"| {name} | " + " | ".join(cell(x[k], L) for k in ks) + tail + " |")
        o.append("")

    base_rows = [("ALL", "全部合格股票"), ("TT", "趨勢樣板股"), ("S9", "合併名單 S9")]
    vrows = [(k, VNAME[k] + "＋樣板") for k in ("V2", "V3", "V3s")]
    table("1. 一年內翻倍（B）：成形狀態（每週）", base_rows + vrows, S, "B", "每週檔數（IS／VAL）")
    table("2. 一年內翻倍（B）：新出現的成形（上週不成立）", [(k + "_new", VNAME[k]) for k in ("V2", "V3", "V3s")], S, "B",
          "每週檔數（IS／VAL）")
    table("3. 一年內翻倍（B）：每次只加一條（拆解，不下結論）", [(k, VNAME[k]) for k in ("V2", "V2+1", "V2+2", "V2+3", "V2+4", "V3")],
          S, "B", "每週檔數（IS／VAL）")
    erows = [("TT_days", "全部樣板股日"), ("GEN", "樣板股一般突破（20 日新高、帶量）")] + \
            [(k, VNAME[k] + " 突破") for k in ("V2", "V3", "V3s")]
    table("4. 一年內翻倍（B）：突破當天買", erows, E, "B")
    table("5. 交易命中（H：先 +20% 才 −8%）：成形狀態", base_rows + vrows, S, "H")
    table("6. 交易命中（H）：突破當天買", erows, E, "H")
    table("7. 3 個月內 +50%（A）：成形狀態", base_rows + vrows, S, "A")
    table("8. 3 個月內 +50%（A）：突破當天買", erows, E, "A")
    o.extend(["## 9. 判定（W5_plan 第 5 節）", ""])
    for v in ("V3", "V3s"):
        j = J[v]
        yn = {True: "成立", False: "不成立", None: "樣本不足"}
        o.append(f"- **{VNAME[v]}**：(a) 偏離書的地方拉低命中率＝{yn[j['a']]}；"
                 f"(b) 有加分＝{yn[j['b']]}（成形 vs 樣板股 {yn[j['b_state']]}、突破 vs 一般突破 {yn[j['b_event']]}）。")
    o.append("")
    o.append("H 的「120 日都沒碰到」比例（成形，IS／VAL）：" + "、".join(
        f"{VNAME.get(k, k)} {pct(S[k]['IS']['H_und'], 0)}／{pct(S[k]['VAL']['H_und'], 0)}" for k in ("TT", "V2", "V3")) + "。")
    o.append("")
    return "\n".join(o)


def export() -> None:
    """頁面用的摘要（照書 VCP 的案例數與命中率、樣板股對照）併進 layer_research.json 的 w5 鍵。"""
    res = json.loads((REPORTS / "W5_results.json").read_text("utf-8"))
    S, E = res["state"], res["event"]

    def pick(x: dict) -> dict:
        return {k: {"n": x[k]["n"], "stocks": x[k]["stocks"], "B": x[k]["B"]["p"], "H": x[k]["H"]["p"]} for k in ("IS", "VAL")}

    out = {"plan": res["plan"], "v3": pick(S["V3"]), "v2": pick(S["V2"]), "tt": pick(S["TT"]),
           "v3_brk": {k: E["V3"][k]["n"] for k in ("IS", "VAL")}, "judge": res["judge"]["V3"]}
    path = LP.REPO / "data" / "lab" / "layer_research.json"
    lay = json.loads(path.read_text("utf-8"))
    lay["w5"] = out
    path.write_text(json.dumps(lay, ensure_ascii=False, sort_keys=True, separators=(",", ":")), "utf-8")
    log(f"[w5] 匯出 {path}")


if __name__ == "__main__":
    if "--export" not in sys.argv:
        main()
    export()
