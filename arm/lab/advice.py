"""籌碼雷達：策略評級＋本期推薦清單＋出場／避開清單（策略頁 v2，2026-10-15）。

使用者（2026-10-15）：「策略那邊好亂、用字很 AI、結論不明確。我要看的就是推薦哪檔、建議佈局時間、預估獲利等等
這種嚴謹的分析」。規劃見 docs/strategy_v2_plan.md。

評級（門檻寫死，改門檻＝改這裡＋改文件）：
  · 計算單位：短線＝逐筆交易；事件型（臺灣50、高股息）＝每次審核（同一次各檔等額平均成一個報酬）。
  · A 可執行：樣本 ≥30 筆（事件型 ≥6 次）、超額報酬 95% 信賴區間下限 > 0、單月占比 ≤40%（短線）、
    前瞻驗證滿 10 筆（事件型 2 次）且平均超額 > 0。
  · C 不推薦：樣本 <10 筆（事件型 <4 次）、平均超額 ≤0、贏大盤比例 <50%、單月占比 >70%，或前瞻驗證滿額但平均超額 ≤0。
  · B 小部位試行：其餘。
  · 2026-10-15 依資料包回測紀律加嚴（docs/strategy_pack_plan.md，回測前寫定）：
    A 級另需「成本加倍後平均超額 >0」與「參數鄰近 9 組中至少 6 組為正」；
    參數鄰近不到一半為正 → C；以 Yahoo 宇宙選股的策略（xe_rule）平均沒贏同宇宙等權 → C。
信賴區間＝bootstrap 2,000 次、固定亂數種子（同一份資料永遠算出同一個區間）。
報酬一律扣來回成本 0.585%；超額＝減去加權指數同期報酬。
"""
from __future__ import annotations

import math
import random
import statistics
from collections import Counter

BOOT_N = 2000
SEED = 20261015
CAP = {"A": 0.05, "B": 0.02, "C": 0.0}       # 每檔部位上限（占總資金）
LOSS_CAP = 0.005                              # 有停損價時：單筆停損虧損 ≤ 總資金 0.5%
LABEL = {"A": "可執行", "B": "小部位試行", "C": "不推薦"}
RULE = [
    {"g": "A", "cond": "樣本 ≥30 筆（事件型 ≥6 次）、超額報酬 95% 信賴區間下限 >0、單月占比 ≤40%、成本加倍後仍贏大盤、"
                       "參數鄰近 9 組中至少 6 組為正，且前瞻驗證滿 10 筆（事件型 2 次）平均超額 >0",
     "cap": "每檔 ≤ 總資金 5%"},
    {"g": "B", "cond": "平均超額 >0 且贏大盤比例 ≥50%，但未達 A 級全部條件", "cap": "每檔 ≤ 總資金 2%"},
    {"g": "C", "cond": "樣本 <10 筆（事件型 <4 次）、平均超額 ≤0、贏大盤比例 <50%、單月占比 >70%、參數鄰近不到一半為正、"
                       "沒贏同一批股票的平均（以 Yahoo 宇宙選股者），或前瞻驗證平均超額 ≤0",
     "cap": "不下單，只列觀察"},
]
RULE_STOP = "有停損價時，部位另以「停損時虧損 ≤ 總資金 0.5%」計算，取兩者較小者。"

# 回測方法 v3（2026-10-15 使用者決定；docs/backtest_v3_plan.md 第 6 節）：取代上面的 RULE
RULE3 = [
    {"g": "A", "cond": "選股：扣成本後贏同一批股票的平均，樣本內 t ≥2、樣本外同方向且 t ≥1；報酬型態樣本內外都過；"
                       "成本加倍、參數鄰近（9 組 ≥6 組為正）、去掉最好 5% 三項都過；前瞻滿 10 期（事件型 2 次）平均超額 >0",
     "cap": "每檔 ≤ 總資金 5%"},
    {"g": "B", "cond": "選股與報酬型態在樣本內都過、樣本外沒有反向（沒有樣本外資料的看前瞻）；穩健度三項最多一項未過",
     "cap": "每檔 ≤ 總資金 2%"},
    {"g": "C", "cond": "其餘；參數鄰近不到一半為正、或樣本外反向，一律 C", "cap": "不下單，只列觀察"},
]
PAY3 = "報酬型態：賺錢機率 ≥60% 且每月平均 ≥+1%；或賺錢機率 ≥40%、賺賠比 ≥2.5 倍、每月平均 ≥+2%（每月平均＝平均報酬 ÷ 持有月數）"
COST3 = "成本：大型股來回 0.48%、中型股 0.68%（手續費 2.8 折、證交稅 0.3%、滑價大型每邊 0.05%／中型 0.15%）"
PER_STRAT = 5                                  # 每條策略本期最多列 5 檔（使用者 2026-10-15）


def pct(x, d: int = 1) -> str:
    if x is None:
        return "—"
    return f"{'+' if x > 0 else '−' if x < 0 else ''}{abs(x):.{d}f}%"


def boot_ci(xs: list[float], b: int = BOOT_N, seed: int = SEED) -> tuple[float, float] | None:
    """平均數的 95% 信賴區間（bootstrap、固定種子）。"""
    xs = [x for x in xs if x is not None]
    if len(xs) < 3:
        return None
    rnd = random.Random(seed)
    n = len(xs)
    ms = sorted(sum(xs[rnd.randrange(n)] for _ in range(n)) / n for _ in range(b))
    return ms[int(0.025 * b)], ms[int(0.975 * b) - 1]


def _q(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    k = (len(xs) - 1) * q
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def per_review(trades: list[dict]) -> list[dict]:
    """事件型：同一次審核的已出場交易等額平均 → 一次一個單位 {d, r, x, n, review}。"""
    by: dict[str, list] = {}
    for t in trades:
        if t.get("st") == "closed" and t.get("r") is not None:
            by.setdefault(t.get("review") or t.get("d", "")[:7], []).append(t)
    out = []
    for rv, ts in sorted(by.items()):
        xs = [t["x"] for t in ts if t.get("x") is not None]
        out.append({"review": rv, "d": min(t.get("d") or "" for t in ts), "n": len(ts),
                    "r": statistics.mean(t["r"] for t in ts), "x": statistics.mean(xs) if xs else None})
    return out


def closed(trades: list[dict]) -> list[dict]:
    return [t for t in trades if t.get("st") == "closed" and t.get("r") is not None]


def stats(units: list[dict], event: bool = False) -> dict:
    """units＝[{d, r, x}]（r、x 為 %、已扣成本）。"""
    rs = [u["r"] for u in units if u.get("r") is not None]
    xs = [u["x"] for u in units if u.get("x") is not None]
    if not rs:
        return {"n": 0}
    ds = sorted(u["d"] for u in units if u.get("d"))
    s = {"n": len(rs), "event": event, "d0": ds[0][:7] if ds else None, "d1": ds[-1][:7] if ds else None,
         "avg": statistics.mean(rs), "med": statistics.median(rs), "p25": _q(rs, 0.25), "p75": _q(rs, 0.75),
         "lo": min(rs), "hi": max(rs),
         "win": round(sum(1 for r in rs if r > 0) / len(rs) * 100), "kwin": sum(1 for r in rs if r > 0)}
    if xs:
        s.update({"x": statistics.mean(xs), "xmed": statistics.median(xs),
                  "xwin": round(sum(1 for x in xs if x > 0) / len(xs) * 100), "kx": sum(1 for x in xs if x > 0),
                  "nx": len(xs), "ci": boot_ci(xs)})
    if not event and ds:
        m, k = Counter(d[:7] for d in ds).most_common(1)[0]
        s["conc"] = [m, round(k / len(ds) * 100)]
    return s


COST_PCT = 0.585     # 來回成本（%）；單位沒帶 cost 時用它（逐筆、每次審核平均都是一次來回）


def robust(units: list[dict], reg: dict | None = None) -> dict:
    """回測紀律 D2–D6（docs/strategy_pack_plan.md）：成本加倍、去掉最好的一筆（次）、最大累計回落、最長連虧、
    大盤年線上／下；有 xe（對同宇宙等權）的另算平均。units 依日期排序後計算；reg＝{日期: 加權在年線上？}。"""
    us = sorted((u for u in units if u.get("x") is not None), key=lambda u: u.get("d") or "")
    xs = [u["x"] for u in us]
    if not xs:
        return {}
    out = {"x2": statistics.mean(u["x"] - (u.get("cost") if u.get("cost") is not None else COST_PCT) for u in us)}
    if len(xs) >= 3:
        out["drop1"] = statistics.mean(sorted(xs)[:-1])
    cum = peak = mdd = 0.0
    run = streak = 0
    for x in xs:
        cum += x
        peak = max(peak, cum)
        mdd = max(mdd, peak - cum)
        run = run + 1 if x <= 0 else 0
        streak = max(streak, run)
    out["mdd"], out["streak"] = mdd, streak
    if reg:
        g: dict[str, list] = {"up": [], "dn": []}
        for u in us:
            k = reg.get((u.get("d") or "")[:10])
            if k is not None:
                g["up" if k else "dn"].append(u["x"])
        for k, v in g.items():
            out[k] = [len(v), statistics.mean(v) if v else None]
    xe = [u["xe"] for u in us if u.get("xe") is not None]
    if xe:
        out.update({"xe": statistics.mean(xe), "kxe": sum(1 for v in xe if v > 0), "nxe": len(xe)})
    return out


def grade(s: dict, fwd: dict | None = None) -> tuple[str, list[str]]:
    """→ (A/B/C, 理由)。理由＝決定評級的條件（B 列出未達 A 的條件）。"""
    if not s.get("n"):
        return "C", ["尚無已出場交易"]
    ev = s.get("event")
    unit = "次" if ev else "筆"
    n_c, n_a, n_f = (4, 6, 2) if ev else (10, 30, 10)
    f = fwd or {}
    conc = s.get("conc")
    if s["n"] < n_c:
        return "C", [f"樣本只有 {s['n']} {unit}"]
    if f.get("n", 0) >= n_f and (f.get("x") is None or f["x"] <= 0):
        return "C", [f"前瞻驗證 {f['n']} {unit}平均超額 {pct(f.get('x'))}"]
    if s.get("x") is None or s["x"] <= 0:
        return "C", [f"平均超額 {pct(s.get('x'))}，沒有贏大盤"]
    if s.get("xwin", 0) < 50:
        return "C", [f"只有 {s['xwin']}% 贏大盤"]
    if conc and conc[1] > 70:
        return "C", [f"{conc[1]}% 的交易集中在 {conc[0]}，只代表一段行情"]
    nb = s.get("nb") or {}
    if nb.get("n") and nb["pos"] * 2 < nb["n"]:
        return "C", [f"參數稍微改動就失效：鄰近 {nb['n']} 組參數只有 {nb['pos']} 組贏大盤"]
    rb = s.get("rb") or {}
    if s.get("xe_rule") and rb.get("xe") is not None and rb["xe"] <= 0:
        return "C", [f"沒有贏同一批股票的等權平均（{pct(rb['xe'])}），成績來自這批股票整體的漲幅"]
    miss = []
    ci = s.get("ci")
    if s["n"] < n_a:
        miss.append(f"樣本 {s['n']} {unit}（A 級需 ≥{n_a}）")
    if not ci or ci[0] <= 0:
        miss.append(f"超額報酬 95% 信賴區間 {pct(ci[0]) if ci else '—'}～{pct(ci[1]) if ci else '—'} 含 0")
    if conc and conc[1] > 40:
        miss.append(f"{conc[1]}% 的交易集中在 {conc[0]}")
    if rb.get("x2") is not None and rb["x2"] <= 0:
        miss.append(f"成本加倍後平均超額 {pct(rb['x2'])}")
    need = math.ceil((nb.get("n") or 9) * 2 / 3)
    if not nb.get("n"):
        miss.append("尚未做參數鄰近檢查")
    elif nb["pos"] < need:
        miss.append(f"參數鄰近 {nb['n']} 組中 {nb['pos']} 組為正（A 級需 ≥{need}）")
    if f.get("n", 0) < n_f:
        miss.append(f"前瞻驗證 {f.get('n', 0)}／{n_f} {unit}")
    return ("B", miss) if miss else ("A", ["全部條件符合"])


def concl(s: dict) -> str:
    """一句話結論（數字全由資料算出）。"""
    if not s.get("n"):
        return "尚無已出場交易。"
    per = f"（{s['d0']}～{s['d1']}）" if s.get("d0") else ""
    ci = s.get("ci")
    cx = f"95% 信賴區間 {pct(ci[0])}～{pct(ci[1])}" if ci else "樣本太少、無信賴區間"
    if s.get("event"):
        a = (f"過去 {s['n']} 次{per}：每次平均 {pct(s['avg'])}、中位 {pct(s['med'])}，{s['kwin']} 次獲利，"
             f"最差一次 {pct(s['lo'])}")
        b = f"；平均贏大盤 {pct(s.get('x'))}（{cx}），{s.get('kx', 0)} 次贏大盤。" if s.get("x") is not None else "。"
    else:
        a = (f"過去 {s['n']} 筆{per}：平均每筆 {pct(s['avg'])}、中位 {pct(s['med'])}，{s['win']}% 獲利，"
             f"最差一筆 {pct(s['lo'])}")
        b = f"；平均贏大盤 {pct(s.get('x'))}（{cx}），{s.get('xwin', 0)}% 贏大盤。" if s.get("x") is not None else "。"
    return a + b


def r1(s: dict) -> dict:
    """輸出用：百分比一律取一位小數（頁面與文字顯示同一個數字；評級判定用的是四捨五入前的值）。"""
    out = {}
    for k, v in s.items():
        if isinstance(v, float):
            out[k] = round(v, 1)
        elif k == "ci" and v:
            out[k] = [round(v[0], 1), round(v[1], 1)]
        elif k in ("up", "dn") and isinstance(v, list):
            out[k] = [v[0], None if v[1] is None else round(v[1], 1)]
        elif k == "rb" and isinstance(v, dict):
            out[k] = r1(v)
        else:
            out[k] = v
    return out


def score(units: list[dict], event: bool = False, fwd_units: list[dict] | None = None, *,
          reg: dict | None = None, nb: dict | None = None, xe_rule: bool = False) -> dict:
    """reg＝大盤年線（robust 分組用）、nb＝參數鄰近（packtest.grid 格式）、xe_rule＝以 Yahoo 宇宙選股、須贏同宇宙等權。"""
    s = stats(units, event)
    if s.get("n"):
        s["rb"] = robust(units, reg)
        if nb:
            s["nb"] = nb
        s["xe_rule"] = xe_rule
    f = stats(fwd_units or [], event) if fwd_units else {"n": 0}
    g, why = grade(s, f)
    return {**r1(s), "grade": g, "label": LABEL[g], "why": why, "concl": concl(s),
            "fwd": r1({k: f.get(k) for k in ("n", "avg", "x", "win", "xwin")}) if f.get("n") else {"n": 0}}


def size(g: str, px: float | None, stop: float | None, capital: float = 1_000_000) -> dict | None:
    """每 100 萬資金的部位：評級上限，有停損時再以「停損虧損 ≤ 0.5%」限制。"""
    cap = CAP.get(g, 0)
    if not cap or not px:
        return None
    p = cap
    if stop and stop < px:
        p = min(cap, LOSS_CAP / (1 - stop / px))
    amt = capital * p
    return {"pct": round(p * 100, 2), "amt": round(amt), "sh": int(amt // px)}


def expect(s: dict) -> dict:
    """推薦卡的預估報酬：中位、25%～75%、獲利比例、最差；每 10 萬的損益（中位、最差）。"""
    if not s.get("n"):
        return {}
    return {"med": s["med"], "p25": s["p25"], "p75": s["p75"], "win": s["win"], "kwin": s["kwin"], "lo": s["lo"],
            "n": s["n"], "event": s.get("event", False), "per10": round(s["med"] * 1000), "lo10": round(s["lo"] * 1000)}


# —— 組裝：策略評級總表、本期推薦、觀察名單、出場／避開

TW50_LEAD = 10        # 臺灣50 建倉日前幾個日曆天內，才把「以今天排名試算」的名單列進本期操作


def _md(d: str | None) -> str:
    return f"{int(d[5:7])}/{int(d[8:10])}" if d and len(d) >= 10 else (d or "—")


def _row_why_s1(r: dict) -> list[str]:
    out = []
    ia = r.get("ia5") or []
    if ia:
        out.append(f"5 日內 {len(ia)} 家投信主動 ETF 加碼（{'、'.join(ia[:3])}{'等' if len(ia) > 3 else ''}）")
    if r.get("a5v") is not None:
        out.append(f"主動 ETF 5 日淨買 {r['a5v']:.1f} 億元")
    return out


def _put(item: dict, picks: list, watch: list) -> None:
    (picks if item["grade"] in ("A", "B") else watch).append(item)


def build(data: dict) -> dict:
    """data＝analyze.run() 的中間結果（rows、strat、grow、idx；last＝最新資料日）。"""
    from .strategy import trading_days_after
    rows = {r["c"]: r for r in data.get("rows") or []}
    strat = data.get("strat") or {}
    L = {s["key"]: s for s in strat.get("list") or []}
    grow = data.get("grow") or {}
    hd = ((data.get("idx") or {}).get("hd") or {})
    last = data.get("last")
    grades, picks, watch, exits = [], [], [], []

    # ① 共識加碼・開低進場（短線）：明日候選＋前瞻持有中
    s1 = L.get("s1")
    if s1 and s1.get("score"):
        sc = s1["score"]
        hold = s1.get("hold") or 3
        grades.append({"k": "s1", "name": s1["name"], "kind": s1.get("kind"), **_g(sc), "fill": s1.get("fill"),
                       "tried": s1.get("tried")})
        for c in (s1.get("cands") or [])[:PER_STRAT]:
            item = {"c": c["c"], "n": c["n"], "k": "s1", "sname": s1["name"], "grade": sc["grade"],
                    "act": "佈局", "d": c.get("d"), "ent": c.get("ent"), "cond": f"開盤價 < {c['px']:,g} 才買",
                    "ent_how": "開盤價低於前一日收盤才買（以 8:59 試撮價判斷），平盤或開高不買",
                    "out": c.get("out"), "out_how": "到期日收盤賣出；期間收盤跌破停損價，當日收盤賣出",
                    "stop_how": f"收盤跌破「進場價 − {s1.get('stop_atr') or 2:g} × ATR」，各檔價位見下方",
                    "px": c.get("px"), "stop": c.get("stop"), "exp": expect(sc), "hold": f"持有 {hold} 個交易日",
                    "why": _row_why_s1(rows.get(c["c"]) or {}), "size": size(sc["grade"], c.get("px"), c.get("stop"))}
            _put(item, picks, watch)
        for t in s1.get("fwd") or []:
            if t.get("st") != "open":
                continue
            ds = trading_days_after(t["d"], hold)
            item = {"c": t["c"], "n": t["n"], "k": "s1", "sname": s1["name"], "grade": sc["grade"], "act": "持有中",
                    "d": t["d"], "ent": ds[0], "entry": t.get("entry"), "now": t.get("now"), "now_r": t.get("r"),
                    "out": ds[-1], "out_how": "到期日收盤賣出；期間收盤跌破停損價，當日收盤賣出",
                    "stop_how": "收盤跌破停損價，當日收盤賣出",
                    "px": t.get("now"), "stop": t.get("stop"), "exp": expect(sc), "hold": f"持有 {hold} 個交易日",
                    "why": _row_why_s1(rows.get(t["c"]) or {}), "size": None}
            _put(item, picks, watch)

    # ② 臺灣50 提前卡位（事件型）
    s3 = L.get("s3")
    ver = next((v for v in (s3 or {}).get("vers") or [] if v.get("k") == "early"), None)
    if ver and ver.get("score"):
        sc = ver["score"]
        grades.append({"k": "s3", "name": s3["name"], "kind": s3.get("kind"), **_g(sc), "fill": ver.get("fill"),
                       "tried": ver.get("tried")})
        p = s3.get("plan") or {}
        for it in p.get("items") or []:
            item = _tw50_item(it, p, sc, last)
            if item:
                _put(item, picks, watch)

    # ③ 高股息換股（追買評級＋出場規則效果）
    flow = hd.get("flow") or {}
    T = {t["k"]: t for t in flow.get("tests") or []}
    if T.get("post_big") and T.get("ride5"):
        from .hdflow import ALERT as HDS
        ride = score((flow.get("units") or {}).get("ride5") or [], event=True)
        post = [b[2] for b in T["post_big"]["by"]]
        pc = boot_ci(post)
        eff = r1({"n": len(post), "avg": statistics.mean(post) if post else None,
                  "neg": sum(1 for x in post if x < 0), "ci": pc,
                  "ok": bool(pc and pc[1] < 0 and len(post) >= 6)})
        dl = [b[2] for b in (T.get("del10") or {}).get("by") or []]
        grades.append({"k": "hd", "name": HDS["name"], "kind": HDS["kind"], **_g(ride), "exit": eff, "tried": HDS.get("tried"),
                       "del": r1({"n": len(dl), "avg": statistics.mean(dl) if dl else None,
                                  "neg": sum(1 for x in dl if x < 0), "ci": boot_ci(dl)})})
        A = hd.get("alert") or {}
        big = A.get("big_th") or 5
        for r in A.get("rows") or []:
            if r[6] is None or r[6] < big:
                continue
            exits.append({"c": r[0], "n": r[1], "k": "hd", "etf": r[2], "review": r[3], "side": r[4], "amt": r[5],
                          "days": r[6], "t0": r[7], "t1": r[8], "until": r[9], "phase": r[10], "src": r[11]})

    # ④ 長線：投信動能成長（月選）
    s5 = grow.get("s5")
    if s5 and s5.get("score"):
        sc = s5["score"]
        grades.append({"k": "s5", "name": s5["name"], "kind": s5.get("kind"), **_g(sc), "fill": s5.get("fill"),
                       "tried": s5.get("tried")})
        scr = s5.get("screen_d") or [None, None]
        for x in [x for x in grow.get("screen") or [] if x.get("pass")][:PER_STRAT]:
            px = x.get("px")
            stop = round(px * 0.8, 2) if px else None
            item = {"c": x["c"], "n": x["n"], "k": "s5", "sname": s5["name"], "grade": sc["grade"], "act": "佈局",
                    "ent": scr[1], "ent_how": f"{_md(scr[0])} 收盤仍符合四項條件才買；開盤高於前收 3% 以上不買",
                    "out": None, "out_how": "收盤自最高收盤回落 30% 賣出；最長持有 250 個交易日",
                    "stop_how": "收盤跌破進場價 20%",
                    "px": px, "stop": stop, "exp": expect(sc), "hold": "平均持有約 4 個月",
                    "why": _why_s5(x), "size": size(sc["grade"], px, stop)}
            _put(item, picks, watch)

    for a in strat.get("alerts") or []:
        exits.append({"c": a["c"], "n": a["n"], "k": "gap", "d": a["d"], "gap": a["gap"]})
    pack = _pack(data.get("pack") or {}, s5)
    # 回測方法 v3：新策略＋既有策略改新評級；本期操作依證據強弱排序（有樣本外的在前）
    v3 = build_v3(data.get("v3") or {}, data.get("v3ex") or {}, last)
    g3 = {g["k"]: g for g in v3["grades"]}
    for it in picks + watch:                       # 既有策略的卡片改掛新評級；C 級移到觀察名單
        if it["k"] in g3:
            it["grade"] = g3[it["k"]]["grade"]
            it["size"] = size(it["grade"], it.get("px"), it.get("stop"))
    allp = picks + watch + v3["picks"] + v3["watch"]
    picks = [x for x in allp if x["grade"] in ("A", "B")]
    watch = [x for x in allp if x["grade"] not in ("A", "B")]
    order = {g["k"]: i for i, g in enumerate(sorted(v3["grades"], key=lambda g: g["ev"]))}
    picks.sort(key=lambda x: (order.get(x["k"], 99), x["act"] != "持有中", x.get("ent") or "9999", x["c"]))
    watch.sort(key=lambda x: (order.get(x["k"], 99), x["c"]))
    old = {g["k"]: g for g in grades}
    if "hd" in old:                                  # 高股息換股：追買評級沿用（平均超額為負，任何規則都是 C）
        h = old["hd"]
        v3["grades"].append({"k": "hd", "grade": h.get("grade") or "C", "why": h.get("why") or [], "ins": None, "oos": None,
                             "unit": "次", "has_oos": False, "ev": (2, 0, 0)})
    for g in v3["grades"]:
        if g["k"] in old:
            g.setdefault("name", old[g["k"]].get("name"))
            g.setdefault("kind", old[g["k"]].get("kind"))
    grades3 = sorted(v3["grades"], key=lambda g: ("ABC".index(g["grade"]) if g["grade"] in "ABC" else 3, g["ev"]))
    for g in grades3:
        g.pop("ev", None)
    return {"rule": RULE3, "rule_old": RULE, "pay3": PAY3, "cost3": COST3, "rule_stop": RULE_STOP, "caps": CAP,
            "loss_cap": LOSS_CAP, "grades": grades, "grades3": grades3, "picks": picks, "watch": watch, "exits": exits,
            "pack": pack, "v3": {"live": v3["live"], "basket": v3["basket"], "meta": v3["meta"]}, "last": last,
            "v3err": (data.get("v3") or {}).get("err") or (data.get("v3ex") or {}).get("err")}


PACK_KEYS = ("n", "event", "d0", "d1", "avg", "med", "x", "xmed", "xwin", "kx", "nx", "ci", "lo", "hi", "win",
             "grade", "label", "why", "rb", "nb")


def _pack(pk: dict, s5: dict | None) -> dict:
    """資料包策略測試表（2026-10-15）：P1–P5 主規格＋CAN SLIM 的 C、M 加在長線策略上的對照（P6，原規則不變）。"""
    if pk.get("err"):
        return {"err": pk["err"]}
    rows = []
    for r in pk.get("rows") or []:
        sc = r.get("score") or {}
        rows.append({k: r.get(k) for k in ("k", "src", "name", "unit", "event", "rule", "lim", "lock", "n_sig")}
                    | {k: sc.get(k) for k in PACK_KEYS})
    alt = (s5 or {}).get("alt") or {}
    base = (s5 or {}).get("score") or {}
    for k, lbl, rule in (("s5", "長線：投信動能成長股（現行規則）", "對照基準"),
                         ("c", "長線＋CAN SLIM 的 C", "另要求最新一季 EPS 比去年同季成長 25% 以上"),
                         ("m", "長線＋CAN SLIM 的 M", "另要求篩選日加權指數在 200 日均線之上")):
        sc = base if k == "s5" else alt.get(k)
        if sc and sc.get("n"):
            row = {"k": "p6" + k, "src": "S08", "name": lbl, "unit": "筆", "event": False, "rule": rule} | {kk: sc.get(kk) for kk in PACK_KEYS}
            if k == "m" and sc.get("n") == base.get("n") and sc.get("x") == base.get("x"):
                row["why"] = ["樣本期間的篩選日都在年線之上，這項條件沒有排除任何交易，無從比較"]
            rows.append(row)
    return {"rows": rows, "skipped": pk.get("skipped") or [], "meta": pk.get("meta") or {}}


def _g(sc: dict) -> dict:
    keys = ("n", "event", "d0", "d1", "avg", "med", "p25", "p75", "lo", "hi", "win", "kwin", "x", "xmed", "xwin",
            "kx", "nx", "ci", "conc", "grade", "label", "why", "concl", "fwd", "rb", "nb", "xe_rule")
    return {k: sc.get(k) for k in keys}


def _why_s5(x: dict) -> list[str]:
    out = []
    if x.get("trust") is not None:
        out.append(f"投信 20 日買超占股本 {x['trust']:.2f}%" + (f"（買 {x['tdays']} 天）" if x.get("tdays") is not None else ""))
    if x.get("yoy") is not None:
        out.append(f"營收年增 {x['yoy']:.0f}%、累計 {x.get('cyoy') or 0:.0f}%")
    if x.get("rs") is not None:
        out.append(f"半年漲幅贏過 {x['rs']}% 的股票")
    return out


def _tw50_item(it: dict, p: dict, sc: dict, last: str | None = None) -> dict | None:
    """臺灣50 計畫中的一檔 → 本期操作。只列「待佈局」與「持有中」；建倉日前 TW50_LEAD 天內才列試算名單。"""
    from datetime import date
    st = p.get("stage")
    cut = st in ("frozen", "announced")
    base = {"c": it["c"], "n": it["n"], "k": "s3", "sname": "臺灣50 提前卡位", "grade": sc["grade"],
            "px": it.get("px"), "stop": None, "stop_how": "不設，依日期出場", "exp": expect(sc), "hold": "持有約 2 個月",
            "why": [x for x in (f"市值排名第 {it['rank']} 名（{'截止日' if cut else '目前'}）" if it.get("rank") else None,
                                f"截止前 40 日漲幅 {pct(it.get('mom'))}" if it.get("mom") is not None else None) if x],
            "out": p.get("out"), "size": size(sc["grade"], it.get("px"), None),
            "out_how": (f"{_md(p.get('effective'))} 生效前一天收盤全部賣出；{_md(p.get('cutoff'))} 資料截止日名單沒有的，"
                        f"{_md(p.get('a_in'))} 開盤先賣出")}
    if st == "watch":
        try:
            lead = (date.fromisoformat(p["e_sig"]) - date.fromisoformat(last)).days if last and p.get("e_sig") else None
        except ValueError:
            lead = None
        if lead is None or lead < 0 or lead > TW50_LEAD:
            return None
        return {**base, "act": "佈局", "ent": p.get("e_in"), "tent": True, "fix": p.get("e_sig"),
                "ent_how": f"{_md(p.get('e_sig'))} 收盤依市值排名定案（目前為試算）；最多 4 檔、等額"}
    ta = it.get("ta") or {}
    if (it.get("e") or it.get("t")) and ta.get("st") == "cand":
        return {**base, "act": "佈局", "ent": ta.get("ent"), "ent_how": "截止日名單補位（最多 4 檔、等額）"}
    if (it.get("e") or it.get("t")) and ta.get("st") == "open":
        return {**base, "act": "持有中", "ent": ta.get("ent"), "entry": ta.get("entry"),
                "now_r": ta.get("r"), "now": ta.get("now"), "size": None}
    return None

# —— 回測方法 v3：月營收驚喜、財報驚喜（研究檔＋每日名單）與既有策略的新評級

V3_HOLD = {"p7": "持有到下一次換股、約 1 個月", "p3": "持有 60 個交易日、約 3 個月"}
V3_RULES = {
    "p7": ["形成日：每月 10 日（營收公告期限；遇假日順延到下一個交易日）收盤",
           "訊號：上個月營收比去年同月的增加金額，除以過去 12 個月這個差額的標準差（至少 6 個月）",
           "選股：當天市值與成交值符合範圍、上個月有公告營收的股票中，訊號最高的 5 檔，等額；不含金融保險業",
           "進場：形成日次一交易日開盤；開盤漲停買不到就不買",
           "出場：下一個形成日收盤；仍在新名單的續抱"],
    "p3": ["形成日：季報法定期限（5/15、8/14、11/14、3/31；遇假日順延到下一個交易日）收盤",
           "訊號：當季 EPS 比去年同季的增加，除以前 8 季（至少 4 季）這個差的標準差",
           "選股：當天市值與成交值符合範圍、當季有 EPS 的股票（至少 20 檔）中，訊號最高的 5 檔，等額",
           "進場：形成日次一交易日開盤；開盤漲停買不到就不買",
           "出場：持有 60 個交易日後收盤賣出；到下一個形成日前持有現金"],
}
BUCKET_TXT = {"M": "中型股：月底市值 50～300 億、20 日均成交值 ≥5,000 萬", "L": "大型股：月底市值 ≥300 億、20 日均成交值 ≥5,000 萬"}


def _side3(x: dict) -> tuple[dict, dict]:
    sel = {"n": x.get("n"), "xe": x.get("xe"), "t": x.get("t"), "drop5": x.get("drop5")}
    pay = {"n": x.get("n"), "ok": x.get("pay_ok"), "win": x.get("win"), "m": x.get("m"), "ratio": x.get("ratio")}
    return sel, pay


def grade_v3(r: dict, fwd: dict | None) -> dict:
    """研究檔一列＋前瞻 → 評級（同 bt3l._grade：A 另需樣本外報酬型態也過）。"""
    from .bt3 import grade3
    si, pi = _side3(r["ins"])
    so, po = _side3(r["oos"])
    nb = r.get("nb") or {}
    g = grade3(si, pi, r["ins"].get("x2"), {"n": nb.get("n"), "pos": nb.get("pos")} if nb.get("n") else None,
               event=r.get("event", False), oos=so if so.get("n") else None,
               fwd={"n": fwd.get("n", 0), "xe": fwd.get("xe")} if fwd else None)
    if g["grade"] == "A" and not po.get("ok"):
        g = {**g, "grade": "B", "why": g["why"] + ["樣本外報酬型態未達門檻（A 級需樣本內外都過）"]}
    return g


def _ev(oos: dict | None, ins: dict) -> tuple:
    """證據強弱排序鍵：有樣本外的在前，再依「樣本內、樣本外 t 值較小的那個」由大到小，同分看較大的那個。"""
    ti = ins.get("t") if ins else None
    to = oos.get("t") if oos else None
    if to is not None and ti is not None:
        return (0, -min(ti, to), -max(ti, to))
    return (1, -(ti if ti is not None else -9), 0)


def _exp3(d: dict, unit: str) -> dict:
    if not d or not d.get("n"):
        return {}
    return {**{k: d.get(k) for k in ("med", "p25", "p75", "win", "kwin", "lo", "n", "per10", "lo10")}, "event": True,
            "grp": "期", "unit": unit}                    # 每期＝同一期 5 檔等額平均


def _oos_txt(o: dict, unit: str) -> str:
    """「樣本外 2013-08～2021-09（98 月）：每月平均報酬比同一批股票高 1.41%（t 1.46）」"""
    xe, t = o.get("xe"), o.get("t")
    if xe is None:
        return ""
    return (f"樣本外 {str(o.get('d0') or '')[:7]}～{str(o.get('d1') or '')[:7]}（{o.get('n')} {unit}）："
            f"每{unit}平均報酬比同一批股票{'高' if xe >= 0 else '低'} {abs(xe):.2f}%（t {'—' if t is None else f'{t:.2f}'}）")


def build_v3(v3: dict, ex: dict, last: str | None) -> dict:
    """→ {"grades": 新策略與既有策略的 v3 評級（依證據強弱排序）, "picks"／"watch": 新策略本期 5 檔,
         "live": 頁面段落資料, "basket": 研究總表（整籃版本）, "meta"}"""
    import math
    from . import store
    res = store.read_json("bt3_research.json", {}) or {}
    grades, picks, watch, live = [], [], [], {}
    if isinstance(v3, dict) and not v3.get("err"):
        for k, v in v3.items():
            r = v.get("res") or {}
            if not r:
                continue
            g = grade_v3(r, v.get("fwd"))
            name = v["name"]
            grades.append({"k": k, "name": name, "kind": f"{'月' if v['src'] == 'p7' else '季'}換股・前 5 檔", "grade": g["grade"],
                           "why": g["why"], "oos": r["oos"], "ins": r["ins"], "unit": v["unit"], "fwd": v.get("fwd"),
                           "has_oos": True, "ev": _ev(r["oos"], r["ins"])})
            now = v.get("now") or {}
            for p in now.get("picks") or []:
                px = p.get("now") or p.get("entry")
                item = {"c": p["c"], "n": p["n"], "k": k, "sname": name, "grade": g["grade"],
                        "act": "持有中" if now.get("entered") else "佈局", "d": now.get("d"), "ent": now.get("ent"),
                        "entry": p.get("entry"), "now": p.get("now"), "now_r": p.get("now_r"), "out": now.get("out"),
                        "px": px, "stop": None, "stop_how": "不設停損，依日期換股",
                        "ent_how": f"{_md(now.get('d'))} 收盤決定，隔天開盤買進；開盤漲停買不到就不買",
                        "out_how": "下一次換股日收盤賣出；仍在新名單的續抱" if v["src"] == "p7" else "持有 60 個交易日後收盤賣出",
                        "exp": _exp3(r.get("dist") or {}, v["unit"]), "hold": V3_HOLD[v["src"]], "why": p.get("why") or [],
                        "size": size(g["grade"], px, None), "oos": True,
                        "oos_txt": _oos_txt(r["oos"], v["unit"])}
                _put(item, picks, watch)
            live[k] = {**{x: v.get(x) for x in ("k", "src", "b", "name", "unit", "since", "fwd", "now", "next")},
                       "grade": g["grade"], "why": g["why"], "rules": V3_RULES[v["src"]], "bucket": BUCKET_TXT[v["b"]],
                       "res": {x: r.get(x) for x in ("oos", "ins", "nb", "nb_oos", "sub", "fsub", "curve", "dist", "ver")}}
    for k, e in (ex or {}).items():
        if k == "err" or not isinstance(e, dict):
            continue
        grades.append({"k": k, "grade": e["grade"], "why": e["why"], "ins": {**e["sel"], **{x: e["pay"].get(x) for x in ("win", "m", "ratio")},
                                                                        "pay_ok": e["pay"].get("ok"), "x2": e.get("x2")},
                       "oos": None, "unit": e.get("unit"), "has_oos": False, "ev": _ev(None, e["sel"]), "nb": e.get("nb"),
                       "fwd": e.get("fwd")})
    basket = [{x: r.get(x) for x in ("k", "src", "name", "b", "ver", "unit", "grade", "why", "oos", "ins", "nb", "nb_oos", "sub")}
              for r in res.get("rows") or [] if r.get("ver") == "basket"]
    return {"grades": grades, "picks": picks, "watch": watch, "live": live, "basket": basket,
            "meta": {**(res.get("meta") or {}), "asof": res.get("asof"), "oos_end": res.get("oos_end")}}
