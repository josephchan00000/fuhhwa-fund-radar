"""新 ETF「自動發現」——確保沒被登錄過的檔也會現形（2026-08-10 使用者：
「你是怎麼確保之後都抓得到的呢？」）。

**要解的洞**：`etfwatch.UPCOMING` 是人工維護，既有守門（graduation／stale guard）
都只認得「已登錄」的條目——**一檔從沒登錄過的 ETF，對所有測試而言不存在、不會有
任何東西變紅**。2026-08-10 就是靠使用者的研討會投影片才發現缺 4 檔。本模組把
「發現」這件事自動化，兩層互補：

  ① **市場首見台帳（掛牌層，零版式風險）**：每輪從 TWSE/TPEx 官方每日收盤取全市場
     證券代碼，篩 ETF 型代碼記入 `data/etf_seen.json` 的「首見日」。**首見日在近
     DISCOVER_DAYS 天內、又不在 WATCHLIST+UPCOMING 的檔＝漏抓**。走的是 CI 已用了
     數週的官方端點，沒有第三方版式漂移風險；缺點是抓到時已經掛牌（下限保證：
     沒有任何一檔新 ETF 會完全從雷達上消失）。
  ② **募集前來源（前瞻層，fail-open）**：MoneyDJ 新基金募集頁（2026-08-10 使用者
     提供之權威彙整）掃 ETF 代碼。**交叉條件是關鍵**——募集中的新 ETF 還沒掛牌，
     所以不會出現在①的市場台帳裡：`頁面代碼 − 市場已掛牌 − 已登錄 = 真正的新募集
     候選`。既有 ETF 的參照連結會被「已掛牌」那項濾掉，版式再怎麼漂移都不會誤報一堆。
     解析失敗＝fail-open（回空、印 CI 日誌），只損失前瞻性、不影響①。

結果寫 `data/etf_upcoming_gap.json`（入庫）→ 儀表板「網頁更新時間」列紅章 ＋ 每日 SOP
讀它去 WebSearch 補 UPCOMING——與「前十大持股簡介」完全同型的逼補迴路。

防呆鐵則（同 etf_watch／macro_chips 慣例）：
  · **首次建台帳＝baseline**：台帳空時把當下全市場代碼一次記為既有（`seeded`），
    **不報 gap**——否則第一輪會噴出市場上 200+ 檔既有 ETF。
  · 本次抓不到（0 列）→ 台帳原封不動、gap 檔不覆寫（本容器 proxy 擋 twse/tpex/moneydj，
    本地跑一定抓不到，那是環境限制不是資料異常）。
  · 台帳只增不減：某檔下市後代碼消失，不刪首見日（重複上市不會被誤判成新檔）。
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path

from . import clock

ROOT = Path(__file__).resolve().parent.parent
SEEN_FP = ROOT / "data" / "etf_seen.json"
GAP_FP = ROOT / "data" / "etf_upcoming_gap.json"

# 「首見日在近幾天內」才算新檔——掛牌後兩個月還沒被登錄就不是「剛漏掉」而是策展決定
# （被動組刻意只策展 6 檔台股大表，不是每檔新 ETF 都要進追蹤）。
DISCOVER_DAYS = 60

# 建 baseline 的最低檔數門檻：台股 ETF 市場 200+ 檔（單上市就逾 150）。**首建那一輪若剛好
# 單邊交易所掛掉**（2026-08-05 tpex openapi 曾整輪失敗），baseline 只會含半個市場 →
# 隔天另一半全被誤判成「新掛牌」噴成雜訊。故市場檔數不足時**寧可不建帳**、下一輪再說。
MIN_MARKET_FOR_BASELINE = 100

# ETF 代碼樣式：0050／00878／006208／009827（4~6 碼、00 開頭）＋ 主動式／債券字尾
# （00991A／00986D／00679B）。台股個股是 1101~9958 不以 00 起頭；ETN 為 02 開頭、
# 權證 03~08 開頭，皆不會誤入。
_ETF_CODE = re.compile(r"^00\d{2,4}[A-Z]?$")
# MoneyDJ 頁面掃描用（需詞界，避免從長數字串中間切出假代碼）
_ETF_TOKEN = re.compile(r"(?<![0-9A-Za-z])(00\d{2,4}[A-Z]?)(?![0-9A-Za-z])")


def is_etf_code(code: str) -> bool:
    return bool(_ETF_CODE.match(str(code or "").strip()))


def load_seen() -> dict:
    """讀首見台帳：{"codes": {code: {"first": iso|None, "name": str}}, ...}。
    `first` 為 None＝baseline（首次建帳時的既有檔，永不報 gap）。"""
    try:
        d = json.loads(SEEN_FP.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) and isinstance(d.get("codes"), dict) else {"codes": {}}
    except (OSError, json.JSONDecodeError):
        return {"codes": {}}


def merge_seen(seen: dict, market: dict[str, str], today: date) -> tuple[dict, list[str]]:
    """把本次市場代碼併入台帳，回 (新台帳, 本次首見的新代碼)。

    market＝{code: name}（已篩過 ETF 型代碼）。台帳空＝首次建帳 → 全部記 baseline
    （first=None）、回空的新代碼清單；但市場檔數不足 MIN_MARKET_FOR_BASELINE（單邊
    交易所掛掉）→ **不建帳**，留待下一輪拿到完整市場再建。
    本次 market 為空 → 原封不動（來源不可達）。"""
    codes = dict(seen.get("codes") or {})
    if not market:
        return {**seen, "codes": codes}, []
    baseline = not codes                       # 首次建帳：當下全市場一次認列為既有
    if baseline and len(market) < MIN_MARKET_FOR_BASELINE:
        print(f"  ⚠ 市場僅 {len(market)} 檔 ETF（< {MIN_MARKET_FOR_BASELINE}）＝來源不完整，"
              f"本輪不建 baseline 台帳（避免隔天把另一半市場誤報成新檔）")
        return {**seen, "codes": codes}, []
    fresh: list[str] = []
    for code, name in sorted(market.items()):
        if code in codes:
            if name and not codes[code].get("name"):
                codes[code]["name"] = name     # 名稱補齊，不動首見日
            continue
        codes[code] = {"first": None if baseline else today.isoformat(), "name": name or ""}
        if not baseline:
            fresh.append(code)
    return {"codes": codes, "as_of": today.isoformat(),
            "seeded": seen.get("seeded") or (today.isoformat() if baseline else None),
            "n": len(codes)}, fresh


def listed_gaps(seen: dict, known: set[str], today: date,
                days: int = DISCOVER_DAYS) -> list[dict]:
    """已掛牌但我們完全沒登錄的新 ETF（首見日在近 days 天內）。"""
    out = []
    for code, info in (seen.get("codes") or {}).items():
        first = (info or {}).get("first")
        if not first or code in known:
            continue
        try:
            fd = date.fromisoformat(first)
        except ValueError:
            continue
        if fd >= today - timedelta(days=days):
            out.append({"code": code, "name": (info or {}).get("name") or "",
                        "first_seen": first, "kind": "listed"})
    return sorted(out, key=lambda x: (x["first_seen"], x["code"]), reverse=True)


def parse_offering_codes(html: str) -> set[str]:
    """從新基金募集頁 HTML 掃出 ETF 型代碼（版式無關：只認代碼 token）。

    刻意不解析表格結構——MoneyDJ 的 djhtm 版式會漂移，硬解一改就死。誤抓的既有
    ETF 參照連結由呼叫端以「市場已掛牌」差集濾掉（見模組 docstring 的交叉條件）。"""
    return set(_ETF_TOKEN.findall(html or ""))


def offering_gaps(offering: set[str], seen: dict, known: set[str]) -> list[dict]:
    """募集頁上、既未掛牌（不在市場台帳）也未登錄的代碼＝真正的新募集候選。"""
    listed = set((seen.get("codes") or {}).keys())
    return [{"code": c, "name": "", "first_seen": None, "kind": "offering", "src": "moneydj"}
            for c in sorted(offering - listed - known)]


# ── 名稱型前瞻（鉅亨 IPO 頁 fund.cnyes.com/IPO/，2026-08-10 使用者提供）────────
# 與 MoneyDJ 代碼層互補的第二前瞻源，且 **cnyes 對 CI 的可達性由 cnyesfund 連接器
# 天天證實**（本容器 proxy 擋、正式區不擋）——MoneyDJ 從沒在 CI 上驗證過、可能 WAF。
# 頁面列的是「基金名稱＋募集期間」而非代碼 → 以**名稱正規化比對**：未派碼的新檔
# （代碼層天生抓不到）也逮得住。誤報防線同代碼層的交叉條件，只是換到名稱空間：
# 頁上名稱 − 已登錄名（watch＋UPCOMING）− 市場台帳名（已掛牌，擋既有 ETF 廣告連結）。

_PAREN = re.compile(r"[（(][^（）()]*[）)]")
_NAME_TOKENS = re.compile(r"主動式|主動|證券投資信託|傘型|連結|ETF|基金")
_PUNCT = re.compile(r"[\s　·・．.，,、;；:：!！?？\-—–_/｜|]")


def _norm_name(s: str) -> str:
    """基金名稱 → 比對核心：去括注（收益平準金等）、去 主動(式)/ETF/基金/傘型 等詞、去標點。
    「統一前沿科技主動式ETF基金(本基金之配息來源…)」與登錄名「主動統一前沿科技」
    都正規化成「統一前沿科技」——兩邊寫法不同、核心一致才比得起來。"""
    s = _PAREN.sub("", str(s or ""))
    s = _NAME_TOKENS.sub("", s)
    return _PUNCT.sub("", s)


def _is_subseq(short: str, long: str) -> bool:
    it = iter(long)
    return all(ch in it for ch in short)


def name_match(a_norm: str, b_norm: str) -> bool:
    """同檔判定：短名是長名的**子序列**（不必連續）；<4 字不比（防泛稱誤配）。

    2026-08-10 CI 首輪修正——原本用「互相包含」（子字串），但**交易所短名是全名的
    縮寫、中間會跳字**，於是同一檔被判成兩檔：
      · 台帳 `富邦科技`(0052) vs 鉅亨 `富邦台灣科技指數` → 跳掉「台灣」就對不上 → 誤報
      · 已追蹤 `永豐科技趨勢`(00410A) vs 鉅亨 `永豐台灣科技趨勢` → 同上
    中文基金縮寫**保留字序**，所以子序列才是正確的模型（`富邦科技` ⊂ `富邦台灣科技指數` ✓；
    而 `群益台灣精選高息` 對 `群益台灣核心50` 仍不匹配 ✓ 不會過度合併）。"""
    if len(a_norm) < 4 or len(b_norm) < 4:
        return False
    short, long = sorted((a_norm, b_norm), key=len)
    return _is_subseq(short, long)


def known_names() -> set[str]:
    """已登錄名稱（正規化）＝追蹤清單＋UPCOMING 全部條目——known_codes() 的名稱層版。"""
    from . import etfwatch
    out = {_norm_name(n) for _c, n, *_ in etfwatch.watch_tuples()}
    out |= {_norm_name(it.get("name") or "") for it in etfwatch.UPCOMING}
    return {n for n in out if n}


# 名稱樣式：連續的「中文／數字／英文」串，至「ETF(基金)」結尾——HTML 文字節點與內嵌
# JSON 字串都吃得到，**不解析表格結構**（djhtm/react 版式都會漂，只認名稱字樣不會）。
# 允許數字／英文起頭（2026-08-10 CI 首輪修正）：原本限定 CJK 起頭，
# 「10年期AAA至A級美元公司債券ETF」的「10」被切掉、名稱殘缺成「年期AAA至…」而對不上任何清單。
# 年期區間的連字號／波浪號也要收（同輪第二次修：「10-35年期…」仍被切成「35年期…」）——
# 債券 ETF 名稱常見 `10-35年期`／`1～3年`，切一半就查不出是哪一檔。
# **但只在「數字之間」放行**：無條件收連字號會把前面無關的文字一起吞進來
# （實測「前後無關文字-中信10-35年期…」整串被當成名稱），那比切斷更糟。
_ETF_NAME = re.compile(r"(?:[一-鿿0-9A-Za-z]|(?<=\d)[-～~](?=\d)){2,46}ETF(?:基金)?")
_CJK = re.compile(r"[一-鿿]")


def extract_etf_names(html: str) -> list[str]:
    """從募集頁抽 ETF 名稱（去括注、正規化去重；核心 <4 字的泛稱標籤直接丟）。

    須含 ≥3 個中文字——擋掉「iShares ETF」「AI ETF」這類純英文/泛稱片段。"""
    out, seen = [], set()
    for m in _ETF_NAME.finditer(html or ""):
        raw = _PAREN.sub("", m.group(0))
        if len(_CJK.findall(raw)) < 3:
            continue
        n = _norm_name(raw)
        if len(n) >= 4 and n not in seen:
            seen.add(n)
            out.append(raw)
    return out


# ── 募集表格解析（鉅亨 IPO 頁，2026-08-10 CI 探針一輪收斂）───────────────
# 探針印出的頁面結構＝純 HTML 表格：
#   基金名稱｜基金類別｜經理人｜申請日｜核淮日期｜募集期間｜申請額度
# （「核淮」是頁面本身的錯字，比對時兩種寫法都收）。拿到這些欄位的好處：
#   ① **階段分得出來**——只有申請日、沒有核淮日期＝還在申請中，不能當「已核准」登錄；
#   ② 募集期間直接就是我們要的資料，週掃只需再找第二來源核對，不必從零查；
#   ③ 基金類別是權威的 ETF 判準（名稱字樣只是啟發式）。
# 解析不到表頭→回 []，呼叫端退回純名稱層（fail-open，不因版式改動而全盤失效）。
_TR = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_TD = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")
_COLS = (("name", ("基金名稱",)), ("cat", ("基金類別", "類別")),
         ("apply", ("申請日",)), ("approve", ("核淮日期", "核准日期", "核淮日", "核准日")),
         ("period", ("募集期間",)), ("quota", ("申請額度",)))


def _cell(fragment: str) -> str:
    return re.sub(r"\s+", " ", _TAG.sub("", fragment)).strip()


def parse_offering_table(html: str) -> list[dict]:
    """鉅亨 IPO 頁表格 → [{name, cat, apply, approve, period, quota}]（空欄為 ""）。

    欄位以**表頭文字定位**、不寫死欄序（同 stockmeta 對付兩家交易所鍵名的作法）。"""
    rows = _TR.findall(html or "")
    idx: dict[str, int] = {}
    out: list[dict] = []
    for row in rows:
        cells = [_cell(c) for c in _TD.findall(row)]
        if not cells:
            continue
        if not idx:                                     # 還沒定位表頭 → 試這一列
            for key, words in _COLS:
                for i, c in enumerate(cells):
                    if any(w in c for w in words):
                        idx[key] = i
                        break
            if "name" not in idx:
                idx = {}                                # 不是表頭列，繼續找
            continue
        if len(cells) <= idx["name"]:
            continue
        rec = {k: (cells[i] if i < len(cells) else "") for k, i in idx.items()}
        if rec.get("name"):
            out.append(rec)
    return out


# 核淮日期欄不一定是日期——實測也會填「審查中」這類狀態字（2026-08-10 CI 第二輪抓到）。
_STATE_TEXT = re.compile(r"審查|審核|申請中|處理中|補件|退件")
_HAS_DATE = re.compile(r"\d{2,4}\s*[./年-]\s*\d{1,2}")     # 115.9.14／2026-09-14／115年9月


def stage_of(rec: dict) -> str:
    """募集階段：raising（募集期間已定）／approved（核淮日期已下）／applied（申請中）。

    **申請中 ≠ 已核准**——沒有這層分辨，會把還在送件的檔當成「已核准待募」登錄上板。
    **且「核淮日期欄非空」≠ 已核准**（2026-08-10 CI 第二輪實測）：該欄會填狀態字，
    `115.9.14申報生效` 才是真核准，`審查中` 是還沒過——只看非空會把聯博兩檔與**本家
    復華台美策略**全標成已核准。故一律要求「欄位含日期樣式、且不含審查/申請中等狀態字」。"""
    period = (rec.get("period") or "").strip()
    approve = (rec.get("approve") or "").strip()
    if period and _HAS_DATE.search(period) and not _STATE_TEXT.search(period):
        return "raising"
    if approve and _HAS_DATE.search(approve) and not _STATE_TEXT.search(approve):
        return "approved"
    return "applied"


def offering_name_gaps(raw_names: list[str], seen: dict, knowns: set[str]) -> list[dict]:
    """名稱層缺口：既不匹配已登錄名、也不匹配市場台帳名（已掛牌）者。
    註：同一檔新基金可能同時被代碼層（MoneyDJ）與名稱層（cnyes）各報一筆——
    無代碼可對不上名稱、無從自動去重；週掃補登後兩筆一起消失，可接受。"""
    ledger = [_norm_name((v or {}).get("name") or "")
              for v in (seen.get("codes") or {}).values()]
    ledger = [n for n in ledger if n]
    out = []
    for raw in raw_names:
        n = _norm_name(raw)
        if any(name_match(n, k) for k in knowns):
            continue
        if any(name_match(n, l) for l in ledger):
            continue
        out.append({"code": None, "name": raw, "first_seen": None,
                    "kind": "offering", "src": "cnyes"})
    return out


def attach_offering_meta(gaps: list[dict], table: list[dict]) -> list[dict]:
    """把募集表格的階段／類別／募集期間掛到對應缺口上（依名稱正規化比對）。

    無表格（版式改了／MoneyDJ 來源）時原樣返回——缺口照報，只是少了輔助欄位。"""
    if not table:
        return gaps
    by_name = {_norm_name(r.get("name") or ""): r for r in table}
    for g in gaps:
        rec = by_name.get(_norm_name(g.get("name") or ""))
        if not rec:
            continue
        g["stage"] = stage_of(rec)
        for k in ("cat", "approve", "period"):
            if (rec.get(k) or "").strip():
                g[k] = rec[k].strip()
    return gaps


def known_codes() -> set[str]:
    """已在雷達上的代碼＝WATCHLIST（含升級檔）＋ UPCOMING 全部條目（含未派碼者跳過）。"""
    from . import etfwatch
    out = {c for c, *_ in etfwatch.watch_tuples()}
    out |= {it["code"] for it in etfwatch.UPCOMING if it.get("code")}
    return out


def save_gap(gaps: list[dict], sources_ok: bool) -> tuple[Path, bool]:
    """落 gap 檔。**來源整批不可達（sources_ok False）→ 一律不寫**（回 saved=False）。

    兩個都要擋，不是只擋覆寫（2026-08-10 實跑抓到）：
      · 有既有檔 → 不覆寫，否則本容器 proxy 擋站時會把 CI 抓到的真缺口洗成 0
        （同 factcheck.json 2026-07-29 的坑）；
      · **沒有既有檔也不新建**——「沒檢查」被寫成「0 缺口 🟢」是假訊號，
        跟著 commit 進去就成了靜默失敗（本專案反覆踩過的那一型）。

    **申請中（stage=applied）不算警示缺口**（2026-08-10 使用者：紅章 13 檔「很躁」）：
    還在送件審查的檔連我們自己的登錄規則都不收（hint 形態要求**已核准**），掛著警示
    只會永遠紅、把真警訊淹掉。它們改入 `pipeline` 欄——僅供週掃盤點、不進 count、
    不上儀表板；核准通過後（下輪 stage 變 approved）自動升入 items 才開始計數。"""
    GAP_FP.parent.mkdir(parents=True, exist_ok=True)
    if not sources_ok:
        return GAP_FP, False
    items = [g for g in gaps if g.get("stage") != "applied"]
    pipeline = [g for g in gaps if g.get("stage") == "applied"]
    GAP_FP.write_text(json.dumps(
        {"as_of": clock.stamp_tw(), "count": len(items), "items": items,
         "pipeline_n": len(pipeline), "pipeline": pipeline},
        ensure_ascii=False, indent=1), encoding="utf-8")
    return GAP_FP, True


def load_gap() -> dict:
    """儀表板用：讀最近一次缺口檔；無檔回 count=0（不壞版）。"""
    try:
        d = json.loads(GAP_FP.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {"count": 0, "items": []}
    except (OSError, json.JSONDecodeError):
        return {"count": 0, "items": []}
