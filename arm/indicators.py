"""重點觀察數據（總經／籌碼／產業報價）—— 規格 ＋ 讀取器 ＋ 驗證。

沿用本專案 prompt-pack 哲學：多數指標（非農、失業率、CPI、Fed 利率、記憶體報價…）
無免費即時 API 或需查證，純 Python 不臆測數字 →
  · scripts/gen_indicators.py 產『可貼進 Claude 的提示包』（reports/indicators/prompts/{date}.md）；
  · Claude 上網查證後回存 reports/indicators/{date}.json（本檔 SCHEMA 結構）；
  · dashboard 讀「最新一份」渲染成各市場面板頂部的數據速覽格。

每筆指標：{market, name, value, change?, as_of, source, note?}
  market ∈ us | tw | both —— us→海外面板、tw→台股面板、both→兩面板皆列。
  value/change 為「已格式化字串」（如 "4.3%"、"+172K"、"-84,168 口"），渲染端不再運算。
  change 開頭 ▲/＋ 視為升、▼/− 視為降（僅配色，紅綠沿用站內 up/down 色）。
數字必須可追溯（as_of ＋ source 必填）；查不到的指標整筆省略、不得杜撰。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IND_DIR = ROOT / "reports" / "indicators"

MARKETS_ALLOWED = {"us", "tw", "both"}

# 提示包用：建議涵蓋的指標清單（查不到就省略該筆，不杜撰）
SPEC = """【重點觀察數據 · 建議涵蓋清單】（查證後回填；查不到就省略該筆，切勿杜撰）
美國總經（market=us）：
  · 非農就業（最新月份，萬/千人與市場預期差）　· 失業率　· CPI 年增率（總體與核心）
  · Fed 基準利率區間（最近一次 FOMC 決議與傾向）
台股籌碼（market=tw）：
  · 外資台指期淨未平倉（口數、增減）　· 三大法人現貨買賣超（億元）
  · 新台幣兌美元收盤匯率
產業報價（market=both）：
  · DRAM／NAND 報價動向（合約價與現貨價分開描述，註明來源如 TrendForce）
  · 其他與追蹤基金持股高度相關之報價（如費半指數、SOX 變動）
每筆必填 as_of（數據基準日）與 source（可追溯來源）；value/change 直接給display字串。"""


def validate(doc: dict) -> list[str]:
    """回傳結構錯誤清單；空＝合法。"""
    errs = []
    if not isinstance(doc, dict):
        return ["整份文件須為 JSON object"]
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(doc.get("date") or "")):
        errs.append("缺 date（YYYY-MM-DD）")
    items = doc.get("items")
    if not isinstance(items, list) or not items:
        errs.append("缺 items（非空陣列）")
        return errs
    for i, it in enumerate(items):
        for f in ("market", "name", "value", "as_of", "source"):
            if not (it or {}).get(f):
                errs.append(f"items[{i}] 缺 {f}")
        if (it or {}).get("market") not in MARKETS_ALLOWED:
            errs.append(f"items[{i}] market 須為 us|tw|both")
    return errs


def load_latest() -> dict | None:
    """最新一份 reports/indicators/{date}.json；壞檔/驗證失敗回 None（儀表板不崩）。"""
    if not IND_DIR.exists():
        return None
    files = sorted(IND_DIR.glob("????-??-??.json"), reverse=True)
    for fp in files:
        try:
            doc = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not validate(doc):
            return doc
    return None


def for_market(doc: dict | None, market: str) -> list[dict]:
    """依市場面板過濾指標：global→us+both、tw→tw+both（依 arm/markets 的鍵）。"""
    if not doc:
        return []
    want = {"global": {"us", "both"}, "tw": {"tw", "both"}}.get(market, {"both"})
    return [it for it in doc.get("items", []) if it.get("market") in want]
