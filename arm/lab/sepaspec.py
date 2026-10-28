"""用《超級績效》的選股邏輯挑台股（W9）的規格。VER 1：2026-10-29，算任何報酬之前寫定（docs/lab_sepa_pick_plan.md）。

使用者 2026-10-28：「根據超級績效的選股邏輯去挑 詳細規劃後跟我討論然後逐步執行」。看過規劃後選了（AskUserQuestion）：
基本面＝照書三關、怎麼賣＝跌破 50 日線才賣、判定＝贏新飆股才換、大盤＝看（加權指數在 200 日線以下不買新的）。

選股（SCREEN，每週最後一個交易日收盤）：特徵＝superx.feats_on（頁面每天算飆股候選的同一套：含息還原收盤、
  季報在法定期限後、月營收在次月 10 日後才算拿得到；只算合格股票＝20 日均成交值 ≥ 1,000 萬、最近月底市值 ≥ 40 億、
  上市滿 60 個交易日）。主規格 MAIN＝
    ① 趨勢樣板 8 條全過（tt_all，含 RS ≥ 70）；② RS ≥ 80；
    ③ 最新一季 EPS 比去年同季多 25% 以上（ey）、近 3 個月營收比去年同期多 25% 以上（ry3）；
    ④ EPS 或營收的成長在加速（eacc > 0 或 racc > 0）。
  缺值＝不通過（去年同季虧損的公司沒有 EPS 年增率）。另外也要是回測引擎當天的合格股票（同 W7 的訊號）。
排序（RANK）：依 RS 原始分數（0.4·r63＋0.2·r126＋0.2·r189＋0.2·r252，含息還原收盤）由高到低；
  RS 名次是這個分數的排名，所以等於「RS 由高到低、同分依原始分數」。分數一樣時引擎依訊號順序（代號由小到大）。
買賣（TRADE）：和新飆股（W7 的 R60）同一個引擎、同一套成本——訊號隔天開盤買，依排序、每檔用這條策略 12.5% 的錢，
  現金不夠就買少一點或買不到；1,000 股一張、單檔 ≤ 總資產 20%、≤ 前 20 日平均成交量 5%、最多 20 檔；
  開盤一價到底漲停買不到；已經拿著的不重複買。
  主規格出場 EXIT＝收盤（含息還原）跌破 50 日均線 → 隔天開盤賣；不停損、沒有持有天數上限（一價到底跌停延後）。
  大盤 MARKET＝訊號那天加權指數收盤在 200 日均線以下 → 不買新的（已經拿著的照出場規則賣）；
  只看 200 日線（不加「新高家數 − 新低家數」，那是 S01 的寫法，規劃時沒有跟使用者提）。
期間（PERIOD）：主要＝新飆股逐年規則開始的 2019-01-02 起一次連續跑到資料最後一天；前後兩半照 W7（2019–2022、2023 起）。
  另外 2014-01-02 起跑一次，只描述（新飆股沒有 2014–2018）。
比較（COMPARE）：新飆股＝W7 的 R60（用 W7_results.json 存的逐年規則重建訊號、同一套引擎重跑；年化必須和 W7 存的相同，
  否則不出結果）；加權報酬指數（含息）；合格股票等權（每天再平衡、不含成本）。
判定（PASS，只看主規格、2019 起）：
  換＝①整段年化、前半年化、後半年化都比新飆股高，而且 ②整段最大回落沒有比新飆股深超過 mdd_extra 個百分點；
  觀察＝沒有「換」，但前後兩半的年化都比加權報酬指數高 → 放研究紀錄觀察；
  沒有用＝兩個都不是。
只描述（VARIANTS，照算、全部列出、不判定、不能因為比較好看就改用）：
  選股寬嚴（主規格／更嚴：EPS 和營收都在加速／只看趨勢與強度：①＋②）× 出場（跌破 50 日線／抱 60 個交易日）× 大盤（看／不看），
  另加書的 8% 停損＋跌破 50 日線（主規格選股與大盤）。
報告（REPORT）：年化、最大回落、逐年、前後兩半、筆數、賺錢比例、每筆中位數、最賺 10 筆占全部獲利、平均持有天數、平均持股比例、
  每週通過幾檔與實際買了幾檔、和新飆股同一天買同一檔的比例。
已經看過的（PRIOR）：P4.0（照書買賣）、P5（84 組＋保留期）、W3（單一條件的命中率）、W5（VCP）、W8（新飆股的出場）的結果，
  以及規劃第 3 節每週通過幾檔的次數。出場選「跌破 50 日線」是使用者看過規劃第 1 節之後選的。
要改就 VER＋1、寫進規劃文件，不在舊版本上改。
"""
from __future__ import annotations

VER = 1
SPEC_DATE = "2026-10-29"

# (特徵鍵, 比較, 門檻)；OR 群組寫成 ("or", [條件…])
MAIN = (("tt_all", "=", True), ("rs", ">=", 80), ("ey", ">=", 0.25), ("ry3", ">=", 0.25),
        ("or", (("eacc", ">", 0), ("racc", ">", 0))))
SCREENS = {
    "main": MAIN,
    "strict": (("tt_all", "=", True), ("rs", ">=", 80), ("ey", ">=", 0.25), ("ry3", ">=", 0.25),
               ("eacc", ">", 0), ("racc", ">", 0)),
    "trend": (("tt_all", "=", True), ("rs", ">=", 80)),
}
RS_WEIGHTS = ((63, 0.4), (126, 0.2), (189, 0.2), (252, 0.2))

TRADE = {"weight": 0.125}                         # 其餘照引擎預設（和 W7 的 R60 相同）
EXITS = {"ma50": {"ma_exit": 50, "max_hold": None, "stop": None},
         "hold60": {"ma_exit": None, "max_hold": 60, "stop": None},
         "book": {"ma_exit": 50, "max_hold": None, "stop": 0.08}}
EXIT = "ma50"
MARKET = {"ma": 200}                             # 加權指數收盤 > 200 日均線才買新的
MAIN_CFG = {"screen": "main", "exit": EXIT, "market": True}
VARIANTS = tuple({"screen": s, "exit": e, "market": mk}
                 for s in ("main", "strict", "trend") for e in ("ma50", "hold60") for mk in (True, False)) + \
    ({"screen": "main", "exit": "book", "market": True},)

START = "2019-01-02"
START_LONG = "2014-01-02"
HALVES = (("2019-01-01", "2022-12-31"), ("2023-01-01", "2100-12-31"))
COMPARE = "R60"
PASS = {"mdd_extra": 10.0}


def cond_ok(f: dict, cond) -> bool:
    """單一條件（或 OR 群組）在特徵 f 上成立？缺值＝不成立。"""
    if cond[0] == "or":
        return any(cond_ok(f, c) for c in cond[1])
    k, op, v = cond
    x = f.get(k)
    if x is None:
        return False
    if op == "=":
        return x == v
    if op == ">=":
        return x >= v
    if op == ">":
        return x > v
    raise ValueError(op)


def passes(f: dict, screen: str = "main") -> bool:
    return all(cond_ok(f, c) for c in SCREENS[screen])


def verdict(sepa: dict, r60: dict, tr: dict) -> str:
    """sepa／r60／tr＝{"cagr": {"all","h1","h2"}, "mdd": {"all"}}（小數）→ 換／觀察／沒有用。"""
    c1 = all(sepa["cagr"][h] > r60["cagr"][h] for h in ("all", "h1", "h2"))
    c2 = sepa["mdd"]["all"] <= r60["mdd"]["all"] + PASS["mdd_extra"] / 100
    if c1 and c2:
        return "換"
    if all(sepa["cagr"][h] > tr["cagr"][h] for h in ("h1", "h2")):
        return "觀察"
    return "沒有用"
