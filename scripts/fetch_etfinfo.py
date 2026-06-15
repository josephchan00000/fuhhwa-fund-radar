#!/usr/bin/env python3
"""從 etfinfo.tw 第三方彙整源補實競品持股 / 主動ETF籌碼追蹤（Tier B，可驗證）。

把 M2「競品逐日持股」與 §18.4「聰明錢」的缺口，用 etfinfo.tw 公開 JSON API 落成
專案既有 drop-in 格式，**落檔即生效、引擎不動**。一律標來源(provenance)+as-of+Tier B，
方便人工核對（鐵則：先給可能值、上線前以投信官網核實）。

用法：
  python scripts/fetch_etfinfo.py holdings      # 補實所有已宣告競品持股 → config/competitor_holdings/
  python scripts/fetch_etfinfo.py active        # 補實主動ETF估算新進 → config/active_flow/{date}.json
  python scripts/fetch_etfinfo.py               # 兩者都跑
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm.connectors import etfinfo, issuers  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
COMP_DIR = ROOT / "config" / "competitor_holdings"
FLOW_DIR = ROOT / "config" / "active_flow"
PROV = ("etfinfo.tw 第三方彙整（/api/etf/{code}，holdings.source={src}）；"
        "Tier B，數字待以投信官網/公開說明書核對")


def fetch_holdings() -> None:
    COMP_DIR.mkdir(parents=True, exist_ok=True)
    for code, issuer in issuers.COMPETITORS.items():
        try:
            hs, meta = etfinfo.holdings(code)
        except Exception as e:
            print(f"  ✗ {code} 取得失敗：{e}")
            continue
        if not hs:
            print(f"  ⚠ {code} 無持股資料（etfinfo 未揭露或代碼不符）")
            continue
        doc = {
            "fund_id": code,
            "issuer": meta.get("issuer") or issuer,
            "as_of": meta.get("as_of"),
            "tier": "B",
            "provenance": PROV.format(code=code, src=meta.get("source")),
            "holdings": hs,
        }
        out = COMP_DIR / f"{code}.json"
        out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        eq = sum(1 for h in hs if h["weight"] > 0)
        print(f"  ✓ {code} {doc['issuer']} → {out.name}（{len(hs)} 檔，{eq} 檔有權重，as-of {doc['as_of']}）")


def fetch_active() -> None:
    FLOW_DIR.mkdir(parents=True, exist_ok=True)
    try:
        meta, items = etfinfo.active_flow("buy")
    except Exception as e:
        print(f"  ✗ active/tracking 取得失敗：{e}")
        return
    if not items:
        print("  ⚠ active/tracking 無資料")
        return
    date = meta.get("date") or "latest"
    doc = {
        "as_of": date, "side": meta.get("side"), "tier": "B",
        "provenance": "etfinfo.tw /api/active/tracking（主動ETF/投信估算新進，法人層級非券商分點）；Tier B，待核對",
        "meta": meta, "items": items,
    }
    out = FLOW_DIR / f"{date}.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ active flow → {out.name}（{len(items)} 檔被法人估算新進/加碼，as-of {date}）")


if __name__ == "__main__":
    what = sys.argv[1].lower() if len(sys.argv) > 1 else "all"
    if what in ("holdings", "all"):
        print("[補實競品持股 ← etfinfo.tw]")
        fetch_holdings()
    if what in ("active", "all"):
        print("[補實主動ETF籌碼追蹤 ← etfinfo.tw]")
        fetch_active()
