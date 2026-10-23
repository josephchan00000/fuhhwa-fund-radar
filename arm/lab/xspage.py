"""舊的大神策略頁（dashboard/x9x.html）＋淨值與每一筆（x9xh.json）。

2026-10-21 大神策略頁上線（docs/lab_nav_plan.md）；2026-10-22 使用者：「你的策略頁面好亂，應該是策略點進去，分成總經策略跟個股策略」
→ 改成策略頁・總經策略（個股頁同一支程式 page.py 的「策略」身分，docs/lab_strategy_ia_plan.md）。這支只剩兩件事：
  x9x.html   轉址頁：舊網址 #i=xs:市場:策略 轉到 x9.html#v=mac&m=市場&x=策略（舊書籤、舊連結照樣到得了）
  x9xh.json  每條策略的淨值與每一筆＋判定依據（訊號總覽的面板點開才下載；策略頁・總經策略打開「規則與成績」才下載，
             說明卡的 1 元變多少、逐筆交易、判定依據讀它）
成績與現在的狀態每天建頁時算（xstrat.run_all，程序內快取）。
"""
from __future__ import annotations

import json
from pathlib import Path

from . import xstratpage as XSP

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dashboard" / "x9x.html"
OUT_DATA = ROOT / "dashboard" / "x9xh.json"
NEW = XSP.HOME                                            # x9.html#v=mac

_HTML = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<link rel="icon" href="data:,">
<title>總經策略</title>
<script>(function(){var m=location.hash.match(/^#i=xs:([a-z0-9]+):([a-z0-9]+)$/),u="{{NEW}}";
if(m)u+="&m="+m[1]+"&x="+m[2];location.replace(u);})();</script>
<noscript><meta http-equiv="refresh" content="0;url={{NEW}}"></noscript>
</head>
<body><p>總經策略（原大神策略）在研究紀錄：<a href="{{NEW}}">打開總經策略</a></p></body></html>
"""


def view(R: dict | None = None) -> dict:
    return {"R": XSP.results() if R is None else R}


def render() -> str:
    return _HTML.replace("{{NEW}}", NEW)


def detail_json(V: dict) -> str:
    """點開才下載的淨值與每一筆（訊號總覽的面板、總經策略的說明卡）＋判定依據 jd（說明卡最下面，xsadvice.judge）。"""
    from . import xsadvice as XA
    out = XSP.detail(V["R"])
    for mk, M in V["R"].items():
        for k, r in (M or {}).items():
            out[f"xs:{mk}:{k}"]["jd"] = XA.judge(r)
    return json.dumps(out, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build(out: Path = OUT, data_out: Path = OUT_DATA) -> bool:
    V = view()
    if not V["R"]:                                        # 算不出來就留著上一版，不拿空的蓋掉
        print("[總經策略] 沒有結果，不改寫")
        return False
    changed = False
    for path, text in ((data_out, detail_json(V)), (out, render())):
        if path.exists() and path.read_text(encoding="utf-8") == text:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        changed = True
    return changed
