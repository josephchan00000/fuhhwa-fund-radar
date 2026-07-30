"""ETF 每日持股與「當日貢獻」歸因（2026-07-29 使用者需求）。

主動式 ETF 依規定**每日揭露完整持股**（各投信申購買回清單／持股頁），被動 ETF 亦多有揭露。
本模組把它變成儀表板 ETF 列可展開的一張明細：

    持股｜權重｜Δ股數（加減碼）｜Δ權重｜個股當日漲跌｜對 ETF 當日漲跌的貢獻(pp)

貢獻 = 權重% × 個股當日漲跌% ÷ 100（單位：百分點 pp）。把全部持股的貢獻加總，
約等於該 ETF 當日淨值漲跌（差額＝現金部位／期貨／費用／揭露時點差 → 誠實列為「其他・現金」殘差，
不硬湊）。

資料層 `data/etf_holdings.json`（**必須入庫**——跨日累積才有「昨天 vs 今天」可比，
同 etf_watch／macro_chips 的坑）：

    {"as_of": 抓取時戳,
     "etfs": {code: {"date": 揭露日, "prev_date": 前一揭露日, "src": 來源標記,
                     "holdings": [{"stock_id","name","shares","weight"}],
                     "prev": {stock_id: {"shares","weight"}}}},
     "diag": {code: 抓取診斷字串}}

合併鐵則（同專案慣例）：本次抓到才推進；抓不到＝原封保留既有揭露，**絕不洗成空**。
只有「本次揭露日 != 既有揭露日」時才把既有 holdings 降級為 prev（同日重抓不會把
prev 洗成今天自己、讓 Δ 全變 0）。

本容器 proxy 擋所有投信站 → 抓取只在正式區 CI 跑；容器內只讀落檔建表。
"""
from __future__ import annotations

import json
from pathlib import Path

from . import clock

ROOT = Path(__file__).resolve().parent.parent
DATA_FP = ROOT / "data" / "etf_holdings.json"

_TOP_N = 12          # 展開明細預設列出的檔數（其餘併「其他 N 檔合計」一列）


# ── 資料層 ────────────────────────────────────────────────────────────

def load() -> dict | None:
    try:
        return json.loads(DATA_FP.read_text(encoding="utf-8"))
    except Exception:
        return None


def _index(holdings: list[dict]) -> dict[str, dict]:
    return {str(h.get("stock_id")): h for h in (holdings or []) if h.get("stock_id")}


def merge_one(old: dict | None, new: dict | None) -> dict | None:
    """單檔 ETF 的揭露合併。

    · new 為空（本次抓不到）→ 原封回 old（絕不洗空）。
    · new 揭露日與 old 相同 → 只更新內容，**prev 保持不動**（同日重抓不可把 prev
      洗成今天自己，否則 Δ 股數全變 0、看起來像「都沒異動」）。
    · 揭露日推進 → old.holdings 降級為 prev。
    """
    if not new or not new.get("holdings"):
        return old
    old = old or {}
    # 日期倒退防呆（2026-07-30 實踩）：換來源時新來源可能給**較舊**的快照
    # （fhtrust T-1 vs 稍早 etfinfo 的當日快照）——若照常合併，較新的快照會被降級成
    # prev，儀表板出現「揭露日 07-28（對比 07-29）」的倒轉比較。舊的進不來，保留較新者。
    if old.get("date") and new.get("date") and str(new["date"]) < str(old["date"]):
        return old
    if old.get("date") and old["date"] == new.get("date"):
        return {**new, "prev": old.get("prev") or {}, "prev_date": old.get("prev_date")}
    prev = {sid: {"shares": h.get("shares"), "weight": h.get("weight")}
            for sid, h in _index(old.get("holdings") or []).items()}
    return {**new, "prev": prev or (old.get("prev") or {}),
            "prev_date": old.get("date") or old.get("prev_date")}


def merge(prev_doc: dict | None, fresh: dict[str, dict], diag: dict[str, str] | None = None) -> dict:
    """全體合併 → 新 doc（不落檔；落檔用 save）。"""
    old_etfs = ((prev_doc or {}).get("etfs") or {})
    etfs: dict[str, dict] = {}
    for code in set(old_etfs) | set(fresh or {}):
        merged = merge_one(old_etfs.get(code), (fresh or {}).get(code))
        if merged:
            etfs[code] = merged
    return {"as_of": clock.stamp_tw(), "etfs": etfs, "diag": diag or {}}


def save(doc: dict) -> bool:
    """落檔防呆：本次全空而既有落檔非空 → 不覆寫（回 False）。"""
    old = load()
    if not (doc.get("etfs") or {}) and (old or {}).get("etfs"):
        return False
    DATA_FP.parent.mkdir(parents=True, exist_ok=True)
    DATA_FP.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return True


# ── 跨源交叉驗證（2026-07-29 使用者指示：不必抓投信第一手，改彙整站＋雙重驗證） ──

_XCHK_TOP_N = 10          # 以主來源前 N 大做重合度比對
_XCHK_OVERLAP = 0.6       # 前 N 大至少 60% 也出現在副來源
_XCHK_DW_PP = 0.75        # 共同持股權重差容忍（百分點）——兩站快照時點差一天內的正常波動

def cross_check(primary: list[dict], secondary: list[dict],
                weights: bool = True) -> dict:
    """兩個來源的持股清單交叉驗證 → {"status": "match"/"mismatch", ...細節}。

    比對（依 weights 分兩級）：
      ① 主來源前 10 大有多少也出現在副來源（重合度 ≥60%）——構成比對，永遠做；
      ② weights=True 時再比共同持股權重差最大值（≤0.75pp）。
    **weights=False＝「構成驗證」**（2026-07-29 教訓）：Yahoo 的 ETF 持股是**月度基準**、
    etfinfo 是每日 PCF 快照——跨基準日比權重是方法錯誤（實測 19/21 檔被誤判 mismatch，
    權重差 1.2–4.2pp 全是時點差）。此時只驗構成、max_dw 僅供參考記錄。
    不比股數——兩站股數口徑（張/股、揭露時點）常不同，比了只會誤殺。
    副來源為空不會呼叫本函式（那是「單源」，由上層標記）。"""
    sec_ids = {str(r.get("stock_id")) for r in secondary}
    top = [str(r.get("stock_id")) for r in
           sorted(primary, key=lambda r: -(r.get("weight") or 0))[:_XCHK_TOP_N]]
    hit = sum(1 for sid in top if sid in sec_ids)
    sec_w = {str(r.get("stock_id")): r.get("weight") for r in secondary}
    dws = [abs((r.get("weight") or 0) - (sec_w.get(str(r.get("stock_id"))) or 0))
           for r in primary
           if str(r.get("stock_id")) in sec_w
           and r.get("weight") is not None and sec_w.get(str(r.get("stock_id"))) is not None]
    max_dw = round(max(dws), 2) if dws else None
    ok = hit >= max(1, int(len(top) * _XCHK_OVERLAP))
    if weights:
        ok = ok and (max_dw is None or max_dw <= _XCHK_DW_PP)
    return {"status": "match" if ok else "mismatch", "weights_compared": weights,
            "top_hit": hit, "top_n": len(top), "n_common": len(dws), "max_dw": max_dw}


# ── 當日貢獻歸因 ──────────────────────────────────────────────────────

def _chg_pct(px: dict | None) -> float | None:
    """{close, change} → 當日漲跌%。change 為金額；前收＝close − change。"""
    if not px:
        return None
    close, chg = px.get("close"), px.get("change")
    if close is None or chg is None:
        return None
    prev = close - chg
    return round(chg / prev * 100, 2) if prev else None


_MOVE_N = 40         # 異動清單上限（方塊圖＋異動表用；其餘併「其餘 N 檔」）


def _kind(d_shares, is_new: bool, is_out: bool) -> str | None:
    """異動類型：新增／加碼／減碼／出清；None＝本次無異動或無可比基準。"""
    if is_out:
        return "out"
    if is_new:
        return "new"
    if d_shares is None or d_shares == 0:
        return None
    return "add" if d_shares > 0 else "cut"


def _moves(rows: list[dict], dropped: list[dict], move_n: int = _MOVE_N) -> dict:
    """異動清單（產業方塊圖／異動表用）。

    · 新增檔的「異動量」＝整個部位（prev 沒有它，Δ股數為 None 但實際是全額買進）；
      出清檔＝前一揭露日的全部股數（負值）。其餘為 Δ股數。
    · 排序依 |金額| 由大到小；無報價（海外／債券）時退回 |股數|——面積依據由
      `amount_basis` 誠實標明，不憑空補價。
    """
    out = []
    for r in rows + dropped:
        kind = _kind(r.get("d_shares"), bool(r.get("is_new")), bool(r.get("is_out")))
        if not kind:
            continue
        m_sh = r.get("shares") if kind == "new" else r.get("d_shares")
        if m_sh in (None, 0):
            continue
        close = r.get("close")
        amt = round(m_sh * close) if (close is not None) else None
        out.append({"stock_id": r["stock_id"], "name": r.get("name") or r["stock_id"],
                    "industry": r.get("industry"), "kind": kind,
                    "m_shares": m_sh, "lots": round(m_sh / 1000, 1),
                    "amount": amt, "weight": r.get("weight"),
                    "d_weight": r.get("d_weight")})
    priced = sum(1 for m in out if m["amount"] is not None)
    key = (lambda m: -abs(m["amount"] or 0)) if priced else (lambda m: -abs(m["m_shares"]))
    out.sort(key=key)
    shown, rest = out[:move_n], out[move_n:]
    return {"moves": shown, "moves_n": len(out), "moves_rest_n": len(rest),
            "moves_rest_amount": (round(sum(m["amount"] or 0 for m in rest)) if rest else None),
            "amount_basis": "amount" if priced else "shares"}


def contributions(entry: dict | None, quotes: dict[str, dict] | None,
                  ind: dict[str, str] | None = None,
                  top_n: int = _TOP_N) -> dict | None:
    """單檔 ETF 的展開明細資料。

    entry  ＝ data/etf_holdings.json 的 etfs[code]
    quotes ＝ {stock_id: {"close","change","name"}}（twse/tpex.fetch_today_all 合併）

    每列：權重、Δ股數（加減碼）、Δ權重、個股當日漲跌%、貢獻 pp（＝權重% × 漲跌% ÷ 100）。
    依 |貢獻| 由大到小排；超過 top_n 者併成一列合計，避免展開後灌爆版面。
    無報價的持股仍列出（貢獻顯示 —），但不計入合計——寧可少算，不憑空補值。
    """
    holdings = (entry or {}).get("holdings") or []
    if not holdings:
        return None
    prev = (entry or {}).get("prev") or {}
    rows, total, covered_w = [], 0.0, 0.0
    for h in holdings:
        sid = str(h.get("stock_id") or "")
        w = h.get("weight")
        sh = h.get("shares")
        p = prev.get(sid) or {}
        d_sh = (sh - p["shares"]) if (sh is not None and p.get("shares") is not None) else None
        d_w = (round(w - p["weight"], 2)
               if (w is not None and p.get("weight") is not None) else None)
        q = (quotes or {}).get(sid) or {}
        chg = _chg_pct(q)
        contrib = round(w * chg / 100, 3) if (w is not None and chg is not None) else None
        if contrib is not None:
            total += contrib
            covered_w += w or 0.0
        rows.append({"stock_id": sid, "name": h.get("name") or q.get("name") or sid,
                     "weight": w, "shares": sh, "d_shares": d_sh, "d_weight": d_w,
                     "chg_pct": chg, "contrib": contrib,
                     # 收盤價（金額 ＝ Δ股數 × 收盤）與產業別（方塊圖外層分組）——
                     # 兩者只有 CI 端取得到（容器 proxy 擋 twse/tpex），存進落檔供渲染
                     "close": q.get("close"), "industry": (ind or {}).get(sid),
                     # 新進／剔除標記：prev 有整份揭露時才判定（prev 空＝首日，不亂標「新增」）
                     "is_new": bool(prev) and sid not in prev})
    # 前一揭露日有、今日沒有的 → 已出清
    dropped = [{"stock_id": sid, "name": sid, "weight": None, "shares": 0,
                "d_shares": -(v.get("shares") or 0) if v.get("shares") else None,
                "d_weight": (round(-v["weight"], 2) if v.get("weight") is not None else None),
                "chg_pct": None, "contrib": None,
                "close": ((quotes or {}).get(sid) or {}).get("close"),
                "industry": (ind or {}).get(sid),
                "is_new": False, "is_out": True}
               for sid, v in prev.items() if sid not in _index(holdings)]
    # 「完整持股明細」（ETF 詳情第三段：搜尋＋排序＋分頁）需要**全部**持股列，
    # 不能只留貢獻前 12——依權重由大到小，與截圖預設排序一致（2026-07-30 使用者需求）
    full = sorted(rows, key=lambda r: (r.get("weight") is None, -(r.get("weight") or 0)))
    mv = _moves(rows, dropped)
    rows = list(rows)
    rows.sort(key=lambda r: (r["contrib"] is None, -abs(r["contrib"] or 0)))
    shown, rest = rows[:top_n], rows[top_n:]
    rest_contrib = round(sum(r["contrib"] for r in rest if r["contrib"] is not None), 3) if rest else None
    rest_weight = round(sum(r["weight"] or 0 for r in rest), 2) if rest else None
    # sum_weight＝揭露清單全體權重合計（≠covered_weight：後者只算「有報價」者）。
    # 全球型主動 ETF（如 00988A）的海外持股代號不符台股 4 碼格式、進不了本表——
    # sum_weight 遠低於 100 就是這種檔，儀表板據此標「僅台股部位」誠實揭露（2026-07-29）。
    return {"date": (entry or {}).get("date"), "prev_date": (entry or {}).get("prev_date"),
            "src": (entry or {}).get("src"), "verify": (entry or {}).get("verify"),
            "rows": shown, "dropped": dropped, "all": full, **mv,
            "rest_n": len(rest), "rest_contrib": rest_contrib, "rest_weight": rest_weight,
            "total_contrib": round(total, 2), "covered_weight": round(covered_w, 1),
            "sum_weight": round(sum(h.get("weight") or 0 for h in holdings), 1),
            "n_holdings": len(holdings)}


def annotate(doc: dict, quotes: dict[str, dict] | None,
             ind: dict[str, str] | None = None, top_n: int = _TOP_N) -> dict:
    """在**抓取端**（CI，連得到報價）把展開明細算好存進落檔的 `detail`。

    為什麼不在儀表板端算：容器內 proxy 擋 twse/tpex，建表時取不到個股報價；
    專案慣例本就是「抓取在 CI、容器內只讀落檔建表」（同 macro_chips／etf_watch）。
    報價抓不到時保留既有 detail，不覆寫成空。"""
    for entry in (doc.get("etfs") or {}).values():
        got = contributions(entry, quotes, ind, top_n)
        if got and (quotes or entry.get("detail") is None):
            entry["detail"] = got
    return doc


def view(doc: dict | None, code: str) -> dict | None:
    """儀表板端取數：以落檔已算好的 detail 為主（純渲染、不連網）。

    落檔 detail 缺 `all`（舊 schema，或 CI 當次取不到報價而沿用舊值）時，就地以
    `holdings`／`prev` 補算「完整持股 + 異動」——這兩者是**純比較、不需要網路**，
    只有收盤價與當日漲跌非連網不可。補算後把舊 detail 已有的個股報價／貢獻依代號嫁接
    回來，既不憑空補價、也不會讓整個詳情區空著（同專案「降級但誠實」慣例）。
    """
    entry = ((doc or {}).get("etfs") or {}).get(code) or {}
    det = entry.get("detail")
    if (det or {}).get("all") or not entry.get("holdings"):
        return det
    from . import stockmeta                     # 延遲載入：避免資料層互相 import
    fresh = contributions(entry, None, stockmeta.industry_map())
    if not fresh:
        return det
    priced = {r["stock_id"]: r for r in ((det or {}).get("rows") or [])}
    for r in fresh["all"]:
        o = priced.get(r["stock_id"])
        if o:
            r["close"], r["chg_pct"], r["contrib"] = o.get("close"), o.get("chg_pct"), o.get("contrib")
    for k in ("total_contrib", "covered_weight", "verify", "src"):
        if (det or {}).get(k) is not None:
            fresh[k] = det[k]
    return fresh
