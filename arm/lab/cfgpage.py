"""配置頁（x9.html 的「配置」：台股｜美股｜策略｜個股（工具）；docs/lab_ia_v5_plan.md 第 18 節）。

使用者 2026-10-23（看過第五版示意圖）：「好 請完全依照你所規劃的步驟逐步執行」。版面：
- 台股、美股各一頁，每頁三塊：①時程與水位（四格、水位長條、警訊、規則、成績、下一個交易日要做的事、時間軸）
  ②持股細節（標的｜比重｜來源｜現況）③這個市場的策略一行。美股整合成一個計畫：長抱 S&P 500＋三成美股強勢品質股；
  那斯達克 100 的版本只在成績下面一行。
- 策略頁＝全部策略一張表（board.py；使用中／觀察中／候選／淘汰）。

數字全部來自現有的研究檔與當天的計算（core、corepage、advice、xsadvice、ussxqm），這裡只組版面，不算任何新數字。
三種警訊今天的讀數要景氣頁算（同一個程序裡較晚才建），所以 x9.html 建兩次：個股頁建頁時先用上一版的讀數
（x9or-{市場}.json），景氣頁建完後 page.finish() 用今天的讀數重建（gen_fund_dashboard.py）。
JS 由 page.render 插在頁面初始化之前（同 stockviz、macpage、copage）；函式一律 cf 開頭，不和其他三支撞名。
"""
from __future__ import annotations

import html

from .. import fund_intro as FI
from . import board as BD
from . import corepage as CPG
from . import corespec as S

PLAN_MK = {"tw": "tw", "us": "spx"}             # 配置頁的市場 → 交易計畫的市場鍵
CORE_ETF = {"tw": "0050", "us": "SPY／VOO"}
SHORT = {"s3": "臺灣50", "v3l": "財報驚喜", "s5": "長線", "s1": "共識加碼", "v7l": "月營收大型", "v3m": "財報中型",
         "v7m": "月營收中型", "hd": "高股息", "qm": "強勢品質股"}
ACT_PILL = {"買進": "b", "賣出": "s", "換股": "w", "調整": "a", "可能買進": "a"}


def _e(x) -> str:
    return html.escape(str(x if x is not None else ""))


def _md(d) -> str:
    return CPG._md(d)


def _mdw(d) -> str:
    return CPG._mdw(d)


def _wp(w: float) -> str:
    return CPG._wp(w)


def _pc(x, d: int = 1) -> str:
    return CPG._pc(x, d)


# ── 共用 ─────────────────────────────────────────────────────────────────────

def _tiles(cells: list[tuple[str, str, str]]) -> str:
    return '<div class="cftiles">' + "".join(
        f'<div class="cftile"><div class="cfl">{l}</div><div class="cfv">{v}</div><div class="cfs">{s}</div></div>' for l, v, s in cells) + "</div>"


def _fam_name(mk: str, k: str) -> str:
    return CPG.plain(mk, k)


def warn_row(mk: str, N: dict) -> str:
    """警訊一行：0／3＋每個警訊一條小長條與分數（長條碰到直線就是警訊；年線：一半＝在年線上，越長越接近跌破）。"""
    out = []
    for f in N["fams"]:
        on, nm = f["lit"], _fam_name(mk, f["k"])
        if f["k"] == "trend":
            pct = f.get("pct")
            if pct is None:
                w, mark, val = 0.0, 50.0, "算不出來"
            else:
                w, mark = max(0.0, min(100.0, 50.0 - pct * 2.5)), 50.0
                val = f'比年線{"低" if pct < 0 else "高"} {abs(pct):.1f}%'
            nm = "年線"
        elif f["k"] == "flat":
            held, na = f.get("held") or [], f.get("n_all") or 0
            w, mark = (100.0 * (1 - len(held) / na) if na else (100.0 if on else 0.0)), 99.0
            val = "全部空手" if on else f"{len(held)} 條有部位"
            nm = "總經策略"
        else:
            v = f.get("v")
            w, mark = (0.0 if v is None else max(0.0, min(100.0, v))), S.HOT
            val = "沒有資料" if v is None else f"{v:.1f}"
        out.append(f'<span class="cfwi{" on" if on else ""}">{_e(nm)}<i class="cfwb"><i style="width:{w:.1f}%"></i>'
                   f'<u style="left:{mark:.0f}%"></u></i>{_e(val)}</span>')
    n = N["n"]
    return (f'<div class="cfwarn"><span class="cfwl">警訊 <b class="{"on" if n else "ok"}">{n}／{len(N["fams"])}</b></span>'
            + "".join(out) + "</div>")


def rule_line(mk: str) -> str:
    pm = PLAN_MK[mk]
    need = S.REENTRY.get(pm, 1)
    if pm in S.FLAT:
        return "兩個以上成立，或總經策略全部空手：隔天收盤把機動 30% 換成現金，都解除了隔天收盤買回"
    return ("兩個以上成立：隔天收盤把機動 30% 換成現金" +
            ("，警訊少於兩個滿兩週才買回" if need > 1 else "，解除了隔天收盤買回"))


def due_line(mk: str, N: dict) -> str:
    """要調整水位的那一句（不用調整回空字串）。"""
    pm = PLAN_MK[mk]
    cash, need = N["next"] < 0.99, N.get("need") or 1
    day = CPG._next_day(pm, N["d"]) if N.get("due") else None
    lit = "、".join(_fam_name(pm, f["k"]) for f in N["fams"] if f["lit"])
    if day and cash:
        return f'<p class="cfdue"><b>{_e(_mdw(day))} 收盤：把機動 30% 賣掉換成現金</b>（{_e(lit)}）</p>'
    if day:
        return f'<p class="cfdue ok"><b>{_e(_mdw(day))} 收盤：把機動 30% 買回來</b></p>'
    if cash and N.get("ok") and need > 1:
        c = N.get("clear") or 0
        buy = CPG._next_day_n(pm, N["d"], need - c + 1)
        return f'<p class="cfdue">機動 30% 放現金中；警訊少於兩個第 {c} 天，接下來都沒有警訊的話最快 {_e(_mdw(buy))} 收盤買回</p>'
    if cash:
        return '<p class="cfdue">機動 30% 放現金中；警訊解除後隔天收盤買回</p>'
    return ""


def _sc(mk: str, bundle: dict) -> dict:
    """研究檔裡這個市場的計畫（美股三成放強勢品質股時，plan 換成 QM 的版本，同 corepage.card）。"""
    pm = PLAN_MK[mk]
    R, qm = bundle.get("R") or {}, bundle.get("qm")
    sc = (((R.get("mk") or {}).get(pm) or {}).get("sc")) or {}
    if CPG.qm_on(pm, qm) and (((qm or {}).get("R") or {}).get("sc") or {}).get(pm):
        sc = {**sc, "plan": qm["R"]["sc"][pm]}
    return sc


def perf_line(mk: str, bundle: dict) -> str:
    sc = _sc(mk, bundle)
    s = sc.get("plan") or sc.get("rule")
    if not s:
        return '<div class="cfperf">過去的成績還沒算出來。</div>'
    p, h = s["plan"], s["hold"]
    etf = "0050" if mk == "tw" else "SPY"
    txt = (f'{s["a"][:4]} 起 100 萬變 <b>{CPG._wan(p["m"])}</b>（{etf} 抱著 {CPG._wan(h["m"])}）・最慘跌 <b>{CPG._ab(p["mdd"])}</b>'
           f'（{CPG._ab(h["mdd"])}）・年化 {_pc((p.get("cagr") or 0), 1).lstrip("+")}（{_pc((h.get("cagr") or 0), 1).lstrip("+")}）')
    out = f'<div class="cfperf">{txt}</div>'
    if mk == "us" and CPG.qm_on("ndx", bundle.get("qm")):
        q = (CPG._qm_plan("ndx", bundle.get("qm")).get("new")) or {}
        if q:
            out += (f'<div class="cfperf cfq">長抱改成那斯達克 100（QQQ）：同一套規則 100 萬變 <b>{CPG._wan(q["plan"]["m"])}</b>'
                    f'（那斯達克 100 抱著 {CPG._wan(q["hold"]["m"])}）・最慘跌 {CPG._ab(q["plan"]["mdd"])}（{CPG._ab(q["hold"]["mdd"])}）；配置照 S&amp;P 500</div>')
    return out


def detail_html(mk: str, bundle: dict) -> str:
    """細節（收起）：照做一年會怎樣、為什麼這樣設計、每一次換現金、逐年、不同期間、上線後怎麼檢查、風險。"""
    pm = PLAN_MK[mk]
    sc = _sc(mk, bundle)
    if not sc:
        return ""
    fw = (bundle.get("fw") or {}).get(pm)
    body = CPG.expect_html(pm, sc) + CPG.details_html(pm, sc, fw, bundle.get("qm"))
    return f'<details class="cfdet"><summary>細節</summary><div class="pln cfpln">{body}</div></details>'


def _stack(mk: str, N: dict | None, parts: list[tuple[str, float]]) -> str:
    """70／30 長條：長抱 70%＋機動三成的分配（放現金時整段標現金）。parts＝[(名稱, 占全部資金)]。"""
    cash = bool(N) and N["next"] < 0.99
    core = f'<div class="cfsc">長抱 70%　{_e(CORE_ETF[mk])}</div>'
    if cash:
        segs = '<div class="cfsx" style="flex:30">機動 30% 放現金</div>'
        lg = "機動 30% 放現金"
    else:
        segs = "".join(f'<div class="cfss cfs{i % 3}" style="flex:{max(1.0, w * 100):.2f}">{_e(n)} {_wp(w)}</div>' for i, (n, w) in enumerate(parts))
        lg = "機動：" + "・".join(f"{_e(n)} {_wp(w)}" for n, w in parts)
    return f'<div class="cfstack">{core}{segs}</div><div class="cfstlg">{lg}</div>'


def _items_txt(items: list, n_items: int | None = None, k: int = 5) -> str:
    nm = [f'{_e(x.get("n") or x.get("c"))}' + (f'<span class="mu">（{_e(x["cond"].replace(" 才買", ""))}）</span>' if x.get("cond") else "")
          for x in items or []]
    more = (n_items or len(nm)) - min(len(nm), k)
    return "、".join(nm[:k]) + (f" 等 {n_items or len(nm)} 檔" if more > 0 else "")


def _pill(at: str, act: str) -> str:
    return f'<span class="kact ka-{ACT_PILL.get(act, "a")}">{_e(at or "")}{_e(act)}</span>'


# ── 台股 ─────────────────────────────────────────────────────────────────────

def _usn(c: str, nms: dict | None) -> str:
    """美股一列的標的格（2026-10-24 使用者：「美股那些公司誰知道你是什麼公司…台股不都有列嗎？比照著做」）：
    公司名＋代號（同台股「台塑 1301」），下一行本業（簡介庫第一段，corepage.us_label）。"""
    nm, what = CPG.us_label(c, nms)
    head = f'{_e(nm)} <span class="cd">{_e(c)}</span>' if nm != c else _e(c)
    return head + (f'<div class="cfin">{_e(what)}</div>' if what else "")


def _tw_next(data: dict, bundle: dict, N: dict | None, d0: str | None) -> tuple[str, str | None]:
    """下一個交易日要做的事（台股）：計畫本身＋使用中的策略；觀察中的策略另外標。"""
    A = data.get("adv") or {}
    stk = bundle.get("stk") or {}
    use = {s["k"] for s in stk.get("st") or []}
    nx = CPG._next_day("tw", d0) if d0 else None
    if not nx:
        return "", None
    rows_use, rows_obs = [], []
    if N and N.get("due"):
        rows_use.append(f'<div class="cfnr">{_pill("收盤", "賣出" if N["next"] < 0.99 else "買進")}'
                        f'<b>機動 30% {"換成現金" if N["next"] < 0.99 else "買回來"}</b></div>')
    for e in A.get("cal") or []:
        if e.get("d") != nx:
            continue
        nm = e.get("sname") or e.get("k")
        it = _items_txt(e.get("items") or [])
        if not it and e.get("pending"):
            it = f'名單 {_e(_md(e.get("fix")))} 收盤產生'
        elif not it:
            it = _e(e.get("note") or "")
        row = f'<div class="cfnr">{_pill(e.get("at") or "", e.get("act") or "")}<b>{_e(nm)}</b><span class="cfni">{it}</span>'
        if e.get("k") in use:
            rows_use.append(row + "</div>")
        else:
            rows_obs.append(row + '<span class="cfob">觀察中的策略，不在配置裡</span></div>')
    MM = ((data.get("mac") or {}).get("m") or {}).get("tw") or {}
    for e in MM.get("cal") or []:
        if e.get("d") == nx:
            rows_obs.append(f'<div class="cfnr">{_pill("收盤", e.get("act") or "")}<b>{_e(e.get("name"))}</b>'
                            '<span class="cfob">指數型・觀察中，不在配置裡</span></div>')
    if not rows_use:
        later = sorted((e for e in stk.get("ev") or [] if (e.get("d") or "") > nx and e.get("k") in use),
                       key=lambda e: (e["d"], 0 if e.get("at") == "開盤" else 1))
        rows_use.append(_none_row(later[0] if later else None))
    return (f'<div class="cfnext"><div class="cfnd"><b>{_e(_mdw(nx))}</b><span>要做的事</span></div>'
            f'<div class="cfna">{"".join(rows_use + rows_obs)}</div></div>'), nx


def _none_row(e: dict | None) -> str:
    """下一個交易日使用中的策略沒有事：一句，附下一件是哪天、做什麼。
    e＝行事曆的一件事 {d, at, act, k, sname／name, items, n_items, pending, fix}，或已經組好的 {"what": HTML}。"""
    if not e:
        return '<div class="cfnr cfnone">使用中的策略沒有排定的買賣。</div>'
    nm = SHORT.get(e.get("k"), e.get("sname") or e.get("name") or "")
    what = e.get("what")
    if not what:
        items = e.get("items") or []
        n = e.get("n_items") or len(items)
        if e.get("act") == "買進" and e.get("pending"):
            what = f'買新名單（{_e(_md(e.get("fix")))} 收盤產生）'
        elif e.get("act") == "買進" and n:
            what = f'買{_items_txt(items, n, 3)}'
        elif e.get("act") == "賣出" and n:
            what = f'賣 {n} 檔'
        else:
            what = _e(e.get("act") or "")
    return (f'<div class="cfnr cfnone">使用中的策略沒有排定的買賣；下一件是 <b>{_e(_mdw(e["d"]))}{_e(e.get("at") or "")}</b>'
            f'：{_e(nm)}{what}。</div>')


def _tw_tiles(N: dict | None, stk: dict) -> str:
    st = stk.get("st") or []
    names = {s["k"]: SHORT.get(s["k"], s.get("name") or s["k"]) for s in st}
    buys = [e for e in stk.get("ev") or [] if e.get("act") == "買進"]
    known = [e for e in buys if not e.get("pending") and (e.get("n_items") or e.get("items"))]
    if known:
        e = known[0]
        nb = sum(e2.get("n_items") or len(e2.get("items") or []) for e2 in known)
        t1 = (f"{nb} 檔", f'{_e(_mdw(e["d"]))} {_e(e.get("at") or "")}・{_e(names.get(e["k"], e["k"]))}')
    elif buys:
        e = buys[0]
        t1 = ("—", f'名單 {_e(_md(e.get("fix")))} 收盤產生・{_e(names.get(e["k"], e["k"]))}')
    else:
        t1 = ("0 檔", "沒有排定的買進")
    hold = stk.get("hold") or {}
    nh = sum(len(v) for v in hold.values())
    t2 = (f"{nh} 檔", "・".join(f"{_e(names[k])} {len(hold.get(k) or [])}" for k in names if hold.get(k)) or "沒有持股")
    if N:
        t3 = (f'{round(N["next"] * 100)}%', f'現金 {round((1 - N["next"]) * 100)}%')
        t4 = (f'{N["n"]}／{len(N["fams"])}', "・".join(_e(_fam_name("tw", f["k"])) for f in N["fams"]))
    else:
        t3 = t4 = ("—", "今天的讀數還沒算出來")
    return _tiles([("待買進",) + t1, ("持有中",) + t2, ("股票水位",) + t3, ("警訊",) + t4])


def tw_hold(stk: dict, N: dict | None) -> str:
    """持股細節（台股）：長抱 70%＋三成每一檔（比重＝占全部資金）；沒部位的那一份寫在 0050 那一列。"""
    W = CPG.sat_weights(stk)
    cash = bool(N) and N["next"] < 0.99
    hmap = {(k, h.get("c")): h for k, hs in (stk.get("hold") or {}).items() for h in hs}
    nxt = {}
    for e in stk.get("ev") or []:
        nxt.setdefault(e["k"], e)
    rows = ['<tr class="g"><td colspan="4">長抱 70%</td></tr>',
            '<tr><td class="idx">0050／006208</td><td class="w">70%</td><td class="src">一直抱著</td><td class="st">—</td></tr>']
    st = stk.get("st") or []
    hd = (f"機動 30%：{len(st)} 條策略各 {_wp(S.SAT / len(st))}，沒有部位的那一份放 0050" if st else "機動 30%")
    if cash:
        hd = "機動 30%：放現金中；買回時照下面這樣買"
    rows.append(f'<tr class="g"><td colspan="4">{hd}</td></tr>')
    for x in W:
        for r in x["rows"]:
            h = hmap.get((x["k"], r["c"])) or {}
            bits = [f'{_md(r.get("ent") or h.get("ent"))} 買']
            if h.get("r") is not None:                   # advice.picks 的 now_r 是百分比
                bits.append(_pc(h["r"] / 100))
            if h.get("out"):
                bits.append(f'{_md(h["out"])} 收盤賣')
            rows.append(f'<tr><td>{_e(r.get("n") or r["c"])} <span class="cd">{_e(r["c"])}</span></td><td class="w">{_wp(r["w"])}</td>'
                        f'<td class="src">{_e(x["name"])}</td><td class="st">{"・".join(bits)}</td></tr>')
        if x["idle"] > 1e-9:
            e = nxt.get(x["k"])
            if x["rows"]:
                why = "名單還沒補滿"
            else:
                why = "這一期沒有部位"
            if e:
                if e.get("act") == "買進" and not e.get("pending"):
                    why += f'・{_md(e["d"])} {e.get("at") or ""}買 {e.get("n_items") or len(e.get("items") or [])} 檔'
                elif e.get("act") == "買進":
                    why += f'・名單 {_md(e.get("fix"))} 收盤產生'
                elif e.get("act") == "調整":
                    why += f'・{_md(e["d"])} 調整'
            rows.append(f'<tr><td class="idx">0050</td><td class="w">{_wp(x["idle"])}</td><td class="src">{_e(x["name"])}</td>'
                        f'<td class="st">{_e(why)}</td></tr>')
    return ('<h2 class="cfh">持股細節<span class="sub">比重＝占全部資金・合計 100%</span></h2>'
            f'<table class="cfht"><tr><th>標的</th><th>比重</th><th>來源</th><th>現況</th></tr>{"".join(rows)}</table>')


def tw_parts(data: dict, bundle: dict) -> dict:
    N = (bundle.get("now") or {}).get("tw")
    stk = bundle.get("stk") or {}
    A = data.get("adv") or {}
    d0 = (N or {}).get("d") or A.get("last")
    W = CPG.sat_weights(stk)
    parts = [(SHORT.get(x["k"], x["name"]), x["share"]) for x in W]
    nxt, nx = _tw_next(data, bundle, N, d0)
    card = (f'<h2 class="cfh">時程與水位<span class="sub">台股・{_e(_md(d0))} 收盤後更新</span></h2>'
            + _tw_tiles(N, stk) + _stack("tw", N, parts)
            + (warn_row("tw", N) if N else "") + f'<div class="cfrule">{rule_line("tw")}</div>' + (due_line("tw", N) if N else "")
            + perf_line("tw", bundle) + detail_html("tw", bundle) + nxt + tl_shell("tw"))
    use = [s["k"] for s in stk.get("st") or []]
    obs = [c["k"] for c in (A.get("opp") or {}).get("cards") or [] if c.get("k") not in use]
    return {"card": card, "hold": tw_hold(stk, N), "d": d0, "nx": nx,
            "tl": {"use": use, "obs": obs, "mm": "tw"}}


# ── 美股 ─────────────────────────────────────────────────────────────────────

def _qm_lane(bundle: dict) -> dict | None:
    """美股強勢品質股在時間軸上的一列：持有中（最早買進那天起，到跌破 50 日線才賣）＋下一次買進（有空位）。"""
    qm = bundle.get("qm")
    n, W, nms = CPG._qm_now(qm), CPG._qm_watch(qm), CPG._qm_names(qm)
    if not n:
        return None
    hold = n.get("hold") or []
    sold = {x["c"]: x for x in W.get("sell") or []} | {c: {"on": n.get("next")} for c in n.get("sell") or []}
    lane = {"k": "qm", "name": CPG.QM_NAME, "hold": "到跌破 50 日線", "held": [], "buy": [], "next": None, "adj": []}
    if hold:
        ent = min(h["ent"] for h in hold)
        lane["held"].append({"ent": ent, "d": None, "act": "賣出", "at": "開盤",
                             "items": [{"c": h["c"], "n": h["c"], "nm": CPG.us_name(h["c"], nms), "entry": h.get("epx"), "now": h.get("px"),
                                        "now_r": None if h.get("r") is None else round(h["r"] * 100, 2), "ent": h["ent"]} for h in hold]})
    for c, x in sold.items():
        if x.get("on"):
            lane["adj"].append({"d": x["on"], "at": "開盤", "act": "賣出", "note": f"賣掉 {CPG.us_name(c, nms)}（收盤跌破 50 日線）"})
    if n.get("buy") and n.get("next"):
        lane["buy"].append({"d": n["next"], "at": "開盤", "act": "買進", "items": [{"c": c, "n": c, "nm": CPG.us_name(c, nms)} for c in n["buy"]],
                            "out": None, "sell": "收盤跌破 50 日線就在下一個交易日開盤賣", "tent": False})
    else:
        free = max(0, 8 - len([h for h in hold if h["c"] not in sold]))
        nf = CPG._qm_next_week_end(W.get("d") or n.get("d"))
        if free and nf:
            from . import ussxqm as QM
            lane["next"] = {"d": QM.next_day(nf), "fix": nf}
    return lane


def _us_next(data: dict, bundle: dict, N: dict | None) -> tuple[str, str | None]:
    qm = bundle.get("qm")
    n, W, nms = CPG._qm_now(qm), CPG._qm_watch(qm), CPG._qm_names(qm)
    un = lambda cs: _e("、".join(CPG.us_name(c, nms) for c in cs))        # noqa: E731
    d0 = (W.get("d") or n.get("d")) if n else (N or {}).get("d")
    nx = CPG._next_day("spx", d0) if d0 else None
    if not nx:
        return "", None
    rows_use, rows_obs = [], []
    if N and N.get("due"):
        rows_use.append(f'<div class="cfnr">{_pill("收盤", "賣出" if N["next"] < 0.99 else "買進")}'
                        f'<b>機動 30% {"換成現金" if N["next"] < 0.99 else "買回來"}</b></div>')
    if n:
        sells = [x["c"] for x in W.get("sell") or [] if x.get("on") == nx] + ([c for c in n.get("sell") or []] if n.get("next") == nx else [])
        if sells:
            rows_use.append(f'<div class="cfnr">{_pill("開盤", "賣出")}<b>{CPG.QM_NAME}</b><span class="cfni">{un(sells)}：收盤跌破 50 日線</span></div>')
        if n.get("buy") and n.get("next") == nx:
            rows_use.append(f'<div class="cfnr">{_pill("開盤", "買進")}<b>{CPG.QM_NAME}</b><span class="cfni">{un(n["buy"])}</span></div>')
    later = None
    if n and n.get("buy") and (n.get("next") or "") > nx:
        later = {"d": n["next"], "at": "開盤", "k": "qm", "what": "買 " + un(n["buy"])}
    elif n and not n.get("buy"):
        later = _qm_fill(bundle)
    sold_later = sorted(x["on"] for x in W.get("sell") or [] if (x.get("on") or "") > nx) if n else []
    if sold_later and (not later or sold_later[0] < later["d"]):
        later = {"d": sold_later[0], "at": "開盤", "k": "qm", "what": "賣掉收盤跌破 50 日線的股票"}
    MM = ((data.get("mac") or {}).get("m") or {}).get("spx") or {}
    for e in MM.get("cal") or []:
        if e.get("d") == nx:
            rows_obs.append(f'<div class="cfnr">{_pill("收盤", e.get("act") or "")}<b>{_e(e.get("name"))}（S&amp;P 500）</b>'
                            '<span class="cfob">指數型・觀察中，不在配置裡</span></div>')
    if not rows_use:
        rows_use.append(_none_row(later))
    return (f'<div class="cfnext"><div class="cfnd"><b>{_e(_mdw(nx))}</b><span>要做的事</span></div>'
            f'<div class="cfna">{"".join(rows_use + rows_obs)}</div></div>'), nx


def _qm_fill(bundle: dict) -> dict | None:
    """美股強勢品質股下一次補空位：這一週的名單（週五收盤定案）之後第一個交易日開盤。沒有空位回 None。"""
    qm = bundle.get("qm")
    n, W, nms = CPG._qm_now(qm), CPG._qm_watch(qm), CPG._qm_names(qm)
    if not n:
        return None
    sold = {x["c"] for x in W.get("sell") or []} | set(n.get("sell") or [])
    have = {h["c"] for h in n.get("hold") or [] if h["c"] not in sold}
    free = max(0, 8 - len(have) - len(n.get("buy") or []))
    nf = CPG._qm_next_week_end(W.get("d") or n.get("d"))
    if not free or not nf:
        return None
    from . import ussxqm as QM
    cand = [x["c"] for x in n.get("list") or [] if x["c"] not in have][:1]
    what = _e(f'補 {free} 檔（名單 {_md(nf)} 收盤定案' + (f'，目前 {CPG.us_name(cand[0], nms)} 領先' if cand else "") + "）")
    return {"d": QM.next_day(nf), "at": "開盤", "act": "買進", "k": "qm", "name": CPG.QM_NAME, "what": what,
            "free": free, "fix": nf}


def _us_tiles(N: dict | None, bundle: dict) -> str:
    qm = bundle.get("qm")
    n = CPG._qm_now(qm) if CPG.qm_on("spx", qm) else {}
    hold = n.get("hold") or []
    if not n:
        t1 = ("—", "機動 30% 放 S&amp;P 500")
    elif n.get("buy"):
        t1 = (f'{len(n["buy"])} 檔', f'{_e(_mdw(n.get("next")))} 開盤・強勢品質股')
    else:
        f = _qm_fill(bundle)
        t1 = ((f'{f["free"]} 檔', f'{_e(_mdw(f["d"]))} 開盤・名單 {_e(_md(f["fix"]))} 收盤定案') if f else ("0 檔", "沒有空位"))
    rs = [h["r"] for h in hold if h.get("r") is not None]
    t2 = (f"{len(hold)} 檔", f'強勢品質股・平均 {_pc(sum(rs) / len(rs))}' if rs else "沒有持股" if n else "S&amp;P 500")
    if N:
        t3 = (f'{round(N["next"] * 100)}%', f'現金 {round((1 - N["next"]) * 100)}%')
        t4 = (f'{N["n"]}／{len(N["fams"])}', "・".join(_e(_fam_name("spx", f["k"]) if f["k"] != "flat" else "總經策略全部空手") for f in N["fams"]))
    else:
        t3 = t4 = ("—", "今天的讀數還沒算出來")
    return _tiles([("待買進",) + t1, ("持有中",) + t2, ("股票水位",) + t3, ("警訊",) + t4])


def _qm_cands(n: dict, W: dict, nms: dict) -> str:
    """名單前幾名（手上沒有的）：有空位時就照這個順序買（每週五收盤定案）。數量＝fund_intro.US_QM_SHOW（缺口檢查涵蓋同一批）。"""
    sold = {x["c"] for x in W.get("sell") or []} | set(n.get("sell") or [])
    have = {h["c"] for h in n.get("hold") or [] if h["c"] not in sold} | set(n.get("buy") or [])
    L = [x for x in n.get("list") or [] if x["c"] not in have][:FI.US_QM_SHOW]
    if not L:
        return ""
    nf = CPG._qm_next_week_end(W.get("d") or n.get("d"))
    sub = (f'{_md(n.get("wk"))} 收盤・名單共 {n.get("n_list", 0)} 檔'
           + (f'・{_md(nf)} 收盤定案' if nf and not n.get("wk_done") else ""))
    rows = "".join(f'<tr><td>{_usn(x["c"], nms)}</td><td class="w">{x["rs"]:.0f}</td></tr>' for x in L)
    return (f'<h3 class="cfh3">有空位時依序買：名單前 {len(L)} 名（手上沒有的）<span class="sub">{sub}</span></h3>'
            '<table class="cfht cfql"><tr><th>標的</th><th title="漲幅勝過多少比例的美股（1～99）">強度</th></tr>'
            f'{rows}</table>')


def us_hold(bundle: dict, N: dict | None) -> str:
    qm = bundle.get("qm")
    n, W, nms = CPG._qm_now(qm), CPG._qm_watch(qm), CPG._qm_names(qm)
    cash = bool(N) and N["next"] < 0.99
    on = CPG.qm_on("spx", qm)
    rows = ['<tr class="g"><td colspan="4">長抱 70%</td></tr>',
            '<tr><td class="idx">SPY／VOO</td><td class="w">70%</td><td class="src">一直抱著</td><td class="st">—</td></tr>']
    if not on or not n:
        rows.append('<tr class="g"><td colspan="4">機動 30%</td></tr>'
                    '<tr><td class="idx">SPY／VOO</td><td class="w">30%</td><td class="src">指數</td><td class="st">美股三成照舊放指數</td></tr>')
    else:
        hd = "機動 30%：放現金中；買回時照下面這樣買" if cash else "機動 30%：強勢品質股最多 8 檔，空位放 S&amp;P 500"
        rows.append(f'<tr class="g"><td colspan="4">{hd}</td></tr>')
        wl = {w["c"]: w for w in W.get("hold") or []}
        sold = {x["c"]: x for x in W.get("sell") or []}
        for h in n.get("hold") or []:
            bits = [f'{_md(h["ent"])} 買', _pc(h.get("r"))]
            pct = CPG._qm_pct_ma(h, wl.get(h["c"]) or {})
            if h["c"] in sold:
                bits.append(f'{_md(sold[h["c"]]["on"])} 開盤賣（跌破 50 日線）')
            elif h.get("sell"):
                bits.append(f'{_md(n.get("next"))} 開盤賣（跌破 50 日線）')
            elif pct is not None:
                bits.append(f'比 50 日線{"高" if pct >= 0 else "低"} {abs(pct) * 100:.1f}%')
            rows.append(f'<tr><td>{_usn(h["c"], nms)}</td><td class="w">{_wp((h.get("w") or 0) * S.SAT)}</td>'
                        f'<td class="src">強勢品質股</td><td class="st">{"・".join(bits)}</td></tr>')
        for c in n.get("buy") or []:
            rows.append(f'<tr><td>{_usn(c, nms)}</td><td class="w">約 {CPG._qm_per()}</td><td class="src">強勢品質股</td>'
                        f'<td class="st">{_e(_md(n.get("next")))} 開盤買</td></tr>')
        idle = max(0.0, (n.get("idle") or 0.0) - len(n.get("buy") or []) / 8)
        if idle > 1e-3:
            nf = CPG._qm_next_week_end(W.get("d") or n.get("d"))
            rows.append(f'<tr><td class="idx">SPY</td><td class="w">{_wp(idle * S.SAT)}</td><td class="src">強勢品質股</td>'
                        f'<td class="st">空位 {round(idle * 8)}' + (f'・名單 {_e(_md(nf))} 收盤定案' if nf else "") + '</td></tr>')
    return ('<h2 class="cfh">持股細節<span class="sub">比重＝占全部資金・合計 100%</span></h2>'
            f'<table class="cfht"><tr><th>標的</th><th>比重</th><th>來源</th><th>現況</th></tr>{"".join(rows)}</table>'
            + (_qm_cands(n, W, nms) if on and n else ""))


def us_parts(data: dict, bundle: dict) -> dict:
    N = (bundle.get("now") or {}).get("spx")
    qm = bundle.get("qm")
    n = CPG._qm_now(qm)
    d0 = n.get("d") or (N or {}).get("d")
    on = CPG.qm_on("spx", qm)
    parts = [(f'強勢品質股（{len(n.get("hold") or [])} 檔）', S.SAT)] if on and n else [("S&P 500", S.SAT)]
    nxt, nx = _us_next(data, bundle, N)
    card = (f'<h2 class="cfh">時程與水位<span class="sub">美股・{_e(_md(d0))} 收盤後更新</span></h2>'
            + _us_tiles(N, bundle) + _stack("us", N, parts)
            + (warn_row("spx", N) if N else "") + f'<div class="cfrule">{rule_line("us")}</div>' + (due_line("us", N) if N else "")
            + perf_line("us", bundle) + detail_html("us", bundle) + nxt + tl_shell("us"))
    return {"card": card, "hold": us_hold(bundle, N), "d": d0, "nx": nx,
            "tl": {"qm": _qm_lane(bundle) if on else None, "mm": "spx"}}


# ── 時間軸（stockviz.tlDraw；設定在 JS 的 cfQ） ──────────────────────────────────

def tl_shell(mk: str) -> str:
    return (f'<div class="tlx cftl"><div class="tlhd"><div class="seg tlrg"><a data-tlr=all class=on>全部</a><a data-tlr=m1>接下來 5 週</a></div>'
            '<span class=tllg><span><span class="tlk b">▲</span>買進</span><span><span class="tlk s">▼</span>賣出</span>'
            '<span><span class="tlk w">◆</span>換股</span><span><span class="tlk a">●</span>調整</span>'
            '<span class=tlsw><i class=tlsh></i>持有中（顏色＝目前漲跌）</span><span class=tlsw><i class=tlsb></i>排定的買進</span></span>'
            f'<div class="seg cfobs"><a data-cfo=0 class=on>使用中</a><a data-cfo=1>＋觀察中</a></div></div>'
            f'<div class=tlbox id="cftl-{mk}"></div><div class=vztip id="cftip-{mk}" hidden></div></div>')


# ── 策略頁 ─────────────────────────────────────────────────────────────────────

def _go_attrs(g: dict) -> str:
    if not g or not g.get("go"):
        return ""
    s = f' data-go="{_e(g["go"])}"'
    if g.get("at"):
        s += f' data-at="{_e(g["at"])}"'
    if g.get("gm"):
        s += f' data-gm="{_e(g["gm"])}"'
    return s


def board_html(B: dict) -> str:
    rows = B["rows"]
    n = B["n"]
    chips = "".join(f'<a data-bst="{s}"{" class=on" if s != "out" else ""}>{BD.ST_NAMES[s]} {n[s]}</a>' for s in BD.STATUS)
    mks = '<a data-bmk="all" class="on">全部</a><a data-bmk="tw">台股</a><a data-bmk="us">美股</a>'
    body = []
    for s in BD.STATUS:
        rs = [r for r in rows if r["st"] == s]
        body.append(f'<tr class="g" data-st="{s}"><td colspan="6"><span class="bpill b{s}">{BD.ST_NAMES[s]}</span>{_e(BD.ST_NOTE[s])}</td></tr>')
        if not rs:
            body.append(f'<tr class="bnone" data-st="{s}"><td colspan="6">{"目前沒有；第一批在每週日新找之後出現" if s == "cand" else "目前沒有"}</td></tr>')
            continue
        for r in rs:
            nm = f'<a{_go_attrs(r.get("go"))}>{_e(r["name"])}</a>' if (r.get("go") or {}).get("go") else _e(r["name"])
            if s == "out":
                body.append(f'<tr class="br" data-st="{s}" data-mk="{_e(r.get("mkk"))}"><td class="bn">{nm}</td><td class="bm">{_e(r["mk"])}</td>'
                            f'<td class="bw" colspan="4">{_e(r.get("why") or "")}</td></tr>')
                continue
            perf = _e(r.get("perf") or "—") + (f'<span class="bref">（{_e(r["ref"])}）</span>' if r.get("ref") else "") + \
                (f'<span class="bsub">{_e(r["sub"])}</span>' if r.get("sub") else "")
            mdd = _e(r.get("mdd") or "—") + (f'<span class="bref">（{_e(r["mddr"])}）</span>' if r.get("mddr") else "")
            body.append(f'<tr class="br" data-st="{s}" data-mk="{_e(r.get("mkk"))}"><td class="bn">{nm}<span class="bt">{_e(r["type"])}</span></td>'
                        f'<td class="bm">{_e(r["mk"])}</td><td class="bh">{_e(r.get("how") or "")}</td><td class="bp">{perf}</td>'
                        f'<td class="bd">{mdd}</td><td class="bto">{_e(r.get("today") or "")}</td></tr>')
        if s == "obs":
            body.append('<tr class="bx" data-st="obs"><td colspan="6"><a data-bx="obs">再看更多觀察中</a></td></tr>')
    return ('<h2 class="cfh">策略<span class="sub">全部 {} 條：進配置的、看著的、新找的、試過沒有用的</span></h2>'.format(len(rows))
            + f'<div class="bfilt"><div class="seg bsts">{chips}</div><div class="seg bmks">{mks}</div></div>'
            + f'<div class="bwrap"><table class="btbl" data-n="{BD.OBS_SHOW}"><thead><tr><th>策略</th><th>市場</th><th class="bh">做什麼</th><th class="bp">成績</th>'
            + '<th class="bd">最慘跌</th><th class="bto">今天</th></tr></thead><tbody>' + "".join(body) + "</tbody></table></div>")


def line_html(mk: str, B: dict) -> str:
    c = (B.get("nm") or {}).get(mk) or {}
    nm = "台股" if mk == "tw" else "美股"
    return (f'<div class="cfline"><b>{nm}的策略</b>' + "".join(f'<span>{BD.ST_NAMES[s]} <b>{c.get(s, 0)}</b></span>' for s in BD.STATUS)
            + f'<a data-go="strat" data-bmk="{mk}">看全部策略</a></div>')


# ── 組起來 ─────────────────────────────────────────────────────────────────────

def build(data: dict, bundle: dict | None) -> dict:
    """→ D.cfg：{"tw": {card, hold, line, d, nx, tl}, "us": {…}, "board": {html, n, nm}, "now": {市場: 警訊的讀數}, "use": [策略]}。
    每一塊各自 try：算不出來只少那一塊（頁面寫「還沒算出來」）。"""
    B = bundle or {}
    out: dict = {"now": {k: v for k, v in (B.get("now") or {}).items() if v},
                 "use": [s["k"] for s in (B.get("stk") or {}).get("st") or []]}    # 台股三成使用中的策略（個股表、個股卡只標這些）
    try:
        bd = BD.build(data, B)
        out["board"] = {"html": board_html(bd), "n": bd["n"], "nm": bd["nm"]}
    except Exception as e:                               # noqa: BLE001
        print(f"[配置] 策略總覽算不出來：{type(e).__name__}: {e}")
        bd = {"nm": {}}
    for mk, fn in (("tw", tw_parts), ("us", us_parts)):
        try:
            x = fn(data, B)
            x["line"] = line_html(mk, bd)
            out[mk] = x
        except Exception as e:                           # noqa: BLE001
            print(f"[配置] {mk} 算不出來：{type(e).__name__}: {e}")
            out[mk] = {"err": f"{type(e).__name__}: {e}"}
    return out


CSS = r"""
/* 配置頁（cfgpage.py；docs/lab_ia_v5_plan.md 第 18 節） */
.cfsec{margin-top:4px}
.cfh{font-size:18px;margin:4px 0 10px;display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 10px}
.cfh .sub{font-size:12.5px;font-weight:400;color:var(--mut)}
.cftiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:0 0 10px}
.cftile{background:var(--card2);border-radius:12px;padding:10px 12px;min-width:0}
.cfl{font-size:12.5px;color:var(--mut)}.cfv{font-size:22px;font-weight:800;line-height:1.3}.cfs{font-size:12.5px;color:var(--ink2)}
.cfstack{display:flex;height:28px;border-radius:8px;overflow:hidden;font-size:12.5px;font-weight:700;color:#fff;margin:2px 0 4px}
.cfstack>div{display:flex;align-items:center;padding:0 9px;white-space:nowrap;overflow:hidden;min-width:0}
.cfsc{flex:70;background:#56698a}.cfss.cfs0{background:#a16207}.cfss.cfs1{background:#c48a2a;color:#2b1d00}.cfss.cfs2{background:#d9b25c;color:#2b1d00}
.cfsx{color:var(--warn);background:repeating-linear-gradient(45deg,rgba(180,83,9,.14),rgba(180,83,9,.14) 6px,transparent 6px,transparent 11px);border:1px dashed var(--warn);border-radius:0 8px 8px 0}
.cfstlg{display:none;font-size:12.5px;color:var(--ink2);margin:0 0 6px}
.cfwarn{display:flex;flex-wrap:wrap;align-items:center;gap:6px 16px;font-size:13px;margin:6px 0 2px}
.cfwl b.ok{color:var(--loss)}.cfwl b.on{color:var(--warn)}
.cfwi{display:inline-flex;align-items:center;gap:6px;white-space:nowrap}.cfwi.on{color:var(--warn);font-weight:700}
.cfwb{position:relative;display:inline-block;width:64px;height:8px;border-radius:4px;background:var(--line)}
.cfwb>i{position:absolute;left:0;top:0;bottom:0;border-radius:4px;background:var(--bar2)}.cfwi.on .cfwb>i{background:var(--warn)}
.cfwb>u{position:absolute;top:-3px;bottom:-3px;width:2px;background:var(--ink2);margin-left:-1px}
.cfrule{font-size:12.5px;color:var(--mut);margin:2px 0 4px}
.cfdue{font-size:13.5px;margin:6px 0;padding:7px 10px;border-radius:8px;background:var(--gbbg)}.cfdue b{color:var(--warn)}.cfdue.ok b{color:var(--acc)}
.cfperf{font-size:13px;color:var(--ink2);margin:4px 0}.cfperf b{color:var(--ink)}.cfq{font-size:12.5px;color:var(--mut)}
.cfdet{margin:6px 0 10px}.cfdet>summary{cursor:pointer;font-size:13px;color:var(--acc);width:max-content}
.pln.cfpln{border:0;border-radius:0;padding:0;background:none;margin:8px 0 0}   /* 細節＝corepage 的圖表與表格（樣式 corepage.CSS，配置頁一起載入）；外框用時程與水位卡自己的 */
.cfnext{display:grid;grid-template-columns:auto minmax(0,1fr);gap:4px 18px;align-items:start;background:var(--card2);border-radius:12px;padding:10px 14px;margin:8px 0 12px}
.cfnd b{display:block;font-size:20px;line-height:1.25}.cfnd span{font-size:12px;color:var(--mut)}
.cfna{display:flex;flex-direction:column;gap:5px;min-width:0}
.cfnr{display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 8px;font-size:13.5px;line-height:1.6}.cfnr .kact{flex:none}.cfnr.cfnone{display:block}
.cfni{color:var(--ink2)}.cfob{font-size:12px;color:var(--mut)}.cfnone{color:var(--ink2)}
.cfobs a{cursor:pointer}
.cfht{width:100%;border-collapse:collapse;font-size:13.5px}
.cfht th{text-align:left;font-weight:600;color:var(--ink2);font-size:12.5px;padding:5px 8px;border-bottom:1px solid var(--line2)}
.cfht td{padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left;white-space:normal}
.cfht td:first-child{position:static;background:none}.cfht th:first-child{position:static}
.cfht th:nth-child(2){text-align:right}
.cfht tr.g td{background:var(--card2);color:var(--ink2);font-size:12.5px;padding:5px 8px}
.cfht td.w{text-align:right;font-weight:700;white-space:nowrap;font-variant-numeric:tabular-nums}
.cfht td.src{color:var(--ink2);white-space:nowrap}.cfht td.st{color:var(--ink2);font-size:12.5px}.cfht td.idx{font-weight:700;color:var(--accd)}
.cfht .cd{color:var(--mut);font-size:12px}.cfht .cfin{font-size:12px;color:var(--mut);line-height:1.45;margin-top:1px}
.cfh3{font-size:14.5px;margin:16px 0 6px;display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 10px}.cfh3 .sub{font-size:12.5px;font-weight:400;color:var(--mut)}
.cfsxl{font-size:13.5px;color:var(--ink2);margin:0 0 4px}.cfsxl a{color:var(--acc);cursor:pointer}.cfsxn{font-size:13px;color:var(--mut);margin:2px 0 8px}
.cfline{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 16px;font-size:13.5px;border:1px solid var(--line);border-radius:12px;padding:10px 14px;margin:14px 0}
.cfline a{color:var(--acc);cursor:pointer}
.cffoot{margin:22px 0 8px;text-align:center;font-size:12.5px;color:var(--mut)}.cffoot a{color:var(--mut)}
.bfilt{display:flex;flex-wrap:wrap;gap:8px 14px;margin:0 0 8px}.bfilt .seg a{cursor:pointer}
.bwrap{overflow-x:auto}
.btbl{width:100%;border-collapse:collapse;font-size:13px}
.btbl th{text-align:left;font-weight:600;color:var(--ink2);font-size:12.5px;padding:6px 8px;border-bottom:1px solid var(--line2);white-space:nowrap}
.btbl td{padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left;white-space:normal}
.btbl td:first-child{min-width:10em}.btbl th.bp,.btbl th.bd,.btbl td.bp,.btbl td.bd{text-align:right}
.btbl td.bto{min-width:7.5em}
.btbl tr.g td{background:var(--card2);font-weight:600;font-size:13px}.btbl tr.g .bpill{margin-right:8px}
.bpill{display:inline-block;font-size:11.5px;font-weight:700;padding:1px 8px;border-radius:999px}
.bpill.buse{background:var(--lossbg);color:var(--loss)}.bpill.bobs{background:var(--inset);color:var(--ink2)}
.bpill.bcand{background:var(--gbbg);color:var(--warn)}.bpill.bout{background:var(--line);color:var(--mut)}
.btbl td.bn a{color:var(--ink);font-weight:600;cursor:pointer}.btbl td.bn a:hover{color:var(--acc)}
.btbl .bt{display:block;font-size:11.5px;color:var(--mut);font-weight:400}
.btbl td.bm{white-space:nowrap;color:var(--ink2)}.btbl td.bh{color:var(--ink2);min-width:220px}
.btbl td.bp,.btbl td.bd{white-space:nowrap;font-variant-numeric:tabular-nums}
.btbl .bref{color:var(--mut);font-size:12px}.btbl .bsub{display:block;font-size:11.5px;color:var(--mut)}
.btbl td.bto{color:var(--ink2);font-size:12.5px}.btbl td.bw{color:var(--ink2);font-size:12.5px}
.btbl tr.bnone td{color:var(--mut);font-size:12.5px}
.btbl tr.bx td a{color:var(--acc);cursor:pointer;font-size:12.5px}
.btbl tr.bhide{display:none}
.cftoolr{display:flex;flex-wrap:wrap;align-items:center;gap:6px 14px;margin:0 0 12px}.cftool{display:flex;width:max-content;max-width:100%}.cfasof{color:var(--mut);font-size:12.5px;min-width:0}
@media (max-width:640px){.cftiles{grid-template-columns:1fr 1fr}.cfv{font-size:19px}
 .cfstack .cfss,.cfstack .cfsx{font-size:0}.cfstlg{display:block}
 .cfnext{grid-template-columns:1fr;gap:6px}.cfnd b{display:inline;font-size:17px;margin-right:6px}
 .cfht,.cfht tbody{display:block}.cfht tr{display:grid;grid-template-columns:minmax(0,1fr) auto;padding:5px 0;border-bottom:1px solid var(--line)}
 .cfht th{display:none}.cfht td{border:0;padding:0 6px}.cfht td.src,.cfht td.st{grid-column:1/-1;font-size:12.5px}
 .cfht tr.g{background:var(--card2)}.cfht tr.g td{grid-column:1/-1}
 .btbl{font-size:12.5px}.btbl th.bh,.btbl td.bh,.btbl th.bd,.btbl td.bd,.btbl .bsub{display:none}
 .btbl td,.btbl th{padding:6px 5px}.btbl td:first-child{min-width:0;width:34%}.btbl td.bm{white-space:nowrap}
 .btbl .bref{display:block}.btbl td.bto{min-width:0}}
"""

JS = r"""
/* ---------- 配置（cfgpage.py；docs/lab_ia_v5_plan.md 第 18 節）：台股｜美股｜策略｜個股（工具）。
   台股、美股：時程與水位（Python 組好的 HTML）＋時間軸（stockviz.tlDraw，設定 cfQ）＋持股細節；策略：全部策略一張表。 ---------- */
const CFG=D.cfg||{};
function cfFoot(){return `<footer class=cffoot><a href="x9r.html">研究紀錄</a></footer>`;}
function cfMk(mk){const C=CFG[mk]||{};let h='';
  if(C.err||!C.card)h+=`<div class=st>配置資料還沒算出來${C.err?`：${esc(C.err)}`:''}。</div>`;
  else h+=`<section class="sec cfsec" id="cf-${mk}" data-nav="時程與水位">${C.card}</section>`+(C.hold?`<section class=sec id="cf-${mk}-h" data-nav="持股細節">${C.hold}</section>`:'')+(mk==='tw'?cfSx():'')+(C.line||'');
  $('#main').innerHTML=h+cfFoot();
  $$('#main [data-cfo]').forEach(a=>{a.classList.toggle('on',(+a.dataset.cfo===1)===!!VZS['cfo_'+mk]);
    a.onclick=e=>{e.preventDefault();VZS['cfo_'+mk]=a.dataset.cfo==='1';$$('#main [data-cfo]').forEach(b=>b.classList.toggle('on',b===a));cfDraw(mk);};});
  const w=$('#main .cftl');if(w)w.addEventListener('click',ev=>{const a=ev.target.closest&&ev.target.closest('.vztip [data-go]');if(!a)return;
    ev.preventDefault();const tp=a.closest('.vztip');tp.classList.remove('pin');tp.hidden=true;if(a.dataset.gm)S.mmk=a.dataset.gm;go(a.dataset.go,a.dataset.at);});
  cfDraw(mk);}
/* 台股：飆股名單（2026-10-24 使用者：「飆股的選股名單要放進去啊」）。觀察中、沒有放錢；到買點、快到買點兩張表（copage 的 wlPick／wlTable，
   研究紀錄的飆股段同一份分組），其他強勢與其餘在研究紀錄。 */
function cfSx(){const W=D.wl||{},C=W.cand||[];if(!W.v||!C.length)return '';const P=wlPick(),ST=(W.lay||{}).stocks||{},T=W.tags||{},rest=C.length-P.A.length-P.B.length;
  let h=`<h2 class=cfh>飆股名單<span class=sub>${W.d?md(W.d)+' 收盤・':''}觀察中，沒有放錢</span></h2>`+
    `<div class=cfsxl>名單 ${C.length} 檔：<b>到買點 ${P.A.length} 檔</b>、<b>快到買點 ${P.B.length} 檔</b>`+
    (rest?`，其他 ${rest} 檔收在下面`:'')+`；過去成績在<a data-go="opp" data-at="o-sx">研究紀錄</a>。點股票名稱看公司。</div>`;
  h+=`<h3 class=cfh3>到買點（${P.A.length} 檔）</h3>`+(P.A.length?wlTable(P.A,ST,T,'cfwla','買點～追價上限',1):`<div class=cfsxn>今天沒有股票在買點。</div>`);
  h+=`<h3 class=cfh3>快到買點（${P.B.length} 檔）<span class=sub>股價強、離 52 週高點 ${f(P.NEAR*100,0)}% 內</span></h3>`+(P.B.length?wlTable(P.B,ST,T,'cfwlc','突破哪裡才算',1):`<div class=cfsxn>今天沒有。</div>`);
  if(P.B2.length)h+=`<details class=mr><summary>其他強勢 ${P.B2.length} 檔（離高點較遠或已漲太遠）</summary>${wlTable(P.B2,ST,T,'','等什麼',1)}</details>`;
  if(P.Rr.length)h+=`<details class=mr><summary>其他 ${P.Rr.length} 檔（股價強度沒到前段）</summary>${wlTable(P.Rr,ST,T,'','等什麼',1)}</details>`;
  return `<section class=sec id="cf-tw-sx" data-nav="飆股名單">${h}</section>`;}
function vCfgTw(){cfMk('tw');}
function vCfgUs(){cfMk('us');}
/* 時間軸的列：使用中的策略；切到「＋觀察中」再加上有東西可畫的觀察中策略（個股策略 ●、指數型 ★／●） */
function cfLanes(mk){const C=CFG[mk]||{},T=C.tl||{},obs=!!VZS['cfo_'+mk],L=[];
  const has=c=>(c.held||[]).length||(c.buy||[]).length||c.next||(c.adj||[]).length;
  const oc=k=>(OPP.cards||[]).find(c=>c.k===k);
  (T.use||[]).forEach(k=>{const c=oc(k);if(c)L.push(Object.assign({},c,{_src:'stk',_st:'use'}));});
  if(T.qm)L.push(Object.assign({},T.qm,{_src:'qm',_st:'use'}));
  if(obs){(T.obs||[]).forEach(k=>{const c=oc(k);if(c&&has(c))L.push(Object.assign({},c,{_src:'stk',_st:'obs'}));});
    ((MCM[T.mm]||{}).cards||[]).forEach(c=>{const t=c.tl||{},x={k:c.k,name:c.name,gname:c.gname,tier:c.tier,held:t.held||[],buy:t.buy||[],next:t.next||null,adj:t.adj||[],_src:'mac',_st:'obs',_mm:T.mm};if(has(x))L.push(x);});}
  L.forEach((c,i)=>{c.rank=i+1;});return L;}
function cfMacLb(x){const e=x.e,M=MCM[x.c._mm]||{};if(x.k==='held')return `${e.ent&&M.d&&vzDay(M.d)-vzDay(e.ent)>120?xmYmd(e.ent)+' 起 ':''}${pctT(e.r)}`;
  return x.k==='buy'?`${md(e.d)} 買`+(e.out?`、${md(e.out)} 賣`:''):x.k==='next'?'可能買進':'';}
function cfTip(x,pin){const c=x.c,e=x.e;let h='';
  if(c._src==='mac'){const s=S.mmk;S.mmk=c._mm;h=xmTip(x,pin).replace(/<a class=vzgo data-to="m-[^"]*">[^<]*<\/a>/,'');S.mmk=s;
    return h+(pin?`<a class=vzgo data-go="macst" data-at="ms-${esc(c.k)}" data-gm="${esc(c._mm)}">規則與成績</a>`:'');}
  if(c._src==='qm'){if(x.k==='held')h=`<b>${esc(c.name)}・持有 ${(e.items||[]).length} 檔</b><ul>${(e.items||[]).map(i=>`<li>${esc(i.nm||i.n)} <span class=vzs>${md(i.ent)} 買</span> <span class=${(i.now_r||0)>=0?'up':'dn'}>${pctT(i.now_r)}</span></li>`).join('')}</ul><div class=vzs>收盤跌破 50 日線，下一個交易日開盤賣</div>`;
    else if(x.k==='buy')h=`<b>${mdw(e.d)} 開盤買進・${esc(c.name)}</b><div>${(e.items||[]).map(i=>esc(i.nm||i.n)).join('、')}</div>`;
    else if(x.k==='next')h=`<b>${esc(c.name)}</b><div>名單 ${mdw(e.fix)} 收盤定案，有空位就 ${mdw(e.d)} 開盤買</div>`;
    else h=`<b>${mdw(e.d)} 開盤・${esc(c.name)}</b><div class=vzs>${esc(e.note||'')}</div>`;
    return h;}
  h=tlTip(x,pin).replace(/<a class=vzgo data-to="o-[^"]*">[^<]*<\/a>/,'');
  return h+(pin?`<a class=vzgo data-go="st" data-at="st-${esc(c.k)}">規則與成績</a>`:'');}
function cfQ(mk){const C=CFG[mk]||{};
  return {box:'cftl-'+mk,tip:'cftip-'+mk,rk:'cft_'+mk,back:120,rtx:'依規則賣出',cards:()=>cfLanes(mk),
    last:()=>C.d||ADV.last||'2026-01-01',dl:()=>C.d,nx:()=>C.nx,
    lb:x=>x.c._src==='mac'?cfMacLb(x):TLO.lb(x),
    nm:c=>`${c.rank}. ${c._src==='mac'?xmNm(c.k)+'（指數）':(STN[c.k]||c.name)}`,
    sub:c=>`${c._st==='use'?'使用中':'觀察中'}・${c._src==='mac'?(c.gname||''):'持有'+hz(c.hold)}`,
    avg:e=>e.r!=null?e.r:tlAvg(e),tipf:(x,pin)=>cfTip(x,pin)};}
function cfDraw(mk){if($('#cftl-'+mk))tlDraw(cfQ(mk));}
let CFR=0,CFW=innerWidth;addEventListener('resize',()=>{clearTimeout(CFR);CFR=setTimeout(()=>{if(Math.abs(innerWidth-CFW)<30)return;CFW=innerWidth;if(S.tab==='tw'||S.tab==='us')cfDraw(S.tab);},220);});
/* 策略：全部策略一張表；狀態、市場篩選（淘汰預設收起） */
const CFB={st:new Set(['use','obs','cand']),mk:'all',open:false};
function vCfgSt(){const B=CFG.board||{};
  $('#main').innerHTML=(B.html?`<section class=sec id="cf-st" data-nav="策略">${B.html}</section>`:'<div class=st>策略總覽還沒算出來。</div>')+cfFoot();
  if(S.bmk){CFB.mk=S.bmk;S.bmk='';}
  $$('#main [data-bst]').forEach(a=>a.onclick=e=>{e.preventDefault();const s=a.dataset.bst;if(CFB.st.has(s))CFB.st.delete(s);else CFB.st.add(s);cfBApply();});
  $$('#main [data-bmk]').forEach(a=>a.onclick=e=>{e.preventDefault();CFB.mk=a.dataset.bmk;cfBApply();});
  $$('#main [data-bx]').forEach(a=>a.onclick=e=>{e.preventDefault();CFB.open=true;cfBApply();});
  cfBApply();}
/* 觀察中依目前的篩選先列 data-n 條，其餘收在「再 N 條觀察中」 */
function cfBApply(){const t=$('#main .btbl');if(!t)return;const N=+t.dataset.n||8;let shown=0,hid=0;
  $$('#main [data-bst]').forEach(a=>a.classList.toggle('on',CFB.st.has(a.dataset.bst)));
  $$('#main [data-bmk]').forEach(a=>a.classList.toggle('on',a.dataset.bmk===CFB.mk));
  $$('#main .btbl tbody tr').forEach(r=>{if(r.classList.contains('bx'))return;const s=r.dataset.st,m=r.dataset.mk;
    let on=CFB.st.has(s)&&(!m||CFB.mk==='all'||m===CFB.mk||m==='all');
    if(on&&s==='obs'&&r.classList.contains('br')){if(!CFB.open&&shown>=N){on=false;hid++;}else shown++;}
    r.classList.toggle('bhide',!on);});
  const x=$('#main .btbl tr.bx');if(x){x.classList.toggle('bhide',!hid);const a=x.querySelector('a');if(a)a.textContent=`再 ${hid} 條觀察中`;}}
/* 個股（工具）：個股｜籌碼｜指數 */
function toolSeg(t){return `<div class=cftoolr><div class="seg cftool" role=group aria-label="工具">${[['stk','個股'],['chip','籌碼'],['idx','指數']].map(([k,n])=>`<a data-go="${k}"${t===k?' class=on':''}>${n}</a>`).join('')}</div>`+
  (D.asl?`<span class=cfasof>${D.asl}</span>`:'')+`</div>`;}
"""
