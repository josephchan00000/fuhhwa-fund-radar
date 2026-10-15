"""Phase 1 關卡：抽 20 檔與官方公開資料對帳。

上市股票：自動抓證交所「個股日成交資訊」比對開高低收與成交股數（盡力而為）。
  端點（雲端環境無法實測，本機首次執行時確認；若格式改了請修 parse_twse_stock_day）：
  https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?date=YYYYMMDD&stockNo=XXXX&response=json
上櫃、下市股票與月營收：產生人工核對清單（附查詢網址），由你或本機 Claude Code 核對。
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path

import pandas as pd
import requests

TWSE_STOCK_DAY = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY"


def roc_to_date(text: str) -> pd.Timestamp:
    y, m, d = str(text).strip().split("/")
    return pd.Timestamp(year=int(y) + 1911, month=int(m), day=int(d))


def _num(text: str) -> float | None:
    t = str(text).replace(",", "").strip()
    if t in ("", "--", "---", "X0.00"):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def parse_twse_stock_day(payload: dict) -> pd.DataFrame:
    """把證交所 STOCK_DAY 的 JSON 轉成 date, volume, open, high, low, close。"""
    if payload.get("stat") not in ("OK", "ok") or not payload.get("data"):
        return pd.DataFrame()
    fields = payload.get("fields") or []
    idx = {name: i for i, name in enumerate(fields)}

    def col(name: str, fallback: int) -> int:
        return idx.get(name, fallback)

    rows = []
    for r in payload["data"]:
        rows.append({
            "date": roc_to_date(r[col("日期", 0)]),
            "volume": _num(r[col("成交股數", 1)]),
            "open": _num(r[col("開盤價", 3)]),
            "high": _num(r[col("最高價", 4)]),
            "low": _num(r[col("最低價", 5)]),
            "close": _num(r[col("收盤價", 6)]),
        })
    return pd.DataFrame(rows)


def pick_sample(universe: pd.DataFrame, prices: pd.DataFrame, n: int = 20, seed: int = 7) -> pd.DataFrame:
    """分層抽樣：上市大型、上市其他、上櫃、已下市。"""
    rng = random.Random(seed)
    value = prices.groupby("stock_id")["value"].median() if "value" in prices.columns else pd.Series(dtype=float)
    u = universe.copy()
    u["med_value"] = u["stock_id"].map(value).fillna(0)
    picks: list[str] = []

    def take(df: pd.DataFrame, k: int, by_value: bool = False) -> None:
        ids = [s for s in (df.sort_values("med_value", ascending=False)["stock_id"].tolist()
                           if by_value else df["stock_id"].tolist()) if s not in picks]
        if not by_value:
            rng.shuffle(ids)
        picks.extend(ids[:k])

    twse = u[(u["market"] == "twse") & ~u["is_delisted"]]
    tpex = u[(u["market"] == "tpex") & ~u["is_delisted"]]
    dele = u[u["is_delisted"]]
    take(twse, 5, by_value=True)
    take(twse, 5)
    take(tpex, 6)
    take(dele, 4)
    if len(picks) < n:
        take(u, n - len(picks))
    return u[u["stock_id"].isin(picks[:n])][["stock_id", "stock_name", "market", "is_delisted"]]


def reconcile(cfg, n: int = 20, sleep_sec: float = 3.0, session: requests.Session | None = None,
              fetch: bool = True) -> Path:
    proc = cfg.processed_dir
    universe = pd.read_parquet(proc / "universe.parquet")
    prices = pd.read_parquet(proc / "prices.parquet")
    revenue = pd.read_parquet(proc / "revenue.parquet") if (proc / "revenue.parquet").exists() else pd.DataFrame()
    sample = pick_sample(universe, prices, n)
    rng = random.Random(11)
    session = session or requests.Session()
    auto_rows, manual_rows = [], []

    for s in sample.itertuples(index=False):
        p = prices[prices["stock_id"] == s.stock_id]
        if p.empty:
            manual_rows.append({"stock_id": s.stock_id, "item": "價格", "note": "本機沒有價格資料"})
            continue
        months = sorted(p["date"].dt.to_period("M").unique())
        chosen = rng.sample(months, k=min(2, len(months)))
        for period in chosen:
            mine = p[p["date"].dt.to_period("M") == period]
            day = mine.sample(1, random_state=rng.randint(0, 10_000)).iloc[0]
            official = None
            if fetch and s.market == "twse" and not s.is_delisted:
                try:
                    resp = session.get(TWSE_STOCK_DAY, params={
                        "date": period.start_time.strftime("%Y%m01"), "stockNo": s.stock_id,
                        "response": "json"}, timeout=20)
                    official = parse_twse_stock_day(resp.json())
                    time.sleep(sleep_sec)  # 證交所會擋太密集的請求
                except Exception as exc:  # noqa: BLE001
                    official = None
                    manual_rows.append({"stock_id": s.stock_id, "item": f"{period} 價格",
                                        "note": f"自動抓取失敗：{exc}"})
            if official is not None and not official.empty:
                o = official[official["date"] == day["date"]]
                if o.empty:
                    auto_rows.append({"stock_id": s.stock_id, "date": str(day["date"].date()),
                                      "result": "官方無此日", "detail": ""})
                    continue
                o = o.iloc[0]
                diffs = []
                for col in ("open", "high", "low", "close"):
                    if o[col] is not None and abs(float(day[col]) - float(o[col])) > 0.0051:
                        diffs.append(f"{col} 本機 {day[col]} vs 官方 {o[col]}")
                if o["volume"] is not None and "volume" in day and abs(float(day["volume"]) - o["volume"]) > 0.5:
                    diffs.append(f"成交股數 本機 {int(day['volume'])} vs 官方 {int(o['volume'])}")
                auto_rows.append({"stock_id": s.stock_id, "date": str(day["date"].date()),
                                  "result": "一致" if not diffs else "不一致", "detail": "；".join(diffs)})
            else:
                manual_rows.append({
                    "stock_id": s.stock_id, "item": f"{day['date'].date()} 收盤價",
                    "note": f"本機：開 {day['open']} 高 {day['high']} 低 {day['low']} 收 {day['close']}"
                            f"｜{'上櫃' if s.market == 'tpex' else '已下市' if s.is_delisted else s.market}，請到櫃買中心或證交所網站核對"})
        if not revenue.empty:
            r = revenue[revenue["stock_id"] == s.stock_id]
            if not r.empty:
                row = r.sample(1, random_state=rng.randint(0, 10_000)).iloc[0]
                manual_rows.append({"stock_id": s.stock_id,
                                    "item": f"{int(row['revenue_year'])}-{int(row['revenue_month']):02d} 月營收",
                                    "note": f"本機：{int(row['revenue']):,} 元｜請到公開資訊觀測站核對（單位可能是千元）"})

    reports = Path(cfg.reports_dir)
    reports.mkdir(parents=True, exist_ok=True)
    n_auto = len(auto_rows)
    n_ok = sum(r["result"] == "一致" for r in auto_rows)
    lines = ["# 抽樣對帳（Phase 1 關卡）", "",
             f"抽樣 {len(sample)} 檔。自動比對 {n_auto} 筆、一致 {n_ok} 筆；人工核對 {len(manual_rows)} 項。", "",
             "## 自動比對（證交所官方日成交資訊）", "",
             "| 代號 | 日期 | 結果 | 差異 |", "| --- | --- | --- | --- |"]
    lines += [f"| {r['stock_id']} | {r['date']} | {r['result']} | {r['detail']} |" for r in auto_rows]
    lines += ["", "## 人工核對清單", "", "| 代號 | 項目 | 本機數值與說明 | 核對結果 |",
              "| --- | --- | --- | --- |"]
    lines += [f"| {r['stock_id']} | {r['item']} | {r['note']} | ☐ |" for r in manual_rows]
    path = reports / "reconciliation.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (reports / "reconciliation.json").write_text(json.dumps(
        {"sample": sample.to_dict("records"), "auto": auto_rows, "manual": manual_rows},
        ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path
