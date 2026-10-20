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


COST_TXT = {"tw": "台股 ETF 每買或賣一次 0.1%", "us": "美股 ETF 每買或賣一次 0.025%",
            "fut": "台指期每買或賣一次約 0.005%（期交稅十萬分之二＋手續費）"}
FUT_NOTE = ("價格用加權指數收盤（不含股息）：台指期的正逆價差、轉倉沒有算；台指期的價格已經扣掉預期的股息，"
            "抱過除息日不會因為除息而跌，這裡會把除息算成跌。")


def cost_txt(mk: str, k: str) -> str:
    if (mk, k) in S.FUT:
        return COST_TXT["fut"]
    return COST_TXT["tw" if mk == "tw" else "us"]


def ref_label(mk: str, k: str, kind: str) -> list[str]:
    """參考列的名稱與小字：當天收盤進出的參考隔天收盤（看網頁再做），其他參考原作者的當天收盤。"""
    if (mk, k) in S.SAME_DAY:
        return ["隔天收盤", "看網頁再做（訊號隔一個交易日收盤買賣），參考"]
    return ["原作者時點", "訊號當天收盤買賣，參考" if kind == "trade" else "當天收盤買賣，全期間，參考"]
PARAM_NAMES = {"rsi2": {"rsi_max": "RSI 低於", "exit_ma": "站上幾日均線賣"},
               "vixs": {"stretch": "VIX 比均線高", "exit_rsi": "RSI 高於幾賣"},
               "tom": {"before": "月底前幾天買", "after": "下個月第幾天賣"},
               "hal": {"start": "從幾月開始持有 6 個月"},
               "faber": {"n": "幾個月均線"}, "ma200": {"n": "幾日均線"}, "mom12": {"n": "看幾個月"},
               "coppock": {"wma": "幾個月加權平均"}, "vix40": {"level": "VIX 到多少"},
               "zweig": {"lo": "先跌到多少以下", "hi": "再衝到多少以上"},
               "ftd": {"corr": "修正幾 %", "up": "那天漲幾 %"}, "dev60": {"th": "季線乖離"},
               "mmr": {"level": "維持率跌破多少"}, "mflush": {"dd": "指數至少跌幾 %"},
               "lowry": {"th": "90% 日的門檻", "win": "下跌日後幾天內"}}
HN = {20: "1 個月", 60: "3 個月", 120: "6 個月", 250: "1 年"}


def pval(k: str, name: str, v) -> str:
    if name == "stretch":
        return f"{v * 100:.0f}%"
    if k == "mmr" and name == "level":
        return f"{v:.0f}%"
    if k == "lowry" and name == "win":
        return f"{v} 天"
    if name in ("lo", "hi", "corr", "up", "th", "dd"):
        x = v * 100
        return f"{x:.{0 if abs(x - round(x)) < 1e-9 else (2 if abs(x * 10 - round(x * 10)) > 1e-9 else 1)}f}%"
    if k == "hal":
        return f"{v} 月"
    return str(v)


# ── 規則、現在、成績的白話 ────────────────────────────────────────────────────

def rule_lines(k: str, mk: str) -> list[str]:
    p = S.BY_KEY[k]["p"]
    cost = cost_txt(mk, k)
    lag = "原作者是訊號當天收盤買賣（另列一列「原作者時點」參考）；這裡用隔天收盤，是看網頁做得到的最早時點。"
    fut = [FUT_NOTE] if (mk, k) in S.FUT else []
    if k == "rsi2" and (mk, k) in S.SAME_DAY:
        out = [f"買：收盤在 {p['ma']} 日均線上，而且 {p['rsi_n']} 日 RSI 低於 {p['rsi_max']} → 當天收盤前用台指期買。",
               f"賣：收盤站上 {p['exit_ma']} 日均線 → 當天收盤前用台指期賣。",
               "現貨 13:30 收盤就知道當天的 RSI 與均線，台指期 13:45 才收盤，還來得及買賣（和原作者一樣是訊號當天收盤）。"
               "頁面每天寫下一個交易日收盤在多少以下就是買進訊號、高於多少就是出場訊號（「現在」那一段）。",
               "另列一列「隔天收盤」＝看網頁再做的成績，參考。"]
    elif k == "rsi2":
        out = [f"買：收盤在 {p['ma']} 日均線上，而且 {p['rsi_n']} 日 RSI 低於 {p['rsi_max']} → 隔天收盤買。",
               f"賣：收盤站上 {p['exit_ma']} 日均線 → 隔天收盤賣。", lag]
    elif k == "vixs":
        out = [f"買：VIX 連 {p['days']} 天比自己的 {p['vix_ma']} 日均線高 {p['stretch'] * 100:.0f}% 以上，而且指數收盤在 {p['ma']} 日均線上 → 隔天收盤買。",
               f"賣：指數的 2 日 RSI 高於 {p['exit_rsi']} → 隔天收盤賣。", lag]
    elif S.BY_KEY[k]["kind"] == "dip":
        out = dip_rules(k, mk)
    elif k == "tom":
        out = [f"買：每個月倒數第 {p['before'] + 1} 個交易日收盤（持有月底最後 {p['before']} 天）。",
               f"賣：下個月第 {p['after']} 個交易日收盤。",
               "日子事先排定，照那天收盤買賣" + ("（用台指期）。" if (mk, k) in S.FUT else "。")]
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
    if fut:
        return out + [f"成本：{cost}。空手時不算利息。"] + fut
    return out + [f"成本：{cost}。指數不含股息、空手時不算利息。"]


def dip_rules(k: str, mk: str) -> list[str]:
    """落底型的規則（規格第 9 節）。"""
    sp = S.BY_KEY[k]
    p, H = sp["p"], sp["H"]
    sell = f"賣：買進後抱 {H} 個交易日（約 {HN[H]}）收盤賣。"
    if k == "coppock":
        out = [f"每個月最後一個交易日算：100 ×（收盤 ÷ {p['r1']} 個月前月底收盤 − 1）＋100 ×（收盤 ÷ {p['r2']} 個月前月底收盤 − 1），"
               f"再取 {p['wma']} 個月加權平均（最近的最重）。",
               "買：曲線在 0 以下、而且這個月比上個月高（由下往上轉）→ 隔天收盤買。", sell]
    elif k == "vix40":
        out = [f"買：VIX 收盤 ≥ {p['level']}，而且之前 {p['reset']} 個交易日都沒有到 {p['level']} → 隔天收盤買。"
               + ("台股用前一個美股交易日的 VIX（台股收盤時已經知道的最新一個）。" if mk == "tw" else ""), sell]
    elif k == "zweig":
        who = ("景氣頁同一份，月底市值 40 億以上的股票" if mk == "tw" else
               "S&P 500 當時的成分股、Yahoo 有資料的；四個美股指數都用這一份")
        out = [f"每天算上漲家數 ÷（上漲＋下跌家數）（{who}），取 10 日指數平均。",
               f"買：指數平均衝上 {p['hi'] * 100:.1f}%（前一天還沒有），而且之前 {p['days']} 個交易日內有一天在 {p['lo'] * 100:.0f}% 以下 → 隔天收盤買。",
               sell, "台股家數資料 2013 年起。" if mk == "tw" else
               "美股家數 1996 年起；已下市、改名的成分股 Yahoo 多半沒有，早年只算得到現在還在交易的公司。"]
    elif k == "mmr":
        out = ["大盤融資維持率＝上市股票與 ETF 的融資市值（融資餘額張數 × 收盤）÷ 上市融資金額（各家券商、媒體的算法不同，數字會差幾個百分點）。",
               f"買：維持率收盤後第一次低於 {p['level']}%（之前 {p['reset']} 個交易日都在 {p['level']}% 以上）→ 隔天收盤買"
               "（融資餘額晚上才公布）。", sell, "2004 年起才有（FinMind 的已下市公司收盤 2004-02 才有，之前算不準）。"]
    elif k == "mflush":
        out = [f"加權指數離近 {p['win']} 個交易日最高收盤跌了幾 %（跌幅），和從那個最高點以來上市融資金額減少了幾 %（融資減幅）。",
               f"買：跌幅 ≥ {p['dd'] * 100:.0f}%，而且融資減幅第一次 ≥ 跌幅（前一天還沒有）→ 隔天收盤買。", sell]
    elif k == "lowry":
        th, th2 = p["th"] * 100, p["th2"] * 100
        out = [f"90% 下跌日：下跌股的成交金額、下跌點數都占 {th:.0f}% 以上（S&P 500 成分股算；點數＝當時價格的漲跌）。",
               f"買：90% 下跌日之後 {p['win']} 個交易日內出現 90% 上漲日（上漲股成交金額、上漲點數都 ≥ {th:.0f}%），"
               f"或連兩天 {th2:.0f}% 上漲日 → 隔天收盤買（要再出現 90% 下跌日才會有下一次）。", sell,
               "美股家數 1996 年起；已下市、改名的成分股 Yahoo 多半沒有。"]
    elif k == "ftd":
        out = [f"修正：收盤比近 {S.FTD_HIGH} 個交易日的最高收盤低 {p['corr'] * 100:.0f}% 以上；收盤回到那個最高收盤的 99.9% 以上＝修正結束。",
               "低點之後第一個收盤上漲的日子＝第 1 天；收盤又跌破低點就重新數。",
               f"買：第 {p['day']} 天以後第一次收盤漲 {p['up'] * 100:.2f}% 以上、而且成交量"
               + ("（台股用上市成交金額）" if mk == "tw" else "") + "比前一天大 → 隔天收盤買（一段修正只算第一個）。", sell]
    else:
        out = [f"買：收盤比 {p['ma']} 日均線（季線）低 {-p['th'] * 100:.0f}% 以上，而且前一天還沒有 → 隔天收盤買。", sell]
    return out + ["一次訊號之後，抱的期間內再出現不算新的一次。"]


TAG = {"buy": "訊號出現", "hold": "持有中", "sell": "出場訊號", "wait": "沒有訊號", "near": "接近訊號",
       "in": "持有", "out": "空手", "turn_in": "要買回", "turn_out": "要賣出"}


def _same_day_rsi2(n: dict, p: dict, D: str, NX: str, d: str) -> str:
    """當天收盤進出的 RSI(2)（台股，台指期）：下一個交易日的價位。"""
    st, ed, ret, held = n["st"], n.get("ed"), n.get("ret"), n.get("held")
    how = "13:30 現貨收盤確認、13:45 台指期收盤前"
    if st == "hold":
        ex, c = n.get("ex_px"), n.get("px")
        rel = f"，比 {D} 收盤{'高' if ex >= c else '低'} {pc(abs(ex / c - 1.0))}" if ex is not None and c else ""
        out = (f"{NX} 收盤高於 {num(ex)}（站上 {p['exit_ma']} 日均線{rel}）就賣——{how}賣出。" if ex is not None
               else f"收盤站上 {p['exit_ma']} 日均線就賣。")
        if not held:
            return f"{D} 收盤出現訊號，照規則 {D} 收盤前買進（{num(n.get('ep'))}）；{out}"
        return f"持有中：{md(ed, d)} 收盤買進（{num(n.get('ep'))}），到 {D} {pc(ret, sign=True)}（第 {held} 個交易日）；{out}"
    hi, lo = n.get("hi_px"), n.get("lo_px")
    if st == "near":
        return (f"接近訊號：{NX} 收盤在 {num(hi)}（比 {D} 收盤 {pc(n.get('hi_chg'), sign=True)}）以下、"
                f"{num(lo)}（200 日均線）以上，就是買進訊號——{how}買進。")
    if n.get("ma") is not None and n["ma"] < 0:
        return f"沒有訊號：收盤在 200 日均線下 {pc(-n['ma'])}（在線上才做）；2 日 RSI {n['rsi2']:.0f}。"
    if hi is None or lo is None:
        return f"沒有訊號：2 日 RSI {n['rsi2']:.0f}（低於 {p['rsi_max']} 才買）；收盤在 200 日均線上 {pc(n.get('ma'))}。"
    if not n.get("can"):
        return (f"沒有訊號：{NX} 收盤要低於 {num(hi)}（{pc(n.get('hi_chg'), sign=True)}）2 日 RSI 才會低於 {p['rsi_max']}，"
                f"但那樣會跌破 200 日均線（{num(lo)}），所以 {NX} 不會出現買進訊號。")
    return (f"沒有訊號：{NX} 收盤低於 {num(hi)}（{pc(n.get('hi_chg'), sign=True)}）而且在 {num(lo)}（200 日均線）以上才是買進訊號；"
            f"2 日 RSI {n['rsi2']:.0f}。")


def now_text(r: dict) -> str:
    """現在的狀態（一句或兩句）。日期寫明（美股的資料日是前一個美股交易日，「今天、明天」會混淆）。"""
    k, n = r["k"], r["now"]
    st, d = n["st"], n["d"]
    p = S.BY_KEY[k]["p"]
    ed, ret, held = n.get("ed"), n.get("ret"), n.get("held")
    D, NX = md(d, d), md(n.get("nx"), d) or "下一個交易日"
    if S.BY_KEY[k]["kind"] == "dip":
        return dip_now_text(k, n, D, NX, d)
    if k == "rsi2" and n.get("lag") == 0:
        return _same_day_rsi2(n, p, D, NX, d)
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


def _dip_ind(k: str, n: dict, D: str, d: str) -> str:
    """落底型現在的指標值（一句）。"""
    if k == "coppock":
        if n.get("cv") is None:
            return ""
        up = n["cv"] > n.get("cp", n["cv"])
        out = (f"Coppock 曲線 {n['cv']:.1f}（{int(n['cm'][5:7])} 月底，比上個月{'高' if up else '低'}；"
               f"{'在 0 以上' if n['cv'] >= 0 else '在 0 以下'}）")
        if n.get("cnow") is not None:
            out += f"，以 {D} 收盤試算 {n['cnow']:.1f}"
        return out + (f"；下一次看 {md(n.get('chk'), d)}" if n.get("chk") else "")
    if k == "vix40":
        return "" if n.get("vix") is None else f"VIX {n['vix']:.1f}（近 60 個交易日最高 {num(n.get('vmax'), 1)}；收盤到 40 以上才算）"
    if k == "zweig":
        if n.get("e") is None:
            return ""
        return (f"上漲家數 10 日平均 {n['e'] * 100:.1f}%（{md(n.get('ed_'), d)}；要先在 40% 以下，10 個交易日內再衝上 61.5%）")
    if k == "mmr":
        if n.get("mr") is None:
            return ""
        q = S.BY_KEY["mmr"]["p"]
        return (f"大盤融資維持率 {n['mr']:.1f}%（{md(n.get('mrd'), d)}；近 {q['reset']} 個交易日最低 {num(n.get('mrmin'), 1)}%，"
                f"跌破 {q['level']}% 才算）")
    if k == "mflush":
        if n.get("dd") is None:
            return ""
        q = S.BY_KEY["mflush"]["p"]
        if n["dd"] < q["dd"]:
            return f"加權指數離近 {q['win']} 個交易日高點 {pc(-n['dd'], sign=True)}（要跌 {q['dd'] * 100:.0f}% 以上才看）"
        return f"加權指數離高點 {pc(-n['dd'], sign=True)}、融資金額從那時以來 {pc(-n['md'], sign=True)}（融資減幅要大於指數跌幅）"
    if k == "lowry":
        out = "" if n.get("u") is None else f"{md(n.get('ud'), d)} 上漲股成交金額占 {pc(n['u'], 0)}、上漲點數占 {pc(n['g'], 0)}"
        if n.get("dn_d"):
            out += f"；最近一次 90% 下跌日 {md(n['dn_d'], d)}（{n.get('dn_ago')} 個交易日前）"
        return out
    if k == "ftd":
        if n.get("in"):
            out = f"修正中：比近 252 個交易日最高收盤低 {pc(-n['dd'])}，低點 {md(n.get('low_d'), d)}（{num(n.get('low_px'))}）"
            if n.get("done"):
                return out + "；這一段修正已經出現過跟進日"
            return out + (f"，反彈第 {n['rday']} 天（第 4 天起看大漲＋量增）" if n.get("rday") else "，還沒有收盤上漲的反彈日")
        return f"沒有在修正（比近 252 個交易日最高收盤低 {pc(-n['dd'])}，低 10% 以上才算修正）"
    if n.get("dev") is None:
        return ""
    return f"收盤比季線{'高' if n['dev'] >= 0 else '低'} {pc(abs(n['dev']))}（要低 15% 以上）"


def dip_now_text(k: str, n: dict, D: str, NX: str, d: str) -> str:
    st, H = n["st"], n["H"]
    ind = _dip_ind(k, n, D, d)
    if st == "buy":
        return f"{D} 收盤出現訊號 → {NX} 收盤買，抱 {H} 個交易日（約 {HN[H]}）。" + (f"{ind}。" if ind else "")
    if st == "hold":
        return (f"持有中：{md(n.get('sd'), d)} 出現訊號、{md(n.get('ed'), d)} 收盤買進（{num(n.get('ep'))}），到 {D} "
                f"{pc(n.get('ret'), sign=True)}（第 {n.get('held')} 個交易日）；{md(n.get('qd'), d)} 收盤賣（還有 {n.get('left')} 個交易日）。")
    last = (f"上一次 {md(n.get('ld'), d)}，抱 {HN[H]} {pc(n.get('lret'), sign=True)}。" if n.get("ld") else "")
    return "沒有訊號" + (f"：{ind}。" if ind else "。") + last


def now_short(r: dict) -> str:
    """清單「現在」那一格：一個關鍵數字。"""
    k, n = r["k"], r["now"]
    if S.BY_KEY[k]["kind"] == "dip":
        if n["st"] == "hold":
            return f"持有中・{md(n.get('qd'), n['d'])} 賣"
        if n["st"] == "buy":
            return "訊號出現"
        if k == "coppock":
            return "—" if n.get("cv") is None else f"Coppock {n['cv']:.0f}（{'向上' if n['cv'] > n.get('cp', n['cv']) else '向下'}）"
        if k == "vix40":
            return "—" if n.get("vix") is None else f"VIX {n['vix']:.1f}"
        if k == "zweig":
            return "—" if n.get("e") is None else f"上漲家數平均 {n['e'] * 100:.0f}%"
        if k == "ftd":
            return (f"修正中・反彈第 {n['rday']} 天" if n.get("in") and n.get("rday") else
                    "修正中" if n.get("in") else f"離高點 {pc(n.get('dd'), 1, sign=True)}")
        if k == "mmr":
            return "—" if n.get("mr") is None else f"維持率 {n['mr']:.0f}%"
        if k == "mflush":
            return "—" if n.get("dd") is None else f"離高點 {pc(-n['dd'], 1, sign=True)}"
        if k == "lowry":
            return (f"90% 下跌日 {md(n['dn_d'], n['d'])}" if n.get("dn_d") and n.get("dn_ago", 99) <= S.BY_KEY[k]["p"]["win"]
                    else "沒有 90% 下跌日" if not n.get("dn_d") else f"上一次 90% 下跌日 {md(n['dn_d'], n['d'])}")
        return f"離季線 {pc(n.get('dev'), 1, sign=True)}"
    if k == "rsi2" and n["st"] == "near":
        return f"{md(n.get('nx'), n['d'])} 收盤低於 {num(n.get('hi_px'))} 就買"
    if k == "rsi2" and n["st"] == "hold" and n.get("ex_px") is not None:
        return f"持有中・{md(n.get('nx'), n['d'])} 收盤高於 {num(n.get('ex_px'))} 就賣"
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
    if r["kind"] == "dip":
        if not f.get("n"):
            return "評估期間沒有出現過。"
        H = r["H"]
        return (f"過去 {f['n']} 次：抱 {HN[H]}賺錢 {pc(f['win'], 0)}（隨便挑一天 {pc(f.get('base'), 0)}）、"
                f"中位數 {pc(f['med'], 1, sign=True)}（扣成本）、中途最多跌中位 {pc(f.get('mae'), 1)}")
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


def _dip_why(s: dict, H: int) -> str:
    if not s.get("n"):
        return "沒有出現過"
    e = (s["win"] - s["base"]) * 100 if s.get("base") is not None else None
    et = "—" if e is None else (f"高 {e:.1f}" if e >= 0 else f"低 {-e:.1f}")
    return (f"抱 {HN[H]}賺錢 {pc(s['win'])}（要 {S.DIP_WIN * 100:.0f}% 以上）、比隨便挑一天{et} 個百分點"
            f"（要高 {S.DIP_EDGE * 100:.0f} 以上）、中位數 {pc(s['med'], 1, sign=True)}（要大於 0）")


def why(r: dict) -> list[list]:
    """判定依據：[[過了沒（1／0／None＝不看）, 文字], …]。"""
    out = []
    f = r["full"]
    if r["kind"] == "dip":
        H = r["H"]
        if f.get("n", 0) < S.DIP_N_MIN:
            out.append([None, f"全期間只有 {f.get('n', 0)} 次，不到 {S.DIP_N_MIN} 次，不判定。"])
        out.append([int(bool(f.get("ok"))), f"全期間（{md(r['a'])} 起，{f.get('n', 0)} 次）：" + _dip_why(f, H)])
        rc = r["rec"]
        if r["rec_ok"] is None:
            out.append([None, f"近 10 年只有 {rc.get('n', 0)} 次（不到 {S.DIP_N10} 次），不看。"])
        else:
            out.append([int(bool(r["rec_ok"])), f"近 10 年（{rc['n']} 次）：" + _dip_why(rc, H)])
    elif r["kind"] == "trade":
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
        what = {"trade": "買進日", "dip": "訊號出現的日子"}.get(r["kind"], "持有／空手的時間")
        out.append([None, f"打亂測試：把{what}整段挪開 {S.LUCK_DRAWS} 次，"
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


def _ds(s: dict | None) -> dict | None:
    """落底型的成績（%）。"""
    if not s or not s.get("n"):
        return {"n": 0, "base": _r((s or {}).get("base"))}
    return {"n": s["n"], "win": _r(s.get("win")), "base": _r(s.get("base")), "med": _r(s.get("med")), "avg": _r(s.get("avg")),
            "mae": _r(s.get("mae")), "worst": _r(s.get("worst")), "best": _r(s.get("best")), "ok": int(bool(s.get("ok")))}


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
        elif r["kind"] == "dip":
            out.append([vals, int(g["ok"]), g.get("n"), _r(g.get("win"), 0), _r(g.get("base"), 0), _r(g.get("med"), 1)])
        else:
            out.append([vals, int(g["ok"]), _r(g["cagr"]), _r(g["mdd"], 0)])
    return out


def payload(R: dict) -> dict:
    spec = {}
    for s in S.STRATS:
        spec[s["k"]] = {"name": s["name"], "grp": s["grp"], "kind": s["kind"], "who": s["who"], "src": s["src"],
                        "logic": s["logic"], "pnote": s.get("pnote") or "",
                        "pk": list(s["grid"]), "pn": [PARAM_NAMES[s["k"]][x] for x in s["grid"]],
                        "main": [s["p"][x] for x in s["grid"]]}
    m: dict = {}
    for mk in S.MARKETS:
        for k, r in (R.get(mk) or {}).items():
            n = r["now"]
            ol = ref_label(mk, k, r["kind"])
            x = {"t": r["tier"], "a": r["a"], "z": r["z"], "r0": r["r0"], "st": n["st"], "side": side(r), "ol": ol[0], "os": ol[1],
                 "now": now_text(r), "nv": now_short(r), "line": result_line(r), "why": why(r), "rules": rule_lines(k, mk),
                 "gok": round(r["grid_ok"], 3), "g": _grid(r), "p": None if r.get("p") is None else round(r["p"] * 100, 2)}
            if r["kind"] == "trade":
                x.update({"f": _ts(r["full"]), "r": _ts(r["rec"]), "o": _ts(r.get("ref")) if r.get("ref") else None,
                          "b": _as(r["bh"]), "br": _as(r["bh_r"])})
            elif r["kind"] == "dip":
                hs = (r["full"].get("hs") or {})
                x.update({"f": _ds(r["full"]), "r": _ds(r["rec"]), "o": _ds(r.get("b1")), "H": r["H"],
                          "hs": [[h, v["n"], _r(v["win"], 0), _r(v["med"]), _r(v["base"], 0)] for h, v in sorted(hs.items())],
                          "b": _as(r["bh"]), "br": _as(r["bh_r"])})
            else:
                x.update({"f": _as(r["full"]), "r": _as(r["rec"]), "o": _as(r.get("ref")), "b": _as(r["bh"]), "br": _as(r["bh_r"])})
            if r.get("season"):
                ss = r["season"]
                x["s"] = {kk: (_r(v) if isinstance(v, float) else v) for kk, v in ss.items()}
            m.setdefault(mk, {})[k] = x
    return {"spec": spec, "m": m, "grp": S.GROUPS, "tn": S.TIER_NAMES, "sn": TAG, "ver": S.VER, "hn": HN,
            "rule": {"n": S.TR_N_MIN, "win": round(S.TR_WIN * 100), "edge": round(S.TR_EDGE * 100), "n10": S.TR_N10,
                     "mdd": round(S.AL_MDD, 2), "grid": "2/3", "draws": S.LUCK_DRAWS,
                     "dn": S.DIP_N_MIN, "dwin": round(S.DIP_WIN * 100), "dedge": round(S.DIP_EDGE * 100)}}


def detail(R: dict) -> dict:
    """{"xs:市場:策略": {"eq": {d, s, b}, "tr": 每一筆或每一段}}。"""
    out = {}
    for mk in S.MARKETS:
        for k, r in (R.get(mk) or {}).items():
            out[f"xs:{mk}:{k}"] = {"eq": r["eq"], "tr": r["tr"]}
    return out


# ── 景氣頁 ─────────────────────────────────────────────────────────────────

def board(mk: str, R: dict | None = None) -> list[dict]:
    """今天的重點要列的策略：★ 而且現在有動作（交易型買／持有／賣／接近訊號、進出型買回列偏多；空手、賣出列警示）。"""
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
