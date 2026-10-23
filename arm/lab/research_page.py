"""研究紀錄頁 dashboard/x9r.html（docs/lab_ia_v5_plan.md 第 7 節；不在頂欄，配置頁、市場頁頁尾「研究紀錄」小字進）。

使用者 2026-10-23（Q3 選 A）：搬走的研究與驗證內容「全部搬到不在頂欄的研究紀錄頁，不刪」。
- 配置與策略：個股策略、總經策略、後台、名詞的資料都內嵌在 x9.html（約 1MB），所以它們留在 x9.html 的「研究紀錄」身分
  （?v=opp／st／mac／macst／bo），這頁只列入口（第 1 段）。
- 景氣：證據地圖、完整數字與方法、階段時間軸、熱度地形的資料都在市場頁（x9m／x9mu），留在市場頁的研究畫面（#v=research／phase／terrain），
  這頁只列入口（第 2 段）。
- 訊號（原本訊號總覽的研究結論、完整研究表、全部指標、名詞與判定方式）與泡沫（原本泡沫頁的全部內容）直接放在這頁（第 2 段）。
用字不受主頁面的規則限制（第 8 節：讀這頁的人是要查證的人）。輸出決定性（沒有時戳），內容沒變不改寫。
"""
from __future__ import annotations

import html
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dashboard" / "x9r.html"

# (段落 id, 標題, 說明, [(名稱, 網址, 一句這裡有什麼)])
GROUPS = (
    ("cfg", "配置與策略", "配置頁（台股、美股、策略）每一條規則的來歷：每一期的名單、過去每一筆、評級與判定、上線後的檢查。", (
        ("個股策略・這一期", "x9.html?v=opp", "推薦順序、時間表、每條個股策略這一期的名單與下一批、飆股、高股息換股避開清單、部位上限"),
        ("個股策略・規則與成績", "x9.html?v=st", "比較表；每條策略的結論、怎麼做、逐年報酬與 1 元變多少、逐筆交易（可下載）、風險"),
        ("總經策略・這一期", "x9.html?v=mac", "五個市場的指數型策略（RSI(2)、VIX 衝刺、Coppock、200 日均線…）：要動作的、持有中的、下一次排定"),
        ("總經策略・規則與成績", "x9.html?v=macst", "每條的規則與出處、逐年報酬、1 元變多少、逐筆交易、風險、判定依據與參數鄰近"),
        ("後台・今天的驗證", "x9.html?v=bo&at=bo-today", "每天建頁時的自我驗證事件、06:35 推播會帶的兩行"),
        ("後台・前瞻紀錄", "x9.html?v=bo&at=bo-fwd", "每條策略起算日之後照規則做的成績：已出場、持有中、同期大盤、比同一批股票"),
        ("後台・策略健檢與改良", "x9.html?v=bo&at=bo-hl", "前瞻和回測比偏離多少（燈號）、每週一重跑的執行細節候選與影子版本"),
        ("後台・評級規則與評級總表", "x9.html?v=bo&at=val-grade", "回測方法 v3 的 A／B／C 評級：樣本內外選股、報酬型態、穩健度三項"),
        ("後台・全部策略總表", "x9.html?v=bo&at=val-bt3", "回測方法 v3 跑過的每一個版本（前 5 檔與整組、大型與中型）"),
        ("後台・訊號成績", "x9.html?v=bo&at=bo-sig", "籌碼雷達 8 種個股訊號照做的實際報酬（持有 5／20 天、同期大盤）"),
        ("後台・換股研究", "x9.html?v=bo&at=idx-study", "臺灣50 與高股息 ETF 換股的事件研究、被動買盤大小、提前卡位回測"),
        ("後台・每日更新時程", "x9.html?v=bo&at=bo-sched", "每一班自動更新做什麼、幾點"),
    )),
    ("mkt", "景氣", "台股、美股景氣（市場頁）的研究畫面：資料都在市場頁，打開後最上面一列可以在三個研究畫面之間切換、回到市場頁。", (
        ("台股・證據地圖與完整數字", "x9m.html#v=research", "各項和台股的關係、Granger、邊際變化的多層回歸、五區回測、事件表現、資料來源"),
        ("台股・階段時間軸", "x9m.html#v=phase", "每個面向每一週在哪個階段（熱還在升溫、熱開始降溫、冷還在降溫、冷開始回溫）"),
        ("台股・熱度地形", "x9m.html#v=terrain", "五個面向的熱度山脊、過熱山頂、過冷谷底與大跌期間"),
        ("美股・證據地圖與完整數字", "x9mu.html#ix=spx&v=research", "四個指數同一套（打開後上方切換指數）：各項和指數的關係、邊際變化、五區回測、資料來源"),
        ("美股・階段時間軸", "x9mu.html#ix=spx&v=phase", "同上，美股四個指數"),
        ("美股・熱度地形", "x9mu.html#ix=spx&v=terrain", "同上，美股四個指數"),
    )),
    ("sig", "訊號", "原本訊號總覽的研究，放在這一頁下面：研究結論、完整研究表、全部指標（五個市場＋個股訊號＋策略）、名詞與判定方式。", (
        ("研究結論", "#research", "每個市場 8 個研究過的問題：照網頁調整持股、期貨加碼、籌碼過熱、剛進入過熱、跌破季線、落底訊號、容易急跌的指標、好訊號之後還準嗎"),
        ("完整研究表", "#rfull", "實測區細節（8 種用法的每週走勢與逐年成績）、短線大跌風險、大跌後檢查、過熱後回撤、反向檢查四張研究卡"),
        ("全部指標", "#all", "每一個指標、每一種訊號過去出現之後的結果與每一次的清單；市場頁只列自己的市場，這裡另有個股訊號與策略"),
        ("名詞與判定方式", "#mth", "★／◆／○ 怎麼判、運氣會產生幾個、預估之後（逐年檢查留下的比例）、市場頁今天的訊號怎麼列、溫度計怎麼讀"),
    )),
    ("bub", "泡沫", "原本泡沫頁的全部內容，放在這一頁下面；市場頁最下面只留等級、條件與產業。", (
        ("五個市場的泡沫等級", "#bub-lv", "每個市場一張卡：一句話、歷史等級、現在的七個條件與兩年拆解、等級 ≥ 3 的泡沫段、成立之後比較容易大跌嗎"),
        ("產業泡沫", "#bub-ind", "台股產業與細分族群、美股類股與 49 細產業的條件、說明與驗證"),
        ("七種條件代表什麼", "#bub-types", "價格爆發、兩年翻倍、偏離趨勢、漲得比基本面快、估值、未來獲利、槓桿的出處與限制"),
        ("方法與資料", "#bub-mth", "分級規則、PSY 臨界值、價格 ÷ 基本面、未來獲利、資料來源"),
    )),
    ("gl", "名詞", "市場頁（今天的訊號、溫度計、任一天…）與配置頁個股工具（真加碼、申贖倍率、超配、成本乖離…）的名詞與方法。", (
        ("名詞與判定方式（市場頁、訊號）", "#mth", "今天的訊號怎麼列、溫度計怎麼讀、任一天、★／◆／○ 怎麼判、預估之後"),
        ("名詞與方法（個股工具）", "x9.html?v=bo#gl", "ETF 部位帳本、時點、公司行動、法人成本的算法與資料來源"),
    )),
)


def _e(x) -> str:
    return html.escape(str(x if x is not None else ""))


def body(host: dict | None = None) -> str:
    """目錄＋每一組的入口；host＝{段落 id: 放在這頁的內容}（訊號、泡沫）。"""
    host = host or {}
    toc = "".join(f'<a href="#{gid}">{_e(t)}</a>' for gid, t, _, _ in GROUPS)
    out = [f'<nav class="rtoc" aria-label="目錄">{toc}</nav>']
    for gid, title, note, items in GROUPS:
        li = "".join(f'<li><a href="{_e(u)}">{_e(n)}</a><span>{_e(d)}</span></li>' for n, u, d in items)
        out.append(f'<section class="rsec" id="{gid}"><h2>{_e(title)}</h2><p class="rnote">{_e(note)}</p><ul class="rlist">{li}</ul></section>')
        if host.get(gid):
            out.append(f'<div class="rhost" data-g="{gid}">{host[gid]}</div>')
    return "".join(out)


def sig_view() -> dict:
    """訊號研究的 view：同一個程序裡 sigpage.build() 算好的（LAST），沒有就自己算（慢，約 1 分鐘）。"""
    from . import sigpage as SPG
    return SPG.LAST.get("V") or SPG.view()


def bub_view() -> dict:
    """泡沫研究的 view：沿用景氣頁算好的等級（bubble.last）與市場頁算好的產業（bubpage.industries）。"""
    from . import bubpage as BPG
    return BPG.view()


def render(SV: dict | None = None, BV: dict | None = None) -> str:
    """SV＝訊號研究的 view（sigpage.view）、BV＝泡沫研究的 view（bubpage.view）；不給就照上面兩個函式取得。"""
    from . import appnav
    from . import bubindpage as IP
    from . import bubpage as BPG
    from . import sigpage as SPG
    from .heatpage import _CSS as HCSS
    SV = sig_view() if SV is None else SV
    BV = bub_view() if BV is None else BV
    has_sig = bool(SV.get("rows"))
    host = {"sig": SPG.research_body(SV), "bub": BPG.research_body(BV)}
    css = HCSS + appnav.CSS + SPG.research_css() + BPG.research_css() + CSS
    js = (SPG.JS if has_sig else "") + BPG.JS + IP.JS
    return appnav.finish(_HTML.replace("{{APPTAB}}", appnav.bar("r")).replace("{{CSS}}", css)
                         .replace("{{BODY}}", body(host)).replace("{{PANEL}}", SPG.PANEL if has_sig else "")
                         .replace("{{SGD}}", f'<script type="application/json" id="sgd">{SPG.page_json(SV)}</script>' if has_sig else "")
                         .replace("{{BUBD}}", BPG.research_data(BV)).replace("{{JS}}", js))


def build(out: Path = OUT, SV: dict | None = None, BV: dict | None = None) -> bool:
    text = render(SV, BV)
    if out.exists() and out.read_text(encoding="utf-8") == text:
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return True


_HTML = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<link rel="icon" href="data:,">
<title>研究紀錄</title>
<style>{{CSS}}</style></head>
<body>
<div class="top">{{APPTAB}}<a class="back" href="./"><span class="bk1">返回</span>主頁</a></div>
<main class="rpm"><h1>研究紀錄</h1>
<p class="rlead">驗證、方法、研究表，以及原本的策略頁、訊號總覽、泡沫頁、後台都在這裡。主頁面（市場、配置）只放結論和要做的事；
要查一個數字怎麼來的、一條規則過去的每一筆，從這裡進去。</p>
{{BODY}}</main>{{PANEL}}
{{SGD}}
<script type="application/json" id="bubd">{{BUBD}}</script>
<script>{{JS}}</script>
</body></html>
"""

CSS = """
.rpm{max-width:1080px;margin:0 auto;padding:10px 16px 60px}
.rpm h1{font-size:22px;margin:8px 0 6px}
.rhost{margin:6px 0 0}.rhost>.sec{padding-left:0;padding-right:0}
.rlead{font-size:14px;line-height:1.75;color:var(--ink2);margin:0 0 12px}
.rtoc{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:14px;margin:0 0 6px}
.rsec{margin-top:22px}.rsec h2{font-size:17px;margin:0 0 4px}
.rnote{font-size:13px;color:var(--mut);margin:0 0 8px;line-height:1.6}
.rlist{list-style:none;margin:0;padding:0;border-top:1px solid var(--line)}
.rlist li{display:grid;grid-template-columns:minmax(12em,15em) minmax(0,1fr);gap:4px 14px;padding:9px 2px;border-bottom:1px solid var(--line);font-size:14px;line-height:1.6}
.rlist li a{font-weight:600}.rlist li span{color:var(--ink2);font-size:13px}
@media (max-width:640px){.rlist li{grid-template-columns:1fr;gap:0}.rpm{padding:8px 16px 50px}}
"""
