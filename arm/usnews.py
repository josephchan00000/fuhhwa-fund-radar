"""昨夜美股新聞（復華基金追蹤版本）—— 兩版型規格常數 ＋ 產出讀取 ＋ 合規掃描。

即時新聞需要「會上網查證的 LLM」，純 Python 無法自動生成 → 沿用本專案 prompt-pack 哲學：
  · scripts/gen_usnews.py 產一份『可貼進 Claude 的提示包』（reports/usnews/prompts/{date}.md），
    內含兩版型完整規格＋當日日期＋昨夜美股交易日；
  · Claude 產兩份 markdown 回存 reports/usnews/{date}_v1.md（Top3 速寫包）與 _v2.md（精簡版）；
  · dashboard / 報告讀「最新一份」呈現，並跑合規掃描標注。

本檔只放：規格文字、讀取器、合規禁用詞掃描（純函式、可單測）。
"""
from __future__ import annotations

import json
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
              "  ⚑ 評分本位＝「對投資的影響」（2026-08-31 使用者定調）：分數只回答「這件事牽動了"
              "哪些資產／族群、幅度多大、確定性多高」——事件本身的嚴重度、悲劇性、軍事烈度、"
              "政治戲劇性與新聞聲量都**不是**加分項；新聞再大條，說不出資產通道就不是高分。\n"
              "  9–10＝結構性衝擊（衝擊大盤或整條產業鏈：龍頭財報暴雷／重大併購／政策級監管／權值股隔夜 ±5% 以上）；\n"
              "  7–8＝重要個股或次產業明顯影響（單一標的隔夜 ±2–5%、關鍵財測／大訂單／法說指引／重大人事）；\n"
              "  6＝值得追蹤但影響侷限（次級題材、分析師評價調整、單一中型股事件）；\n"
              "  ≤5＝不列入（雜訊／重複舊聞；純 Fed 利率大盤限個股本位的美股／台股報適用——"
              "總經報之央行政策屬核心守備、不受此項排除）。\n"
              "  評分校準（證據錨定，2026-08-19 起；2026-08-31 改投資影響本位）：分數須綁「可觀察"
              "證據」——9–10 須有「大盤或整條產業鏈實際波動」等級的證據；7–8 須有「單一主要資產／"
              "權值股／板塊實際明顯波動」**或**「已排定時點、可驗證的具體傳導」（媒體聲量只是"
              "熱度佐證，**不能單獨撐起 7 分**——戰爭類頭條天然聲量大，勿以覆蓋廣度代替資產證據）；"
              "6 至少 2 家主流媒體獨立報導＋說得出具體資產通道。\n"
              "  一致性自查（與漲跌分析欄互鎖）：卡內漲跌分析若寫「反應有限／無可單獨歸因之資產"
              "變動」，該卡**至多 6 分**——除非影響欄寫得出「已排定時點的具體傳導」（寫明機制與時點）。\n"
              "  地緣／戰事／人道事件一律以「資產通道」計分：看油氣、航運、國防、供應鏈、避險資產"
              "的實際變動或新增暴險，不看死傷規模與頭條版面；同一衝突的例行進展（互襲、增援、"
              "談判反覆）若對應資產反應有限、又未新增具體投資暴險＝**至多 5 分、不單獨成卡**"
              "（總覽或相關卡內帶一句即可）。\n"
              "  分數不是湊卡工具：當日真只有 3 條 ≥6 分，寧可少一卡並把時窗往前補真事件，"
              "不得把 5 分事件抬成 6 分；反之真有 7 條 ≥6 分就全收，不得因卡數已夠而壓分。")

# 重點標記＋內容主軸——儀表板把 **粗體** 渲染成「半透明藍底關鍵句」
# （2026-07-18 使用者指示全站抓重點；07-19 檢討：標「事實」不標「情緒」、禁投顧風主軸）。
HILITE_RULE = ("重點標記（標「事實」、不標「情緒」）：每卡的「新聞摘要」與各影響欄，用 **粗體** 標出 "
               "1–2 處『事實性關鍵』——①紀錄性事實與關鍵數字（**史上最大收盤跌點**、**−6.47%**、"
               "**賣超 2,617 億**）；②清單型重點標『內容本身』而非名目：「三大止跌訊號」→ 粗體標 "
               "**費半回穩、新台幣止貶、權值股率先止跌** 這三項，不是標「三大止跌訊號」四個字；"
               "③關鍵日期與檢核點（**7/20 T+2 交割日**、**季線 43,525**）。不可標：情緒與模糊判斷"
               "（多空分歧明顯／情緒偏謹慎／觀望氣氛濃）、名人個人進出與金額、空泛形容句。"
               "每欄 **2–3 處**、標短語不標整句；總覽段與行事曆重點框同規則。\n"
               "內容主軸：卡片標題與主體以「可查證事實」為軸——官方統計、公司公告、交易所／主管機關"
               "措施、具名機構研究；名嘴／投顧的個人進出與情緒性敘事不得作為標題或主軸（至多段內"
               "輔助引用一句並標明屬個人觀點），標題寫事實、不寫聳動語（「砸 8 位數進場」「算帳的"
               "時刻」之類留給來源原題）。\n"
               "數據口徑（2026-07-20 教訓：外資淨空單誤引彙整站快照）：期貨／籌碼類數字（未平倉口數、"
               "買賣超金額）一律以官方口徑為準——台股期貨用期交所盤後「三大法人—區分各期貨契約」的"
               "臺股期貨(TX)外資『多空淨額』並附基準日；彙整站（玩股網等）與媒體標題常混用『空方總"
               "口數 vs 淨額』或把大台／小台／微台不同契約合計，須**兩個獨立來源數字一致**才可引用，"
               "不一致時取官方值或誠實列入資料侷限。美股指數（尤其費半 SOX）媒體極少刊收盤點位："
               "**嚴禁用前收自行推算點位**、嚴禁引盤中快照當收盤；漲跌%與點位皆須兩獨立來源一致，"
               "查不到就只寫方向、把數字缺口列入資料侷限（費半曾連三日出錯：週跌幅誤植／盤中快照"
               "當收盤／同日兩報 3.7% vs 5.21% 矛盾——寧缺勿錯）。"
               "另注意搜尋引擎常把**他日的收盤稿**混進當日結果（自由財經等站文章網址無日期，"
               "2026-08-04 曾因此把他日「費半重挫 5.71%」誤當週一收盤）——引用收盤稿前先核對"
               "文內是否含當日專屬事件標記（如當日獨有的紀錄性事件），對不上就棄用。"
               "**費半（^SOX）與台積電 ADR（TSM）的收盤值優先讀本機官方落檔 `data/macro_chips.json` 的 "
               "`series.sox`／`series.tsm_adr`**（2026-08-04 起 CI 每日自 Yahoo 官方序列抓取入庫，"
               "同籌碼數字「一切以官方為準」）；落檔尚無該序列或尚未更新到最新交易日時，"
               "才回退媒體兩來源一致原則。\n"
               "⚠ 查證過程不入正文（2026-08-04 使用者：「沒抓到數字就算了，還寫出來還加粗體是在"
               "幹嘛」）：數字缺口與查證說明**一律只寫在文末「資料侷限說明」段**；正文（總覽／速覽／"
               "卡片各欄）**嚴禁**出現「未取得兩個獨立來源」「不列數字」「依內規」「見資料侷限說明」"
               "這類流程性字句，更**不得對這類字句加粗**。查不到數字時正文就自然地只寫方向與定性"
               "描述，像一般新聞一樣，不解釋為什麼沒有數字。"
               "**資料來源機制說明同屬流程性字句（2026-08-17 總覽踩坑）**：『取自本機官方落檔』"
               "『series.sox』『data/macro_chips.json』這類**檔名／欄位名／落檔字樣**一律不得出現在"
               "正文（總覽／速覽／卡片各欄）——讀者不知道也不需要知道數字是從哪支檔讀的；"
               "來源機制只寫在文末「資料侷限說明」段。")

# 卡片可讀性規格（2026-09-01 使用者：「不只是在速覽喔，整個新聞卡也要套用」）。
# 與 depth_note 的深度六條並行、不衝突：深度講「要寫到多少層因果」，這裡講「同樣的內容
# 要寫成讀得下去的樣子」——總字數不變，只是把長句拆短、把層次斷開、把結論標出來。
READ_RULE = (
    "🔸卡片可讀性（深度不減，是把同樣的內容寫成讀得下去的樣子）：\n"
    "① **每句 ≤40 字**。2026-09-01 實測當日卡片平均句長 42–70 字、單句最長 146 字——"
    "一句塞三四個子句，讀者中途就放棄。拆成 2–3 句短句即可，總字數與深度都不變。\n"
    "② **每欄 2–3 處粗體，結論詞組也要標**：方向與受影響對象（**記憶體與設備領先**）、"
    "關鍵事件名（**MSCI 季調收盤生效**）、檢核點（**9/4 非農**）——不是只標數字"
    "（當日台股卡粗體 0–3 處、其中一張深度卡整張沒有）。仍不可標情緒與模糊判斷。\n"
    "③ **多層傳導要分句，不要塞成一大塊**：寫成「第一層是資金：…。第二層是訂單流向：…。」"
    "每層各自成句（儀表板會據此自動斷行）；「後續觀察：…」永遠獨立成句、放在該欄最後。\n"
    "④ 填充語一律刪：值得注意的是／整體而言／整體來看／換言之／可以說／這也是…的背景；"
    "同一事實不在同一張卡內講第二次。\n"
    "⑤ 用詞精準：形容詞能換成數字或具體事實就換掉（寫「**跌破季線**」不寫「弱勢整理」）。")

# 速覽／總覽段的文風規格（2026-09-01 使用者看了手機版盤前速覽後指示：「整段粗體的偏少…
# 我想要更好閱讀一點，廢話不要太多，你是專業的語言分析師幫我保留精華用詞精準」）。
# 這段只管「頭段那幾行」——卡片內文另有 depth_note 的深度六條，兩者不衝突：
# 卡片要深、速覽要短，速覽是給「只看 10 秒就要走」的讀者。
BRIEF_STYLE = (
    "🔸速覽／總覽段的寫法（與卡片不同：卡片求深，速覽求快——讀者只花 10 秒）：\n"
    "① 長度硬上限：整段 **≤ 220 字**、至多 3 小段、每小段 2–3 句、**每句 ≤ 35 字**。"
    "寧可少寫一句，也不要把兩個事實塞進同一句。\n"
    "② 結論先行：每小段**第一句就是結論**（方向＋牽動誰），數字與證據放第二句以後；"
    "不要「背景→鋪陳→結論」的敘事順序。\n"
    "③ 版型與內規標籤不得入正文：「國際背景一句帶過」「（細節留給總經與美股報告）」"
    "「盤前研判（中性陳述）」這類**段名與內規說明一律不寫**——要分段就直接換段，"
    "讀者不需要知道版型長什麼樣（同「查證過程不入正文」原則）。\n"
    "④ 刪填充語：值得注意的是／整體而言／整體來看／換言之／可以說／這也是…的背景／"
    "未進一步反映——一律不用；同一事實不在段內講第二次。\n"
    "⑤ **粗體要有落點**（本次重點：原本只有數字被標，整段沒有視覺落點）：每小段 **2–3 處**，"
    "除了關鍵數字，**結論詞組同樣要標**——方向與受影響對象（**記憶體、設備領先**、"
    "**塑化航運偏正向**、**權值代工持平**）、關鍵事件名（**MSCI 季調收盤生效**）、"
    "檢核點（**今日下午 PMI**）。仍不可標情緒與模糊判斷（情緒偏謹慎／觀望氣氛濃／多空分歧）。\n"
    "⑥ 用詞精準：能換成數字或具體事實的形容詞就換掉——寫「**跌破五日線**」不寫「表現不佳」，"
    "寫「外資賣超 **143.9 億**」不寫「賣壓沉重」。")

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
    "不得為一卡的唯一來源（「富聯網 moneylink」維持黑名單、一律排除）。\n"
    "**經濟日報當日頭條必收（2026-08-04 使用者指示：「經濟日報頭條一定要放」）**：查證第一步"
    "先掃經濟日報（money.udn.com）當日頭版頭條／要聞頭條；屬台股守備範圍（大盤、個股、交易所"
    "措施、官方統計等）者**必收為一卡**，不得因選題取捨而漏掉（例：2026-08-04 頭條「台股關禁閉"
    "規定鬆綁」處置股新制即屬必收）；頭條若屬國際／總經事件則交由總經報告收錄，台股報告在"
    "盤前／盤後速覽帶一句即可。")

# 深度報告精選——每日保底 1 篇（2026-07-04 使用者需求：要更多深度報告）。
# {src} 由各市場版型帶入建議訊源。
DEEP_RULE = ("🔹深度報告精選（**保底 1 篇、上不封頂**）：從 {src} 中挑當日（不足時放寬到近 3 天內"
             "並註明刊出日）最有價值的深度分析／專題報導（產業鏈拆解、商業模式、政策影響評估、"
             "長線趨勢），版型同新聞卡，但標題括注第二段改用【深度】"
             "（來源＋日期＋TST｜【深度】｜重要度 N/10），並在摘要後多加一行「**為什麼值得讀**」。"
             "只挑真正有深度者（拒絕即時快訊充數）；查證原文可點連結必附。")

# ── 深度要求＋漲跌分析欄（2026-08-19 使用者：「每日排程模型跑出的內容不夠深入」＋
#     「新聞分析加一欄漲跌分析、大跌/大漲的理由為何」）──
# 深度不倚賴模型自覺，寫成可逐條對照的結構要求；三份報告（usnews/twnews/macronews）
# 提示包共同注入，改規則改這裡即可。check_reports.py 自 2026-08-20 起做結構性把關。


def depth_note(min_chars: int = 200) -> str:
    """分析深度硬性要求。min_chars＝每卡正文（摘要＋漲跌分析＋各影響欄合計）字數下限
    （完整版 200／台股 180／精簡版 150；check_reports 以更寬鬆的 120 字擋真正過薄者）。"""
    return (
        "分析深度（硬性要求、非建議；每卡寫完逐條自我對照）：\n"
        "  ① 因果鏈寫滿三層：影響分析須從「事件本身 → 傳導機制（誰的訂單／成本／供給／"
        "資金流因此改變）→ 具體受影響標的（點名公司或族群、附可查證數字）」寫完整，"
        "禁止只寫第一層結論就收尾；\n"
        "  ② 量化錨點：每卡影響分析至少 1 個查證得到的具體數字（漲跌幅、金額、產能、市占、"
        "營收占比等），不可整卡只有方向形容詞；\n"
        "  ③ 空泛句不得單獨成欄：「市場情緒轉趨保守」「值得留意後續」這類結論句，"
        "後面必須接「為什麼／透過什麼機制」的說明才算完成該欄；\n"
        "  ④ 補原文沒明說的背景（深度的主要來源）：影響分析不可只改寫新聞原文——每卡至少補 "
        "1 項原文之外、查證過的脈絡（該公司在供應鏈的位置與客戶結構、與前次同類事件的對照、"
        "相關數據的歷史水準），查不到的背景寧缺勿杜撰；\n"
        "  ⑤ 後續觀察點：每卡最後一個影響欄末尾以「後續觀察：…」收——寫具體可驗證的檢核"
        "事件與時點（下次法說／數據公布日／政策生效日／官方統計發布），"
        "不寫「持續觀察發展」這種空話；\n"
        f"  ⑥ 篇幅下限：每卡正文（摘要＋漲跌分析＋各影響欄合計）不得少於 {min_chars} 字；"
        "寧可卡少而深（下限仍為 4 卡），不可卡多而淺。")


_MOVE_SCOPE = {
    "us": "該事件牽動的個股與相關指數（昨夜實際收盤）",
    "tw_pre": "該事件牽動的台股個股／族群（前一交易日收盤），及昨夜對應之 ADR／費半／台指期夜盤",
    "tw_post": "該事件牽動的台股個股／族群與大盤（當日收盤）",
    "macro": "該政策牽動的主要資產——美債殖利率／美元／油金／主要股指（最近交易時段）",
}


def move_note(kind: str) -> str:
    """「漲跌分析」欄規格（每卡必填；kind＝us／tw_pre／tw_post／macro）。
    欄位由 extract_cards 解析（move）上儀表板；check_reports 自 2026-08-20 起擋缺欄。"""
    scope = _MOVE_SCOPE.get(kind, _MOVE_SCOPE["us"])
    extra = ("；與「對資產影響」欄分工——本欄寫「已發生」的價格反應與歸因，"
             "「對資產影響」欄寫後續影響機制" if kind == "macro" else "")
    return (f"「漲跌分析」欄（每卡必填、標籤加粗；【深度】精選卡免）：寫{scope}"
            "的**實際漲跌幅**與**大漲大跌的理由**——\n"
            "  · 漲跌數字須可查證（同數據口徑規則）；大漲／大跌（個股約 ±3%、指數約 ±1% 以上）"
            "**必須交代主因與次因**（財報／訂單／評等調整／法人籌碼／政策／獲利了結／估值修正…），"
            "歸因以來源佐證、用「市場解讀為／主因指向」等中性表述，勿自創因果；\n"
            "  · 事件若無明顯價格反應，也要一句交代「反應有限＋為什麼」（市場已提前反應／"
            "尚未開盤交易／事件量級不足），不可留白；\n"
            f"  · 寫成單行『N. **漲跌分析**：…』（內文可用粗體標關鍵數字）{extra}。")


# 卡內欄位標籤必須加粗（2026-07-31 連三次踩坑：無粗體→extract_cards 解析落空、儀表板只剩
# 連結；過去只靠派工 prompt 點名，現直接寫進提示包當源頭防呆；check_reports 仍為最後閘門）。
LABEL_RULE = ("卡內欄位標籤一律寫成『N. **標籤**：內文』——標籤必須加 **粗體**"
              "（例：1. **新聞摘要**：…／3. **漲跌分析**：…／4. **對公司影響**：…）；"
              "儀表板解析依賴粗體標籤，漏加粗體＝該欄在儀表板上整段消失。\n"
              "頭段小節（總覽／速覽）標題一律寫成獨立一行『## 🔹段名』（版面列出的段名原樣照抄、含 ##），"
              "勿寫成『🔹**段名**』粗體行——儀表板總覽卡與列印版 ③ 盤勢總覽靠這行定位"
              "（2026-09-19 起美股報改寫粗體行，總覽在網頁與列印版空了三週）。")


# ── 選題流程＋市場變動錨定（2026-08-19 使用者：「要真的篩到熱門、市場真正重要的新聞」）──
# 舊選題是「關鍵字→搜到什麼收什麼」的由下而上，容易漏掉關鍵字外的當日頭條。改為由上而下：
# 先掃「媒體 Top／頭版＋市場實際變動＋行事曆已公布項」建候選，再過濾評分。
# ⚠ 設計原則（使用者 2026-08-19 特別要求，勿走回頭路）：錨定清單與提及閘門只是「下限保證」、
# 絕不是選題範圍——匯率／原物料／加密資產／他國股市／突發事件等「清單外」的市場主角，
# 由掃描層的開放式判準（「波動異常」或「多家媒體領銜」）負責抓；閘門只會多一道檢查、
# 永遠不會排除任何新聞。

_SCAN = {
    "us": ("①主流媒體當日 Top／最熱：Reuters・Bloomberg・CNBC・WSJ 的 Top News／Most Read／"
           "盤後 wrap 與富途美股異動（用 WebSearch 摘要即可，原頁被擋不硬抓）；"
           "②市場實際變動：昨夜漲跌幅與成交異常的指數／板塊／個股（含盤後財報 movers）；"
           "③昨夜排定且已公布的重大企業財報結果"),
    "tw_pre": ("①主流媒體頭版：經濟日報頭版頭條（必收規則不變）＋工商時報頭版要聞＋中央社台股稿；"
               "②市場實際變動：前一交易日大盤與類股漲跌、成交量、漲跌幅排行、法人買賣超集中"
               "標的、爆量個股；③昨夜美股／台積電 ADR／台指期夜盤異常，**以及今晨亞洲盤的國際突發（油價／匯率／他國股市）**——這類事件在盤前才發生、卻直接牽動開盤族群；④交易所與主管機關公告"),
    "tw_post": ("①主流媒體頭版與盤後稿：經濟日報（必收規則不變）＋工商時報＋中央社；"
                "②當日盤面：大盤與類股漲跌、成交量、漲跌幅排行、法人買賣超集中標的、爆量個股；"
                "③交易所與主管機關公告"),
    "macro": ("①Reuters・Bloomberg・WSJ・FT 的 Top News／Most Read；②白宮／財政部／聯準會與"
              "各國央行「當日實際發布」的聲明與行動；③行事曆昨日排定且已公布的重大數據——"
              "其結果與市場反應必須被涵蓋；④資產面異常：清單外資產（他國匯率、原物料、"
              "加密資產、他國股市、信用市場）的異常波動一樣要查；⑤**持續性議題的最新一手進展**：戰事／封鎖／制裁／關稅等已在追蹤的議題，每輪都要查「最近 24 小時內有沒有發生新的實際事件」（空襲、封鎖、簽署、生效、談判破局），**不可用同一議題的舊稿或背景稿代替新事件**——同題舊料最容易讓真正的新事件整個漏掉"),
}


def pick_note(kind: str) -> str:
    """選題流程五步（由上而下）；kind＝us／tw_pre／tw_post／macro。
    關鍵字清單只是搜尋起點，選到「當日真正熱門重要的新聞」靠本流程。"""
    scan = _SCAN.get(kind, _SCAN["us"])
    return (
        "選題流程（由上而下五步；建議關鍵字只是搜尋起點，選題以本流程為準）：\n"
        f"  ① 掃描建候選（10–15 條）：{scan}。掃描判準＝「當日波動異常」或「多家主流媒體"
        "同日領銜」，與題材是否在關鍵字／錨定清單內**無關**——匯率、原物料、加密資產、"
        "他國股市、突發地緣／天災／供應鏈事件等「清單外」的市場主角一樣要抓進候選；\n"
        "  ② 過濾：守備範圍外→交對應報（速覽可帶一句）；已報導清單內且無新進展→略過"
        "（週末合併時窗日的【週末最重大事件保底】除外）；"
        "非事件（法說／數據「預告」、投顧觀點、盤勢展望）→不入卡——平日與週末同一標準；\n"
        "  ③ 評分：依重要度評分校準逐條給分，分數要有可觀察證據；\n"
        "  ④ 選取：≥6 分全收；**「當日（週末合併時窗日＝整個時窗內）市場最大的一件事」"
        "必須有著落**——屬本報＝必成卡，不屬本報＝速覽帶一句＋細節明確留給對應報；\n"
        "  ⑤ 補漏自查（收尾必做）：自問「今天市場最熱的三件事，各自是否已成卡／已在總覽"
        "歸因／已明確交他報？」任一沒著落，回頭補齊再交稿。")


# 錨定指標：key →（顯示名, 單位, 旗標門檻, 型態）。型態 pct＝價格%變動、bp＝殖利率基點、
# flow＝當日流量（億元，取絕對值比門檻）。門檻偏高：錨定是「保底必答題」，不是灵敏警報。
_ANCHOR = {
    "sox":        ("費半 ^SOX", "點", 2.0, "pct"),
    "tsm_adr":    ("台積電 ADR", "美元", 2.0, "pct"),
    "vix":        ("VIX 恐慌指數", "", 15.0, "pct"),
    "us10y":      ("美國 10 年期公債殖利率", "%", 10.0, "bp"),
    "dxy":        ("美元指數 DXY", "", 1.0, "pct"),
    "usdtwd":     ("美元兌新台幣", "元", 1.0, "pct"),
    "brent":      ("布蘭特原油", "美元/桶", 2.0, "pct"),
    "gold":       ("黃金", "美元/盎司", 2.0, "pct"),
    "inst_total": ("三大法人合計買賣超", "億元", 300.0, "flow"),
}

# 各報提示包印哪些錨定列（僅決定「印什麼」；check_reports 的提及閘門另有自己的子集）
_ANCHOR_KEYS = {
    "us": ("sox", "tsm_adr"),
    "tw_pre": ("sox", "tsm_adr", "inst_total"),
    "tw_post": ("inst_total",),
    "macro": ("us10y", "dxy", "usdtwd", "brent", "gold", "vix"),
}


def _load_chips() -> dict:
    """讀官方落檔 data/macro_chips.json：先 fetch 後讀 origin/main 版（排程會話的工作樹
    可能停在分岔時點、資料是舊的），失敗退回工作區檔；全失敗回 {}（fail-open——
    錨定整段消失只是少一段提示，不影響產包與其他規則）。"""
    import subprocess
    try:
        subprocess.run(["git", "fetch", "origin", "main"], cwd=ROOT,
                       capture_output=True, timeout=20)
    except Exception:
        pass
    try:
        out = subprocess.run(["git", "show", "origin/main:data/macro_chips.json"],
                             cwd=ROOT, capture_output=True, timeout=15)
        if out.returncode == 0 and out.stdout.strip():
            return json.loads(out.stdout.decode("utf-8"))
    except Exception:
        pass
    try:
        return json.loads((ROOT / "data" / "macro_chips.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def _prev_weekday(d: date) -> date:
    x = d - timedelta(days=1)
    while x.weekday() >= 5:
        x -= timedelta(days=1)
    return x


def market_flags(today: date | None = None, chips: dict | None = None) -> dict:
    """官方落檔 → {key: {label, unit, date, last, disp, flag, fresh}}。

    flag＝大變動旗標（達 _ANCHOR 門檻**且**序列新鮮）；fresh＝序列最新日期已到
    「預期最近交易日」（美股系列跳週末＋已知假日；台股 flow 取上一平日——台股國定假日
    會誤判成未更新，但後果只是錨定降級為「自行查證」提示、且閘門不旗標，無害方向）。
    chips 供單測注入；讀不到落檔回 {}。"""
    d = today or clock.today_tw()
    ch = chips if chips is not None else _load_chips()
    series = (ch or {}).get("series") or {}
    exp_us = f"{_prev_us_trading_day(us_session_date(d)):%Y-%m-%d}"
    exp_tw = f"{_prev_weekday(d):%Y-%m-%d}"
    out: dict[str, dict] = {}
    for key, (label, unit, th, typ) in _ANCHOR.items():
        pts = sorted((k, v) for k, v in (series.get(key) or {}).items()
                     if isinstance(v, (int, float)))
        if not pts:
            continue
        last_d, last_v = pts[-1]
        prev_v = pts[-2][1] if len(pts) > 1 else None
        fresh = last_d >= (exp_tw if typ == "flow" else exp_us)
        row = {"label": label, "unit": unit, "date": last_d, "last": last_v, "fresh": fresh}
        if typ == "flow":
            row["disp"] = f"{'買超' if last_v >= 0 else '賣超'} {abs(last_v):,.1f} 億元"
            row["flag"] = fresh and abs(last_v) >= th
        elif prev_v in (None, 0):
            row["disp"] = f"{last_v:,.2f}"
            row["flag"] = False
        elif typ == "bp":
            bp = (last_v - prev_v) * 100
            row["disp"] = f"{last_v:.2f}%（{bp:+.0f}bp）"
            row["flag"] = fresh and abs(bp) >= th
        else:
            pct = (last_v - prev_v) / abs(prev_v) * 100
            row["disp"] = f"{last_v:,.2f}（{pct:+.2f}%）"
            row["flag"] = fresh and abs(pct) >= th
        out[key] = row
    return out


def market_anchor(kind: str, today: date | None = None) -> str:
    """把官方序列的最新變動與大變動旗標寫進提示包（保底必答題）。
    讀不到落檔／該報無對應指標時回空字串（提示包自動略過）。"""
    keys = _ANCHOR_KEYS.get(kind) or ()
    flags = market_flags(today) if keys else {}
    rows = [(k, flags[k]) for k in keys if k in flags]
    if not rows:
        return ""
    lines = ["【市場變動錨定（系統自官方序列算好，數字可直接引用；⚠ 這只是「保底必答題」、"
             "不是選題範圍——市場當日的主角可能完全不在此清單，匯率／原物料／加密資產／"
             "他國股市／突發事件照樣由選題流程掃描層負責抓）】"]
    for _k, r in rows:
        mark = ("  ⚑ 大變動——其歸因必須出現在本報（成卡或總覽歸因擇一，不必硬湊卡）"
                if r["flag"] else "")
        stale = "" if r["fresh"] else "（⚠ 未更新至最近交易日，僅供參考、數字請自行查證）"
        lines.append(f"· {r['label']}：{r['disp']}（資料日 {r['date']}）{stale}{mark}")
    lines.append("⏱ 錨定是「收盤／落檔值」、本質落後：**報告產出當下的亞洲盤即時變動，以及週末與今晨才發生的突發事件，都不在上列數字裡**——這類「錨定看不到的變動」一律由掃描層自行查證，**不可因為錨定沒有旗標就當作沒事發生**。")
    lines.append("錨定數字即官方口徑、可直接寫進正文；但正文不得出現「落檔／序列／檔名」等"
                 "機制字樣（同查證過程不入正文規則）。")
    return "\n".join(lines)


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

【數量與門檻】**至少 4 則、上不封頂**：當夜所有「重要度 6 分以上」的公司/產業事件全數收錄，
未達 6 分者不收、不為湊數抬分（見重要度評分）。排序：先依重要度高→低，
同分再新→舊。

{ETYPE_RULE}
{SEV_RUBRIC}
{HILITE_RULE}
{BRIEF_STYLE}
{READ_RULE}
{LABEL_RULE}
{depth_note(200)}
{move_note('us')}
{pick_note('us')}

版面：
  ## 🔹前後 24 小時重大公司與產業事項總覽
     ↑ 段名行原樣照抄（含 ##）；內容：（Nasdaq／費半／S&P500 各 1 句：收盤與漲跌幅、
     大漲大跌時加一句主因 ＋ 1 句市場解析：主題動能與板塊輪動）
  🔹新聞卡（每則 200–320 字，依「分析深度」要求寫滿因果鏈；≥4 則）：
     標題（來源＋日期＋TST｜【新事件】或【延伸】｜重要度 N/10）  ← 括注三段缺一不可，供儀表板解析徽章
     1. 新聞摘要（2–3 句聚焦事實） 2. 一句話重點 3. 漲跌分析 4. 對公司影響
     5. 對競爭者／合作方影響 6. 對市場情緒與股價影響
     7. 參考資料（逐條列來源與機構評論日期；**每卡至少 1 條以 [標題](URL) markdown
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

【數量與門檻】**至少 4 則、上不封頂**，收錄所有「重要度 6 分以上」者。
排序：先依重要度高→低，同分再新→舊。

{ETYPE_RULE}
{SEV_RUBRIC}
{HILITE_RULE}
{BRIEF_STYLE}
{READ_RULE}
{LABEL_RULE}
{depth_note(150)}
{move_note('us')}
{pick_note('us')}

每則輸出：
  新聞標題（來源 + 日期｜【新事件】或【延伸】｜重要度 N/10）  ← 括注三段缺一不可
  1. 新聞摘要 2. 濃縮成一句話（簡短有力） 3. 漲跌分析 4. 對公司影響 5. 對競爭者/合作方影響
  6. 對市場情緒與股價影響 7. 參考連結（每卡至少 1 條 [來源標題](URL) markdown 可點連結）
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
                 "台股事件**（公司公告、法說、官方統計、籌碼、交易所措施），而不是改抄國際新聞。"
                 "\n  · **例外——只在「盤前／盤後速覽」段落用 1～2 句帶到國際背景**（2026-08-03 使用者同意）："
                 "讓只看台股報告的讀者知道「昨夜／週末國際上有哪些大事在牽動今天開盤」，"
                 "格式為『事件一句＋對台股哪個方向的意涵一句』，**不另開卡片、不展開全球資產分析**；"
                 "細節一律留給總經與美股報告。")
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
            "把這段期間最重要的新聞一次綜合整理（依重要度高→低排序），"
            "切勿只收錄最近一天；先前日報已報導者不得原樣重收，有新進展標【延伸】並註明。")
    # 2026-08-03 使用者回報：週末新聞量少，子代理改用投顧看法／預告性內容湊卡數，
    # 週一那份「一點都不重要」。稀疏時的取捨規則講明白，並要求週一以國際事件領銜。
    thin = ("【週末新聞稀疏時的取捨（重要）】週末本來就少新聞，**寧可少 1～2 卡，也不要用"
            "『投顧／分析師看後市』『法人估某數字』『本週有哪些事要公布』這類看法與預告湊卡數**"
            "——這類內容不是事件、重要度一律視為 5 分以下不得入卡（機構觀點只能放在某張事件卡"
            "的段內輔助引用一句）。卡數不足時，正確作法是**把時窗往前延伸到週五盤中／盤前**"
            "把當時真正發生、且尚未報導過的事件補進來，而不是改用預測性內容。")
    # 2026-08-31 使用者回報：沃許（Fed 主席）週五傑克森霍爾談話＝當週末最重大事件，
    # 六、日報告皆有卡，週一總經報卻因「已報導清單＋週末無新進展」整份無卡、
    # 只剩總覽一句「詳前份日報」。儀表板只顯示當日報告，指向前份日報＝事件對讀者直接消失。
    top = ("【週末最重大事件保底（此條優先於「已報導清單」的略過規則）】本時窗內重要度最高的"
           "1～2 件事（判準：前兩日日報中分數最高的卡、或多家主流媒體整個週末持續領銜者），"
           "即使先前日報已收錄、且其後沒有新進展，今日仍**必須成卡重收**——標【延伸】、"
           "「新在哪」註明「週末綜整」，內容改寫成綜整版（事件全貌＋至今累積的市場反應＋"
           "本週檢核時點），不得照抄前日卡片；也**嚴禁**只在總覽留一句「詳前份日報」了事"
           "（讀者只看得到當日報告，指向前份日報＝該事件直接消失）。\n"
           "⚠ 同時注意反向風險：**週日與今晨才發生的事最容易整個漏掉**——前一日日報涵蓋不到、官方錨定序列也還沒反映（錨定只有週五／週末收盤），所以「錨定沒旗標」不代表沒事發生；務必主動查『週日與今晨的突發事件』與亞洲盤即時變動（原油、黃金、匯率、期指）。")
    return base + "\n" + top + "\n" + thin


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

# NYSE／Nasdaq 全日休市日（美股）——僅供提示錨定，實際以交易所公告為準。
# 7/4（美國國慶）2026 適逢週六，故 7/3（五）補假休市。
# 2027 依 NYSE Group 2026–2028 假日表（ICE IR／Business Wire 2025-12-23）補入（2026-10-13：
# 表只到 2026 會在跨年後讓 calendar_anchor 靜默退化，tests 守「涵蓋今日起 45 天」）；
# 11/26 為下午 1 點提前收盤、非全日休市，不列。
_US_MKT_HOLIDAYS = {
    date(2026, 1, 1): "元旦", date(2026, 1, 19): "馬丁路德金恩日",
    date(2026, 2, 16): "總統日", date(2026, 4, 3): "耶穌受難日",
    date(2026, 5, 25): "陣亡將士紀念日", date(2026, 6, 19): "六月節",
    date(2026, 7, 3): "美國國慶補假（7/4 適逢週六）", date(2026, 9, 7): "勞動節",
    date(2026, 11, 26): "感恩節", date(2026, 12, 25): "耶誕節",
    date(2027, 1, 1): "元旦", date(2027, 1, 18): "馬丁路德金恩日",
    date(2027, 2, 15): "總統日", date(2027, 3, 26): "耶穌受難日",
    date(2027, 5, 31): "陣亡將士紀念日", date(2027, 6, 18): "六月節補假（6/19 適逢週六）",
    date(2027, 7, 5): "美國國慶補假（7/4 適逢週日）", date(2027, 9, 6): "勞動節",
    date(2027, 11, 25): "感恩節", date(2027, 12, 24): "耶誕節補假（12/25 適逢週六）",
}


def _prev_us_trading_day(d: date) -> date:
    """從 d 起（含 d）往回找最近一個美股實際交易日（跳週末＋已知國定假日）。"""
    x = d
    while x.weekday() >= 5 or x in _US_MKT_HOLIDAYS:
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
        skipped = "、".join(f"{h:%m/%d}（{_WD[h.weekday()]}）{_US_MKT_HOLIDAYS.get(h, '休市')}"
                            for h in (ses - timedelta(n) for n in range((ses - real).days))
                            if h.weekday() < 5 and h in _US_MKT_HOLIDAYS)
        note = f"（{skipped} 美股休市，故往回取）" if skipped else ""
        lines.append(f"· 對應昨夜美股實際交易日（美東）：{real:%Y/%m/%d}（{_WD[real.weekday()]}）{note}")
    else:
        lines.append(f"· 對應昨夜美股交易日（美東）：{ses:%Y/%m/%d}（{_WD[ses.weekday()]}）")
    covered = {h.year for h in _US_MKT_HOLIDAYS}
    if d.year not in covered or ses.year not in covered:
        lines.append("· ⚠ 系統假日表未涵蓋本年份——請自行以 WebSearch 確認美股休市日，勿逕信上列推算")
        lines.append(_tw_holiday_line(d))
        return chr(10).join(lines)
    near = [(h, name) for h, name in sorted(_US_MKT_HOLIDAYS.items()) if abs((h - d).days) <= 4]
    if near:
        lines.append("· 鄰近美股休市日：" +
                     "；".join(f"{h:%m/%d}（{_WD[h.weekday()]}）{name}" for h, name in near))
    else:
        lines.append("· 本週美股無鄰近國定假日、正常交易")
    lines.append(_tw_holiday_line(d))
    return "\n".join(lines)


def _tw_holiday_line(d: date) -> str:
    """台股近 10 日官方休市（證交所表，arm/twholidays；2026-10-13 起）——行事曆「市況」段的
    台股欄據此寫，不再由代理自行搜尋推算（那段文字曾直接驅動盤後看門狗的交易日判定）。"""
    from . import twholidays
    horizon = d + timedelta(days=9)
    if not twholidays.covers_partly(d) or not twholidays.covers_partly(horizon):
        return "· ⚠ 證交所休市表未涵蓋本年份——台股休市日請以證交所公告為準"
    up = twholidays.upcoming(d, 10)
    prov = not (twholidays.covers(d) and twholidays.covers(horizon))
    if not up:
        return ("· 台股近 10 日無休市日（證交所官方表）" if not prov else
                "· 台股近 10 日辦公日曆無放假日（證交所年度表未公告，另加休市日以證交所公告為準）")
    items = "；".join(f"{h:%m/%d}（{_WD[h.weekday()]}）{n}" + ("" if off else "＊") for h, n, off in up)
    tail = ("" if all(off for *_x, off in up) else
            "｜＊＝人事行政總處辦公日曆放假日（證交所年度表未公告；證交所另加的休市日以其公告為準）")
    return "· 台股近 10 日休市（證交所官方表，行事曆「市況」台股欄據此寫）：" + items + tail


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
            "唯有實質新進展才收錄、標【延伸】並以一句話註明「新在哪」"
            "（唯一例外：提示包若含【週末最重大事件保底】段，該段指定的保底事件即使無新進展"
            "也必須成卡重收，不受本清單略過規則約束）：\n" + items)


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
# 裸標題型（③）常帶「1. 」「2、」流水號——那是報告檔內的撰寫序號，儀表板依重要度重排後
# 會變成「2.／1.／3.」的錯亂編號（2026-08-16 使用者回報「全球的新聞順序很奇怪」）。
# 一律在解析階段剝掉；要求數字後接標點，「10年期公債…」這類數字開頭的真標題不受影響。
_CARD_SEQ = re.compile(r"^\d{1,2}\s*[.、)）]\s*")


def extract_cards(md: str) -> list[dict]:
    """切出新聞卡（v1『### 卡 N｜…』／v2『## 一、…』／裸標題帶重要度括注）。

    回 [{title, meta, oneline, summary, points, links, body}]：
      title＝去尾端括注的標題；meta＝尾端（來源：…｜日期｜…）括注內容；
      oneline＝『一句話重點／一句話』行；summary＝『新聞摘要』行；
      move＝『漲跌分析』行（2026-08-19 起：實際漲跌幅＋大漲大跌歸因；舊報告無此欄＝空字串）；
      why＝『為什麼值得讀』行（【深度】精選卡專屬；2026-08-19 前雖有寫進報告卻沒被解析、
        整行在儀表板上消失——深度精選最有價值的一句，勿再讓它掉）；
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
            raw = _CARD_SEQ.sub("", raw).strip()          # 剝掉撰寫流水號（見 _CARD_SEQ）
            cur = {"title": raw, "meta": meta, "oneline": "", "summary": "", "move": "",
                   "why": "", "importance": _card_importance(meta), "etype": _card_etype(meta),
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
            mv = re.match(r"^\s*\d*\.?\s*\*\*漲跌分析\*\*[：:]\s*(.+)$", line)
            if mv and not cur["move"]:
                cur["move"] = mv.group(1).strip()
            mw = re.match(r"^\s*\d*\.?\s*\*\*為什麼值得讀\*\*[：:]\s*(.+)$", line)
            if mw and not cur["why"]:
                cur["why"] = mw.group(1).strip()
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


# ── 頭段小節（總覽／速覽）解析——單一實作：儀表板、列印版、check_reports 共用 ──
# 2026-10-13 使用者：「印出來的昨夜美股總覽那欄都是空的」。根因＝版型只寫「🔹…總覽」沒寫 ##，
# 子代理寫成「## 🔹…」或「🔹**…**」整行粗體全憑運氣；舊解析只認 ## 標題 → 美股報自 09-19 改寫
# 粗體行後，螢幕版「昨夜美股總覽」卡、列印版 ③ 全球欄、check_reports 速覽文風閘門三處同時
# 靜默落空三週（台股 8 月也有 22 天「### 🔹盤前速覽」「🔹**盤前速覽**」同型落空）。
# 認法：整行就是「## 標題／整行粗體／🔹 起頭短行」才算標籤——「**記憶體領跌**。中國長鑫…」
# 這種粗體開頭的正文段落不是標籤（粗體後還有字）。
_SEC_MARK = "🔹🔸"
_SEC_RULE = re.compile(r"^(?:-{3,}|[─━—＝=_]{3,})$")     # 分隔線：--- 與台股報的 ──── 皆算
_SEC_LABEL_MAX = 40                                       # 標籤字數上限：長標題是新聞卡、不是小節
OVERVIEW_KEY = "總覽"                                      # 美股／總經報頭段總覽
PREMKT_KEY = r"^盤[前後]速覽"                              # 台股報頭段速覽（「指數速覽」刻意不算）


def section_label(line: str) -> str | None:
    """小節標籤行 → 標籤文字（去 #／粗體／🔹／尾冒號）；不是標籤行回 None。
    認：『## 🔹X』『### X』（標題）、『🔹**X**』『**🔹X**』『**X**』（整行粗體）、
    『🔹X』（🔹 起頭、不含句號的短行）；前綴『> 』引言亦可。"""
    s = re.sub(r"^>\s?", "", (line or "").strip())
    if (m := re.match(r"^#{2,4}\s*(.+)$", s)):
        t = m.group(1)
    elif re.fullmatch(rf"[{_SEC_MARK}]?\s*\*\*[^*\n]+\*\*\s*[：:]?", s) or \
            (s[:1] in _SEC_MARK and "。" not in s):
        t = s
    else:
        return None
    t = re.sub(rf"[*{_SEC_MARK}]", "", t).strip().rstrip("：:").strip()
    return t if 0 < len(t) <= _SEC_LABEL_MAX else None


def _section_end(line: str) -> bool:
    """小節到此結束：任一 # 標題、分隔線、或下一個 🔹 標籤。不帶 🔹 的整行粗體不算——
    總覽正文偶有「**市場解析**」這種獨立粗體行，不可提早切斷。"""
    s = re.sub(r"^>\s?", "", (line or "").strip())
    if s.startswith("#") or _SEC_RULE.match(s):
        return True
    return section_label(s) is not None and s.lstrip("*").lstrip()[:1] in _SEC_MARK


def find_section(md: str, key: str) -> tuple[str, str, str] | None:
    """找第一個標籤符合 key（regex search）的頭段小節 → (標籤, 內文, 移除該節後全文)；
    找不到回 None。內文拆掉『> 』引言前綴（儀表板 _md 不支援 blockquote）。"""
    lines = scrub(md).splitlines()
    pat = re.compile(key)
    for i, line in enumerate(lines):
        lab = section_label(line)
        if lab and pat.search(lab):
            e = next((j for j in range(i + 1, len(lines)) if _section_end(lines[j])), len(lines))
            body = "\n".join(re.sub(r"^\s*>\s?", "", x) for x in lines[i + 1:e]).strip()
            return lab, body, "\n".join(lines[:i] + lines[e:]).strip()
    return None


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
