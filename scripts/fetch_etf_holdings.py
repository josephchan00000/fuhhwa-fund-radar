#!/usr/bin/env python3
"""抓 ETF 每日持股（申購買回清單）→ data/etf_holdings.json。

儀表板 ETF 列可展開的「持股變化＋當日貢獻」明細的資料來源。
主動式 ETF 每日揭露完整持股，但無跨投信統一端點 → 逐檔試候選來源（arm/connectors/issuers/pcf）。

用法：
  python3 scripts/fetch_etf_holdings.py            # 正常抓取＋落檔
  python3 scripts/fetch_etf_holdings.py --probe    # 只探針、不落檔（印各候選 HTTP 實況）

本 Claude 容器 proxy 擋所有投信站 → 只在正式區 CI 有意義；容器內跑會全數失敗（屬正常，
既有落檔原封保留、不會被洗空）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import etfholdings, etfwatch                    # noqa: E402
from arm.connectors.issuers import pcf                   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
_ISSUER_FP = ROOT / "config" / "peer_groups.json"

# 展開明細以主動式為主（使用者 2026-07-29：「ETF 尤其是主動式 ETF 可以拉開」）；
# 被動 ETF 一併嘗試，抓得到就有、抓不到不影響。
_KINDS = ("active", "other", "passive")


def _issuer_map() -> dict[str, str]:
    try:
        return json.loads(_ISSUER_FP.read_text(encoding="utf-8")).get("issuer") or {}
    except Exception:
        return {}


def main() -> int:
    probe_only = "--probe" in sys.argv
    issuers = _issuer_map()
    targets = [(c, k) for c, _n, k, _cat, _i in etfwatch.WATCHLIST if k in _KINDS]
    targets.sort(key=lambda t: _KINDS.index(t[1]))        # 主動式優先

    print(f"[ETF 每日持股] 逐檔試候選來源（{len(targets)} 檔"
          f"{'；--probe 只探測不落檔' if probe_only else ''}）…")
    fresh: dict[str, dict] = {}
    diag: dict[str, str] = {}
    for code, kind in targets:
        issuer = issuers.get(code, "")
        rows, src, probes = pcf.fetch_one(code, issuer)
        if rows:
            fresh[code] = {"date": None, "src": src, "holdings": rows}
            print(f"  ✓ {code}（{issuer or '?'}）{src}：{len(rows)} 檔持股")
        else:
            diag[code] = "；".join(p.line() for p in probes)[:600]
            print(f"  ⚠ {code}（{issuer or '?'}）無可用來源")
            for p in probes:
                print(f"      · {p.line()}")

    if probe_only:
        print(f"[探針] 成功 {len(fresh)}／{len(targets)} 檔；未落檔。")
        return 0

    # 揭露日：來源多半不標日期 → 以最近交易日當揭露日（持股為前一日收盤基準，見儀表板註記）
    asof = _latest_trade_date()
    for v in fresh.values():
        v["date"] = asof
    doc = etfholdings.merge(etfholdings.load(), fresh, diag)
    quotes = _quotes()
    if quotes:
        etfholdings.annotate(doc, quotes)
        print(f"  ✓ 當日貢獻歸因：個股報價 {len(quotes)} 檔（TWSE 上市＋TPEx 上櫃）")
    else:
        print("  ⚠ 個股報價不可得 → 沿用既有貢獻明細（不覆寫成空）")
    ok = etfholdings.save(doc)
    n = len(doc.get("etfs") or {})
    print(f"{'✓ 落檔' if ok else '⚠ 本次全空、保留既有落檔'} "
          f"{etfholdings.DATA_FP}（{n} 檔有揭露；本次新抓 {len(fresh)} 檔，基準日 {asof}）")
    return 0


def _quotes() -> dict[str, dict]:
    """個股當日收盤與漲跌（上市＋上櫃合併）——貢獻歸因的另一半。整段抓不到回 {}。"""
    out: dict[str, dict] = {}
    for mod in ("twse", "tpex"):
        try:
            from importlib import import_module
            out.update(import_module(f"arm.connectors.{mod}").fetch_today_all())
        except Exception as e:                            # noqa: BLE001 —— 兩市場獨立降級
            print(f"  ⚠ {mod} 個股報價不可得：{type(e).__name__}: {str(e)[:80]}")
    return out


def _latest_trade_date() -> str | None:
    """最近交易日（TWSE 官方）；抓不到回 None（合併時就不會誤把揭露日推進）。"""
    try:
        from arm.connectors import twse
        return twse.latest_trade_date()
    except Exception:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
