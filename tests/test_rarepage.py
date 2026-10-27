"""少見但勝率高的策略的頁面（arm/lab/rarepage.py）：配置頁策略表九列（照主頁面用字）、研究紀錄頁一段、06:35 推播提醒。"""
from __future__ import annotations

import re
from urllib.parse import unquote

import pytest

from arm.lab import board as BD
from arm.lab import rare as RA
from arm.lab import rarepage as RP
from arm.lab import rarespec as S
from arm.lab import valog as VL

# 主頁面不能出現的字（docs/lab_ia_v5_plan.md 第 8 節；同 tests/test_plain.py）
NOT_PLAIN = ("只當參考", "看不出", "樣本", "亂排", "打亂", "預估之後", "逐年檢查", "判定", "前後兩半", "樣本外", "穩健度",
             "對照", "規格", "VER", "門檻", "區間", "研究", "注意", "教訓", "本頁", "我們", "信賴", "顯著",
             "★", "●", "○", "◆", "△", "好策略", "可參考", "核心", "衛星", "亮", "前瞻", "→", "←")
BANNED = ("保證", "穩賺", "必賺", "包賺", "必漲", "必跌", "一定會", "唯一", "建議買", "建議賣", "目標價", "零風險", "無風險")


@pytest.fixture(scope="module")
def B():
    b = RP.load()
    if not b.get("res"):
        pytest.skip("研究檔還沒產生")
    return b


def test_board_rows_nine_observing_in_plain_words(B):
    rows = RP.board_rows(B)
    assert [r["id"] for r in rows] == [f"{R['home']}:rare:{R['k']}" for R in S.RULES]
    for r in rows:
        assert r["st"] == "obs" and r["type"] in BD.TYPES and r["href"] == f"x9r.html#rare-{r['id'].split(':')[-1]}"
        assert r["mkk"] in ("tw", "us") and r["today"] and r["perf"].startswith("賺錢 ") and r["ref"].startswith("任一天 ")
        assert r["sub"].endswith(("建議試用", "可以觀察", "不建議"))
        txt = " ".join(str(v) for v in r.values())
        assert not [w for w in NOT_PLAIN + BANNED if w in txt], txt
    labs = {r["id"].split(":")[-1]: r["sub"].split("・")[-1] for r in rows}
    want = {R["k"]: S.REC_NAMES[B["res"]["rules"][R["k"]][R["home"]]["rec_v"]] for R in S.RULES}
    assert labs == want


def test_board_build_includes_rare_rows(monkeypatch, B):
    monkeypatch.setattr(BD, "cand_rows", lambda: [])
    monkeypatch.setattr(BD, "fut_rows", lambda: [])
    monkeypatch.setattr(RP, "load", lambda: B)
    out = BD.build({}, {}, {"rows": [], "override": {}})
    ids = {r["id"] for r in out["rows"]}
    assert {f"{R['home']}:rare:{R['k']}" for R in S.RULES} <= ids


def test_now_text_cases():
    assert RP.now_text("mid", {"st": "wait", "bd": "2026-11-03", "qd": "2027-11-02"}) == "11/3（二）收盤買"
    assert RP.now_text("mid", {"st": "wait", "bd": "2026-11-03", "qd": "2027-11-02"}, short=False) == \
        "下一次：2026/11/3（二）收盤買進，2027/11/2 收盤賣出"
    assert RP.now_text("santa", {"st": "hold", "bd": "2026-12-23", "qd": "2027-01-05", "chg": 0.012}) == "持有中・1/5 收盤賣"
    assert RP.now_text("lnypre", {"st": "wait", "bd": "2027-01-27", "qd": "2027-02-03", "approx": True}) == "1/27（三）收盤買（約）"
    assert RP.now_text("ath", {"st": "wait", "ath": "2026-10-06", "since": 14, "need": 250, "off": -0.018}) == "沒有觸發（10/6 才創新高）"
    assert RP.now_text("ath", {"st": "wait", "ath": "2025-01-06", "since": 300, "need": 250}) == "再創新高就買（已經 300 天沒有新高）"
    assert RP.now_text("bull", {"st": "wait", "bear": True, "low": 5000.0, "confirm": 6000.0, "px": 5500.0}) == "熊市中：漲到 6,000 就買"
    assert RP.now_text("vixinv", {"st": "wait", "ratio": 0.9223, "rd": "2026-10-26"}) == "沒有觸發（VIX ÷ VIX3M＝0.92）"
    assert RP.now_text("nsf", {"st": "wait"}) == "等國安基金下一次進場"
    assert RP.now_text("jan", {"st": "buy", "bd": "2027-02-01", "qd": "2027-12-31"}) == "2/1（一）收盤買"


def test_reminders_two_trading_days_ahead(B):
    """11/2 早上（美股資料到 10/30）與 11/3 早上（到 11/2）都提醒 11/3 收盤買；11/4 早上（到 11/3）就不提了（已經持有）。"""
    rec = {"res": B["res"], "now": {"mid": {"spx": {"st": "wait", "bd": "2026-11-03", "qd": "2027-11-02", "last": "2026-10-30"}}}}
    if B["res"]["rules"]["mid"]["spx"]["rec_v"] != "rec":
        pytest.skip("期中選舉不是建議試用")
    td = RP.reminders(rec)
    assert td == [["2026-11-03", "買", "spx", "mid", "2027-11-02"]]
    assert RP.remind_line(td) == "少見機會：11/3（二）收盤 S&P 500 買進（期中選舉後抱一年，抱到 2027/11/2）。"
    rec["now"]["mid"]["spx"]["last"] = "2026-11-02"
    assert RP.reminders(rec)
    rec["now"]["mid"]["spx"]["last"] = "2026-10-29"                       # 10/30、11/2 兩天內沒有 → 不提
    assert RP.reminders(rec) == []
    rec["now"]["mid"]["spx"] = {"st": "hold", "bd": "2026-11-03", "qd": "2027-11-02", "last": "2026-11-03"}
    assert RP.reminders(rec) == []
    # 賣出前兩天也提醒
    rec["now"]["santa"] = {"spx": {"st": "hold", "bd": "2026-12-23", "qd": "2027-01-05", "last": "2027-01-01"}}
    if B["res"]["rules"]["santa"]["spx"]["rec_v"] == "rec":
        assert RP.remind_line(RP.reminders(rec)) == "少見機會：1/5（二）收盤 S&P 500 賣出（聖誕老人行情）。"
    # 可以觀察的規則不提醒
    rec["now"] = {"jan": {"spx": {"st": "buy", "bd": "2027-02-01", "qd": "2027-12-31", "last": "2027-01-29"}}}
    assert RP.reminders(rec) == []


def test_push_line_added_to_valog(monkeypatch):
    rec = {"todo": {"d": "2026-11-02", "items": []}, "rare": {"td": [["2026-11-03", "買", "spx", "mid", "2027-11-02"]]}}
    out = VL.push_lines(rec)
    assert out[0] == "11/2（一）沒有排定的買賣。"
    assert out[1] == "少見機會：11/3（二）收盤 S&P 500 買進（期中選舉後抱一年，抱到 2027/11/2）。"
    assert VL.push_lines({"todo": {"d": "2026-11-02", "items": []}}) == ["11/2（一）沒有排定的買賣。"]
    monkeypatch.setattr(RP, "reminders", lambda B=None: [])
    assert VL.rare_state() is None


def test_research_body_cards_csv(B):
    h = RP.research_body(B)
    assert 'id="rare-body"' in h and h.count('class="cdcard"') == len(S.RULES)
    for R in S.RULES:
        assert f'id="rare-{R["k"]}"' in h and f'href="#rare-{R["k"]}"' in h
    m = re.search(r'download="rare_trades.csv" href="data:text/csv;charset=utf-8,([^"]+)"', h)
    csv = unquote(m.group(1))
    assert csv.startswith("﻿規則,市場,") and "mid,spx,1950-11-06,1950-11-06," in csv
    n = sum(len(x.get("tr") or []) for v in B["res"]["rules"].values() for x in v.values())
    assert csv.count("\n") == n + 1                                          # 表頭、代號對照＋每一次
    assert "來源發表之後" in h and "S&amp;P 500 1950 年以前" in h and "前一半" in h
    assert not [w for w in BANNED if w in h]


def test_research_page_hosts_rare_section(B):
    from arm.lab import research_page as RPG
    h = RPG.body({"rare": RP.research_body(B)})
    assert '<section class="rsec" id="rare">' in h and 'data-g="rare"' in h
    assert h.index('id="rare"') < h.index('id="fut"')


def test_nsf_extra_dates_only_after_spec(tmp_path, monkeypatch):
    p = tmp_path / "rare_events.json"
    p.write_text('{"nsf": [["2020-03-20", "舊的不收"], ["2027-03-15", "新的"]]}', encoding="utf-8")
    monkeypatch.setattr(RA, "EVENTS", p)
    got = RA.nsf_list()
    assert ("2027-03-15", "新的") in got and len(got) == len(S.NSF) + 1
    p.write_text("壞掉", encoding="utf-8")
    assert RA.nsf_list() == sorted(S.NSF)


def test_pending_signal_on_last_day():
    """事件型：資料最後一天收盤剛出現訊號 → 現在＝下一個交易日收盤買。"""
    cal = [f"2026-01-{d:02d}" for d in (5, 6, 7, 8, 9, 12, 13, 14, 15, 16)]
    px = [100.0, 99, 98, 97, 96, 95, 94, 93, 92, 101]                       # 最後一天創新高（隔了 9 天）
    D = {"mk": "spx", "cal": cal, "px": __import__("numpy").array(px), "vixa": None, "v3a": None}
    M = RA.Mkt.__new__(RA.Mkt)
    M.mk, M.D, M.cal, M.px, M.T, M.c, M.s0, M.r0 = "spx", D, cal, D["px"], len(cal), 0.0, 0, 0
    R = {**S.BY_KEY["ath"], "p": {"gap": 5, "H": 3}}
    fut = ["2026-01-20", "2026-01-21", "2026-01-22", "2026-01-23"]
    t, b, q, qd = RA.pending(M, R, fut)
    assert (t, b, q) == (9, 10, 13) and qd == "2026-01-23"
