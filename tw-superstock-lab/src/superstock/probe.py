"""實測 FinMind 介面（SPEC §3.7）→ reports/live_probe.md（給人看）與 live_probe.json。

報告只寫欄位名、筆數、日期範圍、類別值與檢查結果，不寫原始資料列；token 一律不出現。
  ① 本機已下載的原始資料（smoke 下載過的）逐資料集摘要；
  ② REGISTRY 裡本機還沒有資料的逐檔資料集，各送一次小請求（預設 2330、近 3 年）；
  ③ 事件類資料集「不帶股票代號」能不能整批抓（下載時已判斷過的，直接讀進度紀錄）；
  ④ 語意檢查：月營收 date 的意思、財報 date 是否季底、除權息參考價一致性、股票清單 type 值、
     法人 name 值、指數代號 TAIEX／TPEx 有沒有資料、額度查詢回應格式。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from .config import Config
from .datasets import REGISTRY, DatasetSpec
from .finmind_client import FinMindClient, FinMindError
from .storage import GLOBAL_KEY, Manifest, Store

log = logging.getLogger(__name__)

# 只列「值的種類」不列資料：這些欄位是代碼／類別，不是價格或數量
_VALUE_COLS = ("type", "name", "stock_or_cache_dividend", "industry_category")
_MAX_VALUES = {"industry_category": 60, "type": 60}


def summarize(df: pd.DataFrame) -> dict[str, Any]:
    """欄位、型別、筆數、日期範圍、類別值（不含任何資料列）。"""
    out: dict[str, Any] = {"rows": int(len(df)), "columns": [str(c) for c in df.columns],
                           "dtypes": {str(c): str(t) for c, t in df.dtypes.items()}}
    if "date" in df.columns and len(df):
        d = pd.to_datetime(df["date"], errors="coerce")
        if d.notna().any():
            out["first_date"] = str(d.min().date())
            out["last_date"] = str(d.max().date())
    if "stock_id" in df.columns:
        out["ids"] = int(df["stock_id"].astype(str).nunique())
    values = {}
    for col in _VALUE_COLS:
        if col in df.columns:
            vc = df[col].astype(str).str.strip().value_counts()
            values[col] = {str(k): int(v) for k, v in vc.head(_MAX_VALUES.get(col, 25)).items()}
    if values:
        out["values"] = values
    return out


def revenue_semantics(df: pd.DataFrame) -> dict[str, Any]:
    """月營收的 date 和 revenue_year/revenue_month 是什麼關係（§3.7）。"""
    need = {"date", "revenue_year", "revenue_month"}
    if df.empty or not need <= set(df.columns):
        return {"checked": 0}
    d = pd.to_datetime(df["date"], errors="coerce")
    y = pd.to_numeric(df["revenue_year"], errors="coerce")
    m = pd.to_numeric(df["revenue_month"], errors="coerce")
    ok = d.notna() & y.notna() & m.notna()
    d, y, m = d[ok], y[ok].astype(int), m[ok].astype(int)
    period = pd.to_datetime(pd.DataFrame({"year": y, "month": m, "day": 1}))
    next_month = period + pd.offsets.MonthBegin(1)
    return {
        "checked": int(ok.sum()),
        "date_is_first_of_next_month": round(float((d == next_month).mean()), 4) if len(d) else None,
        "date_is_first_of_same_month": round(float((d == period).mean()), 4) if len(d) else None,
        "date_day_values": {str(k): int(v) for k, v in d.dt.day.value_counts().head(5).items()},
    }


def financial_semantics(df: pd.DataFrame) -> dict[str, Any]:
    """財報 date 是不是季底（§3.7），以及有哪些科目代碼（type）。"""
    if df.empty or "date" not in df.columns:
        return {"checked": 0}
    d = pd.to_datetime(df["date"], errors="coerce").dropna()
    qe = d.dt.is_month_end & d.dt.month.isin([3, 6, 9, 12])
    types = sorted(df["type"].astype(str).unique().tolist()) if "type" in df.columns else []
    return {"checked": int(len(d)), "quarter_end_share": round(float(qe.mean()), 4) if len(d) else None,
            "types": types[:80], "n_types": len(types)}


def dividend_semantics(df: pd.DataFrame) -> dict[str, Any]:
    """除權息結果：純現金股利列的 after_price 是否 ≈ before_price − 股利（§3.7、C7）。"""
    need = {"before_price", "after_price", "stock_and_cache_dividend", "stock_or_cache_dividend"}
    if df.empty or not need <= set(df.columns):
        return {"checked": 0, "missing_columns": sorted(need - set(df.columns))}
    cash = df[df["stock_or_cache_dividend"].astype(str).str.strip() == "息"]
    before = pd.to_numeric(cash["before_price"], errors="coerce")
    after = pd.to_numeric(cash["after_price"], errors="coerce")
    value = pd.to_numeric(cash["stock_and_cache_dividend"], errors="coerce")
    ok = (before > 0) & after.notna() & value.notna()
    diff = ((after - (before - value)).abs() / before)[ok]
    return {"checked": int(ok.sum()),
            "after_eq_before_minus_cash_share": round(float((diff <= 0.005).mean()), 4) if ok.any() else None}


def index_semantics(df: pd.DataFrame) -> dict[str, Any]:
    """指數代號（TAIEX、TPEx）各有幾筆、日期範圍。"""
    if df.empty or "stock_id" not in df.columns:
        return {}
    out = {}
    for sid, g in df.groupby(df["stock_id"].astype(str)):
        d = pd.to_datetime(g["date"], errors="coerce")
        out[sid] = {"rows": int(len(g)), "first_date": str(d.min().date()), "last_date": str(d.max().date())}
    return out


def _try(client: FinMindClient, spec: DatasetSpec, data_id: str, start: str, end: str) -> dict[str, Any]:
    try:
        df = client.get(spec.name, data_id=data_id, start_date=start if spec.use_dates else None,
                        end_date=end if spec.use_dates else None)
    except FinMindError as exc:
        return {"ok": False, "status": exc.status, "error": str(exc)[:300]}
    return {"ok": True, **summarize(df)}


def user_info_shape(cfg: Config, client: FinMindClient) -> dict[str, Any]:
    """額度查詢的回應長什麼樣（只記 HTTP 狀態與鍵名、數字欄位；不帶 token 也試一次）。"""
    out: dict[str, Any] = {}
    try:
        r = requests.get(cfg.finmind.user_info_url, timeout=cfg.finmind.timeout_sec)
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        out["without_token"] = {"http": r.status_code,
                                "keys": sorted(body)[:20] if isinstance(body, dict) else []}
    except Exception as exc:  # noqa: BLE001
        out["without_token"] = {"error": type(exc).__name__}
    if client.has_token:
        try:
            info = client.user_info()
            out["with_token"] = {"keys": sorted(info)[:20],
                                 "api_request_limit": info.get("api_request_limit"),
                                 "user_count": info.get("user_count")}
        except FinMindError as exc:
            out["with_token"] = {"http": exc.status, "error": str(exc)[:200]}
    return out


def run_probe(cfg: Config, client: FinMindClient, today: str, probe_stock: str = "2330",
              extra_calls: bool = True) -> dict[str, Any]:
    store = Store(cfg.raw_dir)
    manifest = Manifest(cfg.manifest_path)
    try:
        result: dict[str, Any] = {"today": today, "has_token": client.has_token,
                                  "limit_per_hour_used": client.limiter.per_hour,
                                  "datasets": {}, "semantics": {}}
        start = (pd.Timestamp(today) - pd.Timedelta(days=3 * 365)).date().isoformat()
        for spec in REGISTRY:
            name = spec.store_name
            keys = store.keys(spec)
            entry: dict[str, Any] = {"group": spec.group, "dataset": spec.name,
                                     "mode": manifest.get_mode(name) or spec.mode,
                                     "disabled": manifest.disabled_reason(name) or ""}
            if keys:
                df = store.read_all(spec, keys)
                entry["source"] = f"本機 {len(keys)} 個檔"
                entry.update(summarize(df))
                if spec.name == "TaiwanStockMonthRevenue":
                    result["semantics"]["revenue"] = revenue_semantics(df)
                elif spec.name == "TaiwanStockFinancialStatements":
                    result["semantics"]["financials"] = financial_semantics(df)
                elif spec.name == "TaiwanStockDividendResult":
                    result["semantics"]["dividend"] = dividend_semantics(df)
                elif name in ("IndexPrice", "TaiwanStockTotalReturnIndex"):
                    result["semantics"][name] = index_semantics(df)
            elif manifest.count(name):
                done = manifest.count(name)
                entry["source"] = "已下載、皆無資料" if not done.get("failed") else "下載失敗"
                entry["tasks"] = done
            elif extra_calls and spec.mode == "per_stock":
                entry["source"] = f"試抓 {probe_stock} {start}～{today}"
                entry.update(_try(client, spec, probe_stock, start, today))
            else:
                entry["source"] = "本機沒有資料"
            result["datasets"][name] = entry
        result["calls"] = client.calls
        return result
    finally:
        manifest.close()


def _fmt_values(values: dict) -> str:
    parts = []
    for col, vc in values.items():
        parts.append(f"{col}: " + "、".join(f"{k}({v})" for k, v in list(vc.items())[:12]))
    return "；".join(parts)


def write_probe_report(result: dict[str, Any], reports_dir: Path, generated_at: str | None = None) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = generated_at or pd.Timestamp.now(tz="Asia/Taipei").strftime("%Y-%m-%d %H:%M")
    lines = ["# FinMind 實測（SPEC §3.7）", "",
             f"產生時間：{ts}（台北）　token：{'有' if result.get('has_token') else '無（每小時 300 次）'}"
             f"　本次請求 {result.get('calls', 0)} 次", "",
             "| 資料集 | 群組 | 方式 | 結果 | 筆數 | 日期範圍 | 欄位 |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for name, e in result["datasets"].items():
        if e.get("ok") is False:
            status = f"失敗：{e.get('error', '')[:80]}"
        elif e.get("disabled"):
            status = f"停用：{e['disabled'][:60]}"
        elif "rows" in e:
            status = "有資料" if e["rows"] else "空"
        else:
            status = e.get("source", "")
        span = f"{e.get('first_date', '')}～{e.get('last_date', '')}" if e.get("first_date") else ""
        cols = ", ".join(e.get("columns", [])[:14])
        lines.append(f"| {name} | {e['group']} | {e.get('mode', '')} | {status} | {e.get('rows', '')} | {span} | {cols} |")
    lines += ["", "## 類別值", ""]
    for name, e in result["datasets"].items():
        if e.get("values"):
            lines.append(f"- {name}：{_fmt_values(e['values'])}")
    sem = result.get("semantics", {})
    lines += ["", "## 語意檢查", "", "```json", json.dumps(sem, ensure_ascii=False, indent=2), "```"]
    if result.get("user_info"):
        lines += ["", "## 額度查詢回應", "", "```json",
                  json.dumps(result["user_info"], ensure_ascii=False, indent=2), "```"]
    path = reports_dir / "live_probe.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (reports_dir / "live_probe.json").write_text(
        json.dumps({"generated_at": ts, **result}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path
