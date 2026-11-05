"""盤中報價探針（docs/lab_txo_plan.md 第 17 節第 3 點）：手機瀏覽器能不能直接讀期交所／證交所的盤中報價。
只在 CI、盤中跑一次；只印、不寫任何檔、不算任何成績。看四件事：
  ① 拿不拿得到（狀態碼、欄位）；② 准不准別的網站直接讀（CORS：帶我們網站的 Origin，看 Access-Control-Allow-Origin；
  POST 帶 JSON 時瀏覽器會先送 OPTIONS 預檢，也一起看）；③ 不送預檢的寫法（text/plain）伺服器收不收；④ 延遲（報價時間 vs 現在）、多久更新一次。
容器連不到這兩個站，不要在容器裡跑。
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from arm.http import _CTX  # noqa: E402

TW = timezone(timedelta(hours=8))
SITE = "https://fuhhwa-fund-radar.vercel.app"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TF = "https://mis.taifex.com.tw/futures/api/"
CORS_H = ("access-control-allow-origin", "access-control-allow-methods", "access-control-allow-headers",
          "access-control-allow-credentials", "vary", "content-type", "cache-control", "server", "date")


def now() -> datetime:
    return datetime.now(TW)


def req(url, data=None, method=None, headers=None, timeout=10):
    t0 = time.time()
    r = urllib.request.Request(url, data=data, method=method, headers={"User-Agent": UA, **(headers or {})})
    try:
        with urllib.request.urlopen(r, timeout=timeout, context=_CTX) as resp:
            body = resp.read()
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, body, time.time() - t0
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read()[:500], time.time() - t0
    except Exception as e:                                                # noqa: BLE001
        return None, {}, f"{type(e).__name__}: {e}".encode()[:300], time.time() - t0


def show(tag, st, h, body, dt):
    print(f"\n=== {tag}：HTTP {st}，{dt * 1000:.0f} ms，{len(body)} bytes", flush=True)
    for k in CORS_H:
        if k in h:
            print(f"    {k}: {h[k]}")
    if not any(k.startswith("access-control") for k in h):
        print("    （沒有任何 Access-Control-* 標頭）")


def parse(body):
    try:
        return json.loads(body.decode("utf-8"))
    except Exception:                                                     # noqa: BLE001
        return None


def tf_body(sym_type, cid, exp=""):
    return {"MarketType": "0", "SymbolType": sym_type, "KindID": "1", "CID": cid, "ExpireMonth": exp,
            "RowSize": "全部", "PageNo": "", "SortColumn": "", "AscDesc": "A"}


def tf_post(api, body, tag, ctype="application/json;charset=UTF-8", origin=SITE):
    st, h, b, dt = req(TF + api, json.dumps(body).encode(), headers={"Content-Type": ctype, "Origin": origin,
                                                                     "Referer": origin + "/"})
    show(tag, st, h, b, dt)
    return st, h, parse(b) if st == 200 else None, b


def quotes(j):
    rt = (j or {}).get("RtData") or {}
    return rt.get("QuoteList") or []


def main() -> int:
    t = now()
    start = t.replace(hour=9, minute=5, second=0, microsecond=0)
    if t < start and (start - t).total_seconds() < 3600:
        print(f"[txolive] 現在 {t:%H:%M:%S}，等到 09:05 再測（要盤中）", flush=True)
        time.sleep((start - t).total_seconds())
    print(f"[txolive] 開始 {now():%F %H:%M:%S}（台北）", flush=True)

    # 1. 期交所：台指期（已知可用的寫法），帶我們網站的 Origin
    st, h, j, _ = tf_post("getQuoteList", tf_body("F", "TXF"), "期交所 台指期 getQuoteList（Origin＝我們網站）")
    q = quotes(j)
    if q:
        print("    筆數", len(q), "欄位", sorted(q[0])[:40])
        for x in q[:3]:
            print("   ", {k: x.get(k) for k in ("DispCName", "SymbolID", "CLastPrice", "CTime", "CDate", "Status")})

    # 2. 期交所：選擇權的幾種寫法（找得到報價的那一種）
    exp_lists = {}
    for api, body in (("getCmdyMonthDDLItemByKind", {"SymbolID": "TXO", "SymbolType": "O", "KindID": "1", "CID": "TXO"}),
                      ("getCmdyMonthDDLItemByKind", tf_body("O", "TXO")),
                      ("getCmdyDDLItemByKind", {"SymbolType": "O", "KindID": "1"})):
        st, h, j, b = tf_post(api, body, f"期交所 {api}（到期月份清單）")
        if j is not None:
            print("    回應", json.dumps(j, ensure_ascii=False)[:600])
            exp_lists[api] = j
    exps = []
    for j in exp_lists.values():
        for it in ((j.get("RtData") or {}).get("Items") or j.get("Items") or []) if isinstance(j, dict) else []:
            v = it.get("ExpireMonth") or it.get("Value") or it.get("CID") if isinstance(it, dict) else None
            if v and v not in exps:
                exps.append(v)
    print("\n[txolive] 找到的到期月份：", exps[:12])
    tries = exps[:3] or ["202611W2", "202611F2", "202611"]
    for api in ("getQuoteListOption", "getQuoteList"):
        for exp in tries[:2]:
            st, h, j, b = tf_post(api, tf_body("O", "TXO", exp), f"期交所 選擇權 {api} 到期 {exp}")
            q = quotes(j)
            print("    筆數", len(q), (("欄位 " + str(sorted(q[0])[:45])) if q else "回應 " + b[:300].decode("utf-8", "replace")))
            for x in q[:4]:
                print("   ", {k: x.get(k) for k in x if k in ("DispCName", "SymbolID", "StrikePrice", "CLastPrice", "CTime",
                                                             "CBidPrice1", "CAskPrice1", "CTotalVolume", "Status")})

    # 3. CORS 預檢（瀏覽器 POST JSON 之前會先送這個）
    for api in ("getQuoteList", "getQuoteListOption"):
        st, h, b, dt = req(TF + api, method="OPTIONS", headers={
            "Origin": SITE, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
        show(f"期交所 {api} 預檢 OPTIONS", st, h, b, dt)

    # 4. 不送預檢的寫法：Content-Type text/plain（瀏覽器的「簡單請求」）
    st, h, j, b = tf_post("getQuoteList", tf_body("F", "TXF"), "期交所 getQuoteList 用 text/plain（不送預檢）",
                          ctype="text/plain;charset=UTF-8")
    print("    伺服器收不收：", "收（有報價）" if quotes(j) else "不收／沒資料：" + b[:200].decode("utf-8", "replace"))

    # 5. 證交所 MIS：加權指數與台積電，帶我們網站的 Origin
    url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_t00.tw|tse_2330.tw&json=1&delay=0&_={int(time.time()*1000)}"
    st, h, b, dt = req(url, headers={"Origin": SITE, "Referer": SITE + "/"})
    show("證交所 MIS getStockInfo（Origin＝我們網站）", st, h, b, dt)
    j = parse(b) if st == 200 else None
    for x in (j or {}).get("msgArray", [])[:2]:
        print("   ", {k: x.get(k) for k in ("c", "n", "z", "t", "d", "tlong")})

    # 6. 延遲與更新頻率：每 10 秒抓一次台指期與加權指數，共 6 次
    print("\n[txolive] 延遲與更新頻率（現在時間 vs 報價時間）", flush=True)
    for i in range(6):
        st, h, b, dt = req(TF + "getQuoteList", json.dumps(tf_body("F", "TXF")).encode(),
                           headers={"Content-Type": "application/json;charset=UTF-8", "Origin": "https://mis.taifex.com.tw"})
        q = quotes(parse(b) if st == 200 else None)
        near = q[0] if q else {}
        st2, h2, b2, dt2 = req(f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_t00.tw&json=1&delay=0&_={int(time.time()*1000)}",
                               headers={"Referer": "https://mis.twse.com.tw/stock/index.jsp"})
        ix = ((parse(b2) or {}).get("msgArray") or [{}])[0] if st2 == 200 else {}
        print(f"    {now():%H:%M:%S}  台指期 {near.get('CLastPrice')} @ {near.get('CTime')}（{dt*1000:.0f} ms）  "
              f"加權指數 {ix.get('z')} @ {ix.get('t')}（{dt2*1000:.0f} ms）", flush=True)
        time.sleep(10)
    print(f"\n[txolive] 結束 {now():%H:%M:%S}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
