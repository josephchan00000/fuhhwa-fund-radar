"""gnews 真實刊出日驗證（離線純函式）：原文 URL 直解、batchexecute 回應解析、
原文頁刊出日抽取。2026-08-06 起防「Google News 把舊文 pubDate 標成近期」。"""
import base64
import json
from datetime import datetime
from urllib.parse import parse_qs

from arm.connectors import gnews


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def test_decoded_direct_url_old_format():
    # 舊式文章 id：base64 內嵌原文 URL（protobuf 夾雜長度位元組）
    aid = _b64(b'\x08\x13"\x22https://www.ctee.com.tw/news/x1\xd2\x01\x00')
    assert gnews._decoded_direct_url(aid) == "https://www.ctee.com.tw/news/x1"
    # 新式 id：解出來只有 AU_yq… 文字、無 URL → None（走 batchexecute 路徑）
    assert gnews._decoded_direct_url(_b64(b'\x08\x13"ZAU_yqLPpXbBihnEF-ESv')) is None
    # 內嵌的是 news.google.com 自家連結 → 不算原文
    assert gnews._decoded_direct_url(_b64(b'"https://news.google.com/x')) is None
    assert gnews._decoded_direct_url("!!!not-base64!!!") is None


def test_url_from_batch_structured_and_fallback():
    payload = json.dumps(["garturlres", "https://money.udn.com/money/story/5618/123"])
    line = json.dumps([["wrb.fr", "Fbv4je", payload, None, None, None, "generic"]])
    raw = ")]}'\n\n583\n" + line + "\n25\n" + json.dumps([["di", 59]])
    assert gnews.url_from_batch(raw) == "https://money.udn.com/money/story/5618/123"
    # 版式漂移 → 字面掃描退路：取第一個非 Google 網域 URL（跳脫斜線也要解）
    raw2 = ")]}'\n\nxx https:\\/\\/news.google.com\\/rss\\/1 yy https:\\/\\/www.ctee.com.tw\\/news\\/2 zz"
    assert gnews.url_from_batch(raw2) == "https://www.ctee.com.tw/news/2"
    assert gnews.url_from_batch(")]}'\n\nhttps://news.google.com/only") is None
    assert gnews.url_from_batch("") is None


def test_published_from_html_jsonld_meta_time():
    jsonld = ('<html><script type="application/ld+json">'
              '{"@type":"NewsArticle","datePublished":"2026-04-14T18:30:00+08:00"}'
              "</script></html>")
    dt = gnews.published_from_html(jsonld)
    assert (dt.year, dt.month, dt.day) == (2026, 4, 14)
    # og meta 兩種屬性順序都要收
    for tag in ('<meta property="article:published_time" content="2026-04-14T10:00:00Z">',
                '<meta content="2026-04-14" property="article:published_time">'):
        dt = gnews.published_from_html(f"<html>{tag}</html>")
        assert dt and (dt.month, dt.day) == (4, 14), tag
    dt = gnews.published_from_html('<time datetime="2026-04-14T09:00">14日</time>')
    assert dt and dt.day == 14 and dt.tzinfo is not None


def test_published_from_url_path_fallback_and_no_false_positive():
    # 工商時報：日期在 URL 路徑（20260414700256）——metadata 缺時的最後退路
    dt = gnews.published_from_html(
        "<html>無日期標記</html>", "https://www.ctee.com.tw/news/20260414700256-439901")
    assert (dt.year, dt.month, dt.day) == (2026, 4, 14)
    # udn 純流水號路徑不可誤判成日期
    assert gnews.published_from_html(
        "<html></html>", "https://udn.com/news/story/123006/9436558") is None
    assert gnews.published_from_html("", "") is None


def test_parse_meta_dt_variants():
    assert gnews._parse_meta_dt("2026-04-14T18:30:00+0800").day == 14   # 無冒號時區
    assert gnews._parse_meta_dt("Tue, 14 Apr 2026 10:00:00 +0800").day == 14  # RFC822
    naive = gnews._parse_meta_dt("2026-04-14")
    assert naive and naive.tzinfo is not None                            # 無時區→視為台北
    assert gnews._parse_meta_dt("1999-01-01") is None                    # 年份不合理
    assert gnews._parse_meta_dt("not a date") is None
    assert gnews._parse_meta_dt("") is None


def test_batch_payload_shape():
    body = gnews._batch_payload("ABC123", "1723", "sig==").decode()
    assert body.startswith("f.req=")
    outer = json.loads(parse_qs(body)["f.req"][0])
    assert outer[0][0][0] == "Fbv4je"
    inner = json.loads(outer[0][0][1])
    assert inner[0] == "garturlreq" and inner[2] == "ABC123"
    assert inner[3] == 1723 and inner[4] == "sig=="


def test_plausible_year_guard():
    assert gnews._plausible(datetime(2026, 4, 14)) is not None
    assert gnews._plausible(datetime(1999, 1, 1)) is None
    assert gnews._plausible(datetime(2199, 1, 1)) is None
    assert gnews._plausible(None) is None
