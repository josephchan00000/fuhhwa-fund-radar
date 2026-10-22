"""策略頁・總經策略的資料（arm/lab/xsadvice.py；docs/lab_strategy_ia_plan.md）：比照個股策略的卡片、時間表、比較表、摘要。"""
import json

import pytest

from arm.lab import xsadvice as XA
from arm.lab import xstrat as X
from arm.lab import xstratpage as P
from arm.lab import xstratspec as S

BANNED = ("保證", "穩賺", "必賺", "包賺", "必漲", "必跌", "一定會", "唯一", "建議買賣", "建議買", "建議賣", "目標價",
          "零風險", "無風險", "穩賺不賠")


@pytest.fixture(scope="module")
def R():
    return X.run_all()


@pytest.fixture(scope="module")
def B(R):
    return XA.build(R)


def _r(k, tier, st, **now):
    return {"k": k, "kind": S.BY_KEY[k]["kind"], "tier": tier, "now": {"st": st, "d": "2026-10-21", "nx": "2026-10-22", **now}}


def test_due_dates_and_verbs():
    """下一個照規則要做的事（原大神策略頁的 due，搬到這裡）：日期＋買進／賣出／可能買進。"""
    assert XA.due(_r("hal", "ref", "in", sw="2027-04-30")) == ("2027-04-30", "賣出")
    assert XA.due(_r("hal", "ref", "out", sw="2026-10-30")) == ("2026-10-30", "買進")
    assert XA.due(_r("tom", "good", "hold", ed="2026-10-20", qd="2026-10-23")) == ("2026-10-23", "賣出")
    assert XA.due(_r("tom", "good", "wait", ed="2026-10-29", qd="2026-11-04")) == ("2026-10-29", "買進")
    assert XA.due(_r("rsi2", "good", "wait")) is None and XA.due(_r("faber", "good", "turn_in")) == ("2026-10-22", "買進")
    assert XA.due(_r("rsi2", "good", "near")) == ("2026-10-22", "可能買進")
    assert XA.due(_r("rsi2", "good", "sell")) == ("2026-10-22", "賣出")
    assert XA.due(_r("coppock", "good", "hold", qd="2027-05-01")) == ("2027-05-01", "賣出")
    assert XA.due(_r("coppock", "good", "hold")) is None and XA.due(_r("ma200", "good", "in")) is None


def test_rank_puts_good_first_then_group_order(R, B):
    """推薦順序：★ 在前、● 在後；同一級照類型（短線 → 落底 → 季節性 → 風險控制），同類型依比對照好多少。○、— 不排。"""
    for mk, M in B["m"].items():
        cards = M["cards"]
        assert [c["rank"] for c in cards] == list(range(1, len(cards) + 1))
        assert all(c["tier"] in ("good", "ref") for c in cards)
        key = [(XA.TIER_ORD[c["tier"]], S.GROUP_ORDER.index(c["grp"])) for c in cards]
        assert key == sorted(key), mk
        for a, b in zip(cards, cards[1:]):
            if (a["tier"], a["grp"]) == (b["tier"], b["grp"]):
                ea, eb = XA.edge(R[mk][a["k"]]), XA.edge(R[mk][b["k"]])
                assert (ea if ea is not None else -9) >= (eb if eb is not None else -9)
        book = M["book"]
        assert {b["k"] for b in book} == set(R[mk])                                 # 比較表＝這個市場全部策略
        assert [b["k"] for b in book[:len(cards)]] == [c["k"] for c in cards]
        assert all(b["rank"] is None and b["tier"] in ("none", "few") for b in book[len(cards):])
        assert M["sum"]["n"] == len(cards) and M["sum"]["nlow"] == len(book) - len(cards)
        assert M["sum"]["ng"] + M["sum"]["nr"] == len(cards)


def test_cards_mirror_stock_strategy_rows(R, B):
    """每張卡：做法（一句）、隱含獲利（每筆／每次／每段，對照隨便挑一天或買進持有）、現在、時間軸；數字和 xstrat 一致。"""
    for mk, M in B["m"].items():
        for c in M["cards"]:
            r = R[mk][c["k"]]
            e, f = c["exp"], r["full"]
            assert c["how"] and c["now"] == P.now_text(r) and c["tag"] == P.TAG[c["st"]] and c["why"] == XA.why(r)
            assert e["unit"] == XA.UNIT[c["kind"]] and e["d0"] == r["a"] and e["d1"] == r["z"]
            assert e["bcagr"] == round(r["bh"]["cagr"] * 100, 1)
            # 每筆的平均、中位、賺錢比例、最差＝逐筆交易那一份（x9xh.json，取到小數第 5 位）重算；和 xstrat 原始數字只差四捨五入
            if c["kind"] == "trade" and f.get("n"):
                assert e["n"] == f["n"] and abs(e["win"] - f["win"] * 100) <= 0.5 + 1e-9 and e["base"] == round(f["base"] * 100)
                assert abs(e["avg"] - f["avg"] * 100) <= 0.006 and abs(e["med"] - f["med"] * 100) <= 0.006   # 顯示 2 位＋每筆取 5 位的誤差
                assert e["cagr"] == round(f["cagr"] * 100, 1)
            if c["kind"] == "dip" and f.get("n"):
                assert e["n"] == f["n"] and abs(e["med"] - f["med"] * 100) <= 0.051 and e["bmed"] == round(f["bmed"] * 100, 1)
                assert e["cagr"] == round(r["curve"]["cagr"] * 100, 1) and 0 <= e["expo"] <= 100
            if c["kind"] == "alloc":
                assert e["cagr"] == round(f["cagr"] * 100, 1) and e["mdd"] == round(f["mdd"] * 100)
                closed = [t for t in r["tr"] if t[2] is not None]
                assert e["n"] == len(closed)
            T = c["tl"]
            if c["st"] in P.HELD:
                assert len(T["held"]) == 1 and T["held"][0]["ent"] == r["now"].get("ed")
                q = XA.due(r)
                assert T["held"][0]["d"] == (q[0] if q and q[1] == "賣出" else None)
                assert bool(T["held"][0]["how"]) == (T["held"][0]["d"] is None)
            else:
                assert T["held"] == []
    txt = json.dumps(B, ensure_ascii=False)
    assert not [w for w in BANNED if w in txt]


def test_how_reads_parameters_from_spec():
    """做法那一句的數字讀規格（改參數不用改文字）；台股 RSI(2)、月底月初寫台指期。"""
    p = S.BY_KEY["rsi2"]["p"]
    assert f"2 日 RSI 低於 {p['rsi_max']}" in XA.how("rsi2", "spx") and "隔天收盤" in XA.how("rsi2", "spx")
    assert "台指期" in XA.how("rsi2", "tw") and "台指期" in XA.how("tom", "tw") and "台指期" not in XA.how("tom", "spx")
    assert "前一個美股交易日的 VIX 收盤衝上" in XA.how("vix40", "tw") and XA.how("vix40", "spx").startswith("VIX 收盤衝上")
    assert f"抱 {P.HN[S.BY_KEY['coppock']['H']]}" in XA.how("coppock", "tw")
    for s in S.STRATS:
        for mk in s["mk"]:
            t = XA.how(s["k"], mk)
            assert t.endswith("。") and not any(w in t for w in BANNED), (s["k"], mk)


def test_calendar_and_summary(B):
    """時間表依日期（同一天依推薦順序）；下一個交易日要動作的數字＝時間表在下一個交易日的策略數；下一次排定＝之後第一個買賣。"""
    for mk, M in B["m"].items():
        cal = M["cal"]
        assert cal == sorted(cal, key=lambda e: (e["d"], e["rank"]))
        assert all(e["act"] in ("買進", "賣出", "可能買進") for e in cal)
        assert M["sum"]["act"] == len({e["k"] for e in cal if e["d"] == M["nx"]})
        later = [e for e in cal if e["d"] > M["nx"] and e["act"] in ("買進", "賣出")]
        assert M["sum"]["next"] == (later[0] if later else None)
        assert M["sum"]["held"] == sum(1 for c in M["cards"] if c["st"] in P.HELD)
        tom = next((c for c in M["cards"] if c["k"] == "tom"), None)
        if tom and tom["tl"]["buy"]:
            b = tom["tl"]["buy"][0]
            assert {"買進": b["d"], "賣出": b["out"]} == {e["act"]: e["d"] for e in cal if e["k"] == "tom"}


def test_build_is_small_and_serializable(B):
    assert B["mks"] == [mk for mk in S.MARKETS if mk in B["m"]] and B["ver"] == S.VER
    assert set(B["rule"]) >= {"n", "win", "edge", "dn", "dwin", "dtq", "dtn", "mdd", "grid"}         # xstratspec VER 6
    assert set(B["spec"]) == {b["k"] for M in B["m"].values() for b in M["book"]}
    assert all(set(v) == {"src", "logic", "pnote"} and v["src"] and v["logic"] for v in B["spec"].values())
    size = len(json.dumps(B, ensure_ascii=False, separators=(",", ":")))
    # 內嵌在個股頁（x9.html），別讓頁面變太大：卡片、比較表約 5 萬字，說明卡（結論、規則、逐年報酬、風險）約 6.5 萬字；
    # 判定依據、1 元變多少、逐筆交易放 x9xh.json（打開規則與成績才下載）
    assert size < 130_000, size


# ── 說明卡（規則與成績；docs/lab_strategy_ia_plan.md 第三段） ─────────────────────────

def _closed(r):
    return [t for t in r["tr"] if t[2] is not None and t[5] is not None]


def test_explain_card_fields(R, B):
    """每一條策略（比較表全部，含 ○、—）都有說明卡：結論、判定一句、規則（＝訊號總覽同一份）、風險、成本；
    交易型與進出型有逐年報酬、落底型有抱多久比較（判定看的那一期標出來）；圖例的最後倍數＝淨值最後一個點。"""
    from arm.lab import xstratpage as XSP
    for mk, M in B["m"].items():
        for b in M["book"]:
            r, e = R[mk][b["k"]], b["ex"]
            assert e["concl"].startswith(f"{r['a'][:7]}～{r['z'][:7]}") and e["tl"] == XA.tier_line(r)
            assert e["rules"] == XSP.rule_lines(b["k"], mk) and e["cost"] == XSP.cost_txt(mk, b["k"])
            assert e["risk"] and any("不含股息" in x for x in e["risk"])
            assert e["cv"] == [r["eq"]["s"][-1], r["eq"]["b"][-1]] and b["how"] == XA.how(b["k"], mk)
            if r["kind"] == "dip":
                assert "yr" not in e and [h[1] for h in e["hs"]] == [v["n"] for _, v in sorted(r["full"]["hs"].items())]
                assert sum(h[5] for h in e["hs"]) == 1 and next(h for h in e["hs"] if h[5])[0] == XSP.HN[r["H"]]
            else:
                assert "hs" not in e and e["yr"]
            assert ("season" in e) == (b["k"] == "hal" and bool(r.get("season", {}).get("n")))
            assert b["exp"]["nt"] == len(r["tr"])
            txt = json.dumps(e, ensure_ascii=False)
            assert not [w for w in BANNED if w in txt], (mk, b["k"])


def test_tier_line_matches_tier(R):
    for mk, M in R.items():
        for k, r in M.items():
            t = XA.tier_line(r)
            if r["tier"] == "good":
                assert t.startswith("全期間過關，") and "但" not in t
            elif r["tier"] == "ref":
                assert t.startswith("全期間過關，但") and ("近 10 年沒過關" in t or "換附近的參數只有" in t)
            elif r["tier"] == "none":
                assert t.startswith("全期間沒過關：") and t.endswith("不列在「這一期」。")
            else:
                assert t.endswith("不判定。")


def test_yearly_compounds_to_final_value(R, B):
    """逐年報酬連乘＝淨值最後一個點（策略、買進持有都是；四捨五入到 0.1%，累積誤差有限）；年份連續、從評估起點那年到資料最後一年；
    今年還沒過完才標「到哪一天」。"""
    for mk, M in B["m"].items():
        for b in M["book"]:
            Y = b["ex"].get("yr")
            if not Y:
                continue
            r = R[mk][b["k"]]
            n = len(Y["s"])
            assert len(Y["b"]) == n and Y["y0"] == r["a"][:4] and int(Y["y0"]) + n - 1 == int(r["z"][:4])
            ps, pb = 1.0, 1.0
            for v, w in zip(Y["s"], Y["b"]):
                ps *= 1 + v / 100
                pb *= 1 + w / 100
            assert abs(ps / r["eq"]["s"][-1] - 1) < 0.0006 * n and abs(pb / r["eq"]["b"][-1] - 1) < 0.0006 * n, (mk, b["k"])
            nx = r["now"].get("nx")
            assert ("to" in Y) == (nx[:4] == r["z"][:4] if nx else r["z"][5:7] != "12")
            if "to" in Y:
                assert Y["to"] == r["z"]


def test_ex_best_removes_best_full_year(R):
    """成績集中在哪一年：最好的完整年份；去掉這一年之後的年化（策略與買進持有去掉同一年）。直接用淨值重算一次對照。"""
    from datetime import date
    r = R["tw"]["rsi2"]
    X = XA.ex_best(r)
    raw = XA._yr_raw(r)
    rets, ps = {}, 1.0
    brets, pb = {}, 1.0
    for y, s_, b_ in raw:
        rets[y], brets[y] = s_ / ps, b_ / pb
        ps, pb = s_, b_
    full = [y for i, y in enumerate(rets) if not (i == 0 and r["a"][5:7] != "01") and not (i == len(rets) - 1 and XA._part_last(r, raw))]
    best = max(full, key=lambda y: rets[y])
    yrs = (date.fromisoformat(r["z"]) - date.fromisoformat(r["a"])).days / 365.25
    assert X["y"] == best and X["r"] == round((rets[best] - 1) * 100, 1)
    assert X["cagr"] == round(((raw[-1][1] / rets[best]) ** (1 / (yrs - 1)) - 1) * 100, 1)
    assert X["bcagr"] == round(((raw[-1][2] / brets[best]) ** (1 / (yrs - 1)) - 1) * 100, 1)


def test_trade_list_numbers_equal_card_numbers(R, B):
    """逐筆交易上方那一句（頁面由每一筆重算）寫「就是上方結論的數字」：已賣出的每一筆（x9xh.json，報酬取到小數第 5 位）
    依時間順序加總的平均、中位、賺錢比例，照頁面的進位方式（.5 進位）就是卡片上的數字。node 實際跑頁面那一段在 test_macpage。"""
    from decimal import ROUND_HALF_UP, Decimal
    import statistics
    up = lambda x, d: float(Decimal(repr(x)).quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP))   # 頁面 toLocaleString 的進位
    for mk, M in B["m"].items():
        for b in M["book"]:
            r, e = R[mk][b["k"]], b["exp"]
            cl = [t[5] * 100 for t in _closed(r)]
            if not cl or not e.get("n"):
                continue
            dd = 2 if r["kind"] == "trade" else 1
            if r["kind"] != "alloc":
                assert len(cl) == e["n"] == r["full"]["n"]
            tot = 0.0
            for v in cl:
                tot += v
            assert up(tot / len(cl), dd) == e["avg"] and up(statistics.median(cl), dd) == e["med"], (mk, b["k"])
            assert int(100 * sum(1 for v in cl if v > 0) / len(cl) + 0.5) == e["win"], (mk, b["k"])
            assert up(min(cl), 1) == e["lo"]
            assert b["why"] == XA.why(r)
            if r["kind"] != "alloc":
                assert f"{e['win']}%" in b["why"]                                  # 推薦順序旁那一句也是同一份數字


def test_judge_rows_and_grid(R):
    """判定依據（x9xh.json）：每一項過了沒＝訊號總覽同一份（xstratpage.why）；參數鄰近表格數＝組數、原作者參數剛好一格、過關數一致。"""
    from arm.lab import xstratpage as XSP
    for mk, M in R.items():
        for k, r in M.items():
            j = XA.judge(r)
            assert j["why"] == XSP.why(r)
            G = j["grid"]
            cells = [c for row in G["c"] for c in row]
            assert len(cells) == len(r["grid"]) == G["n"] and all(cells)
            assert sum(c[1] for c in cells) == 1 and sum(c[0] for c in cells) == G["ok"] == sum(1 for g in r["grid"] if g["ok"])
            sp = S.BY_KEY[k]
            assert len(G["pn"]) == len(sp["grid"]) and len(G["a"]) == len(list(sp["grid"].values())[0])
            if r["kind"] == "dip":
                assert (j["ref"] is None) == (not (r.get("b1") or {}).get("n"))
            elif k not in ("hal", "tom"):                                    # 日子事先排定的沒有落後一天的問題，沒有對照
                assert j["ref"] and ("原作者時點" in j["ref"] or "隔天收盤" in j["ref"])
            txt = json.dumps(j, ensure_ascii=False)
            assert not [w for w in BANNED if w in txt], (mk, k)
