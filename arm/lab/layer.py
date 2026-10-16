"""第二層篩選：交叉比對各策略的條件，提高一年內翻倍的命中率（tw-superstock-lab/reports/W3_plan.md v1；
2026-10-16 使用者：「是要如何把選股的命中率提高」「這麼多策略是不是可以交叉比對」）。

條件與 7 族分數的定義只寫在這裡；研究（tw-superstock-lab src/superstock/layer.py）與每日頁面共用。
第一層門檻與過去成績讀 data/lab/layer_research.json（研究定案後匯出）。只列名單與過去統計，不是買賣訊號。"""
from __future__ import annotations

from . import store

RES_FILE = "layer_research.json"

# (鍵, 名稱)：W3_plan 第 2.1 節，順序固定、之後不加。A、B 規則用過 2020–2022，只列不選。
COND = [
    ("arule", "飆股候選（A 規則）"),
    ("brule", "一年翻倍規則（B 規則）"),
    ("rnha", "月營收創歷史新高"),
    ("sur20", "營收驚喜前 20%"),
    ("ry25", "近 3 月營收年增 ≥ 25%"),
    ("racc", "營收年增加速"),
    ("sue20", "財報驚喜前 20%"),
    ("ey25", "最新季 EPS 年增 ≥ 25%"),
    ("eacc", "EPS 年增加速"),
    ("c33", "Code 33"),
    ("gmd", "毛利率比去年同季高"),
    ("roe15", "近四季 ROE ≥ 15%"),
    ("rs90", "RS ≥ 90"),
    ("rsl", "RS 線創 52 週新高"),
    ("mom10", "相對強勢前 10%"),
    ("vcp", "標準 VCP"),
    ("tight", "緊密整理"),
    ("pp", "爆發型"),
    ("base12", "第 1、2 個基底"),
    ("ma200up", "200 日線上揚 ≥ 80 日"),
    ("ud12", "量價足跡 ≥ 1.2"),
    ("h10", "距 52 週高點 ≤ 10%"),
    ("dry", "量縮 ≤ 0.7"),
    ("ind2", "同產業 ≥ 2 檔在名單"),
    ("cap_s", "市值 40～100 億"),
    ("cap_m", "市值 100～300 億"),
    ("cap_l", "市值 ≥ 300 億"),
    ("vm20", "價值＋動能前 20%"),
]
CKEYS = [k for k, _ in COND]
CNAME = dict(COND)
LIST_ONLY = ("arule", "brule")
TOP = {"sur20": 0.20, "sue20": 0.20, "mom10": 0.10, "vm20": 0.20}     # 橫斷面前幾 %（同當週合格股票比）
TIGHT = (10, 0.08)                                                     # 緊密整理固定 10 日、8%（W3_plan 2.1）

# 7 族分數（W3_plan 3.1）：每族一個事前寫定的代表條件，符合 1 分、權重相同
FAMILY = [
    ("月營收", "月營收創歷史新高或營收驚喜前 20%", lambda c: c["rnha"] or c["sur20"]),
    ("獲利", "財報驚喜前 20%，或 EPS 年增 ≥ 25% 且加速", lambda c: c["sue20"] or (c["ey25"] and c["eacc"])),
    ("價格強度", "RS ≥ 90 或 RS 線創新高", lambda c: c["rs90"] or c["rsl"]),
    ("技術線型", "標準 VCP、緊密整理或爆發型", lambda c: c["vcp"] or c["tight"] or c["pp"]),
    ("階段", "第 1、2 個基底且 200 日線上揚 ≥ 80 日", lambda c: c["base12"] and c["ma200up"]),
    ("量價", "量價足跡 ≥ 1.2", lambda c: c["ud12"]),
    ("族群", "同產業 ≥ 2 檔在名單", lambda c: c["ind2"]),
]
FNAMES = [n for n, _, _ in FAMILY]


def families(cond: dict) -> list[bool]:
    return [bool(f(cond)) for _, _, f in FAMILY]


def score(cond: dict) -> int:
    return sum(families(cond))


def cap_bucket(cap) -> dict:
    """月底市值（元）→ 三個規模條件。"""
    return {"cap_s": cap is not None and 40e8 <= cap < 100e8, "cap_m": cap is not None and 100e8 <= cap < 300e8,
            "cap_l": cap is not None and cap >= 300e8}


def top_set(vals: dict, frac: float) -> set:
    """{代號: 分數} → 分數最高的 ceil(frac × 檔數) 檔（同分依代號）；同 bt3s.pick。"""
    import math
    xs = [(v, c) for c, v in vals.items() if v is not None]
    if not xs:
        return set()
    n = max(1, math.ceil(frac * len(xs)))
    return {c for _, c in sorted(xs, key=lambda x: (-x[0], x[1]))[:n]}


def load_res() -> dict | None:
    res = store.read_json(RES_FILE, None)
    return res if res and res.get("v") == 1 else None
