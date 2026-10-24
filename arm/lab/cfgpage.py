"""配置頁（x9.html 的「配置」：台股｜美股｜策略｜個股（工具）；docs/lab_ia_v5_plan.md 第 18 節、docs/lab_cfg_v2_plan.md）。

配置頁 v2（2026-10-24 使用者：「我完全看不懂你的配置…你要我持有的股票我根本沒辦法點進去看…配置比例在手機版也跑版」）：
台股、美股各一頁、同樣五段——①現在的錢（股票、現金兩個數字＋實際的錢的長條＋現金為什麼有）②持股（依策略分組，每一檔整列可以點；
台股開個股卡／公司卡，美股先開 Yahoo Finance，美股個股卡做好再換）③接下來照規則的買賣（只列配置裡的策略）④警訊（現在多少、到多少才算）
⑤過去照做（＋細節）。台股另有新飆股名單；美股是一個計畫（corespec VER 4 長抱 0%、全部放美股強勢品質股，空位放現金），
那斯達克 100 的版本只在成績下面一行。策略頁＝全部策略一張表（board.py；使用中／觀察中／候選／淘汰）。

數字全部來自現有的研究檔與當天的計算（core、corepage、advice、xsadvice、ussxqm、sxlive），這裡只組版面，不算任何新數字。
警訊今天的讀數要景氣頁算（同一個程序裡較晚才建），所以 x9.html 建兩次：個股頁建頁時先用上一版的讀數
（x9or-{市場}.json），景氣頁建完後 page.finish() 用今天的讀數重建（gen_fund_dashboard.py）。
JS 由 page.render 插在頁面初始化之前（同 stockviz、macpage、copage）；函式一律 cf 開頭，不和其他三支撞名。
"""
from __future__ import annotations

import html
import re

from .. import fund_intro as FI
from . import board as BD
from . import corepage as CPG
from . import corespec as S
from . import ussxspec as QX

PLAN_MK = {"tw": "tw", "us": "spx"}             # 配置頁的市場 → 交易計畫的市場鍵
SHORT = {"s3": "臺灣50", "v3l": "財報驚喜", "s5": "長線", "s1": "共識加碼", "v7l": "月營收大型", "v3m": "財報中型",
         "v7m": "月營收中型", "hd": "高股息", "qm": "強勢品質股", "boom": "新飆股"}


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

def _fam_name(mk: str, k: str) -> str:
    return CPG.plain(mk, k)


def _sat_txt(mk: str) -> str:
    """配置頁的機動：「機動 80%」；長抱 0%＝「全部持股」。"""
    pm = PLAN_MK[mk]
    return "全部持股" if S.core_of(pm) <= 0 else f"機動 {CPG.pct0(S.sat_of(pm))}"


def _sat_sp(mk: str) -> str:
    """_sat_txt 後面接中文時用：「機動 80% 」（% 後面空一格）、「全部持股」。"""
    w = _sat_txt(mk)
    return w + " " if w.endswith("%") else w


def _act_txt(mk: str, cash: bool) -> str:
    """「機動 80% 換成現金」「全部持股換成現金」。"""
    return _sat_sp(mk) + ("換成現金" if cash else "買回來")


def rule_line(mk: str) -> str:
    pm = PLAN_MK[mk]
    need = S.REENTRY.get(pm, 1)
    what = _sat_sp(mk)
    if pm in S.FLAT:
        return f"兩個以上成立，或總經策略全部空手：隔天收盤把{what}換成現金，都解除了隔天收盤買回"
    return (f"兩個以上成立：隔天收盤把{what}換成現金" +
            ("，警訊少於兩個滿兩週才買回" if need > 1 else "，解除了隔天收盤買回"))


def due_line(mk: str, N: dict) -> str:
    """要調整水位的那一句（不用調整回空字串）。"""
    pm = PLAN_MK[mk]
    cash, need = N["next"] < 0.99, N.get("need") or 1
    day = CPG._next_day(pm, N["d"]) if N.get("due") else None
    lit = "、".join(_fam_name(pm, f["k"]) for f in N["fams"] if f["lit"])
    what = _sat_sp(mk)
    if day and cash:
        return f'<p class="cfdue"><b>{_e(_mdw(day))} 收盤：把{what}賣掉換成現金</b>（{_e(lit)}）</p>'
    if day:
        return f'<p class="cfdue ok"><b>{_e(_mdw(day))} 收盤：把{what}買回來</b></p>'
    if cash and N.get("ok") and need > 1:
        c = N.get("clear") or 0
        buy = CPG._next_day_n(pm, N["d"], need - c + 1)
        return f'<p class="cfdue">{what}放現金中；警訊少於兩個第 {c} 天，接下來都沒有警訊的話最快 {_e(_mdw(buy))} 收盤買回</p>'
    if cash:
        return f'<p class="cfdue">{what}放現金中；警訊解除後隔天收盤買回</p>'
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
    txt = (f'{CPG.yr0(s["a"])} 起 100 萬變 <b>{CPG._wan(p["m"])}</b>（{etf} 抱著 {CPG._wan(h["m"])}）・最慘跌 <b>{CPG._ab(p["mdd"])}</b>'
           f'（{CPG._ab(h["mdd"])}）・年化 {_pc((p.get("cagr") or 0), 1).lstrip("+")}（{_pc((h.get("cagr") or 0), 1).lstrip("+")}）')
    out = f'<div class="cfperf">{txt}</div>'
    b = (CPG._qm_plan("spx", bundle.get("qm")).get("base")) if mk == "us" and CPG.qm_on("spx", bundle.get("qm")) else None
    if b and S.core_of("spx") <= 0:                       # ussxspec VER 5：判定跟原本在用的計畫比
        out += (f'<div class="cfperf cfq">原本的計畫（七成長抱 S&amp;P 500＋三成強勢品質股）同一段：100 萬變 {CPG._wan(b["plan"]["m"])}'
                f'・最慘跌 {CPG._ab(b["plan"]["mdd"])}</div>')
    if mk == "us" and CPG.qm_on("ndx", bundle.get("qm")):
        q = (CPG._qm_plan("ndx", bundle.get("qm")).get("new")) or {}
        if q:
            what = "警訊改看那斯達克 100" if S.core_of("ndx") <= 0 else "長抱改成那斯達克 100（QQQ）"
            out += (f'<div class="cfperf cfq">{what}：同一套規則 100 萬變 <b>{CPG._wan(q["plan"]["m"])}</b>'
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


# ── 台股 ─────────────────────────────────────────────────────────────────────

def boom_html(stk: dict, bundle: dict) -> str:
    """新飆股那一本帳（配置頁台股；取代原本的飆股名單）：一行說明、最新一週的名單（前 20，名字可以點）、這一週的試算名單。
    持股在「持股」那一段，這裡不重複。"""
    B = stk.get("boom")
    if B is None:
        return ""
    slot = CPG._boom_slot(stk)
    bw = float(stk.get("bw") or CPG.core_boom())
    R = bundle.get("R") or {}
    bm = ((((R.get("mk") or {}).get("tw") or {}).get("sc") or {}).get("plan") or {}).get("boom") or {}
    hn = B.get("hold_n") or 60
    sub = f'{_md(B.get("d"))} 收盤・占全部資金 {CPG.pct0(bw)}'
    line = (f'每週五（休市就看那一週最後一個交易日）收盤，用之前幾年的資料找出來的條件挑股票，依強勢排；'
            f'下一個交易日開盤買，每檔約占全部資金 {_wp(slot)}，抱 {hn} 個交易日再賣。')
    if bm.get("cagr") is not None:
        line += (f' {CPG.yr0(bm["a"])} 年起照做每年賺 {_pc(bm["cagr"]).lstrip("+")}、最慘時跌 {bm["mdd"] * 100:.0f}%'
                 f'（2026/10/30 起每週記錄驗證中）。')
    h = f'<h2 class="cfh">新飆股名單<span class="sub">{_e(sub)}</span></h2><div class="cfsxl">{line}</div>'
    have = {x["c"] for x in B.get("hold") or []}
    buy = {x["c"]: x for x in B.get("buy") or []}
    if B.get("wk") and B.get("list"):
        rows = []
        for x in B["list"]:
            if x["c"] in have:
                tag = "已經有"
            elif x["c"] in buy:
                tag = f'{_md(B.get("next"))} 開盤買' if buy[x["c"]].get("fill") else "現金不夠"
            else:
                tag = ""
            rows.append(f'<tr><td><a {_ck(x["c"])}>{_e(x.get("n") or x["c"])}</a> <span class="cd">{_e(x["c"])}</span></td>'
                        f'<td class="w">{x["rs"]:.0f}</td><td class="st">{_e(tag)}</td></tr>')
        more = (B.get("n_list") or 0) - len(B["list"])
        h += (f'<h3 class="cfh3">{_e(_mdw(B["wk"]))} 收盤的名單（{B.get("n_list", 0)} 檔）'
              + (f'<span class="sub">前 {len(B["list"])} 名，其餘 {more} 檔現金也用不到</span>' if more > 0 else "") + '</h3>'
              '<table class="cfht cfql"><tr><th>標的</th><th title="漲幅勝過多少比例的股票（1～99）">強度</th><th>現況</th></tr>'
              + "".join(rows) + "</table>")
    else:
        h += '<div class="cfsxn">還沒有任何一週的名單。</div>'
    if B.get("trial"):
        tr = B["trial"]
        h += (f'<h3 class="cfh3">這一週到 {_e(_md(B.get("d")))} 收盤為止符合的（{len(tr)} 檔）'
              f'<span class="sub">試算；{_e(_mdw(B.get("next_wk")))} 收盤才定案</span></h3>'
              f'<div class="cfsxl">' + "、".join(f'<a {_ck(x["c"])}>{_e(x.get("n") or x["c"])}</a> <span class="cd">{_e(x["c"])}</span>' for x in tr[:12])
              + (f" 等 {len(tr)} 檔" if len(tr) > 12 else "") + "</div>")
    elif B.get("next_wk") and B.get("next_wk") != B.get("wk"):
        h += f'<div class="cfsxn">下一份名單：{_e(_mdw(B["next_wk"]))} 收盤。</div>'
    h += '<div class="cfsxl">頁面上原本的飆股名單（到買點、快到買點）放在<a data-go="opp" data-at="o-sx">研究紀錄</a>。</div>'
    return f'<section class=sec id="cf-tw-sx" data-nav="新飆股名單">{h}</section>'


def _boom_lane(stk: dict) -> dict | None:
    """新飆股在時間軸上的一列：持有中（依買進日分批，到期日收盤後下一個交易日開盤賣）＋明天要買的＋下一次看名單。"""
    B = stk.get("boom")
    if not B:
        return None
    lane = {"k": "boom", "name": "新飆股", "hold": f'{B.get("hold_n") or 60} 個交易日', "held": [], "buy": [], "next": None, "adj": []}
    by: dict = {}
    for h in B.get("hold") or []:
        by.setdefault(h["ent"], []).append(h)
    for ent, hs in sorted(by.items()):
        lane["held"].append({"ent": ent, "d": hs[0].get("out"), "act": "賣出", "at": "開盤",
                             "items": [{"c": h["c"], "n": h.get("n") or h["c"], "entry": h.get("epx"), "now": h.get("px"),
                                        "now_r": None if h.get("r") is None else round(h["r"] * 100, 2), "ent": h["ent"]} for h in hs]})
    bb = [x for x in B.get("buy") or [] if x.get("fill")]
    if bb and B.get("next"):
        lane["buy"].append({"d": B["next"], "at": "開盤", "act": "買進", "items": [{"c": x["c"], "n": x.get("n") or x["c"]} for x in bb],
                            "out": None, "sell": f'抱 {B.get("hold_n") or 60} 個交易日', "tent": False})
    nw = B.get("next_wk")
    if nw:
        nb = CPG._next_day("tw", nw)
        if nb:
            lane["next"] = {"d": nb, "fix": nw}
    return lane


# ── 台股：配置頁 v2（docs/lab_cfg_v2_plan.md 第 3.1 節）───────────────────────
# 2026-10-24 使用者：「我完全看不懂你的配置 持股只剩40%是為什麼…現金就現金搞那麼複雜幹嘛…你要我持有的股票我根本沒辦法點進去」。
# 由上到下：現在的錢（實際的錢，不是計畫的比例）→ 持股（依策略分組、每一檔可以點、為什麼選它、現金只有一列）
# → 接下來照規則的買賣（只列配置裡的策略）→ 警訊（現在多少、到多少才算）→ 過去照做 → 新飆股名單。

LABEL = {"core": "0050", "boom": "新飆股", "s3": "臺灣50 卡位", "v3l": "財報驚喜", "s5": "長線"}   # 長條、圖例、接下來的買賣用的短名


def _tp(x) -> str:
    """台股價格：1,000 以上不帶小數；100～1,000 一位；以下兩位（尾端的 0 拿掉）。"""
    if x is None:
        return "—"
    if x >= 1000:
        return f"{x:,.0f}"
    s = f"{x:.1f}" if x >= 100 else f"{x:.2f}"
    return s.rstrip("0").rstrip(".")


def _lbl(k: str, name: str | None = None) -> str:
    return LABEL.get(k) or SHORT.get(k) or name or k


def _pmap(data: dict) -> dict:
    """個股頁 advice 的每一檔（持有中、佈局）：{(策略, 代號): pick}。為什麼選它、買進價、現價、停損、什麼時候賣都在這裡。"""
    return {(p.get("k"), p.get("c")): p for p in ((data.get("adv") or {}).get("picks") or [])}


def _sell_txt(p: dict, h: dict) -> str:
    out = p.get("out") or h.get("out")
    if out:
        return f"{_md(out)} 收盤賣"
    if p.get("stop") is not None:
        return f"停損 {_tp(p['stop'])}"
    return ""


def _stop_pct(p: dict) -> int | None:
    """待買進的停損離參考價幾 %（長線＝跌 20%）；照資料算，不寫死。"""
    px, st = p.get("px"), p.get("stop")
    return round((1 - st / px) * 100) if px and st is not None and 0 < st < px else None


def tw_groups(data: dict, bundle: dict) -> list[dict]:
    """台股持股依策略分組：長抱、新飆股、★ 策略（照個股策略頁的順序）。
    每組 {k, name, share（分到）, held（現在是股票的）, rows（持有中）, todo（待買進）, col（顏色槽）}；w 都是占全部資金。"""
    stk = bundle.get("stk") or {}
    P = _pmap(data)
    book = {b.get("k"): b for b in ((data.get("adv") or {}).get("book") or [])}
    c = S.core_of("tw")
    G = [{"k": "core", "name": "0050", "share": c, "held": c, "rows": [], "todo": [], "col": 1,
          "how": "大盤 ETF，一直抱著（0050 或 006208 都可以，兩檔追同一個指數）。"}]
    B = stk.get("boom")
    if B is not None:
        bw = float(stk.get("bw") or CPG.core_boom())
        slot = CPG._boom_slot(stk)
        hn = B.get("hold_n") or 60
        rows = []
        for h in B.get("hold") or []:
            sell = f'{_md(h.get("out"))} 開盤賣' + (f"（已滿 {hn} 個交易日）" if h.get("sell") else f'（{_md(h.get("due"))} 收盤滿 {hn} 個交易日）')
            rows.append({"c": h["c"], "n": h.get("n") or h["c"], "w": (h.get("w") or 0.0) * bw, "ent": h.get("ent"),
                         "epx": h.get("epx"), "px": h.get("px"), "r": h.get("r"), "sell": sell, "why": h.get("why") or []})
        todo = [{"c": x["c"], "n": x.get("n") or x["c"], "w": slot, "when": f'{_mdw(B.get("next"))}開盤買（{_md(B.get("wk"))} 的名單）',
                 "why": ([f'強度 {x["rs"]:.0f}（漲勢勝過 {x["rs"]:.0f}% 的股票）'] if x.get("rs") is not None else []) + (x.get("why") or [])}
                for x in B.get("buy") or [] if x.get("fill")]
        n_max = round(1 / float(B.get("w") or 0.125))
        G.append({"k": "boom", "name": "新飆股", "share": bw, "held": sum(r["w"] for r in rows), "rows": rows, "todo": todo, "col": 2,
                  "B": B, "slot": slot, "n_max": n_max,
                  "how": f"每週五收盤看名單，下一個交易日開盤買，每檔約 {_wp(slot)}、最多 {n_max} 檔，抱 {hn} 個交易日賣。"})
    hmap = {(k, h.get("c")): h for k, hs in (stk.get("hold") or {}).items() for h in hs}
    for i, x in enumerate(CPG.sat_weights(stk)):
        k = x["k"]
        rows = []
        for r in x["rows"]:
            p, h = P.get((k, r["c"])) or {}, hmap.get((k, r["c"])) or {}
            rr = p.get("now_r") if p.get("now_r") is not None else h.get("r")          # advice 的 now_r 是百分比
            rows.append({"c": r["c"], "n": r.get("n") or p.get("n") or r["c"], "w": r["w"], "ent": r.get("ent") or p.get("ent"),
                         "epx": p.get("entry"), "px": p.get("now"), "r": None if rr is None else rr / 100.0,
                         "sell": _sell_txt(p, h), "why": p.get("why") or []})
        have = {r["c"] for r in rows}
        pend = [p for (kk, cc), p in P.items() if kk == k and p.get("act") != "持有中" and cc not in have]
        slots = S.SLOTS.get(k)
        w1 = x["share"] / slots if slots else (x["share"] / len(pend) if pend else 0.0)
        todo = [{"c": p["c"], "n": p.get("n") or p["c"], "w": w1, "when": f'{_mdw(p.get("ent"))}開盤買' if p.get("ent") else "待買進",
                 "stop": p.get("stop"), "spct": _stop_pct(p), "why": p.get("why") or [], "how": p.get("ent_how")} for p in pend]
        b = book.get(k) or {}
        G.append({"k": k, "name": x["name"], "share": x["share"], "held": sum(r["w"] for r in rows), "rows": rows, "todo": todo,
                  "col": 3 + i, "how": (b.get("how") or "").rstrip("。") + ("。" if b.get("how") else ""), "slots": slots})
    return G


def _first_ev(stk: dict, k: str, acts=("買進", "調整")) -> dict | None:
    return next((e for e in stk.get("ev") or [] if e.get("k") == k and e.get("act") in acts), None)


def _cash_why(G: list[dict], stk: dict) -> tuple[list[str], list[tuple]]:
    """現金為什麼多：每一組還沒買滿的原因；接下來排定的買進 [(日期, 開盤/收盤, 占全部資金, 條件)]。"""
    why, buys = [], []                                       # why＝[(日期, 一句)]，最後依日期排
    for g in G:
        idle = g["share"] - g["held"]
        if g["k"] == "core" or idle <= 0.005:
            continue
        nm = _lbl(g["k"], g["name"])
        if g["k"] == "boom":
            B = g["B"]
            nw = B.get("next_wk")
            nb = CPG._next_day("tw", nw) if nw else None
            if g["todo"]:
                why.append((B.get("next"), f'{nm} {_mdw(B.get("next"))}開盤買 {len(g["todo"])} 檔'))
                buys.append((B.get("next"), "開盤", min(idle, g["slot"] * len(g["todo"])), None))
            elif not g["rows"] and nw and nb:
                why.append((nw, f'{nm}{"第一份" if not B.get("wk") else "下一份"}名單 {_mdw(nw)}收盤才出來，{_mdw(nb)}開盤買'))
                buys.append((nb, "開盤", idle, f'{nm}名單有 {g["n_max"]} 檔以上的話'))
            elif nw:
                why.append((nw, f'{nm}還有 {max(1, round(idle / g["slot"]))} 個空位，{_mdw(nw)}收盤看下一份名單'))
            continue
        e = _first_ev(stk, g["k"])
        if e and e.get("act") == "買進" and not e.get("pending") and (e.get("n_items") or e.get("items")):
            n = e.get("n_items") or len(e.get("items") or [])
            why.append((e["d"], f'{nm} {_mdw(e["d"])}{e.get("at") or ""}買 {n} 檔'))
            w1 = (g["todo"][0]["w"] if g["todo"] else idle / max(1, n))
            buys.append((e["d"], e.get("at") or "", min(idle, w1 * n), None))
        elif e and e.get("act") == "買進":
            why.append((e["d"], f'{nm}下一批 {_md(e.get("fix"))} 收盤選、{_mdw(e["d"])}{e.get("at") or ""}買'))
        elif e and e.get("act") == "調整":
            free = (g.get("slots") or 0) - len(g["rows"])
            why.append((e["d"], f'{nm}另外 {free} 個位子 {_mdw(e["d"])}{e.get("at") or ""}補' if free > 0 else f'{nm} {_mdw(e["d"])}調整'))
        elif g["rows"]:
            why.append(("9999", f'{nm}現在 {len(g["rows"])} 檔，沒有排定的買進'))
        else:
            why.append(("9999", f"{nm}這一期沒有要買的"))
    return [t for _, t in sorted(why, key=lambda x: x[0] or "9999")], buys


def tw_money(G: list[dict], stk: dict, N: dict | None, d0: str | None) -> str:
    """① 現在的錢：股票、現金兩個數字；實際的錢的長條（長抱＋每條策略手上的股票＋現金）；每一段一列寫名字和比例；
    一句話講現金為什麼多、接下來排定的買進之後大約多少。機動放現金時（警訊），只剩長抱是股票。"""
    cash_mode = bool(N) and N["now"] < 0.99
    segs = []
    for g in G:
        if g["held"] <= 1e-6 or (cash_mode and g["k"] != "core"):
            continue
        nm = "0050（一直抱著）" if g["k"] == "core" else f'{_lbl(g["k"], g["name"])} {len(g["rows"])} 檔'
        segs.append((nm, g["held"], g["col"]))
    stock = sum(w for _, w, _ in segs)
    cash = max(0.0, 1.0 - stock)
    bar = "".join(f'<i class="c{col}" style="flex:{w * 100:.2f}"></i>' for _, w, col in segs) + \
        (f'<i class="cx" style="flex:{cash * 100:.2f}"></i>' if cash > 1e-4 else "")
    lab = "、".join(f"{nm} {_wp(w)}" for nm, w, _ in segs) + (f"、現金 {_wp(cash)}" if cash > 1e-4 else "")
    lg = "".join(f'<li><u class="c{col}"></u><span>{_e(nm)}</span><em>{_wp(w)}</em></li>' for nm, w, col in segs) + \
        (f'<li><u class="cx"></u><span>現金</span><em>{_wp(cash)}</em></li>' if cash > 1e-4 else "")
    due = due_line("tw", N) if N and N.get("due") else ""
    if cash_mode:
        txt = due or f'<p class="cfwhy">{_sat_sp("tw")}放現金中（警訊），0050 那 {CPG.pct0(S.core_of("tw"))} 一直抱著。</p>'
    elif cash > 0.005 and len(G) == 1:
        txt = '<p class="cfwhy">讀不到各策略的持股（個股頁的資料還沒算出來）。</p>' + due
    elif cash > 0.005:
        why, buys = _cash_why(G, stk)
        t = f'現金 {_wp(cash)} 是各策略還沒買到的部分' + ("：" + "；".join(_e(w) for w in why) if why else "") + "。"
        ds = [b[0] for b in buys if b[0]]
        if ds:
            d1 = min(ds)
            sells = [e for e in (stk.get("ev") or []) + CPG.boom_events(stk) if e.get("act") == "賣出" and (e.get("d") or "") <= d1]
            if not sells:
                at = next((b[1] for b in buys if b[0] == d1), "")
                add = sum(b[2] for b in buys if b[0] == d1)
                cond = [b[3] for b in buys if b[0] == d1 and b[3]]
                t += f'{_e(_mdw(d1))}{_e(at)}買進之後股票約 <b>{CPG.pct0(min(1.0, stock + add))}</b>' + (f"（{_e('、'.join(cond))}）" if cond else "") + "。"
        txt = f'<p class="cfwhy">{t}</p>' + due
    else:
        txt = due
    return ('<h2 class="cfh">現在的錢<span class="sub">台股' + (f'・{_e(_md(d0))} 收盤' if d0 else '') + '</span></h2><div class="cfmo">'
            f'<div class="cfbig"><span><b>{CPG.pct0(stock)}</b>股票</span><span><b>{CPG.pct0(cash)}</b>現金</span></div>'
            f'<div class="cfbar" role="img" aria-label="{_e(lab)}">{bar}</div><ul class="cflg">{lg}</ul>{txt}</div>')


def _row_b(r: dict, todo: bool = False) -> str:
    """一檔的第二行：持有中＝哪天買、買進價、現在、哪天賣（或停損）；待買進＝哪天買、停損約多少。"""
    if todo:
        b = r.get("when") or ""
        if r.get("stop") is not None:
            b += f'・停損約 {_tp(r["stop"])}' + (f'（買進價跌 {r["spct"]}%）' if r.get("spct") else "")
        return b
    b = f'{_md(r.get("ent"))} 買' + (f' {_tp(r["epx"])}，現在 {_tp(r["px"])}' if r.get("epx") is not None and r.get("px") is not None else "")
    return b + (f'・{r["sell"]}' if r.get("sell") else "")


def _ck(c: str) -> str:
    """點了開卡片：data-c＝籌碼雷達範圍內開個股卡（從最上面的「配置」段開始，‹ › 換這一段的其他股票）；
    範圍外 page.py 不處理，交給 copage 的 data-co 開公司卡（最上面也是「配置」段）。
    只寫 data-co 的話，範圍內的也會捲到公司分析、跳過「配置」段。"""
    c = _e(c)
    return f'data-c="{c}" data-co="{c}"'


def _row(r: dict, todo: bool = False) -> str:
    """持股的一列（整列可以點，見 _ck）。"""
    rr = "" if todo or r.get("r") is None else f'<span class="r {"up" if r["r"] >= 0 else "dn"}">{_pc(r["r"])}</span>'
    b = _row_b(r, todo)
    why = "；".join(r.get("why") or [])
    return (f'<a class="cfrow{" todo" if todo else ""}" {_ck(r["c"])}><span class="cfra"><b>{_e(r["n"])}</b>'
            f'<span class="cd">{_e(r["c"])}</span>' + ('<span class="cftag">待買進</span>' if todo else "") + '<span class="go">›</span>'
            f'<span class="w">{"約 " if todo else ""}{_wp(r["w"])}</span>{rr}</span><span class="cfrb">{_e(b)}</span>'
            + (f'<span class="cfrc">為什麼：{_e(why)}</span>' if why else "") + "</a>")


def _grp(g: dict, stk: dict) -> str:
    n = len(g["rows"])
    head = (f'<span class="cfgt"><b>{_e(g["name"])}</b>' + ("" if g["k"] == "core" else f'<span class="cd">{n} 檔</span>')
            + f'<em>{_wp(g["held"])}</em></span>')
    if g["k"] == "core":
        sub = g["how"]
    else:
        idle = g["share"] - g["held"]
        sub = (f'分到 {_wp(g["share"])}' + ("（買滿）" if idle <= 0.001 else f"，現在用到 {_wp(g['held'])}" if g["held"] > 1e-6 else "") + "。"
               + g["how"])
        hows = {t.get("how") for t in g["todo"] if t.get("how")}
        if len(hows) == 1:
            sub += f' 待買的 {len(g["todo"])} 檔：{hows.pop().rstrip("。")}。'
    body = "".join(_row(r) for r in g["rows"]) + "".join(_row(r, True) for r in g["todo"])
    if not body and g["k"] != "core":
        if g["k"] == "boom":
            B = g["B"]
            nw = B.get("next_wk")
            nb = CPG._next_day("tw", nw) if nw else None
            empty = (f'{"第一份" if not B.get("wk") else "下一份"}名單 {_mdw(nw)}收盤產生' + (f"，{_mdw(nb)}開盤買" if nb else "")
                     + "。名單出來後每一檔都列在這裡，可以點進去看。") if nw else "還沒有名單。"
        else:
            e = _first_ev(stk, g["k"], ("買進", "調整", "賣出"))
            empty = "這一期沒有部位" + (f'；下一件：{_mdw(e["d"])}{e.get("at") or ""}{e.get("act") or ""}' if e else "") + "。"
        body = f'<div class="cfempty">{_e(empty)}</div>'
    return (f'<div class="cfgr" data-k="{_e(g["k"])}"><div class="cfgh">{head}<span class="cfgs">{_e(sub)}</span></div>{body}</div>')


def tw_hold(G: list[dict], stk: dict, N: dict | None) -> str:
    """② 持股：依策略分組，每一檔可以點；現金只在最下面一列。"""
    cash_mode = bool(N) and N["now"] < 0.99
    stock = S.core_of("tw") if cash_mode else sum(g["held"] for g in G)
    cash = max(0.0, 1.0 - stock)
    note = (f'<p class="cfwhy">警訊：{_sat_sp("tw")}現在放現金；下面是各策略照規則該有的股票，買回時照這樣買。</p>' if cash_mode else "")
    cw = "警訊：機動放現金中" if cash_mode else "上面各策略還沒買到的部分"
    return ('<h2 class="cfh">持股<span class="sub">點股票看走勢、籌碼、財報</span></h2>' + note
            + "".join(_grp(g, stk) for g in G)
            + f'<div class="cfcash"><b>現金</b><span>{cw}</span><em>{_wp(cash)}</em></div>')


def _names(items: list, k: int = 8) -> str:
    """一串股票名（每一個都可以點）。"""
    its = [x for x in items or [] if x.get("c")]
    s = "、".join(f'<a {_ck(x["c"])}>{_e(x.get("n") or x["c"])}</a>' for x in its[:k])
    return s + (f" 等 {len(its)} 檔" if len(its) > k else "")


def tw_sched(G: list[dict], stk: dict, N: dict | None) -> str:
    """③ 接下來照規則的買賣：依日期，只列配置裡的策略（2026-10-24 使用者決定：觀察中策略的訊號不放配置頁）。股票名都可以點。"""
    ev = []                                                   # (日期, 開盤 0／收盤 1, 標籤, HTML, 小字)
    cash = bool(N) and N["next"] < 0.99
    if N and N.get("due"):
        day = CPG._next_day("tw", N["d"])
        if day:
            ev.append((day, 1, "賣出" if cash else "買進", _e(_act_txt("tw", cash)), ""))
    gb = next((g for g in G if g["k"] == "boom"), None)
    for e in CPG.boom_events(stk, cash):
        at = 0 if e.get("at") == "開盤" else 1
        if e["act"] == "名單":
            B = gb["B"] if gb else {}
            ev.append((e["d"], 1, "看名單", f'新飆股：{"第一份名單" if not B.get("wk") else "這一週的名單"}', ""))
            nb = CPG._next_day("tw", e["d"])
            free = gb and (gb["share"] - gb["held"]) > gb["slot"] * 0.5
            if nb and free:
                ev.append((nb, 0, "買進", f'新飆股：名單前面的股票，每檔約 {_wp(gb["slot"])}', "依強勢排，現金夠才買" + ("；機動放現金中，先不買" if cash else "")))
        else:
            ev.append((e["d"], at, e["act"], f'新飆股：{_names(e.get("items"))}', _e(re.sub(r"<[^>]+>", "", e.get("sub") or ""))))
    use = {g["k"] for g in G}
    for e in stk.get("ev") or []:
        if e.get("k") not in use:
            continue
        nm = _lbl(e["k"], e.get("sname"))
        at = 0 if e.get("at") == "開盤" else 1
        if e.get("act") == "買進" and e.get("pending"):
            ev.append((e["d"], at, "買進", f'{_e(nm)}：下一批（{_e(_md(e.get("fix")))} 收盤選）', ""))
        elif e.get("items"):
            ev.append((e["d"], at, e.get("act") or "", f'{_e(nm)}：{_names(e.get("items"))}', _e(e.get("how") or "")))
        else:
            ev.append((e["d"], at, e.get("act") or "", f'{_e(nm)}：{_e(e.get("note") or e.get("act") or "")}', ""))
    if not ev:
        return '<h2 class="cfh">接下來照規則的買賣</h2><p class="cfwhy">接下來 45 天沒有排定的買賣。</p>'
    ev.sort(key=lambda x: (x[0], x[1]))
    tags = {"買進": "b", "賣出": "s", "看名單": "l", "調整": "a", "換股": "a"}
    out, last = [], None
    for d, at, tag, html_, sub in ev:
        key = (d, at)
        if key != last:
            if last:
                out.append("</div>")
            out.append(f'<div class="cfev"><div class="cfevd"><b>{_e(_md(d))}</b><span>{_e(_mdw(d)[len(_md(d)):])}{"開盤" if at == 0 else "收盤"}</span></div>')
            last = key
        out.append(f'<div class="cfevx"><span class="cftg t{tags.get(tag, "a")}">{_e(tag)}</span>{html_}'
                   + (f'<span class="cfevs">{sub}</span>' if sub else "") + "</div>")
    out.append("</div>")
    return ('<h2 class="cfh">接下來照規則的買賣<span class="sub">45 天內・只列配置裡的策略・點股票看細節</span></h2>'
            f'<div class="cfsch">{"".join(out)}</div>'
            '<details class="cftlw"><summary>看時間軸</summary>' + tl_shell("tw") + "</details>")


def warn_html(mk: str, N: dict) -> str:
    """④ 警訊：每一個寫「現在多少、到多少才算」，一條小長條畫出門檻線；下面一句規則與要不要動。"""
    rows = []
    pm = PLAN_MK[mk]
    for f in N["fams"]:
        on = f["lit"]
        nm = _fam_name(pm, f["k"])
        if f["k"] == "trend":
            pct = f.get("pct")
            w = 0.0 if pct is None else max(0.0, min(100.0, 50.0 - pct * 2.5))
            mark, lim = 50.0, "跌破才算"
            val = "算不出來" if pct is None else f'收盤比年線{"低" if pct < 0 else "高"} {abs(pct):.1f}%'
        elif f["k"] == "flat":
            held, na = f.get("held") or [], f.get("n_all") or 0
            nm = "總經策略"                                        # 「全部空手」寫在後面的「才算」裡，名稱短一點才不會折成兩行
            w, mark, lim = (100.0 * (1 - len(held) / na) if na else (100.0 if on else 0.0)), 99.0, "全部空手才算"
            val = "全部空手" if on else f"{len(held)} 條有部位"
        else:
            v = f.get("v")
            w, mark, lim = (0.0 if v is None else max(0.0, min(100.0, v))), S.HOT, f"{S.HOT:.0f} 分以上算"
            val = "沒有資料" if v is None else f"{v:.1f} 分"
        rows.append(f'<div class="cfwr{" on" if on else ""}"><b>{_e(nm)}</b><i class="cfwb"><i style="width:{w:.1f}%"></i>'
                    f'<u style="left:{mark:.0f}%"></u></i><span class="cfwv">{_e(val)}<span>（{_e(lim)}）</span>'
                    + ('<em>成立</em>' if on else "") + "</span></div>")
    if mk == "tw":
        c = S.core_of("tw")
        rule = (f"兩個以上同時成立：隔天收盤把新飆股和個股策略（{_sat_txt('tw').replace('機動 ', '')}）換成現金；"
                f"警訊少於兩個滿兩週才買回；0050 那 {CPG.pct0(c)} 一直抱著。")
    else:
        rule = rule_line(mk) + "。"
    return (f'<h2 class="cfh">警訊<span class="sub">{N["n"]}／{len(N["fams"])} 成立</span></h2><div class="cfws">{"".join(rows)}</div>'
            f'<div class="cfrule2">{_e(rule)}</div>' + due_line(mk, N))


def tw_parts(data: dict, bundle: dict) -> dict:
    N = (bundle.get("now") or {}).get("tw")
    stk = bundle.get("stk") or {}
    A = data.get("adv") or {}
    d0 = (N or {}).get("d") or A.get("last")
    G = tw_groups(data, bundle)
    nx = CPG._next_day("tw", d0) if d0 else None
    card = tw_money(G, stk, N, d0)
    perf = ('<h2 class="cfh">過去照做</h2>' + perf_line("tw", bundle) + detail_html("tw", bundle))
    use = [s["k"] for s in stk.get("st") or []]
    bm = ((((bundle.get("R") or {}).get("mk") or {}).get("tw") or {}).get("sc") or {}).get("plan", {}).get("boom") or {}
    bx = (f'過去照做：{CPG.yr0(bm["a"])} 年起每年賺 {_pc(bm["cagr"]).lstrip("+")}、最慘時跌 {bm["mdd"] * 100:.0f}%'
          if bm.get("cagr") is not None else "")
    return {"card": card, "hold": tw_hold(G, stk, N), "sched": tw_sched(G, stk, N), "bx": bx,
            "warn": warn_html("tw", N) if N else '<h2 class="cfh">警訊</h2><p class="cfwhy">今天的讀數還沒算出來。</p>',
            "perf": perf, "boom": boom_html(stk, bundle), "d": d0, "nx": nx,
            "tl": {"use": use, "boom": _boom_lane(stk)},
            "pos": pos_map(G)}


def pos_map(G: list[dict]) -> dict:
    """個股卡、公司卡最上面「配置」段要的：{代號: [{k 策略, n 名稱, w 占全部資金, h 持有中 1／待買進 0, t 第二行, y 為什麼}]}。"""
    out: dict = {}
    for g in G:
        for todo, rs in ((False, g["rows"]), (True, g["todo"])):
            for r in rs:
                out.setdefault(r["c"], []).append({"k": g["k"], "n": r["n"], "w": round(r["w"], 5), "h": 0 if todo else 1,
                                                    "t": _row_b(r, todo), "y": "；".join(r.get("why") or [])})
    return out


# ── 美股：配置頁 v2（docs/lab_cfg_v2_plan.md 第 3.2 節）───────────────────────

def _qm_lane(G: dict) -> dict | None:
    """美股強勢品質股在時間軸上的一列（us_state 的結果）：持有中（最早買進那天起，到跌破 50 日線才賣）、要賣的、
    下一次買進（有空位才有）。"""
    n, nms = G["n"], G["nms"]
    if not G["on"] or not n:
        return None
    lane = {"k": "qm", "name": CPG.QM_NAME, "hold": "到跌破 50 日線", "held": [], "buy": [], "next": None, "adj": []}
    rows = G["rows"]
    if rows:
        lane["held"].append({"ent": min(r["ent"] for r in rows), "d": None, "act": "賣出", "at": "開盤",
                             "items": [{"c": r["c"], "n": r["c"], "nm": CPG.us_name(r["c"], nms), "ent": r["ent"],
                                        "now_r": None if r.get("r") is None else round(r["r"] * 100, 2)} for r in rows]})
    for r in rows:
        if r.get("sell"):
            lane["adj"].append({"d": r["sell"], "at": "開盤", "act": "賣出", "note": f'賣掉 {CPG.us_name(r["c"], nms)}（收盤跌破 50 日線）'})
    buys = [x for x in G["todo"] if x["w"] > 1e-3]
    if buys:
        lane["buy"].append({"d": buys[0]["d"], "at": "開盤", "act": "買進", "out": None, "tent": False,
                            "items": [{"c": x["c"], "n": x["c"], "nm": CPG.us_name(x["c"], nms)} for x in buys],
                            "sell": "收盤跌破 50 日線就在下一個交易日開盤賣"})
    elif G["free"] and G["nf"]:
        from . import ussxqm as QM
        lane["next"] = {"d": QM.next_day(G["nf"]), "fix": G["nf"]}
    return lane


YF = "https://finance.yahoo.com/quote/"


def _yf(c: str) -> str:
    """美股點了開 Yahoo Finance（美股個股卡做好之前的過渡，docs/lab_cfg_v2_plan.md 第 5 節第 2 步）。
    代號的「.」「/」在 Yahoo 寫成「-」（BRK.B → BRK-B）。"""
    return f'href="{YF}{_e(re.sub(r"[./]", "-", str(c)))}" target="_blank" rel="noopener"'


def us_state(bundle: dict) -> dict:
    """美股持股（配置頁 v2 的 ①②③ 共用；w 都是占全部資金）。
    rows＝持有中 [{c, ent, r, pct（比 50 日線）, sell（哪天開盤賣）, trig, rk, rs, w}]；todo＝待買進 [{c, d, rk, rs, w}]；
    gone＝每天的檢查跌破 50 日線、賣出日已經過了的 [{c, on, trig}]；idle＝現金；free＝下一份名單出來時的空位；nf＝下一份名單哪天收盤。
    每週紀錄（週六）之後，每天的 50 日線檢查（W）比較新：漲跌與比重照 W 的收盤更新；賣出日已過的算現金；
    買進日已過的算持有（那一檔的新價格要等下一份每週紀錄，比重照買進時）。"""
    qm = bundle.get("qm")
    on = CPG.qm_on("spx", qm)
    G = {"on": on, "c0": S.core_of("spx"), "sw": S.sat_of("spx"), "rows": [], "todo": [], "gone": [], "idle": 0.0,
         "free": 0, "nf": None, "n": {}, "W": {}, "nms": {}, "d": None, "why": CPG._qm_why_not("spx", qm)}
    if not on:
        return G
    n, W, nms = CPG._qm_now(qm), CPG._qm_watch(qm), CPG._qm_names(qm)
    G.update(n=n, W=W, nms=nms, why="")
    if not n:
        return G
    last = W.get("d") or n.get("d")
    nx = n.get("next")
    upd = bool(W.get("d") and n.get("d") and W["d"] > n["d"])
    wl = {x["c"]: x for x in W.get("hold") or []}
    rank = {x["c"]: (i + 1, x.get("rs")) for i, x in enumerate(n.get("list") or [])}
    wsold = {x["c"]: x for x in W.get("sell") or [] if x.get("on")}
    rows, gone, idle = [], [], float(n.get("idle") or 0.0)
    for h in n.get("hold") or []:
        c, w0 = h["c"], float(h.get("w") or 0.0)
        x = wl.get(c) or {}
        g = x["px"] / h["px"] if upd and x.get("px") and h.get("px") else 1.0
        if c in wsold:
            sell, trig = wsold[c]["on"], wsold[c].get("trig")
        elif h.get("sell"):
            sell, trig = nx, n.get("d")
        else:
            sell = trig = None
        if sell and last and sell <= last:                      # 賣出日已經過了：算現金
            gone.append({"c": c, "on": sell, "trig": trig})
            idle += w0
            continue
        rk, rs = rank.get(c) or (None, None)
        r = h.get("r")
        rows.append({"c": c, "ent": h.get("ent"), "r": None if r is None else (1 + r) * g - 1, "pct": CPG._qm_pct_ma(h, x),
                     "sell": sell, "trig": trig, "v": w0 * g, "rk": rk, "rs": rs})
    split, _ = CPG.qm_buy_split(n, W)
    bought = bool(nx and last and nx <= last)
    todo = []
    for c, wb in split:
        rk, rs = rank.get(c) or (None, None)
        it = {"c": c, "v": wb, "d": nx, "rk": rk, "rs": rs}
        if bought and wb > 1e-6:                                # 買進日已經過了：算持有
            rows.append(dict(it, ent=nx, r=None, pct=None, sell=None, trig=None, new=True))
            idle -= wb
        elif not bought:
            todo.append(it)
    idle = max(0.0, idle)
    tot = sum(r["v"] for r in rows) + idle
    k = G["sw"] / tot if tot > 0 else 0.0
    for r in rows + todo:
        r["w"] = r["v"] * k
    n_after = sum(1 for r in rows if not r.get("sell")) + sum(1 for t in todo if t["w"] > 1e-3)
    G.update(rows=rows, todo=todo, gone=gone, idle=idle * k, d=last, nf=CPG._qm_next_week_end(last),
             free=max(0, QX.QM_SLOTS - n_after))
    return G


def _uname(c: str, nms: dict) -> str:
    return CPG.us_label(c, nms)[0]


def _ulink(c: str, nms: dict) -> str:
    """句子裡的美股名字（可以點，開 Yahoo Finance）。"""
    return f'<a {_yf(c)}>{_e(_uname(c, nms))}</a>'


def _us_cash_why(G: dict) -> str:
    """現金為什麼有（空的位子、這週賣掉的），接下來第一次排定的買賣之後股票大約多少。"""
    nms, cash = G["nms"], G["idle"]
    if cash <= 0.005:
        return ""
    t = f'現金 {_wp(cash)} 是空的位子'
    if G["gone"]:
        t += "（" + "、".join(f'{_e(_uname(x["c"], nms))} {_e(_md(x["on"]))} 開盤賣掉了' for x in G["gone"]) + "）"
    ds = sorted({r["sell"] for r in G["rows"] if r.get("sell")} | {x["d"] for x in G["todo"] if x.get("d") and x["w"] > 1e-3})
    if not ds:
        nf = G["nf"]
        return t + (f'，{_e(_mdw(nf))}收盤看下一份名單，有空位就在下一個交易日開盤買。' if nf else "。")
    d1 = ds[0]
    sells = [r for r in G["rows"] if r.get("sell") == d1]
    buys = [x for x in G["todo"] if x.get("d") == d1 and x["w"] > 1e-3]
    act = []
    if sells:
        act.append("賣 " + "、".join(_e(_uname(r["c"], nms)) for r in sells))
    if buys:
        act.append("買 " + "、".join(f'{_e(_uname(x["c"], nms))}（約 {_wp(x["w"])}）' for x in buys))
    keep = [r for r in G["rows"] if not r.get("sell") or r["sell"] > d1]
    n1 = len(keep) + len(buys)
    stock = G["c0"] + sum(r["w"] for r in keep) + sum(x["w"] for x in buys)
    a = "、".join(act)
    t += f'：{_e(_mdw(d1))}開盤{a}' + (" " if a[-1:].isascii() and a[-1:].isalnum() else "") + "之後，"   # 英文名後面空一格
    t += f'{QX.QM_SLOTS} 個位子都滿' if n1 >= QX.QM_SLOTS else f'{n1} 檔、空 {QX.QM_SLOTS - n1} 個位子'
    t += f'，股票約 <b>{CPG.pct0(min(1.0, stock))}</b>。'
    if n1 < QX.QM_SLOTS and G["nf"] and G["nf"] > d1:
        t += f'空的位子等 {_e(_mdw(G["nf"]))}收盤的下一份名單。'
    return t


def us_money(G: dict, N: dict | None) -> str:
    """① 現在的錢（美股）：股票、現金兩個數字，實際的錢的長條，每一段一列寫名字和比例，一句話講現金為什麼有。
    全部持股放現金時（警訊）只剩長抱（美股 VER 4 長抱 0%，所以整個帳戶都是現金）。"""
    cash_mode = bool(N) and N["now"] < 0.99
    d0 = G["d"] or (N or {}).get("d")
    head = f'<h2 class="cfh">現在的錢<span class="sub">美股' + (f'・{_e(_md(d0))} 收盤' if d0 else '') + '</span></h2>'
    if G["on"] and not G["n"]:
        return head + '<div class="cfmo"><p class="cfwhy">強勢品質股每週六更新的持股紀錄還沒產生，持股要等紀錄出來才算得出來。</p></div>'
    segs = []                                                # (名稱, 占全部資金, 顏色槽)：顏色照順序
    if G["c0"] > 0:
        segs.append(("S&P 500 ETF（一直抱著）", G["c0"], 1))
    if not cash_mode:
        if G["on"]:
            hw = sum(r["w"] for r in G["rows"])
            if hw > 1e-6:
                segs.append((f'強勢品質股 {len(G["rows"])} 檔', hw, len(segs) + 1))
        else:
            segs.append(("S&P 500 ETF（SPY 或 VOO）", G["sw"], len(segs) + 1))
    stock = sum(w for _, w, _ in segs)
    cash = max(0.0, 1.0 - stock)
    bar = "".join(f'<i class="c{col}" style="flex:{w * 100:.2f}"></i>' for _, w, col in segs) + \
        (f'<i class="cx" style="flex:{cash * 100:.2f}"></i>' if cash > 1e-4 else "")
    lab = "、".join(f"{nm} {_wp(w)}" for nm, w, _ in segs) + (f"、現金 {_wp(cash)}" if cash > 1e-4 else "")
    lg = "".join(f'<li><u class="c{col}"></u><span>{_e(nm)}</span><em>{_wp(w)}</em></li>' for nm, w, col in segs) + \
        (f'<li><u class="cx"></u><span>現金</span><em>{_wp(cash)}</em></li>' if cash > 1e-4 else "")
    due = due_line("us", N) if N else ""
    if cash_mode:
        txt = due or f'<p class="cfwhy">警訊：{_sat_sp("us")}放現金中。</p>'
    elif G["on"]:
        w = _us_cash_why(G)
        txt = (f'<p class="cfwhy">{w}</p>' if w else "") + due
    else:
        txt = due
    return (head + '<div class="cfmo">'
            f'<div class="cfbig"><span><b>{CPG.pct0(stock)}</b>股票</span><span><b>{CPG.pct0(cash)}</b>現金</span></div>'
            f'<div class="cfbar" role="img" aria-label="{_e(lab)}">{bar}</div><ul class="cflg">{lg}</ul>{txt}</div>')


def _urow(r: dict, G: dict, todo: bool = False) -> str:
    """美股持股的一列：整列點了開 Yahoo Finance（美股個股卡做好之前）。第二行本業，第三行哪天買、離 50 日線多遠或哪天賣，
    第四行為什麼（這一週名單的第幾名）。"""
    nm, what = CPG.us_label(r["c"], G["nms"])
    wk = G["n"].get("wk")
    rr = "" if todo or r.get("r") is None else f'<span class="r {"up" if r["r"] >= 0 else "dn"}">{_pc(r["r"])}</span>'
    if todo:
        b = f'{_mdw(r["d"])}開盤買' if r["w"] > 1e-3 else "現金不夠，這一檔先不買"
    else:
        b = f'{_md(r["ent"])} 買'
        if r.get("sell"):
            b += f'・{_mdw(r["sell"])}開盤賣（{_md(r["trig"])} 收盤跌破 50 日線）'
        elif r.get("pct") is not None:
            b += f'・比 50 日線{"高" if r["pct"] >= 0 else "低"} {abs(r["pct"]) * 100:.1f}%'
        elif r.get("new"):
            b += "・漲跌等這週六的持股紀錄"
    why = ""
    if r.get("rk") and r.get("rs") is not None and wk:
        why = (f'{_md(wk)} 收盤的名單第 {r["rk"]} 名' + ("（手上還沒有）" if todo else "")
               + f'，漲勢勝過 {r["rs"]:.0f}% 的美股')
    w = (("約 " if todo else "") + _wp(r["w"])) if r["w"] > 1e-3 else ""
    head = f'<b>{_e(nm)}</b>' + (f'<span class="cd">{_e(r["c"])}</span>' if nm != r["c"] else "")
    return (f'<a class="cfrow{" todo" if todo else ""}" {_yf(r["c"])}><span class="cfra">{head}'
            + ('<span class="cftag">待買進</span>' if todo else "") + '<span class="go">›</span>'
            f'<span class="w">{w}</span>{rr}</span>' + (f'<span class="cfri">{_e(what)}</span>' if what else "")
            + f'<span class="cfrb">{_e(b)}</span>' + (f'<span class="cfrc">為什麼：{_e(why)}</span>' if why else "") + "</a>")


def _usn(c: str, nms: dict | None) -> str:
    """美股一列的標的格（2026-10-24 使用者：「美股那些公司誰知道你是什麼公司…台股不都有列嗎？比照著做」）：
    公司名＋代號（同台股「台塑 1301」），下一行本業（簡介庫第一段，corepage.us_label）。"""
    nm, what = CPG.us_label(c, nms)
    head = f'{_e(nm)} <span class="cd">{_e(c)}</span>' if nm != c else _e(c)
    return head + (f'<div class="cfin">{_e(what)}</div>' if what else "")


def _qm_cands(G: dict) -> str:
    """名單前幾名（手上沒有的）：有空位時就照這個順序買（每週五收盤定案）。數量＝fund_intro.US_QM_SHOW（缺口檢查涵蓋同一批）。
    名字點了開 Yahoo Finance。"""
    n, nms = G["n"], G["nms"]
    have = {r["c"] for r in G["rows"]} | {x["c"] for x in G["todo"]} | {x["c"] for x in G["gone"]}
    L = [x for x in n.get("list") or [] if x["c"] not in have][:FI.US_QM_SHOW]
    if not L:
        return ""
    nf = G["nf"]
    sub = (f'{_md(n.get("wk"))} 收盤・名單共 {n.get("n_list", 0)} 檔'
           + (f'・{_md(nf)} 收盤定案' if nf and not n.get("wk_done") else ""))
    rows = "".join(f'<tr><td><a {_yf(x["c"])}>{_usn(x["c"], nms)}</a></td><td class="w">{x["rs"]:.0f}</td></tr>' for x in L)
    return (f'<h3 class="cfh3">有空位時依序買：名單前 {len(L)} 名（手上沒有的）<span class="sub">{sub}</span></h3>'
            '<table class="cfht cfql"><tr><th>公司</th><th title="漲幅勝過多少比例的美股（1～99）">強度</th></tr>'
            f'{rows}</table>')


def us_hold(G: dict, N: dict | None) -> str:
    """② 持股（美股）：美股強勢品質股一組（判定沒過＝S&P 500 ETF），每一檔點了開 Yahoo Finance；現金只在最下面一列；
    下面是名單前幾名（有空位時依序買）。"""
    cash_mode = bool(N) and N["now"] < 0.99
    sw = G["sw"]
    note = (f'<p class="cfwhy">警訊：{_sat_sp("us")}現在放現金；下面是照規則該有的股票，買回時照這樣買。</p>' if cash_mode else "")
    grs = []
    if G["c0"] > 0:
        grs.append(f'<div class="cfgr" data-k="core"><div class="cfgh"><span class="cfgt"><b>S&amp;P 500 ETF</b><em>{_wp(G["c0"])}</em></span>'
                   f'<span class="cfgs">一直抱著（例如 SPY、VOO）。</span></div></div>')
    if not G["on"]:
        sub = (G["why"] + " " if G["why"] else "") + "全部持股買 S&P 500 ETF（例如 SPY、VOO），有警訊時換成現金。"
        row = (f'<a class="cfrow" {_yf("SPY")}><span class="cfra"><b>S&amp;P 500 ETF</b><span class="cd">SPY／VOO</span>'
               f'<span class="go">›</span><span class="w">{_wp(sw)}</span></span><span class="cfrb">一直抱著・有警訊時換成現金</span></a>')
        grs.append(f'<div class="cfgr" data-k="idx"><div class="cfgh"><span class="cfgt"><b>S&amp;P 500</b><em>{_wp(0.0 if cash_mode else sw)}</em></span>'
                   f'<span class="cfgs">{_e(sub)}</span></div>{row}</div>')
        stock = G["c0"] + (0.0 if cash_mode else sw)
    else:
        held = sum(r["w"] for r in G["rows"])
        nt = len(G["todo"])
        cnt = f'{len(G["rows"])} 檔' + (f'＋{nt} 檔待買' if nt else "")
        sub = (f'分到 {_wp(sw)}' + ("（買滿）" if sw - held <= 0.001 else f"，現在用到 {_wp(held)}" if held > 1e-6 else "") + "。"
               f'每週五收盤看名單（股價強勢、本業賺錢的公司），有空位就在下一個交易日開盤買，最多 {QX.QM_SLOTS} 檔、每檔約 {CPG._qm_per("spx")}；'
               "收盤跌破 50 日線，就在下一個交易日開盤賣。")
        body = "".join(_urow(r, G) for r in G["rows"]) + "".join(_urow(x, G, True) for x in G["todo"])
        if not body:
            nf = G["nf"]
            body = ('<div class="cfempty">' + ("每週六更新的持股紀錄還沒產生。" if not G["n"] else
                                                 f'現在沒有股票；{_e(_mdw(nf))}收盤看下一份名單。' if nf else "現在沒有股票。") + "</div>")
        grs.append(f'<div class="cfgr" data-k="qm"><div class="cfgh"><span class="cfgt"><b>{CPG.QM_NAME}</b><span class="cd">{cnt}</span>'
                   f'<em>{_wp(0.0 if cash_mode else held)}</em></span><span class="cfgs">{_e(sub)}</span></div>{body}</div>')
        stock = G["c0"] + (0.0 if cash_mode else held)
    cash = max(0.0, 1.0 - stock)
    cw = "警訊：全部持股放現金中" if cash_mode and G["c0"] <= 0 else "警訊：機動放現金中" if cash_mode else "空的位子"
    return ('<h2 class="cfh">持股<span class="sub">點股票開 Yahoo Finance 看走勢、財報</span></h2>' + note + "".join(grs)
            + f'<div class="cfcash"><b>現金</b><span>{cw}</span><em>{_wp(cash)}</em></div>'
            + (_qm_cands(G) if G["on"] and G["n"] else ""))


def us_sched(G: dict, N: dict | None) -> str:
    """③ 接下來照規則的買賣（美股）：依日期；拿著的股票每天收盤看 50 日線那一列放在第一天後面。股票名點了開 Yahoo Finance。"""
    ev = []                                                   # (日期, 開盤 0／收盤 1, 標籤, HTML, 小字)
    cash = bool(N) and N["next"] < 0.99
    nms = G["nms"]
    if N and N.get("due"):
        day = CPG._next_day("spx", N["d"])
        if day:
            ev.append((day, 1, "賣出" if cash else "買進", _e(_act_txt("us", cash)), ""))
    if G["on"] and G["n"]:
        by: dict = {}
        for r in G["rows"]:
            if r.get("sell"):
                by.setdefault(r["sell"], []).append(r)
        for d, rs in sorted(by.items()):
            trig = {r["trig"] for r in rs}
            ev.append((d, 0, "賣出", "強勢品質股：" + "、".join(_ulink(r["c"], nms) for r in rs),
                       (f'{_e(_md(trig.pop()))} 收盤跌破 50 日線' if len(trig) == 1 and None not in trig else "收盤跌破 50 日線")))
        ok = [x for x in G["todo"] if x["w"] > 1e-3]
        if ok:
            wk = G["n"].get("wk")
            ev.append((ok[0]["d"], 0, "買進", "強勢品質股：" + "、".join(f'{_ulink(x["c"], nms)}（約 {_wp(x["w"])}）' for x in ok),
                       f'{_e(_md(wk))} 收盤的名單裡手上還沒有的' + ("；全部持股放現金中，先不買" if cash else "")))
        nf = G["nf"]
        if nf:
            free = G["free"]
            ev.append((nf, 1, "看名單", "強勢品質股：這一週的名單",
                       f'{QX.QM_SLOTS} 個位子都滿，有空位才買' if not free else f'有 {free} 個空位，名單前面、手上沒有的下一個交易日開盤買'))
            if free:
                from . import ussxqm as QM
                ev.append((QM.next_day(nf), 0, "買進", f'強勢品質股：名單前面的公司，每檔約 {CPG._qm_per("spx")}',
                           "依強勢排，現金夠才買" + ("；全部持股放現金中，先不買" if cash else "")))
    ev.sort(key=lambda x: (x[0], x[1]))
    tags = {"買進": "b", "賣出": "s", "看名單": "l", "檢查": "l"}
    out, last = [], None
    for d, at, tag, html_, sub in ev:
        key = (d, at)
        if key != last:
            if last:
                out.append("</div>")
            out.append(f'<div class="cfev"><div class="cfevd"><b>{_e(_md(d))}</b><span>{_e(_mdw(d)[len(_md(d)):])}{"開盤" if at == 0 else "收盤"}</span></div>')
            last = key
        out.append(f'<div class="cfevx"><span class="cftg t{tags.get(tag, "a")}">{_e(tag)}</span>{html_}'
                   + (f'<span class="cfevs">{sub}</span>' if sub else "") + "</div>")
    if out:
        out.append("</div>")
    if G["on"] and G["rows"]:                               # 每天的 50 日線檢查：放在第一天後面（同示意圖）
        near = sorted((r["pct"], r["c"]) for r in G["rows"] if r.get("pct") is not None and not r.get("sell"))
        sub = f'最接近的是 {_ulink(near[0][1], nms)}，比 50 日線高 {near[0][0] * 100:.1f}%' if near and near[0][0] >= 0 else ""
        daily = ('<div class="cfev"><div class="cfevd"><b>每天</b><span>收盤</span></div><div class="cfevx"><span class="cftg tl">檢查</span>'
                 '拿著的股票收盤跌破 50 日線，就在下一個交易日開盤賣' + (f'<span class="cfevs">{sub}</span>' if sub else "") + "</div></div>")
        i = next((k for k, s in enumerate(out) if k > 0 and s == "</div>"), None)
        out = out[:i + 1] + [daily] + out[i + 1:] if i is not None else [daily] + out
    if not out:
        txt = "接下來沒有排定的買賣；有警訊時才會換成現金。" if not G["on"] else "接下來沒有排定的買賣。"
        return f'<h2 class="cfh">接下來照規則的買賣</h2><p class="cfwhy">{txt}</p>'
    return ('<h2 class="cfh">接下來照規則的買賣<span class="sub">點股票開 Yahoo Finance</span></h2>'
            f'<div class="cfsch">{"".join(out)}</div>'
            + ('<details class="cftlw"><summary>看時間軸</summary>' + tl_shell("us") + "</details>" if G["on"] and G["n"] else ""))


def us_parts(data: dict, bundle: dict) -> dict:
    N = (bundle.get("now") or {}).get("spx")
    G = us_state(bundle)
    d0 = G["d"] or (N or {}).get("d")
    nx = CPG._next_day("spx", d0) if d0 else None
    perf = '<h2 class="cfh">過去照做</h2>' + perf_line("us", bundle) + detail_html("us", bundle)
    return {"card": us_money(G, N), "hold": us_hold(G, N), "sched": us_sched(G, N),
            "warn": warn_html("us", N) if N else '<h2 class="cfh">警訊</h2><p class="cfwhy">今天的讀數還沒算出來。</p>',
            "perf": perf, "d": d0, "nx": nx, "tl": {"qm": _qm_lane(G)}}


# ── 時間軸（stockviz.tlDraw；設定在 JS 的 cfQ） ──────────────────────────────────

def tl_shell(mk: str) -> str:
    """時間軸外框（收在「看時間軸」裡）。只畫配置裡的策略：觀察中策略的訊號不放配置頁（2026-10-24 使用者決定）。"""
    return (f'<div class="tlx cftl"><div class="tlhd"><div class="seg tlrg"><a data-tlr=all class=on>全部</a><a data-tlr=m1>接下來 5 週</a></div>'
            '<span class=tllg><span><span class="tlk b">▲</span>買進</span><span><span class="tlk s">▼</span>賣出</span>'
            '<span><span class="tlk w">◆</span>換股</span><span><span class="tlk a">●</span>調整</span>'
            '<span class=tlsw><i class=tlsh></i>持有中（顏色＝目前漲跌）</span><span class=tlsw><i class=tlsb></i>排定的買進</span></span></div>'
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
            nm = (f'<a href="{_e(r["href"])}">{_e(r["name"])}</a>' if r.get("href") else
                  f'<a{_go_attrs(r.get("go"))}>{_e(r["name"])}</a>' if (r.get("go") or {}).get("go") else _e(r["name"]))
            if r.get("src"):
                nm += f' <a class="bsrc" href="{_e(r["src"])}" target="_blank" rel="noopener">來源</a>'

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
.cfwb{position:relative;display:inline-block;width:64px;height:8px;border-radius:4px;background:var(--line)}
.cfwb>i{position:absolute;left:0;top:0;bottom:0;border-radius:4px;background:var(--bar2)}.cfwr.on .cfwb>i{background:var(--warn)}
.cfwb>u{position:absolute;top:-3px;bottom:-3px;width:2px;background:var(--ink2);margin-left:-1px}
.cfdue{font-size:13.5px;margin:6px 0;padding:7px 10px;border-radius:8px;background:var(--gbbg)}.cfdue b{color:var(--warn)}.cfdue.ok b{color:var(--acc)}
.cfperf{font-size:13px;color:var(--ink2);margin:4px 0}.cfperf b{color:var(--ink)}.cfq{font-size:12.5px;color:var(--mut)}
.cfdet{margin:6px 0 10px}.cfdet>summary{cursor:pointer;font-size:13px;color:var(--acc);width:max-content}
.pln.cfpln{border:0;border-radius:0;padding:0;background:none;margin:8px 0 0}   /* 細節＝corepage 的圖表與表格（樣式 corepage.CSS，配置頁一起載入）；外框用時程與水位卡自己的 */
.cfht{width:100%;border-collapse:collapse;font-size:13.5px}
.cfht th{text-align:left;font-weight:600;color:var(--ink2);font-size:12.5px;padding:5px 8px;border-bottom:1px solid var(--line2)}
.cfht td{padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left;white-space:normal}
.cfht td:first-child{position:static;background:none}.cfht th:first-child{position:static}
.cfht th:nth-child(2){text-align:right}
.cfht td.w{text-align:right;font-weight:700;white-space:nowrap;font-variant-numeric:tabular-nums}
.cfht td.st{color:var(--ink2);font-size:12.5px}
.cfht .cd{color:var(--mut);font-size:12px}.cfht .cfin{font-size:12px;color:var(--mut);line-height:1.45;margin-top:1px}
.cfh3{font-size:14.5px;color:var(--ink);margin:16px 0 6px;display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 10px}.cfh3 .sub{font-size:12.5px;font-weight:400;color:var(--mut)}
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
.btbl td.bn a.bsrc{font-size:11.5px;font-weight:400;color:var(--mut);text-decoration:underline}
.btbl td.bm{white-space:nowrap;color:var(--ink2)}.btbl td.bh{color:var(--ink2);min-width:220px}
.btbl td.bp,.btbl td.bd{white-space:nowrap;font-variant-numeric:tabular-nums}
.btbl .bref{color:var(--mut);font-size:12px}.btbl .bsub{display:block;font-size:11.5px;color:var(--mut)}
.btbl td.bto{color:var(--ink2);font-size:12.5px}.btbl td.bw{color:var(--ink2);font-size:12.5px}
.btbl tr.bnone td{color:var(--mut);font-size:12.5px}
.btbl tr.bx td a{color:var(--acc);cursor:pointer;font-size:12.5px}
.btbl tr.bhide{display:none}
.cfmo{background:var(--card2);border-radius:14px;padding:12px 14px;margin:0 0 6px}   /* 配置頁 v2（docs/lab_cfg_v2_plan.md）：分類色 --cfc1～8 在 page.py 的 :root（深色另一組） */
.cfbig{display:flex;flex-wrap:wrap;gap:4px 24px;align-items:baseline}.cfbig span{font-size:13px;color:var(--ink2)}.cfbig b{font-size:28px;line-height:1.2;margin-right:5px;color:var(--ink)}
.cfbar{display:flex;gap:2px;height:20px;margin:10px 0 8px}.cfbar i{display:block;height:100%;min-width:3px}
.cfbar i:first-child{border-radius:6px 0 0 6px}.cfbar i:last-child{border-radius:0 6px 6px 0}.cfbar i:only-child{border-radius:6px}
.cfmo .c1{background:var(--cfc1)}.cfmo .c2{background:var(--cfc2)}.cfmo .c3{background:var(--cfc3)}.cfmo .c4{background:var(--cfc4)}
.cfmo .c5{background:var(--cfc5)}.cfmo .c6{background:var(--cfc6)}.cfmo .c7{background:var(--cfc7)}.cfmo .c8{background:var(--cfc8)}
.cfmo .cx{background:repeating-linear-gradient(135deg,var(--line2) 0 2px,transparent 2px 7px);box-shadow:inset 0 0 0 1px var(--line2)}
.cflg{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:2px 22px;font-size:13.5px}
.cflg li{display:flex;align-items:center;gap:7px;min-width:0}.cflg u{flex:none;width:11px;height:11px;border-radius:3px}
.cflg em{margin-left:auto;font-style:normal;font-weight:700;font-variant-numeric:tabular-nums}
.cfwhy{font-size:13.5px;color:var(--ink2);margin:10px 0 0;line-height:1.65}.cfwhy b{color:var(--ink)}
.cfgr{border:1px solid var(--line);border-radius:12px;overflow:hidden;margin:0 0 12px}
.cfgh{display:block;background:var(--card2);padding:8px 12px}
.cfgt{display:flex;align-items:baseline;gap:8px}.cfgt b{font-size:15px}.cfgt .cd{color:var(--mut);font-size:12.5px}
.cfgt em{margin-left:auto;font-style:normal;font-weight:700;font-variant-numeric:tabular-nums}
.cfgs{display:block;font-size:12.5px;color:var(--ink2);line-height:1.55;margin-top:1px}
.cfrow{display:block;padding:9px 12px;border-top:1px solid var(--line);color:inherit;text-decoration:none;cursor:pointer}
.cfrow:hover{background:var(--hover)}
.cfra{display:flex;align-items:baseline;gap:6px}.cfra b{font-size:15px;color:var(--ink)}.cfra .cd{color:var(--mut);font-size:12.5px}
.cfra .go{color:var(--acc);font-size:14px}.cfra .w{margin-left:auto;font-weight:700;font-variant-numeric:tabular-nums;white-space:nowrap}
.cfra .r{min-width:4.4em;text-align:right;font-weight:700;font-variant-numeric:tabular-nums}.cfra .r.up{color:var(--gain)}.cfra .r.dn{color:var(--loss)}
.cftag{font-size:11px;font-weight:700;color:var(--warn);background:var(--gbbg);border-radius:4px;padding:0 5px;white-space:nowrap}
.cfri{display:block;font-size:12.5px;color:var(--ink2);margin-top:1px}.cfrb{display:block;font-size:12.5px;color:var(--ink2);margin-top:1px}.cfrc{display:block;font-size:12.5px;color:var(--mut);line-height:1.5}
.cfempty{padding:8px 12px;border-top:1px solid var(--line);font-size:13px;color:var(--ink2)}
.cfcash{display:flex;align-items:baseline;gap:8px;padding:10px 12px;border:1px dashed var(--line2);border-radius:12px;font-size:14px}
.cfcash span{font-size:12.5px;color:var(--mut)}.cfcash em{margin-left:auto;font-style:normal;font-weight:700;font-variant-numeric:tabular-nums}
.cfsch{border-left:2px solid var(--line);margin:4px 0 0 7px;padding-left:14px}
.cfev{position:relative;padding:5px 0 7px}.cfev::before{content:"";position:absolute;left:-21px;top:11px;width:10px;height:10px;border-radius:50%;background:var(--bg);border:2px solid var(--acc)}
.cfevd b{font-size:14.5px}.cfevd span{font-size:12.5px;color:var(--mut);margin-left:3px}
.cfevx{font-size:13.5px;color:var(--ink2);margin-top:3px;line-height:1.6}.cfevx a{color:var(--acc);cursor:pointer}
.cfevs{display:block;font-size:12px;color:var(--mut)}
.cftg{display:inline-block;font-size:11.5px;font-weight:700;border-radius:4px;padding:0 6px;margin-right:6px}
.cftg.tb{background:var(--gainbg);color:var(--gain)}.cftg.ts{background:var(--lossbg);color:var(--loss)}.cftg.tl,.cftg.ta{background:var(--inset);color:var(--ink2)}
.cftlw{margin:8px 0 0}.cftlw>summary{cursor:pointer;color:var(--acc);font-size:13.5px;width:max-content}
.cfws .cfwr{display:grid;grid-template-columns:7.5em minmax(0,1fr);gap:2px 12px;align-items:center;padding:7px 0;border-top:1px solid var(--line);font-size:13.5px}
.cfws .cfwr:first-child{border-top:0}.cfws .cfwr.on b{color:var(--warn)}.cfws .cfwb{display:block;width:auto}
.cfwv{grid-column:2;font-size:12.5px;color:var(--ink2)}.cfwv span{color:var(--mut)}.cfwv em{font-style:normal;font-weight:700;color:var(--warn);margin-left:6px}
.cfrule2{font-size:13px;color:var(--ink2);background:var(--card2);border-radius:10px;padding:8px 12px;margin-top:8px}
.cfmo,.cfgr,.cfcash,.cfsch,.cfws,.cfrule2,.cfht.cfql{max-width:880px}   /* 電腦版不要拉到整頁寬：名字和比重離太遠 */
.cftoolr{display:flex;flex-wrap:wrap;align-items:center;gap:6px 14px;margin:0 0 12px}.cftool{display:flex;width:max-content;max-width:100%}.cfasof{color:var(--mut);font-size:12.5px;min-width:0}
@media (max-width:640px){
 .cfht,.cfht tbody{display:block}.cfht tr{display:grid;grid-template-columns:minmax(0,1fr) auto;padding:5px 0;border-bottom:1px solid var(--line)}
 .cfht th{display:none}.cfht td{border:0;padding:0 6px}.cfht td.st{grid-column:1/-1;font-size:12.5px}
 .btbl{font-size:12.5px}.btbl th.bh,.btbl td.bh,.btbl th.bd,.btbl td.bd,.btbl .bsub{display:none}
 .btbl td,.btbl th{padding:6px 5px}.btbl td:first-child{min-width:0;width:34%}.btbl td.bm{white-space:nowrap}
 .btbl .bref{display:block}.btbl td.bto{min-width:0}}
"""

JS = r"""
/* ---------- 配置（cfgpage.py；docs/lab_ia_v5_plan.md 第 18 節）：台股｜美股｜策略｜個股（工具）。
   台股、美股（配置頁 v2）：現在的錢、持股、接下來、警訊、過去照做（Python 組好的 HTML）＋時間軸（stockviz.tlDraw，設定 cfQ）；
   策略：全部策略一張表。 ---------- */
const CFG=D.cfg||{};
function cfFoot(){return `<footer class=cffoot><a href="x9r.html">研究紀錄</a></footer>`;}
function cfMk(mk){const C=CFG[mk]||{};let h='';
  if(C.err||!C.card)h+=`<div class=st>配置資料還沒算出來${C.err?`：${esc(C.err)}`:''}。</div>`;
  else h+=`<section class="sec cfsec" id="cf-${mk}" data-nav="現在的錢">${C.card}</section>`+   /* 配置頁 v2（docs/lab_cfg_v2_plan.md） */
    `<section class=sec id="cf-${mk}-h" data-nav="持股">${C.hold}</section><section class=sec id="cf-${mk}-s" data-nav="接下來">${C.sched}</section>`+
    `<section class=sec id="cf-${mk}-w" data-nav="警訊">${C.warn||''}</section><section class=sec id="cf-${mk}-p" data-nav="過去照做">${C.perf||''}</section>`+(C.boom||'')+(C.line||'');
  $('#main').innerHTML=h+cfFoot();
  const w=$('#main .cftl');if(w)w.addEventListener('click',ev=>{const a=ev.target.closest&&ev.target.closest('.vztip [data-go]');if(!a)return;
    ev.preventDefault();const tp=a.closest('.vztip');tp.classList.remove('pin');tp.hidden=true;go(a.dataset.go,a.dataset.at);});
  const tw=$('#main .cftlw');if(tw)tw.addEventListener('toggle',()=>{if(tw.open)cfDraw(mk);});   /* 時間軸收在「看時間軸」裡：打開才畫（收起時寬度是 0） */
  if(!tw)cfDraw(mk);}
function vCfgTw(){cfMk('tw');}
function vCfgUs(){cfMk('us');}
/* 時間軸的列：配置裡的策略（觀察中策略的訊號不放配置頁，2026-10-24 使用者決定） */
function cfLanes(mk){const C=CFG[mk]||{},T=C.tl||{},L=[];
  const oc=k=>(OPP.cards||[]).find(c=>c.k===k);
  if(T.boom)L.push(Object.assign({},T.boom,{_src:'boom'}));
  (T.use||[]).forEach(k=>{const c=oc(k);if(c)L.push(Object.assign({},c,{_src:'stk'}));});
  if(T.qm)L.push(Object.assign({},T.qm,{_src:'qm'}));
  L.forEach((c,i)=>{c.rank=i+1;});return L;}
function cfTip(x,pin){const c=x.c,e=x.e;let h='';
  if(c._src==='boom'){const it=e.items||[];
    if(x.k==='held')h=`<b>${esc(c.name)}・${md(e.ent)} 買的 ${it.length} 檔</b><ul>${it.map(i=>`<li>${esc(i.n)} <span class=vzs>買進 ${fp(i.entry)}，現在 ${fp(i.now)}</span> <span class=${(i.now_r||0)>=0?'up':'dn'}>${pctT(i.now_r)}</span></li>`).join('')}</ul><div class=vzs>${mdw(e.d)} 開盤賣（抱滿${hz(c.hold)}）</div>`;
    else if(x.k==='buy')h=`<b>${mdw(e.d)} 開盤買進・${esc(c.name)}</b><div>${it.map(i=>esc(i.n)).join('、')}</div><div class=vzs>${esc(e.sell||'')}</div>`;
    else if(x.k==='next')h=`<b>${esc(c.name)}</b><div>名單 ${mdw(e.fix)} 收盤產生，有空位就 ${mdw(e.d)} 開盤買</div>`;
    return h+(pin?`<a class=vzgo data-go="tw" data-at="cf-tw-sx">看新飆股</a>`:'');}
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
    lb:x=>TLO.lb(x),nm:c=>`${c.rank}. ${STN[c.k]||c.name}`,sub:c=>'持有'+hz(c.hold),
    avg:e=>e.r!=null?e.r:tlAvg(e),tipf:(x,pin)=>cfTip(x,pin)};}
function cfDraw(mk){const b=$('#cftl-'+mk),d=b&&b.closest('details');if(b&&(!d||d.open))tlDraw(cfQ(mk));}
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
