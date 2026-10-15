"""籌碼雷達：交易策略＋前瞻紙上交易（2026-10-14 使用者：「幫我擬定交易策略」→「好」）。

驗證原則（改這裡之前先讀 CLAUDE.md 籌碼雷達「策略」段）：
  · **規則寫死、帶版本與起算日**。紙上交易只記「規則建立之後」的訊號——之前的資料只能當
    「樣本內參考」，因為規則本身就是看那段資料挑出來的。要改規則＝新版本、新起算日、成績歸零。
  · **每次建表由分片資料重算**，不存交易狀態：同樣的資料永遠算出同樣的帳，不會有狀態檔壞掉的問題。
  · 進出場一律用「當時已知」的價格：訊號日 t 收盤後才知道 → 最早 t+1 開盤。
  · 成本：來回 0.585%；超額：對加權指數同一時窗（進場日開盤 → 出場日收盤；指數開盤取 Yahoo ^TWII），與成績單同口徑。
  · 驗證期滿（30 筆或 30 個交易日，先到者）：平均超額＞0 且勝率＞50% → 達標；否則不達標。
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, timedelta

from . import advice
from . import backtest
from . import ledger as LG
from . import ta

COST = 0.00585
PASS_N = 30
PASS_DAYS = 30

# 策略頁 v2（2026-10-15 使用者：「好亂、用字很 AI、結論不明確」→ 改成固定五段：結論／操作規則／歷史績效／本期名單／風險）。
# 結論與評級由 advice.py 依資料即時算出（不寫死數字）；這裡只放不會隨樣本改變的規則與風險說明。
# 群益新建倉（S4）2026-10-15 依使用者指示移除（83% 交易集中在 2026-08 同一個月，不具可靠性）。
STRATEGIES = [
    # 持有期是看過 1～10 日全掃描後選的（開低組多數持有期為正、方向不隨持有期改變）；頁面「歷史績效」照實寫出。
    {"key": "s1", "ver": 1, "since": "2026-10-14", "name": "共識加碼・開低進場", "kind": "短線・持有 3 個交易日",
     "rule": ["選股：5 個交易日內有 3 家以上投信的主動 ETF 同時真加碼，且主動 ETF 合計淨買（同一檔 5 日內只取第一次）",
              "進場：訊號日次一交易日，開盤價低於訊號日收盤才買進（以 8:59 試撮價判斷）；平盤或開高不買",
              "出場：買進後第 3 個交易日收盤賣出",
              "停損：收盤跌破「進場價 − 2 × ATR(14)」，當日收盤賣出"],
     "basis": "同一個訊號，次日開盤低於前收時進場的成績，明顯好於平盤或開高時進場；下方「持有天數比較」列出兩組在持有 1～10 天的平均超額。",
     "risk": ["回測期間自 2026-07 起，交易多集中在少數月份",
              "持有天數短，來回成本 0.585% 占報酬比重高",
              "開盤後若大幅下跌，停損價可能在收盤才觸發"],
     "scan": [["s", "開盤低於前收（本策略）"], ["c", "平盤或開高（不進場）"]], "scan_h": 10,
     "hold": 3, "stop_atr": 2.0, "gap_max": 0.0, "gap_strict": True},
]


S3 = {"key": "s3", "ver": 1, "since": "2026-10-14", "name": "臺灣50 提前卡位",
      "kind": "事件型・每季審核、持有約 2 個月",
      "basis": "臺灣50 依市值排名換股，規則公開，資料截止日收盤後即可算出名單。納入股多數在截止日前就已上漲，"
               "因此在截止前 25 個交易日依當時排名先買進漲勢最強的 4 檔，截止日再依規則校正。",
      "risk": ["一年 4 次審核，樣本少，成績可能集中在少數幾次",
               "提前買進的股票若截止日未進名單，隔天開盤賣出，可能小幅虧損",
               "不設停損，進出依日期；持有期間跌 5～11% 屬常見波動"],
      "rule": ["名單：富時／證交所官方公告的納入與刪除（週一 ETF 週掃寫入 config/index_reviews.json）",
               "納入：公告後第一個交易日開盤買進，生效日收盤賣出（賣給被動買盤）",
               "刪除：生效日收盤買進（承接被動賣壓），第 5 個交易日收盤賣出"],
      "hold": None}

# 臺灣50 兩個新版本（2026-10-14 使用者：「公告前就先預估可能納進去的…也幫我去歸因哪些股票會漲最多」→
# 「不用一檔可以 3-4 檔，然後能越早卡位越好」）：提前卡位（截止前 25 個交易日、最多 4 檔）與公告後進場並列紙上比較。
# 交易由 tw50study.version_trades 依同一套規則重算。上面的 S3（官方名單全部）規則不變，留作對照組。
TW50_VERS = [
    {"k": "early", "ver": 1, "since": "2026-10-14", "name": "提前卡位・漲勢前 4 檔",
     "buy": "截止前 25 個交易日的隔天開盤", "sell": "生效前一天收盤",
     "rule": ["建倉：資料截止日前第 25 個交易日收盤後選股，次一交易日開盤買進",
              "候選：當天市值排名的預估納入股（非成分股進入前 40 名；截止日尚未上市者除外），以及第 41～45 名的非成分股",
              "選股：候選中截止前 40 個交易日漲幅最大的 4 檔，不足 4 檔則全買，等額配置",
              "校正：資料截止日收盤後依規則重算名單。名單沒有的，次一交易日開盤賣出；名單有但尚未買進的，依漲幅補足 4 檔，次一交易日開盤買進",
              "出場：生效日前一個交易日收盤全部賣出；官方公告名單沒有的，公告後第一個交易日開盤賣出"]},
    {"k": "post", "ver": 1, "since": "2026-10-14", "name": "公告後進場・漲勢前一半",
     "buy": "公告後第一個交易日開盤", "sell": "生效前一天收盤",
     "rule": ["名單：富時／證交所官方公告的納入股",
              "選股：依資料截止日前 40 個交易日漲幅排序，買進前一半（無條件進位；僅 1 檔時買進該檔）",
              "進場：公告後第一個交易日開盤買進",
              "出場：生效日前一個交易日收盤賣出（個股生效日延後時，以個股為準）"]},
]


def _pct(xs: list[float], q: float) -> float | None:
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def dist(trs: list[dict]) -> dict:
    """已出場交易的報酬分布——頁面「參考價位」據此把今日收盤換算成價位（歷史統計，非預測）。
    p＝毛報酬（出場價÷進場價−1，%）的 10／25／50／75／90 分位；aw／al＝扣成本後平均賺／平均賠；
    mo＝逐月 [月份, 筆數, 平均超額]（看成績是否集中在某一段行情）。"""
    cl = [t for t in trs if t.get("st") == "closed" and t.get("entry") and t.get("exit")]
    if not cl:
        return {"n": 0}
    g = [(t["exit"] / t["entry"] - 1) * 100 for t in cl]
    rs = [t["r"] for t in cl if t.get("r") is not None]
    win = [r for r in rs if r > 0]
    loss = [r for r in rs if r <= 0]
    mo: dict[str, list] = defaultdict(list)
    for t in cl:
        if t.get("x") is not None:
            mo[t["d"][:7]].append(t["x"])
    return {"n": len(cl), "p": [round(_pct(g, q), 2) for q in (0.1, 0.25, 0.5, 0.75, 0.9)],
            "aw": round(statistics.mean(win), 2) if win else None,
            "al": round(statistics.mean(loss), 2) if loss else None,
            "lo": round(min(rs), 2) if rs else None, "hi": round(max(rs), 2) if rs else None,
            "stop": sum(1 for t in cl if t.get("why") == "停損"),
            "held": round(statistics.mean(t["held"] for t in cl if t.get("held") is not None), 1),
            "mo": [[m, len(v), round(statistics.mean(v), 2)] for m, v in sorted(mo.items())]}


def scan(groups: list, series, idx: list, io: list, H: int) -> dict:
    """樣本內持有期掃描：每組在持有 1～H 個交易日（t+1 開盤進、t+h 收盤出，同成績單口徑）的
    平均超額與勝率。groups＝[(鍵, 標籤, [(代號, 訊號日索引)], 條件(隔夜跳空)->bool 或 None)]。
    用途：證明結論「不是挑了某一個持有期才成立」。"""
    out = {"h": H, "grp": []}
    for k, lbl, sigs, cond in groups:
        g = {"k": k, "lbl": lbl, "n": [], "x": [], "w": []}
        for h in range(1, H + 1):
            xs = []
            for code, t in sigs:
                r = backtest._ret(series(code), idx, t, h, io)
                if r and (cond is None or cond(r["g"])):
                    xs.append(r["x"])
            g["n"].append(len(xs))
            g["x"].append(round(statistics.mean(xs) * 100, 2) if xs else None)
            g["w"].append(round(sum(1 for x in xs if x > 0) / len(xs) * 100) if xs else None)
        out["grp"].append(g)
    return out


def trading_days_after(d: str, n: int) -> list[str]:
    """d 之後的 n 個台股交易日（週末＋證交所官方休市表；表未涵蓋的平日視為開市）。"""
    from .. import twholidays
    years = twholidays.load()
    out, x = [], date.fromisoformat(d)
    while len(out) < n:
        x += timedelta(days=1)
        if x.weekday() >= 5 or twholidays.is_closed(x, years):
            continue
        out.append(x.isoformat())
    return out


def tw50_trades(D, idx: list, io: list, names: dict, today: str) -> list[dict]:
    """依官方歷次結果模擬 S3（對照組）。公告在收盤後 → 納入股進場＝公告日之後第一個交易日開盤。
    資料還沒到該進場／出場的日子 → 待進場（cand）／持有中（open），不拿最新收盤冒充進出場價。"""
    from . import indexes
    ix = ((indexes.load_cfg().get("indexes") or {}).get("tw50") or {})
    out = []
    cal = D.cal
    last = cal[-1] if cal else ""
    for h in sorted(ix.get("history") or [], key=lambda x: x.get("effective") or ""):
        ann, eff0 = h.get("announce"), h.get("effective")
        if not ann or not eff0:
            continue
        a_i = next((i for i, d in enumerate(cal) if d > ann), None)
        for side, codes in (("add", h.get("adds") or []), ("del", h.get("dels") or [])):
            for c in codes:
                # 個股生效日延後（處置股依基本規則延後，例：南亞科 2025-12-30）→ 以個股為準
                eff = (h.get("eff_override") or {}).get(c) or eff0
                base = {"c": c, "n": names.get(c, c), "d": eff, "side": side, "review": h.get("review")}
                S = D.series(c)
                if side == "add":
                    if a_i is None:
                        out.append({**base, "st": "cand"})
                        continue
                    i0, px0 = a_i, S["o"][a_i]
                    b0 = io[a_i] or (idx[a_i - 1] if a_i else None)
                    i1 = max((i for i, d in enumerate(cal) if d <= eff), default=None) if last >= eff else None
                else:
                    if last < eff:
                        out.append({**base, "st": "cand"})
                        continue
                    i0 = max(i for i, d in enumerate(cal) if d <= eff)
                    px0, b0, i1 = S["c"][i0], idx[i0], i0 + 5
                if i1 is None or i1 >= D.T or not px0 or not S["c"][i1]:
                    li = max((i for i in range(i0, D.T) if S["c"][i]), default=None)
                    out.append({**base, "st": "open", "entry": px0, "now": None if li is None else S["c"][li]})
                    continue
                r = S["c"][i1] / px0 - 1 - COST
                b = idx[i1] / b0 - 1 if b0 and idx[i1] else None
                out.append({**base, "st": "closed", "entry": px0, "exit": S["c"][i1],
                            "held": i1 - i0 + (1 if side == "add" else 0),
                            "why": "納入・生效日出" if side == "add" else "刪除・5 日出",
                            "r": round(r * 100, 2), "x": None if b is None else round((r - b) * 100, 2)})
    return out


def _signals(key: str, D, sig_hist: dict, L, meta: dict) -> list[tuple[str, int]]:
    """(代號, 訊號日索引) 清單，只含台股。"""
    out = []
    if key == "s1":
        for code, hist in sig_hist.items():
            if not LG.is_tw(code):
                continue
            last = -999
            for t, day in enumerate(hist):
                if "cons" in day:
                    if t - last > 5:
                        out.append((code, t))
                    last = t
    out.sort(key=lambda x: (x[1], x[0]))
    return out


def _trade(st: dict, code: str, t: int, S: dict, atr: list, idx: list, T: int,
           idx_open: list | None = None) -> dict | None:
    """模擬一筆。回傳 None＝資料還沒到訊號隔日（候選中）。"""
    o, c = S["o"], S["c"]
    if t + 1 >= T or c[t] is None:
        return None
    if o[t + 1] is None:
        return {"st": "skip", "why": "隔日無開盤價"}
    gap = o[t + 1] / c[t] - 1
    if st["gap_max"] is not None and (gap >= st["gap_max"] if st.get("gap_strict") else gap > st["gap_max"]):
        return {"st": "skip", "why": f"開高 {gap * 100:+.1f}%", "gap": round(gap * 100, 2)}
    entry = o[t + 1]
    a = ta.last_at(atr, t)
    stop = entry - st["stop_atr"] * a if a else None
    exit_i, why = None, None
    for i in range(t + 1, min(t + st["hold"], T - 1) + 1):
        if c[i] is None:
            continue
        if stop and c[i] < stop:
            exit_i, why = i, "停損"
            break
        if i == t + st["hold"]:
            exit_i, why = i, "到期"
    rec = {"gap": round(gap * 100, 2), "entry": entry, "stop": None if stop is None else round(stop, 2)}
    if exit_i is None:
        last_i = max((i for i in range(t + 1, T) if c[i] is not None), default=t + 1)
        r = c[last_i] / entry - 1 if c[last_i] else None
        rec.update({"st": "open", "held": last_i - t, "now": c[last_i],
                    "r": None if r is None else round(r * 100, 2)})
        return rec
    r = c[exit_i] / entry - 1 - COST
    i0 = (idx_open[t + 1] if idx_open and idx_open[t + 1] else None) or idx[t]
    b = idx[exit_i] / i0 - 1 if idx[exit_i] and i0 else None
    rec.update({"st": "closed", "exit": c[exit_i], "why": why, "held": exit_i - t,
                "r": round(r * 100, 2), "x": None if b is None else round((r - b) * 100, 2)})
    return rec


def _agg(trs: list[dict]) -> dict:
    xs = [t["x"] for t in trs if t.get("st") == "closed" and t.get("x") is not None]
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "x": round(statistics.mean(xs), 2), "xm": round(statistics.median(xs), 2),
            "w": round(sum(1 for x in xs if x > 0) / len(xs) * 100), "sum": round(sum(xs), 2)}


def run(D, sig_hist: dict, L, meta: dict, idx: list, names: dict) -> dict:
    T = D.T
    io = D.taiex_open()
    cache: dict[str, tuple] = {}

    def series(code):
        if code not in cache:
            S = D.series(code)
            cache[code] = (S, ta.atr(S["h"], S["l"], S["c"]))
        return cache[code]

    def ser_only(code):
        return series(code)[0]

    nxt = trading_days_after(D.cal[-1], 25) if D.cal else []
    out = []
    for st in STRATEGIES:
        sigs = _signals(st["key"], D, sig_hist, L, meta)
        fwd, ins, cands = [], [], []
        for code, t in sigs:
            S, atr = series(code)
            rec = _trade(st, code, t, S, atr, idx, T, io)
            base = {"c": code, "n": names.get(code, code), "d": D.cal[t]}
            if rec is None:
                a = ta.last_at(atr, t)
                px = S["c"][t]
                cands.append({**base, "px": px,
                              "stop": round(px - st["stop_atr"] * a, 2) if a and px else None,
                              "atr": round(a, 2) if a else None, "gap_max": st["gap_max"],
                              # 進場＝訊號日隔一個交易日開盤；出場＝訊號日後第 hold 個交易日收盤
                              "ent": nxt[0] if t == T - 1 and nxt else None,
                              "out": nxt[st["hold"] - 1] if t == T - 1 and len(nxt) >= st["hold"] else None})
                continue
            (fwd if D.cal[t] >= st["since"] else ins).append({**base, **rec})
        days = sum(1 for d in D.cal if d >= st["since"])
        g = _agg(fwd)
        if g["n"] >= PASS_N or days >= PASS_DAYS:
            status = "達標" if g["n"] and g["x"] > 0 and g["w"] > 50 else "不達標"
        else:
            status = "驗證中"
        ins_sigs = [(c, t) for c, t in sigs if D.cal[t] < st["since"]]
        grps = [(st["scan"][0][0], st["scan"][0][1], ins_sigs, lambda gp: gp < 0),
                (st["scan"][1][0], st["scan"][1][1], ins_sigs, lambda gp: gp >= 0)]
        out.append({"key": st["key"], "ver": st["ver"], "since": st["since"], "name": st["name"],
                    "kind": st["kind"], "basis": st["basis"], "risk": st["risk"], "hold": st["hold"],
                    "stop_atr": st["stop_atr"],
                    "score": advice.score(advice.closed(ins), fwd_units=advice.closed(fwd)),
                    "rule": st["rule"], "status": status, "days": days,
                    "fwd": fwd[-60:], "fwd_stats": g, "ins_stats": _agg(ins),
                    "ins_n": len(ins), "cands": cands,
                    "scan": scan(grps, ser_only, idx, io, st["scan_h"]),
                    "dist": dist(ins), "ins": [t for t in ins if t.get("st") in ("closed", "open")][-80:]})
    # S3 臺灣50 換股：事件型、驗證期滿判準用「兩次審核」（筆數少、每季一次）。
    # 卡片＝三個版本並列：公告前卡位／公告後進場（兩個新版本）＋官方名單全部（原 S3，對照）。
    trs = tw50_trades(D, idx, io, names, D.cal[-1] if D.cal else "")
    fwd = [t for t in trs if t["d"] >= S3["since"]]
    ins = [t for t in trs if t["d"] < S3["since"]]
    status, n_rev = _ev_status(fwd)
    s3 = {"key": "s3", "ver": S3["ver"], "since": S3["since"], "name": S3["name"], "rule": S3["rule"],
          "kind": S3["kind"], "basis": S3["basis"], "risk": S3["risk"],
          "status": status, "days": n_rev, "fwd": fwd[-60:], "fwd_stats": _agg(fwd), "ins_stats": _agg(ins),
          "ins_n": len(ins), "cands": [], "event": True,
          "sides": {sd: {**_agg([t for t in ins if t["side"] == sd]),
                         **{"p": dist([t for t in ins if t["side"] == sd]).get("p")}}
                    for sd in ("add", "del")},
          "post5": _post_effective(D, ins, idx), "ins": ins[-80:]}
    try:
        s3.update(tw50_versions(D, names, s3, fwd, ins))
    except Exception as e:                                # noqa: BLE001 —— 新版本壞掉不連累整張卡
        s3["vers_err"] = f"{type(e).__name__}: {e}"
    out.insert(2, s3)
    # 跳空減碼提醒的證據：共識加碼亮燈、隔日開高 ≥3% 那一組（樣本內）
    s1 = STRATEGIES[0]
    s1_ins = [(c, t) for c, t in _signals("s1", D, sig_hist, L, meta) if D.cal[t] < s1["since"]]
    a_scan = scan([("g3", "共識加碼・隔日開高 ≥3%", s1_ins, lambda gp: gp >= 0.03)], ser_only, idx, io, 10)
    return {"list": out, "alerts": gap_alerts(D, sig_hist, names), "alert_scan": a_scan,
            "pass": [PASS_N, PASS_DAYS], "next": nxt[:5]}


def _ev_stats(trs: list[dict]) -> dict:
    """事件型版本的成績（已出場、扣成本）：報酬平均／中位／賺錢比例＋平均超額。"""
    cl = [t for t in trs if t.get("st") == "closed" and t.get("r") is not None]
    if not cl:
        return {"n": 0}
    rs = [t["r"] for t in cl]
    xs = [t["x"] for t in cl if t.get("x") is not None]
    return {"n": len(cl), "rev": len({t.get("review") for t in cl}),
            "avg": round(statistics.mean(rs), 2), "med": round(statistics.median(rs), 2),
            "win": round(sum(1 for r in rs if r > 0) / len(rs) * 100),
            "x": round(statistics.mean(xs), 2) if xs else None,
            "xw": round(sum(1 for x in xs if x > 0) / len(xs) * 100) if xs else None,
            "lo": round(min(rs), 2), "hi": round(max(rs), 2)}


def _ev_status(fwd: list[dict]) -> tuple[str, int]:
    """事件型：前瞻滿 2 次審核才判定（平均超額＞0 且勝率＞50% → 達標）。"""
    n_rev = len({t["review"] for t in fwd if t.get("st") == "closed"})
    g = _agg(fwd)
    if n_rev < 2:
        return "驗證中", n_rev
    return ("達標" if g["n"] and g["x"] > 0 and g["w"] > 50 else "不達標"), n_rev


def _rev_stats(trs: list[dict]) -> dict:
    """事件型版本「每次審核」的成績：同一次的各筆平均分配資金，一次算一個報酬（扣成本），再看幾次賺、最差一次。"""
    by: dict[str, list] = defaultdict(list)
    bx: dict[str, list] = defaultdict(list)
    for t in trs:
        if t.get("st") == "closed" and t.get("r") is not None:
            by[t.get("review")].append(t["r"])
            if t.get("x") is not None:
                bx[t.get("review")].append(t["x"])
    if not by:
        return {"n": 0}
    per = [statistics.mean(v) for v in by.values()]
    px = [statistics.mean(v) for v in bx.values()]
    return {"n": len(per), "trades": sum(len(v) for v in by.values()),
            "avg": round(statistics.mean(per), 2), "med": round(statistics.median(per), 2),
            "win": sum(1 for x in per if x > 0), "lo": round(min(per), 2),
            "x": round(statistics.mean(px), 2) if px else None, "xw": sum(1 for x in px if x > 0)}


def tw50_versions(D, names: dict, s3: dict, fwd: list[dict], ins: list[dict]) -> dict:
    """臺灣50 三個版本的成績＋「目前這一次」審核的計畫（日期、名單、漲勢、各版本部位）。"""
    from . import indexes, tw50study
    cfg = indexes.load_cfg()
    pl = tw50study.plans(D, cfg)
    V = tw50study.version_trades(D, cfg, names, pl)
    vers = []
    for vm in TW50_VERS:
        tv = V.get(vm["k"]) or []
        iv = [t for t in tv if t["d"] < vm["since"]]
        fv = [t for t in tv if t["d"] >= vm["since"]]
        st, nr = _ev_status(fv)
        vers.append({**{k: vm[k] for k in ("k", "ver", "since", "name", "buy", "sell", "rule")},
                     "status": st, "days": nr, "ins_stats": _ev_stats(iv), "fwd_stats": _ev_stats(fv),
                     "rev_stats": _rev_stats(iv), "fwd_rev": _rev_stats(fv),
                     "fwd": fv[-40:], "ins": iv[-80:], "dist": dist(iv),
                     "score": advice.score(advice.per_review(iv), event=True, fwd_units=advice.per_review(fv))})
    add_i = [t for t in ins if t.get("side") == "add"]
    vers.append({"k": "all", "ver": S3["ver"], "since": S3["since"], "name": "官方名單全部（對照）",
                 "buy": "公告後第一個交易日開盤", "sell": "生效日收盤", "rule": S3["rule"],
                 "status": s3["status"], "days": s3["days"], "ins_stats": _ev_stats(add_i),
                 "fwd_stats": _ev_stats([t for t in fwd if t.get("side") == "add"]),
                 "rev_stats": _rev_stats(add_i), "fwd_rev": _rev_stats([t for t in fwd if t.get("side") == "add"]),
                 "del_stats": _ev_stats([t for t in ins if t.get("side") == "del"]),
                 "fwd": fwd[-40:], "ins": ins[-80:], "dist": dist(add_i),
                 "score": advice.score(advice.per_review(add_i), event=True,
                                       fwd_units=advice.per_review([t for t in fwd if t.get("side") == "add"]))})
    by_rev, sens = _tw50_by_review(D, pl, V, add_i)
    # 目前這一次：還沒走完（出場日 ≥ 最新資料日）的最早一次審核
    last = D.cal[-1] if D.cal else ""
    cur = next((p for p in pl if (p.get("out") or "") >= last), None)
    plan = None
    if cur:
        stage = ("watch" if cur.get("e_t") is None and not cur["frozen"] else
                 "early" if not cur["frozen"] else "frozen" if not cur["official"] else "announced")
        tr = {k: {t["c"]: t for t in V.get(k) or [] if t.get("review") == cur["review"]} for k in ("early", "post")}
        pred, act = cur["pred"] or [], cur["act"] or []
        if stage == "watch":
            codes = list(cur["pick_now"])
        elif stage == "early":
            codes = list(cur["pick_e"])
        else:                                        # 截止後：先列持有中（早買仍在名單＋補位）、再列賣掉的、最後是沒買的
            held = [c for c in cur["pick_e"] if c in pred] + list(cur["pick_t"])
            sold = [c for c in cur["pick_e"] if c not in pred]
            codes = list(dict.fromkeys(held + sold + list(pred) + list(act)))
        mom_c, mom_e = cur.get("mom") or {}, cur.get("mom_e") or {}
        b_if = indexes.top_half(pred, mom_c) if stage == "frozen" else set()
        items = []
        for c in codes:
            m = mom_e.get(c) if stage in ("watch", "early") or c in cur["pick_e"] else mom_c.get(c)
            items.append({"c": c, "n": names.get(c, c), "rank": (cur.get("rank") or {}).get(c), "px": _last_close(D, c),
                          "mom": None if m is None else round(m * 100, 1),
                          "e": c in cur["pick_e"], "t": c in cur["pick_t"],
                          "pred": (c in pred) if cur["frozen"] else None, "act": (c in act) if cur["official"] else None,
                          "b": c in cur["pick_b"] or c in b_if,
                          "ta": _slim(tr["early"].get(c)), "tb": _slim(tr["post"].get(c))})
        plan = {k: cur.get(k) for k in ("review", "cutoff", "a_in", "announce", "b_in", "out", "effective", "status",
                                       "e_sig", "e_in")}
        plan.update({"stage": stage, "items": items, "out_c": cur.get("out_c") or {},
                     "K": tw50study.EARLY_K, "N": tw50study.EARLY_N,
                     "dels": [[c, names.get(c, c)] for c in ((cur.get("act_del") if cur["official"] else cur.get("pred_del")) or [])]})
    return {"vers": vers, "plan": plan, "by_rev": by_rev, "sens": sens}


def _tw50_by_review(D, pl: list[dict], V: dict, add_i: list[dict]) -> tuple[list, dict | None]:
    """逐次比較（樣本內、已出場、扣成本平均報酬）＋敏感度：扣掉兩版差距最大的 2 次後各剩多少。
    2026-10-14 發現：公告後版的成績幾乎都來自 2026-03、06 兩次——公告後第一天開盤納入股跌 9～10%（大盤急跌），
    剛好買在低點。這種「集中在少數幾次」要讓頁面自己算出來、自己講，不寫死。"""
    def avg(xs):
        xs = [x for x in xs if x is not None]
        return round(statistics.mean(xs), 2) if xs else None
    since = TW50_VERS[0]["since"]
    cl = {k: [t for t in V.get(k) or [] if t.get("st") == "closed" and t["d"] < since] for k in ("early", "post")}
    ctl = [t for t in add_i if t.get("st") == "closed"]
    rows = []
    for p in pl:
        rv = p["review"]
        ea = [t["r"] for t in cl["early"] if t["review"] == rv]
        post = [t["r"] for t in cl["post"] if t["review"] == rv]
        if not ea and not post:
            continue
        gaps = []                                          # 公告後版進場那天：開盤相對公告日收盤
        i0 = next((i for i, x in enumerate(D.cal) if p.get("announce") and x > p["announce"]), None)
        if i0:
            for c in p["pick_b"]:
                S = D.series(c)
                if S["o"][i0] and S["c"][i0 - 1]:
                    gaps.append((S["o"][i0] / S["c"][i0 - 1] - 1) * 100)
        rows.append([rv, avg(ea), avg(post), avg([t["r"] for t in ctl if t["review"] == rv]), avg(gaps)])
    both = [r for r in rows if r[1] is not None and r[2] is not None]
    sens = None
    if len(both) >= 4:
        top = sorted(both, key=lambda r: -abs(r[2] - r[1]))[:2]
        drop = {r[0] for r in top}
        left = [r for r in both if r[0] not in drop]
        sens = {"revs": [r[0] for r in top], "gaps": [r[4] for r in top],
                "early": avg([r[1] for r in left]), "post": avg([r[2] for r in left]),
                "early_all": avg([r[1] for r in both]), "post_all": avg([r[2] for r in both]),
                "n_left": len(left)}
    return rows, sens


def _last_close(D, c: str) -> float | None:
    cs = D.series(c)["c"]
    return next((x for x in reversed(cs) if x), None)


def _slim(t: dict | None) -> dict | None:
    return None if not t else {k: t.get(k) for k in ("st", "entry", "exit", "now", "r", "x", "held", "ent", "out", "why")}


def _post_effective(D, trs: list[dict], idx: list) -> dict:
    """納入股生效日收盤之後續抱 5 個交易日的報酬（扣成本）——證明「生效日一定要出」。"""
    xs = []
    for t in trs:
        if t.get("side") != "add" or t.get("st") != "closed" or t["d"] not in D.ix:
            continue
        i = D.ix[t["d"]]
        S = D.series(t["c"])
        if i + 5 < D.T and S["c"][i] and S["c"][i + 5]:
            xs.append((S["c"][i + 5] / S["c"][i] - 1 - COST) * 100)
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "r": round(statistics.mean(xs), 2), "w": round(sum(1 for x in xs if x > 0) / len(xs) * 100)}


def gap_alerts(D, sig_hist: dict, names: dict) -> list[dict]:
    """策略 2：最新交易日開盤跳空 ≥3% 的共識加碼股（前一交易日亮燈）——已持有者的減碼提醒。"""
    T = D.T
    out = []
    for code, hist in sig_hist.items():
        if not LG.is_tw(code) or T < 2:
            continue
        S = D.series(code)
        t = max((i for i in range(T) if S["o"][i] is not None), default=None)
        if not t or "cons" not in (hist[t - 1] or []) or not S["c"][t - 1]:
            continue
        gap = S["o"][t] / S["c"][t - 1] - 1
        if gap >= 0.03:
            out.append({"c": code, "n": names.get(code, code), "d": D.cal[t], "gap": round(gap * 100, 2)})
    return sorted(out, key=lambda x: -x["gap"])
