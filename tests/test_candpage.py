"""新策略候選的頁面（arm/lab/candpage.py）：策略表的列（狀態、成績一行、今天、白話）、研究紀錄頁的卡、06:35 推播一行（valog）。"""
from arm.lab import candpage as CP
from arm.lab import candspec as CS
from arm.lab import valog as VL

METHOD = ("只當參考", "看不出", "樣本不足", "亂排", "打亂", "預估之後", "判定", "前後兩半", "樣本外", "穩健度", "對照", "規格",
          "VER", "門檻", "區間", "研究", "注意", "我們", "隨便挑一天", "樣本", "★", "●", "○", "核心", "衛星", "前瞻", "→")


def _it(cid, **kw):
    it = {"id": cid, "found": "2026-10-25", "name": f"候選{cid}", "mk": "spx", "engine": "index", "kind": "alloc",
          "how": "收盤在 200 日均線上就拿", "src": [{"t": "Faber（2007）", "u": "https://example.org/faber"}], "why": "規則清楚",
          "p": {"n": 200}, "grid": {"n": [150, 200, 250]}, "sha": "a" * 64}
    it.update(kw)
    return it


def _plan(m_new, m_cur, ok):
    sc = lambda m: {"a": "2014-01-02", "b": "2026-10-23", "plan": {"m": m, "mdd": 0.3, "cagr": 0.1}, "hold": {"m": 3.0},
                    "halves": [{"a": "2014-01-02", "b": "2020-05-01", "plan": {"m": m / 2}},
                               {"a": "2020-05-01", "b": "2026-10-23", "plan": {"m": m / 2}}]}
    return {"cur": sc(m_cur), "new": sc(m_new), "judge": {"money": ok, "halves": ok, "mdd": True, "pass": ok}}


def _B():
    items = [_it("c001"),
             _it("c002", mk="tw", engine="tw_stock", kind="per", b="L", p={"look": 126}, pick={"top": 0.0, "nmin": 5},
                 grid={"look": [105, 126, 147], "pick": [[0.0, 3], [0.0, 5], [0.0, 8]]}),
             _it("c003", kind="trade"), _it("c004", kind="dip", H=60),
             {k: v for k, v in _it("c005").items() if k not in ("p", "grid", "sha")} | {"need": "需要資料：每天的分點進出"},
             _it("c006", mk="us", engine="us_stock", kind="book", ex={"slots": 8, "ma": 50})]
    res = {
        "c001": {"v": "good", "x": {"full": {"cagr": 0.091, "mdd": 0.23}, "bh": {"cagr": 0.086, "mdd": 0.57}},
                 "plan": {"spx": _plan(21.0, 20.2, True)}},
        "c002": {"v": "ref", "x": {"acc": {"cagr": 0.15, "mdd": 0.35}, "tr": {"cagr": 0.18, "mdd": 0.29},
                                   "full": {"n": 40, "avg": 2.1, "win": 61.0}}, "plan": {"tw": _plan(12.0, 13.07, False)}},
        "c003": {"v": "none", "x": {"full": {"n": 120, "avg": 0.004, "win": 0.58, "base": 0.6, "cagr": 0.05, "mdd": 0.3},
                                   "bh": {"cagr": 0.086, "mdd": 0.57}}},
        "c004": {"v": "few", "x": {"full": {"n": 4, "win": 0.75, "base": 0.7}, "curve": {"cagr": 0.02, "mdd": 0.1},
                                   "bh": {"cagr": 0.086, "mdd": 0.57}}},
        "c006": {"v": "good", "x": {"full": {"cagr": 0.21, "mdd": 0.33}, "spx": {"cagr": 0.136, "mdd": 0.34}},
                 "plan": {"spx": _plan(25.0, 20.2, True), "ndx": _plan(26.0, 24.0, True)}},
    }
    dec = {"c003": {"dec": "reject", "d": "2026-10-27", "why": "勝率不夠"}, "c002": {"dec": "trial", "d": "2026-10-27"},
           "c006": {"dec": "adopt", "d": "2026-10-27"}}
    live = {"c002": {"start": "2026-10-28", "r": {"2026-10-28": 0.01, "2026-10-29": -0.005}, "h": {"2026-10-28": 0.0}}}
    return {"items": items, "res": res, "dec": dec, "live": live}


def test_board_rows_status_today_and_perf():
    rows = {r["id"]: r for r in CP.board_rows(_B())}
    a = rows["cand:c001"]
    assert a["st"] == "cand" and a["today"] == "過關，等你決定" and a["type"] == "指數型" and a["mkk"] == "us"
    assert a["perf"] == "年化 9.1%" and a["ref"] == "一直抱著 8.6%" and a["mdd"] == "23%" and a["mddr"] == "57%"
    assert a["sub"] == "放進計畫：100 萬變 2,100 萬（現在 2,020 萬）" and a["href"] == "x9r.html#cand-c001"
    assert a["src"] == "https://example.org/faber"
    b = rows["cand:c002"]
    assert b["st"] == "obs" and b["today"] == "試用中・記了 2 天" and b["type"] == "個股" and b["mkk"] == "tw"
    assert b["perf"] == "年化 15.0%" and b["ref"] == "大盤 18.0%"
    assert b["sub"].startswith("40 期・每期 +2.1%・賺錢 61%") and "沒有比較好" in b["sub"]
    c = rows["cand:c003"]
    assert c["st"] == "out" and c["why"] == "勝率不夠"
    d = rows["cand:c004"]
    assert d["today"] == "次數不夠，等你決定" and d["sub"].startswith("4 次・抱完賺錢 75%")
    e = rows["cand:c005"]
    assert e["st"] == "cand" and e["today"] == "需要資料：每天的分點進出" and e["perf"] == "—"
    f = rows["cand:c006"]
    assert f["st"] == "obs" and f["today"] == "納入，等計畫改版" and f["ref"] == "S&P 500 含息 13.6%"
    assert "放進S&P 500計畫" in f["sub"]                                           # 兩個計畫都有：寫第一個並標名稱


def test_board_rows_plain_wording():
    for r in CP.board_rows(_B()):
        txt = " ".join(str(r.get(k) or "") for k in ("name", "how", "perf", "ref", "mdd", "mddr", "sub", "today", "why"))
        for w in METHOD:
            assert w not in txt, (r["id"], w, txt)


def test_research_body_cards_and_empty():
    h = CP.research_body(_B())
    for cid in ("c001", "c002", "c003", "c004", "c005", "c006"):
        assert f'id="cand-{cid}"' in h and f'href="#cand-{cid}"' in h
    assert "https://example.org/faber" in h and "需要資料：每天的分點進出" in h
    assert "試用紀錄" in h and "不納入" in h and "勝率不夠" in h
    empty = CP.research_body({"items": [], "res": {}, "dec": {}, "live": {}})
    assert "目前沒有候選" in empty


def test_valog_push_line_new_once_and_full(monkeypatch):
    B = _B()
    monkeypatch.setattr(CP, "load", lambda: B)
    cur = VL.cand_state(None)
    assert set(cur["ids"]) == {"c001", "c002", "c003", "c004", "c005", "c006"} and len(cur["new"]) == 6
    line = VL.cand_line(cur)
    assert line.startswith("策略候選：新增 候選c001（S&P 500），過去成績過關") and line.endswith("回「試用／納入／不納入」。")
    again = VL.cand_state(cur)
    assert again["new"] == [] and VL.cand_line(again) is None                     # 第二天不再推
    monkeypatch.setattr(CS, "MAX_OPEN", 3)
    full = VL.cand_state({"ids": cur["ids"], "open": 2})
    assert full["full"] and "週報先停" in VL.cand_line(full)
    assert not VL.cand_state({"ids": cur["ids"], "open": 3})["full"]               # 已經提醒過就不再提醒


def test_push_lines_include_cand_line():
    rec = {"todo": {"d": "2026-10-27", "items": []}, "cand": {"new": ["X（台股），過去成績過關"], "ids": ["c001"], "open": 1}}
    out = VL.push_lines(rec)
    assert out[0].startswith("10/27") and out[-1].startswith("策略候選：新增 X（台股）")
