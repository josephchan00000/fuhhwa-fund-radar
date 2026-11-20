"""台股股市位階（規格 arm/lab/mposspec.py VER 1；docs/lab_earnings_plan.md 第 8、9 節）：只描述現在在哪裡。

  compute(B)        → 每天的四組分數、原值、位階（B＝arm/lab/heatcalc.build() 的結果）
  peaks(d, v)       → 近 CHART_YEARS 年的高點、低點
  record(X, log)    → 每天第一次算出來的數字記下來（只增不改；data/lab/heat/mpos_log.json）
  block(B)          → 市場頁（x9m.html）最上面那一塊 HTML（伺服器端畫好、含 SVG；CSS class 一律 mpz- 開頭）
heatpage.build 建正式頁（寫到預設的 x9m.html）時才記 log；測試建到別的地方不寫。
"""
from __future__ import annotations

import bisect
import html
import json
from pathlib import Path

from . import mposspec as S

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / "data" / "lab" / "heat" / "mpos_log.json"


def log_path(mk: str = "tw") -> Path:
    """公布的數字：台股 mpos_log.json、美股每個指數 mpos_log_{指數}.json（VER 3）。"""
    return LOG if mk == "tw" else LOG.with_name(f"mpos_log_{mk}.json")


def groups(inc: dict, defs=None) -> list[tuple[str, list[str]]]:
    """規格第 1 點：清單和現在有算分的項目取交集（defs＝S.GROUPS 台股、S.GROUPS_US 美股）。"""
    on = {k for ks in (inc or {}).values() for k in ks}
    return [(name, [k for k in ks if k in on]) for name, ks in (defs or S.GROUPS)]


def compute(B: dict, defs=None) -> dict:
    cal, heat = B["cal"], B["heat"]
    T = len(cal)
    G = groups(B.get("inc") or {}, defs)
    gs = {}
    for name, ks in G:
        need = min(S.MIN_ITEMS, len(ks)) if ks else 1          # VER 2（VER 1＝一半，無條件進位）
        col = []
        for i in range(T):
            vs = [heat[k][i] for k in ks if k in heat and heat[k][i] is not None]
            col.append(sum(vs) / len(vs) if ks and len(vs) >= need else None)
        gs[name] = col
    raw = []
    for i in range(T):
        vs = [gs[n][i] for n, ks in G if ks]               # VER 3：沒有算分項目的組不放進平均（台股四組都有）
        raw.append(sum(vs) / len(vs) if all(v is not None for v in vs) else None)
    v, win = [], []                                       # win＝過去 WIN 天（含當天）有值的原值，排好序
    q = []                                                # 照日期的佇列，滑出視窗時從 win 拿掉
    for i in range(T):
        if raw[i] is not None:
            bisect.insort(win, raw[i])
            q.append((i, raw[i]))
        while q and q[0][0] <= i - S.WIN:
            win.pop(bisect.bisect_left(win, q.pop(0)[1]))
        if raw[i] is None or len(win) < S.MIN_DAYS:
            v.append(None)
            continue
        v.append(round(10 * bisect.bisect_left(win, raw[i]) / len(win), 1))
    return {"cal": cal, "g": gs, "raw": raw, "v": v, "items": {n: ks for n, ks in G}}


def label(x: float) -> str:
    return ("極端低位" if x <= S.X_LOW else "低位" if x <= S.LOW else "極端高位" if x >= S.X_HIGH
            else "高位" if x >= S.HIGH else "中間")


def peaks(d: list[str], v: list) -> list[tuple[str, float, str]]:
    """規格第 6 點：前後 PEAK_GAP 個交易日內最高（≥ HIGH）／最低（≤ LOW）；同一種點相隔 < PEAK_GAP 只留比較極端的。"""
    G = S.PEAK_GAP
    out: list[list] = []
    for i, x in enumerate(v):
        if x is None:
            continue
        win = [y for y in v[max(0, i - G):i + G + 1] if y is not None]
        kind = "hi" if x >= S.HIGH and x == max(win) else "lo" if x <= S.LOW and x == min(win) else None
        if not kind:
            continue
        if out and out[-1][2] == kind and i - out[-1][3] < G:
            if (kind == "hi" and x > out[-1][1]) or (kind == "lo" and x < out[-1][1]):
                out[-1] = [d[i], x, kind, i]
            continue
        out.append([d[i], x, kind, i])
    return [(a, b, c) for a, b, c, _ in out]


def read_log(path: Path | None = None) -> dict:
    try:
        return json.loads((path or LOG).read_text(encoding="utf-8")).get("days") or {}
    except (OSError, ValueError, AttributeError):
        return {}


def record(X: dict, log: dict, path: Path | None = None) -> bool:
    """每天第一次算出來的數字記下來，之後不改（規格第 7 點）。"""
    i = len(X["v"]) - 1
    d, x = X["cal"][i], X["v"][i]
    if x is None or d in log:
        return False
    path = path or LOG
    log[d] = {"v": x, "raw": round(X["raw"][i], 2), "g": [None if X["g"][n][i] is None else round(X["g"][n][i], 1) for n in X["g"]]}
    rows = [json.dumps(k) + ":" + json.dumps(log[k], ensure_ascii=False, separators=(",", ":")) for k in sorted(log)]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text('{"ver":' + str(S.VER) + ',"days":{\n' + ",\n".join(rows) + "\n}}\n", encoding="utf-8")
    tmp.replace(path)
    return True


# ── 頁面 ─────────────────────────────────────────────────────────────────────

CSS = (
    ".mpz{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:12px 14px;margin:0 0 14px}"
    ".mpz-top{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(0,1fr);gap:14px}"
    ".mpz-h{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 12px}.mpz-h h2{margin:0;font-size:17px}.mpz-h small{color:var(--mut)}"
    ".mpz-big{font-size:34px;font-weight:800;line-height:1;font-variant-numeric:tabular-nums}.mpz-big small{font-size:14px;color:var(--mut);font-weight:400}"
    ".mpz-lv{font-weight:700;font-size:16px}.mpz-lv.lo{color:var(--t0)}.mpz-lv.hi{color:var(--t4)}.mpz-lv.mid{color:var(--ink2)}"
    ".mpz-sl{position:relative;height:8px;border-radius:4px;margin:12px 0 2px;"
    "background:linear-gradient(90deg,var(--c0) 0 30%,var(--line2) 30% 80%,var(--c4) 80%)}"
    ".mpz-sl b{position:absolute;top:-5px;width:18px;height:18px;margin-left:-9px;border-radius:50%;background:var(--ink);border:3px solid var(--panel)}"
    ".mpz-sl i{position:absolute;top:-4px;width:16px;height:16px;margin-left:-8px;border-radius:50%;border:2px solid var(--mut)}"
    ".mpz-sll{display:flex;justify-content:space-between;font-size:11px;color:var(--mut)}"
    ".mpz-sub{font-size:12.5px;color:var(--ink2);margin:6px 0 0}.mpz-fix{font-size:12px;color:var(--warn);margin:4px 0 0}"
    ".mpz-gs{display:grid;grid-template-columns:1fr 1fr;gap:6px 14px;margin-top:10px}"
    ".mpz-g{display:grid;grid-template-columns:5.5em 1fr 4.5em;align-items:center;gap:8px;background:var(--card2);border-radius:8px;padding:6px 10px;font-size:13px}"
    ".mpz-g .hb{background:var(--line)}.mpz-g em{font-style:normal;font-size:12px;color:var(--mut);text-align:right}"
    ".mpz-m{display:flex;align-items:baseline;gap:8px;padding:6px 0;border-bottom:1px solid var(--line);font-size:13.5px}"
    ".mpz-m span{flex:1}.mpz-m b{font-size:18px;font-variant-numeric:tabular-nums}.mpz-m small{color:var(--mut);min-width:6.5em;text-align:right}"
    ".mpz-ct{font-size:14px;margin:14px 0 4px}.mpz-ct small{font-weight:400;color:var(--mut);font-size:12px;margin-left:6px}"
    ".mpz-svg{display:block;width:100%;height:auto}.mpz-svg .br{fill:var(--zh)}.mpz-svg .bg{fill:var(--zc)}"
    ".mpz-svg .ln{fill:none;stroke:var(--acc);stroke-width:1.4}.mpz-svg .gl{stroke:var(--line);stroke-dasharray:3 4}"
    ".mpz-svg text{font-size:11px;fill:var(--mut)}.mpz-svg .pl{fill:var(--ink2);font-weight:600}"
    ".mpz-svg .ph{fill:var(--c4);stroke:var(--panel);stroke-width:2}.mpz-svg .pg{fill:var(--c0);stroke:var(--panel);stroke-width:2}"
    ".mpz-cw{overflow-x:auto;-webkit-overflow-scrolling:touch}"
    "@media (max-width:760px){.mpz-top{grid-template-columns:1fr}.mpz-gs{grid-template-columns:1fr}}"
    "@media (max-width:640px){.mpz-cw .mpz-svg{min-width:780px}}"
)


def _md(d: str) -> str:
    return f"{int(d[5:7])}/{int(d[8:10])}"


def _chart(d: list[str], v: list, pk: list) -> str:
    W, H, L, R, T, Bm = 1000, 300, 30, 12, 38, 38
    n = len(d)
    if n < 2:
        return ""
    xs = lambda i: L + i * (W - L - R) / (n - 1)       # noqa: E731
    ys = lambda x: T + (10 - x) / 10 * (H - T - Bm)    # noqa: E731
    seg, segs = [], []
    for i, x in enumerate(v):
        if x is None:
            if seg:
                segs.append(seg)
            seg = []
            continue
        seg.append(f"{xs(i):.1f},{ys(x):.1f}")
    if seg:
        segs.append(seg)
    o = [f'<svg class="mpz-svg" viewBox="0 0 {W} {H}" role="img" aria-label="台股股市位階近 {S.CHART_YEARS} 年">',
         f'<rect x="{L}" y="{ys(10)}" width="{W - L - R}" height="{ys(S.HIGH) - ys(10):.1f}" class="br"/>',
         f'<rect x="{L}" y="{ys(S.LOW)}" width="{W - L - R}" height="{ys(0) - ys(S.LOW):.1f}" class="bg"/>']
    for k in (0, S.LOW, 5, S.HIGH, 10):
        o.append(f'<text x="{L - 6}" y="{ys(k) + 4:.1f}" text-anchor="end">{k:g}</text>')
    for i in range(1, n):
        if d[i][:4] != d[i - 1][:4]:
            o.append(f'<line x1="{xs(i):.1f}" x2="{xs(i):.1f}" y1="{T}" y2="{H - Bm}" class="gl"/>'
                     f'<text x="{xs(i):.1f}" y="{H - 7}" text-anchor="middle">{d[i][:4]}</text>')
    for s in segs:
        o.append(f'<polyline points="{" ".join(s)}" class="ln"/>')
    pos = {x: i for i, x in enumerate(d)}
    last = {"hi": [], "lo": []}                         # 同一種點的字太近就錯開一行（不重疊）
    for day, x, kind in pk:
        i = pos[day]
        up = kind == "hi"
        cx = xs(i)
        tx = min(max(cx, L + 30), W - R - 30)             # 最左、最右的字往內收，不被邊界切掉
        lift = 13 if any(abs(tx - t) < 64 and not k for t, k in last[kind]) else 0
        last[kind].append((tx, lift))
        ty = ys(x) - 9 - lift if up else ys(x) + 17 + lift
        o.append(f'<circle cx="{cx:.1f}" cy="{ys(x):.1f}" r="4.5" class="{"ph" if up else "pg"}"/>'
                 f'<text x="{tx:.1f}" y="{ty:.1f}" text-anchor="middle" class="pl">{day[2:4]}/{day[5:7]} {x:.1f}</text>')
    return "".join(o) + "</svg>"


def block(B: dict, X: dict | None = None, log: dict | None = None, mk: str = "tw") -> str:
    """市場頁最上面一塊（規格第 4～8 點；mk＝tw 或美股指數代號）。"""
    from . import heatspec as HS
    from .heatpage import n0
    e = html.escape
    _NM = {k: nm for k, _, nm, *_ in HS.IND}
    X = X or compute(B, S.GROUPS if mk == "tw" else S.GROUPS_US)
    v, cal = X["v"], X["cal"]
    idx = [i for i, x in enumerate(v) if x is not None]
    if not idx:
        return ""
    i = idx[-1]
    d, x = cal[i], v[i]
    prev = next((v[j] for j in range(i - 1, -1, -1) if v[j] is not None), None)
    w4 = v[i - 20] if i >= 20 else None
    log = read_log(log_path(mk)) if log is None else log
    fix = ""
    if prev is not None:
        pd = cal[max(j for j in idx if j < i)]
        pub = (log.get(pd) or {}).get("v")
        if pub is not None and abs(pub - prev) >= 0.1:
            fix = f'<p class="mpz-fix">昨天公布 {pub:g}，用今天的資料重算是 {prev:g}（之前幾天的資料補進來了）。</p>'
    lv = label(x)
    cls = "lo" if x <= S.LOW else "hi" if x >= S.HIGH else "mid"
    below = round(x * 10)
    sub = [f"昨天 {prev:g}" if prev is not None else "", f"20 個交易日前 {w4:g}" if w4 is not None else ""]
    how = "四組（價格位置、部位與籌碼、情緒、廣度）平均之後，和過去 10 年每一天比；0＝最低、10＝最高。"
    miss = [n for n, ks in X["items"].items() if not ks]
    if miss:
        how += f"這個指數的{'、'.join(miss)}沒有算分的項目，不放進平均。"
    gs = []
    for name, ks in X["items"].items():
        g = X["g"][name][i]
        if not ks:
            gs.append(f'<div class="mpz-g"><span>{name}</span><span class="hb"><i class="na"></i></span><em>沒有算分的項目</em></div>')
            continue
        if g is None:
            gs.append(f'<div class="mpz-g"><span>{name}</span><span class="hb"><i class="na"></i></span><em>—</em></div>')
            continue
        b = HS.band(g)
        gs.append(f'<div class="mpz-g" title="{e("、".join(_NM.get(k, k) for k in X["items"][name]))}">'
                  f'<span>{name}</span><span class="hb"><i class="{_band_cls(b)}" style="width:{g:.0f}%"></i></span><em>{n0(g)} {b}</em></div>')
    ms = []
    for k in (S.MACRO if mk == "tw" else S.MACRO_US):
        c = (B.get("comp") or {}).get(k) or []
        now = c[i] if i < len(c) else None
        old = c[i - S.MACRO_CHG] if i >= S.MACRO_CHG and i < len(c) else None
        if now is None or k not in HS.DIMS:
            continue
        chg = "" if old is None else f"比 20 天前 {'+' if now - old >= 0 else '−'}{abs(now - old):.0f}"
        ms.append(f'<div class="mpz-m"><span>{e(HS.DIMS[k]["name"].replace("熱度", ""))}</span><b>{n0(now)}</b><small>{HS.band(now)}・{chg}</small></div>')
    y0 = f"{int(d[:4]) - S.CHART_YEARS}{d[4:]}"
    c0 = next((j for j, dd in enumerate(cal) if dd >= y0), 0)
    cd, cv = cal[c0:i + 1], v[c0:i + 1]
    pk = [p for p in peaks(cal[:i + 1], v[:i + 1]) if p[0] >= cal[c0]]     # 整段算、只畫近 5 年（圖的左邊界不會冒出假的高低點）
    return (f'<section class="mpz" id="mpz"><div class="mpz-top"><div>'
            f'<div class="mpz-h"><h2 title="{e(how)}">股市位階</h2><small>{_md(d)} 收盤</small></div>'
            f'<div class="mpz-h" style="margin-top:6px"><span class="mpz-big">{x:g}<small> /10</small></span>'
            f'<span class="mpz-lv {cls}">{lv}</span><small>{"・".join(s for s in sub if s)}</small></div>'
            f'<div class="mpz-sl"><i style="left:{(prev if prev is not None else x) * 10:.0f}%"></i><b style="left:{x * 10:.0f}%"></b></div>'
            f'<div class="mpz-sll"><span>低（{S.LOW:g} 以下）</span><span>高（{S.HIGH:g} 以上）</span></div>'
            f'<p class="mpz-sub">過去 10 年有 {below}% 的日子比現在低。空心圈＝昨天。</p>{fix}'
            f'<div class="mpz-gs">{"".join(gs)}</div></div>'
            f'<div><div class="mpz-h"><h2>總經</h2></div>{"".join(ms)}</div></div>'
            f'<h3 class="mpz-ct">近 {S.CHART_YEARS} 年<small>藍帶＝低（{S.LOW:g} 以下）、紅帶＝高（{S.HIGH:g} 以上）；點＝每一段的高低點</small></h3>'
            f'<div class="mpz-cw">{_chart(cd, cv, pk)}</div>'
            '<script>(function(){var c=document.querySelector(".mpz-cw");if(c)c.scrollLeft=c.scrollWidth;})();</script></section>')


def _band_cls(b: str) -> str:
    from .heatpage import BAND_CLS
    return BAND_CLS.get(b, "b2")
