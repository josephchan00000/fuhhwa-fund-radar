"""新策略候選的程式（規格 arm/lab/candspec.py；docs/lab_ia_v5_plan.md 第 24 節）。

一條候選＝config/strategy_candidates.json 的一筆＋這個資料夾的一支 {編號}.py（例 c001.py）。
寫定之後程式一個字都不能改（規格裡記著它的 sha256）；要改就用新的編號。
程式只准用「那一天收盤以前就拿得到」的資料；參數一律從 p 讀（規格的 p 與 grid），不要寫死在程式裡。
寫好先跑：python3 scripts/run_cands.py --check （只驗格式與 sha、不回測）＋ pytest -q tests/test_cands.py。

── 指數型（engine "index"；市場 tw、spx、ixic、ndx、sox）────────────────────────────
  C＝arm.lab.xstrat.Ctx：C.cal 日期、C.px 收盤（np.ndarray）、C.T 天數、C.ma(n) n 日均線、C.rsi2、C.ends 確定的月底索引、
  C.D 其他序列（"vix" 美股 VIX、"vixa" 收盤時已知的 VIX、"vol" 量、"adv"／"dec" 漲跌家數、"mr" 台股融資維持率…，沒有＝nan）。
  可以用 xstrat 的工具（sma、rsi、sig_trades、month_ends、pos_daily_ma、dedupe…）。lag＝隔幾個交易日收盤動作（引擎給 1）。

  # trade 型：空手時第 t 天收盤成立 → 第 t＋lag 天收盤買；出場訊號 x → 第 x＋lag 天收盤賣
  def trades(C, p, lag, now=False):
      setup = (C.px > C.ma(p["ma"])) & (...)            # 只用到第 t 天以前
      return XT.sig_trades(setup, exit_ok, C.s0, lag)    # → ([(t, e, x, q)], 最後的狀態)

  # dip 型：訊號日（去重前）與第一個可能出現訊號的日子；買在訊號隔天收盤、抱規格的 H 天
  def dip_raw(C, p, now=False):
      return [t for t in range(C.T) if ...], 0

  # alloc 型：每天收盤後要不要拿（1／0／nan），已經照 lag 往後挪好（同 xstrat.pos_daily_ma）
  def pos(C, p, lag, now=False):
      return XT.pos_daily_ma(C.px, p["n"], lag)

── 台股個股（engine "tw_stock"；b＝L 大型股、M 中型股）──────────────────────────────
  P＝bt3d.Panel（packtest.Px 介面：P.cal、P.T、P.s[代號]["o"／"h"／"l"／"c"／"v"] 還原權息後的價量、P.cap 市值、P.liq 20 日均成交值）；
  E(t, b)＝第 t 天的合格名單（bt3.Elig）；codes＝全部代號；F＝Fin（下面），財報與月營收一律經過它（只給那一天拿得到的）。
  回傳 [(t, x, {代號: 分數})]：t＝形成日（收盤決定、隔天開盤買）、x＝下一個形成日（最後一期 None）；分數大的先買（asc＝True 反過來），
  規格的 pick 決定買幾檔（top＝比例、nmin＝至少幾檔、umin＝有分數的股票至少幾檔才成立、event＝事件型）。

  def rows(P, E, b, codes, p, F):
      forms = [t for t in PT._month_ends(P.cal) if t >= p["look"]]
      def score(c, t): ...                               # 只用到第 t 天以前
      return bt3s.rows_at(P, E, b, codes, forms, score)

── 美股個股（engine "us_stock"）───────────────────────────────────────────────
  C＝ussxqm.context()：C["cal"] 日期、C["cols"] 每週一列的特徵（"j" 代號欄、"di" 週訊號日、"f" 特徵：rs、d52h、om、roe、cap…）、
  C["Cf"] 含息收盤、C["el"] 合格、C["P"] 面板。回傳 {週訊號日: [(代號欄, 分數)]}（分數高到低排好）；規格的 ex 寫出場與檔數。

  def signals(C, p):
      ...
"""
from __future__ import annotations

from pathlib import Path

DIR = Path(__file__).resolve().parent


class Fin:
    """台股個股候選要的財務資料，一律只給「那一天拿得到的」（candspec 第二節）：
      eps_ttm(P, c, t)  第 t 天已過法定期限的最近四季 EPS 合計（packtest.ttm_eps；沒有＝None）
      rev_ym(d)         日期 d 拿得到的最新月營收月份（次月 REV_DAY 日起才算拿得到）
      rev(c)            {YYYY-MM: 當月營收（千元）}——只准讀 rev_ym(d) 以前的月份
      fs_q(d)           日期 d 已過法定期限的最新一季季底（packtest.deadline）
      fs(c)             {季底: {欄位: 值}}（v3data.load_fs，損益與現金流量為單季）——只准讀 fs_q(d) 以前的季"""

    def __init__(self):
        self._eps = self._rev = self._fs = None

    def _e(self):
        if self._eps is None:
            from .. import bt3d
            self._eps = bt3d.load_eps()
        return self._eps

    def eps_ttm(self, P, c: str, t: int):
        from .. import packtest as PT
        e = self._e().get(c)
        return PT._ttm_cached(P, self._e(), c, P.cal[t]) if e else None

    def rev_ym(self, d: str) -> str:
        from .. import candspec as CS
        from .. import packtest as PT
        ym = d[:7]
        return PT.ym_shift(ym, -1 if int(d[8:10]) >= CS.REV_DAY else -2)

    def rev(self, c: str) -> dict:
        if self._rev is None:
            from .. import packtest as PT
            self._rev = PT.load_rev()
        return self._rev.get(c) or {}

    def fs_q(self, d: str) -> str | None:
        from .. import packtest as PT
        y = int(d[:4])
        qs = [f"{yy}-{md}" for yy in (y - 2, y - 1, y) for md in ("03-31", "06-30", "09-30", "12-31")]
        ok = [q for q in qs if PT.deadline(q) <= d]
        return ok[-1] if ok else None

    def fs(self, c: str) -> dict:
        if self._fs is None:
            from .. import v3data
            self._fs = v3data.load_fs()
        return self._fs.get(c) or {}
