"""台指期早盤策略的頁面（arm/lab/futpage.py）：配置頁策略表一列（照主頁面用字）、研究紀錄頁一段（每一筆可下載）。"""
from __future__ import annotations

import re
from urllib.parse import unquote

from arm.lab import board as BD
from arm.lab import futpage as FPG
from arm.lab import futres as FR

# 主頁面不能出現的方法字（docs/lab_ia_v5_plan.md 第 8 節；同 tests/test_plain.py）
NOT_PLAIN = ("只當參考", "看不出", "樣本", "亂排", "打亂", "預估之後", "逐年檢查", "判定", "前後兩半", "樣本外", "穩健度",
             "對照", "規格", "VER", "門檻", "區間", "研究", "注意", "教訓", "本頁", "我們", "信賴", "顯著")
BANNED = ("保證", "穩賺", "必賺", "包賺", "必漲", "必跌", "一定會", "唯一", "建議買", "建議賣", "目標價", "零風險", "無風險")


def _sim(why, net, t_in=32371, t_out=32405):
    return [t_in, 48425, t_out, 48403, why, net, 11, -20, 0]


def _B(pre=()):
    days = [{"d": "2026-09-09", "dp": "2026-09-08", "skip": "前一個交易日沒有資料"},
            {"d": "2026-10-13", "dp": "2026-10-12", "c": "202610", "f": 48426, "est": 48413.87, "basis": 177.04, "div": 0.09,
             "ip": 48600.0, "e": 164.99, "th": 72.43, "side": "long", "pts": [20, 4, 41, 122],
             "L": _sim("stop", -24.54), "S": _sim("trail", -18.5), "Lr": _sim("stop", -12.5), "Sr": None,
             "mv": [-25, -4, 135, 221, 57]},
            {"d": "2026-10-14", "dp": "2026-10-13", "c": "202610", "f": 48764, "est": 48617.55, "basis": 141.69, "div": 0.0,
             "ip": 48413.0, "e": -4.76, "th": 76.57, "side": None, "pts": [20, 4, 40, 121],
             "L": _sim("stop", -25.6), "S": _sim("trail", -4.6), "Lr": None, "Sr": None, "mv": [-8, -49, -56, 199, 133]}]
    R = {"spec_ver": 1, "cols": list(FR.SIM_COLS), "catch_at": [a for a, _ in FR.CATCH],
         "lookahead": {"days": days, "n_days": 2, "placebo_p": 0.15, "verdict": "wait",
                       "main": FR.summarize([-24.54]),
                       "compare": {"raw_points": FR.summarize([-12.5]), "always_long": FR.summarize([-24.54, -25.6]),
                                   "always_short": FR.summarize([-18.5, -4.6])},
                       "catchup": {"all": FR.catchup([d for d in days if "e" in d]),
                                   "traded": FR.catchup([d for d in days if "e" in d], only_traded=True)}}}
    return {"R": R, "pre": list(pre)}


def test_board_row_is_candidate_in_plain_words():
    r = FPG.board_rows(_B())[0]
    assert r["id"] == "tw:fut" and r["st"] == "cand" and r["type"] in BD.TYPES and r["mkk"] == "tw"
    assert r["href"] == "x9r.html#fut"
    assert r["today"] == "記錄中・開盤前取樣還沒開始" and r["sub"] == "台指期每一筆成交已存 2 天"
    assert FPG.board_rows(_B(pre=["2026-10-28"]))[0]["today"] == "記錄中・開盤前取樣 1 天（滿 60 天看結果）"
    txt = " ".join(str(v) for v in r.values())
    assert not [w for w in NOT_PLAIN + BANNED if w in txt]


def test_board_build_includes_fut_row(monkeypatch):
    monkeypatch.setattr(BD, "cand_rows", lambda: [])
    monkeypatch.setattr(FPG, "load", lambda: _B())
    B = BD.build({}, {}, {"rows": [], "override": {}})
    rows = {r["id"]: r for r in B["rows"]}
    assert rows["tw:fut"]["st"] == "cand" and B["n"]["cand"] == 1


def test_research_body_trades_csv_and_days():
    h = FPG.research_body(_B())
    assert 'id="fut-body"' in h and "futspec VER 1" in h
    assert "10/13" in h and "停損" in h and "−24.5" in h                       # 有做的那一筆
    m = re.search(r'download="fut_trades.csv" href="data:text/csv;charset=utf-8,([^"]+)"', h)
    csv = unquote(m.group(1))
    assert csv.startswith("﻿日期,") and "2026-10-13,202610,做多,164.99,72.43,08:59:31,48425,09:00:05,48403,停損,-24.54" in csv
    assert csv.count("\n") == 1                                                # 表頭＋一筆（10/14 沒做）
    assert "前一個交易日沒有資料" in h and "不做" in h                           # 每天的落差：沒算的日子、沒做的日子
    assert "下載每一筆" in h and "一定高估" in h
    assert not [w for w in BANNED if w in h]


def test_research_body_without_data():
    h = FPG.research_body({"R": {}, "pre": []})
    assert "還沒有交易" in h and "開盤前取樣 0 天" in h
