"""景氣頁「短線大跌風險」卡（docs/lab_crash_plan.md 第 3.6、10、11 節；規格 crashspec VER 1）。

台股景氣頁、美股景氣頁（四個指數各一份）各一張卡（Q1 A），放在雷達與關鍵狀態下面：
  一句話            現在哪些「研究判定有差別」的條件成立（熱的時候之後比較容易／比較不容易大跌）
  先看波動          今天的 20 日波動在歷史上的位置，同一組波動的日子之後五種大跌的比例（描述，不是檢定）
  判定有差別的項目  只列研究判定「較容易／較不容易大跌」的（Q2 A）；現在熱的展開，其他收起。每一列＝各區之後的比例小圖
                    （今天這一區上色）、熱與不熱的時候、今天同樣狀態（熱或不熱 × 今天這組波動）、扣掉波動後的差與區間、
                    期間與段數、穩健度、樣本外
  全部項目與算法    收起：全部項目 × 五種大跌的判定表、怎麼算、事前寫定的 4 個主要假說
每天建頁只讀研究檔的統計（crash.load_research）；今天的值、今天落在哪一組波動每天重算（crash.now、crash.vol_state）。
只描述位置與過去的比例，不寫買賣指示；用字照專案禁用詞。
"""
from __future__ import annotations

import html
import math

from . import crashspec as S

ONAME = {"A1": "單日大跌", "A2": "20 日內急跌", "A3": "60 日內修正", "A4": "波動放大", "A5": "最差 3 天跌幅"}
OSHORT = {"A1": "單日", "A2": "20 日", "A3": "60 日", "A4": "波動", "A5": "最差 3 天"}
GNAME = ("低", "中", "高")
VCLS = {"up": "weak", "down": "strong", "none": "none", "few": "few"}      # 同景氣頁：紅＝較弱（這裡是較容易大跌）、藍＝較強
MARK = {"up": "▲", "down": "▼", "none": "·", "few": "—"}
OOS_TXT = {"better": "樣本外變準", "same": "樣本外沒有變準", "worse": "樣本外變差"}
FLAG_DEF = {"BL2": "泡沫頁每月判定的泡沫等級在 2 以上（漲勢過熱）", "BP1": "泡沫頁每月判定的「價格爆發」成立"}
TRADE_DAYS = 252


def _e(x) -> str:
    return html.escape(str(x), quote=True)


def _num(x: float, dec: int, sign: bool = False) -> str:
    """先取位數再判正負（不寫「−0.0」）；負號用全形減號，同景氣頁。"""
    r = round(x, dec)
    return ("−" if r < 0 else ("+" if sign and r > 0 else "")) + f"{abs(r):.{dec}f}"


def _th(x: float) -> str:
    return f"{x * 100:g}"


def _ym(d: str | None) -> str:
    return f"{int(d[:4])} 年 {int(d[5:7])} 月" if d and len(d) >= 7 else "—"


def odef(mk: str, o: str, px: str = "") -> str:
    """結果變數的白話定義（門檻用該市場的；px＝指數名，台股是加權指數）。"""
    a1, a2, a3 = S.TH[mk]
    return {"A1": f"之後 {S.H['A1']} 個交易日內{px}有一天跌 {_th(a1)}% 以上",
            "A2": f"之後 {S.H['A2']} 個交易日內{px}收盤比今天低 {_th(a2)}% 以上",
            "A3": f"之後 {S.H['A3']} 個交易日內{px}收盤比今天低 {_th(a3)}% 以上",
            "A4": f"之後 {S.H['A4']} 個交易日的波動是之前 {S.VOL_BEFORE} 個交易日的 {S.VOL_RATIO:g} 倍以上",
            "A5": f"之後 {S.H['A5']} 個交易日最差 {S.WORST_K} 天的平均漲跌"}[o]


def val(o: str, x, sig: float, short: bool = False) -> str:
    """A1～A4＝之後發生的比例；A5＝之後最差 3 天的平均漲跌（研究檔存的是跌幅 ÷ 這個市場的日報酬標準差）。"""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    if o == "A5":
        return _num(-x * sig * 100, 1 if short else 2) + "%"
    p = x * 100
    return _num(p, (1 if abs(p) < 10 else 0) if short else 1) + "%"


def dtxt(o: str, d, sig: float) -> str:
    """扣掉波動後的差：A1～A4 是比例差（個百分點）；A5 是最差 3 天平均的差（個百分點，越負越嚴重）。"""
    if d is None:
        return "—"
    if o == "A5":
        return _num(-d * sig * 100, 2, True) + " 個百分點"
    return _num(d * 100, 1, True) + " 個百分點"


def citxt(o: str, lo, hi, sig: float) -> str:
    if lo is None or hi is None:
        return "—"
    if o == "A5":
        return f"{_num(-hi * sig * 100, 2, True)}～{_num(-lo * sig * 100, 2, True)}"
    return f"{_num(lo * 100, 1, True)}～{_num(hi * 100, 1, True)}"


def zone_k(v: float) -> int:
    """0～100 → 第幾區（0＝≥ 80 … 4＝< 20），同 crash.zone_of。"""
    for k, (lo, _) in enumerate(S.ZONES):
        if v >= lo:
            return k
    return len(S.ZONES) - 1


# ── 每天建頁的資料 ─────────────────────────────────────────────────────────

def state(B: dict) -> dict | None:
    """景氣頁的 B（heatcalc.build／heatcalc_us.build）→ 卡片要的資料；研究檔沒有、不是這一版就回 None（不顯示卡片）。
    原始資料沿用景氣頁已經載入的 B["D"]，景氣頁沒有載入的幾個檔（央行市值與融資、美股成交量）才另外讀。"""
    from . import bubble as BU
    from . import crash as CR
    from . import heatdata as HD
    from . import heatpage as HP
    mk = "tw" if HP.MK["tab"] == "tw" else B.get("idx")
    R = CR.load_research()
    if mk not in S.MARKETS or not R or mk not in (R.get("markets") or {}) or not B.get("cal") or B.get("D") is None:
        return None
    D = dict(B["D"])
    BX = {mk: BU.market_for(mk, B["D"])}
    if mk == "tw":
        for n in ("twcap", "twmgn", "taiex90"):
            if n not in D:
                D[n] = HD.load(n)
        D["_tsmc"] = CR._tsmc_month(None)
        I = CR.tw_inputs(D=D, B=B, BX=BX)
    else:
        n = f"us_vol_{mk}"
        if "VOL" in S.PRED[mk] and n not in D:
            D[n] = HD.load(n)
        I = CR.us_inputs(mk, D=D, Bu=B, BX=BX)
    if not I["cal"]:
        return None
    return {"mk": mk, "px": HP.MK["px"], "now": CR.now(mk, I, R), "vs": CR.vol_state(mk, I),
            "R": R["markets"][mk], "primary": R.get("primary") or {}}


def _orow(o: str, r: dict, n: dict) -> dict:
    """一個判定有差別的結果：研究檔的統計＋今天同樣狀態（熱或不熱 × 今天這組波動）的比例。"""
    g = (n.get("g") or {}).get(o)
    hot = bool(n.get("hot"))
    same = None
    st = r.get("strata") or []
    if n.get("v") is not None and g is not None and 0 <= g < len(st):
        cnt, y = (st[g][0], st[g][1]) if hot else (st[g][2], st[g][3])
        if cnt >= S.MIN_STRAT and y is not None:
            same = {"n": cnt, "y": y, "g": g}
    oo = r.get("oos") or {}
    oos = (oo.get("v") if oo.get("n") else None) if o in S.BINARY else "na"
    return {"o": o, "v": r["v"], "hot": r.get("hot"), "not": r.get("not"), "base": r.get("base"), "d": r.get("d"),
            "lo": r.get("lo"), "hi": r.get("hi"), "q": r.get("q"), "nh": r.get("nh"), "nn": r.get("nn"), "ep": r.get("ep"),
            "a": r.get("a"), "ok": r.get("ok"), "oos": oos, "zones": r.get("zones") or [], "same": same, "g": g}


def items(C: dict) -> list[dict]:
    """研究判定「較容易／較不容易大跌」的項目：今天的值＋判定有差別的結果（其他結果不列）。現在熱的排前面，再依今天的值。"""
    from . import crash as CR
    mk, N, R = C["mk"], C["now"], C["R"]
    out = []
    for p in S.PRED[mk]:
        rp = (R.get("preds") or {}).get(p) or {}
        n = (N.get("preds") or {}).get(p) or {}
        outs = [_orow(o, r, n) for o in S.OUTCOMES
                for r in [((rp.get("out") or {}).get(o) or {})] if r.get("v") in S.SHOW]
        if not outs:
            continue
        info = CR.pred_info(mk, p)
        out.append({"p": p, "name": info["name"], "hotdef": FLAG_DEF.get(p) or info["hot"],
                    "v": n.get("v"), "hot": bool(n.get("hot")), "flag": p in S.FLAGS, "monthly": p in S.MONTHLY,
                    "a": rp.get("a"), "outs": outs})
    out.sort(key=lambda it: (not it["hot"], -(it["v"] if it["v"] is not None else -1.0)))
    return out


def _active(its: list[dict], v: str) -> list[tuple[dict, list[dict]]]:
    xs = [(it, [r for r in it["outs"] if r["v"] == v]) for it in its if it["hot"]]
    return [(it, rs) for it, rs in xs if rs]


def lead(its: list[dict]) -> list[str]:
    """一句話（第二句講樣本外）：全部由研究判定與今天的值算出來。"""
    up, dn = _active(its, "up"), _active(its, "down")

    def lst(xs):
        return "、".join(f'{it["name"]}（{"、".join(ONAME[r["o"]] for r in rs)}）' for it, rs in xs)

    def cnt(xs):
        return f"{len(xs)} 個條件成立" if any(it["flag"] for it, _ in xs) else f"{len(xs)} 項在熱區"
    out = []
    if up:
        out.append(f"{cnt(up)}，歷史上這種時候之後比較容易大跌：{lst(up)}。")
    if dn:
        out.append(f"{cnt(dn)}，歷史上這種時候之後比較不容易大跌：{lst(dn)}。")
    if not up and not dn:
        if its:
            out.append(f"研究判定有差別的 {len(its)} 項，現在都不在熱區：沒有「之後比較容易或比較不容易大跌」的條件成立。")
        else:
            out.append("扣掉現在的波動之後，沒有項目判定和之後大跌有關。")
        return out
    act = [r for _, rs in up + dn for r in rs if r["o"] in S.BINARY]
    if act:
        k = {s: sum(1 for r in act if r["oos"] == s) for s in ("better", "same", "worse")}
        nx = sum(1 for r in act if r["oos"] is None)
        parts = ([f'{k["better"]} 個變準'] if k["better"] else []) + ([f'{k["same"]} 個沒有變準'] if k["same"] else []) \
            + ([f'{k["worse"]} 個變差'] if k["worse"] else []) + ([f"{nx} 個資料太短沒有做"] if nx else [])
        out.append("樣本外（2010 年起每月只用當時已知的資料重估，看加了這一項預測有沒有變準）：" + "、".join(parts) + "。只當參考。")
    else:
        out.append("只當參考。")
    return out


# ── HTML ─────────────────────────────────────────────────────────────────

def zbars(o: str, r: dict, sig: float, cur: int | None, flag: bool, w: int = 300, h: int = 92) -> str:
    """各區之後的比例長條（由冷到熱；今天這一區上色），虛線＝這段期間全部日子。A5 畫最差 3 天的平均跌幅（越長越嚴重）。
    天數不到 20 天的區不畫（寫 —）。"""
    zs = r.get("zones") or []
    if flag:
        bars = [("不成立", r.get("nn") or 0, r.get("not"), len(S.ZONES) - 1), ("成立", r.get("nh") or 0, r.get("hot"), 0)]
    elif len(zs) == len(S.ZONES):
        bars = [(S.ZONES[k][1], zs[k][0] or 0, zs[k][1], k) for k in range(len(S.ZONES) - 1, -1, -1)]
    else:
        return ""
    mag = (lambda v: v * sig * 100) if o == "A5" else (lambda v: v * 100)  # noqa: E731
    vals = [mag(v) for _, c, v, _ in bars if v is not None and c >= S.MIN_STRAT]
    base = mag(r["base"]) if r.get("base") is not None else None
    if not vals:
        return ""
    hi = max(vals + ([base] if base is not None else [])) * 1.1 or 1.0
    top, bot = 15, h - 19
    Y = lambda v: bot - (bot - top) * max(v, 0.0) / hi                    # noqa: E731
    bw = (w - 8) / len(bars)
    s = [f'<line class="kz0" x1="0" x2="{w}" y1="{bot}" y2="{bot}"/>']
    if base is not None:
        s.append(f'<line class="kza" x1="4" x2="{w - 4}" y1="{Y(base):.1f}" y2="{Y(base):.1f}"/>')
    for i, (lab, c, v, k) in enumerate(bars):
        x = 4 + i * bw + bw * 0.22
        bwi = bw * 0.56
        cx = x + bwi / 2
        on = cur is not None and k == cur
        zc = len(S.ZONES) - 1 - k
        s.append(f'<text class="kzl{" on zt" + str(zc) if on else ""}" x="{cx:.1f}" y="{h - 5}">{_e(lab)}</text>')
        if v is None or c < S.MIN_STRAT:
            s.append(f'<text class="kzv" x="{cx:.1f}" y="{bot - 4}">—</text>')
            continue
        y0 = Y(mag(v))
        s.append(f'<rect class="{"zf" + str(zc) if on else "kzo"}" x="{x:.1f}" y="{y0:.1f}" width="{bwi:.1f}" '
                 f'height="{max(1.0, bot - y0):.1f}" rx="3"/>')
        s.append(f'<text class="kzv{" on" if on else ""}" x="{cx:.1f}" y="{y0 - 4:.1f}">{_e(val(o, v, sig, True))}</text>')
    what = "最差 3 天的平均跌幅" if o == "A5" else "發生的比例"
    return (f'<svg class="kzs xrz" viewBox="0 0 {w} {h}" role="img" aria-label="{_e(ONAME[o])}：各區之後{what}">'
            + "".join(s) + "</svg>")


def _vtxt(it: dict) -> tuple[str, str]:
    """今天的值 → （文字, 顏色 class）。泡沫兩項寫成立／不成立。"""
    v = it["v"]
    if v is None:
        return "—", "ztx"
    zc = f"zt{len(S.ZONES) - 1 - zone_k(v)}"
    if it["flag"]:
        return ("成立" if it["hot"] else "不成立"), zc
    from .heatpage import n0
    return n0(v) + (" 熱" if it["hot"] else ""), zc


def _row(C: dict, it: dict, r: dict, sig: float) -> str:
    o = r["o"]
    hl, nl = ("成立", "不成立") if it["flag"] else ("熱", "不熱")
    head = (f'<div class="xrn"><span class="vt {VCLS[r["v"]]}">{_e(S.VERDICT[r["v"]])}</span><b>{_e(ONAME[o])}</b>'
            f'<span class="xrf">{_e(odef(C["mk"], o, C.get("px") or ""))}</span></div>')
    sm = r["same"]
    if it["v"] is None:
        st = '—<small>今天沒有值</small>'
    elif sm:
        st = (f'{_e(val(o, sm["y"], sig))}<small>{hl if it["hot"] else nl}、波動{GNAME[sm["g"]]}'
              f'（{_e((r["a"] or "")[:4])} 年起的日子分三組），{sm["n"]:,} 天</small>')
    else:
        st = f'—<small>同樣狀態的日子不到 {S.MIN_STRAT} 天</small>'
    grid = (f'<dl class="xrg"><div><dt>{hl}的時候</dt><dd>{_e(val(o, r["hot"], sig))}</dd></div>'
            f'<div><dt>{nl}的時候</dt><dd>{_e(val(o, r["not"], sig))}</dd></div>'
            f'<div><dt>今天這種狀態</dt><dd>{st}</dd></div>'
            f'<div><dt>扣掉波動後</dt><dd>{_e(dtxt(o, r["d"], sig))}<small>95% 區間 {_e(citxt(o, r["lo"], r["hi"], sig))}</small></dd></div></dl>')
    ok = {True: "✓", False: "✗"}.get(r["ok"], "—")
    oos = "" if r["oos"] == "na" else "；" + (OOS_TXT.get(r["oos"]) or "樣本外：資料太短沒有做")
    foot = f'{_ym(r["a"])}起，{hl}的日子 {r["nh"] or 0:,} 天（{r["ep"] or 0} 段）；穩健度 {ok}{oos}'
    cur = None if it["v"] is None else zone_k(it["v"])
    if it["flag"] and it["v"] is not None:
        cur = 0 if it["hot"] else len(S.ZONES) - 1
    return (f'<div class="xrr">{head}<div class="xrb">{zbars(o, r, sig, cur, it["flag"])}{grid}</div>'
            f'<p class="xrx">{_e(foot)}</p></div>')


def _item(C: dict, it: dict, sig: float) -> str:
    vt, zc = _vtxt(it)
    by: dict[str, list[str]] = {}
    for r in it["outs"]:
        by.setdefault(r["v"], []).append(ONAME[r["o"]])
    tags = "".join(f'<span class="xrsv"><span class="vt {VCLS[v]}">{_e(S.VERDICT[v])}</span>{_e("、".join(ns))}</span>'
                   for v, ns in by.items())
    mon = "；月資料，用最近一個月底的值" if it["monthly"] else ""
    hl = "成立" if it["flag"] else "熱"
    return (f'<details class="xri" data-p="{_e(it["p"])}"{" open" if it["hot"] else ""}>'
            f'<summary><span class="xrt"><b>{_e(it["name"])}</b><span class="xrv {zc}">{_e(vt)}</span></span>'
            f'<span class="xrs">{tags}</span></summary>'
            f'<p class="xrd">{hl}＝{_e(it["hotdef"])}{_e(mon)}。</p>'
            + "".join(_row(C, it, r, sig) for r in it["outs"]) + "</details>")


def vol_html(C: dict) -> str:
    vs = C.get("vs") or {}
    if vs.get("vol") is None or vs.get("g") is None or not vs.get("rows"):
        return ""
    sig = C["R"]["sigma"]
    g = GNAME[vs["g"]]
    ann = vs["vol"] * math.sqrt(TRADE_DAYS) * 100
    head = (f'<p class="xrvh"><b>先看波動</b>：現在 20 日波動 {vs["vol"] * 100:.2f}%（年化約 {ann:.0f}%），'
            f'比 {_e((vs.get("a") or "")[:4])} 年以來 {vs["pct"] * 100:.0f}% 的日子高，屬於「{g}」的三分之一。'
            '波動越大，之後本來就越常大跌；下面判定有差別的項目都已經扣掉這一塊。</p>')
    rows = "".join(f'<tr><td class="l">{_e(ONAME[o])}<span class="xrf">{_e(odef(C["mk"], o, C.get("px") or ""))}</span></td>'
                   f'<td>{_e(val(o, r["g"], sig))}</td><td>{_e(val(o, r["all"], sig))}</td></tr>'
                   for o, r in vs["rows"].items())
    return (head + f'<div class="tw"><table class="xrvt"><tr><th class="l">之後</th><th>波動「{g}」的日子</th>'
            f'<th>全部日子</th></tr>{rows}</table></div>')


def table_html(C: dict) -> str:
    """全部項目 × 五種大跌的判定（▲ 較容易、▼ 較不容易、· 看不出、— 樣本不足）。"""
    from . import crash as CR
    mk, N, R = C["mk"], C["now"], C["R"]
    head = '<tr><th class="l">項目</th><th>今天</th>' + "".join(f"<th>{_e(OSHORT[o])}</th>" for o in S.OUTCOMES) + "</tr>"
    rows = []
    for p in S.PRED[mk]:
        n = (N.get("preds") or {}).get(p) or {}
        rp = (R.get("preds") or {}).get(p) or {}
        it = {"v": n.get("v"), "hot": bool(n.get("hot")), "flag": p in S.FLAGS}
        vt, zc = _vtxt(it)
        cells = []
        for o in S.OUTCOMES:
            v = (((rp.get("out") or {}).get(o) or {}).get("v")) or "few"
            cells.append(f'<td class="xrm{v}" title="{_e(S.VERDICT[v])}">{MARK[v]}</td>')
        rows.append(f'<tr><td class="l">{_e(CR.pred_info(mk, p)["name"])}</td><td class="{zc}">{_e(vt)}</td>{"".join(cells)}</tr>')
    lg = "　".join(f"{MARK[v]} {S.VERDICT[v]}" for v in ("up", "down", "none", "few"))
    return (f'<div class="tw"><table class="xrmt">{head}{"".join(rows)}</table></div>'
            f'<p class="note">{_e(lg)}（樣本不足＝熱的日子不到 {S.MIN_HOT_DAYS} 天、不到 {S.MIN_EPISODES} 段，或不熱的日子不到 '
            f'{S.MIN_HOT_DAYS} 天）。欄位：{_e("、".join(f"{OSHORT[o]}＝{ONAME[o]}" for o in S.OUTCOMES))}。</p>')


def primary_html(P: dict, mk: str) -> str:
    """事前寫定的 4 個主要假說：一句總結四個；只列和這個市場有關的（台股頁 HA1、HA2、HA4；S&P 500、那斯達克 HA3、HA4）。"""
    li = []
    n_ok = sum(1 for h in S.PRIMARY if ((P or {}).get(h) or {}).get("ok"))
    for h, spec in S.PRIMARY.items():
        if mk not in spec["mk"]:
            continue
        r = (P or {}).get(h) or {}
        if r.get("few"):
            res = f'樣本不足（熱的日子 {r.get("nh") or 0:,} 天、{r.get("ep") or 0} 段）'
        elif r.get("d") is None or r.get("padj") is None:
            res = "—"
        else:
            if spec["out"] == "A5":
                d, ci = f'{_num(r["d"], 3, True)} 個標準差', f'{_num(r["lo"], 3, True)}～{_num(r["hi"], 3, True)}'
            else:
                d, ci = dtxt("A1", r["d"], 0.0), citxt("A1", r["lo"], r["hi"], 0.0)
            res = f'差 {d}（95% 區間 {ci}），Holm 校正後 p＝{r["padj"]:.3f}，{"成立" if r.get("ok") else "不成立"}'
        li.append(f'<li><b>{h}</b> {_e(spec["text"])}：{_e(res)}</li>')
    tl = f"{len(S.PRIMARY)} 個都沒有通過" if not n_ok else f"{n_ok} 個通過"
    tail = "下面是和這個市場有關的。" if li else "沒有一個是針對這個指數的。"
    return (f'<p class="xrmh"><b>事前寫定的 {len(S.PRIMARY)} 個主要假說</b>（Holm 校正、單尾）：{tl}；{tail}</p>'
            + (f'<ul class="xrpl">{"".join(li)}</ul>' if li else ""))


def _method(mk: str, px: str) -> str:
    lim = ("加權指數是價格指數（不含息），除息旺季會多跌一點，對 20、60 日的跌幅影響很小。" if mk == "tw"
           else f"{px.lstrip()}是價格指數（不含股利），對 20、60 日的跌幅影響很小。")
    return _METHOD.replace("{{LIM}}", _e(lim))


_METHOD = (
    '<div class="xrmth">'
    '<p><b>怎麼算</b>：每一項換成 0～100（和自己的過去比），≥ 80 算熱。比較熱的日子和不熱的日子，之後發生大跌的比例差多少。'
    '波動大的時候本來就比較常大跌，所以先依當時的 20 日波動把日子分成三組，在組內比，再依熱的天數加權平均，這就是「扣掉波動後」的差。</p>'
    '<p><b>判定</b>：95% 區間用 60 個交易日一塊重抽 2,000 次；區間不含 0、前後兩半方向一樣，'
    '而且同一種大跌的全部項目一起做多重比較校正後 q ≤ 0.10，才寫「較容易大跌」或「較不容易大跌」。</p>'
    '<p><b>穩健度</b>：把熱、現在的波動、對 60 日線的乖離放進同一個回歸，熱的係數同方向而且明顯（|z| ≥ 1.96）＝✓。'
    '<b>樣本外</b>：2010 年起每月只用當時已知的資料重估，比較「只用波動」和「波動加這一項」的預測誤差（Brier 分數）。'
    '最差 3 天沒有做樣本外。</p>'
    '<p><b>限制</b>：熱的日子常常集中在少數幾段行情（段數寫在每一列）；{{LIM}}'
    '規格在看結果之前寫定（VER 1，2026-10-19），規劃文件 docs/lab_crash_plan.md 第 10、11 節。</p></div>')


def card(C: dict | None) -> str:
    """整張卡；C＝state() 的結果（None＝研究檔沒有，不顯示）。"""
    if not C:
        return ""
    from .heatpage import _md
    its = items(C)
    sig = C["R"]["sigma"]
    yr = (C["R"].get("start") or "")[:4]
    ls = lead(its)
    lead_html = f'<p class="xrl">{_e(ls[0])}</p>' + "".join(f'<p class="xrl2">{_e(s)}</p>' for s in ls[1:])
    body = "".join(_item(C, it, sig) for it in its)
    lst = ""
    if its:
        how = "現在熱的先列、已展開" if any(it["hot"] for it in its) else "點一下展開"
        lst = (f'<h3 class="xrh3">研究判定有差別的項目<span class="sub">{len(its)} 項；{how}</span></h3>'
               '<p class="ksub">長條＝這一項在各區時，之後發生的比例（最差 3 天＝平均跌幅）；上色的是今天這一區，虛線＝這段期間全部日子。'
               '長條沒有扣掉波動，判定看「扣掉波動後」。</p>'
               f'<div class="xrls">{body}</div>')
    return (f'<section class="sec xrsec" id="crash"><div class="card xrc">'
            f'<div class="khd"><h2>短線大跌風險</h2><span class="kn">之後 20～60 個交易日・資料到 {_e(_md(C["now"].get("d")))}</span></div>'
            f'{lead_html}'
            f'<p class="ksub">研究用 {_e(yr)} 年起的資料：扣掉現在的波動之後，判定和之後大跌有關的項目才列出來，其他收在最下面。'
            '只描述過去的比例，不是買賣指示。</p>'
            f'{vol_html(C)}{lst}'
            f'<details class="xrmore"><summary>全部 {len(S.PRED[C["mk"]])} 項的判定、怎麼算、主要假說</summary>'
            f'{table_html(C)}{_method(C["mk"], C.get("px") or "")}{primary_html(C.get("primary") or {}, C["mk"])}</details>'
            '</div></section>')


CSS = (
    ".xrc{padding:12px 14px;min-width:0}"
    ".xrl{font-size:15px;font-weight:700;margin:8px 0 4px;line-height:1.6}"
    ".xrl2{font-size:13.5px;color:var(--ink2);margin:0 0 4px;line-height:1.65}"
    ".xrvh{font-size:13.5px;color:var(--ink2);margin:12px 0 6px;line-height:1.65}"
    ".xrvh b{color:var(--ink)}"
    "table.xrvt{max-width:640px}"
    "table.xrvt td:first-child{white-space:normal;min-width:10em}"
    ".xrf{display:block;font-size:11.5px;color:var(--mut);font-weight:400;line-height:1.5}"
    ".xrh3{font-size:15px;margin:16px 0 2px}"
    ".xri{border-top:1px solid var(--line);padding:8px 0 6px}"
    ".xri>summary{cursor:pointer;line-height:1.6}"
    ".xri>summary::marker{color:var(--mut)}"
    ".xrt{display:inline-flex;align-items:baseline;gap:4px 10px;flex-wrap:wrap}"
    ".xrt b{font-size:14.5px}"
    ".xrv{font-size:14.5px;font-weight:800}"
    ".xrs{display:block;margin:2px 0 0 1.15em;font-size:12.5px;color:var(--ink2)}"
    ".xrsv{display:inline-block;margin:2px 12px 0 0}"
    ".xrsv .vt{margin:0 6px 0 0}"
    ".xrd{font-size:12.5px;color:var(--mut);margin:6px 0 4px 1.15em;line-height:1.6}"
    ".xrr{margin:8px 0 4px 1.15em;padding:8px 10px;background:var(--card2);border-radius:10px;min-width:0}"
    ".xrn{display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 8px}"
    ".xrn .vt{margin:0}"
    ".xrn b{font-size:13.5px}"
    ".xrn .xrf{flex-basis:100%}"
    ".xrb{display:grid;grid-template-columns:minmax(0,300px) minmax(0,1fr);gap:6px 16px;align-items:center;margin-top:4px}"
    ".xrz{max-width:300px}"
    ".xrz .kzv{paint-order:stroke;stroke:var(--card2);stroke-width:3px;stroke-linejoin:round}"
    ".xrg{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 12px;margin:0}"
    ".xrg div{min-width:0}"
    ".xrg dt{font-size:11.5px;color:var(--mut)}"
    ".xrg dd{margin:0;font-size:15px;font-weight:700;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}"
    ".xrg small{display:block;font-size:11px;font-weight:400;color:var(--mut);line-height:1.45}"
    ".xrx{font-size:11.5px;color:var(--mut);margin:6px 0 0;line-height:1.6}"
    ".xrmore{margin-top:12px}"
    ".xrmore>summary{cursor:pointer;font-size:13px;color:var(--acc);padding:8px 0 2px;border-top:1px solid var(--line)}"
    ".xrmore[open]>summary{margin-bottom:8px}"
    "table.xrmt th,table.xrmt td{padding:5px 4px;text-align:center}"
    "table.xrmt td:first-child,table.xrmt th:first-child{white-space:normal;min-width:7em;text-align:left}"
    ".xrmup{color:var(--t4);font-weight:800}"
    ".xrmdown{color:var(--t0);font-weight:800}"
    ".xrmnone,.xrmfew{color:var(--mut)}"
    ".xrmth p,.xrmh{font-size:12.5px;color:var(--ink2);line-height:1.7;margin:6px 0}"
    ".xrpl{font-size:12.5px;color:var(--ink2);line-height:1.7;padding-left:1.2em;margin:4px 0}"
    "@media (max-width:640px){"
    ".xrb{grid-template-columns:minmax(0,1fr)}"
    ".xrs,.xrd,.xrr{margin-left:0}"
    ".xrr{padding:8px}"
    "table.xrvt td:first-child{min-width:8em}"
    "table.xrmt td:first-child,table.xrmt th:first-child{min-width:6em}"
    "}"
)
