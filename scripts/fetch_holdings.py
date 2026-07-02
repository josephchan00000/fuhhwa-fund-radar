#!/usr/bin/env python3
"""抓復華基金『持股介紹』快照 → data/funds/{id}.json（追蹤版本的核心資料）。

每檔取：基本資料 / NAV / 多期報酬 / 經理人 / 月報連結 / 投資策略敘述
＋ 月底十大持有標的（含產業）＋ 國家配置 ＋ 產業配置 ＋ 資料日期。
共同基金無逐日持股張數 → 本版本不做「每天持股變化」，只做月度持股介紹快照。

用法：
  python scripts/fetch_holdings.py            # 全部追蹤基金
  python scripts/fetch_holdings.py 47 12      # 指定 fundID
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import config                       # noqa: E402
from arm.connectors import fhfund            # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "funds"


def run(ids: list[str]) -> list[dict]:
    OUT.mkdir(parents=True, exist_ok=True)
    by_id = {str(f["id"]): f for f in config.funds()}
    index = []
    print(f"[持股介紹 ← 復華官網]　{datetime.now():%Y-%m-%d %H:%M}")
    for fid in ids:
        cfg = by_id.get(str(fid), {})
        try:
            doc = fhfund.fetch_fund(fid)
        except Exception as e:
            print(f"  ✗ {fid}：抓取失敗（{type(e).__name__}：{e}）")
            continue
        doc["group"] = cfg.get("group")
        doc["fetched_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        (OUT / f"{fid}.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        n = len(doc.get("top_holdings") or [])
        print(f"  ✓ {fid} {doc.get('name','')[:22]}｜NAV {doc.get('nav')} "
              f"({doc.get('nav_date')})｜十大 {n} 檔｜持股基準 {doc.get('as_of')}")
        index.append({"id": fid, "name": doc.get("name"), "group": doc.get("group"),
                      "category": doc.get("category"), "region": doc.get("region"),
                      "nav": doc.get("nav"), "nav_date": doc.get("nav_date"),
                      "as_of": doc.get("as_of"), "n_top": n})
    (OUT / "_index.json").write_text(
        json.dumps({"as_of": datetime.now().strftime("%Y-%m-%d %H:%M"), "funds": index},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    return index


def main() -> None:
    ids = sys.argv[1:] or [str(f["id"]) for f in config.funds()]
    if not ids:
        print("config/funds.json 無追蹤基金；請先設定。")
        return
    run(ids)


if __name__ == "__main__":
    main()
