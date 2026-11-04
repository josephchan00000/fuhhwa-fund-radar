"""策略熔斷與拿錢規則改版觀察期的規格。VER 1：2026-11-04，算任何策略的門檻之前寫定（docs/lab_killswitch_plan.md）。

使用者 2026-11-04 貼了三條交易紀律問能不能用，選了：熔斷用「跟大盤比」的版本、拿錢的規則改版要新舊並行 63 天才換（修錯除外）、
主觀游擊隊只當自己的規矩（網站不做）。同日決定：門檻 1.5 倍（K1）、落後太久只標示＋推播一次（K3）、暫停後自動恢復（K4）、
觀察期不設成績門檻（K5）。台股的大盤原本說 0050 含息，寫規格時查到 repo 沒有回測期間的 0050 含息價 → 改用加權報酬指數（K2，已寫進規劃）。

熔斷（每一份拿錢的策略各自算）：
  哪幾份（SLICES）：台股新飆股（sxlivespec.PLAN_BOOK 那一本）、台股 ★ 個股策略每一條（交易計畫當天拿錢的那幾條）、美股強勢品質股（ussxspec 規則 QM）。
    長抱那一份就是大盤本身，不設。
  大盤（BENCH）：台股＝加權報酬指數（含息，v3_tr.json 的 q）；美股＝S&P 500 含息（和 ussxqm 的 spx_tr 同一個口徑）。
  相對淨值 rel＝策略淨值 ÷ 大盤淨值（兩邊都從同一天＝1 起算）；落後 lag_t＝1 − rel_t ÷ max(rel_0..t)；
  落後天數 uw_t＝離上一次 rel 創新高（含相等；比大小容差 EPS＝1e-9，浮點誤差不算落後）幾個交易日。
  門檻（bounds）：回測期間（那條策略判定用的同一個回測，逐日淨值；起點到 SPEC_DATE 以前最後一天）的 max(lag) × DD_MULT；
    max(uw) × UW_MULT（無條件進位成整數天）。數字算出來之後寫進門檻檔鎖住，不因之後的成績改；策略本身改版（VER＋1）才重算。
  前瞻（LIVE_FROM）：從那份策略的前瞻紀錄起點重新量（rel＝1），回測只拿來定門檻。
  觸發（walk）：某天收盤 lag > 門檻 → 暫停，下一個交易日收盤（ACT_LAG）把那一份換現金，推播一句。暫停中照樣每天紙上記。
  自動恢復（K4）：暫停中紙上的 rel 回到觸發那天收盤的 rel（≥）→ 恢復，下一個交易日收盤買回、推播一句；
    恢復那天的落後還在邊界外，所以恢復之後重新量：最高點與落後天數從恢復那天算起。
  落後太久（K3）：uw > 落後天數門檻 → 頁面標「落後很久，要檢討」、推播一次；同一段（到下一次創新高或恢復為止）不再推；不暫停。
  熔斷暫停不算改版（規則本身寫好的動作）。

改版觀察期：
  拿錢的規則（PLAN_RULES）：交易計畫的比例與警訊（corespec）、新飆股那一本（sxlivespec 的 PLAN_BOOK 與它的照做方式）、
    美股強勢品質股的規則（ussxspec 規則 QM 與它的照做方式）、★ 個股策略的選股與出場（各策略程式）。
    頁面上的訊號、溫度計、泡沫、個股報告等不拿錢的規格不在內，照舊改版就上線。
  流程：新版本寫好規格（VER＋1）→ 現行版照常拿錢、新版從同一天起紙上記 → 滿 QUAR_DAYS 個交易日推播「新版觀察滿 3 個月，回『好』才換」
    → 使用者回「好」才換；回「不換」新版停記。不設成績門檻（QUAR_GATE＝None；K5：63 天的成績差大多是雜訊，換不換由使用者看並列成績決定）。
  修錯當天改（FIX_KINDS）：資料錯、用到未來的資料、程式和規格不一致；commit 與知識庫日誌寫「修錯」並說明為什麼不算改版；拿不準先問使用者。
"""
from __future__ import annotations

import math

VER = 1
SPEC_DATE = "2026-11-04"

SLICES = ("tw_boom", "tw_star", "us_qm")      # tw_star＝★ 個股策略每一條各自一份
BENCH = {"tw": "加權報酬指數（含息）", "us": "S&P 500 含息"}
LIVE_FROM = {"tw_boom": "2026-10-23", "us_qm": "2026-10-23", "tw_star": "2026-10-15"}   # sxlivespec.START、ussx 前瞻、v3live.SINCE
DD_MULT = 1.5                 # K1
UW_MULT = 1.5                 # K3：只標示＋推播
ACT_LAG = 1                   # 觸發／恢復那天之後第幾個交易日收盤動作
AUTO_RESUME = True            # K4
RESUME_RESET = True           # 恢復之後重新量
UW_PAUSES = False             # K3：落後太久不暫停
EPS = 1e-9                    # 比大小的容差（浮點誤差：和最高點相等算創新高）

QUAR_DAYS = 63                # 改版觀察期（交易日）
QUAR_GATE = None              # K5：不設成績門檻
PLAN_RULES = ("corespec", "sxlivespec.PLAN_BOOK", "ussxspec.QM", "tw_star")
FIX_KINDS = ("資料錯", "用到未來的資料", "程式和規格不一致")


def rel_series(s: list, b: list) -> list:
    """策略淨值與大盤淨值（同一串日子）→ 相對淨值（第一個兩邊都有值的那天＝1；缺值＝None）。"""
    i0 = next((i for i, (x, y) in enumerate(zip(s, b)) if x and y), None)
    if i0 is None:
        return [None] * len(s)
    s0, b0 = s[i0], b[i0]
    return [None if i < i0 or not x or not y else (x / s0) / (y / b0) for i, (x, y) in enumerate(zip(s, b))]


def lag(rel: list) -> tuple[list, list]:
    """相對淨值 → (落後 lag_t, 落後天數 uw_t)；缺值那天兩個都是 None，不影響最高點與天數。"""
    pk, last, dd, uw = None, None, [], []
    for i, r in enumerate(rel):
        if r is None:
            dd.append(None)
            uw.append(None)
            continue
        if pk is None or r >= pk * (1 - EPS):
            pk, last = max(r, pk or r), i
        dd.append(max(0.0, 1.0 - r / pk))
        uw.append(sum(1 for x in rel[last + 1:i + 1] if x is not None))
    return dd, uw


def bounds(rel_bt: list) -> dict:
    """回測的相對淨值 → 門檻 {dd, uw, dd_bt, uw_bt}。"""
    dd, uw = lag(rel_bt)
    d0 = max((x for x in dd if x is not None), default=0.0)
    u0 = max((x for x in uw if x is not None), default=0)
    return {"dd": d0 * DD_MULT, "uw": math.ceil(u0 * UW_MULT), "dd_bt": d0, "uw_bt": u0}


def walk(rel: list, b: dict) -> list[dict]:
    """前瞻的相對淨值（紙上，暫停中也照記）＋門檻 → 事件 [{i, k}]：k＝pause（觸發，第 i+ACT_LAG 天收盤換現金）、
    resume（恢復，第 i+ACT_LAG 天收盤買回）、slow（落後太久，只推播一次）。"""
    ev, paused, r_trig, slow_sent = [], False, None, False
    pk, last = None, None
    for i, r in enumerate(rel):
        if r is None:
            continue
        if paused:
            if AUTO_RESUME and r >= r_trig * (1 - EPS):
                ev.append({"i": i, "k": "resume"})
                paused, pk, last, slow_sent = False, r, i, False
            continue
        if pk is None or r >= pk * (1 - EPS):
            if pk is not None and r > pk * (1 + EPS):
                slow_sent = False
            pk, last = max(r, pk or r), i
        d = max(0.0, 1.0 - r / pk)
        u = sum(1 for x in rel[last + 1:i + 1] if x is not None)
        if d > b["dd"]:
            ev.append({"i": i, "k": "pause"})
            paused, r_trig = True, r
            continue
        if u > b["uw"] and not slow_sent:
            ev.append({"i": i, "k": "slow"})
            slow_sent = True
    return ev
