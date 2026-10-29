"""新飆股買賣做法的回測（W10）規格。VER 1：2026-10-29，算任何一組之前寫定（docs/lab_boom_v2_plan.md 第 5、8 節）。

使用者 2026-10-29：「名單太多我沒辦法選啊 那個建議比例感覺也很雞肋 而且我不懂為什麼只放60天整個邏輯很鳥 …
你幾乎都是漲上來才買也沒挑到什麼飆股」；看過規劃後選「B1～B4 都試」。
診斷（規劃第 1 節，只描述現行規則的 408 筆）：大飆股常只放到零頭（報酬最高的 12 筆裡 7 筆不到 1%）；
名單第一次列到時漲幅走了 62%、真正買到時 81%（帳戶滿了要等到期）；到期後再抱 60 天中位數 −3%、平均 +5%。

只改買賣做法，選股不動：名單＝W7 的 R60（每年用之前的資料找的規則，W7_results.json 的 folds 原封不動），
同一套引擎、成本（engine 預設）、單檔 ≤ 總資產 20%、≤ 前 20 日均量 5%、開盤一價到底漲停買不到、跌停延後賣。

四個維度（GRID，全部組合 3×2×2×2＝24 組）：
  B1 部位 SIZE：
    cur＝現行：每次用總資產 12.5%，現金不夠就買少一點，最多 20 檔；
    s10＝固定 10 格：有空格時把現金平分給空格（每格＝現金 ÷ 空格數），一格不到總資產 1/10 的一半就不買（不留零頭）；
    s8＝固定 8 格，同上（一半＝總資產 1/8 的一半）。
  B2 先買誰 ORDER：rs＝強度高的先（現行）；new＝這一次連續上名單的週數少的先，同週數再看強度。
    週數＝到訊號那個週末為止連續幾個週末都在名單上（第一次上名單＝1）。
  B3 漲太遠先不買 EXT：off＝現行；on＝訊號那天收盤（含息還原）高於 50 日線 × EXT_MA50 → 這一週不買（之後的名單再看）。
  B4 抱多久 HOLD：h60＝現行，第 60 個交易日收盤到期、隔天開盤賣；
    renew＝到期那天的最近一個週末還在名單上 → 再抱 60 天（每次到期都看一次），最長 HOLD_MAX 個交易日。
現行＝(cur, rs, off, h60)，必須和 W7 存的 R60 年化一模一樣才出結果。

期間：START 起一次連續跑到資料最後一天；前後兩半 HALVES 同 W7。
挑選（PICK，只用 2019–2022）：24 組裡 2019–2022 最大回落沒有比現行同期深超過 mdd_extra 個百分點的，取 2019–2022 年化最高的一組；
  同分取 GRID 順序在前的。
判定（PASS）：挑出來的那一組，整段、2019–2022、2023 起三段的年化都比現行高，而且整段最大回落沒有比現行深超過 mdd_extra
  個百分點 → 換；挑出來的是現行本身或沒過 → 不換。
只描述（不判定）：24 組各自的成績、逐年、筆數、賺錢比例、每筆中位數、零頭（買進時不到總資產 3%）筆數與獲利占比、
  每年漲最多 30 檔有沒有買到與買到時這一年的漲幅已走完幾成。
已經看過的：現行規則 2019 年起的成績與逐筆（W7、W8、W9、規劃第 1 節）；四個維度的 24 組都沒有算過。
要改就 VER＋1、寫進規劃文件，不在舊版本上改。
"""
from __future__ import annotations

VER = 1
SPEC_DATE = "2026-10-29"

SIZE = {"cur": {"weight": 0.125, "slots": None, "max_pos": 20},
        "s10": {"weight": None, "slots": 10, "max_pos": 10},
        "s8": {"weight": None, "slots": 8, "max_pos": 8}}
MIN_SLOT = 0.5                      # 一格不到 1/N 總資產的這個比例就不買
ORDER = ("rs", "new")
EXT = ("off", "on")
EXT_MA50 = 1.25                     # 同 sepa.EXT_MA50（書上的「漲太遠」）
HOLD = ("h60", "renew")
HOLD_N = 60
HOLD_MAX = 250

GRID = tuple((s, o, e, h) for s in SIZE for o in ORDER for e in EXT for h in HOLD)
CURRENT = ("cur", "rs", "off", "h60")

START = "2019-01-02"
HALVES = (("2019-01-01", "2022-12-31"), ("2023-01-01", "2100-12-31"))
PASS = {"mdd_extra": 10.0}


def name(g: tuple) -> str:
    return "-".join(g)


def pick(runs: dict) -> tuple | None:
    """runs＝{組: {"cagr": {"all","h1","h2"}, "mdd": {"all","h1"}}} → 2019–2022 挑出來的那一組。"""
    cur = runs[CURRENT]
    ok = [g for g in GRID if g in runs and runs[g]["mdd"]["h1"] <= cur["mdd"]["h1"] + PASS["mdd_extra"] / 100]
    if not ok:
        return None
    best = max(runs[g]["cagr"]["h1"] for g in ok)
    return next(g for g in ok if runs[g]["cagr"]["h1"] == best)


def verdict(runs: dict) -> tuple[str, tuple | None]:
    g = pick(runs)
    if g is None or g == CURRENT:
        return "不換", g
    a, c = runs[g], runs[CURRENT]
    better = all(a["cagr"][k] > c["cagr"][k] for k in ("all", "h1", "h2"))
    dd_ok = a["mdd"]["all"] <= c["mdd"]["all"] + PASS["mdd_extra"] / 100
    return ("換" if better and dd_ok else "不換"), g
