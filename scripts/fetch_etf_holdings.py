#!/usr/bin/env python3
"""ETF 每日持股 —— 彙整站雙源抓取（etfinfo 主＋MoneyDJ 交叉驗證）。

**路線沿革（2026-07-29 定案）**：投信官網逐家逆向 7 輪＋無頭瀏覽器 3 輪後，
使用者指示「不必抓官網第一手，彙整站即可、找第二站雙重驗證」：
  · **主來源 etfinfo.tw**（Tier B）：`GET /api/etf/{code}` 的 holdings 欄位＝完整每日快照
    （stock_id／weight／shares＋snapshotDate）。既有連接器 `arm/connectors/etfinfo.py`
    早已封裝（`holdings_fresh`），且 CI 每天抓規模／殖利率就在打同一 API——可達性已被證實數週。
  · **副來源 MoneyDJ**（Tier B）：ETF 持股頁為老式 SSR HTML 表格
    （`basic0007.xdjhtm?etfid={code}.tw`），以既有 `pcf.parse_html` 解析；並涵蓋
    etfinfo 未收錄的上櫃檔（00998A／00986D 在 etfinfo 是 404）。

**雙重驗證（etfholdings.cross_check）**：兩源皆得 → 比「主來源前十大重合度 ≥60%」＋
「共同持股權重差 ≤0.75pp」→ 🟢 match；僅一源 → 標 single；不符 → 標 mismatch
（照用主來源但儀表板掛 ⚠，差異細節入日誌）。不比股數——兩站股數口徑常不同，比了誤殺。

假陽性驗證（is_plausible）、合併鐵則（merge）、貢獻歸因（annotate）全部重用既有模組。
無頭瀏覽器版（fetch_etf_holdings_browser.py）保留為備援、不再排程。

本容器 proxy 擋 etfinfo/moneydj —— 只在正式區 CI 有意義；容器內跑會全數失敗（屬正常，
既有落檔原封保留）。
"""
from __future__ import annotations

import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import etfholdings, etfwatch                    # noqa: E402
from arm.connectors import etfinfo                       # noqa: E402
from arm.connectors.issuers import pcf                   # noqa: E402

_KINDS = ("active", "other", "passive")
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


# ── 副來源：MoneyDJ（SSR HTML 表格） ─────────────────────────────────

_MDJ_URL = "https://www.moneydj.com/etf/x/basic/basic0007.xdjhtm?etfid={eid}"


def _from_moneydj(code: str) -> tuple[list[dict], str]:
    """→ (持股列, 診斷)。上市/上櫃代碼字尾各試（.tw → .two）。"""
    last = ""
    for suffix in (".tw", ".two"):
        url = _MDJ_URL.format(eid=code.lower() + suffix)
        try:
            req = urllib.request.Request(url, headers=_UA)
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
                raw = r.read()
        except Exception as e:                            # noqa: BLE001
            last = f"moneydj ✗ {type(e).__name__}: {str(e)[:80]}"
            continue
        rows = pcf._normalize(pcf.parse_html(raw))
        why = pcf.implausible_reason(rows)
        if not why:
            return rows, f"moneydj ✓ {len(rows)} 檔（{suffix}）"
        head = re.sub(rb"\s+", b" ", raw[:200]).decode("utf-8", "replace")
        last = f"moneydj {len(rows)} 檔未過驗證（{why}）｜首段：{head[:120]}"
    return [], last


# ── 主流程 ───────────────────────────────────────────────────────────

def main() -> int:
    probe_only = "--probe" in sys.argv
    targets = [(c, k) for c, _n, k, _cat, _i in etfwatch.WATCHLIST if k in _KINDS]
    targets.sort(key=lambda t: _KINDS.index(t[1]))
    print(f"[ETF 每日持股・雙源] etfinfo 主＋MoneyDJ 驗證（{len(targets)} 檔"
          f"{'；--probe 不落檔' if probe_only else ''}）…")

    fresh: dict[str, dict] = {}
    diag: dict[str, str] = {}
    n_match = n_single = n_mismatch = 0
    fallback_date = _latest_trade_date()
    for code, _kind in targets:
        pri, asof, log1 = _from_etfinfo(code)
        sec, log2 = _from_moneydj(code)
        rows, src = (pri, "etfinfo") if pri else ((sec, "moneydj") if sec else ([], ""))
        if not rows:
            diag[code] = f"{log1}；{log2}"
            print(f"  ⚠ {code} 兩源皆不可得")
            print(f"      · {log1}\n      · {log2}")
            continue
        if pri and sec:
            verify = etfholdings.cross_check(pri, sec)
            verify["other"] = "moneydj"
            if verify["status"] == "match":
                n_match += 1
            else:
                n_mismatch += 1
                print(f"  ⚠ {code} 兩源不符：前十大重合 {verify['top_hit']}/{verify['top_n']}、"
                      f"共同持股權重差最大 {verify['max_dw']}pp（照用 etfinfo、儀表板掛 ⚠）")
        else:
            verify = {"status": "single", "other": None}
            n_single += 1
        fresh[code] = {"date": asof or fallback_date, "src": src,
                       "verify": verify, "holdings": rows}
        mark = {"match": "🟢", "single": "◯", "mismatch": "⚠"}[verify["status"]]
        print(f"  {mark} {code}：{len(rows)} 檔（{src}）｜{log1}｜{log2}")

    if probe_only:
        print(f"[探針] 成功 {len(fresh)}/{len(targets)}（🟢 雙源相符 {n_match}、"
              f"◯ 單源 {n_single}、⚠ 不符 {n_mismatch}）；未落檔。")
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
          f"／◯ {n_single}／⚠ {n_mismatch}）")
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
