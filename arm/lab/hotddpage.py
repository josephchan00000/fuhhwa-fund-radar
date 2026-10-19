"""景氣頁「過熱之後 3 個月的最大回撤」卡（docs/lab_hotdd_plan.md 第 4.9、6 節；規格 hotddspec VER 2）。

台股景氣頁、美股景氣頁（四個指數各一份）各一張卡，放在「短線大跌風險」卡下面：
  一句話        現在過熱中的面向與項目；過去同樣的情況之後 3 個月的最大回撤，判定比平常大／小的各幾項
  研究重點      這個市場全部比較的判定次數、技術面向進入過熱之後、大跌前 3 個月有沒有過熱（都由研究檔算）
  平常          任挑一天之後 3 個月的最大回撤（中位數、超過 10%、超過 20%、漲跌）
  現在過熱中    每一項：今天的 0～100、已連續幾週；進入過熱、連續滿 N 週之後：點圖（過去每一次）、中位數與比例（和平常比）、
                最差一次、這一次（之後 3 個月，不到 3 個月的算到今天）、過去每一次的清單
  剛結束過熱    最近 3 個月內「連續過熱 4 週以上之後結束」的
  收起          大跌前 3 個月有沒有過熱（跌 20% 以上的每一段 × 面向）、全部項目 × 6 種事件、怎麼算、主要假說
每天建頁只讀研究檔（hotdd.load_research）；現在的狀態每天重算（hotdd.now）。只描述過去，不寫買賣指示；用字照專案禁用詞。
"""
from __future__ import annotations

import html
import math

from . import hotddspec as S

VCLS = {"up": "weak", "down": "strong", "none": "none", "few": "few"}     # 同景氣頁：紅＝較弱（這裡是回撤較大）、藍＝較強
MARK = {"up": "▲", "down": "▼", "none": "·", "few": "—"}
EVL = {"E": "進入過熱", "S4": "連續過熱滿 4 週", "S8": "連續過熱滿 8 週", "S13": "連續過熱滿 13 週",
       "S26": "連續過熱滿 26 週", "X4": "過熱結束"}                  # X4＝之前連續過熱 4 週以上
ESHORT = {"E": "進入", "S4": "滿 4 週", "S8": "滿 8 週", "S13": "滿 13 週", "S26": "滿 26 週", "X4": "結束"}
ROWS_MAX = 4                    # 點圖最多疊幾排
LIST_MAX = 20                   # 「過去每一次」清單列最近幾次（點圖畫全部）
GAP = 2.8                       # 兩個點的水平距離小於軸寬的 2.8% 就換一排（點 9px、手機軸寬約 320px）


def _e(x) -> str:
    return html.escape(str(x), quote=True)


def _nan(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def pct(x, dec: int = 1) -> str:
    """比例或回撤（正數）→「12.3%」。"""
    return "—" if _nan(x) else f"{x * 100:.{dec}f}%"


def spct(x, dec: int = 1) -> str:
    """有正負的漲跌 →「+2.0%」「−3.4%」（先取位數再判正負；負號用全形減號，同景氣頁）。"""
    if _nan(x):
        return "—"
    r = round(x * 100, dec)
    return ("−" if r < 0 else ("+" if r > 0 else "")) + f"{abs(r):.{dec}f}%"


def ppt(x, dec: int = 1) -> str:
    """差（比例的差）→「+1.5 個百分點」。"""
    if _nan(x):
        return "—"
    r = round(x * 100, dec)
    return ("−" if r < 0 else ("+" if r > 0 else "")) + f"{abs(r):.{dec}f} 個百分點"


def ci(lo, hi, dec: int = 1) -> str:
    """區間 →「−3.5～+3.4 個百分點」。"""
    if _nan(lo) or _nan(hi):
        return "—"
    return ppt(lo, dec).replace(" 個百分點", "") + "～" + ppt(hi, dec)


def _d(d: str | None) -> str:
    """2024-07-11 → 2024/7/11。"""
    if not d or len(d) < 10:
        return "—"
    return f"{int(d[:4])}/{int(d[5:7])}/{int(d[8:10])}"


# ── 每天建頁的資料 ─────────────────────────────────────────────────────────

def state(B: dict) -> dict | None:
    """景氣頁的 B（heatcalc.build／heatcalc_us.build；美股要在 heatspec.use(該指數) 裡呼叫）→ 卡片要的資料；
    研究檔沒有、不是這一版就回 None（不顯示卡片）。"""
    from . import heatpage as HP
    from . import heatspec as HS
    from . import hotdd as K
    mk = "tw" if HP.MK["tab"] == "tw" else B.get("idx")
    R = K.load_research()
    if mk not in S.MARKETS or not R or mk not in (R.get("markets") or {}) or not B.get("cal"):
        return None
    RM = R["markets"][mk]
    N = K.now(B, RM)
    dims, items = K.variables(B)
    names = {d: HS.DIMS[d]["name"] for d in dims}
    names.update({r[0]: r[2] for r in HS.IND if r[0] in items})
    names.update(S.MKT_NAMES)
    tags = {d: "面向" for d in dims}
    tags.update({k: HS.DSHORT.get(HS.DIM_OF[k], "") for k in items})
    short = {d: HS.DSHORT.get(d, names[d]) for d in dims}
    T = len(B["cal"])
    today = {}                                        # 今天的值：(文字, 是否過熱)
    for k in dims + items:
        x = (B["comp"] if k in dims else B["hc"]).get(k) or [None] * T
        v = None if not x or x[-1] is None else float(x[-1])
        today[k] = None if v is None else (HP.n0(v) + (" 熱" if v >= S.HOT else ""), v >= S.HOT)
    m = N.get("multi") or {}
    today["M2"] = (f'{m.get("n", 0)} 個面向' + (" 熱" if m.get("n", 0) >= S.MULTI_K else ""), m.get("n", 0) >= S.MULTI_K)
    bn = HP.bubble_now(B)
    if bn and bn.get("L") is not None:
        for kk in S.BUB_K:
            today[f"BL{kk}"] = (f'等級 {bn["L"]}' + (" 熱" if bn["L"] >= kk else ""), bn["L"] >= kk)
    return {"mk": mk, "px": (HP.MK.get("px") or "").strip(), "R": RM, "now": N, "primary": R.get("primary") or {},
            "dims": dims, "items": items, "names": names, "tags": tags, "short": short, "today": today}


def _st(C: dict, k: str, e: str) -> dict:
    return ((((C["R"].get("rows") or {}).get(k) or {}).get("ev") or {}).get(e)) or {}


def lead(C: dict) -> list[str]:
    """一句話（第二句講現在過熱的那些，過去同樣的情況之後回撤的判定）：全部由研究檔與今天的值算出來。"""
    hot = C["now"]["hot"]
    if not hot:
        return ["現在沒有面向或項目在過熱（0～100 在 80 以上）。"]
    dims = [r for r in hot if r["kind"] == "dim"]
    its = [r for r in hot if r["kind"] == "item"]
    if dims:
        lst = "、".join(f'{C["short"][r["k"]]}已連續 {r["wk"]} 週' for r in dims)
        s1 = f"現在過熱中：{len(dims)} 個面向（{lst}）" + (f"，另有 {len(its)} 個項目。" if its else "。")
    else:
        s1 = f"現在過熱中：{len(its)} 個項目。"
    def cnt(pairs):
        c = {v: 0 for v in ("up", "down", "none", "few")}
        for k, e in pairs:
            c[_st(C, k, e).get("v") or "few"] += 1
        return c

    def seg(c):
        return "、".join(f"{lab} {c[v]} 項" for v, lab in (("up", "比平常大"), ("down", "比平常小"), ("none", "看不出差別"),
                                                         ("few", "次數太少")) if c[v])
    cE = cnt([(r["k"], "E") for r in hot])
    sx = [r for r in hot if len(r["ev"]) > 1]
    cS = cnt([(r["k"], r["ev"][-1]) for r in sx])
    up = cE["up"] + cS["up"]
    head = "沒有一項判定比平常大" if not up else f"有 {up} 個判定比平常大"
    s2 = (f"過去同樣的情況之後 3 個月的最大回撤，{head}。進入過熱之後：{seg(cE)}"
          + (f"；連續過熱滿 N 週之後（已連續 4 週以上的 {len(sx)} 項）：{seg(cS)}" if sx else "") + "。")
    return [s1, s2]


def keys(C: dict) -> list[str]:
    """研究重點三句：這個市場全部比較的判定次數、技術面向進入過熱之後、跌 20% 以上的大跌前有沒有出現技術面過熱。"""
    R = C["R"]
    yr = (R.get("start") or "")[:4]
    c = {v: 0 for v in ("up", "down", "none", "few")}
    for r in (R.get("rows") or {}).values():
        if r.get("kind") == "mkt":
            continue
        for st in (r.get("ev") or {}).values():
            c[st.get("v") or "few"] += 1
    n = sum(c.values())
    out = [f'{yr} 年起，面向與項目 × 6 種事件共 {n:,} 個比較：之後 3 個月最大回撤判定比平常大 {c["up"]} 個、比平常小 {c["down"]} 個，'
           f'其他 {c["none"] + c["few"]:,} 個看不出差別或次數太少。']
    st = _st(C, "tech", "E")
    if st.get("n"):
        ev, b = st.get("ev") or {}, st.get("base") or {}
        out.append(f'技術面向進入過熱之後（{st["n"]} 次）：最大回撤中位數 {pct(ev.get("med"))}，平常 {pct(b.get("med"))}；'
                   f'超過 10% 的比例 {pct(ev.get("q10"), 0)}，平常 {pct(b.get("q10"), 0)}——{S.VERDICT[st.get("v") or "few"]}。')
    rc = ((((R.get("rows") or {}).get("tech") or {}).get("rec") or {}).get("20")) or {}
    if rc.get("n"):
        out.append(f'跌 20% 以上的 {rc["n"]} 次大跌，高點前 3 個月出現技術面過熱的 {rc["h1"]} 次；'
                   f'任挑一段 3 個月，出現過熱的比例 {pct(rc.get("c1"), 0)}。')
    return out


# ── HTML ─────────────────────────────────────────────────────────────────

def xmax_of(C: dict) -> float:
    """點圖的橫軸上限（同一張卡共用，方便互相比）：要畫的回撤與今天這一次的最大值，往上取到 10% 的倍數，介於 30%～90%。"""
    vals = []
    for r in C["now"]["hot"] + C["now"]["exit"]:
        for e, inst in (r.get("inst") or {}).items():
            vals += [x[1] for x in (_st(C, r["k"], e).get("list") or [])]
            if inst.get("mdd") is not None:
                vals.append(inst["mdd"])
    m = max(vals) if vals else 0.0
    return min(0.9, max(0.3, math.ceil((m + 0.015) * 10) / 10))


def _rows(xs: list[float]) -> list[int]:
    """每個點放第幾排：由小到大排，和同一排前一個點太近就往下一排；四排都太近就放最空的那排。"""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    last = [None] * ROWS_MAX
    out = [0] * len(xs)
    for i in order:
        x = xs[i]
        r = next((k for k in range(ROWS_MAX) if last[k] is None or x - last[k] >= GAP), None)
        if r is None:
            r = min(range(ROWS_MAX), key=lambda k: last[k])
        out[i], last[r] = r, x
    return out


def strip(lst: list, base: dict, inst: dict | None, xmax: float, label: str) -> str:
    """點圖：每一點＝過去一次事件之後 3 個月的最大回撤；灰帶＝平常中間一半的日子、虛線＝平常的中位數；圓圈＝這一次（到今天）。"""
    X = lambda v: max(0.0, min(1.0, v / xmax)) * 100                          # noqa: E731
    s = []
    nt = int(round(xmax / 0.1))
    for k in range(1, nt):
        s.append(f'<span class="xogl{" xogt" if k in (1, 2) else ""}" style="left:{X(k / 10):.2f}%"></span>')
    p25, p75, med = base.get("p25"), base.get("p75"), base.get("med")
    if p25 is not None and p75 is not None:
        s.append(f'<span class="xobd" style="left:{X(p25):.2f}%;width:{max(0.6, X(p75) - X(p25)):.2f}%"></span>')
    if med is not None:
        s.append(f'<span class="xobm" style="left:{X(med):.2f}%"></span>')
    xs = [X(x[1]) for x in lst]
    for x, rw, ev in zip(xs, _rows(xs), lst):
        tip = f"{_d(ev[0])}：{pct(ev[1])}"
        s.append(f'<span class="xodt xoy{rw}" style="left:{x:.2f}%" title="{_e(tip)}"></span>')
    if inst and inst.get("mdd") is not None:
        tip = f"這一次（{_d(inst['d'])} 起 {inst['days']} 個交易日）：最大回撤 {pct(inst['mdd'])}"
        s.append(f'<span class="xonw{"" if inst.get("full") else " xopart"}" style="left:{X(inst["mdd"]):.2f}%" '
                 f'title="{_e(tip)}"></span>')
    ax = "".join(f'<span style="left:{X(k / 10):.2f}%">{k * 10}%</span>' for k in range(0, nt + 1))
    return (f'<div class="xoss" role="img" aria-label="{_e(label)}"><div class="xopl">{"".join(s)}</div>'
            f'<div class="xoax">{ax}</div></div>')


def legend() -> str:
    return ('<div class="xolg"><span><i class="xolgd"></i>過去每一次（點上去看日期）</span>'
            '<span><i class="xolgb"></i>平常：中間一半的日子</span><span><i class="xolgm"></i>平常的中位數</span>'
            '<span><i class="xolgn"></i>這一次（到今天）</span></div>')


def _inst_txt(e: str, inst: dict) -> str:
    what = {"E": "開始過熱", "X4": "結束過熱"}.get(e, EVL[e])
    if inst.get("mdd") is None:
        return f'這一次：{_d(inst["d"])} {what}，還沒有之後的收盤。'
    tail = "（3 個月已走完）" if inst.get("full") else "（還沒滿 3 個月）"
    return (f'這一次：{_d(inst["d"])} {what}，之後 {inst["days"]} 個交易日{tail}最大回撤 {pct(inst["mdd"])}'
            f'（{_d(inst.get("pk"))} → {_d(inst.get("tr"))}），期間漲跌 {spct(inst.get("chg"))}。')


def block(C: dict, k: str, e: str, inst: dict | None, xmax: float) -> str:
    """一種事件：判定、點圖、和平常比、最差一次、這一次、過去每一次的清單。"""
    st = _st(C, k, e)
    v = st.get("v") or "few"
    n = st.get("n") or 0
    head = (f'<div class="xorh"><span class="vt {VCLS[v]}">{_e(S.VERDICT[v])}</span>'
            f'<b>{_e(EVL[e])}之後 3 個月</b><span class="xof">過去 {n} 次（{st.get("ep") or 0} 段）'
            + (f'，{_e((st.get("a") or "")[:4])} 年起' if n else "") + '</span></div>')
    now_txt = f'<p class="xonow">{_e(_inst_txt(e, inst))}</p>' if inst else ""
    if not n:
        return f'<div class="xor">{head}<p class="xof2">過去沒有這種情況，沒有可以比的。</p>{now_txt}</div>'
    ev, b, w = st.get("ev") or {}, st.get("base") or {}, st.get("worst") or {}
    lst = st.get("list") or []
    pic = strip(lst, b, inst, xmax, f'{C["names"][k]}{EVL[e]}之後 3 個月的最大回撤，過去 {n} 次')
    grid = (f'<dl class="xog"><div><dt>中位數</dt><dd>{pct(ev.get("med"))}<small>平常 {pct(b.get("med"))}</small></dd></div>'
            f'<div><dt>超過 10%</dt><dd>{pct(ev.get("q10"), 0)}<small>平常 {pct(b.get("q10"), 0)}</small></dd></div>'
            f'<div><dt>超過 20%</dt><dd>{pct(ev.get("q20"), 0)}<small>平常 {pct(b.get("q20"), 0)}</small></dd></div>'
            f'<div><dt>最差一次</dt><dd>{pct(w.get("mdd"))}<small>{_e(_d(w.get("pk")))} → {_e(_d(w.get("tr")))}</small></dd></div></dl>')
    foot = (f'平均差 {ppt(st.get("d"))}（95% 區間 {ci(st.get("lo"), st.get("hi"))}）；扣掉波動 {ppt(st.get("vadj"))}；'
            f'3 個月漲跌平均 {spct(ev.get("r60"))}，平常 {spct(b.get("r60"))}')
    rows = []
    if inst and inst.get("mdd") is not None:
        rows.append(f'<tr class="xocur"><td>{_e(_d(inst["d"]))}<small>這一次</small></td><td>{pct(inst["mdd"])}</td>'
                    f'<td>{_e(_d(inst.get("pk")))} → {_e(_d(inst.get("tr")))}</td><td>{spct(inst.get("chg"))}</td></tr>')
    for x in sorted(lst, key=lambda r: r[0], reverse=True)[:LIST_MAX]:
        rows.append(f'<tr><td>{_e(_d(x[0]))}</td><td>{pct(x[1])}</td><td>{_e(_d(x[4]))} → {_e(_d(x[5]))}</td>'
                    f'<td>{spct(x[3])}</td></tr>')
    cap = f"最近 {LIST_MAX} 次（共 {n} 次，點圖畫全部）" if n > LIST_MAX else f"過去每一次（{n} 次）"
    tbl = (f'<details class="xoev"><summary>{cap}</summary><div class="xoevw"><table class="xoet">'
           '<tr><th>日期</th><th>3 個月最大回撤</th><th>高點 → 低點</th><th>3 個月漲跌</th></tr>'
           + "".join(rows) + "</table></div></details>")
    return f'<div class="xor">{head}{pic}{grid}{now_txt}<p class="xox">{_e(foot)}</p>{tbl}</div>'


def _sum_line(C: dict, k: str, evs: list[str]) -> str:
    out = []
    for e in evs:
        st = _st(C, k, e)
        ev = st.get("ev") or {}
        v = st.get("v") or "few"
        if st.get("n"):
            txt = f'中位數 {pct(ev.get("med"))}・超過 10% {pct(ev.get("q10"), 0)}・{st["n"]} 次'
        else:
            txt = "過去沒有"
        out.append(f'<span class="xose"><i>{_e(EVL[e])}之後</i>{_e(txt)}<em class="xom{v}">{_e(S.VERDICT[v])}</em></span>')
    return "".join(out)


def hot_row(C: dict, r: dict, xmax: float) -> str:
    k = r["k"]
    from .heatpage import n0
    wk = f'已連續 {r["wk"]} 週' if r["wk"] else "這週才過熱"
    blocks = "".join(block(C, k, e, r["inst"].get(e), xmax) for e in r["ev"])
    return (f'<details class="xoi" data-k="{_e(k)}"{" open" if r["kind"] == "dim" else ""}>'
            f'<summary><span class="xot"><b>{_e(C["names"][k])}</b><span class="kk">{_e(C["tags"].get(k, ""))}</span>'
            f'<span class="xov zt4">{_e(n0(r["v"]))}</span><span class="kw">{_e(wk)}（這一段從 {_e(_d(r["start"]))} 起）</span></span>'
            f'<span class="xos">{_sum_line(C, k, r["ev"])}</span></summary>{blocks}</details>')


def exit_row(C: dict, r: dict, xmax: float) -> str:
    k = r["k"]
    from .heatpage import n0
    inst = r["inst"]["X4"]
    return (f'<details class="xoi" data-k="{_e(k)}">'
            f'<summary><span class="xot"><b>{_e(C["names"][k])}</b><span class="kk">{_e(C["tags"].get(k, ""))}</span>'
            f'<span class="xov">{_e(n0(r["v"]))}</span><span class="kw">{_e(_d(inst["d"]))} 結束過熱</span></span>'
            f'<span class="xos">{_sum_line(C, k, ["X4"])}</span></summary>{block(C, k, "X4", inst, xmax)}</details>')


def base_html(C: dict) -> str:
    b = C["R"].get("base") or {}
    yr = (C["R"].get("start") or "")[:4]
    return (f'<div class="xobase"><p class="xobh">平常（{_e(yr)} 年起任挑一天，共 {b.get("n") or 0:,} 天）之後 3 個月：</p>'
            f'<dl class="xog"><div><dt>最大回撤中位數</dt><dd>{pct(b.get("med"))}</dd></div>'
            f'<div><dt>超過 10%</dt><dd>{pct(b.get("q10"), 0)}</dd></div>'
            f'<div><dt>超過 20%</dt><dd>{pct(b.get("q20"), 0)}</dd></div>'
            f'<div><dt>3 個月漲跌平均</dt><dd>{spct(b.get("r60"))}<small>上漲 {pct(b.get("up"), 0)}</small></dd></div></dl></div>')


def decl_html(C: dict) -> str:
    """跌 20% 以上的每一段 × 面向：高點前 3 個月有沒有過熱（● 連續 4 週以上、○ 有過熱、· 沒有、— 還沒有資料）。"""
    R = C["R"]
    dl = (R.get("decl") or {}).get("20") or []
    if not dl:
        return ""
    dims = C["dims"]
    head = "<tr><th>高點</th><th>低點</th><th>跌幅</th>" + "".join(f"<th>{_e(C['short'][d])}</th>" for d in dims) + "</tr>"
    sym = lambda h: "—" if h is None else ("●" if h[1] else ("○" if h[0] else "·"))                 # noqa: E731
    rows = []
    for e in dl:
        cells = "".join(f'<td class="xoh{"1" if (e["dims"].get(d) or [0])[0] else "0"}">{sym(e["dims"].get(d))}</td>'
                        for d in dims)
        op = "<small>還沒反彈</small>" if e.get("open") else ""
        rows.append(f'<tr><td>{_e(_d(e["pk"]))}</td><td>{_e(_d(e["tr"]))}{op}</td><td>{pct(e["dd"], 0)}</td>{cells}</tr>')

    def rec(d, th):
        return ((((R.get("rows") or {}).get(d) or {}).get("rec") or {}).get(th)) or {}
    rows.append('<tr class="xosm"><td colspan="3">高點前 3 個月有過熱</td>'
                + "".join(f'<td>{rec(d, "20").get("h1", 0)}／{rec(d, "20").get("n", 0)}</td>' for d in dims) + "</tr>")
    rows.append('<tr class="xosm"><td colspan="3">任挑一段 3 個月有過熱</td>'
                + "".join(f'<td>{pct(rec(d, "20").get("c1"), 0)}</td>' for d in dims) + "</tr>")
    ten = "；".join(f'{C["short"][d]} {rec(d, "10").get("h1", 0)}／{rec(d, "10").get("n", 0)}（任挑 {pct(rec(d, "10").get("c1"), 0)}）'
                   for d in dims if rec(d, "10").get("n"))
    return (f'<details class="xomore"><summary>大跌前 3 個月有沒有過熱（跌 20% 以上的 {len(dl)} 次）</summary>'
            '<p class="xomh">想靠過熱避開大跌，要看兩件事：大跌之前有沒有先出現過熱，以及平常隨便哪一段 3 個月出現過熱的機率有多高。'
            '大跌段＝從最高收盤跌 20% 以上、從低點反彈 20% 才算結束；看高點那天和之前 60 個交易日。</p>'
            f'<div class="tw"><table class="xodtb">{head}{"".join(rows)}</table></div>'
            f'<p class="note">● 高點前 3 個月有一個週末已經連續過熱滿 4 週；○ 有過熱（≥ 80）但沒有連續 4 週；· 沒有過熱；'
            f'— 那時這個面向還沒有資料（或資料不滿 3 個月）。跌 10% 以上的大跌：{_e(ten)}。</p></details>')


def table_html(C: dict) -> str:
    """全部面向與項目 × 6 種事件：之後 3 個月最大回撤的中位數＋判定（▲ 較大、▼ 較小、· 看不出、— 樣本不足）。"""
    head = '<tr><th class="l">項目</th><th>今天</th>' + "".join(f"<th>{_e(ESHORT[e])}</th>" for e in S.EVENTS) + "</tr>"
    rows = []
    for k in C["dims"] + list(S.MKT_VARS) + C["items"]:
        if k not in (C["R"].get("rows") or {}):
            continue
        tv = C["today"].get(k)
        tcell, thot = tv if tv else ("—", False)
        cells = []
        for e in S.EVENTS:
            st = _st(C, k, e)
            if not st:
                cells.append('<td class="xoe"></td>')
                continue
            v = st.get("v") or "few"
            ev = st.get("ev") or {}
            tip = f'{st.get("n") or 0} 次，平常 {pct((st.get("base") or {}).get("med"))}'
            txt = f'{pct(ev.get("med"))} {MARK[v]}' if st.get("n") else MARK[v]
            cells.append(f'<td data-h="{_e(ESHORT[e])}" class="xom{v}" title="{_e(tip)}">{_e(txt)}</td>')
        nm = C["names"].get(k, k)
        tg = C["tags"].get(k) or ("綜合" if k in S.MKT_VARS else "")
        rows.append(f'<tr><td class="l">{_e(nm)}<span class="xotg">{_e(tg)}</span></td>'
                    f'<td data-h="今天" class="{"zt4" if thot else ""}">{_e(tcell)}</td>{"".join(cells)}</tr>')
    lg = "　".join(f"{MARK[v]} {S.VERDICT[v]}" for v in ("up", "down", "none", "few"))
    return (f'<div class="tw"><table class="xomt">{head}{"".join(rows)}</table></div>'
            f'<p class="note">每一格＝那種事件之後 3 個月最大回撤的中位數，旁邊是判定：{_e(lg)}。'
            f'欄位：{_e("、".join(f"{ESHORT[e]}＝{EVL[e]}" for e in S.EVENTS))}（之前連續過熱 4 週以上）。'
            f'樣本不足＝過去不到 {S.MIN_EVENTS} 次或不到 {S.MIN_EPISODES} 段（相隔 {S.EP_GAP} 個交易日以內算同一段）。</p>')


def primary_html(C: dict) -> str:
    """事前寫定的 4 個主要假說：一句總結；只列和這個市場有關的。"""
    P = C.get("primary") or {}
    n_ok = sum(1 for h in S.PRIMARY if (P.get(h) or {}).get("ok"))
    li = []
    for h, spec in S.PRIMARY.items():
        if spec["mk"] != C["mk"]:
            continue
        r = P.get(h) or {}
        if r.get("few") or r.get("d") is None:
            res = f'樣本不足（{r.get("n") or 0} 次、{r.get("ep") or 0} 段）'
        else:
            res = (f'{r["n"]} 次，平均差 {ppt(r["d"])}（95% 區間 {ci(r["lo"], r["hi"])}），'
                   f'Holm 校正後 p＝{r["padj"]:.3f}，{"成立" if r.get("ok") else "不成立"}')
        li.append(f'<li><b>{h}</b> {_e(spec["text"])}：{_e(res)}</li>')
    tl = f"{len(S.PRIMARY)} 個都沒有通過" if not n_ok else f"{n_ok} 個通過"
    tail = "下面是和這個市場有關的。" if li else "沒有一個是針對這個指數的。"
    return (f'<p class="xomh"><b>事前寫定的 {len(S.PRIMARY)} 個主要假說</b>（都是「之後 3 個月的平均最大回撤比平常大」；'
            f'Holm 校正、單尾）：{tl}；{tail}</p>' + (f'<ul class="xopl2">{"".join(li)}</ul>' if li else ""))


def method_html(C: dict) -> str:
    px = C.get("px") or ""
    lim = ("加權指數是價格指數（不含息）" if C["mk"] == "tw" else f"{px} 是價格指數（不含股利）")
    return ('<div class="xomh">'
            '<p><b>怎麼算</b>：每一次事件（進入過熱、連續過熱滿 N 週、連續過熱 4 週以上之後結束）之後，從隔天收盤起算 60 個交易日'
            '（約 3 個月），找出這段期間從最高收盤跌到之後最低收盤的最大跌幅（最大回撤）；和同一段期間任挑一天的最大回撤比。'
            '過熱＝0～100 在 80 以上；連續幾週＝每週最後一個交易日都在 80 以上。</p>'
            '<p><b>判定</b>：平均差的 95% 區間用 60 個交易日一塊重抽 2,000 次；區間不含 0、前後兩半方向一樣，'
            '而且同一種事件的全部項目一起做多重比較校正後 q ≤ 0.10，才寫「回撤較大」或「回撤較小」。'
            f'過去不到 {S.MIN_EVENTS} 次或不到 {S.MIN_EPISODES} 段＝樣本不足，只列出每一次。</p>'
            '<p><b>扣掉波動</b>：過熱常出現在漲勢穩、波動低的時候，這種時候本來就回撤小；依當時的 20 日波動分三組、在組內比，'
            '寫在每一項的小字（不改判定）。</p>'
            f'<p><b>限制</b>：{_e(lim)}；泡沫等級用泡沫頁的歷史判定（估值和全部歷史比，用到之後的資料，只當參考）。'
            '規格在看結果之前寫定（VER 1；VER 2 只改大跌段的定義，同日），規劃文件 docs/lab_hotdd_plan.md 第 4、5 節。</p></div>')


def card(C: dict | None, note: str | None = None) -> str:
    """整張卡；C＝state() 的結果（None＝研究檔沒有，不顯示）；note＝研究重點最後加一句（下一張「反向檢查」卡的提示）。"""
    if not C:
        return ""
    from .heatpage import _md
    N = C["now"]
    xmax = xmax_of(C)
    ls = lead(C)
    lead_html = f'<p class="xol">{_e(ls[0])}</p>' + "".join(f'<p class="xol2">{_e(s)}</p>' for s in ls[1:])
    kk = "".join(f"<li>{_e(s)}</li>" for s in keys(C) + ([note] if note else []))
    hot = "".join(hot_row(C, r, xmax) for r in N["hot"])
    ex = "".join(exit_row(C, r, xmax) for r in N["exit"])
    sec_hot = ""
    if N["hot"]:
        nd = sum(1 for r in N["hot"] if r["kind"] == "dim")
        how = "面向已展開，項目點一下展開" if nd else "點一下展開"
        sec_hot = (f'<h3 class="xoh3">現在過熱中<span class="sub">{len(N["hot"])} 項；{how}</span></h3>{legend()}'
                   f'<div class="xols">{hot}</div>')
    sec_ex = ""
    if N["exit"]:
        sec_ex = (f'<h3 class="xoh3">最近 3 個月結束過熱<span class="sub">之前連續過熱 4 週以上；{len(N["exit"])} 項</span></h3>'
                  f'<div class="xols">{ex}</div>')
    nall = len(C["dims"]) + len(C["items"])
    px = C.get("px") or ""
    px = px + (" " if px and px[-1].isascii() else "")      # 「S&P 500 接下來」：英數字結尾補一個空格
    return (f'<section class="sec xosec" id="hotdd"><div class="card xoc">'
            f'<div class="khd"><h2>過熱之後 3 個月的最大回撤</h2><span class="kn">之後 60 個交易日・資料到 {_e(_md(N.get("d")))}</span></div>'
            f'{lead_html}'
            f'<p class="ksub">過熱之後（進入過熱、連續過熱滿 N 週、過熱結束），{_e(px)}接下來 3 個月最多從高點跌多少，'
            '和平常任挑一天比。只描述過去，不是買賣指示。</p>'
            f'<ul class="xokey">{kk}</ul>{base_html(C)}{sec_hot}{sec_ex}{decl_html(C)}'
            f'<details class="xomore"><summary>全部 {nall} 項 × 6 種事件的判定、怎麼算、主要假說</summary>'
            f'{table_html(C)}{method_html(C)}{primary_html(C)}</details>'
            '</div></section>')


CSS = (
    ".xoc{padding:12px 14px;min-width:0}"
    ".xol{font-size:15px;font-weight:700;margin:8px 0 4px;line-height:1.6}"
    ".xol2{font-size:13.5px;color:var(--ink2);margin:0 0 4px;line-height:1.65}"
    ".xokey{margin:8px 0 6px;padding-left:1.2em;font-size:13px;color:var(--ink2);line-height:1.7}"
    ".xokey li{margin:2px 0}"
    ".xobase{margin:10px 0 4px;padding:8px 10px;background:var(--card2);border-radius:10px}"
    ".xobh{font-size:12.5px;color:var(--mut);margin:0 0 4px}"
    ".xog{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px 12px;margin:6px 0 0}"
    ".xog div{min-width:0}"
    ".xog dt{font-size:11.5px;color:var(--mut)}"
    ".xog dd{margin:0;font-size:15px;font-weight:700;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}"
    ".xog small{display:block;font-size:11px;font-weight:400;color:var(--mut);line-height:1.45}"
    ".xoh3{font-size:15px;margin:16px 0 2px}"
    ".xolg{display:flex;flex-wrap:wrap;gap:2px 14px;font-size:11.5px;color:var(--mut);margin:2px 0 4px}"
    ".xolg span{display:inline-flex;align-items:center;gap:5px}"
    ".xolg i{display:inline-block;flex:none}"
    ".xolgd{width:9px;height:9px;border-radius:50%;background:var(--t4);opacity:.8}"
    ".xolgb{width:16px;height:9px;background:var(--line);border-radius:2px}"
    ".xolgm{width:0;height:11px;border-left:2px dashed var(--ink2)}"
    ".xolgn{width:9px;height:9px;border-radius:50%;border:2px solid var(--ink)}"
    ".xoi{border-top:1px solid var(--line);padding:8px 0 6px}"
    ".xoi>summary{cursor:pointer;line-height:1.6}"
    ".xoi>summary::marker{color:var(--mut)}"
    ".xot{display:inline}"
    ".xot>*{margin-right:8px}"
    ".xot b{font-size:14.5px}"
    ".xov{font-size:14.5px;font-weight:800}"
    ".xos{display:flex;flex-direction:column;gap:1px;margin:2px 0 0 1.15em;font-size:12.5px;color:var(--ink2)}"
    ".xose i{font-style:normal;color:var(--mut);margin-right:6px}"
    ".xose em{font-style:normal;font-size:11.5px;margin-left:6px}"
    ".xomup{color:var(--t4);font-weight:700}.xomdown{color:var(--t0);font-weight:700}.xomnone,.xomfew{color:var(--mut)}"
    ".xor{margin:8px 0 4px 1.15em;padding:8px 10px;background:var(--card2);border-radius:10px;min-width:0}"
    ".xorh{display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 8px}"
    ".xorh .vt{margin:0}"
    ".xorh b{font-size:13.5px}"
    ".xof{font-size:11.5px;color:var(--mut)}"
    ".xof2{font-size:12.5px;color:var(--mut);margin:6px 0 0}"
    ".xoss{margin:8px 4px 2px}"
    ".xopl{position:relative;height:46px;border-bottom:1px solid var(--line2)}"
    ".xogl{position:absolute;top:0;bottom:0;width:0;border-left:1px solid var(--line)}"
    ".xogt{border-left-color:var(--line2)}"
    ".xobd{position:absolute;top:3px;bottom:3px;background:var(--line);border-radius:3px}"
    ".xobm{position:absolute;top:0;bottom:0;width:0;border-left:2px dashed var(--ink2)}"
    ".xodt{position:absolute;width:9px;height:9px;margin:-4.5px 0 0 -4.5px;border-radius:50%;background:var(--t4);opacity:.85;"
    "box-shadow:0 0 0 2px var(--card2);cursor:default}"
    ".xodt:hover{opacity:1;box-shadow:0 0 0 2px var(--card2),0 0 0 3.5px var(--ink)}"
    ".xoy0{top:9px}.xoy1{top:19px}.xoy2{top:29px}.xoy3{top:39px}"
    ".xonw{position:absolute;top:23px;width:15px;height:15px;margin:-7.5px 0 0 -7.5px;border-radius:50%;"
    "border:2.5px solid var(--ink);background:transparent;box-sizing:border-box;z-index:1}"
    ".xonw.xopart{border-style:dashed}"
    ".xoax{position:relative;height:16px;font-size:10.5px;color:var(--mut)}"
    ".xoax span{position:absolute;top:2px;transform:translateX(-50%);white-space:nowrap}"
    ".xoax span:first-child{transform:none}.xoax span:last-child{transform:translateX(-100%)}"
    ".xonow{font-size:12.5px;color:var(--ink);margin:8px 0 0;line-height:1.6}"
    ".xox{font-size:11.5px;color:var(--mut);margin:4px 0 0;line-height:1.6}"
    ".xoev{margin-top:6px}"
    ".xoev>summary{cursor:pointer;font-size:12.5px;color:var(--acc)}"
    ".xoevw{max-height:18em;overflow:auto;margin-top:4px}"
    "table.xoet{font-size:12px;width:100%}"
    "table.xoet th,table.xoet td{padding:4px 6px;text-align:right}"
    "table.xoet th:first-child,table.xoet td:first-child{text-align:left}"
    "table.xoet small{display:block;font-size:10.5px;color:var(--mut)}"
    "tr.xocur td{font-weight:700}"
    ".xomore{margin-top:12px}"
    ".xomore>summary{cursor:pointer;font-size:13px;color:var(--acc);padding:8px 0 2px;border-top:1px solid var(--line)}"
    ".xomore[open]>summary{margin-bottom:8px}"
    ".xomh,.xomh p{font-size:12.5px;color:var(--ink2);line-height:1.7;margin:6px 0}"
    ".xopl2{font-size:12.5px;color:var(--ink2);line-height:1.7;padding-left:1.2em;margin:4px 0}"
    "table.xodtb th,table.xodtb td{padding:4px 6px;text-align:center}"
    "table.xodtb td:nth-child(-n+3){text-align:left}"
    "table.xodtb small{display:block;font-size:10.5px;color:var(--mut)}"
    ".xoh1{color:var(--t4);font-weight:800}.xoh0{color:var(--mut)}"
    "tr.xosm td{font-size:12px;color:var(--ink2);background:var(--card2)}"
    "table.xomt th,table.xomt td{padding:5px 4px;text-align:center}"
    "table.xomt td:first-child,table.xomt th:first-child{white-space:normal;min-width:8em;text-align:left}"
    ".xotg{display:block;font-size:11px;color:var(--mut)}"
    "@media (max-width:640px){"
    ".xog{grid-template-columns:repeat(2,minmax(0,1fr))}"
    ".xos,.xor{margin-left:0}"
    ".xor{padding:8px}"
    "table.xomt,table.xomt tbody{display:block}table.xomt tr:first-child{display:none}"
    "table.xomt tr{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:2px 8px;padding:8px 2px;"
    "border-bottom:1px solid var(--line)}"
    "table.xomt td{display:block;border:0;padding:0;text-align:left;font-size:12px;min-width:0!important;white-space:nowrap}"
    "table.xomt td:first-child{grid-column:1/3;white-space:normal}"
    "table.xomt td:nth-child(2){grid-column:3/4;text-align:right}"
    "table.xomt td[data-h]::before{content:attr(data-h) \" \";color:var(--mut);font-size:11px}"
    "table.xomt td:nth-child(2)::before{content:none}"
    "table.xomt td.xoe{display:none}"
    "}"
)
