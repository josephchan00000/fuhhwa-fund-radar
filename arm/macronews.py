"""昨夜美股交易時段・總經／政策面速寫（復華基金追蹤版本）—— 版型規格 ＋ 產出讀取。

第三種新聞（與 usnews 公司/產業面、twnews 台股並列），聚焦「政策面」：
  ① 川普主導的美國政府政策（白宮／行政命令／關稅／對中／外交）
  ② 聯準會重大訊息（主席／副主席／FOMC／利率）
  ③ 重大國際政策（戰爭、制裁、能源／出口管制／科技封鎖）

同 prompt-pack 哲學（純 Python 不杜撰新聞）：
  · scripts/gen_macronews.py 產提示包 reports/macronews/prompts/{date}.md；
  · 會上網查證的 Claude（訂閱額度）產 reports/macronews/{date}.md；
  · dashboard 讀「最新一份」呈現「總經・政策」區塊，跑合規掃描標燈。

解析／萃取／禁用詞掃描沿用 arm/usnews（extract_cards 已支援事件屬性＋重要度徽章）。
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from . import usnews

ROOT = Path(__file__).resolve().parent.parent
NEWS_DIR = ROOT / "reports" / "macronews"
CAL_DIR = ROOT / "reports" / "macrocal"        # 本週經濟數據行事曆

# 政策面版型（多找＋事件屬性＋重要度，與 usnews/twnews 同一套徽章標準）
SPEC_MACRO = f"""【版型：昨夜美股交易時段・總經／政策面速寫包】
角色：台灣投信給內外部溝通使用的「政策面速寫編輯」。針對【昨夜美股交易時段】，用 WebSearch 實際查證。

範圍（只收下列三類，其餘不收）：
  ① 川普主導的美國政府政策（白宮／行政命令／關稅／對中／外交）
  ② 聯準會重大訊息（主席 Powell／副主席／FOMC 會議與聲明／利率路徑）
  ③ 重大國際政策（戰爭、制裁、能源／出口管制／科技封鎖）
主要訊源：Reuters／Bloomberg／WSJ／FT（以 Top News／Most Read／Market Wrap 為主）；
可各補 ≤1 段 JPMorgan／Goldman Sachs／Morgan Stanley／BlackRock 政策評論（附日期）。
每則附來源連結與台北時間戳（TST；例：2026/07/02 09:30 TST，並於卡末再標一次）。

【數量與門檻】盡量多找：**至少 4 則、上不封頂**，收錄所有「重要度 6 分以上」的政策事件，寧多勿漏；
以「24 小時內」為主、跨站比對首發與更新。排序：先依重要度高→低，同分再新→舊。

{usnews.ETYPE_RULE}
{usnews.SEV_RUBRIC}
（政策面重要度參考：9–10＝牽動美債殖利率／美元指數／油金／S&P500·Nasdaq 隔夜且具結構性（影響 >3 個月或跨產業）；
 7–8＝使單一主要資產或產業明顯波動（隔夜 ±1% 上下）；6＝方向性政策訊號、值得追蹤但影響侷限。）

版面：
  🔹前後 24 小時政策總覽（Fed／美政府／國際政策各 1 句 ＋ 1 句市場解析）
  🔹政策新聞卡（每則 120–180 字；≥4 則）：
     標題（來源＋日期＋TST｜【新事件】或【延伸】｜重要度 N/10）  ← 括注三段缺一不可，供儀表板解析徽章
     1. 新聞摘要（2–3 句） 2. 一句話重點 3. 對全球經濟影響
     4. 對資產影響（美債殖利率／美元／WTI·Brent／金價／股指／加密，依內容取捨）
     5. 對產業受益／受害 6. 對市場情緒影響
     7. 參考連結（逐條列來源與機構評論日期；**每卡至少 1 條 [來源標題](URL) markdown 可點連結**）
  🔹次級觀察摘要（Top 政策不足 4 則時補充）
  I. 合規揭露（附完整揭露段）
用語合規：僅市場資訊彙編/教育用途、非投資建議；禁用詞見 usnews.BANNED；機構觀點以
『該機構表示／認為／估測（日期）』呈現；不預測報酬、不以過去績效推未來。
查不到或跨來源矛盾者只留方向、標「以官方為準」，切勿杜撰數字。
（若文中提及基金主題，附揭露：投資人申購本基金係持有基金受益憑證，非本文提及之投資資產或標的。）"""


# 本週財經行事曆版型（給提示包用）——2026-07-05 使用者需求：
# 除美國經濟數據外，加入歐盟、中國、日本重點數據與「重要企業財報／法說」。
SPEC_CAL = """【版型：本週重點財經行事曆（美國＋歐盟＋中國＋日本＋重要企業財報）】
用 WebSearch 查證本週（週一~週五，以台北日期所在整週）重點財經行事曆，涵蓋五類
（「項目」欄一律加地區／類別前綴「美：／歐：／中：／日：／財報：」，休市列可免）：
  · 美：非農/失業率/時薪、CPI/PCE/核心通膨、FOMC 與 Fed 官員談話、GDP、零售銷售、
    ISM/PMI、初領失業金、JOLTS、消費者信心、重大財政/關稅時程；並標示美股休市日。
  · 歐：ECB 利率決議與官員談話、歐元區 CPI/PMI/GDP/零售銷售、歐盟重大貿易／關稅／監管時程。
  · 中：CPI/PPI、進出口、官方與財新 PMI、社融/信貸、LPR 與人行動作、重大政策會議。
  · 日：日銀（BOJ）會議與官員談話、CPI、短觀、薪資／貿易數據。
  · 財報：本週排定之重要企業財報／法說會（美股大型權值與關鍵半導體、台股台積電等指標企業；
    「預期／前值」欄可填市場共識 EPS 或營收，查不到填「—」）。
以「已公布」列出實際值、「未公布」留待公布。

嚴格輸出成一個 markdown 表格（欄位固定、供程式解析）：

# 本週重點財經行事曆（{起}–{迄}）
> 更新：{今天}；{若有休市：例「美股 7/3 因國慶假期休市」，無則寫「本週美股正常交易」}

| 日期 | 項目 | 預期 | 實際 | 前值 | 狀態 |
|---|---|---|---|---|---|
| 07/02 | 美：6月非農就業 | +11.5萬 | +5.7萬 | +14.4萬 | 已公布 |
| 07/03 | 美股國慶假期休市 | — | — | — | 休市 |
| 07/02 | 歐：歐元區6月CPI（年增） | +2.0% | — | +1.9% | 未公布 |
| 07/03 | 中：6月財新服務業PMI | — | — | 51.1 | 未公布 |
| 07/01 | 日：日銀短觀（Q2 大型製造業） | +12 | +13 | +12 | 已公布 |
| 07/02 | 財報：美光（MU）FY26Q3 財報 | EPS 2.5美元 | — | — | 未公布 |

規則：日期用 MM/DD；狀態只填「已公布／未公布／休市」三者之一；已公布須填實際值，未公布實際值填「—」；
數字查不到或跨來源矛盾者填「—」並不杜撰。**未公布之數據列（如初領失業金、CPI/PPI、零售銷售、
消費信貸等），盡量以可靠第三方（Trading Economics／Investing.com／FXStreet／investingLive 等）
之市場共識填「預期」欄，並在數值後加「*」**（＝市場共識預估、非官方，儀表板會轉成橘色上標＋頁尾註解，
來源寫進本表下方「註」）；查無一致共識才填「—」。會議／談話／公聽會等無預期值項目維持「—」。
至少涵蓋本週所有交易日的重點項目（無數據日可只標休市或略過）；
歐／中／日與財報僅收「對市場有影響力」的重點項目，勿灌水湊列。
僅為資訊彙編、非投資建議；不預測數值、不含禁用詞。"""


# 行事曆「項目」欄的地區／類別前綴（美：／歐：／中：／日：／財報：）——
# md 檔保留前綴供程式解析；儀表板顯示時轉成彩色小徽章、財報獨立子表。
_REGION_RE = re.compile(r"^(美|歐|中|日|財報)\s*[：:]\s*")


def _parse_cal_rows(md: str) -> list[dict]:
    """把行事曆 markdown 表格解析成 [{date,item,region,cons,actual,prev,status}]。

    region＝項目前綴（美／歐／中／日／財報；無前綴如休市列為空字串），
    item＝去前綴後的項目名。"""
    rows: list[dict] = []
    for line in usnews.scrub(md or "").splitlines():
        s = line.strip()
        if not (s.startswith("|") and s.endswith("|")):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 6:
            continue
        if cells[0] in ("日期", "") or set(cells[0]) <= set("-: "):   # 表頭/分隔列
            continue
        item = cells[1]
        m = _REGION_RE.match(item)
        region = m.group(1) if m else ""
        if m:
            item = item[m.end():]
        rows.append({"date": cells[0], "item": item, "region": region,
                     "cons": cells[2], "actual": cells[3], "prev": cells[4],
                     "status": cells[5]})
    return rows


def _cal_note(md: str) -> str:
    """取行事曆檔內 `>` 引言（通常含休市說明）。"""
    for line in usnews.scrub(md or "").splitlines():
        s = line.strip()
        if s.startswith(">"):
            return s.lstrip("> ").strip()
    return ""


def load_calendar() -> dict | None:
    """dashboard 用：最新一份本週行事曆 {date, md, rows, note, title}。"""
    if not CAL_DIR.exists():
        return None
    dates = sorted({m.group(1) for f in CAL_DIR.glob("*.md")
                    if (m := re.match(r"(\d{4}-\d{2}-\d{2})\.md$", f.name))}, reverse=True)
    if not dates:
        return None
    d = dates[0]
    md = (CAL_DIR / f"{d}.md").read_text(encoding="utf-8")
    title = next((ln.lstrip("# ").strip() for ln in md.splitlines()
                  if ln.startswith("#")), "本週重點財經行事曆")
    return {"date": d, "md": md, "rows": _parse_cal_rows(md),
            "note": _cal_note(md), "title": title}


def load_latest() -> dict | None:
    """dashboard 用：最新一份總經／政策面新聞 {date, md, banned_hits}。"""
    if not NEWS_DIR.exists():
        return None
    dates = sorted({m.group(1) for f in NEWS_DIR.glob("*.md")
                    if (m := re.match(r"(\d{4}-\d{2}-\d{2})\.md$", f.name))}, reverse=True)
    if not dates:
        return None
    d = dates[0]
    md = (NEWS_DIR / f"{d}.md").read_text(encoding="utf-8")
    return {"date": d, "md": md, "banned_hits": usnews.compliance_scan(md)}


def us_session_date(today: date | None = None) -> date:
    """沿用 usnews：台北日期 → 對應昨夜美股交易日。"""
    return usnews.us_session_date(today)
