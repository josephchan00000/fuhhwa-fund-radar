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
            if c["kind"] == "trade" and f.get("n"):
                assert e["n"] == f["n"] and e["win"] == round(f["win"] * 100) and e["base"] == round(f["base"] * 100)
                assert e["avg"] == round(f["avg"] * 100, 2) and e["cagr"] == round(f["cagr"] * 100, 1)
            if c["kind"] == "dip" and f.get("n"):
                assert e["n"] == f["n"] and e["med"] == round(f["med"] * 100, 1) and e["bmed"] == round(f["bmed"] * 100, 1)
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
    assert set(B["rule"]) >= {"n", "win", "edge", "dn", "dwin", "dedge", "dmx", "dadd", "mdd", "grid"}
    size = len(json.dumps(B, ensure_ascii=False, separators=(",", ":")))
    assert size < 90_000, size                                                      # 內嵌在個股頁，別讓頁面變太大
