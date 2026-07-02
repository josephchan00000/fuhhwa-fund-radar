#!/usr/bin/env python3
"""抓復華基金『持股介紹』快照 → data/{market.data}/{id}.json（追蹤版本的核心資料）。

每檔取：基本資料 / NAV / 多期報酬 / 經理人 / 月報連結 / 投資策略敘述
＋ 月底十大持有標的（含產業）＋ 國家配置 ＋ 產業配置 ＋ 資料日期。
共同基金無逐日持股張數 → 本版本不做「每天持股變化」，只做月度持股介紹快照。

用法：
  python scripts/fetch_holdings.py                 # 海外版全部追蹤基金 → data/funds/
  python scripts/fetch_holdings.py 47 12           # 海外版指定 fundID
  python scripts/fetch_holdings.py --market tw      # 台股版全部 14 檔 → data/funds_tw/
  python scripts/fetch_holdings.py --market tw 06   # 台股版指定 fundID
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import config, fund_intro, markets  # noqa: E402
from arm.connectors import fhfund            # noqa: E402


def run(ids: list[str], market: str = "global") -> list[dict]:
    out_dir = fund_intro.funds_dir(market)
    out_dir.mkdir(parents=True, exist_ok=True)
    by_id = {str(f["id"]): f for f in config.funds(market)}
    index = []
    print(f"[持股介紹 ← 復華官網｜市場 {market}]　{datetime.now():%Y-%m-%d %H:%M}")
    for fid in ids:
        cfg = by_id.get(str(fid), {})
        try:
            doc = fhfund.fetch_fund(fid)
        except Exception as e:
            print(f"  ✗ {fid}：抓取失敗（{type(e).__name__}：{e}）")
            continue
        doc["group"] = cfg.get("group")
        doc["fetched_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        (out_dir / f"{fid}.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        n = len(doc.get("top_holdings") or [])
        print(f"  ✓ {fid} {doc.get('name','')[:22]}｜NAV {doc.get('nav')} "
              f"({doc.get('nav_date')})｜十大 {n} 檔｜持股基準 {doc.get('as_of')}")
        index.append({"id": fid, "name": doc.get("name"), "group": doc.get("group"),
                      "category": doc.get("category"), "region": doc.get("region"),
                      "nav": doc.get("nav"), "nav_date": doc.get("nav_date"),
                      "as_of": doc.get("as_of"), "n_top": n})
    (out_dir / "_index.json").write_text(
        json.dumps({"as_of": datetime.now().strftime("%Y-%m-%d %H:%M"), "funds": index},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    return index


def _parse_args(argv: list[str]) -> tuple[str, list[str]]:
    """回傳 (market, ids)。--market <name> 可出現在任意位置；其餘視為 fundID。"""
    market = "global"
    ids: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--market":
            market = argv[i + 1]
            i += 2
            continue
        if a.startswith("--market="):
            market = a.split("=", 1)[1]
            i += 1
            continue
        ids.append(a)
        i += 1
    return market, ids


def main() -> None:
    market, ids = _parse_args(sys.argv[1:])
    if not ids:
        ids = [str(f["id"]) for f in config.funds(market)]
    if not ids:
        print(f"市場 {market} 無追蹤基金；請先設定 config/{markets.get(market)['funds']}。")
        return
    run(ids, market)


if __name__ == "__main__":
    main()
