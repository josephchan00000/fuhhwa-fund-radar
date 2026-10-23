"""研究結論（訊號總覽「研究結論」段；docs/lab_research_v2_plan.md，2026-10-22 使用者決定）。

原本的「研究細節」（實測區＋四張研究卡，展開後台股一個市場就有 4 萬多像素高）改成每個市場八則白話問答：
問題 → 答案（由研究判定決定，不寫死）→ 一個「這種時候 vs 平常」的對照 → 現在是不是這樣 → 過去每一次（收起）。
最上面一行「現在適用」彙整現在成立的那幾則。原本的研究卡與實測細節照留，收在最下面的「完整研究表」。

  第 1 則  照網頁調整持股，能不能比一直抱著賺更多？      實測研究檔（practsim）＋前瞻紀錄；訊號總覽建頁時算（money）
  第 2 則  平常抱著、買點出現時用期貨多拿，能不能賺更多？ 期貨加碼研究檔（tilt，docs/lab_tilt_plan.md）；訊號總覽建頁時算
  第 3 則  籌碼一直很熱，之後會不會跌比較深？            反向檢查（hotchpage.state）
  第 4 則  剛進入過熱，之後會不會跌比較多？              過熱之後回撤（hotddpage.state）
  第 5 則  跌破季線之後，會不會再大跌？                  反向檢查的技術面轉空與大跌時訊號位置
  第 6 則  大跌後等落底訊號再買，會不會買得比較低？      大跌後檢查（bottompage.state）
  第 7 則  哪些指標熱的時候，之後比較容易急跌？          短線大跌風險（crashpage.state）
  第 8 則  網頁上的好訊號，之後還準嗎？                  訊號的逐年檢查（sigoos）
第幾則照 QS 的順序（QN）。

第 3～7 則要景氣頁算好的「現在」：景氣頁建頁時 compute(V) 存進 sigpage.CARDS[市場]["find"]（同研究卡的機制），
訊號總覽建頁時寫進 x9or-{市場}.json；單獨建訊號總覽時讀上一版的檔。只改呈現：研究規格與判定一律不動。
用字照專案禁用詞；問題寫成描述句（「會不會」），不寫成要不要買賣。class 一律 rf 開頭。
"""
from __future__ import annotations

import html as _h
import math

QS = ("money", "tilt", "chip", "hotin", "ma60", "bottom", "crash", "keep")
QN = {q: i + 1 for i, q in enumerate(QS)}                     # 第幾則（照 QS 的順序）
MK_NAMES = {"tw": "台股", "spx": "S&P 500", "ixic": "那斯達克", "ndx": "那斯達克 100", "sox": "費半"}
PX_NAMES = {"tw": "加權指數", "spx": "S&P 500", "ixic": "那斯達克", "ndx": "那斯達克 100", "sox": "費半"}
STATE_WEEKS = {"H1": 1, "H4": 4, "H13": 13, "H26": 26}
LIST_MAX = 20
TL_MIN_DAYS = 63                                               # 前瞻滿 3 個月才寫成績（同 tilt.LIVE_MIN_DAYS）
MONEY_RULES = ("A1", "A2", "A3", "A4", "B1", "M1", "M2")       # 會調整持股的做法（D1＝偏多全部照做，幾乎一直拿滿，只當對照）
MONEY_NAMES = {"bh": "一直抱著", "A1": "溫度計：短線警示多就減半", "A2": "溫度計：中線警示多就減半", "A3": "溫度計：長線警示多就減半",
               "A4": "溫度計：兩支以上警示多就減半", "B1": "溫度計：短線偏多多才拿滿", "D1": "溫度計：偏多有東西就拿滿（幾乎一直拿滿）",
               "M1": "總經策略：只照 ★ 做", "M2": "總經策略全部照做（★＋●）"}
MONEY_SHORT = {"bh": "一直抱著", "A1": "溫度計", "M2": "總經策略"}
TILT_NAMES = {"K1": "短線買點出現才加碼", "K2": "落底買點出現才加碼", "K3": "策略頁的買點全部加碼",
              "K4": "200 日均線上才加碼", "K5": "溫度計短線偏多多才加碼"}
TILT_SHORT = {"bh": "一直抱著", "fix": "固定多拿同樣多", "K1": "短線買點加碼", "K2": "落底買點加碼", "K3": "買點全部加碼",
              "K4": "200 日均線上加碼", "K5": "溫度計偏多加碼"}
TILT_V = {"better": "訊號有用", "same": "差不多", "worse": "比固定多拿差"}


def _e(x) -> str:
    return _h.escape(str(x), quote=True)


def _nan(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def _pc(x, dec: int = 0) -> str:
    """0.123 → 12%（dec 位小數）。"""
    return "—" if _nan(x) else f"{x * 100:.{dec}f}%"


def _sp(x, dec: int = 1) -> str:
    """有正負的漲跌：+2.0%、−3.4%（負號用全形減號，同景氣頁）。"""
    if _nan(x):
        return "—"
    r = round(x * 100, dec)
    return ("−" if r < 0 else ("+" if r > 0 else "")) + f"{abs(r):.{dec}f}%"


def _d(d: str | None) -> str:
    """2026-10-22 → 2026/10/22。"""
    if not d or len(str(d)) < 10:
        return "—"
    d = str(d)
    return f"{int(d[:4])}/{int(d[5:7])}/{int(d[8:10])}"


def _md(d: str | None) -> str:
    """2026-10-22 → 10/22。"""
    if not d or len(str(d)) < 10:
        return "—"
    d = str(d)
    return f"{int(d[5:7])}/{int(d[8:10])}"


def _r(x, k: int = 5):
    return None if _nan(x) else round(float(x), k)


# ── 第 2～6 則：景氣頁建頁時算（存進 x9or-{市場}.json）───────────────────────────────

def compute(V: dict) -> dict:
    """景氣頁的 V（heatpage.view）→ 這個市場第 2～6 則的資料（JSON 可存）。每一則各自算，算不出來的那一則只印日誌、不擋其他則。"""
    mk = V.get("mk") or (V.get("signow") or {}).get("mk")
    out = {"mk": mk, "d": V.get("asof")}
    for k, fn, src in (("chip", chip, "hotch"), ("hotin", hotin, "hotdd"), ("ma60", ma60, "hotch"),
                       ("bottom", bottom, "bottom"), ("crash", crash, "crash")):
        C = V.get(src)
        if not C:
            continue
        try:
            x = fn(C)
        except Exception as e:                          # noqa: BLE001 —— 一則算不出來不擋其他則
            print(f"[研究結論] {mk} {k} 算不出來：{type(e).__name__}: {e}", flush=True)
            x = None
        if x:
            out[k] = x
    return out


def _mq(st: dict, part: str) -> list:
    x = st.get(part) or {}
    return [_r(x.get("med")), _r(x.get("q10"))]


def chip(C: dict) -> dict | None:
    """第 2 則（反向檢查 A）：籌碼項目連續過熱之後 3 個月的最大回撤。
    主角＝現在過熱、而且今天的狀態研究判定「較大」的第一項；沒有的話＝研究判定有「較大」的第一項（取它最長的那個狀態）。"""
    from . import hotchpage as QP
    from . import hotchspec as HS
    N, nm, order = C["now"], C["names"], C["order"]
    A = C["R"].get("A") or {}
    chipnow = N.get("chip") or {}

    def ups(k):
        return [s for s in HS.STATES_A if QP._A(C, k, s).get("v") == "up"]
    hot = [k for k in order if ((chipnow.get(k) or {}).get("w") or 0) >= 1]
    head, key, on = None, None, False
    for k in hot:
        m = QP.matched(C, k)
        if m and m != "H0" and QP._A(C, k, m).get("v") == "up":
            head, key, on = k, m, True
            break
    if not head:
        for k in order:
            u = ups(k)
            if u:
                head, key = k, u[-1]
                break
    also = [nm.get(k, k) for k in order if k != head and ups(k)]
    down = [nm.get(k, k) for k in order if any(QP._A(C, k, s).get("v") == "down" for s in HS.STATES_A) and not ups(k)]
    out = {"lab": "融資" if C["mk"] == "tw" else "籌碼", "start": (C["R"].get("start") or "")[:4], "also": also, "down": down,
           "hot": [[nm.get(k, k), chipnow[k]["w"]] for k in hot], "on": False}
    if head:
        st = QP._A(C, head, key)
        out.update({"ans": "yes" if st.get("vv") == "up" else "raw", "k": head, "name": nm.get(head, head), "st": key,
                    "sname": HS.STATE_NAMES[key], "thr": STATE_WEEKS[key], "n": st.get("n"), "ep": st.get("ep"),
                    "ev": _mq(st, "ev"), "base": _mq(st, "base"), "on": on,
                    "w": (chipnow.get(head) or {}).get("w") or 0})
        runs = (N.get("runs") or {}).get(head) or (A.get(head) or {}).get("runs") or []
        thr = max(STATE_WEEKS[key], HS.RUN_MIN)
        out["runs"] = [[r["a"], r["wk"], _r(r.get("mdd")), 1 if r.get("open") else 0, 1 if r.get("hot") else 0]
                       for r in runs if (r.get("wk") or 0) >= thr]
        out["thr_runs"] = thr
    else:
        out["ans"] = "less" if down else "no"
        for k in order:                               # 長條畫「反而比較淺」的那一項（沒有就不畫），免得長條和答案看起來矛盾
            dn = [s for s in HS.STATES_A if QP._A(C, k, s).get("v") == "down"]
            if dn:
                st = QP._A(C, k, dn[-1])
                out.update({"k": k, "name": nm.get(k, k), "st": dn[-1], "sname": HS.STATE_NAMES[dn[-1]], "n": st.get("n"),
                            "ev": _mq(st, "ev"), "base": _mq(st, "base"), "on": False})
                break
    return out


def hotin(C: dict) -> dict | None:
    """第 3 則（過熱之後回撤）：技術面向剛進入過熱之後 3 個月；另列全部比較的判定次數。"""
    R = C["R"]
    rows = R.get("rows") or {}
    st = ((rows.get("tech") or {}).get("ev") or {}).get("E") or {}
    if not st.get("n"):
        return None
    c = {"up": 0, "down": 0, "none": 0, "few": 0}
    for r in rows.values():
        if r.get("kind") == "mkt":
            continue
        for s in (r.get("ev") or {}).values():
            c[s.get("v") or "few"] += 1
    v = st.get("v") or "few"
    hot = [r for r in (C["now"].get("hot") or []) if r.get("kind") == "dim"]
    lst = sorted(st.get("list") or [], key=lambda x: x[0], reverse=True)[:LIST_MAX]
    return {"ans": {"up": "yes", "down": "less", "none": "same"}.get(v, "few"), "n": st["n"], "ep": st.get("ep"),
            "ev": _mq(st, "ev"), "base": _mq(st, "base"), "start": (st.get("a") or R.get("start") or "")[:4],
            "cnt": {"all": sum(c.values()), "up": c["up"], "down": c["down"]},
            "hot": [[C["short"].get(r["k"], C["names"].get(r["k"], r["k"])), r.get("wk") or 0] for r in hot],
            "thot": any(r["k"] == "tech" for r in hot),
            "list": [[x[0], _r(x[1]), _r(x[3]), x[4], x[5]] for x in lst]}


def ma60(C: dict) -> dict | None:
    """第 4 則（反向檢查 B）：跌破季線之後 3 個月的最大回撤（判定用的量），跌 20% 以上的大跌時跌破季線在哪裡。"""
    B = C["R"].get("B") or {}
    e = (B.get("ev") or {}).get("ma60_dn") or {}
    if not e.get("n"):
        return None
    d20 = ((B.get("dsum") or {}).get("20") or {}).get("ma60_dn") or {}
    dl = (B.get("decl") or {}).get("20") or []
    dr = (((B.get("drows") or {}).get("20") or {}).get("ma60_dn")) or [None] * len(dl)
    rows = []
    for j, x in enumerate(dl):
        r = dr[j] if j < len(dr) else None
        if r is None:
            brk = ["na"]
        elif r[0] is None:
            brk = [None]
        else:
            brk = [r[0], _r(r[2]), _r(r[3])]
        rows.append([x["pk"], x["tr"], _r(x["dd"]), 1 if x.get("open") else 0] + brk)
    N = C["now"]
    rec = (N.get("recent") or {}).get("ma60_dn") or []
    b60 = (N.get("states") or {}).get("below60") or {}
    v = e.get("v") or "few"
    return {"ans": {"up": "yes", "down": "less", "none": "same"}.get(v, "few"), "n": e["n"], "start": (e.get("a") or "")[:4],
            "ev": _mq(e, "ev"), "base": _mq(e, "base"),
            "big": {"n": d20.get("n") or 0, "hit": d20.get("hit") or 0, "lost": _r(d20.get("lost")), "rem": _r(d20.get("rem"))},
            "rows": rows[::-1], "recent": rec[-1] if rec else None,
            "below": (b60.get("days") or 0) if b60.get("on") else 0, "since": b60.get("since") if b60.get("on") else None}


def bottom(C: dict) -> dict | None:
    """第 5 則（大跌後檢查，bottomspec VER 4 的判定）：5 日急跌之後，隔天買、等 10 天、等落底訊號，買在這一波相對低點的比例。"""
    from . import bottompage as BP
    from . import bottomspec as BS
    mk, R, N = C["mk"], C["R"], C["now"]
    E = (R.get("ev") or {}).get("E5") or {}
    if not E.get("n"):
        return None
    A = E.get("all") or {}
    rs = E.get("rules") or {}
    w = (rs.get(BS.SIG_BASE) or {}).get("lp") or {}
    sig = [k for k in BS.SIG_MK[mk] + BS.SIG_ADD4.get(mk, ()) if ((rs.get(k) or {}).get("lp") or {}).get("n")]
    sig = list(dict.fromkeys(sig))
    good = [BP.SHORT[k] for k in sig if rs[k].get("v") == "better"]
    lean = [[BP.SHORT[k], _r(rs[k]["lp"].get("lp_rule")), _r(rs[k]["lp"].get("lp_base"))] for k in sig
            if rs[k].get("v") != "better" and not rs[k]["lp"].get("few") and (rs[k]["lp"].get("lp_lo") or 0) > 0]
    low = [[BP.SHORT[k], _r(rs[k]["lp"].get("lp_rule")), _r(rs[k]["lp"].get("lp_base"))] for k in sig
           if rs[k]["lp"].get("lp_dir") == "down"]
    act = []
    for a in N.get("active") or []:
        act.append({"ev": a["ev"], "t": a["t"], "p": a["p"], "days": a["days"], "nowdd": _r(a.get("nowdd")),
                    "low": a.get("low"), "lowdd": _r(a.get("lowdd")), "depth": _r(a.get("depth")), "also": a.get("also")})
    r60 = A.get("r60") or {}
    lst = list(reversed(E.get("list") or []))[:LIST_MAX]
    return {"ans": "yes" if good else "no", "good": good, "lean": lean, "low": low, "nsig": len(sig),
            "n": E["n"], "th": BS.E5_TH[mk], "start": (R.get("start") or "")[:4],
            "lp_b1": _r((A.get("lp") or {}).get("rate")), "lp_w10": _r(w.get("lp_rule")), "lp_w10b": _r(w.get("lp_base")),
            "r60": [_r(r60.get("mean")), _r(r60.get("med")), _r(r60.get("up"))],
            "active": act, "dd60": _r(N.get("dd60")), "last": N.get("last") or {},
            "list": [[x["d"], _r(x.get("depth")), _r(x.get("r60")), _r(x.get("pos")), _r(x.get("mae"))] for x in lst]}


def crash(C: dict) -> dict | None:
    """第 6 則（短線大跌風險）：研究判定「熱的時候之後較容易／較不容易大跌」的項目、現在熱不熱、樣本外有沒有變準。"""
    from . import crashpage as CP
    from . import crashspec as CS
    its = CP.items(C)
    mk, px = C["mk"], (C.get("px") or "")             # 美股指數名前後帶空白（「內 S&P 500 有一天」），台股「加權指數」沒有
    up, dn, used = [], [], set()

    def word(it):                                     # 熱＝偏高還是偏低（直接寫出來，「VIX 熱」讀者會誤會成 VIX 高）
        h = str(it.get("hotdef") or "")
        return "偏高" if h.endswith("高") else ("偏低" if h.endswith("低") else ("過熱" if "面向分數" in h else ""))
    for it in its:
        b = [r for r in it["outs"] if r["o"] in CS.BINARY]
        u = [r for r in b if r["v"] == "up"]
        d = [r for r in b if r["v"] == "down"]
        if u:
            r = max(u, key=lambda r: (r.get("hot") or 0) - (r.get("not") or 0))
            up.append([it["name"], bool(it["hot"]), _r(it.get("v"), 1), r["o"], _r(r.get("hot")), _r(r.get("not")), r.get("oos"), word(it)])
            used.add(r["o"])
        elif d:
            r = d[0]
            dn.append([it["name"], bool(it["hot"]), _r(it.get("v"), 1), r["o"], _r(r.get("hot")), _r(r.get("not")), r.get("oos"), word(it)])
            used.add(r["o"])
    better = sum(1 for x in up if x[6] == "better")
    vs = C.get("vs") or {}
    return {"ans": "some" if up else ("down_only" if dn else "none"), "n": len(its), "up": up, "down": dn, "better": better,
            "odef": {o: CP.odef(mk, o, px) for o in sorted(used)}, "oname": {o: CP.ONAME[o] for o in sorted(used)},
            "vol": [_r(vs.get("vol")), _r(vs.get("pct")), vs.get("g")]}


# ── 第 1、2、8 則：訊號總覽建頁時算 ──────────────────────────────────────────────

def _mdd(v: list[float]) -> float:
    pk, m = v[0], 0.0
    for x in v:
        pk = max(pk, x)
        m = max(m, 1 - x / pk)
    return m


def money(R: dict | None, mk: str, P: dict | None = None) -> dict | None:
    """第 1 則（實測研究檔 practsim）：從同一天開始（溫度計與總經策略兩組裡較晚的起點），100 萬放到最後一週變多少、最慘時跌多少、
    平均拿幾成股票。價格指數、不含股息、空手沒有利息（同實測研究）。P＝practpage.payload（今天照規則該拿幾成、前瞻紀錄）。"""
    M = ((R or {}).get("mk") or {}).get(mk) or {}
    t, x = M.get("t_series") or {}, M.get("x_series") or {}
    if not t.get("d") or not x.get("d"):
        return None
    d0 = max(t["d"][0], x["d"][0])
    it = next((i for i, d in enumerate(t["d"]) if d >= d0), None)
    ix = next((i for i, d in enumerate(x["d"]) if d >= d0), None)
    if it is None or ix is None:
        return None
    yrs = max(1e-9, (len(t["d"]) - 1 - it) / 52.18)

    def row(nav, pos):
        v = [a / nav[0] for a in nav]
        cagr = v[-1] ** (1 / yrs) - 1 if v[-1] > 0 else None
        return [_r(v[-1], 4), _r(_mdd(v), 4), _r(sum(pos) / len(pos) if pos else 1.0, 3), _r(cagr, 4)]
    rows = {"bh": row(t["bh"][it:], [])}
    rows["bh"][2] = 1.0
    for k, s in (t.get("r") or {}).items():
        rows[k] = row(s["nav"][it:], s["pos"][it:])
    for k, s in (x.get("r") or {}).items():
        rows[k] = row(s["nav"][ix:], s["pos"][ix:])
    adj = [k for k in MONEY_RULES if k in rows]
    more = [k for k in adj if rows[k][0] > rows["bh"][0]]
    out = {"ans": "some" if more else "no", "more": more, "start": t["d"][it], "end": t["d"][-1], "rows": rows, "adj": adj}
    P = P or {}
    L = (P.get("live") or {}).get(mk) or {}
    out["now"] = {k: _r((L.get("t") or {}).get(k), 3) for k in ("A1", "M2") if (L.get("t") or {}).get(k) is not None}
    out["now_d"] = L.get("d")
    out["since"] = (P.get("since") or {}).get(mk)
    fw = ((P.get("fw") or {}).get(mk) or {}).get("M2") or {}
    if fw.get("ret") is not None:
        out["fw"] = [_r(fw["ret"], 4), _r(fw.get("bh"), 4), fw.get("n"), bool(fw.get("ok"))]
    return out


def tilt(R: dict | None, mk: str, live: bool = True) -> dict | None:
    """第 2 則（期貨加碼研究檔 tilt，docs/lab_tilt_plan.md）：每條規則和一直抱著、固定多拿同樣多比的 100 萬變多少、最慘時跌多少、判定；
    放上網頁的規則（tiltspec 第 8 節）另外算今天的狀態與前瞻（live＝False 時不算，測試用）。"""
    from . import tiltspec as TS
    M = ((R or {}).get("mk") or {}).get(mk) or {}
    rules = M.get("rules") or {}
    if not rules:
        return None
    rows = {}
    for k in TS.RULES:
        x = rules.get(k)
        if not x:
            continue
        f, h1, h2 = x["full"], x["h1"], x["h2"]
        rows[k] = {"m": x["man"] / 1e6, "dd": f["rule"]["mdd"], "fm": x["man_fix"] / 1e6, "fdd": f["fix"]["mdd"], "v": x["v"],
                   "share": f["rule"]["share"], "abar": f["abar"], "cagr": f["rule"]["cagr"], "fcagr": f["fix"]["cagr"],
                   "h": [h1["rule"]["cagr"], h1["fix"]["cagr"], h2["rule"]["cagr"], h2["fix"]["cagr"]],
                   "worst": f["rule"]["worst"], "fworst": f["fix"]["worst"], "bears": x.get("bears") or []}
    x0 = rules[next(iter(rows))]
    bh = {"m": x0["man_bh"] / 1e6, "dd": x0["full"]["bh"]["mdd"], "cagr": x0["full"]["bh"]["cagr"], "worst": x0["full"]["bh"]["worst"]}
    page = (R or {}).get("page") or {}
    ok = [k for k in TS.PAGE_RULES if (page.get(k) or {}).get("ok") and k in rows]
    main = ok[0] if ok else max((k for k in rows if k in TS.PAGE_RULES), key=lambda k: rows[k]["m"] - rows[k]["fm"])
    out = {"start": M.get("a"), "end": M.get("z"), "rows": rows, "bh": bh, "ok": ok, "main": main, "judged": mk in TS.JUDGED,
           "fut": TS.FUT.get(mk), "h2a": x0["h2"]["rule"]["a"]}
    if live and main == "K4":
        try:
            from . import tilt as TL
            out["live"] = TL.live(mk, rows["K4"]["abar"])
        except Exception as e:                        # noqa: BLE001 —— 前瞻算不出來只少那一句
            print(f"[研究結論] {mk} 第 2 則前瞻算不出來：{type(e).__name__}: {e}", flush=True)
    return out


def keep() -> dict | None:
    """第 8 則（sigoos 衰退表的 L3 格，同景氣頁「怎麼看」那一句）：偏多看 1／3／12 個月、大跌風險看 1／3 個月，之後留下的比例。"""
    from . import sigoos as OOS
    from . import sigspec as SS
    T = OOS.load()
    if not T:
        return None
    C = T.get("cells") or {}

    def k(d, H):
        c = C.get(OOS.key(d, H, None, "p")) or {}
        return _r(c.get("k"), 4)
    out = {"u1": k("up", SS.H_TECH), "u3": k("up", SS.H_CRASH), "u12": k("up", SS.H_BUB), "w1": k("warn", SS.H_TECH),
           "w3": k("warn", SS.H_CRASH)}
    return out if any(v is not None for v in out.values()) else None


# ── HTML ─────────────────────────────────────────────────────────────────

def _bars(rows: list, mx: float, hi: set | None = None, cls: str = "hi") -> str:
    """橫條：rows＝[(標籤, 值, 右邊的字)]；mx＝最長那條代表的值；hi＝要上色的列（0 起算）。"""
    hi = hi or set()
    h = []
    for i, (lb, v, txt) in enumerate(rows):
        w = 0 if _nan(v) or not mx or v <= 0 else max(1.5, min(100.0, 100.0 * v / mx))
        c = f" {cls}" if i in hi else ""
        h.append(f'<span class="rfbl">{_e(lb)}</span><span class="rfbt"><i class="rfbb{c}" style="width:{w:.1f}%"></i></span>'
                 f'<span class="rfbv">{_e(txt)}</span>')
    wide = " rfbw" if max((len(str(r[0])) for r in rows), default=0) > 8 else ""     # 標籤長：手機上標籤自己一行
    return f'<div class="rfbars{wide}">' + "".join(h) + "</div>"


def _cmp_bars(ev: list, base: list, lab_ev: str, lab_base: str = "平常", risk: bool = False) -> str:
    """「之後 3 個月最多回檔超過 10% 的比例」：這種時候 vs 平常。"""
    a, b = (ev or [None, None])[1], (base or [None, None])[1]
    mx = max([v for v in (a, b) if not _nan(v)] + [0.05]) * 1.15
    return ('<div class="rfbh">之後 3 個月內，最多回檔超過 10% 的比例</div>'
            + _bars([(lab_ev, a, _pc(a)), (lab_base, b, _pc(b))], mx, {0} if risk else set()))


def _card(q: str, n: int, title: str, ans: str, small: str, acls: str, body: str, now: str, nflag: str,
          detail: tuple | str = "") -> str:
    """一則：問題、答案、內容、現在（HTML）、過去每一次（(摘要, HTML)）。nflag＝risk（現在成立而且是風險）、side（現在有關、只當參考）、空字串。"""
    on = " on" if nflag == "risk" else ""
    return (f'<article class="rfc{on}" id="rf-{q}"><div class="rfq"><i>{n}</i>{_e(title)}</div>'
            f'<div class="rfa {acls}">{_e(ans)}' + (f"<small>{_e(small)}</small>" if small else "") + "</div>"
            + body + f'<div class="rfnw{" " + nflag if nflag else ""}"><b>現在</b>：{now}</div>'
            + (f'<details class="rfdt"><summary>{detail[0]}</summary>{detail[1]}</details>' if detail else "") + "</article>")


def money_card(mk: str, X: dict | None) -> tuple[str, tuple | str]:
    if not X:
        return "", ""
    rw = X["rows"]
    bh = rw["bh"]
    yr = X["start"][:4]
    a1, m2 = rw.get("A1"), rw.get("M2")
    pick = [("bh", bh)] + [(k, rw[k]) for k in ("A1", "M2") if rw.get(k)]
    mx_v = max(v[0] for _, v in pick) * 1.05
    mx_d = max(v[1] for _, v in pick) * 1.15
    bars = ('<div class="rftwo"><div><div class="rfbh">100 萬變多少</div>'
            + _bars([(MONEY_SHORT[k], v[0], f"{v[0] * 100:,.0f} 萬") for k, v in pick], mx_v, {0}, "ac")
            + '</div><div><div class="rfbh">最慘時帳面跌多少</div>'
            + _bars([(MONEY_SHORT[k], v[1], _pc(v[1])) for k, v in pick], mx_d, {0}) + "</div></div>")
    adj = X["adj"]
    vals = [rw[k][0] for k in adj]
    mdds = [rw[k][1] for k in adj]
    if X["ans"] == "no":
        ans, small = "不能", "好處只有少跌"
        sub = (f"試過 {len(adj)} 種照網頁調整持股的做法，{yr} 年起放到今天都比一直抱著少（{min(vals) * 100:,.0f}～{max(vals) * 100:,.0f} 萬）；"
               f"好處只有少跌：最慘時跌 {_pc(min(mdds))}～{_pc(max(mdds))}，一直抱著 {_pc(bh[1])}。")
    else:
        ans, small = f"有 {len(X['more'])} 種比較多", "、".join(MONEY_NAMES[k] for k in X["more"])
        sub = f"試過 {len(adj)} 種照網頁調整持股的做法，{yr} 年起放到今天，有 {len(X['more'])} 種比一直抱著多。"
    body = (f'<p class="rfl">{_e(yr)} 年起放 100 萬到今天（{_e(_d(X["end"]))}）：</p>' + bars
            + f'<p class="rfs">{_e(sub)}價格指數、不含股息、空手沒有利息。</p>')
    nw = X.get("now") or {}
    parts = []
    if nw.get("M2") is not None:
        parts.append(f"總經策略全部照做拿 {nw['M2'] * 100:.0f}% 股票")
    if nw.get("A1") is not None:
        parts.append(f"溫度計（短線警示多就減半）拿 {nw['A1'] * 100:.0f}%")
    now = ("今天照做：" + "、".join(parts) + "。") if parts else "今天的部位還沒算出來。"
    if X.get("since"):
        fw = X.get("fw")
        if fw and fw[3]:
            now += f"{_d(X['since'])} 起真的照做（總經策略全部照做）{_sp(fw[0])}，一直抱著 {_sp(fw[1])}。"
        else:
            now += f"{_d(X['since'])} 起每天記錄真的照做的成績（不到 3 個月，還在累積）。"
    head = "<tr><th class=\"l\">做法</th><th>100 萬變</th><th>最慘時跌</th><th>平均拿幾成</th><th>年化</th><th></th></tr>"
    trs = []
    for k in ["bh"] + [k for k in ("A1", "A2", "A3", "A4", "B1", "D1", "M1", "M2") if k in rw]:
        v = rw[k]
        link = "" if k == "bh" else f'<a href="#p={k}:{mk}" class="rfln">每週走勢 ›</a>'
        trs.append(f'<tr{' class="rfbhr"' if k == "bh" else ""}><td class="l">{_e(MONEY_NAMES[k])}</td><td>{v[0] * 100:,.0f} 萬</td>'
                   f'<td>{_pc(v[1])}</td><td>{_pc(v[2])}</td><td>{_sp(v[3])}</td><td>{link}</td></tr>')
    det = (f"8 種做法的完整成績（{_e(yr)} 年起）",
           f'<div class="rftw"><table class="rftb">{head}{"".join(trs)}</table></div>'
           '<p class="rfnote">溫度計的做法每週最後一個交易日看一次溫度計、下一個交易日收盤調整；總經策略每年 1 月 1 日只用之前的資料重新判定，'
           '每一條一份、平均分。每年的判定都只用當時拿得到的資料。點「每週走勢」看那一種做法的走勢圖、逐年成績與每一段大跌。</p>')
    risk = ""
    return _card("money", QN["money"], "照網頁的訊號調整持股，能不能比一直抱著賺更多？", ans, small, "no" if X["ans"] == "no" else "yes",
                 body, _e(now), risk, det), ""


def _wan(m: float) -> str:
    """100 萬的倍數 → 「1,852 萬」。"""
    return f"{m * 100:,.0f} 萬"


def tilt_card(mk: str, X: dict | None) -> tuple[str, tuple | str]:
    if not X:
        return "", ""
    from . import tiltspec as TS
    rw, bh, k = X["rows"], X["bh"], X["main"]
    r = rw[k]
    yr, h2y = (X["start"] or "")[:4], (X.get("h2a") or "")[:4]
    here = r["v"] == "better"
    if not X["judged"]:
        ans, small, acls = "沒有對應的期貨", "只當參考", "mid"
    elif k in X["ok"] and here:
        ans, small, acls = "可以參考", f"{TILT_NAMES[k]}（前瞻驗證中）", "ac"
    elif k in X["ok"] and r["v"] == "worse":
        ans, small, acls = "比固定多拿差", f"{TILT_NAMES[k]}在這裡不如每天固定多拿同樣多", "no"
    elif k in X["ok"]:
        ans, small, acls = "差不多", f"{TILT_NAMES[k]}和固定多拿同樣多差不多", "mid"
    else:
        ans, small, acls = "多賺的是多拿股票", "訊號沒有比固定多拿好", "no"
    pick = [("bh", bh["m"], bh["dd"]), (k, r["m"], r["dd"]), ("fix", r["fm"], r["fdd"])]
    mx_v = max(v for _, v, _ in pick) * 1.05
    mx_d = max(d for _, _, d in pick) * 1.15
    bars = ('<div class="rftwo"><div><div class="rfbh">100 萬變多少</div>'
            + _bars([(TILT_SHORT[q], v, _wan(v)) for q, v, _ in pick], mx_v, {1}, "ac")
            + '</div><div><div class="rfbh">最慘時帳面跌多少</div>'
            + _bars([(TILT_SHORT[q], d, _pc(d)) for q, _, d in pick], mx_d, {1}, "ac") + "</div></div>")
    h = r["h"]
    cmp = f"{yr}～{h2y} 年 {_sp(h[0])} 對 {_sp(h[1])}、{h2y} 年起 {_sp(h[2])} 對 {_sp(h[3])}，都是年化"
    if here:
        why = f"前後兩段都比較好（{cmp}）。"
    elif r["v"] == "worse":
        why = f"前後兩段都比較少賺（{cmp}），算比固定多拿差。"
    elif h[0] > h[1] and h[2] > h[3]:
        why = f"前後兩段都比較好（{cmp}），但最慘時跌得比較兇，所以算差不多。"
    else:
        why = f"前後兩段不一致（{cmp}），所以算差不多。"
    dm, ddd, dbh = r["m"] - r["fm"], r["fdd"] - r["dd"], r["dd"] - bh["dd"]
    vs_bh = ("最慘時跌得差不多" if abs(dbh) < 0.005 else
             f"最慘時{'多' if dbh > 0 else '少'}跌 {abs(dbh) * 100:.0f} 個百分點")
    others = [q for q in ("K1", "K2", "K3") if q in rw and q != k]
    ob = [q for q in others if rw[q]["v"] == "better"]
    ow = [q for q in others if rw[q]["v"] == "worse"]
    if ob:
        oth = (f"用總經策略買點加碼的 {len(others)} 種做法裡，" + "、".join(TILT_NAMES[q] for q in ob)
               + "在這裡也訊號有用（但其他市場不成立）" + ("，" + "、".join(TILT_NAMES[q] for q in ow) + "比固定多拿差" if ow else "") + "。")
    elif ow:
        oth = (f"用總經策略買點加碼的 {len(others)} 種做法，" + "、".join(TILT_NAMES[q] for q in ow) + "比固定多拿差，其他差不多。")
    else:
        oth = f"用總經策略買點加碼的 {len(others)} 種做法，在這裡都和固定多拿差不多。"
    sub = (f"加碼＝用期貨多拿帳戶 5 成。多拿股票本來就會多賺：每天固定多拿 {r['abar'] * 100:.0f}%，100 萬也會變 {_wan(r['fm'])}。"
           f"{TILT_NAMES[k]}比固定多拿{'多' if dm >= 0 else '少'} {abs(dm) * 100:,.0f} 萬、"
           f"最慘時{'少' if ddd >= 0 else '多'}跌 {abs(ddd) * 100:.0f} 個百分點；{why}和一直抱著比，{vs_bh}。{oth}")
    if not X["judged"]:
        sub += "這個指數沒有對應的期貨，要加碼只能融資買 ETF，成本比期貨高。"
    body = (f'<p class="rfl">{_e(yr)} 年起放 100 萬到今天（{_e(_d(X["end"]))}）：</p>' + bars + f'<p class="rfs">{_e(sub)}</p>')
    L = X.get("live") or {}
    st = L.get("state") or {}
    nflag, line = "", ""
    if k == "K4" and st:
        if st["up"]:
            now = f"收盤在 200 日均線上（{_d(st['since'])} 起），照這個做法正在加碼。"
        else:
            now = f"收盤在 200 日均線下（{_d(st['since'])} 起），照這個做法不加碼，只抱本金。"
        if k in X["ok"] and here and X["judged"]:
            if (L.get("days") or 0) >= TL_MIN_DAYS and L.get("rule") is not None:
                now += f"{_d(L['a'])} 起真的照做 {_sp(L['rule'])}，固定多拿 {_sp(L['fix'])}，一直抱著 {_sp(L['bh'])}。"
            else:
                now += f"{_d(L.get('since'))} 起每天記錄照做的成績（不到 3 個月，還在累積）。"
            if st["up"]:
                nflag = "side"
                line = ("side", f"200 日均線上：照「{TILT_NAMES[k]}」正在加碼（前瞻驗證中）")
    else:
        now = "今天的狀態還沒算出來。"
    head = ('<tr><th class="l">做法</th><th>加碼的時間</th><th>100 萬變</th><th>最慘時跌</th>'
            '<th>固定多拿同樣多<small>100 萬變・最慘時跌</small></th><th class="l">結果</th></tr>')
    trs = [f'<tr class="rfbhr"><td class="l">一直抱著</td><td class="mu" data-h="加碼的時間">—</td><td data-h="100 萬變">{_wan(bh["m"])}</td>'
           f'<td data-h="最慘時跌">{_pc(bh["dd"])}</td><td class="mu rfkx">—</td><td class="rfkx"></td></tr>']
    for q in TS.RULES:
        if q not in rw:
            continue
        v = rw[q]
        res = TILT_V[v["v"]] + ("（只描述）" if q not in TS.PAGE_RULES else "")
        trs.append(f'<tr><td class="l">{_e(TILT_NAMES[q])}</td><td data-h="加碼的時間">{_pc(v["share"])}</td>'
                   f'<td data-h="100 萬變">{_wan(v["m"])}</td><td data-h="最慘時跌">{_pc(v["dd"])}</td>'
                   f'<td data-h="固定多拿同樣多">{_wan(v["fm"])}・{_pc(v["fdd"])}</td><td class="l" data-h="結果">{_e(res)}</td></tr>')
    bt = ""
    if r["bears"]:
        sk = _e(TILT_SHORT[k])
        bt = ('<div class="rfbh">每一段大跌（指數跌 20% 以上）時的變化</div>'
              '<div class="rftw"><table class="rftb rftk"><tr><th class="l">期間</th><th>一直抱著</th>'
              f'<th>{sk}</th><th>固定多拿同樣多</th></tr>'
              + "".join(f'<tr><td class="l">{_e(_d(b["pk"]))}～{_e(_d(b["tr"]))}</td>'
                        f'<td data-h="一直抱著">{_sp(b["bh"])}</td><td data-h="{sk}">{_sp(b["rule"])}</td>'
                        f'<td data-h="固定多拿同樣多">{_sp(b["fix"])}</td></tr>' for b in r["bears"])
              + "</table></div>")
    fut = f"期貨：{X['fut']}。" if X.get("fut") else "這個指數沒有對應的期貨（只當參考）。"
    det = (f"5 種加碼做法的完整成績（{_e(yr)} 年起）",
           f'<div class="rftw"><table class="rftb rftk">{head}{"".join(trs)}</table></div>{bt}'
           '<p class="rfnote">平常 100% 抱著指數，訊號成立時另外用期貨多拿 5 成、訊號沒了就平掉。期貨的成本照「含息報酬 − 利率」算'
           '（台股股息高、利率低，台指期多半是逆價差，等於多拿股息），每一邊十萬分之五，每月（美股每季）換月。本金三種做法都沒算股息。'
           '期貨帳戶的錢另外準備（加碼 5 成時，指數跌 20% 要補進帳戶約 1 成的錢）。總經策略的買點每年 1 月 1 日只用之前的資料重新判定。'
           '結果：全期間與前後兩段都比固定多拿同樣多賺得多、最慘時也沒有跌得比較兇＝訊號有用；溫度計那一種的類似做法之前看過結果，只描述。'
           f'{_e(fut)}</p>')
    return _card("tilt", QN["tilt"], "平常抱著，買點出現時用期貨多拿 5 成，能不能賺更多？", ans, small, acls, body, _e(now), nflag, det), line


def chip_card(mk: str, X: dict | None) -> tuple[str, tuple | str]:
    if not X:
        return "", ""
    lab = X["lab"]
    title = "融資一直很熱，之後會不會跌比較深？" if mk == "tw" else "籌碼一直很熱，之後會不會跌比較深？"
    a = X["ans"]
    ans, small, acls = {"yes": ("會", "之後回檔比平常深", "yes"), "raw": ("表面上會", "但主要是那時波動本來就大", "mid"),
                        "less": ("不會", "有的反而比較淺", "no"), "no": ("不會", "", "no")}[a]
    body = ""
    if X.get("ev"):
        body += f'<p class="rfl">{_e(X["name"])}{_e(X["sname"])}的日子，之後 3 個月：</p>'
        body += _cmp_bars(X["ev"], X["base"], "這種時候", risk=a == "yes")
    if a in ("less", "no"):
        s = (f"{lab}項目已連續過熱的日子，之後 3 個月最多回檔都沒有比平常深"
             + (f"（{_asc('、'.join(X['down'][:3]))}反而比較淺）" if X.get("down") else "") + "。")
    else:
        s = f'最多回檔的中位數 {_pc(X["ev"][0], 1)}，平常 {_pc(X["base"][0], 1)}。'
        if a == "raw":
            s += "那段時間本來就波動大；和同樣波動的日子比，看不出差別。"
        if X.get("also"):
            s += "、".join(X["also"][:3]) + "連續過熱也有這個現象。"
    body += f'<p class="rfs">{_e(s)}</p>'
    hot = X.get("hot") or []
    if X.get("on"):
        now, nf = f'<b class="rfy">成立</b>：{_e(X["name"])}已連續過熱 {X["w"]} 週', "risk"
    elif hot:
        now = "、".join(f"{_e(n)}已連續過熱 {w} 週" for n, w in hot[:3]) + "（過去這種時候沒有比平常深）"
        nf = ""
    else:
        now, nf = f"現在沒有{_e(lab)}項目過熱", ""
    det = ""
    if X.get("runs"):
        trs = "".join(f'<tr><td class="l">{_e(_d(r[0]))}' + ("<small>還在過熱</small>" if r[4] else ("<small>結束未滿 3 個月</small>" if r[3] else ""))
                      + f'</td><td>{r[1]} 週</td><td>{_pc(r[2], 1)}' + ("<small>到今天</small>" if r[3] else "") + "</td></tr>"
                      for r in reversed(X["runs"]))
        det = (f'過去每一次（{_e(X["name"])}連續過熱 {X["thr_runs"]} 週以上的 {len(X["runs"])} 段）',
               f'<div class="rftw"><table class="rftb"><tr><th class="l">開始</th><th>連續幾週</th><th>之後最多回檔</th></tr>{trs}</table></div>'
               '<p class="rfnote">之後最多回檔＝從連續過熱滿 4 週那天起，到過熱結束後 3 個月內，指數最多從高點跌多少。</p>')
    return _card("chip", QN["chip"], title, ans, small, acls, body, now, nf, det), (
        ("risk", f'{_e(X["name"])}已連續過熱 {X["w"]} 週：過去這種時候，之後 3 個月最多回檔的中位數 {_pc(X["ev"][0], 1)}'
                 f'（平常 {_pc(X["base"][0], 1)}），{_pc(X["ev"][1])} 的時候跌超過 10%（平常 {_pc(X["base"][1])}）。') if nf == "risk" else "")


def hotin_card(mk: str, X: dict | None) -> tuple[str, tuple | str]:
    if not X:
        return "", ""
    a = X["ans"]
    ans, small, acls = {"yes": ("會", "剛過熱之後回檔比平常深", "yes"), "less": ("不會", "反而比較少", "no"),
                        "same": ("不會", "和平常差不多", "no"), "few": ("看不出", "次數太少", "no")}[a]
    body = (f'<p class="rfl">技術面熱度剛進入過熱之後 3 個月（{_e(X["start"])} 年起 {X["n"]} 次）：</p>'
            + _cmp_bars(X["ev"], X["base"], "剛過熱之後", risk=a == "yes")
            + f'<p class="rfs">{_e("各面向與項目剛進入過熱、連續過熱滿幾週、過熱結束，全部 " + format(X["cnt"]["all"], ",") + " 個比較：")}'
            f'比平常深 {X["cnt"]["up"]} 個、比平常淺 {X["cnt"]["down"]} 個，其他看不出差別或次數太少。'
            + ("要留意的是籌碼「連續熱很久」（第 2 則），不是剛變熱。" if mk == "tw" else "") + "</p>")
    hot = X.get("hot") or []
    now = ("、".join(f"{_e(n)}已連續過熱 {w} 週" for n, w in hot) if hot else "沒有面向在過熱")
    nf = "risk" if a == "yes" and X.get("thot") else ""
    trs = "".join(f'<tr><td class="l">{_e(_d(r[0]))}</td><td>{_pc(r[1], 1)}</td><td>{_e(_md(r[3]))} → {_e(_md(r[4]))}</td><td>{_sp(r[2])}</td></tr>'
                  for r in X.get("list") or [])
    det = (f"過去每一次（技術面剛進入過熱，最近 {min(LIST_MAX, X['n'])} 次）",
           f'<div class="rftw"><table class="rftb"><tr><th class="l">日期</th><th>3 個月最多回檔</th><th>高點 → 低點</th><th>3 個月漲跌</th></tr>{trs}</table></div>'
           ) if trs else ""
    return _card("hotin", QN["hotin"], "剛進入過熱，之後會不會跌比較多？", ans, small, acls, body, now, nf, det), ""


def ma60_card(mk: str, X: dict | None) -> tuple[str, tuple | str]:
    if not X:
        return "", ""
    a = X["ans"]
    ans, small, acls = {"yes": ("會", "跌破之後回檔比平常深", "yes"), "less": ("不會", "反而比較淺", "no"),
                        "same": ("和平常差不多", "", "no"), "few": ("看不出", "次數太少", "no")}[a]
    big = X.get("big") or {}
    body = ""
    if big.get("n"):
        body += (f'<p class="rfl">跌 20% 以上的 {big["n"]} 次大跌，{big["hit"]} 次在低點前跌破季線，'
                 f'但那時已經跌了 {_pc(big["lost"], 1)}（中位數），之後還跌 {_pc(big["rem"], 1)}。</p>')
    body += _cmp_bars(X["ev"], X["base"], "跌破季線之後", "任挑一天", risk=a == "yes")
    if a == "same":
        body += '<p class="rfs">大跌前多半會跌破季線，但跌破之後回檔變大的機會，和任挑一天差不多：跌破季線本身不是大跌的預告。</p>'
    else:
        body += f'<p class="rfs">跌破季線之後 3 個月最多回檔的中位數 {_pc(X["ev"][0], 1)}，任挑一天 {_pc(X["base"][0], 1)}。</p>'
    if X.get("since"):
        now, nf = f"{_md(X['since'])} 起收盤在季線下（第 {X['below']} 天）", "side"
    elif X.get("recent"):
        now, nf = f"{_d(X['recent'])} 跌破季線", "side"
    else:
        now, nf = "最近 3 個月沒有跌破季線", ""
    if a == "yes" and nf:
        nf = "risk"
    trs = []
    for r in X.get("rows") or []:
        op = "<small>還沒反彈</small>" if r[3] else ""
        if r[4] == "na":
            b = '<td class="mu">還沒有資料</td><td></td><td></td>'
        elif r[4] is None:
            b = '<td class="mu">低點前沒有跌破</td><td></td><td></td>'
        else:
            b = f"<td>{_e(_d(r[4]))}</td><td>{_pc(r[5], 1)}</td><td>{_pc(r[6], 1)}</td>"
        trs.append(f'<tr><td class="l">{_e(_d(r[0]))} → {_e(_d(r[1]))}{op}</td><td>{_pc(r[2])}</td>{b}</tr>')
    det = (f"過去每一次（跌 20% 以上的 {len(trs)} 次大跌）",
           '<div class="rftw"><table class="rftb"><tr><th class="l">高點 → 低點</th><th>跌幅</th><th>跌破季線</th><th>那時已跌</th><th>之後還跌</th></tr>'
           + "".join(trs) + '</table></div><p class="rfnote">大跌＝從最高收盤跌 20% 以上、從低點反彈 20% 才算結束。那時已跌＝跌破季線隔天收盤比高點低多少。</p>'
           ) if trs else ""
    return _card("ma60", QN["ma60"], "跌破季線之後，會不會再大跌？", ans, small, acls, body, _e(now), nf, det), (
        (nf, f"{_e(now)}：過去跌破季線之後，回檔{'比平常深' if a == 'yes' else '和任挑一天差不多'}。") if nf else "")


def bottom_card(mk: str, X: dict | None) -> tuple[str, tuple | str]:
    if not X:
        return "", ""
    a = X["ans"]
    ans, small, acls = ("會", "、".join(X["good"]), "yes") if a == "yes" else ("不會", "和等 10 天差不多", "no")
    body = (f'<p class="rfl">{_e(X["start"])} 年起 {X["n"]} 次 5 日急跌（5 天跌 {X["th"] * 100:g}% 以上）：</p>'
            '<div class="rfbh">買在這一波相對低點（跌幅的下三分之一）的比例</div>'
            + _bars([("隔天就買", X["lp_b1"], _pc(X["lp_b1"])), ("等 10 天", X["lp_w10"], _pc(X["lp_w10"]))],
                    max([v for v in (X["lp_b1"], X["lp_w10"]) if not _nan(v)] + [0.05]) * 1.6))
    s = (f"等 {X['nsig']} 種落底訊號出現再買，" + ("有用的：" + "、".join(X["good"]) + "。" if X["good"] else "沒有一種明顯比等 10 天常買在低點"))
    if not X["good"]:
        if X["lean"]:
            n0 = X["lean"][0]
            s += f"；最接近的是「{n0[0]}」（{_pc(n0[1])}，同一批事件等 10 天 {_pc(n0[2])}），但次數少、不夠明顯"
        if X["low"]:
            s += "；" + "、".join(f"「{x[0]}」" for x in X["low"][:2]) + "反而更少買在低點（訊號出現時已經反彈一段）"
        s += "。"
    r = X["r60"]
    s += f"急跌隔天就買，3 個月後平均 {_sp(r[0])}、{_pc(r[2])} 上漲。"
    body += f'<p class="rfs">{_e(s)}</p>'
    act = X.get("active") or []
    if act:
        x = act[0]
        what = " 5 日急跌" if x["ev"] == "E5" else "從 60 日高點跌 10%"
        now = f"{_e(_d(x['t']))} 出現{what}：現在比 {_e(_md(x['p']))} 的高點低 {_pc(-x['nowdd'] if x['nowdd'] is not None else None, 1)}，事件後第 {x['days']} 個交易日"
        nf = "side"
        line = ("side", f"{now}：過去等落底訊號再買，" + ("有用的是" + _e("、".join(X["good"])) + "。" if X["good"] else "沒有比等 10 天常買在低點。"))
    else:
        now, nf, line = f"沒有大跌（離 60 日高點 {_sp(X['dd60'])}）", "", ""
    trs = "".join(f'<tr><td class="l">{_e(_d(r[0]))}</td><td>{_sp(r[1])}</td><td>{_sp(r[2])}</td><td>{_pc(r[3])}</td></tr>'
                  for r in X.get("list") or [])
    det = (f"過去每一次（最近 {len(X.get('list') or [])} 次 5 日急跌）",
           f'<div class="rftw"><table class="rftb"><tr><th class="l">日期</th><th>5 日跌</th><th>隔天買，3 個月後</th><th>隔天買在這一波的位置</th></tr>{trs}</table></div>'
           '<p class="rfnote">位置：0%＝這一波最低收盤、100%＝事件前高點，33% 以內算相對低點；還沒走完的不列。</p>') if trs else ""
    return _card("bottom", QN["bottom"], "大跌後等落底訊號再買，會不會買得比較低？", ans, small, acls, body, now, nf, det), line


def _asc(s: str) -> str:
    """名稱最後是英數字時，後面接中文先空一格（「VIX 偏低」「VIX ÷ 3 個月 VIX 反而」）。"""
    return s + " " if s[-1:].isascii() and s[-1:].isalnum() else s


def _nw(x: list) -> str:
    """項目名稱＋偏高／偏低（舊資料沒有第 8 欄就只寫名稱）。"""
    w = x[7] if len(x) > 7 else ""
    nm = str(x[0])
    return _asc(nm) + w if w else nm


def crash_card(mk: str, X: dict | None) -> tuple[str, tuple | str]:
    if not X:
        return "", ""
    a = X["ans"]
    up, dn = X.get("up") or [], X.get("down") or []
    if a == "some":
        ans, small, acls = f"有 {len(up)} 項", ("但沒有比看波動準" if not X.get("better") else ""), "mid"
    elif a == "down_only":
        ans, small, acls = "沒有", f"{_nw(dn[0])}的時候反而比較少", "no"
    else:
        ans, small, acls = "沒有", "", "no"
    body = ""
    if up:
        rows = sorted(up, key=lambda x: (not x[1], -((x[4] or 0) - (x[5] or 0))))[:4]
        mx = max([x[4] or 0 for x in rows] + [0.05]) * 1.1
        body += ('<p class="rfl">這幾項在熱區的時候，之後比較常急跌：</p><div class="rfbh">在熱區的時候 → 其他時候</div>'
                 + _bars([(f"{_nw(x)}・{X['oname'][x[3]]}", x[4], f"{_pc(x[4])} → {_pc(x[5])}") for x in rows], mx,
                         {i for i, x in enumerate(rows) if x[1]}))
        defs = "；".join(f"{X['oname'][o]}＝{d}" for o, d in X["odef"].items())
        s = defs + "。"
        if not X.get("better"):
            s += "但 2010 年起逐月檢查：加進這幾項，沒有比只看「最近波動大不大」更準。"
        if dn:
            s += "、".join(_nw(x) for x in dn[:2]) + "的時候反而比較少急跌。"
        body += f'<p class="rfs">{_e(s)}</p>'
    elif dn:
        body += (f'<p class="rfs">{_e("、".join(_nw(x) for x in dn[:3]))}的時候反而比較少急跌'
                 f'（{_e(X["oname"][dn[0][3]])}：在熱區 {_pc(dn[0][4])}，其他時候 {_pc(dn[0][5])}）。其他項目和之後急跌看不出關係。</p>')
    else:
        body += '<p class="rfs">和同樣波動的日子比，沒有項目和之後急跌有關。</p>'
    hu = [x for x in up if x[1]]
    if hu:
        now, nf = f'<b class="rfy">{len(hu)} 項在熱區</b>：' + "、".join(_e(_nw(x)) for x in hu), "risk"
        line = ("risk", f"{len(hu)} 項急跌指標在熱區（{_e('、'.join(_nw(x) for x in hu))}）：過去這種時候之後比較常急跌"
                + ("，但沒有比看波動準。" if not X.get("better") else "。"))
    else:
        hd = [x for x in dn if x[1]]
        now = (f"{'、'.join(_e(_nw(x)) for x in hd)}（過去這種時候比較少急跌）" if hd
               else (f"研究判定有關的 {X['n']} 項，現在都不在熱區" if X["n"] else "—"))
        nf, line = "", ""
    trs = "".join(f'<tr><td class="l">{_e(_nw(x))}</td><td>{_e(X["oname"][x[3]])}</td><td>{_pc(x[4])}</td><td>{_pc(x[5])}</td>'
                  f'<td>{"在熱區" if x[1] else "—"}</td></tr>' for x in up + dn)
    det = ("每一項在熱區與其他時候",
           f'<div class="rftw"><table class="rftb"><tr><th class="l">項目</th><th>之後</th><th>在熱區</th><th>其他時候</th><th>現在</th></tr>{trs}</table></div>'
           '<p class="rfnote">在熱區＝比過去 3 年 80% 的時候高（寫「偏低」的項目＝比 80% 的時候低）。</p>') if trs else ""
    return _card("crash", QN["crash"], "哪些指標熱的時候，之後比較容易急跌？", ans, small, acls, body, now, nf, det), line


def keep_card(X: dict | None) -> tuple[str, tuple | str]:
    if not X:
        return "", ""
    u = [X.get(k) for k in ("u1", "u3", "u12") if X.get(k) is not None]
    w1 = X.get("w1")
    ans = "偏多的不準" if u and max(u) < 0.2 else "偏多的部分準"
    small = f"大跌風險（1 個月）留下 {_pc(w1)}" if w1 is not None else ""
    rows = [(lb, X.get(k), _pc(X.get(k))) for lb, k in (("偏多・看 1 個月", "u1"), ("偏多・看 3 個月", "u3"), ("偏多・看 12 個月", "u12"),
                                                        ("大跌風險・看 1 個月", "w1"), ("大跌風險・看 3 個月", "w3")) if X.get(k) is not None]
    body = ('<p class="rfl">每年 1 月 1 日只用之前的資料挑出好訊號，看之後那一年：過去比平常多出的勝率，之後留下多少？</p>'
            '<div class="rfbh">之後留下的比例（100%＝過去的優勢全部留下）</div>'
            + _bars(rows, 1.0, {i for i, r in enumerate(rows) if r[0].startswith("大跌")})
            + f'<p class="rfs">偏多訊號過去看起來的優勢，之後幾乎沒有留下；1 個月內的大跌風險留下 {_pc(w1)}（多半是波動已經變大的時候）。'
            '所以今天的重點把「之後也成立」的排在前面，偏多那一邊只當參考。</p>')
    det = ("怎麼算", '<p class="rfnote">每年 1 月 1 日只用當時窗口已經走完的資料，算每個訊號過去比平常高幾個百分點；再看它之後那一年實際比平常高幾個百分點。'
           '兩者相除＝留下的比例（全部訊號、全部市場、全部年份一起算）。細節在下面「名詞與判定方式」。</p>')
    return _card("keep", QN["keep"], "網頁上的好訊號，之後還準嗎？", ans, small, "no", body, "溫度計與今天的訊號照舊列出，偏多那一邊只當參考", "", det), ""


def market_html(mk: str, F: dict | None, money_x: dict | None, keep_x: dict | None, show: bool = False,
                tilt_x: dict | None = None, plan: str = "") -> str:
    """一個市場：交易計畫卡（plan，corepage.card 的 HTML）→「現在適用」＋八則。F＝compute 的結果（可能是上一版的檔，沒有就只有第 1、2、8 則）。"""
    F = F or {}
    parts = [money_card(mk, money_x), tilt_card(mk, tilt_x), chip_card(mk, F.get("chip")), hotin_card(mk, F.get("hotin")), ma60_card(mk, F.get("ma60")),
             bottom_card(mk, F.get("bottom")), crash_card(mk, F.get("crash")), keep_card(keep_x)]
    cards = [c for c, _ in parts if c]
    lines = [ln for _, ln in parts if ln]
    risk = [x for lv, x in lines if lv == "risk"]
    info = [x for lv, x in lines if lv == "side"]
    if risk or info:
        ban = (f'<div class="rfnow{"" if risk else " rfside"}"><b>現在適用</b><ul>' + "".join(f"<li>{x}</li>" for x in risk)
               + "".join(f'<li class="rfi">{x}</li>' for x in info) + "</ul></div>")
    else:
        ban = '<div class="rfnow rfnone"><b>現在適用</b>：沒有。研究過的這幾種情況，現在都沒有出現。</div>'
    d = F.get("d")
    asof = f'<p class="rfas">資料到 {_e(_d(d))}</p>' if d else ""
    if not F.get("chip") and not F.get("crash") and not F.get("bottom"):
        asof += '<p class="rfas">這個市場的研究狀態還沒產生（景氣頁建頁時會算）。</p>'
    return (f'<div class="rfm" data-mk="{_e(mk)}"' + ("" if show else " hidden") + f">{plan}{asof}{ban}"
            f'<div class="rfg">{"".join(cards)}</div></div>')


CSS = """
.rfhd{display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 10px;margin:0 0 6px}
#rfmk{margin:4px 0 10px}
.rfas{font-size:12px;color:var(--mut);margin:0 0 6px}
.rfnow{border-left:4px solid var(--t4);background:var(--sbg);padding:8px 12px;border-radius:0 10px 10px 0;margin:0 0 12px;font-size:14px;line-height:1.7}
.rfnow b{color:var(--t4)}.rfnow ul{margin:2px 0 0;padding-left:18px}.rfnow li{margin:2px 0}
.rfnow.rfnone{border-left-color:var(--line2);background:var(--card2)}.rfnow.rfnone b{color:var(--ink)}
.rfnow.rfside{border-left-color:var(--t3);background:var(--curbg)}.rfnow.rfside b{color:var(--ink)}.rfnow li.rfi{color:var(--ink2)}
.rfg{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;align-items:start}
.rfc{border:1px solid var(--line);border-radius:12px;padding:12px 14px;background:var(--panel);display:flex;flex-direction:column;gap:7px;min-width:0}
.rfc.on{border-color:var(--t4);box-shadow:inset 3px 0 0 var(--t4)}
.rfq{font-size:14px;color:var(--ink2);display:flex;gap:8px;align-items:baseline;line-height:1.5}
.rfq i{font-style:normal;font-size:11.5px;color:var(--mut);border:1px solid var(--line2);border-radius:999px;padding:0 7px;flex:none}
.rfa{font-size:22px;font-weight:700;line-height:1.25;color:var(--ink)}
.rfa.yes{color:var(--t4)}.rfa.mid{color:var(--t3)}
.rfa small{font-size:14px;font-weight:400;color:var(--ink2);margin-left:8px}
.rfc p{margin:0}.rfl{font-size:14px;line-height:1.65}.rfs{font-size:13px;color:var(--ink2);line-height:1.7}
.rfbh{font-size:12px;color:var(--mut);margin-top:2px}
.rfbars{display:grid;grid-template-columns:auto minmax(40px,1fr) auto;gap:4px 8px;align-items:center;font-size:13px}
.rfbl{color:var(--ink2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:15em}
.rfbv{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.rfbt{display:block;height:10px}.rfbb{display:block;height:10px;border-radius:0 4px 4px 0;background:var(--line2)}
.rfbb.hi{background:var(--t4)}.rfbb.ac{background:var(--acc)}
.rftwo{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.rfnw{font-size:13px;padding:5px 9px;border-radius:8px;background:var(--card2);line-height:1.6}
.rfnw.risk{background:var(--sbg)}.rfnw.side{background:var(--curbg)}.rfnw .rfy{color:var(--t4)}
.rfdt{font-size:13px}.rfdt>summary{cursor:pointer;color:var(--acc)}
.rftw{overflow-x:auto;margin:6px 0 2px}
.rftb{border-collapse:collapse;width:100%;font-size:12.5px}
.rftb th,.rftb td{padding:3px 6px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
.rftb th{color:var(--ink2);font-weight:600}.rftb .l{text-align:left;white-space:normal}.rftb small{display:block;font-size:11px;color:var(--mut)}
.rftb .mu{color:var(--mut)}.rftb tr.rfbhr td{font-weight:600}
.rfln{font-size:12px;color:var(--acc);text-decoration:none;white-space:nowrap}
.rfa.ac{color:var(--acc)}
.rfnote{font-size:12px;color:var(--mut);margin:4px 0 0;line-height:1.65}
.rffoot{font-size:12.5px;color:var(--mut);margin:12px 0 0;line-height:1.7}
.rffull{margin:16px 0 0;border:1px solid var(--line);border-radius:12px;background:var(--panel)}
.rffull>summary{cursor:pointer;padding:10px 14px;font-size:14px;color:var(--ink2)}.rffull>summary b{color:var(--ink)}
.rffull[open]>summary{border-bottom:1px solid var(--line)}
.rffb{padding:8px 14px 14px}
@media (max-width:760px){.rfg{grid-template-columns:1fr}}
@media (max-width:520px){.rftwo{grid-template-columns:1fr}.rfa{font-size:20px}.rfc{padding:11px 11px}.rfbl{max-width:11em}
.rfbw{grid-template-columns:minmax(40px,1fr) auto;row-gap:1px}.rfbw .rfbl{grid-column:1/-1;max-width:none;white-space:normal;margin-top:3px}
.rftk tr:first-child{display:none}
.rftk tr{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 10px;padding:5px 0;border-bottom:1px solid var(--line)}
.rftk td{border:0;padding:1px 0;text-align:left;white-space:normal}.rftk td.l{grid-column:1/-1;font-weight:600}
.rftk td[data-h]::before{content:attr(data-h) "：";color:var(--mut);font-size:11.5px}.rftk td.l[data-h]{font-weight:400}
.rftk td.rfkx{display:none}}
"""
