#!/usr/bin/env python3
"""景氣溫度頁 H0 第三輪探針（docs/lab_heat_plan.md 第 10 節）：前兩輪還缺的兩項。

① 美國 CPI 長歷史：勞工統計局 v1 的 GET 不吃年份參數（只回近 3 年），改試 v1 POST（JSON，一次 10 年）、
   v2 GET（不帶金鑰）、DBnomics 轉載。
② 聯邦基金有效利率 2016 年以前：紐約聯準銀行只有 2016-03 起；試聯準會理事會 H.15 下載（CSV／ZIP）、DBnomics。
③ 期交所 P/C 比最早到哪一年。
結果寫 data/lab/heat_probe3.json（lab_backfill.yml 會 commit 回分支）；合併前刪掉。
"""
from __future__ import annotations

import io
import json
import ssl
import sys
import time
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import certifi  # noqa: E402

from scripts.probe_heat import BROWSER, RES, guard, log, plain, rec, taifex  # noqa: E402

OUT = ROOT / "data" / "lab" / "heat_probe3.json"
CTX = ssl.create_default_context(cafile=certifi.where())


def post_json(url: str, body: dict, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={
        **BROWSER, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return r.read()


def bls_post(a: int, z: int) -> None:
    name = f"勞工統計局 CPI v1 POST {a}–{z}"

    def run():
        b = post_json("https://api.bls.gov/publicAPI/v1/timeseries/data/",
                      {"seriesid": ["CUUR0000SA0"], "startyear": str(a), "endyear": str(z)})
        doc = json.loads(b.decode("utf-8"))
        rows = ((((doc.get("Results") or {}).get("series") or [{}])[0]) or {}).get("data") or []
        per = sorted(f"{r['year']}-{r['period']}" for r in rows if r.get("period", "").startswith("M"))
        rec(name, ok=bool(per), status=doc.get("status"), msg=doc.get("message"), n=len(per),
            first=per[0] if per else None, last=per[-1] if per else None, head=rows[:2], tail=rows[-2:])
    guard(name, run)


def fed_zip() -> None:
    name = "聯準會理事會 H.15 ZIP"

    def run():
        req = urllib.request.Request("https://www.federalreserve.gov/datadownload/Output.aspx?rel=H15&filetype=zip",
                                     headers=BROWSER)
        with urllib.request.urlopen(req, timeout=120, context=CTX) as r:
            b = r.read()
        info = {"bytes": len(b)}
        try:
            z = zipfile.ZipFile(io.BytesIO(b))
            info["files"] = [(n.filename, n.file_size) for n in z.infolist()][:20]
            for n in z.infolist():
                if n.filename.lower().endswith(".xml") and n.file_size > 10000:
                    txt = z.read(n.filename)[:200000].decode("utf-8", "replace")
                    i = txt.find("RIFSPFF_N.B")
                    info["ff_ctx"] = txt[max(0, i - 600):i + 1500] if i >= 0 else None
                    info["xml_head"] = txt[:1500]
                    break
        except zipfile.BadZipFile:
            info["head"] = b[:600].decode("utf-8", "replace")
        rec(name, ok="files" in info, **info)
    guard(name, run)


def main() -> None:
    t0 = time.time()
    for a, z in ((1990, 1999), (2000, 2009)):
        bls_post(a, z)
        time.sleep(1)
    plain("勞工統計局 CPI v2 GET 1990–2009（無金鑰）",
          "https://api.bls.gov/publicAPI/v2/timeseries/data/CUUR0000SA0?startyear=1990&endyear=2009")
    plain("DBnomics 美國 CPI", "https://api.db.nomics.world/v22/series/BLS/cu/CUUR0000SA0?observations=1&format=json")
    plain("聯準會理事會 H.15 頁面", "https://www.federalreserve.gov/releases/h15/")
    plain("聯準會理事會 H.15 CSV（全部日資料）",
          "https://www.federalreserve.gov/datadownload/Output.aspx?rel=H15&series=bf17364827e38702b42a58cf8eaa3f78"
          "&lastobs=&from=01/01/1990&to=12/31/2026&filetype=csv&label=include&layout=seriescolumn")
    fed_zip()
    plain("DBnomics 聯邦基金有效利率", "https://api.db.nomics.world/v22/series/FED/H15/RIFSPFF_N.B?observations=1&format=json")
    for ym in ("2001/12", "2005/01", "2010/01", "2013/01"):
        y, m = ym.split("/")
        taifex(f"期交所 P/C {ym}", "pcRatioDown", {"queryStartDate": f"{y}/{m}/01", "queryEndDate": f"{y}/{m}/28"})
        time.sleep(1.5)
    OUT.write_text(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "res": RES},
                              ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    ok = sum(1 for v in RES.values() if v.get("ok"))
    log(f"[heat-probe3] 完成 {ok}/{len(RES)} 個成功，{time.time() - t0:.0f} 秒；寫 {OUT}")


if __name__ == "__main__":
    main()
