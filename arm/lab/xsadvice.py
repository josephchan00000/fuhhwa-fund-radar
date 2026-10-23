"""總經策略（原大神策略）整理成跟個股策略同樣的形狀，給策略頁「總經策略」用（docs/lab_strategy_ia_plan.md）。

2026-10-22 使用者：「策略點進去，分成總經策略跟個股策略，然後你的總經策略的排版設計要比照個股策略那邊的方式跟呈現邏輯」，
選了「先選市場」「兩頁跟個股一樣」。每個市場一份：
  cards  ★ 好策略、● 可參考，依推薦順序（做法／隱含獲利／現在／下一次；時間軸也讀這裡）
  cal    時間表：照規則哪天收盤要買賣（下一個交易日要做的事、時間軸的日期）
  book   比較表：這個市場全部策略（○ 不推薦、— 次數不夠放後面）；每一條帶 ex＝說明卡（結論／怎麼做／逐年報酬／風險；判定依據在 x9xh.json）
  sum    摘要（推薦幾條、下一個交易日要動作幾條、持有中幾條、下一次排定）
數字與判定全部來自 xstrat（這裡不另外算判定），只整理、排順序、寫一句話。只描述照規則做過去的成績，不寫建議。
"""
from __future__ import annotations

import math
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from . import robust as RB
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
    """推薦順序旁邊那一句（過去的成績，和對照比；數字＝stats，和卡片、逐筆交易同一份）。"""
    e = stats(r)
    if r["kind"] == "trade":
        if not e.get("n"):
            return "評估期間沒有交易"
        return f"勝率 {e['win']}%（隨便挑同樣天數 {_pp(e['base'], 0, sign=False)}），{e['n']} 筆"
    if r["kind"] == "dip":
        if not e.get("n"):
            return "評估期間沒有出現過"
        bm = "" if e.get("bmed") is None else f"（隨便挑一天 {_pp(e['bmed'])}）"
        return f"抱 {e['hn']}賺錢 {e['win']}%（隨便挑一天 {_pp(e['base'], 0, sign=False)}）、中位數 {_pp(e['med'])}{bm}，{e['n']} 次"
    return f"最大回撤 {_pp(e['mdd'], 0, sign=False)}（買進持有 {_pp(e['bmdd'], 0, sign=False)}），年化 {_pp(e['cagr'], sign=False)}（買進持有 {_pp(e['bcagr'], sign=False)}）"


def _q(x, d: int):
    """四捨五入到 d 位，和頁面的 toLocaleString 一樣：先取最短的十進位寫法（0.345 不是 0.34499…），再 .5 進位
    （Python 的 round 是 .5 取偶、而且看二進位的真值，0.345 會變 0.34）。"""
    return None if x is None else float(Decimal(repr(float(x))).quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP))


def _list_stats(tr: list, d: int) -> dict:
    """已經賣出的每一筆（每一次、每一段；x9xh.json 那一份，報酬取到小數第 5 位）→ 筆數、平均、中位、賺錢比例、最差（%）。
    和頁面「逐筆交易」上方那一句用同一份數字、同一個算法（依時間順序加總、.5 進位），所以卡片上的數字和逐筆重算的一定一樣。
    d＝頁面顯示的小數位（交易型 2、落底型與進出型 1）。"""
    rs = [t[5] * 100 for t in tr if t[2] is not None and t[5] is not None]
    if not rs:
        return {"n": 0}
    m = len(rs)
    srt = sorted(rs)
    med = srt[m // 2] if m % 2 else (srt[m // 2 - 1] + srt[m // 2]) / 2
    return {"n": m, "avg": _q(sum(rs) / m, d), "med": _q(med, d), "win": math.floor(100 * sum(1 for v in rs if v > 0) / m + 0.5),
            "lo": _q(min(rs), 1), "trim": _q(RB.trim_mean(rs), d), "lbo": _q(RB.lbo_mean(rs), d)}   # VER 6：排除極端、去掉最好一筆


def _pp(v, d: int = 1, sign: bool = True) -> str:
    """百分比數字（已經是 %）→ 文字。"""
    if v is None:
        return "—"
    s = f"{abs(v):.{d}f}%"
    return (("+" if v > 0 else "−" if v < 0 else "") if sign else ("−" if v < 0 else "")) + s


def stats(r: dict) -> dict:
    """隱含獲利與比較表共用的數字（%）：每筆／每次／每段的平均、中位、賺錢比例、最差，全部資金照做的年化與最大回撤，
    對照（交易型＝隨便挑同樣天數、落底型＝隨便挑一天抱一樣久、進出型＝買進持有）。"""
    f, b, kind = r["full"], r["bh"], r["kind"]
    out = {"unit": UNIT[kind], "d0": r["a"], "d1": r["z"], "bcagr": _p(b["cagr"]), "bmdd": _p(b["mdd"], 0),
           "nt": len(r.get("tr") or [])}                       # 逐筆交易的筆數（進出型含還在持有的那一段）
    L = _list_stats(r.get("tr") or [], 2 if kind == "trade" else 1)          # 每筆的平均、中位、賺錢比例、最差（和逐筆交易同一份）
    if kind == "trade":
        if f.get("n"):
            out.update(L)
            out.update({"base": _p(f.get("base"), 0), "hold": round(f["hold"], 1),
                        "cagr": _p(f.get("cagr")), "mdd": _p(f.get("mdd"), 0), "expo": _p(f.get("expo"), 0)})
        else:
            out["n"] = 0
    elif kind == "dip":
        c = r.get("curve") or {}
        out.update({"H": r["H"], "hn": XSP.HN.get(r["H"], f"{r['H']} 個交易日")})
        if f.get("n"):
            out.update(L)
            out.update({"base": _p(f.get("base"), 0), "bmed": _p(f.get("bmed")), "mae": _p(f.get("mae")),
                        "cagr": _p(c.get("cagr")), "mdd": _p(c.get("mdd"), 0), "expo": _p(c.get("expo"), 0)})
        else:
            out["n"] = 0
    else:
        out.update(L)
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


# ── 說明卡（規則與成績；比照個股策略的結論／怎麼做／過去成績／逐筆交易／風險，判定依據收起來） ──────────────

def _yr_raw(r: dict) -> list[tuple]:
    """逐年（月底取樣的淨值）：[(年, 這一年最後一個點的策略淨值, 買進持有淨值)]，第一年的起點＝評估起點的 1。"""
    E = r.get("eq") or {}
    d, s, b = E.get("d") or [], E.get("s") or [], E.get("b") or []
    last: dict = {}
    for i, t in enumerate(d):
        if s[i] is not None and b[i] is not None:
            last[t[:4]] = i
    return [(y, float(s[last[y]]), float(b[last[y]])) for y in sorted(last)]


def _part_last(r: dict, yr: list) -> bool:
    """最後一年還沒過完：下一個交易日還在同一年（沒有下一個交易日＝看資料最後一天是不是 12 月）。"""
    z, nx = r["z"], (r.get("now") or {}).get("nx")
    return bool(yr) and yr[-1][0] == z[:4] and (nx[:4] == z[:4] if nx else z[5:7] != "12")


def yearly(r: dict) -> dict | None:
    """逐年報酬（%）：全部資金照做 vs 買進持有（同個股策略的逐年報酬表）。每年最後一個點 ÷ 前一年最後一個點；
    第一年從評估起點起算。{"y0": 第一年, "s": [策略], "b": [買進持有], "to": 今年還沒過完＝資料最後一天（頁面寫「到 M/D」）}。"""
    raw = _yr_raw(r)
    if not raw:
        return None
    out = {"y0": raw[0][0], "s": [], "b": []}
    ps, pb = 1.0, 1.0
    for y, s, b in raw:
        out["s"].append(round((s / ps - 1) * 100, 1))
        out["b"].append(round((b / pb - 1) * 100, 1))
        ps, pb = s, b
    if _part_last(r, raw):
        out["to"] = r["z"]
    return out


def ex_best(r: dict) -> dict | None:
    """成績集中在哪一年（同個股策略風險欄）：完整的年份裡策略最好的那一年；去掉這一年之後的年化（買進持有也去掉同一年）。
    完整的年份不到 5 年＝不算。"""
    raw = _yr_raw(r)
    if not raw:
        return None
    a, z = r["a"], r["z"]
    rows, ps, pb = [], 1.0, 1.0
    for i, (y, s, b) in enumerate(raw):
        full = not (i == 0 and a[5:7] != "01") and not (i == len(raw) - 1 and _part_last(r, raw))
        rows.append((y, s / ps, b / pb, full))
        ps, pb = s, b
    full = [x for x in rows if x[3]]
    if len(full) < 5:
        return None
    y, gs, gb, _ = max(full, key=lambda x: x[1])
    yrs = _days(a, z) / 365.25
    if yrs <= 1.5:
        return None
    S_end, B_end = raw[-1][1], raw[-1][2]
    return {"y": y, "r": round((gs - 1) * 100, 1), "cagr": round(((S_end / gs) ** (1 / (yrs - 1)) - 1) * 100, 1),
            "bcagr": round(((B_end / gb) ** (1 / (yrs - 1)) - 1) * 100, 1)}


def _fail(r: dict) -> str:
    """全期間沒過關的主要原因（一句）。"""
    f, kind = r["full"], r["kind"]
    pc = XSP.pc
    if kind == "trade":
        if f["win"] < S.TR_WIN:
            return f"勝率 {pc(f['win'], 0)}，不到 {S.TR_WIN * 100:.0f}%"
        if f.get("base") is not None and f["win"] - f["base"] < S.TR_EDGE:
            return f"勝率只比隨便挑同樣天數高 {(f['win'] - f['base']) * 100:.1f} 個百分點，要高 {S.TR_EDGE * 100:.0f} 以上"
        return "平均每筆沒有賺錢"
    if kind == "dip":
        if f.get("win") is not None and f["win"] < S.DIP_WIN:
            return f"抱完賺錢的比例 {pc(f['win'], 0)}，不到 {S.DIP_WIN * 100:.0f}%"
        if f.get("base") is not None and f["win"] < f["base"]:          # xstratspec VER 6：不比隨便挑一天差
            e = (f["base"] - f["win"]) * 100
            return (f"抱完賺錢的比例 {pc(f['win'], 1)}，比隨便挑一天（{pc(f['base'], 1)}）低 "
                    f"{e:.{2 if e < 0.05 else 1}f} 個百分點")
        if f.get("med") is None or f["med"] <= 0:
            return f"扣成本後的報酬中位數 {pc(f.get('med'), 1, sign=True)}，沒有賺錢"
        return f"排除極端（去掉最好和最差幾次）的平均 {pc(f.get('trim'), 1, sign=True)}，沒有賺錢"
    b = r["bh"]
    if f["mdd"] > S.AL_MDD * b["mdd"]:
        return f"最大回撤 {pc(f['mdd'], 0)}，比買進持有（{pc(b['mdd'], 0)}）少不到三分之一"
    return "年化 ÷ 最大回撤輸給買進持有"


def fail_txt(r: dict) -> str | None:
    """沒過的原因一句（配置頁・策略總覽「淘汰」那一列用）：次數不夠或全期間沒過的主要原因；過了回 None。"""
    if r["tier"] == "few":
        n = (r.get("full") or {}).get("n")
        return f"次數不夠（{n} 次）" if n is not None else "次數不夠"
    if r["tier"] == "none":
        return _fail(r)
    return None


def tier_line(r: dict) -> str:
    """判定的一句話：過了哪幾項、沒過哪一項。"""
    t, kind, f = r["tier"], r["kind"], r["full"]
    if t == "few":
        if kind == "alloc":
            return f"評估期間不到 {S.AL_YEARS_MIN} 年，不判定。"
        need, u = (S.TR_N_MIN if kind == "trade" else S.DIP_N_MIN), UNIT[kind]
        return f"全期間只有 {f.get('n', 0)} {u}（要 {need} {u}以上），不判定。"
    if t == "none":
        return f"全期間沒過關：{_fail(r)}。不列在「這一期」。"
    g = r["grid"]
    k = sum(1 for x in g if x["ok"])
    if t == "good":
        rec = "近 10 年也過關" if r["rec_ok"] else "近 10 年次數太少、不看"
        return f"全期間過關，{rec}，換附近的參數 {k}/{len(g)} 組也過關。"
    miss = []
    if r["rec_ok"] is False:
        miss.append("近 10 年沒過關")
    if r["grid_ok"] < S.GRID_OK - 1e-12:
        miss.append(f"換附近的參數只有 {k}/{len(g)} 組過關（要 2/3 以上）")
    return f"全期間過關，但{'、'.join(miss)}。"


def concl(r: dict) -> str:
    """結論：照規則做過去的成績（扣成本）一段（同個股策略的結論欄；數字＝stats，和卡片、逐筆交易同一份）；判定那一句另外放（tier_line）。"""
    e, kind = stats(r), r["kind"]
    span = f"{r['a'][:7]}～{r['z'][:7]}"
    if kind == "trade":
        if not e.get("n"):
            return f"{span} 沒有交易。"
        return (f"{span} 照規則做 {e['n']} 筆：每筆平均 {_pp(e['avg'], 2)}、中位 {_pp(e['med'], 2)}，"
                f"{e['win']}% 賺錢（隨便挑同樣天數 {_pp(e['base'], 0, sign=False)}），最差一筆 {_pp(e['lo'])}；"
                f"排除極端的平均 {_pp(e.get('trim'), 2)}、去掉最好一筆 {_pp(e.get('lbo'), 2)}。"
                f"全部資金照做年化 {_pp(e['cagr'])}（買進持有 {_pp(e['bcagr'])}），"
                f"資金從高點最多跌 {_pp(e['mdd'], 0, sign=False)}（買進持有 {_pp(e['bmdd'], 0, sign=False)}），有部位的時間 {_pp(e['expo'], 0, sign=False)}。")
    if kind == "dip":
        if not e.get("n"):
            return f"{span} 沒有出現過。"
        return (f"{span} 出現 {e['n']} 次，每次抱 {e['hn']}：平均 {_pp(e['avg'])}、中位 {_pp(e['med'])}，"
                f"{e['win']}% 賺錢（隨便挑一天抱一樣久 {_pp(e['base'], 0, sign=False)}、中位 {_pp(e['bmed'])}），"
                f"最差一次 {_pp(e['lo'])}；排除極端的平均 {_pp(e.get('trim'))}、去掉最好一次 {_pp(e.get('lbo'))}。"
                f"全部資金照做年化 {_pp(e['cagr'])}（買進持有 {_pp(e['bcagr'])}），"
                f"有部位的時間 {_pp(e['expo'], 0, sign=False)}。")
    seg = f"{e['n']} 段持有平均 {_pp(e['avg'])}、中位 {_pp(e['med'])}、{e['win']}% 賺錢，" if e.get("n") else ""
    return (f"{span} 全部資金照做年化 {_pp(e['cagr'])}（買進持有 {_pp(e['bcagr'])}），"
            f"資金從高點最多跌 {_pp(e['mdd'], 0, sign=False)}（買進持有 {_pp(e['bmdd'], 0, sign=False)}）；{seg}"
            f"有部位的時間 {_pp(e['expo'], 0, sign=False)}、一年進出約 {e.get('sw') or 0:.1f} 次。")


def risk(r: dict) -> list[str]:
    """風險（同個股策略的風險欄）：最大回撤、最差一筆、成績集中在哪一年、近 10 年、次數、打亂測試、價格口徑。"""
    mk, k, kind, f = r["mk"], r["k"], r["kind"], r["full"]
    pc, md = XSP.pc, XSP.md
    e = stats(r)                                            # 和結論、卡片同一份數字
    out = []
    if e.get("mdd") is not None:
        out.append(f"全部資金照做，資金從高點最多跌 {_pp(e['mdd'], 0, sign=False)}（買進持有 {_pp(e['bmdd'], 0, sign=False)}）")
    closed = [t for t in (r.get("tr") or []) if t[2] is not None and t[5] is not None]
    if closed:
        w = min(closed, key=lambda t: t[5])
        u = {"trade": "一筆", "dip": "一次", "alloc": "一段"}[kind]
        out.append(f"最差{u} {_pp(e['lo'])}（{md(w[0])} 買、{md(w[2])} 賣）")
    if kind == "dip" and closed:
        m = max(closed, key=lambda t: t[6] or 0)
        out.append(f"抱固定時間、中途不設停損：中途最多跌中位 {_pp(e.get('mae'), 1, sign=False)}，最多一次跌 {pc(m[6], 1)}（{md(m[0])} 買）")
    X = ex_best(r) if kind != "dip" else None
    if X:
        out.append(f"成績集中在少數年份：最好的 {X['y']} 年 {X['r']:+.1f}%；去掉這一年，年化 {X['cagr']:+.1f}%"
                   f"（買進持有也去掉這一年 {X['bcagr']:+.1f}%）")
    if kind == "trade" and e.get("lbo") is not None and e.get("avg") and e["avg"] > 0 and e["lbo"] < e["avg"] / 2:
        out.append(f"成績靠少數幾筆：每筆平均 {_pp(e['avg'], 2)}，去掉最好一筆只剩 {_pp(e['lbo'], 2)}")
    if kind == "dip" and len(closed) >= 3:
        best = max(closed, key=lambda t: t[5])
        rest = [t[5] for t in closed if t is not best]
        out.append(f"成績集中在少數幾次：最好的一次 {pc(best[5], 1, sign=True)}（{md(best[0])} 買）；去掉這一次，"
                   f"每次平均 {pc(sum(rest) / len(rest), 1, sign=True)}、{pc(sum(1 for v in rest if v > 0) / len(rest), 0)} 賺錢")
    rc = r.get("rec") or {}
    if r.get("rec_ok") is False:
        if kind == "trade":
            out.append(f"近 10 年沒過關：{rc.get('n', 0)} 筆，勝率 {pc(rc.get('win'), 0)}（隨便挑同樣天數 {pc(rc.get('base'), 0)}）、"
                       f"平均每筆 {pc(rc.get('avg'), 2, sign=True)}")
        elif kind == "dip":
            out.append(f"近 10 年沒過關：{rc.get('n', 0)} 次，抱完賺錢 {pc(rc.get('win'), 0)}（隨便挑一天 {pc(rc.get('base'), 0)}）、"
                       f"中位數 {pc(rc.get('med'), 1, sign=True)}")
        else:
            br = r["bh_r"]
            out.append(f"近 10 年沒過關：年化 {pc(rc.get('cagr'), 1, sign=True)}（買進持有 {pc(br['cagr'], 1, sign=True)}）、"
                       f"最大回撤 {pc(rc.get('mdd'), 0)}（買進持有 {pc(br['mdd'], 0)}）")
    elif r.get("rec_ok") is None and kind != "alloc":
        out.append(f"近 10 年只有 {rc.get('n', 0)} {UNIT[kind]}，看不出最近還有沒有用")
    if kind == "dip" and f.get("n") and f["n"] < 15:
        out.append(f"次數少：全期間只有 {f['n']} 次，每一次的結果對成績影響很大")
    if kind == "alloc" and k != "hal":
        when = "每天收盤" if k == "ma200" else "月底"
        out.append(f"賣出要等{when}的訊號：急跌時跌幅會先吃到一段；盤整時會反覆進出（一年約 {f.get('sw') or 0:.1f} 次），每次都付成本")
    if r.get("p") is not None and r["p"] >= 0.05:
        what = {"trade": "買進日", "dip": "訊號出現的日子"}.get(kind, "持有／空手的時間")
        out.append(f"打亂測試：把{what}整段挪開 {S.LUCK_DRAWS} 次，有 {r['p'] * 100:.0f}% 做得到一樣好，成績有一部分可能是運氣")
    if (mk, k) in S.FUT:
        out.append(XSP.FUT_NOTE.rstrip("。"))
    else:
        out.append("價格是指數本身、不含股息：買進持有少算了股息（台股每年約 3～4%、美股約 1.5～2%），照規則空手時也沒算利息")
    if kind == "trade":
        out.append("成交都假設在收盤價，實際下單的滑價沒有算")
    return out


def ref_line(r: dict) -> str | None:
    """對照（不判定）：交易型、進出型＝原作者時點（台股 RSI(2)＝隔天收盤）；落底型＝同一個市場 5 日急跌隔天就買。"""
    pc, kind = XSP.pc, r["kind"]
    if kind == "dip":
        s = r.get("b1") or {}
        if not s.get("n"):
            return None
        hn = XSP.HN.get(r["H"], f"{r['H']} 個交易日")
        return (f"同一個市場 5 日急跌隔天就買：抱 {hn}賺錢 {pc(s.get('win'), 0)}（隨便挑一天 {pc(s.get('base'), 0)}）、"
                f"中位數 {pc(s.get('med'), 1, sign=True)}，{s['n']} 次")
    s = r.get("ref")
    if not s:
        return None
    lb = ("隔天收盤（看網頁再做）" if (r["mk"], r["k"]) in S.SAME_DAY else
          "原作者時點（訊號當天收盤買賣）" if kind == "trade" else "原作者時點（當天收盤買賣）")
    if kind == "trade":
        if not s.get("n"):
            return f"{lb}：沒有交易"
        return (f"{lb}：勝率 {pc(s['win'], 0)}（隨便挑同樣天數 {pc(s.get('base'), 0)}）、"
                f"平均每筆 {pc(s['avg'], 2, sign=True)}，{s['n']} 筆")
    return f"{lb}：年化 {pc(s['cagr'], 1, sign=True)}、最大回撤 {pc(s['mdd'], 0)}"


def grid_tbl(r: dict) -> dict:
    """參數鄰近表：列＝第一個參數、欄＝第二個參數（只有一個參數就一列）；每格 [過關, 原作者參數, 第一行, 第二行]。"""
    k, kind = r["k"], r["kind"]
    sp = S.BY_KEY[k]
    names = list(sp["grid"])
    vals = [list(sp["grid"][x]) for x in names]
    main = tuple(sp["p"][x] for x in names)
    pc = XSP.pc
    cell = {}
    for g in r["grid"]:
        key = tuple(g["p"][x] for x in names)
        if kind == "trade":
            t1, t2 = f"勝率 {pc(g.get('win'), 0)}", f"{pc(g.get('avg'), 2, sign=True)}・{g.get('n') or 0} 筆"
        elif kind == "dip":
            t1 = f"賺錢 {pc(g.get('win'), 0)}" if g.get("n") else "沒有出現"
            t2 = f"隨便挑 {pc(g.get('base'), 0)}・{g.get('n') or 0} 次"
        else:
            t1, t2 = f"年化 {pc(g.get('cagr'), 1, sign=True)}", f"回撤 {pc(g.get('mdd'), 0)}"
        cell[key] = [int(bool(g["ok"])), int(key == main), t1, t2]
    if len(names) == 2:
        rows = [[cell.get((a, c)) for c in vals[1]] for a in vals[0]]
    else:
        rows = [[cell.get((a,)) for a in vals[0]]]
    return {"pn": [XSP.PARAM_NAMES[k][x] for x in names],
            "a": [XSP.pval(k, names[0], v) for v in vals[0]],
            "b": [XSP.pval(k, names[1], v) for v in vals[1]] if len(names) == 2 else [],
            "c": rows, "ok": sum(1 for g in r["grid"] if g["ok"]), "n": len(r["grid"])}


def season_line(r: dict) -> str | None:
    """Halloween：每年 11～4 月與 5～10 月的漲跌（xstrat.season）。"""
    s = r.get("season") or {}
    if not s.get("n"):
        return None
    pc = XSP.pc
    t = (f"{s['y0']}～{s['y1']} 年（{s['n']} 年）：每年 11～4 月平均 {pc(s['w'], 1, sign=True)}（上漲的年份 {pc(s['wu'], 0)}），"
         f"5～10 月平均 {pc(s['o'], 1, sign=True)}（{pc(s['ou'], 0)}）；{pc(s['better'], 0)} 的年份 11～4 月比較好。")
    if s.get("w10") is not None:
        t += (f"最近 10 年：11～4 月 {pc(s['w10'], 1, sign=True)}、5～10 月 {pc(s['o10'], 1, sign=True)}"
              f"（{pc(s['b10'], 0)} 的年份 11～4 月比較好）。")
    return t


def hs_rows(r: dict) -> list[list]:
    """落底型換別的期間看（只列，不判定）：[期間, 次數, 賺錢%, 中位%, 隨便挑一天%, 判定看這一期]。"""
    hs = (r.get("full") or {}).get("hs") or {}
    return [[XSP.HN.get(h, f"{h} 個交易日"), v["n"], _p(v.get("win"), 0), _p(v.get("med")), _p(v.get("base"), 0), int(h == r["H"])]
            for h, v in sorted(hs.items())]


def explain(r: dict) -> dict:
    """一條策略的說明卡（規則與成績，內嵌在頁面）：結論、怎麼做（規則逐條）、過去成績（交易型、進出型＝逐年報酬；
    落底型＝換別的期間看）、風險。出處與邏輯每條策略一份（build 的 spec）；判定依據、1 元變多少、逐筆交易在 x9xh.json
    （judge、xstratpage.detail；打開規則與成績才下載）。"""
    E = r.get("eq") or {}
    out = {"concl": concl(r), "tl": tier_line(r), "rules": XSP.rule_lines(r["k"], r["mk"]), "risk": risk(r),
           "cost": XSP.cost_txt(r["mk"], r["k"])}
    if E.get("s") and E.get("b"):
        out["cv"] = [E["s"][-1], E["b"][-1]]              # 1 元變多少的最後倍數（圖還沒載入前，圖例先寫好，高度不變）
    if r["kind"] == "dip":
        out["hs"] = hs_rows(r)
    else:
        out["yr"] = yearly(r)
    sl = season_line(r)
    if sl:
        out["season"] = sl
    return out


def judge(r: dict) -> dict:
    """判定依據（說明卡最下面、收起來；放 x9xh.json）：每一項過了沒、對照（不判定）、參數鄰近表。"""
    return {"why": XSP.why(r), "ref": ref_line(r), "grid": grid_tbl(r)}


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
                     "st": r["now"]["st"], "tag": XSP.TAG[r["now"]["st"]], "how": how(r["k"], mk), "ex": explain(r),
                     "fail": fail_txt(r)})
    act = sorted({e["k"] for e in cal if e["d"] == nx})
    later = [e for e in cal if nx and e["d"] > nx and e["act"] in ("買進", "賣出")]
    summ = {"n": len(cards), "ng": sum(1 for c in cards if c["tier"] == "good"), "nr": sum(1 for c in cards if c["tier"] == "ref"),
            "act": len(act), "held": sum(1 for c in cards if c["st"] in XSP.HELD),
            "next": later[0] if later else None, "nlow": len(rs) - len(rec)}
    return {"d": d0, "nx": nx, "name": XSP.MK_NAMES[mk], "cards": cards, "cal": cal, "book": book, "sum": summ}


def build(R: dict | None = None) -> dict:
    """{"mks": [市場], "mkn": {市場: 名稱}, "m": {市場: market()}, "ver": 規格版本, "rule": 判定門檻,
    "spec": {策略: 出處、邏輯、參數說明}}。"""
    R = XSP.results() if R is None else R
    m = {mk: market(mk, R[mk]) for mk in S.MARKETS if R.get(mk)}
    rule = {"n": S.TR_N_MIN, "win": round(S.TR_WIN * 100), "edge": round(S.TR_EDGE * 100), "n10": S.TR_N10,
            "dn": S.DIP_N_MIN, "dwin": round(S.DIP_WIN * 100), "dn10": S.DIP_N10, "dtq": round(S.DIP_TRIM_Q * 100),
            "dtn": S.DIP_TRIM_N, "mdd": round((1 - S.AL_MDD) * 100, 1),
            "grid": "2/3", "draws": S.LUCK_DRAWS}
    spec = {sp["k"]: {"src": f"{sp['who']}《{sp['src']}》", "logic": sp["logic"], "pnote": sp.get("pnote") or ""}
            for sp in S.STRATS if any(sp["k"] in (R.get(mk) or {}) for mk in m)}
    return {"mks": list(m), "mkn": dict(XSP.MK_NAMES), "m": m, "ver": S.VER, "rule": rule, "spec": spec}
