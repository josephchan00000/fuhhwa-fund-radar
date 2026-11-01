"""景氣溫度與籌碼雷達共用的頂欄（2026-10-18 使用者：點主頁的「·」先到景氣頁、個股頁放旁邊；不要窄欄）。

台股景氣（x9m.html）、美股景氣（x9mu.html）、泡沫（x9b.html）、個股（x9.html，籌碼雷達）四頁的頂欄是同一組主分頁，右邊「返回主頁」。
泡沫頁 2026-10-18 起獨立（docs/lab_risk_plan.md 第 7 節：使用者「泡沫單獨拉出來、自己一個頁面不要混淆」）。
訊號總覽（x9o.html）2026-10-19 加入（docs/lab_signal_plan.md：「有一個地方是訊號總覽，所有訊號跟所有的策略妥善分類」）。
大神策略（x9x.html）2026-10-21 加入（docs/lab_nav_plan.md：使用者「大神策略是放在訊號那邊而已嗎？這樣很難找」）；
2026-10-22 改成「策略」（docs/lab_strategy_ia_plan.md：「策略點進去，分成總經策略跟個股策略」）：策略與個股是同一頁 x9.html 的兩種身分，
策略＝x9.html#v=mac（頁面載入後依網址換身分、亮頂欄的「策略」）；x9x.html 留成轉址頁。
2026-10-23 起策略與個股合成「配置」（docs/lab_ia_v5_plan.md 第 18 節：台股｜美股｜策略｜個股（工具）），頂欄一格、連 x9.html；
原本的總經策略、個股策略、後台改從不在頂欄的研究紀錄頁（x9r.html）進去（還是 x9.html 裡的分頁）。
2026-10-23 第 2 段（市場頁改版）：泡沫頁、訊號總覽併進兩個景氣頁（市場頁），頂欄拿掉這兩格（x9b.html、x9o.html 留成轉址頁）。
2026-10-23 第 4 段（docs/lab_ia_v5_plan.md 第 2、22 節，照核准過的示意圖）：頂欄只剩「市場｜配置」兩格，右邊小字「研究紀錄・名詞・查公司」，
再來是深淺色鈕與返回主頁；原本擠在頂欄的「資料到…」移到各區塊（市場頁的面向標題、選股頁個股工具那一列）。
2026-10-28（docs/lab_pick_page_plan.md）：「配置」拿掉、改成「選股」（x9.html：台股｜美股｜個股），原本的配置搬到研究紀錄。
- 市場＝台股 x9m.html、美股四個指數 x9mu.html（第二排切換）；選股＝x9.html。研究紀錄頁（x9r.html）兩格都不亮。
- 兩格各記住上次看到哪裡（這台瀏覽器的 localStorage "labLast"）：從選股點「市場」回到上次看的市場、從市場點「選股」回到上次看的選股分頁；
  沒有紀錄（或瀏覽器擋 localStorage）就是台股、選股台股。只記看得到的位置（市場與指數、選股的台股｜美股｜個股工具），不記個股卡與研究紀錄。
- 名詞：市場頁＝研究紀錄頁的「名詞與判定方式」、選股頁＝頁內的名詞面板、研究紀錄頁＝這一頁的名詞段。
  查公司：選股頁＝頂欄打開搜尋框；其他頁＝到選股頁打開搜尋框（x9.html#q）。
- 手機（640px 以下）：深淺色鈕只留圖示、返回主頁寫「主頁」，360px 以上一列放得下兩格＋小字＋兩顆鈕；更窄的（320px）小字換到第二列靠右。
"""
from __future__ import annotations

TABS = (("mkt", "市場", "x9m.html"), ("pick", "選股", "x9.html"))
LAST_KEY = "labLast"

CSS = (".top{align-items:center}"
       ".apptab{display:flex;gap:2px;background:var(--card2);border-radius:10px;padding:3px;align-self:center}"
       ".apptab a{padding:5px 14px;border-radius:8px;font-size:14.5px;font-weight:600;color:var(--ink2);"
       "text-decoration:none;white-space:nowrap}"
       ".apptab a:hover{color:var(--ink)}"
       ".apptab a.on{background:var(--bg);color:var(--ink);box-shadow:0 1px 3px rgba(20,30,50,.14)}"
       ".applk{display:flex;align-items:center;margin-left:auto;position:relative;font-size:12.5px;color:var(--mut);white-space:nowrap}"
       ".applk>a{color:var(--mut);text-decoration:none;padding:5px 3px;border-radius:6px}"
       ".applk>a:hover{color:var(--ink)}.applk>a[aria-current]{color:var(--ink);font-weight:600}"
       ".applk>a:focus-visible{outline:2px solid var(--acc);outline-offset:0}"
       ".applk .als{padding:0 1px}"
       ".top>.back{align-self:center}"
       "@media (max-width:640px){.top{gap:6px}.apptab a{padding:5px 10px;font-size:14px}.applk{font-size:12px}.applk>a{padding:5px 2px}"
       ".top .thm{padding:4px 7px}.top .thm-t{display:none}.top .bk1{display:none}}"
       "@media (max-width:400px){.applk{font-size:11.5px}}"
       "@media (max-width:359px){.applk{order:5;flex-basis:100%;justify-content:flex-end;margin-left:0}.top .thm{margin-left:auto}}"
       # 計算核對不一致的紅字（valog.verify_note；finish 的 note）。紅框＋半透明紅底、字用頁面本身的顏色：
       # 深淺色都看得清楚，也不用 @media（finish 會改寫深色規則，這一段要能原樣出現在頁面裡）
       ".vfy{margin:10px max(16px,calc((100% - 1048px)/2)) 0;padding:8px 12px;border-radius:8px;border-left:4px solid #d33a34;"
       "background:rgba(211,58,52,.13);color:inherit;font-size:13.5px;line-height:1.6}")


def links(page: str = "", search: str = "") -> str:
    """頂欄右邊小字：研究紀錄・名詞・查公司（第 4 段；見本檔開頭）。page＝"mkt"／"pick"（選股頁 x9.html）／"r"（研究紀錄頁）；
    search＝選股頁的查公司搜尋框（copage.SEARCH_HTML），放在這一組裡、點「查公司」才打開。"""
    rec = '<a href="x9r.html"' + (' aria-current="page"' if page == "r" else "") + ">研究紀錄</a>"
    if page == "pick":
        gl = '<a href="#gl" class="glk">名詞</a>'
    elif page == "r":
        gl = '<a href="#gl">名詞</a>'
    else:
        gl = '<a href="x9r.html#mth">名詞</a>'
    if page == "pick" and search:
        co = '<a href="#q" class="coqb" role="button" aria-expanded="false" aria-controls="cos">查公司</a>' + search
    else:
        co = '<a href="x9.html#q">查公司</a>'
    sep = '<span class="als" aria-hidden="true">・</span>'
    return f'<nav class="applk" aria-label="研究紀錄、名詞、查公司">{rec}{sep}{gl}{sep}{co}</nav>'


def bar(page: str = "", cur: str = "", search: str = "") -> str:
    """頂欄：主分頁（市場｜選股；目前所在的加 class="on"、aria-current="page"）＋右邊小字。
    cur＝目前這一格連到哪裡（美股頁傳 x9mu.html；不給就是那一格的預設頁）。"""
    out = []
    for key, label, href in TABS:
        on = key == page
        attr = ' class="on" aria-current="page"' if on else ""
        out.append(f'<a{attr} data-k="{key}" href="{cur if on and cur else href}">{label}</a>')
    return '<nav class="apptab" aria-label="頁面">' + "".join(out) + "</nav>" + links(page, search)


# 兩格各記住上次看到哪裡（見本檔開頭）。<head> 裡定義 labLast(格, 位置)，美股頁換指數、選股頁換分頁時呼叫；
# 畫面出來後：亮的那一格＝現在的位置（紀錄不是這一頁的就記成這一頁，例如台股市場頁），沒亮的那一格改連到上次的位置。
# 位置只收這幾種寫法（其他一律不理），讀寫失敗就用預設。
NAV_HEAD = ('<script>(function(){var K="' + LAST_KEY + '",O={},'
            'OK={mkt:/^x9mu?\\.html(#ix=(spx|ixic|ndx|sox))?$/,pick:/^x9\\.html(\\?v=(us|stk|chip|idx))?$/};'
            'try{O=JSON.parse(localStorage.getItem(K)||"{}")||{}}catch(e){O={}}'
            'window.labLast=function(k,v){if(!OK[k]||!OK[k].test(v)||O[k]===v)return;O[k]=v;'
            'try{localStorage.setItem(K,JSON.stringify(O))}catch(e){}};'
            'document.addEventListener("DOMContentLoaded",function(){var a=document.querySelectorAll(".apptab a[data-k]");'
            'for(var i=0;i<a.length;i++){var k=a[i].getAttribute("data-k"),v=O[k],h=a[i].getAttribute("href")||"";'
            'if(a[i].classList.contains("on")){if(!v||v.indexOf(h)!==0)window.labLast(k,h)}'
            'else if(v&&OK[k]&&OK[k].test(v))a[i].setAttribute("href",v)}});'
            '})();</script>')


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

BACK = '<a class="back" href="./"><span class="bk1">返回</span>主頁</a>'


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


def finish(page: str, note: str = "") -> str:
    """頁面輸出前最後一步：<head> 的樣式改寫成可切換深淺色、加切換程式與「記住上次位置」的程式，頂欄「返回主頁」前面加按鈕；
    note（例 計算核對不一致的紅字，valog.page_note）放在頂欄下面。"""
    if note:
        page = page.replace(BACK + "</div>", BACK + "</div>" + note, 1)
    h = page.find("</head>")
    if h < 0:
        return page
    head = page[:h]
    a, b = head.find("<style>"), head.find("</style>")
    if a >= 0 and b > a:
        head = head[:a + 7] + dual_dark(head[a + 7:b]) + THEME_CSS + head[b:]
    rest = page[h:].replace(BACK, THEME_BTN + BACK, 1)
    return head + THEME_HEAD + NAV_HEAD + rest
