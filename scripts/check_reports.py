#!/usr/bin/env python3
"""當日新聞報告「內容 QA 閘門」——結構性把關（合規掃描之外的即時正確性檢查）。

檢查（任一不過 exit 1，供每日自動更新流程擋下不完整的產出）：
  · 檔案齊全：usnews v1/v2、twnews、macronews、macrocal 皆有「今日」檔
  · 卡數下限：每報新聞卡 ≥4（macrocal 改查表格資料列 ≥10）
  · 連結：每張卡至少 1 條 markdown 可點連結 [標題](http…)
  · 詳細分析：每張卡摘要／影響分析欄位須至少一項非空（2026-07-31 踩坑：twnews 子代理
    漏加 **粗體** 標籤，extract_cards() 解析不到摘要/影響，儀表板只剩連結、詳細分析消失）
  · 漲跌分析＋深度下限（2026-08-20 起、【深度】卡豁免；2026-08-19 使用者需求）：
    每卡須有「N. **漲跌分析**：」欄（實際漲跌幅＋大漲大跌歸因）、影響分析 ≥2 條、
    摘要＋漲跌分析＋影響分析合計 ≥120 字（擋「卡多而淺」的過薄產出）
  · 大變動提及（2026-08-20 起）：官方序列（usnews.market_flags）旗標的大變動，對應報告
    全文須至少提及該資產（美股報＝費半/ADR；總經報＝美債/美元/台幣/油/金/VIX）——
    「下限保證」設計：只擋「大變動卻隻字未提」，提及即過、不要求成卡、序列過期跳過、
    清單外資產不設閘門（選題廣度由提示包選題流程負責，閘門永不排除任何新聞）
  · 徽章：每張卡標題括注可解析出重要度（≥6）與屬性（新事件/延伸/深度）
  · 正文禁流程性字句：檔名/欄位名/落檔字樣（「取自官方落檔」「series.sox」「macro_chips.json」）
    只能出現在「資料侷限說明」「合規揭露」段（2026-08-17 踩坑：總覽正文出現
    「數字取自本機官方落檔 `series.sox`」，讀者不需要知道數字從哪支檔讀）
  · 頭段總覽／速覽（2026-10-13 起）：美股 v1／總經的「…總覽」、台股的「盤前／盤後速覽」須抽得到
    且有內文——儀表板置頂總覽卡與列印版 ③ 盤勢總覽三欄都靠它（2026-09-19 起美股報把段名寫成
    「🔹**…總覽**」粗體行，舊解析只認 ## 標題，網頁與列印版的美股總覽靜默空了三週）
  · 行事曆：表頭「更新：」需為今日；2026-10-13 起須有「台股：」公司法說／財報列（代號必填、≤10 列），
    或註明「台股：本週無觀察清單內公司法說／財報」——只確認有查，不強求一定有事件
  · 行事曆漂移（2026-10-14 起）：與同週昨日版相比，日期改了、已公布實際值的數字不見了、已公布退回未公布，
    而「註」沒有「修正：」交代 → 🔴
  · 核心排程錨（2026-10-14 起）：config/official_schedule.json 列在本週的事件沒列、或日期不同且沒有「修正：」→ 🔴
  · 市況台股欄 vs 證交所官方休市表（2026-10-13 起）：本週官方休市日沒寫、或寫了官方表沒有的休市日 → 🔴
  · 行事曆精簡（2026-10-13 起）：「台：」台灣經濟數據列（≤4）或註明「台：本週無台灣重點經濟數據」；
    總列數 ≤30（休市列不計）；引言 ≤220 字（只留更新／市況／本週焦點）

用法：TZ=Asia/Taipei python3 scripts/check_reports.py [YYYY-MM-DD]（預設今日台北）
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import usnews  # noqa: E402
from arm.clock import today_tw  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MIN_CARDS = 4
# 「漲跌分析」欄＋深度下限自此日起強制（此前的舊報告不回溯——新提示包自 08-20 首輪起才會產此欄）
MOVE_SINCE = "2026-08-20"
MIN_ANALYSIS = 120        # 每卡摘要＋漲跌分析＋影響分析合計字數下限（提示包要求 150–200，此為寬鬆底線）


def _check_cards(path: Path, date: str) -> list[str]:
    errs: list[str] = []
    if not path.exists():
        return [f"缺檔：{path.relative_to(ROOT)}"]
    md = path.read_text(encoding="utf-8")
    cards = usnews.extract_cards(md)
    rel = str(path.relative_to(ROOT))
    if len(cards) < MIN_CARDS:
        errs.append(f"{rel}：卡數 {len(cards)} < {MIN_CARDS}")
    errs += _check_process_language(md, rel)
    for i, c in enumerate(cards, 1):
        if not c.get("links"):
            errs.append(f"{rel}：卡{i}「{c['title'][:18]}…」無可點連結")
        if not c.get("summary") and not c.get("points"):
            errs.append(f"{rel}：卡{i}「{c['title'][:18]}…」摘要／影響分析皆空"
                        "（標籤未加 **粗體**，儀表板只會顯示連結、看不到詳細分析）")
        imp, et = c.get("importance"), c.get("etype")
        if not isinstance(imp, int) or imp < 6:
            errs.append(f"{rel}：卡{i} 重要度標注缺失或 <6（{imp}）")
        if et not in ("new", "ext", "deep"):
            errs.append(f"{rel}：卡{i} 屬性標注缺失（新事件/延伸/深度）")
        # 漲跌分析＋深度下限（2026-08-20 起；【深度】精選卡豁免——它有「為什麼值得讀」自成一格）
        if date >= MOVE_SINCE and et != "deep":
            pts = c.get("points") or []
            if not c.get("move"):
                errs.append(f"{rel}：卡{i}「{c['title'][:18]}…」缺「漲跌分析」欄"
                            "（需『N. **漲跌分析**：』標籤加粗體；寫實際漲跌幅＋大漲大跌歸因，"
                            "無明顯反應也要一句交代原因）")
            if len(pts) < 2:
                errs.append(f"{rel}：卡{i}「{c['title'][:18]}…」影響分析僅 {len(pts)} 條（<2）"
                            "——需多視角影響欄（『N. **對…影響**：』標籤加粗體）")
            depth = (len(c.get("summary") or "") + len(c.get("move") or "")
                     + sum(len(t) for _, t in pts))
            if depth < MIN_ANALYSIS:
                errs.append(f"{rel}：卡{i}「{c['title'][:18]}…」分析內容過薄"
                            f"（{depth} 字 < {MIN_ANALYSIS}）——影響分析須寫滿"
                            "「事件→傳導機制→具體標的」因果鏈並含量化數字（深度要求見提示包）")
    return errs


# 流程性字句（正文不得出現；「資料侷限」「合規」段豁免）——檔名/欄位名/落檔字樣＋
# 08-04 那批查證過程句式。加項時保持「決定性字樣」原則，勿加會誤傷一般新聞用語的詞。
_PROCESS_RE = re.compile(
    r"官方落檔|本機落檔|series\.[a-z_]+|macro_chips|[a-z_]+\.json|"
    r"未取得兩[個項]?獨立來源|一律不列數字|依內規|見資料侷限")


def _check_process_language(md: str, rel: str) -> list[str]:
    errs, sec = [], ""
    for n, line in enumerate(md.splitlines(), 1):
        s = line.strip()
        if re.match(r"^#{1,3}\s", s):
            sec = s
        if "資料侷限" in sec or "合規" in sec:
            continue
        m = _PROCESS_RE.search(line)
        if m:
            errs.append(f"{rel}：第{n}行正文出現流程性字句「{m.group(0)}」"
                        "——檔名/欄位名/查證過程只能寫在「資料侷限說明」段")
    return errs


# ── 速覽／總覽段文風閘門（2026-09-01 使用者：「整段粗體的偏少…廢話不要太多、用詞精準」）──
# 只管頭段那幾行（卡片求深、速覽求快，兩套標準不衝突）。三條都是「一眼可見」的結構性問題：
# 太長、把版型標籤寫進正文、整段沒有粗體落點。
BRIEF_SINCE = "2026-09-01"
BRIEF_MAX = 320            # 散文段字數；提示包要求 ≤220 字，閘門給緩衝、只擋明顯超長
BRIEF_MAX_BULLETS = 6      # 條列（索引式總覽）條數上限
BRIEF_MAX_BULLET_LEN = 130  # 每條條列字數上限——防止把長文塞進 bullet 繞過上限
_BRIEF_BAN = re.compile(
    r"一句帶過|細節留給|中性陳述|值得注意的是|整體而言|整體來看|換言之")


def _brief_sections(md: str) -> list[tuple[str, str]]:
    """回 [(段名, 內文)]——段名含「速覽」或「總覽」的頭段小節。
    段名行的寫法交 usnews.find_section 統一認（同儀表板）：舊版只認 ## 標題，美股報
    09-19 起寫成「🔹**…總覽**」粗體行後，本閘門對美股總覽靜默跳過了三週。"""
    labs: list[str] = []
    for line in (md or "").splitlines():
        lab = usnews.section_label(line)
        if lab and ("速覽" in lab or "總覽" in lab) and lab not in labs:
            labs.append(lab)
    out = []
    for lab in labs:
        sec = usnews.find_section(md, rf"^{re.escape(lab)}$")
        if sec:
            out.append((lab, sec[1]))
    return out


# ── 頭段小節存在閘門（2026-10-13 使用者：「印出來的昨夜美股總覽那欄都是空的」）──
# 儀表板置頂總覽卡／台股速覽卡、列印版 ③ 盤勢總覽三欄都靠這段；抽不到時網頁與列印版
# 只會安靜少一塊，合規掃描與其他閘門照樣 🟢——這正是美股總覽空了三週沒人發現的原因。
HEAD_SINCE = "2026-10-13"


def _check_head_sections(date: str) -> list[str]:
    """美股 v1／總經＝「…總覽」、台股＝「盤前／盤後速覽」須抽得到且有內文（同儀表板的抽法）。"""
    errs = []
    for rel, key, want, use_head in (
            (f"reports/usnews/{date}_v1.md", usnews.OVERVIEW_KEY,
             "## 🔹前後 24 小時重大公司與產業事項總覽", True),
            (f"reports/macronews/{date}.md", usnews.OVERVIEW_KEY, "## 🔹前後 24 小時政策總覽", True),
            (f"reports/twnews/{date}.md", usnews.PREMKT_KEY, "## 🔹盤前速覽／## 🔹盤後速覽", False)):
        p = ROOT / rel
        if not p.exists():
            continue                                  # 缺檔由 _check_cards 回報
        md = p.read_text(encoding="utf-8")
        sec = usnews.find_section(usnews.split_doc(md)[0] if use_head else md, key)
        if not sec or not sec[1].strip():
            errs.append(f"{rel}：抽不到頭段「{want.split('🔹')[-1]}」或內文為空——段名請寫成獨立一行"
                        f"『{want}』；抽不到時網頁總覽卡與列印版 ③ 盤勢總覽該欄整片空白")
    return errs


def _plain(t: str) -> str:
    return re.sub(r"\s+", "", re.sub(r"[*`>\-]", "", t))


def _check_brief(md: str, rel: str) -> list[str]:
    """⚠ 字數只算「散文段」，條列行分開算（2026-09-01 首版把兩者合計，害得
    美股／總經那種「指數收盤條列＋一段解析」的索引式總覽必紅——而條列本來就是
    好掃的版式、不是使用者抱怨的那種長篇敘述）。條列改以「條數×每條長度」設限，
    免得有人把長文塞進 bullet 繞過閘門。"""
    errs = []
    for head, body in _brief_sections(md):
        name = head.lstrip("# ").strip()
        bullets = [ln for ln in body.splitlines() if ln.strip().startswith(("-", "*", "・"))]
        prose = "\n".join(ln for ln in body.splitlines()
                           if not ln.strip().startswith(("-", "*", "・")))
        text = _plain(prose)
        if not _plain(body):
            continue
        if len(text) > BRIEF_MAX:
            errs.append(f"{rel}：「{name}」散文 {len(text)} 字超過上限 {BRIEF_MAX}"
                        "——速覽是給只看 10 秒的讀者，長內容請放進卡片")
        if len(bullets) > BRIEF_MAX_BULLETS:
            errs.append(f"{rel}：「{name}」條列 {len(bullets)} 條超過 {BRIEF_MAX_BULLETS} 條")
        for b in bullets:
            if len(_plain(b)) > BRIEF_MAX_BULLET_LEN:
                errs.append(f"{rel}：「{name}」有一條條列 {len(_plain(b))} 字"
                            f"（上限 {BRIEF_MAX_BULLET_LEN}）——條列是索引、不是段落")
        m = _BRIEF_BAN.search(body)
        if m:
            errs.append(f"{rel}：「{name}」出現版型標籤／填充語「{m.group(0)}」"
                        "——段名與內規說明不入正文，要分段就直接換段")
        if len(re.findall(r"\*\*[^*\n]+\*\*", body)) < 2:
            errs.append(f"{rel}：「{name}」粗體不足 2 處——整段沒有視覺落點，"
                        "關鍵數字與結論詞組（方向／受影響對象／檢核點）都要標")
    return errs


# ── 卡片可讀性閘門（2026-09-01 使用者：「不只是速覽，整個新聞卡也要套用」）──
# 只擋「一眼可見」的三件事：整卡沒有粗體落點、句子長到讀不下去、填充語。
# 深度本身由 depth_note／既有的字數閘門管——這裡不看深度、也不會逼人少寫。
READ_SINCE = "2026-09-02"   # 規則進提示包後的首個產出日起（今日既有報告不回溯）
READ_MIN_BOLD = 3           # 每卡（摘要＋漲跌＋影響欄合計）粗體處數下限
READ_LONG_SENT = 60         # 單句字數：提示包要求 ≤40，閘門只擋明顯超長
READ_MAX_LONG = 2           # 每卡容許的超長句數（緩衝，超過即整卡難讀）
_FILLER = re.compile(r"值得注意的是|整體而言|整體來看|換言之|可以說是|這也是.{0,12}的背景")


def _card_body(c: dict) -> str:
    return " ".join([c.get("summary") or "", c.get("move") or "", c.get("why") or ""]
                    + [t for _, t in (c.get("points") or [])])


def _check_card_read(path: Path, rel: str) -> list[str]:
    errs = []
    if not path.exists():
        return errs
    _head, cards, _tail = usnews.split_doc(path.read_text(encoding="utf-8"))
    for c in cards:
        body = _card_body(c)
        if not body.strip():
            continue
        title = (c.get("title") or "")[:18]
        bolds = len(re.findall(r"\*\*[^*\n]+\*\*", body))
        if bolds < READ_MIN_BOLD:
            errs.append(f"{rel}：「{title}」粗體僅 {bolds} 處（需 ≥{READ_MIN_BOLD}）"
                        "——結論詞組（方向／受影響對象／檢核點）也要標，不是只標數字")
        plain = re.sub(r"\*\*", "", body)
        longs = [x for x in re.split(r"[。；;]", plain) if len(x.strip()) >= READ_LONG_SENT]
        if len(longs) > READ_MAX_LONG:
            errs.append(f"{rel}：「{title}」有 {len(longs)} 句超過 {READ_LONG_SENT} 字"
                        f"（最長 {max(len(x) for x in longs)} 字）——拆成短句，總字數不必減")
        m = _FILLER.search(body)
        if m:
            errs.append(f"{rel}：「{title}」出現填充語「{m.group(0)}」")
    return errs


# ── 大變動提及閘門（2026-08-20 起）──
# ⚠ 設計原則（使用者 2026-08-19：「閘門不能反過來限縮新聞範圍」）：本閘門只會因
# 「官方序列顯示大變動、報告全文卻隻字未提」多報一條錯——提及即過（不要求成卡）、
# 序列未更新到最近交易日不旗標、清單外資產（其他匯率/原物料/加密/他國股市…）根本不進
# 閘門，其選題由提示包 pick_note 掃描層開放式負責。它永遠不可能「排除」任何一則新聞。
_MENTION = {"sox": ("費半", "費城半導體", "SOX"), "tsm_adr": ("ADR",),
            "us10y": ("殖利率", "美債"), "dxy": ("美元指數", "DXY"),
            "usdtwd": ("新台幣", "台幣"), "brent": ("油",), "gold": ("黃金", "金價"),
            "vix": ("VIX", "恐慌指數")}


def _check_big_moves(targets: list[tuple[str, str, tuple[str, ...]]], flags: dict) -> list[str]:
    """targets＝[(rel, 全文, 該報閘門指標)]；flags＝usnews.market_flags() 結果。
    純函式供單測；flags 空（落檔讀不到）＝整段跳過（fail-open、不擋發佈）。"""
    errs: list[str] = []
    for rel, md, keys in targets:
        for k in keys:
            r = flags.get(k)
            if not r or not r.get("flag"):
                continue
            if not any(w in md for w in _MENTION.get(k, ())):
                errs.append(f"{rel}：官方序列顯示「{r['label']}」大變動（{r['disp']}）而全文"
                            "隻字未提——當日大變動的歸因必須被涵蓋（成卡或總覽歸因皆可）")
    return errs


def _check_calendar(path: Path, date: str) -> list[str]:
    if not path.exists():
        return [f"缺檔：{path.relative_to(ROOT)}"]
    md = path.read_text(encoding="utf-8")
    rel = str(path.relative_to(ROOT))
    errs: list[str] = []
    rows = [l for l in md.splitlines()
            if l.strip().startswith("|") and not re.match(r"^\|\s*[-:]+", l.strip())
            and "日期" not in l]
    if len(rows) < 10:
        errs.append(f"{rel}：行事曆資料列 {len(rows)} < 10")
    d_slash = date.replace("-", "/")
    if f"更新：{d_slash}" not in md and f"更新：{date}" not in md:
        errs.append(f"{rel}：表頭「更新：」非今日（{d_slash}）")
    if date >= TWCAL_SINCE:
        errs += _check_calendar_tw(md, rel, date)
    if date >= CALSLIM_SINCE:
        errs += _check_calendar_slim(md, rel, date)
    if date >= LASTWEEK_SINCE:
        errs += _check_calendar_lastweek(md, rel, date)
    if date >= HOLIDAY_SINCE:
        errs += _check_calendar_holidays(md, rel, date)
    if date >= DRIFT_SINCE:
        errs += _check_calendar_drift(md, rel, date)
    if date >= ANCHOR_SINCE:
        errs += _check_calendar_anchors(md, rel, date)
    return errs


# ── 核心排程錨（資料可信度盤查 Phase 3）：config/official_schedule.json 的本週事件必列、日期須一致 ──
ANCHOR_SINCE = "2026-10-14"


def _check_calendar_anchors(md: str, rel: str, date_iso: str) -> list[str]:
    import datetime as _dt
    from arm import macronews
    ws = macronews.cal_week_start(md, _dt.date.fromisoformat(date_iso))
    if not ws:
        return []
    rows = macronews._parse_cal_rows(md)
    errs = []
    for ev in macronews.week_anchors(ws):
        lv = {"official": "官方", "secondary": "可信次級"}.get(ev.get("level"), ev.get("level"))
        hits = [r for r in rows if macronews.anchor_matches(ev, r)]
        if not hits:
            errs.append(f"{rel}：核心排程「{ev['region']}：{ev['item']}」（{ev['d']:%m/%d}，{lv}）沒列——本週排程錨必列")
            continue
        def _md(s):
            m = re.match(r"\s*(\d{1,2})/(\d{1,2})", s or "")
            return (int(m.group(1)), int(m.group(2))) if m else None
        if not any(_md(r["date"]) == (ev["d"].month, ev["d"].day) for r in hits) and \
                not macronews.drift_explained({"item": ev["item"]}, md):
            errs.append(f"{rel}：「{ev['region']}：{ev['item']}」寫成 {hits[0]['date']}，排程錨為 "
                        f"{ev['d']:%m/%d}（{lv}，{ev.get('source', '')[:60]}）——照錨寫；確屬官方改期須在「註」寫「修正：」")
    return errs


# ── 行事曆漂移閘門（資料可信度盤查 Phase 2）──
# 回測 2026-07～10：同週有前一版的 84 天中 15 天出現沒交代的改動（日期來回翻 14 次、已公布實際值
# 改了 7 次——8 月失業率 4.3%→4.1%、時薪 3.7%→3.1%、核心 PCE 3.6%→3.3%…）。提示包已附昨日版當底稿；
# 這裡擋「改了卻沒在註寫『修正：』」。換順序、補細節、精度不同、談話要點換句話說都不算改動。
DRIFT_SINCE = "2026-10-14"


def _check_calendar_drift(md: str, rel: str, date_iso: str) -> list[str]:
    import datetime as _dt
    from arm import macronews
    today = _dt.date.fromisoformat(date_iso)
    ws = macronews.cal_week_start(md, today)
    prior = macronews.prior_cal(today, ws, cal_dir=ROOT / "reports" / "macrocal") if ws else None
    if not prior:
        return []
    errs = []
    for d in macronews.cal_drift(prior[1], md):
        if not macronews.drift_explained(d, md):
            errs.append(f"{rel}：「{d['item'][:20]}」{d['kind']}與昨日版不同（{d['old'][:16]} → {d['new'][:16]}）"
                        "——若是官方修正／改期，在表下「註」加「修正：…（來源）」；否則照昨日版")
    return errs


# ── 市況台股欄 vs 證交所官方休市表（2026-10-13 使用者：「你抓資料要確認資料的可信度還有穩定度」）──
# 這段文字原本直接驅動盤後看門狗的交易日判定；判定已改讀官方表（arm/twholidays），但它仍是
# 讀者看到的「本週休市」——與官方表不一致就是錯資訊上版。官方表未涵蓋的年份跳過（fail-open）。
HOLIDAY_SINCE = "2026-10-13"


def _check_calendar_holidays(md: str, rel: str, date_iso: str) -> list[str]:
    import datetime as _dt
    from arm import macronews, twholidays
    rng = re.search(r"（(\d{1,2})/(\d{1,2})[–\-~～](\d{1,2})/(\d{1,2})）", md)
    if not rng:
        return []
    y = int(date_iso[:4])
    m1, d1, m2, d2 = map(int, rng.groups())
    try:
        start = _dt.date(y - (1 if m1 == 12 and date_iso[5:7] == "01" else 0), m1, d1)
        end = _dt.date(start.year + (1 if m2 < m1 else 0), m2, d2)
    except ValueError:
        return []
    years = twholidays.load()
    names = twholidays.closed_days(years, with_provisional=True)
    days = [start + _dt.timedelta(n) for n in range((end - start).days + 1)]
    # 暫代年份（證交所表未公告、只有人事行政總處辦公日曆）：只驗「辦公日曆放假日有沒有寫」，
    # 其餘平日 is_closed＝None（證交所可能另加休市日）→ 兩個方向都不驗
    days = [d for d in days if d.weekday() < 5 and (d.year in years or d.year in twholidays.PROVISIONAL)]
    if not days:
        return []
    seg = re.search(r"市況：\s*台股\s*([^｜|；;]*)", macronews._cal_note(md) or "")
    seg = seg.group(1) if seg else ""
    claimed = set()
    if "休市" in seg:
        for mm, dd in re.findall(r"(\d{1,2})/(\d{1,2})", seg):
            claimed.add((int(mm), int(dd)))
        # 區間寫法「2/12–2/20 因春節休市」：中間的日子也算有寫（只取端點會誤報漏寫）
        for a, b, c, e in re.findall(r"(\d{1,2})/(\d{1,2})\s*[–\-~～至到]\s*(\d{1,2})/(\d{1,2})", seg):
            try:
                lo = _dt.date(start.year, int(a), int(b))
                hi = _dt.date(start.year + (1 if int(c) < int(a) else 0), int(c), int(e))
            except ValueError:
                continue
            for n in range(min((hi - lo).days, 31) + 1):
                x = lo + _dt.timedelta(n)
                claimed.add((x.month, x.day))
    errs = []
    for d in days:
        off = twholidays.is_closed(d, years)
        said = (d.month, d.day) in claimed
        if off and not said:
            src = "證交所官方表" if d.year in years else "人事行政總處辦公日曆（證交所表未公告）"
            errs.append(f"{rel}：{src} {d:%m/%d} 台股休市（{names.get(d, '休市')}），"
                        "市況「台股」欄沒寫——照提示包【交易日曆錨定】的官方休市表寫")
        elif said and off is False and not twholidays.typhoon_said(seg, d):
            # 颱風停止交易不在年度表上（2026-10-23 薔琵颱風）：寫明「因颱風休市」的日子不擋，查證後補進 twholidays.ADHOC
            errs.append(f"{rel}：市況「台股」欄寫 {d:%m/%d} 休市，證交所官方表該日為交易日——勿自行推算假日")
    return errs


# ── 行事曆台股公司列（2026-10-13 使用者：「行事曆是不是也要把台股的重要公司法說或是財報公布都加進去」）──
# 舊版型只點名「台股台積電等指標企業」，歷史行事曆裡的台股公司事件只出現過台積電。
# 閘門只問「有沒有查」：有台股列，或註明本週清單內無事件；不要求一定有事件（淡季本來就可能沒有）。
TWCAL_SINCE = "2026-10-13"


def _this_week_rows(md: str, date_iso: str | None) -> list[dict]:
    """本週的列（週末版帶過來的上週結果不算進各種列數上限；2026-10-30 起）。"""
    import datetime as _dt
    from arm import macronews
    rows = macronews._parse_cal_rows(md)
    if not date_iso:
        return rows
    ref = _dt.date.fromisoformat(date_iso)
    return macronews.week_split(rows, macronews.cal_week_start(md, ref), ref)[0]


def _check_calendar_tw(md: str, rel: str, date_iso: str | None = None) -> list[str]:
    from arm import macronews
    rows = macronews.retag_tw(_this_week_rows(md, date_iso), {r["code"] for r in macronews.tw_watch()})
    tw = [r for r in rows if r["region"] == "台股"]
    errs = []
    if not tw and not re.search(r"台股[：:]\s*本週無", md):
        errs.append(f"{rel}：沒有「台股：」公司法說／財報列，也沒註明「台股：本週無觀察清單內公司法說／財報」"
                    "——請依提示包【台股公司觀察清單】逐家查證")
    for r in tw:
        if not macronews.tw_codes(r["item"]):
            errs.append(f"{rel}：台股列「{r['item'][:24]}」缺代號——寫成「公司名（代號）」，"
                        "儀表板才比對得到復華持股")
    if len(tw) > macronews.TW_CAL_MAX:
        errs.append(f"{rel}：台股列 {len(tw)} 列超過 {macronews.TW_CAL_MAX}——持股多者優先，其餘在「註」帶過")
    return errs


# ── 行事曆台灣數據＋精簡上限（2026-10-13 使用者：「不要讓資訊過於複雜零散」）──
# 近 12 份行事曆 20–39 列（美國單區 10–24 列、同一指標拆成月增／年增／核心多列）、引言 314–418 字
# （「昨夜重點」與同頁政策總覽重複）。加入台灣官方數據的同時把上限講死，總量才不會只增不減。
CALSLIM_SINCE = "2026-10-13"


def _check_calendar_slim(md: str, rel: str, date_iso: str | None = None) -> list[str]:
    from arm import macronews
    rows = _this_week_rows(md, date_iso)
    errs = []
    tw_data = [r for r in rows if r["region"] == "台"]
    if not tw_data and not re.search(r"(?<!股)台[：:]\s*本週無", md):
        errs.append(f"{rel}：沒有「台：」台灣經濟數據列，也沒註明「台：本週無台灣重點經濟數據」"
                    "——央行理監事會／出口／外銷訂單／CPI／GDP／景氣燈號六類逐項查證")
    if len(tw_data) > macronews.TW_DATA_MAX:
        errs.append(f"{rel}：台灣數據 {len(tw_data)} 列超過 {macronews.TW_DATA_MAX}——只收六類核心數據")
    n = sum(1 for r in rows if "休市" not in (r.get("status") or ""))
    if n > macronews.CAL_MAX_ROWS:
        errs.append(f"{rel}：行事曆 {n} 列超過 {macronews.CAL_MAX_ROWS}（休市列不計）——同一指標的月增／年增／"
                    "核心併一列、刪非排定事件、依市場影響刪尾端")
    note = macronews._cal_note(md)
    if len(note) > macronews.CAL_NOTE_MAX:
        errs.append(f"{rel}：引言 {len(note)} 字超過 {macronews.CAL_NOTE_MAX}——只寫「更新／市況／本週焦點」，"
                    "昨夜重點不寫（同頁政策總覽已有），來源說明放表下「註」")
    return errs


# ── 週末版要帶上週結果（2026-10-30 使用者：「總經的行事曆有資料沒更新到」「上週結果放下面收合」）──
# 週末版原本只寫下一週，上週五的結果（非農、日本 CPI…）從沒上過網頁（10/17、10/24 兩份都沒有）。
# 擋「上週五的列、上週還沒公布的列，沒帶到週末版」；查不到實際值可以，但要帶上、在註寫原因。
LASTWEEK_SINCE = "2026-10-31"


def _check_calendar_lastweek(md: str, rel: str, date_iso: str) -> list[str]:
    import datetime as _dt
    from arm import macronews
    today = _dt.date.fromisoformat(date_iso)
    if today.weekday() < 5:
        return []
    last = macronews.last_week_cal(today, cal_dir=ROOT / "reports" / "macrocal")
    if not last:
        return []
    have = {macronews.cal_key(r) for r in macronews._parse_cal_rows(md)}
    return [f"{rel}：上週「{r['item'][:20]}」（{r['date']}）沒帶到週末版——上週五的列與上週還沒公布的列要放在表格最後、"
            "填實際值（查不到就維持未公布並在註寫原因）"
            for r in macronews.lastweek_needed(last[1], last[0]) if macronews.cal_key(r) not in have]


def run(date: str) -> int:
    errs: list[str] = []
    errs += _check_cards(ROOT / f"reports/usnews/{date}_v1.md", date)
    errs += _check_cards(ROOT / f"reports/usnews/{date}_v2.md", date)
    errs += _check_cards(ROOT / f"reports/twnews/{date}.md", date)
    errs += _check_cards(ROOT / f"reports/macronews/{date}.md", date)
    errs += _check_calendar(ROOT / f"reports/macrocal/{date}.md", date)
    _reports = (f"reports/usnews/{date}_v1.md", f"reports/usnews/{date}_v2.md",
                f"reports/twnews/{date}.md", f"reports/macronews/{date}.md")
    if date >= HEAD_SINCE:                     # 頭段總覽／速覽須抽得到（網頁總覽卡＋列印版 ③）
        errs += _check_head_sections(date)
    if date >= BRIEF_SINCE:                    # 速覽／總覽文風（長度／版型標籤／粗體落點）
        for rel in _reports:
            p = ROOT / rel
            if p.exists():
                errs += _check_brief(p.read_text(encoding="utf-8"), rel)
    if date >= READ_SINCE:                     # 卡片可讀性（粗體落點／超長句／填充語）
        for rel in _reports:
            errs += _check_card_read(ROOT / rel, rel)
    if date >= MOVE_SINCE:                     # 大變動提及閘門（fail-open：落檔讀不到＝跳過）
        try:
            import datetime as _dt
            flags = usnews.market_flags(_dt.date.fromisoformat(date))
        except Exception:
            flags = {}
        targets = []
        for rel, keys in ((f"reports/usnews/{date}_v1.md", ("sox", "tsm_adr")),
                          (f"reports/macronews/{date}.md",
                           ("us10y", "dxy", "usdtwd", "brent", "gold", "vix"))):
            p = ROOT / rel
            if p.exists():
                targets.append((rel, p.read_text(encoding="utf-8"), keys))
        errs += _check_big_moves(targets, flags)
    if errs:
        print(f"[內容 QA] 🔴 {date} 未通過（{len(errs)} 項）：")
        for e in errs:
            print(f"  ✗ {e}")
        return 1
    print(f"[內容 QA] 🟢 {date} 通過：五檔齊全、卡數/連結/重要度/行事曆結構皆合格")
    return 0


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else today_tw().strftime("%Y-%m-%d")
    sys.exit(run(d))
