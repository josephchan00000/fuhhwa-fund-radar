#!/usr/bin/env python3
"""重點觀察數據產生器 —— 總經／籌碼／產業報價的提示包與驗證。

指標數字需上網查證（非農、失業率、CPI、Fed 利率、外資期貨部位、記憶體報價…），
純 Python 不臆測 → 沿用 prompt-pack 哲學：

  python scripts/gen_indicators.py            # 產提示包 reports/indicators/prompts/{today}.md
  python scripts/gen_indicators.py --check    # 驗證最新 {date}.json 結構並列印內容

產出提示包後：在 Claude Code 說「依此提示包上網查證，回存 reports/indicators/{date}.json」，
或貼進聯網 Claude 回存。dashboard 會自動讀「最新一份」渲染成數據速覽格。
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import indicators  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROMPT_DIR = ROOT / "reports" / "indicators" / "prompts"


def build_prompt(today: date) -> str:
    return f"""你是「台灣投信公司內部使用的市場數據編輯」。請以 WebSearch/WebFetch 實際查證
下列重點觀察數據的最新值，回存成 JSON 檔 reports/indicators/{today:%Y-%m-%d}.json。
查不到或無法查證的指標「整筆省略」，切勿杜撰數字；每筆必附數據基準日與來源。

台北日期（TST, UTC+8）：{today:%Y/%m/%d}

{indicators.SPEC}

JSON 結構（arm/indicators.py SCHEMA）：
{{
  "date": "{today:%Y-%m-%d}",
  "items": [
    {{"market": "us",  "name": "非農就業（5月）", "value": "+172K", "change": "優於預期 +80K",
      "as_of": "2026/06/05", "source": "BLS／CNBC", "note": "6月數據 7/3 公布"}},
    {{"market": "tw",  "name": "外資台指期淨未平倉", "value": "-84,168 口", "change": "▼ 空單高水位",
      "as_of": "2026/07/01", "source": "期交所／玩股網"}},
    {{"market": "both","name": "伺服器 DRAM 合約價", "value": "Q1 季增逾 60%",
      "as_of": "2026/06", "source": "TrendForce"}}
  ]
}}
value/change 為顯示字串（含單位）；change 開頭 ▲/＋ 顯示上升色、▼/− 顯示下降色。
合規：僅中性數據陳述，不得加任何買賣建議或預測語（禁用詞比照 arm/usnews.BANNED）。
"""


def cmd_check() -> None:
    doc = indicators.load_latest()
    if not doc:
        print("找不到合法的 reports/indicators/{date}.json｜先產提示包再查證回填。")
        return
    errs = indicators.validate(doc)
    print(f"[重點觀察數據] 最新 {doc['date']}｜{len(doc.get('items', []))} 筆"
          f"｜{'🟢 結構合法' if not errs else '🔴 ' + '；'.join(errs)}")
    for it in doc.get("items", []):
        print(f"  [{it['market']:4}] {it['name']}：{it['value']}"
              f"　{it.get('change') or ''}（{it['as_of']}｜{it['source']}）")


def main() -> None:
    if "--check" in sys.argv[1:]:
        cmd_check()
        return
    today = date.today()
    PROMPT_DIR.mkdir(parents=True, exist_ok=True)
    out = PROMPT_DIR / f"{today:%Y-%m-%d}.md"
    out.write_text(build_prompt(today), encoding="utf-8")
    print(f"[重點觀察數據 提示包] 已寫入 {out}")
    print("  下一步：在 Claude Code 說『依此提示包上網查證，回存 JSON』，或貼進聯網 Claude。")


if __name__ == "__main__":
    main()
