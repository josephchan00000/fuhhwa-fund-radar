"""台股位階往前補資料的探針（docs/lab_earnings_plan.md 第 14 節）：只印、不寫檔。只在 CI 跑（本容器擋證交所、櫃買、Yahoo、FinMind、期交所）。

看三件事能回到哪一年：
  1. 廣度（T5～T7）要的每一檔日線與月底市值：證交所月底收盤（q_tw）與發行股數（x_tw）、櫃買月底（q_tp）、
     Yahoo 個股日線（現在還在的）、FinMind 個股日線（已下市的）
  2. 部位與籌碼（C4～C6）要的期貨、選擇權法人未平倉：FinMind（現在的來源）、期交所官方三大法人下載
  3. 小台全市場未平倉（C4 的分母）：期交所期貨每日交易行情下載
用法：python3 scripts/probe_twhist.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _try(label, f):
    try:
        print(f"  {label}：{f()}")
    except Exception as e:                                    # noqa: BLE001
        print(f"  {label}：失敗 {type(e).__name__}: {str(e)[:160]}")


def _rows(x):
    if x is None:
        return "沒有資料"
    if isinstance(x, dict):
        return f"{len(x)} 筆"
    if isinstance(x, (list, tuple)):
        return f"{len(x)} 筆"
    return str(x)[:80]


def main() -> None:
    from arm.lab import market as MK
    from arm.lab import heatfetch as HF
    print("== 1a. 證交所月底收盤（q_tw）與發行股數（x_tw）")
    for d in ("2004-02-27", "2005-12-30", "2008-12-31", "2010-12-31", "2012-12-28"):
        for part in ("q_tw", "x_tw"):
            _try(f"{part} {d}", lambda part=part, d=d: (lambda r: f"{r[1]}，{_rows(r[0])}")(MK.fetch_part(part, d)))
    print("== 1b. 櫃買月底（q_tp）")
    for d in ("2007-01-31", "2008-12-31", "2010-12-31", "2012-12-28"):
        _try(f"q_tp {d}", lambda d=d: (lambda r: f"{r[1]}，{_rows(r[0])}")(MK.fetch_part("q_tp", d)))
    print("== 1c. Yahoo 個股日線（從 2003 起要）")
    for s in ("2330.TW", "2317.TW", "1101.TW", "2002.TW", "5347.TWO"):
        _try(s, lambda s=s: (lambda h: f"{len(h.get('t') or h.get('d') or [])} 天，第一天 {(h.get('t') or h.get('d') or ['—'])[0]}")(
            MK.yahoo_hist_from(s, "2003-01-01", adj=True) or {}))
    print("== 1d. FinMind 已下市個股日線")
    for c in ("2311", "2325", "2448"):
        _try(f"TaiwanStockPrice {c}", lambda c=c: (lambda r: f"{len(r)} 天，第一天 {r[0].get('date') if r else '—'}")(
            HF._finmind("TaiwanStockPrice", c, "2003-01-01", "2013-01-01")))
    print("== 2a. FinMind 期貨、選擇權法人（現在的來源）")
    for a, z in (("2007-07-01", "2007-07-31"), ("2012-01-01", "2012-01-31"), ("2017-01-01", "2017-01-31"), ("2019-06-01", "2019-06-30")):
        _try(f"TaiwanFuturesInstitutionalInvestors TX {a}", lambda a=a, z=z: _rows(HF._finmind("TaiwanFuturesInstitutionalInvestors", "TX", a, z)))
        _try(f"TaiwanOptionInstitutionalInvestors TXO {a}", lambda a=a, z=z: _rows(HF._finmind("TaiwanOptionInstitutionalInvestors", "TXO", a, z)))
    print("== 2b. 期交所官方三大法人（期貨、選擇權）")
    for url, form in (
            ("https://www.taifex.com.tw/cht/3/futContractsDateDown", {"queryStartDate": "2008/01/02", "queryEndDate": "2008/01/10", "commodityId": "TXF"}),
            ("https://www.taifex.com.tw/cht/3/futContractsDateDown", {"queryStartDate": "2008/01/02", "queryEndDate": "2008/01/10", "commodityId": "MXF"}),
            ("https://www.taifex.com.tw/cht/3/callsAndPutsDateDown", {"queryStartDate": "2008/01/02", "queryEndDate": "2008/01/10", "commodityId": "TXO"}),
            ("https://www.taifex.com.tw/cht/3/futContractsDateDown", {"queryStartDate": "2015/01/05", "queryEndDate": "2015/01/09", "commodityId": "TXF"})):
        def go(url=url, form=form):
            txt = MK.post_bytes(url, form, timeout=60, retries=1).decode("cp950", "replace")
            ls = [x for x in txt.splitlines() if x.strip()]
            return f"{len(ls)} 行；前兩行 {ls[:2]!r}"[:400]
        _try(f"{url.rsplit('/', 1)[-1]} {form['commodityId']} {form['queryStartDate']}", go)
    print("== 3. 期交所期貨每日交易行情（小台全市場未平倉）")
    def mtx():
        txt = MK.post_bytes("https://www.taifex.com.tw/cht/3/futDataDown",
                            {"down_type": "1", "commodity_id": "MTX", "queryStartDate": "2008/01/02", "queryEndDate": "2008/01/04"},
                            timeout=60, retries=1).decode("cp950", "replace")
        ls = [x for x in txt.splitlines() if x.strip()]
        return f"{len(ls)} 行；前兩行 {ls[:2]!r}"[:400]
    _try("futDataDown MTX 2008/01", mtx)


if __name__ == "__main__":
    main()
