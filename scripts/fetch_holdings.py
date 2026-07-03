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
    _write_index(index)
    return index


def _write_index(fetched: list[dict]) -> None:
    """把本次抓到的檔目「合併」進 _index.json（依 config 順序重排）。

    部分抓取（指定 fundID）或全數失敗時，不得清掉既有索引——只更新本次成功的檔目。"""
    old: dict[str, dict] = {}
    fp = OUT / "_index.json"
    if not fetched and fp.exists():          # 全數失敗：保留最後一次成功狀態（含 as_of）
        return
    if fp.exists():
        try:
            old = {str(e.get("id")): e
                   for e in json.loads(fp.read_text(encoding="utf-8")).get("funds", [])}
        except Exception:
            old = {}
    old.update({str(e["id"]): e for e in fetched})
    order = [str(f["id"]) for f in config.funds()]
    merged = [old[i] for i in order if i in old]
    merged += [e for i, e in old.items() if i not in order]      # 已移出清單者仍保留
    fp.write_text(json.dumps({"as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
                              "funds": merged}, ensure_ascii=False, indent=2),
                  encoding="utf-8")


def main() -> None:
    ids = sys.argv[1:] or [str(f["id"]) for f in config.funds()]
    if not ids:
        print("config/funds.json 無追蹤基金；請先設定。")
        return
    run(ids)


if __name__ == "__main__":
    main()
