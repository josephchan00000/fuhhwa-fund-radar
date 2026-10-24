"""籌碼雷達後台自我驗證紀錄（版面 v4，2026-10-15；docs/lab_ia_v4_plan.md 第 5 節）。

每次重建頁面都算一次今天的紀錄與事件（後台頁顯示）；只有 CI（GITHUB_ACTIONS）才寫回 data/lab/val_log.json，
容器本機重建只讀不寫（本機檔不混進 commit）。檔案以資料日為鍵、一天一行，同一天後面的班次覆蓋；保留 KEEP 天。

每條策略記：評級、推薦順序、前瞻（規則起算後已出場）筆數、平均報酬、同期大盤、平均贏同一批股票多少、
持有中檔數與平均報酬、待買進檔數。

事件（事前寫定；改規則＝改這裡＋改文件）：
  grade  評級變動：和前一個資料日的評級不同。
  full   前瞻滿額：已出場筆數第一次達到 A 級門檻（逐筆 10、事件型 2）。
  lag    前瞻落後：已出場 ≥ 門檻一半，且平均沒贏同一批股票（狀態第一次出現時記）。
  deep   持有中虧損超過歷史最差：逐檔計的策略看每一檔、其餘看同一批的平均，跌得比過去最差的一次還多（第一次出現時記）。
  miss   該出名單沒出：月營收、財報驚喜的形成日已過一個交易日以上，那一期沒有產生名單（第一次出現時記）。
  stale  資料過期：最新資料日之後已有 2 個以上交易日收盤卻沒有資料（每天都記，直到恢復）。
  dev    表現偏離回測（策略健檢，docs/lab_selfopt_plan.md 第 3 節）：燈號第一次變成「明顯低於回測」，或持有中的部位
         （逐檔策略每檔、其餘每批）第一次低於回測同一持有天數的第 5 百分位。
  shok   影子版本達標（第 6 節）：前瞻滿門檻、贏過現行、回落沒有變差、每週重跑仍是證據強——你回「好」才換。
  sout   影子版本淘汰（第 6 節）：前瞻滿門檻卻沒有贏、回落變差、每週重跑不再是證據強，或現行規則改版。
  sxl    飆股前瞻記錄（sxlivespec；docs/lab_core70_plan.md 第 14 節）：第一次到半年、一年的檢討日；今年的規則還沒找、卻已經有訊號日。
  uqm    美股三成（corespec VER 3、ussxspec QM；docs/lab_us_sleeve_plan.md 第 13.3～13.4 節；研究檔判定換了才有）：
         每週紀錄停在比該有的還早的一週（美股週五收盤＋36 小時以後算該有）、第一次滿 63／126／252 個交易日的檢討、
         每週重跑和之前的紀錄不一樣（多一筆差異時）。另外推播多一行：美股下一個交易日開盤要賣、要買的股票（每天的 50 日線檢查＋每週紀錄）。
台股機動的新飆股（corespec VER 4；飆股前瞻記錄的 R60 那本帳）：推播多一行，下一個交易日開盤要賣、要買的股票（不是事件）。
"""
from __future__ import annotations

import json
import os
import statistics
from datetime import date, datetime, timedelta

from . import store

FP = "val_log.json"
KEEP = 250                 # 保留最近幾個資料日
STALE_TD = 2               # 落後幾個交易日算過期
CLOSE_HM = (14, 30)        # 這個時間之後，今天算已收盤
EVENT = {"s3"}             # 事件型（以「次」計、A 級門檻 2 次）；財報驚喜另由 src＝p3 判斷
TYPES = {"grade": "評級變動", "full": "前瞻滿額", "lag": "前瞻落後", "deep": "虧損超過歷史最差",
         "miss": "該出名單沒出", "stale": "資料過期", "dev": "表現偏離回測", "shok": "影子版本達標", "sout": "影子版本淘汰",
         "sxl": "飆股觀察", "uqm": "美股三成"}
LOW_LIGHT = "明顯低於回測"


def _md(d: str | None) -> str:
    return f"{int(d[5:7])}/{int(d[8:10])}" if d and len(d) >= 10 else (d or "—")


def _wd(d: str) -> str:
    return "一二三四五六日"[date.fromisoformat(d).weekday()]


def _pct(x, d: int = 1) -> str:
    if x is None:
        return "—"
    return f"{'+' if x > 0 else '−' if x < 0 else ''}{abs(x):.{d}f}%"


def _mean(xs: list) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(statistics.mean(xs), 2) if xs else None


def _event(k: str, live: dict) -> bool:
    return k in EVENT or (live.get(k) or {}).get("src") == "p3"


# ── 今天的紀錄 ──────────────────────────────────────────────────────────

def snapshot(adv: dict) -> dict:
    """→ {鍵: 當天狀態}。只看有評級的策略（含 C 級，評級變動也要記）；高股息換股不是選股策略，不記。"""
    live = (adv.get("v3") or {}).get("live") or {}
    old = {g["k"]: g for g in adv.get("grades") or []}
    cards = {c["k"]: c for c in (adv.get("opp") or {}).get("cards") or []}
    bk = {b["k"]: b for b in adv.get("book") or []}
    last = adv.get("last")
    out = {}
    for g in adv.get("grades3") or []:
        k = g["k"]
        if k == "hd":
            continue
        ev = _event(k, live)
        f = g.get("fwd") or {}
        L = live.get(k)
        if L:
            us = (L.get("fwd") or {}).get("units") or []
            fr, fmk = _mean([u.get("r") for u in us]), _mean([u.get("mk") for u in us])
        else:
            of = (old.get(k) or {}).get("fwd") or {}
            fr = of.get("avg")
            fmk = None if of.get("avg") is None or of.get("x") is None else round(of["avg"] - of["x"], 2)
        c = cards.get(k) or {}
        held = [i for e in c.get("held") or [] for i in e.get("items") or []]
        lo = ((bk.get(k) or {}).get("exp") or {}).get("lo")
        unit = (bk.get(k) or {}).get("unit") or "次"
        deep = []
        if lo is not None:
            if unit == "檔":
                deep = [[i["n"], i["now_r"]] for i in held if i.get("now_r") is not None and i["now_r"] < lo]
            else:
                for e in c.get("held") or []:
                    a = _mean([i.get("now_r") for i in e.get("items") or []])
                    if a is not None and a < lo:
                        deep.append([f"{_md(e.get('ent'))} 買進的 {len(e['items'])} 檔平均", a])
        due = (L or {}).get("due") or {}
        out[k] = {"name": g.get("name") or (bk.get(k) or {}).get("name") or k, "g": g.get("grade"), "r": g.get("rank"),
                  "u": unit, "fn": f.get("n") or 0, "need": 2 if ev else 10, "fxe": f.get("xe"), "fr": fr, "fmk": fmk,
                  "hn": len(held), "hr": _mean([i.get("now_r") for i in held]),
                  "bn": sum(len(e.get("items") or []) for e in c.get("buy") or []), "lo": lo, "deep": deep,
                  "miss": due["d"] if due.get("d") and not due.get("ok") and due["d"] < (last or "") else None,
                  "why": (g.get("why") or [None])[0], "since": g.get("since")}
    return out


def merge_health(st: dict, hl: dict | None, opt: dict | None) -> dict:
    """把策略健檢（燈號、低於第 5 百分位的部位）與影子版本狀態併進當天每條策略的紀錄（事件比對用）。"""
    hl = hl if isinstance(hl, dict) else {}
    items = (((opt or {}).get("shadow") or {}).get("items") or []) if isinstance(opt, dict) else []
    for k, s in st.items():
        h = hl.get(k)
        if isinstance(h, dict):
            s["hl"] = h.get("light")
            s["hla"], s["hln"] = h.get("avg"), h.get("n")
            s["low"] = [[x["n"], x.get("d"), x.get("x")] for x in h.get("hold") or []
                        if x.get("pct") is not None and x["n"] in (h.get("low") or [])]
        sh = [[x["c"], x["st"], x.get("what"), x.get("n"), x.get("mean"), x.get("why")] for x in items if x.get("k") == k]
        if sh:
            s["sh"] = sh
    return st


def lag_days(last: str | None, now: datetime) -> int | None:
    """最新資料日之後、到最新收盤日（今天 14:30 後算今天）為止，有幾個交易日。"""
    if not last:
        return None
    from .. import twholidays
    years = twholidays.load()
    end = now.date() if (now.hour, now.minute) >= CLOSE_HM else now.date() - timedelta(days=1)
    d, n = date.fromisoformat(last), 0
    while d < end:
        d += timedelta(days=1)
        if d.weekday() < 5 and not twholidays.is_closed(d, years):
            n += 1
    return n


def todo(adv: dict) -> dict:
    """下一個交易日要做的事（行事曆上那一天的買賣）：06:35 推播用。"""
    d = adv.get("nxt")
    its = []
    for e in adv.get("cal") or []:
        if e.get("d") != d:
            continue
        nm = [i.get("n") for i in e.get("items") or [] if i.get("n")]
        its.append({"at": e.get("at"), "act": e.get("act"), "k": e.get("k"), "s": e.get("sname"), "n": nm,
                    "fix": e.get("fix") if e.get("pending") else None, "tent": bool(e.get("tent"))})
    return {"d": d, "items": its}


def events(cur: dict, prev: dict | None, last: str | None, lag: int | None) -> list[dict]:
    """事件規則見檔頭。prev＝前一個資料日的 st（沒有就當空的：當天的狀態都算新出現；評級變動要有前一天才記）。"""
    P = prev or {}
    out = []
    for k, s in cur.items():
        p = P.get(k) or {}
        nm, u = s["name"], s["u"]
        if p.get("g") and s.get("g") and p["g"] != s["g"]:
            out.append({"k": k, "ty": "grade", "txt": f"{nm}：評級 {p['g']} → {s['g']}" + (f"（{s['why']}）" if s.get("why") else "")})
        if s["fn"] >= s["need"] > (p.get("fn") or 0):
            vs = "" if s.get("fxe") is None else f"，比同一批股票{'高' if s['fxe'] >= 0 else '低'} {abs(s['fxe']):.2f}%"
            out.append({"k": k, "ty": "full", "txt": f"{nm}：規則起算後已出場 {s['fn']} {u}，達到 A 級門檻；"
                        f"平均每{u}報酬 {_pct(s['fr'])}（同期大盤 {_pct(s['fmk'])}）{vs}"})
        lag_now = s["fn"] * 2 >= s["need"] and s["fn"] > 0 and s.get("fxe") is not None and s["fxe"] < 0
        lag_pre = (p.get("fn") or 0) * 2 >= p.get("need", s["need"]) and (p.get("fn") or 0) > 0 and \
            p.get("fxe") is not None and p["fxe"] < 0
        if lag_now and not lag_pre:
            out.append({"k": k, "ty": "lag", "txt": f"{nm}：規則起算後已出場 {s['fn']} {u}，平均比同一批股票低 {abs(s['fxe']):.2f}%"
                        f"（平均報酬 {_pct(s['fr'])}、同期大盤 {_pct(s['fmk'])}）"})
        seen = {x[0] for x in p.get("deep") or []}
        new = [x for x in s.get("deep") or [] if x[0] not in seen]
        if new:
            out.append({"k": k, "ty": "deep", "txt": f"{nm}：持有中 " + "、".join(f"{x[0]} {_pct(x[1])}" for x in new) +
                        f"，跌得比過去最差的一{u}（{_pct(s['lo'])}）還多"})
        if s.get("miss") and s["miss"] != p.get("miss"):
            out.append({"k": k, "ty": "miss", "txt": f"{nm}：{_md(s['miss'])} 應產生名單，到 {_md(last)} 仍沒有（營收或財報資料可能沒進來）"})
        if s.get("hl") == LOW_LIGHT and p.get("hl") != LOW_LIGHT:
            out.append({"k": k, "ty": "dev", "txt": f"{nm}：規則起算後 {s.get('hln')} {u}平均 {_pct(s.get('hla'))}，"
                        "低於回測同樣筆數抽樣的 95%（表現偏離回測）"})
        seen_low = {x[0] for x in p.get("low") or []}
        new_low = [x for x in s.get("low") or [] if x[0] not in seen_low]
        if new_low:
            out.append({"k": k, "ty": "dev", "txt": f"{nm}：持有中 " + "、".join(f"{x[0]} 第 {x[1]} 天 {_pct(x[2])}" for x in new_low)
                        + "，低於回測同一持有天數的第 5 百分位"})
        pst = {x[0]: x[1] for x in p.get("sh") or []}
        for c, stt, what, n, mean, why in s.get("sh") or []:
            if stt == "達標" and pst.get(c) != "達標":
                out.append({"k": k, "ty": "shok", "txt": f"{nm}：影子版本「{what}」達標（前瞻 {n} {u}，"
                            f"平均每{u}比現行多 {_pct(mean, 2)}），回「好」才換"})
            if stt == "淘汰" and pst.get(c) != "淘汰":
                out.append({"k": k, "ty": "sout", "txt": f"{nm}：影子版本「{what}」淘汰" + (f"（{why}）" if why else "")})
    if lag is not None and lag >= STALE_TD:
        out.append({"k": None, "ty": "stale", "txt": f"資料過期：最新資料 {_md(last)}，之後已有 {lag} 個交易日收盤沒有資料"})
    return out


def sx_state(L: dict | None) -> dict | None:
    """飆股前瞻記錄的摘要（sxlive.LAST）→ 存進每天紀錄的部分（只存發提醒要比對的狀態，不存成績）。"""
    if not L or not L.get("d"):
        return None
    return {"due": L.get("due"), "miss": L.get("miss")}


def sx_events(L: dict | None, prev: dict | None) -> list[dict]:
    """第一次到檢討日（半年／一年）、今年的規則還沒找卻已經有訊號日 → 推播第二行（數字取當天的摘要）。"""
    cur, P = sx_state(L), prev or {}
    if not cur:
        return []
    out = []
    if cur["due"] and cur["due"] != P.get("due"):
        v = L.get("v") or {}
        wan = lambda x: "—" if x is None else f"{100 + x:.1f} 萬"  # noqa: E731
        name = {"half": "滿半年", "year": "滿一年"}.get(cur["due"], cur["due"])
        out.append({"k": None, "ty": "sxl", "txt": f"飆股觀察{name}（{_md(L.get('start'))} 起照做 100 萬）：新飆股 {wan(v.get('R60'))}、"
                    f"舊目標 {wan(v.get('A'))}、頁面飆股 {wan(v.get('R1'))}、大盤 {wan(v.get('TR'))}；回覆「飆股觀察」看細節"
                    + ("，一年的提議照事前寫好的門檻" if cur["due"] == "year" else "")})
    if cur["miss"] and cur["miss"] != P.get("miss"):
        out.append({"k": None, "ty": "sxl", "txt": f"飆股觀察：{cur['miss']} 年的規則還沒找（長歷史股價要先補到去年底），"
                    "這幾週的新飆股、舊目標先沒記"})
    return out


def _us_week_end(now: datetime) -> str | None:
    """現在應該已經記好的那一週（美股週五收盤＋36 小時，＝台北週六中午以後；休市就是那一週最後一個交易日）。"""
    from . import ussxqm as QM
    try:
        d = (now - timedelta(hours=36)).date()
        for _ in range(14):
            x = d.isoformat()
            if QM.next_day((d - timedelta(days=1)).isoformat()) == x and QM.week_done(x):
                return x
            d -= timedelta(days=1)
    except Exception:                                     # noqa: BLE001 —— 休市表讀不到：不判
        return None
    return None


def uqm_state(now: datetime) -> dict | None:
    """美股三成（ussxqm）：研究檔判定換了才有。→ 存進每天紀錄的部分（要做的買賣、已到的檢討、停在哪一週、差異筆數）。"""
    from . import corepage as CPG
    from . import ussxqm as QM
    R = QM.load()
    if not R or not any(CPG.qm_on(mk, {"R": R}) for mk in CPG.US):
        return None
    L, W = QM.load_live(), QM.load_watch() or {}
    n = L.get("now") or {}
    if not n.get("d"):
        return None
    if W.get("base") != n["d"]:                           # 對不上最新一週紀錄的檢查不採用
        W = {}
    last = W.get("d") or n["d"]
    td = [[x["on"], "賣", x["c"]] for x in W.get("sell") or [] if x.get("on") and x["on"] > last]
    td += [[n["next"], "賣", c] for c in n.get("sell") or []] + [[n["next"], "買", c] for c in n.get("buy") or []]
    rv = {str(x["k"]): {"d": x["d"], "ex": round(x["ex"], 4), "pct": None if x.get("pct") is None else round(x["pct"], 3),
                        "low": bool(x.get("low"))} for x in QM.review_now(L, R) if x.get("d")}
    exp = _us_week_end(now)
    return {"d": n["d"], "td": sorted(td), "rv": rv, "stale": n["d"] if exp and n["d"] < exp else None, "exp": exp,
            "nd": len(L.get("diff") or [])}


def uqm_events(cur: dict | None, prev: dict | None) -> list[dict]:
    """停在舊的一週（同一個停住的日子只記一次）、第一次滿檢討日、多一筆重跑差異。"""
    if not cur:
        return []
    P, out = prev or {}, []
    if cur.get("stale") and cur["stale"] != P.get("stale"):
        out.append({"k": None, "ty": "uqm", "txt": f"美股三成的每週紀錄停在 {_md(cur['stale'])}（應該要有 {_md(cur['exp'])} 那一週），"
                    "這一週的名單和買賣沒有更新"})
    for k, x in sorted((cur.get("rv") or {}).items(), key=lambda kv: int(kv[0])):
        if k in (P.get("rv") or {}):
            continue
        g = (2.718281828459045 ** x["ex"] - 1) * 100
        out.append({"k": None, "ty": "uqm", "txt": f"美股三成滿 {k} 個交易日（{_md(x['d'])}）：三成比 S&P 500 含息{'多' if g >= 0 else '少'}賺 {abs(g):.1f}%"
                    + (f"，在回測同樣長度的期間裡排在最差的 {x['pct'] * 100:.0f}%" if x.get("pct") is not None else "")
                    + ("，比回測差；要不要換回指數由你決定" if x.get("low") else "")})
    if (cur.get("nd") or 0) > (P.get("nd") or 0):
        out.append({"k": None, "ty": "uqm", "txt": f"美股三成：每週重跑和之前的紀錄不一樣（第 {cur['nd']} 筆），要查原因"})
    return out


def boom_state(P: dict | None, N: dict | None = None) -> dict | None:
    """台股機動的新飆股（corespec VER 4）：P＝那本帳現在的狀態（sxlive.LAST["plan"]），N＝配置頁台股的警訊讀數
    （機動放現金中就先不買）。→ 存進每天紀錄的部分：下一個交易日開盤要賣、要買的股票。"""
    if not P or not P.get("d") or not P.get("next"):
        return None
    nx = P["next"]
    td = [[nx, "賣", h.get("n") or h["c"]] for h in P.get("hold") or [] if h.get("sell")]
    td += [[nx, "買", x.get("n") or x["c"]] for x in P.get("buy") or [] if x.get("fill")]
    return {"d": P["d"], "td": td, "cash": bool(N and N.get("next") is not None and N["next"] < 0.99)}


def boom_line(cur: dict | None) -> str | None:
    """推播多一行：新飆股下一個交易日開盤要賣、要買的股票。沒有要做的就不加。"""
    by: dict[str, dict[str, list]] = {}
    for d, act, c in (cur or {}).get("td") or []:
        by.setdefault(d, {}).setdefault(act, []).append(c)
    if not by:
        return None
    parts = [f"{_md(d)}（{_wd(d)}）開盤" + "、".join(f"{a} {'、'.join(by[d][a])}" for a in ("賣", "買") if by[d].get(a))
             for d in sorted(by)]
    return "新飆股：" + "；".join(parts) + ("（機動放現金中，買的先不買）" if cur.get("cash") and any("買" in v for v in by.values()) else "") + "。"


def uqm_line(cur: dict | None) -> str | None:
    """推播多一行：美股下一個交易日開盤要賣、要買的股票。沒有要做的就不加。"""
    by: dict[str, dict[str, list]] = {}
    for d, act, c in (cur or {}).get("td") or []:
        by.setdefault(d, {}).setdefault(act, []).append(c)
    if not by:
        return None
    parts = [f"{_md(d)}（{_wd(d)}）開盤" + "、".join(f"{a} {'、'.join(by[d][a])}" for a in ("賣", "買") if by[d].get(a))
             for d in sorted(by)]
    return "美股三成：" + "；".join(parts) + "。"


def push_lines(rec: dict) -> list[str]:
    """06:35 推播多帶的兩行：那一天開盤（與收盤）要做的事；有驗證事件才加第二行。"""
    T = rec.get("todo") or {}
    d, its = T.get("d"), T.get("items") or []
    if not d:
        a = "下一個交易日不確定（休市表讀不到）。"
    elif not its:
        a = f"{_md(d)}（{_wd(d)}）沒有排定的買賣。"
    else:
        parts = []
        for at in ("開盤", "收盤"):
            xs = [i for i in its if i.get("at") == at]
            if xs:
                parts.append(f"{at}" + "；".join(
                    f"{i['act']} {i['s']} " + ("、".join(i["n"][:5]) + (f" 等 {len(i['n'])} 檔" if len(i["n"]) > 5 else "")
                                               if i["n"] else f"（名單 {_md(i['fix'])} 收盤產生）") +
                    ("（試算名單）" if i.get("tent") else "") for i in xs))
        a = f"{_md(d)}（{_wd(d)}）" + "；".join(parts) + "。"
    out = [a]
    b = boom_line(rec.get("boom"))
    if b:
        out.append(b)
    u = uqm_line(rec.get("uqm"))
    if u:
        out.append(u)
    ev = rec.get("ev") or []
    if ev:
        out.append("策略驗證：" + "；".join(e["txt"] for e in ev) + "。")
    return out


# ── 讀寫 ────────────────────────────────────────────────────────────────

def read() -> dict:
    doc = store.read_json(FP, {}) or {}
    days = doc.get("days") if isinstance(doc, dict) else None
    return {"v": 1, "days": days if isinstance(days, dict) else {}}


def _dump(log: dict) -> str:
    """一天一行（決定性）：每天只改最後一行，git diff 小。"""
    days = log.get("days") or {}
    rows = [json.dumps(k) + ":" + json.dumps(days[k], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            for k in sorted(days)]
    return '{"v":1,"days":{\n' + ",\n".join(rows) + "\n}}\n"


def write(log: dict) -> bool:
    p = store.LAB / FP
    txt = _dump(log)
    if p.exists() and p.read_text(encoding="utf-8") == txt:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt, encoding="utf-8")
    return True


def update(data: dict, write_file: bool | None = None, now: datetime | None = None) -> dict:
    """算今天的紀錄與事件；write_file（預設＝在 CI 裡）時寫回檔案。→ 頁面「後台」用的資料。"""
    from .. import clock
    adv = data.get("adv") or {}
    if adv.get("err") or not adv.get("last"):
        return {"err": adv.get("err") or "沒有評級資料"}
    if write_file is None:
        write_file = os.environ.get("GITHUB_ACTIONS") == "true"
    now = now or clock.now_tw()
    last = adv["last"]
    log = read()
    days = log["days"]
    prev_d = max((d for d in days if d < last), default=None)
    prev = (days.get(prev_d) or {}).get("st") if prev_d else None
    st = merge_health(snapshot(adv), data.get("hl"), data.get("opt"))
    try:
        lag = lag_days(last, now)
    except Exception:                                     # noqa: BLE001 —— 休市表讀不到：不判過期
        lag = None
    rec = {"st": st, "lag": lag, "todo": todo(adv)}
    rec["ev"] = events(st, prev, last, lag)
    try:                                                  # 飆股前瞻記錄（不上頁面；只有提醒）
        from . import sxlive
        sx = sx_state(sxlive.LAST)
        if sx:
            rec["sx"] = sx
            rec["ev"] += sx_events(sxlive.LAST, (days.get(prev_d) or {}).get("sx") if prev_d else None)
        bm = boom_state(sxlive.LAST.get("plan"), ((data.get("cfg") or {}).get("now") or {}).get("tw"))
        if bm:
            rec["boom"] = bm
    except Exception:                                     # noqa: BLE001 —— 摘要讀不到：不發提醒
        pass
    try:                                                  # 美股三成（研究檔判定換了才有）
        uq = uqm_state(now)
        if uq:
            rec["uqm"] = uq
            rec["ev"] += uqm_events(uq, (days.get(prev_d) or {}).get("uqm") if prev_d else None)
    except Exception:                                     # noqa: BLE001 —— 讀不到：不發提醒
        pass
    rec["push"] = push_lines(rec)
    old = days.get(last) or {}
    if {k: v for k, v in old.items() if k != "t"} != rec:   # 內容沒變就不動檔（時間戳也不改）
        days[last] = {**rec, "t": now.strftime("%Y-%m-%d %H:%M")}
    else:
        rec = old
    for d in sorted(days)[:-KEEP]:
        days.pop(d, None)
    if write_file:
        write(log)
    return view(days, last)


def view(days: dict, last: str) -> dict:
    """頁面「後台」：今天的紀錄、近 60 個資料日的事件、評級變動史、紀錄起點。"""
    ds = sorted(days)
    hist = [[d, days[d].get("ev")] for d in ds[-60:] if days[d].get("ev")]
    gh: dict[str, list] = {}
    pv: dict[str, str] = {}
    for d in ds:
        for k, s in (days[d].get("st") or {}).items():
            if s.get("g") and pv.get(k) != s["g"]:
                gh.setdefault(k, []).append([d, s["g"]])
                pv[k] = s["g"]
    return {"today": days.get(last) or {}, "d": last, "since": ds[0] if ds else None, "n": len(ds),
            "hist": list(reversed(hist)), "gh": gh}
