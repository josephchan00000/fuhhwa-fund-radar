"""VCP v2（tw-superstock-lab `features.VCP_V2` 的純 Python 版，給每日「超級飆股觀察名單」用；CI 不裝 pandas）。

規則（tw-superstock-lab/reports/P4_S01_plan.md 第 2、9 節）：
  · 轉折門檻＝max(3%, 1.5 × ATR14 ÷ 收盤)：往上一段裡最低跌破候選高點 × (1 − 門檻) 確認高點，往下一段裡最高漲過候選低點 × (1 + 門檻) 確認低點；
  · 基底起點＝近 260 日最高點（同價取最早），且至少 30 日前；收縮＝每個已確認高點配它之後的低點（最後一段可用目前最低）；
  · 成立＝2～6 段、每段 < 前一段 × 1.1、第一段 ≤ 35%、最後一段 ≤ 10%、收盤 ≥ 樞紐（最後一個已確認高點）× 0.9、
    10 日 ÷ 50 日均量 ≤ 0.7。
價格用 superx.Px 的日線（已前值補齊）；研究用的是含息還原價，除息日附近的段落深度可能有一點差別。"""
from __future__ import annotations

SPEC = {"thr": 0.03, "atr_k": 1.5, "win": 260, "base_min": 30, "n_min": 2, "n_max": 6, "grow": 1.1, "d1_max": 0.35,
        "dn_max": 0.10, "near": 0.9, "dry": 0.7}


def _mean(xs: list, k_min: int):
    v = [x for x in xs if x is not None]
    return sum(v) / len(v) if len(v) >= k_min else None


def thresholds(h: list, l: list, c: list, a: int, b: int, spec: dict = SPEC) -> dict[int, float]:
    """a..b 每天的轉折門檻（ATR14 用當天以前 14 日的真實波幅，至少 10 日）。"""
    out = {}
    tr = {}
    for t in range(max(1, a - 14), b + 1):
        if h[t] is None or l[t] is None or c[t - 1] is None:
            continue
        tr[t] = max(h[t], c[t - 1]) - min(l[t], c[t - 1])
    for t in range(a, b + 1):
        atr = _mean([tr.get(k) for k in range(t - 13, t + 1)], 10)
        th = spec["atr_k"] * atr / c[t] if atr is not None and c[t] else None
        out[t] = max(spec["thr"], th) if th is not None else spec["thr"]
    return out


def contractions(h: list, l: list, s: int, t: int, th: dict[int, float]) -> tuple[list[tuple], float | None]:
    """從基底起點 s 推到 t 的 3%／ATR 轉折 → ([(高點, 低點, 高點日, 低點日)], 樞紐)。"""
    sw: list[tuple] = []
    up, cv, ci = True, h[s], s
    for i in range(s + 1, t + 1):
        hi, lo = h[i], l[i]
        if hi is None or lo is None:
            continue
        thr = th.get(i, SPEC["thr"])
        if up:
            if hi > cv:
                cv, ci = hi, i
            elif lo <= cv * (1 - thr):
                sw.append(("H", ci, cv))
                up, cv, ci = False, lo, i
        else:
            if lo < cv:
                cv, ci = lo, i
            elif hi >= cv * (1 + thr):
                sw.append(("L", ci, cv))
                up, cv, ci = True, hi, i
    pairs = []
    for k in range(0, len(sw), 2):
        _, hi_i, hi_v = sw[k]
        if k + 1 < len(sw):
            _, lo_i, lo_v = sw[k + 1]
        elif not up:
            lo_i, lo_v = ci, cv
        else:
            continue
        pairs.append((hi_v, lo_v, hi_i, lo_i))
    return pairs, (pairs[-1][0] if pairs else None)


def check(h: list, l: list, c: list, v: list, i: int, spec: dict = SPEC) -> dict | None:
    """第 i 天收盤時 VCP 是否成立；資料不夠（不到一年或沒有基底）回 None。"""
    if i < spec["win"] or c[i] is None:
        return None
    a = i - spec["win"] + 1
    hs = [(x, k) for k, x in enumerate(h[a:i + 1], start=a) if x is not None]
    if not hs:
        return None
    top = max(x for x, _ in hs)
    s = next(k for x, k in hs if x == top)
    if i - s < spec["base_min"]:
        return {"ok": False, "why": "基底不到 30 日"}
    pairs, pivot = contractions(h, l, s, i, thresholds(h, l, c, s, i, spec))
    n = len(pairs)
    ds = [1 - lo / hi for hi, lo, _, _ in pairs]
    v10, v50 = _mean(v[i - 9:i + 1], 8), _mean(v[i - 49:i + 1], 40)
    dry = v10 / v50 if v10 is not None and v50 else None
    ok = (spec["n_min"] <= n <= spec["n_max"] and ds[0] <= spec["d1_max"] and ds[-1] <= spec["dn_max"]
          and all(ds[k] < spec["grow"] * ds[k - 1] for k in range(1, n)) and pivot is not None
          and c[i] >= spec["near"] * pivot and dry is not None and dry <= spec["dry"])
    return {"ok": bool(ok), "pivot": pivot, "n": n, "d1": ds[0] if ds else None, "dn": ds[-1] if ds else None,
            "dry": dry, "base": i - s, "low": pairs[-1][1] if pairs else None, "ds": ds}
