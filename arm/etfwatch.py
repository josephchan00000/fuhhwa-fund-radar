"""ETF 數據追蹤 —— 台股被動／主動 ETF 週績效追蹤（儀表板第四分頁「ETF」的資料層）。

追蹤兩組清單（2026-07-06 使用者以週報圖表指定；異動只改 WATCHLIST）：
  · 被動 ETF：高股息（0056/00878/00919/00929）＋市值型（0050/006208）
  · 主動式 ETF：00980A 等 11 檔台股主動 ETF（含本家 00991A 主動復華未來50）
欄位對齊週報：規模(億)／成立日期／過去一週報酬／過去一月報酬／配息殖利率／收益分配頻率。
配息殖利率＝年化配息率：最新公布一次的配息金額 ÷ 最新市價 × 配息頻率次數
（月配×12／季配×4／半年配×2／年配×1），非 trailingYield 近12月回溯值。

資料來源（雙源、各自獨立降級）：
  · 規模(AUM)／年化配息率／配息頻率 ← arm/connectors/etfinfo（Tier B 第三方彙整）。
  · 過去一週／一月報酬 ← 多來源、單檔單請求取密序列（Yahoo 還原收盤＝總報酬口徑，與逐檔可點
    連結同源 → FinMind → TWSE 官方，依序取第一個歷史足夠密者），以最新交易日收盤對回推
    7／30 日曆日之前最後交易日收盤計算。序列太稀疏會產生錯值（曾見 ret_1w==ret_1m），故加
    「基準日須接近目標日」防呆，寧缺勿錯（不足即退回底稿並標基準日）。

防呆（同專案鐵則）：
  · 雲端 Claude 容器的 proxy 會擋 etfinfo.tw 與 TWSE——抓不到就沿用既有落檔，
    GitHub Actions（不受 proxy 擋）每日自動補抓。
  · 逐檔「欄位級合併」，fallback 鏈：本次新值 → 既有落檔 → 內建 SEED_PERF 週報底稿；
    成立日期一律取 WATCHLIST 靜態值。本次抓不到的欄位保留既有值、絕不洗成空白／null；
    整批全空 → 不覆寫既有落檔（同 fundnews 2026-07-04 教訓）。
  · 報酬標 perf_asof 基準日、規模／殖利率標 as_of 抓取日，儀表板分別註記。
  · etfinfo 數字屬「先給可能值、上線前以投信官網核對」（Tier B）。

落檔 data/etf_watch.json；arm/fund_dashboard 以「ETF 數據追蹤」分頁呈現。
"""
from __future__ import annotations

import json
import math
import re
from datetime import date, timedelta
from pathlib import Path

from . import clock

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "etf_watch.json"

# (code, name, kind, cat, inception)：kind＝passive/active/other（other＝債券型主動式等，
# 儀表板獨立「其他」表——2026-07-21 使用者指示新增分類）；cat＝表內「性質」欄；
# inception＝成立日期（固定值，不會變、不需抓、永不空白——避免來源缺欄時整片留空）。
WATCHLIST: list[tuple[str, str, str, str, str]] = [
    ("0056",   "元大高股息",       "passive", "高股息", "2007/12/13"),
    ("00878",  "國泰永續高股息",   "passive", "高股息", "2020/07/10"),
    ("00919",  "群益台灣精選高息", "passive", "高股息", "2022/10/13"),
    ("00929",  "復華台灣科技優息", "passive", "高股息", "2023/06/01"),
    ("0050",   "元大台灣50",       "passive", "市值型", "2003/06/30"),
    ("006208", "富邦台灣50",       "passive", "市值型", "2012/06/22"),
    ("00980A", "主動野村臺灣優選", "active", "主動式", "2025/04/22"),
    ("00982A", "主動群益台灣強棒", "active", "主動式", "2025/05/13"),
    ("00981A", "主動統一台股增長", "active", "主動式", "2025/05/15"),
    ("00984A", "主動安聯台灣高息", "active", "主動式", "2025/07/03"),
    ("00985A", "主動野村台灣50",   "active", "主動式", "2025/07/08"),
    ("00991A", "主動復華未來50",   "active", "主動式", "2025/12/09"),
    ("00992A", "主動群益科技創新", "active", "主動式", "2025/12/16"),
    ("00987A", "主動台新優勢成長", "active", "主動式", "2025/12/16"),
    ("00994A", "主動第一金台股優", "active", "主動式", "2025/12/26"),
    ("00995A", "主動中信台灣卓越", "active", "主動式", "2026/01/13"),
    ("00993A", "主動安聯台灣",     "active", "主動式", "2026/01/20"),
    # 2026-07-06 加入熱門／新募集主動式 ETF（成立日期靜態值，經 WebSearch 逐檔查證投信官網／TWSE）：
    ("00988A", "主動統一全球創新", "active", "主動式", "2025/10/21"),  # 統一投信，年配，2026 規模衝上約 594 億
    ("00990A", "主動元大AI新經濟", "active", "主動式", "2025/12/22"),  # 元大投信，不配息，全球 AI 新經濟主題
    ("00403A", "主動統一台股升級50", "active", "主動式", "2026/04/28"),  # 統一投信，季配，募資破紀錄約 792 億
    ("00407A", "主動凱基台灣",     "active", "主動式", "2026/06/12"),  # 凱基投信，不配息，台灣首檔不配息主動台股 ETF
    # 2026-08-05 使用者指示補齊缺檔（WebSearch 逐檔查證工商時報／經濟日報／投信官網）：
    ("00404A", "主動聯博動能50",   "active", "主動式", "2026/05/28"),  # 聯博投信首檔台股主動，6/9 掛牌，季配（首配預計 9 月中）
    ("00405A", "主動富邦台灣龍耀", "active", "主動式", "2026/05/25"),  # 富邦投信首檔，6/9 掛牌，季配，募集 129.28 億
    ("00996A", "主動兆豐台灣豐收", "active", "主動式", "2026/03/16"),  # 兆豐投信，3/25 掛牌，季配（成立滿 180 日後首配）
    ("00410A", "主動永豐科技趨勢", "active", "主動式", "2026/08/03"),  # 永豐投信首檔，8/3 掛牌（成立日查無、暫用掛牌日——同 00986D 前例），半年配（首配 2027/3）
    # 2026-08-05 第二批補齊（使用者點名 00401A/00402A/00406A；掃名單再撿回 00400A/00408A/00999A。
    # 成立日查無者暫用掛牌日，同 00986D 前例）：
    ("00400A", "主動國泰動能高息", "active", "主動式", "2026/04/09"),  # 國泰投信，台股首檔月配主動式，4/9 掛牌（成立日暫用掛牌日）
    ("00401A", "主動摩根台灣鑫收", "active", "主動式", "2026/03/31"),  # 摩根投信首檔，成立 3/31、4/10 掛牌，月配（掩護性買權）
    ("00402A", "主動安聯美國科技", "active", "主動式", "2026/06/09"),  # 安聯第 3 檔，美國科技股，6/9 掛牌（成立日暫用掛牌日），年配
    ("00406A", "主動中信台灣收益", "active", "主動式", "2026/06/11"),  # 中國信託投信，6/11 掛牌（成立日暫用掛牌日），月配（掩護性買權，首配 0.128 除息 7/31）
    ("00408A", "主動第一金優股息", "active", "主動式", "2026/07/15"),  # 第一金投信，7/15 掛牌（成立日暫用掛牌日），季配（成立滿 60 日後）
    ("00999A", "主動野村臺灣高息", "active", "主動式", "2026/05/05"),  # 野村投信 3D 鎖息，5/5 掛牌（成立日暫用掛牌日），季配
    # 上櫃檔（2026-08-28 使用者指示：分組照投資型態走，「上櫃」不再另立「其他」組——
    # kind 一律填 active／passive，性質欄以「・上櫃」註記掛牌地。上櫃的技術差異
    # （etfinfo 未收錄 → 規模等欄靠種子＋序列回填；Yahoo 報酬 .TW→.TWO 自動退）與 kind 無關）：
    # · 2026-07-21 本家金融股債雙收傘型（工商時報 2026/4/15 掛牌報導＋復華官網 ETF24/25）：
    ("00998A", "主動復華金融股息", "active", "主動式股票・上櫃", "2026/03/31"),  # 全球金融股入息，季配（成立日 3/31、掛牌 4/15）
    ("00986D", "主動復華金融債息", "active", "主動式債券・上櫃", "2026/04/15"),  # 全球金融債入息，月配（成立日查無、暫用掛牌日 4/15）
    # · 2026-08-28 轉正：統一股債雙主動傘型（8/5~8/7 募集、8/26 櫃買掛牌）：
    ("00411A", "主動統一前沿科技", "active", "主動式股票・上櫃", "2026/08/11"),  # 全球前沿科技（AI 基建/機器人/自駕/太空/量子），年配；成立日 8/11（WebSearch 查證）
    ("00987D", "主動統一美國公債量化增益", "active", "主動式債券・上櫃", "2026/08/26"),  # 美債量化多空策略，季配；成立日查無、暫用掛牌日 8/26——同 00986D 前例
    # · 2026-09-03 轉正：本家復華全球未來50（8/12~8/14 募集、9/2 上市掛牌）：
    ("00409A", "主動復華全球未來50", "active", "主動式", "2026/09/02"),  # 全球 AI 產業贏家 50 檔（美日韓台），年配（TVBS＋股感兩來源一致，首次評價日每年 10 月底）；成立日查無、暫用掛牌日 9/2——同 00986D 前例
]

# 債券型追蹤檔（cat 含「債」）：收盤價 tick 小、日波動低，收盤值天然高度重複，
# 「髒序列」防呆（_is_degenerate 相異值 <60%）會誤殺合法序列（2026-07-22 踩坑：00986D
# 各源全被判髒 → 報酬整片空）→ 對這些檔放寬相異值門檻。
# 2026-08-05 改為函式：UPCOMING 自動升級的債券檔（cat 含「債」）也要吃得到放寬門檻。
def bond_codes() -> set[str]:
    return {c for c, _n, _k, cat, _i in watch_tuples() if "債" in cat}

# 投信已公告之「當月預估配息」人工維護清單——etfinfo 只揭露已實際除息者、MOPS 端點又抓不到，
# 故投信官方公告（首配或當期預告，除息日未到）於此登錄，作為 est_div 的可靠 fallback。
# 格式 {code: {"amount": 每單位預估金額, "ex_date": "YYYY-MM-DD"}}；僅在「除息日=本月且未到期」時顯示，
# 過月自動失效。投信新公告時更新此處（來源：各投信官網／經濟日報等，除息公告後由 etfinfo 接手實際值）。
# 2026-07 已公告（除息日未到）——經 WebSearch 逐檔查證各投信官網/經濟日報等，跨來源核對。
# 本月除息者：季配(1/4/7/10) 0056/00984A/00992A、月配 00929、半年配 0050/006208、本家 00991A。
# 其餘檔本月非除息月（下次落在 8/9/12 月或 2027），故不列。
ANNOUNCED_EST: dict[str, dict] = {
    "0056":   {"amount": 1.35,  "ex_date": "2026-07-21"},  # 季配 Q3 擬配，創季配新高（元大投信/聯合）
    "00929":  {"amount": 0.38,  "ex_date": "2026-07-21"},  # 月配 7月，創掛牌新高、年化14.8%（復華/ETtoday）
    "0050":   {"amount": 0.6,   "ex_date": "2026-07-21"},  # 半年配 7月第一階段預估（7/17 定案）
    "006208": {"amount": 4.75,  "ex_date": "2026-07-16"},  # 半年配 7月，史上新高（富邦/Newtalk）
    "00984A": {"amount": 0.415, "ex_date": "2026-07-16"},  # 季配 7月，成立以來最高、年化9.9%（安聯/Newtalk）
    "00991A": {"amount": 0.77,  "ex_date": "2026-07-21"},  # 本家首配（復華投信/經濟日報）
    "00992A": {"amount": 0.47,  "ex_date": "2026-07-16"},  # 首配（群益投信/Newtalk）
}

# 「即將登場」的新 ETF（前瞻資訊）。**條目自 2026-08-10 起存 `data/etf_upcoming.json`**（本檔只留
# 載入器與機制）：使用者要求「找到募集資訊主動更新、一週一次」——每週「ETF 募集週掃」Routine
# 只改資料檔＋push，daily.yml 併檔段（驗證＋as_of 比新舊）就會自動帶進 main 重建上線，
# **不需人工 merge 程式碼分支**。改狀態機制／視窗常數才動本檔。
# 來源：各投信官方募集頁／公開資訊觀測站／經濟日報・工商時報・Newtalk 等，經 WebSearch 逐檔查證。
# 五種狀態、依日期自動歸類與過期（2026-08-10 大改版：使用者以研討會「即將上市ETF」投影片抓包
# 「資料不齊全」——舊版募集結束沒掛牌日的檔會直接消失、已公告掛牌日超過 14 天也不顯示）：
#   · 「募集中」(now)／「即將募集」(soon)＝填 raise_start／raise_end；截止前都顯示，
#     起日在今日起 UPCOMING_RAISE_DAYS 內即入窗（raise_end 未填以起日＋FALLBACK 估算）。
#     募集期間優先於掛牌呈現——已知掛牌日以「預定掛牌」副標帶出，不重複佔兩張卡。
#   · 「已核准・時程未定」(hint)＝僅獲准募集、日期未公告：填 raise_hint（顯示文字）＋asof（查證日）；
#     asof 後 UPCOMING_HINT_DAYS 內顯示（日期公告後改填 raise_start/list_date 即轉正常狀態）。
#     **獨立第三組、儀表板精簡列呈現**（2026-08-10 使用者：「太長記得分類一下，尤其是只有核准
#     還沒確定募集時間的」）；代號未派者 code 填 None（顯示「代號未定」）——只有 hint 形態允許無代號。
#   · 「即將掛牌」(list)＝已公告掛牌日：掛牌日在今日起 UPCOMING_LIST_DAYS 內顯示。
#   · 「募集結束・待掛牌」(pend)＝募集截止、掛牌日未公告：截止後 UPCOMING_PEND_DAYS 內顯示
#     ——這是舊版的結構洞（檔案直接消失），現在誠實顯示待掛牌狀態。
# url＝該檔「活動介紹／募集公告」頁（投信官方活動頁優先，其次主流媒體介紹）——供使用者點開了解。
# 過期自動消失；掛牌日一過由升級機制接手（見下）。投信新公告時於此清單增修一筆即可；
# 守門測試 test_upcoming_stale_entries_guard 會逼補（募集結束逾30天無掛牌日／核准待定逾45天／
# 掛牌逾30天未清理 → 紅）。
# **掛牌日一到自動升級進追蹤**（2026-08-05 使用者需求，機制見 watch_tuples()）：list_date ≤ 今日且
# 尚未列入 WATCHLIST 者，自動以 stub 進「績效表＋持股詳情＆異動」（成立日暫用掛牌日、數據待 CI 抓）。
# 選填欄 kind／cat 供升級用（不填＝active／主動式；債券型務必填 cat 含「債」——髒序列門檻靠它放寬；
# 上櫃檔（櫃買掛牌）kind 照投資型態填 active／passive、cat 加「・上櫃」註記（2026-08-28 使用者
# 指示：分組跟型態走，勿再填 other——etfinfo 未收錄、Yahoo .TWO 等技術差異都會自動處理）。
# **track: False＝僅前瞻展示、掛牌後不自動進追蹤表**（2026-08-10 新增）：海外被動指數新檔
# （韓股／跨國主題）掛牌後自動塞進「被動」組會污染策展的 6 檔台股大表——只在本區亮相、到期退場。
UPCOMING_LIST_DAYS = 45      # 「即將掛牌」視窗：掛牌日在今日起 45 天內（14→45，掛牌日一公告就該看得到）
UPCOMING_RAISE_DAYS = 45     # 「即將募集」視窗：募集開始在今日起 45 天內
UPCOMING_RAISE_FALLBACK = 14  # raise_end 未填時，以「募集起日＋此天數」估算截止，讓未定截止者仍自動過期
UPCOMING_PEND_DAYS = 45      # 「募集結束・待掛牌」視窗：募集截止後最長顯示 45 天（守門測試 30 天就先紅）
UPCOMING_HINT_DAYS = 45      # 「已核准・時程未定」視窗：asof 查證日後最長顯示 45 天
UPCOMING_FP = ROOT / "data" / "etf_upcoming.json"


def _load_upcoming() -> list[dict]:
    """讀 data/etf_upcoming.json 的 items（「即將登場」條目的唯一真實來源）。

    搬出程式碼的原因（2026-08-10）：每週「ETF 募集週掃」Routine 要能只推「資料檔」就讓
    更新自動入 main（daily.yml 併檔通道只收資料、不自動併程式碼——那是不可開的注入面）。
    壞檔／缺檔 fail-open 回 []（「即將登場」顯示暫無、不壞版）——但不會靜默太久：
    tests 的 required-fields／seminar 守門會紅，CI 併檔前也有 JSON 驗證擋壞檔。"""
    try:
        d = json.loads(UPCOMING_FP.read_text(encoding="utf-8"))
        items = d.get("items") if isinstance(d, dict) else d
        return items if isinstance(items, list) else []
    except (OSError, json.JSONDecodeError) as e:
        print(f"  ⚠ etf_upcoming.json 讀取失敗（{e}）——「即將登場」以空清單顯示")
        return []


UPCOMING: list[dict] = _load_upcoming()


def _load_not_tracked() -> list[dict]:
    """讀 data/etf_upcoming.json 的 not_tracked——「已掛牌、但刻意不納入追蹤」的登記簿。

    **要解的洞（2026-09-21，009829 大華銀韓國KOSPI50 實例）**：stale guard 與自動發現層
    對 `track:false` 的海外被動檔互相矛盾——前者要求「掛牌逾 30 天的條目要清理」（對的，
    否則「即將登場」永遠掛著已掛牌的舊檔），但條目一離開 UPCOMING，`etfdiscover.known_codes()`
    就再也不認得它，於是每天判成「已掛牌未登錄」🔴 真漏網（儀表板紅章＋4 個 pytest 紅）。
    009829 就是 09-20 週掃依規清理後，隔天開始天天誤報。
    **兩邊都沒錯，缺的是第三種狀態**：「看到了、認得、就是不追蹤」。列此即不再警示，
    而且**留下 why 供日後複核**——不是把警示關掉，是把判斷記下來。
    與 UPCOMING 同放資料檔（非程式碼）：週掃 Routine 只推資料檔即可經 daily.yml 併入 main。
    壞檔／缺鍵 fail-open 回 []（退回修法前行為＝該檔重新被警示，不會靜默漏掉真的新 ETF）。
    """
    try:
        d = json.loads(UPCOMING_FP.read_text(encoding="utf-8"))
        rows = d.get("not_tracked") if isinstance(d, dict) else None
        return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
    except (OSError, json.JSONDecodeError):
        return []                                  # _load_upcoming 已印過同檔的讀取錯誤


NOT_TRACKED: list[dict] = _load_not_tracked()


def upcoming(today: date | None = None) -> dict:
    """即將登場的新 ETF（前瞻，手動維護 UPCOMING）——五狀態、三分組自動歸類與過期。

    回 {"raising": [...], "listing": [...], "approved": [...]}，每筆附 stat＋when（排序鍵）：
      · raising＝「募集中・即將募集」：stat=now（募集期進行中）／soon（起日在未來
        UPCOMING_RAISE_DAYS 內）。募集期間優先於掛牌呈現（掛牌日以副標帶出）。
      · listing＝「即將掛牌・待掛牌」：stat=list（掛牌日在未來 UPCOMING_LIST_DAYS 內）／
        pend（募集截止、掛牌日未公告——截止後 UPCOMING_PEND_DAYS 內顯示。2026-08-10 前
        這種檔會直接消失，使用者以研討會名單抓包「資料不齊全」，勿再改回）。
      · approved＝「已核准・募集時程未定」（stat=hint）：獨立第三組（2026-08-10 使用者
        指示分類，儀表板以精簡列呈現、不佔卡片版面）；raise_hint＋asof，登錄後
        UPCOMING_HINT_DAYS 內顯示，日期公告後改填正式欄位即自動移入前兩組。
    掛牌日已過＝退場（升級機制 watch_tuples 接手）。無資料回三個空清單（儀表板顯示
    「暫無」、不壞版）。"""
    t = today or clock.today_tw()

    def _d(s):
        try:
            return date.fromisoformat(s) if s else None
        except (TypeError, ValueError):
            return None

    listing, raising, approved = [], [], []
    for it in UPCOMING:
        ld = _d(it.get("list_date"))
        rs, re_ = _d(it.get("raise_start")), _d(it.get("raise_end"))
        if ld and ld <= t:
            continue                                   # 已掛牌：前瞻卡退場，升級機制接手
        # 未填 raise_end 者以「起日＋fallback」估截止，避免未定截止的募集永不過期
        eff_end = re_ if re_ is not None else (
            rs + timedelta(days=UPCOMING_RAISE_FALLBACK) if rs else None)
        if rs and eff_end and eff_end >= t:            # 募集尚未截止 → 募集組（優先於掛牌組）
            if rs <= t:
                raising.append({**it, "stat": "now", "when": rs.isoformat()})
            elif rs <= t + timedelta(days=UPCOMING_RAISE_DAYS):
                raising.append({**it, "stat": "soon", "when": rs.isoformat()})
            continue
        if rs is None and it.get("raise_hint"):        # 已核准、募集時程未定（asof 後 45 天內顯示）
            a = _d(it.get("asof"))
            if a and t <= a + timedelta(days=UPCOMING_HINT_DAYS):
                approved.append({**it, "stat": "hint", "when": a.isoformat()})
            continue
        if ld:                                          # 募集已截止（或純掛牌條目）、已知掛牌日
            if ld <= t + timedelta(days=UPCOMING_LIST_DAYS):
                listing.append({**it, "stat": "list", "when": ld.isoformat()})
        elif eff_end and eff_end >= t - timedelta(days=UPCOMING_PEND_DAYS):
            listing.append({**it, "stat": "pend", "when": eff_end.isoformat()})
    raising.sort(key=lambda x: ({"now": 0}.get(x["stat"], 1), x["when"]))
    listing.sort(key=lambda x: x["when"])
    approved.sort(key=lambda x: (x["when"], x["name"]))
    return {"raising": raising, "listing": listing, "approved": approved}


def watch_tuples(today: date | None = None) -> list[tuple[str, str, str, str, str]]:
    """有效追蹤清單＝靜態 WATCHLIST ＋「掛牌日已到」的 UPCOMING 自動升級檔。

    2026-08-05 使用者需求：「即將登場」列過的新 ETF，到掛牌那天要**自動**加入下方的
    績效表／持股詳情＆異動，不必等人工。機制：UPCOMING 有 list_date 且 ≤ 今日、
    又還沒列入 WATCHLIST 者，以 (code, name, kind, cat, 掛牌日) 升級——當天 CI 就會
    抓它的規模／報酬／持股（抓不到前由 stub 先上代碼與名稱，數據欄顯示 —）。

    track: False 的條目（海外被動指數檔）不升級——僅「即將登場」前瞻展示（2026-08-10 新增）。

    仍需人工的兩件事（結構性做不掉，勿誤以為全自動）：
    ① UPCOMING 本身要人工登錄（募集／掛牌公告散在各投信官網，無統一 API）；
    ② 掛牌後要「轉正」進 WATCHLIST（補查證確切成立日／頻率）——否則清理 UPCOMING
      舊條目時該檔會掉出追蹤。tests/test_etfwatch.py 有守：掛牌逾 14 天未轉正 → 紅。
    """
    t = today or clock.today_tw()
    have = {c for c, *_ in WATCHLIST}
    out = list(WATCHLIST)
    for it in UPCOMING:
        if it.get("track") is False:      # 僅前瞻展示的檔（海外被動指數）：掛牌後不進追蹤表
            continue
        try:
            ld = date.fromisoformat(it.get("list_date") or "")
        except (TypeError, ValueError):
            continue
        if ld > t or it["code"] in have:
            continue
        out.append((it["code"], it["name"], it.get("kind") or "active",
                    it.get("cat") or "主動式", ld.strftime("%Y/%m/%d")))
    return out


# 內建週報基準底稿（來源全倒／JSON 被清空時的最後 fallback，永不整片留空）。
# 值取自使用者提供之週報圖表；ret_1w/ret_1m＝該基準日的近1週／近1月報酬（%）。
SEED_ASOF = "2026-07-03"
SEED_PERF: dict[str, dict] = {
    "0056":   {"aum_e8": 7270.42, "ret_1w": 3.32, "ret_1m": 15.17, "yield_pct": 7.5,  "freq": "季配"},
    "00878":  {"aum_e8": 6257.30, "ret_1w": 2.90, "ret_1m": 19.89, "yield_pct": 7.84, "freq": "季配"},
    "00919":  {"aum_e8": 5542.20, "ret_1w": 2.23, "ret_1m": 18.15, "yield_pct": 13.2, "freq": "季配"},
    "00929":  {"aum_e8": 1448.10, "ret_1w": 4.03, "ret_1m": 17.57, "yield_pct": 9.97, "freq": "月配"},
    "0050":   {"aum_e8": 22413.0, "ret_1w": 3.06, "ret_1m": 12.70, "yield_pct": 1.87, "freq": "半年配"},
    "006208": {"aum_e8": 4658.56, "ret_1w": 3.07, "ret_1m": 12.71, "yield_pct": 3.59, "freq": "半年配"},
    "00980A": {"aum_e8": 180.24, "ret_1w": 1.62, "ret_1m": 8.18,  "yield_pct": 7.85,  "freq": "季配"},
    "00982A": {"aum_e8": 540.03, "ret_1w": 3.03, "ret_1m": 9.06,  "yield_pct": 10.41, "freq": "季配"},
    "00981A": {"aum_e8": 2948.01, "ret_1w": 2.72, "ret_1m": 7.72, "yield_pct": 8.05,  "freq": "季配"},
    "00984A": {"aum_e8": 79.19,  "ret_1w": 3.44, "ret_1m": 10.49, "yield_pct": 6.4,   "freq": "季配"},
    "00985A": {"aum_e8": 109.85, "ret_1w": 1.76, "ret_1m": 5.76,  "yield_pct": None,  "freq": "年配"},
    "00991A": {"aum_e8": 651.97, "ret_1w": 2.81, "ret_1m": 10.46, "yield_pct": None,  "freq": "半年配"},
    "00992A": {"aum_e8": 465.97, "ret_1w": 2.26, "ret_1m": 3.71,  "yield_pct": None,  "freq": "季配"},
    "00987A": {"aum_e8": 31.94,  "ret_1w": 1.50, "ret_1m": 2.08,  "yield_pct": None,  "freq": "年配"},
    "00994A": {"aum_e8": 56.42,  "ret_1w": -0.93, "ret_1m": 2.20, "yield_pct": None,  "freq": "季配"},
    "00995A": {"aum_e8": 57.44,  "ret_1w": 1.61, "ret_1m": 5.95,  "yield_pct": None,  "freq": "季配"},
    "00993A": {"aum_e8": 115.73, "ret_1w": 2.50, "ret_1m": 8.64,  "yield_pct": None,  "freq": "年配"},
    # 2026-07-06 新增（規模為查證概值、報酬待 CI 抓；抓不到時沿用此底稿，報酬留空由儀表板標「—」）：
    "00988A": {"aum_e8": 594.0, "ret_1w": None, "ret_1m": None, "yield_pct": None, "freq": "年配"},
    "00990A": {"aum_e8": None,  "ret_1w": None, "ret_1m": None, "yield_pct": None, "freq": "不配息"},
    "00403A": {"aum_e8": 792.0, "ret_1w": None, "ret_1m": None, "yield_pct": None, "freq": "季配"},
    "00407A": {"aum_e8": 78.7,  "ret_1w": None, "ret_1m": None, "yield_pct": None, "freq": "不配息"},
    # 2026-07-21 新增（本家金融股債、上櫃 .TWO；etfinfo 未收錄 → 規模／首配用 WebSearch 查證值
    # 當種子（Tier B：規模 00998A≈35.21 億（7/8）、00986D≈28.40 億（MoneyDJ）；兩檔首配皆 2026/6/17
    # 除息：00998A 0.404 元/季、00986D 0.09 元/月——Yahoo股市/MoneyDJ/復華官網報導），
    # 年化配息率暫用媒體報導之首配年化口徑，etfinfo/實際除息資料接上後覆蓋）：
    "00998A": {"aum_e8": 35.21, "ret_1w": None, "ret_1m": None, "yield_pct": 10.0, "freq": "季配",
               "last_div": 0.404, "last_div_date": "2026-06-17"},
    "00986D": {"aum_e8": 28.40, "ret_1w": None, "ret_1m": None, "yield_pct": 7.3,  "freq": "月配",
               "last_div": 0.09,  "last_div_date": "2026-06-17"},
    # 2026-08-05 新增（上市檔、etfinfo 有收錄 → 規模／報酬待 CI 首抓，不杜撰；freq 為查證值。
    # 四檔首次除息皆未到（00404A 預計 9 月中、00996A 滿180日後、00410A 2027/3）→ last_div 留空）：
    "00404A": {"aum_e8": None, "ret_1w": None, "ret_1m": None, "yield_pct": None, "freq": "季配"},
    "00405A": {"aum_e8": None, "ret_1w": None, "ret_1m": None, "yield_pct": None, "freq": "季配"},
    "00996A": {"aum_e8": None, "ret_1w": None, "ret_1m": None, "yield_pct": None, "freq": "季配"},
    "00410A": {"aum_e8": None, "ret_1w": None, "ret_1m": None, "yield_pct": None, "freq": "半年配"},
    # 2026-08-05 第二批（同上原則：freq 查證值、其餘待 CI 首抓；00406A 首配已實際除息 → 種子帶入）：
    "00400A": {"aum_e8": None, "ret_1w": None, "ret_1m": None, "yield_pct": None, "freq": "月配"},
    "00401A": {"aum_e8": None, "ret_1w": None, "ret_1m": None, "yield_pct": None, "freq": "月配"},
    "00402A": {"aum_e8": None, "ret_1w": None, "ret_1m": None, "yield_pct": None, "freq": "年配"},
    "00406A": {"aum_e8": None, "ret_1w": None, "ret_1m": None, "yield_pct": None, "freq": "月配",
               "last_div": 0.128, "last_div_date": "2026-07-31"},
    "00408A": {"aum_e8": None, "ret_1w": None, "ret_1m": None, "yield_pct": None, "freq": "季配"},
    "00999A": {"aum_e8": None, "ret_1w": None, "ret_1m": None, "yield_pct": None, "freq": "季配"},
    # 2026-08-28 轉正（上櫃 .TWO、etfinfo 未收錄 → 規模走 WebSearch 查證種子，同 00998A/00986D 慣例。
    # 00411A 募集規模 ~70.3 億兩來源一致；00987D 查無可靠規模數字 → 留 None、寧缺勿錯。
    # 首次配息皆未到（00411A 年配、00987D 季配）→ last_div 留空）：
    "00411A": {"aum_e8": 70.3, "ret_1w": None, "ret_1m": None, "yield_pct": None, "freq": "年配"},
    "00987D": {"aum_e8": None, "ret_1w": None, "ret_1m": None, "yield_pct": None, "freq": "季配"},
    # 2026-09-03 轉正（上市檔、etfinfo 已收錄 → 規模／報酬待 CI 首抓；募集完成規模查無兩來源
    # 一致值 → 留 None、寧缺勿錯，同 00987D 前例。年配、首次配息未到 → last_div 留空）：
    "00409A": {"aum_e8": None, "ret_1w": None, "ret_1m": None, "yield_pct": None, "freq": "年配"},
}

# 「待首次 CI 抓取」的新增檔：本環境（雲端 Claude proxy）抓不到乾淨報酬／規模，且無使用者週報底稿，
# 故報酬暫留空（儀表板標「—」），不杜撰數字；待 daily.yml（CI，不受 proxy 擋）首次抓取後由實際值補上。
# 這些檔暫不受「SEED 報酬一律非空」不變式約束（成立日期／頻率等靜態欄位仍必備）。
_SEED_PENDING: set[str] = {"00988A", "00990A", "00403A", "00407A", "00998A", "00986D",
                           "00404A", "00405A", "00996A", "00410A",
                           "00400A", "00401A", "00402A", "00406A", "00408A", "00999A",
                           "00411A", "00987D", "00409A"}

# 收益分配頻率的英文 → 表內中文（etfinfo dividendFrequency 兩種寫法都見過，中文直接放行）
_FREQ_MAP = {"monthly": "月配", "quarterly": "季配", "semiannual": "半年配",
             "semi-annual": "半年配", "semiannually": "半年配", "biannual": "半年配",
             "annual": "年配", "annually": "年配", "yearly": "年配", "none": "不配息"}

# 收益分配頻率（中文）→ 一年配息次數（年化配息率＝單次配息率 × 次數）
_FREQ_PER_YEAR = {"月配": 12, "季配": 4, "半年配": 2, "年配": 1}


def _num(v) -> float | None:
    """字串/數字 → float；'+3.32%'、'2兆2413億' 這類顯示字串也盡量救。None/'N/A' 回 None。"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) if math.isfinite(float(v)) else None
    s = str(v).strip().replace(",", "").replace("％", "%")
    if not s or s.upper() in ("N/A", "NA", "—", "-"):
        return None
    m = re.match(r"^([+-]?\d+(?:\.\d+)?)兆(?:(\d+(?:\.\d+)?)億?)?$", s)   # 「2兆2413億」→ 億
    if m:
        return float(m.group(1)) * 1e4 + (float(m.group(2)) if m.group(2) else 0.0)
    m = re.match(r"^([+-]?\d+(?:\.\d+)?)億?%?$", s)
    return float(m.group(1)) if m else None


def _norm_aum_e8(v, prev_e8: float | None) -> float | None:
    """規模正規化成「億元」。etfinfo 的 aum 單位未定（元／百萬／億都有可能），
    有既有值時挑「與既有值數量級最接近」的候選（規模週變動不會差 5 倍）；
    無既有值用門檻猜：≥5e7 視為元、≥1e5 視為百萬、其餘視為已是億。"""
    x = _num(v)
    if x is None or x <= 0:
        return None
    cands = [x, x / 100.0, x / 1e5, x / 1e8]      # 億／百萬／千元／元 → 億
    if prev_e8 and prev_e8 > 0:
        return min(cands, key=lambda c: abs(math.log(c / prev_e8)) if c > 0 else 99)
    if x >= 5e7:
        return x / 1e8
    if x >= 1e5:
        return x / 100.0
    return x


def _freq(info: dict) -> str | None:
    v = str(info.get("dividendFrequency") or info.get("dividend_frequency") or "").strip()
    if not v:
        return None
    return _FREQ_MAP.get(v.lower(), v if re.search(r"[配息]", v) else None)


def _div_rows(divs) -> list[tuple[date, float, bool]]:
    """配息紀錄 → [(除息日, 每單位金額, 是否為預估)]，依除息日排序。

    預估旗標：etfinfo 常見多種寫法都認（estimated/isEstimate/type=estimate/status 含『預』）。"""
    out: list[tuple[date, float, bool]] = []
    for x in (divs or []):
        amt = _num(x.get("amount"))
        m = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})",
                     str(x.get("exDate") or x.get("ex_date") or ""))
        if amt is None or not m:
            continue
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
        flag = " ".join(str(x.get(k) or "") for k in
                        ("estimated", "isEstimate", "estimate", "type", "status", "note"))
        est = bool(x.get("estimated")) or ("estimate" in flag.lower()) or ("預" in flag)
        out.append((d, amt, est))
    out.sort(key=lambda r: r[0])
    return out


def _latest_dividend(divs) -> float | None:
    """最近一次「已實際配發」（除息日已到、非預估）的每單位配息金額——年化殖利率用。"""
    last, _ld, _e, _ed = _dividend_split(divs)
    return last


def _dividend_split(divs, today: date | None = None) -> tuple:
    """拆成 (最近一次實際配息, 其除息日, 當月預估配息, 其除息日)。

    · 最近一次實際：除息日 ≤ 今天且非預估者中最新一筆。
    · 當月預估：投信於配息月 1 日公告的「預計配息金額」——取除息日在『本月且尚未除息』
      或明確標記為預估者中最近一筆。無則 (…, None, None)。"""
    today = today or clock.today_tw()
    rows = _div_rows(divs)
    actual = [r for r in rows if r[0] <= today and not r[2]]
    last_amt, last_d = (actual[-1][1], actual[-1][0].isoformat()) if actual else (None, None)
    est_cands = [r for r in rows
                 if (r[2] or r[0] > today) and r[0].year == today.year and r[0].month == today.month]
    est_amt, est_d = (est_cands[0][1], est_cands[0][0].isoformat()) if est_cands else (None, None)
    return last_amt, last_d, est_amt, est_d


def _annualized_yield(divs, price, freq: str | None) -> float | None:
    """年化配息率＝最新一次配息金額 ÷ 最新市價 × 一年配息次數 ×100%。
    缺配息／市價／頻率任一 → None（由 merge 保留既有值）。"""
    amt, p = _latest_dividend(divs), _num(price)
    n = _FREQ_PER_YEAR.get(freq or "")
    if amt is None or not p or p <= 0 or not n:
        return None
    return round(amt / p * n * 100, 2)


def _fetch_market(code: str) -> dict:
    """etfinfo（Tier B）：規模(AUM)／年化配息率／配息頻率／市價日。

    殖利率一律「年化配息率」：最新公布一次的配息金額 ÷ 最新市價 × 配息頻率次數，
    而非 etfinfo 的 trailingYield（近12月回溯值）——反映當下配息水準。"""
    from .connectors import etfinfo
    d = etfinfo.fetch_etf(code, cache_ttl=600)
    info = d.get("info") or {}
    lm = d.get("latestMarket") or {}
    freq = _freq(info)
    last_amt, last_d, est_amt, est_d = _dividend_split(d.get("dividends"))
    return {"aum_raw": lm.get("aum") or info.get("aum"),
            "close_px": _num(lm.get("price")),
            "yield_pct": _annualized_yield(d.get("dividends"), lm.get("price"), freq),
            "last_div": last_amt, "last_div_date": last_d,
            "est_div": est_amt, "est_div_date": est_d,
            "freq": freq, "mkt_date": lm.get("date")}


def _stooq_series(code: str) -> dict[str, float]:
    """stooq 日線 CSV（乾淨、每交易日一筆原始收盤，專為程式抓取）→ {iso_date: 收盤}。

    Yahoo 圖表 API 曾對個別檔回傳「不同日期同一收盤值」的髒資料（例 0056 6/5 與 6/29 都 51.8），
    改以 stooq 為第一來源交叉比對。抓不到或代碼不存在回 {}（退下一來源）。"""
    from .http import get_bytes
    url = f"https://stooq.com/q/d/l/?s={code.lower()}.tw&i=d"
    try:
        txt = get_bytes(url, cache_ttl=3600, retries=2).decode("utf-8", "ignore")
    except Exception:
        return {}
    out: dict[str, float] = {}
    for line in txt.splitlines()[1:]:                # 跳表頭 Date,Open,High,Low,Close,Volume
        p = line.split(",")
        if len(p) >= 5 and re.match(r"\d{4}-\d{2}-\d{2}$", p[0].strip()):
            c = _num(p[4])
            if c:
                out[p[0].strip()] = c
    if len(out) > 90:                                # 只留近 ~90 個交易日，夠算週/月報酬
        for k in sorted(out)[:-90]:
            del out[k]
    return out


_DIV_EVENTS: dict[str, dict[str, float]] = {}   # {code: {除息日iso: 每單位金額}}——_yahoo_series 抓到即存


def _yahoo_series(code: str) -> dict[str, float]:
    """Yahoo Finance 圖表 API → {iso_date: 收盤}。單一請求、涵蓋近3月逐日。

    取「原始收盤」(quote.close) 為主、adjClose 為輔——避開 adjClose 偶發的稀疏/還原偏差；
    同請求帶 events=div 把視窗內除息事件存進 _DIV_EVENTS，報酬計算時把息加回
    （原始收盤跨除息日會低估總報酬——2026-07-22 踩坑：006208 於 7/16 除息 4.75，
    一週報酬 -8.41% 比同指數 0050 的 -6.42% 多跌整整一個股息）。取不到回 {}。"""
    from datetime import datetime

    from .http import get_json
    d = None
    for suf in (".TW", ".TWO"):     # 上市 → 上櫃（00998A/00986D 等 TPEX 掛牌檔）依序試
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{code}{suf}"
               "?range=3mo&interval=1d&events=div")
        try:
            d = get_json(url, cache_ttl=3600)
        except Exception:
            d = None
        if (((d or {}).get("chart") or {}).get("result") or [None])[0]:
            break
    res = (((d or {}).get("chart") or {}).get("result") or [None])[0]
    if not res:
        return {}
    divs: dict[str, float] = {}
    for ev in (((res.get("events") or {}).get("dividends") or {})).values():
        a = _num((ev or {}).get("amount"))
        t = (ev or {}).get("date")
        if a and t:
            divs[datetime.fromtimestamp(int(t), clock.TW_TZ).date().isoformat()] = a
    if divs:
        _DIV_EVENTS[code] = divs
    ts = res.get("timestamp") or []
    ind = res.get("indicators") or {}
    raw = ((ind.get("quote") or [{}])[0] or {}).get("close") or []
    adj = ((ind.get("adjclose") or [{}])[0] or {}).get("adjclose") or []
    out: dict[str, float] = {}
    for i, t in enumerate(ts):
        c = raw[i] if i < len(raw) and raw[i] is not None else \
            (adj[i] if i < len(adj) and adj[i] is not None else None)
        if c:
            iso = datetime.fromtimestamp(t, clock.TW_TZ).date().isoformat()
            out[iso] = float(c)
    return out


def _finmind_series(code: str, today: date) -> dict[str, float]:
    """FinMind TaiwanStockPrice（免金鑰，有 token 更寬鬆）→ {iso_date: 收盤}。單一請求涵蓋近75日。"""
    import os

    from .http import get_json
    start = (today - timedelta(days=75)).isoformat()
    token = os.environ.get("FINMIND_TOKEN", "")
    url = (f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPrice"
           f"&data_id={code}&start_date={start}&end_date={today.isoformat()}"
           + (f"&token={token}" if token else ""))
    try:
        d = get_json(url, cache_ttl=3600)
    except Exception:
        return {}
    if not isinstance(d, dict) or d.get("status") != 200:
        return {}
    return {r["date"]: float(r["close"]) for r in (d.get("data") or [])
            if r.get("date") and r.get("close")}


def _twse_series(code: str, today: date) -> dict[str, float]:
    """TWSE 官方每日收盤（權威）→ {iso_date: 收盤}。抓當月＋前兩月，涵蓋 30 日回推。
    註：TWSE 為價格收盤（未還原息），高股息 ETF 於除息日附近會低估總報酬。"""
    from .connectors import twse
    close: dict[str, float] = {}
    m0 = today.replace(day=1)
    for back in (0, 1, 2):
        d0 = m0
        for _ in range(back):
            d0 = (d0 - timedelta(days=1)).replace(day=1)
        for iso, c, _v in twse.fetch_month(code, d0.year, d0.month):
            if c:
                close[iso] = c
    return close


def _returns_from_series(close: dict[str, float], divs: dict[str, float] | None = None) -> dict:
    """由 {iso: close} 日序列算過去一週(7)/一月(30 日曆日)報酬（總報酬口徑）。

    divs＝{除息日iso: 每單位金額}（Yahoo events=div）：區間內（基準日之後、含最新日）的除息
    加回最新收盤再算——原始收盤跨除息日會把配息當跌幅、低估報酬（2026-07-22 教訓）。
    另回 last_close（序列最新收盤）供上層當收盤價 fallback（etfinfo 未收錄的上櫃檔）。

    防呆：某週期的基準日必須「真的接近 N 天前」（在 target 前 12 天內）——資料太稀疏時
    基準會落在很早的孤點、把區間拉長算出錯值（曾見 ret_1w==ret_1m）；此時該週期不報（回 None、
    交由上層退回底稿），寧缺勿錯。"""
    dates = sorted(close)
    out: dict = {"ret_1w": None, "ret_1m": None, "perf_date": None, "last_close": None,
                 "ret_1w_base": None, "ret_1m_base": None,
                 "chg_pct": None, "chg_amt": None, "prev_close": None, "prev_date": None,
                 "chg_ex_div": None}
    if len(dates) < 2:
        return out
    last = dates[-1]
    last_d = date.fromisoformat(last)
    out["perf_date"] = last
    out["last_close"] = close[last]

    # ── 當日漲跌（2026-07-29 使用者需求）：最新交易日 vs 前一交易日收盤 ──
    # 除息日特例：台股慣例當日漲跌是對「除息參考價」＝前收 − 每單位配息，否則整段配息會被
    # 當成跌幅（與 ret_1w/1m 加回配息的總報酬口徑同一個坑，2026-07-22 已在區間報酬修過）。
    prev = dates[-2]
    ref = close[prev]
    ex_div = round((divs or {}).get(last) or 0, 4)
    if ex_div:
        ref = round(ref - ex_div, 4)
        out["chg_ex_div"] = ex_div
    out["prev_close"], out["prev_date"] = close[prev], prev
    if ref:
        out["chg_amt"] = round(close[last] - ref, 4)
        out["chg_pct"] = round((close[last] / ref - 1) * 100, 2)

    def _ret(days: int, tag: str):
        target = last_d - timedelta(days=days)
        prior = [d for d in dates if date.fromisoformat(d) <= target]
        if not prior:
            return None
        bd = prior[-1]
        if (target - date.fromisoformat(bd)).days > 12:      # 基準離目標日太遠＝大缺口 → 不報
            return None
        base = close[bd]
        out[f"{tag}_base"] = f"{bd}={base:g}"                 # 追查用：所用基準日與收盤
        # 區間內除息加回（bd 當日除息不算——基準收盤已是除息後價）
        d_add = round(sum(a for d, a in (divs or {}).items() if bd < d <= last), 4)
        if d_add:
            out[f"{tag}_div"] = d_add                         # 追查用：加回的每單位息
        return round(((close[last] + d_add) / base - 1) * 100, 2) if base else None

    out["ret_1w"] = _ret(7, "ret_1w")
    out["ret_1m"] = _ret(30, "ret_1m")
    return out


# 3 個月日線約 60 個交易日；序列夠密才信任（否則 1 個月基準會落孤點算出錯值）。
_MIN_SERIES = 25


def _is_degenerate(series: dict[str, float], relax: bool = False) -> bool:
    """髒序列偵測：相異收盤值太少（<60% 交易日各異）＝疑似來源回傳重複值
    （曾見 Yahoo 對 0056 多日回同一 51.8）→ 不信任、換下一來源。

    relax＝債券型（bond_codes()）：tick 小、日波動低，收盤值天然重複，60% 門檻會誤殺
    合法序列（2026-07-22 教訓：00986D 全源被判髒 → 報酬整片空）→ 放寬到 15%。"""
    n = len(series)
    thr = 0.15 if relax else 0.6
    return n >= 10 and len(set(series.values())) < n * thr


_BAD_BARS: dict[str, set[str]] = {}     # {code: 被剔除的日期}——fetch() 收尾印一行摘要


def _sane_series(series: dict[str, float], today: date, code: str = "") -> dict[str, float]:
    """剔除「不可能存在」的日期：未來日與週末日（台股週六／日不交易）。

    **2026-09-21 踩坑（使用者：「00998A 整個數字都是錯的」）**：Yahoo 對全部 36 檔都多回
    一個 **2026-09-20（週日）** 的 bar，整張表被它一手汙染——當日漲跌 0050 顯示 -7.15%、
    0056 顯示 0.00%、00998A 顯示 +4.99%（實為 -2.70%，方向相反），連週／月報酬一起中毒
    （00998A 一週 +4.66%／一月 +4.37%，實為約 +0.25%／-0.03%）。
    而且**完全靜默**：那個假 bar 的日期比 etfinfo 資料日「還新」，L1／L2 備案與渲染端
    過期章的判準當時都只看「序列落後」（chg_asof < as_of），三道防線一致放行。

    根因是「來源給什麼就收什麼」＝把不可能的日期當事實。在入口一次濾掉，當日漲跌與
    區間報酬同時止血（兩者都讀同一條序列）。

    註：台股偶有颱風補行交易的週六（如 2021-02-20），本濾網會連那天一起丟。代價可接受
    ——區間報酬有 12 天基準容差、當日漲跌另有官方當日表（L1）頂上，而「丟掉一個真 bar」
    遠輕於「採信一個假 bar」（寧缺勿錯，同 _md_stale_badge 的取捨）。
    """
    out: dict[str, float] = {}
    for d, c in (series or {}).items():
        try:
            dt = date.fromisoformat(str(d)[:10])
        except (TypeError, ValueError):
            _BAD_BARS.setdefault(code, set()).add(str(d))    # 版式漂移：日期格式不對，不收
            continue
        if dt > today or dt.weekday() >= 5:                  # 未來日／週六日＝不可能的交易日
            _BAD_BARS.setdefault(code, set()).add(str(d)[:10])
            continue
        out[d] = c
    return out


def _official_day_quotes() -> dict[str, dict]:
    """官方全市場「當日收盤」表 → {code: {date, close, change, …}}（上市＋上櫃各 1 請求）。

    2026-09-03 使用者：「沒辦法從其他地方補嗎？」——當日漲跌原本只有報酬序列一條路，
    Yahoo 日線缺當日 bar 就整格失真。這兩支官方 openapi 是**現成的**：CI 每天已在打
    （新 ETF 發現層篩代碼、ETF 持股貢獻取報價），ETF 代碼確定在回傳內，且**直接帶
    `change` 漲跌額**，連前收都不必自己找。整輪只發 2 個請求（`get_json` 另有 30 分快取，
    同輪其他腳本打過就不重打），不違反「多班次不放大來源站請求」。
    口徑＝官方市價，與 etfinfo 的 close_px 同一種價（不是 Yahoo 的還原收盤）。
    單邊失敗只損失該市場、不影響另一邊；全失敗回空 → 上層自動退下一層備案。"""
    from importlib import import_module
    out: dict[str, dict] = {}
    for mod in ("twse", "tpex"):
        try:
            out.update(import_module(f".connectors.{mod}", __package__)
                       .fetch_today_all(retries=1, timeout=12))   # 硬性上限：被擋時預設 3×25s 會讓整輪空轉（同 fundhot 前例）
        except Exception as e:
            print(f"  ⚠ {mod} 當日收盤表不可得（當日漲跌改走下一層備案）：{e}")
    return out


def _fetch_returns(code: str, today: date | None = None) -> dict:
    """過去一週／一月報酬 —— 多來源、單檔單請求，取第一個「乾淨且夠密」的序列。

    來源順序：stooq（乾淨日線）→ Yahoo → FinMind → TWSE。序列須 ≥ _MIN_SERIES 點且非「重複值
    髒序列」才採用；回傳 ret_src／ret_n／基準日供追查；全失敗回 None（上層退回底稿）。"""
    today = today or clock.today_tw()
    best = None
    relax = code in bond_codes()                       # 債券型：放寬「髒序列」門檻（收盤天然重複）
    # 惰性呼叫（審查 2026-07-18）：tuple 字面值會在進迴圈前把四個來源全打一遍，
    # 「依序取第一個」短路失效——每檔多發 ~5 個不必要請求。改存 callable 迴圈內才呼叫。
    for src, fetch in (("stooq", lambda: _stooq_series(code)),
                       ("yahoo", lambda: _yahoo_series(code)),
                       ("finmind", lambda: _finmind_series(code, today)),
                       ("twse", lambda: _twse_series(code, today))):
        series = _sane_series(fetch(), today, code)   # 先濾掉不可能的日期（未來／週末）
        n = len(series)
        if n < 5 or _is_degenerate(series, relax=relax):  # 太短或髒（重複值）→ 換下一來源
            continue
        # 除息事件取自 Yahoo（_yahoo_series 順帶存 _DIV_EVENTS）；stooq 先中選時視窗除息
        # 資訊未載入（維持價格口徑）——CI 實務上 stooq 對台股 ETF 多半抓不到、以 Yahoo 為主。
        r = _returns_from_series(series, _DIV_EVENTS.get(code))
        r["ret_src"], r["ret_n"] = src, n
        # 註：一週==一月報酬是「該檔近月盤整（兩基準日同價）」的合理結果，非錯值——不再據此判髒
        # （2026-07-06 教訓：0056 6月盤整於 51.8，週≈月≈2.8% 是對的；曾誤攔正確資料）。
        if n >= _MIN_SERIES and (r["ret_1w"] is not None or r["ret_1m"] is not None):
            return r                                  # 乾淨且夠密即採用
        best = best or r                              # 太稀疏：暫存，後續來源皆不足才用
    return best or {"ret_1w": None, "ret_1m": None, "perf_date": None,
                    "ret_src": None, "ret_n": 0}


def _pick(old: dict, base: dict, key: str):
    """欄位級 fallback：既有落檔值（非 None）優先，否則用內建週報底稿 base。
    注意用『值是否為 None』判斷，不用 key 是否存在——CI 曾把欄位寫成顯式 null，
    dict.get(key, default) 會回傳那個 null 而非 default，反而把資料洗空。"""
    v = old.get(key)
    return v if v is not None else base.get(key)


def fetch() -> dict:
    """全清單抓取，與既有落檔／內建週報底稿逐檔「欄位級合併」→ 新 doc（不落檔；落檔用 save）。

    雙來源、各自獨立降級：規模／年化配息率／頻率 ← etfinfo；過去一週／一月報酬 ← TWSE 官方收盤自算。
    fallback 鏈（每欄位獨立）：本次新值 → 既有落檔值 → 內建 SEED_PERF 週報底稿。
    成立日期一律取 WATCHLIST 靜態值（永不空白）。抓不到的欄位絕不留空／不洗成 null。
    """
    prev = {i.get("code"): i for i in (load() or {}).get("items", [])}
    today = clock.today_tw()
    try:                                                  # 當月預估配息 ← MOPS（一次抓全 ETF）
        from .connectors import mops
        mops_dist = mops.etf_distributions({c for c, *_ in watch_tuples()})
    except Exception as e:
        print(f"  ⚠ MOPS 收益分配抓取失敗（預估配息欄留空）：{e}")
        mops_dist = {}
    # 配息頻率的升級 fallback：UPCOMING 自動升級檔沒有 SEED_PERF 底稿，
    # 但募集公告的頻率是已知的——別讓它顯示 —（etfinfo 抓到後照樣覆蓋）。
    up_freq = {it["code"]: it.get("freq") for it in UPCOMING
               if it.get("freq") and it["freq"] != "—"}
    items, got_mkt, got_ret, got_est = [], 0, 0, 0
    got_chg_off = got_chg_l1 = 0   # 當日漲跌走備案的檔數（官方當日表／etfinfo 前收），供 CI 日誌診斷
    day_q = _official_day_quotes()  # 迴圈外取一次：整輪 2 請求，不是逐檔
    for code, name, kind, cat, inception in watch_tuples():
        old = prev.get(code) or {}
        base = SEED_PERF.get(code, {}) or (
            {"freq": up_freq[code]} if code in up_freq else {})
        item = {"code": code, "name": name, "kind": kind, "cat": cat,
                "inception": inception,                       # 靜態、永遠有值
                "aum_e8": _pick(old, base, "aum_e8"),
                "close_px": old.get("close_px"),              # 最新收盤價（etfinfo 市價）
                "ret_1w": _pick(old, base, "ret_1w"),
                "ret_1m": _pick(old, base, "ret_1m"),
                "last_div": _pick(old, base, "last_div"),     # 最近一次「實際」配息金額
                "last_div_date": _pick(old, base, "last_div_date"),  # （上櫃檔 etfinfo 缺 → 用種子）
                "est_div": old.get("est_div"),                # 當月「預估」配息金額（投信公告，非正式）
                "est_div_date": old.get("est_div_date"),
                "yield_pct": _pick(old, base, "yield_pct"),
                "freq": _pick(old, base, "freq"),
                # 當日漲跌（2026-07-29 使用者需求）：與報酬同源、由收盤序列末兩點自算。
                # 沿用既有落檔值當 fallback（本次序列抓不到就別讓整欄變空白）。
                "chg_pct": old.get("chg_pct"), "chg_amt": old.get("chg_amt"),
                "prev_close": old.get("prev_close"), "prev_date": old.get("prev_date"),
                "chg_ex_div": old.get("chg_ex_div"),
                # 當日漲跌備案 L1 用（2026-09-03）：etfinfo 收盤價的「前一個資料日快照」。
                # as_of 推進時把舊 close_px 降級存於此（同 etfholdings.merge_one 的 prev 慣例），
                # 供序列缺當日 bar 時自算——與 close_px 同為 etfinfo 市價，口徑天然一致。
                "prev_px": old.get("prev_px"), "prev_px_date": old.get("prev_px_date"),
                "chg_asof": old.get("chg_asof"),   # 當日漲跌所屬交易日（≠perf_asof：漲跌可走 L1）
                "chg_src": old.get("chg_src"),     # 漲跌來源：序列來源名／etfinfo_prev
                "as_of": old.get("as_of"),
                "perf_asof": old.get("perf_asof") or SEED_ASOF,  # 報酬數據基準日
                "ret_src": old.get("ret_src") or "seed",         # 報酬來源（yahoo/finmind/twse/seed）
                "src": old.get("src") or "seed"}
        # ① 規模／收盤價／配息（實際＋預估）／殖利率／頻率 ← etfinfo
        yield_from_src = False        # etfinfo 本輪是否給了殖利率（否→步驟④可用配息+收盤自算）
        # 覆蓋前的落檔快照（①-b 官方表覆蓋與 prev_px 降級都要用 → 提到 try 之外）
        px_before, asof_before = item.get("close_px"), item.get("as_of")
        try:
            m = _fetch_market(code)
            aum = _norm_aum_e8(m.get("aum_raw"), item["aum_e8"])
            for k, v in (("aum_e8", aum), ("close_px", m.get("close_px")),
                         ("yield_pct", m.get("yield_pct")), ("freq", m.get("freq")),
                         ("last_div", m.get("last_div")), ("last_div_date", m.get("last_div_date"))):
                if v is not None:
                    item[k] = v
            yield_from_src = m.get("yield_pct") is not None
            item["est_div"] = m.get("est_div")                # 預估配息：無公告即清空（過月即消失）
            item["est_div_date"] = m.get("est_div_date")
            if any(v is not None for v in (aum, m.get("close_px"), m.get("yield_pct"), m.get("freq"))):
                item["src"] = "etfinfo+px"
                if m.get("mkt_date"):
                    item["as_of"] = str(m["mkt_date"])[:10]
                got_mkt += 1
        except Exception as e:                     # proxy 擋站/斷網 → 沿用 fallback 值
            print(f"  ⚠ {code} 規模／殖利率抓取失敗（沿用既有值／週報底稿）：{e}")

        # ①-b 收盤價／資料日以「官方全市場當日收盤表」為準（2026-09-21 使用者回報
        # 「ETF 的當日淨值上櫃的沒有更新到」）──**etfinfo 對上櫃檔的市價慢一個交易日、
        # 卻照樣把 mkt_date 標成當日**，實測逐日成立（etfinfo close_px@D == 官方收盤@D-1）：
        #   00998A etfinfo 17.30@9/18 ＝ 9/17 收盤（9/18 實為 17.22）
        #   00411A etfinfo  9.91@9/18 ＝ 9/17 收盤（9/18 實為 10.13）
        #   00986D etfinfo 14.17@9/18 ＝ 9/17 收盤（9/18 實為 14.20）
        # 上市檔（0050 等 32 檔）則逐日與官方同值——所以這是 etfinfo 的上櫃口徑問題，
        # 不是我們的合併邏輯。原本唯一能修正它的路徑（序列末值回填）被 `close_px is None`
        # 擋住＝**只有史上第一輪會生效**，之後永遠沿用 etfinfo 的落後值。
        # 修法＝改用 day_q：官方權威（非 Tier B）、市價口徑與 close_px 一致、
        # **整輪只 2 請求且已在 L1 取過**（零額外成本），日期同源＝與 L1 漲跌天然同日。
        # 同日也覆蓋（不只更新日）：上櫃的坑正是「日期相同、值差一天」。
        # day_q 取不到（本容器 proxy 擋 twse/tpex）→ 整段跳過，行為與修法前一致（fail-open）。
        q0 = day_q.get(code) or {}
        qc0, qd0 = q0.get("close"), q0.get("date")
        if qc0 and qd0 and (not item.get("as_of") or str(qd0)[:10] >= item["as_of"]):
            item["close_px"], item["as_of"] = round(float(qc0), 4), str(qd0)[:10]
            item["src"] = "official_px+etfinfo"

        # 資料日「真的推進」才把舊收盤降級為前收——同一資料日重抓時若照降，
        # prev_px 會被洗成今天自己、當日漲跌永遠算成 0（同 etfholdings 的假無異動坑）。
        # 置於 ①-b 之後：判準要用最終 as_of（官方表可能比 etfinfo 更新）。
        if (asof_before and item.get("as_of") and item["as_of"] > asof_before
                and px_before is not None):
            item["prev_px"], item["prev_px_date"] = px_before, asof_before

        # ② 過去一週／一月報酬 ← Yahoo 還原收盤／FinMind／TWSE（依序取密序列）自算
        try:
            r = _fetch_returns(code)
            if r.get("ret_1w") is not None:
                item["ret_1w"] = r["ret_1w"]
            if r.get("ret_1m") is not None:
                item["ret_1m"] = r["ret_1m"]
            if (r.get("ret_1w") is not None or r.get("ret_1m") is not None) and r.get("perf_date"):
                item["perf_asof"] = str(r["perf_date"])[:10]     # 報酬有更新才推進基準日
                item["ret_src"] = r.get("ret_src")               # 報酬取自哪個來源（追查用）
                item["ret_n"] = r.get("ret_n")                   # 序列點數（診斷稀疏度）
                item["ret_1w_base"] = r.get("ret_1w_base")       # 一週報酬所用基準日=收盤
                item["ret_1m_base"] = r.get("ret_1m_base")       # 一月報酬所用基準日=收盤
                item["ret_1w_div"] = r.get("ret_1w_div")         # 區間內加回的除息（總報酬口徑）
                item["ret_1m_div"] = r.get("ret_1m_div")
                got_ret += 1
            # 當日漲跌：序列末兩點；本次算不出就保留既有值（絕不洗成空白）
            if r.get("chg_pct") is not None:
                for k in ("chg_pct", "chg_amt", "prev_close", "prev_date", "chg_ex_div"):
                    item[k] = r.get(k)
                # 漲跌所屬交易日＝序列末日（供渲染端判斷是否與收盤價同日；L1 會覆寫成 as_of）
                item["chg_asof"] = str(r["perf_date"])[:10] if r.get("perf_date") else None
                item["chg_src"] = r.get("ret_src")
            # etfinfo 未收錄（上櫃 00998A/00986D）→ 收盤價用報酬序列最新收盤回填
            if item.get("close_px") is None and r.get("last_close") is not None:
                item["close_px"] = round(float(r["last_close"]), 2)
                if item.get("as_of") is None and r.get("perf_date"):
                    item["as_of"] = str(r["perf_date"])[:10]
        except Exception as e:
            print(f"  ⚠ {code} 報酬抓取失敗（沿用既有值／週報底稿）：{e}")

        # ②-b 當日漲跌備案 L1＝官方全市場當日收盤表（2026-09-03 使用者：「沒辦法從其他
        # 地方補嗎？」）──序列缺當日 bar 時的**第一順位**備案：TWSE／TPEx openapi 直接給
        # 當日 close 與 change，官方權威（非 Tier B）、整輪只 2 請求、市價口徑與 close_px 一致。
        # 漲跌基準 ref＝close − change：除息日證交所的 change 本就對「除息參考價」計算，
        # 與 _returns_from_series 的除息處理同口徑，不必另外扣息。
        # 以來源自報的 date 當 chg_asof——官方表若自己也落後，渲染端的日期判準會照樣揭露。
        # 判準是「≠ as_of」而非「< as_of」（2026-09-21）：序列日期**超前**收盤價時同樣
        # 不可信——實測超前只有兩種來路，都是壞資料：①週末／未來的假 bar（9/20 那次）；
        # ②盤中未收盤的 partial bar（9/17 09:28 那輪 0050 給 +2.07%，收盤實為 +1.69%）。
        # 舊版只擋「落後」，超前反而直接勝過官方備案並繞過渲染端過期章＝完全靜默。
        ao = item.get("as_of")
        if ao and (not item.get("chg_asof") or item["chg_asof"] != ao):
            q = day_q.get(code) or {}
            qc, qch, qd = q.get("close"), q.get("change"), q.get("date")
            if qc and qch is not None and qd:
                ref = round(qc - qch, 4)
                if ref:
                    item["chg_amt"], item["chg_pct"] = round(qch, 4), round(qch / ref * 100, 2)
                    item["prev_close"], item["prev_date"] = ref, None   # 官方表不給前一交易日日期
                    item["chg_ex_div"] = None
                    item["chg_asof"], item["chg_src"] = str(qd)[:10], "twse_today"
                    got_chg_off += 1

        # ②-c 當日漲跌備案 L2＝etfinfo 自帶前收自算（官方當日表也拿不到時的零請求退路）──
        # 序列缺當日 bar 時（Yahoo 對台股 ETF 的當日日線不穩定，實測會跳動甚至倒退），
        # 末兩點會退成「前一交易日 vs 再前一日」，與 etfinfo 當日收盤價差一天並排、方向可能
        # 相反（2026-09-02：0050 收 106.80 實跌約 1.5%，序列卻給 +2.07%＝9/1 的漲幅）。
        # 備案＝改用 etfinfo 自己的前一個資料日收盤（prev_px）自算：與 close_px 同源同口徑、
        # 零額外請求。僅在序列與官方當日表都給不出當日時接手；序列夠新時一律讓序列走
        # （它帶除息還原資訊）。
        ao = item.get("as_of")
        if ao and (not item.get("chg_asof") or item["chg_asof"] != ao):   # 同上：超前也算不一致
            ppx, ppd = item.get("prev_px"), item.get("prev_px_date")
            px = item.get("close_px")
            if px is not None and ppx is not None and ppd and ppd < ao:
                # 除息日仍以「除息參考價＝前收 − 每單位配息」為基準（同 _returns_from_series；
                # etfinfo 是市價、跨除息不還原，不扣就會把整段配息算成跌幅）
                exd = round((_DIV_EVENTS.get(code) or {}).get(ao) or 0, 4)
                ref = round(ppx - exd, 4) if exd else ppx
                if ref:
                    item["chg_amt"] = round(px - ref, 4)
                    item["chg_pct"] = round((px / ref - 1) * 100, 2)
                    item["prev_close"], item["prev_date"] = ppx, ppd
                    item["chg_ex_div"] = exd or None
                    item["chg_asof"], item["chg_src"] = ao, "etfinfo_prev"
                    got_chg_l1 += 1

        # ③ 當月預估配息（僅取本月、除息日尚未到期者）：etfinfo 未揭露預告時，
        #    依序補 MOPS 公告 → 投信已公告人工清單 ANNOUNCED_EST（etfinfo/MOPS 皆抓不到時的可靠來源）。
        # 沿用舊檔的預估值也要重新驗期（審查 2026-07-18）：etfinfo 斷源期間跨過除息日/跨月時，
        # 過期的「預估 X*」不得繼續顯示（docstring 承諾「過月自動失效」）。
        if item.get("est_div") is not None:
            try:
                _exd = (date.fromisoformat(item.get("est_div_date"))
                        if item.get("est_div_date") else None)
            except ValueError:
                _exd = None
            if not (_exd and _exd.year == today.year and _exd.month == today.month
                    and _exd >= today):
                item["est_div"], item["est_div_date"] = None, None
        if item.get("est_div") is None:
            for src_name, cand in (("mops", mops_dist.get(code)),
                                   ("announced", ANNOUNCED_EST.get(code))):
                ex = (cand or {}).get("ex_date")
                amt = (cand or {}).get("amount")
                try:
                    exd = date.fromisoformat(ex) if ex else None
                except ValueError:
                    exd = None
                if (exd and exd.year == today.year and exd.month == today.month
                        and exd >= today and amt is not None):
                    item["est_div"], item["est_div_date"], item["est_src"] = amt, ex, src_name
                    got_est += 1
                    break

        # ④ 換算年化配息率：有當月預估配息時，改用「預估配息 × 年配息次數 ÷ 最新收盤價」（新聞口徑）
        #    並標記 yield_is_est；否則維持最近一次「實際」配息年化。
        n = _FREQ_PER_YEAR.get(item.get("freq") or "")
        if item.get("est_div") is not None and item.get("close_px") and n:
            item["yield_pct"] = round(item["est_div"] / item["close_px"] * n * 100, 2)
            item["yield_is_est"] = True
        else:
            item["yield_is_est"] = False
            # etfinfo 沒給殖利率（如上櫃檔）但有配息＋收盤＋頻率 → 以同公式自算，
            # 取代種子的靜態口徑值（配息實際值接上後隨市價浮動）。
            if (not yield_from_src and item.get("last_div") is not None
                    and item.get("close_px") and n):
                item["yield_pct"] = round(item["last_div"] / item["close_px"] * n * 100, 2)

        items.append(item)
    got = got_mkt + got_ret
    # L1 備案用量進 CI 日誌：常態應為 0，持續非 0＝主序列的當日 bar 長期缺（該查來源端）
    if got_chg_off or got_chg_l1:
        print(f"  ℹ 當日漲跌走備案：官方當日表 {got_chg_off} 檔、etfinfo 前收自算 {got_chg_l1} 檔"
              f"——主序列缺當日 bar，非資料錯誤；持續發生請查 Yahoo/stooq 當日日線")
    # 假 bar 剔除摘要（2026-09-21）：常態應為 0 行。多檔同時出現同一個日期＝來源整批回了
    # 不可能的交易日（9/20 那次 36 檔全中），這行是唯一看得見它的地方。
    if _BAD_BARS:
        dates = sorted({d for ds in _BAD_BARS.values() for d in ds})
        print(f"  ⚠ 已剔除來源回傳的「不可能交易日」bar：{len(_BAD_BARS)} 檔、日期 {dates}"
              f"——未來日或週末日，採信會汙染當日漲跌與週／月報酬（2026-09-21 踩坑）")
    as_of = max((i.get("as_of") or "" for i in items), default="") or \
        (load() or {}).get("as_of") or clock.today_tw().isoformat()
    est_note = f"；當月預估配息 ← 投信公告／MOPS（{got_est} 檔）" if got_est else ""
    if got_ret:
        src_note = ("規模／配息殖利率 ← etfinfo.tw（Tier B）；過去一週／一月報酬 ← Yahoo 還原收盤"
                    f"（總報酬口徑）／FinMind／TWSE 官方自算{est_note}。正式對外前以各投信官網核對")
    elif got_mkt:
        src_note = ("規模／配息殖利率 ← etfinfo.tw（Tier B）；報酬沿用最近可得週報底稿"
                    f"（報酬來源本次不可達）{est_note}。正式對外前以各投信官網核對")
    else:
        src_note = "沿用既有落檔／週報底稿（本次來源皆不可達）"
    return {
        "as_of": str(as_of)[:10],
        "perf_asof": max((i.get("perf_asof") or "" for i in items), default="") or SEED_ASOF,
        "fetched_at": clock.stamp_tw("%Y/%m/%d %H:%M"),
        "source": src_note,
        "items": items,
    }


def is_empty(doc: dict | None) -> bool:
    """全部項目連「規模／週報酬」都沒有 → 視為來源異常，不是真的沒資料。"""
    if not doc or not doc.get("items"):
        return True
    return not any(i.get("aum_e8") is not None or i.get("ret_1w") is not None
                   for i in doc["items"])


def save(doc: dict) -> tuple[Path, bool]:
    """落檔。防呆：本次全空且既有落檔非空 → 保留舊檔不覆寫（回 saved=False）。"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if is_empty(doc) and not is_empty(load()):
        return OUT, False
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return OUT, True


def load() -> dict | None:
    """儀表板用：讀最近一次落檔；無檔回 None（分頁顯示提示、不壞版）。
    WATCHLIST 新增而落檔尚無的檔（CI 還沒抓）→ 以靜態值補 stub（代碼/名稱/性質/成立日先上、
    數據欄顯示 —），下輪 CI 抓到即被真值覆蓋——新增追蹤標的不用等隔天才看得到。"""
    try:
        doc = json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    have = {i.get("code") for i in doc.get("items") or []}
    statics = {c: (k, cat) for c, _n, k, cat, _i in watch_tuples()}
    for code, name, kind, cat, inception in watch_tuples():
        if code not in have:
            doc.setdefault("items", []).append(
                {"code": code, "name": name, "kind": kind, "cat": cat, "inception": inception,
                 # 配息頻率是查證靜態值（SEED 或募集公告）——stub 期也照實顯示，別留 —
                 "freq": (SEED_PERF.get(code) or {}).get("freq")
                         or next((it.get("freq") for it in UPCOMING
                                  if it["code"] == code and it.get("freq") != "—"), None)})
    # kind／cat 屬顯示分組的靜態值，一律以當前 WATCHLIST 為準覆蓋落檔舊值——
    # 否則改分組（如 2026-08-28 上櫃檔 other→active）要等下輪 CI 重抓才生效（同成立日慣例）。
    for i in doc.get("items") or []:
        st = statics.get(i.get("code"))
        if st:
            i["kind"], i["cat"] = st
    # 顯示順序照代碼字典序（2026-08-05 使用者：「績效那邊照代碼編號排序，不然有點亂」）。
    # 在 load() 這個單一入口排——績效表、詳情卡、代碼泡泡三處順序自動一致；
    # 落檔本身仍保持抓取順序（rows() 有自己的 WATCHLIST 序，資料層不受影響）。
    (doc.get("items") or []).sort(key=lambda i: str(i.get("code") or ""))
    return doc
