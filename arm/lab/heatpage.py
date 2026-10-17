"""景氣溫度頁 → dashboard/x9m.html（docs/lab_heat_plan.md 第 12、13 節；入口＝籌碼雷達頂欄「景氣」小字，主頁不加入口）。

五個面向各一張卡（基本面、籌碼、全球資金、台灣資金、技術；使用者 2026-10-17：「要把短線籌碼熱度跟基本面區隔開來看」，
第四版再把資金拆成全球與台灣）：
分數、五段色條、和上週比、過去同一區之後的表現、判定；細項一律展開：每一項自己的 0～100、拉動分數幾分、佔比、本週增減
（使用者：「我要可以看到裡面的細項影響佔比，各項都有一個 0～100 讓我參考，不然這種綜合指標很容易只有象徵性」）。
當天的分數用 heatcalc 同一套算法重算；過去的分區統計與判定讀研究檔 data/lab/heat_research.json（只當資訊）。
技術卡後面是「關鍵價位與事件」（heattech）：均線、扣抵值、前波高低點、支撐壓力、近期事件與事件研究（不進分數）。
輸出決定性：不寫牆鐘時間，資料沒變時位元組相同。用字照專案禁用詞，不寫買賣指示。
"""
from __future__ import annotations

import bisect
import html
import json
from datetime import date
from pathlib import Path

from . import heat as H
from . import heatcalc as C
from . import heatspec as S
from . import heattech as TT

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dashboard" / "x9m.html"
RES = ROOT / "data" / "lab" / "heat_research.json"
TREND_DAYS = 500
TA_RECENT = 60                      # 「近期事件」列最近幾個交易日
WEEK = S.CHG_DAYS
NAV = {"fund": "基本面", "chip": "籌碼", "gliq": "全球資金", "tliq": "台灣資金", "tech": "技術"}
LINE_CLS = {"fund": "l1", "chip": "l2", "gliq": "l3", "tliq": "l5", "tech": "l4"}
SIGNED = {"B2", "B4", "B5", "B6", "B7", "B8", "C2", "C4", "C5", "C6", "G1", "G2", "G3", "G4",
          "L1", "L2", "L3", "L4", "L5", "L6", "L7", "L9", "L10", "T1", "T2", "T3", "T7", "T12", "T13"}
DEC = {"B1": 0, "B3": 1, "B4": 1, "B5": 1, "B6": 1, "C1": 0, "C2": 1, "C4": 1, "C5": 0, "C6": 1, "C7": 1, "C8": 2,
       "L5": 1, "L6": 1, "L9": 3, "T1": 1, "T2": 1, "T3": 1, "T4": 1, "T5": 1, "T6": 1, "T7": 1, "T8": 1, "T11": 0,
       "T12": 2, "T13": 1}
# 沒有 0～100 的固定原因（其他項目沒有分數時寫「沒有最新資料」或「歷史還不夠」）
WHY = {"L6": "證期局只公開最新一期新聞稿，從 2026 年 9 月開始累積，滿 60 個月才有 0～100"}
SRC = {
    "B1": "國發會", "B2": "國發會", "B3": "國發會", "B4": "經濟部", "B5": "國發會（海關出口值）",
    "B6": "自算（公開資訊觀測站月營收）", "B7": "主計總處", "B8": "勞工統計局",
    "C1": "FinMind（證交所融資融券）", "C2": "FinMind（證交所融資融券）", "C3": "FinMind（證交所融資融券）",
    "C4": "FinMind（期交所）", "C5": "FinMind（期交所法人未平倉）", "C6": "FinMind（期交所）", "C7": "期交所",
    "C8": "投信投顧公會（國內股票型基金持股比重，週）",
    "G1": "聯準會 H.15、紐約聯準銀行", "G2": "美國財政部", "G3": "美國財政部", "G4": "Yahoo HYG、IEF",
    "G5": "OFR 貨幣基金監測、Yahoo ^GSPC",
    "L1": "央行", "L2": "央行", "L3": "FinMind＋證交所成交金額", "L4": "央行", "L5": "證交所",
    "L6": "證期局外資新聞稿", "L7": "證交所（外資及陸資投資類股持股比率表）", "L8": "央行（定存單、M2）",
    "L9": "央行（金融業拆款利率）", "L10": "央行（存款、放款）",
    "T1": "證交所加權指數", "T2": "證交所加權指數", "T3": "證交所加權指數", "T4": "證交所加權指數",
    "T5": "自算（上市櫃日線）", "T6": "自算（上市櫃日線）", "T7": "自算（上市櫃日線）", "T8": "證交所加權指數",
    "T9": "Yahoo ^VIX", "T10": "期交所", "T11": "證交所加權指數", "T12": "證交所加權指數", "T13": "證交所加權指數",
}
BAND_CLS = {"過冷": "b0", "偏冷": "b1", "中性": "b2", "偏熱": "b3", "過熱": "b4"}
WD = "一二三四五六日"


def load_research(path: Path = RES) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _md(d: str | None) -> str:
    if not d:
        return "—"
    if len(d) == 7:
        return f"{int(d[:4])}/{int(d[5:])} 月"
    x = date.fromisoformat(d)
    return f"{x.month}/{x.day}（{WD[x.weekday()]}）"


def _ymd(d: str | None) -> str:
    if not d:
        return "—"
    return f"{int(d[:4])}/{int(d[5:7])}" + (f"/{int(d[8:10])}" if len(d) >= 10 else "")


def _fmt(k: str, v) -> str:
    if v is None:
        return "—"
    dec = DEC.get(k, 2)
    s = f"{abs(v):,.{dec}f}"
    sign = "−" if v < 0 else ("+" if k in SIGNED and v > 0 else "")
    unit = S.IND[S.KEYS.index(k)][3]
    if unit == "%":
        return f"{sign}{s}%"
    return f"{sign}{s}" + (f" {unit}" if unit else "")


def _src_date(B: dict, k: str, t: int) -> str | None:
    if S.FREQ_OF[k] == "m":
        return B["ym"][k][t]
    ks = sorted(B["nat"].get(k) or {})
    day = B["cal"][t]
    j = (bisect.bisect_left(ks, day) if k in S.US else bisect.bisect_right(ks, day)) - 1
    return ks[j] if j >= 0 else None


def _ev(d: dict | None, h: int) -> dict:
    d = d or {}
    return d.get(str(h)) or d.get(h) or {}


def view(B: dict | None = None, R: dict | None = None) -> dict:
    B = B if B is not None else C.build()
    R = R if R is not None else (load_research() or {})
    if R.get("ver") != S.VER:                      # 舊版研究檔（第二版三條線）不用
        R = {}
    cal, px = B["cal"], B["px"]
    T = len(cal)
    t = T - 1
    t0 = max(0, t - WEEK)
    a = max(0, T - TREND_DAYS)
    dims = {}
    for dim, L in S.DIMS.items():
        rd = (R.get("dims") or {}).get(dim) or {}
        keys = S.ITEMS[dim]
        hn = {k: B["hc"][k][t] for k in keys}
        ha = {k: B["hc"][k][t0] for k in keys}
        cn, ca = H.contrib(hn, keys), H.contrib(ha, keys)
        items = []
        for k in keys:
            ind = S.IND[S.KEYS.index(k)]
            prox = k in B["proxy"] and bool(B["proxy"][k][t])
            heat = B["heat"][k][t]
            why = None
            if heat is None:
                why = WHY.get(k) or ("沒有最新資料" if B["raw"][k][t] is None else "歷史還不夠")
            items.append({
                "k": k, "name": ind[2], "how": ind[6], "hot": ind[4], "freq": ind[5],
                "val": _fmt(k, B["raw"][k][t]), "src": _src_date(B, k, t), "heat": heat, "ago": B["heat"][k][t0],
                "proxy": prox, "why": why,
                "pull": (cn.get(k) or {}).get("pull"), "share": (cn.get(k) or {}).get("share"),
                "dpull": cn[k]["pull"] - ca[k]["pull"] if k in cn and k in ca else None,
                "first": (rd.get("first") or {}).get(k), "ev": (rd.get("items") or {}).get(k) or {},
            })
        comp = B["comp"][dim]
        sc = comp[t] if T else None
        dims[dim] = {"name": L["name"], "hot": L["hot"], "span": L["span"], "fwd": L["fwd"], "freq": L["freq"],
                     "score": sc, "ago": comp[t0] if T else None, "band": S.band(sc), "items": items, "n_have": len(cn),
                     "cev": rd.get("comp") or {}, "first": next((cal[i] for i, v in enumerate(comp) if v is not None), None),
                     "trend": [None if v is None else round(v, 1) for v in comp[a:]]}
    ta = None
    if T > S.EV_START:
        ev = TT.all_events(px)
        lo = max(0, t - TA_RECENT + 1)
        recent = sorted(((i, k) for k, ix in ev.items() for i in ix if i >= lo), reverse=True)
        ta = {"lv": TT.levels(px, cal), "recent": [(cal[i], k) for i, k in recent],
              "last": {k: (cal[ix[-1]] if ix else None) for k, ix in ev.items()}, "study": R.get("events") or {},
              "next": next_days(cal[t], S.DEDUCT_N)}
    return {"asof": cal[t] if cal else None, "dims": dims, "tdates": cal[a:], "tpx": px[a:], "R": R,
            "data": R.get("data") or {}, "cal_info": B.get("cal_info"), "vixcorr": B.get("vixcorr") or {}, "ta": ta}


def next_days(d: str, n: int) -> list[str]:
    """d 之後 n 個交易日（跳過週末與證交所休市日；官方表沒涵蓋的年份只跳週末）。"""
    from datetime import timedelta
    from .. import twholidays
    out, x = [], date.fromisoformat(d)
    while len(out) < n:
        x += timedelta(days=1)
        if x.weekday() < 5 and not twholidays.is_closed(x):
            out.append(x.isoformat())
    return out


# ── HTML ─────────────────────────────────────────────────────────────

def _e(x) -> str:
    return html.escape(str(x), quote=True)


def _pct(x, dec=1, sign=True) -> str:
    if x is None:
        return "—"
    r = round(x, dec)                              # 先取位數再判正負，不寫「−0.0」
    return ("−" if r < 0 else ("+" if sign and r > 0 else "")) + f"{abs(r):.{dec}f}%"


def _sgn(x, dec=1) -> str:
    if x is None:
        return "—"
    r = round(x, dec)
    return ("+" if r > 0 else ("−" if r < 0 else "")) + f"{abs(r):.{dec}f}"


def _bar(h: float | None) -> str:
    if h is None:
        return '<span class="hb"><i class="na"></i></span><b class="hn mu">—</b>'
    cls = BAND_CLS.get(S.band(h), "b2")
    return f'<span class="hb"><i class="{cls}" style="width:{h:.0f}%"></i></span><b class="hn">{h:.0f}</b>'


def _meter(score: float | None) -> str:
    seg = "".join(f'<i class="{BAND_CLS[nm]}"></i>' for _, _, nm in S.BANDS)
    mk = "" if score is None else f'<b class="mk" style="left:{score:.1f}%"></b>'
    lab = "".join(f"<span>{_e(nm)}</span>" for _, _, nm in S.BANDS)
    return f'<div class="mt">{seg}{mk}</div><div class="mtl">{lab}</div>'


def _band_of(ev: dict, nm: str | None) -> dict | None:
    for b in ev.get("bands") or []:
        if b.get("band") == nm:
            return b
    return None


def _unit(freq: str) -> str:
    return "個月" if freq == "m" else "天"


def _yrs(ys: list | None) -> str:
    """["2004","2010","2021","2022"] → 「2004、2010、2021–2022」：讓人看出樣本是不是集中在一兩段。"""
    v = sorted({int(y) for y in ys or []})
    out, i = [], 0
    while i < len(v):
        j = i
        while j + 1 < len(v) and v[j + 1] == v[j] + 1:
            j += 1
        out.append(str(v[i]) if i == j else f"{v[i]}–{v[j]}")
        i = j + 1
    return "、".join(out)


def _past(L: dict) -> str:
    """過去面向分數落在現在這一區時，之後加權指數的表現（全期間，兩個持有期間各自的樣本數）。"""
    band = L["band"]
    if band is None:
        return ""
    parts, allp, yrs, start = [], [], set(), None
    for h in L["fwd"]:
        e = _ev(L["cev"], h)
        b, al = _band_of(e, band), _band_of(e, "全部")
        if not b or not b.get("n") or not al or not al.get("n"):
            continue
        start = start or (e.get("a") or "")[:4]
        yrs |= set(b.get("yrs") or [])
        parts.append(f"之後 {h} 日（{b['n']:,} {_unit(L['freq'])}）加權指數平均 {_pct(b['avg'])}、上漲機率 {b['up']:.0f}%、"
                     f"期間最大跌幅中位數 {_pct(b['dd'])}")
        allp.append(f"{h} 日 {_pct(al['avg'])}")
    if not parts:
        return ""
    where = f"，出現在 {_e(_yrs(sorted(yrs)))} 年" if yrs else ""
    return (f"過去分數在「{_e(band)}」時（{_e(start)} 年起的資料{where}）："
            + "；".join(parts) + "。所有日子：" + "、".join(allp) + "。")


def _verdict_line(L: dict) -> str:
    vs = []
    for h in L["fwd"]:
        v = _ev(L["cev"], h).get("verdict")
        if v:
            vs.append(f"之後 {h} 日<b>{_e(S.VERDICT.get(v, '—'))}</b>")
    if not vs:
        return ""
    return f'<p class="vd">過去關係（只當參考，不拿來刪項目）：{"、".join(vs)}。</p>'


def _items(L: dict) -> str:
    out = ['<div class="ith"><span>項目</span><span>0～100</span><span>拉動分數</span><span>佔比</span><span>本週</span></div>']
    have = sorted((it for it in L["items"] if it["pull"] is not None), key=lambda x: -abs(x["pull"]))
    rest = [it for it in L["items"] if it["pull"] is None]
    for it in have + rest:
        pull = "—" if it["pull"] is None else f'{_sgn(it["pull"])} 分'
        sh = "—" if it["share"] is None else f'{it["share"]:.0f}%'
        dp = _sgn(it["dpull"])
        tag = ""
        if it["proxy"]:
            tag = '<em class="px">用美國 VIX 的排名代替，不算進分數</em>'
        elif it["why"]:
            tag = f'<em class="px">{_e(it["why"])}</em>'
        cls = "it" if it["pull"] is not None else "it it0"
        out.append(f'<div class="{cls}"><span class="inm"><b>{_e(it["name"])}</b><i>{_e(it["val"])}・{_e(_md(it["src"]))}</i>{tag}</span>'
                   f'<span class="ihb">{_bar(it["heat"])}</span><span class="ipl">{pull}</span>'
                   f'<span class="ish">{sh}</span><span class="iwk">{dp}</span></div>')
    return "".join(out)


def _card(dim: str, L: dict, V: dict) -> str:
    sc = L["score"]
    head = (f'<b class="sc {BAND_CLS.get(L["band"], "b2")}">{sc:.0f}</b><span class="bn {BAND_CLS.get(L["band"], "b2")}">{_e(L["band"])}</span>'
            if sc is not None else '<b class="sc mu">—</b><span class="bn mu">還沒有分數</span>')
    wk = ""
    if sc is not None and L["ago"] is not None:
        wk = f'<span class="wk">和上週比 {_sgn(sc - L["ago"], 0)}</span>'
    eq = ""
    if sc is not None:
        s = sum(it["pull"] for it in L["items"] if it["pull"] is not None)
        extra = "；台指 VIX 用美國 VIX 代替的日子不算" if dim == "tech" else ""
        eq = (f'<p class="eq">分數 {sc:.1f} ＝ 50 ＋ 各項拉動合計 {_sgn(s)}（{L["n_have"]} 項有值，等權平均；'
              f'每項拉動＝（0～100 − 50）÷ 有值的項數{extra}）</p>')
    else:
        need = H.need(len(L["items"]))
        eq = f'<p class="eq">有值的項目不到 {need} 項（{len(L["items"])} 項的 2/3），不給分數。</p>'
    vx = ""
    vc = V.get("vixcorr") or {}
    if dim == "tech" and vc.get("n"):
        r = "—" if vc.get("r") is None else f'{vc["r"]:.2f}'
        vx = (f'<p class="note">台指 VIX 從 {_e(_ymd(vc.get("a")))} 起才有資料（{vc["n"]} 天），和美國 VIX 的相關係數 {r}；'
              f'自己的歷史滿 {S.PCT_MIN["d"]} 個交易日後改用自己的排名並算進分數。</p>')
    return (f'<section class="cd" id="c-{dim}"><div class="ch"><h2>{_e(L["name"])}<span class="sub">{_e(L["span"])}</span></h2>'
            f'<div class="sv">{head}{wk}</div></div><p class="hot">熱＝{_e(L["hot"])}</p>{_meter(sc)}'
            f'<p class="past">{_past(L) if sc is not None else ""}</p>{_verdict_line(L)}{eq}'
            f'<div class="its">{_items(L)}</div>{vx}</section>')


def _tiles(V: dict) -> str:
    out = []
    for dim, L in V["dims"].items():
        sc = L["score"]
        cls = BAND_CLS.get(L["band"], "b2")
        num = f'<b class="sc {cls}">{sc:.0f}</b><span class="bn {cls}">{_e(L["band"])}</span>' if sc is not None else \
            '<b class="sc mu">—</b><span class="bn mu">沒有分數</span>'
        wk = f'和上週比 {_sgn(sc - L["ago"], 0)}' if sc is not None and L["ago"] is not None else "&nbsp;"
        out.append(f'<a class="tile" href="#c-{dim}"><span class="tl-n">{_e(L["name"])}</span><span class="tl-v">{num}</span>'
                   f'<span class="tl-w">{wk}</span><span class="tl-s">{_e(L["span"])}</span></a>')
    return f'<div class="tiles">{"".join(out)}</div>'


def _chart(V: dict) -> str:
    W, Hh, P = 720, 210, 28
    ds, px = V["tdates"], V["tpx"]
    n = len(ds)
    if n < 2:
        return ""
    xs = lambda i: P + (W - 2 * P) * i / (n - 1)          # noqa: E731
    ys = lambda v: 10 + (Hh - 30) * (1 - v / 100)         # noqa: E731
    out = [f'<svg viewBox="0 0 {W} {Hh}" role="img" aria-label="五個面向的走勢">']
    for v in (20, 40, 60, 80):
        out.append(f'<line x1="{P}" x2="{W - P}" y1="{ys(v):.1f}" y2="{ys(v):.1f}" class="gl"/>'
                   f'<text x="{W - P + 4}" y="{ys(v) + 4:.1f}" class="gt">{v}</text>')
    pv = [p for p in px if p]
    if pv:
        lo, hi = min(pv), max(pv)
        pts = " ".join(f"{xs(i):.1f},{ys(100 * (p - lo) / (hi - lo or 1)):.1f}" for i, p in enumerate(px) if p)
        out.append(f'<polyline points="{pts}" class="lpx"/>')
    for dim, L in V["dims"].items():
        tr = L.get("trend") or []
        seg, segs = [], []
        for i, v in enumerate(tr):
            if v is None:
                if seg:
                    segs.append(seg)
                seg = []
            else:
                seg.append(f"{xs(i):.1f},{ys(v):.1f}")
        if seg:
            segs.append(seg)
        out += [f'<polyline points="{" ".join(sg)}" class="{LINE_CLS[dim]}"/>' for sg in segs if len(sg) > 1]
    for i in range(0, n, max(1, n // 6)):
        out.append(f'<text x="{xs(i):.1f}" y="{Hh - 4}" class="gt" text-anchor="middle">{_e(ds[i][:7])}</text>')
    out.append("</svg>")
    lg = "".join(f'<span><i class="{LINE_CLS[dim]}"></i>{_e(NAV[dim])}</span>' for dim, L in V["dims"].items()
                 if any(v is not None for v in (L.get("trend") or [])))
    return "".join(out) + f'<div class="lg">{lg}<span><i class="lpx"></i>加權指數（換算成同一高度）</span></div>'


def _band_table(ev: dict, h: int, freq: str) -> str:
    bs = ev.get("bands") or []
    if not bs:
        return '<p class="note">沒有資料。</p>'

    def up(b):
        return "—" if b.get("up") is None else f'{b["up"]:.0f}%'
    rows = "".join(f'<tr><td>{_e(b["band"])}</td><td>{b["n"]:,}</td><td>{_pct(b["avg"], 2)}</td><td>{_pct(b["med"], 2)}</td>'
                   f'<td>{up(b)}</td><td>{_pct(b["dd"], 2)}</td><td class="l">{_e(_yrs(b.get("yrs")) or "—")}</td></tr>'
                   for b in bs)
    return (f'<div class="tw"><table><tr><th>分數區間</th><th>樣本（{_unit(freq)}）</th><th>之後 {h} 日平均</th><th>中位數</th>'
            f'<th>上漲機率</th><th>期間最大跌幅中位數</th><th class="l">出現在哪幾年</th></tr>{rows}</table></div>')


def _rho(e: dict) -> str:
    if e.get("rho") is None:
        return "—"
    ci = f'［{e["lo"]:+.2f}, {e["hi"]:+.2f}］' if e.get("lo") is not None else ""
    return f'{e["rho"]:+.2f}{ci}'


def _r(x) -> str:
    return "—" if x is None else f"{x:+.2f}"


def _refc(r: dict | None, freq: str) -> str:
    r = r or {}
    if not r.get("n"):
        return "—"
    return f'{_r(r.get("rho"))}<span class="hw">{r["n"]:,} {_unit(freq)}</span>'      # 樣本太少的對照數字要看得出來


def _vrow(name: str, first: str | None, e: dict, freq: str) -> str:
    h1, h2 = e.get("h1") or {}, e.get("h2") or {}
    ref = (e.get("ref") or []) + [{}, {}]
    return (f'<tr><td class="l">{_e(name)}</td><td>{_e(_ymd(first))}</td><td>{e.get("n", 0):,}</td><td>{_rho(e)}</td>'
            f'<td>{_r(h1.get("rho"))}</td><td>{_r(h2.get("rho"))}</td>'
            f'<td class="l">{_e(S.VERDICT.get(e.get("verdict"), "—"))}</td>'
            f'<td>{_refc(ref[0], freq)}</td><td>{_refc(ref[1], freq)}</td></tr>')


def _valid(dim: str, L: dict) -> str:
    ref = S.SPLIT_REF[L["freq"]]
    r0 = f'{ref[0][0][:4]}–{ref[0][1][:4]}'
    r1 = f'{ref[1][0][:4]} 起'
    out = [f'<div class="vsec"><h3>{_e(L["name"])}<span class="sub">{"每月最後一個交易日一個樣本" if L["freq"] == "m" else "每天一個樣本"}</span></h3>']
    for h in L["fwd"]:
        ce = _ev(L["cev"], h)
        rows = ([_vrow("面向分數", L["first"], ce, L["freq"])]
                + [_vrow(it["name"], it["first"], _ev(it["ev"], h), L["freq"]) for it in L["items"]])
        out.append(f'<h4>之後 {h} 個交易日：面向分數各區</h4>{_band_table(ce, h, L["freq"])}'
                   f'<h4>之後 {h} 個交易日：各項</h4><div class="tw"><table><tr><th class="l">項目</th><th>有分數起</th><th>樣本</th>'
                   f'<th>等級相關［95% 信賴區間］</th><th>前一半</th><th>後一半</th><th class="l">判定</th>'
                   f'<th>對照 {_e(r0)}</th><th>對照 {_e(r1)}</th></tr>{"".join(rows)}</table></div>')
    out.append("</div>")
    return "".join(out)


def _hist(it: dict, fwd: tuple) -> str:
    """這一項自己的分區統計：目前所在的區，過去之後的加權指數平均（全期間）。"""
    band = S.band(it["heat"])
    if band is None:
        return "—"
    parts, allp = [], []
    for h in fwd:
        e = _ev(it["ev"], h)
        b, al = _band_of(e, band), _band_of(e, "全部")
        if b and b.get("n") and al and al.get("n"):
            parts.append(f"{h} 日 {_pct(b['avg'])}")
            allp.append(_pct(al["avg"]))
    if not parts:
        return f"<b>{_e(band)}</b>"
    return f'<b>{_e(band)}</b>：{"｜".join(parts)}<span class="hw">所有日子 {"／".join(allp)}</span>'


def _detail(L: dict) -> str:
    rows = []
    for it in L["items"]:
        d = None if it["heat"] is None or it["ago"] is None else it["heat"] - it["ago"]
        hv = "—" if it["heat"] is None else f'{it["heat"]:.0f}'
        rows.append(f'<tr><td class="l"><b>{_e(it["name"])}</b><span class="hw">{_e(it["how"])}</span></td>'
                    f'<td>{_e(it["val"])}</td><td>{hv}</td><td>{_sgn(d, 0)}</td><td>{"高＝熱" if it["hot"] > 0 else "低＝熱"}</td>'
                    f'<td class="l">{_hist(it, L["fwd"])}</td><td>{_e(_md(it["src"]))}</td>'
                    f'<td class="l">{_e(SRC.get(it["k"], ""))}</td></tr>')
    return (f'<div class="tw"><table class="dt"><tr><th class="l">{_e(L["name"])}</th><th>現值</th><th>0～100</th><th>5 日變化</th>'
            f'<th>熱的方向</th><th class="l">目前這一區，過去之後加權指數平均</th><th>資料日</th>'
            f'<th class="l">來源</th></tr>{"".join(rows)}</table></div>')


def _num0(v) -> str:
    return "—" if v is None else f"{v:,.0f}"


DIRW = {1: "上揚", -1: "下彎", 0: "持平", None: "—"}
_ST = {   # 狀態：（+1 的說法, −1 的說法, 變成 +1 叫什麼, 變成 −1 叫什麼）
    "ma20": ("收在月線上", "收在月線下", "站回月線", "跌破月線"),
    "ma60": ("收在季線上", "收在季線下", "站回季線", "跌破季線"),
    "ma240": ("收在年線上", "收在年線下", "站回年線", "跌破年線"),
    "x": ("月線在季線上方", "月線在季線下方", "黃金交叉", "死亡交叉"),
    "s60": ("季線上揚", "季線下彎", "季線轉上揚", "季線轉下彎"),
}


def _st_text(key: str, st: dict) -> str:
    if not st or st.get("side") not in (1, -1):
        return "—"
    up, dn, to_up, to_dn = _ST[key]
    s = st["side"]
    txt = f'{up if s > 0 else dn}第 {st["n"]} 天'
    if st.get("pending"):
        k = S.EV_CONF - st["n"]
        txt += f'（前 {st["prev"]} 個交易日{dn if s > 0 else up}；再 {k} 天就算<b>{to_up if s > 0 else to_dn}</b>）'
    return txt


def _evc(r: dict | None, h: int) -> str:
    r = r or {}
    if not r.get("n"):
        return "<td>—</td><td>—</td><td class=\"l\">—</td>"
    avg = f'{_pct(100 * r["avg"], 2)}<span class="hw">上漲 {100 * r["up"]:.0f}%</span>'
    ci = ""
    if r.get("lo") is not None:
        ci = f'<span class="hw">［{_pct(100 * r["lo"], 2)}, {_pct(100 * r["hi"], 2)}］</span>'
    d = f'{_pct(100 * r["diff"], 2)}{ci}' if r.get("diff") is not None else "—"
    return f'<td>{avg}</td><td>{d}</td><td class="l">{_e(S.EV_VERDICT.get(r.get("verdict"), "—"))}</td>'


def _ta(V: dict) -> str:
    ta = V.get("ta")
    if not ta:
        return ""
    lv = ta["lv"]
    rows = []
    for n, key in ((20, "ma20"), (60, "ma60"), (120, None), (240, "ma240")):
        m = lv["ma"][n]
        rows.append(f'<tr><td class="l">{_e(S.MA_NAME[n])}（{n} 日）</td><td>{_num0(m["v"])}</td>'
                    f'<td>{_pct(m["dist"])}</td>'
                    f'<td>{DIRW.get(m["dir"], "—")}</td><td class="l">{_st_text(key, lv["st"].get(key)) if key else ""}</td></tr>')
    ded = "、".join(f'{_e(_md(d)[:-3])} {_num0(x["v"])}' for d, x in zip(ta["next"], lv["deduct"]))
    hi, lo = lv.get("hi"), lv.get("lo")
    piv = []
    if hi:
        piv.append(f'前波高點 {_num0(hi["p"])}（{_e(_ymd(hi["d"]))}）')
    if lo:
        piv.append(f'前波低點 {_num0(lo["p"])}（{_e(_ymd(lo["d"]))}）')
    sr = []
    for key, nm in (("sup", "下方最近的支撐"), ("res", "上方最近的壓力")):
        x = lv.get(key)
        if x:
            when = f'（{_e(_ymd(x["d"]))}）' if x.get("d") else ""
            sr.append(f'{nm}：{_e(x["what"])}{when} {_num0(x["v"])}（距離 {_pct(x["dist"])}）')
    lis = [f'<li>月線季線：{_st_text("x", lv["st"].get("x"))}。</li>',
           f'<li>季線方向：{_st_text("s60", lv["st"].get("s60"))}。之後 {S.DEDUCT_N} 個交易日的扣抵值：{ded}'
           f'（收盤高於扣抵值，季線就往上）。</li>']
    if piv:
        lis.append(f'<li>{"、".join(piv)}（收盤回落／反彈 5% 才確認是高點／低點）。</li>')
    if sr:
        lis.append(f'<li>{"；".join(sr)}。</li>')
    rec = "、".join(f'{_e(_md(d))} {_e(S.EVENTS[k])}' for d, k in ta["recent"]) or "沒有"
    st = ta.get("study") or {}
    allr = ""
    any_ev = next((v for v in st.values() if v), None)
    if any_ev:
        a10, a60 = any_ev.get("10") or {}, any_ev.get("60") or {}
        if a10.get("all_avg") is not None and a60.get("all_avg") is not None:
            allr = (f'所有交易日（{_e((a10.get("a") or "1998")[:4])} 年起）：之後 10 日平均 {_pct(100 * a10["all_avg"], 2)}'
                    f'（上漲 {100 * a10["all_up"]:.0f}%）、60 日 {_pct(100 * a60["all_avg"], 2)}（上漲 {100 * a60["all_up"]:.0f}%）。')
    trs = []
    for k, nm in S.EVENTS.items():
        e = st.get(k) or {}
        e10, e60 = e.get("10") or {}, e.get("60") or {}
        n = e10.get("n") or e60.get("n") or 0
        last = ta["last"].get(k)
        trs.append(f'<tr><td class="l">{_e(nm)}</td><td>{n:,}</td><td>{_e(_ymd(last))}</td>{_evc(e10, 10)}{_evc(e60, 60)}</tr>')
    table = (f'<div class="tw"><table class="evt"><tr><th class="l">事件</th><th>次數</th><th>最近一次</th>'
             f'<th>之後 10 日平均</th><th>和所有日子差［95% 信賴區間］</th><th class="l">判定</th>'
             f'<th>之後 60 日平均</th><th>和所有日子差［95% 信賴區間］</th><th class="l">判定</th></tr>{"".join(trs)}</table></div>'
             if st else '<p class="warn">事件研究還沒產生（data/lab/heat_research.json）。</p>')
    return (f'<section class="cd" id="ta"><div class="ch"><h2>關鍵價位與事件<span class="sub">加權指數 {_e(_md(lv["t"]))}收盤 '
            f'{_num0(lv["close"])}；不進分數，只描述位置</span></h2></div>'
            f'<p class="hot">均線是收盤的簡單平均。跌破、站回、交叉、季線轉向一律要「之前 {S.EV_PRIOR} 個交易日是原來的狀態、'
            f'連 {S.EV_CONF} 個交易日是新狀態」才算，第 {S.EV_CONF} 天是事件日。</p>'
            f'<div class="tw"><table class="lvt"><tr><th class="l">均線</th>'
            f'<th>數值</th><th>距離</th><th>方向</th><th class="l">現在的狀態</th></tr>{"".join(rows)}</table></div>'
            f'<ul class="tal">{"".join(lis)}</ul>'
            f'<h3>近 {TA_RECENT} 個交易日的事件</h3><p class="rec">{rec}</p>'
            f'<h3>事件之後加權指數的表現<span class="sub">只當參考，不當買賣訊號</span></h3>'
            f'<p class="note">{allr}型態（M 頭、W 底、頭肩）用收盤轉折點認，收盤跌破／突破頸線那天才算成立。'
            f'16 種事件 × 2 個期間＝32 個比較，就算全是運氣也會有一兩個看起來「顯著」；判定要信賴區間不含 0、'
            f'前後兩半方向一樣才寫，事件少於 {S.EV_MIN} 次寫「樣本不足」。</p>{table}</section>')


def render(V: dict) -> str:
    Ds = V["dims"]
    asof = V["asof"]
    R = V.get("R") or {}
    nores = "" if R.get("dims") else '<p class="warn">驗證結果還沒產生（data/lab/heat_research.json），先只列各項的 0～100。</p>'
    data_rows = "".join(f'<tr><td class="l">{_e(k)}</td><td>{v[0]:,}</td><td>{_e(v[1] or "—")}</td><td>{_e(v[2] or "—")}</td></tr>'
                        for k, v in sorted((V.get("data") or {}).items()))
    firsts = "、".join(f'{NAV[d]} {_ymd(L["first"])}' for d, L in Ds.items() if L["first"])
    body = (
        _tiles(V) + f'<p class="hz">{_e(S.HORIZON_NOTE)}。<span class="mu">（資料到 {_e(_md(asof))}）</span></p>{nores}'
        + "".join(_card(d, Ds[d], V) for d in Ds) + _ta(V)
        + f'<section class="sec" id="trend"><h2>五個面向的走勢<span class="sub">近 {TREND_DAYS} 個交易日</span></h2>{_chart(V)}</section>'
        + '<section class="sec" id="detail"><h2>各項明細</h2>' + "".join(_detail(Ds[d]) for d in Ds) + "</section>"
        + '<section class="sec" id="valid"><h2>驗證</h2>' + _METHOD
        + (f'<p class="note">面向分數最早從哪天有：{_e(firsts)}。</p>' if firsts else "")
        + "".join(_valid(d, Ds[d]) for d in Ds) + "</section>"
        + f'<section class="sec" id="src"><h2>資料來源與筆數</h2><div class="tw"><table><tr><th class="l">檔</th><th>筆數</th>'
          f'<th>起</th><th>到</th></tr>{data_rows}</table></div><p class="note">{_e(_SRC_NOTE)}</p></section>'
    )
    nav = "".join(f'<a href="#c-{d}">{_e(NAV[d])}</a>' for d in Ds) + ('<a href="#ta">價位事件</a>' if V.get("ta") else "")
    return (_HTML.replace("{{CSS}}", _CSS).replace("{{ASOF}}", _e(_md(asof))).replace("{{NAV}}", nav)
            .replace("{{BODY}}", body))


def build(out: Path = OUT) -> bool:
    text = render(view())
    if out.exists() and out.read_text(encoding="utf-8") == text:
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return True


_SRC_NOTE = ("融資融券、法人、期貨選擇權法人：FinMind（轉載證交所、期交所）；成交金額與加權指數：證交所；P/C 比、台指 VIX：期交所；"
             "新台幣、M1B／M2：央行；景氣燈號、領先指標、PMI、海關出口值：國發會；外銷訂單：經濟部；台灣 CPI：主計總處；"
             "上市櫃營收：公開資訊觀測站月營收（自算合計）；美國 CPI：勞工統計局；公債殖利率：美國財政部；"
             "聯邦基金利率：聯準會 H.15（DBnomics 轉載）與紐約聯準銀行；VIX、HYG、IEF、S&P 500：Yahoo；美國貨幣基金：OFR；"
             "外資持股比率：證交所；外資淨匯入：證期局新聞稿；央行定存單、存放款、拆款利率：央行統計資料庫；"
             "投信基金持股比重：投信投顧公會。"
             "廣度用上市櫃日線自算（當天最近一個月底市值 40 億以上的股票）。")

_METHOD = (
    '<div class="mth"><p><b>分數怎麼來</b>：每一項和自己過去比——今天的值在過去 3 年（月資料用 10 年）裡排第幾（只用今天以前的資料），'
    '依「熱的方向」換成 0～100。面向分數＝該面向全部項目的 0～100 平均，有值的項數要有 2/3 以上。</p>'
    '<p><b>驗證只當參考，不拿來刪項目</b>：看分數和之後加權指數漲跌的等級相關（全期間＋95% 信賴區間），再把同一批樣本依日期切成前後兩半各算一次；'
    '全期間信賴區間不含 0、而且兩半方向一樣，才寫「熱了之後較弱」或「熱了之後較強」，其他寫「看不出穩定關係」。'
    '「對照」兩欄是第一階段的切分，只列數字。</p>'
    '<p><b>等級相關</b>：負數＝分數越高，之後漲幅越小；正數相反。數字都很小是正常的，這頁是參考讀數。</p>'
    '<p><b>限制</b>：國發會資料用修正後的數字（兩個月後才算拿得到）；PMI、月營收從 2012 年、期貨選擇權法人從 2018 年、'
    '投信基金持股比重從 2021 年 10 月、美國貨幣基金從 2010 年 11 月、台指 VIX 從 2026 年 7 月、外資淨匯入從 2026 年 9 月才有資料，'
    '歷史不夠的照樣列出，但要等排名有 3 年（月資料 5 年）的歷史才有 0～100。'
    '美國 ICI 的基金現金比率在 CI 連不上、央行沒有公開超額準備的序列，改用央行定存單餘額 ÷ M2。</p></div>')

_HTML = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>景氣溫度</title>
<style>{{CSS}}</style></head>
<body>
<div class="top"><b>景氣溫度</b><span class="asof">台股，資料到 {{ASOF}}</span><a class="back" href="x9.html">籌碼雷達</a><a class="back" href="./">返回主頁</a></div>
<p class="purp">五個面向分開看，各一個 0～100（100 最熱）：基本面、籌碼、全球資金、台灣資金、技術。每一項都和自己的過去比，面向分數＝該面向全部項目的平均；技術面另附關鍵價位與破線、型態事件。頁面只描述現在熱不熱、過去同樣情況之後大盤的表現，怎麼操作由你判斷。</p>
<nav class="snav">{{NAV}}<a href="#trend">走勢</a><a href="#detail">明細</a><a href="#valid">驗證</a><a href="#src">來源</a></nav>
<main>{{BODY}}</main>
</body></html>
"""

_CSS = """
:root{--bg:#fff;--card2:#f4f6fa;--ink:#1f2733;--ink2:#44505f;--mut:#727e8c;--line:#e8ebf1;--acc:#2563c9;--accd:#1c4fa8;
--c0:#2f6fb5;--c1:#7fb0de;--c2:#b8c0cc;--c3:#f0a35a;--c4:#d33a34;--warn:#b45309}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 -apple-system,"PingFang TC","Noto Sans TC",Segoe UI,sans-serif;-webkit-text-size-adjust:100%}
a{color:var(--acc);text-decoration:none}
table,.num{font-variant-numeric:tabular-nums}
.top{display:flex;align-items:baseline;gap:4px 12px;flex-wrap:wrap;padding:10px 16px 4px;max-width:1080px;margin:0 auto}
.top b{font-size:18px}.asof{color:var(--mut);font-size:12.5px;flex:1;min-width:0}
.back{font-size:13px;color:var(--mut);white-space:nowrap}
.purp{max-width:1080px;margin:0 auto;padding:0 16px 6px;color:var(--ink2);font-size:13.5px;line-height:1.75}
.snav{position:sticky;top:0;z-index:5;background:var(--bg);display:flex;gap:4px;overflow-x:auto;scrollbar-width:none;padding:6px 16px 7px;border-bottom:1px solid var(--line);max-width:1080px;margin:0 auto}
.snav::-webkit-scrollbar{display:none}
.snav a{padding:2px 10px;border-radius:12px;color:var(--ink2);font-size:13px;white-space:nowrap;background:var(--card2)}
main{padding:14px 16px 80px;max-width:1080px;margin:0 auto}
.mu{color:var(--mut)}.warn{color:var(--warn);font-size:13.5px}
.tiles{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin:2px 0 8px}
.tile{display:flex;flex-direction:column;gap:2px;border:1px solid var(--line);border-radius:12px;padding:10px 12px;color:var(--ink)}
.tl-n{font-size:13.5px;font-weight:700}.tl-v{display:flex;align-items:baseline;gap:6px}
.tl-w{font-size:12px;color:var(--mut)}.tl-s{font-size:11.5px;color:var(--mut)}
.hz{font-size:13px;color:var(--ink2);margin:0 0 16px;line-height:1.75}.hz .mu{margin-left:4px}
.cd{border:1px solid var(--line);border-radius:14px;padding:12px 16px 14px;margin:0 0 18px;scroll-margin-top:48px}
.ch{display:flex;align-items:flex-start;flex-wrap:wrap;gap:4px 12px}
.ch h2{margin:0;font-size:17px;flex:1;min-width:0}.ch h2 .sub,.sec h2 .sub,h3 .sub{font-size:12.5px;font-weight:400;color:var(--mut);margin-left:8px}
.sv{display:flex;align-items:baseline;gap:8px}.sc{font-size:34px;line-height:1;font-weight:800}.bn{font-weight:700}
.tile .sc{font-size:30px}
.sc.b0,.bn.b0{color:var(--c0)}.sc.b1,.bn.b1{color:#3f7fc0}.sc.b2,.bn.b2{color:var(--ink2)}.sc.b3,.bn.b3{color:#c26a16}.sc.b4,.bn.b4{color:var(--c4)}
.wk{font-size:12.5px;color:var(--mut)}
.hot{font-size:12.5px;color:var(--mut);margin:4px 0 0}
.mt{position:relative;display:grid;grid-template-columns:repeat(5,1fr);gap:2px;height:10px;margin:10px 0 2px}
.mt i{display:block;border-radius:3px}.mt .b0{background:var(--c0)}.mt .b1{background:var(--c1)}.mt .b2{background:var(--c2)}.mt .b3{background:var(--c3)}.mt .b4{background:var(--c4)}
.mt .mk{position:absolute;top:-5px;width:4px;height:20px;margin-left:-2px;background:var(--ink);border-radius:2px;box-shadow:0 0 0 2px #fff}
.mtl{display:grid;grid-template-columns:repeat(5,1fr);font-size:11px;color:var(--mut);text-align:center}
.past{font-size:13.5px;color:var(--ink2);margin:8px 0 2px;line-height:1.75}
.vd{font-size:13.5px;margin:2px 0}.eq{font-size:12px;color:var(--mut);margin:2px 0 8px}
.its{margin-top:6px}
.ith,.it{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(120px,1.3fr) 72px 48px 48px;gap:8px;align-items:center;padding:6px 2px;border-bottom:1px solid var(--line)}
.ith{font-size:11.5px;color:var(--mut);border-bottom:2px solid var(--line);padding-top:8px}
.ith span:nth-child(n+3),.ipl,.ish,.iwk{text-align:right;white-space:nowrap}
.inm{min-width:0;display:flex;flex-direction:column;line-height:1.35}.inm b{font-weight:600;font-size:14px}.inm i{font-style:normal;color:var(--mut);font-size:12px}
.inm em.px{font-style:normal;color:var(--warn);font-size:11.5px}
.it0 .ipl,.it0 .ish,.it0 .iwk{color:var(--mut);font-weight:400}
.ihb{display:flex;align-items:center;gap:8px}.hb{flex:1;height:8px;background:var(--card2);border-radius:4px;overflow:hidden;min-width:60px}
.hb i{display:block;height:100%;border-radius:4px}.hb .b0{background:var(--c0)}.hb .b1{background:var(--c1)}.hb .b2{background:var(--c2)}.hb .b3{background:var(--c3)}.hb .b4{background:var(--c4)}
.hn{width:2.2em;text-align:right;font-size:14px}
.ipl{font-weight:700}.ish,.iwk{font-size:13px;color:var(--ink2)}
.sec{margin:28px 0 0;scroll-margin-top:48px}.sec>h2{font-size:17px;margin:0 0 10px}
svg{display:block;width:100%;height:auto}
svg .gl{stroke:var(--line);stroke-width:1}svg .gt{font-size:11px;fill:var(--mut)}
svg polyline{fill:none;stroke-width:2}svg .l1{stroke:#2f6fb5}svg .l2{stroke:#d33a34}svg .l3{stroke:#2a9d6f}svg .l4{stroke:#c26a16}svg .l5{stroke:#7b5ea7}
svg .lpx{stroke:#9aa3ae;stroke-width:1.2;stroke-dasharray:3 3}
.lg{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:12px;color:var(--mut);margin-top:4px}.lg i{display:inline-block;width:16px;height:3px;vertical-align:middle;margin-right:4px}
.lg .l1{background:#2f6fb5}.lg .l2{background:#d33a34}.lg .l3{background:#2a9d6f}.lg .l4{background:#c26a16}.lg .l5{background:#7b5ea7}.lg .lpx{background:#9aa3ae}
.lvt td:last-child{white-space:normal;min-width:220px}.tal{margin:8px 0 4px;padding-left:20px;font-size:13.5px;line-height:1.8;color:var(--ink2)}
.rec{font-size:13.5px;color:var(--ink2);margin:2px 0 8px;line-height:1.8}
.evt td:first-child{white-space:nowrap}
.tw{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:0 0 14px}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap;vertical-align:top}
th{background:var(--card2);color:var(--mut);font-weight:600;font-size:12px}
td.l,th.l{text-align:left}
table.dt td:first-child{white-space:normal;min-width:170px}.hw{display:block;font-size:11.5px;color:var(--mut);font-weight:400}
h3{font-size:15px;margin:18px 0 6px;color:var(--accd)}h4{font-size:13.5px;margin:10px 0 4px}
.mth p{font-size:13.5px;line-height:1.8;margin:6px 0;color:var(--ink2)}
.note{color:var(--mut);font-size:12px;line-height:1.7}
@media (max-width:640px){
 .tiles{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
 .ith{display:none}
 .it{grid-template-columns:minmax(0,1fr) 64px 78px;row-gap:3px}
 .it .inm{grid-column:1/2;grid-row:1}.it .ihb{grid-column:1/2;grid-row:2}
 .it .ipl{grid-column:2/3;grid-row:1/3;align-self:center}
 .it .ish{grid-column:3/4;grid-row:1}.it .iwk{grid-column:3/4;grid-row:2}
 .it .ish::before{content:"佔比 "}.it .iwk::before{content:"本週 "}
 .sc{font-size:30px}.tile .sc{font-size:26px}
 .ch h2 .sub{display:block;margin-left:0}
 .lvt,.lvt tbody{display:block}.lvt tr:first-child{display:none}
 .lvt tr{display:grid;grid-template-columns:minmax(0,1fr) auto auto auto;gap:2px 12px;padding:7px 2px;border-bottom:1px solid var(--line)}
 .lvt td{border:0;padding:0}
 .lvt td:last-child{grid-column:1/-1;min-width:0;white-space:normal;color:var(--ink2);font-size:12.5px;text-align:left}
 .lvt td:last-child:empty{display:none}
 .evt th:first-child,.evt td:first-child{position:sticky;left:0;background:var(--bg);z-index:1}
}
"""
