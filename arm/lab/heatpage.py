"""景氣溫度頁 → dashboard/x9m.html（docs/lab_heat_plan.md 第 6 節；入口＝籌碼雷達頂欄「景氣」小字，主頁不加入口）。

三張卡（短線、中線、長線）＋期貨選擇權籌碼：每張卡的總分、五段色條、和上週比、過去同一區之後的表現、判定；
細項一律展開：每一項自己的 0～100、把總分拉了幾分、佔比、本週增減（使用者 2026-10-17：「我要可以看到裡面的細項影響佔比，
各項都有一個 0～100 讓我參考，不然這種綜合指標很容易只有象徵性」）。
當天的分數用 heatcalc 同一套算法重算；哪些指標算進總分、過去的分區統計讀研究檔 data/lab/heat_research.json。
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

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dashboard" / "x9m.html"
RES = ROOT / "data" / "lab" / "heat_research.json"
TREND_DAYS = 500
WEEK = 5
SIGNED = {"S1", "S3", "S5", "S6", "F1", "F2", "F3", "M1", "M3", "M4", "M5", "M6", "M7", "L2", "L4", "L5", "L7", "L9"}
DEC = {"F1": 0, "L1": 0, "F3": 1, "L3": 1, "L4": 1, "L8": 1, "S2": 1, "M2": 1, "S4": 1, "S7": 1}
SRC = {
    "S1": "FinMind（證交所融資融券）", "M4": "FinMind（證交所融資融券）",
    "S2": "自算（上市櫃日線）", "M2": "自算（上市櫃日線）", "M3": "自算（上市櫃日線）",
    "S3": "FinMind＋證交所成交金額", "M5": "FinMind＋證交所成交金額",
    "S4": "證交所加權指數", "S6": "證交所加權指數", "M1": "證交所加權指數",
    "S5": "Yahoo ^VIX", "M8": "Yahoo ^VIX", "S7": "期交所", "F4": "期交所",
    "F1": "FinMind（期交所法人未平倉）", "F2": "FinMind（期交所）", "F3": "FinMind（期交所）",
    "M6": "央行", "M7": "Yahoo HYG、IEF",
    "L1": "國發會", "L2": "國發會", "L3": "國發會", "L4": "經濟部", "L5": "央行", "L6": "主計總處",
    "L7": "聯準會 H.15、紐約聯準銀行", "L8": "勞工統計局", "L9": "美國財政部",
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


def _fmt(k: str, v) -> str:
    if v is None:
        return "—"
    dec = DEC.get(k, 2)
    s = f"{abs(v):,.{dec}f}"
    sign = "−" if v < 0 else ("+" if k in SIGNED and v > 0 else "")
    unit = S.IND[S.KEYS.index(k)][3]
    if unit in ("%",):
        return f"{sign}{s}%"
    return f"{sign}{s}" + (f" {unit}" if unit else "")


def _src_date(B: dict, k: str, t: int) -> str | None:
    if S.LINES[S.LINE_OF[k]]["freq"] == "m":
        return B["ym"][k][t]
    ks = sorted(B["nat"].get(k) or {})
    day = B["cal"][t]
    j = (bisect.bisect_left(ks, day) if k in C.US else bisect.bisect_right(ks, day)) - 1
    return ks[j] if j >= 0 else None


def _ev(rl: dict, k: str | None, h: int) -> dict:
    src = rl.get("comp") if k is None else (rl.get("items") or {}).get(k)
    return ((src or {}).get(str(h)) or (src or {}).get(h)) or {}


def _reason(rl: dict, k: str, main: int) -> str:
    e = _ev(rl, k, main)
    d, ld = e.get("dir", 0), rl.get("dir", 0)
    if d and ld and d != ld:
        return "樣本內方向和這條線相反"
    if e.get("verdict") == "few" and not d:
        return "樣本不足"
    return "樣本內看不出關係"


def view(B: dict | None = None, R: dict | None = None) -> dict:
    B = B if B is not None else C.build()
    R = R if R is not None else (load_research() or {})
    cal, px = B["cal"], B["px"]
    T = len(cal)
    t = T - 1
    t0 = max(0, t - WEEK)
    lines = {}
    for ln, L in S.LINES.items():
        rl = (R.get("lines") or {}).get(ln) or {}
        inc = rl.get("inc") or []
        keys = [k for k in S.KEYS if S.LINE_OF[k] == ln]
        hn = {k: B["heat"][k][t] for k in keys}
        ha = {k: B["heat"][k][t0] for k in keys}
        cn, ca = H.contrib(hn, inc), H.contrib(ha, inc)
        items = []
        for k in keys:
            e = _ev(rl, k, L["main"])
            on = k in inc
            items.append({
                "k": k, "name": S.IND[S.KEYS.index(k)][2], "how": S.IND[S.KEYS.index(k)][5], "hot": S.HOT[k],
                "val": _fmt(k, B["raw"][k][t]), "src": _src_date(B, k, t), "heat": hn[k], "ago": ha[k],
                "inc": on, "pull": (cn.get(k) or {}).get("pull") if on else None,
                "share": (cn.get(k) or {}).get("share") if on else None,
                "dpull": ((cn.get(k) or {}).get("pull") - (ca.get(k) or {}).get("pull"))
                if on and k in cn and k in ca else None,
                "verdict": e.get("verdict"), "first": (rl.get("first") or {}).get(k),
                "why": None if on else _reason(rl, k, L["main"]),
                "ev": e,
            })
        comp = H.composite(hn, inc)
        lines[ln] = {"name": L["name"], "span": L["span"], "main": L["main"], "dir": rl.get("dir", 0), "inc": inc,
                     "score": comp, "ago": H.composite(ha, inc), "band": S.band(comp), "items": items,
                     "cev": _ev(rl, None, L["main"]) if inc else {},
                     "trend": [None if v is None else round(v, 1)
                               for v in C.composite_series(B["heat"], inc, T)[max(0, T - TREND_DAYS):]] if inc else None}
    a = max(0, T - TREND_DAYS)
    return {"asof": cal[t] if cal else None, "lines": lines, "tdates": cal[a:], "tpx": px[a:], "R": R,
            "data": R.get("data") or {}, "cal_info": B.get("cal_info")}


# ── HTML ─────────────────────────────────────────────────────────────

def _e(x) -> str:
    return html.escape(str(x), quote=True)


def _pct(x, dec=1, sign=True) -> str:
    if x is None:
        return "—"
    s = f"{abs(x):.{dec}f}%"
    return ("−" if x < 0 else ("+" if sign and x > 0 else "")) + s


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


def _band_of(ev: dict, part: str, nm: str | None) -> dict | None:
    for b in ((ev.get(part) or {}).get("bands") or []):
        if b.get("band") == nm:
            return b
    return None


def _past(ev: dict, band: str | None, main: int, part: str = "oos") -> str:
    b, allb = _band_of(ev, part, band), _band_of(ev, part, "全部")
    if not b or not b.get("n") or not allb:
        return ""
    yr = ((ev.get(part) or {}).get("a") or "")[:4]
    return (f"過去分數在「{_e(band)}」時（{_e(yr)} 起，{b['n']:,} 個樣本），之後 {main} 個交易日加權指數："
            f"平均 {_pct(b['avg'])}、上漲機率 {b['up']:.0f}%、期間最大跌幅中位數 {_pct(b['dd'])}。"
            f"所有日子：平均 {_pct(allb['avg'])}、上漲機率 {allb['up']:.0f}%。")


def _verdict_line(ln: str, L: dict) -> str:
    ev = L["cev"]
    if not L["inc"]:
        return '<p class="vd">這條線沒有指標通過樣本內驗證，<b>不給總分</b>，只列細項。</p>'
    v = ev.get("verdict")
    d = "熱了之後較弱" if L["dir"] < 0 else "熱了之後較強"
    oy = S.SPLIT[C.split_key(ln)]["oos"][0][:4]
    if v in ("weak", "strong"):
        txt = f"樣本內：{d}；{oy} 年起的樣本外也一樣。"
    elif v == "flip":
        txt = f"樣本內：{d}；<b>樣本外方向相反</b>，參考時要打折。"
    elif v == "few":
        txt = f"樣本內：{d}；樣本外的資料還不夠判斷。"
    else:
        txt = f"樣本內：{d}（指標各自的判定）；總分本身看不出穩定關係。"
    return f'<p class="vd">判定：{txt}</p>'


def _items(L: dict) -> str:
    inc = [it for it in L["items"] if it["inc"]]
    out = ['<div class="ith"><span>細項</span><span>熱度（0～100）</span><span>拉動總分</span><span>佔比</span><span>本週</span></div>']
    for it in sorted(inc, key=lambda x: -abs(x["pull"] or 0)):
        pull = "—" if it["pull"] is None else f'{"+" if it["pull"] > 0 else ("−" if it["pull"] < 0 else "")}{abs(it["pull"]):.1f} 分'
        sh = "—" if it["share"] is None else f'{it["share"]:.0f}%'
        dp = "—" if it["dpull"] is None else f'{"+" if it["dpull"] > 0 else ("−" if it["dpull"] < 0 else "")}{abs(it["dpull"]):.1f}'
        out.append(f'<div class="it"><span class="inm"><b>{_e(it["name"])}</b><i>{_e(it["val"])}・{_e(_md(it["src"]))}</i></span>'
                   f'<span class="ihb">{_bar(it["heat"])}</span><span class="ipl">{pull}</span>'
                   f'<span class="ish">{sh}</span><span class="iwk">{dp}</span></div>')
    rest = [it for it in L["items"] if not it["inc"]]
    if rest:
        out.append('<div class="ith ith2"><span>沒算進總分</span><span>熱度（0～100）</span><span class="wide">原因</span></div>')
        for it in rest:
            out.append(f'<div class="it it2"><span class="inm"><b>{_e(it["name"])}</b><i>{_e(it["val"])}・{_e(_md(it["src"]))}</i></span>'
                       f'<span class="ihb">{_bar(it["heat"])}</span><span class="iwhy">{_e(it["why"])}</span></div>')
    return "".join(out)


def _card(ln: str, L: dict) -> str:
    sc = L["score"]
    head = (f'<b class="sc {BAND_CLS.get(L["band"], "b2")}">{sc:.0f}</b><span class="bn">{_e(L["band"])}</span>'
            if sc is not None else '<b class="sc mu">—</b><span class="bn mu">沒有總分</span>')
    wk = ""
    if sc is not None and L["ago"] is not None:
        d = sc - L["ago"]
        wk = f'<span class="wk">和上週比 {"+" if d > 0 else ("−" if d < 0 else "")}{abs(d):.0f}</span>'
    tot = ""
    if sc is not None:
        s = sum((it["pull"] or 0) for it in L["items"] if it["inc"])
        tot = (f'<p class="eq">總分 {sc:.1f} ＝ 50 ＋ 各項拉動合計 {"+" if s >= 0 else "−"}{abs(s):.1f}'
               f'（算進總分的 {len(L["inc"])} 項等權平均；每項拉動＝（熱度 − 50）÷ 有值的項數）</p>')
    return (f'<section class="cd" id="c-{ln}"><div class="ch"><h2>{_e(L["name"])}<span class="sub">{_e(L["span"])}</span></h2>'
            f'<div class="sv">{head}{wk}</div></div>{_meter(sc)}'
            f'<p class="past">{_past(L["cev"], L["band"], L["main"]) if sc is not None else ""}</p>{_verdict_line(ln, L)}'
            f'{tot}<div class="its">{_items(L)}</div></section>')


def _chart(V: dict) -> str:
    W, Hh, P = 720, 210, 28
    ds, px = V["tdates"], V["tpx"]
    n = len(ds)
    if n < 2:
        return ""
    xs = lambda i: P + (W - 2 * P) * i / (n - 1)          # noqa: E731
    ys = lambda v: 10 + (Hh - 30) * (1 - v / 100)         # noqa: E731
    out = [f'<svg viewBox="0 0 {W} {Hh}" role="img" aria-label="溫度走勢">']
    for v in (20, 40, 60, 80):
        out.append(f'<line x1="{P}" x2="{W - P}" y1="{ys(v):.1f}" y2="{ys(v):.1f}" class="gl"/>'
                   f'<text x="{W - P + 4}" y="{ys(v) + 4:.1f}" class="gt">{v}</text>')
    pv = [p for p in px if p]
    if pv:
        lo, hi = min(pv), max(pv)
        pts = " ".join(f"{xs(i):.1f},{ys(100 * (p - lo) / (hi - lo or 1)):.1f}" for i, p in enumerate(px) if p)
        out.append(f'<polyline points="{pts}" class="lpx"/>')
    for ln, cls in (("short", "l1"), ("mid", "l2"), ("long", "l3")):
        tr = V["lines"][ln].get("trend")
        if not tr:
            continue
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
        out += [f'<polyline points="{" ".join(sg)}" class="{cls}"/>' for sg in segs if len(sg) > 1]
    for i in range(0, n, max(1, n // 6)):
        out.append(f'<text x="{xs(i):.1f}" y="{Hh - 4}" class="gt" text-anchor="middle">{_e(ds[i][:7])}</text>')
    out.append("</svg>")
    lg = ('<div class="lg"><span><i class="l1"></i>短線</span><span><i class="l2"></i>中線</span>'
          '<span><i class="l3"></i>長線</span><span><i class="lpx"></i>加權指數（右軸換算成同一高度）</span></div>')
    return "".join(out) + lg


def _band_table(ev: dict, part: str, main: int) -> str:
    bs = (ev.get(part) or {}).get("bands") or []
    if not bs:
        return '<p class="note">沒有資料。</p>'
    def up(b):
        return "—" if b.get("up") is None else f'{b["up"]:.0f}%'
    rows = "".join(f'<tr><td>{_e(b["band"])}</td><td>{b["n"]:,}</td><td>{_pct(b["avg"], 2)}</td><td>{_pct(b["med"], 2)}</td>'
                   f'<td>{up(b)}</td><td>{_pct(b["dd"], 2)}</td></tr>' for b in bs)
    return (f'<div class="tw"><table><tr><th>分數區間</th><th>樣本</th><th>之後 {main} 日平均</th><th>中位數</th>'
            f'<th>上漲機率</th><th>期間最大跌幅中位數</th></tr>{rows}</table></div>')


def _rho(e: dict) -> str:
    if e.get("rho") is None:
        return "—"
    ci = f'［{e["lo"]:+.2f}, {e["hi"]:+.2f}］' if e.get("lo") is not None else ""
    return f'{e["rho"]:+.2f}{ci}'


def _valid(ln: str, L: dict) -> str:
    main = L["main"]
    rows = []
    for it in L["items"]:
        e = it["ev"]
        rows.append(f'<tr><td class="l">{_e(it["name"])}</td><td>{_e(_md(it["first"]))}</td>'
                    f'<td>{(e.get("is") or {}).get("n", 0):,}</td><td>{_rho(e.get("is") or {})}</td>'
                    f'<td>{(e.get("oos") or {}).get("n", 0):,}</td><td>{_rho(e.get("oos") or {})}</td>'
                    f'<td class="l">{_e(S.VERDICT.get(e.get("verdict"), "—"))}</td><td>{"✓" if it["inc"] else ""}</td></tr>')
    sp = S.SPLIT[C.split_key(ln)]
    span = f'樣本內 {sp["is"][0][:4] if sp["is"][0] else "資料起點"}–{sp["is"][1][:4]}、樣本外 {sp["oos"][0][:4]} 起'
    comp = ""
    if L["inc"]:
        comp = (f'<h4>總分：樣本內</h4>{_band_table(L["cev"], "is", main)}'
                f'<h4>總分：樣本外</h4>{_band_table(L["cev"], "oos", main)}')
    return (f'<div class="vsec"><h3>{_e(L["name"])}<span class="sub">之後 {main} 個交易日；{_e(span)}</span></h3>{comp}'
            f'<h4>各指標</h4><div class="tw"><table><tr><th class="l">指標</th><th>有分數起</th><th>樣本內</th>'
            f'<th>等級相關［95% 信賴區間］</th><th>樣本外</th><th>等級相關</th><th class="l">判定</th><th>算進總分</th></tr>'
            f'{"".join(rows)}</table></div></div>')


def _detail(ln: str, L: dict) -> str:
    rows = []
    for it in L["items"]:
        d = None if it["heat"] is None or it["ago"] is None else it["heat"] - it["ago"]
        dd = "—" if d is None else f'{"+" if d > 0 else ("−" if d < 0 else "")}{abs(d):.0f}'
        hv = "—" if it["heat"] is None else f'{it["heat"]:.0f}'
        rows.append(f'<tr><td class="l"><b>{_e(it["name"])}</b><span class="hw">{_e(it["how"])}</span></td>'
                    f'<td>{_e(it["val"])}</td><td>{hv}</td>'
                    f'<td>{dd}</td><td>{"高＝熱" if it["hot"] > 0 else "低＝熱"}</td><td>{_e(_md(it["src"]))}</td>'
                    f'<td class="l">{_e(SRC.get(it["k"], ""))}</td></tr>')
    return (f'<div class="tw"><table class="dt"><tr><th class="l">{_e(L["name"])}</th><th>現值</th><th>熱度</th><th>5 日變化</th>'
            f'<th>熱的方向</th><th>資料日</th><th class="l">來源</th></tr>{"".join(rows)}</table></div>')


def render(V: dict) -> str:
    Ls = V["lines"]
    asof = V["asof"]
    head = "｜".join(f'{L["name"][:2]} {_e(L["band"]) + " " + format(L["score"], ".0f") if L["score"] is not None else "沒有總分"}'
                     for ln, L in Ls.items() if ln != "fo")
    R = V.get("R") or {}
    nores = "" if R.get("lines") else '<p class="warn">驗證結果還沒產生（data/lab/heat_research.json），先只列各指標的 0～100。</p>'
    data_rows = "".join(f'<tr><td class="l">{_e(k)}</td><td>{v[0]:,}</td><td>{_e(v[1] or "—")}</td><td>{_e(v[2] or "—")}</td></tr>'
                        for k, v in sorted((V.get("data") or {}).items()))
    body = (
        f'<p class="hl">{head}<span class="mu">（資料到 {_e(_md(asof))}）</span></p>{nores}'
        + "".join(_card(ln, Ls[ln]) for ln in ("short", "mid", "long", "fo"))
        + f'<section class="sec" id="trend"><h2>溫度走勢<span class="sub">近 {TREND_DAYS} 個交易日</span></h2>{_chart(V)}</section>'
        + '<section class="sec" id="detail"><h2>各線指標明細</h2>'
        + "".join(_detail(ln, Ls[ln]) for ln in ("short", "mid", "long", "fo")) + "</section>"
        + '<section class="sec" id="valid"><h2>驗證</h2>' + _METHOD
        + "".join(_valid(ln, Ls[ln]) for ln in ("short", "mid", "long", "fo")) + "</section>"
        + f'<section class="sec" id="src"><h2>資料來源與筆數</h2><div class="tw"><table><tr><th class="l">檔</th><th>筆數</th>'
          f'<th>起</th><th>到</th></tr>{data_rows}</table></div><p class="note">{_e(_SRC_NOTE)}</p></section>'
    )
    return _HTML.replace("{{CSS}}", _CSS).replace("{{ASOF}}", _e(_md(asof))).replace("{{BODY}}", body)


def build(out: Path = OUT) -> bool:
    text = render(view())
    if out.exists() and out.read_text(encoding="utf-8") == text:
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return True


_SRC_NOTE = ("融資、法人、期貨選擇權法人：FinMind（轉載證交所、期交所）；成交金額與加權指數：證交所；P/C 比、台指 VIX：期交所；"
             "新台幣、M1B／M2：央行；景氣燈號、領先指標、PMI：國發會；外銷訂單：經濟部；台灣 CPI：主計總處；"
             "美國 CPI：勞工統計局；公債殖利率：美國財政部；聯邦基金利率：聯準會 H.15（DBnomics 轉載）與紐約聯準銀行；"
             "VIX、HYG、IEF：Yahoo。廣度用上市櫃日線自算（當天最近一個月底市值 40 億以上的股票）。")

_METHOD = (
    '<div class="mth"><p><b>分數怎麼來</b>：每個指標和自己過去比——今天的值在過去 3 年（長線用 10 年）裡排第幾（百分位，只用今天以前的資料），'
    '依「熱的方向」換成 0～100 的熱度。每條線的總分＝算進去的指標熱度等權平均。</p>'
    '<p><b>哪些算進總分</b>（事前寫定）：用樣本內資料看每個指標的熱度和之後加權指數漲跌的等級相關，信賴區間不含 0 才算「有關係」；'
    '同一條線以多數方向為準，同方向的才算進去。樣本外只用來事後檢查，不拿來挑指標。</p>'
    '<p><b>等級相關</b>：負數＝熱度越高，之後漲幅越小；正數相反。數字都很小是正常的，這頁是參考讀數。</p>'
    '<p><b>限制</b>：景氣燈號與領先指標用修正後的數字（到修正值公布才算拿得到）；PMI 從 2012 年、期貨選擇權法人從 2018 年、'
    '台指 VIX 從 2026 年 7 月才有資料，樣本不夠的照樣列出自己的 0～100，但不算進總分。</p></div>')

_HTML = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>景氣溫度</title>
<style>{{CSS}}</style></head>
<body>
<div class="top"><b>景氣溫度</b><span class="asof">台股，資料到 {{ASOF}}</span><a class="back" href="x9.html">籌碼雷達</a><a class="back" href="./">返回主頁</a></div>
<p class="purp">每天三個讀數：短線（未來 1～2 週）、中線（1～3 個月）、長線（6～12 個月），各 0～100，100 最熱。頁面只描述現在熱不熱、過去同樣熱度之後大盤的表現，怎麼操作由你判斷。</p>
<nav class="snav"><a href="#c-short">短線</a><a href="#c-mid">中線</a><a href="#c-long">長線</a><a href="#c-fo">期貨選擇權</a><a href="#trend">走勢</a><a href="#detail">明細</a><a href="#valid">驗證</a><a href="#src">來源</a></nav>
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
.hl{font-size:16px;font-weight:700;margin:4px 0 14px;line-height:1.7}.hl .mu{font-weight:400;font-size:13px;margin-left:6px}
.mu{color:var(--mut)}.warn{color:var(--warn);font-size:13.5px}
.cd{border:1px solid var(--line);border-radius:14px;padding:12px 16px 14px;margin:0 0 18px;scroll-margin-top:48px}
.ch{display:flex;align-items:flex-start;flex-wrap:wrap;gap:4px 12px}
.ch h2{margin:0;font-size:17px;flex:1;min-width:0}.ch h2 .sub,.sec h2 .sub,h3 .sub{font-size:12.5px;font-weight:400;color:var(--mut);margin-left:8px}
.sv{display:flex;align-items:baseline;gap:8px}.sc{font-size:34px;line-height:1;font-weight:800}.bn{font-weight:700}
.sc.b0,.bn.b0{color:var(--c0)}.sc.b1{color:#3f7fc0}.sc.b2{color:var(--ink2)}.sc.b3{color:#c26a16}.sc.b4{color:var(--c4)}
.wk{font-size:12.5px;color:var(--mut)}
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
.ith2,.it2{grid-template-columns:minmax(0,1.6fr) minmax(120px,1.3fr) minmax(0,168px)}
.ith.ith2 span.wide{text-align:left}.iwhy{font-size:12.5px;color:var(--mut)}
.inm{min-width:0;display:flex;flex-direction:column;line-height:1.35}.inm b{font-weight:600;font-size:14px}.inm i{font-style:normal;color:var(--mut);font-size:12px}
.ihb{display:flex;align-items:center;gap:8px}.hb{flex:1;height:8px;background:var(--card2);border-radius:4px;overflow:hidden;min-width:60px}
.hb i{display:block;height:100%;border-radius:4px}.hb .b0{background:var(--c0)}.hb .b1{background:var(--c1)}.hb .b2{background:var(--c2)}.hb .b3{background:var(--c3)}.hb .b4{background:var(--c4)}
.hn{width:2.2em;text-align:right;font-size:14px}
.ipl{font-weight:700}.ish,.iwk{font-size:13px;color:var(--ink2)}
.sec{margin:28px 0 0;scroll-margin-top:48px}.sec>h2{font-size:17px;margin:0 0 10px}
svg{display:block;width:100%;height:auto}
svg .gl{stroke:var(--line);stroke-width:1}svg .gt{font-size:11px;fill:var(--mut)}
svg polyline{fill:none;stroke-width:2}svg .l1{stroke:#d33a34}svg .l2{stroke:#c26a16}svg .l3{stroke:#2f6fb5}svg .lpx{stroke:#9aa3ae;stroke-width:1.2;stroke-dasharray:3 3}
.lg{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:12px;color:var(--mut);margin-top:4px}.lg i{display:inline-block;width:16px;height:3px;vertical-align:middle;margin-right:4px}
.lg .l1{background:#d33a34}.lg .l2{background:#c26a16}.lg .l3{background:#2f6fb5}.lg .lpx{background:#9aa3ae}
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
 .ith{display:none}.ith.ith2{display:block;padding-top:12px}.ith.ith2 span:not(:first-child){display:none}
 .it{grid-template-columns:minmax(0,1fr) 64px 78px;row-gap:3px}
 .it .inm{grid-column:1/2;grid-row:1}.it .ihb{grid-column:1/2;grid-row:2}
 .it .ipl{grid-column:2/3;grid-row:1/3;align-self:center}
 .it .ish{grid-column:3/4;grid-row:1}.it .iwk{grid-column:3/4;grid-row:2}
 .it .ish::before{content:"佔比 "}.it .iwk::before{content:"本週 "}
 .it2{grid-template-columns:minmax(0,1fr)}.it2 .ihb{grid-row:auto}.it2 .iwhy{grid-column:1/2}
 .sc{font-size:30px}
}
"""
