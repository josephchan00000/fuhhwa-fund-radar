"""景氣頁的視覺化版面（docs/lab_visual_plan.md 第 5～8 節；2026-10-18 使用者選定：雷達＋關鍵狀態為主畫面，
羅盤、3D 地形、研究可以切換，配色跟著系統深淺）。

只改呈現：分數、0～100、研究的算法與規格都不動（heatspec、研究檔照舊）。
  · pack(B, V)：主畫面要的小份資料（每個面向、每一項的現在、上週、4 週前、1 年前，雷達的比較日期與每季小圖），
    嵌在頁面的 <script type="application/json" class="hviz">（美股頁每個指數各一份，跟著內容切換）；
    每週的長序列照舊從 x9mh.json 下載（時間拉桿、羅盤、3D、面板裡的大張走勢）。
  · 關鍵狀態＝研究檔的判定是「熱了之後較弱／較強」（全期間信賴區間不含 0、前後兩半同號），而且現在在過熱（≥ 80）或過冷（< 20）。
  · 右側面板的內容在這裡產生（<template id="dt-面向">、<template id="it-項目">），瀏覽器只負責打開、畫走勢。
  · 比較日期：指數從高點跌 20% 以上（每週收盤）的最近兩段，高點與低點各一個，只描述位置，不是訊號。
輸出決定性：資料沒變時位元組相同。用字照專案禁用詞，不寫買賣指示。
"""
from __future__ import annotations

import html
import json
import math
from datetime import date

from . import heatpage as HP
from . import heatpos as PO
from . import heatspec as S

DD_MIN = 0.20          # 比較日期：高點到低點跌幅門檻（每週收盤）
N_EPI = 2              # 取最近幾段
NQ = 8                 # 每季小圖幾張（最後一張是現在）
KEY_SHOW = 4           # 關鍵狀態先列幾個
MOVE_MIN = 20          # 這週 0～100 變動多少算大幅移動
MOVE_SHOW = 6
REC_YEARS = 3          # 幾年新高新低以上才列進「這週變化」
HOT, COLD = 80, 20
VIEWS = (("radar", "雷達"), ("compass", "羅盤"), ("terrain", "地形 3D"), ("research", "研究"))
BC = HP.BAND_CLS


def _e(x) -> str:
    return html.escape(str(x), quote=True)


def _r1(x):
    if x is None:
        return None
    v = round(x, 1)
    return int(v) if float(v).is_integer() else v


def _ym(d: str) -> str:
    return f"{int(d[:4])}/{int(d[5:7])}"


def _zc(v) -> str:
    """分數 → 五區的 class 尾碼 0～4（沒有值回 x）。"""
    b = S.band(v) if v is not None else None
    return BC.get(b, "b2")[1] if b else "x"


# ── 資料 ────────────────────────────────────────────────────────────────

def episodes(dates: list[str], px: list, thr: float = DD_MIN) -> list[dict]:
    """每週收盤從高點跌 thr 以上的段：[{"peak", "trough", "dd", "open"}]。回到前高才算一段結束；
    最後一段還沒回到前高時 open＝True（低點是到目前為止的最低）。"""
    out, pk, tr, deep = [], None, None, False
    for i, v in enumerate(px):
        if v is None or v <= 0:
            continue
        if pk is None or v >= px[pk]:
            if deep:
                out.append({"peak": dates[pk], "trough": dates[tr], "dd": px[tr] / px[pk] - 1, "open": False})
            pk, tr, deep = i, None, False
            continue
        if tr is None or v < px[tr]:
            tr = i
        if px[tr] / px[pk] - 1 <= -thr:
            deep = True
    if deep:
        out.append({"peak": dates[pk], "trough": dates[tr], "dd": px[tr] / px[pk] - 1, "open": True})
    return out


def _run_weeks(series: list, we: list[int]) -> int:
    """最近連續幾週（每週最後一個交易日）在同一區。"""
    if not we or series[we[-1]] is None:
        return 0
    bd, n = S.band(series[we[-1]]), 0
    for i in reversed(we):
        if series[i] is None or S.band(series[i]) != bd:
            break
        n += 1
    return n


def _ev(d: dict | None, h) -> dict:
    return HP._ev(d, h)


def _zones(e: dict) -> dict:
    return {b["band"]: b for b in (e.get("bands") or []) if b.get("band")}


def key_states(B: dict, V: dict, we: list[int]) -> list[dict]:
    """研究成立（較弱／較強）而且現在在過熱或過冷：面向在前，其餘依「這一區之後的平均 − 所有時候」差距大到小。"""
    out = []

    def add(kind, k, name, dim, freq, heat, cev, weeks):
        band = S.band(heat)
        if band not in ("過熱", "過冷"):
            return
        hs = [h for h in V["dims"][dim]["fwd"] if _ev(cev, h).get("verdict") in ("weak", "strong")]
        if not hs:
            return
        h = max(hs)
        z = _zones(_ev(cev, h))
        cur, al = z.get(band) or {}, z.get("全部") or {}
        if not cur.get("n"):
            return
        gap = abs((cur.get("avg") or 0) - (al.get("avg") or 0))
        out.append({"kind": kind, "k": k, "name": name, "dim": dim, "freq": freq, "heat": heat, "band": band, "h": h,
                    "hs": hs, "verdict": {x: _ev(cev, x)["verdict"] for x in hs}, "cur": cur, "all": al,
                    "bands": [z.get(nm) or {"band": nm} for _, _, nm in S.BANDS], "weeks": weeks,
                    "a": (_ev(cev, h).get("a") or "")[:4], "gap": gap})
    for d, L in V["dims"].items():
        if L["score"] is None:
            continue
        add("dim", d, S.DSHORT[d], d, L["freq"], L["score"], L["cev"], (V["strips"].get(d) or {}).get("weeks") or 0)
    for d, L in V["dims"].items():
        for it in L["items"]:
            if it["heat"] is None or it["proxy"]:
                continue
            add("item", it["k"], it["name"], d, L["freq"], it["heat"], it["ev"], _run_weeks(B["heat"][it["k"]], we))
    out.sort(key=lambda a: (a["kind"] != "dim", -a["gap"], a["k"]))
    return out


def _quarters(cal: list[str], we: list[int], n: int = NQ) -> list[int]:
    """最近 n−1 個季底（每季最後一週）＋現在：回傳 week_ends 裡的位置。"""
    last = date.fromisoformat(cal[we[-1]])
    y, q = last.year, (last.month - 1) // 3          # 這一季的序號（0～3）；季底＝上一季的最後一天
    ends = []
    for _ in range(n - 1):
        q -= 1
        if q < 0:
            q, y = 3, y - 1
        m = 3 * (q + 1)
        nd = date(y + (m == 12), 1 if m == 12 else m + 1, 1).toordinal() - 1
        ends.append(date.fromordinal(nd).isoformat())
    ds = [cal[i] for i in we]
    pos = []
    for e in reversed(ends):
        j = max((x for x, d in enumerate(ds) if d <= e), default=None)
        if j is not None and j not in pos:
            pos.append(j)
    pos.append(len(we) - 1)
    return pos


def pack(B: dict, V: dict) -> dict:
    """主畫面的小份資料（嵌在頁面裡）。"""
    cal, px = B["cal"], B["px"]
    if not cal:
        return {}
    we = PO.week_ends(cal)
    dims = list(S.DIMS)
    need = math.ceil(2 * len(dims) / 3)
    comp = B["comp"]
    j0 = next((j for j, i in enumerate(we) if sum(comp[d][i] is not None for d in dims) >= need), len(we) - 1)

    def snap(j):
        i = we[j]
        return {"d": cal[i], "px": _r1(px[i]), "v": [_r1(comp[d][i]) for d in dims]}
    J = len(we) - 1
    wd = [cal[i] for i in we]
    wp = [px[i] for i in we]
    pre = []
    for j, lab in ((J - 4, "4 週前"), (J - 52, "1 年前")):
        if j >= j0:
            pre.append({"key": "w4" if lab == "4 週前" else "y1", "lab": lab, "sub": "", **snap(j)})
    a0 = cal.index(wd[j0])                       # 跌幅用每天收盤認（週收盤會漏掉週中急跌又反彈的段），日期換成那一週
    eps = episodes(cal[a0:], px[a0:])[-N_EPI:]
    wk = lambda d: next(j for j, x in enumerate(wd) if x >= d)          # noqa: E731
    for e in reversed(eps):
        jp, jt = wk(e["peak"]), wk(e["trough"])
        dd = f"{abs(100 * e['dd']):.0f}%"
        if e["open"]:
            pre.append({"key": f"p{jp}", "lab": f"{_ym(e['peak'])} 高點", "sub": f"之後最多跌 {dd}，還沒回到高點", **snap(jp)})
        else:
            pre.append({"key": f"p{jp}", "lab": f"{_ym(e['peak'])} 高點", "sub": f"之後跌 {dd}", **snap(jp)})
            pre.append({"key": f"t{jt}", "lab": f"{_ym(e['trough'])} 低點", "sub": f"從 {_ym(e['peak'])} 高點跌 {dd}", **snap(jt)})
    qs = [snap(j) for j in _quarters(cal, we) if j >= j0]
    t, t0 = len(cal) - 1, max(0, len(cal) - 1 - HP.WEEK)
    out_d = []
    for d, L in V["dims"].items():
        st = (V.get("strips") or {}).get(d) or {}
        out_d.append({"id": d, "name": S.DSHORT[d], "full": L["name"], "span": L["span"], "sc": _r1(L["score"]),
                      "ago": _r1(L["ago"]), "st": HP.strip_text(st) if st else ""})
    items = []
    for d, L in V["dims"].items():
        for it in L["items"]:
            items.append({"k": it["k"], "dim": d, "name": it["name"], "h": _r1(it["heat"]), "ago": _r1(it["ago"]),
                          "pull": _r1(it["pull"]), "px": bool(it["proxy"]), "val": it["val"]})
    ordr = {d: [it["k"] for it in _item_order(L)] for d, L in V["dims"].items()}
    return {"asof": cal[t], "start": wd[j0], "dims": out_d, "items": items, "ord": ordr, "pre": pre, "qs": qs,
            "mkt": HP.MK["mkt"].strip(), "px": HP.MK["px"].strip(), "t0": cal[t0]}


def _item_order(L: dict) -> list[dict]:
    """面板裡的順序（同 heatpage._items）：有拉動的依 |拉動| 大到小，其餘照規格順序。"""
    have = sorted((it for it in L["items"] if it["pull"] is not None), key=lambda x: -abs(x["pull"]))
    return have + [it for it in L["items"] if it["pull"] is None]


# ── HTML：主畫面 ────────────────────────────────────────────────────────

def _pct(x, dec=1) -> str:
    return HP._pct(x, dec)


def zone_svg(bands: list[dict], cur: str, al: dict, w: int = 300, h: int = 96) -> str:
    """五區之後的平均報酬長條（現在這一區上色，其他灰色），虛線＝所有時候的平均。"""
    vals = [b.get("avg") for b in bands]
    have = [v for v in vals if v is not None] + ([al["avg"]] if al.get("avg") is not None else [])
    if not have:
        return ""
    lo, hi = min(0.0, min(have)), max(0.0, max(have))
    if hi - lo < 1e-9:
        hi = lo + 1
    top, bot = 16, h - 34                       # 下面留給負數的數字（bot＋11）和區名（h−5），兩行不會疊在一起
    Y = lambda v: top + (bot - top) * (hi - v) / (hi - lo)                       # noqa: E731
    n = len(bands)
    bw = (w - 16) / n
    s = []
    if al.get("avg") is not None:                # 所有時候的平均（虛線）先畫，壓在長條與數字底下
        ya = Y(al["avg"])
        s.append(f'<line class="kza" x1="4" x2="{w - 4}" y1="{ya:.1f}" y2="{ya:.1f}"/>')
    s.append(f'<line class="kz0" x1="0" x2="{w}" y1="{Y(0):.1f}" y2="{Y(0):.1f}"/>')
    for k, b in enumerate(bands):
        x = 8 + k * bw + bw * 0.2
        bwi = bw * 0.6
        nm = b.get("band")
        on = nm == cur
        lab = f'<text class="kzl{" on zt" + _zc_of(nm) if on else ""}" x="{x + bwi / 2:.1f}" y="{h - 6}">{_e(nm)}</text>'
        v = b.get("avg")
        if v is None or not b.get("n"):
            s.append(lab + f'<text class="kzv" x="{x + bwi / 2:.1f}" y="{Y(0) - 4:.1f}">—</text>')
            continue
        y0, y1 = Y(max(v, 0)), Y(min(v, 0))
        cls = f"kzb zf{_zc_of(nm)}" if on else "kzb kzo"
        s.append(f'<rect class="{cls}" x="{x:.1f}" y="{y0:.1f}" width="{bwi:.1f}" height="{max(1.0, y1 - y0):.1f}" rx="3"/>')
        ty = y0 - 4 if v >= 0 else y1 + 11
        s.append(f'<text class="kzv{" on" if on else ""}" x="{x + bwi / 2:.1f}" y="{ty:.1f}">{_e(_pct(v))}</text>' + lab)
    return (f'<svg class="kzs" viewBox="0 0 {w} {h}" role="img" aria-label="各區之後的平均漲跌">' + "".join(s) + "</svg>")


def _zc_of(band: str | None) -> str:
    return BC.get(band, "b2")[1] if band else "2"


def _verd(a: dict) -> str:
    by: dict[str, list] = {}
    for h in a["hs"]:
        by.setdefault(a["verdict"][h], []).append(h)
    return "".join(f'<span class="vt {v}">{_e(S.VERDICT[v])}（{"、".join(str(x) for x in hs)} 日）</span>'
                   for v, hs in by.items())


def _key_line(a: dict) -> str:
    cur, al = a["cur"], a["all"]
    unit = HP._unit(a["freq"])
    yrs = HP._yrs(cur.get("yrs"))
    where = f"，出現在 {yrs} 年" if yrs else ""
    up = f'、上漲 {cur["up"]:.0f}%' if cur.get("up") is not None else ""
    allt = f'；所有時候 {_pct(al.get("avg"))}' if al.get("avg") is not None else ""
    return (f'過去在「{_e(a["band"])}」時，之後 {a["h"]} 日{_e(HP.MK["px"])}平均 <b>{_e(_pct(cur.get("avg")))}</b>'
            f'{up}（{cur["n"]:,} {unit}{_e(where)}）{_e(allt)}。')


def _kcard(a: dict, full: bool) -> str:
    did = f'dim:{a["k"]}' if a["kind"] == "dim" else f'item:{a["k"]}'
    kind = "面向" if a["kind"] == "dim" else S.DSHORT[a["dim"]]
    wk = f'<span class="kw">已連續 {a["weeks"]} 週</span>' if a["weeks"] else ""
    z = _zc(a["heat"])
    head = (f'<div class="kt"><b>{_e(a["name"])}</b><span class="kk">{_e(kind)}</span>'
            f'<span class="kv zt{z}">{HP.n0(a["heat"])} {_e(a["band"])}</span>{wk}</div>')
    if not full:
        return (f'<li><button type="button" class="kmini" data-open="{did}">{head}<span class="ke">{_verd(a)}</span></button></li>')
    return (f'<article class="kcard" data-open="{did}" tabindex="0" role="button" aria-label="{_e(a["name"])}：打開細節">{head}'
            f'<div class="ke">{_verd(a)}</div><p class="kp">{_key_line(a)}</p>'
            f'{zone_svg(a["bands"], a["band"], a["all"])}</article>')


def key_html(ks: list[dict]) -> str:
    if not ks:
        return ('<section class="kstate card" id="key"><div class="khd"><h2>關鍵狀態</h2></div>'
                '<p class="note">現在沒有「研究顯示有穩定關係、而且正在過熱或過冷」的項目。</p></section>')
    cards = "".join(_kcard(a, True) for a in ks[:KEY_SHOW])
    more = ""
    if len(ks) > KEY_SHOW:
        more = (f'<details class="kmore"><summary>還有 {len(ks) - KEY_SHOW} 個</summary><ul class="klist">'
                + "".join(_kcard(a, False) for a in ks[KEY_SHOW:]) + "</ul></details>")
    return (f'<section class="kstate card" id="key"><div class="khd"><h2>關鍵狀態</h2><span class="kn">{len(ks)} 個</span></div>'
            '<p class="ksub">研究顯示有穩定關係、而且現在在過熱或過冷；長條＝過去在各區之後的平均漲跌，虛線＝所有時候。只當參考。</p>'
            f'{cards}{more}</section>')


def _nmb(k: str, name: str) -> str:
    return f'<button type="button" class="nmb" data-k="{_e(k)}">{_e(name)}</button>'


def moves_html(V: dict) -> str:
    """這週變化：面向換區、進入過熱過冷、0～100 大幅移動、歷史新高新低（和上週＝5 個交易日前比）。"""
    lines = []
    for d, L in V["dims"].items():
        a, b = L["ago"], L["score"]
        if a is None or b is None:
            continue
        ba, bb = S.band(a), S.band(b)
        if ba != bb:
            lines.append(f'<li><span class="wtag">面向換區</span>{_nmb(d, S.DSHORT[d])} {HP.n0(a)} → '
                         f'<b class="zt{_zc(b)}">{HP.n0(b)}</b>（{_e(ba)} → {_e(bb)}）</li>')
    its = [(d, it) for d, L in V["dims"].items() for it in L["items"] if it["heat"] is not None and it["ago"] is not None]
    into_h = [(d, it) for d, it in its if it["heat"] >= HOT > it["ago"]]
    into_c = [(d, it) for d, it in its if it["heat"] < COLD <= it["ago"]]
    for lab, xs in (("進入過熱", into_h), ("進入過冷", into_c)):
        if xs:
            lines.append(f'<li><span class="wtag">{lab}</span>' + "、".join(
                f'{_nmb(it["k"], it["name"])} {HP.n0(it["ago"])}→<b class="zt{_zc(it["heat"])}">{HP.n0(it["heat"])}</b>'
                for _, it in xs) + "</li>")
    seen = {it["k"] for _, it in into_h + into_c}
    big = sorted((x for x in its if abs(x[1]["heat"] - x[1]["ago"]) >= MOVE_MIN and x[1]["k"] not in seen),
                 key=lambda x: (-abs(x[1]["heat"] - x[1]["ago"]), x[1]["k"]))[:MOVE_SHOW]
    if big:
        lines.append('<li><span class="wtag">大幅移動</span>' + "、".join(
            f'{_nmb(it["k"], it["name"])} {HP.n0(it["ago"])}→<b class="zt{_zc(it["heat"])}">{HP.n0(it["heat"])}</b>'
            for _, it in big) + "</li>")
    rec = []
    for d, L in V["dims"].items():
        for it in L["items"]:
            r = (it.get("pos") or {}).get("rec") or {}
            w = "高" if r.get("side") == "hi" else "低"
            if r.get("kind") == "ath":
                rec.append(f'{_nmb(it["k"], it["name"])} 有資料以來最{w}')
            elif r.get("kind") == "since_y" and (r.get("n") or 0) >= REC_YEARS:
                rec.append(f'{_nmb(it["k"], it["name"])} {r["n"]} 年新{w}')
    if rec:
        lines.append('<li><span class="wtag">歷史極端</span>' + "、".join(rec) + "</li>")
    body = "".join(lines) or '<li class="mu">這週沒有換區、進入過熱過冷或大幅移動的項目。</li>'
    return (f'<section class="wchg card" id="wchg"><div class="khd"><h2>這週變化</h2><span class="kn">和 '
            f'{_e(HP._md(V.get("viz", {}).get("t0")))}比</span></div><ul>{body}</ul></section>')


def items_table(V: dict) -> str:
    rows = []
    for d, L in V["dims"].items():
        for it in _item_order(L):
            h, a = it["heat"], it["ago"]
            ch = "—" if h is None or a is None else HP._sgn(h - a, 0)
            hv = "—" if h is None else HP.n0(h)
            av = "—" if a is None else HP.n0(a)
            pl = "—" if it["pull"] is None else HP._sgn(it["pull"])
            sh = "—" if it["share"] is None else f'{it["share"]:.0f}%'
            rows.append(f'<tr><td class="l">{_nmb(it["k"], it["name"])}</td><td class="l">{_e(S.DSHORT[d])}</td>'
                        f'<td><b class="zt{_zc(h)}">{hv}</b></td><td>{av}</td><td>{ch}</td><td>{pl}</td><td>{sh}</td>'
                        f'<td class="l">{_e(it["val"])}</td></tr>')
    return ('<div class="tw itab" id="itab" hidden><table><tr><th class="l">項目</th><th class="l">面向</th><th>0～100</th>'
            '<th>上週</th><th>變化</th><th>拉動</th><th>佔比</th><th class="l">現值</th></tr>' + "".join(rows) + "</table></div>")


def _radar_card() -> str:
    return ('<div class="rcard card"><div class="khd"><h2>面向雷達</h2><span class="kn" id="rdate"></span></div>'
            '<p class="ksub">越外圈越熱（100 最熱）；外圈淡紅＝過熱，內圈淡藍＝過冷。點面向名稱看細項；拉下面的時間軸看過去任何一週的形狀。</p>'
            '<div class="rad" id="rad"><p class="note">雷達要開啟 JavaScript 才看得到。</p></div>'
            '<div class="rleg" id="rleg"></div>'
            '<div class="rtl"><button type="button" class="rplay" id="rplay" aria-label="播放近兩年">▶</button>'
            '<div class="rtrk"><svg id="rtsvg" viewBox="0 0 600 44" preserveAspectRatio="none" aria-hidden="true"></svg>'
            '<input type="range" id="rtin" min="0" max="0" value="0" aria-label="選一週" disabled></div>'
            '<span class="rnow" id="rnow"></span></div>'
            '<div class="rchips" id="rchips" role="group" aria-label="疊上比較的日期"></div>'
            '<div class="rsm" id="rsm"></div></div>')


def main_view(V: dict, ks: list[dict]) -> str:
    asof = V["asof"]
    nav = ('<nav class="snav"><a href="#top">雷達</a><a href="#key">關鍵狀態</a><a href="#items">全部項目</a>'
           f'<a href="#cmp">{_e(HP.MK["cmp"])}</a>' + ('<a href="#ta">價位事件</a>' if V.get("ta") else "")
           + '<button type="button" class="snv" data-goview="research">研究與驗證 →</button></nav>')
    nores = "" if (V.get("R") or {}).get("dims") else f'<p class="warn">驗證結果還沒產生（{_e(HP.MK["res"])}），先只列各項的 0～100。</p>'
    top = (f'<section class="vtop" id="top"><p class="sum">{_e(V.get("summary") or "")}</p>{nores}'
           f'<div class="vgrid">{_radar_card()}<div class="vside">{key_html(ks)}{moves_html(V)}</div></div>'
           f'<p class="hz">{_e(S.HORIZON_NOTE)}。<span class="mu">（資料到 {_e(HP._md(asof))}）</span></p></section>')
    items = ('<section class="sec" id="items"><div class="ish2"><h2>全部項目<span class="sub" id="isub"></span></h2>'
             '<div class="seg"><button type="button" class="tb" id="itabb" aria-pressed="false">表格</button></div></div>'
             '<div class="imap" id="imap"></div>'
             '<p class="note">每一點是一項：位置＝現在的 0～100；短線＝和上週比從哪裡移過來；點越大＝拉動面向分數越多。點一下打開右邊的面板。</p>'
             f'{items_table(V)}</section>')
    return (f'<div class="hview" data-view="radar">{nav}{top}{items}{HP._cmp_section()}{HP._ta_main(V)}'
            '<p class="vmore"><button type="button" class="tb" data-goview="research">研究與驗證（各項和指數的關係、多層回歸、事件研究、資料來源）→</button></p></div>')


def compass_view() -> str:
    return ('<div class="hview" data-view="compass" hidden><section class="sec" id="cps-sec"><div class="vgrid">'
            '<div class="ccard card"><div class="khd"><h2>熱度羅盤</h2><span class="kn" id="cdate"></span>'
            '<button type="button" class="tb cback" id="cback" hidden>← 回到面向</button></div>'
            '<p class="ksub" id="csub">橫軸＝現在多熱（0～100）；縱軸＝近 4 週升溫（上）或降溫（下）；尾巴＝過去 8 週走過的路。點泡泡展開那個面向的項目。</p>'
            '<div class="cps" id="cps"><p class="note">走勢載入中…</p></div>'
            '<div class="rtl"><button type="button" class="rplay" id="cplay" aria-label="播放近兩年">▶</button>'
            '<div class="rtrk"><svg id="ctsvg" viewBox="0 0 600 44" preserveAspectRatio="none" aria-hidden="true"></svg>'
            '<input type="range" id="ctin" min="0" max="0" value="0" aria-label="選一週" disabled></div>'
            '<span class="rnow" id="cnow"></span></div><div class="rchips" id="cchips"></div></div>'
            '<div class="vside"><section class="card cquad" id="cquad"></section></div></div></section></div>')


def terrain_view() -> str:
    return ('<div class="hview" data-view="terrain" hidden><section class="sec"><div class="tcard card">'
            '<div class="khd"><h2>熱度地形</h2><span class="kn">每條山脊是一個面向，高出紅色平面＝過熱，最右邊是現在</span></div>'
            '<div class="seg tctl"><button type="button" class="tb on" data-tr="10" aria-pressed="true">近 10 年</button>'
            '<button type="button" class="tb" data-tr="0" aria-pressed="false">全部</button>'
            '<button type="button" class="tb" id="tflat" aria-pressed="false">平面熱圖</button>'
            '<button type="button" class="tb" id="treset">轉回原角度</button></div>'
            '<div class="ter" id="ter"><canvas id="tcv" aria-label="熱度地形" role="img"></canvas><div class="tip" id="ttip" hidden></div>'
            '<p class="note tld" id="tld">走勢載入中…</p></div>'
            '<p class="note">拖曳旋轉；滑過山脊看那一週的分數；點一下跳到雷達看那一週。3D 只適合看「哪些時期同時過熱」，讀數字請用雷達或對照圖。</p>'
            '</div></section></div>')


def research_view(V: dict, body: str) -> str:
    nav = ('<nav class="snav"><button type="button" class="snv" data-goview="radar">← 回到雷達</button>'
           '<a href="#dv">邊際變化</a><a href="#valid">驗證</a>' + ('<a href="#tas">事件研究</a>' if V.get("ta") else "")
           + '<a href="#src">資料來源</a></nav>')
    return f'<div class="hview" data-view="research" hidden>{nav}{body}</div>'


def switch_html() -> str:
    btn = []
    for k, nm in VIEWS:
        on = ' class="on" aria-pressed="true"' if k == "radar" else ' aria-pressed="false"'
        btn.append(f'<button type="button" data-view="{k}"{on}>{_e(nm)}</button>')
    return '<nav class="vsw" aria-label="視角">' + "".join(btn) + "</nav>"


DRAWER = ('<aside class="drw" id="drw" hidden aria-labelledby="drw-t"><div class="drw-h">'
          '<button type="button" class="drw-b" id="drw-back" hidden aria-label="回上一層">←</button>'
          '<div class="drw-tt"><span id="drw-k"></span><h2 id="drw-t"></h2></div>'
          '<button type="button" class="drw-n" id="drw-prev" aria-label="上一項">‹</button>'
          '<button type="button" class="drw-n" id="drw-next" aria-label="下一項">›</button>'
          '<button type="button" class="drw-x" id="drw-x" aria-label="關閉">×</button></div>'
          '<div class="drw-c" id="drw-c"></div></aside>')


# ── 右側面板的內容 ───────────────────────────────────────────────────────

def _dnum(cells: list[tuple[str, str, str]]) -> str:
    return '<div class="dnum">' + "".join(f'<div><span>{_e(a)}</span><b>{b}</b><i>{c}</i></div>' for a, b, c in cells) + "</div>"


def _trk(lab: str, p) -> str:
    if p is None:
        return ""
    hi = p >= 50
    v = math.floor(p if hi else 100 - p)
    return (f'<div class="dtrk"><span>{_e(lab)}</span><span class="dtb"><i style="left:{p:.1f}%"></i></span>'
            f'<b>比 {v}% {"高" if hi else "低"}</b></div>')


def dim_tpl(d: str, L: dict, V: dict) -> str:
    sc = L["score"]
    st = (V.get("strips") or {}).get(d) or {}
    z = _zc(sc)
    wk = "—" if sc is None or L["ago"] is None else HP._sgn(sc - L["ago"], 0)
    cells = [("分數", f'<span class="zt{z}">{"—" if sc is None else HP.n0(sc)}</span>', _e(L["band"] or "還沒有分數")),
             ("和上週比", _e(wk), f'上週 {"—" if L["ago"] is None else HP.n0(L["ago"])}'),
             ("有值的項目", f'{L["n_have"]}／{len(L["items"])}', "等權平均")]
    stt = f'<p class="dst">{_e(HP.strip_text(st))}</p>' if st else ""
    return (f'<template id="dt-{d}" data-kick="面向・{_e(L["span"])}" data-title="{_e(L["name"])}">'
            f'{_dnum(cells)}{stt}<div class="dchart" data-k="{d}"></div>{HP._card(d, L, V)}</template>')


def _rel_bits(k: str, V: dict) -> str:
    a = (V.get("rel") or {}).get(k) or {}
    if not a.get("first"):
        return ""
    g = a.get("gr") or {}
    ga, gb = g.get("A") or {}, g.get("B") or {}
    m = HP.MK["mkt"].strip()
    qa = f'（q＝{ga["q"]:.2f}）' if ga.get("q") is not None else ""
    li = [f'<li><b>跟著走還是領先</b>：{_e(HP._ll_text(a.get("ll")))}</li>',
          f'<li><b>這一項 → {_e(m)}</b>（Granger）：{_e(HP.GRV.get(ga.get("verdict"), "—"))}{_e(qa)}</li>',
          f'<li><b>{_e(m)} → 這一項</b>：{_e(HP._grb().get(gb.get("verdict"), "—"))}</li>',
          f'<li><b>剛進入過熱之後</b>：{_e(HP._evt_cell((a.get("evt") or {}).get("hot")))}；'
          f'<b>剛進入過冷之後</b>：{_e(HP._evt_cell((a.get("evt") or {}).get("cold")))}</li>']
    return f'<h4>和{_e(m)}的關係<span>研究檔；只當參考</span></h4><ul class="drel">{"".join(li)}</ul>'


def item_tpl(it: dict, d: str, L: dict, V: dict) -> str:
    k = it["k"]
    h = it["heat"]
    z = _zc(h)
    band = S.band(h) if h is not None else None
    dname = S.DSHORT[d]
    pull = "—" if it["pull"] is None else HP._sgn(it["pull"])
    share = "" if it["share"] is None else f'佔{_e(dname)} {it["share"]:.0f}%'
    wk = "" if h is None or it["ago"] is None else f'・上週 {HP.n0(it["ago"])}'
    why = ""
    if it["proxy"]:
        why = '<p class="warn">用美國 VIX 的排名代替，不算進分數。</p>'
    elif it["why"]:
        why = f'<p class="warn">{_e(it["why"])}</p>'
    cells = [("現值", _e(it["val"]), _e(HP._md(it["src"]))),
             ("0～100", f'<span class="zt{z}">{"—" if h is None else HP.n0(h)}</span>', _e((band or "沒有分數") + wk)),
             (f"拉動{dname}", _e(pull), _e(share) or "沒有算進分數")]
    hot = "越高越熱" if it["hot"] == 1 else "越低越熱"
    src = HP.SRC.get(k) if HP.MK.get("tab") == "tw" else None     # 美股頁的來源寫在頁尾（SRC 是台股項目的表）
    how = f'<p class="dhow">{_e(it["how"])}；{hot}{("。來源：" + _e(src)) if src else ""}。</p>'
    pos = it.get("pos") or {}
    trk = ""
    if pos:
        frm = f'{int(pos["from"][:4])} 年以來' if pos.get("from") else "有資料以來"
        trk = _trk("近 3 年", pos.get("p3")) + _trk("近 10 年", pos.get("p10")) + _trk(frm, pos.get("pall"))
        pl = HP.pos_line(k, pos)
        trk = (f'<h4>歷史位置<span>和過去的{"月份" if S.FREQ_OF[k] == "m" else "日子"}比</span></h4>{trk}'
               + (f'<p class="dpos">{_e(pl)}</p>' if pl else ""))
    dv = ""
    if it.get("dv") and k in HP.DLABEL:
        dv = (f'<h4>邊際變化<span>二次微分；不進分數</span></h4><p class="dpos"><b>{_e(HP.acc_label(k, it["dv"]))}</b>：'
              f'{_e(HP.dv_line(k, it["dv"]))}</p>')
    past = ""
    ev = it.get("ev") or {}
    if band and ev:
        parts = []
        for hh in L["fwd"]:
            e = _ev(ev, hh)
            zz = _zones(e)
            cur, al = zz.get(band) or {}, zz.get("全部") or {}
            if not cur.get("n"):
                continue
            v = e.get("verdict")
            vt = f'<span class="vt {v}">{_e(S.VERDICT.get(v, "—"))}</span>' if v else ""
            parts.append(f'<div class="dzone"><p>之後 {hh} 日：{vt}</p>'
                         f'{zone_svg([zz.get(nm) or {"band": nm} for _, _, nm in S.BANDS], band, al, 300, 92)}</div>')
        if parts:
            past = (f'<h4>過去在各區之後的{_e(HP.MK["px"].rstrip())}<span>現在在「{_e(band)}」；只當參考</span></h4>'
                    f'<div class="dzs">{"".join(parts)}</div>')
    btn = (f'<p class="dbtn"><button type="button" class="tb cmpk" data-k="{_e(k)}">在「{_e(HP.MK["cmp"])}」圖看這一項 →</button>'
           f'<button type="button" class="tb" data-goview="research" data-anchor="v-{_e(d)}">研究畫面的數字 →</button></p>')
    return (f'<template id="it-{k}" data-kick="{_e(dname)}・{"月資料" if it["freq"] == "m" else "日資料"}" data-title="{_e(it["name"])}">'
            f'{_dnum(cells)}{why}{how}<div class="dchart" data-k="{_e(k)}"></div>{trk}{dv}{past}{_rel_bits(k, V)}{btn}</template>')


def templates(V: dict) -> str:
    out = []
    for d, L in V["dims"].items():
        out.append(dim_tpl(d, L, V))
        for it in L["items"]:
            out.append(item_tpl(it, d, L, V))
    return '<div class="dtpl" hidden>' + "".join(out) + "</div>"


def viz_json(V: dict) -> str:
    js = json.dumps(V.get("viz") or {}, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return '<script type="application/json" class="hviz">' + js.replace("</", "<\\/") + "</script>"


# ── CSS（顏色一律用 heatpage._CSS 的變數，深淺色跟著系統）──────────────────────
CSS = """
.vbar{display:flex;align-items:center;flex-wrap:wrap;gap:6px 14px;max-width:1080px;margin:2px auto 6px;padding:0 16px}
.vsw{display:inline-flex;gap:2px;background:var(--card2);border-radius:10px;padding:3px}
.vsw button{border:0;background:none;padding:5px 12px;border-radius:8px;font:inherit;font-size:13.5px;font-weight:600;color:var(--ink2);cursor:pointer}
.vsw button.on{background:var(--panel);color:var(--ink);box-shadow:0 1px 3px rgba(0,0,0,.18)}
.vsw button:focus-visible,.rch:focus-visible,.kcard:focus-visible,.rax:focus-visible,.idot:focus-visible{outline:2px solid var(--acc);outline-offset:2px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px}
.hview>.snav{margin:0 -16px 12px}
.snv{border:0;background:var(--accbg);color:var(--acc);font:inherit;font-size:13px;border-radius:12px;padding:2px 10px;cursor:pointer;white-space:nowrap}
.vgrid{display:grid;grid-template-columns:minmax(0,1.12fr) minmax(0,1fr);gap:14px;align-items:start}
.vside{display:flex;flex-direction:column;gap:14px;min-width:0}
.rcard,.kstate,.wchg,.ccard,.tcard,.cquad{padding:12px 14px;min-width:0}
.khd{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}.khd h2{font-size:16px;margin:0}.kn{font-size:12.5px;color:var(--mut)}
.ksub{font-size:12.5px;color:var(--mut);margin:3px 0 8px;line-height:1.6}
.zt0{color:var(--t0);fill:var(--t0)}.zt1{color:var(--t1);fill:var(--t1)}.zt2{color:var(--t2);fill:var(--t2)}.zt3{color:var(--t3);fill:var(--t3)}.zt4{color:var(--t4);fill:var(--t4)}.ztx{color:var(--mut);fill:var(--mut)}
.zf0{fill:var(--c0)}.zf1{fill:var(--c1)}.zf2{fill:var(--c2)}.zf3{fill:var(--c3)}.zf4{fill:var(--c4)}.zfx{fill:none;stroke:var(--mut)!important}
.vtop .sum{margin:4px 0 10px}
.rad{position:relative;min-height:200px}.rad svg{display:block;width:100%;height:auto;max-width:600px;margin:0 auto;overflow:visible}
.rzh{fill:var(--zh)}.rzc{fill:var(--zc)}.rpn{fill:var(--panel)}.rring{fill:none;stroke:var(--line2);stroke-width:1}.rring.r80{stroke:var(--c4);stroke-opacity:.45;stroke-dasharray:4 3}.rring.r20{stroke:var(--c0);stroke-opacity:.45;stroke-dasharray:4 3}
.rrl{font-size:10.5px;fill:var(--mut)}.rgl{stroke:var(--line2);stroke-width:1}
.rax{cursor:pointer}.rhit{fill:transparent}.ran{font-size:14px;font-weight:700;fill:var(--ink)}.ras{font-size:13px;font-weight:800}
.rax:hover .ran,.rax:focus .ran,.rax.sel .ran{fill:var(--acc)}
.rmain{fill:var(--accbg);stroke:var(--ink);stroke-width:2.2;stroke-linejoin:round}
.rghost{fill:none;stroke:var(--ink2);stroke-width:1.6;stroke-dasharray:3 3}
.rov{fill:none;stroke-width:2;stroke-dasharray:7 4;stroke-linejoin:round}.rov.o0{stroke:var(--p0)}.rov.o1{stroke:var(--p1)}.rov.o2{stroke:var(--p2)}
.rv{stroke:var(--ring);stroke-width:2}
.rleg{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12px;color:var(--ink2);margin:2px 0 6px;justify-content:center}
.rleg span{display:inline-flex;align-items:center;gap:6px}.rleg i{display:inline-block;width:20px;height:0;border-top:2.4px solid var(--ink)}
.rleg i.gh{border-top:2px dashed var(--ink2)}.rleg i.o0{border-top:2px dashed var(--p0)}.rleg i.o1{border-top:2px dashed var(--p1)}.rleg i.o2{border-top:2px dashed var(--p2)}
.rtl{display:flex;align-items:center;gap:10px;margin:4px 0 6px}
.rplay{flex:none;width:34px;height:34px;border-radius:50%;border:1px solid var(--line2);background:var(--card2);color:var(--ink);font-size:12px;cursor:pointer}
.rplay:disabled{opacity:.45;cursor:default}
.rtrk{position:relative;flex:1;height:44px;min-width:0}
.rtrk svg{position:absolute;left:9px;top:0;height:44px;width:calc(100% - 18px)}
.rtx{fill:none;stroke:var(--mut);stroke-width:1.2}.rty{font-size:10px;fill:var(--mut)}.rtz{fill:var(--accbg)}
.rtrk input{position:absolute;left:0;top:0;width:100%;height:44px;margin:0;background:transparent;-webkit-appearance:none;appearance:none;cursor:pointer}
.rtrk input::-webkit-slider-runnable-track{height:44px;background:transparent}
.rtrk input::-moz-range-track{height:44px;background:transparent}
.rtrk input::-webkit-slider-thumb{-webkit-appearance:none;width:18px;height:44px;border-radius:9px;background:var(--acc);opacity:.85;border:3px solid var(--panel);box-sizing:border-box}
.rtrk input::-moz-range-thumb{width:12px;height:38px;border-radius:9px;background:var(--acc);opacity:.85;border:3px solid var(--panel)}
.rtrk input:disabled{cursor:default}.rtrk input:disabled::-webkit-slider-thumb{background:var(--mut)}
.rnow{flex:none;min-width:5.6em;text-align:right;font-weight:700;font-size:13px;line-height:1.3}.rnow i{display:block;font-style:normal;font-weight:400;font-size:11.5px;color:var(--mut)}
.rchips{display:flex;flex-wrap:wrap;gap:6px;margin:2px 0 4px}
.rch{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line2);background:var(--bg);color:var(--ink2);border-radius:999px;padding:3px 10px;font:inherit;font-size:12.5px;cursor:pointer}
.rch i{display:inline-block;width:14px;height:0;border-top:2px dashed var(--line2)}
.rch.on{color:var(--ink);font-weight:600;border-color:var(--ink2)}.rch.on.o0 i{border-color:var(--p0)}.rch.on.o1 i{border-color:var(--p1)}.rch.on.o2 i{border-color:var(--p2)}
.rch em{font-style:normal;color:var(--mut);font-weight:400;font-size:11.5px}
.rsm{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;margin-top:10px}
.rsm button{border:1px solid var(--line);background:var(--card2);border-radius:10px;padding:4px 2px 3px;font:inherit;color:inherit;cursor:pointer;min-width:0}
.rsm button.now{border-color:var(--acc)}.rsm button.sel{box-shadow:inset 0 0 0 2px var(--acc)}
.rsm svg{display:block;width:100%;height:auto}.rsm b{display:block;font-size:12px}.rsm i{display:block;font-style:normal;font-size:10.5px;color:var(--mut);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.rsm .mr{fill:none;stroke:var(--line2)}.rsm .mp{fill:var(--accbg);stroke:var(--ink2);stroke-width:1.4}.rsm .mp.hot{fill:var(--zh);stroke:var(--c4)}
.rsmc{font-size:11.5px;color:var(--mut);margin:4px 0 0}
.kstate .kcard{display:block;border-top:1px solid var(--line);padding:9px 6px 6px;margin:0 -6px;border-radius:10px;cursor:pointer}
.kcard:hover{background:var(--card2)}
.kt{display:flex;align-items:baseline;gap:6px 8px;flex-wrap:wrap}.kt b{font-size:15px}
.kk{font-size:11px;color:var(--mut);border:1px solid var(--line2);border-radius:999px;padding:0 7px;line-height:1.6}
.kv{font-size:15px;font-weight:800}.kw{font-size:12px;color:var(--mut)}
.vt{display:inline-block;font-size:12px;font-weight:600;border-radius:999px;padding:1px 9px;margin:4px 6px 0 0}
.vt.weak{color:var(--t4);background:var(--zh);box-shadow:inset 0 0 0 1px var(--c4)}.vt.strong{color:var(--t0);background:var(--zc);box-shadow:inset 0 0 0 1px var(--c0)}
.vt.none,.vt.few{color:var(--mut);background:var(--card2)}
.kp{font-size:13px;color:var(--ink2);margin:5px 0 2px;line-height:1.65}.kp b{color:var(--ink)}
.kzs{display:block;width:100%;max-width:330px;height:auto;margin:2px 0}
.kz0{stroke:var(--line2)}.kzo{fill:var(--bp)}.kzv{font-size:10.5px;fill:var(--ink2);text-anchor:middle}.kzv.on{font-weight:700;fill:var(--ink)}
.kzl{font-size:10.5px;fill:var(--mut);text-anchor:middle}.kzl.on{font-weight:700}.kza{stroke:var(--ink2);stroke-width:1.2;stroke-dasharray:4 3}
.kmore>summary{cursor:pointer;font-size:13px;color:var(--acc);padding:8px 0 2px;border-top:1px solid var(--line)}
.klist{list-style:none;margin:4px 0 0;padding:0}
.kmini{display:block;width:100%;text-align:left;border:0;background:none;padding:6px 4px;border-top:1px solid var(--line);font:inherit;color:inherit;cursor:pointer;border-radius:8px}
.kmini:hover{background:var(--card2)}.kmini .vt{margin-top:2px}
.wchg ul{list-style:none;margin:6px 0 0;padding:0}.wchg li{font-size:13px;line-height:1.75;margin:3px 0;color:var(--ink2)}
.wtag{display:inline-block;font-size:11.5px;color:var(--mut);margin-right:6px;min-width:4.6em}
.wchg .nmb{font-size:13px}
.ish2{display:flex;align-items:baseline;justify-content:space-between;gap:6px 10px;flex-wrap:wrap;margin:0 0 6px}.ish2 h2{margin:0;font-size:17px}
.imap{position:relative}.imap svg{display:block;width:100%;height:auto}
.iln{fill:var(--card2)}.izb{opacity:.13}.ilab{font-size:13.5px;font-weight:700;fill:var(--ink)}.ilsc{font-weight:800}.ilsub{font-size:11px;fill:var(--mut)}
.imv{stroke-width:2.2;stroke-linecap:round}.imv.up{stroke:var(--c4);stroke-opacity:.75}.imv.dn{stroke:var(--c0);stroke-opacity:.8}
.iago{fill:var(--panel);stroke:var(--mut);stroke-width:1.2}
.idot{stroke:var(--ring);stroke-width:1.3;cursor:pointer}.idot:hover,.idot.sel{stroke:var(--ink);stroke-width:2.4}
.iann{font-size:12px;fill:var(--ink)}.iannv{font-weight:700}.ilead{fill:none;stroke:var(--line2);stroke-width:1}
.itk{font-size:10.5px;fill:var(--mut);text-anchor:middle}
.itab td .nmb{font-size:13px}
.vmore{margin:22px 0 0}
.drw{position:fixed;top:0;right:0;bottom:0;width:min(480px,100vw);background:var(--panel);border-left:1px solid var(--line);box-shadow:var(--shadow);z-index:40;display:flex;flex-direction:column}
.drw-h{display:flex;align-items:center;gap:6px;padding:10px 12px;border-bottom:1px solid var(--line)}
.drw-tt{flex:1;min-width:0}.drw-tt span{display:block;font-size:12px;color:var(--mut)}.drw-tt h2{margin:0;font-size:17px;line-height:1.35}
.drw-h button{flex:none;width:34px;height:34px;border-radius:9px;border:1px solid var(--line);background:var(--card2);color:var(--ink);font-size:17px;line-height:1;cursor:pointer}
.drw-h button:disabled{opacity:.35;cursor:default}
.drw-c{flex:1;overflow-y:auto;padding:12px 14px 48px;container-type:inline-size;overscroll-behavior:contain}
.dnum{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:0 0 8px}
.dnum div{background:var(--card2);border-radius:10px;padding:7px 9px;min-width:0}
.dnum>div>span{display:block;font-size:11.5px;color:var(--mut)}.dnum>div>b{display:block;font-size:19px;line-height:1.3;overflow-wrap:anywhere}
.dnum>div>i{display:block;font-style:normal;font-size:11.5px;color:var(--ink2)}
.dhow,.dst,.dpos{font-size:13px;color:var(--ink2);line-height:1.7;margin:4px 0}
.drw h4{font-size:13.5px;margin:16px 0 6px}.drw h4 span{font-weight:400;color:var(--mut);font-size:11.5px;margin-left:6px}
.dtrk{display:grid;grid-template-columns:78px minmax(0,1fr) 72px;gap:8px;align-items:center;font-size:12.5px;margin:7px 0;color:var(--ink2)}
.dtb{position:relative;height:8px;border-radius:4px;background:linear-gradient(90deg,var(--c0),var(--c2) 50%,var(--c4))}
.dtb i{position:absolute;top:-4px;width:4px;height:16px;margin-left:-2px;border-radius:2px;background:var(--ink);box-shadow:0 0 0 2px var(--ring)}
.dtrk b{text-align:right;color:var(--ink);font-weight:600}
.dzs{display:grid;grid-template-columns:1fr;gap:6px}.dzone p{margin:0;font-size:12.5px;color:var(--ink2)}.dzone .kzs{max-width:360px}
.drel{margin:0;padding-left:18px;font-size:13px;line-height:1.75;color:var(--ink2)}
.dbtn{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}
.dchart{position:relative;min-height:60px;margin:8px 0 2px}.dchart svg{display:block;width:100%;height:auto}
.dchart .seg{margin:0 0 4px}
.dzh{fill:var(--zh)}.dzc{fill:var(--zc)}.dgl{stroke:var(--line);stroke-width:1}.dgt{font-size:10.5px;fill:var(--mut)}
.dln{fill:none;stroke:var(--acc);stroke-width:2;stroke-linejoin:round}.dpx{fill:none;stroke:var(--ink2);stroke-width:1.4}
.ddot{stroke:var(--ring);stroke-width:2}.dcx{stroke:var(--ink);stroke-width:1;opacity:.45}
.drw .cd{border:0;padding:0;margin:10px 0 0;border-radius:0}.drw .cd>.ch{display:none}
.drw .its .nmb{font-size:13.5px}
@container (max-width:520px){
 .its .ith{display:none}
 .its .it{grid-template-columns:minmax(0,1fr) 64px 78px;row-gap:3px}
 .its .it .inm{grid-column:1/2;grid-row:1}.its .it .ihb{grid-column:1/2;grid-row:2}
 .its .it .ipl{grid-column:2/3;grid-row:1/3;align-self:center}
 .its .it .ish{grid-column:3/4;grid-row:1}.its .it .iwk{grid-column:3/4;grid-row:2}
 .its .it .ish::before{content:"佔比 "}.its .it .iwk::before{content:"本週 "}
}
.cps{position:relative;min-height:240px}.cps svg{display:block;width:100%;height:auto}
.czn{opacity:.09}.czl{font-size:11.5px;text-anchor:middle;font-weight:600}.cax{stroke:var(--line2)}.cat{font-size:10.5px;fill:var(--mut)}
.czero{stroke:var(--line2);stroke-dasharray:4 4}.cql{font-size:12.5px;font-weight:700;fill:var(--mut)}
.ctl{fill:none;stroke-linecap:round;stroke-linejoin:round}.ctl.zt0{stroke:var(--c0)}.ctl.zt1{stroke:var(--c1)}.ctl.zt2{stroke:var(--c2)}.ctl.zt3{stroke:var(--c3)}.ctl.zt4{stroke:var(--c4)}
.cbub{cursor:pointer}.cbub circle{stroke:var(--ring);stroke-width:1.6}.cbub text{text-anchor:middle;font-weight:800;fill:#fff;pointer-events:none;paint-order:stroke;stroke:rgba(0,0,0,.35);stroke-width:2px}
.cbub .cn{font-size:12px}.cbub .cs{font-size:15px}.cbub.zb1 text,.cbub.zb2 text,.cbub.zb3 text{fill:#0b1220;stroke:rgba(255,255,255,.45)}
#cps-sec{margin-top:6px}
.cit circle{stroke:var(--ring);stroke-width:1.2;cursor:pointer}.cit text{font-size:11.5px;fill:var(--ink);paint-order:stroke;stroke:var(--panel);stroke-width:3px;pointer-events:none}
.cquad h3{margin:0 0 6px;font-size:15px;color:var(--ink)}.cquad dl{margin:0}.cquad dt{font-size:12.5px;font-weight:700;margin:10px 0 2px;color:var(--ink)}
.cquad dt i{font-style:normal;font-weight:400;color:var(--mut);margin-left:6px}.cquad dd{margin:0;font-size:13px;color:var(--ink2);line-height:1.7}
.ter{position:relative;height:min(68vh,620px);min-height:360px;background:var(--card2);border-radius:12px;overflow:hidden;touch-action:none}
.ter canvas{position:absolute;inset:0;width:100%;height:100%;cursor:grab}.ter canvas.drag{cursor:grabbing}
.tld{position:absolute;left:14px;top:10px;margin:0}.tctl{margin:6px 0 8px}
.ter .tip{min-width:170px}
@media (max-width:820px){.vgrid{grid-template-columns:1fr}.vbar{gap:6px 10px}}
@media (max-width:640px){
 .vsw button{padding:5px 9px;font-size:13px}.rsm{grid-template-columns:repeat(4,minmax(0,1fr));gap:4px}.rsm .pxn{display:none}
 .rchips{flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none;margin:2px -16px 4px;padding:0 16px}.rchips::-webkit-scrollbar{display:none}.rch{flex:none}
 .rnow{min-width:4.8em;font-size:12.5px}.dnum b{font-size:17px}.drw{width:100vw;border-left:0}
 .ter{height:62vh;min-height:320px}
}
body.drw-on{overflow:hidden}
@media (min-width:1100px){body.drw-on{overflow:auto}}
@media (prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
"""


# ── 瀏覽器端（雷達、項目分布、右側面板、羅盤、3D 地形、視角切換）。資料：頁面裡的 script.hviz（小份）＋ x9mh.json
#    （heatInit 下載、window.heatGet() 共用）。heatInit 每次（換指數時）最後呼叫 heatViz：先拿掉上一次掛的事件再重建。
JS = r"""
window.heatViz = function () {
'use strict';
if (window.heatClose) window.heatClose();
if (window.__vizAC) window.__vizAC.abort();
const AC = window.__vizAC = new AbortController(), SG = {signal: AC.signal};
const J = document.querySelector('script.hviz');
if (!J) return;
let P = null;
try { P = JSON.parse(J.textContent); } catch (e) { P = null; }
if (!P || !P.dims) return;
const M = window.HEAT_META || {}, ROOT = J.closest('main') || document.body;
const $ = (s, r) => (r || ROOT).querySelector(s), $$ = (s, r) => Array.from((r || ROOT).querySelectorAll(s));
const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const RM = !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
const BD = M.bands || [[0, 20, '過冷'], [20, 40, '偏冷'], [40, 60, '中性'], [60, 80, '偏熱'], [80, 100, '過熱']];
function zc(v) { if (v == null) return 'x'; for (let k = 0; k < BD.length; k++) if (v >= BD[k][0] && (v < BD[k][1] || k === BD.length - 1)) return String(k); return '2'; }
function bn(v) { const z = zc(v); return z === 'x' ? '沒有分數' : BD[+z][2]; }
function n0(v) { if (v == null) return '—'; const r = Math.round(v); return (r === 20 || r === 40 || r === 60 || r === 80) && v < r ? (Math.floor(v * 10) / 10).toFixed(1) : String(r); }   // 同 Python n0()
function sg(v, d) { if (v == null) return '—'; d = d || 0; const r = Number(v.toFixed(d)); return (r > 0 ? '+' : (r < 0 ? '−' : '')) + Math.abs(r).toFixed(d); }
function ym(d) { return d ? (+d.slice(0, 4)) + '/' + (+d.slice(5, 7)) : '—'; }
function ymd(d) { return d ? ym(d) + (d.length > 7 ? '/' + (+d.slice(8, 10)) : '') : '—'; }
function val(t, i) { if (!t) return null; const j = i - t.o; return j >= 0 && j < t.v.length ? t.v[j] : null; }
function fpx(v) { return v == null ? '—' : Math.round(v).toLocaleString('en-US'); }
function css(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
const DIM = P.dims.map(d => d.id), NM = {}, IT = {};
P.dims.forEach(d => { NM[d.id] = d.name; });
P.items.forEach(it => { IT[it.k] = it; NM[it.k] = it.name; });
const PXN = P.px || M.px || '';
let D = null;
const hooks = [];
function withData(fn) { if (D) fn(); else hooks.push(fn); }

// ── 視角切換（雷達｜羅盤｜地形 3D｜研究）：網址記在 #v=…（美股頁另有 #ix=…，兩個並存）
const VIEWS = ['radar', 'compass', 'terrain', 'research'];
function hget(k) { const m = new RegExp('(?:^#|&)' + k + '=([\\w-]+)').exec(location.hash || ''); return m ? m[1] : null; }
function hset(k, v) {
  const ps = (location.hash || '').replace(/^#/, '').split('&').filter(x => x && x.split('=')[0] !== k);
  if (v) ps.push(k + '=' + v);
  try { history.replaceState(history.state, '', ps.length ? '#' + ps.join('&') : location.pathname + location.search); } catch (e) { /* file:// */ }
}
function setView(v, o) {
  o = o || {};
  if (VIEWS.indexOf(v) < 0) v = 'radar';
  document.documentElement.dataset.hv = v;
  $$('.hview').forEach(el => { el.hidden = el.dataset.view !== v; });
  document.querySelectorAll('.vsw [data-view]').forEach(b => { const on = b.dataset.view === v; b.classList.toggle('on', on); b.setAttribute('aria-pressed', on ? 'true' : 'false'); });
  if (!o.quiet) hset('v', v === 'radar' ? null : v);
  if (v !== 'radar') stopPlay();
  if (v === 'compass') cShow();
  if (v === 'terrain') tShow();
  if (v === 'radar') { radarDraw(); trackDraw(); imapDraw(); window.dispatchEvent(new Event('resize')); }
  if (o.anchor) { const a = document.getElementById(o.anchor); if (a) setTimeout(() => a.scrollIntoView({block: 'start'}), 0); }
  else if (!o.quiet) window.scrollTo(0, 0);
}
window.heatView = (v, a) => setView(v, {anchor: a});

// ── 右側面板（內容在 id＝dt-面向、it-項目 的 template；手機全螢幕，返回鍵關閉）
const DRW = document.getElementById('drw'), DC = document.getElementById('drw-c');
const bPrev = document.getElementById('drw-prev'), bNext = document.getElementById('drw-next');
const bBack = document.getElementById('drw-back'), bX = document.getElementById('drw-x');
let cur = null, stack = [], lastFocus = null;
function tplOf(kind, k) { return document.getElementById((kind === 'dim' ? 'dt-' : 'it-') + k); }
function listOf(kind, k) { if (kind === 'dim') return DIM; const it = IT[k]; return it ? (P.ord[it.dim] || [k]) : [k]; }
function openD(kind, k, o) {
  o = o || {};
  const t = tplOf(kind, k);
  if (!t || !DRW) return false;
  if (o.push && cur) stack.push(cur); else if (!o.keep) stack = [];
  cur = {kind: kind, k: k};
  document.getElementById('drw-k').textContent = t.dataset.kick || '';
  document.getElementById('drw-t').textContent = t.dataset.title || '';
  DC.replaceChildren(t.content.cloneNode(true));
  DC.scrollTop = 0;
  const L = listOf(kind, k), j = L.indexOf(k);
  bPrev.disabled = j <= 0; bNext.disabled = j < 0 || j >= L.length - 1;
  bBack.hidden = !stack.length;
  if (stack.length) bBack.setAttribute('aria-label', '回到' + (NM[stack[stack.length - 1].k] || ''));
  const was = !DRW.hidden;
  DRW.hidden = false;
  if (!was) {
    lastFocus = document.activeElement;
    document.body.classList.add('drw-on');
    try { history.pushState({hdrw: 1}, ''); } catch (e) { /* file:// */ }
  }
  $$('.dchart', DC).forEach(el => bigChart(el, el.dataset.k));
  mark(kind === 'dim' ? k : null, kind === 'item' ? k : null);
  bX.focus({preventScroll: true});
  return true;
}
function closeD(fromPop) {
  if (!DRW || DRW.hidden) return;
  DRW.hidden = true;
  DC.textContent = '';
  cur = null; stack = [];
  document.body.classList.remove('drw-on');
  mark(null, null);
  if (!fromPop && history.state && history.state.hdrw) { try { history.back(); } catch (e) { /* */ } }
  if (lastFocus && lastFocus.focus && document.contains(lastFocus)) lastFocus.focus({preventScroll: true});
}
function step(dir) {
  if (!cur) return;
  const L = listOf(cur.kind, cur.k), j = L.indexOf(cur.k) + dir;
  if (j >= 0 && j < L.length) openD(cur.kind, L[j], {keep: true});
}
let selDim = null, selItem = null;
function mark(d, k) {
  selDim = d; selItem = k;
  $$('.rax').forEach(g => g.classList.toggle('sel', g.dataset.open === 'dim:' + d));
  $$('.idot').forEach(c => c.classList.toggle('sel', c.dataset.k === k));
}
if (DRW) {
  bX.addEventListener('click', () => closeD(), SG);
  bPrev.addEventListener('click', () => step(-1), SG);
  bNext.addEventListener('click', () => step(1), SG);
  bBack.addEventListener('click', () => { const p = stack.pop(); if (p) openD(p.kind, p.k, {keep: true}); }, SG);
  DRW.addEventListener('click', e => {                 // 面板裡點項目名稱＝往下一層（返回鍵回上一層）
    const b = e.target.closest && e.target.closest('.nmb');
    if (!b || !b.dataset.k) return;
    const k = b.dataset.k, kind = IT[k] ? 'item' : (DIM.indexOf(k) >= 0 ? 'dim' : null);
    if (!kind) return;
    e.preventDefault(); e.stopPropagation();
    openD(kind, k, {push: true});
  }, SG);
}
window.addEventListener('popstate', () => { if (DRW && !DRW.hidden) closeD(true); }, SG);
window.heatOpen = k => (DIM.indexOf(k) >= 0 ? openD('dim', k) : (IT[k] ? openD('item', k) : false));
window.heatClose = () => closeD();

// 面板裡的大張走勢：上＝0～100（淡紅＝過熱、淡藍＝過冷），下＝指數（對數），共用時間軸
function bigChart(el, id) {
  if (!D) { el.dataset.wait = '1'; el.innerHTML = '<p class="note">走勢載入中…</p>'; return; }
  delete el.dataset.wait;
  const s0 = D.s[id];
  if (!s0 || !s0.h || !s0.h.v.length) { el.innerHTML = '<p class="note">沒有每週的 0～100 走勢。</p>'; return; }
  const rg = el.dataset.rg == null ? 3 : +el.dataset.rg, ds = D.w.d, i1 = ds.length - 1;
  let i0 = s0.h.o;
  if (rg) { const cut = (+ds[i1].slice(0, 4) - rg) + ds[i1].slice(4); const j = ds.findIndex(d => d > cut); i0 = Math.max(i0, j < 0 ? 0 : j); }
  const W = Math.max(280, Math.floor(el.clientWidth || 440)), PL = 30, PR = 8, T = 6, H1 = 124, G = 26, H2 = 66;
  const X = i => PL + (W - PL - PR) * (i - i0) / Math.max(1, i1 - i0), Y = v => T + H1 * (1 - v / 100);
  let s = '<rect class="dzh" x="' + PL + '" y="' + Y(100) + '" width="' + (W - PL - PR) + '" height="' + (Y(80) - Y(100)).toFixed(1) + '"/>'
    + '<rect class="dzc" x="' + PL + '" y="' + Y(20).toFixed(1) + '" width="' + (W - PL - PR) + '" height="' + (Y(0) - Y(20)).toFixed(1) + '"/>';
  [0, 50, 100].forEach(v => { s += '<line class="dgl" x1="' + PL + '" x2="' + (W - PR) + '" y1="' + Y(v).toFixed(1) + '" y2="' + Y(v).toFixed(1) + '"/><text class="dgt" x="' + (PL - 4) + '" y="' + (Y(v) + 3.5).toFixed(1) + '" text-anchor="end">' + v + '</text>'; });
  let d = '', pen = false, li = null;
  for (let i = i0; i <= i1; i++) { const v = val(s0.h, i); if (v == null) { pen = false; continue; } d += (pen ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(v).toFixed(1); pen = true; li = i; }
  s += '<path class="dln" d="' + d + '"/>';
  if (li != null) { const v = val(s0.h, li); s += '<circle class="ddot zf' + zc(v) + '" cx="' + X(li).toFixed(1) + '" cy="' + Y(v).toFixed(1) + '" r="4.5"/>'; }
  const top2 = T + H1 + G;
  let lo = Infinity, hi = -Infinity;
  for (let i = i0; i <= i1; i++) { const v = D.w.px[i]; if (v > 0) { const l = Math.log(v); lo = Math.min(lo, l); hi = Math.max(hi, l); } }
  const Y2 = l => top2 + H2 * (1 - (l - lo) / ((hi - lo) || 1));
  d = ''; pen = false;
  for (let i = i0; i <= i1; i++) { const v = D.w.px[i]; if (!(v > 0)) { pen = false; continue; } d += (pen ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y2(Math.log(v)).toFixed(1); pen = true; }
  s += '<path class="dpx" d="' + d + '"/><text class="dgt" x="' + PL + '" y="' + (top2 - 6) + '">' + esc(PXN) + '（對數）</text>';
  const yrs = [];
  for (let i = i0 + 1; i <= i1; i++) if (ds[i].slice(0, 4) !== ds[i - 1].slice(0, 4)) yrs.push(i);
  const st = Math.max(1, Math.ceil(yrs.length / (W < 380 ? 4 : 7)));
  yrs.filter((_, k) => k % st === 0).forEach(i => { s += '<text class="dgt" x="' + X(i).toFixed(1) + '" y="' + (top2 + H2 + 14) + '" text-anchor="middle">' + ds[i].slice(0, 4) + '</text>'; });
  const Ht = top2 + H2 + 18;
  s += '<line class="dcx" x1="0" x2="0" y1="' + T + '" y2="' + (top2 + H2) + '" visibility="hidden"/>';
  el.innerHTML = '<div class="seg">' + [3, 10, 0].map(r => '<button type="button" class="tb' + (r === rg ? ' on' : '') + '" data-rg="' + r + '" aria-pressed="' + (r === rg) + '">' + (r ? '近 ' + r + ' 年' : '全部') + '</button>').join('') + '</div>'
    + '<svg viewBox="0 0 ' + W + ' ' + Ht + '" width="' + W + '" height="' + Ht + '" role="img" aria-label="' + esc(NM[id] || '') + '的 0～100 與' + esc(PXN) + '">' + s + '</svg><div class="tip" hidden></div>';
  el.querySelectorAll('[data-rg]').forEach(b => b.addEventListener('click', () => { el.dataset.rg = b.dataset.rg; bigChart(el, id); }));
  const svg = el.querySelector('svg'), tip = el.querySelector('.tip'), cx = svg.querySelector('.dcx');
  const mv = ev => {
    const r = svg.getBoundingClientRect(), x = (ev.clientX - r.left) * (W / r.width);
    const i = Math.max(i0, Math.min(i1, Math.round(i0 + (x - PL) / ((W - PL - PR) || 1) * (i1 - i0)))), xx = X(i).toFixed(1);
    cx.setAttribute('x1', xx); cx.setAttribute('x2', xx); cx.setAttribute('visibility', 'visible');
    const v = val(s0.h, i);
    tip.innerHTML = '<b>' + esc(ymd(ds[i])) + '</b><div><strong>' + n0(v) + '</strong> ' + esc(v == null ? '' : bn(v)) + '</div><div class="tpx">' + esc(PXN) + ' ' + fpx(D.w.px[i]) + '</div>';
    tip.hidden = false;
    const bx = el.getBoundingClientRect(), tw = tip.offsetWidth;
    let left = ev.clientX - bx.left + 12;
    if (left + tw > bx.width) left = ev.clientX - bx.left - tw - 12;
    tip.style.left = Math.max(0, left) + 'px';
    tip.style.top = Math.max(0, ev.clientY - bx.top - 50) + 'px';
  };
  svg.addEventListener('pointermove', mv);
  svg.addEventListener('pointerdown', mv);
  svg.addEventListener('pointerleave', () => { cx.setAttribute('visibility', 'hidden'); tip.hidden = true; });
}

// ── 雷達：時間（RS.i＝x9mh.json 的第幾週；null＝現在）雷達和羅盤共用
const RS = {i: null, ov: [], cur: null, tgt: null, raf: 0, play: 0};
const PRE = {};
(P.pre || []).forEach(p => { PRE[p.key] = p; });
if (PRE.w4) RS.ov.push({key: 'w4', slot: 0});
function iLast() { return D ? D.w.d.length - 1 : -1; }
function iStart() { if (!D) return 0; const j = D.w.d.findIndex(d => d >= P.start); return j < 0 ? 0 : j; }
function nowV() { return P.dims.map(d => d.sc); }
function atV(i) { return DIM.map(id => val(D.s[id] && D.s[id].h, i)); }
function isNow() { return RS.i == null || !D || RS.i >= iLast(); }
function tgtV() { return isNow() ? nowV() : atV(RS.i); }
function geo() { const b = $('#rad'), w = b ? b.clientWidth : 0; return w && w < 470 ? {W: 380, H: 356, cx: 190, cy: 180, R: 108, m: 1} : {W: 560, H: 466, cx: 280, cy: 236, R: 162, m: 0}; }
function rp(g, k, v) { const a = -Math.PI / 2 + k * 2 * Math.PI / DIM.length, r = g.R * Math.max(0, Math.min(100, v == null ? 0 : v)) / 100; return [g.cx + Math.cos(a) * r, g.cy + Math.sin(a) * r]; }
function rpath(g, vs) { return vs.map((v, k) => { const p = rp(g, k, v); return (k ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1); }).join('') + 'Z'; }
function radarDraw() {
  const box = $('#rad');
  if (!box) return;
  const g = geo(), n = DIM.length, tg = RS.tgt || tgtV(), cv = RS.cur || tg;
  let s = '<circle class="rzh" cx="' + g.cx + '" cy="' + g.cy + '" r="' + g.R + '"/><circle class="rpn" cx="' + g.cx + '" cy="' + g.cy + '" r="' + (g.R * 0.8).toFixed(1) + '"/>'
    + '<circle class="rzc" cx="' + g.cx + '" cy="' + g.cy + '" r="' + (g.R * 0.2).toFixed(1) + '"/>';
  [20, 40, 60, 80, 100].forEach(v => { s += '<circle class="rring r' + v + '" cx="' + g.cx + '" cy="' + g.cy + '" r="' + (g.R * v / 100).toFixed(1) + '"/>'; });
  [20, 40, 60, 80].forEach(v => { s += '<text class="rrl" x="' + (g.cx + 3) + '" y="' + (g.cy - g.R * v / 100 - 2).toFixed(1) + '">' + v + '</text>'; });
  DIM.forEach((id, k) => { const p = rp(g, k, 100); s += '<line class="rgl" x1="' + g.cx + '" y1="' + g.cy + '" x2="' + p[0].toFixed(1) + '" y2="' + p[1].toFixed(1) + '"/>'; });
  RS.ov.forEach(o => { const p = PRE[o.key]; if (p) s += '<path class="rov o' + o.slot + '" d="' + rpath(g, p.v) + '"/>'; });
  if (!isNow()) s += '<path class="rghost" d="' + rpath(g, nowV()) + '"/>';
  s += '<path class="rmain" d="' + rpath(g, cv) + '"/>';
  cv.forEach((v, k) => {
    const p = rp(g, k, v), z = zc(tg[k]);
    s += '<circle class="rv ' + (z === 'x' ? 'zfx' : 'zf' + z) + '" cx="' + p[0].toFixed(1) + '" cy="' + p[1].toFixed(1) + '" r="' + (g.m ? 4.5 : 5.5) + '"><title>' + esc(NM[DIM[k]] + '：' + n0(tg[k]) + '（' + bn(tg[k]) + '）') + '</title></circle>';
  });
  DIM.forEach((id, k) => {
    const a = -Math.PI / 2 + k * 2 * Math.PI / n, ca = Math.cos(a), sa = Math.sin(a);
    const lx = g.cx + ca * (g.R + (g.m ? 14 : 22)), ly = g.cy + sa * (g.R + (g.m ? 12 : 20));
    const an = ca > 0.3 ? 'start' : (ca < -0.3 ? 'end' : 'middle');
    const y1 = ly + (sa < -0.5 ? -(g.m ? 14 : 18) : (sa > 0.5 ? (g.m ? 10 : 12) : -4));
    const nm = NM[id], wpx = Math.max(nm.length, 6) * (g.m ? 12.5 : 14) + 10, z = zc(tg[k]);
    const rx = an === 'start' ? lx - 5 : (an === 'end' ? lx - wpx + 5 : lx - wpx / 2);
    s += '<g class="rax' + (selDim === id ? ' sel' : '') + '" data-open="dim:' + id + '" tabindex="0" role="button" aria-label="' + esc(nm + ' ' + n0(tg[k]) + ' ' + bn(tg[k]) + '：打開細項') + '">'
      + '<rect class="rhit" x="' + rx.toFixed(1) + '" y="' + (y1 - 16).toFixed(1) + '" width="' + wpx.toFixed(1) + '" height="' + (g.m ? 34 : 39) + '" rx="6"/>'
      + '<text class="ran" x="' + lx.toFixed(1) + '" y="' + y1.toFixed(1) + '" text-anchor="' + an + '"' + (g.m ? ' style="font-size:12.5px"' : '') + '>' + esc(nm) + '</text>'
      + '<text class="ras zt' + z + '" x="' + lx.toFixed(1) + '" y="' + (y1 + (g.m ? 15 : 17)).toFixed(1) + '" text-anchor="' + an + '"' + (g.m ? ' style="font-size:12px"' : '') + '>' + n0(tg[k]) + ' ' + esc(bn(tg[k])) + '</text></g>';
  });
  box.innerHTML = '<svg viewBox="0 0 ' + g.W + ' ' + g.H + '" role="img" aria-label="面向雷達">' + s + '</svg>';
  legend();
}
function legend() {
  const el = $('#rleg');
  if (!el) return;
  let h = '<span><i></i>' + esc(isNow() ? '現在（' + ymd(P.asof) + '）' : ymd(D.w.d[RS.i]) + ' 那一週') + '</span>';
  if (!isNow()) h += '<span><i class="gh"></i>現在</span>';
  RS.ov.forEach(o => { const p = PRE[o.key]; if (p) h += '<span><i class="o' + o.slot + '"></i>' + esc(p.lab + '（' + ymd(p.d) + '）') + '</span>'; });
  el.innerHTML = h;
}
function setT(i, now) {
  if (!D) return;
  const last = iLast();
  i = Math.max(iStart(), Math.min(last, i));
  RS.i = i >= last ? null : i;
  const tg = tgtV(), from = RS.cur || tg;
  RS.tgt = tg;
  ['#rtin', '#ctin'].forEach(sel => { const inp = $(sel); if (inp && +inp.value !== i) inp.value = i; });
  nowLab();
  smMark();
  cancelAnimationFrame(RS.raf);
  if (document.documentElement.dataset.hv === 'compass') cDraw();
  if (now || RM) { RS.cur = tg.slice(); radarDraw(); return; }
  const t0 = performance.now(), dur = 260;
  const fr = t => {
    const p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 3);
    RS.cur = tg.map((v, k) => (v == null || from[k] == null) ? v : from[k] + (v - from[k]) * e);
    radarDraw();
    if (p < 1) RS.raf = requestAnimationFrame(fr);
  };
  RS.raf = requestAnimationFrame(fr);
}
function nowLab() {
  const i = isNow() ? iLast() : RS.i, d = isNow() ? P.asof : D.w.d[i];
  const h = esc(ymd(d)) + '<i>' + esc(isNow() ? '現在' : PXN + ' ' + fpx(D.w.px[i])) + '</i>';
  ['#rnow', '#cnow'].forEach(sel => { const el = $(sel); if (el) el.innerHTML = h; });
  const rd = $('#rdate');
  if (rd) rd.textContent = isNow() ? '現在（' + ymd(P.asof) + '）' : ymd(d) + ' 那一週';
}
function trackDraw() {
  [['#rtsvg', '#rtin'], ['#ctsvg', '#ctin']].forEach(p => {
    const svg = $(p[0]), inp = $(p[1]);
    if (!svg || !inp || !D || !svg.getBoundingClientRect().width) return;
    const i0 = iStart(), i1 = iLast(), w = Math.max(100, Math.round(svg.getBoundingClientRect().width)), h = 44;
    inp.min = i0; inp.max = i1; inp.value = RS.i == null ? i1 : RS.i; inp.disabled = false;
    let lo = Infinity, hi = -Infinity;
    for (let i = i0; i <= i1; i++) { const v = D.w.px[i]; if (v > 0) { lo = Math.min(lo, Math.log(v)); hi = Math.max(hi, Math.log(v)); } }
    const X = i => w * (i - i0) / Math.max(1, i1 - i0), Y = l => 4 + (h - 17) * (1 - (l - lo) / ((hi - lo) || 1));
    let d = '', pen = false;
    for (let i = i0; i <= i1; i++) { const v = D.w.px[i]; if (!(v > 0)) { pen = false; continue; } d += (pen ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(Math.log(v)).toFixed(1); pen = true; }
    let s = '<path class="rtx" d="' + d + '"/>';
    const yrs = [];
    for (let i = i0 + 1; i <= i1; i++) if (D.w.d[i].slice(0, 4) !== D.w.d[i - 1].slice(0, 4)) yrs.push(i);
    const st = Math.max(1, Math.ceil(yrs.length / (w < 420 ? 4 : 8)));
    yrs.filter((_, k) => k % st === 0).forEach(i => { s += '<text class="rty" x="' + X(i).toFixed(1) + '" y="' + (h - 2) + '">' + D.w.d[i].slice(0, 4) + '</text>'; });
    svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
    svg.innerHTML = s;
  });
  ['#rplay', '#cplay'].forEach(sel => { const b = $(sel); if (b) b.disabled = !D; });
}
function play() {
  if (!D) return;
  const last = iLast();
  if (RM) { setT(last, true); return; }
  let i = isNow() ? Math.max(iStart(), last - 104) : RS.i;
  setT(i, true);
  ['#rplay', '#cplay'].forEach(sel => { const b = $(sel); if (b) { b.textContent = '❚❚'; b.setAttribute('aria-label', '暫停'); } });
  RS.play = setInterval(() => { i += 1; setT(i, true); if (i >= last) stopPlay(); }, 90);
}
function stopPlay() {
  if (!RS.play) return;
  clearInterval(RS.play); RS.play = 0;
  ['#rplay', '#cplay'].forEach(sel => { const b = $(sel); if (b) { b.textContent = '▶'; b.setAttribute('aria-label', '播放近兩年'); } });
}
function chips() {
  const el = $('#rchips');
  if (el) el.innerHTML = (P.pre || []).map(p => {
    const o = RS.ov.find(x => x.key === p.key);
    return '<button type="button" class="rch' + (o ? ' on o' + o.slot : '') + '" data-ov="' + esc(p.key) + '" aria-pressed="' + (o ? 'true' : 'false') + '" title="' + esc(p.sub || '') + '"><i></i>' + esc(p.lab) + (p.sub ? '<em>' + esc(p.sub) + '</em>' : '') + '</button>';
  }).join('');
  const ce = $('#cchips');
  if (ce) ce.innerHTML = '<button type="button" class="rch" data-go="now">現在</button>' + (P.pre || []).map(p => '<button type="button" class="rch" data-go="' + esc(p.d) + '" title="' + esc(p.sub || '') + '">' + esc(p.lab) + '</button>').join('');
}
function toggleOv(key) {
  const j = RS.ov.findIndex(x => x.key === key);
  if (j >= 0) RS.ov.splice(j, 1);
  else {
    if (RS.ov.length >= 3) RS.ov.shift();                    // 最多疊 3 個；顏色跟著日期，不因為別的拿掉而換色
    const used = new Set(RS.ov.map(x => x.slot));
    let s = 0;
    while (used.has(s)) s++;
    RS.ov.push({key: key, slot: s});
  }
  chips(); radarDraw();
}
function goDate(d) {
  if (!D) return;
  if (d === 'now') { setT(iLast()); return; }
  const j = D.w.d.indexOf(d);
  if (j >= 0) setT(j);
}
function smDraw() {
  const el = $('#rsm');
  if (!el) return;
  el.innerHTML = (P.qs || []).map((q, j) => {
    const g = {cx: 50, cy: 50, R: 40}, hot = q.v.filter(v => v != null && v >= 80).length, last = j === P.qs.length - 1;
    let s = '<circle class="mr" cx="50" cy="50" r="20"/><circle class="mr" cx="50" cy="50" r="40"/><path class="mp' + (hot >= 3 ? ' hot' : '') + '" d="' + rpath(g, q.v) + '"/>';
    q.v.forEach((v, k) => { const p = rp(g, k, v), z = zc(v); s += '<circle class="' + (z === 'x' ? 'zfx' : 'zf' + z) + '" cx="' + p[0].toFixed(1) + '" cy="' + p[1].toFixed(1) + '" r="3"/>'; });
    return '<button type="button" data-go="' + (last ? 'now' : q.d) + '" class="' + (last ? 'now' : '') + '" aria-label="' + esc((last ? '現在' : ymd(q.d)) + '的形狀') + '"><svg viewBox="0 0 100 100" aria-hidden="true">' + s + '</svg><b>' + esc(last ? '現在' : ym(q.d)) + '</b><i><span class="pxn">' + esc(PXN) + ' </span>' + fpx(q.px) + '</i></button>';
  }).join('');
  smMark();
}
function smMark() {
  const d = isNow() ? 'now' : (D ? D.w.d[RS.i] : null);
  $$('#rsm button').forEach(b => b.classList.toggle('sel', b.dataset.go === d && d !== 'now'));
}

// ── 全部項目分布：每個面向一條，位置＝0～100、短線＝和上週比從哪裡移過來、點越大＝拉動越多
function swarm(os, half) {
  const placed = [];
  os.slice().sort((a, b) => b.r - a.r || a.x - b.x).forEach(o => {
    let best = 0, bestOv = Infinity;
    for (let k = 0; k <= 80; k++) {
      const off = (k % 2 ? 1 : -1) * Math.ceil(k / 2) * 2.2;
      if (Math.abs(off) + o.r > half + 2) continue;
      let ov = 0;
      placed.forEach(p => { const dd = Math.hypot(p.x - o.x, p.y - off), need = p.r + o.r + 1.2; if (dd < need) ov += need - dd; });
      if (ov === 0) { best = off; bestOv = 0; break; }
      if (ov < bestOv) { bestOv = ov; best = off; }
    }
    o.y = best; placed.push(o);
  });
}
function imapDraw() {
  const box = $('#imap');
  if (!box || !box.clientWidth) return;
  const mob = box.clientWidth < 640, VW = mob ? 390 : 920, LW = mob ? 10 : 156, RW = mob ? 10 : 252, lh = mob ? 100 : 88, top = 4;
  const x0 = LW + (mob ? 6 : 0), x1 = VW - RW - (mob ? 9 : 12), X = v => x0 + (x1 - x0) * v / 100, VH = top + P.dims.length * lh + 18;
  const mx = Math.max(1, ...P.items.map(it => Math.abs(it.pull || 0)));
  let s = '';
  P.dims.forEach((d, j) => {
    const y0 = top + j * lh, yc = mob ? y0 + 62 : y0 + lh / 2, half = mob ? 28 : lh / 2 - 10, z = zc(d.sc);
    s += '<rect class="iln" x="2" y="' + (y0 + 3) + '" width="' + (VW - 4) + '" height="' + (lh - 6) + '" rx="10"/>';
    BD.forEach((b, k) => { s += '<rect class="izb zf' + k + '" x="' + X(b[0]).toFixed(1) + '" y="' + (yc - half - 4).toFixed(1) + '" width="' + (X(Math.min(100, b[1])) - X(b[0])).toFixed(1) + '" height="' + (2 * half + 8).toFixed(1) + '"/>'; });
    if (mob) s += '<text class="ilab" x="12" y="' + (y0 + 21) + '">' + esc(d.name) + ' <tspan class="ilsc zt' + z + '">' + n0(d.sc) + ' ' + esc(bn(d.sc)) + '</tspan></text>';
    else s += '<text class="ilab" x="16" y="' + (yc - 3) + '">' + esc(d.name) + '</text><text class="ilsub" x="16" y="' + (yc + 14) + '"><tspan class="ilsc zt' + z + '">' + n0(d.sc) + ' ' + esc(bn(d.sc)) + '</tspan></text>';
    const os = P.items.filter(it => it.dim === d.id && it.h != null).map(it => ({it: it, x: X(it.h), r: (mob ? 4 : 4.5) + (mob ? 6 : 8) * Math.abs(it.pull || 0) / mx, y: 0}));
    swarm(os, half);
    os.forEach(o => {
      const it = o.it, y = yc + o.y;
      if (it.ago != null && Math.abs(it.h - it.ago) >= 1) s += '<line class="imv ' + (it.h > it.ago ? 'up' : 'dn') + '" x1="' + X(it.ago).toFixed(1) + '" x2="' + o.x.toFixed(1) + '" y1="' + y.toFixed(1) + '" y2="' + y.toFixed(1) + '"/><circle class="iago" cx="' + X(it.ago).toFixed(1) + '" cy="' + y.toFixed(1) + '" r="2.4"/>';
    });
    os.forEach(o => {
      const it = o.it, y = yc + o.y;
      s += '<circle class="idot zf' + zc(it.h) + (selItem === it.k ? ' sel' : '') + '" data-open="item:' + esc(it.k) + '" data-k="' + esc(it.k) + '" tabindex="0" role="button" aria-label="' + esc(it.name + ' ' + n0(it.h) + ' ' + bn(it.h)) + '" cx="' + o.x.toFixed(1) + '" cy="' + y.toFixed(1) + '" r="' + o.r.toFixed(1) + '"/>';
    });
    const sc = o => (o.it.ago != null ? Math.abs(o.it.h - o.it.ago) : 0) + 0.6 * Math.abs(o.it.h - 50);
    const lab = os.slice().sort((a, b) => sc(b) - sc(a)).slice(0, mob ? 1 : 3);
    const txt = it => (it.ago != null && Math.abs(it.h - it.ago) >= 10 ? n0(it.ago) + '→' : '') + n0(it.h);
    if (!mob) lab.sort((a, b) => a.y - b.y).forEach((o, q) => {
      const ly = y0 + 23 + q * 24, lx = VW - RW + 22, y = yc + o.y, it = o.it;
      s += '<path class="ilead" d="M' + o.x.toFixed(1) + ' ' + y.toFixed(1) + 'L' + (VW - RW + 8) + ' ' + (ly - 4) + 'L' + (lx - 4) + ' ' + (ly - 4) + '"/>'
        + '<text class="iann" x="' + lx + '" y="' + ly + '">' + esc(it.name.length > 12 ? it.name.slice(0, 12) + '…' : it.name) + '</text>'
        + '<text class="iann iannv zt' + zc(it.h) + '" x="' + (VW - 8) + '" y="' + ly + '" text-anchor="end">' + txt(it) + '</text>';
    });
    else if (lab.length) { const it = lab[0].it; s += '<text class="iann" x="' + (VW - 12) + '" y="' + (y0 + 21) + '" text-anchor="end">' + esc(it.name.length > 9 ? it.name.slice(0, 9) + '…' : it.name) + ' <tspan class="iannv zt' + zc(it.h) + '">' + txt(it) + '</tspan></text>'; }
  });
  [0, 20, 40, 60, 80, 100].forEach(v => { s += '<text class="itk" x="' + X(v).toFixed(1) + '" y="' + (VH - 3) + '">' + v + '</text>'; });
  box.innerHTML = '<svg viewBox="0 0 ' + VW + ' ' + VH + '" role="img" aria-label="全部項目的 0～100">' + s + '</svg><div class="tip" hidden></div>';
  const svg = box.querySelector('svg'), tip = box.querySelector('.tip');
  svg.addEventListener('pointermove', e => {
    const c = e.target.closest && e.target.closest('.idot');
    if (!c) { tip.hidden = true; return; }
    const it = IT[c.dataset.k];
    tip.innerHTML = '<b>' + esc(it.name) + '</b><div><strong>' + n0(it.h) + '</strong> ' + esc(bn(it.h)) + (it.ago != null ? '（上週 ' + n0(it.ago) + '）' : '') + '</div><div>現值 ' + esc(it.val) + '</div>' + (it.pull != null ? '<div>拉動面向 ' + sg(it.pull, 1) + ' 分</div>' : '');
    tip.hidden = false;
    const bx = box.getBoundingClientRect(), tw = tip.offsetWidth;
    let left = e.clientX - bx.left + 14;
    if (left + tw > bx.width) left = e.clientX - bx.left - tw - 14;
    tip.style.left = Math.max(0, left) + 'px';
    tip.style.top = Math.max(0, e.clientY - bx.top - 64) + 'px';
  });
  svg.addEventListener('pointerleave', () => { tip.hidden = true; });
  const nx = P.items.filter(it => it.h != null && (it.h >= 80 || it.h < 20)).length, nb = P.items.filter(it => it.h != null && it.ago != null && Math.abs(it.h - it.ago) >= 20).length;
  const sub = $('#isub');
  if (sub) sub.textContent = P.items.length + ' 項；' + nx + ' 項在過熱或過冷、' + nb + ' 項這週移動 20 分以上';
}

// ── 羅盤：橫軸＝0～100、縱軸＝近 4 週變化、尾巴＝過去 8 週；點泡泡展開項目（動畫從泡泡飛出去）
const CS = {drill: null, prog: 1, raf: 0, inited: false};
const YM = 45, TL = 9;
function mom(t, i) { const a = val(t, i), b = val(t, i - 4); return a == null || b == null ? null : a - b; }
function cgeo() { const b = $('#cps'), w = b ? b.clientWidth : 0; return w && w < 640 ? {W: 400, H: 440, l: 34, r: 10, t: 26, b: 30, m: 1} : {W: 860, H: 540, l: 46, r: 18, t: 30, b: 36, m: 0}; }
function cShow() { if (!D) { const b = $('#cps'); if (b) b.innerHTML = '<p class="note">走勢載入中…</p>'; withData(cShow); return; } if (!CS.inited) { CS.inited = true; trackDraw(); } cDraw(); }
function chaikin(p) {
  if (p.length < 3) return p;
  const o = [p[0]];
  for (let k = 0; k < p.length - 1; k++) { const a = p[k], b = p[k + 1]; o.push([0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1], a[2]], [0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1], b[2]]); }
  o.push(p[p.length - 1]);
  return o;
}
function quad(h, m) { return h >= 50 ? (m >= 0 ? 0 : 1) : (m >= 0 ? 3 : 2); }
const QN = ['熱、還在升溫', '熱、開始降溫', '冷、還在降溫', '冷、開始回溫'], QS = ['最熱的階段', '高檔轉弱', '低檔轉弱', '低檔轉強'];
function cDraw() {
  const box = $('#cps');
  if (!box || !D || !box.clientWidth) return;
  const g = cgeo(), i = isNow() ? iLast() : RS.i;
  const X = v => g.l + (g.W - g.l - g.r) * v / 100, Y = m => g.t + (g.H - g.t - g.b) * (1 - (Math.max(-YM, Math.min(YM, m)) + YM) / (2 * YM));
  let s = '';
  BD.forEach((b, k) => { const xa = X(b[0]), xb = X(Math.min(100, b[1])); s += '<rect class="czn zf' + k + '" x="' + xa.toFixed(1) + '" y="' + g.t + '" width="' + (xb - xa).toFixed(1) + '" height="' + (g.H - g.t - g.b) + '"/><text class="czl zt' + k + '" x="' + ((xa + xb) / 2).toFixed(1) + '" y="' + (g.t - 9) + '">' + esc(b[2]) + '</text>'; });
  s += '<line class="czero" x1="' + g.l + '" x2="' + (g.W - g.r) + '" y1="' + Y(0).toFixed(1) + '" y2="' + Y(0).toFixed(1) + '"/>';
  [0, 20, 40, 60, 80, 100].forEach(v => { s += '<text class="cat" x="' + X(v).toFixed(1) + '" y="' + (g.H - g.b + 15) + '" text-anchor="middle">' + v + '</text>'; });
  [-40, -20, 0, 20, 40].forEach(v => { s += '<text class="cat" x="' + (g.l - 6) + '" y="' + (Y(v) + 3.5).toFixed(1) + '" text-anchor="end">' + (v > 0 ? '+' + v : v) + '</text>'; });
  const qp = [[g.W - g.r - 8, g.t + 18, 'end'], [g.W - g.r - 8, g.H - g.b - 10, 'end'], [g.l + 8, g.H - g.b - 10, 'start'], [g.l + 8, g.t + 18, 'start']];
  qp.forEach((q, k) => { s += '<text class="cql" x="' + q[0] + '" y="' + q[1] + '" text-anchor="' + q[2] + '" style="' + (g.m ? 'font-size:11px;' : '') + (CS.drill ? 'opacity:.35' : '') + '">' + QN[k] + '</text>'; });
  const dims = DIM.map(id => { const t = D.s[id] && D.s[id].h; return {id: id, t: t, h: val(t, i), m: mom(t, i)}; }).filter(d => d.h != null && d.m != null);
  dims.forEach(d => {
    let pts = [];
    for (let j = i - TL + 1; j <= i; j++) { const h = val(d.t, j), m = mom(d.t, j); if (h != null && m != null) pts.push([X(h), Y(m), h]); }
    pts = chaikin(chaikin(pts));                                               // 尾巴磨圓（只是畫法；終點不動）
    const op = CS.drill && CS.drill !== d.id ? 0.12 : 1;
    for (let k = 1; k < pts.length; k++) s += '<path class="ctl zt' + zc(pts[k][2]) + '" style="opacity:' + (op * (0.12 + 0.8 * k / pts.length)).toFixed(2) + '" stroke-width="' + (0.8 + 2.6 * k / pts.length).toFixed(1) + '" d="M' + pts[k - 1][0].toFixed(1) + ' ' + pts[k - 1][1].toFixed(1) + 'L' + pts[k][0].toFixed(1) + ' ' + pts[k][1].toFixed(1) + '"/>';
  });
  let par = null;
  dims.forEach(d => {
    const on = CS.drill === d.id, r = on ? 13 : (g.m ? 21 : 27), z = zc(d.h), x = X(d.h), y = Y(d.m);
    if (on) par = [x, y];
    s += '<g class="cbub zb' + z + '" data-cd="' + d.id + '" tabindex="0" role="button" aria-label="' + esc(NM[d.id] + ' ' + n0(d.h) + '，近 4 週 ' + sg(d.m) + '：展開項目') + '" transform="translate(' + x.toFixed(1) + ',' + y.toFixed(1) + ')" style="opacity:' + (CS.drill && !on ? 0.18 : 1) + '">'
      + '<circle class="zf' + z + '" r="' + r + '" style="fill-opacity:' + (on ? 0.4 : 0.93) + '"/>' + (on ? '' : '<text class="cn" dy="-3"' + (g.m ? ' style="font-size:10.5px"' : '') + '>' + esc(NM[d.id]) + '</text><text class="cs" dy="14"' + (g.m ? ' style="font-size:13px"' : '') + '>' + n0(d.h) + '</text>') + '</g>';
  });
  if (CS.drill && par) {
    const keys = (P.ord[CS.drill] || []).filter(k => D.s[k] && D.s[k].h);
    const its = keys.map(k => ({k: k, h: val(D.s[k].h, i), m: mom(D.s[k].h, i)})).filter(x => x.h != null && x.m != null);
    const mx = Math.max(1, ...its.map(x => Math.abs(x.h - 50)));
    const lab = new Set(its.slice().sort((a, b) => Math.abs(b.h - 50) - Math.abs(a.h - 50)).slice(0, g.m ? 4 : 7).map(x => x.k));
    const e = 1 - Math.pow(1 - CS.prog, 3);
    its.forEach(x => {
      const tx = X(x.h), ty = Y(x.m), px = par[0] + (tx - par[0]) * e, py = par[1] + (ty - par[1]) * e, r = 5 + 8 * Math.abs(x.h - 50) / mx;
      s += '<g class="cit" transform="translate(' + px.toFixed(1) + ',' + py.toFixed(1) + ')"><circle class="zf' + zc(x.h) + '" r="' + r.toFixed(1) + '" data-open="item:' + esc(x.k) + '" tabindex="0" role="button" aria-label="' + esc(NM[x.k] + ' ' + n0(x.h)) + '"/>' + (lab.has(x.k) && CS.prog > 0.8 ? '<text x="' + (r + 4).toFixed(1) + '" dy="4">' + esc(NM[x.k]) + '</text>' : '') + '</g>';
    });
  }
  box.innerHTML = '<svg viewBox="0 0 ' + g.W + ' ' + g.H + '" role="img" aria-label="熱度羅盤">' + s + '</svg>';
  const cd = $('#cdate');
  if (cd) cd.textContent = isNow() ? '現在（' + ymd(P.asof) + '）' : ymd(D.w.d[i]) + ' 那一週';
  const cb = $('#cback');
  if (cb) cb.hidden = !CS.drill;
  const csub = $('#csub');
  if (csub) csub.textContent = CS.drill ? NM[CS.drill] + '的項目：位置同一套座標，點越大＝離 50 越遠；點一項打開細節。' : '橫軸＝現在多熱（0～100）；縱軸＝近 4 週升溫（上）或降溫（下）；尾巴＝過去 8 週走過的路。點泡泡展開那個面向的項目。';
  quadPanel(dims, i);
}
function quadPanel(dims, i) {
  const el = $('#cquad');
  if (!el) return;
  let rows = dims.map(d => ({id: d.id, nm: NM[d.id], h: d.h, m: d.m}));
  if (CS.drill) rows = (P.ord[CS.drill] || []).map(k => { const t = D.s[k] && D.s[k].h; return {id: k, nm: NM[k], h: val(t, i), m: mom(t, i)}; }).filter(x => x.h != null && x.m != null);
  const by = [[], [], [], []];
  rows.forEach(r => by[quad(r.h, r.m)].push(r));
  el.innerHTML = '<h3>' + esc(CS.drill ? NM[CS.drill] + '的項目' : '各面向在哪一格') + '</h3><dl>' + QN.map((q, k) => '<dt>' + q + '<i>' + QS[k] + '</i></dt><dd>' + (by[k].length ? by[k].sort((a, b) => b.h - a.h).map(r => '<button type="button" class="nmb" data-k="' + esc(r.id) + '">' + esc(r.nm) + '</button> <span class="zt' + zc(r.h) + '">' + n0(r.h) + '</span>（' + sg(r.m) + '）').join('、') : '—') + '</dd>').join('') + '</dl>'
    + '<p class="note">括號裡＝近 4 週 0～100 的變化。50 以上算「熱」那一半；這只是描述位置與方向，不是訊號。</p>';
}
function drill(id) {
  CS.drill = id; CS.prog = RM ? 1 : 0;
  cancelAnimationFrame(CS.raf);
  if (RM) { cDraw(); return; }
  const t0 = performance.now();
  const fr = t => { CS.prog = Math.min(1, (t - t0) / 420); cDraw(); if (CS.prog < 1) CS.raf = requestAnimationFrame(fr); };
  CS.raf = requestAnimationFrame(fr);
}

// ── 3D 熱度地形（canvas 自己投影，不載入外部套件）：每條山脊一個面向、高出紅色平面＝過熱；拖曳旋轉、點一下跳到雷達
const TS = {yaw: -0.55, pitch: 0.55, rg: 10, flat: false, inited: false, pts: [], drag: null};
function tShow() { if (!D) { withData(tShow); return; } if (!TS.inited) tInit(); tDraw(); }
function tInit() {
  TS.inited = true;
  const cv = $('#tcv'), ld = $('#tld');
  if (ld) ld.hidden = true;
  if (!cv) return;
  cv.tabIndex = 0;
  cv.addEventListener('pointerdown', e => { TS.drag = {x: e.clientX, y: e.clientY, yaw: TS.yaw, pitch: TS.pitch, moved: false}; cv.setPointerCapture(e.pointerId); cv.classList.add('drag'); });
  cv.addEventListener('pointermove', e => {
    if (TS.drag) {
      const dx = e.clientX - TS.drag.x, dy = e.clientY - TS.drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 4) TS.drag.moved = true;
      if (TS.drag.moved && !TS.flat) { TS.yaw = TS.drag.yaw + dx * 0.008; TS.pitch = Math.max(0.12, Math.min(1.25, TS.drag.pitch + dy * 0.006)); tDraw(); }
      return;
    }
    tHover(e);
  });
  cv.addEventListener('pointerup', e => {
    const d = TS.drag; TS.drag = null; cv.classList.remove('drag');
    if (d && !d.moved) { const h = tHit(e); if (h) { setView('radar'); setT(h.i); const r = $('#top'); if (r) r.scrollIntoView({block: 'start'}); } }
  });
  cv.addEventListener('pointerleave', () => { const t = $('#ttip'); if (t) t.hidden = true; });
  cv.addEventListener('keydown', e => {
    const k = e.key;
    if (k === 'ArrowLeft' || k === 'ArrowRight') { TS.yaw += (k === 'ArrowLeft' ? -0.08 : 0.08); tDraw(); e.preventDefault(); }
    if (k === 'ArrowUp' || k === 'ArrowDown') { TS.pitch = Math.max(0.12, Math.min(1.25, TS.pitch + (k === 'ArrowUp' ? 0.06 : -0.06))); tDraw(); e.preventDefault(); }
  });
  $$('[data-tr]').forEach(b => b.addEventListener('click', () => { TS.rg = +b.dataset.tr; $$('[data-tr]').forEach(x => { const on = x === b; x.classList.toggle('on', on); x.setAttribute('aria-pressed', on ? 'true' : 'false'); }); tDraw(); }, SG));
  const fl = $('#tflat');
  if (fl) fl.addEventListener('click', () => { TS.flat = !TS.flat; fl.classList.toggle('on', TS.flat); fl.setAttribute('aria-pressed', TS.flat ? 'true' : 'false'); tDraw(); }, SG);
  const rs = $('#treset');
  if (rs) rs.addEventListener('click', () => { TS.yaw = -0.55; TS.pitch = 0.55; tDraw(); }, SG);
  if (window.matchMedia) matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { if (document.documentElement.dataset.hv === 'terrain') tDraw(); }, SG);
}
function tData() {
  const ds = D.w.d, i1 = ds.length - 1;
  let i0 = iStart();
  if (TS.rg) { const cut = (+ds[i1].slice(0, 4) - TS.rg) + ds[i1].slice(4); const j = ds.findIndex(d => d > cut); i0 = Math.max(i0, j < 0 ? 0 : j); }
  const rows = DIM.map(id => {
    const t = D.s[id] && D.s[id].h, raw = [], sm = [];
    for (let i = i0; i <= i1; i++) raw.push(val(t, i));
    raw.forEach((v, j) => { const xs = raw.slice(Math.max(0, j - 3), j + 1).filter(x => x != null); sm.push(v == null || !xs.length ? null : xs.reduce((a, b) => a + b, 0) / xs.length); });
    const have = raw.filter(x => x != null);
    return {id: id, raw: raw, sm: sm, avg: have.length ? have.reduce((a, b) => a + b, 0) / have.length : 0};
  });
  return {i0: i0, i1: i1, rows: rows};
}
function tColors() { return [0, 1, 2, 3, 4].map(k => css('--c' + k) || '#888'); }
function hexA(c, a) { const m = /^#?([0-9a-f]{6})$/i.exec(c); if (!m) return c; const n = parseInt(m[1], 16); return 'rgba(' + (n >> 16 & 255) + ',' + (n >> 8 & 255) + ',' + (n & 255) + ',' + a + ')'; }
function tDraw() {
  const cv = $('#tcv'), box = $('#ter');
  if (!cv || !box || !D || !box.clientWidth) return;
  const W = box.clientWidth, H = box.clientHeight, dpr = Math.min(2, window.devicePixelRatio || 1);
  cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
  const c = cv.getContext('2d');
  c.setTransform(dpr, 0, 0, dpr, 0, 0);
  c.clearRect(0, 0, W, H);
  const T = tData(), N = T.i1 - T.i0 + 1, COL = tColors(), ink = css('--ink'), mut = css('--mut'), line = css('--line2'), panel = css('--panel');
  const zcol = v => COL[+zc(v)] || COL[2];
  TS.pts = [];
  if (TS.flat) {                                                          // 平面熱圖：列＝面向、欄＝週
    const L = 76, R = 10, top = 18, rh = Math.min(46, (H - top - 30) / T.rows.length), cw = (W - L - R) / N;
    T.rows.forEach((r, k) => {
      const y = top + k * rh;
      c.fillStyle = ink; c.font = '600 13px sans-serif'; c.textBaseline = 'middle'; c.fillText(NM[r.id], 8, y + rh / 2);
      r.raw.forEach((v, j) => { if (v == null) return; c.fillStyle = zcol(v); c.fillRect(L + j * cw, y + 2, Math.ceil(cw + 0.5), rh - 4); });
      TS.pts.push({row: k, y0: y, y1: y + rh, L: L, cw: cw, id: r.id, raw: r.raw});
    });
    tYears(c, T, i => L + (i - T.i0 + 0.5) * cw, top + T.rows.length * rh + 14, mut, W);
    return;
  }
  const rows = T.rows.slice().sort((a, b) => a.avg - b.avg), n = rows.length;   // 前面放比較冷的，擋得比較少
  const XW = 120, YH = 24, ZS = 14, cx0 = XW / 2, cy0 = YH / 2, cz0 = (n - 1) * ZS / 2, DIST = 300;
  const cyw = Math.cos(TS.yaw), syw = Math.sin(TS.yaw), cp = Math.cos(TS.pitch), sp = Math.sin(TS.pitch);
  const raw = (x, y, z) => { const X0 = x - cx0, Y0 = y - cy0, Z0 = z - cz0, x1 = X0 * cyw - Z0 * syw, z1 = X0 * syw + Z0 * cyw, y1 = Y0 * cp + z1 * sp, z2 = z1 * cp - Y0 * sp, f = DIST / (DIST + z2); return [x1 * f, y1 * f, z2]; };   // 鏡頭往下看：越遠越靠近地平線
  const za0 = -ZS / 2, za1 = cz0 * 2 + ZS / 2;                       // 整個場景（含地面與名稱的位置）先投影一次，再縮放到畫面裡
  let mnx = Infinity, mxx = -Infinity, mny = Infinity, mxy = -Infinity;
  [[-14, 0], [XW, 0], [-14, YH], [XW, YH + 4]].forEach(xy => [za0, za1].forEach(z => { const q = raw(xy[0], xy[1], z); mnx = Math.min(mnx, q[0]); mxx = Math.max(mxx, q[0]); mny = Math.min(mny, q[1]); mxy = Math.max(mxy, q[1]); }));
  const pad = W < 520 ? 12 : 26, sc = Math.min((W - 2 * pad) / ((mxx - mnx) || 1), (H - 2 * pad - 14) / ((mxy - mny) || 1));
  const ox = (W - (mxx - mnx) * sc) / 2 - mnx * sc, oy = (H - 14 - (mxy - mny) * sc) / 2 + mxy * sc;
  const pr = (x, y, z) => { const q = raw(x, y, z); return [ox + q[0] * sc, oy - q[1] * sc, q[2]]; };
  const xi = j => j / Math.max(1, N - 1) * XW, yv = v => v / 100 * YH;
  const poly = (pts, fill) => { c.beginPath(); pts.forEach((p, k) => (k ? c.lineTo(p[0], p[1]) : c.moveTo(p[0], p[1]))); c.closePath(); c.fillStyle = fill; c.fill(); };
  poly([pr(0, 0, za0), pr(XW, 0, za0), pr(XW, 0, za1), pr(0, 0, za1)], hexA(panel, 0.55));      // 地面
  c.strokeStyle = line; c.lineWidth = 1;
  for (let j = 1; j < N; j++) if (D.w.d[T.i0 + j].slice(0, 4) !== D.w.d[T.i0 + j - 1].slice(0, 4)) { const a = pr(xi(j), 0, za0), b = pr(xi(j), 0, za1); c.beginPath(); c.moveTo(a[0], a[1]); c.lineTo(b[0], b[1]); c.stroke(); }
  const order = rows.map((r, k) => ({r: r, k: k, z: pr(cx0, cy0, k * ZS)[2]})).sort((a, b) => b.z - a.z);   // 由遠到近
  const farDir = pr(cx0, cy0, ZS)[2] > pr(cx0, cy0, 0)[2] ? 1 : -1;   // 深度往哪邊增加
  const hot = hexA(COL[4], 0.09);
  const plane = (zA, zB) => poly([pr(0, yv(80), zA), pr(XW, yv(80), zA), pr(XW, yv(80), zB), pr(0, yv(80), zB)], hot);
  const labs = [];
  order.forEach((o, q) => {
    const z = o.k * ZS;
    plane(q ? order[q - 1].k * ZS : z + farDir * ZS / 2, z);                      // 這條山脊後面那一段紅色平面
    const sm = o.r.sm, b0 = pr(0, 0, z), b1 = pr(XW, 0, z), dx = b1[0] - b0[0], dy = b1[1] - b0[1], dd = dx * dx + dy * dy || 1;
    const gr = c.createLinearGradient(b0[0], b0[1], b1[0], b1[1]);
    let lastPos = -1;
    for (let t = 0; t < N; t++) {
      if (sm[t] == null) continue;
      const pp = pr(xi(t), 0, z), pos = Math.max(0, Math.min(1, ((pp[0] - b0[0]) * dx + (pp[1] - b0[1]) * dy) / dd));
      if (pos - lastPos < 0.002 && t < N - 1) continue;
      gr.addColorStop(pos, hexA(zcol(sm[t]), 0.92)); lastPos = pos;
    }
    let seg = [];
    const flush = () => { if (seg.length >= 2) { const top = seg.map(t => pr(xi(t), yv(sm[t]), z)), base = seg.map(t => pr(xi(t), 0, z)).reverse(); poly(top.concat(base), gr); } seg = []; };
    for (let t = 0; t < N; t++) { if (sm[t] == null) flush(); else seg.push(t); }
    flush();
    c.beginPath(); let pen = false;
    for (let t = 0; t < N; t++) {
      if (sm[t] == null) { pen = false; continue; }
      const p = pr(xi(t), yv(sm[t]), z);
      if (pen) c.lineTo(p[0], p[1]); else c.moveTo(p[0], p[1]);
      pen = true;
      if (t % 2 === 0 || t === N - 1) TS.pts.push({x: p[0], y: p[1], z: p[2], id: o.r.id, i: T.i0 + t, v: o.r.raw[t]});
    }
    c.strokeStyle = hexA(ink, 0.5); c.lineWidth = 1.1; c.stroke();
    const f = sm.findIndex(v => v != null);
    if (f >= 0) labs.push({p: pr(-1.5, yv(8), z), id: o.r.id});
  });
  const zf = order.length ? order[order.length - 1].k * ZS : 0;
  plane(zf, zf - farDir * ZS / 2);
  c.textBaseline = 'middle';
  labs.forEach(l => {                                                         // 名稱最後畫，不會被山脊擋住
    const sc0 = P.dims.find(d => d.id === l.id).sc, lb = NM[l.id] + ' ' + n0(sc0);
    c.font = '700 12.5px sans-serif'; c.textAlign = 'right';
    const tw = c.measureText(lb).width;
    c.fillStyle = hexA(panel, 0.82); c.fillRect(l.p[0] - tw - 8, l.p[1] - 10, tw + 10, 20);
    c.fillStyle = css('--t' + zc(sc0)) || ink; c.fillText(lb, l.p[0] - 3, l.p[1]);
  });
  const pl = pr(-1.5, yv(80), za0);
  c.font = '600 11.5px sans-serif'; c.textAlign = 'right'; c.fillStyle = css('--t4'); c.fillText('過熱（80）', pl[0] - 4, pl[1]);
  const nw = pr(XW, YH + 3, za1);
  c.textAlign = 'center'; c.fillStyle = css('--acc'); c.fillText('現在', nw[0], nw[1] - 6);
  c.fillStyle = mut; c.font = '11px sans-serif';
  let last = -1e9;
  for (let j = 1; j < N; j++) if (D.w.d[T.i0 + j].slice(0, 4) !== D.w.d[T.i0 + j - 1].slice(0, 4)) { const p = pr(xi(j), 0, za0 - 3); if (Math.abs(p[0] - last) > 34) { c.fillText(D.w.d[T.i0 + j].slice(0, 4), p[0], p[1] + 9); last = p[0]; } }
}
function tYears(c, T, X, y, col, W) {
  c.fillStyle = col; c.font = '11px sans-serif'; c.textAlign = 'center';
  let last = -1e9;
  for (let i = T.i0 + 1; i <= T.i1; i++) if (D.w.d[i].slice(0, 4) !== D.w.d[i - 1].slice(0, 4)) { const x = X(i); if (x - last > 36 && x < W - 10) { c.fillText(D.w.d[i].slice(0, 4), x, y); last = x; } }
}
function tHit(e) {
  const cv = $('#tcv'), r = cv.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
  if (TS.flat) {
    const row = TS.pts.find(p => y >= p.y0 && y < p.y1);
    if (!row) return null;
    const j = Math.floor((x - row.L) / row.cw);
    if (j < 0 || j >= row.raw.length) return null;
    const T0 = iLast() - row.raw.length + 1;
    return {id: row.id, i: T0 + j, v: row.raw[j]};
  }
  let best = null, bd = 16;
  TS.pts.forEach(p => { const d = Math.hypot(p.x - x, p.y - y) + p.z * 0.02; if (d < bd) { bd = d; best = p; } });
  return best;
}
function tHover(e) {
  const t = $('#ttip'), h = tHit(e), box = $('#ter');
  if (!t) return;
  if (!h) { t.hidden = true; return; }
  t.innerHTML = '<b>' + esc(NM[h.id]) + '・' + esc(ymd(D.w.d[h.i])) + '</b><div><strong>' + n0(h.v) + '</strong> ' + esc(h.v == null ? '' : bn(h.v)) + '</div><div class="tpx">' + esc(PXN) + ' ' + fpx(D.w.px[h.i]) + '</div><div class="tpx">點一下看那一週的雷達</div>';
  t.hidden = false;
  const bx = box.getBoundingClientRect(), tw = t.offsetWidth;
  let left = e.clientX - bx.left + 14;
  if (left + tw > bx.width) left = e.clientX - bx.left - tw - 14;
  t.style.left = Math.max(0, left) + 'px';
  t.style.top = Math.max(0, e.clientY - bx.top - 70) + 'px';
}

// ── 事件與啟動
document.addEventListener('click', e => {
  const t = e.target;
  if (!t || !t.closest) return;
  const gv = t.closest('[data-goview]');
  if (gv) { e.preventDefault(); closeD(); setView(gv.dataset.goview, {anchor: gv.dataset.anchor}); return; }
  const vb = t.closest('.vsw [data-view]');
  if (vb) { e.preventDefault(); setView(vb.dataset.view); return; }
  const ov = t.closest('[data-ov]');
  if (ov) { e.preventDefault(); toggleOv(ov.dataset.ov); return; }
  const go = t.closest('[data-go]');
  if (go) { e.preventDefault(); goDate(go.dataset.go); return; }
  const cb = t.closest('[data-cd]');
  if (cb) { e.preventDefault(); drill(cb.dataset.cd); return; }
  if (t.closest('#cback')) { e.preventDefault(); drill(null); return; }
  const op = t.closest('[data-open]');
  if (op) { e.preventDefault(); const p = op.dataset.open.split(':'); openD(p[0], p[1]); return; }
  if (t.closest('#itabb')) { const tb = $('#itab'), im = $('#imap'), b = $('#itabb'), on = tb.hidden; tb.hidden = !on; im.hidden = on; b.classList.toggle('on', on); b.setAttribute('aria-pressed', on ? 'true' : 'false'); if (!on) imapDraw(); }
}, SG);
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && DRW && !DRW.hidden) { closeD(); return; }
  const t = e.target;
  if ((e.key === 'Enter' || e.key === ' ') && t && t.matches && t.matches('.kcard, .rax, .idot, .cbub, .cit circle')) { e.preventDefault(); t.dispatchEvent(new MouseEvent('click', {bubbles: true})); }
}, SG);
['#rtin', '#ctin'].forEach(sel => { const inp = $(sel); if (inp) inp.addEventListener('input', () => { stopPlay(); setT(+inp.value, true); }, SG); });
['#rplay', '#cplay'].forEach(sel => { const b = $(sel); if (b) { b.disabled = true; b.addEventListener('click', () => (RS.play ? stopPlay() : play()), SG); } });
let rt = null, lastW = window.innerWidth;
window.addEventListener('resize', () => {
  clearTimeout(rt);
  rt = setTimeout(() => {
    const v = document.documentElement.dataset.hv || 'radar';
    if (v === 'radar') { radarDraw(); trackDraw(); if (Math.abs(window.innerWidth - lastW) > 30 || !$('#imap svg')) imapDraw(); }
    if (v === 'compass') { cDraw(); trackDraw(); }
    if (v === 'terrain') tDraw();
    if (cur && Math.abs(window.innerWidth - lastW) > 30) $$('.dchart', DC).forEach(el => bigChart(el, el.dataset.k));
    lastW = window.innerWidth;
  }, 160);
}, SG);
chips(); smDraw(); radarDraw(); nowLab();
setView(document.documentElement.dataset.hv || hget('v') || 'radar', {quiet: true});
imapDraw();
if (window.heatGet) window.heatGet().then(d => {
  if (AC.signal.aborted) return;
  D = d;
  hooks.splice(0).forEach(f => { try { f(); } catch (err) { /* 一張圖壞了不影響其他 */ } });
  trackDraw(); nowLab();
  if (cur) $$('.dchart[data-wait]', DC).forEach(el => bigChart(el, el.dataset.k));
}).catch(() => {
  if (AC.signal.aborted) return;
  ['#cps', '#tld'].forEach(sel => { const el = $(sel); if (el) el.innerHTML = '走勢資料載入失敗，重新整理頁面再試一次。'; });
});
};
"""
