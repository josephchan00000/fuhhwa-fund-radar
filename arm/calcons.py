"""行事曆「預期」欄自動補（市場共識；docs/macrocal_fill_plan.md 第五段）。

使用者 2026-11-03：「你主頁的行事曆的預估值都沒東西欸，是不是要修一下」。預期值原本只靠早上的子代理上網找，
還沒公布的數據列只有兩到四成有值。這支在 CI（scripts/run_calfill.py，官方補值之後）用兩個免費、不用金鑰的財經日曆補空白：
  · ForexFactory 週曆（nfs.faireconomy.media，只有本週；欄位 title、country、date〔美東〕、forecast）
  · Nasdaq 經濟日曆（api.nasdaq.com，任一天；欄位 gmt〔美國中部時間〕、country、eventName、consensus）
    查 D 這一天回的是美國中部時間 D 前一天的事件；同一個名字常同時有月增和年增（例 CPI），所以這種只拿來核對。

規則（使用者 2026-11-03 決定：兩個都用、互相核對；只補空白）：
  · 只補「預期」空白、還沒公布（實際空白、狀態不是已公布／休市／延後）、日期在今天前 3 天到後 10 天的列；
    子代理已經寫了的一律不動。
  · 項目要對得上下面的對照表（地區、關鍵字、要月增還是年增、要不要核心）；要的東西有一部分沒有就整列不補。
  · 兩邊都有而數字不同 → 不補（CI 日誌印出來）；只有一邊有也補（Nasdaq 名字分不出月增年增的那幾種只能核對、不能單獨補）。
  · 補上的值後面加「*」（＝市場共識、非官方，和子代理的寫法一樣），「註」加一行「預期自動補」寫哪一列、多少、哪個來源
    （同一行就地更新，不重複加）。
  · 抓到的事件兩個來源各存一份 data/lab/heat/calcons.json.gz：某一邊這輪抓不到（ForexFactory 連抓會回 429）、或盤後那支 push 被拒
    改用 --no-fetch 重算時，用那一邊兩天內存的。
"""
from __future__ import annotations

import html
import json
import re
import time
from datetime import date, datetime, timedelta, timezone

from . import calfill as CF
from . import fileio
from . import macronews as MN
from .http import get_bytes
from .lab import heatdata as HD

FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
NQ_URL = "https://api.nasdaq.com/api/calendar/economicevents?date={d}"
HDR = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
       "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9"}
SRC = {"FF": "ForexFactory", "NQ": "Nasdaq"}
SNAP = "calcons"                 # data/lab/heat/calcons.json.gz
BACK, AHEAD = 3, 10              # 補哪幾天的列：今天前 3 天到後 10 天
BUDGET_S = 90                    # run_calfill 那一步 timeout 300 秒，官方來源先用掉最多 120 秒
NQ_MAX = 14                      # Nasdaq 一輪最多查幾天
STALE_DAYS = 2                   # 存檔超過兩天不用

FF_CTRY = {"USD": "US", "EUR": "EZ", "GBP": "UK", "CNY": "CN", "JPY": "JP", "CHF": "CH"}
NQ_CTRY = {"United States": "US", "Euro Zone": "EZ", "United Kingdom": "UK", "China": "CN", "Japan": "JP",
           "Switzerland": "CH", "Germany": "DE"}
LOCAL_UTC = {"US": -5, "EZ": 1, "DE": 1, "CH": 1, "UK": 0, "CN": 8, "JP": 9}     # 事件當地日期（夏令時差一小時不影響）
NQ_CT_UTC = -6                                                                # Nasdaq 的時間是美國中部時間

BLANK = CF.BLANK
_NUM = re.compile(r"^([+-]?)(\d+(?:\.\d+)?)\s*([KMBT%]?)$")
MULT = {"": 1.0, "K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12, "%": 1.0}
UNITS = {"idx": {""}, "sidx": {""}, "cnt": {"K", "M"}, "chg": {"K", "M"}, "pct": {"%"}, "spct": {"%"},
         "rate": {"%"}, "bn": {"B", "T"}, "bbl": {"K", "M"}}


# ── 數字 ──

def parse(s) -> tuple[float, str, int] | None:
    """'7.15M' → (7.15, 'M', 2)；'-107.90B'、'1,701K'、'4.0%'、'54.8'；空白、&nbsp;、看不懂的 → None。"""
    t = html.unescape(str(s or "")).replace("\xa0", " ").replace(",", "").replace("−", "-").strip()
    m = _NUM.match(t)
    if not m:
        return None
    sign, num, unit = m.groups()
    return float(num) * (-1 if sign == "-" else 1), unit, len(num.split(".")[1]) if "." in num else 0


def _val(p: tuple) -> float:
    return round(p[0] * MULT[p[1]], 6)


def _trim(x: float, dec: int) -> str:
    """小數照來源的位數，多出來的 0 去掉到剩一位（2.40 → 2.4、4.25 → 4.25、4 → 4.0）。"""
    s = f"{abs(x):.{max(dec, 1)}f}"
    while len(s.split(".")[1]) > 1 and s.endswith("0"):
        s = s[:-1]
    return s


def _wan(x: float, signed: bool, keep0: bool) -> str:
    """人數、戶數 → 萬：19.7、715、707.9；signed 加正負號（+6.5）；keep0＝不到 100 萬保留 .0（20.0 萬，初領的寫法）。"""
    s = f"{abs(x):.1f}"
    if s.endswith(".0") and (abs(x) >= 100 or not keep0):
        s = s[:-2]
    return (("+" if x > 0 else "-" if x < 0 else "") if signed else ("-" if x < 0 else "")) + s


def fmt(kind: str, p: tuple, word: str = "") -> str:
    v, unit, dec = p
    if kind == "idx":
        return f"{v:.{dec}f}"
    if kind == "sidx":
        return f"{v:+.{dec}f}" if v else f"{v:.{dec}f}"
    if kind in ("pct", "spct"):
        s = _trim(v, dec)
        return (("+" if v > 0 else "-" if v < 0 else "") if kind == "spct" else ("-" if v < 0 else "")) + s + "%"
    if kind == "rate":
        return f"{v:.2f}%"
    if kind == "cnt":
        return _wan(_val(p) / 1e4, False, True) + (word or "萬")
    if kind == "chg":
        return _wan(_val(p) / 1e4, True, False) + (word or "萬")
    if kind == "bn":
        x = _val(p) / 1e8
        return f"{x:,.0f}" + (word or "億美元")
    if kind == "bbl":
        x = _val(p) / 1e4
        return (f"{x:+,.0f}" if round(x) else "0") + "萬桶"
    raise ValueError(kind)


# ── 對照表：項目 → 要哪幾個數字（每個數字：ForexFactory 標題、Nasdaq 名稱、格式；chk＝Nasdaq 只拿來核對）──

def P(ff=(), nq=(), k="idx", w="", chk=False) -> dict:
    return {"ff": tuple(ff), "nq": tuple(nq), "k": k, "w": w, "chk": chk}


def one(p: dict):
    return lambda item: ([p], "{0}")


def _core_mode(item: str) -> str | None:
    """只要總數（head）、只要核心（core）、兩個都要（both）；看不出來＝None（寧缺勿錯）。"""
    if "核心" not in item:
        return "head"
    body = re.sub(r"^\d{1,2}月|^第[一二三四1-4]季|^Q[1-4]", "", item)
    if body.startswith("核心") or "（核心" in item or "(核心" in item:
        return "core"
    if re.search(r"[；;、／/＋+及與和]核心", item):
        return "both"
    return None


def _meas(item: str, default: str | None) -> str | None:
    m, y = "月增" in item, "年增" in item
    if m and y:
        return None
    return "mm" if m else "yy" if y else default


def infl(head: dict, core: dict, default: str | None, nq_head=(), nq_core=(), chk=True):
    """CPI、PPI、PCE 這一類：head／core＝{"mm": ForexFactory 標題, "yy": …}；寫成「+3.7%（核心+2.6%）」。"""
    def b(item: str):
        ms, mode = _meas(item, default), _core_mode(item)
        if not ms or not mode or not head.get(ms) and mode != "core" or not core.get(ms) and mode != "head":
            return None
        h = P(head.get(ms, ()), nq_head, "spct", chk=chk)
        c = P(core.get(ms, ()), nq_core, "spct", chk=chk)
        return {"head": ([h], "{0}"), "core": ([c], "{0}"), "both": ([h, c], "{0}（核心{1}）")}[mode]
    return b


def pmi(flash: dict, final: dict, nq: dict):
    """製造業／服務業／綜合 PMI（可能一列放兩個：「製造業／服務業PMI初值」→「53.0／55.5」）；初值、終值分開，沒寫就兩個都收。"""
    def b(item: str):
        it = item.replace("非製造業", "服務業")
        ks = sorted((k for k in ("製造業", "服務業", "綜合") if k in it), key=it.find)
        if not ks:
            return None
        pre, fin = "初值" in item or "快報" in item, "終值" in item or "最終" in item
        if pre and fin:
            return None
        parts = []
        for k in ks:
            ff = (flash.get(k, ()) if not fin else ()) + (final.get(k, ()) if not pre else ())
            if not ff and not nq.get(k):
                return None
            parts.append(P(ff, nq.get(k, ()), "idx"))
        return parts, "／".join("{%d}" % i for i in range(len(parts)))
    return b


def us_gdp(item: str):
    if "年增" in item:
        return None
    if re.search(r"終值|第三次", item):
        t = ("Final GDP q/q",)
    elif re.search(r"第二次|二次|修正", item):
        t = ("Prelim GDP q/q",)
    elif re.search(r"初估|預估|初值|首次|速報", item):
        t = ("Advance GDP q/q",)
    else:
        t = ("Advance GDP q/q", "Prelim GDP q/q", "Final GDP q/q")
    return [P(t, ("GDP",), "spct", chk=True)], "{0}"


def cn_gdp(item: str):
    if "月增" in item:
        return None
    yy = P(("GDP q/y",), ("GDP",), "spct", chk=True)
    qq = P(("GDP q/q",), ("GDP",), "spct", chk=True)
    if "季增" in item and "年增" in item:
        return ([yy, qq], "{0}（{1}）") if item.find("年增") < item.find("季增") else ([qq, yy], "{0}（{1}）")
    return ([qq], "{0}") if "季增" in item else ([yy], "{0}")


def nfp(item: str):
    n = P(("Non-Farm Employment Change",), ("Nonfarm Payrolls",), "chg")
    if "失業率" in item:
        return [n, P(("Unemployment Rate",), ("Unemployment Rate",), "pct")], "{0}（{1}）"
    return [n], "{0}"


def tankan(item: str):
    if "非製造業" in item:
        return [P(("Tankan Non-Manufacturing Index",), ("Tankan Large Non-Manufacturers Index",), "sidx")], "{0}"
    return [P(("Tankan Manufacturing Index",), ("Tankan Large Manufacturers Index",), "sidx")], "{0}"


def lpr(item: str):
    return [P(("1-y Loan Prime Rate",), (), "rate"), P(("5-y Loan Prime Rate",), (), "rate")], "{0}／{1}"


US, EZ = ("US",), ("EZ",)
# (地區, 國別, 要有的關鍵字, 不能有的字, 怎麼對)；由上往下第一個對到的算數
RULES = [
    ("美", US, r"初領失業金|初請失業金", "", one(P(("Unemployment Claims",), ("Initial Jobless Claims",), "cnt"))),
    ("美", US, r"JOLTS|職缺", "", one(P(("JOLTS Job Openings",), ("JOLTS Job Openings",), "cnt"))),
    ("美", US, r"ADP", r"每週|週報|當週", one(P(("ADP Non-Farm Employment Change",), ("ADP Nonfarm Employment Change",), "chg"))),
    ("美", US, r"非農", r"時薪|薪資|參與率", nfp),
    ("美", US, r"失業率", r"時薪|薪資", one(P(("Unemployment Rate",), ("Unemployment Rate",), "pct"))),
    ("美", US, r"ISM.*製造業.*(物價|價格)", "", one(P(("ISM Manufacturing Prices",), ("ISM Manufacturing Prices",)))),
    ("美", US, r"ISM.*(服務業|非製造業).*(物價|價格)", "",
     one(P(("ISM Services Prices",), ("ISM Non-Manufacturing Prices", "ISM Services Prices")))),
    ("美", US, r"ISM.*(服務業|非製造業)", r"物價|價格|就業|新訂單|分項",
     one(P(("ISM Services PMI",), ("ISM Non-Manufacturing PMI", "ISM Services PMI")))),
    ("美", US, r"ISM.*製造業", r"物價|價格|就業|新訂單|分項", one(P(("ISM Manufacturing PMI",), ("ISM Manufacturing PMI",)))),
    ("美", US, r"(密大|密西根).*(信心|情緒)", r"通膨|預期|現況|終值.*初值",
     lambda it: ([P(("Revised UoM Consumer Sentiment",) if "終值" in it else ("Prelim UoM Consumer Sentiment",),
                    ("Michigan Consumer Sentiment",))], "{0}")),
    ("美", US, r"(世界大型企業|經濟諮商會|諮商會|CB).*信心", r"預期|現況",
     one(P(("CB Consumer Confidence",), ("CB Consumer Confidence",)))),
    ("美", US, r"零售銷售", r"核心|控制|除|年增", one(P(("Retail Sales m/m",), ("Retail Sales",), "spct", chk=True))),
    ("美", US, r"耐久財", r"核心|除|年增", one(P(("Durable Goods Orders m/m",), ("Durable Goods Orders",), "spct", chk=True))),
    ("美", US, r"工業生產", r"年增|產能", one(P(("Industrial Production m/m",), ("Industrial Production",), "spct", chk=True))),
    ("美", US, r"PCE", r"個人所得|支出",
     infl({"mm": ("PCE Price Index m/m",), "yy": ("PCE Price Index y/y",)},
          {"mm": ("Core PCE Price Index m/m",), "yy": ("Core PCE Price Index y/y",)}, None,
          ("PCE Price Index",), ("Core PCE Price Index",))),
    ("美", US, r"CPI", r"預期|通膨預期",
     infl({"mm": ("CPI m/m",), "yy": ("CPI y/y",)}, {"mm": ("Core CPI m/m",), "yy": ("Core CPI y/y",)}, None,
          ("CPI",), ("Core CPI",))),
    ("美", US, r"PPI", "",
     infl({"mm": ("PPI m/m",), "yy": ("PPI y/y",)}, {"mm": ("Core PPI m/m",), "yy": ("Core PPI y/y",)}, None,
          ("PPI",), ("Core PPI",))),
    ("美", US, r"GDP", r"GDPNow|物價|平減|消費", us_gdp),
    ("美", US, r"貿易(收支|差額|逆差)", r"商品", one(P(("Trade Balance",), ("Trade Balance",), "bn"))),
    ("美", US, r"新屋銷售", r"月增|年增", one(P(("New Home Sales",), ("New Home Sales",), "cnt", "萬戶"))),
    ("美", US, r"成屋銷售", r"月增|年增|待完成", one(P(("Existing Home Sales",), ("Existing Home Sales",), "cnt", "萬戶"))),
    ("美", US, r"S&P|標普", "",
     pmi({"製造業": ("Flash Manufacturing PMI",), "服務業": ("Flash Services PMI",), "綜合": ("Flash Composite PMI",)},
         {"製造業": ("Final Manufacturing PMI",), "服務業": ("Final Services PMI",), "綜合": ("Final Composite PMI",)},
         {"製造業": ("S&P Global Manufacturing PMI",), "服務業": ("S&P Global Services PMI",),
          "綜合": ("S&P Global Composite PMI",)})),
    ("美", US, r"紐約|帝國", r"服務", one(P(("Empire State Manufacturing Index",), ("NY Empire State Manufacturing Index",)))),
    ("美", US, r"費城", r"服務", one(P(("Philly Fed Manufacturing Index",), ("Philadelphia Fed Manufacturing Index",)))),
    ("美", US, r"EIA.*原油庫存|原油庫存", r"API|庫欣", one(P(("Crude Oil Inventories",), ("Crude Oil Inventories",), "bbl"))),
    ("歐", EZ, r"(ECB|歐洲央行|歐央行).*(利率|決議)", r"紀要|談話|演說|記錄",
     one(P(("Deposit Facility Rate",), ("Deposit Facility Rate",), "rate", "存款利率"))),
    ("歐", ("UK",), r"(英國央行|英格蘭銀行|BoE|BOE).*(利率|決議)", r"紀要|談話|演說|報告$",
     one(P(("Official Bank Rate",), ("BoE Interest Rate Decision",), "rate"))),
    ("歐", ("CH",), r"(瑞士央行|瑞士國家銀行|SNB).*(利率|決議)", r"談話|演說",
     one(P(("SNB Policy Rate",), ("SNB Interest Rate Decision",), "rate"))),
    ("歐", EZ, r"歐元區.*(HICP|CPI|通膨).*(快報|初值|初估)",  "",
     infl({"yy": ("CPI Flash Estimate y/y",)}, {"yy": ("Core CPI Flash Estimate y/y",)}, "yy", ("CPI",), ("Core CPI",))),
    ("歐", EZ, r"歐元區.*(HICP|CPI|通膨).*(終值|最終)|歐元區.*最終.*(HICP|CPI)", "",
     infl({"yy": ("Final CPI y/y",)}, {"yy": ("Final Core CPI y/y",)}, "yy", ("CPI",), ("Core CPI",))),
    ("歐", EZ, r"歐元區.*PMI", "",
     pmi({"製造業": ("Flash Manufacturing PMI",), "服務業": ("Flash Services PMI",), "綜合": ("Flash Composite PMI",)},
         {"製造業": ("Final Manufacturing PMI",), "服務業": ("Final Services PMI",), "綜合": ("Final Composite PMI",)},
         {"製造業": ("HCOB Eurozone Manufacturing PMI",), "服務業": ("HCOB Eurozone Services PMI",),
          "綜合": ("HCOB Eurozone Composite PMI",)})),
    ("歐", ("UK",), r"英國.*(CPI|通膨)", r"終值",
     infl({"yy": ("CPI y/y",), "mm": ("CPI m/m",)}, {"yy": ("Core CPI y/y",)}, "yy", ("CPI",), ("Core CPI",))),
    ("歐", ("EZ", "DE"), r"德國.*(Ifo|IFO)", r"預期|現況",
     one(P(("German Ifo Business Climate",), ("Ifo Business Climate Index",)))),
    ("歐", ("EZ", "DE"), r"德國.*ZEW", r"現況",
     one(P(("German ZEW Economic Sentiment",), ("ZEW Economic Sentiment",)))),
    ("中", ("CN",), r"(財新|RatingDog).*服務業", r"綜合",
     one(P(("RatingDog Services PMI", "Caixin Services PMI"), ("RatingDog Services PMI", "Caixin Services PMI")))),
    ("中", ("CN",), r"(財新|RatingDog).*製造業", "",
     one(P(("RatingDog Manufacturing PMI", "Caixin Manufacturing PMI"),
           ("RatingDog Manufacturing PMI", "Caixin Manufacturing PMI")))),
    ("中", ("CN",), r"非製造業PMI", r"財新|RatingDog",
     one(P(("Non-Manufacturing PMI",), ("Non-Manufacturing PMI", "NBS Non-Manufacturing PMI")))),
    ("中", ("CN",), r"製造業PMI", r"財新|RatingDog|非製造業",
     one(P(("Manufacturing PMI",), ("Manufacturing PMI", "NBS Manufacturing PMI", "Chinese Manufacturing PMI")))),
    ("中", ("CN",), r"CPI", r"核心", infl({"yy": ("CPI y/y",), "mm": ("CPI m/m",)}, {}, "yy", ("CPI",))),
    ("中", ("CN",), r"PPI", "", infl({"yy": ("PPI y/y",)}, {}, "yy", ("PPI",))),
    ("中", ("CN",), r"工業(生產|增加值)", r"利潤|月增", one(P(("Industrial Production y/y",), ("Industrial Production",), "spct", chk=True))),
    ("中", ("CN",), r"社會消費品零售|零售銷售", r"月增",
     one(P(("Retail Sales y/y",), ("Retail Sales",), "spct", chk=True))),
    ("中", ("CN",), r"固定資產投資", r"月增", one(P(("Fixed Asset Investment ytd/y",), ("Fixed Asset Investment",), "spct", chk=True))),
    ("中", ("CN",), r"GDP", "", cn_gdp),
    ("中", ("CN",), r"LPR|貸款市場報價利率", "", lpr),
    ("日", ("JP",), r"日銀.*(利率|貨幣政策會議)", r"摘要|紀要|談話|演說|副總裁|意見",
     one(P(("BOJ Policy Rate",), ("BoJ Interest Rate Decision",), "rate"))),
    ("日", ("JP",), r"東京.*CPI", r"月增",
     infl({"yy": ("Tokyo CPI y/y",)}, {"yy": ("Tokyo Core CPI y/y",)}, "yy", ("Tokyo CPI",), ("Tokyo Core CPI",), chk=False)),
    ("日", ("JP",), r"全國.*CPI|^\d{1,2}月CPI", r"月增",
     infl({"yy": ("National CPI y/y",)}, {"yy": ("National Core CPI y/y",)}, "yy", ("National CPI",),
          ("National Core CPI",), chk=False)),
    ("日", ("JP",), r"短觀", "", tankan),
    ("日", ("JP",), r"(Jibun|jibun|au).*PMI", "",
     pmi({"製造業": ("Flash Manufacturing PMI",), "服務業": ("Flash Services PMI",)},
         {"製造業": ("Final Manufacturing PMI",), "服務業": ("Final Services PMI",)},
         {"製造業": ("au Jibun Bank Manufacturing PMI",), "服務業": ("au Jibun Bank Services PMI",)})),
    ("日", ("JP",), r"核心機械訂單|機械訂單", r"年增",
     one(P(("Core Machinery Orders m/m",), ("Core Machinery Orders",), "spct", chk=True))),
]


def match(r: dict) -> tuple[tuple, list[dict], str] | None:
    """列 → (國別, 要的數字, 格式)；對不上＝None。"""
    reg = r.get("region") or ""
    item = re.sub(r"\s+", "", r.get("item") or "")
    for rg, ctry, inc, exc, build in RULES:
        if rg != reg or not re.search(inc, item) or (exc and re.search(exc, item)):
            continue
        got = build(item)
        return (ctry, got[0], got[1]) if got else None
    return None


# ── 事件 ──

def _ev_ff(rows: list) -> list[list]:
    out = []
    for x in rows or []:
        c = FF_CTRY.get(str(x.get("country") or ""))
        if not c or not str(x.get("forecast") or "").strip():
            continue
        try:
            dt = datetime.fromisoformat(str(x.get("date")))
        except ValueError:
            continue
        d = (dt.astimezone(timezone.utc) + timedelta(hours=LOCAL_UTC[c])).date() if dt.tzinfo else dt.date()
        out.append(["FF", c, str(x.get("title") or "").strip(), d.isoformat(), str(x.get("forecast")).strip()])
    return out


def _ev_nq(rows: list, qd: date) -> list[list]:
    out = []
    for x in rows or []:
        c = NQ_CTRY.get(str(x.get("country") or "").strip())
        v = html.unescape(str(x.get("consensus") or "")).replace("\xa0", " ").strip()
        if not c or not v or v == "-":
            continue
        m = re.match(r"^(\d{1,2}):(\d{2})$", str(x.get("gmt") or "").strip())
        ct = datetime.combine(qd - timedelta(days=1), datetime.min.time()) + (
            timedelta(hours=int(m.group(1)), minutes=int(m.group(2))) if m else timedelta(hours=12))
        d = (ct - timedelta(hours=NQ_CT_UTC) + timedelta(hours=LOCAL_UTC[c])).date()
        out.append(["NQ", c, re.sub(r"\s+", " ", str(x.get("eventName") or "")).strip(), d.isoformat(), v])
    return out


def _get(url: str) -> bytes:
    return get_bytes(url, retries=1, timeout=20, use_cache=False, headers=HDR)


def fetch_events(qdates: list[date], get=None, pause: float = 1.0, budget: float = BUDGET_S) -> tuple[list, list[str]]:
    """ForexFactory 本週＋Nasdaq 指定的幾天 → (事件 [[來源, 國別, 名稱, 當地日期, 預期值]…], 日誌)；抓不到的那一邊略過。"""
    get = get or _get
    t0, ev, log = time.time(), [], []
    try:
        ff = _ev_ff(json.loads(get(FF_URL).decode("utf-8", "replace")))
        ev += ff
        log.append(f"ForexFactory 本週 {len(ff)} 則有預期值")
    except Exception as e:                                    # noqa: BLE001
        log.append(f"ForexFactory 抓取失敗：{type(e).__name__}: {str(e)[:120]}")
    n, bad = 0, 0
    for qd in qdates[:NQ_MAX]:
        if time.time() - t0 > budget:
            log.append(f"Nasdaq 超過 {budget:.0f} 秒，{qd} 以後不抓")
            break
        try:
            j = json.loads(get(NQ_URL.format(d=qd.isoformat())).decode("utf-8", "replace"))
            got = _ev_nq(((j.get("data") or {}).get("rows")) or [], qd)
            ev += got
            n += len(got)
        except Exception as e:                                # noqa: BLE001
            bad += 1
            if bad == 1:
                log.append(f"Nasdaq {qd} 抓取失敗：{type(e).__name__}: {str(e)[:120]}")
        if pause:
            time.sleep(pause)
    log.append(f"Nasdaq 查 {min(len(qdates), NQ_MAX)} 天、{n} 則有預期值" + (f"、{bad} 天失敗" if bad else ""))
    return ev, log


# ── 補 ──

def _rows_todo(md: str, file_date: date, today: date):
    """要補的列：預期空白、還沒公布、日期在範圍內、對得上對照表 → (行號, 欄位, 列, 日期, 對照)。"""
    for i, c, r, rel in CF._rows(md, file_date):
        if not rel or not -BACK <= (rel - today).days <= AHEAD:
            continue
        if c[2] not in BLANK or c[3] not in BLANK or re.search(r"已公布|休市|延|取消|改期", c[5]):
            continue
        m = match(r)
        if m:
            yield i, c, r, rel, m


def query_dates(md: str, file_date: date, today: date) -> list[date]:
    """要查 Nasdaq 的日子：每一列日期前一天到後兩天（查 D 回美國中部時間 D 前一天）。"""
    ds = set()
    for _, _, _, rel, _ in _rows_todo(md, file_date, today):
        ds.update(rel + timedelta(days=k) for k in range(-1, 3))
    return sorted(ds)


def _pick(events: list, src: str, names: tuple, ctry: tuple, rd: date, kind: str) -> list[tuple]:
    want = {n.lower() for n in names}
    out = []
    for e in events:
        if e[0] != src or e[1] not in ctry or e[2].lower() not in want:
            continue
        try:
            d = date.fromisoformat(e[3])
        except ValueError:
            continue
        p = parse(e[4])
        if abs((d - rd).days) <= 1 and p and p[1] in UNITS[kind]:
            out.append(p)
    return out


def _part(events: list, part: dict, ctry: tuple, rd: date) -> tuple[tuple | None, set, str]:
    """一個數字 → (值, 用到的來源, 不補的原因)。"""
    k = part["k"]
    ff = _pick(events, "FF", part["ff"], ctry, rd, k) if part["ff"] else []
    nq = _pick(events, "NQ", part["nq"], ctry, rd, k) if part["nq"] else []
    fv, nv = {_val(p) for p in ff}, {_val(p) for p in nq}
    if len(fv) > 1:
        return None, set(), f"ForexFactory 同名有 {len(fv)} 個不同的數"
    chk = part["chk"] or len(nv) > 1                          # 名字分不出月增年增（或同名不只一個數）→ 只核對
    if fv:
        f = ff[0]
        if nv and _val(f) not in nv:
            return None, set(), f"兩邊不同：ForexFactory {f[0]:g}{f[1]}、Nasdaq {'／'.join(f'{p[0]:g}{p[1]}' for p in nq)}"
        return f, {"FF", "NQ"} if nv else {"FF"}, ""
    if nv and not chk:
        return nq[0], {"NQ"}, ""
    return None, set(), "沒有"


def _rate_note(v: float, prev_cell: str) -> str:
    ps = MN._nums(prev_cell)
    if len(ps) != 1 or "%" not in prev_cell:
        return ""
    bp = round((v - float(ps[0])) * 100)
    return "（維持）" if bp == 0 else f"（升息{bp}bp）" if bp > 0 else f"（降息{-bp}bp）"


def value_for(r: dict, rd: date, prev_cell: str, events: list) -> tuple[str | None, str]:
    """列 → (預期值文字〔不含 *〕, 來源或不補的原因)。"""
    m = match(r)
    if not m:
        return None, "對不上"
    ctry, parts, tpl = m
    vals, srcs, both = [], set(), True
    for part in parts:
        p, s, why = _part(events, part, ctry, rd)
        if p is None:
            return None, why
        vals.append(fmt(part["k"], p, part["w"] if part["k"] != "rate" else ""))
        srcs |= s
        both = both and len(s) == 2
    txt = tpl.format(*vals)
    if len(parts) == 1 and parts[0]["k"] == "rate":
        txt = parts[0]["w"] + txt + _rate_note(parse(vals[0])[0], prev_cell)
    src = "、".join(SRC[s] for s in sorted(srcs)) + ("一致" if both and len(srcs) == 2 else "")
    return txt, src


NOTE_HEAD = "- 預期自動補"


def _note(md: str, entries: list[str], stamp: str) -> str:
    """「註」裡那一行就地更新（原有的項目留著、同一列不重複）；沒有就加一行。"""
    lines = md.split("\n")
    k = next((j for j, ln in enumerate(lines) if ln.strip().startswith(NOTE_HEAD)), None)
    old = []
    if k is not None:
        body = lines[k].split("）：", 1)[1] if "）：" in lines[k] else ""
        old = [x for x in body.rstrip("。").split("；") if x.strip()]
    seen = {x.split(" ")[0] for x in old}
    allx = old + [e for e in entries if e.split(" ")[0] not in seen]
    line = f"{NOTE_HEAD}（{stamp}；市場共識、非官方）：" + "；".join(allx) + "。"
    if k is not None:
        lines[k] = line
        return "\n".join(lines)
    return CF._add_notes(md, [line])


def fill(md: str, file_date: date, today: date, now: datetime, events: list) -> tuple[str, list[dict]]:
    """→ (新的 md, 動作 [{kind: fill|skip, item, value, src, why}])；沒有補到任何一列就回原文。"""
    lines = md.split("\n")
    acts, entries = [], []
    for i, c, r, rel, _m in _rows_todo(md, file_date, today):
        txt, src = value_for(r, rel, c[4], events)
        short = CF._short(r)
        if not txt:
            acts.append({"kind": "skip", "item": short, "why": src})
            continue
        c[2] = txt + "*"
        lines[i] = "| " + " | ".join(c) + " |"
        acts.append({"kind": "fill", "item": short, "value": txt, "src": src})
        entries.append(f"{short.replace(' ', '')} {txt}（{src}）")
    if not entries:
        return md, acts
    return _note("\n".join(lines), entries, f"{now:%m/%d %H:%M}"), acts


def merge_snapshot(events: list, now: datetime, save: bool = True) -> tuple[list, list[str]]:
    """兩個來源各存一份（data/lab/heat/calcons.json.gz：{"FF": {"as_of", "ev"}, "NQ": {…}}）：這次抓到的那一邊換新；
    沒抓到的那一邊（例 ForexFactory 回 429、push 被拒重算不抓）用存檔裡兩天內的。"""
    snap = HD.load(SNAP)
    stamp = now.isoformat(timespec="minutes")
    out, log, changed = [], [], False
    for src in ("FF", "NQ"):
        got = [e for e in events if e[0] == src]
        if got:
            out += got
            snap[src] = {"as_of": stamp, "ev": got}
            changed = True
            continue
        old = snap.get(src) if isinstance(snap.get(src), dict) else {}
        try:
            age = (now.replace(tzinfo=None) - datetime.fromisoformat(str(old.get("as_of"))).replace(tzinfo=None)).days
        except (TypeError, ValueError):
            age = None
        if old.get("ev") and age is not None and age < STALE_DAYS:
            out += old["ev"]
            log.append(f"{SRC[src]} 用 {str(old['as_of'])[:16]} 存的 {len(old['ev'])} 則")
    if save and changed:
        HD.save(SNAP, "ForexFactory 週曆、Nasdaq 經濟日曆", {k: v for k, v in snap.items() if k in ("FF", "NQ")})
    return out, log


def run(today: date, now: datetime, cal_dir=None, fetch: bool = True, write: bool = True, get=None,
        pause: float = 1.0) -> dict:
    """CI 用：補最新一份行事曆的「預期」空白。寫檔前確認表格列數沒變、內容變長；任何一步不對就不寫。"""
    got = CF.latest(cal_dir or MN.CAL_DIR, today)
    if not got:
        return {"file": None, "acts": [], "log": ["沒有行事曆檔"], "wrote": False}
    f, fd = got
    md = f.read_text(encoding="utf-8")
    qd = query_dates(md, fd, today)
    if not qd:
        return {"file": str(f), "acts": [], "log": ["沒有要補的列"], "wrote": False}
    events, log = [], []
    if fetch:
        events, log = fetch_events(qd, get=get, pause=pause)
    events, more = merge_snapshot(events, now, save=fetch)
    log += more
    if not events:
        return {"file": str(f), "acts": [], "log": log + ["沒有事件可用"], "wrote": False}
    new, acts = fill(md, fd, today, now, events)
    wrote = False
    if write and new != md and len(MN._parse_cal_rows(new)) == len(MN._parse_cal_rows(md)) and len(new) > len(md):
        fileio.write_text(f, new)
        wrote = True
    return {"file": str(f), "acts": acts, "log": log, "wrote": wrote}
