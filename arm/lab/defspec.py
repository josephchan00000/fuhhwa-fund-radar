"""個股策略的防守研究（個股頁優化 C 段）規格。VER 1：2026-11-11，算任何結果之前寫定（docs/lab_stock_page_plan.md 第 4.2、9 節）。

使用者 2026-11-11：個股頁「推薦的股票賠錢」→ 防守三種都研究（D1 大盤走弱新名單先不買、D2 同一類最多幾檔、D3 熔斷門檻收緊）；
規格先寫、回測、判定事先定；過關而且使用者同意才換，沒過就照實講。寫規格前只數了「加權指數收在 60 日線下的天數比例」
（2014 起 32%、2019 起 29%；沒有算任何報酬）。

三條策略（SLICES）與基準：照現在的引擎與規則重跑一次（沒有部位的錢不算利息），年報酬要和官方結果檔（BASE_SRC）差 0.01 個百分點以內（BASE_CHECK）才算接對引擎：
  boom＝台股新飆股 N8（tw-superstock-lab/scripts/run_w10.py 的 s8-new-off-h60；和 sx_n8_curve 同一個；2019-01-02 起）
  v3l＝財報驚喜（大型股）（bt3l.top5 的 p3 L；2014-05-15 起）
  qm＝美股強勢品質股（ussxqm 規則 QM、ussxspec VER 8；2013-12-31 起；資料分支 claude/ussx-data）

D1 大盤走弱，新名單先不買（主：D1_MA＝60）
  決定買進那一天收盤，大盤 < 自己的 D1_MA 日均線（含當天）→ 那一次的新買進全部不做（空位放現金到下一次決定），已經拿著的照原規則。
  大盤：台股＝加權指數（價格指數，引擎裡的 index_level／P.idx）；美股＝SPY 調整後收盤（ussxdata.ETFS，QM 引擎同一份）。
  boom＝每一天的 decide()；v3l＝每一期的決定日（整期不買）；qm＝每週訊號日。

D2 同一類最多幾檔（主：D2_K＝2）
  補空位照原本的優先順序；某一類已經拿著 D2_K 檔（含當天新買的）就跳過、往下一個補；已經拿著的不賣。v3l 從排好的名單往下補到 5 檔（照舊至少要 20 檔有分數才選）。
  類別：台股＝證交所／櫃買產業別——用 data/lab/indsnap.json 在那一天以前最近的一份快照（每年年初＋2026-09-30），快照沒有的用 stockmeta 現在的分類；
  美股＝GICS 產業部門（data/lab/ussx_gics.json，現在的分類），不在 S&P 1500 的用資料分支 Nasdaq 篩選器的 sector；都查不到＝自成一類（不限）。
  美股分類是現在的、不是當時的：只能當近似，研究紀錄寫明。

D3 熔斷門檻收緊（主：D3_MULT＝1.0）
  熔斷的回測不能偷看：每一天的門檻＝那一天以前（不含）的最大落後 × 倍數；回測開始的 D3_WARM 個交易日（約 2 年）不熔斷。
  落後、暫停換現金、自動恢復照 ksspec VER 2（大盤、ACT_LAG、AUTO_RESUME、RESUME_RESET）；暫停中那一份淨值不動（現金），紙上照記。
  用在基準回測的逐日淨值上（不重跑引擎）。現行規則（全期最大落後 × 1.5）在自己的回測裡不可能觸發，所以 D3 和「不熔斷」比；
  「不偷看的 1.5 倍」只列。

判定（JUDGE；規劃第 4.2 節寫好的，看過結果不改）：每條策略、每個主做法各自判。
  ① 全期年報酬 ≥ 基準 − 2 個百分點（MAX_CAGR_LOSS）；② 全期最大跌幅 ≤ 基準 − 5 個百分點（MIN_DD_GAIN）；
  ③ 前後兩半各自 ①② 都成立（兩半照各策略原本的切法 HALVES：boom 2019–2022／2023 起；v3l 2021-10-01 前／後；qm 交易日中點）。
  全過＝過關。過關的換不換由使用者決定；換的話照 ksspec 的改版觀察期（新舊並行 63 個交易日）。沒過＝維持現狀，頁面只講清楚風險。
只列（COMPARE）：D1 的 20、200 日線；D2 的 3 檔；D3 的 0.75 倍、固定 30%、不偷看的 1.5 倍；D1＋D2 一起；每年報酬；2026-10 以後的差別（只描述）。
不做：中途停損（新飆股六種中途出場已測過都比較差）、到條件才買（W11 沒有比較好）、美股出場與檔數（ussx 第 12 節已測過）。
要改就 VER＋1、寫進規劃，不在舊版本上改。
"""
from __future__ import annotations

import hashlib
import json

VER = 1
SPEC_DATE = "2026-11-11"

SLICES = ("boom", "v3l", "qm")
BASE_SRC = {"boom": "data/lab/sx_n8_curve.json", "v3l": "data/lab/bt3_research.json", "qm": "data/lab/ussx_qm.json"}
BASE_CHECK = 0.0001                                          # 年報酬差 0.01 個百分點以內

D1_MA = 60
D1_ALT = (20, 200)
D2_K = 2
D2_ALT = (3,)
D3_MULT = 1.0
D3_ALT = (0.75, 1.5)
D3_FIXED = 0.30
D3_WARM = 504

MAX_CAGR_LOSS = 0.02
MIN_DD_GAIN = 0.05
HALVES = {"boom": ("2019-01-02", "2023-01-01"), "v3l": ("2014-05-15", "2021-10-01"), "qm": ("2013-12-31", "mid")}
RECENT_FROM = "2026-10-01"


def judge(base: dict, alt: dict) -> dict:
    """base／alt：{"all": {"cagr", "mdd"}, "h1": {...}, "h2": {...}}（mdd 是正的跌幅）→ 各條件與結論。"""
    def ok(b, a):
        return {"cagr": a["cagr"] >= b["cagr"] - MAX_CAGR_LOSS - 1e-12, "mdd": a["mdd"] <= b["mdd"] - MIN_DD_GAIN + 1e-12}
    r = {k: ok(base[k], alt[k]) for k in ("all", "h1", "h2")}
    passed = all(v["cagr"] and v["mdd"] for v in r.values())
    return {"ok": r, "verdict": "過關" if passed else "沒過"}


def fingerprint() -> str:
    """規格常數的指紋（tests 鎖住；改任何一個都要 VER＋1）。"""
    keys = sorted(k for k, v in globals().items() if k.isupper() and not callable(v))
    blob = json.dumps({k: globals()[k] for k in keys}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]
