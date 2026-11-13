"""盤前第 5 段：08:46 用台指期開盤重估 09:01（研究 arm/lab/pmest.py、上線 arm/lab/pm850.py、頁面 arm/lab/premkpage.py；
docs/lab_premarket_plan.md 第 16 節）。"""
import numpy as np

from arm.lab import pm850 as E
from arm.lab import pmest, pmestspec

RES = {"ver": pmestspec.VER, "judge": {"verdict": "過關"}, "full": {"e2": {"med_em": 0.187, "p80_em": 0.355}}}
# 11/11 的真實情況：11/10 加權指數收盤 42,711.92、台指期 11 月（TXFK6）11/10 收 42,623、11/11 08:45 開 42,942 → 研究的 E2＝43,031
PM = {"d": "2026-11-10", "next": "2026-11-11", "close": 42711.92, "tx": {"sym": "202611", "close": 42623}, "night": {"sym": "TXFK6-M"},
      "em": 1000, "est": 42614}
Q = [{"SymbolID": "TXF-S", "COpenPrice": "", "CRefPrice": "42711.92"},
     {"SymbolID": "TXFA7-F", "CTime": "085317", "COpenPrice": "43199.00", "CRefPrice": "42748.00", "CTotalVolume": "2"},
     {"SymbolID": "TXFK6-F", "CTime": "084500", "COpenPrice": "42942.00", "CRefPrice": "42646.00", "CTotalVolume": "5535"}]


def test_month_symbol():
    assert E.month_sym("202611") == "TXFK6" and E.month_sym("202701") == "TXFA7" and E.month_sym("2026") is None


def test_estimate_matches_research_e2_for_11_11():
    e = E.estimate(PM, Q, RES, "084610", "2026-11-11")
    assert e["sym"] == "TXFK6-F" and e["est"] == 43031 and e["ref"] == 42623 and e["ref_src"] == "昨天 13:45 收盤"
    assert e["typ"] == 187 and e["p80"] == 355 and e["early"] == 42614 and e["t"] == "08:46"


def test_estimate_refuses_stale_or_unvalidated_quotes():
    assert E.estimate(PM, Q, RES, "084400", "2026-11-11") is None                         # 08:45 之前（CTime 比現在晚）
    assert E.estimate(PM, [dict(q, CDate="20261110") for q in Q], RES, "084610", "2026-11-11") is None   # 前一天的報價
    assert E.estimate(PM, [dict(q, CTime="134500") for q in Q], RES, "084610", "2026-11-11") is None    # 昨天收盤那筆
    assert E.estimate(PM, [dict(q, COpenPrice="") for q in Q], RES, "084610", "2026-11-11") is None     # 還沒開盤
    assert E.estimate(PM, Q, RES, "084610", "2026-11-12") is None                          # 盤前作戰圖不是今天的
    assert E.estimate(PM, Q, dict(RES, judge={"verdict": "沒過"}), "084610", "2026-11-11") is None
    assert E.estimate(PM, Q, dict(RES, ver=pmestspec.VER + 1), "084610", "2026-11-11") is None


def test_estimate_falls_back_to_reference_price_when_contract_rolls():
    pm = dict(PM, tx={"sym": "202610", "close": 41000})                                  # 結算日隔天：昨天的近月已經不是這一口
    e = E.estimate(pm, Q, RES, "084610", "2026-11-11")
    assert e["ref"] == 42646 and e["ref_src"] == "期交所參考價" and e["est"] == round(42711.92 + 42942 - 42646)


def test_pick_uses_volume_when_night_symbol_missing():
    assert E.pick(Q, {"night": {}})["SymbolID"] == "TXFK6-F"
    assert E.pick([{"SymbolID": "TXFK6-F", "CTotalVolume": "0"}], {}) is None


def test_apply_keeps_recent_and_only_same_day():
    log = {f"2026-01-{d:02d}": {"est": 1} for d in range(1, 31)}
    e = E.estimate(PM, Q, RES, "084610", "2026-11-11")
    assert not E.apply(dict(PM, next="2026-11-12"), e, log)
    pm = dict(PM)
    assert E.apply(pm, e, log) and pm["e850"]["est"] == 43031 and E.cur(pm) == e
    assert log["2026-11-11"]["est"] == 43031 and len(log) == 31
    E.KEEP, keep = 5, E.KEEP
    try:
        E.apply(pm, e, log)
        assert sorted(log)[-1] == "2026-11-11" and len(log) == 5
    finally:
        E.KEEP = keep
    assert E.cur(dict(pm, next="2026-11-12")) is None                                    # 隔天就不算數


def test_attach_to_recent_checks():
    from arm.lab.premkt import attach_e850
    chk = [{"d": "2026-11-10", "est": 1, "open": 2}, {"d": "2026-11-11", "est": 42611, "open": 43296}]
    attach_e850(chk, {"2026-11-11": {"est": 43031}})
    assert "e850" not in chk[0] and chk[1]["e850"] == 43031


def test_page_uses_reestimate_and_shows_column():
    from arm.lab import premkpage
    e = E.estimate(PM, Q, RES, "084610", "2026-11-11")
    pm = dict(PM, hi=43000, lo=42000, est_src="夜盤收盤", made="2026-11-11 05:12", facts=[], warn=[], bands=[], sc=[],
              v={"typ": 229, "p80": 463, "q2": {"x": [0.5, 1.0], "up": [0.3, 0.1], "dn": [0.4, 0.2]}, "n1": 1, "n2": 1},
              check=[{"d": "2026-11-10", "est": 42626, "open": 42706, "hi": 43136, "lo": 41930},
                     {"d": "2026-11-11", "est": 42614, "open": 43296, "hi": 44257, "lo": 42708, "e850": 43031}])
    h0 = premkpage.block(pm)
    assert 'data-to="42614"' in h0 and "平常差 <b>±229</b>" in h0 and "已用台指期開盤重估" not in h0
    E.apply(pm, e, {})
    h = premkpage.block(pm)
    assert 'data-to="43031"' in h and "平常差 <b>±187</b>" in h and "十次有八次在 <b>±355</b> 內" in h
    assert "08:46 已用台指期開盤重估（清晨估 42,614，+417）" in h and "08:46 用台指期開盤 42,942 重估" in h
    assert "預估 43,031" in h                                                             # 「今天可能走多遠」以重估為中心
    rec = h.split('id="pzrec"', 1)[1]
    assert "<th>08:46 重估</th>" in rec and "<td>43,031</td><td>+265</td>" in rec and "<td>—</td><td>—</td>" in rec
    assert "08:46 用台指期開盤重估的 1 天平均差 <b>265</b> 點" in rec
    assert "<b>08:46 重估</b>" in h                                                      # 「這些數字怎麼來的」有說明


def test_research_judge_logic(monkeypatch):
    rng = np.random.default_rng(1)
    rs = []
    for i in range(200):
        o = 10000 + rng.normal(0, 50)
        rs.append({"d": f"2020-{1 + i // 28:02d}-{1 + i % 28:02d}", "o": o, "c": 10000.0, "em": 100.0,
                   "e1": o + rng.normal(0, 40), "e2": o + rng.normal(0, 20)})
    monkeypatch.setattr(pmest, "rows", lambda root, log=print: rs)
    monkeypatch.setattr(pmest, "e3_rows", lambda r: [])
    out = pmest.run(".", log=lambda *a: None)
    assert out["judge"]["verdict"] == "過關" and out["judge"]["ok"] == {"gain": True, "h1": True, "h2": True}
    assert out["full"]["e2"]["med"] < out["full"]["e1"]["med"] and out["n"] == 200 and "e3" not in out
    for r in rs:
        r["e2"] = r["e1"]
    assert pmest.run(".", log=lambda *a: None)["judge"]["verdict"] == "沒過"


def test_restore_keeps_reestimate_when_premkt_is_rebuilt():
    """2026-11-13 踩到：08:46 重估之後，09 點多 daily.yml 重算盤前作戰圖、整份重寫，e850 不見、頁面變回清晨的估。
    premkt.build 重算時從紀錄檔 e850.json 掛回去。"""
    e = E.estimate(PM, Q, RES, "084610", "2026-11-11")
    log = {}
    E.apply(dict(PM), e, log)
    pm = dict(PM)                                                                       # 重算出來的新一份：沒有 e850
    assert E.restore(pm, log, RES) and E.cur(pm)["est"] == 43031 and pm["e850"]["p80"] == 355 and pm["e850"]["early"] == 42614
    assert not E.restore(dict(PM, next="2026-11-12"), log, RES)                          # 別天的不掛
    assert not E.restore(dict(PM), log, dict(RES, judge={"verdict": "沒過"}))           # 研究沒過不掛
