"""探針：官方免費資料（處置股歷史、集保股權分散表）能不能拿、格式長怎樣——只印 CI 日誌，不落檔。

用法：python scripts/probe_official.py
  證交所處置公告（rwd 新站、舊站、openapi）、櫃買處置公告（新站 GET/POST、舊站、openapi），
  各試幾個年份與區間長度；集保 opendata 1-5（最新一週）與集保查詢頁可選的歷史日期。
"""

from __future__ import annotations

import json
import re
import ssl
import time

import requests

UA = {"User-Agent": "Mozilla/5.0 (research; superstock-lab)", "Accept": "application/json,text/html,*/*"}


def roc(y: int, m: int, d: int) -> str:
    return f"{y - 1911}/{m:02d}/{d:02d}"


def show(label: str, r: requests.Response | None, err: str | None = None) -> None:
    if r is None:
        print(f"\n### {label}\n   ✗ {err}")
        return
    ct = r.headers.get("content-type", "")
    txt = r.text
    print(f"\n### {label}\n   HTTP {r.status_code}｜{ct}｜{len(r.content):,} bytes｜{r.url[:160]}")
    try:
        j = r.json()
    except Exception:
        print("   非 JSON：", re.sub(r"\s+", " ", txt[:500]))
        return
    if isinstance(j, list):
        print(f"   list {len(j)} 筆；首筆：", json.dumps(j[:2], ensure_ascii=False)[:700])
        return
    keys = list(j.keys())
    print("   keys：", keys[:20])
    for k in ("stat", "total", "date", "title", "subtitle", "iTotalRecords", "reportDate", "msg"):
        if k in j:
            print(f"   {k}：", str(j[k])[:200])
    for k in ("fields", "aaData", "data"):
        if k in j:
            v = j[k]
            if isinstance(v, list):
                print(f"   {k}：{len(v)} 筆；前 3：", json.dumps(v[:3], ensure_ascii=False)[:900])
            else:
                print(f"   {k}：", str(v)[:300])
    if "tables" in j and isinstance(j["tables"], list):
        for t in j["tables"][:3]:
            if isinstance(t, dict):
                rows = t.get("data") or []
                print(f"   table「{t.get('title')}」fields={t.get('fields')}｜{len(rows)} 筆；前 3：",
                      json.dumps(rows[:3], ensure_ascii=False)[:900], "｜末筆：", json.dumps(rows[-1:], ensure_ascii=False)[:300])


def get(s: requests.Session, label: str, url: str, **kw) -> requests.Response | None:
    try:
        r = s.get(url, headers=UA, timeout=40, **kw)
        show(label, r)
        return r
    except Exception as e:
        show(label, None, f"{type(e).__name__}: {e}"[:300])
    finally:
        time.sleep(3)


def post(s: requests.Session, label: str, url: str, data: dict) -> requests.Response | None:
    try:
        r = s.post(url, data=data, headers=UA, timeout=40)
        show(label + f"（POST {data}）", r)
        return r
    except Exception as e:
        show(label, None, f"{type(e).__name__}: {e}"[:300])
    finally:
        time.sleep(3)


def twse(s: requests.Session) -> None:
    print("\n========== 證交所 處置有價證券 ==========")
    for (a, b) in [("20240101", "20240131"), ("20240101", "20241231"), ("20180101", "20180131"),
                   ("20120101", "20120131"), ("20080101", "20080131"), ("20000101", "20000131")]:
        get(s, f"rwd punish {a}~{b}",
            f"https://www.twse.com.tw/rwd/zh/announcement/punish?startDate={a}&endDate={b}&response=json")
    get(s, "rwd punish（querytype=1、全欄位參數）",
        "https://www.twse.com.tw/rwd/zh/announcement/punish?startDate=20240101&endDate=20240131"
        "&querytype=1&stockNo=&selectType=&proceType=&remarkType=&response=json")
    get(s, "舊站 punish", "https://www.twse.com.tw/announcement/punish?response=json&startDate=20240101&endDate=20240131")
    get(s, "openapi punish（目前）", "https://openapi.twse.com.tw/v1/announcement/punish")
    get(s, "rwd notice（注意股，參考）",
        "https://www.twse.com.tw/rwd/zh/announcement/notice?startDate=20240101&endDate=20240105&response=json")


def tpex(s: requests.Session) -> None:
    print("\n========== 櫃買 處置有價證券 ==========")
    base = "https://www.tpex.org.tw/www/zh-tw/bulletin/disposal"
    for (sd, ed) in [((2024, 1, 1), (2024, 1, 31)), ((2018, 1, 1), (2018, 1, 31)), ((2008, 1, 1), (2008, 1, 31))]:
        a_ad, b_ad = "%d/%02d/%02d" % sd, "%d/%02d/%02d" % ed
        get(s, f"新站 GET 西元 {a_ad}~{b_ad}", f"{base}?startDate={a_ad}&endDate={b_ad}&response=json")
        get(s, f"新站 GET 民國 {roc(*sd)}~{roc(*ed)}", f"{base}?startDate={roc(*sd)}&endDate={roc(*ed)}&response=json")
    post(s, "新站", base, {"startDate": "2024/01/01", "endDate": "2024/01/31", "response": "json"})
    post(s, "新站（民國）", base, {"startDate": roc(2024, 1, 1), "endDate": roc(2024, 1, 31), "response": "json"})
    get(s, "新站 GET 全年 2024", f"{base}?startDate=2024/01/01&endDate=2024/12/31&response=json")
    old = "https://www.tpex.org.tw/web/bulletin/disposal_information/disposal_information_result.php"
    get(s, "舊站 2024-01", f"{old}?l=zh-tw&o=json&sd={roc(2024, 1, 1)}&ed={roc(2024, 1, 31)}")
    get(s, "舊站 2010-01", f"{old}?l=zh-tw&o=json&sd={roc(2010, 1, 1)}&ed={roc(2010, 1, 31)}")
    get(s, "openapi disposal（目前）", "https://www.tpex.org.tw/openapi/v1/tpex_disposal_information")


def _lenient_tls_get(url: str) -> requests.Response | None:
    """集保憑證缺 Subject Key Identifier，嚴格模式驗不過：仍驗證憑證鏈與主機名，只關掉 X509 嚴格檢查。"""
    import certifi
    from requests.adapters import HTTPAdapter

    class A(HTTPAdapter):
        def init_poolmanager(self, *a, **kw):
            ctx = ssl.create_default_context(cafile=certifi.where())
            if hasattr(ssl, "VERIFY_X509_STRICT"):
                ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
            kw["ssl_context"] = ctx
            return super().init_poolmanager(*a, **kw)

    s = requests.Session()
    s.mount("https://", A())
    return s.get(url, headers=UA, timeout=90)


def tdcc(s: requests.Session) -> None:
    print("\n========== 集保 股權分散表 ==========")
    url = "https://opendata.tdcc.com.tw/getOD.ashx?id=1-5"
    for label, fn in (("requests 預設", lambda: s.get(url, headers=UA, timeout=90)),
                      ("關掉 X509 嚴格檢查", lambda: _lenient_tls_get(url))):
        try:
            r = fn()
            txt = r.content.decode("utf-8-sig", "replace")
            lines = txt.splitlines()
            print(f"\n### opendata 1-5（{label}）HTTP {r.status_code}｜{len(r.content):,} bytes｜{len(lines):,} 行")
            print("   表頭：", lines[0][:200] if lines else "")
            print("   前 3 列：", lines[1:4])
            codes = {ln.split(",")[1] for ln in lines[1:] if ln.count(",") >= 2}
            print("   代號數：", len(codes))
            break
        except Exception as e:
            print(f"\n### opendata 1-5（{label}）✗ {type(e).__name__}: {str(e)[:300]}")
        time.sleep(2)
    try:
        r = _lenient_tls_get("https://opendata.tdcc.com.tw/getOD.ashx?id=1-5&date=20240105")
        txt = r.content.decode("utf-8-sig", "replace").splitlines()
        print(f"\n### opendata 1-5 帶 date=20240105：HTTP {r.status_code}｜首列資料日：", txt[1][:40] if len(txt) > 1 else "")
    except Exception as e:
        print(f"\n### opendata 1-5 帶 date ✗ {type(e).__name__}: {str(e)[:200]}")
    try:
        r = _lenient_tls_get("https://www.tdcc.com.tw/portal/zh/smWeb/qryStock")
        html = r.text
        opts = re.findall(r'<option[^>]*value="(\d{8})"', html)
        print(f"\n### 集保查詢頁 qryStock：HTTP {r.status_code}｜{len(html):,} 字｜可選資料日 {len(opts)} 個：",
              (opts[:3], opts[-3:]) if opts else re.sub(r"\s+", " ", html[:600]))
        tok = re.search(r'name="SYNCHRONIZER_TOKEN"\s+value="([^"]+)"', html)
        print("   表單 token：", "有" if tok else "無", "｜表單欄位：",
              sorted(set(re.findall(r'name="([A-Za-z_]+)"', html)))[:30])
    except Exception as e:
        print(f"\n### 集保查詢頁 ✗ {type(e).__name__}: {str(e)[:200]}")


def main() -> None:
    s = requests.Session()
    twse(s)
    tpex(s)
    tdcc(s)


if __name__ == "__main__":
    main()
