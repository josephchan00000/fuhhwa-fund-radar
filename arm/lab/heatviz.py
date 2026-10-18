"""景氣頁的視覺化版面（docs/lab_visual_plan.md 第 5～8 節；2026-10-18 使用者選定：雷達＋關鍵狀態為主畫面，
階段時間軸、3D 地形、研究可以切換，配色跟著系統深淺）。

只改呈現：分數、0～100、研究的算法與規格都不動（heatspec、研究檔照舊）。
  · pack(B, V)：主畫面要的小份資料（每個面向、每一項的現在、上週、4 週前、1 年前，雷達的比較日期與每季小圖），
    嵌在頁面的 <script type="application/json" class="hviz">（美股頁每個指數各一份，跟著內容切換）；
    每週的長序列照舊從 x9mh.json 下載（時間拉桿、階段、3D、面板裡的大張走勢）。
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
# 地形圖每條山脊的身分色（CSS 變數，深淺兩套在 heatpage._CSS）。不用紅、藍（紅＝過熱、藍＝過冷）；
# 依山脊由後到前的順序，相鄰兩條在色弱模擬下也分得開（2026-10-18 用 dataviz 驗色工具檢查，數字見 docs/lab_visual_plan.md 第 9 節）
DCOL = {"fund": "dfund", "chip": "dchip", "sent": "dchip", "gliq": "dgliq", "liq": "dgliq", "tliq": "dtliq", "tech": "dtech", "bubl": "dbubl"}
VIEWS = (("radar", "雷達"), ("phase", "階段"), ("terrain", "地形 3D"), ("research", "研究"))
# 階段時間軸（2026-10-18 取代羅盤，docs/lab_visual_plan.md 第 11 節）：8 週平均熱度、近 13 週變化；跨過 50 要多 hl 分、
# 變化要超過 hm 分才換階段（不然沿用原本的），一個階段通常維持 2～6 個月。只描述位置，升溫降溫沒有驗證過能預測漲跌
PH = {"ma": 8, "chg": 13, "hl": 5, "hm": 3}
PHN = ("熱、還在升溫", "熱、開始降溫", "冷、還在降溫", "冷、開始回溫")
PHS = ("最熱的階段", "高檔轉弱", "低檔轉弱", "低檔轉強")
PH_ORDER = (3, 0, 1, 2)       # 圖例順序＝常見的順序（冷回溫 → 熱升溫 → 熱降溫 → 冷降溫）
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
    eps_all = episodes(cal[a0:], px[a0:])
    eps = eps_all[-N_EPI:]
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
                      "ago": _r1(L["ago"]), "st": HP.strip_text(st) if st else "", "col": DCOL[d]})
    items = []
    for d, L in V["dims"].items():
        for it in L["items"]:
            items.append({"k": it["k"], "dim": d, "name": it["name"], "h": _r1(it["heat"]), "ago": _r1(it["ago"]),
                          "pull": _r1(it["pull"]), "px": bool(it["proxy"]), "val": it["val"]})
    ordr = {d: [it["k"] for it in _item_order(L)] for d, L in V["dims"].items()}
    return {"asof": cal[t], "start": wd[j0], "dims": out_d, "items": items, "ord": ordr, "pre": pre, "qs": qs,
            "mkt": HP.MK["mkt"].strip(), "px": HP.MK["px"].strip(), "t0": cal[t0],
            "ph": {**PH, "n": list(PHN), "s": list(PHS)},
            "eps": [{"p": e["peak"], "t": e["trough"], "dd": _r1(100 * e["dd"]), "o": e["open"]} for e in eps_all]}


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


def phase_track(x: list) -> tuple[list, list, list]:
    """每週分數 → （8 週平均、近 13 週變化、階段 0～3 或 None）。和頁面 JS phTrack() 同一套（tests/test_heatviz.py 逐週比對）。"""
    w, c, hl, hm = PH["ma"], PH["chg"], PH["hl"], PH["hm"]
    n = len(x)
    L = [None] * n
    for i in range(w - 1, n):
        seg = x[i - w + 1:i + 1]
        if all(v is not None for v in seg):
            t = 0
            for v in seg:                                     # 由左往右加，和 JS 同一個順序（浮點數結果才會一樣）
                t += v
            L[i] = t / w
    M = [L[i] - L[i - c] if i >= c and L[i] is not None and L[i - c] is not None else None for i in range(n)]
    P, prev = [], None
    for lv, m in zip(L, M):
        if lv is None or m is None:
            P.append(None)
            prev = None
            continue
        if prev is None:
            hot, up = lv >= 50, m >= 0
        else:
            hot = prev[0] if abs(lv - 50) < hl else lv >= 50
            up = prev[1] if abs(m) < hm else m >= 0
        prev = (hot, up)
        P.append((0 if up else 1) if hot else (3 if up else 2))
    return L, M, P


def phase_view() -> str:
    px = _e(HP.MK["px"].strip())
    rg = "".join(f'<button type="button" class="tb" data-phr="{y}" aria-pressed="false">{nm}</button>'
                 for y, nm in ((2, "2 年"), (5, "5 年"), (10, "10 年"), (0, "全部")))
    lg = "".join(f'<span><i class="pq{q}"></i>{PHN[q]}<em>{PHS[q]}</em></span>' for q in PH_ORDER)
    return ('<div class="hview" data-view="phase" hidden><section class="sec"><div class="card phcard">'
            '<div class="khd"><h2>階段時間軸</h2><span class="kn" id="phdate"></span></div>'
            '<p class="phlead" id="phlead"></p>'
            f'<p class="ksub">每一條是一個面向，顏色＝那一週在哪個階段：看 8 週平均熱度（50 以上算熱）和近 {PH["chg"]} 週的變化（升溫或降溫）；'
            f'跨過 50 要多 {PH["hl"]} 分、變化要超過 {PH["hm"]} 分才算換階段，所以一個階段通常維持 2～6 個月。'
            '只描述位置，升溫、降溫沒有驗證過能預測漲跌。</p>'
            f'<div class="seg phrg" role="group" aria-label="期間">{rg}</div>'
            '<div class="phw" id="phw"><div class="phx" id="phx"><p class="note">走勢載入中…</p></div><div class="tip" id="phtip" hidden></div></div>'
            f'<div class="plg">{lg}</div>'
            f'<p class="note">上面是{px}，灰底＝從高點跌 20% 以上的期間（每天收盤，和雷達、地形同一套）。滑過看那一週各面向的階段；點一下到雷達看那一週。</p>'
            '</div></section></div>')


def terrain_view() -> str:
    px = _e(HP.MK["px"].strip())
    chips = ('<button type="button" class="rch on" data-tf="" aria-pressed="true">全部</button>'
             + "".join(f'<button type="button" class="rch" data-tf="{d}" aria-pressed="false"><i class="tfd" style="background:var(--{DCOL[d]})"></i>'
                       f'{_e(S.DSHORT[d])}</button>' for d in S.DIMS))
    return ('<div class="hview" data-view="terrain" hidden><section class="sec"><div class="tcard card">'
            '<div class="khd"><h2>熱度地形</h2><span class="kn">每條山脊是一個面向，越高越熱，最右邊是現在</span></div>'
            '<div class="seg tctl"><button type="button" class="tb on" data-tr="10" aria-pressed="true">近 10 年</button>'
            '<button type="button" class="tb" data-tr="0" aria-pressed="false">全部</button>'
            '<button type="button" class="tb" id="tflat" aria-pressed="false">平面</button>'
            '<button type="button" class="tb" id="treset">轉回原角度</button></div>'
            f'<div class="rchips tfoc" id="tfoc" role="group" aria-label="只看一條">{chips}</div>'
            '<div class="ter" id="ter"><canvas id="tcv" aria-label="熱度地形" role="img"></canvas><div class="tip" id="ttip" hidden></div>'
            '<p class="note tld" id="tld">走勢載入中…</p></div>'
            '<div class="tlg" data-m="3d"><span><i class="tlh"></i>紅色山頂＝過熱（80 以上）</span><span><i class="tlc"></i>藍色谷底＝過冷（20 以下）</span>'
            f'<span><i class="tld2"></i>灰色地面＝{px}從高點跌 20% 以上的期間</span><span><i class="tlx"></i>最前面一排＝同一週有幾個面向過熱</span></div>'
            '<div class="tlg" data-m="flat" hidden>' + "".join(f'<span><i class="tlz{k}"></i>{nm}</span>' for k, (_, _, nm) in enumerate(S.BANDS))
            + f'<span><i class="tld2"></i>灰底＝{px}從高點跌 20% 以上的期間</span><span><i class="tlx"></i>最下面一列＝同一週有幾個面向過熱</span></div>'
            '<p class="note">每條山脊一個顏色；點上面的按鈕或右側的名字，只看那一條。山脊是近 4 週平均（全部期間用 8 週）；分數是現在的，滑過圖會換成那一週；點山脊跳到雷達看那一週。3D 可以拖曳旋轉。</p>'
            '</div></section></div>')


# 研究畫面＝證據地圖（2026-10-18 使用者選 B，docs/lab_visual_plan.md 第 11 節）：每個面向一張卡，每一項一列，
# 點＝和之後漲跌的等級相關、橫線＝95% 信賴區間、顏色＝判定；原本的表格與方法收在下面（內容不刪）
EV_LO, EV_HI = -0.8, 0.8
EV_TICKS = (-0.6, -0.3, 0.0, 0.3, 0.6)
EV_STABLE = ("weak", "strong")


def _epos(v: float) -> float:
    return round(100 * (min(EV_HI, max(EV_LO, v)) - EV_LO) / (EV_HI - EV_LO), 2)


def _rho(x) -> str:
    return "—" if x is None else HP._sgn(x, 2)


def _etrack(e: dict | None, cls: str) -> str:
    if not e or e.get("rho") is None:
        return f'<span class="etk {cls} ev-x"><em>—</em></span>'
    vd = e.get("verdict") or "none"
    ci = ""
    if e.get("lo") is not None and e.get("hi") is not None:
        a, b = _epos(e["lo"]), _epos(e["hi"])
        ci = f'<i class="eci" style="left:{a}%;width:{max(0.6, b - a):.2f}%"></i>'
    return f'<span class="etk {cls} ev-{vd}">{ci}<i class="edot" style="left:{_epos(e["rho"])}%"></i></span>'


def _ehs(e: dict | None, h: int) -> str:
    if not e or not e.get("verdict"):
        return f"之後 {h} 個交易日：沒有結果"
    ci = f"（95% 區間 {_rho(e.get('lo'))}～{_rho(e.get('hi'))}）" if e.get("lo") is not None else ""
    return f"之後 {h} 個交易日：{S.VERDICT.get(e['verdict'], e['verdict'])}，相關 {_rho(e.get('rho'))}{ci}"


def _erow(kind: str, k: str, name: str, ev: dict, hs: tuple, now) -> str:
    es, el = ev.get(str(hs[0])), ev.get(str(hs[1]))
    st = lambda e: "1" if e and e.get("verdict") in EV_STABLE else "0"            # noqa: E731
    vc = lambda e: (e or {}).get("verdict") or "x"                                # noqa: E731
    lab = f"{name}。{_ehs(es, hs[0])}；{_ehs(el, hs[1])}。現在 {HP.n0(now) if now is not None else '沒有分數'}"
    return (f'<button type="button" class="erow{" ecomp" if kind == "dim" else ""}" data-open="{kind}:{_e(k)}" data-ss="{st(es)}" data-sl="{st(el)}"'
            f' title="{_e(lab)}" aria-label="{_e(lab)}：點開看細節"><span class="en">{_e(name)}</span>'
            f'{_etrack(es, "eh-s")}{_etrack(el, "eh-l")}'
            f'<span class="er eh-s ev-{vc(es)}">{_rho((es or {}).get("rho"))}</span><span class="er eh-l ev-{vc(el)}">{_rho((el or {}).get("rho"))}</span>'
            f'<span class="enow zt{_zc(now)}">{HP.n0(now) if now is not None else "—"}</span></button>')


def _ecard(d: str, L: dict) -> str:
    hs = tuple(L["fwd"])
    rows = [_erow("dim", d, f"{S.DSHORT[d]}（面向分數）", L.get("cev") or {}, hs, L["score"])]
    rows += [_erow("item", it["k"], it["name"], it.get("ev") or {}, hs, it["heat"]) for it in L["items"]]
    ax = "".join(f'<b style="left:{_epos(v)}%">{"0" if v == 0 else HP._sgn(v, 1)}</b>' for v in EV_TICKS)
    return (f'<div class="card ecard" id="e-{d}" data-dim="{d}"><div class="ehd"><h3>{_e(S.DSHORT[d])}</h3>'
            f'<span class="kn"><span class="eh-s">看之後 {hs[0]} 個交易日</span><span class="eh-l">看之後 {hs[1]} 個交易日</span></span></div>'
            f'<div class="ehead" aria-hidden="true"><span>項目</span><span class="eaxis">{ax}</span><span class="er">相關</span><span class="enow">現在</span></div>'
            + "".join(rows) + '<p class="note enone" hidden>這個期間沒有穩定的項目。</p></div>')


def evidence_summary(V: dict) -> list[str]:
    """研究重點（全部由研究檔的判定算出，不寫死數字）。"""
    Ds = V["dims"]
    n_items = sum(len(L["items"]) for L in Ds.values())
    cnt = {"weak": 0, "strong": 0, "none": 0, "few": 0}
    for L in Ds.values():
        for it in L["items"]:
            for e in (it.get("ev") or {}).values():
                if e and e.get("verdict") in cnt:
                    cnt[e["verdict"]] += 1
    tot = sum(cnt.values())
    out = [f"{n_items} 項，每項看兩個期間，共 {tot} 個檢驗：<b>{cnt['weak'] + cnt['strong']} 個有穩定關係</b>"
           f"（{cnt['weak']} 個熱了之後較弱、{cnt['strong']} 個較強），其餘看不出或樣本不足。"]
    good, bad = [], []
    for d, L in Ds.items():
        st = [(h, (L.get("cev") or {}).get(str(h)) or {}) for h in L["fwd"]]
        st = [(h, e) for h, e in st if e.get("verdict") in EV_STABLE]
        (good if st else bad).append((d, L, st))
    if good:
        g = []
        for d, L, st in good:
            ws = {e["verdict"] for _, e in st}
            word = "較弱" if ws == {"weak"} else ("較強" if ws == {"strong"} else "方向不一")
            best = max(st, key=lambda he: abs(he[1].get("rho") or 0))
            g.append(f"<b>{_e(S.DSHORT[d])}</b>（熱了之後 {'、'.join(str(h) for h, _ in st)} 日{word}，相關 {_rho(best[1].get('rho'))}）")
        out.append("面向分數本身有穩定關係的：" + "、".join(g) + "。")
        now = [f"{_e(S.DSHORT[d])} {HP.n0(L['score'])}（{_e(L['band'])}）" for d, L, _ in good if L["score"] is not None]
        if now:
            out.append("現在" + "、".join(now) + "。")
    if bad:
        out.append("、".join(_e(S.DSHORT[d]) for d, _, _ in bad) + "的面向分數本身看不出穩定關係（個別項目可能有，看下面紅、藍點）。")
    extra = []
    pr = (V.get("m6") or {}).get("primary") or {}
    if pr:
        npass = sum(1 for x in pr.values() if x.get("pass"))
        extra.append(f"加速減速：{len(pr)} 個主要假說{f'有 {npass} 個通過' if npass else '都沒有通過'}")
    ta = (V.get("ta") or {}).get("study") or {}
    if ta:
        nst = sum(1 for hv in ta.values() if any((e or {}).get("verdict") in EV_STABLE for e in hv.values()))
        extra.append(f"均線、型態事件：{len(ta)} 種{f'有 {nst} 種有穩定差別' if nst else '都看不出穩定差別'}")
    if extra:
        out.append("；".join(extra) + "（細節在最下面「完整數字與方法」）。")
    return out


def evidence_html(V: dict) -> str:
    Ds = V["dims"]
    n = {"s": [0, 0], "l": [0, 0]}
    for L in Ds.values():
        hs = tuple(L["fwd"])
        evs = [L.get("cev") or {}] + [it.get("ev") or {} for it in L["items"]]
        for key, h in (("s", hs[0]), ("l", hs[1])):
            for ev in evs:
                n[key][0] += 1
                n[key][1] += int(((ev.get(str(h)) or {}).get("verdict")) in EV_STABLE)
    chips = (f'<button type="button" class="rch on" data-ef="all" aria-pressed="true">全部<em data-cs="{n["s"][0]}" data-cl="{n["l"][0]}">{n["l"][0]}</em></button>'
             f'<button type="button" class="rch" data-ef="st" aria-pressed="false">只看穩定的<em data-cs="{n["s"][1]}" data-cl="{n["l"][1]}">{n["l"][1]}</em></button>'
             + "".join(f'<button type="button" class="rch" data-ed="{d}" aria-pressed="false">{_e(S.DSHORT[d])}</button>' for d in Ds))
    lg = ('<div class="elg"><span><i class="ev-weak"></i>熱了之後較弱（穩定）</span><span><i class="ev-strong"></i>熱了之後較強（穩定）</span>'
          '<span><i class="ev-none"></i>看不出穩定關係</span><span><i class="ev-few"></i>樣本不足</span>'
          '<span>點＝等級相關、橫線＝95% 信賴區間；在 0 左邊＝熱了之後較弱；「現在」＝今天的 0～100</span></div>')
    summ = "".join(f"<li>{x}</li>" for x in evidence_summary(V))
    return (f'<section class="sec emap" id="emap" data-h="l"><div class="card esum"><h2>研究重點</h2><ul>{summ}</ul></div>'
            '<div class="ectl"><div class="seg" role="group" aria-label="看多久之後">'
            '<button type="button" class="tb" data-eh="s" aria-pressed="false">短期</button><button type="button" class="tb on" data-eh="l" aria-pressed="true">長期</button></div>'
            f'<div class="rchips" role="group" aria-label="篩選">{chips}</div></div>{lg}'
            '<p class="note">短期、長期是每個面向自己的兩個期間（卡片上寫幾日）；穩定＝全期間 95% 信賴區間不含 0，而且前後兩半方向一樣。點一列，右邊打開那一項的細節。</p>'
            f'<div class="egrid">{"".join(_ecard(d, L) for d, L in Ds.items())}</div></section>')


def research_view(V: dict, body: str) -> str:
    nav = ('<nav class="snav"><button type="button" class="snv" data-goview="radar">← 回到雷達</button>'
           '<a href="#emap" data-jump="emap">證據地圖</a><a href="#more" data-jump="more">完整數字與方法</a></nav>')
    more = ('<details class="card emore" id="more"><summary><b>完整數字與方法</b><span class="kn">原本的表格：邊際變化、各面向各區之後的表現、'
            '各項和指數的關係、多層回歸、泡沫事件、事件研究、資料來源</span></summary>' + body + '</details>')
    return f'<div class="hview" data-view="research" hidden>{nav}{evidence_html(V)}{more}</div>'


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
           f'<button type="button" class="tb" data-goview="research" data-anchor="e-{_e(d)}">研究的證據地圖 →</button></p>')
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
.phcard{padding:12px 14px;min-width:0}.phlead{font-size:14.5px;line-height:1.75;margin:6px 0 2px}.phlead b{font-weight:700}
.phrg{margin:4px 0 6px}.phw{position:relative}.phx{min-height:160px}.phx svg{display:block;width:100%;height:auto}
.phg{stroke:var(--line);stroke-width:1}.pht{font-size:10.5px;fill:var(--mut)}.phpx{fill:none;stroke:var(--ink2);stroke-width:1.5;stroke-linejoin:round}
.phdd{fill:var(--line2);opacity:.55}.phddl{font-size:10.5px;fill:var(--mut);text-anchor:middle}.phbg{fill:var(--card2)}
.phn{font-size:12.5px;font-weight:700;fill:var(--ink)}.phs{font-size:12px;font-weight:700;fill:var(--ink)}.phw2{font-size:12px;fill:var(--ink2);font-weight:400}
.phgd{stroke:var(--ink);stroke-width:1.2;pointer-events:none}.phhit{fill:transparent;cursor:pointer}
.pq0{fill:var(--q0);background:var(--q0)}.pq1{fill:var(--q1);background:var(--q1)}.pq2{fill:var(--q2);background:var(--q2)}.pq3{fill:var(--q3);background:var(--q3)}
.plg{display:flex;flex-wrap:wrap;gap:4px 16px;margin:8px 2px 0;font-size:12.5px;color:var(--ink2)}.plg span{display:inline-flex;align-items:center;gap:6px}
.plg i{display:inline-block;width:12px;height:12px;border-radius:3px}.plg em{font-style:normal;color:var(--mut);margin-left:2px}
#phtip{min-width:180px}#phtip div{gap:8px}#phtip .phq{display:inline-block;width:10px;height:10px;border-radius:3px;flex:none}#phtip .tgo{display:block;margin-top:3px;font-weight:600}
.ter{position:relative;height:min(64vh,600px);min-height:360px;background:var(--card2);border-radius:12px;overflow:hidden}
.ter canvas{position:absolute;inset:0;width:100%;height:100%;cursor:grab;touch-action:pan-y}.ter canvas.drag{cursor:grabbing}
.tld{position:absolute;left:14px;top:10px;margin:0}.tctl{margin:6px 0 8px}
.ter .tip{min-width:0;white-space:nowrap}.ter .tip .tgo{display:block;margin-top:3px;font-weight:600}
.tlg{display:flex;flex-wrap:wrap;gap:4px 16px;margin:8px 2px 0;font-size:12.5px;color:var(--ink2)}
.tlg i{display:inline-block;width:14px;height:10px;border-radius:2px;margin-right:6px;vertical-align:-1px}
.tlg .tlh{background:var(--c4)}.tlg .tlc{background:var(--c0)}.tlg .tld2{background:var(--line2)}
.tlg .tlx{background:linear-gradient(90deg,var(--zh),var(--c4))}
.rch .tfd{width:10px;height:10px;border:0;border-radius:50%;flex:none}.tfoc{margin:0 0 8px}
.tlg .tlz0{background:var(--c0)}.tlg .tlz1{background:var(--c1)}.tlg .tlz2{background:var(--c2)}.tlg .tlz3{background:var(--c3)}.tlg .tlz4{background:var(--c4)}
.esum{padding:12px 16px}.esum h2{font-size:16px;margin:0 0 4px}.esum ul{margin:4px 0 2px;padding-left:20px;font-size:14px;line-height:1.85}.esum b{font-weight:700}
.ectl{display:flex;flex-wrap:wrap;align-items:center;gap:8px 14px;margin:12px 0 4px}.ectl .rchips{margin:0}.rch em{margin-left:4px}
.elg{display:flex;flex-wrap:wrap;align-items:center;gap:4px 14px;font-size:12px;color:var(--ink2);margin:4px 0 2px}.elg span{display:inline-flex;align-items:center;gap:6px}
.elg i{display:inline-block;width:10px;height:10px;border-radius:50%;box-sizing:border-box;border:1.6px solid var(--mut);background:var(--panel)}
.elg i.ev-weak{background:var(--c4);border-color:var(--c4)}.elg i.ev-strong{background:var(--c0);border-color:var(--c0)}.elg i.ev-few{border-style:dashed}
.egrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:8px}
.ecard{padding:10px 12px;min-width:0;scroll-margin-top:56px}.ehd{display:flex;align-items:baseline;gap:8px;margin:0 0 2px}.ehd h3{margin:0;font-size:15px}
.erow,.ehead{display:grid;grid-template-columns:minmax(0,10em) minmax(0,1fr) 3.3em 2.4em;gap:8px;align-items:center}
.ehead{padding:2px 4px 3px;font-size:10.5px;color:var(--mut)}.ehead .er,.ehead .enow{font-weight:400;color:var(--mut)}
.erow{width:100%;border:0;border-top:1px solid var(--line);background:none;padding:5px 4px;font:inherit;color:inherit;text-align:left;cursor:pointer;border-radius:6px}
.erow:hover{background:var(--card2)}.erow:focus-visible{outline:2px solid var(--acc);outline-offset:1px}.erow.ecomp .en{font-weight:700}
.en{font-size:13px;line-height:1.35;overflow-wrap:anywhere}
.etk,.eaxis{position:relative;height:16px}
.etk{background:linear-gradient(var(--line),var(--line)) 12.5% 0/1px 100% no-repeat,linear-gradient(var(--line),var(--line)) 31.25% 0/1px 100% no-repeat,linear-gradient(var(--ink2),var(--ink2)) 50% 0/1px 100% no-repeat,linear-gradient(var(--line),var(--line)) 68.75% 0/1px 100% no-repeat,linear-gradient(var(--line),var(--line)) 87.5% 0/1px 100% no-repeat}
.etk em{position:absolute;left:50%;top:0;transform:translateX(-50%);font-style:normal;font-size:11px;color:var(--mut);background:var(--panel);padding:0 3px;line-height:16px}
.eaxis b{position:absolute;top:1px;transform:translateX(-50%);font-weight:400;white-space:nowrap}
.eci{position:absolute;top:7px;height:2px;border-radius:1px;background:var(--bp)}
.edot{position:absolute;top:3px;width:10px;height:10px;margin-left:-5px;border-radius:50%;box-sizing:border-box;background:var(--panel);border:1.6px solid var(--mut)}
.etk.ev-weak .eci{background:var(--c4);height:3px;top:6.5px}.etk.ev-weak .edot{background:var(--c4);border-color:var(--ring)}
.etk.ev-strong .eci{background:var(--c0);height:3px;top:6.5px}.etk.ev-strong .edot{background:var(--c0);border-color:var(--ring)}
.etk.ev-few .edot{border-style:dashed}
.er{font-size:12px;text-align:right;color:var(--ink2);font-variant-numeric:tabular-nums}.er.ev-weak{color:var(--t4);font-weight:700}.er.ev-strong{color:var(--t0);font-weight:700}
.enow{font-size:12.5px;font-weight:700;text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.emap[data-h="s"] .eh-l,.emap[data-h="l"] .eh-s{display:none}
.emore{margin-top:18px;padding:10px 14px}.emore>summary{cursor:pointer;font-size:14px;line-height:1.7}.emore>summary .kn{display:block}
.emore[open]>summary{margin-bottom:8px}
@media (max-width:900px){.egrid{grid-template-columns:1fr}}
@media (max-width:640px){.erow,.ehead{grid-template-columns:minmax(0,8.6em) minmax(0,1fr) 2.6em;gap:6px}.er{display:none}.ehead .er{display:none}}
@media (max-width:820px){.vgrid{grid-template-columns:1fr}.vbar{gap:6px 10px}}
@media (max-width:640px){
 .vsw button{padding:5px 9px;font-size:13px}.rsm{grid-template-columns:repeat(4,minmax(0,1fr));gap:4px}.rsm .pxn{display:none}
 .rchips{flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none;margin:2px -16px 4px;padding:0 16px}.rchips::-webkit-scrollbar{display:none}.rch{flex:none}
 .rnow{min-width:4.8em;font-size:12.5px}.dnum b{font-size:17px}.drw{width:100vw;border-left:0}
 .ter{height:58vh;min-height:320px}
}
body.drw-on{overflow:hidden}
@media (min-width:1100px){body.drw-on{overflow:auto}}
@media (prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
"""


# ── 瀏覽器端（雷達、項目分布、右側面板、階段時間軸、3D 地形、視角切換）。資料：頁面裡的 script.hviz（小份）＋ x9mh.json
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

// ── 視角切換（雷達｜階段｜地形 3D｜研究）：網址記在 #v=…（美股頁另有 #ix=…，兩個並存）；舊網址 #v=compass 轉到階段
const VIEWS = ['radar', 'phase', 'terrain', 'research'];
function hget(k) { const m = new RegExp('(?:^#|&)' + k + '=([\\w-]+)').exec(location.hash || ''); return m ? m[1] : null; }
function hset(k, v) {
  const ps = (location.hash || '').replace(/^#/, '').split('&').filter(x => x && x.split('=')[0] !== k);
  if (v) ps.push(k + '=' + v);
  try { history.replaceState(history.state, '', ps.length ? '#' + ps.join('&') : location.pathname + location.search); } catch (e) { /* file:// */ }
}
function setView(v, o) {
  o = o || {};
  if (v === 'compass') v = 'phase';
  if (VIEWS.indexOf(v) < 0) v = 'radar';
  document.documentElement.dataset.hv = v;
  $$('.hview').forEach(el => { el.hidden = el.dataset.view !== v; });
  document.querySelectorAll('.vsw [data-view]').forEach(b => { const on = b.dataset.view === v; b.classList.toggle('on', on); b.setAttribute('aria-pressed', on ? 'true' : 'false'); });
  if (!o.quiet) hset('v', v === 'radar' ? null : v);
  if (v !== 'radar') stopPlay();
  if (v === 'phase') phShow();
  if (v === 'terrain') tShow();
  if (v === 'research') eApply();
  if (v === 'radar') { radarDraw(); trackDraw(); imapDraw(); window.dispatchEvent(new Event('resize')); }
  if (o.anchor) jump(o.anchor);
  else if (!o.quiet) window.scrollTo(0, 0);
}
window.heatView = (v, a) => setView(v, {anchor: a});
function jump(id) {                                                  // 目標在收起來的段落裡：先打開再捲過去
  const a = document.getElementById(id);
  if (!a) return;
  for (let d = a.closest('details'); d; d = d.parentElement && d.parentElement.closest('details')) d.open = true;
  if (a.tagName === 'DETAILS') a.open = true;
  setTimeout(() => a.scrollIntoView({block: 'start'}), 0);
}

// ── 研究畫面：證據地圖（短期／長期、全部／只看穩定的、各面向）
const ES = {h: 'l', f: 'all', d: null};
function eApply() {
  const box = $('#emap');
  if (!box) return;
  box.dataset.h = ES.h;
  $$('.ecard', box).forEach(c => {
    const okd = !ES.d || c.dataset.dim === ES.d;
    let n = 0;
    $$('.erow', c).forEach(r => { const v = okd && (ES.f === 'all' || r.dataset[ES.h === 's' ? 'ss' : 'sl'] === '1'); r.hidden = !v; if (v) n++; });
    c.hidden = !okd;
    const nn = $('.enone', c); if (nn) nn.hidden = n > 0;
  });
  const set = (sel, on) => $$(sel, box).forEach(b => { const o = on(b); b.classList.toggle('on', o); b.setAttribute('aria-pressed', o ? 'true' : 'false'); });
  set('[data-eh]', b => b.dataset.eh === ES.h);
  set('[data-ef]', b => b.dataset.ef === ES.f);
  set('[data-ed]', b => b.dataset.ed === ES.d);
  $$('[data-cs]', box).forEach(el => { el.textContent = ES.h === 's' ? el.dataset.cs : el.dataset.cl; });
}

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

// ── 雷達：時間（RS.i＝x9mh.json 的第幾週；null＝現在）
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
  const rin = $('#rtin'); if (rin && +rin.value !== i) rin.value = i;
  nowLab();
  smMark();
  cancelAnimationFrame(RS.raf);
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
  const rn = $('#rnow'); if (rn) rn.innerHTML = h;
  const rd = $('#rdate');
  if (rd) rd.textContent = isNow() ? '現在（' + ymd(P.asof) + '）' : ymd(d) + ' 那一週';
}
function trackDraw() {
  [['#rtsvg', '#rtin']].forEach(p => {
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
  const rpb = $('#rplay'); if (rpb) rpb.disabled = !D;
}
function play() {
  if (!D) return;
  const last = iLast();
  if (RM) { setT(last, true); return; }
  let i = isNow() ? Math.max(iStart(), last - 104) : RS.i;
  setT(i, true);
  const pb = $('#rplay'); if (pb) { pb.textContent = '❚❚'; pb.setAttribute('aria-label', '暫停'); }
  RS.play = setInterval(() => { i += 1; setT(i, true); if (i >= last) stopPlay(); }, 90);
}
function stopPlay() {
  if (!RS.play) return;
  clearInterval(RS.play); RS.play = 0;
  const pb = $('#rplay'); if (pb) { pb.textContent = '▶'; pb.setAttribute('aria-label', '播放近兩年'); }
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

// ── 階段時間軸（取代羅盤）：每個面向一條色帶，顏色＝那一週的階段（8 週平均熱度 × 近 13 週變化，含門檻；和 Python phase_track() 同一套）
const PHC = P.ph || {ma: 8, chg: 13, hl: 5, hm: 3, n: [], s: []};
const PS = {tr: null, rg: null, g: null, pin: null};
// @@PH 下面兩支用 node 和 Python phase_track() 逐週比對（tests/test_heatviz.py），只用 PHC 與 val
function phTrack(t, n) {
  const w = PHC.ma, c = PHC.chg, L = new Array(n).fill(null), M = new Array(n).fill(null), Q = new Array(n).fill(null);
  for (let i = w - 1; i < n; i++) {
    let s = 0, ok = true;
    for (let k = i - w + 1; k <= i; k++) { const v = val(t, k); if (v == null) { ok = false; break; } s += v; }
    if (ok) L[i] = s / w;
  }
  for (let i = c; i < n; i++) if (L[i] != null && L[i - c] != null) M[i] = L[i] - L[i - c];
  let prev = null;
  for (let i = 0; i < n; i++) {
    const l = L[i], m = M[i];
    if (l == null || m == null) { prev = null; continue; }
    const hot = prev && Math.abs(l - 50) < PHC.hl ? prev[0] : l >= 50;
    const up = prev && Math.abs(m) < PHC.hm ? prev[1] : m >= 0;
    prev = [hot, up];
    Q[i] = hot ? (up ? 0 : 1) : (up ? 3 : 2);
  }
  return {L: L, M: M, Q: Q};
}
function phSince(Q, i) { let j = i; while (j > 0 && Q[j - 1] === Q[i]) j--; return j; }
// @@ENDPH
function phShow() {
  if (!D) { const b = $('#phx'); if (b) b.innerHTML = '<p class="note">走勢載入中…</p>'; withData(phShow); return; }
  if (!PS.tr) { const n = D.w.d.length; PS.tr = {}; DIM.forEach(id => { PS.tr[id] = phTrack(D.s[id] && D.s[id].h, n); }); }
  phDraw();
}
function phLead() {
  const i = D.w.d.length - 1, by = [[], [], [], []];
  DIM.forEach(id => { const q = PS.tr[id].Q[i]; if (q != null) by[q].push(id); });
  const parts = [0, 1, 2, 3].filter(q => by[q].length).map(q => '<b>' + by[q].map(id => esc(NM[id])).join('、') + '</b>在「' + esc(PHC.n[q]) + '」');
  const el = $('#phlead');
  if (el) el.innerHTML = parts.length ? '現在：' + parts.join('；') + '。' : '';
  const dt = $('#phdate');
  if (dt) dt.textContent = '資料到 ' + ymd(D.w.d[i]) + '（每週一格）';
}
function phDraw() {
  const box = $('#phx');
  if (!box || !D || !PS.tr || !box.clientWidth) return;
  const W = Math.round(box.clientWidth), mob = W < 560, ds = D.w.d, i1 = ds.length - 1;
  let first = i1;                                                // 「全部」和地形一樣從雷達的起點開始（大跌期間也從那裡算）
  DIM.forEach(id => { const j = PS.tr[id].Q.findIndex(q => q != null); if (j >= 0 && j < first) first = j; });
  first = Math.max(first, iStart());
  const rg = PS.rg == null ? (mob ? 2 : 5) : PS.rg;
  let i0 = first;
  if (rg) { const cut = (+ds[i1].slice(0, 4) - rg) + ds[i1].slice(4), j = ds.findIndex(d => d > cut); i0 = Math.max(first, j < 0 ? 0 : j); }
  $$('[data-phr]').forEach(b => { const on = +b.dataset.phr === rg; b.classList.toggle('on', on); b.setAttribute('aria-pressed', on ? 'true' : 'false'); });
  const lw = mob ? 0 : 76, rw = mob ? 0 : 168, top = mob ? 92 : 124, rh = mob ? 14 : 22, gap = mob ? 8 : 9, cap = mob ? 17 : 0;
  const x0 = lw + 4, x1 = W - rw - 4, N = i1 - i0 + 1, cw = (x1 - x0) / N, X = i => x0 + (i - i0) * cw;
  let lo = Infinity, hi = -Infinity;
  for (let i = i0; i <= i1; i++) { const v = D.w.px[i]; if (v > 0) { lo = Math.min(lo, Math.log(v)); hi = Math.max(hi, Math.log(v)); } }
  const yt = 18, yb = top - 22, Yp = v => yt + (yb - yt) * (1 - (Math.log(v) - lo) / ((hi - lo) || 1));
  const H = top + DIM.length * (rh + gap + cap) + 2;
  let s = '', lastL = -1e9;
  (P.eps || []).forEach(e => {
    const a = wkIdx(e.p), b = wkIdx(e.t);
    if (b < i0 || a > i1) return;
    const xa = X(Math.max(a, i0)), xb = X(Math.min(b, i1)) + cw;
    s += '<rect class="phdd" x="' + xa.toFixed(1) + '" y="' + (yt - 4) + '" width="' + Math.max(1, xb - xa).toFixed(1) + '" height="' + (yb - yt + 8) + '"/>';
    const lb = '跌 ' + Math.round(Math.abs(e.dd)) + '%', xm = (xa + xb) / 2;
    if (xb - xa > 24 && xm - 18 > lastL) { s += '<text class="phddl" x="' + xm.toFixed(1) + '" y="' + (yb + 15) + '">' + lb + '</text>'; lastL = xm + 18; }
  });
  const yrs = [];
  for (let i = i0 + 1; i <= i1; i++) if (ds[i].slice(0, 4) !== ds[i - 1].slice(0, 4)) yrs.push(i);
  const st = Math.max(1, Math.ceil(yrs.length / (mob ? 4 : 10)));
  yrs.forEach((i, k) => {
    s += '<line class="phg" x1="' + X(i).toFixed(1) + '" x2="' + X(i).toFixed(1) + '" y1="4" y2="' + (H - 2) + '"/>';
    if (k % st === 0) s += '<text class="pht" x="' + (X(i) + 3).toFixed(1) + '" y="12">' + ds[i].slice(0, 4) + '</text>';
  });
  let d = '', pen = false;
  for (let i = i0; i <= i1; i++) { const v = D.w.px[i]; if (!(v > 0)) { pen = false; continue; } d += (pen ? 'L' : 'M') + (X(i) + cw / 2).toFixed(1) + ' ' + Yp(v).toFixed(1); pen = true; }
  s += '<path class="phpx" d="' + d + '"/>';
  let y = top;
  DIM.forEach(id => {
    const Q = PS.tr[id].Q, q1 = Q[i1], j1 = q1 == null ? null : phSince(Q, i1);
    const lab = q1 == null ? '沒有資料' : PHC.n[q1], wk = q1 == null ? '' : '已 ' + (i1 - j1 + 1) + ' 週';
    if (mob) { s += '<text class="phn" x="' + x0 + '" y="' + (y + 12) + '">' + esc(NM[id]) + '<tspan class="phw2" dx="7">' + esc(lab) + (wk ? '・' + wk : '') + '</tspan></text>'; y += cap; }
    else s += '<text class="phn" x="' + (lw - 6) + '" y="' + (y + rh / 2 + 4.5).toFixed(1) + '" text-anchor="end">' + esc(NM[id]) + '</text>';
    s += '<rect class="phbg" x="' + x0 + '" y="' + y + '" width="' + (x1 - x0).toFixed(1) + '" height="' + rh + '"/>';
    let i = i0;
    while (i <= i1) {
      const q = Q[i];
      let j = i;
      while (j + 1 <= i1 && Q[j + 1] === q) j++;
      if (q != null) s += '<rect class="pq' + q + '" x="' + X(i).toFixed(2) + '" y="' + y + '" width="' + (X(j) - X(i) + cw + 0.4).toFixed(2) + '" height="' + rh + '"/>';
      i = j + 1;
    }
    if (!mob) s += '<text class="phs" x="' + (x1 + 8).toFixed(1) + '" y="' + (y + rh / 2 + 4.5).toFixed(1) + '">' + esc(lab) + '<tspan class="phw2" dx="6">' + esc(wk) + '</tspan></text>';
    y += rh + gap;
  });
  s += '<line class="phgd" id="phgd" x1="0" x2="0" y1="4" y2="' + (H - gap) + '" style="display:none"/>';
  s += '<rect class="phhit" id="phhit" x="' + x0 + '" y="0" width="' + (x1 - x0).toFixed(1) + '" height="' + H + '"/>';
  box.innerHTML = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="各面向的階段時間軸">' + s + '</svg>';
  PS.g = {x0: x0, x1: x1, cw: cw, i0: i0, i1: i1, H: H, gap: gap};
  phLead();
  phTip(null);
}
function phAt(e) {
  const g = PS.g, svg = $('#phx svg');
  if (!g || !svg) return null;
  const r = svg.getBoundingClientRect(), x = (e.clientX - r.left) * (svg.viewBox.baseVal.width / r.width);
  if (x < g.x0 || x > g.x1) return null;
  return Math.max(g.i0, Math.min(g.i1, g.i0 + Math.floor((x - g.x0) / g.cw)));
}
function phTip(i, e, touch) {
  const t = $('#phtip'), gd = $('#phgd'), w = $('#phw');
  if (!t || !gd || !w) return;
  if (i == null) { t.hidden = true; gd.style.display = 'none'; return; }
  const g = PS.g, gx = g.x0 + (i - g.i0 + 0.5) * g.cw;
  gd.setAttribute('x1', gx.toFixed(1)); gd.setAttribute('x2', gx.toFixed(1)); gd.style.display = '';
  let h = '<b>' + esc(ymd(D.w.d[i])) + (D.w.px[i] ? '・' + esc(PXN) + ' ' + fpx(D.w.px[i]) : '') + '</b>';
  DIM.forEach(id => {
    const tr = PS.tr[id], q = tr.Q[i];
    h += '<div><i class="phq' + (q == null ? '' : ' pq' + q) + '"' + (q == null ? ' style="background:var(--line2)"' : '') + '></i>' + esc(NM[id]) + '：' + (q == null ? '沒有資料' : esc(PHC.n[q]) + '（' + n0(tr.L[i]) + '）') + '</div>';
  });
  h += touch ? '<a href="#" class="tgo" data-phgo="' + i + '">看那一週的雷達 →</a>' : '<div class="tpx">括號＝8 週平均熱度；點一下看那一週的雷達</div>';
  t.innerHTML = h;
  t.style.pointerEvents = touch ? 'auto' : 'none';
  t.hidden = false;
  const bx = w.getBoundingClientRect(), svg = $('#phx svg'), sc = svg ? svg.getBoundingClientRect().width / svg.viewBox.baseVal.width : 1;
  const tw = t.offsetWidth, th = t.offsetHeight, px = gx * sc;
  let left = px + 12;
  if (left + tw > bx.width - 4) left = px - tw - 12;
  t.style.left = Math.max(4, left) + 'px';
  const ey = e ? e.clientY - bx.top : 24;
  t.style.top = Math.max(4, Math.min(bx.height - th - 4, ey - th / 2)) + 'px';
}
function phGo(i) { setView('radar'); setT(i); const r = $('#top'); if (r) r.scrollIntoView({block: 'start'}); }

// ── 3D 熱度地形（canvas 自己投影，不載入外部套件）：每條山脊一個面向，越高越熱，最右邊是現在。
//    山脊只用一個顏色；高出 80 的山頂塗紅（過熱）、低於 20 的谷底積藍（過冷）；地面灰帶＝指數從高點跌 20% 以上的期間；
//    最前面一排＝同一週有幾個面向過熱。右側一欄是讀數（平常是現在，滑過時換成那一週）。拖曳旋轉，點一下跳到雷達看那一週
const TDEF = {yaw: -0.34, pitch: 0.6}, TDEFM = {yaw: -0.1, pitch: 0.92};       // 手機：往下看多一點，山脊上下分開
const TS = {yaw: TDEF.yaw, pitch: TDEF.pitch, rg: 10, flat: false, inited: false, pts: [], drag: null, hi: null, hiRow: null, raf: 0, T: null, geo: null};
const clampY = v => Math.max(-0.95, Math.min(0.2, v)), clampP = v => Math.max(0.28, Math.min(1.12, v));
function tMob() { const b = $('#ter'); return !!b && b.clientWidth < 560; }
function tShow() { if (!D) { withData(tShow); return; } if (!TS.inited) { tInit(); const d = tMob() ? TDEFM : TDEF; TS.yaw = d.yaw; TS.pitch = d.pitch; } TS.T = null; tDraw(); }
function tReq() { if (!TS.raf) TS.raf = requestAnimationFrame(() => { TS.raf = 0; tDraw(); }); }
function tGo(j) { if (j == null || !TS.T) return; setView('radar'); setT(TS.T.i0 + j); const r = $('#top'); if (r) r.scrollIntoView({block: 'start'}); }
function tInit() {
  TS.inited = true;
  const cv = $('#tcv'), ld = $('#tld'), tip = $('#ttip');
  if (ld) ld.hidden = true;
  if (!cv) return;
  cv.tabIndex = 0;
  cv.addEventListener('pointerdown', e => { TS.drag = {x: e.clientX, y: e.clientY, yaw: TS.yaw, pitch: TS.pitch, moved: false, touch: e.pointerType === 'touch'}; cv.setPointerCapture(e.pointerId); cv.classList.add('drag'); });
  cv.addEventListener('pointermove', e => {
    if (TS.drag) {
      const dx = e.clientX - TS.drag.x, dy = e.clientY - TS.drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 5) TS.drag.moved = true;
      if (TS.drag.moved && !TS.flat) {
        TS.yaw = clampY(TS.drag.yaw + dx * 0.005);
        if (!TS.drag.touch) TS.pitch = clampP(TS.drag.pitch + dy * 0.005);       // 手機上下滑是捲頁面，只轉水平
        TS.hi = null; tTip(null); tReq();
      }
      return;
    }
    tHover(e);
  });
  const end = e => {
    const d = TS.drag; TS.drag = null; cv.classList.remove('drag');
    if (!d || d.moved || e.type === 'pointercancel') return;
    const r = cv.getBoundingClientRect(), lx = e.clientX - r.left, ly = e.clientY - r.top, lb = (TS.labs || []).find(q => lx >= q.x0 && lx <= q.x1 && ly >= q.y0 && ly <= q.y1);
    if (lb && !TS.flat) { tFocus(lb.id); return; }
    const h = tHit(e);
    if (!h) { TS.hi = null; tTip(null); tReq(); return; }
    if (d.touch) { TS.hi = h.j; tTip(h, e, true); tReq(); }            // 手機：先顯示那一週，按提示框裡的連結才跳
    else tGo(h.j);
  };
  cv.addEventListener('pointerup', end);
  cv.addEventListener('pointercancel', end);
  cv.addEventListener('pointerleave', e => { if (!TS.drag && e.pointerType !== 'touch') { TS.hi = null; tTip(null); tReq(); } });
  cv.addEventListener('keydown', e => {
    const k = e.key;
    if (k === 'ArrowLeft' || k === 'ArrowRight') { TS.yaw = clampY(TS.yaw + (k === 'ArrowLeft' ? -0.08 : 0.08)); tReq(); e.preventDefault(); }
    if (k === 'ArrowUp' || k === 'ArrowDown') { TS.pitch = clampP(TS.pitch + (k === 'ArrowUp' ? 0.06 : -0.06)); tReq(); e.preventDefault(); }
  });
  if (tip) tip.addEventListener('click', e => { const a = e.target.closest && e.target.closest('[data-tgo]'); if (a) { e.preventDefault(); tGo(+a.dataset.tgo); } }, SG);
  $$('[data-tr]').forEach(b => b.addEventListener('click', () => { TS.rg = +b.dataset.tr; TS.T = null; TS.hi = null; tTip(null); $$('[data-tr]').forEach(x => { const on = x === b; x.classList.toggle('on', on); x.setAttribute('aria-pressed', on ? 'true' : 'false'); }); tDraw(); }, SG));
  const fc = $('#tfoc');
  if (fc) fc.addEventListener('click', e => { const b = e.target.closest && e.target.closest('[data-tf]'); if (b) tFocus(b.dataset.tf || null); }, SG);
  const fl = $('#tflat');
  if (fl) fl.addEventListener('click', () => {
    TS.flat = !TS.flat; TS.hi = null; tTip(null); fl.classList.toggle('on', TS.flat); fl.setAttribute('aria-pressed', TS.flat ? 'true' : 'false');
    const rs = $('#treset'); if (rs) rs.hidden = TS.flat;
    $$('.tlg').forEach(g => { g.hidden = (g.dataset.m === 'flat') !== TS.flat; });
    tDraw();
  }, SG);
  const rs = $('#treset');
  if (rs) rs.addEventListener('click', () => { const d = tMob() ? TDEFM : TDEF; TS.yaw = d.yaw; TS.pitch = d.pitch; tDraw(); }, SG);
  if (window.matchMedia) matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { if (document.documentElement.dataset.hv === 'terrain') tDraw(); }, SG);
}
function wkIdx(d) { const ds = D.w.d; let lo = 0, hi = ds.length - 1; if (d > ds[hi]) return hi; while (lo < hi) { const m = (lo + hi) >> 1; if (ds[m] >= d) hi = m; else lo = m + 1; } return lo; }
function tData() {
  const ds = D.w.d, i1 = ds.length - 1;
  let i0 = iStart();
  if (TS.rg) { const cut = (+ds[i1].slice(0, 4) - TS.rg) + ds[i1].slice(4); const j = ds.findIndex(d => d > cut); i0 = Math.max(i0, j < 0 ? 0 : j); }
  const K = TS.rg ? 4 : 8, N = i1 - i0 + 1;                           // 山脊畫最近 K 週平均（只用當週以前）；讀數用原始分數
  const rows = DIM.map(id => {
    const t = D.s[id] && D.s[id].h, raw = [], sm = [];
    for (let i = i0; i <= i1; i++) raw.push(val(t, i));
    let s = 0, q = [];
    raw.forEach(v => { if (v == null) { sm.push(null); s = 0; q = []; return; } q.push(v); s += v; if (q.length > K) s -= q.shift(); sm.push(s / q.length); });
    let last = -1;
    for (let j = N - 1; j >= 0; j--) if (sm[j] != null) { last = j; break; }
    return {id: id, raw: raw, sm: sm, last: last};
  });
  const hot = [];
  for (let j = 0; j < N; j++) { let h = 0, any = false; rows.forEach(r => { if (r.raw[j] != null) { any = true; if (r.raw[j] >= 80) h++; } }); hot.push(any ? h : null); }
  const eps = (P.eps || []).map(e => ({a: wkIdx(e.p) - i0, b: wkIdx(e.t) - i0, dd: e.dd, o: e.o, p: e.p, t: e.t})).filter(e => e.b >= 0 && e.a < N);
  return {i0: i0, i1: i1, N: N, rows: rows, hot: hot, eps: eps};
}
function hexA(c, a) { const m = /^#?([0-9a-f]{6})$/i.exec(c); if (!m) return c; const n = parseInt(m[1], 16); return 'rgba(' + (n >> 16 & 255) + ',' + (n >> 8 & 255) + ',' + (n & 255) + ',' + a + ')'; }
function mixC(a, b, t) {
  const p = x => { const m = /^#?([0-9a-f]{6})$/i.exec(x); const n = m ? parseInt(m[1], 16) : 0x888888; return [n >> 16 & 255, n >> 8 & 255, n & 255]; };
  const A = p(a), B = p(b);
  return 'rgb(' + A.map((v, k) => Math.round(v + (B[k] - v) * t)).join(',') + ')';
}
function tColors() {
  const dc = {};
  P.dims.forEach(d => { dc[d.id] = css('--' + d.col); });
  return {bg: css('--card2'), ink: css('--ink'), ink2: css('--ink2'), mut: css('--mut'), line: css('--line2'), hot: css('--c4'), cold: css('--c0'),
          acc: css('--acc'), panel: css('--panel'), dc: dc, t: [0, 1, 2, 3, 4].map(k => css('--t' + k)), c: [0, 1, 2, 3, 4].map(k => css('--c' + k))};
}
function tCanvas() {
  const cv = $('#tcv'), box = $('#ter');
  if (!cv || !box || !D || !box.clientWidth) return null;
  const W = box.clientWidth, H = box.clientHeight, dpr = Math.min(2, window.devicePixelRatio || 1);
  if (cv.width !== Math.round(W * dpr) || cv.height !== Math.round(H * dpr)) { cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); }
  const c = cv.getContext('2d');
  c.setTransform(dpr, 0, 0, dpr, 0, 0);
  c.clearRect(0, 0, W, H);
  return {c: c, W: W, H: H};
}
function tDraw() {
  const cx = tCanvas();
  if (!cx) return;
  const T = TS.T || (TS.T = tData());
  const K = tColors();
  TS.pts = [];
  if (TS.flat) { tFlat(cx, T, K); return; }
  const FOC = TS.focus || null;                                                // 點選只看一條：其他山脊變淡
  const c = cx.c, W = cx.W, n = T.rows.length, N = T.N, mob = W < 560;
  if (!mob) { const box = $('#ter'); if (box && box.style.height && !TS.fit) { box.style.height = ''; box.style.minHeight = ''; TS.fit = true; tDraw(); TS.fit = false; return; } }
  const LW = mob ? 92 : 132, pad = mob ? 8 : 18, BOT = 34, TOP = mob ? 30 : 34;      // 右側讀數欄、下方年份與跌幅、上方日期
  if (mob) {                                                                // 手機：畫布高度照內容（用預設角度算，拖曳時不會跳）
    const f = tCam(TDEFM.yaw, TDEFM.pitch, n, W - LW - 2 * pad, 1e9), want = Math.round(Math.max(270, Math.min(560, TOP + f.h + BOT + pad + 4)));
    const box = $('#ter');
    if (box && Math.abs(box.clientHeight - want) > 4 && !TS.fit) { box.style.minHeight = '0'; box.style.height = want + 'px'; TS.fit = true; tDraw(); TS.fit = false; return; }
  }
  const H = cx.H, CAM = tCam(TS.yaw, TS.pitch, n, W - LW - 2 * pad, H - TOP - BOT - pad);
  const XW = CAM.XW, YH = CAM.YH, ZS = CAM.ZS, FR = CAM.FR, z0 = CAM.z0, z1 = CAM.z1, cx0 = CAM.cx0, sc = CAM.sc, raw = CAM.raw;
  const ox = pad + (W - LW - 2 * pad - CAM.w) / 2 - CAM.mnx * sc, oy = TOP + (H - TOP - BOT - pad - CAM.h) / 2 + CAM.mxy * sc;
  const pr = (x, y, z) => { const q = raw(x, y, z); return [ox + q[0] * sc, oy - q[1] * sc, q[2]]; };
  const xi = j => j / Math.max(1, N - 1) * XW, yv = v => v / 100 * YH;
  const poly = pts => { c.beginPath(); pts.forEach((p, k) => (k ? c.lineTo(p[0], p[1]) : c.moveTo(p[0], p[1]))); c.closePath(); };
  const zOf = k => (n - 1 - k) * ZS;                                         // 第一個面向在最後面
  // 地面、年份格線、大跌期間
  poly([pr(0, 0, z0), pr(XW, 0, z0), pr(XW, 0, z1), pr(0, 0, z1)]); c.fillStyle = mixC(K.bg, K.ink, 0.045); c.fill();
  T.eps.forEach(e => { const a = Math.max(0, e.a), b = Math.min(N - 1, Math.max(e.b, a + 1)); poly([pr(xi(a), 0, z0), pr(xi(b), 0, z0), pr(xi(b), 0, z1), pr(xi(a), 0, z1)]); c.fillStyle = hexA(K.ink, 0.13); c.fill(); });
  c.strokeStyle = hexA(K.ink, 0.10); c.lineWidth = 1;
  const yrs = [];
  for (let j = 1; j < N; j++) if (D.w.d[T.i0 + j].slice(0, 4) !== D.w.d[T.i0 + j - 1].slice(0, 4)) yrs.push(j);
  yrs.forEach(j => { const a = pr(xi(j), 0, z0), b = pr(xi(j), 0, z1); c.beginPath(); c.moveTo(a[0], a[1]); c.lineTo(b[0], b[1]); c.stroke(); });
  // 同時過熱（最前面一排）
  const hz0 = z0 + FR * 0.22, hz1 = z0 + FR * 0.72;
  let j = 0;
  while (j < N) {
    const h = T.hot[j]; let k = j;
    while (k + 1 < N && T.hot[k + 1] === h) k++;
    if (h) { poly([pr(xi(j), 0, hz0), pr(xi(k + 1 < N ? k + 1 : k), 0, hz0), pr(xi(k + 1 < N ? k + 1 : k), 0, hz1), pr(xi(j), 0, hz1)]); c.fillStyle = hexA(K.hot, Math.min(0.9, 0.18 + 0.2 * h)); c.fill(); }
    j = k + 1;
  }
  // 山脊（由遠到近）：每個面向一個顏色（線＋淡淡的牆面）；低於 20 的谷底積藍、高出 80 的山頂塗紅
  const order = T.rows.map((r, k) => ({r: r, k: k, z: zOf(k), d: pr(cx0, 0, zOf(k))[2]})).sort((a, b) => b.d - a.d);
  const segs = sm => { const out = []; let s = null; sm.forEach((v, t) => { if (v == null) { if (s) out.push(s); s = null; } else (s = s || []).push(t); }); if (s) out.push(s); return out; };
  order.forEach((o, q) => {
    const z = o.z, sm = o.r.sm, rank = q / Math.max(1, n - 1);              // rank：0＝最遠、1＝最近
    const dimR = !!FOC && FOC !== o.r.id, col = K.dc[o.r.id] || K.ink;
    c.globalAlpha = dimR ? 0.16 : 1;
    const wall = mixC(K.bg, col, 0.10 + 0.09 * rank), wallT = mixC(K.bg, col, 0.17 + 0.1 * rank);
    const top = pr(cx0, YH, z), base = pr(cx0, 0, z), gr = c.createLinearGradient(top[0], top[1], base[0], base[1]);
    gr.addColorStop(0, wallT); gr.addColorStop(1, wall);
    const hiRow = TS.hiRow === o.r.id;
    segs(sm).forEach(sg => {
      const a = xi(sg[0]), b = xi(sg[sg.length - 1]);
      const tp = sg.map(t => pr(xi(t), yv(sm[t]), z)), body = tp.concat([pr(b, 0, z), pr(a, 0, z)]);
      poly(body); c.fillStyle = gr; c.fill();
      const band = (thr, f, col) => { poly(sg.map(t => pr(xi(t), yv(f(sm[t], thr)), z)).concat([pr(b, yv(thr), z), pr(a, yv(thr), z)])); c.fillStyle = col; c.fill(); };
      if (sg.some(t => sm[t] < 20)) band(20, Math.min, hexA(K.cold, 0.85));            // 谷底低於 20：門檻線到山脊之間積藍
      if (sg.some(t => sm[t] >= 80)) band(80, Math.max, hexA(K.hot, 0.92));            // 山頂高出 80：門檻線到山脊之間塗紅
      c.beginPath(); tp.forEach((p, k) => (k ? c.lineTo(p[0], p[1]) : c.moveTo(p[0], p[1])));
      c.strokeStyle = col; c.lineWidth = FOC === o.r.id ? 2.6 : (hiRow ? 2.3 : 1.7); c.lineJoin = 'round'; c.stroke();
      const b0 = pr(a, 0, z), b1 = pr(b, 0, z); c.beginPath(); c.moveTo(b0[0], b0[1]); c.lineTo(b1[0], b1[1]); c.strokeStyle = hexA(K.ink, 0.22); c.lineWidth = 1; c.stroke();
      sg.forEach(t => { const p = tp[t - sg[0]]; TS.pts.push({x: p[0], y: p[1], z: p[2], id: o.r.id, j: t}); });
    });
    if (TS.hi != null && sm[TS.hi] != null) {                              // 滑過的那一週：每條山脊一條直線＋一個點（照遠近順序畫，會被前面的山擋住）
      const t = TS.hi, p = pr(xi(t), yv(sm[t]), z), b0 = pr(xi(t), 0, z);
      c.beginPath(); c.moveTo(b0[0], b0[1]); c.lineTo(p[0], p[1]); c.strokeStyle = hexA(K.ink, 0.7); c.lineWidth = 1.2; c.stroke();
      c.beginPath(); c.arc(p[0], p[1], 3.6, 0, 6.3); c.fillStyle = K.c[+zc(o.r.raw[t] == null ? sm[t] : o.r.raw[t])] || K.ink; c.fill(); c.strokeStyle = K.panel; c.lineWidth = 1.4; c.stroke();
    }
    c.globalAlpha = 1;
  });
  if (TS.hi != null) { const a = pr(xi(TS.hi), 0, z0), b = pr(xi(TS.hi), 0, hz1); c.beginPath(); c.moveTo(a[0], a[1]); c.lineTo(b[0], b[1]); c.strokeStyle = hexA(K.ink, 0.7); c.lineWidth = 1.4; c.stroke(); }
  // 下方：年份、跌幅
  c.textBaseline = 'alphabetic'; c.font = '11px sans-serif'; c.fillStyle = K.mut; c.textAlign = 'center';
  let last = -1e9;
  const yf = p => p[1] + 14;
  yrs.forEach(j => { const p = pr(xi(j), 0, z0); if (p[0] - last > (mob ? 30 : 34) && p[0] < W - LW - 6) { c.fillText(D.w.d[T.i0 + j].slice(0, 4), p[0], yf(p)); last = p[0]; } });
  last = -1e9;
  c.font = '600 10.5px sans-serif';
  T.eps.forEach(e => {
    const a = Math.max(0, e.a), b = Math.min(N - 1, e.b), p = pr(xi((a + b) / 2), 0, z0), lb = '跌 ' + Math.round(Math.abs(e.dd)) + '%';
    const w = c.measureText(lb).width;
    if (p[0] - w / 2 < last + 6 || p[0] + w / 2 > W - LW) return;
    c.fillStyle = K.ink2; c.fillText(lb, p[0], yf(p) + 14); last = p[0] + w / 2;
  });
  tReadout(c, T, K, W, H, LW, pad, mob, order.map(o => ({id: o.r.id, p: o.r.last >= 0 ? pr(xi(o.r.last), yv(o.r.sm[o.r.last]), o.z) : null})),
    pr(xi(N - 1), 0, (hz0 + hz1) / 2));
  TS.geo = {W: W, LW: LW};
}
// 投影：時間長 120、滿分高 22、山脊間距 15；最前面一排留給「同時過熱」。回傳縮放後的寬高（放進 aw × ah）
function tCam(yaw, pitch, n, aw, ah) {
  const XW = 120, YH = 22, ZS = 15, FR = ZS * 1.05, z0 = -FR, z1 = (n - 1) * ZS + ZS * 0.45;
  const cx0 = XW / 2, cy0 = YH / 3, cz0 = (z0 + z1) / 2, DIST = 340;
  const cyw = Math.cos(yaw), syw = Math.sin(yaw), cp = Math.cos(pitch), sp = Math.sin(pitch);
  const raw = (x, y, z) => { const X0 = x - cx0, Y0 = y - cy0, Z0 = z - cz0, x1 = X0 * cyw - Z0 * syw, z1 = X0 * syw + Z0 * cyw, y1 = Y0 * cp + z1 * sp, z2 = z1 * cp - Y0 * sp, f = DIST / (DIST + z2); return [x1 * f, y1 * f, z2]; };
  let mnx = Infinity, mxx = -Infinity, mny = Infinity, mxy = -Infinity;
  [0, XW].forEach(x => [0, YH].forEach(y => [z0, z1].forEach(z => { const q = raw(x, y, z); mnx = Math.min(mnx, q[0]); mxx = Math.max(mxx, q[0]); mny = Math.min(mny, q[1]); mxy = Math.max(mxy, q[1]); })));
  const sc = Math.min(aw / ((mxx - mnx) || 1), ah / ((mxy - mny) || 1));
  return {XW: XW, YH: YH, ZS: ZS, FR: FR, z0: z0, z1: z1, cx0: cx0, raw: raw, sc: sc, mnx: mnx, mxy: mxy, w: (mxx - mnx) * sc, h: (mxy - mny) * sc};
}
// 右側讀數欄：每個面向一列（照畫面上下排、用細線連到山脊），最下面是同時過熱的數目；平常是現在，滑過時換成那一週
function md2(d) { return d ? (+d.slice(5, 7)) + '/' + (+d.slice(8, 10)) : '—'; }
function tReadout(c, T, K, W, H, LW, pad, mob, ends, hotP) {
  TS.labs = [];
  const j = TS.hi != null ? TS.hi : T.N - 1, x0 = W - LW + (mob ? 4 : 10), gap = mob ? 18 : 21, fs = mob ? 11.5 : 12.5;
  c.textBaseline = 'middle'; c.textAlign = 'left';
  const dd = D.w.d[T.i0 + j];
  c.font = '700 ' + (mob ? 12 : 13) + 'px sans-serif'; c.fillStyle = TS.hi != null ? K.acc : K.ink;
  c.fillText(TS.hi != null ? ymd(dd) : '現在 ' + (mob ? md2(dd) : ymd(dd)), x0, pad + 6);
  c.font = (mob ? 10.5 : 11.5) + 'px sans-serif'; c.fillStyle = K.mut;
  c.fillText((mob ? '指數' : PXN) + ' ' + fpx(D.w.px[T.i0 + j]), x0, pad + (mob ? 23 : 25));
  const L = ends.filter(e => e.p).map(e => ({id: e.id, p: e.p, y: e.p[1]})).sort((a, b) => a.y - b.y);
  const y0 = pad + (mob ? 46 : 50), y1 = H - 34 - gap;                       // 標籤中心可以放的範圍（上面留給日期、下面留給同時過熱）
  for (let k = 0; k < L.length; k++) L[k].y = Math.max(L[k].y, k ? L[k - 1].y + gap : y0);
  for (let k = L.length - 1; k >= 0; k--) L[k].y = Math.min(L[k].y, k < L.length - 1 ? L[k + 1].y - gap : y1);
  for (let k = 0; k < L.length; k++) L[k].y = Math.max(L[k].y, k ? L[k - 1].y + gap : y0);
  L.forEach(l => {
    const r = T.rows.find(x => x.id === l.id), v = r.raw[j] != null ? r.raw[j] : null, z = zc(v);
    c.beginPath(); c.moveTo(l.p[0] + 3, l.p[1]); c.lineTo(x0 - 4, l.y); c.strokeStyle = hexA(K.ink, 0.28); c.lineWidth = 1; c.stroke();
    c.beginPath(); c.arc(l.p[0], l.p[1], 2.6, 0, 6.3); c.fillStyle = hexA(K.ink, 0.75); c.fill();
    const pc = K.dc[l.id] || K.ink, fo = TS.focus;
    c.globalAlpha = fo && fo !== l.id ? 0.35 : 1;
    c.fillStyle = pc; c.fillRect(x0, l.y - 1.5, 12, 3);
    const xs = x0 + 16;
    c.font = (fo === l.id ? '800 ' : '600 ') + fs + 'px sans-serif'; c.fillStyle = K.ink; c.fillText(NM[l.id], xs, l.y);
    const w = c.measureText(NM[l.id]).width + (xs - x0);
    c.font = '800 ' + (fs + 1) + 'px sans-serif'; c.fillStyle = z === 'x' ? K.mut : K.t[+z]; c.fillText(n0(v), x0 + w + 6, l.y);
    c.globalAlpha = 1;
    TS.labs.push({id: l.id, x0: x0 - 4, x1: W - 4, y0: l.y - gap / 2, y1: l.y + gap / 2});
  });
  const h = T.hot[j], hy = Math.max(H - 30, (L.length ? L[L.length - 1].y : 0) + gap);
  c.beginPath(); c.moveTo(hotP[0] + 3, hotP[1]); c.lineTo(x0 - 4, hy); c.strokeStyle = hexA(K.hot, 0.45); c.lineWidth = 1; c.stroke();
  c.font = '600 ' + (fs - 0.5) + 'px sans-serif'; c.fillStyle = K.ink2; c.fillText('同時過熱', x0, hy);
  const w = c.measureText('同時過熱').width;
  c.font = '800 ' + fs + 'px sans-serif'; c.fillStyle = h ? K.t[4] : K.mut; c.fillText((h == null ? '—' : h) + ' 個', x0 + w + 6, hy);
}
// 平面：列＝面向（左邊名稱與讀數）、欄＝週；最下面一列同時過熱；灰底＝大跌期間
function tFlat(cx, T, K) {
  const c = cx.c, W = cx.W, H = cx.H, N = T.N, n = T.rows.length, mob = W < 560;
  const L = mob ? 86 : 118, R = 8, top = 34, rh = mob ? 30 : 40, cw = (W - L - R) / N, want = Math.round(top + (n + 1) * rh + 50);
  const box = $('#ter');
  if (box && Math.abs(box.clientHeight - want) > 4 && !TS.fit) { box.style.minHeight = '0'; box.style.height = want + 'px'; TS.fit = true; tDraw(); TS.fit = false; return; }
  const j = TS.hi != null ? TS.hi : N - 1;
  T.eps.forEach(e => { const a = Math.max(0, e.a), b = Math.min(N - 1, e.b); c.fillStyle = hexA(K.ink, 0.08); c.fillRect(L + a * cw, top - 4, Math.max(1, (b - a + 1) * cw), (n + 1) * rh + 8); });
  c.textBaseline = 'middle'; c.textAlign = 'left';
  c.font = '700 ' + (mob ? 12 : 13) + 'px sans-serif'; c.fillStyle = TS.hi != null ? K.acc : K.ink;
  c.fillText((TS.hi != null ? '' : '現在 ') + ymd(D.w.d[T.i0 + j]), 8, 14);
  c.font = (mob ? 10.5 : 11.5) + 'px sans-serif'; c.fillStyle = K.mut; c.textAlign = 'right';
  c.fillText(PXN + ' ' + fpx(D.w.px[T.i0 + j]), W - R, 14);
  T.rows.forEach((r, k) => {
    const y = top + k * rh;
    c.globalAlpha = TS.focus && TS.focus !== r.id ? 0.25 : 1;
    let s = 0;
    while (s < N) { const v = r.raw[s]; let e = s; const z = zc(v); while (e + 1 < N && zc(r.raw[e + 1]) === z) e++; if (z !== 'x') { c.fillStyle = K.c[+z]; c.fillRect(L + s * cw, y + 2, (e - s + 1) * cw + 0.5, rh - 4); } s = e + 1; }
    const v = r.raw[j], z = zc(v);
    c.fillStyle = K.dc[r.id] || K.ink; c.fillRect(6, y + rh / 2 - 1.5, 10, 3);
    c.textAlign = 'left'; c.font = '600 ' + (mob ? 11.5 : 12.5) + 'px sans-serif'; c.fillStyle = K.ink; c.fillText(NM[r.id], 20, y + rh / 2);
    c.textAlign = 'right'; c.font = '800 ' + (mob ? 12 : 13) + 'px sans-serif'; c.fillStyle = z === 'x' ? K.mut : K.t[+z]; c.fillText(n0(v), L - 6, y + rh / 2);
    c.globalAlpha = 1;
  });
  const hy = top + n * rh;
  for (let s = 0; s < N; s++) { const h = T.hot[s]; if (h) { c.fillStyle = hexA(K.hot, Math.min(0.9, 0.18 + 0.2 * h)); c.fillRect(L + s * cw, hy + 2, cw + 0.5, rh - 4); } }
  c.textAlign = 'left'; c.font = '600 ' + (mob ? 11 : 12) + 'px sans-serif'; c.fillStyle = K.ink2; c.fillText('同時過熱', 6, hy + rh / 2);
  c.textAlign = 'right'; c.font = '800 ' + (mob ? 12 : 13) + 'px sans-serif'; c.fillStyle = T.hot[j] ? K.t[4] : K.mut; c.fillText((T.hot[j] == null ? '—' : T.hot[j]) + ' 個', L - 6, hy + rh / 2);
  if (TS.hi != null) { c.fillStyle = hexA(K.ink, 0.85); c.fillRect(L + TS.hi * cw + cw / 2 - 0.75, top - 6, 1.5, (n + 1) * rh + 10); }
  c.textBaseline = 'alphabetic'; c.textAlign = 'center'; c.fillStyle = K.mut; c.font = '11px sans-serif';
  let last = -1e9;
  const yb = top + (n + 1) * rh + 16;
  for (let s = 1; s < N; s++) if (D.w.d[T.i0 + s].slice(0, 4) !== D.w.d[T.i0 + s - 1].slice(0, 4)) { const x = L + s * cw; if (x - last > 34 && x < W - 14) { c.fillText(D.w.d[T.i0 + s].slice(0, 4), x, yb); last = x; } }
  last = -1e9; c.font = '600 10.5px sans-serif'; c.fillStyle = K.ink2;
  T.eps.forEach(e => { const a = Math.max(0, e.a), b = Math.min(N - 1, e.b), x = L + (a + b + 1) / 2 * cw, lb = '跌 ' + Math.round(Math.abs(e.dd)) + '%', w = c.measureText(lb).width; if (x - w / 2 < last + 6) return; c.fillText(lb, x, yb + 14); last = x + w / 2; });
  TS.pts = {flat: true, L: L, cw: cw, top: top, bot: top + (n + 1) * rh, N: N};
}
function tFocus(id) {
  TS.focus = id && TS.focus !== id ? id : null;
  $$('#tfoc [data-tf]').forEach(b => { const on = (b.dataset.tf || null) === TS.focus; b.classList.toggle('on', on); b.setAttribute('aria-pressed', on ? 'true' : 'false'); });
  tReq();
}
function tHit(e) {
  const cv = $('#tcv'), r = cv.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
  if (TS.flat) {
    const F = TS.pts;
    if (!F || !F.flat || y < F.top - 6 || y > F.bot + 6) return null;
    const j = Math.floor((x - F.L) / F.cw);
    return j < 0 || j >= F.N ? null : {j: j};
  }
  if (TS.geo && x > TS.geo.W - TS.geo.LW) return null;
  let best = null, bd = 44;
  TS.pts.forEach(p => {
    if (TS.focus && p.id !== TS.focus) return; const d = Math.abs(p.x - x) + Math.max(0, Math.abs(p.y - y) - 8) * 0.35; if (d < bd) { bd = d; best = p; } });
  return best ? {j: best.j, id: best.id} : null;
}
function tTip(h, e, touch) {
  const t = $('#ttip'), box = $('#ter');
  if (!t) return;
  if (!h || !TS.T) { t.hidden = true; return; }
  const T = TS.T, i = T.i0 + h.j;
  const row = h.id ? T.rows.find(r => r.id === h.id) : null, v = row ? row.raw[h.j] : null;
  t.innerHTML = (row ? '<b>' + esc(NM[row.id]) + ' ' + n0(v) + '</b> <span class="tpx">' + esc(bn(v)) + '</span><div>' + esc(ymd(D.w.d[i])) + '</div>' : '<b>' + esc(ymd(D.w.d[i])) + '</b>') + (touch ? '<a href="#" class="tgo" data-tgo="' + h.j + '">看那一週的雷達 →</a>' : '<div class="tpx">點一下看那一週的雷達</div>');
  t.style.pointerEvents = touch ? 'auto' : 'none';
  t.hidden = false;
  const bx = box.getBoundingClientRect(), tw = t.offsetWidth, th = t.offsetHeight;
  let left = e.clientX - bx.left + 14;
  if (left + tw > bx.width - (TS.geo && !TS.flat ? TS.geo.LW : 0)) left = e.clientX - bx.left - tw - 14;
  t.style.left = Math.max(4, left) + 'px';
  t.style.top = Math.max(4, Math.min(bx.height - th - 4, e.clientY - bx.top - th - 12)) + 'px';
}
function tHover(e) {
  const h = tHit(e);
  const nj = h ? h.j : null, nr = h ? h.id || null : null;
  if (nj !== TS.hi || nr !== TS.hiRow) { TS.hi = nj; TS.hiRow = nr; tReq(); }
  tTip(h, e, false);
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
  const eh = t.closest('[data-eh]'), ef = t.closest('[data-ef]'), ed = t.closest('[data-ed]');
  if (eh || ef || ed) { e.preventDefault(); if (eh) ES.h = eh.dataset.eh; if (ef) ES.f = ef.dataset.ef; if (ed) ES.d = ES.d === ed.dataset.ed ? null : ed.dataset.ed; eApply(); return; }
  const jp = t.closest('[data-jump]');
  if (jp) { e.preventDefault(); jump(jp.dataset.jump); return; }
  const pr = t.closest('[data-phr]');
  if (pr) { e.preventDefault(); PS.rg = +pr.dataset.phr; phDraw(); return; }
  const pg = t.closest('[data-phgo]');
  if (pg) { e.preventDefault(); phGo(+pg.dataset.phgo); return; }
  const op = t.closest('[data-open]');
  if (op) { e.preventDefault(); const p = op.dataset.open.split(':'); openD(p[0], p[1]); return; }
  if (t.closest('#itabb')) { const tb = $('#itab'), im = $('#imap'), b = $('#itabb'), on = tb.hidden; tb.hidden = !on; im.hidden = on; b.classList.toggle('on', on); b.setAttribute('aria-pressed', on ? 'true' : 'false'); if (!on) imapDraw(); }
}, SG);
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && DRW && !DRW.hidden) { closeD(); return; }
  const t = e.target;
  if ((e.key === 'Enter' || e.key === ' ') && t && t.matches && t.matches('.kcard, .rax, .idot')) { e.preventDefault(); t.dispatchEvent(new MouseEvent('click', {bubbles: true})); }
}, SG);
const rtin = $('#rtin'); if (rtin) rtin.addEventListener('input', () => { stopPlay(); setT(+rtin.value, true); }, SG);
const rplay = $('#rplay'); if (rplay) { rplay.disabled = true; rplay.addEventListener('click', () => (RS.play ? stopPlay() : play()), SG); }
const phw = $('#phw');
if (phw) {
  phw.addEventListener('pointermove', e => { if (e.pointerType === 'mouse' && e.target.id === 'phhit') phTip(phAt(e), e, false); else if (e.pointerType === 'mouse' && !e.target.closest('#phtip')) phTip(null); }, SG);
  phw.addEventListener('pointerleave', e => { if (e.pointerType === 'mouse') phTip(null); }, SG);
  phw.addEventListener('click', e => {
    if (e.target.id !== 'phhit') return;
    const i = phAt(e);
    if (i == null) return;
    const touch = e.pointerType ? e.pointerType !== 'mouse' : !matchMedia('(hover: hover)').matches;
    if (touch && PS.pin !== i) { PS.pin = i; phTip(i, e, true); return; }
    PS.pin = null; phGo(i);
  }, SG);
}
let rt = null, lastW = window.innerWidth;
window.addEventListener('resize', () => {
  clearTimeout(rt);
  rt = setTimeout(() => {
    const v = document.documentElement.dataset.hv || 'radar';
    if (v === 'radar') { radarDraw(); trackDraw(); if (Math.abs(window.innerWidth - lastW) > 30 || !$('#imap svg')) imapDraw(); }
    if (v === 'phase') phDraw();
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
  ['#phx', '#tld'].forEach(sel => { const el = $(sel); if (el) el.innerHTML = '走勢資料載入失敗，重新整理頁面再試一次。'; });
});
};
"""
