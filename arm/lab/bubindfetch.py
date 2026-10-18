"""產業泡沫的資料抓取（docs/lab_risk_plan.md 第 12.1 節；規格 bubindspec）。只在 CI 跑：本容器的 proxy 擋這些站。

  us_ff49x   Ken French 49 產業（價值加權）不含股利的月報酬（%）      {YYYY-MM: [49 個產業，沒有資料＝None]}  1926-07 起
  us_ff49n   Ken French 49 產業的家數                                    {YYYY-MM: [49]}
  us_ff49s   Ken French 49 產業的平均公司規模（百萬美元，前一個月底）  {YYYY-MM: [49]}
  us_etf_{代號}  SPDR 類股 ETF 與 SPY 的 Yahoo 收盤（已還原分割、不含股利）  {日期: 收盤}  1998-12 起

Ken French 的檔會整段修訂（CRSP 更新），所以整段換（_replace：這次拿到的筆數少於原有 9 成就只補不換）。
台股產業不用抓：用既有的 Panel、月營收、月底市值與 Yahoo 預估（bubind 裡算）。
解析函式（parse_*）不碰網路，tests/test_bubind.py 測。
"""
from __future__ import annotations

import io
import re
import zipfile

from . import bubindspec as BI
from .heatfetch import _get, _replace
from .heatfetch_us import yahoo_us
from .market import log

FF_SECTIONS = {"vw": "Average Value Weighted Returns -- Monthly", "n": "Number of Firms in Portfolios",
               "size": "Average Firm Size"}


def parse_ff_csv(txt: str) -> dict:
    """Ken French 的 CSV（好幾段表）→ {段落標題: {"cols": [欄名], "rows": {YYYY-MM 或 YYYY: [值或 None]}}}。
    段落標題是表頭（逗號開頭那一列）前面一列的文字；值 ≤ −99.99 是沒有資料。"""
    out: dict = {}
    lines = txt.replace("\r", "").split("\n")
    title, cur = None, None
    for i, raw in enumerate(lines):
        s = raw.strip()
        if not s:
            cur = None
            continue
        if s.startswith(","):
            cols = [c.strip() for c in s.split(",")[1:]]
            if title:
                cur = out.setdefault(title, {"cols": cols, "rows": {}})
            continue
        head = s.split(",")[0].strip()
        if re.fullmatch(r"\d{6}", head) and cur is not None:
            key = f"{head[:4]}-{head[4:]}"
        elif re.fullmatch(r"\d{4}", head) and cur is not None:
            key = head
        else:
            title, cur = s, None
            continue
        vals = []
        for x in s.split(",")[1:]:
            try:
                v = float(x)
            except ValueError:
                v = None
            vals.append(None if v is None or v <= BI.FF_MISSING + 1e-9 else v)
        cur["rows"][key] = vals
    return out


def _csv_from_zip(b: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(b)) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        return z.read(name).decode("latin-1")


def ff_tables(txt: str, keys=("vw",)) -> dict:
    """解析後挑出要的段（FF_SECTIONS），檢查欄名是 49 個產業（順序一樣）；不對就丟 ValueError（不寫壞資料）。"""
    P = parse_ff_csv(txt)
    out = {}
    for k in keys:
        sec = P.get(FF_SECTIONS[k])
        if not sec:
            raise ValueError(f"找不到「{FF_SECTIONS[k]}」；有的段：{list(P)[:12]}")
        if tuple(sec["cols"]) != BI.FF49:
            raise ValueError(f"「{FF_SECTIONS[k]}」欄名不是 49 產業：{sec['cols'][:6]}…")
        out[k] = {ym: v for ym, v in sec["rows"].items() if len(ym) == 7}
    return out


def ff49() -> int:
    """兩個 zip：不含股利的檔拿月報酬，含股利的檔拿家數與平均公司規模。"""
    xd = _csv_from_zip(_get(BI.FF_URL.format(f=BI.FF_FILES[1]), timeout=120))
    full = _csv_from_zip(_get(BI.FF_URL.format(f=BI.FF_FILES[0]), timeout=120))
    a = ff_tables(xd, ("vw",))
    b = ff_tables(full, ("n", "size"))
    n = _replace("us_ff49x", "ken_french_wout_div", a["vw"])
    n += _replace("us_ff49n", "ken_french", b["n"])
    n += _replace("us_ff49s", "ken_french", b["size"])
    ks = sorted(a["vw"])
    log(f"[bubind] Ken French 49 產業：月報酬 {len(ks)} 個月（{ks[0] if ks else '—'}～{ks[-1] if ks else '—'}）")
    return n


def etf_names() -> list[str]:
    return sorted(BI.US_ETF) + [BI.US_MKT]


def etf(start: str | None = None) -> int:
    """類股 ETF 與 SPY 的收盤（start 預設 US_START；每天只補最近的）。"""
    n = 0
    for sym in etf_names():
        n += yahoo_us(f"us_etf_{sym}", sym, start or BI.US_START)
    return n
