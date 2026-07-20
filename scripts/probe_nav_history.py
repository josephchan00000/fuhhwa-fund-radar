"""診斷：為「新加入追蹤清單」的基金探勘可用的歷史淨值來源，並把序列印進 CI 日誌。

背景：data/fund_nav_history.json 由每日 CI 累積，新加入追蹤的基金（如 101 已開發國家300）
只有加入後的 2 筆，1週/1月報酬算不出來；git 回填也救不了（_index 舊史裡沒有它）。
本腳本借 CI 網路各路試撈歷史淨值（官網走勢 API 候選／鉅亨詳情頁／MoneyDJ 淨值表），
成功的來源把「日期→淨值」序列以 `NAVHIST {fund_id} {json}` 行印出，只讀不寫。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm.http import get_bytes  # noqa: E402

# fund_id → (鉅亨 cnyesId, MoneyDJ 代碼)；None＝該來源無已知代碼
TARGETS: dict[str, tuple[str | None, str | None]] = {
    "101": ("A4ITGA5", "ACFH98"),
    "131": (None, None),
    "126": (None, None),
    "128": (None, None),
}

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"}


def _get(url: str) -> bytes | None:
    try:
        return get_bytes(url, cache_ttl=0, headers=UA, timeout=20, retries=1)
    except Exception as e:
        print(f"    GET 失敗 {url}: {type(e).__name__}: {e}")
        return None


def _emit(fid: str, src: str, series: dict[str, float]) -> None:
    if series:
        print(f"NAVHIST {fid} src={src} n={len(series)} {json.dumps(series, ensure_ascii=False)}")


def probe_fhtrust_chart(fid: str) -> None:
    """官網淨值走勢：掃 detail 頁 HTML 內含 'api' 的字串線索＋常見端點猜測。"""
    raw = _get(f"https://www.fhtrust.com.tw/funds/funds_detail/{fid}")
    if raw:
        html = raw.decode("utf-8", "ignore")
        hints = sorted(set(re.findall(r'["\']([^"\']*api[^"\']*)["\']', html)))[:40]
        print(f"  [{fid}] detail 頁 api 線索：{hints}")
    for tpl in (
        "https://www.fhtrust.com.tw/api/fundNav?fundID={f}",
        "https://www.fhtrust.com.tw/api/fundNavHistory?fundID={f}",
        "https://www.fhtrust.com.tw/api/fund/nav?fundID={f}",
        "https://www.fhtrust.com.tw/api/navChart?fundID={f}",
        "https://www.fhtrust.com.tw/api/fundChart?fundID={f}",
    ):
        url = tpl.format(f=fid)
        raw = _get(url)
        if raw:
            head = raw[:200].decode("utf-8", "ignore")
            print(f"  [{fid}] 候選 {url} → {len(raw)}B：{head!r}")
            try:
                d = json.loads(raw)
                series = _dig_series(d)
                _emit(fid, url, series)
            except Exception:
                pass


def _dig_series(obj) -> dict[str, float]:
    """遞迴挖『日期字串→數值』對或 [{date,nav}] 陣列。"""
    out: dict[str, float] = {}
    date_re = re.compile(r"^20\d{2}[/-]\d{2}[/-]\d{2}")

    def walk(o):
        if isinstance(o, dict):
            ks = list(o.keys())
            if ks and all(isinstance(k, str) and date_re.match(k) for k in ks):
                for k, v in o.items():
                    try:
                        out[k.replace("-", "/")] = float(v)
                    except (TypeError, ValueError):
                        pass
            dt = nv = None
            for k, v in o.items():
                lk = str(k).lower()
                if lk in ("date", "navdate", "pricedate", "tradedate") and isinstance(v, str) and date_re.match(v):
                    dt = v
                if lk in ("nav", "pnav", "price", "value", "close") and isinstance(v, (int, float, str)):
                    try:
                        nv = float(v)
                    except ValueError:
                        pass
            if dt and nv is not None:
                out[dt[:10].replace("-", "/")] = nv
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(obj)
    return out


def probe_cnyes(fid: str, cid: str) -> None:
    """鉅亨詳情頁（含 /history 走勢分頁）平衡物件掃描挖日期→淨值。"""
    from arm.connectors.cnyesfund import _objects_from_html  # 延遲載入避免不必要依賴
    for url in (f"https://fund.cnyes.com/detail/x/{cid}/",
                f"https://fund.cnyes.com/detail/x/{cid}/history/"):
        raw = _get(url)
        if not raw:
            continue
        html = raw.decode("utf-8", "ignore")
        objs = _objects_from_html(html)
        series: dict[str, float] = {}
        for o in objs:
            series.update(_dig_series(o))
        # 頁面內嵌 [timestamp, nav] 走勢陣列也試著撈
        for m in re.finditer(r"\[(1[6-9]\d{11}),\s*(\d+\.\d+)\]", html):
            import datetime as _dt
            d = _dt.datetime.fromtimestamp(int(m.group(1)) / 1000).strftime("%Y/%m/%d")
            series[d] = float(m.group(2))
        print(f"  [{fid}] cnyes {url}：物件 {len(objs)} 筆，挖到日期點 {len(series)} 筆")
        _emit(fid, url, series)


def probe_moneydj(fid: str, code: str) -> None:
    """MoneyDJ 淨值表（yp010002 每日淨值列表）。"""
    for url in (f"https://www.moneydj.com/funddj/ya/yp010002.djhtm?a={code}",
                f"https://www.moneydj.com/funddj/ya/yp010001.djhtm?a={code}"):
        raw = _get(url)
        if not raw:
            continue
        html = raw.decode("big5", "ignore") if b"big5" in raw[:400].lower() else raw.decode("utf-8", "ignore")
        rows = re.findall(r"(20\d{2}/\d{2}/\d{2})[^0-9-]{0,80}?(\d+\.\d{2,4})", re.sub(r"<[^>]+>", " ", html))
        series = {d: float(v) for d, v in rows[:40]}
        print(f"  [{fid}] moneydj {url}：解析出 {len(series)} 筆")
        _emit(fid, url, series)


for fid, (cid, djcode) in TARGETS.items():
    print(f"== fund {fid} ==")
    probe_fhtrust_chart(fid)
    if cid:
        probe_cnyes(fid, cid)
    if djcode:
        probe_moneydj(fid, djcode)
