"""極簡 HTTP GET（標準庫 urllib），含重試、逾時、UA、磁碟快取。

用 urllib 以避免重依賴；正式版改 httpx 即可。
TLS 一律走 certifi CA 驗證（M1-7：移除未驗證退回，杜絕中間人風險）。
"""
from __future__ import annotations

import hashlib
import json
import ssl
import time
import urllib.request
import urllib.error
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "http_cache"
UA = "Mozilla/5.0 (FH-ARM research bot; contact: marketing)"


def _ssl_context() -> ssl.SSLContext:
    """一律以 certifi CA bundle 做完整 TLS 憑證驗證（不再退回未驗證）。"""
    try:
        import certifi
    except ImportError as e:  # certifi 是硬需求
        raise RuntimeError(
            "缺少 certifi：請執行 `python3 -m pip install certifi`（M1-7 已要求完整 TLS 驗證）。"
        ) from e
    return ssl.create_default_context(cafile=certifi.where())


_CTX = _ssl_context()


def _cache_path(url: str) -> Path:
    h = hashlib.sha1(url.encode()).hexdigest()[:16]
    return CACHE_DIR / f"{h}.bin"


def get_bytes(url: str, *, retries: int = 3, timeout: int = 25,
              use_cache: bool = True, cache_ttl: int = 3600,
              headers: dict | None = None, cache_ok=None) -> bytes:
    """抓 URL 回傳 bytes。預設快取 1 小時，避免重複打外部站。

    `headers`：額外標頭（如 PTT 的 over18 cookie、Dcard 的瀏覽器標頭）；併入快取鍵，
    避免「帶/不帶 cookie」拿到同一份快取。
    `cache_ok`：可選 predicate(bytes)->bool；只在為真時才寫快取。用來避免把暫時性的
    「查無資料／錯誤」回應寫進快取毒化後續 TTL（如 TWSE STOCK_DAY 偶發 stat!=OK）。
    """
    cache_key = url + ("|" + json.dumps(headers, sort_keys=True) if headers else "")
    cp = _cache_path(cache_key)
    if use_cache and cp.exists() and (time.time() - cp.stat().st_mtime) < cache_ttl:
        return cp.read_bytes()

    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as resp:
                data = resp.read()
            if use_cache and (cache_ok is None or cache_ok(data)):
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                cp.write_bytes(data)
            return data
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET 失敗 {url}: {last_err}")


def get_json(url: str, **kw) -> object:
    return json.loads(get_bytes(url, **kw).decode("utf-8"))
