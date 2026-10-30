"""個股報告的圖（伺服器端畫 SVG；列印清楚、深淺色由頁面 CSS 的 class 上色，不把顏色寫死在屬性裡）。

一張圖只有一條縱軸（dataviz 準則：不畫雙軸）。營收與年增率這種兩個單位的，畫成上下兩格、共用橫軸。
顏色：k1 藍、k2 橘、k3 綠松（類別色，照 dataviz 參考色盤順序）；up 紅＝漲、dn 綠＝跌（台股慣例，數字另帶正負號）；mu 灰。
每個點、每根柱都有 <title>，滑過看數字。
"""
from __future__ import annotations

import math
from html import escape

W = 640
PL, PR, PT, PB = 56, 14, 22, 32


def fmt(v, d: int | None = None) -> str:
    if v is None:
        return "—"
    if d is None:
        a = abs(v)
        d = 0 if a >= 100 else 1 if a >= 10 else 2
    s = f"{v:,.{d}f}"
    return s


def ticks(lo: float, hi: float, n: int = 4) -> list[float]:
    if hi <= lo:
        hi = lo + 1
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    step = min((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw), default=10 * mag)
    a = math.floor(lo / step) * step
    out = []
    v = a
    while v <= hi + step * 1e-9:
        out.append(round(v, 10))
        v += step
    return out


def _yr(vals, zero=False, pad=0.06):
    v = [x for x in vals if x is not None]
    if not v:
        return 0.0, 1.0
    lo, hi = min(v), max(v)
    if zero:
        lo, hi = min(lo, 0), max(hi, 0)
    if hi == lo:
        hi, lo = hi + 1, lo - 1
    span = hi - lo
    return lo - span * pad * (0 if zero and lo == 0 else 1), hi + span * pad


def tick_fmt(tk: list[float]):
    """刻度的小數位數依間距決定（間距是整數就不帶小數）。"""
    step = abs(tk[1] - tk[0]) if len(tk) > 1 else 1
    d = 0 if step >= 1 - 1e-9 else 1 if step >= 0.1 - 1e-12 else 2
    return lambda v: fmt(v, d)


def ticks_cover(lo: float, hi: float, n: int = 4) -> list[float]:
    """刻度一定蓋住 [lo, hi]（最後一格不夠就多加一格）。"""
    tk = ticks(lo, hi, n)
    if len(tk) > 1 and tk[-1] < hi - 1e-9:
        tk.append(round(tk[-1] + (tk[1] - tk[0]), 10))
    return tk


class Panel:
    """一格：x 是類別序號（0..n-1），y 線性。"""

    def __init__(self, n: int, lo: float, hi: float, top: float, h: float, yfmt=None, unit: str = "", nt: int = 4):
        tk = ticks_cover(lo, hi, nt)
        self.lo, self.hi = min(lo, tk[0]), max(hi, tk[-1])
        self.tk = [t for t in tk if self.lo - 1e-9 <= t <= self.hi + 1e-9]
        self.n, self.top, self.h = n, top, h
        self.yfmt = yfmt or tick_fmt(self.tk)
        self.unit = unit
        self.bw = (W - PL - PR) / max(n, 1)

    def x(self, i: float) -> float:
        return PL + self.bw * (i + 0.5)

    def y(self, v: float) -> float:
        return self.top + self.h * (1 - (v - self.lo) / (self.hi - self.lo))

    def grid(self) -> str:
        out = []
        for t in self.tk:
            yy = self.y(t)
            cls = "g0" if abs(t) < 1e-12 and self.lo < 0 < self.hi else "g"
            out.append(f'<line class="{cls}" x1="{PL}" x2="{W - PR}" y1="{yy:.1f}" y2="{yy:.1f}"/>'
                       f'<text class="ty" x="{PL - 5}" y="{yy + 3.5:.1f}" text-anchor="end">{escape(self.yfmt(t))}</text>')
        if self.unit:
            out.append(f'<text class="tu" x="{PL + 2}" y="{self.top - 7:.1f}">{escape(self.unit)}</text>')
        return "".join(out)

    def bars(self, vals, cls="k1", sign=False, names=None, label=None, w=0.62, off=0.0) -> str:
        out = []
        z = self.y(max(self.lo, min(0, self.hi)))
        for i, v in enumerate(vals):
            if v is None:
                continue
            yy = self.y(v)
            c = ("up" if v >= 0 else "dn") if sign else cls
            bw = self.bw * w
            x0 = self.x(i) - bw / 2 + off * self.bw
            t = f"{names[i] if names else ''} {label + ' ' if label else ''}{fmt(v)}{self.unit if self.unit in ('%',) else ''}"
            out.append(f'<rect class="{c}" x="{x0:.1f}" y="{min(yy, z):.1f}" width="{bw:.1f}" height="{max(abs(z - yy), 0.6):.1f}" rx="1.5">'
                       f'<title>{escape(t.strip())}</title></rect>')
        return "".join(out)

    def line(self, vals, cls="k1", dash=False, names=None, label=None, dots=False, width=2.0) -> str:
        pts, segs = [], []
        for i, v in enumerate(vals):
            if v is None:
                if pts:
                    segs.append(pts)
                pts = []
                continue
            pts.append((self.x(i), self.y(v), i, v))
        if pts:
            segs.append(pts)
        out = []
        da = ' stroke-dasharray="5 4"' if dash else ""
        for s in segs:
            d = " ".join(f"{'M' if j == 0 else 'L'}{x:.1f},{y:.1f}" for j, (x, y, _, _) in enumerate(s))
            out.append(f'<path class="ln {cls}" d="{d}" stroke-width="{width}"{da}/>')
            if dots or len(s) == 1:
                for x, y, i, v in s:
                    t = f"{names[i] if names else ''} {label + ' ' if label else ''}{fmt(v)}"
                    out.append(f'<circle class="dt {cls}" cx="{x:.1f}" cy="{y:.1f}" r="3"><title>{escape(t.strip())}</title></circle>')
        return "".join(out)

    def hline(self, v, cls="mu", text="", dash=True, right=True) -> str:
        if v is None or not (self.lo <= v <= self.hi):
            return ""
        yy = self.y(v)
        da = ' stroke-dasharray="4 4"' if dash else ""
        lab = (f'<text class="tl {cls}" x="{W - PR - 2 if right else PL + 4}" y="{yy - 4:.1f}" '
               f'text-anchor="{"end" if right else "start"}">{escape(text)}</text>') if text else ""
        return f'<line class="hl {cls}" x1="{PL}" x2="{W - PR}" y1="{yy:.1f}" y2="{yy:.1f}"{da}/>' + lab


def _xlabels(p: Panel, labels: list[str], y: float, every: int | None = None) -> str:
    n = len(labels)
    if not n:
        return ""
    every = every or max(1, math.ceil(n / 6))
    out = []
    idx = list(range(0, n, every))
    if idx[-1] != n - 1:
        if len(idx) > 1:
            idx[-1] = n - 1                       # 最後一個一定標，換掉太近的前一個
        else:
            idx.append(n - 1)
    for i in idx:
        anc = "start" if i == 0 and p.x(i) - PL < 20 else "end" if i == n - 1 and W - PR - p.x(i) < 20 else "middle"
        out.append(f'<text class="tx" x="{p.x(i):.1f}" y="{y + 4:.1f}" text-anchor="{anc}">{escape(labels[i])}</text>')
    return "".join(out)


def legend(items: list[tuple[str, str, str]]) -> str:
    """[(class, 名稱, 'line'|'bar'|'dash')] → HTML 圖例（字用文字色，色塊帶身分）。"""
    out = []
    for cls, name, kind in items:
        out.append(f'<span class="lg"><i class="sw {kind} {cls}"></i>{escape(name)}</span>')
    return '<div class="lgs">' + "".join(out) + "</div>"


def _svg(h: float, body: str, label: str) -> str:
    return (f'<svg class="ch" viewBox="0 0 {W} {h:.0f}" role="img" aria-label="{escape(label)}" '
            f'preserveAspectRatio="xMidYMid meet">{body}</svg>')


# ── 圖 ─────────────────────────────────────────────────────────────────────

def price_chart(dates: list[str], px: list, ix: list, tp=None, hi52=None, label="股價", unit="元", ix_name="加權指數") -> str:
    """股價＋大盤指數換算成同一起點（一條軸）＋目標價虛線。每週取一點。"""
    keep = [i for i in range(len(dates)) if px[i]]
    if len(keep) < 2:
        return ""
    wk, last_w = [], None
    for i in keep:
        w = dates[i][:4] + str((int(dates[i][5:7]) - 1) * 5 + (int(dates[i][8:]) - 1) // 7)
        if w != last_w:
            wk.append(i)
            last_w = w
        else:
            wk[-1] = i
    p0 = next(px[i] for i in wk)
    i0 = next((ix[i] for i in wk if ix[i]), None)
    a = [px[i] for i in wk]
    b = [ix[i] / i0 * p0 if ix[i] and i0 else None for i in wk]
    names = [dates[i] for i in wk]
    lo, hi = _yr(a + b + ([tp] if tp else []))
    p = Panel(len(wk), lo, hi, PT, 190, unit=unit)
    body = p.grid() + p.line(b, "mu", names=names, label=f"{ix_name}（換算）", width=1.6) + p.line(a, "k1", names=names, label="收盤")
    if tp:
        body += p.hline(tp, "k2", f"目標價 {fmt(tp)}")
    labs = [d[2:7].replace("-", "/") for d in names]
    body += _xlabels(p, labs, PT + 190 + 16)
    return _svg(PT + 190 + PB, body, label) + legend([("k1", "收盤", "line"), ("mu", f"{ix_name}（換算成同一起點）", "line")]
                                                    + ([("k2", "目標價", "dash")] if tp else []))


def bars_yoy(labels: list[str], vals: list, yoy: list, unit="億元", label="營收", title_v="營收", title_y="年增") -> str:
    """上格數值柱、下格年增率（%）柱，共用橫軸。"""
    n = len(labels)
    lo, hi = _yr(vals, zero=True)
    p1 = Panel(n, 0 if lo >= 0 else lo, hi, PT + 4, 130, unit=unit)
    ylo, yhi = _yr(yoy, zero=True)
    p2 = Panel(n, ylo, yhi, PT + 4 + 130 + 34, 70, unit="%", yfmt=lambda v: fmt(v, 0), nt=2)
    body = (p1.grid() + p1.bars(vals, "k1", names=labels, label=title_v) + p2.grid()
            + p2.bars(yoy, sign=True, names=labels, label=title_y)
            + f'<text class="tu" x="{W - PR}" y="{p2.top - 7:.1f}" text-anchor="end">{escape(title_y)}（%）</text>'
            + _xlabels(p2, labels, p2.top + p2.h + 16))
    return _svg(p2.top + p2.h + PB, body, label)


def lines(labels: list[str], series: list[tuple[str, str, list]], unit="%", label="", zero=False, dots=True, h=170) -> str:
    """[(class, 名稱, 值)] 多條線、一條軸。"""
    allv = [v for _, _, vs in series for v in vs]
    lo, hi = _yr(allv, zero=zero)
    p = Panel(len(labels), lo, hi, PT + 4, h, unit=unit)
    body = p.grid()
    for cls, name, vs in series:
        body += p.line(vs, cls, names=labels, label=name, dots=dots)
    body += _xlabels(p, labels, p.top + h + 16)
    return _svg(p.top + h + PB, body, label) + legend([(c, n, "line") for c, n, _ in series])


def grouped_bars(labels: list[str], series: list[tuple[str, str, list]], unit="億元", label="", h=170) -> str:
    allv = [v for _, _, vs in series for v in vs]
    lo, hi = _yr(allv, zero=True)
    p = Panel(len(labels), lo, hi, PT + 4, h, unit=unit)
    k = len(series)
    body = p.grid()
    for j, (cls, name, vs) in enumerate(series):
        body += p.bars(vs, cls, names=labels, label=name, w=0.8 / k, off=(j - (k - 1) / 2) * 0.8 / k)
    body += _xlabels(p, labels, p.top + h + 16)
    return _svg(p.top + h + PB, body, label) + legend([(c, n, "bar") for c, n, _ in series])


def bars_line(labels: list[str], bars: tuple[str, str, list], line: tuple[str, str, list], unit="元", label="", h=170) -> str:
    """同一單位的柱＋線（例：每季 EPS 與近四季 EPS）。"""
    allv = list(bars[2]) + list(line[2])
    lo, hi = _yr(allv, zero=True)
    p = Panel(len(labels), lo, hi, PT + 4, h, unit=unit)
    body = p.grid() + p.bars(bars[2], bars[0], names=labels, label=bars[1]) + p.line(line[2], line[0], names=labels, label=line[1], dots=True)
    body += _xlabels(p, labels, p.top + h + 16)
    return _svg(p.top + h + PB, body, label) + legend([(bars[0], bars[1], "bar"), (line[0], line[1], "line")])


def river(labels: list[str], px: list, base: list, mults: list[float], unit="元", label="", name="本益比", tp=None) -> str:
    """月底收盤＋「倍數 × 當時的近四季 EPS（或每股淨值）」幾條線（一條軸）。"""
    bands = [[b * m if b and b > 0 else None for b in base] for m in mults]
    allv = [v for v in px if v] + [v for bb in bands for v in bb if v] + ([tp] if tp else [])
    lo, hi = _yr(allv, zero=True)
    p = Panel(len(labels), lo, hi, PT + 4, 190, unit=unit)
    body = p.grid()
    cls = ["k3", "mu", "k2"]
    for j, (m, bb) in enumerate(zip(mults, bands)):
        body += p.line(bb, cls[j % 3], dash=True, names=labels, label=f"{fmt(m, 1)} 倍", width=1.4)
    body += p.line(px, "k1", names=labels, label="月底收盤", width=2.2)
    if tp:
        body += p.hline(tp, "k2", f"目標價 {fmt(tp)}", dash=False)
    body += _xlabels(p, labels, p.top + 190 + 16)
    leg = [("k1", "月底收盤", "line")] + [(cls[j % 3], f"{name} {fmt(m, 1)} 倍", "dash") for j, m in enumerate(mults)]
    return _svg(p.top + 190 + PB, body, label) + legend(leg)


def football(rows: list[tuple[str, float, float, float | None]], px: float, tp: float | None, unit="元", label="估值區間") -> str:
    """[(名稱, 低, 高, 中)] 每一列：上面一行左邊名稱、右邊「低～高」，下面一條橫條；現價、目標價各一條直線。
    名稱放在橫條上方（不是左邊），手機上字放大也不會被切掉。"""
    rows = [r for r in rows if r[1] is not None and r[2] is not None]
    if not rows:
        return ""
    lo = min([r[1] for r in rows] + [px] + ([tp] if tp else []))
    hi = max([r[2] for r in rows] + [px] + ([tp] if tp else []))
    tk = ticks_cover(lo * 0.95, hi * 1.05)
    a, b = tk[0], tk[-1]
    tf = tick_fmt(tk)
    x0, x1 = 12, W - PR

    def X(v):
        return x0 + (x1 - x0) * (v - a) / (b - a)
    rh, top = 44, PT + 6
    yb = top + rh * len(rows)
    out = []
    for t in tk:
        out.append(f'<line class="g" x1="{X(t):.1f}" x2="{X(t):.1f}" y1="{top}" y2="{yb:.1f}"/>'
                   f'<text class="tx" x="{X(t):.1f}" y="{yb + 16:.1f}" text-anchor="middle">{escape(tf(t))}</text>')
    for j, (name, l, r, m) in enumerate(rows):
        y = top + rh * j
        out.append(f'<text class="ty" x="{x0}" y="{y + 15:.1f}">{escape(name)}</text>'
                   f'<text class="tv" x="{x1}" y="{y + 15:.1f}" text-anchor="end">{escape(fmt(l))}～{escape(fmt(r))} {escape(unit)}</text>'
                   f'<rect class="k1 fb" x="{X(l):.1f}" y="{y + 22:.1f}" width="{max(X(r) - X(l), 2):.1f}" height="14" rx="3">'
                   f'<title>{escape(f"{name}：{fmt(l)}～{fmt(r)}{unit}")}</title></rect>')
        if m is not None:
            out.append(f'<line class="fbm" x1="{X(m):.1f}" x2="{X(m):.1f}" y1="{y + 22:.1f}" y2="{y + 36:.1f}"/>')
    out.append(f'<line class="hl mu" x1="{X(px):.1f}" x2="{X(px):.1f}" y1="{top - 4}" y2="{yb:.1f}"/>'
               f'<text class="tl mu" x="{X(px):.1f}" y="{yb + 34:.1f}" text-anchor="middle">現價 {escape(fmt(px))}</text>')
    if tp:
        out.append(f'<line class="hl k2" x1="{X(tp):.1f}" x2="{X(tp):.1f}" y1="{top - 4}" y2="{yb:.1f}" stroke-dasharray="4 3"/>'
                   f'<text class="tl k2" x="{X(tp):.1f}" y="{top - 8:.1f}" text-anchor="middle">目標價 {escape(fmt(tp))}</text>')
    return _svg(yb + 40, "".join(out), label)


def scatter(points: list[tuple[str, float, float, str]], xlabel: str, ylabel: str, label="") -> str:
    """[(名稱, x, y, class)]；名稱直接標在點旁（同業不到十家）。"""
    pts = [p for p in points if p[1] is not None and p[2] is not None]
    if len(pts) < 2:
        return ""
    xlo, xhi = _yr([p[1] for p in pts], zero=True, pad=0.12)
    ylo, yhi = _yr([p[2] for p in pts], zero=True, pad=0.12)
    tx, ty = ticks_cover(xlo, xhi), ticks_cover(ylo, yhi)
    fx, fy = tick_fmt(tx), tick_fmt(ty)
    xlo, xhi, ylo, yhi = min(xlo, tx[0]), max(xhi, tx[-1]), min(ylo, ty[0]), max(yhi, ty[-1])
    h = 240
    top = PT + 4

    def X(v):
        return PL + (W - PL - PR) * (v - xlo) / (xhi - xlo)

    def Y(v):
        return top + h * (1 - (v - ylo) / (yhi - ylo))
    out = []
    for t in ty:
        if ylo <= t <= yhi:
            out.append(f'<line class="g" x1="{PL}" x2="{W - PR}" y1="{Y(t):.1f}" y2="{Y(t):.1f}"/>'
                       f'<text class="ty" x="{PL - 5}" y="{Y(t) + 3.5:.1f}" text-anchor="end">{escape(fy(t))}</text>')
    for t in tx:
        if xlo <= t <= xhi:
            out.append(f'<text class="tx" x="{X(t):.1f}" y="{top + h + 16:.1f}" text-anchor="middle">{escape(fx(t))}</text>')
    out.append(f'<text class="tu" x="{W - PR}" y="{top + h + 32:.1f}" text-anchor="end">{escape(xlabel)} →</text>'
               f'<text class="tu" x="{PL}" y="{top - 9:.1f}">↑ {escape(ylabel)}</text>')
    for name, x, y, cls in pts:
        out.append(f'<circle class="dt {cls}" cx="{X(x):.1f}" cy="{Y(y):.1f}" r="{6 if cls == "k2" else 4.5}">'
                   f'<title>{escape(f"{name}：{xlabel} {fmt(x)}、{ylabel} {fmt(y)}")}</title></circle>'
                   f'<text class="tp" x="{X(x) + 8:.1f}" y="{Y(y) + 4:.1f}">{escape(name)}</text>')
    return _svg(top + h + 38, "".join(out), label)
