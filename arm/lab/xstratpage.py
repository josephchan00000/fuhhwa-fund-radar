"""大神策略的文字與頁面資料（規格 xstratspec 第 8 節；計算在 xstrat.py）。

訊號總覽「大神策略」一類、景氣頁今天的重點（只列 ★、標「策略」）與最上面那一行（10 個月均線）共用同一套說法：
  payload(R)        訊號總覽頁面裡的小份資料（成績、判定依據、參數鄰近、現在）
  detail(R)         點開才下載的淨值與每一筆（放進 x9oh.json）
  board(mk)         景氣頁今天的重點要列的策略（★ 而且現在有動作）
  chip(mk)          景氣頁最上面那一行的「10 個月均線」
只描述照規則做過去的成績，不寫建議。
"""
from __future__ import annotations

from . import xstratspec as S
from .heatpage import _e


def results() -> dict:
    """五個市場的結果（xstrat.run_all，程序內快取）；算不出來回空的、不擋頁面。"""
    try:
        from . import xstrat as X
        return X.run_all()
    except Exception as e:                                # noqa: BLE001
        print(f"[大神策略] 算不出來：{type(e).__name__}: {e}")
        return {}


# ── 格式 ───────────────────────────────────────────────────────────────────

def pc(v, d: int = 1, sign: bool = False) -> str:
    if v is None:
        return "—"
    s = f"{abs(v) * 100:.{d}f}%"
    if sign:
        return ("+" if v > 0 else "−" if v < 0 else "") + s
    return ("−" if v < 0 else "") + s


def md(d: str | None, ref: str | None = None) -> str:
    """M/D；和參考日不同年就加年份。"""
    if not d:
        return ""
    s = f"{int(d[5:7])}/{int(d[8:10])}"
    return s if ref and d[:4] == ref[:4] else f"{d[:4]}/{s}"


def num(v, d: int = 0) -> str:
    return "—" if v is None else f"{v:,.{d}f}"


COST_TXT = {"tw": "台股 ETF 每買或賣一次 0.1%", "us": "美股 ETF 每買或賣一次 0.025%"}
PARAM_NAMES = {"rsi2": {"rsi_max": "RSI 低於", "exit_ma": "站上幾日均線賣"},
               "vixs": {"stretch": "VIX 比均線高", "exit_rsi": "RSI 高於幾賣"},
               "tom": {"before": "月底前幾天買", "after": "下個月第幾天賣"},
               "hal": {"start": "從幾月開始持有 6 個月"},
               "faber": {"n": "幾個月均線"}, "ma200": {"n": "幾日均線"}, "mom12": {"n": "看幾個月"}}


def pval(k: str, name: str, v) -> str:
    if name == "stretch":
        return f"{v * 100:.0f}%"
    if k == "hal":
        return f"{v} 月"
    return str(v)


# ── 規則、現在、成績的白話 ────────────────────────────────────────────────────

def rule_lines(k: str, mk: str) -> list[str]:
    p = S.BY_KEY[k]["p"]
    cost = COST_TXT["tw" if mk == "tw" else "us"]
    lag = "原作者是訊號當天收盤買賣（另列一列「原作者時點」參考）；這裡用隔天收盤，是看網頁做得到的最早時點。"
    if k == "rsi2":
        out = [f"買：收盤在 {p['ma']} 日均線上，而且 {p['rsi_n']} 日 RSI 低於 {p['rsi_max']} → 隔天收盤買。",
               f"賣：收盤站上 {p['exit_ma']} 日均線 → 隔天收盤賣。", lag]
    elif k == "vixs":
        out = [f"買：VIX 連 {p['days']} 天比自己的 {p['vix_ma']} 日均線高 {p['stretch'] * 100:.0f}% 以上，而且指數收盤在 {p['ma']} 日均線上 → 隔天收盤買。",
               f"賣：指數的 2 日 RSI 高於 {p['exit_rsi']} → 隔天收盤賣。", lag]
    elif k == "tom":
        out = [f"買：每個月倒數第 {p['before'] + 1} 個交易日收盤（持有月底最後 {p['before']} 天）。",
               f"賣：下個月第 {p['after']} 個交易日收盤。", "日子事先排定，照那天收盤買賣。"]
    elif k == "hal":
        out = ["買：10 月最後一個交易日收盤；賣：4 月最後一個交易日收盤。5～10 月空手。", "日子事先排定，照那天收盤買賣。"]
    elif k == "faber":
        out = [f"每個月最後一個交易日看：收盤在 {p['n']} 個月均線（最近 {p['n']} 個月底收盤的平均）上 → 持有；在線下 → 空手。",
               "照這個決定在隔天收盤買賣。" + lag.split("；")[0] + "。"]
    elif k == "ma200":
        out = [f"每天看：收盤在 {p['n']} 日均線上 → 持有；在線下 → 空手。", "隔天收盤買賣。" + lag.split("；")[0] + "。"]
    else:
        out = [f"每個月最後一個交易日看：收盤比 {p['n']} 個月前的月底高 → 持有；比較低 → 空手。",
               "隔天收盤買賣。" + lag.split("；")[0] + "。"]
    return out + [f"成本：{cost}。指數不含股息、空手時不算利息。"]


TAG = {"buy": "訊號出現", "hold": "持有中", "sell": "出場訊號", "wait": "沒有訊號",
       "in": "持有", "out": "空手", "turn_in": "要買回", "turn_out": "要賣出"}


def now_text(r: dict) -> str:
    """現在的狀態（一句或兩句）。日期寫明（美股的資料日是前一個美股交易日，「今天、明天」會混淆）。"""
    k, n = r["k"], r["now"]
    st, d = n["st"], n["d"]
    p = S.BY_KEY[k]["p"]
    ed, ret, held = n.get("ed"), n.get("ret"), n.get("held")
    D, NX = md(d), md(n.get("nx"), d) or "下一個交易日"
    if k == "rsi2":
        if st == "buy":
            return f"{D} 收盤出現訊號：2 日 RSI {n['rsi2']:.1f}（低於 {p['rsi_max']}）、收盤在 200 日均線上 {pc(n['ma'])} → {NX} 收盤買。"
        if st == "hold":
            if not held:
                return f"{D} 收盤照規則買進（{num(n.get('ep'))}）；之後收盤站上 {p['exit_ma']} 日均線，隔天收盤賣。"
            ex = n.get("ex")
            exs = "" if ex is None else f"（現在{'低' if ex < 0 else '高'} {pc(abs(ex))}）"
            return (f"持有中：{md(ed, d)} 收盤買進（{num(n.get('ep'))}），到 {D} {pc(ret, sign=True)}（第 {held} 個交易日）；"
                    f"收盤站上 {p['exit_ma']} 日均線就隔天收盤賣{exs}。")
        if st == "sell":
            return f"{D} 收盤站上 {p['exit_ma']} 日均線 → {NX} 收盤賣（{md(ed, d)} 買進，到 {D} {pc(ret, sign=True)}）。"
        if n.get("ma") is not None and n["ma"] < 0:
            return f"沒有訊號：收盤在 200 日均線下 {pc(-n['ma'])}（在線上才做）；2 日 RSI {n['rsi2']:.0f}。"
        return f"沒有訊號：2 日 RSI {n['rsi2']:.0f}（低於 {p['rsi_max']} 才買）；收盤在 200 日均線上 {pc(n.get('ma'))}。"
    if k == "vixs":
        vs = n.get("vs")
        vtxt = f"VIX {n.get('vix'):.1f}" + ("" if vs is None else f"，比 10 日均線{'高' if vs >= 0 else '低'} {pc(abs(vs), 0)}")
        if st == "buy":
            return f"{D} 收盤出現訊號：{vtxt}，連 {n.get('run')} 天高 {p['stretch'] * 100:.0f}% 以上、指數在 200 日均線上 → {NX} 收盤買。"
        if st == "hold":
            if not held:
                return f"{D} 收盤照規則買進（{num(n.get('ep'))}）；之後 2 日 RSI 高於 {p['exit_rsi']}，隔天收盤賣。"
            return (f"持有中：{md(ed, d)} 收盤買進，到 {D} {pc(ret, sign=True)}（第 {held} 個交易日）；"
                    f"2 日 RSI 高於 {p['exit_rsi']} 就隔天收盤賣（現在 {n['rsi2']:.0f}）。")
        if st == "sell":
            return f"{D} 2 日 RSI {n['rsi2']:.0f} 高於 {p['exit_rsi']} → {NX} 收盤賣（{md(ed, d)} 買進，到 {D} {pc(ret, sign=True)}）。"
        tail = "；指數在 200 日均線下（在線上才做）" if n.get("ma") is not None and n["ma"] < 0 else ""
        return f"沒有訊號：{vtxt}（連 {p['days']} 天高 {p['stretch'] * 100:.0f}% 以上才買）{tail}。"
    if k == "tom":
        q = n.get("qd")
        if st == "buy":
            return f"{md(n.get('ed'), d)} 收盤買（下一個交易日）、{md(q, d)} 收盤賣。"
        if st == "hold":
            return f"持有中：{md(n.get('ed'), d)} 收盤買進，到 {D} {pc(ret, sign=True)}；{md(q, d)} 收盤賣。"
        if st == "sell":
            return f"{md(q, d)} 收盤賣（下一個交易日；{md(n.get('ed'), d)} 買進，到 {D} {pc(ret, sign=True)}）。"
        return f"下一次：{md(n.get('ed'), d)} 收盤買、{md(q, d)} 收盤賣。" if n.get("ed") else "沒有排到下一次。"
    sw = n.get("sw")
    since = f"（{md(ed, d)} 起持有，{pc(ret, 0, sign=True)}）" if ed and ret is not None else ""
    if k == "hal":
        if st == "turn_in":
            return f"{md(sw, d)} 收盤買進（下一個交易日），持有到 4 月底。"
        if st == "turn_out":
            return f"{md(sw, d)} 收盤賣出（下一個交易日），5～10 月空手。"
        if st == "in":
            return f"持有中（11～4 月）{since}；{md(sw, d)} 收盤賣出。"
        return f"空手（5～10 月）；{md(sw, d)} 收盤買進，持有到 4 月底。"
    dist, chk = n.get("dist"), n.get("chk")
    if k == "ma200":
        if st == "turn_out":
            return f"{D} 收盤跌破 {p['n']} 日均線（{pc(dist, sign=True)}）→ {NX} 收盤賣出。"
        if st == "turn_in":
            return f"{D} 收盤站回 {p['n']} 日均線（{pc(dist, sign=True)}）→ {NX} 收盤買回。"
        if st == "in":
            return f"持有：收盤在 {p['n']} 日均線上 {pc(dist)}{since}。"
        return f"空手：收盤在 {p['n']} 日均線下 {pc(-dist if dist is not None else None)}。"
    if k == "faber":
        what = f"{p['n']} 個月均線"
        cur = "" if dist is None else f"以 {D} 收盤試算：在線{'上' if dist > 0 else '下'} {pc(abs(dist))}。"
    else:
        what = f"{p['n']} 個月前"
        cur = "" if dist is None else f"以 {D} 收盤試算：{p['n']} 個月 {pc(dist, 0, sign=True)}。"
    nxt = f"下一次看 {md(chk, d)}。" if chk else ""
    if st == "turn_out":
        return f"{D} 是月底，收盤{'跌破 ' + what if k == 'faber' else '比 ' + what + '低'} → {NX} 收盤賣出。"
    if st == "turn_in":
        return f"{D} 是月底，收盤{'站回 ' + what if k == 'faber' else '比 ' + what + '高'} → {NX} 收盤買回。"
    if st == "in":
        return f"持有：上個月底收盤{'在 ' + what + '上' if k == 'faber' else '比 ' + what + '高'}{since}。{cur}{nxt}"
    return f"空手：上個月底收盤{'在 ' + what + '下' if k == 'faber' else '比 ' + what + '低'}。{cur}{nxt}"


def now_short(r: dict) -> str:
    """清單「現在」那一格：一個關鍵數字。"""
    k, n = r["k"], r["now"]
    if k == "rsi2":
        return f"RSI(2) {n['rsi2']:.0f}・200 日線 {pc(n.get('ma'), 0, sign=True)}"
    if k == "vixs":
        return f"VIX {n.get('vix'):.1f}・比 10 日均線 {pc(n.get('vs'), 0, sign=True)}"
    if k == "tom":
        return f"下一次 {md(n.get('ed'), n['d'])}" if n["st"] == "wait" else TAG[n["st"]]
    if k == "hal":
        return "11～4 月持有中" if n["st"] in ("in", "turn_out") else "5～10 月空手"
    if k == "ma200":
        return f"離 200 日線 {pc(n.get('dist'), 1, sign=True)}"
    if k == "faber":
        return f"離 10 個月線 {pc(n.get('dist'), 1, sign=True)}"
    return f"12 個月 {pc(n.get('dist'), 0, sign=True)}"


def result_line(r: dict) -> str:
    f = r["full"]
    if r["kind"] == "trade":
        if not f.get("n"):
            return "評估期間沒有交易。"
        return (f"過去 {f['n']} 筆：勝率 {pc(f['win'], 0)}（隨便挑同樣天數 {pc(f.get('base'), 0)}）、"
                f"平均每筆 {pc(f['avg'], 2, sign=True)}（扣成本）、平均抱 {f['hold']:.1f} 天")
    b = r["bh"]
    return (f"年化 {pc(f['cagr'])}（買進持有 {pc(b['cagr'])}）、最大回撤 {pc(f['mdd'], 0)}（買進持有 {pc(b['mdd'], 0)}）")


def _trade_why(s: dict) -> str:
    if not s.get("n"):
        return "沒有交易"
    e = (s["win"] - s["base"]) * 100 if s.get("base") is not None else None
    et = "—" if e is None else (f"高 {e:.1f}" if e >= 0 else f"低 {-e:.1f}")
    return (f"勝率 {pc(s['win'])}（要 {S.TR_WIN * 100:.0f}% 以上）、比隨便挑同樣天數{et} 個百分點"
            f"（要高 {S.TR_EDGE * 100:.0f} 以上）、平均每筆 {pc(s['avg'], 2, sign=True)}（要大於 0）")


def _alloc_why(s: dict, b: dict) -> str:
    less = 1.0 - s["mdd"] / b["mdd"] if b["mdd"] else None
    lt = "—" if less is None else (f"少跌 {less * 100:.1f}%" if less >= 0 else f"多跌 {-less * 100:.1f}%")
    mar, bmar = s.get("mar"), (b["cagr"] / b["mdd"] if b["mdd"] else None)
    return (f"最大回撤 {pc(s['mdd'], 0)}，比買進持有（{pc(b['mdd'], 0)}）{lt}（要少跌三分之一，{(1 - S.AL_MDD) * 100:.1f}% 以上）；"
            f"年化 ÷ 最大回撤 {'—' if mar is None else f'{mar:.3f}'}（買進持有 {'—' if bmar is None else f'{bmar:.3f}'}，要不輸）")


def why(r: dict) -> list[list]:
    """判定依據：[[過了沒（1／0／None＝不看）, 文字], …]。"""
    out = []
    f = r["full"]
    if r["kind"] == "trade":
        if f.get("n", 0) < S.TR_N_MIN:
            out.append([None, f"全期間只有 {f.get('n', 0)} 筆，不到 {S.TR_N_MIN} 筆，不判定。"])
        out.append([int(bool(f.get("ok"))), f"全期間（{md(r['a'])} 起）：" + _trade_why(f)])
        rc = r["rec"]
        if r["rec_ok"] is None:
            out.append([None, f"近 10 年只有 {rc.get('n', 0)} 筆（不到 {S.TR_N10} 筆），不看。"])
        else:
            out.append([int(bool(r["rec_ok"])), f"近 10 年（{md(r['r0'])} 起，{rc['n']} 筆）：" + _trade_why(rc)])
    else:
        out.append([int(bool(f.get("ok"))), f"全期間（{md(r['a'])} 起）：" + _alloc_why(f, r["bh"])])
        out.append([int(bool(r["rec_ok"])), f"近 10 年（{md(r['r0'])} 起）：" + _alloc_why(r["rec"], r["bh_r"])])
    g = r["grid"]
    k = sum(1 for x in g if x["ok"])
    out.append([int(r["grid_ok"] >= S.GRID_OK - 1e-12), f"參數鄰近：{len(g)} 組有 {k} 組過關（要 2/3 以上）。"])
    if r.get("p") is not None:
        out.append([None, f"打亂測試：把{'買進日' if r['kind'] == 'trade' else '持有／空手的時間'}整段挪開 {S.LUCK_DRAWS} 次，"
                          f"做得到一樣好的比例 {r['p'] * 100:.1f}%（只標示，不影響判定）。"])
    return out


def side(r: dict) -> str | None:
    st = r["now"]["st"]
    if st in S.BOARD_UP:
        return "up"
    if st in S.BOARD_WARN:
        return "warn"
    return None


# ── 訊號總覽的資料 ─────────────────────────────────────────────────────────────

def _r(v, k: int = 1):
    return None if v is None else round(float(v) * 100, k)


def _ts(s: dict) -> dict | None:
    if not s or not s.get("n"):
        return {"n": 0}
    return {"n": s["n"], "win": _r(s["win"]), "base": _r(s.get("base")), "avg": _r(s["avg"], 2), "med": _r(s.get("med"), 2),
            "pf": None if s.get("pf") is None else round(s["pf"], 2), "hold": round(s["hold"], 1), "worst": _r(s["worst"]),
            "best": _r(s.get("best")), "cagr": _r(s.get("cagr")), "mdd": _r(s.get("mdd")), "expo": _r(s.get("expo"), 0),
            "ok": int(bool(s.get("ok")))}


def _as(s: dict | None) -> dict | None:
    if not s:
        return None
    return {"cagr": _r(s["cagr"]), "mdd": _r(s["mdd"]), "mar": None if s.get("mar") is None else round(s["mar"], 2),
            "worst": _r(s.get("worst")), "sw": None if s.get("sw") is None else round(s["sw"], 1), "expo": _r(s.get("expo"), 0),
            "ok": int(bool(s.get("ok")))}


def _grid(r: dict) -> list:
    out = []
    for g in r["grid"]:
        vals = list(g["p"].values())
        if r["kind"] == "trade":
            out.append([vals, int(g["ok"]), g.get("n"), _r(g.get("win"), 0), _r(g.get("base"), 0), _r(g.get("avg"), 2)])
        else:
            out.append([vals, int(g["ok"]), _r(g["cagr"]), _r(g["mdd"], 0)])
    return out


def payload(R: dict) -> dict:
    spec = {}
    for s in S.STRATS:
        spec[s["k"]] = {"name": s["name"], "grp": s["grp"], "kind": s["kind"], "who": s["who"], "src": s["src"],
                        "logic": s["logic"], "pk": list(s["grid"]), "pn": [PARAM_NAMES[s["k"]][x] for x in s["grid"]],
                        "main": [s["p"][x] for x in s["grid"]]}
    m: dict = {}
    for mk in S.MARKETS:
        for k, r in (R.get(mk) or {}).items():
            n = r["now"]
            x = {"t": r["tier"], "a": r["a"], "z": r["z"], "r0": r["r0"], "st": n["st"], "side": side(r),
                 "now": now_text(r), "nv": now_short(r), "line": result_line(r), "why": why(r), "rules": rule_lines(k, mk),
                 "gok": round(r["grid_ok"], 3), "g": _grid(r), "p": None if r.get("p") is None else round(r["p"] * 100, 2)}
            if r["kind"] == "trade":
                x.update({"f": _ts(r["full"]), "r": _ts(r["rec"]), "o": _ts(r.get("ref")) if r.get("ref") else None,
                          "b": _as(r["bh"]), "br": _as(r["bh_r"])})
            else:
                x.update({"f": _as(r["full"]), "r": _as(r["rec"]), "o": _as(r.get("ref")), "b": _as(r["bh"]), "br": _as(r["bh_r"])})
            if r.get("season"):
                ss = r["season"]
                x["s"] = {kk: (_r(v) if isinstance(v, float) else v) for kk, v in ss.items()}
            m.setdefault(mk, {})[k] = x
    return {"spec": spec, "m": m, "grp": S.GROUPS, "tn": S.TIER_NAMES, "sn": TAG, "ver": S.VER,
            "rule": {"n": S.TR_N_MIN, "win": round(S.TR_WIN * 100), "edge": round(S.TR_EDGE * 100), "n10": S.TR_N10,
                     "mdd": round(S.AL_MDD, 2), "grid": "2/3", "draws": S.LUCK_DRAWS}}


def detail(R: dict) -> dict:
    """{"xs:市場:策略": {"eq": {d, s, b}, "tr": 每一筆或每一段}}。"""
    out = {}
    for mk in S.MARKETS:
        for k, r in (R.get(mk) or {}).items():
            out[f"xs:{mk}:{k}"] = {"eq": r["eq"], "tr": r["tr"]}
    return out


# ── 景氣頁 ─────────────────────────────────────────────────────────────────

def board(mk: str, R: dict | None = None) -> list[dict]:
    """今天的重點要列的策略：★ 而且現在有動作（交易型買／持有／賣、進出型買回列偏多；空手、賣出列警示）。"""
    R = results() if R is None else R
    out = []
    for s in S.STRATS:
        r = (R.get(mk) or {}).get(s["k"])
        if not r or r["tier"] != "good":
            continue
        sd = side(r)
        if sd:
            out.append({"id": f"xs:{mk}:{s['k']}", "side": sd, "name": s["name"], "st": r["now"]["st"], "now": now_text(r),
                        "line": result_line(r), "grp": S.GROUPS[s["grp"]]})
    return out


def board_li(it: dict) -> str:
    return (f'<li><a class="tzi" href="x9o.html#i={_e(it["id"])}"><span class="tzh"><span class="tzk tzk-good">★</span>'
            f'<b>{_e(it["name"])}</b><span class="tzd tzs">策略</span><span class="tzd">{_e(TAG[it["st"]])}</span></span>'
            f'<span class="tzl">{_e(it["now"])}<br>{_e(it["line"])}</span></a></li>')


def chip(mk: str, R: dict | None = None) -> str:
    """最上面那一行：10 個月均線的狀態（不論判定，每個市場都列）。"""
    R = results() if R is None else R
    r = (R.get(mk) or {}).get("faber")
    if not r:
        return ""
    n = r["now"]
    st = n["st"]
    dist = n.get("dist")
    held = st in ("in", "turn_out")
    lab = TAG[st]
    pos = "" if dist is None else f"線{'上' if dist > 0 else '下'} {pc(abs(dist))}"
    tip = (f"10 個月均線（Faber）：{now_text(r)} 判定 {S.TIER_MARK[r['tier']]} {S.TIER_NAMES[r['tier']]}；"
           f"{result_line(r)}。點了看細節。")
    cls = "stc" if held and st != "turn_out" else "stc stx"
    return (f'<a class="{cls}" href="x9o.html#i=xs:{_e(mk)}:faber" title="{_e(tip)}"><b>10 個月均線</b>{_e(pos)}'
            f'<i>{_e(lab)}</i></a>')
