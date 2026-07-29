#!/usr/bin/env python3
"""ETF 每日持股 —— 彙整站多源抓取（etfinfo 主；MoneyDJ／Yahoo 交叉驗證與補位）。

**路線沿革（2026-07-29 定案）**：投信官網逐家逆向 7 輪＋無頭瀏覽器 3 輪後，
使用者指示「不必抓官網第一手，彙整站即可、找第二站雙重驗證」：
  · **主來源 etfinfo.tw**（Tier B）：`GET /api/etf/{code}` 的 holdings 欄位＝完整每日快照
    （stock_id／weight／shares＋snapshotDate）。既有連接器 `arm/connectors/etfinfo.py`
    早已封裝（`holdings_fresh`），且 CI 每天抓規模／殖利率就在打同一 API——可達性已被證實數週。
  · **副來源 Yahoo 股市持股頁**（Tier B）：SSR 內嵌 JSON（parse_embedded_json）。
    注意 Yahoo 持股為**月度基準前十大**、etfinfo 為每日 PCF 快照——只做「構成驗證」
    （前十大重合度），**不比權重**（跨基準日比權重是方法錯誤，實測 19/21 檔被誤判）。
    MoneyDJ 已移除：basic0007 頁 table×0（改 JS 渲染，SSR 表格已不存在，2026-07-29 實測）。

**雙重驗證（etfholdings.cross_check）**：兩源皆得 → 比「主來源前十大重合度 ≥60%」＋
「共同持股權重差 ≤0.75pp」→ 🟢 match；僅一源 → 標 single；不符 → 標 mismatch
（照用主來源但儀表板掛 ⚠，差異細節入日誌）。不比股數——兩站股數口徑常不同，比了誤殺。

假陽性驗證（is_plausible）、合併鐵則（merge）、貢獻歸因（annotate）全部重用既有模組。
無頭瀏覽器版（fetch_etf_holdings_browser.py）保留為備援、不再排程。

本容器 proxy 擋 etfinfo/yahoo —— 只在正式區 CI 有意義；容器內跑會全數失敗（屬正常，
既有落檔原封保留）。
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import etfholdings, etfwatch                    # noqa: E402
from arm.connectors import etfinfo                       # noqa: E402
from arm.connectors.issuers import pcf                   # noqa: E402

_KINDS = ("active", "other", "passive")

# 結構性不支援（2026-07-29 定案）：本功能的資料模型以「台股個股 4 碼代號」為鍵
#（Δ 股數、當日貢獻都靠它對報價）。下列檔的持倉不是台股個股，任何來源都裝不進來：
UNSUPPORTED: dict[str, str] = {
    "00998A": "持倉為海外金融股（無台股個股代號可對映報價）",
    "00986D": "持倉為海外金融債（債券無個股代號與日內報價）",
}
_TIMEOUT = 20
_UA = {"User-Agent": "Mozilla/5.0 (fuhhwa-fund-radar; etf-holdings)"}


# ── 主來源：etfinfo ──────────────────────────────────────────────────

def _from_etfinfo(code: str) -> tuple[list[dict], str | None, str]:
    """→ (持股列, 快照日, 診斷)。抓不到／不像持股回 ([], None, 原因)。"""
    try:
        raw, meta = etfinfo.holdings_fresh(code)
    except Exception as e:                                # noqa: BLE001 —— 每源獨立降級
        return [], None, f"etfinfo ✗ {type(e).__name__}: {str(e)[:90]}"
    rows = [{"stock_id": str(r["stock_id"]), "name": r.get("stock_name") or "",
             "shares": (int(r["shares"]) if r.get("shares") else None),
             "weight": (float(r["weight"]) if r.get("weight") else None)}
            for r in raw]
    rows = pcf._drop_value_like_shares(
        sorted(rows, key=lambda h: -(h.get("weight") or 0)))
    why = pcf.implausible_reason(rows)
    if why:
        return [], None, f"etfinfo {len(rows)} 檔未過驗證（{why}）"
    asof = (str(meta.get("as_of"))[:10] or None) if meta.get("as_of") else None
    return rows, asof, f"etfinfo ✓ {len(rows)} 檔（快照日 {asof or '未標'}）"




def _get_raw(url: str) -> bytes:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
        return r.read()



# ── 副來源：Yahoo 股市持股頁（SSR 內嵌 JSON、月度基準 → 只做構成驗證） ──

_YH_URL = "https://tw.stock.yahoo.com/quote/{sym}/holding"


def _from_yahoo(code: str) -> tuple[list[dict], str]:
    last = ""
    for suffix in (".TW", ".TWO"):
        try:
            raw = _get_raw(_YH_URL.format(sym=code + suffix))
        except Exception as e:                            # noqa: BLE001
            last = f"yahoo ✗ {type(e).__name__}: {str(e)[:80]}"
            continue
        rows = pcf._normalize(pcf.parse_embedded_json(raw) or pcf.parse_html(raw))
        why = pcf.implausible_reason(rows)
        if not why:
            return rows, f"yahoo ✓ {len(rows)} 檔（{suffix}）"
        last = (f"yahoo {len(rows)} 檔未過驗證（{why}）｜"
                + "；".join(pcf._key_hits(raw))[:180])
    return [], last


# ── 主流程 ───────────────────────────────────────────────────────────

def main() -> int:
    probe_only = "--probe" in sys.argv
    targets = [(c, k) for c, _n, k, _cat, _i in etfwatch.WATCHLIST if k in _KINDS]
    targets.sort(key=lambda t: _KINDS.index(t[1]))
    skipped = [c for c, _k in targets if c in UNSUPPORTED]
    print(f"[ETF 每日持股・雙源] etfinfo 主＋Yahoo 構成驗證（{len(targets) - len(skipped)} 檔"
          f"{'；--probe 不落檔' if probe_only else ''}）…")
    for c in skipped:
        print(f"  ∅ {c} 不支援：{UNSUPPORTED[c]}")

    fresh: dict[str, dict] = {}
    diag: dict[str, str] = {}
    n_match = n_single = n_mismatch = n_weak = 0
    fallback_date = _latest_trade_date()
    for code, _kind in targets:
        if code in UNSUPPORTED:
            continue                                      # 結構性不支援（見 UNSUPPORTED 註記）
        e_rows, asof, log1 = _from_etfinfo(code)
        y_rows, log3 = _from_yahoo(code)
        got = [(s, r) for s, r in (("etfinfo", e_rows), ("yahoo", y_rows)) if r]
        if not got:
            diag[code] = "；".join(x for x in (log1, log3) if x)
            print(f"  ⚠ {code} 全部來源皆不可得")
            for x in (log1, log3):
                if x:
                    print(f"      · {x}")
            continue
        src, rows = got[0]
        pri, sec = rows, (got[1][1] if len(got) > 1 else [])
        if pri and sec:
            # Yahoo 為月度基準 → 只驗構成（weights=False），權重差僅記錄不判失敗
            verify = etfholdings.cross_check(pri, sec, weights=False)
            verify["other"] = got[1][0]
            if verify["status"] == "match":
                n_match += 1
            else:
                # 構成重合過低＝副源基準過舊、無法據以驗證——**不是**主來源錯誤的證據
                # （00929 月度重合 3/10 即此類：月內調倉大，Yahoo 舊快照對不上每日 PCF）
                verify["status"] = "weak"
                n_weak += 1
                print(f"  ◐ {code} 副源基準過舊、未能交叉驗證"
                      f"（構成重合 {verify['top_hit']}/{verify['top_n']}）")
        else:
            verify = {"status": "single", "other": None}
            n_single += 1
        fresh[code] = {"date": (asof if src == "etfinfo" and asof else fallback_date),
                       "src": src, "verify": verify, "holdings": rows}
        mark = {"match": "🟢", "single": "◯", "mismatch": "⚠", "weak": "◐"}[verify["status"]]
        logs = "｜".join(x for x in (log1, log3) if x)
        print(f"  {mark} {code}：{len(rows)} 檔（{src}）｜{logs}")

    if probe_only:
        print(f"[探針] 成功 {len(fresh)}/{len(targets) - len(skipped)}（🟢 構成相符 {n_match}、"
              f"◯ 單源 {n_single}、◐ 副源過舊 {n_weak}、⚠ 不符 {n_mismatch}）；未落檔。")
        return 0

    doc = etfholdings.merge(etfholdings.load(), fresh, diag)
    quotes = _quotes()
    if quotes:
        etfholdings.annotate(doc, quotes)
        print(f"  ✓ 當日貢獻歸因：個股報價 {len(quotes)} 檔")
    else:
        print("  ⚠ 個股報價不可得 → 沿用既有貢獻明細（不覆寫成空）")
    ok = etfholdings.save(doc)
    print(f"{'✓ 落檔' if ok else '⚠ 本次全空、保留既有落檔'} {etfholdings.DATA_FP}"
          f"（{len(doc.get('etfs') or {})} 檔有揭露；本次 {len(fresh)} 檔：🟢 {n_match}"
          f"／◯ {n_single}／◐ {n_weak}／⚠ {n_mismatch}；不支援 {len(skipped)} 檔）")
    return 0


def _quotes() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for mod in ("twse", "tpex"):
        try:
            from importlib import import_module
            out.update(import_module(f"arm.connectors.{mod}").fetch_today_all())
        except Exception as e:                            # noqa: BLE001
            print(f"  ⚠ {mod} 個股報價不可得：{type(e).__name__}: {str(e)[:80]}")
    return out


def _latest_trade_date() -> str | None:
    try:
        from arm.connectors import twse
        return twse.latest_trade_date()
    except Exception:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
