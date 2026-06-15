#!/usr/bin/env python3
"""M6 文案層 CLI —— 讀每日想法報告 → 產四通路文案（baseline，可選 LLM 潤稿）。

用法：
  python scripts/gen_copy.py 00991A                 # 讀最新報告 → baseline 文案 + 產 prompt-pack
  python scripts/gen_copy.py 00991A --date 2026-06-12
  python scripts/gen_copy.py 00991A --ingest        # 回灌 prompt-pack 回覆（手動 Claude 潤稿）
  python scripts/gen_copy.py 00991A --ingest path.json
  python scripts/gen_copy.py all                    # reports/ 內全部主角

雙路 LLM（設計決策 ①）：
  · 預設免 key：出 baseline + 產 prompt-pack（貼進你的 Claude → 存回覆 → --ingest）。
  · 有 ANTHROPIC_API_KEY：自動走 API 潤稿（無須 prompt-pack）。
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import copy as cp  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "reports" / "copy"


def _gen_one(etf_id: str, *, date=None, ingest=None) -> None:
    doc = cp.parse_file(cp.latest_report(etf_id, date=date))
    if not doc.ideas:
        print(f"  ⚠ {etf_id}：報告無可解析想法，略過。")
        return

    llm = None
    mode = "baseline"
    if ingest is not None:                              # 手動 prompt-pack 回灌
        rpath = Path(ingest) if isinstance(ingest, str) and ingest else cp.prompt_pack.response_path(doc)
        resp = cp.prompt_pack.load_response(rpath)
        if not resp:
            print(f"  ⚠ {etf_id}：找不到/讀不到回覆 {rpath} → 退回 baseline。")
        else:
            llm = cp.prompt_pack.as_llm(resp)
            mode = f"prompt-pack 回灌（{rpath.name}）"
    elif cp.default_llm() is not None:                 # 有金鑰→自動 API
        llm = cp.default_llm()
        mode = "Claude 自動 API 潤稿"

    results = cp.generate_doc(doc, llm=llm)

    OUT.mkdir(parents=True, exist_ok=True)
    md_path = OUT / f"{doc.date}_{doc.etf_id}.copy.md"
    md_path.write_text(cp.render_markdown(doc, results), encoding="utf-8")

    fab = sum(len(c.fabricated) for r in results for c in r.channels.values())
    print(f"  ✅ {etf_id}（{mode}）→ {md_path.relative_to(OUT.parent.parent)}"
          f"　想法 {len(results)} 則／疑似杜撰數字 {fab} 處")

    if llm is None:                                    # 未潤稿 → 一併產 prompt-pack 供手動升級
        # 用「基線原稿（未補揭露）」當 prompt 較乾淨
        bundle = [(r.idea, cp.baseline.render(r.idea, doc), r.allowed) for r in results]
        ppath = cp.prompt_pack.write_prompt(doc, bundle)
        print(f"     📋 prompt-pack → {ppath.relative_to(OUT.parent.parent)}"
              f"（貼進你的 Claude → 存回覆到 reports/copy/responses/{doc.date}_{doc.etf_id}.json → --ingest）")


def main() -> None:
    ap = argparse.ArgumentParser(description="M6 文案層")
    ap.add_argument("target", nargs="?", default="all", help="ETF 代號或 all")
    ap.add_argument("--date", default=None, help="指定報告日期 YYYY-MM-DD")
    ap.add_argument("--ingest", nargs="?", const="", default=None,
                    help="回灌 prompt-pack 回覆（可給路徑；省略則用預設 responses/{date}_{etf}.json）")
    args = ap.parse_args()

    if args.target.lower() == "all":
        ids = cp.list_etf_ids()
        if not ids:
            print("reports/ 沒有任何報告，請先跑 scripts/run_daily.py")
            return
        print(f"# M6 文案層：{len(ids)} 檔 → {'、'.join(ids)}")
        for i in ids:
            try:
                _gen_one(i, date=args.date, ingest=args.ingest)
            except FileNotFoundError as e:
                print(f"  ⚠ {i}：{e}")
    else:
        _gen_one(args.target, date=args.date, ingest=args.ingest)


if __name__ == "__main__":
    main()
