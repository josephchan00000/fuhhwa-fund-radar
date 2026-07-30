"""Squarified treemap 佈局（純數學、無外部套件）——ETF 持股異動的產業分層方塊圖。

2026-07-30 使用者需求：ETF 詳情要「外層是產業、內層是異動股票」的方塊圖，
面積 ∝ |金額|，加碼／新增同紅系、減碼／刪除同綠系。

為什麼在 Python 算而不在瀏覽器算：
  · 版面座標一律輸出**百分比**（0–100），HTML 端只要 `position:absolute` + `%`
    就能隨容器寬度自適應，不需要 JS 量測或重排；
  · 切換 ETF 時前端只要換一份已算好的 rect 清單，不必在 JS 再實作一次 squarify
    （同專案「算在產表端、前端純渲染」的慣例，如 macro sparkline、ETF 貢獻）。

演算法為經典 squarify（Bruls et al. 2000）：依值由大到小，逐段決定「橫排或直排」，
取最壞長寬比最小者，遞迴填滿剩餘矩形——方塊接近正方形、標籤才放得下。
"""
from __future__ import annotations

_EPS = 1e-9


def _layout_row(sizes: list[float], x: float, y: float, dy: float) -> list[dict]:
    """把 sizes 依「同一直欄、上下堆疊」排進寬 = 覆蓋面積/dy 的欄。"""
    covered = sum(sizes)
    w = covered / dy if dy > _EPS else 0.0
    out, cy = [], y
    for s in sizes:
        h = s / w if w > _EPS else 0.0
        out.append({"x": x, "y": cy, "w": w, "h": h})
        cy += h
    return out


def _layout_col(sizes: list[float], x: float, y: float, dx: float) -> list[dict]:
    """把 sizes 依「同一橫列、左右並排」排進高 = 覆蓋面積/dx 的列。"""
    covered = sum(sizes)
    h = covered / dx if dx > _EPS else 0.0
    out, cx = [], x
    for s in sizes:
        w = s / h if h > _EPS else 0.0
        out.append({"x": cx, "y": y, "w": w, "h": h})
        cx += w
    return out


def _layout(sizes: list[float], x: float, y: float, dx: float, dy: float) -> list[dict]:
    return _layout_row(sizes, x, y, dy) if dx >= dy else _layout_col(sizes, x, y, dx)


def _leftover(sizes: list[float], x: float, y: float,
              dx: float, dy: float) -> tuple[float, float, float, float]:
    covered = sum(sizes)
    if dx >= dy:
        w = covered / dy if dy > _EPS else 0.0
        return (x + w, y, max(dx - w, 0.0), dy)
    h = covered / dx if dx > _EPS else 0.0
    return (x, y + h, dx, max(dy - h, 0.0))


def _worst(sizes: list[float], x: float, y: float, dx: float, dy: float) -> float:
    rects = _layout(sizes, x, y, dx, dy)
    worst = 0.0
    for r in rects:
        if r["w"] <= _EPS or r["h"] <= _EPS:
            return float("inf")
        worst = max(worst, r["w"] / r["h"], r["h"] / r["w"])
    return worst


def _squarify(sizes: list[float], x: float, y: float, dx: float, dy: float) -> list[dict]:
    if not sizes or dx <= _EPS or dy <= _EPS:
        return []
    if len(sizes) == 1:
        return _layout(sizes, x, y, dx, dy)
    i = 1
    while (i < len(sizes)
           and _worst(sizes[:i], x, y, dx, dy) >= _worst(sizes[:i + 1], x, y, dx, dy)):
        i += 1
    cur, rest = sizes[:i], sizes[i:]
    lx, ly, ldx, ldy = _leftover(cur, x, y, dx, dy)
    return _layout(cur, x, y, dx, dy) + _squarify(rest, lx, ly, ldx, ldy)


def layout(items: list[tuple], x: float = 0.0, y: float = 0.0,
           w: float = 100.0, h: float = 100.0) -> list[dict]:
    """items = [(key, value), …] → [{key, value, x, y, w, h}]（座標與傳入單位相同）。

    value ≤ 0 或 None 者剔除（面積無意義）；依 value 由大到小排。
    """
    vals = [(k, float(v)) for k, v in items if v is not None and float(v) > 0]
    vals.sort(key=lambda kv: -kv[1])
    if not vals or w <= _EPS or h <= _EPS:
        return []
    total = sum(v for _, v in vals)
    sizes = [v / total * w * h for _, v in vals]
    rects = _squarify(sizes, x, y, w, h)
    return [{"key": k, "value": v, **r} for (k, v), r in zip(vals, rects)]


def grouped(groups: list[tuple], w: float = 100.0, h: float = 100.0,
            gap: float = 1.2, head: float = 7.0,
            head_min_h: float = 18.0) -> list[dict]:
    """兩層 treemap：外層＝群組（產業）、內層＝群組內項目（個股）。

    groups = [(group_key, [(item_key, value), …]), …]
    回傳 [{key, value, x, y, w, h, head, items:[{key, value, x, y, w, h}]}]

    · 外層面積 ∝ 群組值合計；內層在群組矩形內縮 gap、上方保留 head 給產業標籤。
    · 群組高度不足（< head_min_h）時不留標籤空間（head=0）——小方塊硬留標籤會把
      內層壓成細線，寧可標籤只進 title 提示（渲染端據 head 判斷是否印標籤）。
    """
    tot = [(gk, sum(float(v) for _, v in its if v is not None and float(v) > 0))
           for gk, its in groups]
    outer = layout(tot, 0.0, 0.0, w, h)
    by_key = {gk: its for gk, its in groups}
    out = []
    for g in outer:
        hd = head if g["h"] >= head_min_h else 0.0
        ix = g["x"] + gap
        iy = g["y"] + gap + hd
        iw = max(g["w"] - gap * 2, 0.0)
        ih = max(g["h"] - gap * 2 - hd, 0.0)
        out.append({**g, "head": hd,
                    "items": layout(by_key.get(g["key"]) or [], ix, iy, iw, ih)})
    return out
