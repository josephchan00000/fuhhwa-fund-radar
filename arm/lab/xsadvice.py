"""總經策略（原大神策略）整理成跟個股策略同樣的形狀，給策略頁「總經策略」用（docs/lab_strategy_ia_plan.md）。

2026-10-22 使用者：「策略點進去，分成總經策略跟個股策略，然後你的總經策略的排版設計要比照個股策略那邊的方式跟呈現邏輯」，
選了「先選市場」「兩頁跟個股一樣」。每個市場一份：
  cards  ★ 好策略、● 可參考，依推薦順序（做法／隱含獲利／現在／下一次；時間軸也讀這裡）
  cal    時間表：照規則哪天收盤要買賣（下一個交易日要做的事、時間軸的日期）
  book   比較表：這個市場全部策略（○ 不推薦、— 次數不夠放後面）
  sum    摘要（推薦幾條、下一個交易日要動作幾條、持有中幾條、下一次排定）
數字與判定全部來自 xstrat（這裡不另外算判定），只整理、排順序、寫一句話。只描述照規則做過去的成績，不寫建議。
"""
from __future__ import annotations

from datetime import date

from . import xstratpage as XSP
from . import xstratspec as S

TIER_ORD = {"good": 0, "ref": 1, "none": 2, "few": 3}
REC = ("good", "ref")
UNIT = {"trade": "筆", "dip": "次", "alloc": "段"}
SOON = 45                     # 時間軸、下一次排定看多遠（日曆天；Halloween 4 月底的賣出照樣列在卡片的「現在」）


def _p(v, k: int = 1):
    """比例 → 百分比（四捨五入）。"""
    return None if v is None else round(float(v) * 100, k)


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def how(k: str, mk: str) -> str:
    """做法：一句話（規則細節在「規則與成績」）。參數讀規格，不寫死。"""
    p = S.BY_KEY[k]["p"]
    H = S.BY_KEY[k].get("H")
    hold = XSP.HN.get(H, f"{H} 個交易日") if H else ""
    same = S.lag(mk, k) == 0 if S.BY_KEY[k]["kind"] == "trade" and k != "tom" else False
    when = "訊號當天收盤前用台指期買賣" if same else "隔天收盤買賣"
    if k == "rsi2":
        return (f"收盤在 {p['ma']} 日均線上、2 日 RSI 低於 {p['rsi_max']} 就買，收盤站上 {p['exit_ma']} 日均線就賣"
                f"（{when}）。")
    if k == "vixs":
        return (f"VIX 連 {p['days']} 天比自己的 {p['vix_ma']} 日均線高 {p['stretch'] * 100:.0f}% 以上、指數在 {p['ma']} 日均線上就買，"
                f"2 日 RSI 高於 {p['exit_rsi']} 就賣（{when}）。")
    if k == "tom":
        fut = "（台指期）" if mk == "tw" else ""
        return f"每個月倒數第 {p['before'] + 1} 個交易日收盤買，下個月第 {p['after']} 個交易日收盤賣{fut}。"
    if k == "coppock":
        return f"每個月底看 Coppock 曲線：在 0 以下由下往上轉就買（隔天收盤），抱 {hold}。"
    if k == "vix40":
        vt = "前一個美股交易日的 VIX" if mk == "tw" else "VIX"
        return f"{vt} 收盤衝上 {p['level']}（之前 {p['reset']} 個交易日都沒有）就買（隔天收盤），抱 {hold}。"
    if k == "zweig":
        return (f"上漲家數占比的 {p['ema']} 日平均在 {p['days']} 個交易日內從 {p['lo'] * 100:.0f}% 以下衝上 {p['hi'] * 100:.1f}% 以上就買"
                f"（隔天收盤），抱 {hold}。")
    if k == "ftd":
        return (f"從 52 週高點跌 {p['corr'] * 100:.0f}% 以上之後，反彈第 {p['day']} 天起出現一天大漲 {p['up'] * 100:.2f}% 以上、"
                f"量比前一天大就買（隔天收盤），抱 {hold}。")
    if k == "dev60":
        return f"收盤比 {p['ma']} 日均線（季線）低 {-p['th'] * 100:.0f}% 以上就買（隔天收盤），抱 {hold}。"
    if k == "mmr":
        return f"大盤融資維持率第一次跌破 {p['level']}%（之前 {p['reset']} 個交易日都在上面）就買（隔天收盤），抱 {hold}。"
    if k == "mflush":
        return (f"指數從近 {p['win']} 個交易日高點跌 {p['dd'] * 100:.0f}% 以上、融資減少的比例第一次比指數跌幅大就買"
                f"（隔天收盤），抱 {hold}。")
    if k == "lowry":
        return (f"出現 {p['th'] * 100:.0f}% 下跌日之後 {p['win']} 個交易日內，出現 {p['th'] * 100:.0f}% 上漲日"
                f"（或連兩天 {p['th2'] * 100:.0f}% 上漲日）就買（隔天收盤），抱 {hold}。")
    if k == "hal":
        return "每年 10 月最後一個交易日收盤買、4 月最後一個交易日收盤賣，5～10 月空手。"
    if k == "faber":
        return f"每個月底收盤在 {p['n']} 個月均線上就持有、跌破就空手（隔天收盤買賣）。"
    if k == "ma200":
        return f"每天收盤在 {p['n']} 日均線上就持有、跌破就空手（隔天收盤買賣）。"
    if k == "mom12":
        return f"每個月底比 {p['n']} 個月前高就持有、比較低就空手（隔天收盤買賣）。"
    return S.BY_KEY[k]["logic"]


def exit_rule(k: str) -> str:
    """持有中、還沒有排定賣出日的：什麼時候賣。"""
    p = S.BY_KEY[k]["p"]
    if k == "rsi2":
        return f"收盤站上 {p['exit_ma']} 日均線就賣"
    if k == "vixs":
        return f"2 日 RSI 高於 {p['exit_rsi']} 就賣"
    if k == "ma200":
        return f"收盤跌破 {p['n']} 日均線就賣（隔天收盤）"
    if k == "faber":
        return f"月底跌破 {p['n']} 個月均線就賣（隔天收盤）"
    if k == "mom12":
        return f"月底比 {p['n']} 個月前低就賣（隔天收盤）"
    if k == "hal":
        return "4 月最後一個交易日收盤賣"
    H = S.BY_KEY[k].get("H")
    return f"抱 {XSP.HN.get(H, f'{H} 個交易日')}收盤賣" if H else "照規則賣"


def due(r: dict) -> tuple[str, str] | None:
    """下一個照規則要做的事：(日期, 買進／賣出／可能買進)。沒有排定、也沒有訊號 → None。"""
    n, k = r["now"], r["k"]
    st = n["st"]
    if k == "tom":
        if st in ("buy", "wait"):
            return (n["ed"], "買進") if n.get("ed") else None
        return (n["qd"], "賣出") if n.get("qd") else None
    if k == "hal":
        if not n.get("sw"):
            return None
        return n["sw"], ("買進" if st in ("turn_in", "out") else "賣出")
    if not n.get("nx"):
        return None
    if r["kind"] == "dip":
        if st == "buy":
            return n["nx"], "買進"
        return (n["qd"], "賣出") if st == "hold" and n.get("qd") else None
    if st in ("buy", "turn_in"):
        return n["nx"], "買進"
    if st in ("sell", "turn_out"):
        return n["nx"], "賣出"
    if st == "near":
        return n["nx"], "可能買進"
    return None


def edge(r: dict) -> float | None:
    """比對照好多少：交易型、落底型＝賺錢比例多幾個百分點；進出型＝最大回撤少幾成。"""
    f = r["full"]
    if r["kind"] in ("trade", "dip"):
        return None if not f.get("n") or f.get("base") is None else float(f["win"] - f["base"])
    b = r["bh"]
    return None if not b.get("mdd") else float(1.0 - f["mdd"] / b["mdd"])


def rank_key(r: dict) -> tuple:
    """推薦順序：★ 在前、● 在後；同一級照類型（短線 → 落底 → 季節性 → 風險控制），同類型依比對照好多少。"""
    e = edge(r)
    return (TIER_ORD[r["tier"]], S.GROUP_ORDER.index(r["grp"]), -(e if e is not None else -9.0),
            [s["k"] for s in S.STRATS].index(r["k"]))


def why(r: dict) -> str:
    """推薦順序旁邊那一句（過去的成績，和對照比）。"""
    f, b = r["full"], r["bh"]
    if r["kind"] == "trade":
        if not f.get("n"):
            return "評估期間沒有交易"
        return f"勝率 {f['win'] * 100:.0f}%（隨便挑同樣天數 {f['base'] * 100:.0f}%），{f['n']} 筆"
    if r["kind"] == "dip":
        if not f.get("n"):
            return "評估期間沒有出現過"
        hn = XSP.HN.get(r["H"], f"{r['H']} 個交易日")
        bm = "" if f.get("bmed") is None else f"（隨便挑一天 {XSP.pc(f['bmed'], 1, sign=True)}）"
        return (f"抱 {hn}賺錢 {f['win'] * 100:.0f}%（隨便挑一天 {f['base'] * 100:.0f}%）、"
                f"中位數 {XSP.pc(f['med'], 1, sign=True)}{bm}，{f['n']} 次")
    return (f"最大回撤 {f['mdd'] * 100:.0f}%（買進持有 {b['mdd'] * 100:.0f}%），"
            f"年化 {XSP.pc(f['cagr'])}（買進持有 {XSP.pc(b['cagr'])}）")


def _spans_stats(tr: list) -> dict:
    """進出型每一段（已經賣出的）：段數、平均、中位、賺錢比例、最差（%）。"""
    rs = sorted(float(x[5]) for x in tr if x[2] is not None and x[5] is not None)
    if not rs:
        return {"n": 0}
    m = len(rs)
    med = rs[m // 2] if m % 2 else (rs[m // 2 - 1] + rs[m // 2]) / 2
    return {"n": m, "avg": _p(sum(rs) / m, 2), "med": _p(med, 2), "win": _p(sum(1 for v in rs if v > 0) / m, 0), "lo": _p(rs[0])}


def stats(r: dict) -> dict:
    """隱含獲利與比較表共用的數字（%）：每筆／每次／每段的平均、中位、賺錢比例、最差，全部資金照做的年化與最大回撤，
    對照（交易型＝隨便挑同樣天數、落底型＝隨便挑一天抱一樣久、進出型＝買進持有）。"""
    f, b, kind = r["full"], r["bh"], r["kind"]
    out = {"unit": UNIT[kind], "d0": r["a"], "d1": r["z"], "bcagr": _p(b["cagr"]), "bmdd": _p(b["mdd"], 0)}
    if kind == "trade":
        if f.get("n"):
            out.update({"n": f["n"], "avg": _p(f["avg"], 2), "med": _p(f.get("med"), 2), "win": _p(f["win"], 0),
                        "base": _p(f.get("base"), 0), "lo": _p(f["worst"]), "hold": round(f["hold"], 1),
                        "cagr": _p(f.get("cagr")), "mdd": _p(f.get("mdd"), 0), "expo": _p(f.get("expo"), 0)})
        else:
            out["n"] = 0
    elif kind == "dip":
        c = r.get("curve") or {}
        out.update({"H": r["H"], "hn": XSP.HN.get(r["H"], f"{r['H']} 個交易日")})
        if f.get("n"):
            out.update({"n": f["n"], "avg": _p(f.get("avg")), "med": _p(f.get("med")), "win": _p(f.get("win"), 0),
                        "base": _p(f.get("base"), 0), "bmed": _p(f.get("bmed")), "lo": _p(f.get("worst")),
                        "mae": _p(f.get("mae")), "cagr": _p(c.get("cagr")), "mdd": _p(c.get("mdd"), 0), "expo": _p(c.get("expo"), 0)})
        else:
            out["n"] = 0
    else:
        out.update(_spans_stats(r.get("tr") or []))
        out.update({"cagr": _p(f["cagr"]), "mdd": _p(f["mdd"], 0), "expo": _p(f.get("expo"), 0),
                    "sw": None if f.get("sw") is None else round(f["sw"], 1)})
    return out


def _tl(r: dict, d0: str) -> dict:
    """時間軸（同個股策略的畫法）：held＝持有中的條（d＝排定賣出日，沒有＝照規則賣、畫到右邊）、buy＝排定的買進、
    next＝接近訊號（可能買進）、adj＝每個月底要看一次的日子。"""
    n, k, st = r["now"], r["k"], r["now"]["st"]
    out: dict = {"held": [], "buy": [], "next": None, "adj": []}
    q = due(r)
    if st in XSP.HELD:
        sell = q[0] if q and q[1] == "賣出" else None
        out["held"].append({"ent": n.get("ed"), "d": sell, "r": _p(n.get("ret")), "px0": n.get("ep"), "px": n.get("px"),
                            "how": "" if sell else exit_rule(k)})
    elif q and q[1] == "買進":
        sell = n.get("qd") if k == "tom" else None
        out["buy"].append({"d": q[0], "out": sell, "how": "" if sell else exit_rule(k)})
    elif q and q[1] == "可能買進":
        out["next"] = {"d": q[0]}
    chk = n.get("chk")
    if chk and chk >= d0 and not (q and q[0] == chk):
        out["adj"].append({"d": chk, "note": "月底看"})
    return out


def card(r: dict, rank: int) -> dict:
    k, mk = r["k"], r["mk"]
    sp = S.BY_KEY[k]
    n = r["now"]
    st = n["st"]
    return {"k": k, "rank": rank, "tier": r["tier"], "name": sp["name"], "grp": sp["grp"], "gname": S.GROUPS[sp["grp"]],
            "kind": r["kind"], "who": sp["who"], "why": why(r), "how": how(k, mk), "logic": sp["logic"], "exp": stats(r),
            "st": st, "tag": XSP.TAG[st], "sk": "a" if st in XSP.ACT else "h" if st in XSP.HELD else "f",
            "now": XSP.now_text(r), "nv": XSP.now_short(r), "tl": _tl(r, n["d"])}


def market(mk: str, M: dict) -> dict:
    rs = sorted(M.values(), key=rank_key)
    rec = [r for r in rs if r["tier"] in REC]
    cards = [card(r, i + 1) for i, r in enumerate(rec)]
    d0 = max(r["now"]["d"] for r in rs)
    nx = next((r["now"].get("nx") for r in rs if r["now"].get("nx")), None)
    cal = []
    for c, r in zip(cards, rec):
        q = due(r)
        if q and q[0] and _days(d0, q[0]) <= SOON:
            cal.append({"d": q[0], "act": q[1], "k": c["k"], "name": c["name"], "rank": c["rank"]})
        if r["k"] == "tom" and q and q[1] == "買進" and r["now"].get("qd") and _days(d0, r["now"]["qd"]) <= SOON:
            cal.append({"d": r["now"]["qd"], "act": "賣出", "k": c["k"], "name": c["name"], "rank": c["rank"]})
    cal.sort(key=lambda e: (e["d"], e["rank"]))
    book = []
    for i, r in enumerate(rs):
        book.append({"k": r["k"], "rank": i + 1 if r["tier"] in REC else None, "tier": r["tier"], "name": S.BY_KEY[r["k"]]["name"],
                     "grp": r["grp"], "gname": S.GROUPS[r["grp"]], "kind": r["kind"], "why": why(r), "exp": stats(r),
                     "st": r["now"]["st"], "tag": XSP.TAG[r["now"]["st"]]})
    act = sorted({e["k"] for e in cal if e["d"] == nx})
    later = [e for e in cal if nx and e["d"] > nx and e["act"] in ("買進", "賣出")]
    summ = {"n": len(cards), "ng": sum(1 for c in cards if c["tier"] == "good"), "nr": sum(1 for c in cards if c["tier"] == "ref"),
            "act": len(act), "held": sum(1 for c in cards if c["st"] in XSP.HELD),
            "next": later[0] if later else None, "nlow": len(rs) - len(rec)}
    return {"d": d0, "nx": nx, "name": XSP.MK_NAMES[mk], "cards": cards, "cal": cal, "book": book, "sum": summ}


def build(R: dict | None = None) -> dict:
    """{"mks": [市場], "mkn": {市場: 名稱}, "m": {市場: market()}, "ver": 規格版本, "rule": 判定門檻}。"""
    R = XSP.results() if R is None else R
    m = {mk: market(mk, R[mk]) for mk in S.MARKETS if R.get(mk)}
    rule = {"n": S.TR_N_MIN, "win": round(S.TR_WIN * 100), "edge": round(S.TR_EDGE * 100), "n10": S.TR_N10,
            "dn": S.DIP_N_MIN, "dwin": round(S.DIP_WIN * 100), "dedge": round(S.DIP_EDGE * 100), "dn10": S.DIP_N10,
            "dmx": S.DIP_MED_X, "dadd": round(S.DIP_MED_ADD * 100), "mdd": round((1 - S.AL_MDD) * 100, 1),
            "grid": "2/3", "draws": S.LUCK_DRAWS}
    return {"mks": list(m), "mkn": dict(XSP.MK_NAMES), "m": m, "ver": S.VER, "rule": rule}
