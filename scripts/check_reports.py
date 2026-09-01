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
  · 行事曆：表頭「更新：」需為今日

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
    """回 [(標題, 內文)]——標題含「速覽」或「總覽」的小節（頭段那幾行）。"""
    out, cur, buf = [], "", []
    for line in (md or "").splitlines():
        if re.match(r"^#{2,3}\s", line.strip()):
            if cur:
                out.append((cur, "\n".join(buf)))
            cur, buf = line.strip(), []
            continue
        if cur:
            buf.append(line)
    if cur:
        out.append((cur, "\n".join(buf)))
    return [(h, b) for h, b in out if ("速覽" in h or "總覽" in h)]


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
    return errs


def run(date: str) -> int:
    errs: list[str] = []
    errs += _check_cards(ROOT / f"reports/usnews/{date}_v1.md", date)
    errs += _check_cards(ROOT / f"reports/usnews/{date}_v2.md", date)
    errs += _check_cards(ROOT / f"reports/twnews/{date}.md", date)
    errs += _check_cards(ROOT / f"reports/macronews/{date}.md", date)
    errs += _check_calendar(ROOT / f"reports/macrocal/{date}.md", date)
    _reports = (f"reports/usnews/{date}_v1.md", f"reports/usnews/{date}_v2.md",
                f"reports/twnews/{date}.md", f"reports/macronews/{date}.md")
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
