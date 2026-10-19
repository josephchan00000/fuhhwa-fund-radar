"""景氣溫度與籌碼雷達共用的頂欄（2026-10-18 使用者：點主頁的「·」先到景氣頁、個股頁放旁邊；不要窄欄）。

台股景氣（x9m.html）、美股景氣（x9mu.html）、泡沫（x9b.html）、個股（x9.html，籌碼雷達）四頁的頂欄是同一組主分頁，右邊「返回主頁」。
泡沫頁 2026-10-18 起獨立（docs/lab_risk_plan.md 第 7 節：使用者「泡沫單獨拉出來、自己一個頁面不要混淆」）。
訊號總覽（x9o.html）2026-10-19 加入（docs/lab_signal_plan.md：「有一個地方是訊號總覽，所有訊號跟所有的策略妥善分類」）。
"""
from __future__ import annotations

TABS = (("tw", "台股景氣", "x9m.html"), ("us", "美股景氣", "x9mu.html"), ("bub", "泡沫", "x9b.html"), ("stk", "個股", "x9.html"),
        ("sig", "訊號總覽", "x9o.html"))

CSS = (".apptab{display:flex;gap:2px;background:var(--card2);border-radius:10px;padding:3px;align-self:center}"
       ".apptab a{padding:5px 12px;border-radius:8px;font-size:14.5px;font-weight:600;color:var(--ink2);"
       "text-decoration:none;white-space:nowrap}"
       ".apptab a:hover{color:var(--ink)}"
       ".apptab a.on{background:var(--bg);color:var(--ink);box-shadow:0 1px 3px rgba(20,30,50,.14)}"
       "@media (max-width:640px){.top>.apptab{flex:1 1 100%}.apptab a{flex:1;text-align:center;padding:5px 4px;font-size:14px}}")


def bar(active: str) -> str:
    """主分頁：目前所在的頁加 class="on"、aria-current="page"。"""
    out = []
    for key, label, href in TABS:
        on = ' class="on" aria-current="page"' if key == active else ""
        out.append(f'<a{on} href="{href}">{label}</a>')
    return '<nav class="apptab" aria-label="頁面">' + "".join(out) + "</nav>"
