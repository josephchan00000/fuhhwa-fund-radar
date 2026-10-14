"""個股「產業別」對照（ETF 持股異動方塊圖的外層分組用；2026-07-30 使用者需求）。

資料源＝證交所／櫃買**公開資訊觀測站基本資料** openapi（Tier A 官方）：
  · 上市 https://openapi.twse.com.tw/v1/opendata/t187ap03_L
  · 上櫃 https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O

落檔 `data/stock_industry.json`（**必須入庫**）：產業別半年才動一次，入庫後
①容器端建表也有分組可用（proxy 擋 twse/tpex，抓取只在 CI）；②某日 openapi 失效時
沿用既有對照，不會讓整張方塊圖退回「未分類」。合併鐵則同專案慣例：
本次抓到的覆蓋同代號舊值，**整段抓不到＝原封保留，絕不洗成空**。

欄位名在兩家 openapi 不一致（上市為中文鍵「公司代號／產業別」、上櫃為英文鍵且
歷來改過名），故解析走「**鍵名關鍵字比對＋值型態驗證**」而非寫死鍵名，並在抓不到時
把實際鍵名印進 CI 日誌供一輪收斂（同 cnyesfund／pcf 的做法）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import clock

ROOT = Path(__file__).resolve().parent.parent
DATA_FP = ROOT / "data" / "stock_industry.json"

# 證交所產業別代碼 → 名稱（t187ap03_L 的「產業別」欄有時給代碼而非名稱）。
# 名稱刻意與證交所公告用字一致（半導體業／電子零組件業…），方塊圖標籤直接沿用。
IND_CODE = {
    "01": "水泥工業", "02": "食品工業", "03": "塑膠工業", "04": "紡織纖維",
    "05": "電機機械", "06": "電器電纜", "07": "化學生技醫療", "08": "玻璃陶瓷",
    "09": "造紙工業", "10": "鋼鐵工業", "11": "橡膠工業", "12": "汽車工業",
    "13": "電子工業", "14": "建材營造", "15": "航運業", "16": "觀光餐旅",
    "17": "金融保險", "18": "貿易百貨", "19": "綜合", "20": "其他",
    "21": "化學工業", "22": "生技醫療業", "23": "油電燃氣業", "24": "半導體業",
    "25": "電腦及週邊設備業", "26": "光電業", "27": "通信網路業",
    "28": "電子零組件業", "29": "電子通路業", "30": "資訊服務業",
    "31": "其他電子業", "32": "文化創意業", "33": "農業科技業",
    "34": "電子商務", "35": "綠能環保", "36": "數位雲端", "37": "運動休閒",
    "38": "居家生活", "39": "航太工業", "80": "管理股票",
}

UNCLASSIFIED = "未分類"

_CODE_RE = re.compile(r"^\d{4}[A-Z]?$")
_CODE_KEY = re.compile(r"代號|代碼|Code|code")
_IND_KEY = re.compile(r"產業|Industry|industry")
# 上市／上櫃日期（2026-10-14 起一併落檔：臺灣50 預測要排除「截止日時還沒上市」的股票——
# 鴻勁 2025-11-27 才由興櫃轉上市，兩次審核被誤列預估納入）
_LIST_KEY = re.compile(r"上市日期|上櫃日期|ListingDate|Listing_Date|DateOfListing", re.I)


def _norm_industry(v) -> str | None:
    """產業別欄位值 → 名稱。純數字＝代碼（補零查表）；已是名稱則原樣沿用。"""
    s = str(v or "").strip()
    if not s:
        return None
    if s.isdigit():
        return IND_CODE.get(s.zfill(2))
    return s


def rows_to_map(rows) -> dict[str, str]:
    """openapi 列 → {股票代號: 產業名稱}（鍵名關鍵字比對，兩家格式通吃）。"""
    out: dict[str, str] = {}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        code = None
        for k, v in r.items():
            if _CODE_KEY.search(str(k)) and _CODE_RE.match(str(v or "").strip()):
                code = str(v).strip()
                break
        if not code:
            continue
        ind = next((_norm_industry(v) for k, v in r.items() if _IND_KEY.search(str(k))), None)
        if ind:
            out[code] = ind
    return out


def _iso_date(v) -> str | None:
    """'19620209'／'0510209'（民國）／'2025/11/27'／'114/11/27' → ISO；無法解析回 None。"""
    s = re.sub(r"[^\d/.-]", "", str(v or "").strip())
    m = re.match(r"^(\d{2,4})[/.-](\d{1,2})[/.-](\d{1,2})$", s)
    if m:
        y, mo, d = (int(x) for x in m.groups())
    elif s.isdigit() and len(s) in (7, 8):
        y, mo, d = int(s[:-4]), int(s[-4:-2]), int(s[-2:])
    else:
        return None
    if y < 1911:
        y += 1911
    if not (1950 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return f"{y:04d}-{mo:02d}-{d:02d}"


def listing_map(rows) -> dict[str, str]:
    """openapi 列 → {股票代號: 上市（櫃）日期 ISO}；找不到該欄的列略過。"""
    out: dict[str, str] = {}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        code = next((str(v).strip() for k, v in r.items()
                     if _CODE_KEY.search(str(k)) and _CODE_RE.match(str(v or "").strip())), None)
        if not code:
            continue
        d = next((_iso_date(v) for k, v in r.items() if _LIST_KEY.search(str(k))), None)
        if d:
            out[code] = d
    return out


def sample_keys(rows) -> str:
    """抓到列但一個都解析不出時，印實際鍵名供 CI 一輪收斂。"""
    for r in rows or []:
        if isinstance(r, dict):
            return "鍵名=" + "/".join(list(r)[:14])
    return "（回應非物件陣列）"


# ── 落檔 ──────────────────────────────────────────────────────────────

def load() -> dict:
    try:
        return json.loads(DATA_FP.read_text(encoding="utf-8"))
    except Exception:
        return {}


def industry_map() -> dict[str, str]:
    return (load().get("industry") or {})


def listing_dates() -> dict[str, str]:
    return (load().get("listed") or {})


def merge(fresh: dict[str, str], listed: dict[str, str] | None = None) -> dict:
    """本次新值覆蓋同代號舊值；本次全空＝原封保留（絕不洗成空）。上市日期同一套規則。"""
    doc = load()
    old = dict(doc.get("industry") or {})
    if fresh:
        old.update({k: v for k, v in fresh.items() if v})
    lst = dict(doc.get("listed") or {})
    if listed:
        lst.update({k: v for k, v in listed.items() if v})
    out = {"as_of": clock.stamp_tw() if fresh else doc.get("as_of"), "industry": old}
    if lst:
        out["listed"] = lst
    return out


def save(doc: dict) -> bool:
    if not (doc.get("industry") or {}):
        return False
    DATA_FP.parent.mkdir(parents=True, exist_ok=True)
    DATA_FP.write_text(json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True),
                       encoding="utf-8")
    return True
