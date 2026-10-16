"""W4：大盤時機——什麼時候名單比較準（reports/W4_plan.md v1，跑之前寫定）。

    .venv/bin/python -u scripts/run_w4.py --stage is    週大盤狀態（快取 data/cache/w4_mkt.pkl）＋只算 2014–2019 → reports/W4_is.{md,json}
    .venv/bin/python -u scripts/run_w4.py --stage val   2020–2022 判定、2023 起參考、逐年表 → reports/W4_results.{md,json}
                                                         ＋ ../data/lab/layer_research.json（價格強度子名單、大盤時機）
需要 W3 的資料表快取（run_w3.py --stage is 產生的 data/cache/w3_table.pkl）。
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_w3 as R3  # noqa: E402
from superstock import features as FT  # noqa: E402
from superstock import labpanel as LP  # noqa: E402
from superstock import layer as LA  # noqa: E402
from superstock import regime as RG  # noqa: E402

REPORTS = ROOT / "reports"
CACHE = ROOT / "data" / "cache" / "w4_mkt.pkl"
T0 = time.time()
HALVES = [LA.SUBS["IS1"], LA.SUBS["IS2"]]


def log(msg: str) -> None:
    print(f"{msg}（{time.time() - T0:.0f} 秒）", flush=True)


def _p(x, d=1):
    return "—" if x is None else f"{x * 100:.{d}f}%"


def _x(x, d=2):
    return "—" if x is None else f"{x:.{d}f}"


def load() -> tuple:
    with R3.CACHE.open("rb") as fh:
        tb = pickle.load(fh)
    return tb, LA.Tab(tb)


def ps_mask(T) -> np.ndarray:
    """價格強度子名單：RS ≥ 90 或相對強勢前 10%（使用者 2026-10-16 選；看過 W3 的 2020–2022 結果後才選）。"""
    return T.col("rs90") | T.col("mom10")


def stage_is() -> None:
    tb, T = load()
    m, extra = LP.load()
    log("[w4] 面板")
    F = FT.compute(m, extra["cap"], FT.VCP_V2)
    D = RG.daily_states(m, F)
    W = np.array(tb["W"])
    WS = RG.weekly_states(D, W, tb["S9w"].sum(axis=1))
    idx_w = D["idx"][W]
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with CACHE.open("wb") as fh:
        pickle.dump({"WS": WS, "idx": D["idx"].tolist(), "cal": tb["cal"], "W": tb["W"], "idx_w": idx_w}, fh)
    log("[w4] 大盤狀態")
    wd = np.array(tb["dates"])
    a, b = LA.PER["IS"]
    rows = []
    for k, (name, labels) in RG.VARS.items():
        full = RG.by_state(T, WS[k], wd, a, b)
        halves = [RG.by_state(T, WS[k], wd, x, y) for x, y in HALVES]
        ok, sp = RG.stable(full, halves)
        rows.append({"var": k, "name": name, "labels": labels, "full": full, "halves": halves, "stable": ok,
                     "spread": sp, "base": RG.base_by_state(tb, WS[k], a, b)})
    good = [r for r in rows if r["stable"]]
    pick = max(good, key=lambda r: r["spread"][2])["var"] if good else None
    out = LA.to_json({"plan": "reports/W4_plan.md v1", "asof": time.strftime("%Y-%m-%d"), "period": [a, b], "pick": pick,
                      "vars": rows})
    (REPORTS / "W4_is.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), "utf-8")
    (REPORTS / "W4_is.md").write_text(md_is(out), "utf-8")
    log(f"[w4] 2014–2019：選中 {pick or '無'}")


def _state_line(st: dict, labels: list) -> str:
    return "；".join(f"{labels[int(v)]} {_p(x['p'])}（{x['weeks']} 週、{x['runs']} 段）" for v, x in sorted(st.items(), key=lambda kv: int(kv[0])))


def md_is(o: dict) -> str:
    L = ["# W4　大盤時機：2014–2019（選變數；2020–2022 還沒看）", "",
         "方法：`reports/W4_plan.md` v1（跑之前 commit）。表格由 `scripts/run_w4.py --stage is` 產生。"
         "格子＝該狀態下合併名單 S9 的一年翻倍命中率（週數、出現段數）。", "",
         f"**選中：{o['pick'] + ' ' + next(r['name'] for r in o['vars'] if r['var'] == o['pick']) if o['pick'] else '無（沒有變數在兩個子期間都穩定）'}**", "",
         "| 變數 | 2014–2019 | 2014–16 | 2017–19 | 差距 | 穩定 | 全部合格股票 |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in o["vars"]:
        sp = r["spread"]
        L.append(f"| {r['var']} {r['name']} | {_state_line(r['full'], r['labels'])} | {_state_line(r['halves'][0], r['labels'])} | "
                 f"{_state_line(r['halves'][1], r['labels'])} | {_x(sp[2]) if sp else '—'} | {'是' if r['stable'] else '否'} | "
                 + "；".join(f"{r['labels'][int(v)]} {_p(p)}" for v, p in sorted(r["base"].items(), key=lambda kv: int(kv[0]))) + " |")
    return "\n".join(L) + "\n"


def stage_val() -> None:
    tb, T = load()
    with CACHE.open("rb") as fh:
        mk = pickle.load(fh)
    isr = json.loads((REPORTS / "W4_is.json").read_text("utf-8"))
    WS = mk["WS"]
    wd = np.array(tb["dates"])
    ps = ps_mask(T)
    res: dict = {"plan": "reports/W4_plan.md v1", "asof": time.strftime("%Y-%m-%d"), "pick": isr["pick"]}
    if isr["pick"]:
        k = isr["pick"]
        r = next(x for x in isr["vars"] if x["var"] == k)
        hi, lo, _ = r["spread"]
        per = {p: {"s9": RG.by_state(T, WS[k], wd, a, b), "ps": RG.by_state(T, WS[k], wd, a, b, ps),
                   "base": RG.base_by_state(tb, WS[k], a, b)} for p, (a, b) in LA.PER.items()}
        allp = {"s9": RG.by_state(T, WS[k], wd, LA.PER["IS"][0], LA.PER["VAL"][1]),
                "ps": RG.by_state(T, WS[k], wd, LA.PER["IS"][0], LA.PER["VAL"][1], ps),
                "base": RG.base_by_state(tb, WS[k], LA.PER["IS"][0], LA.PER["VAL"][1])}
        v = per["VAL"]["s9"]
        okw = all(v.get(s, {}).get("weeks", 0) >= RG.HALF_MIN and v[s]["p"] is not None for s in (hi, lo))
        ratio = v[hi]["p"] / v[lo]["p"] if okw and v[lo]["p"] else None
        res.update({"var": k, "name": r["name"], "labels": r["labels"], "hi": hi, "lo": lo, "per": per, "all": allp,
                    "val_ratio": ratio, "pass": bool(okw and ratio is not None and ratio >= RG.RATIO)})
    # 價格強度子名單（W3 的評估函式：三段期間、逐年、涵蓋率）
    res["ps"] = R3.evaluate(T, tb, ps)
    # 逐年表
    years = sorted({d[:4] for d in tb["dates"] if d >= "2014"})
    idx = np.array(mk["idx"], dtype=float)
    cal = tb["cal"]
    yr = []
    for y in years:
        allm = np.ones(len(T.d), dtype=bool)
        a, b = f"{y}-01-01", f"{y}-12-31"
        s9, sp = T.stat(allm, a, b), T.stat(ps, a, b)
        i0 = max([i for i, d in enumerate(cal) if d < a] or [0])
        i1 = max(i for i, d in enumerate(cal) if d <= b)
        yr.append({"y": y, "s9": s9["p"], "s9_n": s9["n"], "ps": sp["p"], "ps_n": sp["n"], "base": LA.base_rate(tb, "B", a, b),
                   "taiex": float(idx[i1] / idx[i0] - 1) if idx[i0] == idx[i0] and idx[i1] == idx[i1] else None})
    res["years"] = yr
    out = LA.to_json(res)
    (REPORTS / "W4_results.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), "utf-8")
    (REPORTS / "W4_results.md").write_text(md_val(out), "utf-8")
    export(out)
    log(f"[w4] 大盤時機：{(out.get('var') or '無') + ('，過關' if out.get('pass') else '，不過關')}；"
        f"價格強度子名單 2020–2022 {_x(out['ps']['judge']['lift'])} 倍")


def md_val(o: dict) -> str:
    L = ["# W4　大盤時機與價格強度子名單：結果", "",
         "方法：`reports/W4_plan.md` v1。變數只用 2014–2019 選（`reports/W4_is.md`，看 2020–2022 之前 commit）。"
         "表格由 `scripts/run_w4.py --stage val` 產生。2023 年起只列數字、不參與判定。", ""]
    if o.get("var"):
        lab = o["labels"]
        L += [f"## 大盤時機：{o['var']} {o['name']}（{'過關' if o['pass'] else '不過關'}）", "",
              f"2014–2019 最高的狀態「{lab[o['hi']]}」、最低的「{lab[o['lo']]}」；2020–2022 兩者的差距 {_x(o['val_ratio'])} 倍（門檻 {1.3}）。", "",
              "| 期間 | 狀態 | 週數（段數） | S9 一年翻倍 | 價格強度子名單 | 全部合格股票 |", "| --- | --- | --- | --- | --- | --- |"]
        for p, x in o["per"].items():
            for v in sorted(x["s9"], key=int):
                s, q = x["s9"][v], x["ps"].get(v, {})
                L.append(f"| {p} | {lab[int(v)]} | {s['weeks']}（{s['runs']}） | {_p(s['p'])} | {_p(q.get('p'))} | {_p(x['base'].get(v))} |")
        L.append("")
    else:
        L += ["## 大盤時機：2014–2019 沒有穩定的變數，不做判定", ""]
    j = o["ps"]["judge"]
    L += ["## 價格強度子名單（RS ≥ 90 或相對強勢前 10%）", "",
          "這個條件是看過 W3 的 2020–2022 結果後才選的，所以三段期間都不是獨立的檢驗；能看的是三段是否一致。", "",
          "| 期間 | 子名單 | 名單其餘 | S9 | 全部合格股票 | 子名單新進名單 | S9 新進名單 |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for p, x in o["ps"]["per"].items():
        L.append(f"| {p} | {_p(x['t1']['B']['p'])}（每週 {_x(x['t1']['B']['per_week'], 1)}） | {_p(x['t2']['B']['p'])} | {_p(x['s9']['B']['p'])} | "
                 f"{_p(x['base']['B'])} | {_p(x['t1_new']['p'])} | {_p(x['s9_new']['p'])} |")
    e = o["ps"]["cover_e"]
    L += ["", f"2020–2022 是 S9 的 {_x(j['lift'])} 倍。5 年 10 倍股（2014 起）：子名單抓得早 {e['t1']['early']}／{e['t1']['n']} 檔，S9 {e['s9']['early']}／{e['s9']['n']} 檔。", "",
          "## 逐年（一年內翻倍）", "", "| 年 | S9 | 價格強度子名單 | 全部合格股票 | 加權指數漲跌 |", "| --- | --- | --- | --- | --- |"]
    for r in o["years"]:
        L.append(f"| {r['y']} | {_p(r['s9'])}（{r['s9_n']:,}） | {_p(r['ps'])}（{r['ps_n']:,}） | {_p(r['base'])} | {_p(r['taiex'])} |")
    L.append("\n最近一年的命中率還在累積（一年翻倍要看之後 250 個交易日，期限沒走完的股票週不算）。")
    return "\n".join(L) + "\n"


def export(o: dict) -> None:
    """併入 data/lab/layer_research.json：價格強度子名單（ps）與大盤時機（mkt）。"""
    res = json.loads(R3.OUT.read_text("utf-8"))
    keep = ("p", "per_week", "n")

    def sm(x):
        return {k: x.get(k) for k in keep}

    ps = o["ps"]
    res["ps"] = {"desc": "RS ≥ 90 或相對強勢前 10%", "post_hoc": True, "lift_val": ps["judge"]["lift"],
                 "per": {p: {"t1": {L: sm(x["t1"][L]) for L in LA.LABS}, "t2": {L: sm(x["t2"][L]) for L in LA.LABS},
                             "s9": {L: sm(x["s9"][L]) for L in LA.LABS}, "base": x["base"]} for p, x in ps["per"].items()},
                 "cover_e": ps["cover_e"]}
    res["mkt"] = ({"var": o["var"], "name": o["name"], "labels": o["labels"], "hi": o["hi"], "lo": o["lo"],
                   "pass": o["pass"], "val_ratio": o["val_ratio"], "all": o["all"]} if o.get("var") else {"var": None, "pass": False})
    res["years"] = o["years"]
    R3.OUT.write_text(json.dumps(LA.to_json(res), ensure_ascii=False, sort_keys=True, separators=(",", ":")), "utf-8")
    log(f"[w4] → {R3.OUT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=("is", "val"), required=True)
    {"is": stage_is, "val": stage_val}[ap.parse_args().stage]()
