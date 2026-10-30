"""行事曆官方自動補值（docs/macrocal_fill_plan.md 第二段；2026-10-30 使用者：「總經的行事曆有資料沒更新到」）。

行事曆一天只在 06:35 由 Claude 寫一次，當天 16:00、晚上才公布的數字要等到隔天早上；可是專案已經在抓這些官方序列
（data/lab/heat/：國發會景氣燈號、主計總處 CPI、經濟部外銷訂單、紐約聯準銀行利率區間、勞工統計局失業率與 CPI——
景氣頁在用）；第三段（2026-10-30）再加只有行事曆用得到的：勞工統計局非農、時薪、季調 CPI、PPI、JOLTS、ECI，
歐洲央行決議，主計總處實質 GDP 年增——這些由 arm/calsrc.py 在有列等著（wanted）的時候才抓。CI 每一班抓完資料後跑這裡：最新一份 reports/macrocal/*.md 裡「日期已到、實際值空白、狀態未公布」
而且對得上這些序列的列，直接補上實際值、狀態改「已公布」，「註」加一行「官方自動補值」。隔天早上的 Claude
以昨天版當底稿，自然沿用（漂移閘門也擋「已公布退回未公布」）。

規則（寧缺勿錯）：
  · 只補空白的；項目對不上規則、月份推不出來、序列還沒有那個月、算出來剛好落在四捨五入的邊界 → 不補。
  · 項目要的東西有一部分抓不到（還要月增、非農、核心而序列沒有）→ 整列不補，留給早上的 Claude。
  · 已經填了而且和官方不同 → 不覆寫，「註」加一行「官方核對」（同一行不重複加），CI 日誌印出來。
  · 國發會會修正上個月的分數：表上寫的是第一次公布的分數（ndc_first）也算對。
  · 景氣燈號列的前值（上個月）是國發會修正前的分數 →「註」加一行「官方核對」（2026-10-30 第四段）。
"""
from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from . import macronews as MN
from .lab import heatdata as HD

BLANK = {"", "—", "-", "–", "－", "─", "待公布", "未公布", "尚未公布"}
_PAREN = re.compile(r"（[^（）]*）|\([^()]*\)")


def _ym(m: int, rel: date) -> str | None:
    """項目寫的「N月」→ YYYY-MM：這幾項的數字一定在下一個月以後才公布（9 月的 10 月公布、12 月的隔年 1 月）；
    月份和公布月相同＝不是這幾項的寫法，不補。"""
    if not 1 <= m <= 12 or m == rel.month:
        return None
    return f"{rel.year - (m > rel.month):04d}-{m:02d}"


def _ym_back(ym: str, k: int = 12) -> str:
    y, m = int(ym[:4]), int(ym[5:7]) - k
    while m < 1:
        y, m = y - 1, m + 12
    return f"{y:04d}-{m:02d}"


def _r(v: float, nd: int, g: float = 0.02) -> float | None:
    """四捨五入到 nd 位；離進位邊界不到 g 個單位（官方用的位數可能和這裡差一點）就不補。
    g：指數三位小數算的月增（CPI、PPI）差不到 0.003 個單位，用 0.01；平均時薪只到分，最多差 0.276 個單位，用 0.28。"""
    x = v * 10 ** nd
    if abs((x - math.floor(x)) - 0.5) < g:
        return None
    return round(v, nd)


def _pct(v: float, nd: int = 1) -> str:
    return f"{v:+.{nd}f}%"


def _yoy(ser: dict, ym: str, j: int | None = None) -> float | None:
    def get(k):
        x = ser.get(k)
        if j is not None:
            x = x[j] if isinstance(x, (list, tuple)) and len(x) > j else None
        return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None
    cur, prev = get(ym), get(_ym_back(ym))
    if cur is None or not prev:
        return None
    return (cur / prev - 1) * 100


def _q_key(item: str, rel: date) -> tuple[int, int] | None:
    """項目寫的「Q3／第三季」→ (年, 季)：季資料一定在季末下一個月以後才公布（Q4 的隔年 1 月）。"""
    m = re.search(r"Q([1-4])|第([一二三四1-4])季", item, re.I)
    if not m:
        return None
    q = int(m.group(1)) if m.group(1) else "一二三四".find(m.group(2)) + 1 or int(m.group(2))
    end = q * 3
    if end == rel.month:
        return None
    return (rel.year if end < rel.month else rel.year - 1), q


def _meas(item: str, default: tuple) -> list[str]:
    """項目要月增、年增還是兩個都要（照項目裡出現的順序）；都沒寫＝default。"""
    pos = {k: item.find(k) for k in ("月增", "年增") if k in item}
    return sorted(pos, key=pos.get) or list(default)


def _core_meas(item: str, ms: list[str]) -> list[str]:
    """「核心」後面緊接月增／年增＝只要那一個；只寫「核心」＝每一個都要。"""
    if "核心" not in item:
        return []
    got = [k for k in ("月增", "年增") if "核心" + k in item]
    return got or list(ms)


def _fmt(ms: list[str], head: dict, cms: list[str], core: dict, explicit: bool) -> str:
    """一個量：「+3.7%（核心+2.6%）」（項目沒寫月增年增才加標籤）；兩個量：「年增+3.7%、月增+0.6%（核心月增+0.3%）」。"""
    lab = len(ms) > 1 or not explicit
    s = "、".join(f"{m if lab else ''}{_pct(head[m])}" for m in ms)
    if cms:
        s += "（" + "、".join(f"核心{m if lab or len(cms) > 1 else ''}{_pct(core[m])}" for m in cms) + "）"
    return s


def _cal(S, k: str, sid: str):
    """us_bls_cal（arm/calsrc.py）裡某一期某條序列的值。"""
    x = (S("us_bls_cal").get(k) or {}).get(sid)
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def _chg(S, sid: str, ym: str, k: int) -> float | None:
    a, b = _cal(S, ym, sid), _cal(S, _ym_back(ym, k), sid)
    return (a / b - 1) * 100 if a is not None and b else None


# ── 每一種列怎麼算：回傳 (實際值文字, 核對用的數字組) 或 None；每一組都要在表上的數字裡找得到（組內任一個就算）──

def _ndc(item: str, ym: str, rel: date, S) -> tuple | None:
    v = S("ndc").get(ym)
    if not v or len(v) < 8 or v[6] is None or not v[7]:
        return None
    sc = f"{v[6]:.0f}" if float(v[6]).is_integer() else f"{v[6]}"
    light = str(v[7]).strip()
    alt = (S("ndc_first").get(ym) or [None])[0]
    ok = [sc] + ([f"{alt:.0f}" if float(alt).is_integer() else f"{alt}"] if isinstance(alt, (int, float)) else [])
    return f"{sc}分（{light if light.endswith('燈') else light + '燈'}）", [ok]


def _twcpi(item: str, ym: str, rel: date, S) -> tuple | None:
    v = S("twcpi").get(ym)
    if not v or len(v) < 2 or v[1] is None:
        return None
    s = _pct(v[1], 2)
    return (s if "年增" in item else f"年增{s}"), [[f"{v[1]:.2f}"]]


def _orders(item: str, ym: str, rel: date, S) -> tuple | None:
    ser = S("orders")
    y = _yoy(ser, ym)
    y1 = _r(y, 1) if y is not None else None
    if y1 is None:
        return None
    if "年增" in item and "金額" not in item:
        return _pct(y1), [[f"{y1:.1f}"]]
    amt = ser[ym] / 100                                       # 百萬美元 → 億美元
    a1 = _r(amt, 1)
    if a1 is None:
        return None
    return f"{a1:,.1f}億美元（{_pct(y1)}）", [[f"{y1:.1f}"]]


def _us_unemp(item: str, ym: str, rel: date, S) -> tuple | None:
    v = S("us_bls").get(ym)
    if not v or v[0] is None:
        return None
    return f"{v[0]:.1f}%", [[f"{v[0]:.1f}"]]


def _us_cpi(item: str, ym: str, rel: date, S) -> tuple | None:
    """年增用未季調指數（us_bls），月增用季調指數（us_bls_cal，第三段）；項目沒寫＝年增。"""
    core_only = bool(re.search(r"\d月核心", item))
    ms = _meas(item, ("年增",))
    cms = list(ms) if core_only else _core_meas(item, ms)
    bls = S("us_bls")

    def one(m, core):
        if m == "年增":
            y = _yoy(bls, ym, 2 if core else 1)
            if y is None and not core:
                y = _yoy(S("uscpi"), ym)
        else:
            y = _chg(S, "CUSR0000SA0L1E" if core else "CUSR0000SA0", ym, 1)
            return _r(y, 1, 0.01) if y is not None else None
        return _r(y, 1) if y is not None else None

    head = {} if core_only else {m: one(m, False) for m in ms}
    core = {m: one(m, True) for m in cms}
    if None in head.values() or None in core.values():
        return None
    nums = [[f"{v:.1f}"] for v in list(head.values()) + list(core.values())]
    explicit = any(k in item for k in ("月增", "年增"))
    if core_only:
        s = _fmt(cms, core, [], {}, explicit)
    else:
        s = _fmt(ms, head, cms, core, explicit)
    return s, nums


def _us_ppi(item: str, ym: str, rel: date, S) -> tuple | None:
    """PPI 最終需求：月增用季調、年增用未季調（和勞工統計局新聞稿一致）；項目沒寫＝兩個都填。核心的定義有兩種，不補。"""
    ms = _meas(item, ("月增", "年增"))
    head = {}
    for m in ms:
        y = _chg(S, "WPSFD4", ym, 1) if m == "月增" else _chg(S, "WPUFD4", ym, 12)
        head[m] = _r(y, 1, 0.01) if y is not None else None
    if None in head.values():
        return None
    return _fmt(ms, head, [], {}, any(k in item for k in ("月增", "年增"))), [[f"{v:.1f}"] for v in head.values()]


def _us_ahe(item: str, ym: str, rel: date, S) -> tuple | None:
    """平均時薪：月增、年增都用季調（2026 年 7～9 月對過新聞稿：季調 3.2／3.1／3.0，未季調 3.1／3.8／2.9）。"""
    ms = _meas(item, ("月增", "年增"))
    head = {}
    for m in ms:
        y = _chg(S, "CES0500000003", ym, 1 if m == "月增" else 12)
        head[m] = _r(y, 1, 0.28) if y is not None else None
    if None in head.values():
        return None
    return _fmt(ms, head, [], {}, any(k in item for k in ("月增", "年增"))), [[f"{v:.1f}"] for v in head.values()]


def _us_nfp(item: str, ym: str, rel: date, S) -> tuple | None:
    """非農新增＝這個月減上個月的就業人數（季調，千人；上個月是公布當下修正後的）→「+2.9萬」。"""
    a, b = _cal(S, ym, "CES0000000001"), _cal(S, _ym_back(ym, 1), "CES0000000001")
    if a is None or b is None:
        return None
    d = (a - b) / 10
    return f"{d:+.1f}萬", [[f"{d:.1f}"]]


def _us_jolts(item: str, ym: str, rel: date, S) -> tuple | None:
    v = _cal(S, ym, "JTS000000000000000JOL")
    return (f"{v / 10:.1f}萬", [[f"{v / 10:.1f}"]]) if v is not None else None


def _us_eci(item: str, yq: str, rel: date, S) -> tuple | None:
    """就業成本指數（季資料）：季增（季調）、年增（未季調）都是勞工統計局公布的百分比；項目沒寫＝季增。"""
    pos = {k: item.find(k) for k in ("季增", "年增") if k in item}
    ms = sorted(pos, key=pos.get) or ["季增"]
    head = {m: _cal(S, yq, "CIS1010000000000Q" if m == "季增" else "CIU1010000000000A") for m in ms}
    if None in head.values():
        return None
    lab = len(ms) > 1
    return "、".join(f"{m if lab else ''}{_pct(v)}" for m, v in head.items()), [[f"{v:.1f}"] for v in head.values()]


def _twgdp(item: str, ym: str, rel: date, S) -> tuple | None:
    """主計總處實質 GDP 年增率（經濟成長率，兩位小數）；概估、初值都是最新一次公布的值。"""
    v = S("twgdp_yoy").get(ym)
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return None
    return _pct(v, 2), [[f"{v:.2f}"]]


def _ecb(item: str, k, rel: date, S) -> tuple | None:
    """決議日的新聞稿（存款利率）＋會前的存款利率序列，兩邊對得上才有（arm/calsrc.ecb_decision）。"""
    v = S("ecb_dec").get(rel.isoformat())
    if not v or len(v) < 2:
        return None
    rate, chg = v[0], v[1]
    if chg == 0:
        return f"維持{rate:.2f}%", [[f"{rate:.2f}"]]
    steps = chg / 0.25
    if abs(steps - round(steps)) > 1e-6:
        return None
    return f"{'升息' if chg > 0 else '降息'}{abs(int(round(steps)))}碼至{rate:.2f}%", [[f"{rate:.2f}"]]


def _fomc(item: str, ym: str | None, rel: date, S) -> tuple | None:
    """決議日（列的日期；寫成台北日期也一樣）前一天以前最後一筆＝會前區間，後一天以後第一筆＝會後區間
    （紐約聯準銀行的區間從決議隔天生效、隔天才公布）。前後一週內找不到、或變動不是 1 碼的整數倍 → 不補。"""
    s = S("fedtgt")
    ks = sorted(s)
    pre = [k for k in ks if k <= (rel - timedelta(days=1)).isoformat()]
    post = [k for k in ks if k >= (rel + timedelta(days=1)).isoformat()]
    if not pre or not post:
        return None
    if (rel - date.fromisoformat(pre[-1])).days > 7 or (date.fromisoformat(post[0]) - rel).days > 7:
        return None
    (lo0, hi0), (lo1, hi1) = s[pre[-1]][:2], s[post[0]][:2]
    d = round(lo1 - lo0, 4)
    if round(hi1 - hi0, 4) != d:
        return None
    rng = f"{lo1:.2f}%–{hi1:.2f}%"
    nums = [[f"{lo1:.2f}"], [f"{hi1:.2f}"]]
    if d == 0:
        return f"維持{rng}", nums
    steps = d / 0.25
    if abs(steps - round(steps)) > 1e-6:
        return None
    return f"{'升息' if d > 0 else '降息'}{abs(int(round(steps)))}碼至{rng}", nums


# 區域、項目要有的字、不能有的字（還要抓不到的東西、會議紀要…＝不補）、算法、來源；
# per＝期別（m 月、q 季、None 看列的日期）；fetch＝本機沒有那一期時要叫 arm/calsrc.py 抓哪一個（景氣頁已在抓的不填）
RULES = [
    {"key": "ndc", "region": "台", "re": r"(\d{1,2})月景氣(?:對策)?(?:信號|燈號)", "not": r"領先|同時|落後",
     "fn": _ndc, "src": "國發會"},
    {"key": "twcpi", "region": "台", "re": r"(\d{1,2})月(?:消費者物價(?:指數)?|CPI)",
     "not": r"核心|不含|躉售|WPI|進口|出口|月增", "fn": _twcpi, "src": "主計總處"},
    {"key": "orders", "region": "台", "re": r"(\d{1,2})月外銷訂單", "not": r"月增|季增|地區|貨品|預估|展望",
     "fn": _orders, "src": "經濟部"},
    {"key": "twgdp", "region": "台", "re": r"(?:Q[1-4]|第[一二三四1-4]季).*(?:GDP|經濟成長)|(?:GDP|經濟成長).*(?:Q[1-4]|第[一二三四1-4]季)",
     "not": r"預測|預估|全年|年度|名目|平減|每人|季增|年化|季調", "per": "q", "fn": _twgdp, "src": "主計總處", "fetch": "twgdp"},
    {"key": "us_unemp", "region": "美", "re": r"(\d{1,2})月失業率", "not": r"非農|時薪|就業|申請|初領|續領",
     "fn": _us_unemp, "src": "勞工統計局"},
    {"key": "us_nfp", "region": "美", "re": r"(\d{1,2})月非農", "not": r"失業率|時薪|基準|修正|ADP|民間",
     "fn": _us_nfp, "src": "勞工統計局", "fetch": "bls_cal"},
    {"key": "us_ahe", "region": "美", "re": r"(\d{1,2})月(?:平均)?時薪", "not": r"非農|失業率|實質",
     "fn": _us_ahe, "src": "勞工統計局", "fetch": "bls_cal"},
    {"key": "us_cpi", "region": "美", "re": r"(\d{1,2})月(?:核心)?(?:CPI|消費者物價)",
     "not": r"PCE|PPI|生產者|進口|出口|預期|超級核心|不含住房", "fn": _us_cpi, "src": "勞工統計局",
     "fetch": lambda item: "bls_cal" if "月增" in item else None},
    {"key": "us_ppi", "region": "美", "re": r"(\d{1,2})月(?:PPI|生產者物價)",
     "not": r"核心|不含|進口|出口|貿易|服務|商品|中間|原料", "fn": _us_ppi, "src": "勞工統計局", "fetch": "bls_cal"},
    {"key": "us_jolts", "region": "美", "re": r"(\d{1,2})月(?:JOLTS)?職缺|(\d{1,2})月JOLTS",
     "not": r"職缺率|離職|聘僱|辭職|裁員", "fn": _us_jolts, "src": "勞工統計局", "fetch": "bls_cal"},
    {"key": "us_eci", "region": "美", "re": r"(?:就業|僱用|雇用)成本|ECI", "not": r"薪資|福利|民間",
     "per": "q", "fn": _us_eci, "src": "勞工統計局", "fetch": "bls_cal"},
    {"key": "fomc", "region": "美", "re": r"FOMC|聯準會|Fed", "need": r"決議",
     "not": r"紀要|紀錄|首日|會前|褐皮書|談話|緘默|官員|聽證|證詞", "per": None, "fn": _fomc, "src": "紐約聯準銀行"},
    {"key": "ecb", "region": "歐", "re": r"ECB|歐洲央行", "need": r"決議",
     "not": r"紀要|紀錄|談話|官員|演講|緘默|聽證", "per": None, "fn": _ecb, "src": "歐洲央行", "fetch": "ecb"},
]


def match(r: dict, rel: date) -> tuple[dict, str | None] | None:
    """列 → (規則, 資料期別)；對不上任何規則＝None。FOMC、ECB 不用期別（看列的日期）。"""
    item = re.sub(r"\s+", "", r.get("item") or "")
    for rule in RULES:
        if (r.get("region") or "") != rule["region"]:
            continue
        m = re.search(rule["re"], item, re.I)
        if not m or (rule.get("not") and re.search(rule["not"], item, re.I)):
            continue
        if rule.get("need") and not re.search(rule["need"], item):
            continue
        per = rule.get("per", "m")
        if per is None:
            return rule, None
        if per == "q":
            yq = _q_key(item, rel)
            if not yq:
                return None
            return rule, (f"{yq[0]}-{yq[1] * 3:02d}" if rule["key"] == "twgdp" else f"{yq[0]}-Q{yq[1]}")
        ym = _ym(int(next(g for g in m.groups() if g)), rel)
        return (rule, ym) if ym else None
    return None


def official(r: dict, rel: date, S=HD.load) -> tuple | None:
    """列 → (實際值文字, 核對用數字, 來源)；對不上規則或序列還沒有＝None。rel＝列的結束日（公布日）。"""
    hit = match(r, rel)
    if not hit:
        return None
    rule, ym = hit
    item = re.sub(r"\s+", "", r.get("item") or "")
    got = rule["fn"](item, ym, rel, S)
    return (got[0], got[1], rule["src"]) if got else None


def _rows(md: str, file_date: date):
    """表格的每一列 → (行號, 欄位, 列 dict, 結束日)。"""
    for i, line in enumerate(md.split("\n")):
        c = _cells(line)
        if not c:
            continue
        it = c[1]
        mr = MN._REGION_RE.match(it)
        r = {"date": c[0], "item": it[mr.end():] if mr else it, "region": mr.group(1) if mr else "",
             "actual": c[3], "status": c[5]}
        yield i, c, r, MN.row_end_date(r, file_date)


def wanted(md: str, file_date: date, today: date, S=HD.load) -> set[str]:
    """公布後 3 天內、對得上第三段規則、本機又算不出來的列 → 要叫 arm/calsrc.py 抓的來源（例 {"bls_cal"}）。
    公布當天在數字出來之前每一班都會抓一次（抓不到就下一班），抓到那一期就不再抓；超過 3 天留給早上的 Claude。"""
    need: set[str] = set()
    for _, c, r, rel in _rows(md, file_date):
        if not rel or not 0 <= (today - rel).days <= 3 or re.search(r"休市|延|取消|改期", c[5]):
            continue
        hit = match(r, rel)
        f = hit[0].get("fetch") if hit else None
        key = f(re.sub(r"\s+", "", r["item"])) if callable(f) else f
        if key and official(r, rel, S) is None:
            need.add(key)
    return need


def _ndc_prev(r: dict, rel: date, cell: str, S) -> tuple | None:
    """景氣燈號列的前值（上個月）：國發會公布新月份時會修正上個月，表上還是第一次公布的分數 → (官方最新寫法, 月份)。"""
    hit = match(r, rel)
    if not hit or hit[0]["key"] != "ndc" or cell in BLANK or not MN._nums(cell):
        return None
    pym = _ym_back(hit[1], 1)
    v = S("ndc").get(pym)
    if not v or len(v) < 8 or v[6] is None or not v[7]:
        return None
    sc = f"{v[6]:.0f}" if float(v[6]).is_integer() else f"{v[6]}"
    if _consistent(cell, [[sc]]):
        return None
    light = str(v[7]).strip()
    return f"{sc}分（{light if light.endswith('燈') else light + '燈'}）", int(pym[5:])


def _short(r: dict) -> str:
    return f"{r.get('region')}：{_PAREN.sub('', r.get('item') or '').strip()}"


def _consistent(actual: str, groups: list[list[str]]) -> bool:
    """表上的數字有沒有官方的每一個數字（精度不同以較粗的比；ndc 另收第一次公布的分數）。"""
    have = MN._nums(actual)
    return all(any(MN._num_eq(x, y) for x in g for y in have) for g in groups)


def _cells(line: str) -> list[str] | None:
    s = line.strip()
    if not (s.startswith("|") and s.endswith("|")):
        return None
    c = [x.strip() for x in s.strip("|").split("|")]
    if len(c) < 6 or c[0] in ("日期", "") or set(c[0]) <= set("-: "):
        return None
    return c


def fill(md: str, file_date: date, today: date, now: datetime, S=HD.load) -> tuple[str, list[dict]]:
    """→ (新的 md, 動作清單 [{kind: fill|mismatch, item, value, actual, src}])；沒有可補的回原文。"""
    lines = md.split("\n")
    acts: list[dict] = []
    stamp = f"{now:%m/%d %H:%M}"
    for i, c, r, rel in _rows(md, file_date):
        if not rel or rel > today or re.search(r"休市|延|取消|改期", c[5]):
            continue
        pv = _ndc_prev(r, rel, c[4], S) if (today - rel).days <= 10 else None
        if pv:                                                  # 國發會公布新月份時修正了上個月（前值）
            acts.append({"kind": "prev", "item": _short(r), "value": pv[0], "actual": c[4], "src": "國發會",
                         "note": f"- 官方核對：{_short(r)}的前值（{pv[1]}月）國發會已修正為 {pv[0]}，表中寫「{c[4]}」，以官方為準。"})
        got = official(r, rel, S)
        if not got:
            continue
        val, ok_nums, src = got
        if c[3] in BLANK and "已公布" not in c[5]:
            c[3], c[5] = val, "已公布"
            lines[i] = "| " + " | ".join(c) + " |"
            acts.append({"kind": "fill", "item": _short(r), "value": val, "src": src,
                         "note": f"- 官方自動補值（{stamp}）：{_short(r)} {val}（{src}）。"})
        elif ("已公布" in c[5] and c[3] not in BLANK and (today - rel).days <= 10
              and not _consistent(c[3], ok_nums)):              # 只核對已公布的（「延後至 11/5」這類不是結果）
            acts.append({"kind": "mismatch", "item": _short(r), "value": val, "actual": c[3], "src": src,
                         "note": f"- 官方核對：{_short(r)}官方公布 {val}（{src}），表中寫「{c[3]}」，以官方為準。"})
    if not acts:
        return md, []
    out = "\n".join(lines)
    notes = [a["note"] for a in acts if a["note"] not in out]
    for a in acts:
        a["new"] = a["note"] in notes
    if notes:
        out = _add_notes(out, notes)
    return out, acts


def _add_notes(md: str, notes: list[str]) -> str:
    """加在「註：」那段最後一條之後；最後一條是免責聲明（「非投資建議」）就加在它前面。沒有「註：」就新開一段。"""
    lines = md.rstrip("\n").split("\n")
    try:
        k = next(j for j, ln in enumerate(lines) if ln.strip().startswith("註"))
    except StopIteration:
        return "\n".join(lines + ["", "註："] + notes) + "\n"
    end = k
    for j in range(k + 1, len(lines)):
        if lines[j].strip().startswith("- "):
            end = j
        elif lines[j].strip():
            break
    if end > k and "非投資建議" in lines[end]:
        end -= 1
    return "\n".join(lines[:end + 1] + notes + lines[end + 1:]) + "\n"


def latest(cal_dir: Path, today: date) -> tuple[Path, date] | None:
    """最新一份（日期不晚於今天）的行事曆檔。"""
    best = None
    for f in cal_dir.glob("*.md"):
        m = re.match(r"(\d{4}-\d{2}-\d{2})\.md$", f.name)
        if m and m.group(1) <= today.isoformat() and (best is None or m.group(1) > best[1].isoformat()):
            best = (f, date.fromisoformat(m.group(1)))
    return best


def run(today: date, now: datetime, cal_dir: Path | None = None, S=HD.load, write: bool = True) -> dict:
    """CI 用：補最新一份行事曆。寫檔前確認表格列數沒變、內容沒變短；任何一步不對就不寫。"""
    got = latest(cal_dir or MN.CAL_DIR, today)
    if not got:
        return {"file": None, "acts": []}
    f, fd = got
    md = f.read_text(encoding="utf-8")
    new, acts = fill(md, fd, today, now, S)
    wrote = False
    if write and new != md and len(MN._parse_cal_rows(new)) == len(MN._parse_cal_rows(md)) and len(new) > len(md):
        f.write_text(new, encoding="utf-8")
        wrote = True
    return {"file": str(f), "acts": acts, "wrote": wrote}
