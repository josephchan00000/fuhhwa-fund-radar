"""2026-10-30 資安檢查的修補（repo 已公開；併檔通道把 claude/** 分支的資料帶進 main 後直接上網頁）。

L1：新聞併檔只收一般檔——git checkout 會把分支上的符號連結原樣變成 runner 上的連結，建頁讀它就把
    runner 的檔（環境變數、.git/config）印上網頁。
L2：外部餵入的連結（即將登場、基金月報、基金新聞、社群）一律只放行 http(s)。"""
from pathlib import Path

from arm import fund_dashboard as fd

ROOT = Path(__file__).resolve().parent.parent


def test_daily_news_merge_copies_regular_files_only():
    y = (ROOT / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")
    assert 'git checkout "$REF" -- "$f"' not in y
    assert 'git ls-tree "$REF" -- "$f"' in y and '= "100644" ]' in y and 'git show "$REF:$f" > "$f"' in y


def test_external_links_only_http():
    bad = "javascript:alert(1)"
    card = fd._upcoming_etf_card({"name": "復華X", "issuer": "復華投信", "url": bad, "status": "募集中"})
    row = fd._upcoming_hint_row({"name": "復華Y", "issuer": "復華投信", "url": bad})
    news = fd._fundnews_item({"title": "t", "url": bad, "date": "2026-10-30", "source": "s"})
    for h in (card, row, news):
        assert "javascript:" not in h
    ok = fd._upcoming_hint_row({"name": "復華Y", "issuer": "復華投信", "url": "https://example.com/x"})
    assert 'href="https://example.com/x"' in ok
