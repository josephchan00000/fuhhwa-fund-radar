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
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import config, fundnav             # noqa: E402
from arm.clock import now_tw                 # noqa: E402  台北時間（UTC 容器/CI 防跨日錯置）
from arm.connectors import fhfund            # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "funds"
HOLD_KEYS = ("as_of", "top_holdings", "asset_alloc", "country_alloc", "sector_alloc")


def _keep_holdings(doc: dict, fp: Path) -> bool:
    """這一次持股頁抓不到（出錯或解析 0 筆）而舊檔有持股 → 持股、配置、持股基準日都沿用舊檔，淨值等其他欄位照新的。
    持股基準日跟著舊的（月底日期就是過期標記），另記 holdings_error。回傳有沒有沿用。
    鐵則：非空的落檔絕不覆寫成空（docs/code_ponytail_audit.md 第 1 條）。"""
    if doc.get("top_holdings"):
        return False
    try:
        old = json.loads(fp.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not old.get("top_holdings"):
        return False
    for k in HOLD_KEYS:
        doc[k] = old.get(k)
    doc.setdefault("holdings_error", "持股頁解析 0 筆")
    return True


def _name_matches(cfg_name: str | None, api_name: str | None) -> bool:
    """config 名稱與官網 /api/fund 名稱是否指同一檔（正規化後互為前綴即可）。

    防呆背景（2026-07-20）：新募集基金的官網頁常未被搜尋引擎收錄，fundID 只能由相鄰
    檔號推定——推錯會整檔抓成別的基金且名稱被 API 權威值覆寫、儀表板看不出異狀。
    任一方缺名（舊檔／API 缺欄）放行，維持既有行為。"""
    if not cfg_name or not api_name:
        return True
    a = re.sub(r"[\s​]+", "", cfg_name)
    b = re.sub(r"[\s​]+", "", api_name)
    return a.startswith(b) or b.startswith(a)


def run(ids: list[str]) -> list[dict]:
    OUT.mkdir(parents=True, exist_ok=True)
    by_id = {str(f["id"]): f for f in config.funds()}
    index = []
    docs = []
    print(f"[持股介紹 ← 復華官網]　{now_tw():%Y-%m-%d %H:%M}")
    for fid in ids:
        cfg = by_id.get(str(fid), {})
        try:
            doc = fhfund.fetch_fund(fid)
        except Exception as e:
            print(f"  ✗ {fid}：抓取失敗（{type(e).__name__}：{e}）")
            continue
        if not _name_matches(cfg.get("name"), doc.get("name")):
            print(f"  ✗ {fid}：官網名稱「{doc.get('name')}」與 config 名稱"
                  f"「{cfg.get('name')}」不符——疑 fundID 錯置，跳過不落檔"
                  "（請修正 config/funds.json 的 id）")
            continue
        doc["group"] = cfg.get("group")
        doc["fetched_at"] = now_tw().strftime("%Y-%m-%d %H:%M")
        if _keep_holdings(doc, OUT / f"{fid}.json"):
            print(f"  ↺ {fid}：持股頁這次抓不到（{doc['holdings_error']}），持股沿用上一次（持股基準 {doc.get('as_of')}）")
        docs.append(doc)
        (OUT / f"{fid}.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        n = len(doc.get("top_holdings") or [])
        print(f"  ✓ {fid} {doc.get('name','')[:22]}｜NAV {doc.get('nav')} "
              f"({doc.get('nav_date')})｜十大 {n} 檔｜持股基準 {doc.get('as_of')}")
        index.append({"id": fid, "name": doc.get("name"), "group": doc.get("group"),
                      "category": doc.get("category"), "region": doc.get("region"),
                      "nav": doc.get("nav"), "nav_date": doc.get("nav_date"),
                      "as_of": doc.get("as_of"), "n_top": n})
    # 鉅亨每日多期報酬覆蓋（Tier B）：官網多期報酬為月底基準，鉅亨為每日基準；
    # 整層失敗只影響「當日基準」欄位（儀表板回退官網值），不影響既有流程
    try:
        from arm.connectors import cnyesfund
        cnyesfund.apply_overlay(docs, OUT)
    except Exception as e:
        print(f"  ↳ 鉅亨覆蓋層跳過（{type(e).__name__}：{e}）")
    by_id_doc = {str(d.get("fund_id")): d for d in docs}   # 覆蓋層可能更新 NAV → 同步索引
    for e in index:
        d = by_id_doc.get(str(e["id"]))
        if d:
            e["nav"], e["nav_date"] = d.get("nav"), d.get("nav_date")
    _write_index(index)
    n_nav = fundnav.record(docs)             # NAV 序列累積（總覽 1週/1月報酬資料層）
    if n_nav:
        print(f"  ↳ NAV 歷史追加 {n_nav} 筆 → data/fund_nav_history.json")
    # 新加入追蹤清單的基金短史自動回填（官方 /api/fundNav 全史，只補缺日）
    fundnav.backfill_official(docs, fhfund.fetch_nav_history)
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
    fp.write_text(json.dumps({"as_of": now_tw().strftime("%Y-%m-%d %H:%M"),
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
