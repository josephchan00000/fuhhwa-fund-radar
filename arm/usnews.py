"""昨夜美股新聞（復華基金追蹤版本）—— 兩版型規格常數 ＋ 產出讀取 ＋ 合規掃描。

即時新聞需要「會上網查證的 LLM」，純 Python 無法自動生成 → 沿用本專案 prompt-pack 哲學：
  · scripts/gen_usnews.py 產一份『可貼進 Claude 的提示包』（reports/usnews/prompts/{date}.md），
    內含兩版型完整規格＋當日日期＋昨夜美股交易日；
  · Claude 產兩份 markdown 回存 reports/usnews/{date}_v1.md（Top3 速寫包）與 _v2.md（精簡版）；
  · dashboard / 報告讀「最新一份」呈現，並跑合規掃描標注。

本檔只放：規格文字、讀取器、合規禁用詞掃描（純函式、可單測）。
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

from . import clock

ROOT = Path(__file__).resolve().parent.parent
NEWS_DIR = ROOT / "reports" / "usnews"

# 新聞版型硬性禁用詞（用戶規格 F ＋ compliance 絕對化字眼）
BANNED = ["保證", "穩賺", "必賺", "包賺", "必漲", "必跌", "一定會", "唯一",
          "建議買賣", "建議買", "建議賣", "目標價", "零風險", "無風險", "穩賺不賠"]

# 機構觀點須以此類語氣呈現（提醒用）
ATTRIBUTION_HINT = "該機構表示／認為／估測（日期）"

# 事件屬性（二擇一）與重要度評分準則——寫進提示包，並由 extract_cards 解析成徽章。
ETYPE_RULE = ("消息屬性（二擇一，放標題括注）：【新事件】＝過去 24–48 小時內首次曝光；"
              "【延伸】＝既有事件的新進展／二度報導／專欄（若僅重複舊聞須註明非首發）。")

SEV_RUBRIC = ("重要度（1–10 分，放標題括注『重要度 N/10』；**只列入 6 分（含）以上**，其餘捨棄）：\n"
              "  9–10＝結構性衝擊（衝擊大盤或整條產業鏈：龍頭財報暴雷／重大併購／政策級監管／權值股隔夜 ±5% 以上）；\n"
              "  7–8＝重要個股或次產業明顯影響（單一標的隔夜 ±2–5%、關鍵財測／大訂單／法說指引／重大人事）；\n"
              "  6＝值得追蹤但影響侷限（次級題材、分析師評價調整、單一中型股事件）；\n"
              "  ≤5＝不列入（雜訊／純 Fed 利率大盤／重複舊聞）。")

# 重點標記＋內容主軸——儀表板把 **粗體** 渲染成「半透明藍底關鍵句」
# （2026-07-18 使用者指示全站抓重點；07-19 檢討：標「事實」不標「情緒」、禁投顧風主軸）。
HILITE_RULE = ("重點標記（標「事實」、不標「情緒」）：每卡的「新聞摘要」與各影響欄，用 **粗體** 標出 "
               "1–2 處『事實性關鍵』——①紀錄性事實與關鍵數字（**史上最大收盤跌點**、**−6.47%**、"
               "**賣超 2,617 億**）；②清單型重點標『內容本身』而非名目：「三大止跌訊號」→ 粗體標 "
               "**費半回穩、新台幣止貶、權值股率先止跌** 這三項，不是標「三大止跌訊號」四個字；"
               "③關鍵日期與檢核點（**7/20 T+2 交割日**、**季線 43,525**）。不可標：情緒與模糊判斷"
               "（多空分歧明顯／情緒偏謹慎／觀望氣氛濃）、名人個人進出與金額、空泛形容句。"
               "每欄至多 2 處、標短語不標整句；總覽段與行事曆重點框同規則。\n"
               "內容主軸：卡片標題與主體以「可查證事實」為軸——官方統計、公司公告、交易所／主管機關"
               "措施、具名機構研究；名嘴／投顧的個人進出與情緒性敘事不得作為標題或主軸（至多段內"
               "輔助引用一句並標明屬個人觀點），標題寫事實、不寫聳動語（「砸 8 位數進場」「算帳的"
               "時刻」之類留給來源原題）。\n"
               "數量與密度：重大事件延續期（史上級波動、政策巨變後的週末／休市日）以 5–7 卡為目標，"
               "把主事件的分支（籌碼／制度／公司／政策／國際連動）分卡呈現，勿讓讀者當日只見零星卡片。\n"
               "數據口徑（2026-07-20 教訓：外資淨空單誤引彙整站快照）：期貨／籌碼類數字（未平倉口數、"
               "買賣超金額）一律以官方口徑為準——台股期貨用期交所盤後「三大法人—區分各期貨契約」的"
               "臺股期貨(TX)外資『多空淨額』並附基準日；彙整站（玩股網等）與媒體標題常混用『空方總"
               "口數 vs 淨額』或把大台／小台／微台不同契約合計，須**兩個獨立來源數字一致**才可引用，"
               "不一致時取官方值或誠實列入資料侷限。美股指數（尤其費半 SOX）媒體極少刊收盤點位："
               "**嚴禁用前收自行推算點位**、嚴禁引盤中快照當收盤；漲跌%與點位皆須兩獨立來源一致，"
               "查不到就只寫方向、把數字缺口列入資料侷限（費半曾連三日出錯：週跌幅誤植／盤中快照"
               "當收盤／同日兩報 3.7% vs 5.21% 矛盾——寧缺勿錯）。")

# 來源優先序（2026-07-20 使用者指示：新聞以主流媒體為主）。美股／總經與台股各一份，
# 由各版型注入；違反時卡片仍可收，但查證代理應優先替換成主流媒體原文連結。
SRC_RULE_GLOBAL = (
    "來源優先序（以主流媒體為主）：首選 **華爾街日報（WSJ）／Financial Times／CNN／Reuters／"
    "Bloomberg／CNBC／富途牛牛（news.futunn.com）**，次選 Fortune／Axios／Yahoo Finance／"
    "Barron's 等具名財經媒體；**每卡參考資料至少 1 條上述主流媒體原文連結**。聚合站與二手彙整"
    "（ts2.tech、KuCoin News、cryptobriefing、內容農場等）只能當補充出處、不得為一卡的唯一來源；"
    "同一事件有主流媒體報導時，優先引主流媒體版本。")
SRC_RULE_TW = (
    "來源優先序（以主流媒體為主）：**以經濟日報（money.udn.com）為主要來源**——選題與查證"
    "優先掃經濟日報，其次才是 **工商時報／中央社／聯合新聞網／鉅亨網**，"
    "次選 Yahoo奇摩股市、財訊／今周刊等具名台灣財經媒體；"
    "**每卡參考連結至少 1 條上述主流媒體原文連結**。彙整站與內容農場只能當補充出處、"
    "不得為一卡的唯一來源（「富聯網 moneylink」維持黑名單、一律排除）。")

# 深度報告精選——每日保底 1 篇（2026-07-04 使用者需求：要更多深度報告）。
# {src} 由各市場版型帶入建議訊源。
DEEP_RULE = ("🔹深度報告精選（**保底 1 篇、上不封頂**）：從 {src} 中挑當日（不足時放寬到近 3 天內"
             "並註明刊出日）最有價值的深度分析／專題報導（產業鏈拆解、商業模式、政策影響評估、"
             "長線趨勢），版型同新聞卡，但標題括注第二段改用【深度】"
             "（來源＋日期＋TST｜【深度】｜重要度 N/10），並在摘要後多加一行「**為什麼值得讀**」。"
             "只挑真正有深度者（拒絕即時快訊充數）；查證原文可點連結必附。")

_SEV_RE = re.compile(r"重要度\s*(\d{1,2})")


def _card_importance(meta: str) -> int | None:
    """從卡標題括注解析『重要度 N/10』→ 1–10 的整數；無則 None。"""
    m = _SEV_RE.search(meta or "")
    if not m:
        return None
    n = int(m.group(1))
    return n if 1 <= n <= 10 else None


def _card_etype(meta: str) -> str | None:
    """從卡標題括注判定事件屬性：'new'（新事件）／'ext'（延伸）／'deep'（深度報告）／None。"""
    t = meta or ""
    if "深度" in t:
        return "deep"
    if "新事件" in t or "新消息" in t:
        return "new"
    if "延伸" in t or "事件更新" in t:
        return "ext"
    return None

DISCLOSURE = (
    "本資料僅供參考，非屬投資建議或招攬；本文所載資料多引自公開來源，已於文末列示出處，"
    "本公司不保證其完整、即時或正確，亦不負損益責任。基金投資有風險，申購前應詳閱公開說明書／"
    "投資人須知；過去績效不代表未來表現，淨值可能因市場變動而上下。境外基金涉及匯率與國際市場"
    "風險；使用衍生性商品者另涉及槓桿、流動性與對手風險。"
)

# 版型一：〈昨夜美股公司與產業面速寫包〉（完整版）
SPEC_V1 = f"""【版型一：昨夜美股公司與產業面速寫包（完整版）】
範圍：只收「公司與產業動因」（AI/晶片/雲端/電動車/通訊/製造鏈；企業合作、併購、
產品發表、重大投資/資本支出；財報/財測/營收預告、公司聲明；供應鏈調整、人事異動；
具實質營運影響的監管/法律事件）。排除單純 Fed/利率/大盤漲跌。
{SRC_RULE_GLOBAL}
可各補 ≤1 段 JPMorgan/Goldman Sachs/Morgan Stanley/BlackRock 當日評論（附日期）。
每則附來源連結與台北時間戳（例：2026/07/02 05:30 TST）。

【數量與門檻】盡量多找：**至少 4 則、上不封頂**，把當夜所有「重要度 6 分以上」的公司/產業事件全數收錄，
寧多勿漏；不足時擴大次級題材（法說會效應／分析師報告／行業趨勢）到 6 分線為止。排序：先依重要度高→低，
同分再新→舊。

{ETYPE_RULE}
{SEV_RUBRIC}
{HILITE_RULE}

版面：
  🔹前後 24 小時重大公司與產業事項總覽（Nasdaq／費半／S&P500 各 1 句 ＋ 1 句市場解析：主題動能與板塊輪動）
  🔹新聞卡（每則 120–180 字；≥4 則）：
     標題（來源＋日期＋TST｜【新事件】或【延伸】｜重要度 N/10）  ← 括注三段缺一不可，供儀表板解析徽章
     1. 新聞摘要（2–3 句聚焦事實） 2. 一句話重點 3. 對公司影響
     4. 對競爭者／合作方影響 5. 對市場情緒與股價影響
     6. 參考資料（逐條列來源與機構評論日期；**每卡至少 1 條以 [標題](URL) markdown
        格式附可點的原文連結**，儀表板「新聞重點」卡會直接取用）
  {DEEP_RULE.format(src="富途牛牛深度文章（news.futunn.com）、Reuters Analysis／Bloomberg 深度專題、WSJ／FT 專欄")}
  I. 合規揭露（附完整揭露段）
用語合規：僅市場資訊彙編/教育用途、非投資建議；禁用詞見 BANNED；機構觀點以
『該機構表示／認為／估測（日期）』呈現；不預測報酬、不以過去績效推未來。
若查無足量或無法查證，誠實加「資料侷限說明」，切勿杜撰。"""

# 版型二：昨夜美股重點（精簡版）
SPEC_V2 = f"""【版型二：昨夜美股重點（精簡版）】
聚焦 Nasdaq／費城半導體／S&P500，只收公司行為或產業動因（AI 投資、企業合作、併購、
產品發表、產業鏈合作、財報/財測、重大投資/資本支出、供應鏈調整、人事異動、監管/法律事件），
不含單純 Fed/利率/大盤漲跌。
{SRC_RULE_GLOBAL}

【數量與門檻】盡量多找：**至少 4 則、上不封頂**，收錄所有「重要度 6 分以上」者，寧多勿漏。
排序：先依重要度高→低，同分再新→舊。

{ETYPE_RULE}
{SEV_RUBRIC}
{HILITE_RULE}

每則輸出：
  新聞標題（來源 + 日期｜【新事件】或【延伸】｜重要度 N/10）  ← 括注三段缺一不可
  1. 新聞摘要 2. 濃縮成一句話（簡短有力） 3. 對公司影響 4. 對競爭者/合作方影響 5. 對市場情緒與股價影響
  6. 參考連結（每卡至少 1 條 [來源標題](URL) markdown 可點連結）
末尾附合規短語（非投資建議）。"""


_LANE = {
    "tw": "**台股本位**：台股大盤與個股、族群與供應鏈、公司公告與法說、官方統計（主計總處／"
          "財政部／經濟部）、交易所措施、官方籌碼（三大法人／期貨／融資券）、除權息與新股。",
    "macro": "**國際政策與總體本位**：白宮／關稅／對中政策、聯準會與各國央行、地緣政治與戰事、"
             "制裁與出口管制，以及它們對全球經濟與資產價格（美債／美元／油金／主要股指）的影響。",
    "us": "**美股公司與產業本位**：美股個股與產業鏈事件——財報財測、併購合作、產品與資本支出、"
          "供應鏈與人事、具營運影響的監管訴訟。",
}


def lane_note(kind: str) -> str:
    """各報分工：三份報告切開來、不要混成同一篇（2026-08-03 使用者指示）。

    緣起：同日稍早曾試過「週一台股報告以國際事件領銜」，使用者看過後回覆
    「感覺新聞變成都一樣了，還是要切開來…不要混在一起」——那版讓台股報告
    變成總經報告的翻版。故改為各報守自己的領域，累進時窗只在各自範圍內做。
    kind＝tw/macro/us。"""
    lane = _LANE.get(kind)
    if not lane:
        return ""
    extra = ""
    if kind == "tw":
        extra = ("\n  · 國際事件（戰事、央行、關稅、油價、國際大廠消息）**原則上留給總經／美股報告**；"
                 "只有在**直接牽動台股**時才收，且**只寫「對台股哪些族群／個股／供應鏈的影響」那一面**，"
                 "不要重述事件本身的來龍去脈與全球資產分析——那會讓本報變成總經報告的翻版。"
                 "\n  · 台股當日新聞量少時（週末／連假），**往前累進到週五盤中／盤前補真正發生過的"
                 "台股事件**（公司公告、法說、官方統計、籌碼、交易所措施），而不是改抄國際新聞。")
    return (f"【本報守備範圍（重要）】{lane}{extra}\n"
            "  · 三份報告（台股／總經／美股）**要切開來、各寫各的領域**，不要三份都在寫同一批事件；"
            "讀者是把三份當成三個不同視角在看的。")


def weekend_note(today: date | None = None) -> str:
    """週末／週一提示包的「合併時窗」規則（2026-07-05 使用者需求）。

    週六＝涵蓋週五晚間（美股週五交易時段／台股週五盤後）起；週日＝再含週六全日；
    週一＝把週五晚間＋週六＋週日整個週末的重要新聞一次綜合整理，不可只看最近一天。
    平日（週二~週五）回空字串。三類新聞（usnews/twnews/macronews）提示包共用。"""
    d = today or clock.today_tw()
    names = {5: "週六", 6: "週日", 0: "週一"}
    spans = {5: "上一交易日（週五）台股盤後／美股週五交易時段起至今",
             6: "週五台股盤後／美股週五交易時段起、涵蓋週六全日至今",
             0: "週五台股盤後／美股週五交易時段起、涵蓋週六與週日整個週末至今晨"}
    wd = d.weekday()
    if wd not in names:
        return ""
    base = (f"【週末合併時窗】今日為{names[wd]}：本次彙編收錄時窗擴大為「{spans[wd]}」，"
            "把這段期間最重要的新聞一次綜合整理（依重要度高→低排序、寧多勿漏），"
            "切勿只收錄最近一天；先前日報已報導者不得原樣重收，有新進展標【延伸】並註明。")
    # 2026-08-03 使用者回報：週末新聞量少，子代理改用投顧看法／預告性內容湊卡數，
    # 週一那份「一點都不重要」。稀疏時的取捨規則講明白，並要求週一以國際事件領銜。
    thin = ("【週末新聞稀疏時的取捨（重要）】週末本來就少新聞，**寧可少 1～2 卡，也不要用"
            "『投顧／分析師看後市』『法人估某數字』『本週有哪些事要公布』這類看法與預告湊卡數**"
            "——這類內容不是事件、重要度一律視為 5 分以下不得入卡（機構觀點只能放在某張事件卡"
            "的段內輔助引用一句）。卡數不足時，正確作法是**把時窗往前延伸到週五盤中／盤前**"
            "把當時真正發生、且尚未報導過的事件補進來，而不是改用預測性內容。")
    return base + "\n" + thin


def us_session_date(today: date | None = None) -> date:
    """給定台北日期，回傳『昨夜美股』對應的美股交易日（最近一個美股工作日）。

    台北 D 日早上收的美股＝美東 D-1；週一早上對應的最近美股交易日為上週五（略過假日，
    提示包會請 Claude 自行以實際交易日查證）。"""
    d = (today or clock.today_tw()) - timedelta(days=1)
    while d.weekday() >= 5:      # 5=Sat, 6=Sun
        d -= timedelta(days=1)
    return d


# ── 交易日曆錨定 ＋ 前一日已報導清單（2026-07 效率優化）──
# 動機：查證代理常花數次搜尋去自行釐清「今日星期幾／昨夜美股是否休市／上一交易日是哪天」，
# 且會重覆查證前一日已報導的舊聞。把這兩件事「系統算好、直接寫進提示包」＝純提示、不影響
# 查證深度，卻可省下代理的釐清與重查時間（實測每次約 2–4 分）。

_WD = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]

# NYSE／Nasdaq 2026 全日休市日（美股）——僅供提示錨定，實際以交易所公告為準。
# 7/4（美國國慶）2026 適逢週六，故 7/3（五）補假休市。
_US_MKT_HOLIDAYS_2026 = {
    date(2026, 1, 1): "元旦", date(2026, 1, 19): "馬丁路德金恩日",
    date(2026, 2, 16): "總統日", date(2026, 4, 3): "耶穌受難日",
    date(2026, 5, 25): "陣亡將士紀念日", date(2026, 6, 19): "六月節",
    date(2026, 7, 3): "美國國慶補假（7/4 適逢週六）", date(2026, 9, 7): "勞動節",
    date(2026, 11, 26): "感恩節", date(2026, 12, 25): "耶誕節",
}


def _prev_us_trading_day(d: date) -> date:
    """從 d 起（含 d）往回找最近一個美股實際交易日（跳週末＋已知國定假日）。"""
    x = d
    while x.weekday() >= 5 or x in _US_MKT_HOLIDAYS_2026:
        x -= timedelta(days=1)
    return x


def calendar_anchor(today: date | None = None) -> str:
    """系統算好『今日星期幾／對應昨夜美股實際交易日／鄰近美股休市日』，寫進提示包，
    讓查證代理不必自行推算星期與假日（這是 2026-07 觀察到最常見的空轉來源）。純提示、
    不縮減查證範圍。"""
    d = today or clock.today_tw()
    ses = us_session_date(d)              # 僅跳週末（沿用既有契約/測試）
    real = _prev_us_trading_day(ses)      # 再跳國定假日 → 真實最近交易日
    lines = ["【交易日曆錨定（以下為系統計算，勿再自行推算星期或假日；仍以交易所公告為準）】",
             f"· 台北今日：{d:%Y/%m/%d}（{_WD[d.weekday()]}）"]
    if real != ses:
        skipped = "、".join(f"{h:%m/%d}（{_WD[h.weekday()]}）{_US_MKT_HOLIDAYS_2026.get(h, '休市')}"
                            for h in (ses - timedelta(n) for n in range((ses - real).days))
                            if h.weekday() < 5 and h in _US_MKT_HOLIDAYS_2026)
        note = f"（{skipped} 美股休市，故往回取）" if skipped else ""
        lines.append(f"· 對應昨夜美股實際交易日（美東）：{real:%Y/%m/%d}（{_WD[real.weekday()]}）{note}")
    else:
        lines.append(f"· 對應昨夜美股交易日（美東）：{ses:%Y/%m/%d}（{_WD[ses.weekday()]}）")
    covered = {h.year for h in _US_MKT_HOLIDAYS_2026}
    if d.year not in covered or ses.year not in covered:
        lines.append("· ⚠ 系統假日表未涵蓋本年份——請自行以 WebSearch 確認美股休市日，勿逕信上列推算")
        return chr(10).join(lines)
    near = [(h, name) for h, name in sorted(_US_MKT_HOLIDAYS_2026.items()) if abs((h - d).days) <= 4]
    if near:
        lines.append("· 鄰近美股休市日：" +
                     "；".join(f"{h:%m/%d}（{_WD[h.weekday()]}）{name}" for h, name in near))
    else:
        lines.append("· 本週美股無鄰近國定假日、正常交易")
    return "\n".join(lines)


def prior_titles(news_dir, today: date, stem_re: str = r"(\d{4}-\d{2}-\d{2})\.md$",
                 limit: int = 16) -> list[str]:
    """讀 news_dir 內『日期 < today』最新一份報告的卡標題（沿用 extract_cards）。
    供提示包「已報導清單」用——今日若僅重複舊聞即可略過、不必重查。找不到回 []。"""
    p = Path(news_dir)
    if not p.exists():
        return []
    today_s = f"{today:%Y-%m-%d}"
    by_date: dict[str, Path] = {}
    for f in p.glob("*.md"):
        m = re.match(stem_re, f.name)
        if m and m.group(1) < today_s:
            by_date.setdefault(m.group(1), f)
    if not by_date:
        return []
    md = by_date[max(by_date)].read_text(encoding="utf-8")
    return [c["title"] for c in extract_cards(md) if c.get("title")][:limit]


def prior_block(titles: list[str], scope_label: str = "前一日日報") -> str:
    """把已報導標題清單格式化成提示段落；空清單回空字串（提示包會略過）。"""
    if not titles:
        return ""
    items = "\n".join(f"  - {t}" for t in titles)
    return (f"【已報導清單（{scope_label}，勿原樣重收）】\n"
            "以下為最近一份日報已收錄之事件；今日若僅為重複舊聞請直接略過、不要重新查證，"
            "唯有實質新進展才收錄、標【延伸】並以一句話註明「新在哪」：\n" + items)


# 否定詞：緊鄰禁用詞前方者視為合規揭露語（沿用 arm/copy/compliance.py 的 _NEG 慣例）。
_NEG = ("非", "不", "無", "未", "免")


def compliance_scan(text: str) -> list[str]:
    """回傳文中出現的禁用詞（去重）。空＝乾淨。

    命中禁用詞時，若其前兩字內含否定詞（非／不／無／未／免），視為合規揭露語（如『並非保證』
    『並非無風險』『非零風險』『不保證』），不計入違規；避免把必附揭露或否定句誤判為違規。"""
    t = text or ""
    hits: set[str] = set()
    for w in BANNED:
        i = t.find(w)
        while i != -1:
            prev = t[max(0, i - 2):i]
            if not any(n in prev for n in _NEG):
                hits.add(w)
                break                      # 出現一次未被否定即算違規
            i = t.find(w, i + 1)           # 此處被否定，繼續找下一個同詞
    return sorted(hits)


# ── 結構化萃取（供儀表板「今日重點」「新聞重點」「新聞×持股連動」使用；萃取失敗回空、不擋版面） ──

# 隱形/控制字元（零寬空白、方向控制、BOM、軟連字號）——來源複製貼上常夾帶，
# 部分字型會顯示為亂碼方框；渲染與萃取前一律刷掉。
_INVISIBLE = re.compile("[\\u00ad\\u200b-\\u200f\\u2028\\u2029\\u2060\\ufeff]")


def scrub(text: str) -> str:
    """去隱形/控制字元。"""
    return _INVISIBLE.sub("", text or "")


_IDX_LABELS = [(("那斯達克", "Nasdaq", "NASDAQ"), "Nasdaq"),
               (("費城半導體", "費半", "SOX"), "費半 SOX"),
               (("標普", "S&P"), "S&P 500")]


def extract_indices(md: str, labels: list[tuple[tuple[str, ...], str]] | None = None) -> list[dict]:
    """從新聞 markdown 的指數速覽／總覽條列萃取指數收盤與漲跌幅。

    labels 預設美股三大指數；twnews 傳台股標籤組。
    回 [{label, close, pct, up}]（依 labels 順序、去重取首見）；解析不到回 []。"""
    _IDX = labels if labels is not None else _IDX_LABELS
    out: dict[str, dict] = {}
    for line in scrub(md).splitlines():
        m = re.match(r"^\s*[-*]\s+\*\*(.+?)\*\*[：:](.*)$", line)
        if not m:
            continue
        label_raw, body = m.group(1), m.group(2)
        label = next((std for keys, std in _IDX
                      if any(k in label_raw for k in keys)), None)
        if not label or label in out:
            continue
        mc = re.search(r"收\s*([0-9][0-9,]*(?:\.\d+)?)", body)
        mp = re.search(r"(上漲|下跌)約?\s*([0-9]+(?:\.\d+)?)\s*%", body)
        if not (mc and mp):
            continue
        out[label] = {"label": label, "close": mc.group(1),
                      "pct": float(mp.group(2)), "up": mp.group(1) == "上漲"}
    order = [std for _, std in _IDX]
    return sorted(out.values(), key=lambda d: order.index(d["label"]))


# 卡片標頭三型：①「### 卡 N｜…」②「## 一、…」③裸標題但尾端帶（…重要度 N/10）括注
# （③為容錯：LLM 產卡偶爾漏「卡 N｜」前綴——2026-07-15 總經報實測；總覽/合規等
#   小節標題不帶重要度括注，不會誤判）
_CARD_HEAD = re.compile(
    r"^#{2,3}\s+(?:(?:卡\s*\d+｜|[一二三四五六七八九十]+、)(.+)"
    r"|(.+（[^（）]*重要度\s*\d+\s*/\s*10[^（）]*）))\s*$")
_MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")


def extract_cards(md: str) -> list[dict]:
    """切出新聞卡（v1『### 卡 N｜…』／v2『## 一、…』／裸標題帶重要度括注）。

    回 [{title, meta, oneline, summary, points, links, body}]：
      title＝去尾端括注的標題；meta＝尾端（來源：…｜日期｜…）括注內容；
      oneline＝『一句話重點／一句話』行；summary＝『新聞摘要』行；
      points＝影響條列 [(標籤, 內文)]（對公司影響／對持股・族群影響／對市場情緒…）；
      links＝卡內 markdown 連結 [(文字, URL)]（原文出處）。缺者為空。"""
    cards: list[dict] = []
    cur: dict | None = None
    for line in scrub(md).splitlines():
        m = _CARD_HEAD.match(line.strip())
        if m:
            raw = (m.group(1) or m.group(2)).strip()
            meta = ""
            mm = re.search(r"（([^（）]*)）\s*$", raw)
            if mm:
                meta, raw = mm.group(1).strip(), raw[:mm.start()].strip()
            cur = {"title": raw, "meta": meta, "oneline": "", "summary": "",
                   "importance": _card_importance(meta), "etype": _card_etype(meta),
                   "points": [], "links": [], "body": ""}
            cards.append(cur)
            continue
        if line.strip().startswith(("## ", "---")) and not _CARD_HEAD.match(line.strip()):
            cur = None                        # 卡片群結束（次級觀察/合規段等）
            continue
        if cur is not None:
            cur["body"] += line + "\n"
            mo = re.match(r"^\s*\d*\.?\s*\*\*一句話(?:重點)?\*\*[：:]\s*(.+)$", line)
            if mo and not cur["oneline"]:
                cur["oneline"] = mo.group(1).strip().rstrip("。")
            ms = re.match(r"^\s*\d*\.?\s*\*\*新聞摘要\*\*[：:]\s*(.+)$", line)
            if ms and not cur["summary"]:
                cur["summary"] = ms.group(1).strip()
            mp = re.match(r"^\s*\d+\.\s*\*\*((?:對|市場情緒)[^*]{1,20})\*\*[：:]\s*(.+)$", line)
            if mp:
                cur["points"].append((mp.group(1).strip(), mp.group(2).strip()))
    for c in cards:
        c["links"] = [(t, u) for t, u in _MD_LINK.findall(c["body"])]
    return cards


def split_doc(md: str) -> tuple[str, list[dict], str]:
    """把新聞全文切成 (頭段, [新聞卡], 尾段)：
      頭段＝首張卡之前（標題／指數速覽／總覽）；
      尾段＝末張卡之後（次級觀察／資料侷限／合規揭露）。
    供儀表板「新聞全文」逐則收合＋其餘另置一收合塊。"""
    lines = scrub(md).splitlines()
    idxs = [i for i, l in enumerate(lines) if _CARD_HEAD.match(l.strip())]
    if not idxs:
        return md or "", [], ""
    head = "\n".join(lines[: idxs[0]]).strip()
    tail_start = len(lines)
    for j in range(idxs[-1] + 1, len(lines)):
        s = lines[j].strip()
        if (s.startswith("## ") or s == "---") and not _CARD_HEAD.match(s):
            tail_start = j
            break
    tail = "\n".join(lines[tail_start:]).strip()
    return head, extract_cards(md), tail


def _latest_pair() -> dict | None:
    """找最新一組 {date}_v1.md / _v2.md。回 {date, v1, v2}（缺的那版為 None）。"""
    if not NEWS_DIR.exists():
        return None
    dates = sorted({m.group(1) for f in NEWS_DIR.glob("*_v*.md")
                    if (m := re.match(r"(\d{4}-\d{2}-\d{2})_v[12]\.md", f.name))}, reverse=True)
    if not dates:
        return None
    d = dates[0]
    rd = lambda v: (NEWS_DIR / f"{d}_{v}.md").read_text(encoding="utf-8") \
        if (NEWS_DIR / f"{d}_{v}.md").exists() else None
    return {"date": d, "v1": rd("v1"), "v2": rd("v2")}


def load_latest() -> dict | None:
    """dashboard 用：最新一份昨夜美股新聞（含兩版型內容與合規掃描結果）。"""
    p = _latest_pair()
    if not p:
        return None
    p["banned_hits"] = compliance_scan((p.get("v1") or "") + (p.get("v2") or ""))
    return p
