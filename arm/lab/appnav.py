"""景氣溫度與籌碼雷達共用的頂欄（2026-10-18 使用者：點主頁的「·」先到景氣頁、個股頁放旁邊；不要窄欄）。

台股景氣（x9m.html）、美股景氣（x9mu.html）、泡沫（x9b.html）、個股（x9.html，籌碼雷達）四頁的頂欄是同一組主分頁，右邊「返回主頁」。
泡沫頁 2026-10-18 起獨立（docs/lab_risk_plan.md 第 7 節：使用者「泡沫單獨拉出來、自己一個頁面不要混淆」）。
訊號總覽（x9o.html）2026-10-19 加入（docs/lab_signal_plan.md：「有一個地方是訊號總覽，所有訊號跟所有的策略妥善分類」）。
大神策略（x9x.html）2026-10-21 加入（docs/lab_nav_plan.md：使用者「大神策略是放在訊號那邊而已嗎？這樣很難找」）；
2026-10-22 改成「策略」（docs/lab_strategy_ia_plan.md：「策略點進去，分成總經策略跟個股策略」）：策略與個股是同一頁 x9.html 的兩種身分，
策略＝x9.html#v=mac（頁面載入後依網址換身分、亮頂欄的「策略」）；x9x.html 留成轉址頁。
手機（640px 以下）六格放不下全名，改顯示短名（SHORT）。
"""
from __future__ import annotations

TABS = (("tw", "台股景氣", "x9m.html"), ("us", "美股景氣", "x9mu.html"), ("bub", "泡沫", "x9b.html"), ("st", "策略", "x9.html#v=mac"),
        ("stk", "個股", "x9.html"), ("sig", "訊號總覽", "x9o.html"))
SHORT = {"tw": "台股", "us": "美股", "sig": "訊號"}

CSS = (".apptab{display:flex;gap:2px;background:var(--card2);border-radius:10px;padding:3px;align-self:center}"
       ".apptab a{padding:5px 12px;border-radius:8px;font-size:14.5px;font-weight:600;color:var(--ink2);"
       "text-decoration:none;white-space:nowrap}"
       ".apptab a:hover{color:var(--ink)}"
       ".apptab a.on{background:var(--bg);color:var(--ink);box-shadow:0 1px 3px rgba(20,30,50,.14)}"
       ".apptab .aps{display:none}"
       "@media (max-width:640px){.top>.apptab{flex:1 1 100%}.apptab a{flex:1;text-align:center;padding:5px 2px;font-size:14px}"
       ".apptab .apl{display:none}.apptab .aps{display:inline}}")


def bar(active: str) -> str:
    """主分頁：目前所在的頁加 class="on"、aria-current="page"。"""
    out = []
    for key, label, href in TABS:
        on = ' class="on" aria-current="page"' if key == active else ""
        txt = f'<span class="apl">{label}</span><span class="aps">{SHORT[key]}</span>' if key in SHORT else label
        out.append(f'<a{on} href="{href}">{txt}</a>')
    return '<nav class="apptab" aria-label="頁面">' + "".join(out) + "</nav>"


# ── 日夜間模式（docs/lab_noise_plan.md 第 5、11 節；使用者 2026-10-20 選「自動 → 淺色 → 深色」三段）──────────────
#   六頁頂欄右邊一顆按鈕，點一下依序換；選擇記在這台瀏覽器（localStorage "labTheme"，沒有＝自動）。
#   <head> 一小段程式在畫面出來之前就套上 data-theme（不會先閃一下別的顏色）。
#   深色樣式原本只寫在 @media (prefers-color-scheme:dark) 裡；finish() 把每一段改寫成兩份：
#   「系統是深色而且沒選淺色」（:root:not([data-theme="light"])）與「選了深色」（:root[data-theme="dark"]）。
#   用程式算顏色的圖（景氣頁 3D 地形、個股頁資金地圖等）聽 "labtheme" 事件重畫。主頁（復華雷達）不用這支。
import re as _re

THEME_KEY = "labTheme"
_AUTO, _DARK = ':root:not([data-theme="light"])', ':root[data-theme="dark"]'
_DARK_MQ = _re.compile(r"@media\s*\(\s*prefers-color-scheme\s*:\s*dark\s*\)\s*\{")

THEME_HEAD = ('<script>(function(){var K="' + THEME_KEY + '",O=["auto","light","dark"],N={auto:"自動",light:"淺色",dark:"深色"},'
              'r=document.documentElement,cur="auto";'
              'try{var s=localStorage.getItem(K);if(s==="light"||s==="dark")cur=s}catch(e){}'
              'function ap(){if(cur==="auto")r.removeAttribute("data-theme");else r.setAttribute("data-theme",cur);'
              'var b=document.getElementById("thm");if(!b)return;b.setAttribute("data-t",cur);'
              'var t=b.querySelector(".thm-t");if(t)t.textContent=N[cur];'
              'var nx=N[O[(O.indexOf(cur)+1)%3]],lb="深淺色："+N[cur]+(cur==="auto"?"（跟系統）":"")+"，點一下換成"+nx;'
              'b.setAttribute("aria-label",lb);b.title=lb}'
              'ap();document.addEventListener("DOMContentLoaded",ap);'
              'document.addEventListener("click",function(e){var b=e.target&&e.target.closest&&e.target.closest("#thm");if(!b)return;'
              'cur=O[(O.indexOf(cur)+1)%3];try{if(cur==="auto")localStorage.removeItem(K);else localStorage.setItem(K,cur)}catch(x){}'
              'ap();try{window.dispatchEvent(new Event("labtheme"))}catch(x){}});'
              '})();</script>')

THEME_BTN = ('<button type="button" class="thm" id="thm" data-t="auto" aria-label="深淺色：自動（跟系統），點一下換成淺色">'
             '<svg class="ti-a" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" stroke-width="1.6"/>'
             '<path d="M8 2a6 6 0 0 1 0 12z" fill="currentColor"/></svg>'
             '<svg class="ti-l" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="3.1" fill="currentColor"/>'
             '<path d="M8 1.3v1.9M8 12.8v1.9M1.3 8h1.9M12.8 8h1.9M3.3 3.3l1.3 1.3M11.4 11.4l1.3 1.3M3.3 12.7l1.3-1.3M11.4 4.6l1.3-1.3" '
             'stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>'
             '<svg class="ti-d" viewBox="0 0 16 16" aria-hidden="true"><path d="M12.2 10.3A5.7 5.7 0 0 1 5.7 3.8a5.8 5.8 0 1 0 6.5 6.5z" fill="currentColor"/></svg>'
             '<span class="thm-t">自動</span></button>')

THEME_CSS = (".thm{display:inline-flex;align-items:center;gap:5px;align-self:center;padding:3px 10px;border:1px solid var(--line);"
             "border-radius:999px;background:var(--bg);color:var(--ink2);font:inherit;font-size:12.5px;line-height:1.4;white-space:nowrap;cursor:pointer}"
             ".thm:hover{color:var(--ink)}.thm:focus-visible{outline:2px solid var(--acc);outline-offset:2px}"
             ".thm svg{display:none;width:14px;height:14px;flex:none}"
             '.thm[data-t="auto"] .ti-a,.thm[data-t="light"] .ti-l,.thm[data-t="dark"] .ti-d{display:block}'
             ':root[data-theme="light"]{color-scheme:light}:root[data-theme="dark"]{color-scheme:dark}')

_BACK = '<a class="back" href="./">返回主頁</a>'


def _rules(body: str) -> list[tuple[str, str]] | None:
    """「選擇器{宣告}」一串 → [(選擇器, 宣告)]；裡面還有別的 @ 規則或括號對不上就回 None（照原樣保留）。"""
    out, i, n = [], 0, len(body)
    while i < n:
        j = body.find("{", i)
        if j < 0:
            return out if not body[i:].strip() else None
        k = body.find("}", j)
        sel = body[i:j].strip()
        if k < 0 or "@" in sel or "{" in body[j + 1:k]:
            return None
        out.append((sel, body[j + 1:k]))
        i = k + 1
    return out


def _pre(sel: str, p: str) -> str:
    out = []
    for s in sel.split(","):
        s = s.strip()
        out.append(p + s[5:] if s.startswith(":root") else f"{p} {s}")
    return ",".join(out)


def dual_dark(css: str) -> str:
    """每一段 @media (prefers-color-scheme:dark){…} → 「系統深色而且沒選淺色」＋「選了深色」兩份（見本節說明）。"""
    out, i = [], 0
    while True:
        m = _DARK_MQ.search(css, i)
        if not m:
            out.append(css[i:])
            return "".join(out)
        out.append(css[i:m.start()])
        k, depth = m.end(), 1
        while k < len(css) and depth:
            depth += (css[k] == "{") - (css[k] == "}")
            k += 1
        body = css[m.end():k - 1]
        rs = _rules(body)
        if rs is None:
            out.append(css[m.start():k])
        else:
            auto = "".join(f"{_pre(s, _AUTO)}{{{d}}}" for s, d in rs)
            dark = "".join(f"{_pre(s, _DARK)}{{{d}}}" for s, d in rs)
            out.append(f"@media (prefers-color-scheme:dark){{{auto}}}{dark}")
        i = k


def finish(page: str) -> str:
    """六頁輸出前最後一步：<head> 的樣式改寫成可切換深淺色、加切換程式，頂欄「返回主頁」前面加按鈕。"""
    h = page.find("</head>")
    if h < 0:
        return page
    head = page[:h]
    a, b = head.find("<style>"), head.find("</style>")
    if a >= 0 and b > a:
        head = head[:a + 7] + dual_dark(head[a + 7:b]) + THEME_CSS + head[b:]
    rest = page[h:].replace(_BACK, THEME_BTN + _BACK, 1)
    return head + THEME_HEAD + rest
