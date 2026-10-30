"""行事曆官方自動補值（docs/macrocal_fill_plan.md 第二段；2026-10-30 使用者：「總經的行事曆有資料沒更新到」）。

行事曆一天只在 06:35 由 Claude 寫一次，當天 16:00、晚上才公布的數字要等到隔天早上；可是專案已經在抓這些官方序列
（data/lab/heat/：國發會景氣燈號、主計總處 CPI、經濟部外銷訂單、紐約聯準銀行利率區間、勞工統計局失業率與 CPI——
景氣頁在用）。CI 每一班抓完資料後跑這裡：最新一份 reports/macrocal/*.md 裡「日期已到、實際值空白、狀態未公布」
而且對得上這些序列的列，直接補上實際值、狀態改「已公布」，「註」加一行「官方自動補值」。隔天早上的 Claude
以昨天版當底稿，自然沿用（漂移閘門也擋「已公布退回未公布」）。

規則（寧缺勿錯）：
  · 只補空白的；項目對不上規則、月份推不出來、序列還沒有那個月、算出來剛好落在四捨五入的邊界 → 不補。
  · 項目要的東西有一部分抓不到（還要月增、非農、核心而序列沒有）→ 整列不補，留給早上的 Claude。
  · 已經填了而且和官方不同 → 不覆寫，「註」加一行「官方核對」（同一行不重複加），CI 日誌印出來。
  · 國發會會修正上個月的分數：表上寫的是第一次公布的分數（ndc_first）也算對。
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


def _r(v: float, nd: int) -> float | None:
    """四捨五入到 nd 位；離進位邊界太近（官方用的位數可能和這裡差一點）就不補。"""
    x = v * 10 ** nd
    if abs((x - math.floor(x)) - 0.5) < 0.02:
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
    bls = S("us_bls")
    core_only = bool(re.search(r"\d月核心", item))
    want_core = core_only or "核心" in item
    head = None
    if not core_only:
        y = _yoy(bls, ym, 1)
        if y is None:
            y = _yoy(S("uscpi"), ym)
        head = _r(y, 1) if y is not None else None
        if head is None:
            return None
    core = None
    if want_core:
        c = _yoy(bls, ym, 2)
        core = _r(c, 1) if c is not None else None
        if core is None:
            return None
    if core_only:
        s = _pct(core)
        return (s if "年增" in item else f"年增{s}"), [[f"{core:.1f}"]]
    s = _pct(head) + (f"（核心{_pct(core)}）" if want_core else "")
    return (s if "年增" in item else f"年增{s}"), [[f"{head:.1f}"]] + ([[f"{core:.1f}"]] if want_core else [])


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


# 區域、項目要有的字、不能有的字（還要月增、非農、會議紀要…＝抓不到或不是決議）、算法、來源
RULES = [
    {"key": "ndc", "region": "台", "re": r"(\d{1,2})月景氣(?:對策)?(?:信號|燈號)", "not": r"領先|同時|落後",
     "fn": _ndc, "src": "國發會"},
    {"key": "twcpi", "region": "台", "re": r"(\d{1,2})月(?:消費者物價(?:指數)?|CPI)",
     "not": r"核心|不含|躉售|WPI|進口|出口|月增", "fn": _twcpi, "src": "主計總處"},
    {"key": "orders", "region": "台", "re": r"(\d{1,2})月外銷訂單", "not": r"月增|季增|地區|貨品|預估|展望",
     "fn": _orders, "src": "經濟部"},
    {"key": "us_unemp", "region": "美", "re": r"(\d{1,2})月失業率", "not": r"非農|時薪|就業|申請|初領|續領",
     "fn": _us_unemp, "src": "勞工統計局"},
    {"key": "us_cpi", "region": "美", "re": r"(\d{1,2})月(?:核心)?(?:CPI|消費者物價)",
     "not": r"月增|季調|PCE|PPI|生產者|進口|出口|預期", "fn": _us_cpi, "src": "勞工統計局"},
    {"key": "fomc", "region": "美", "re": r"FOMC|聯準會|Fed", "need": r"決議",
     "not": r"紀要|紀錄|首日|會前|褐皮書|談話|緘默|官員|聽證|證詞", "fn": _fomc, "src": "紐約聯準銀行"},
]


def match(r: dict, rel: date) -> tuple[dict, str | None] | None:
    """列 → (規則, 資料月份)；對不上任何規則＝None。FOMC 不用月份。"""
    item = re.sub(r"\s+", "", r.get("item") or "")
    for rule in RULES:
        if (r.get("region") or "") != rule["region"]:
            continue
        m = re.search(rule["re"], item, re.I)
        if not m or (rule.get("not") and re.search(rule["not"], item, re.I)):
            continue
        if rule.get("need") and not re.search(rule["need"], item):
            continue
        if rule["key"] == "fomc":
            return rule, None
        ym = _ym(int(m.group(1)), rel)
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
    for i, line in enumerate(lines):
        c = _cells(line)
        if not c:
            continue
        it = c[1]
        mr = MN._REGION_RE.match(it)
        r = {"date": c[0], "item": it[mr.end():] if mr else it, "region": mr.group(1) if mr else "",
             "actual": c[3], "status": c[5]}
        rel = MN.row_end_date(r, file_date)
        if not rel or rel > today or re.search(r"休市|延|取消|改期", c[5]):
            continue
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
