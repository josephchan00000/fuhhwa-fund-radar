"""手算固定案例（docs/lab_signal_quality_plan.md 第 11.4 節，A-3d）：用真的落檔資料，答案是人工核對過、寫死的。
改程式改壞（或資料被改掉）就會紅。核對方式寫在每個測試的說明；資料不在就跳過。

  ① 大家都知道的收盤值（新聞、交易所公告都查得到）：加權指數、S&P 500、VIX 幾個歷史低點與高點。
  ② 自營商（自行買賣）連續 10 天賣超／買超：每一段的 10 天逐日都是賣超（買超）、前一天不是（原始金額逐日核對）。
  ③ 跌破／站回年線：規則＝連 3 天在 240 日均線的另一邊、之前 10 天都在原來那一邊（heatspec EV_CONF、EV_PRIOR）；
     2007-11～2008-06、2020 年 2～3 月的 S&P 500 在線上下來回，不滿「之前 10 天」→ 沒有事件（照規則，不是漏算）。
"""
import pytest

from arm.lab import heatcalc as HC
from arm.lab import heatdata as HD
from arm.lab import heattech as TT
from arm.lab import sigcat as G

TAIEX = {"2000-02-17": 10202.20, "2008-11-20": 4089.93, "2020-03-19": 8681.34, "2022-10-25": 12666.12,
         "2024-07-11": 24390.03}
SPX = {"1987-10-19": 224.84, "2007-10-09": 1565.15, "2009-03-09": 676.53, "2020-03-23": 2237.40, "2022-10-12": 3577.03}
VIX = {"2008-11-20": 80.86, "2020-03-16": 82.69}
DL_SELL10 = ["2017-12-13", "2018-10-26", "2020-12-16", "2022-12-08", "2023-08-14", "2025-04-24", "2026-10-21"]
DL_BUY10 = ["2015-09-17", "2017-02-15", "2018-03-19", "2019-03-22", "2020-06-05", "2023-05-25", "2024-05-06",
            "2024-05-27", "2025-10-29", "2025-12-05"]
TW_MA240_DN = ["2010-05-24", "2011-08-05", "2012-08-30", "2014-10-15", "2014-12-18", "2015-06-11", "2018-04-26",
               "2018-09-12", "2018-10-08", "2020-03-11", "2022-03-09", "2022-04-11"]      # 2007～2022


def _load(name):
    d = HD.load(name)
    if not d:
        pytest.skip(f"沒有落檔 {name}")
    return d


@pytest.mark.parametrize("name,known", [("taiex", TAIEX), ("us_px_spx", SPX), ("vix", VIX)])
def test_known_closes(name, known):
    s = _load(name)
    for d, v in known.items():
        assert s.get(d) == pytest.approx(v, abs=0.01), (name, d)


def _dealer():
    inst, tx = _load("inst"), _load("taiex")
    cal = sorted(d for d in tx if d >= "2014-11-01" and d <= "2026-10-30")
    return inst, cal


def test_dealer_runs_production_and_by_hand():
    """正式程式（HC.inst_amounts → sigcat.run_days）和手算（原始 Dealer_self 逐日數）都要是寫死的那幾天。"""
    import numpy as np
    inst, cal = _dealer()
    A = HC.inst_amounts(inst)["dl"]
    amt = np.array([np.nan if A.get(d) is None else float(A[d]) for d in cal])
    assert [cal[t] for t in G.run_days(amt, -1, 10)] == DL_SELL10
    assert [cal[t] for t in G.run_days(amt, 1, 10)] == DL_BUY10

    def by_hand(sign):
        out, c = [], 0
        for d in cal:
            v = (inst.get(d) or {}).get("Dealer_self")
            c = c + 1 if v is not None and v * sign > 0 else 0
            if c == 10:
                out.append(d)
        return out
    assert by_hand(-1) == DL_SELL10 and by_hand(1) == DL_BUY10
    for d in DL_SELL10:                                  # 每一段：10 天都賣超、前一天不是
        i = cal.index(d)
        assert all(inst[cal[j]]["Dealer_self"] < 0 for j in range(i - 9, i + 1))
        assert not inst.get(cal[i - 10], {}).get("Dealer_self", 1) < 0


def _events(ks, px, lo, hi):
    ev = TT.all_events(px)
    return {e: [ks[t] for t in idx if lo <= ks[t] <= hi] for e, idx in ev.items()}


def test_year_line_events_taiex():
    """台股用正式的日曆與收盤（heatcalc.calendar：證交所收盤，沒有才用 Yahoo；含 2018 年以前的週六補班日、不含颱風停市日）。"""
    ks, px, _ = HC.calendar({"turnover": _load("turnover"), "taiex": _load("taiex")})
    ev = _events(ks, px, "2007-01-01", "2022-12-31")
    assert ev["ma240_dn"] == TW_MA240_DN
    assert "2008-03-26" in ev["ma240_up"]
    assert not [d for d in ev["ma240_dn"] if "2007-07-01" <= d <= "2010-05-01"]   # 2007～2008 在線上下來回：照規則沒有事件
    # 手算 2020-03-11：3/9、3/10、3/11 收盤在 240 日均線下，之前 10 個交易日都在線上
    i = ks.index("2020-03-11")
    side = [px[j] > sum(px[j - 239:j + 1]) / 240 for j in range(i - 12, i + 1)]
    assert side == [True] * 10 + [False] * 3


def test_year_line_events_spx():
    s = _load("us_px_spx")
    ks = sorted(k for k in s if s[k])
    ev = _events(ks, [s[k] for k in ks], "2020-01-01", "2022-12-31")
    assert ev["ma240_dn"] == ["2022-02-22"]                  # 2020 年 2～3 月在線上下來回：照規則沒有事件
    assert ev["ma240_up"] == ["2020-05-29", "2022-03-22"]
