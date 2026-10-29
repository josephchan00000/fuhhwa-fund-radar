"""知識庫 wiki/ 的目錄與 CLAUDE.md 切點（規劃 docs/llm_wiki_plan.md）。

歷史：第一段（2026-10-29）把 CLAUDE.md 逐字切成各頁；第二、三段把每一頁整理過；
第五段（2026-10-29）CLAUDE.md 瘦身，只留鐵則與五個指令（瘦身前全文 `git show d6ed51029:CLAUDE.md`）。

現在這支只做兩件事：
  · 產目錄 wiki/index.md（標題與摘要讀各頁第 1、3 行；頁的清單與順序看 PAGES、EXTRA）；
  · CUTS＝CLAUDE.md 還留著的段落「某一行開頭 → 對應哪一頁」（None＝只在 CLAUDE.md：開頭、知識庫用法、鐵則）。
    scripts/wiki_facts.py 用它檢查：CLAUDE.md 那幾段的事實記號，對應的頁上都要有（MIRROR＝有對應段落的頁）。
    其他頁就是正本，CLAUDE.md 沒有對應段落。

用法：
  python3 scripts/wiki_split.py          # 重產目錄＋檢查
  python3 scripts/wiki_split.py --check  # 只檢查，不寫檔；有錯時 exit 1
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "CLAUDE.md"
WIKI = ROOT / "wiki"

GROUPS = [
    ("ops", "每天的作業"),
    ("env", "環境與限制"),
    ("main", "主儀表板（復華雷達）"),
    ("lab", "籌碼雷達與研究"),
]

# 頁：(標題, 一句話摘要)；目錄的標題與摘要以頁面自己的第 1、3 行為準，這裡是頁的清單與排序（摘要只是備用）
PAGES = {
    "ops/daily-update": ("「全部更新」每日 SOP",
                         "效率原則、產提示包、合規掃描與 QA、重建驗證、commit、CI 單一 commit、步驟 9 驗證線上內容（含 9⑤～9⑨）。"),
    "ops/news-rules": ("新聞報告規則（全部更新步驟 2）",
                       "週末時窗、三報守備範圍、來源、經濟日報頭條、查證字句、籌碼讀落檔、深度與漲跌分析、選題、速覽文風、卡片可讀性、粗體標籤、子代理回傳。"),
    "ops/deploy": ("部署與「線上沒更新」",
                   "內容在 main 不等於線上已部署、Deploy Hook、診斷順序、Vercel 部署上限、多人化硬化、快取。"),
    "ops/etf-weekly-scan": ("指令「ETF 募集週掃」",
                            "每週一主動盤點新 ETF、與每日缺口處理的分工、指數審核維護。"),
    "ops/strategy-scouting": ("指令「策略探勘週報」",
                              "每週日找新策略、先寫規格與程式再回測、等合併通道結果、使用者的決定。"),
    "ops/wiki-maintenance": ("指令「整理知識庫」",
                             "使用者打「整理知識庫」才全面檢查：體檢、事實比對、找矛盾與過時、修好、日誌一行、回報；平常做完事只改相關的那一頁。"),
    "ops/routines": ("排程與「排程搬家」",
                     "六個排程、搬家步驟、prompt 原文、為什麼火進主會話、模型要重設。"),
    "ops/schedule": ("每日時點地圖與 cron",
                     "盤後刷新、GitHub cron 遲到、當日完整性看門狗、每日時點地圖、備援。"),
    "ops/ci-budget": ("GitHub Actions 額度",
                      "實測用量、四個省分鐘的修法、repo 公開之後。"),
    "ops/content-rules": ("內容鐵則：新聞來源黑名單與禁用詞",
                          "禁用詞清單與「目標價」的兩個例外。"),
    "env/git-history": ("2026-10-16 改寫 git 歷史（隱私）",
                        "作者欄換成 noreply、舊分支封存、PR 參照；本頁開頭也是「已知環境限制與防呆」段的標題。"),
    "env/container": ("容器的限制",
                      "時區、被擋的站與空轉、check_numbers 洗檔、git add 寫明路徑。"),
    "env/mcp-approval": ("排程會話 MCP 審批（-32003）",
                         "send_later 被擋的原因、settings.json 預先核准、背景迴圈備援。"),
    "main/news-cards": ("新聞卡",
                        "詳細分析消失的根因（粗體標籤）、卡片排序、做過又拿掉的保底要點卡。"),
    "main/fund-news": ("復華新聞與社群",
                       "Google News 洗日期、ezfunds、品質重規劃、強基金、YouTube 三層清單、PTT、日文影片。"),
    "main/holdings-intro": ("持股簡介補齊",
                            "前十大簡介一再漏掉的根因、三道防呆、補簡介格式。"),
    "main/print": ("列印版／存 PDF",
                   "獨立列印樹、五組重點、分頁規則、驗證方法、踩過的坑。"),
    "main/calendar": ("行事曆與資料可信度",
                      "台灣區與精簡規則、台股法說財報、官方休市表與颱風、昨日版底稿與漂移閘門、核心排程錨。"),
    "main/freshness": ("資料更新時間區塊",
                       "版面、只列逾期、交易日口徑、不能拿來源名稱當 grep 標記。"),
    "main/macro-thermometer": ("市場溫度計（總經分頁）",
                               "全球與台股籌碼兩張表、外資淨空單凍結、證交所盤後修正、資料層鐵則。"),
    "main/etf-watch": ("ETF 數據追蹤表",
                       "追蹤清單、雙來源、報酬與配息、預估配息、欄序、落檔與欄位級合併。"),
    "main/etf-upcoming": ("即將登場與新 ETF 自動發現",
                          "掛牌自動加入追蹤、上櫃檔分組、五狀態三分組、發現層、not_tracked、募集表格解析、併檔通道。"),
    "main/etf-daily-change": ("ETF 當日漲跌的坑",
                              "差一天並排、官方表與前收備案、假 bar、上櫃慢一天、週月報酬錨定、今天對前天、除息日。"),
    "main/etf-detail": ("ETF 詳情卡畫面",
                        "列高、卡片與泡泡、方塊圖、異動與持股表、產業別、本機截圖驗版、表格排序。"),
    "main/etf-holdings": ("ETF 持股資料",
                          "貢獻與報價日、假無異動、假全部出清、彙整站雙源、本家第一手、第三方探針、期貨部位。"),
    "main/fund-returns": ("基金多期報酬",
                          "鉅亨每日基準覆蓋層、自建 NAV 序列算 1 週／1 月。"),
    "lab/overview": ("籌碼雷達總覽",
                     "入口、x9.html 兩種身分、模組、建頁接在哪裡、workflow 要裝 numpy。"),
    "lab/chip-data": ("籌碼雷達資料層",
                      "data/lab 分片、帳本口徑、官方端點坑、擴充 ETF、Yahoo 歷史價量備援。"),
    "lab/chip-strategy": ("籌碼雷達的訊號與第一代策略",
                          "8 個訊號與成績單、紙上交易規則、S1 等策略、策略頁 v2、持有期差一天的坑。"),
    "lab/index-changes": ("指數調整",
                          "臺灣50 與高股息的審核時程、公告前預測、被動 ETF 動向。"),
    "lab/tw50": ("臺灣50 換股研究與提前卡位",
                 "研究結論、歸因、提前 25 日買 4 檔、兩個版本、前瞻流程。"),
    "lab/high-dividend": ("高股息換股研究",
                          "四檔名單與買賣期間、預估名單、價格口徑、被動買盤大小、依編製規則提前卡位。"),
    "lab/strategy-pack": ("資料包策略測試與回測紀律",
                          "P1～P6、存活者偏誤、成本加倍與參數鄰近、成交檢查、效能。"),
    "lab/backtest-v3": ("回測方法 v3",
                        "比較基準、大型與中型、評級條件、資料、模組、結果、踩過的坑、頁面。"),
    "lab/chip-ui": ("籌碼雷達介面改版歷史",
                    "版面 v3、版面 v4（機會｜策略｜個股｜籌碼｜指數＋後台）、後台自我驗證、2026-10-14 介面。"),
    "lab/trades": ("逐筆交易",
                   "頁面、資料流、緊湊陣列、當時價格換算、核對時修正的回測資料問題。"),
    "lab/selfopt": ("策略健檢與自我改良",
                    "影子版本、事前寫定的候選、每天體檢、每週重跑、不變式。"),
    "lab/company": ("公司分析與飆股研究",
                    "點進去才算的公司卡、財報資料、飆股規則（superx）與結果。"),
    "lab/superstock": ("《超級績效》SEPA 與飆股名單研究",
                       "S01、綜合最優解、W1～W6 名單研究、W9 照書選股的結論。"),
    "lab/forecast": ("法人預估與產業比較",
                     "FactSet 與 Yahoo 資料、目標價的用字例外、產業比較、頁面。"),
    "lab/growth-s5": ("長線投信動能成長股（S5）",
                      "四關、回測、出場教訓。"),
    "lab/heat-tw": ("台股景氣溫度頁",
                    "各版本規格、計算、資料來源、驗證結果、踩過的坑。"),
    "lab/heat-us": ("美股景氣頁",
                    "四個指數、規格、泡沫模型、資料、各指數自己的情緒籌碼。"),
    "lab/bubble": ("泡沫（市場層級）",
                   "VER 1～4 的等級條件、規格、程式、頁面、結果。"),
    "lab/bubble-industry": ("產業泡沫",
                            "台股產業、美股類股與細產業、已下市公司的產業別、台股細分族群。"),
    "lab/crash-cards": ("大跌相關研究卡",
                        "短線大跌風險、過熱後 3 個月回撤、反向檢查、大跌後檢查、部位參考（做了又拿掉）。"),
    "lab/practical": ("實戰模擬、研究結論、期貨加碼",
                      "照網頁操作能不能比一直抱著好、研究結論的問答、200 日線上才加碼。"),
    "lab/core-plan": ("交易計畫（長抱＋機動）",
                      "corespec VER 1～4、兩期重疊重複計算的修正、計算、結果、頁面。"),
    "lab/us-qm": ("美股個股策略與美股強勢品質股",
                  "美股資料、三條個股策略、美股飆股研究、強勢品質股 VER 3～8。"),
    "lab/boom-live": ("飆股修正與新飆股前瞻記錄",
                      "W7、W8、前瞻記錄 VER 1～4（接手、N8）。"),
    "lab/fut": ("台指期早盤策略（股票期貨人生）",
                "估算開盤的想法、規格 VER 1～2、資料、盤前取樣、結果、頁面。"),
    "lab/rare": ("少見但勝率高的策略",
                 "九條規則、結果、上線與觸發前提醒。"),
    "lab/signals": ("訊號總覽（一）：基本規則與頁面",
                    "sigspec VER 1～3、6：判定、訊號清單、計算、頁面、景氣頁瘦身、指標頁、警示改看最大回撤、法人買賣超。"),
    "lab/signals-versions": ("訊號總覽（二）：後續版本",
                             "VER 4～5、9～24：情境、進場後報酬、打亂測試、溫度計、預估之後、盤查、每一天一樣重、最差一次。"),
    "lab/pick-page": ("選股頁",
                      "台股｜美股｜個股、進場行事曆、策略卡、新飆股卡 v2、行事曆 v2。"),
    "lab/cfg-research": ("配置頁（已改成選股頁）與研究紀錄",
                         "x9.html 兩種身分、配置頁 v1／v2、美股個股卡、全部策略表、研究紀錄頁。"),
    "lab/market-page": ("市場頁",
                        "四塊版面、全部指標、泡沫與產業泡沫、轉址、美股點到才下載。"),
    "lab/plain-words": ("主頁面用字",
                        "不能出現的詞、比較的寫法、test_plain 怎麼掃。"),
    "lab/nav": ("導覽與入口",
                "頂欄、名詞、查公司、記住上次位置、舊網址、整站建頁的測試夾具。"),
    "lab/candidates": ("新策略候選",
                       "規格＋程式、三種引擎、用到未來資料的檢查、放進計畫試算、合併通道、使用者的決定。"),
    "lab/strategy-pages": ("總經策略／個股策略頁",
                           "一份頁面兩種身分、網址、說明卡、時間軸共用、x9x 轉址。"),
    "lab/expert": ("總經策略（原大神策略）",
                   "xstratspec VER 1～6：短線、落底、季節性、風險控制、融資維持率、判定。"),
    "lab/heat-viz": ("景氣頁與個股頁的視覺化",
                     "雷達、比較日期、溫度計、這週變化、階段時間軸、證據地圖、3D 地形、日夜間按鈕、個股頁三張圖。"),
}

# (CLAUDE.md 某一行的開頭, 從這一行起對應哪一頁)；照檔案順序，第一個必須是第 1 行。None＝只在 CLAUDE.md。
CUTS = [
    ("# CLAUDE.md — 復華基金雷達", None),
    ("## 指令：「全部更新」／「資料更新」", "ops/daily-update"),
    ("2. **上網查證產新聞內容**", "ops/news-rules"),
    ("3. **合規掃描＋內容 QA＋數字核對**", "ops/daily-update"),
    ("   - ⚠️ **「內容在 main」≠「線上已部署」", "ops/deploy"),
    ("   - **⑤ 前十大簡介缺口", "ops/daily-update"),
    ("## 指令：「ETF 募集週掃」", "ops/etf-weekly-scan"),
    ("## 指令：「策略探勘週報」", "ops/strategy-scouting"),
    ("## 指令：「整理知識庫」", "ops/wiki-maintenance"),
    ("## 指令：「排程搬家」", "ops/routines"),
    ("## 已知環境限制與防呆", "env/mcp-approval"),
]
MIRROR: set[str] = {p for _, p in CUTS if p}

# 第二段起新寫的頁：(標題, 一句話摘要)；沒有「/」的放在目錄的「跨主題」，
# 「某頁-子題」排在那一頁後面。目錄的標題與摘要以頁面自己的第 1、3 行為準（這裡只是備用）。
EXTRA: dict[str, tuple[str, str]] = {
    "user": ("使用者偏好與做決定的方式", "他要什麼、怎麼判斷好壞、畫面與用字的要求、怎麼一起做事；每條附原話與日期。"),
    "lessons": ("跨主題的教訓", "踩過不只一次、換個地方還會再踩的事；一條一句，細節連到出處頁。"),
    "lab/signals-versions-early": ("訊號總覽：版本紀錄 VER 1～16", "從 lab/signals-versions 拆出來的早期版本紀錄。"),
}


def cut(text: str) -> list[tuple[int, int, str | None]]:
    """回 [(起行, 迄行, 頁)]（行號從 1 起、含迄行），照檔案順序、涵蓋每一行恰好一次。"""
    lines = text.split("\n")
    starts = []
    for anchor, page in CUTS:
        hit = [i for i, s in enumerate(lines) if s.startswith(anchor)]
        if len(hit) != 1:
            raise ValueError(f"切點「{anchor}」在 CLAUDE.md 找到 {len(hit)} 行（要剛好 1 行）")
        if page is not None and page not in PAGES:
            raise ValueError(f"切點「{anchor}」指到沒有定義的頁 {page}")
        starts.append((hit[0], page))
    if [s for s, _ in starts] != sorted(s for s, _ in starts):
        raise ValueError("CUTS 的順序和 CLAUDE.md 不一致")
    if starts[0][0] != 0:
        raise ValueError("第一個切點必須是 CLAUDE.md 第 1 行")
    out = []
    for k, (s, page) in enumerate(starts):
        e = starts[k + 1][0] - 1 if k + 1 < len(starts) else len(lines) - 1
        out.append((s + 1, e + 1, page))
    return out


def head(page: str, fallback: tuple[str, str]) -> tuple[str, str]:
    """標題、摘要讀頁面自己的第 1、3 行；讀不到用 PAGES／EXTRA 的備用值。"""
    f = WIKI / f"{page}.md"
    if f.exists():
        t = f.read_text("utf-8").split("\n")
        if len(t) > 2 and t[0].startswith("# ") and t[2].startswith("> "):
            # 摘要裡的連結是相對那一頁的，放進目錄會斷：只留連結文字
            return t[0][2:].strip(), re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t[2][2:].strip())
    return fallback


def index() -> str:
    rows = [
        "# 知識庫目錄",
        "",
        "> 復華基金雷達的知識庫（做法照 Karpathy 的 LLM Wiki）：先看這份目錄，再讀相關的頁；做完事更新那一頁，[日誌](log.md) 加一行。"
        "下面的連結都相對於 `wiki/`。",
        "> 規劃：`docs/llm_wiki_plan.md`。2026-10-29 起頁面就是正本；CLAUDE.md 只留鐵則與五個指令，"
        "指令在 `wiki/ops/` 的整理版要和 CLAUDE.md 一致（`python3 scripts/wiki_facts.py` 會檢查）。",
        "",
    ]
    allp = {**PAGES, **EXTRA}

    def row(page: str) -> str:
        title, summary = head(page, allp[page])
        return f"- [{title}]({page}.md)：{summary}"

    tops = [p for p in EXTRA if "/" not in p]
    if tops:
        rows += ["## 跨主題", ""] + [row(p) for p in tops] + [""]
    subs = {p for p in EXTRA if "/" in p and any(p.startswith(q + "-") for q in PAGES)}
    for key, name in GROUPS:
        rows += [f"## {name}（{key}）", ""]
        for page in PAGES:
            if page.split("/")[0] != key:
                continue
            rows.append(row(page))
            rows += [row(q) for q in EXTRA if q in subs and q.startswith(page + "-")]
        rows += [row(q) for q in EXTRA if q.split("/")[0] == key and "/" in q and q not in subs]
        rows.append("")
    rows += [
        "## 原始資料（不在知識庫裡，頁面會連過去）",
        "",
        "- `docs/*_plan.md`：每個功能的規劃、使用者的決定、結果。",
        "- `docs/prompt_audit/`：2026-09-24 prompt 稽核。",
        "- `tw-superstock-lab/`：飆股研究（自己的 CLAUDE.md、PROGRESS.md、reports/）。",
        "- `reports/`：每天的新聞報告；`data/`：資料與研究檔。",
        "",
    ]
    return "\n".join(rows)


def check(text: str) -> list[str]:
    errs = []
    try:
        cut(text)
    except ValueError as e:
        errs.append(str(e))
    idx = WIKI / "index.md"
    if not idx.exists() or idx.read_text("utf-8") != index():
        errs.append("wiki/index.md 不是最新的")
    known = {"index.md", "log.md"} | {f"{p}.md" for p in {**PAGES, **EXTRA}}
    for name in sorted(known - {"index.md", "log.md"}):
        if not (WIKI / name).exists():
            errs.append(f"wiki/{name} 不存在（PAGES／EXTRA 有列）")
    for f in sorted(WIKI.rglob("*.md")):
        rel = f.relative_to(WIKI).as_posix()
        if rel not in known:
            errs.append(f"wiki/{rel} 不在 PAGES／EXTRA 裡（目錄沒有列）")
    return errs


def main(argv: list[str]) -> int:
    text = SRC.read_text("utf-8")
    if "--check" not in argv:
        idx = WIKI / "index.md"
        txt = index()
        if not idx.exists() or idx.read_text("utf-8") != txt:
            idx.write_text(txt, "utf-8")
    errs = check(text)
    for e in errs:
        print("✗", e)
    if errs and "--check" in argv:
        print("→ 跑 `python3 scripts/wiki_split.py` 重產目錄")
    print(f"{'✗' if errs else '✓'} 知識庫目錄與切點：{len(PAGES) + len(EXTRA)} 頁，CLAUDE.md 留著的段落對應 {len(MIRROR)} 頁")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
