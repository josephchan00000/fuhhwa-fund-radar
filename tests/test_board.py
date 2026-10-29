"""配置頁・策略總覽（arm/lab/board.py；docs/lab_ia_v5_plan.md 第 15.4、18 節）：四種狀態、淘汰都有原因、
自動列依研究檔判定、config/strategy_board.json 的列與使用者決定（override）、排序與計數、用字。"""
import json

import pytest

from arm.lab import board as BD

BANNED = ("保證", "穩賺", "必賺", "包賺", "必漲", "必跌", "一定會", "唯一", "建議買", "建議賣", "目標價", "零風險", "無風險")


@pytest.fixture(autouse=True)
def _no_real_candidates(monkeypatch):
    """新策略候選讀 config/strategy_candidates.json（每週會變多）、台指期早盤讀研究檔；這裡的計數只看假資料，
    候選列另在 test_candpage、test_futpage 測。"""
    monkeypatch.setattr(BD, "cand_rows", lambda: [])
    monkeypatch.setattr(BD, "fut_rows", lambda: [])
    monkeypatch.setattr(BD, "rare_rows", lambda: [])


def _adv():
    """advice.build 的最小樣子：book（三條 ★ 在三成裡、一條 ●、一條 ○、高股息）＋機會卡＋行事曆。"""
    book = [{"k": k, "name": n, "tier": t, "how": "規則一句", "unit": u,
             "exp": {"n": 30, "avg": 2.5, "win": 61, "mk": 0.8, "lo": -12.0},
             "all": {"cagr": 18.2, "tr_cagr": 9.5, "mdd": 31.0, "tr_mdd": 28.0} if k in ("v3l", "v7m") else {},
             "j": {"win": 61.0}}
            for k, n, t, u in (("v3l", "財報驚喜（大型股）", "good", "期"), ("s3", "臺灣50 提前卡位", "good", "次"),
                               ("s5", "長線投信動能", "good", "筆"), ("s1", "共識加碼", "ref", "檔"),
                               ("v7m", "月營收驚喜（中型股）", "none", "月"), ("hd", "高股息換股", "few", "次"))]
    return {"book": book, "last": "2026-10-22",
            "opp": {"cards": [{"k": "v3l", "held": [{"ent": "2026-08-17", "items": [{"c": "2330"}, {"c": "2317"}]}]}]},
            "cal": [{"d": "2026-11-17", "at": "開盤", "act": "買進", "k": "v3l", "items": [{"c": "2330"}]},
                    {"d": "2026-11-12", "at": "收盤", "act": "賣出", "k": "v3l", "items": []}]}


def _mac():
    return {"mks": ["tw", "spx"], "m": {
        "tw": {"book": [{"k": "rsi2", "name": "RSI(2) 超賣反彈", "tier": "good", "kind": "trade", "how": "跟隨機挑一天比",
                         "tag": "空手", "exp": {"cagr": 7.1, "bcagr": 6.0, "mdd": 22.0, "bmdd": 55.0, "n": 200, "avg": 0.4,
                                                "win": 64, "base": 55}},
                        {"k": "tom", "name": "月底月初", "tier": "none", "kind": "trade", "fail": "勝率比隨便挑一天只高 4.6 點",
                         "exp": {"cagr": 3.0, "bcagr": 6.0, "mdd": 30.0, "bmdd": 55.0}}]},
        "spx": {"book": [{"k": "ma200", "name": "200 日均線", "tier": "ref", "kind": "timing", "tag": "持有中",
                          "exp": {"cagr": 8.0, "bcagr": 9.0, "mdd": 20.0, "bmdd": 55.0}}]}}}


def _stk():
    return {"st": [{"k": "v3l"}, {"k": "s3"}, {"k": "s5"}]}


CONF = {"override": {}, "rows": [
    {"id": "tw:sxlive", "name": "飆股（台股，紙上記錄）", "mkk": "tw", "type": "個股", "st": "obs", "how": "每週記一次", "today": "sxlive"},
    {"id": "tw:p5", "name": "短期反轉週換股", "mkk": "tw", "type": "個股", "st": "out", "why": "2013 年起前後兩段都明顯輸"},
    {"id": "us:qqq", "name": "美股三成改買 QQQ", "mkk": "us", "type": "配置", "st": "out", "why": "只是換一個指數"}]}


def _build(conf=CONF, bundle=None):
    return BD.build({"adv": _adv(), "mac": _mac()}, bundle if bundle is not None else {"stk": _stk()}, conf=conf)


def test_statuses_reasons_and_sorting():
    B = _build()
    rows = B["rows"]
    assert rows and all(r["st"] in BD.STATUS for r in rows)
    assert len({r["id"] for r in rows}) == len(rows)                              # id 不重複
    st = {r["id"]: r["st"] for r in rows}
    assert st["tw:plan"] == st["us:plan"] == "obs"                                # 交易計畫本身（2026-10-28 起在研究紀錄，前瞻照記）
    assert st["tw:v3l"] == st["tw:s3"] == st["tw:s5"] == "use"                    # 選股頁台股主要的三條
    assert st["tw:s1"] == "obs" and st["tw:v7m"] == "out" and st["tw:hd"] == "out"
    assert st["tw:rsi2"] == "obs" and st["spx:ma200"] == "obs" and st["tw:tom"] == "out"
    assert st["tw:sxlive"] == "obs" and st["tw:p5"] == "out" and st["us:qqq"] == "out"
    for r in rows:
        if r["st"] == "out":
            assert (r.get("why") or "").strip(), r["id"]                          # 淘汰的一列一句原因
    order = [BD.STATUS.index(r["st"]) for r in rows]
    assert order == sorted(order)                                                 # 依狀態排
    use = [r for r in rows if r["st"] == "use"]
    assert [r["type"] for r in use] == sorted((r["type"] for r in use), key=BD.TYPES.index)   # 同狀態內：交易計畫 → 個股 → 指數型
    assert B["n"] == {s: sum(r["st"] == s for r in rows) for s in BD.STATUS}
    assert B["nm"]["tw"]["use"] == 3 and B["nm"]["us"]["use"] == 0                # 台股＝三條（這份假資料沒有新飆股、美股強勢品質股）
    why = {r["id"]: r.get("why") for r in rows}
    assert why["tw:tom"] == "勝率比任一天只高 4.6 點"                              # 「隨便挑一天」一律寫「任一天」
    assert why["tw:hd"] == "次數不夠" and why["tw:v7m"] == "每一筆賺錢的比例 61%，賺錢的比例和幅度都不夠"


def test_override_changes_status_and_counts():
    C = json.loads(json.dumps(CONF))
    C["override"] = {"tw:s1": "use", "tw:p5": "cand", "tw:nosuch": "use", "tw:rsi2": "bogus"}
    B = _build(C)
    st = {r["id"]: r["st"] for r in B["rows"]}
    assert st["tw:s1"] == "use" and st["tw:p5"] == "cand" and st["tw:rsi2"] == "obs"   # 不是四種之一的狀態不採用
    assert B["n"]["cand"] == 1 and "tw:nosuch" not in st


def test_today_and_links():
    rows = {r["id"]: r for r in _build()["rows"]}
    assert rows["tw:v3l"]["today"] == "持有 2 檔・11/12 賣"                         # 持有幾檔＋最近一件事
    assert rows["tw:s3"]["today"] == "空手"
    assert rows["tw:v3l"]["go"] == {"go": "st", "at": "st-v3l"}                    # 點名稱開研究紀錄的說明卡
    assert rows["tw:rsi2"]["go"] == {"go": "macst", "at": "ms-rsi2", "gm": "tw"}
    assert rows["tw:plan"]["go"] == {"go": "plan", "pm": "tw"} and rows["us:plan"]["go"] == {"go": "plan", "pm": "us"}   # 交易計畫在研究紀錄（2026-10-28 起）
    assert rows["tw:sxlive"]["today"] in ("還沒有紀錄",) or rows["tw:sxlive"]["today"].startswith("已記 ")


def test_missing_inputs_do_not_raise():
    B = BD.build({}, None, conf={"rows": [], "override": {}})
    st = {r["id"]: r["st"] for r in B["rows"]}
    assert st.get("tw:plan") == st.get("us:plan") == "obs" and B["n"]["use"] == 0   # 計畫本身一定在（觀察中）
    assert BD.load_conf(BD.ROOT / "nope.json") == {"rows": [], "override": {}}


def test_config_file_rows_are_valid():
    C = BD.load_conf()
    assert C["rows"] and isinstance(C["override"], dict)
    ids = [r["id"] for r in C["rows"]]
    assert len(set(ids)) == len(ids)
    for r in C["rows"]:
        assert r["st"] in BD.STATUS and r["type"] in BD.TYPES and r["mkk"] in ("tw", "us", "all"), r
        assert r["name"] and (r["st"] != "out" or r.get("why")), r
        assert ":" in r["id"] and r["id"].split(":")[0] in ("tw", "us", "all"), r
    for k, v in C["override"].items():
        assert v in BD.STATUS, (k, v)
    txt = json.dumps(C, ensure_ascii=False)
    for w in BANNED + ("隨便挑",):
        assert w not in txt, w


def test_rows_have_no_banned_words():
    txt = json.dumps(_build()["rows"], ensure_ascii=False)
    for w in BANNED + ("隨便挑",):
        assert w not in txt, w


def test_plan_names_follow_core_share_and_boom_row():
    """corespec VER 4：計畫的名字照長抱比例（台股兩成、美股全部機動）；新飆股另外一列「使用中」（選股頁台股的第一條）。"""
    from arm.lab import core as CO
    from arm.lab import corespec as S
    R = CO.load()
    stk = dict(_stk(), w=S.sat_of("tw") * 0.5 / 3, bw=S.sat_of("tw") * S.BOOM_SHARE["tw"],
               boom={"d": "2026-10-30", "next": "2026-11-02", "next_wk": "2026-11-06", "w": 0.125,
                     "hold": [{"c": "3017", "n": "奇鋐", "w": 0.5}], "buy": [{"c": "2368", "fill": True}, {"c": "6274", "fill": False}]})
    rows = {r["id"]: r for r in _build(bundle={"stk": stk, "R": R})["rows"]}
    assert rows["tw:plan"]["name"] == "兩成長抱＋警訊（台股）" and rows["us:plan"]["name"] == "全部機動＋警訊（美股）"
    assert "0050 兩成一直抱著；八成一半買新飆股、一半跟著 3 條個股策略" in rows["tw:plan"]["how"]
    assert rows["us:plan"]["how"].startswith("全部買") and "總經策略全部空手就把全部換成現金" in rows["us:plan"]["how"]
    b = rows["tw:boom"]
    assert b["st"] == "use" and b["type"] == "個股" and b["go"] == {"go": "tw", "at": "pk-boom"}
    assert b["today"] == "持有 1 檔・11/2 買 1 檔" and "分 8 格、新上名單的先買" in b["how"] and b["name"] == "新飆股"
    bm = R["mk"]["tw"]["sc"]["plan"]["boom"]
    assert b["perf"] == f"年化 {BD._pc(bm['cagr'] * 100)}" and b["ref"] == f"大盤 {BD._pc(bm['hold']['cagr'] * 100)}"
    nb = {r["id"]: r for r in _build(bundle={"stk": dict(stk, boom={"d": "2026-10-22", "next": "2026-10-27", "next_wk": "2026-10-30"}),
                                              "R": R})["rows"]}
    assert nb["tw:boom"]["today"] == "空手・名單 10/30 收盤產生"
