"""台灣固定時程＋展會行事曆（2026-09-18 建）——提示包的「本週必列／下週預告」與央行決議旗標。

緣起：2026-09-17 央行第 3 季理監事會（利率連 10 凍、不跟進 Fed 升息；房市管制自 9/18 鬆綁：
第 2 戶房貸成數 6→7 成、土融 18 個月限期動工令退場），隔日台股報／總經報／行事曆三份全沒收。
根因是結構性的：台股報守備範圍只寫「官方統計」、總經報把「各國央行」當國際看、行事曆版型
只有美／歐／中／日／財報五類——台灣根本不在清單裡。使用者：「寫進 SOP 以後不要漏抓，
總經行事曆也加台灣重要的事，還有展覽開幕像半導體展」。

本模組只做三件事（純函式、可單測、fail-open）：
  · cbc_meeting(year, month)：央行理監事會＝3／6／9／12 月**第三個週四**（2025：3/20、6/19、
    9/18、12/18；2026：3/19、6/18、9/17、12/17 皆符），程式自算、不靠子代理記憶。
  · 種子檔 config/tw_events.json：展會／發表會（台灣＋對台股供應鏈有影響的國際大展）、
    台灣官方時程（台積電法說等）、台股休市提示——一年維護一次，日期仍以主辦單位公告為準。
  · 月度統計慣例窗（主計總處 CPI／財政部進出口／經濟部外銷訂單／失業率／景氣燈號）：
    只給「慣例落在幾號」讓子代理去查證實際公布日，不寫死日期、不杜撰。

輸出兩段提示：
  calendar_note(today)＝行事曆提示包用（本週必列＋下週預告）；
  tw_policy_note(today)＝台股報提示包用（央行決議日／隔日必成卡旗標＋房市政策必收）。
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from . import clock

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "config" / "tw_events.json"

_WD = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
CBC_MONTHS = (3, 6, 9, 12)

# 月度統計慣例窗（day_lo, day_hi, 項目）——只是「本週可能有」的查證起點，實際日期子代理查證。
MONTHLY_RULES = (
    (5, 8, "主計總處 上月 CPI／PPI"),
    (7, 9, "財政部 上月出口／進口（海關進出口貿易統計）"),
    (10, 10, "上市櫃公司 上月營收申報截止（台積電等權值股月營收）"),
    (18, 22, "經濟部 上月外銷訂單"),
    (20, 24, "主計總處 上月失業率"),
    (25, 28, "國發會 上月景氣燈號"),
)
# 季度 GDP：主計總處概估／初步統計慣例月份（月末前後）——同樣只當查證起點
QUARTERLY_GDP_MONTHS = {1: "上年 Q4 GDP 概估", 2: "上年 Q4 GDP 初步統計與全年預測",
                        4: "Q1 GDP 概估", 5: "Q1 GDP 初步統計與預測更新",
                        7: "Q2 GDP 概估", 8: "Q2 GDP 初步統計與預測更新",
                        10: "Q3 GDP 概估", 11: "Q3 GDP 初步統計與預測更新"}


def cbc_meeting(year: int, month: int) -> date | None:
    """央行理監事會日期（該月第三個週四）；非 3/6/9/12 月回 None。"""
    if month not in CBC_MONTHS:
        return None
    first = date(year, month, 1)
    off = (3 - first.weekday()) % 7          # 3＝週四
    return first + timedelta(days=off + 14)


def cbc_meetings(year: int) -> list[date]:
    return [d for m in CBC_MONTHS if (d := cbc_meeting(year, m))]


def cbc_recent(today: date | None = None, lookback: int = 2) -> date | None:
    """今日或最近 lookback 天內（含）有央行理監事會 → 回該日期，否則 None。
    lookback=2：決議在週四 16:30 後公布，週五盤前報與（週六）週末報都該收。"""
    d = today or clock.today_tw()
    for back in range(lookback + 1):
        x = d - timedelta(days=back)
        if x.month in CBC_MONTHS and cbc_meeting(x.year, x.month) == x:
            return x
    return None


def load_seed(path: Path | None = None) -> list[dict]:
    """讀種子檔；壞檔／缺檔回 []（fail-open——提示包少一段、不影響產包）。"""
    p = path or SEED
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        out = []
        for e in data.get("events", []):
            try:
                s = date.fromisoformat(e["start"])
                t = date.fromisoformat(e.get("end") or e["start"])
            except Exception:
                continue
            out.append({"name": str(e.get("name") or "").strip(), "start": s, "end": t,
                        "kind": str(e.get("kind") or "展"), "note": str(e.get("note") or ""),
                        "tentative": bool(e.get("tentative"))})
        return [e for e in out if e["name"]]
    except Exception:
        return []


def week_bounds(d: date) -> tuple[date, date]:
    """d 所在週的週一～週五（週末歸屬前一個週一起的那週，與行事曆「本週」定義一致）。"""
    mon = d - timedelta(days=d.weekday())
    return mon, mon + timedelta(days=4)


def due(today: date | None = None, events: list[dict] | None = None) -> dict:
    """回 {"this": [...], "next": [...], "cbc": date|None, "cbc_next": date|None}：
    本週（週一～週五）與下週有交集的種子事件；央行季會本週／下週日期。"""
    d = today or clock.today_tw()
    evs = load_seed() if events is None else events
    mon, fri = week_bounds(d)
    nmon, nfri = mon + timedelta(days=7), fri + timedelta(days=7)

    def hit(lo: date, hi: date) -> list[dict]:
        return sorted((e for e in evs if e["start"] <= hi and e["end"] >= lo),
                      key=lambda e: (e["start"], e["name"]))

    def cbc_in(lo: date, hi: date) -> date | None:
        for y in {lo.year, hi.year}:
            for x in cbc_meetings(y):
                if lo <= x <= hi:
                    return x
        return None

    return {"this": hit(mon, fri), "next": hit(nmon, nfri),
            "cbc": cbc_in(mon, fri), "cbc_next": cbc_in(nmon, nfri),
            "week": (mon, fri), "next_week": (nmon, nfri)}


def _fmt(e: dict) -> str:
    span = (f"{e['start']:%m/%d}" if e["start"] == e["end"]
            else f"{e['start']:%m/%d}–{e['end']:%m/%d}")
    tag = "（日期為慣例推估，須查證）" if e.get("tentative") else ""
    note = f"——{e['note']}" if e.get("note") else ""
    return f"{e['kind']}：{e['name']}（{span}）{tag}{note}"


def _monthly_hints(mon: date, fri: date) -> list[str]:
    """本週（週一～週五）與月度統計慣例窗有交集的項目（查證起點，不是日期斷言）。"""
    hints = []
    days = {(mon + timedelta(n)).day: (mon + timedelta(n)) for n in range(5)}
    months = {(mon + timedelta(n)).month for n in range(5)}
    for lo, hi, item in MONTHLY_RULES:
        if any(lo <= dd <= hi for dd in days):
            hints.append(f"台：{item}（慣例每月 {lo}{'–' + str(hi) if hi != lo else ''} 日，"
                         "請查證本週實際公布日與數值）")
    for m in months:
        if m in QUARTERLY_GDP_MONTHS and any(dd.month == m and dd.day >= 24 for dd in days.values()):
            hints.append(f"台：主計總處 {QUARTERLY_GDP_MONTHS[m]}（慣例月底前後，請查證本週是否公布）")
    return hints


def calendar_note(today: date | None = None) -> str:
    """行事曆提示包段落：本週必列（央行季會＋種子展會／時程＋月度統計慣例窗）＋下週預告。
    種子讀不到就只剩程式算得出的央行與慣例窗——永不因缺檔而整段消失。"""
    d = today or clock.today_tw()
    info = due(d)
    mon, fri = info["week"]
    lines = ["【台灣固定時程＋展會（系統自種子檔與慣例規則帶入；本週項目必列、日期仍以官方／主辦公告為準）】"]
    must: list[str] = []
    if info["cbc"]:
        x = info["cbc"]
        must.append(f"台：央行第 {CBC_MONTHS.index(x.month) + 1} 季理監事會（{x:%m/%d} {_WD[x.weekday()]}，"
                    "16:30 後記者會）——利率決議、選擇性信用管制／房市措施、GDP／CPI 預測更新；"
                    "已公布時「實際」欄填一句要點（如「利率不變、第 2 戶房貸成數放寬至 7 成」）")
    must += [_fmt(e) for e in info["this"] if e["kind"] != "休市"]
    must += _monthly_hints(mon, fri)
    halts = [e for e in info["this"] if e["kind"] == "休市"]
    if must:
        lines.append(f"· 本週（{mon:%m/%d}–{fri:%m/%d}）必列：")
        lines += [f"    - {m}" for m in must]
    else:
        lines.append(f"· 本週（{mon:%m/%d}–{fri:%m/%d}）種子檔無固定項目——仍須主動查證台灣官方數據／展會，"
                     "「台：」列至少 1 筆（台股休市日、月營收、官方統計皆可）")
    if halts:
        lines.append("· 本週台股休市提示（請核對證交所公告後寫進「市況」段台股欄）：" +
                     "；".join(f"{e['start']:%m/%d} {e['name']}" for e in halts))
    nxt: list[str] = []
    if info["cbc_next"]:
        nxt.append(f"台：央行理監事會 {info['cbc_next']:%m/%d}")
    nxt += [_fmt(e) for e in info["next"]]
    if nxt:
        nmon, nfri = info["next_week"]
        lines.append(f"· 下週預告（{nmon:%m/%d}–{nfri:%m/%d}；週五那份行事曆可在「註」段預告 1 句，不入表）：")
        lines += [f"    - {m}" for m in nxt]
    lines.append("· 「展：」列的日期＝開幕日（多日展寫「開幕 M/D、至 M/D」），「實際」欄已公布時填開幕焦點一句"
                 "（如「NVIDIA 主題演講揭 GB300 出貨時程」）；只收對台股供應鏈有影響的展會與發表會，勿灌水。")
    return "\n".join(lines)


def tw_policy_note(today: date | None = None) -> str:
    """台股報提示包段落：央行決議日（含隔日盤前、隔兩日）掛「必成卡」旗標；平日回常態提醒。"""
    d = today or clock.today_tw()
    x = cbc_recent(d)
    if x:
        when = "今日" if x == d else f"{x:%m/%d}（{_WD[x.weekday()]}）"
        return (f"⚑【央行理監事會必收】{when} 為央行理監事會（16:30 後記者會）——"
                "利率決議（含「不跟進 Fed」這類方向）、選擇性信用管制／房市措施（房貸成數、土融動工期限、"
                "新青安）、GDP／CPI 預測更新，**必成卡**（決議與房市措施可分兩卡：利率＝匯率／資金面與"
                "金融股角度；房市＝營建・資產・金融族群角度），並在速覽帶一句。這是台股本位事件、"
                "不得交給總經報（總經報只在總覽一句對照 Fed）。2026-09-17 曾三份全漏，勿再犯。")
    nxt = None
    for y in (d.year, d.year + 1):
        for m in cbc_meetings(y):
            if m > d:
                nxt = m
                break
        if nxt:
            break
    hint = f"（下次央行理監事會 {nxt:%Y/%m/%d}）" if nxt else ""
    return ("【台灣政策與房市＝台股本位必收】央行理監事會決議與選擇性信用管制、金管會／財政部／內政部的"
            "房市與金融政策（房貸成數、新青安、房地稅制、囤房稅）、房市官方數據（六都買賣移轉、"
            "房貸餘額、建物開工）——屬台股報守備範圍，重要度依投資影響評分，但當日有此類**正式政策"
            "行動**（非預告、非投顧看法）時至少成 1 卡" + hint + "。")
