"""景氣溫度頁 → dashboard/x9m.html ＋ dashboard/x9mh.json（docs/lab_heat_plan.md 第 12、13、14 節；入口＝籌碼雷達頂欄「景氣」小字，主頁不加入口）。

第五版（第 14 節）：頁首換成五個面向的近 52 週熱度色帶；每一項加歷史位置（近 3 年／10 年／有資料以來的百分位、創幾年新高）；
核心 13 項加邊際變化（二次微分）；新的「對照台股」互動圖（點選最多 5 條線，上圖是線、下圖是加權指數，共用時間軸），
只選 1 條時列出這一項和台股的關係（領先落後、Granger、滾動相關、五區、進入過熱過冷事件），選多條時在瀏覽器算交互分析。

五個面向各一張卡（基本面、籌碼、全球資金、台灣資金、技術；使用者 2026-10-17：「要把短線籌碼熱度跟基本面區隔開來看」，
第四版再把資金拆成全球與台灣）：
分數、五段色條、和上週比、過去同一區之後的表現、判定；細項一律展開：每一項自己的 0～100、拉動分數幾分、佔比、本週增減
（使用者：「我要可以看到裡面的細項影響佔比，各項都有一個 0～100 讓我參考，不然這種綜合指標很容易只有象徵性」）。
當天的分數用 heatcalc 同一套算法重算；過去的分區統計與判定讀研究檔 data/lab/heat_research.json（只當資訊）。
技術卡後面是「關鍵價位與事件」（heattech）：均線、扣抵值、前波高低點、支撐壓力、近期事件與事件研究（不進分數）。
輸出決定性：不寫牆鐘時間，資料沒變時位元組相同。用字照專案禁用詞，不寫買賣指示。
"""
from __future__ import annotations

import bisect
import html
import json
import math
from datetime import date
from pathlib import Path

from . import heat as H
from . import heatcalc as C
from . import heatchart as HC
from . import heatpos as HP
from . import heatreg as RG
from . import heatspec as S
from . import heattech as TT

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dashboard" / "x9m.html"
OUT_DATA = HC.OUT
RES = ROOT / "data" / "lab" / "heat_research.json"
TA_RECENT = 60                      # 「近期事件」列最近幾個交易日
WEEK = S.CHG_DAYS
SIGNED = {"B2", "B4", "B5", "B6", "B7", "B8", "C2", "C4", "C5", "C6", "G1", "G2", "G3", "G4",
          "L1", "L2", "L3", "L4", "L5", "L6", "L7", "L9", "L10", "T1", "T2", "T3", "T7", "T12", "T13",
          "X1", "X2", "X3", "X4", "X5"}
DEC = {"B1": 0, "B3": 1, "B4": 1, "B5": 1, "B6": 1, "C1": 0, "C2": 1, "C4": 1, "C5": 0, "C6": 1, "C7": 1, "C8": 2,
       "L5": 1, "L6": 1, "L9": 3, "T1": 1, "T2": 1, "T3": 1, "T4": 1, "T5": 1, "T6": 1, "T7": 1, "T8": 1, "T11": 0,
       "T12": 2, "T13": 1, "X2": 1, "X3": 1, "X5": 1, "X6": 1, "X7": 0}
# 沒有 0～100 的固定原因（其他項目沒有分數時寫「沒有最新資料」或「歷史還不夠」）
WHY = {"L6": "證期局只公開最新一期新聞稿，從 2026 年 9 月開始累積，滿 60 個月才有 0～100"}
SRC = {
    "B1": "國發會", "B2": "國發會", "B3": "國發會", "B4": "經濟部", "B5": "國發會（海關出口值）",
    "B6": "自算（公開資訊觀測站月營收）", "B7": "主計總處", "B8": "勞工統計局",
    "C1": "FinMind（證交所融資融券）", "C2": "FinMind（證交所融資融券）", "C3": "FinMind（證交所融資融券）",
    "C4": "FinMind（期交所）", "C5": "FinMind（期交所法人未平倉）", "C6": "FinMind（期交所）", "C7": "期交所",
    "C8": "投信投顧公會（國內股票型基金持股比重，週）",
    "G1": "聯準會 H.15、紐約聯準銀行", "G2": "美國財政部", "G3": "美國財政部", "G4": "Yahoo HYG、IEF",
    "G5": "OFR 貨幣基金監測、Yahoo ^GSPC",
    "L1": "央行", "L2": "央行", "L3": "FinMind＋證交所成交金額", "L4": "央行", "L5": "證交所",
    "L6": "證期局外資新聞稿", "L7": "證交所（外資及陸資投資類股持股比率表）", "L8": "央行（定存單、M2）",
    "L9": "央行（金融業拆款利率）", "L10": "央行（存款、放款）",
    "T1": "證交所加權指數", "T2": "證交所加權指數", "T3": "證交所加權指數", "T4": "證交所加權指數",
    "T5": "自算（上市櫃日線）", "T6": "自算（上市櫃日線）", "T7": "自算（上市櫃日線）", "T8": "證交所加權指數",
    "T9": "Yahoo ^VIX", "T10": "期交所", "T11": "證交所加權指數", "T12": "證交所加權指數", "T13": "證交所加權指數",
}
BAND_CLS = {"過冷": "b0", "偏冷": "b1", "中性": "b2", "偏熱": "b3", "過熱": "b4"}
# 對照圖的 5 個線色：避開過冷藍、過熱紅（那兩色代表冷熱），白底用 dataviz 的 validate_palette.js 驗過（相鄰檢查全過）
PALETTE = ("#7b5ea7", "#199e70", "#c98500", "#d55181", "#4d7c0f")
# 邊際變化的寫法：（一階叫什麼, 二階叫什麼, 一階單位, 二階單位）
DLABEL = {
    "B1": ("近 3 個月變化", "比前 3 個月的變化", "分", "分"),
    "B2": ("6 個月變化", "比 3 個月前", "點", "點"),
    "B3": ("PMI − 50", "PMI 比 3 個月前", "", ""),
    "B4": ("年增率", "比 3 個月前", "%", "個百分點"), "B5": ("年增率", "比 3 個月前", "%", "個百分點"),
    "B6": ("年增率", "比 3 個月前", "%", "個百分點"), "B7": ("年增率", "比 3 個月前", "%", "個百分點"),
    "B8": ("年增率", "比 3 個月前", "%", "個百分點"), "L2": ("年增率", "比 3 個月前", "%", "個百分點"),
    "C1": ("20 日增減（5 日平均）", "比前 20 日的增減", "%", "個百分點"),
    "C5": ("20 日變化（5 日平均）", "比前 20 日的變化", "口", "口"),
    "G1": ("6 個月變化", "比 63 個交易日前", "個百分點", "個百分點"),
    "G2": ("60 日變化", "比 20 個交易日前", "個百分點", "個百分點"),
}
DVDEC = {"B1": 0, "B2": 2, "B3": 1, "C5": 0, "G1": 2, "G2": 2}
WD = "一二三四五六日"
# 第六版（第 15.7、15.11 節）：對照圖的三條組線、判定的寫法
ACC_IDS = {g: f"A_{g}" for g in S.M6_GROUPS}
ACC_NAME = {g: f"{nm}加速度" for g, nm in S.M6_GROUP_NAME.items()}
V6 = {"pred": "有預測性", "in_only": "樣本內看得到、樣本外沒有", "in_untested": "樣本內看得到（這個期間沒有做樣本外）",
      "none": "看不出", "few": "樣本不足"}
V6MARK = {"pred": "★", "in_only": "●", "in_untested": "○"}
GORDER = ["GA_grow", "GA_rate", "GA_lev", "DI", "SH_grow", "SH_rate", "SH_lev"]
OOS_TXT = {"pred": "成立", "fail": "不成立", "untested": "沒有做", "few": "樣本不足", "none": "—"}
# 市場的說法（台股頁＝預設；美股頁在 heatpage_us 用 use_market 換上，連同 SRC、DEC、SIGNED、WHY、DLABEL、DVDEC 與說明文字）
MK = {"tab": "tw", "mkt": "台股", "px": "加權指數", "cmp": "對照台股", "title": "景氣溫度", "data": "x9mh.json",
      "res": "data/lab/heat_research.json", "bull": "台股在 10 個月均線之上", "hike": "聯準會 6 個月內升息",
      "purp": ("六個面向分開看，各一個 0～100（100 最熱）：基本面、籌碼、全球資金、台灣資金、技術、泡沫。"
               "每一項都和自己的過去比，面向分數＝該面向全部項目的平均。最上面的色帶看每個面向這一年怎麼變過來；"
               "「對照台股」可以點選任何一項和加權指數放在一起看，也可以同時選幾條，看它們一起出現時台股之後的表現。"
               "頁面只描述位置與過去的統計，怎麼操作由你判斷。"),
      "closed": None, "pre": "", "switch": ""}


def use_market(values: dict):
    """暫時換上另一個市場的說法與項目表（同 heatspec.use）；離開時換回台股頁。"""
    from contextlib import contextmanager

    @contextmanager
    def _cm():
        g = globals()
        old = {k: g[k] for k in values if k in g}
        g.update(values)
        try:
            yield
        finally:
            g.update(old)
    return _cm()


def load_research(path: Path = RES) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _md(d: str | None) -> str:
    if not d:
        return "—"
    if len(d) == 7:
        return f"{int(d[:4])}/{int(d[5:])} 月"
    x = date.fromisoformat(d)
    return f"{x.month}/{x.day}（{WD[x.weekday()]}）"


def _ymd(d: str | None) -> str:
    if not d:
        return "—"
    return f"{int(d[:4])}/{int(d[5:7])}" + (f"/{int(d[8:10])}" if len(d) >= 10 else "")


def _fmt(k: str, v) -> str:
    if v is None:
        return "—"
    dec = DEC.get(k, 2)
    s = f"{abs(v):,.{dec}f}"
    sign = "−" if v < 0 else ("+" if k in SIGNED and v > 0 else "")
    unit = S.IND[S.KEYS.index(k)][3]
    if unit == "%":
        return f"{sign}{s}%"
    return f"{sign}{s}" + (f" {unit}" if unit else "")


def _src_date(B: dict, k: str, t: int) -> str | None:
    """這一項今天用到的資料日（月資料是月份；週資料存的是拿得到的那天，換回資料日）。"""
    if S.FREQ_OF[k] == "m":
        return B["ym"][k][t]
    ks = sorted(B["nat"].get(k) or {})
    day = B["cal"][t]
    j = (bisect.bisect_left(ks, day) if k in S.US else bisect.bisect_right(ks, day)) - 1
    if j < 0:
        return None
    sh = S.AVAIL_DAYS.get(k)
    if sh:
        from datetime import timedelta
        return (date.fromisoformat(ks[j]) - timedelta(days=sh)).isoformat()
    return ks[j]


def _m6a(V: dict) -> str | None:
    return ((V.get("m6") or {}).get("sample") or {}).get("a")


def _ym_txt(ym: str | None) -> str:
    return f"{int(ym[:4])} 年 {int(ym[5:7])} 月" if ym else "—"


def _ev(d: dict | None, h: int) -> dict:
    d = d or {}
    return d.get(str(h)) or d.get(h) or {}


# 泡沫面向另外放到泡沫頁（docs/lab_risk_plan.md 第 7 節；使用者 2026-10-18 選「拿掉，只留一行等級」）。
# 規格（heatspec VER 7）與研究檔照舊算，只是景氣頁不顯示：雷達、階段、地形、色帶、對照圖、證據地圖都只用 shown_dims()。
HIDE_DIMS = ("bubl",)


def shown_dims() -> dict:
    return {d: L for d, L in S.DIMS.items() if d not in HIDE_DIMS}


def bubble_now(B: dict) -> dict | None:
    """泡沫頁的現在等級（bubble.now_for；同一個程序裡泡沫頁直接沿用）；算不出來就不顯示那一行。"""
    try:
        from . import bubble as BU
        mk = "tw" if MK["tab"] == "tw" else B.get("idx")
        return BU.now_for(mk, B["D"]) if mk and B.get("D") else None
    except Exception as e:                          # noqa: BLE001  泡沫頁的問題不擋景氣頁
        print(f"[景氣溫度] 泡沫等級算不出來：{type(e).__name__}: {e}")
        return None


def crash_now(B: dict) -> dict | None:
    """「短線大跌風險」卡的資料（crashpage.state；研究檔 data/lab/crash_research.json）；算不出來就不顯示那張卡。"""
    try:
        from . import crashpage as CP
        return CP.state(B)
    except Exception as e:                          # noqa: BLE001  大跌風險的問題不擋景氣頁
        print(f"[景氣溫度] 大跌風險算不出來：{type(e).__name__}: {e}")
        return None


def hotdd_now(B: dict) -> dict | None:
    """「過熱之後 3 個月的最大回撤」卡的資料（hotddpage.state；研究檔 data/lab/hotdd_research.json）；算不出來就不顯示那張卡。"""
    try:
        from . import hotddpage as XP
        return XP.state(B)
    except Exception as e:                          # noqa: BLE001  過熱後回撤的問題不擋景氣頁
        print(f"[景氣溫度] 過熱後回撤算不出來：{type(e).__name__}: {e}")
        return None


def hotch_now(B: dict) -> dict | None:
    """「反向檢查：籌碼連續過熱、技術面轉空」卡的資料（hotchpage.state；研究檔 data/lab/hotch_research.json）；算不出來就不顯示那張卡。"""
    try:
        from . import hotchpage as QP
        return QP.state(B)
    except Exception as e:                          # noqa: BLE001  反向檢查的問題不擋景氣頁
        print(f"[景氣溫度] 反向檢查算不出來：{type(e).__name__}: {e}")
        return None


def bottom_now(B: dict) -> dict | None:
    """「大跌後檢查」卡的資料（bottompage.state；研究檔 data/lab/bottom_research.json）；算不出來就不顯示那張卡。"""
    try:
        from . import bottompage as BP
        return BP.state(B)
    except Exception as e:                          # noqa: BLE001  大跌後檢查的問題不擋景氣頁
        print(f"[景氣溫度] 大跌後檢查算不出來：{type(e).__name__}: {e}")
        return None


def sig_now(B: dict) -> dict | None:
    """訊號總覽：這個市場現在有效的訊號（sigcat.now_for_B，存進程序裡給訊號總覽沿用）；算不出來回 None。"""
    try:
        from . import sigcat
        return sigcat.now_for_B(B)
    except Exception as e:                          # noqa: BLE001  訊號總覽的問題不擋景氣頁
        print(f"[景氣溫度] 訊號總覽的狀態算不出來：{type(e).__name__}: {e}")
        return None


def sig_today(now: dict | None) -> dict | None:
    """「今天的重點」：這個市場現在有效的好訊號（sigcat.today_for）；研究檔沒有或算不出來回 None。"""
    try:
        from . import sigcat
        return sigcat.today_for(now)
    except Exception as e:                          # noqa: BLE001
        print(f"[景氣溫度] 今天的重點算不出來：{type(e).__name__}: {e}")
        return None


def xs_board(mk: str | None) -> list:
    """今天的重點：現在有動作的 ★ 總經策略（xstratpage.board）；算不出來回空的、不擋景氣頁。"""
    try:
        from . import xstratpage as XSP
        return XSP.board(mk) if mk else []
    except Exception as e:                          # noqa: BLE001
        print(f"[景氣溫度] 總經策略算不出來：{type(e).__name__}: {e}")
        return []


def xs_chip(mk: str | None) -> str:
    """最上面那一行的「10 個月均線」（xstratpage.chip）。"""
    try:
        from . import xstratpage as XSP
        return XSP.chip(mk) if mk else ""
    except Exception as e:                          # noqa: BLE001
        print(f"[景氣溫度] 10 個月均線算不出來：{type(e).__name__}: {e}")
        return ""


def mr_chip(mk: str | None) -> str:
    """最上面那一行的「融資維持率」（只有台股；xstratpage.mr_chip）。"""
    try:
        from . import xstratpage as XSP
        return XSP.mr_chip(mk) if mk else ""
    except Exception as e:                          # noqa: BLE001
        print(f"[景氣溫度] 融資維持率算不出來：{type(e).__name__}: {e}")
        return ""


def xs_line(mk: str | None) -> str:
    """今天的重點下面一行：這個市場的總經策略幾條、現在有部位幾條，連到策略頁（xstratpage.summary_line）。"""
    try:
        from . import xstratpage as XSP
        return XSP.summary_line(mk) if mk else ""
    except Exception as e:                          # noqa: BLE001
        print(f"[景氣溫度] 總經策略那一行算不出來：{type(e).__name__}: {e}")
        return ""


def view(B: dict | None = None, R: dict | None = None) -> dict:
    B = B if B is not None else C.build()
    R = R if R is not None else (load_research() or {})
    if R.get("ver") != S.VER:                      # 舊版研究檔（第二版三條線）不用
        R = {}
    cal, px = B["cal"], B["px"]
    T = len(cal)
    t = T - 1
    t0 = max(0, t - WEEK)
    dvn = {k: HP.deriv_now(B, k) for k in S.DERIV} if T else {}
    dims = {}
    for dim, L in shown_dims().items():
        rd = (R.get("dims") or {}).get(dim) or {}
        keys = S.ITEMS[dim]
        hn = {k: B["hc"][k][t] for k in keys}
        ha = {k: B["hc"][k][t0] for k in keys}
        cn, ca = H.contrib(hn, keys), H.contrib(ha, keys)
        items = []
        for k in keys:
            ind = S.IND[S.KEYS.index(k)]
            prox = k in B["proxy"] and bool(B["proxy"][k][t])
            heat = B["heat"][k][t]
            why = None
            if heat is None:
                why = WHY.get(k) or ("沒有最新資料" if B["raw"][k][t] is None else "歷史還不夠")
            items.append({
                "k": k, "name": ind[2], "how": ind[6], "hot": ind[4], "freq": ind[5],
                "val": _fmt(k, B["raw"][k][t]), "src": _src_date(B, k, t), "heat": heat, "ago": B["heat"][k][t0],
                "proxy": prox, "why": why,
                "pull": (cn.get(k) or {}).get("pull"), "share": (cn.get(k) or {}).get("share"),
                "dpull": cn[k]["pull"] - ca[k]["pull"] if k in cn and k in ca else None,
                "first": (rd.get("first") or {}).get(k), "ev": (rd.get("items") or {}).get(k) or {},
                "pos": HP.position(B, k, t) if T else None,
                "dv": dvn.get(k),
            })
        comp = B["comp"][dim]
        sc = comp[t] if T else None
        dims[dim] = {"name": L["name"], "hot": L["hot"], "span": L["span"], "fwd": L["fwd"], "freq": L["freq"],
                     "score": sc, "ago": comp[t0] if T else None, "band": S.band(sc), "items": items, "n_have": len(cn),
                     "cev": rd.get("comp") or {}, "first": next((cal[i] for i, v in enumerate(comp) if v is not None), None)}
    ta = None
    if T > S.EV_START:
        ev = TT.all_events(px)
        lo = max(0, t - TA_RECENT + 1)
        recent = sorted(((i, k) for k, ix in ev.items() for i in ix if i >= lo), reverse=True)
        ta = {"lv": TT.levels(px, cal), "recent": [(cal[i], k) for i, k in recent],
              "last": {k: (cal[ix[-1]] if ix else None) for k, ix in ev.items()}, "study": R.get("events") or {},
              "next": next_days(cal[t], S.DEDUCT_N), "base_a": cal[S.EV_START]}
    we = HP.week_ends(cal) if T else []
    strips = {d: HP.strip(B, d, we=we) for d in shown_dims()} if T else {}
    out = {"asof": cal[t] if cal else None, "mk": "tw" if MK["tab"] == "tw" else B.get("idx"), "dims": dims, "R": R,
            "data": R.get("data") or {}, "cal_info": B.get("cal_info"), "vixcorr": B.get("vixcorr") or {}, "ta": ta,
            "strips": strips, "summary": HP.summary(strips) if strips else "", "dvn": dvn,
            "dvr": R.get("deriv") or {}, "rel": R.get("rel") or {}, "m6": R.get("m6") or {}, "meta": meta(),
            "bubnow": bubble_now(B) if T else None, "crash": crash_now(B) if T else None,
            "hotdd": hotdd_now(B) if T else None, "hotch": hotch_now(B) if T else None,
            "bottom": bottom_now(B) if T else None, "signow": sig_now(B) if T else None}
    out["sigtoday"] = sig_today(out["signow"])
    out["xsb"] = xs_board(out["mk"]) if T else []   # 總經策略（xstratspec）：今天的重點要列的 ★ 策略
    out["xschip"] = xs_chip(out["mk"]) if T else ""
    out["mrchip"] = mr_chip(out["mk"]) if T else ""
    out["xsl"] = xs_line(out["mk"]) if T else ""     # 今天的重點下面一行（連到策略頁）
    if T:                                          # 視覺化版面（heatviz）：雷達、關鍵狀態、這週變化的資料
        from . import heatviz as VZ
        out["viz"] = VZ.pack(B, out)
        out["sigitems"] = VZ.sig_items(B, out)     # 訊號總覽「依指標」的現在（docs/lab_sigview_plan.md）
        out["ks"] = VZ.key_states(B, out, we)
    return out


def meta() -> dict:
    """給前端的設定（名稱、單位、顏色、門檻），嵌在頁面裡；序列資料另外放 x9mh.json。"""
    return {
        "ver": S.VER, "mkt": MK["mkt"], "px": MK["px"], "data": MK["data"],
        "famn": {k: len(v) for k, v in _gr_fams().items()},
        "dims": [{"id": d, "name": L["name"], "short": S.DSHORT[d]} for d, L in shown_dims().items()],
        "items": {k: {"name": nm, "unit": u, "hot": hot, "dim": dim, "dec": DEC.get(k, 2), "signed": k in SIGNED}
                  for k, dim, nm, u, hot, *_ in S.IND},
        "order": {d: S.ITEMS[d] for d in shown_dims()},
        "pal": list(PALETTE), "max": S.CH_MAX, "ranges": list(S.CH_RANGES), "rdef": S.CH_DEFAULT_RANGE,
        "shade": list(S.CH_SHADE), "relh": list(S.REL_H), "llh": list(S.LL_H),
        "bands": [[lo, min(hi, 100), nm] for lo, hi, nm in S.BANDS], "evtfwd": list(S.EVT_FWD),
        "roll": [S.ROLL_WEEKS, S.ROLL_H], "grmain": S.GR_MAIN, "grlags": list(S.GR_LAGS), "bhq": S.BH_Q,
        "evt": {k: list(v) for k, v in S.EVT.items()},
        "acc": [{"id": ACC_IDS[g], "name": ACC_NAME[g], "n": len(S.M6_GROUPS[g])} for g in S.M6_GROUPS],
        "m6": {"delay": list(S.M6_DELAY), "win": S.M6_WIN, "cum": list(S.M6_CUM), "minn": S.M6_MIN_N},
    }


def _gr_fams() -> dict:
    from . import heatrel
    return heatrel.gr_families()


def next_days(d: str, n: int) -> list[str]:
    """d 之後 n 個交易日（跳過週末與證交所休市日；官方表沒涵蓋的年份只跳週末）。"""
    from datetime import timedelta
    from .. import twholidays
    closed = MK.get("closed") or twholidays.is_closed
    out, x = [], date.fromisoformat(d)
    while len(out) < n:
        x += timedelta(days=1)
        if x.weekday() < 5 and not closed(x):
            out.append(x.isoformat())
    return out


# ── HTML ─────────────────────────────────────────────────────────────

def _e(x) -> str:
    return html.escape(str(x), quote=True)


def _pct(x, dec=1, sign=True) -> str:
    if x is None:
        return "—"
    r = round(x, dec)                              # 先取位數再判正負，不寫「−0.0」
    return ("−" if r < 0 else ("+" if sign and r > 0 else "")) + f"{abs(r):.{dec}f}%"


def _sgn(x, dec=1) -> str:
    if x is None:
        return "—"
    r = round(x, dec)
    return ("+" if r > 0 else ("−" if r < 0 else "")) + f"{abs(r):.{dec}f}"


def n0(x: float) -> str:
    """分數取整數；四捨五入會跨到下一區時（例如 79.6 → 80，五區的界線是 20／40／60／80）改成無條件捨去到一位小數，
    免得畫面寫「80 偏熱」。頁面 JS 的 sc0() 同一套規則。"""
    s = f"{x:.0f}"
    if int(s) in (20, 40, 60, 80) and x < int(s):
        return f"{math.floor(x * 10) / 10:.1f}"
    return s


def _bar(h: float | None) -> str:
    if h is None:
        return '<span class="hb"><i class="na"></i></span><b class="hn mu">—</b>'
    cls = BAND_CLS.get(S.band(h), "b2")
    return f'<span class="hb"><i class="{cls}" style="width:{h:.0f}%"></i></span><b class="hn">{n0(h)}</b>'


def _meter(score: float | None) -> str:
    seg = "".join(f'<i class="{BAND_CLS[nm]}"></i>' for _, _, nm in S.BANDS)
    mk = "" if score is None else f'<b class="mk" style="left:{score:.1f}%"></b>'
    lab = "".join(f"<span>{_e(nm)}</span>" for _, _, nm in S.BANDS)
    return f'<div class="mt">{seg}{mk}</div><div class="mtl">{lab}</div>'


def _band_of(ev: dict, nm: str | None) -> dict | None:
    for b in ev.get("bands") or []:
        if b.get("band") == nm:
            return b
    return None


def _unit(freq: str) -> str:
    return "個月" if freq == "m" else "天"


def _yrs(ys: list | None) -> str:
    """["2004","2010","2021","2022"] → 「2004、2010、2021–2022」：讓人看出樣本是不是集中在一兩段。"""
    v = sorted({int(y) for y in ys or []})
    out, i = [], 0
    while i < len(v):
        j = i
        while j + 1 < len(v) and v[j + 1] == v[j] + 1:
            j += 1
        out.append(str(v[i]) if i == j else f"{v[i]}–{v[j]}")
        i = j + 1
    return "、".join(out)


def _past(L: dict) -> str:
    """過去面向分數落在現在這一區時，之後加權指數的表現（全期間，兩個持有期間各自的樣本數）。"""
    band = L["band"]
    if band is None:
        return ""
    parts, allp, yrs, start = [], [], set(), None
    for h in L["fwd"]:
        e = _ev(L["cev"], h)
        b, al = _band_of(e, band), _band_of(e, "全部")
        if not b or not b.get("n") or not al or not al.get("n"):
            continue
        start = start or (e.get("a") or "")[:4]
        yrs |= set(b.get("yrs") or [])
        parts.append(f"之後 {h} 日（{b['n']:,} {_unit(L['freq'])}）{MK['px']}平均 {_pct(b['avg'])}、上漲機率 {b['up']:.0f}%、"
                     f"期間最大跌幅中位數 {_pct(b['dd'])}")
        allp.append(f"{h} 日 {_pct(al['avg'])}")
    if not parts:
        return ""
    where = f"，出現在 {_e(_yrs(sorted(yrs)))} 年" if yrs else ""
    return (f"過去分數在「{_e(band)}」時（{_e(start)} 年起的資料{where}）："
            + "；".join(parts) + "。所有日子：" + "、".join(allp) + "。")


def _verdict_line(L: dict) -> str:
    vs = []
    for h in L["fwd"]:
        v = _ev(L["cev"], h).get("verdict")
        if v:
            vs.append(f"之後 {h} 日<b>{_e(S.VERDICT.get(v, '—'))}</b>")
    if not vs:
        return ""
    return f'<p class="vd">過去關係（只當參考，不拿來刪項目）：{"、".join(vs)}。</p>'


def _items(L: dict) -> str:
    out = ['<div class="ith"><span>項目</span><span>0～100</span><span>拉動分數</span><span>佔比</span><span>本週</span></div>']
    have = sorted((it for it in L["items"] if it["pull"] is not None), key=lambda x: -abs(x["pull"]))
    rest = [it for it in L["items"] if it["pull"] is None]
    for it in have + rest:
        pull = "—" if it["pull"] is None else f'{_sgn(it["pull"])} 分'
        sh = "—" if it["share"] is None else f'{it["share"]:.0f}%'
        dp = _sgn(it["dpull"])
        tag = ""
        if it["proxy"]:
            tag = '<em class="px">用美國 VIX 的排名代替，不算進分數</em>'
        elif it["why"]:
            tag = f'<em class="px">{_e(it["why"])}</em>'
        cls = "it" if it["pull"] is not None else "it it0"
        pl = pos_line(it["k"], it.get("pos"))
        al = acc_label(it["k"], it.get("dv"))
        extra = (f'<i class="ipos">{_e(pl)}</i>' if pl else "") + \
            (f'<i class="idv" title="{_e(dv_line(it["k"], it.get("dv")))}">邊際變化 {_e(al)}</i>' if al else "")
        out.append(f'<div class="{cls}"><span class="inm"><button type="button" class="nmb" data-k="{_e(it["k"])}" '
                   f'title="在上面的對照圖只看這一項">{_e(it["name"])}</button><i>{_e(it["val"])}・{_e(_md(it["src"]))}</i>'
                   f'{extra}{tag}</span>'
                   f'<span class="ihb">{_bar(it["heat"])}</span><span class="ipl">{pull}</span>'
                   f'<span class="ish">{sh}</span><span class="iwk">{dp}</span></div>')
    return "".join(out)


def _when(d: str | None) -> str:
    """YYYY-MM → 「YYYY 年 M 月」；YYYY-MM-DD → 「YYYY/M/D」。"""
    if not d:
        return "—"
    if len(d) == 7:
        return f"{int(d[:4])} 年 {int(d[5:7])} 月"
    return _ymd(d)


def _since(d: str) -> str:
    return f"{int(d[:4])} 年 {int(d[5:7])} 月"


def pct_phrase(pos: dict, freq: str) -> str:
    """百分位換成白話：「比近 3 年 99%、近 10 年 100%、1984 年以來 100% 的月份高」；高低方向不同時分開寫。
    數字取整數往下捨（99.8 寫 99），寫 100% 時就是比區間裡每一筆都高（低）。"""
    unit = "月份" if freq == "m" else "日子"
    groups: list[list] = []
    for lab, p in (("近 3 年", pos.get("p3")), ("近 10 年", pos.get("p10")),
                   (f'{int(pos["from"][:4])} 年以來' if pos.get("from") else None, pos.get("pall"))):
        if p is None or lab is None:
            continue
        hi = p >= 50
        v = math.floor(p if hi else 100 - p)
        if groups and groups[-1][0] == hi:
            groups[-1][1].append(f"{lab} {v}%")
        else:
            groups.append([hi, [f"{lab} {v}%"]])
    return "，".join(f'比{"、".join(xs)} 的{unit}{"高" if hi else "低"}' for hi, xs in groups)


def pos_line(k: str, pos: dict | None) -> str:
    """歷史位置一行（規劃文件第 14.14 節第 1 點）：比近 3 年、近 10 年、有資料以來多少比例的日子高（低）；
    創幾年新高（新低）；近 10 年的高（低）點在哪裡、離現在多遠。"""
    if not pos:
        return ""
    parts = []
    pc = pct_phrase(pos, S.FREQ_OF[k])
    if pc:
        parts.append(pc)
    rec = pos.get("rec") or {}
    word = "高" if rec.get("side") == "hi" else "低"
    if rec.get("kind") == "ath":
        parts.append(f'有資料以來最{word}（{"並列，" if rec.get("tie") else ""}資料從 {int(rec["d"][:4])} 年起）')
    elif rec.get("kind") == "since_y":
        parts.append(f'{_since(rec["d"])}以來最{word}，{rec["n"]} 年新{word}')
    elif rec.get("kind") == "since":
        parts.append(f'{_since(rec["d"])}以來最{word}')
    rg = pos.get("rng")
    if rg and rg["dist"] != 0 and pc:                    # 歷史太短（三個區間都沒有百分位）就不寫範圍
        side_hi = rg["side"] == "hi"
        ext, d = (rg["hi"], rg["hi_d"]) if side_hi else (rg["lo"], rg["lo_d"])
        lab = "有資料以來" if rg["a"] == pos["from"] else f"近 {S.RANGE_YEARS} 年"   # 序列從 10 年內才開始
        dist = rg["dist"]
        way = "低" if dist < 0 else "高"
        if rg["how"] == "pct":
            dtxt = f"現在{way} {abs(dist):.1f}%"
        elif rg["how"] == "pp":
            dtxt = f"現在{way} {abs(dist):.2f} 個百分點"
        else:
            dtxt = f'現在{way} {_fmt(k, abs(dist)).lstrip("+")}'
        parts.append(f'{lab}最{"高" if side_hi else "低"} {_fmt(k, ext)}（{_when(d)}），{dtxt}')
    return "；".join(parts)


def _dvnum(k: str, v: float, which: int) -> str:
    dec = DVDEC.get(k, 1)
    u = DLABEL[k][2 + which]
    r = round(v, dec)
    s = f"{abs(r):,.{dec}f}"
    if which == 0:
        sign = "−" if r < 0 else ("+" if r > 0 else "")
        return f"{sign}{s}{u if u in ('%',) else (' ' + u if u else '')}"
    return f"{s}{'' if not u else ' ' + u}"


def dv_line(k: str, dv: dict | None) -> str:
    """邊際變化一行，例如「年增率 +49.4%，比 3 個月前高 12.7 個百分點：成長加速（連 3 個月）」。"""
    if not dv or k not in DLABEL:
        return ""
    l1, l2, _, _ = DLABEL[k]
    d2 = dv["d2"]
    dec = DVDEC.get(k, 1)
    if round(d2, dec) == 0:
        mid = l2.replace("比", "和", 1) + "一樣"
    else:
        mid = f'{l2}{"高" if d2 > 0 else "低"} {_dvnum(k, d2, 1)}'
    unit = "個月" if S.FREQ_OF[k] == "m" else "天"
    tail = f'（連 {dv["streak"]} {unit}）' if dv.get("streak") else ""
    note = f'（{dv["note"]}）' if dv.get("note") else ""
    return f'{l1} {_dvnum(k, dv["d1"], 0)}，{mid}：{dv["word"]}{note}{tail}'



def acc_label(k: str, dv: dict | None) -> str:
    """二階的正負與連續幾期：「▲ 加速 3 個月」「▼ 減速 2 個月」「持平」（和研究的「原始二階 > 0」同一個判斷）。"""
    if not dv:
        return ""
    d2 = dv["d2"]
    if d2 == 0:
        return "持平"
    unit = "個月" if S.FREQ_OF[k] == "m" else "天"
    n = dv.get("streak") or 0
    return ("▲ 加速" if d2 > 0 else "▼ 減速") + (f" {n} {unit}" if n else "")


def acc_counts(dvn: dict) -> dict:
    """幾項在加速（原始二階 > 0）：{"all": (加速, 有值), 組: (...)}。"""
    out = {}
    for g, keys in list(S.M6_GROUPS.items()) + [("all", tuple(S.DERIV))]:
        have = [k for k in keys if dvn.get(k)]
        out[g] = (sum(1 for k in have if dvn[k]["d2"] > 0), len(have))
    return out


def _iname(k: str) -> str:
    return S.IND[S.KEYS.index(k)][2]


def m6_conclusion(m6: dict) -> str:
    """研究結論一句（照判定規則；先講結論，看不出就照寫）。"""
    P = m6.get("primary") or {}
    passed = [h for h in S.M6_PRIMARY if (P.get(h) or {}).get("pass")]
    hp = [P[h]["holm"] for h in S.M6_PRIMARY if (P.get(h) or {}).get("holm") is not None]
    by: dict[str, list] = {"pred": [], "fail": [], "untested": []}
    for k in S.DERIV:
        sm = (((m6.get("items") or {}).get(k) or {}).get("sum")) or {}
        if sm.get("oos") in by:
            by[sm["oos"]].append(f'{_iname(k)}（{RG.react_text(sm.get("react") or [])}）')
    parts = []
    if passed or by["pred"]:
        head = "有預測性：" + "；".join([P[h]["what"] for h in passed] + by["pred"])
        if by["fail"]:
            parts.append("樣本內看得到、樣本外沒有：" + "、".join(by["fail"]))
    else:
        head = f"二階（加速度）在 1～{max(S.M6_CUM)} 個月看不出穩定的預測性"
        parts.append(f"{len(S.M6_PRIMARY)} 個主要假說都沒有通過" + (f"（Holm 校正後 p 最小 {min(hp):.2f}）" if hp else ""))
        if by["fail"]:
            near = "、".join(by["fail"])
            parts.append("比較接近的是" + (" " if near[:1].isascii() else "") + near + "，但樣本外沒有成立")
    if by["untested"]:
        parts.append("只在樣本內看到、那段期間沒有做樣本外：" + "、".join(by["untested"]))
    return head + ("：" + "；".join(parts) if parts else "") + "。"


def _card(dim: str, L: dict, V: dict) -> str:
    sc = L["score"]
    head = (f'<b class="sc {BAND_CLS.get(L["band"], "b2")}">{n0(sc)}</b><span class="bn {BAND_CLS.get(L["band"], "b2")}">{_e(L["band"])}</span>'
            if sc is not None else '<b class="sc mu">—</b><span class="bn mu">還沒有分數</span>')
    wk = ""
    if sc is not None and L["ago"] is not None:
        wk = f'<span class="wk">和上週比 {_sgn(sc - L["ago"], 0)}</span>'
    eq = ""
    if sc is not None:
        s = sum(it["pull"] for it in L["items"] if it["pull"] is not None)
        extra = "；台指 VIX 用美國 VIX 代替的日子不算" if dim == "tech" and S.PROXY else ""
        eq = (f'<p class="eq">分數 {sc:.1f} ＝ 50 ＋ 各項拉動合計 {_sgn(s)}（{L["n_have"]} 項有值，等權平均；'
              f'每項拉動＝（0～100 − 50）÷ 有值的項數{extra}）</p>')
    else:
        need = H.need(len(L["items"]))
        eq = f'<p class="eq">有值的項目不到 {need} 項（{len(L["items"])} 項的 2/3），不給分數。</p>'
    vx = ""
    vc = V.get("vixcorr") or {}
    if dim == "tech" and S.PROXY and vc.get("n"):
        r = "—" if vc.get("r") is None else f'{vc["r"]:.2f}'
        vx = (f'<p class="note">台指 VIX 從 {_e(_ymd(vc.get("a")))} 起才有資料（{vc["n"]} 天），和美國 VIX 的相關係數 {r}；'
              f'自己的歷史滿 {S.PCT_MIN["d"]} 個交易日後改用自己的排名並算進分數。</p>')
    return (f'<section class="cd" id="c-{dim}"><div class="ch"><h2>{_e(L["name"])}<span class="sub">{_e(L["span"])}</span></h2>'
            f'<div class="sv">{head}{wk}</div></div><p class="hot">熱＝{_e(L["hot"])}</p>{_meter(sc)}'
            f'<p class="past">{_past(L) if sc is not None else ""}</p>{_verdict_line(L)}{eq}'
            f'<div class="its">{_items(L)}</div>{vx}</section>')


def strip_text(st: dict) -> str:
    """色帶右邊的說明：連續幾週、全期間位置、上次這麼熱（冷）。"""
    if st.get("score") is None:
        return "還沒有分數"
    parts = [f'已連續 {st["weeks"]} 週在{st["band"]}']
    pos = st.get("pos")
    y = int(st["first"][:4]) if st.get("first") else None
    if pos and pos[1] is not None:
        if pos[0] == "hot":
            parts.append(f"比 {y} 年以來 {pos[1]:.1f}% 的日子熱")
        elif pos[0] == "cold":
            parts.append(f"比 {y} 年以來 {pos[1]:.1f}% 的日子冷")
        else:
            parts.append(f"{y} 年以來第 {pos[1]:.0f} 百分位")
    last = st.get("last")
    if last:
        w = "熱" if last[0] == "hot" else "冷"
        parts.append(f"上次這麼{w}：{_since(last[1])}" if last[1] else f"有分數以來最{w}")
    return "；".join(parts)


def _strips(V: dict) -> str:
    rows = []
    for dim, L in V["dims"].items():
        st = (V.get("strips") or {}).get(dim) or {}
        cells = "".join(f'<i class="{BAND_CLS.get(b, "na") if b else "na"}" title="{_e(_ymd(d))}　{"—" if v is None else n0(v)}"></i>'
                        for d, v, b in st.get("cells") or [])
        sc = st.get("score")
        cls = BAND_CLS.get(st.get("band"), "b2")
        num = (f'<b class="sc {cls}">{n0(sc)}</b><em class="bn {cls}">{_e(st["band"])}</em>' if sc is not None else
               '<b class="sc mu">—</b><em class="bn mu">沒有分數</em>')
        rows.append(f'<a class="sr" href="#c-{dim}"><span class="sr-n"><b>{_e(S.DSHORT[dim])}</b><i>{_e(L["span"])}</i></span>'
                    f'<span class="sr-c" role="img" aria-label="{_e(S.DSHORT[dim])}近 {S.STRIP_WEEKS} 週的熱度">{cells}</span>'
                    f'<span class="sr-v">{num}</span><span class="sr-t">{_e(strip_text(st))}</span></a>')
    lg = "".join(f'<span><i class="{BAND_CLS[nm]}"></i>{_e(nm)}</span>' for _, _, nm in S.BANDS)
    return (f'<section class="hd" id="top"><p class="sum">{_e(V.get("summary") or "")}</p>'
            f'<div class="strips">{"".join(rows)}</div>'
            f'<div class="srl">{lg}<span class="mu">每格一週（每週最後一個交易日），最右邊是最新的一週，往左共 {S.STRIP_WEEKS} 週；'
            f'滑過格子看日期與分數，點一列跳到那個面向。</span></div></section>')


def _band_table(ev: dict, h: int, freq: str) -> str:
    bs = ev.get("bands") or []
    if not bs:
        return '<p class="note">沒有資料。</p>'

    def up(b):
        return "—" if b.get("up") is None else f'{b["up"]:.0f}%'
    rows = "".join(f'<tr><td>{_e(b["band"])}</td><td>{b["n"]:,}</td><td>{_pct(b["avg"], 2)}</td><td>{_pct(b["med"], 2)}</td>'
                   f'<td>{up(b)}</td><td>{_pct(b["dd"], 2)}</td><td class="l">{_e(_yrs(b.get("yrs")) or "—")}</td></tr>'
                   for b in bs)
    return (f'<div class="tw"><table><tr><th>分數區間</th><th>樣本（{_unit(freq)}）</th><th>之後 {h} 日平均</th><th>中位數</th>'
            f'<th>上漲機率</th><th>期間最大跌幅中位數</th><th class="l">出現在哪幾年</th></tr>{rows}</table></div>')


def _rho(e: dict) -> str:
    if e.get("rho") is None:
        return "—"
    ci = f'［{e["lo"]:+.2f}, {e["hi"]:+.2f}］' if e.get("lo") is not None else ""
    return f'{e["rho"]:+.2f}{ci}'


def _r(x) -> str:
    return "—" if x is None else f"{x:+.2f}"


def _refc(r: dict | None, freq: str) -> str:
    r = r or {}
    if not r.get("n"):
        return "—"
    return f'{_r(r.get("rho"))}<span class="hw">{r["n"]:,} {_unit(freq)}</span>'      # 樣本太少的對照數字要看得出來


def _vrow(name: str, first: str | None, e: dict, freq: str) -> str:
    h1, h2 = e.get("h1") or {}, e.get("h2") or {}
    ref = (e.get("ref") or []) + [{}, {}]
    return (f'<tr><td class="l">{_e(name)}</td><td>{_e(_ymd(first))}</td><td>{e.get("n", 0):,}</td><td>{_rho(e)}</td>'
            f'<td>{_r(h1.get("rho"))}</td><td>{_r(h2.get("rho"))}</td>'
            f'<td class="l">{_e(S.VERDICT.get(e.get("verdict"), "—"))}</td>'
            f'<td>{_refc(ref[0], freq)}</td><td>{_refc(ref[1], freq)}</td></tr>')


def _rng_txt(a: str | None, z: str | None) -> str:
    """對照切分的期間：兩頭都有＝YYYY–YYYY；只有起點＝YYYY 起；只有終點＝YYYY 以前。"""
    if a and z:
        return f"{a[:4]}–{z[:4]}"
    return f"{a[:4]} 起" if a else (f"{z[:4]} 以前" if z else "全部")


def _valid(dim: str, L: dict) -> str:
    ref = S.SPLIT_REF[L["freq"]]
    r0, r1 = (_rng_txt(a, z) for a, z in ref)
    out = [f'<div class="vsec" id="v-{dim}"><h3>{_e(L["name"])}<span class="sub">{"每月最後一個交易日一個樣本" if L["freq"] == "m" else "每天一個樣本"}</span></h3>']
    for h in L["fwd"]:
        ce = _ev(L["cev"], h)
        rows = ([_vrow("面向分數", L["first"], ce, L["freq"])]
                + [_vrow(it["name"], it["first"], _ev(it["ev"], h), L["freq"]) for it in L["items"]])
        out.append(f'<h4>之後 {h} 個交易日：面向分數各區</h4>{_band_table(ce, h, L["freq"])}'
                   f'<h4>之後 {h} 個交易日：各項</h4><div class="tw"><table><tr><th class="l">項目</th><th>有分數起</th><th>樣本</th>'
                   f'<th>等級相關［95% 信賴區間］</th><th>前一半</th><th>後一半</th><th class="l">判定</th>'
                   f'<th>對照 {_e(r0)}</th><th>對照 {_e(r1)}</th></tr>{"".join(rows)}</table></div>')
    out.append("</div>")
    return "".join(out)


def _num0(v) -> str:
    return "—" if v is None else f"{v:,.0f}"


DIRW = {1: "上揚", -1: "下彎", 0: "持平", None: "—"}
_ST = {   # 狀態：（+1 的說法, −1 的說法, 變成 +1 叫什麼, 變成 −1 叫什麼）
    "ma20": ("收在月線上", "收在月線下", "站回月線", "跌破月線"),
    "ma60": ("收在季線上", "收在季線下", "站回季線", "跌破季線"),
    "ma240": ("收在年線上", "收在年線下", "站回年線", "跌破年線"),
    "x": ("月線在季線上方", "月線在季線下方", "黃金交叉", "死亡交叉"),
    "s60": ("季線上揚", "季線下彎", "季線轉上揚", "季線轉下彎"),
}


def _st_text(key: str, st: dict) -> str:
    if not st or st.get("side") not in (1, -1):
        return "—"
    up, dn, to_up, to_dn = _ST[key]
    s = st["side"]
    txt = f'{up if s > 0 else dn}第 {st["n"]} 天'
    if st.get("pending"):
        k = S.EV_CONF - st["n"]
        txt += f'（前 {st["prev"]} 個交易日{dn if s > 0 else up}；再 {k} 天就算<b>{to_up if s > 0 else to_dn}</b>）'
    return txt


def _evc(r: dict | None, h: int) -> str:
    r = r or {}
    if not r.get("n"):
        return "<td>—</td><td>—</td><td class=\"l\">—</td>"
    avg = f'{_pct(100 * r["avg"], 2)}<span class="hw">上漲 {100 * r["up"]:.0f}%</span>'
    ci = ""
    if r.get("lo") is not None:
        ci = f'<span class="hw">［{_pct(100 * r["lo"], 2)}, {_pct(100 * r["hi"], 2)}］</span>'
    d = f'{_pct(100 * r["diff"], 2)}{ci}' if r.get("diff") is not None else "—"
    return f'<td>{avg}</td><td>{d}</td><td class="l">{_e(S.EV_VERDICT.get(r.get("verdict"), "—"))}</td>'


def _ta_parts(V: dict) -> tuple[str, str]:
    ta = V.get("ta")
    if not ta:
        return "", ""
    lv = ta["lv"]
    rows = []
    for n, key in ((20, "ma20"), (60, "ma60"), (120, None), (240, "ma240")):
        m = lv["ma"][n]
        rows.append(f'<tr><td class="l">{_e(S.MA_NAME[n])}（{n} 日）</td><td>{_num0(m["v"])}</td>'
                    f'<td>{_pct(m["dist"])}</td>'
                    f'<td>{DIRW.get(m["dir"], "—")}</td><td class="l">{_st_text(key, lv["st"].get(key)) if key else ""}</td></tr>')
    ded = "、".join(f'{_e(_md(d)[:-3])} {_num0(x["v"])}' for d, x in zip(ta["next"], lv["deduct"]))
    hi, lo = lv.get("hi"), lv.get("lo")
    piv = []
    if hi:
        piv.append(f'前波高點 {_num0(hi["p"])}（{_e(_ymd(hi["d"]))}）')
    if lo:
        piv.append(f'前波低點 {_num0(lo["p"])}（{_e(_ymd(lo["d"]))}）')
    sr = []
    for key, nm in (("sup", "下方最近的支撐"), ("res", "上方最近的壓力")):
        x = lv.get(key)
        if x:
            when = f'（{_e(_ymd(x["d"]))}）' if x.get("d") else ""
            sr.append(f'{nm}：{_e(x["what"])}{when} {_num0(x["v"])}（距離 {_pct(x["dist"])}）')
    lis = [f'<li>月線季線：{_st_text("x", lv["st"].get("x"))}。</li>',
           f'<li>季線方向：{_st_text("s60", lv["st"].get("s60"))}。之後 {S.DEDUCT_N} 個交易日的扣抵值：{ded}'
           f'（收盤高於扣抵值，季線就往上）。</li>']
    if piv:
        lis.append(f'<li>{"、".join(piv)}（收盤回落／反彈 5% 才確認是高點／低點）。</li>')
    if sr:
        lis.append(f'<li>{"；".join(sr)}。</li>')
    rec = "、".join(f'{_e(_md(d))} {_e(S.EVENTS[k])}' for d, k in ta["recent"]) or "沒有"
    st = ta.get("study") or {}
    allr = ""
    any_ev = next((st[k] for k in S.EVENTS if st.get(k)), None)
    if any_ev:
        a10, a60 = any_ev.get("10") or {}, any_ev.get("60") or {}
        if a10.get("all_avg") is not None and a60.get("all_avg") is not None:
            allr = (f'所有交易日（{_e(_ymd(ta.get("base_a")))} 起）：之後 10 日平均 {_pct(100 * a10["all_avg"], 2)}'
                    f'（上漲 {100 * a10["all_up"]:.0f}%）、60 日 {_pct(100 * a60["all_avg"], 2)}（上漲 {100 * a60["all_up"]:.0f}%）。')
    trs = []
    for k, nm in S.EVENTS.items():
        e = st.get(k) or {}
        e10, e60 = e.get("10") or {}, e.get("60") or {}
        n = e10.get("n") or e60.get("n") or 0
        last = ta["last"].get(k)
        trs.append(f'<tr><td class="l">{_e(nm)}</td><td>{n:,}</td><td>{_e(_ymd(last))}</td>{_evc(e10, 10)}{_evc(e60, 60)}</tr>')
    table = (f'<div class="tw"><table class="evt"><tr><th class="l">事件</th><th>次數</th><th>最近一次</th>'
             f'<th>之後 10 日平均</th><th>和所有日子差［95% 信賴區間］</th><th class="l">判定</th>'
             f'<th>之後 60 日平均</th><th>和所有日子差［95% 信賴區間］</th><th class="l">判定</th></tr>{"".join(trs)}</table></div>'
             if st else '<p class="warn">事件研究還沒產生（data/lab/heat_research.json）。</p>')
    main = (f'<section class="cd" id="ta"><div class="ch"><h2>關鍵價位與事件<span class="sub">{_e(MK["px"])} {_e(_md(lv["t"]))}收盤 '
            f'{_num0(lv["close"])}；不進分數，只描述位置</span></h2></div>'
            f'<p class="hot">均線是收盤的簡單平均。跌破、站回、交叉、季線轉向一律要「之前 {S.EV_PRIOR} 個交易日是原來的狀態、'
            f'連 {S.EV_CONF} 個交易日是新狀態」才算，第 {S.EV_CONF} 天是事件日。</p>'
            f'<div class="tw"><table class="lvt"><tr><th class="l">均線</th>'
            f'<th>數值</th><th>距離</th><th>方向</th><th class="l">現在的狀態</th></tr>{"".join(rows)}</table></div>'
            f'<ul class="tal">{"".join(lis)}</ul>'
            f'<h3>近 {TA_RECENT} 個交易日的事件</h3><p class="rec">{rec}</p>'
            '<p class="note">16 種事件之後的表現（次數、平均、判定）在研究畫面。'
            '<button type="button" class="tb" data-goview="research" data-anchor="tas">看事件研究 →</button></p></section>')
    study = (f'<section class="sec" id="tas"><h2>事件之後{_e(MK["px"])}的表現<span class="sub">只當參考，不當買賣訊號</span></h2>'
             f'<p class="note">{allr}型態（M 頭、W 底、頭肩）用收盤轉折點認，收盤跌破／突破頸線那天才算成立。'
             f'16 種事件 × 2 個期間＝32 個比較，就算全是運氣也會有一兩個看起來「顯著」；判定要信賴區間不含 0、'
             f'前後兩半方向一樣才寫，事件少於 {S.EV_MIN} 次寫「樣本不足」。</p>{table}</section>')
    return main, study


def _ta_main(V: dict) -> str:
    """主畫面：均線、扣抵、前波高低點、支撐壓力、近期事件。"""
    return _ta_parts(V)[0]


def _ta_study(V: dict) -> str:
    """研究畫面：16 種事件之後的表現。"""
    return _ta_parts(V)[1]


CPLV = {"strong": "之後較強", "weak": "之後較弱", "none": "看不出差別", "few": "樣本不足"}
PCV = {"strong": "加速之後較強，比水準多出預測資訊", "weak": "加速之後較弱，比水準多出預測資訊",
       "none": "沒有比水準多出預測資訊", "few": "樣本不足"}
GRV = {"strong": "有額外的預測力（熱了之後下個月較強）", "weak": "有額外的預測力（熱了之後下個月較弱）",
       "none": "看不出額外的預測力", "few": "樣本不足"}
def _grb() -> dict:
    m = MK["mkt"]
    return {"strong": f"{m}過去的漲跌可以預測（{m}漲了之後這一項變熱）", "weak": f"{m}過去的漲跌可以預測（{m}漲了之後這一項變冷）",
            "none": "看不出", "few": "樣本不足"}


def _cmp_section() -> str:
    return (f'<section class="sec" id="cmp"><h2>{_e(MK["cmp"])}<span class="sub">點按鈕加入或拿掉線（最多 {S.CH_MAX} 條）；滑過圖看當天的值</span></h2>'
            '<div class="cbar"><div class="chips" id="cmp-dims"></div>'
            '<button type="button" class="tb" id="cmp-more" aria-expanded="false">＋ 細項</button>'
            '<div class="seg" id="cmp-rng"></div><div class="seg" id="cmp-mode" hidden></div></div>'
            '<p class="warn" id="cmp-msg" hidden></p><div class="pick" id="cmp-pick" hidden></div>'
            '<div class="cw" id="cmp-chart"><p class="note">走勢載入中…</p></div><p class="note" id="cmp-cap"></p>'
            '<div id="cmp-an"></div><noscript><p class="warn">這一段要開啟 JavaScript 才看得到。</p></noscript></section>')


def _pctv(x, dec=1):
    """小數（0.012）→ 「+1.2%」。"""
    return _pct(None if x is None else 100 * x, dec)


def dv_past(rr: dict, state, hs) -> str:
    """過去這個狀態之後（研究檔）：各期間的平均與所有週，週數與段數，判定只列成立的。"""
    if state is None:
        return "—"
    parts, sig, vs, nr = [], [], [], None
    for h in hs:
        e = ((rr.get("h") or {}).get(str(h)) or {}).get("states") or {}
        stt = e.get(str(state))
        if not stt or not stt.get("n"):
            continue
        parts.append(f'{h} 日 {_pctv(stt["avg"])}（所有週 {_pctv(stt["all_avg"])}）')
        nr = nr or (stt["n"], stt["runs"])
        vs.append(stt["verdict"])
        if stt["verdict"] in ("strong", "weak"):
            sig.append(f'{h} 日{CPLV[stt["verdict"]]}')
    if not parts:
        return "—"
    vtxt = "、".join(sig) if sig else ("樣本不足" if all(v == "few" for v in vs) else "看不出差別")
    return f'{"；".join(parts)}。{nr[0]:,} 週、{nr[1]} 段；{vtxt}'


def dv_more(rr: dict, hs) -> str:
    """扣掉水準之後，加速減速有沒有多出預測資訊（偏等級相關、BH 校正）。"""
    got, sig = [], []
    for h in hs:
        pc = ((rr.get("h") or {}).get(str(h)) or {}).get("pc") or {}
        if pc.get("r") is None:
            continue
        got.append((h, pc))
        if pc.get("verdict") in ("strong", "weak"):
            sig.append(f'{h} 日：{PCV[pc["verdict"]]}（偏相關 {_sgn(pc["r"], 2)}，校正後 q＝{pc["q"]:.2f}）')
    if sig:
        return "；".join(sig)
    if not got:
        return "—"
    days = "／".join(str(h) for h, _ in got)
    rs = "／".join(_sgn(pc["r"], 2) for _, pc in got)
    qs = "／".join(f'{pc["q"]:.2f}' for _, pc in got if pc.get("q") is not None)
    return f"沒有（{days} 日：偏相關 {rs}" + (f"，校正後 q {qs}" if qs else "") + "）"


def _dv_section(V: dict) -> str:
    """邊際變化區（第 15.7 節）：一句話、研究結論一句、4 欄精簡表；詳細數字在驗證段（預設收起）。"""
    dvn = V.get("dvn") or {}
    m6 = V.get("m6") or {}
    cnt = acc_counts(dvn)
    a, b = cnt["all"]
    grp = "、".join(f'<button type="button" class="nmb" data-k="{ACC_IDS[g]}" title="在上面的對照圖看這一組幾成在加速">'
                    f'{_e(S.M6_GROUP_NAME[g])}</button> {cnt[g][0]}/{cnt[g][1]}' for g in S.M6_GROUPS)
    have = "" if b == len(S.DERIV) else f"（有最新值的 {b} 項）"
    head = f'<p class="sum">{len(S.DERIV)} 項裡 {a} 項在加速{have}：{grp}</p>'
    concl = (f'<p class="vd"><b>研究：</b>{_e(m6_conclusion(m6))}</p>' if m6.get("items") else
             '<p class="warn">多層回歸的結果還沒產生（研究檔不是第六版）。</p>')
    rows = []
    for k in S.DERIV:
        dv = dvn.get(k)
        sm = (((m6.get("items") or {}).get(k) or {}).get("sum")) or {}
        rt = RG.react_text(sm.get("react") or []) or ("樣本不足" if sm.get("oos") == "few" else ("看不出" if sm else "—"))
        tip = dv_line(k, dv)
        rows.append(f'<tr><td class="l"><button type="button" class="nmb" data-k="{_e(k)}">{_e(_iname(k))}</button>'
                    f'<span class="hw">{_e(_when((dv or {}).get("asof")))}</span></td>'
                    f'<td class="l" data-h="現在"><span class="acl" title="{_e(tip)}">{_e(acc_label(k, dv) or "—")}</span></td>'
                    f'<td class="l" data-h="幾個月後有反應">{_e(rt)}</td>'
                    f'<td class="l" data-h="樣本外">{_e(OOS_TXT.get(sm.get("oos"), "—"))}</td></tr>')
    for g in S.M6_GROUPS:
        e = ((m6.get("groups") or {}).get(f"SH_{g}")) or {}
        sm = e.get("sum") or {}
        rt = RG.react_text(sm.get("react") or []) or ("樣本不足" if sm.get("oos") == "few" else ("看不出" if sm else "—"))
        rows.append(f'<tr class="grow"><td class="l"><button type="button" class="nmb" data-k="{ACC_IDS[g]}">{_e(ACC_NAME[g])}</button>'
                    f'<span class="hw">{len(S.M6_GROUPS[g])} 項幾成在加速</span></td>'
                    f'<td class="l" data-h="現在">{cnt[g][0]}/{cnt[g][1]} 在加速</td>'
                    f'<td class="l" data-h="幾個月後有反應">{_e(rt)}</td>'
                    f'<td class="l" data-h="樣本外">{_e(OOS_TXT.get(sm.get("oos"), "—")) if sm.get("oos") != "untested" else "沒有樣本外模型"}</td></tr>')
    return (f'<section class="sec" id="dv"><h2>邊際變化（二次微分）<span class="sub">核心 {len(S.DERIV)} 項；不進分數</span></h2>'
            f'{head}{concl}<div class="tw"><table class="dvs stk"><tr><th class="l">項目</th><th class="l">現在</th>'
            f'<th class="l">幾個月後有反應（加速時）</th><th class="l">樣本外</th></tr>{"".join(rows)}</table></div>'
            '<p class="note">「▲ 加速」＝一階（例如年增率）比之前高，「▼ 減速」＝比之前低；後面是連續幾個月（日資料是幾天），滑過看數字。'
            f'「幾個月後有反應」只寫多重比較校正後成立、前後兩半與相鄰期間方向都一樣的期間（每個月一個樣本，{_e(_ym_txt(_m6a(V)))}起，'
            f'控制{MK["mkt"]}過去 1、12 個月的漲跌）；「較弱」＝加速得越快，那段期間{MK["mkt"]}報酬越低。'
            f'樣本外＝{int(S.M6_OOS_START[:4])} 年起每個月只用當時拿得到的資料重新估計、'
            '往後預測，和不看二階的模型比。點名稱，上面的對照圖只看那一條，下面會出現延遲反應圖。詳細數字在「驗證」最下面。</p></section>')


def _pp(x, dec: int = 2) -> str:
    """係數（對數報酬）→ 百分點，帶正負號。"""
    return "—" if x is None else _sgn(100 * x, dec)


def _rtip(e: dict) -> str:
    """回歸一格的滑過說明：係數、信賴區間、t、q、前後兩半、月數、判定。"""
    if not e or e.get("b") is None:
        return f'{e.get("n", 0) if e else 0} 個月，不到 {S.M6_MIN_N} 個月'
    q = e.get("q")
    t = e.get("t")
    return (f'{_pp(e["b"])} 個百分點［{_pp(e.get("lo"))}, {_pp(e.get("hi"))}］，Newey–West t {"—" if t is None else f"{t:+.2f}"}，'
            f'q {"—" if q is None else f"{q:.3f}"}，前後兩半 {_pp(e.get("h1"))}／{_pp(e.get("h2"))}，{e["n"]} 個月（{e.get("a")}～{e.get("z")}）；'
            f'{V6.get(e.get("v"), "—")}')


def _rcell(e: dict | None) -> str:
    if not e or e.get("b") is None:
        return '<td class="mu">—</td>'
    mk = V6MARK.get(e.get("v"), "")
    return f'<td title="{_e(_rtip(e))}">{_e(_pp(e["b"]))}{f"<b>{mk}</b>" if mk else ""}</td>'


def _part(title: str, tally: str, body: str) -> str:
    """驗證段裡的一層：預設收起，標題列直接寫數一數的結果。"""
    return (f'<details class="m6s"><summary>{_e(title)}<span class="sub">{_e(tally)}</span></summary>{body}</details>')


def _tally(results: list) -> str:
    """★●○ 各幾個（★＝有預測性、●＝樣本內看得到樣本外沒有、○＝樣本內看得到沒有做樣本外）。"""
    vs = [(r or {}).get("v") for r in results]
    n = sum(1 for v in vs if v not in (None, "few"))
    marks = [f"{V6MARK[k]} {vs.count(k)}" for k in ("pred", "in_only", "in_untested") if vs.count(k)]
    return f'{n} 個有結果' + ("：" + "、".join(marks) if marks else "：都看不出")


def _rmat(title: str, rows: list, cols: list, note: str = "", tally: str | None = None) -> str:
    """rows＝[(名稱, {視窗: 結果})]；cols＝[(視窗, 欄名)]；tally＝標題列的數一數（沒給就數 ★●○）。"""
    head = "".join(f"<th>{_e(h)}</th>" for _, h in cols)
    body = "".join(f'<tr><td class="l">{_e(nm)}</td>' + "".join(_rcell((d or {}).get(w)) for w, _ in cols) + "</tr>"
                   for nm, d in rows)
    tally = tally if tally is not None else _tally([(d or {}).get(w) for _, d in rows for w, _ in cols])
    return _part(title, tally, f'<div class="tw"><table class="m6t"><tr><th class="l">項目</th>{head}</tr>{body}</table></div>'
                 + (f'<p class="note">{_e(note)}</p>' if note else ""))


DCOLS = [(f"{k},{S.M6_WIN}", f"{k}～{k + S.M6_WIN} 月後") for k in S.M6_DELAY]
CCOLS = [(f"0,{m}", f"累積 {m} 月") for m in S.M6_CUM]
OCOLS = [(f"{k},{m}", (f"{k}～{k + m} 月後" if k else f"累積 {m} 月")) for k, m in S.M6_OOS_WINDOWS]
GNAME = {**{f"GA_{g}": f"{nm}（組加速度）" for g, nm in S.M6_GROUP_NAME.items()},
         **{f"SH_{g}": f"{nm}（幾成在加速）" for g, nm in S.M6_GROUP_NAME.items()}, "DI": "加速擴散（13 項）"}
STNAME = {"hi_acc": "水準高、加速", "hi_dec": "水準高、減速", "lo_acc": "水準低、加速", "lo_dec": "水準低、減速",
          "gA_rA": "景氣加速、通膨利率加速", "gA_rD": "景氣加速、通膨利率減速", "gD_rA": "景氣減速、通膨利率加速",
          "gD_rD": "景氣減速、通膨利率減速"}
EVKIND = {"1": "一階 > 0 時轉加速", "2": "一階 > 0 時轉減速", "3": "一階 < 0 時轉減速", "4": "一階 < 0 時轉加速"}


def _stcell(e: dict | None) -> str:
    if not e or not e.get("n"):
        return '<td class="mu">—</td>'
    mk = {"strong": "▲", "weak": "▼"}.get(e.get("verdict"), "")
    tip = (f'{e["n"]} 個月、{e.get("runs", "—")} 段；平均 {_pp(e.get("avg"), 1)}%，所有月份 {_pp(e.get("all"), 1)}%；'
           f'差 {_pp(e.get("diff"), 1)}［{_pp(e.get("lo"), 1)}, {_pp(e.get("hi"), 1)}］；前後兩半 {_pp(e.get("d1"), 1)}／{_pp(e.get("d2"), 1)}；'
           f'{CPLV.get(e.get("verdict"), "—")}')
    return f'<td title="{_e(tip)}">{_e(_pp(e.get("diff"), 1))}<span class="hw">{e["n"]} 月</span>{f"<b>{mk}</b>" if mk else ""}</td>'


def _oook(o: dict | None, pair: str = "m2>m1") -> bool:
    c = ((o or {}).get("cw") or {}).get(pair) or {}
    r2, p = c.get("r2"), c.get("p")
    return bool(o) and not o.get("few") and r2 is not None and p is not None and r2 > 0 and p < S.M6_CW_ALPHA


def _r2txt(o: dict | None, mo: str) -> str:
    r2 = ((((o or {}).get("models") or {}).get(mo)) or {}).get("r2_0")
    return "—" if r2 is None else f"{_sgn(100 * r2, 1)}%"


def _oocell(o: dict | None, pair: str = "m2>m1") -> str:
    if not o or not o.get("n"):
        return '<td class="mu">—</td>'
    c = (o.get("cw") or {}).get(pair) or {}
    r2, p = c.get("r2"), c.get("p")
    ok = _oook(o, pair)
    tip = (f'{o["n"]} 個月（{o.get("a")}～{o.get("z")}）；R² {"—" if r2 is None else f"{100 * r2:+.2f}%"}，'
           f'Clark–West p {"—" if p is None else f"{p:.3f}"}' + ("；樣本外不到 36 個月" if o.get("few") else ""))
    return (f'<td title="{_e(tip)}">{"—" if r2 is None else _e(_sgn(100 * r2, 1)) + "%"}'
            f'<span class="hw">p {"—" if p is None else f"{p:.2f}"}</span>{"<b>●</b>" if ok else ""}</td>')


def _m6_valid(V: dict) -> str:
    """驗證段：第六版多層回歸的詳細數字（預設收起）。"""
    m6 = V.get("m6") or {}
    if not m6.get("items"):
        return '<p class="warn">第六版的多層回歸還沒產生（研究檔不是第六版）。</p>'
    it, gr = m6["items"], m6.get("groups") or {}
    names = [(k, _iname(k)) for k in S.DERIV]
    out = []
    P = m6.get("primary") or {}
    prow = []
    for h in S.M6_PRIMARY:
        e = P.get(h) or {}
        if h == "H2":
            stat = "—" if e.get("w") is None else f'Wald {e["w"]:.2f}'
        else:
            stat = _pp(e.get("b")) + (f'［{_pp(e.get("lo"))}, {_pp(e.get("hi"))}］' if e.get("lo") is not None else "")
        if h == "H3" and e.get("n_dec") is not None:
            stat += f'<span class="hw">減速 {e["n_dec"]} 月、加速 {e["n_acc"]} 月</span>'
        pv = "—" if e.get("p") is None else f'{e["p"]:.3f}'
        hv = "—" if e.get("holm") is None else f'{e["holm"]:.3f}'
        prow.append(f'<tr><td class="l">{h}</td><td class="l" data-h="內容">{_e(S.M6_PRIMARY[h][0])}</td><td data-h="月數">{e.get("n", 0)}</td>'
                    f'<td data-h="係數或統計量">{stat}</td><td data-h="重抽 p">{pv}</td><td data-h="Holm 校正後 p">{hv}</td>'
                    f'<td class="l" data-h="結果">{"通過" if e.get("pass") else "沒有通過"}</td></tr>')
    out.append('<h4>主要假說（事前寫定，Holm 校正，α 0.05）</h4><div class="tw"><table class="m6p stk"><tr><th class="l">假說</th>'
               '<th class="l">內容</th><th>月數</th><th>係數（百分點）或統計量</th><th>重抽 p</th><th>Holm 校正後 p</th>'
               '<th class="l">結果</th></tr>' + "".join(prow) + "</table></div>")
    leg = "★＝有預測性（樣本外也成立）、●＝樣本內看得到、樣本外沒有、○＝樣本內看得到（那段期間沒有做樣本外）；滑過看信賴區間、q、前後兩半。"
    gks = [g for g in GORDER if g in gr]
    rows_d = [(nm, it[k]["l1"]["d"]) for k, nm in names] + [(GNAME[g], gr[g]["l1"]["d"]) for g in gks]
    rows_c = [(nm, it[k]["l1"]["c"]) for k, nm in names] + [(GNAME[g], gr[g]["l1"]["c"]) for g in gks]
    out.append(_rmat(f"L1 延遲反應：二階（近 10 年百分位，中位數＝0、最高＝1）每多 1，那段期間{MK['mkt']}的報酬多幾個百分點",
                     rows_d, DCOLS, leg))
    out.append(_rmat("L1 累積期間", rows_c, CCOLS, leg))
    out.append(_rmat("L2 扣掉水準（0～100）與一階之後的二階", [(nm, it[k]["l2"]) for k, nm in names], DCOLS,
                     "一階就是項目本身的（年增率、PMI）只扣水準；" + "、".join(RG._x1_items()) + " 另外扣一階。"))
    out.append(_rmat("L3a 水準 × 二階的交互係數", [(nm, it[k]["l3a"]) for k, nm in names], DCOLS,
                     "正數＝水準越高，加速之後越強；負數＝水準越高，加速之後越弱。"))
    for zn, znm in (("bull", MK["bull"]), ("hike", MK["hike"])):
        out.append(_rmat(f"L3c 二階 × 環境（{znm}）的交互係數", [(nm, it[k]["l3c"][zn]) for k, nm in names], DCOLS))
    L4 = m6.get("l4") or {}
    out.append(_rmat("L4 景氣動能加速度 × 通膨利率加速度的交互係數",
                     [("延遲", (L4.get("inter") or {}).get("d")), ("累積", (L4.get("inter") or {}).get("c"))],
                     DCOLS + CCOLS))
    sth = "".join(f"<th>{_e(STNAME[x])}</th>" for x in ("hi_acc", "hi_dec", "lo_acc", "lo_dec"))
    srows = "".join(f'<tr><td class="l">{_e(nm)}</td>' + "".join(_stcell(((it[k].get("l3b") or {}).get("12") or {}).get(x))
                                                             for x in ("hi_acc", "hi_dec", "lo_acc", "lo_dec")) + "</tr>"
                    for k, nm in names)
    vs = [(((it[k].get("l3b") or {}).get("12") or {}).get(x) or {}).get("verdict") for k, _ in names
          for x in ("hi_acc", "hi_dec", "lo_acc", "lo_dec")]
    out.append(_part("L3b 四個狀態之後 12 個月（和所有月份比的差，百分點）", f'較強 {vs.count("strong")}、較弱 {vs.count("weak")}',
                     '<div class="tw"><table class="m6t"><tr><th class="l">項目</th>' + sth + "</tr>" + srows
                     + '</table></div><p class="note">▲▼＝信賴區間不含 0、前後兩半同號（月數 ≥ 24、段數 ≥ 4 才判定）。'
                       '同一列比「水準高、加速」和「水準高、減速」，看得出差別的才是加速度的作用。</p>'))
    gth = "".join(f"<th>{_e(STNAME[x])}</th>" for x in ("gA_rA", "gA_rD", "gD_rA", "gD_rD"))
    grows = "".join(f'<tr><td class="l">之後 {h} 個月</td>' + "".join(_stcell(((L4.get("states") or {}).get(str(h)) or {}).get(x))
                                                                for x in ("gA_rA", "gA_rD", "gD_rA", "gD_rD")) + "</tr>"
                    for h in S.M6_STATE_H)
    vs = [((((L4.get("states") or {}).get(str(h)) or {}).get(x)) or {}).get("verdict") for h in S.M6_STATE_H
          for x in ("gA_rA", "gA_rD", "gD_rA", "gD_rD")]
    out.append(_part("L4 景氣動能 × 通膨利率四個狀態（和所有月份比的差，百分點）", f'較強 {vs.count("strong")}、較弱 {vs.count("weak")}',
                     '<div class="tw"><table class="m6t"><tr><th class="l">期間</th>' + gth + "</tr>" + grows
                     + '</table></div><p class="note">四個狀態合起來的檢定是主要假說 H2。</p>'))
    orow = "".join(f'<tr><td class="l">{_e(nm)}</td>' + "".join(_oocell((it[k].get("oos") or {}).get(w)) for w, _ in OCOLS) + "</tr>"
                   for k, nm in names)
    ok = sum(1 for k, _ in names for w, _ in OCOLS if _oook((it[k].get("oos") or {}).get(w)))
    tot = sum(1 for k, _ in names for w, _ in OCOLS if ((it[k].get("oos") or {}).get(w) or {}).get("n")
              and not ((it[k].get("oos") or {}).get(w) or {}).get("few"))
    out.append(_part("樣本外：單項（有二階的模型對沒有二階的模型，R²；小字＝Clark–West p）", f"{tot} 個比較裡 {ok} 個 ●",
                     '<div class="tw"><table class="m6t"><tr><th class="l">項目</th>' + "".join(f"<th>{_e(h)}</th>" for _, h in OCOLS)
                     + "</tr>" + orow + '</table></div><p class="note">2008 年起每個月重新估計，只用報酬已經結束的月份；'
                     'R² > 0 而且 p < 0.05 標 ●（樣本內沒有成立的期間，這一格亮了也不算有預測性）。</p>'))
    G = m6.get("goos") or {}
    mods = [("m2", "m2>m1", "加組加速度"), ("m3", "m3>m1", "再加三個交互"), ("ridge", "m1>ridge", "脊回歸"), ("tree", "m0>tree", "決策樹")]
    grow_ = []
    for mo, pair, nm in mods:
        cells = []
        for w, _ in OCOLS:
            o = G.get(w) or {}
            pr = pair if mo != "ridge" else "ridge>m1"
            pr = pr if mo != "tree" else "tree>m0"
            cells.append(_oocell(o, pr))
        grow_.append(f'<tr><td class="l">{_e(nm)}</td>{"".join(cells)}</tr>')
    out.append(_part("樣本外：組與綜合模型", "對只看組水準的模型比，決策樹對過去平均報酬比",
                     '<div class="tw"><table class="m6t"><tr><th class="l">模型</th>' + "".join(f"<th>{_e(h)}</th>" for _, h in OCOLS)
                     + "</tr>" + "".join(grow_) + '</table></div><p class="note">只看組水準的模型本身在累積 24 個月對過去平均的 R²：'
                     + _e(_r2txt(G.get(f"0,{max(S.M6_CUM)}"), "m1")) + '。</p>'))
    erow = []
    for k, nm in names:
        l6 = it[k].get("l6") or {}
        cells = "".join(_stcell(((l6.get("kinds") or {}).get(kd) or {}).get("h", {}).get("12")) for kd in ("1", "2", "3", "4"))
        erow.append(f'<tr><td class="l">{_e(nm)}<span class="hw">{l6.get("n", 0)} 次</span></td>{cells}</tr>')
    vs = [((((it[k].get("l6") or {}).get("kinds") or {}).get(kd) or {}).get("h", {}).get(str(h)) or {}).get("verdict")
          for k, _ in names for kd in ("1", "2", "3", "4") for h in S.M6_STATE_H]
    out.append(_part("L6 轉折事件（平滑版二階翻正、翻負，新方向連 2 個月）之後 12 個月，和所有月份比的差",
                     f'6、12、24 個月共 {len(vs)} 個比較：較強 {vs.count("strong")}、較弱 {vs.count("weak")}、樣本不足 {vs.count("few")}',
                     '<div class="tw"><table class="m6t"><tr><th class="l">項目</th>'
                     + "".join(f"<th>{_e(EVKIND[x])}</th>" for x in ("1", "2", "3", "4"))
                     + "</tr>" + "".join(erow) + '</table></div><p class="note">少於 20 次＝樣本不足；▲▼＝信賴區間不含 0、前後兩半同號。</p>'))
    ext = m6.get("ext") or {}
    if ext:
        xl = ext.get("l1") or {}
        xr = [(_iname(k) if k in S.DERIV else GNAME.get(k, k), xl[k].get("d")) for k in list(S.DERIV) + GORDER if k in xl]
        hs = "；".join(f'{h} {_pp((ext.get(h) or {}).get("b"))}（p {(ext.get(h) or {}).get("p", 0) or 0:.2f}）' for h in ("H1", "H4"))
        rs = [(d or {}).get(w) or {} for _, d in xr for w, _ in DCOLS]
        nb = sum(1 for r in rs if r.get("b") is not None)
        n5 = sum(1 for r in rs if r.get("p") is not None and r["p"] < 0.05)
        out.append(_rmat(f'延伸樣本（國發會股價指數月平均，{ext.get("a")}～{ext.get("z")}；只當穩健度）', xr, DCOLS,
                         "報酬用月平均、晚一個月起算；沒有做多重比較校正，只看方向是不是和主樣本一樣。",
                         tally=f"{nb} 個有結果，重抽 p < 0.05 的 {n5} 個；{hs}"))
    # 第五版的每週驗證（狀態、偏相關）也留著
    rows5 = []
    for k in S.DERIV:
        rr = (V.get("dvr") or {}).get(k) or {}
        hs = S.DIMS[S.DIM_OF[k]]["fwd"]
        st = ((V.get("dvn") or {}).get(k) or {}).get("state")
        rows5.append(f'<tr><td class="l">{_e(_iname(k))}</td><td class="l">{_e(dv_past(rr, st, hs))}</td>'
                     f'<td class="l">{_e(dv_more(rr, hs))}</td></tr>')
    out.append(_part("第五版：每週樣本", "現在這個狀態之後的表現；扣掉水準之後的偏等級相關",
                     '<div class="tw"><table class="dvt"><tr><th class="l">項目</th><th class="l">過去這個狀態之後</th>'
                     '<th class="l">加速減速有沒有多出資訊</th></tr>' + "".join(rows5) + "</table></div>"))
    sm = m6.get("sample") or {}
    head = (f'邊際變化的多層回歸（第六版；每月樣本 {sm.get("a")}～{sm.get("z")}、{sm.get("T")} 個月；樣本外 {sm.get("oos_start")} 起）')
    return (f'<details class="ovw" id="m6"><summary><b>{_e(head)}</b><span class="sub">點開看每一層的數字；規格在看結果之前寫定（規劃文件第 15.11 節）</span>'
            f'</summary>{"".join(out)}</details>')


def _ll_text(ll: dict | None) -> str:
    if not ll:
        return "—"
    parts = []
    if ll.get("follow"):
        h = ll.get("follow_h")
        r = ((ll.get("past") or {}).get(str(h)) or (ll.get("past") or {}).get(h) or {}).get("rho")
        parts.append(f"主要反映已經走過的路（和之前 {h} 日漲跌 {_sgn(r, 2)}）")
    if ll.get("lead"):
        h = ll["lead"]
        e = (ll.get("fut") or {}).get(str(h)) or (ll.get("fut") or {}).get(h) or {}
        parts.append(f'之後 {h} 日{"較強" if (e.get("rho") or 0) > 0 else "較弱"}（{_sgn(e.get("rho"), 2)}）')
    return "；".join(parts) or "看不出領先"


def _evt_cell(ev: dict | None) -> str:
    if not ev:
        return "—"
    n = (ev.get(str(S.EVT_FWD[0])) or {}).get("n", 0)
    if not n:
        return "沒有"
    vs = "／".join(f'{h} 日{S.EV_VERDICT.get((ev.get(str(h)) or {}).get("verdict"), "—")}' for h in S.EVT_FWD)
    return f"{n} 次：{vs}"


def _rel_overview(V: dict) -> str:
    rel = V.get("rel") or {}
    if not rel:
        return '<p class="warn">單項分析還沒產生（研究檔不是第五版）。</p>'
    rows = []
    nf = nl = nga = ngb = nh = 0
    for sid in list(S.DIMS) + list(S.KEYS):
        a = rel.get(sid)
        if not a:
            continue
        name = S.DIMS[sid]["name"] if sid in S.DIMS else S.IND[S.KEYS.index(sid)][2]
        if not a.get("first"):
            rows.append(f'<tr><td class="l"><button type="button" class="nmb" data-k="{_e(sid)}">{_e(name)}</button></td>'
                        '<td class="l" colspan="5">歷史還不夠，還沒有結果</td></tr>')
            continue
        nh += 1
        ll = a.get("ll") or {}
        nf += bool(ll.get("follow"))
        nl += bool(ll.get("lead"))
        nga += ((a.get("gr") or {}).get("A") or {}).get("verdict") in ("strong", "weak")
        ngb += ((a.get("gr") or {}).get("B") or {}).get("verdict") in ("strong", "weak")
        g = a.get("gr") or {}
        ga, gb = g.get("A") or {}, g.get("B") or {}
        qa = f'（q＝{ga["q"]:.2f}）' if ga.get("q") is not None else ""
        rows.append(f'<tr><td class="l"><button type="button" class="nmb" data-k="{_e(sid)}">{_e(name)}</button></td>'
                    f'<td class="l" data-h="跟著走還是領先">{_e(_ll_text(a.get("ll")))}</td>'
                    f'<td class="l" data-h="這一項 → {_e(MK["mkt"])}">{_e(GRV.get(ga.get("verdict"), "—"))}{_e(qa)}</td>'
                    f'<td class="l" data-h="{_e(MK["mkt"])} → 這一項">{_e(_grb().get(gb.get("verdict"), "—"))}</td>'
                    f'<td class="l" data-h="進入過熱之後">{_e(_evt_cell((a.get("evt") or {}).get("hot")))}</td>'
                    f'<td class="l" data-h="進入過冷之後">{_e(_evt_cell((a.get("evt") or {}).get("cold")))}</td></tr>')
    m = MK["mkt"]
    head = (f'各項和{m}的關係（{nh} 條有結果）：{nf} 條主要反映已經走過的路、{nl} 條之後有領先關係；'
            f'Granger 這一項 → {m}成立 {nga} 條、{m} → 這一項成立 {ngb} 條')
    return (f'<details class="ovw"><summary><b>{_e(head)}</b><span class="sub">點開看每一條；點名稱，上面的對照圖會只看那一項</span></summary>'
            '<div class="tw"><table class="rlt stk"><tr><th class="l">項目</th><th class="l">跟著走還是領先</th>'
            f'<th class="l">Granger：這一項 → {_e(m)}</th><th class="l">Granger：{_e(m)} → 這一項</th>'
            '<th class="l">進入過熱之後</th><th class="l">進入過冷之後</th></tr>' + "".join(rows) + "</table></div></details>")


def _meta_json(V: dict) -> str:
    return json.dumps(V.get("meta") or meta(), ensure_ascii=False, separators=(",", ":"), sort_keys=True).replace("</", "<\\/")


def bottom_chip(a: dict, mk: str) -> str:
    """一段大跌進行中：這一次的落底訊號出現了沒（不論判定；docs/lab_noise_plan.md 第 10.7 節）。點了到訊號總覽的大跌後檢查卡。"""
    from . import bottomspec as BS
    rules = {"W10": a.get("w10") or {}, **(a.get("sig") or {})}
    parts, on = [], 0
    for k, v in rules.items():
        st = v.get("st")
        nm = BS.RULE_NAMES.get(k, k)
        if st == "on":
            on += 1
            parts.append(f'{nm}：{int(v["d"][5:7])}/{int(v["d"][8:10])} 出現')
        elif st == "wait":
            parts.append(f'{nm}：還沒' + (f'（再 {v["left"]} 個交易日）' if k == "W10" else ""))
        elif st == "none":
            parts.append(f'{nm}：這一次沒有出現')
    tip = "；".join(parts) + "。點了看每個落底訊號過去的成績（大跌後檢查）。"
    return (f'<a class="stc stx" href="x9o.html#r={_e(mk)}:bottom" title="{_e(tip)}"><b>落底訊號</b>{on}／{len(parts)} 出現</a>')


def state_line(V: dict) -> str:
    """頁首的市場狀態一行（docs/lab_signal_plan.md 第 6.1 節）：各面向熱度、泡沫等級、是否在一段大跌中。"""
    names = [nm for _, _, nm in S.BANDS]
    chips = []
    for d, L in V["dims"].items():
        sc = L["score"]
        if sc is None:
            chips.append(f'<span class="stc"><b>{_e(S.DSHORT[d])}</b>—</span>')
            continue
        z = names.index(L["band"]) if L["band"] in names else 2
        chips.append(f'<span class="stc stz{z}"><b>{_e(S.DSHORT[d])}</b>{n0(sc)}<i>{_e(L["band"])}</i></span>')
    b = V.get("bubnow")
    if b:
        from . import bubble as BU
        from . import bubspec as BS
        cs = "、".join(BU.SHORT[c] for c in b["cond"])
        tip = f'泡沫等級 {b["L"]} {BS.LEVELS[b["L"]]}' + (f'（{cs}）' if cs else "") + "，點了看泡沫頁"
        chips.append(f'<a class="stc" href="x9b.html#{_e(b["mk"])}" title="{_e(tip)}"><b>泡沫</b>{b["L"]}'
                     f'<i>{_e(BS.LEVELS[b["L"]])}</i></a>')
    if V.get("xschip"):                                      # 10 個月均線（總經策略，xstratspec；每個市場都列）
        chips.append(V["xschip"])
    if V.get("mrchip"):                                      # 融資維持率（只有台股；docs/lab_crash_plan.md 第 22 節）
        chips.append(V["mrchip"])
    nw = (V.get("bottom") or {}).get("now") or {}
    mk = V.get("mk") or (V.get("signow") or {}).get("mk") or ""
    if nw.get("active"):
        a = nw["active"][0]
        pd = a["p"]
        chips.append(f'<a class="stc stx" href="x9o.html#r={_e(mk)}:bottom"><b>一段大跌中</b>比 {int(pd[5:7])}/{int(pd[8:10])} 高點'
                     f' {_e(_sgn(100 * a["nowdd"], 1))}%</a>')
        chips.append(bottom_chip(a, mk))
    elif nw.get("dd60") is not None:
        chips.append(f'<span class="stc"><b>離 60 日高點</b>{_e(_sgn(100 * nw["dd60"], 1))}%</span>')
    on = (V.get("signow") or {}).get("on") or {}
    from . import sigspec as SS
    act = [nm for key, nm, *_ in SS.SCENARIOS if f"{mk}:scen:{key}" in on]
    if act:                                                  # 現在落在哪幾個情境（sigspec 第 4.10 節；景氣頁情境卡）
        chips.append(f'<a class="stc stw" href="#o=scen" data-open="out:out" data-to="scen" title="點了看「之後怎麼走？」裡的情境">'
                     f'<b>情境</b>{_e("、".join(act))}</a>')
    return f'<div class="stl" aria-label="市場狀態">{"".join(chips)}</div>'


def parts(V: dict) -> dict:
    """頁面的主體（美股頁每個指數各一份）：四個視角（雷達、階段、地形、研究）＋右側面板的內容＋雷達的資料；asof＝資料日。
    研究畫面＝原本的邊際變化、驗證、事件研究、資料來源，內容原封搬過去（docs/lab_visual_plan.md 第 5 節）。"""
    from . import heatviz as VZ
    Ds = V["dims"]
    asof = V["asof"]
    data_rows = "".join(f'<tr><td class="l">{_e(k)}</td><td>{v[0]:,}</td><td>{_e(v[1] or "—")}</td><td>{_e(v[2] or "—")}</td></tr>'
                        for k, v in sorted((V.get("data") or {}).items()))
    firsts = "、".join(f'{S.DSHORT[d]} {_ymd(L["first"])}' for d, L in Ds.items() if L["first"])
    research = (
        _dv_section(V)
        + '<section class="sec" id="valid"><h2>驗證</h2>' + _METHOD + _METHOD5
        + (f'<p class="note">面向分數最早從哪天有：{_e(firsts)}。</p>' if firsts else "")
        + _rel_overview(V) + _m6_valid(V)
        + "".join(_valid(d, Ds[d]) for d in Ds) + "</section>" + _ta_study(V)
        + f'<section class="sec" id="src"><h2>資料來源與筆數</h2><div class="tw"><table><tr><th class="l">檔</th><th>筆數</th>'
          f'<th>起</th><th>到</th></tr>{data_rows}</table></div><p class="note">{_e(_SRC_NOTE)}</p></section>'
    )
    body = (state_line(V) + VZ.main_view(V, V.get("ks") or []) + VZ.phase_view() + VZ.terrain_view() + VZ.research_view(V, research)
            + VZ.templates(V) + VZ.viz_json(V))
    return {"nav": "", "body": body, "asof": asof}


def render(V: dict) -> str:
    from . import appnav
    from . import heatviz as VZ
    P = parts(V)
    return appnav.finish(_HTML.replace("{{APPTAB}}", appnav.bar(MK["tab"])).replace("{{CSS}}", _CSS + appnav.CSS + VZ.CSS)
                         .replace("{{TITLE}}", _e(MK["title"])).replace("{{PURP}}", _e(MK["purp"])).replace("{{PRE}}", MK["pre"])
                         .replace("{{ASOF}}", _e(_md(P["asof"]))).replace("{{VSW}}", VZ.switch_html()).replace("{{DRAWER}}", VZ.DRAWER)
                         .replace("{{BODY}}", P["body"]).replace("{{META}}", _meta_json(V)).replace("{{JS}}", VZ.JS + _JS))


def _write(out: Path, text: str) -> bool:
    if out.exists() and out.read_text(encoding="utf-8") == text:
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return True


def build(out: Path = OUT, data_out: Path = OUT_DATA) -> bool:
    """建頁面與對照圖資料；兩個檔內容都沒變時不改寫。"""
    B = C.build()
    R = load_research() or {}
    changed = _write(out, render(view(B, R)))
    return HC.write(HC.build_data(B, R), data_out) or changed


_SRC_NOTE = ("融資融券、法人、期貨選擇權法人：FinMind（轉載證交所、期交所）；成交金額與加權指數：證交所；P/C 比、台指 VIX：期交所；"
             "新台幣、M1B／M2：央行；景氣燈號、領先指標、PMI、海關出口值：國發會；外銷訂單：經濟部；台灣 CPI：主計總處；"
             "上市櫃營收：公開資訊觀測站月營收（自算合計）；美國 CPI：勞工統計局；公債殖利率：美國財政部；"
             "聯邦基金利率：聯準會 H.15（DBnomics 轉載）與紐約聯準銀行；VIX、HYG、IEF、S&P 500：Yahoo；美國貨幣基金：OFR；"
             "外資持股比率：證交所；外資淨匯入：證期局新聞稿；央行定存單、存放款、拆款利率：央行統計資料庫；"
             "投信基金持股比重：投信投顧公會。"
             "廣度用上市櫃日線自算（當天最近一個月底市值 40 億以上的股票）。")

_METHOD = (
    '<div class="mth"><p><b>分數怎麼來</b>：每一項和自己過去比——今天的值在過去 3 年（月資料用 10 年）裡排第幾（只用今天以前的資料），'
    '依「熱的方向」換成 0～100。面向分數＝該面向全部項目的 0～100 平均，有值的項數要有 2/3 以上。</p>'
    '<p><b>驗證只當參考，不拿來刪項目</b>：看分數和之後加權指數漲跌的等級相關（全期間＋95% 信賴區間），再把同一批樣本依日期切成前後兩半各算一次；'
    '全期間信賴區間不含 0、而且兩半方向一樣，才寫「熱了之後較弱」或「熱了之後較強」，其他寫「看不出穩定關係」。'
    '「對照」兩欄是第一階段的切分，只列數字。</p>'
    '<p><b>等級相關</b>：負數＝分數越高，之後漲幅越小；正數相反。數字都很小是正常的，這頁是參考讀數。</p>'
    '<p><b>限制</b>：國發會資料用修正後的數字（兩個月後才算拿得到）；PMI、月營收從 2012 年、期貨選擇權法人從 2018 年、'
    '投信基金持股比重從 2021 年 10 月、美國貨幣基金從 2010 年 11 月、台指 VIX 從 2026 年 7 月、外資淨匯入從 2026 年 9 月才有資料，'
    '歷史不夠的照樣列出，但要等排名有 3 年（月資料 5 年）的歷史才有 0～100。'
    '美國 ICI 的基金現金比率在 CI 連不上、央行沒有公開超額準備的序列，改用央行定存單餘額 ÷ M2。</p></div>')

_METHOD5 = (
    '<div class="mth"><p><b>第五版加的分析</b>（只當參考；規格在看結果之前寫定，規劃文件第 14.14 節）：</p>'
    '<p><b>歷史位置</b>：百分位＝比過去多少比例的日子（月資料是月份）高；近 3 年、近 10 年、有資料以來各算一次，只和今天以前比。'
    '「YYYY 年 M 月以來最高」＝上一次比現在高是那個月；相隔不到 3 個月不寫。</p>'
    '<p><b>跟著走還是領先</b>：每週一個樣本，今天的 0～100 和台股「之前」與「之後」5～250 日漲跌的等級相關。'
    '之前的相關明顯比之後大，代表這一項主要在反映台股已經走過的路。</p>'
    '<p><b>Granger 預測力</b>：每月一個樣本，扣掉台股自己過去 3 個月的報酬之後，這一項過去 3 個月的 0～100 能不能幫忙預測下個月的台股'
    '（異質變異穩健的 Wald 檢定）；原本 44 項一起、泡沫 7 項一組、6 個面向另一組做多重比較校正，q ≤ 0.10、前後兩半方向一樣才算。'
    '這是預測上的先後關係，不等於真正的因果。</p>'
    '<p><b>情境</b>：事先定義好的 9 種面向組合（例：景氣好、價格回檔＝基本面 60 以上、技術未滿 40），在情境裡的日子之後 3 個月'
    '上漲、大跌的機率和隨便挑一天比，判定同訊號總覽（2026-10-20 起取代對照圖的交互分析）。</p></div>')

_HTML = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<link rel="icon" href="data:,">
<title>{{TITLE}}</title>
<style>{{CSS}}</style></head>
<body>
<div class="top">{{APPTAB}}<span class="asof">資料到 {{ASOF}}</span><a class="back" href="./">返回主頁</a></div>
<div class="vbar">{{VSW}}<details class="purp"><summary>這頁怎麼看</summary><p>{{PURP}}</p></details></div>{{PRE}}
<main>{{BODY}}</main>
{{DRAWER}}
<script>window.HEAT_META={{META}};</script>
<script>{{JS}}</script>
</body></html>
"""

_CSS = """
:root{color-scheme:light dark;--bg:#fff;--panel:#fff;--card2:#f4f6fa;--ink:#1f2733;--ink2:#44505f;--mut:#67727f;--line:#e8ebf1;--line2:#d3dae4;
--acc:#2563c9;--accd:#1c4fa8;--accbg:rgba(37,99,201,.10);--warn:#b45309;--ring:#fff;--tipbg:#fff;--shadow:0 4px 14px rgba(20,30,50,.14);
--c0:#2f6fb5;--c1:#7fb0de;--c2:#b8c0cc;--c3:#f0a35a;--c4:#d33a34;--t0:#2a65a8;--t1:#3572b2;--t2:#44505f;--t3:#b25f10;--t4:#c8322c;
--sbg:#fdecea;--wbg:#e6f4ec;--curbg:#fff7e6;--bp:#c2c8d0;--zh:rgba(211,58,52,.07);--zc:rgba(47,111,181,.08);
--p0:#7b5ea7;--p1:#199e70;--p2:#c98500;--p3:#d55181;--p4:#4d7c0f;
--dfund:#199e70;--dchip:#7b5ea7;--dgliq:#a88a00;--dtliq:#d55181;--dtech:#0f8fa8;--dbubl:#a0522d;
--q0:#c8322c;--q1:#f0948d;--q2:#245fa6;--q3:#5a9fe8}
@media (prefers-color-scheme:dark){:root{--bg:#0b111c;--panel:#121a28;--card2:#182234;--ink:#e8eef8;--ink2:#aab6c9;--mut:#8392a8;
--line:#223049;--line2:#30425f;--acc:#6aa8ff;--accd:#8fbcff;--accbg:rgba(106,168,255,.14);--warn:#f0a24a;--ring:#0b111c;--tipbg:#182234;
--shadow:0 8px 26px rgba(0,0,0,.5);--c0:#3d82e0;--c1:#7cb3ec;--c2:#8b96a8;--c3:#f3a35c;--c4:#f15b50;
--t0:#6ea6f0;--t1:#93c0ef;--t2:#aab6c9;--t3:#f2a65e;--t4:#ff7d72;--sbg:rgba(241,91,80,.16);--wbg:rgba(47,191,113,.15);
--curbg:rgba(243,163,92,.14);--bp:#4a5a74;--zh:rgba(241,91,80,.10);--zc:rgba(61,130,224,.12);
--p0:#997ac9;--p1:#24a476;--p2:#bf7c00;--p3:#db5786;--p4:#6c9d3a;
--dfund:#24a476;--dchip:#997ac9;--dgliq:#a68900;--dtliq:#db5786;--dtech:#22a5c0;--dbubl:#c87a4f;
--q0:#f0584b;--q1:#a04038;--q2:#5294e6;--q3:#3260a3}}
*{box-sizing:border-box}
[hidden]{display:none!important}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 -apple-system,"PingFang TC","Noto Sans TC",Segoe UI,sans-serif;-webkit-text-size-adjust:100%}
a{color:var(--acc);text-decoration:none}
table,.num{font-variant-numeric:tabular-nums}
.top{display:flex;align-items:baseline;gap:4px 12px;flex-wrap:wrap;padding:10px 16px 4px;max-width:1080px;margin:0 auto}
.top b{font-size:18px}.asof{color:var(--mut);font-size:12.5px;flex:1;min-width:0}
.back{font-size:13px;color:var(--mut);white-space:nowrap}
.purp{color:var(--ink2);font-size:13px;line-height:1.75}.purp>summary{cursor:pointer;color:var(--mut);font-size:12.5px;list-style:none}
.purp>summary::-webkit-details-marker{display:none}.purp>summary::before{content:"ⓘ ";}.purp p{margin:4px 0 2px;max-width:860px}
.snav{position:sticky;top:0;z-index:5;background:var(--bg);display:flex;gap:4px;overflow-x:auto;scrollbar-width:none;padding:6px 16px 7px;border-bottom:1px solid var(--line);max-width:1080px;margin:0 auto}
.snav::-webkit-scrollbar{display:none}
.snav a{padding:2px 10px;border-radius:12px;color:var(--ink2);font-size:13px;white-space:nowrap;background:var(--card2)}
main{padding:14px 16px 80px;max-width:1080px;margin:0 auto}
.mu{color:var(--mut)}.warn{color:var(--warn);font-size:13.5px}
.hz{font-size:13px;color:var(--ink2);margin:0 0 16px;line-height:1.75}.hz .mu{margin-left:4px}
.cd{border:1px solid var(--line);border-radius:14px;padding:12px 16px 14px;margin:0 0 18px;scroll-margin-top:48px}
.ch{display:flex;align-items:flex-start;flex-wrap:wrap;gap:4px 12px}
.ch h2{margin:0;font-size:17px;flex:1;min-width:0}.ch h2 .sub,.sec h2 .sub,h3 .sub{font-size:12.5px;font-weight:400;color:var(--mut);margin-left:8px}
.sv{display:flex;align-items:baseline;gap:8px}.sc{font-size:34px;line-height:1;font-weight:800}.bn{font-weight:700}
.sc.b0,.bn.b0{color:var(--t0)}.sc.b1,.bn.b1{color:var(--t1)}.sc.b2,.bn.b2{color:var(--t2)}.sc.b3,.bn.b3{color:var(--t3)}.sc.b4,.bn.b4{color:var(--t4)}
.wk{font-size:12.5px;color:var(--mut)}
.hot{font-size:12.5px;color:var(--mut);margin:4px 0 0}
.mt{position:relative;display:grid;grid-template-columns:repeat(5,1fr);gap:2px;height:10px;margin:10px 0 2px}
.mt i{display:block;border-radius:3px}.mt .b0{background:var(--c0)}.mt .b1{background:var(--c1)}.mt .b2{background:var(--c2)}.mt .b3{background:var(--c3)}.mt .b4{background:var(--c4)}
.mt .mk{position:absolute;top:-5px;width:4px;height:20px;margin-left:-2px;background:var(--ink);border-radius:2px;box-shadow:0 0 0 2px var(--ring)}
.mtl{display:grid;grid-template-columns:repeat(5,1fr);font-size:11px;color:var(--mut);text-align:center}
.past{font-size:13.5px;color:var(--ink2);margin:8px 0 2px;line-height:1.75}
.vd{font-size:13.5px;margin:2px 0}.eq{font-size:12px;color:var(--mut);margin:2px 0 8px}
.its{margin-top:6px}
.ith,.it{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(120px,1.3fr) 72px 48px 48px;gap:8px;align-items:center;padding:6px 2px;border-bottom:1px solid var(--line)}
.ith{font-size:11.5px;color:var(--mut);border-bottom:2px solid var(--line);padding-top:8px}
.ith span:nth-child(n+3),.ipl,.ish,.iwk{text-align:right;white-space:nowrap}
.inm{min-width:0;display:flex;flex-direction:column;line-height:1.35}.inm b{font-weight:600;font-size:14px}.inm i{font-style:normal;color:var(--mut);font-size:12px}
.inm em.px{font-style:normal;color:var(--warn);font-size:11.5px}
.it0 .ipl,.it0 .ish,.it0 .iwk{color:var(--mut);font-weight:400}
.ihb{display:flex;align-items:center;gap:8px}.hb{flex:1;height:8px;background:var(--card2);border-radius:4px;overflow:hidden;min-width:60px}
.hb i{display:block;height:100%;border-radius:4px}.hb .b0{background:var(--c0)}.hb .b1{background:var(--c1)}.hb .b2{background:var(--c2)}.hb .b3{background:var(--c3)}.hb .b4{background:var(--c4)}
.hn{width:2.2em;text-align:right;font-size:14px}
.ipl{font-weight:700}.ish,.iwk{font-size:13px;color:var(--ink2)}
.sec{margin:28px 0 0;scroll-margin-top:48px}.sec>h2{font-size:17px;margin:0 0 10px}
svg{display:block;width:100%;height:auto}
svg .gl{stroke:var(--line);stroke-width:1}svg .gt{font-size:11px;fill:var(--mut)}
.lvt td:last-child{white-space:normal;min-width:220px}.tal{margin:8px 0 4px;padding-left:20px;font-size:13.5px;line-height:1.8;color:var(--ink2)}
.rec{font-size:13.5px;color:var(--ink2);margin:2px 0 8px;line-height:1.8}
.evt td:first-child{white-space:nowrap}
.tw{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:0 0 14px}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap;vertical-align:top}
th{background:var(--card2);color:var(--mut);font-weight:600;font-size:12px}
td.l,th.l{text-align:left}
table.dt td:first-child{white-space:normal;min-width:170px}.hw{display:block;font-size:11.5px;color:var(--mut);font-weight:400}
h3{font-size:15px;margin:18px 0 6px;color:var(--accd)}h4{font-size:13.5px;margin:10px 0 4px}
.mth p{font-size:13.5px;line-height:1.8;margin:6px 0;color:var(--ink2)}
.note{color:var(--mut);font-size:12px;line-height:1.7}
.hd{margin:2px 0 6px}.sum{font-size:15px;font-weight:700;margin:0 0 8px;line-height:1.6}
.strips{display:flex;flex-direction:column;border:1px solid var(--line);border-radius:12px;overflow:hidden}
.sr{display:grid;grid-template-columns:96px minmax(0,1fr) 92px minmax(0,1.1fr);gap:4px 12px;align-items:center;padding:9px 12px;border-top:1px solid var(--line);color:var(--ink)}
.sr:first-child{border-top:0}.sr:hover{background:var(--card2)}
.sr-n{display:flex;flex-direction:column;line-height:1.3}.sr-n b{font-size:14px}.sr-n i{font-style:normal;font-size:11px;color:var(--mut)}
.sr-c{display:grid;grid-template-columns:repeat(52,minmax(0,1fr));gap:1px;height:20px}
.sr-c i{display:block;border-radius:1px}.sr-c .na{background:transparent;box-shadow:inset 0 0 0 1px var(--line)}
.sr-c .b0,.srl .b0{background:var(--c0)}.sr-c .b1,.srl .b1{background:var(--c1)}.sr-c .b2,.srl .b2{background:var(--c2)}.sr-c .b3,.srl .b3{background:var(--c3)}.sr-c .b4,.srl .b4{background:var(--c4)}
.sr-v{display:flex;align-items:baseline;gap:6px}.sr-v .sc{font-size:26px}.sr-v em{font-style:normal;font-weight:700;font-size:13px}
.sr-t{font-size:12.5px;color:var(--ink2);line-height:1.5}
.srl{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:11.5px;color:var(--mut);margin:6px 2px 0;align-items:center}
.srl span{display:inline-flex;align-items:center;gap:4px}.srl i{display:inline-block;width:12px;height:10px;border-radius:2px}
.nmb{background:none;border:0;padding:0;margin:0;font:inherit;font-weight:600;font-size:14px;color:var(--ink);text-align:left;cursor:pointer}
.nmb:hover,.nmb:focus-visible{color:var(--acc);text-decoration:underline dotted}
.inm .ipos{color:var(--ink2);font-size:11.5px}.inm .idv{color:var(--accd);font-size:11.5px}
.cbar{display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center;margin:0 0 6px}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.ck{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);background:var(--bg);border-radius:14px;padding:3px 10px;font:inherit;font-size:13px;color:var(--ink2);cursor:pointer}
.ck i{display:inline-block;width:14px;height:3px;border-radius:2px;background:var(--line)}
.ck.on{border-color:var(--ink2);color:var(--ink);font-weight:600}.ck.on i{background:var(--c,var(--ink2))}
.tb{border:1px solid var(--line);background:var(--bg);border-radius:8px;padding:3px 10px;font:inherit;font-size:12.5px;color:var(--ink2);cursor:pointer}
.tb.on{background:var(--ink);border-color:var(--ink);color:var(--bg)}
.seg{display:inline-flex;gap:4px;flex-wrap:wrap}
.pick{border:1px solid var(--line);border-radius:10px;padding:8px 10px;margin:0 0 8px;display:flex;flex-direction:column;gap:8px}
.pg{display:flex;flex-wrap:wrap;gap:6px;align-items:center}.pg b{font-size:12.5px;color:var(--mut);min-width:4.5em}
.cw{position:relative;min-height:160px}
.cw svg{display:block;width:100%;height:auto;touch-action:pan-y}
.cw .ln{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.cw .lpx{fill:none;stroke:var(--ink2);stroke-width:1.5}
.cw .el{font-size:11.5px;fill:var(--ink2)}.cw .pt{font-size:11.5px;fill:var(--mut)}
.cw .shh{fill:var(--c4);opacity:.14}.cw .shc{fill:var(--c0);opacity:.14}
.cw .zh{fill:var(--zh)}.cw .zc{fill:var(--zc)}
.cw .cx{stroke:var(--ink);stroke-width:1;opacity:.5}
.tip{position:absolute;pointer-events:none;background:var(--tipbg);color:var(--ink);border:1px solid var(--line);border-radius:8px;box-shadow:var(--shadow);padding:6px 9px;font-size:12px;min-width:150px;z-index:3}
.tip b{display:block;font-size:12px;margin-bottom:2px}.tip div{display:flex;align-items:center;gap:6px;white-space:nowrap}
.tip i{display:inline-block;width:12px;height:3px;border-radius:2px}.tip strong{font-size:13px;min-width:2.4em}
.tip .tpx{color:var(--mut);margin-top:2px}
#cmp-an h3{margin-top:14px}#cmp-an h4{margin:14px 0 4px}#cmp-an p{font-size:13.5px;line-height:1.75;margin:4px 0;color:var(--ink2)}
.an svg{display:block;width:auto;max-width:100%;height:auto}
.an .mob{display:none}
.an .bp{fill:var(--bp)}.an .bf{fill:var(--ink2)}.an .ci{stroke:var(--ink);stroke-width:1.5}.an .zl{stroke:var(--ink2);stroke-width:1}
.an .lr{fill:none;stroke:var(--ink2);stroke-width:2}
table.g3 td.c3{white-space:normal;min-width:118px;text-align:left;vertical-align:top}
table.g3 th{white-space:normal}
table.ct td:first-child{white-space:normal;min-width:6em}
.an th{white-space:normal}
.c3 b{display:block;font-size:15px}.c3 span{display:block;font-size:11.5px;color:var(--ink2)}.c3 em{display:block;font-style:normal;font-size:12px;font-weight:600;margin-top:2px}
.c3.cs{background:var(--sbg)}.c3.cw{background:var(--wbg)}.c3.cf{color:var(--mut)}.c3.cf b{color:var(--mut)}
.c3.cur{box-shadow:inset 0 0 0 2px var(--ink)}
tr.cur td{background:var(--curbg)}.ovl{font-size:13px}
.ovw{margin:14px 0}.ovw>summary{cursor:pointer;font-size:14px;line-height:1.7;color:var(--accd)}.ovw>summary .sub{display:block;font-size:12px;color:var(--mut);font-weight:400}
table.dvt td:nth-child(2),table.dvt td:nth-child(4),table.dvt td:nth-child(5){white-space:normal;min-width:180px}
table.rlt td{white-space:normal;min-width:120px}table.rlt td:first-child{min-width:150px}
table.dvs td:nth-child(3){white-space:normal;min-width:180px}table.dvs tr.grow td{background:var(--card2)}
.acl{font-weight:600;cursor:help;border-bottom:1px dotted var(--mut)}
table.m6t{font-size:12px}table.m6t th{white-space:normal;font-size:11px}table.m6t td{padding:5px 6px}
table.m6t td:first-child,table.m6t th:first-child{position:sticky;left:0;background:var(--bg);z-index:1;white-space:normal;min-width:7.5em}
table.m6t th:first-child{background:var(--card2)}table.m6t td b{color:var(--accd);margin-left:2px}
table.m6p td:nth-child(2){white-space:normal;min-width:220px}
.rsp{display:flex;flex-wrap:wrap;gap:12px}
.m6s{margin:6px 0;border-top:1px solid var(--line);padding-top:6px}.m6s>summary{cursor:pointer;font-size:13.5px;font-weight:600;color:var(--ink)}
.m6s>summary .sub{display:block;margin:1px 0 0;font-weight:400;font-size:12px;color:var(--mut)}.an .rp{fill:var(--acc)}.an .ri{fill:var(--ink)}.an .rn{fill:var(--bg);stroke:var(--mut);stroke-width:1.5}
@media (max-width:640px){
 .sr{grid-template-columns:minmax(0,1fr) auto;grid-template-areas:"n v" "c c" "t t";padding:9px 10px}
 .sr-n{grid-area:n}.sr-v{grid-area:v}.sr-c{grid-area:c;height:16px}.sr-t{grid-area:t;font-size:12px}
 .sr-n{flex-direction:row;align-items:baseline;gap:8px}
 .pg b{min-width:100%}
 .tip{min-width:130px}
 table.g3 td.c3{min-width:0;padding:6px 4px}.c3 b{font-size:14px}.c3 span,.c3 em{font-size:11px}.c3 span{white-space:nowrap;letter-spacing:-.2px}
 table.g3 th{padding:6px 5px}
 .an .mob{display:block}.an .dsk{display:none}
 .an table{font-size:12px}.an th,.an td{padding:6px 4px}
 table.stk,table.stk tbody{display:block}table.stk tr:first-child{display:none}
 table.stk tr{display:block;padding:8px 2px;border-bottom:1px solid var(--line)}
 table.stk td{display:block;border:0;padding:1px 0;text-align:left;white-space:normal;min-width:0!important}
 table.stk td[data-h]::before{content:attr(data-h) "：";color:var(--mut);font-size:12px}
}
@media (max-width:640px){
 .ith{display:none}
 .it{grid-template-columns:minmax(0,1fr) 64px 78px;row-gap:3px}
 .it .inm{grid-column:1/2;grid-row:1}.it .ihb{grid-column:1/2;grid-row:2}
 .it .ipl{grid-column:2/3;grid-row:1/3;align-self:center}
 .it .ish{grid-column:3/4;grid-row:1}.it .iwk{grid-column:3/4;grid-row:2}
 .it .ish::before{content:"佔比 "}.it .iwk::before{content:"本週 "}
 .sc{font-size:30px}
 .ch h2 .sub{display:block;margin-left:0}
 .lvt,.lvt tbody{display:block}.lvt tr:first-child{display:none}
 .lvt tr{display:grid;grid-template-columns:minmax(0,1fr) auto auto auto;gap:2px 12px;padding:7px 2px;border-bottom:1px solid var(--line)}
 .lvt td{border:0;padding:0}
 .lvt td:last-child{grid-column:1/-1;min-width:0;white-space:normal;color:var(--ink2);font-size:12.5px;text-align:left}
 .lvt td:last-child:empty{display:none}
 .evt th:first-child,.evt td:first-child{position:sticky;left:0;background:var(--bg);z-index:1}
}
"""

# 對照台股、單項分析、交互分析（第 14.14 節第 3～5 點）。序列從 x9mh.json 讀；交互分析在瀏覽器算（和 heatrel.group_stats 同一套規則）。
_JS = r"""
window.heatInit = function () {
'use strict';
if (window.__heatAC) window.__heatAC.abort();            // 換指數時重跑：先拿掉上一次掛在 document、window 的事件
const AC = window.__heatAC = new AbortController(), SIG = {signal: AC.signal};
const M = window.HEAT_META, ROOT = document.getElementById('cmp');
if (!M || !ROOT) return;
const $ = (s, r) => (r || document).querySelector(s);
const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const MKT = M.mkt || '台股', PXN = M.px || '加權指數', MKH = esc(MKT), PXH = esc(PXN);
const NAME = {}, SHORT = {};
M.dims.forEach(d => { NAME[d.id] = d.name; SHORT[d.id] = d.short; });
Object.keys(M.items).forEach(k => { NAME[k] = M.items[k].name; SHORT[k] = M.items[k].name; });
const ACC = {};
(M.acc || []).forEach(a => { NAME[a.id] = a.name; SHORT[a.id] = a.name; ACC[a.id] = a; });
const isDim = id => Object.prototype.hasOwnProperty.call(M.order, id);
const isAcc = id => Object.prototype.hasOwnProperty.call(ACC, id);
const noRaw = id => isDim(id) || isAcc(id);
const VERD = {strong: '之後較強', weak: '之後較弱', none: '看不出差別', few: '樣本不足'};
let D = null, failed = false;
const st = {sel: M.dims.slice(0, M.max).map((d, i) => ({id: d.id, slot: i})), range: M.rdef, mode: 'h', pick: false};

// ── 數字與日期
const sgn = r => (r < 0 ? '−' : (r > 0 ? '+' : ''));
function pct(x, d) { if (x == null) return '—'; d = d == null ? 1 : d; const r = Number(x.toFixed(d)); return sgn(r) + Math.abs(r).toFixed(d) + '%'; }
function rho(x) { if (x == null) return '—'; const r = Number(x.toFixed(2)); return sgn(r) + Math.abs(r).toFixed(2); }
function pf(p) { return p == null ? '—' : (p < 0.001 ? '< 0.001' : p.toFixed(3)); }
function pq(lab, p) { return p != null && p < 0.001 ? lab + ' < 0.001' : lab + '＝' + pf(p); }
function sc0(v) { const r = Math.round(v); return (r === 20 || r === 40 || r === 60 || r === 80) && v < r ? (Math.floor(v * 10) / 10).toFixed(1) : String(r); }  // 同 Python n0()
function grp(v, dec) { return Math.abs(v).toLocaleString('en-US', {minimumFractionDigits: dec, maximumFractionDigits: dec}); }
function fmtRaw(id, v) {
  if (v == null) return '—';
  const it = M.items[id];
  if (!it) return String(Math.round(v));
  const s = grp(v, it.dec), sign = v < 0 ? '−' : (it.signed && v > 0 ? '+' : '');
  return it.unit === '%' ? sign + s + '%' : sign + s + (it.unit ? ' ' + it.unit : '');
}
function ymd(d) { return d ? (+d.slice(0, 4)) + '/' + (+d.slice(5, 7)) + (d.length > 7 ? '/' + (+d.slice(8, 10)) : '') : '—'; }
function val(t, i) { if (!t) return null; const j = i - t.o; return j >= 0 && j < t.v.length ? t.v[j] : null; }
function trunc(s, n) { return s.length > n ? s.slice(0, n) + '…' : s; }
function bandName(x) { for (const b of M.bands) if (x >= b[0] && (x < b[1] || b[1] >= 100)) return b[2]; return null; }
function pal(slot) { return 'var(--p' + slot + ')'; }                     // 線色跟著深淺色（CSS 變數 --p0～--p4）

// ── 選線
function slotOf(id) { const s = st.sel.find(x => x.id === id); return s ? s.slot : -1; }
function msg(t) { const m = $('#cmp-msg'); m.textContent = t || ''; m.hidden = !t; }
function toggle(id) {
  const i = st.sel.findIndex(x => x.id === id);
  if (i >= 0) st.sel.splice(i, 1);
  else {
    if (st.sel.length >= M.max) { msg('最多同時 ' + M.max + ' 條線，先拿掉一條再加。'); return; }
    const used = new Set(st.sel.map(x => x.slot));
    let s = 0;
    while (used.has(s)) s++;
    st.sel.push({id: id, slot: s});
  }
  msg('');
  if (st.sel.length !== 1 || noRaw(st.sel[0].id)) st.mode = 'h';
  render();
}
function only(id) {
  if (window.heatView) window.heatView('radar', 'cmp');       // 對照圖在雷達畫面
  st.sel = [{id: id, slot: 0}];
  st.mode = 'h';
  msg('');
  render();
  ROOT.scrollIntoView({behavior: 'smooth', block: 'start'});
}
function btn(t, on, fn) {
  const b = document.createElement('button');
  b.type = 'button'; b.className = 'tb' + (on ? ' on' : ''); b.textContent = t;
  b.setAttribute('aria-pressed', on ? 'true' : 'false');
  b.addEventListener('click', fn);
  return b;
}
function chip(id, label) {
  const b = document.createElement('button');
  b.type = 'button'; b.className = 'ck';
  const s = slotOf(id);
  if (s >= 0) { b.classList.add('on'); b.style.setProperty('--c', pal(s)); }
  b.setAttribute('aria-pressed', s >= 0 ? 'true' : 'false');
  b.appendChild(document.createElement('i'));
  b.appendChild(document.createTextNode(label));
  b.addEventListener('click', () => toggle(id));
  return b;
}
function controls() {
  const dims = $('#cmp-dims');
  dims.textContent = '';
  M.dims.forEach(d => dims.appendChild(chip(d.id, d.short)));
  const nItems = st.sel.filter(x => !isDim(x.id)).length;
  const more = $('#cmp-more');
  more.textContent = (st.pick ? '收起細項' : '＋ 細項') + (nItems ? '（已選 ' + nItems + '）' : '');
  more.setAttribute('aria-expanded', st.pick ? 'true' : 'false');
  const pk = $('#cmp-pick');
  pk.hidden = !st.pick;
  pk.textContent = '';
  if (st.pick) {
    if (M.acc && M.acc.length) {
      const g = document.createElement('div'); g.className = 'pg';
      const h = document.createElement('b'); h.textContent = '加速度'; g.appendChild(h);
      M.acc.forEach(a => g.appendChild(chip(a.id, a.name)));
      pk.appendChild(g);
    }
    M.dims.forEach(d => {
      const g = document.createElement('div'); g.className = 'pg';
      const h = document.createElement('b'); h.textContent = d.short; g.appendChild(h);
      M.order[d.id].forEach(k => g.appendChild(chip(k, M.items[k].name)));
      pk.appendChild(g);
    });
  }
  const rg = $('#cmp-rng');
  rg.textContent = '';
  M.ranges.forEach(r => rg.appendChild(btn(r ? r + ' 年' : '全部', st.range === r, () => { st.range = r; msg(''); render(); })));
  const md = $('#cmp-mode');
  md.textContent = '';
  const can = st.sel.length === 1 && !noRaw(st.sel[0].id);
  md.hidden = !can;
  if (can) {
    md.appendChild(btn('0～100', st.mode === 'h', () => { st.mode = 'h'; render(); }));
    md.appendChild(btn('原始值', st.mode === 'r', () => { st.mode = 'r'; render(); }));
  }
}

// ── 對照圖
function win() {
  const daily = st.range === 1;
  const ds = daily ? D.d.d : D.w.d, px = daily ? D.d.px : D.w.px;
  const i1 = ds.length - 1;
  let i0 = 0;
  if (st.range) {
    const last = ds[i1];
    const cut = (+last.slice(0, 4) - st.range) + last.slice(4);
    i0 = ds.findIndex(d => d > cut);
    if (i0 < 0) i0 = 0;
  }
  return {daily: daily, ds: ds, px: px, i0: i0, i1: i1};
}
function seriesOf(id, w, raw) {
  const s = D.s[id];
  const key = (raw && !noRaw(id) ? 'r' : 'h') + (w.daily ? 'd' : '');
  const t = s ? s[key] : null;
  const out = [];
  for (let i = w.i0; i <= w.i1; i++) out.push(val(t, i));
  return out;
}
function nice(a, b, n) {
  if (!(b > a)) return [a];
  const span = b - a, step0 = span / Math.max(1, n), mag = Math.pow(10, Math.floor(Math.log10(step0))), e = step0 / mag;
  const step = (e >= 7.5 ? 10 : e >= 3.5 ? 5 : e >= 1.5 ? 2 : 1) * mag;
  const out = [];
  for (let v = Math.ceil(a / step) * step; v <= b + 1e-9 * span; v += step) out.push(Number(v.toPrecision(12)));
  return out;
}
function logTicks(a, b) {
  const out = [];
  for (let e = Math.floor(Math.log10(a)); e <= Math.ceil(Math.log10(b)); e++) {
    [1, 2, 5].forEach(m => { const v = m * Math.pow(10, e); if (v >= a && v <= b) out.push(v); });
  }
  return out.length >= 2 ? out : nice(a, b, 3);
}
function xTicks(ds, i0, i1, maxN) {
  const yrs = [];
  for (let i = i0 + 1; i <= i1; i++) if (ds[i].slice(0, 4) !== ds[i - 1].slice(0, 4)) yrs.push(i);
  if (yrs.length >= 2) {
    const s = Math.ceil(yrs.length / maxN);
    return yrs.filter((_, k) => k % s === 0).map(i => [i, ds[i].slice(0, 4)]);
  }
  const ms = [];
  for (let i = i0 + 1; i <= i1; i++) if (ds[i].slice(5, 7) !== ds[i - 1].slice(5, 7)) ms.push(i);
  const s = Math.max(1, Math.ceil(ms.length / maxN));
  return ms.filter((_, k) => k % s === 0).map(i => [i, (+ds[i].slice(0, 4)) + '/' + (+ds[i].slice(5, 7))]);
}
function path(vals, X, Y, i0) {
  let d = '', pen = false;
  for (let j = 0; j < vals.length; j++) {
    const v = vals[j];
    if (v == null) { pen = false; continue; }
    d += (pen ? 'L' : 'M') + X(i0 + j).toFixed(1) + ' ' + Y(v).toFixed(1);
    pen = true;
  }
  return d;
}
function draw() {
  const box = $('#cmp-chart');
  if (!D) {
    box.innerHTML = failed ? '<p class="warn">走勢資料載入失敗。<button type="button" class="tb" id="cmp-retry">重試</button></p>'
                           : '<p class="note">走勢載入中…</p>';
    const r = $('#cmp-retry');
    if (r) r.addEventListener('click', load);
    return;
  }
  if (!st.sel.length) { box.innerHTML = '<p class="note">點上面的按鈕加入要看的線。</p>'; $('#cmp-cap').textContent = ''; return; }
  const W = Math.max(300, Math.floor(box.clientWidth || 640)), narrow = W < 560;
  const PL = narrow ? 46 : 52, PR = narrow ? 8 : 108, T1 = 8, H1 = narrow ? 180 : 230, G = 28, H2 = narrow ? 110 : 140, PB = 22;
  const w = win(), n = w.i1 - w.i0 + 1;
  const X = i => PL + (W - PL - PR) * (n <= 1 ? 0 : (i - w.i0) / (n - 1));
  const raw = st.mode === 'r' && st.sel.length === 1 && !noRaw(st.sel[0].id);
  const lines = st.sel.map(x => ({id: x.id, slot: x.slot, v: seriesOf(x.id, w, raw)}));
  let y0 = 0, y1 = 100;
  if (raw) {
    const vs = lines[0].v.filter(v => v != null);
    if (vs.length) {
      y0 = Math.min.apply(null, vs); y1 = Math.max.apply(null, vs);
      if (y0 === y1) { y0 -= 1; y1 += 1; }
      const p = (y1 - y0) * 0.06; y0 -= p; y1 += p;
    }
  }
  const Y = v => T1 + H1 * (1 - (v - y0) / (y1 - y0));
  let s = '';
  if (!raw) {
    s += '<rect class="zh" x="' + PL + '" y="' + Y(100).toFixed(1) + '" width="' + (W - PL - PR) + '" height="' + (Y(80) - Y(100)).toFixed(1) + '"/>';
    s += '<rect class="zc" x="' + PL + '" y="' + Y(20).toFixed(1) + '" width="' + (W - PL - PR) + '" height="' + (Y(0) - Y(20)).toFixed(1) + '"/>';
  }
  (raw ? nice(y0, y1, 4) : [0, 20, 40, 60, 80, 100]).forEach(t => {
    const y = Y(t).toFixed(1);
    s += '<line class="gl" x1="' + PL + '" x2="' + (W - PR) + '" y1="' + y + '" y2="' + y + '"/><text class="gt" x="' + (PL - 5) + '" y="' + (+y + 3.5).toFixed(1) + '" text-anchor="end">' + esc(raw ? fmtRaw(lines[0].id, t) : t) + '</text>';
  });
  lines.forEach(L => { const d = path(L.v, X, Y, w.i0); if (d) s += '<path class="ln" d="' + d + '" style="stroke:' + pal(L.slot) + '"/>'; });
  if (!narrow) {
    const labs = [];
    lines.forEach(L => {
      for (let j = L.v.length - 1; j >= 0; j--) if (L.v[j] != null) { labs.push({y: Y(L.v[j]), x: X(w.i0 + j), t: SHORT[L.id], c: pal(L.slot)}); break; }
    });
    labs.sort((a, b) => a.y - b.y);
    let last = -1e9;
    labs.forEach(l => {
      s += '<circle cx="' + l.x.toFixed(1) + '" cy="' + l.y.toFixed(1) + '" r="4" style="fill:' + l.c + ';stroke:var(--ring)" stroke-width="2"/>';
      if (l.y - last < 13) return;
      last = l.y;
      s += '<text class="el" x="' + (W - PR + 8) + '" y="' + (l.y + 4).toFixed(1) + '">' + esc(trunc(l.t, 7)) + '</text>';
    });
  }
  const top2 = T1 + H1 + G;
  const pv = [];
  for (let i = w.i0; i <= w.i1; i++) pv.push(w.px[i]);
  const lv = pv.filter(v => v > 0);
  const lo = Math.min.apply(null, lv), hi = Math.max.apply(null, lv);
  const Y2 = v => top2 + H2 * (1 - (Math.log(v) - Math.log(lo)) / ((Math.log(hi) - Math.log(lo)) || 1));
  if (st.sel.length === 1) {
    const hv = seriesOf(st.sel[0].id, w, false), half = n > 1 ? (W - PL - PR) / (n - 1) / 2 : 0;
    const kind = v => (v == null ? 0 : (v >= M.shade[0] ? 1 : (v < M.shade[1] ? -1 : 0)));
    let j = 0;
    while (j < hv.length) {
      const k = kind(hv[j]);
      if (!k) { j++; continue; }
      let e = j;
      while (e + 1 < hv.length && kind(hv[e + 1]) === k) e++;
      const xa = Math.max(PL, X(w.i0 + j) - half), xb = Math.min(W - PR, X(w.i0 + e) + half);
      s += '<rect class="' + (k === 1 ? 'shh' : 'shc') + '" x="' + xa.toFixed(1) + '" y="' + top2 + '" width="' + Math.max(1, xb - xa).toFixed(1) + '" height="' + H2 + '"/>';
      j = e + 1;
    }
  }
  logTicks(lo, hi).forEach(t => {
    const y = Y2(t).toFixed(1);
    s += '<line class="gl" x1="' + PL + '" x2="' + (W - PR) + '" y1="' + y + '" y2="' + y + '"/><text class="gt" x="' + (PL - 5) + '" y="' + (+y + 3.5).toFixed(1) + '" text-anchor="end">' + esc(Math.round(t).toLocaleString('en-US')) + '</text>';
  });
  s += '<path class="lpx" d="' + path(pv, X, Y2, w.i0) + '"/>';
  s += '<text class="pt" x="' + PL + '" y="' + (top2 - 9) + '">' + PXH + '（對數座標）</text>';
  xTicks(w.ds, w.i0, w.i1, narrow ? 4 : 7).forEach(t => {
    s += '<text class="gt" x="' + X(t[0]).toFixed(1) + '" y="' + (top2 + H2 + 15) + '" text-anchor="middle">' + esc(t[1]) + '</text>';
  });
  const Ht = top2 + H2 + PB;
  s += '<line class="cx" x1="0" x2="0" y1="' + T1 + '" y2="' + (top2 + H2) + '" visibility="hidden"/>';
  box.innerHTML = '<svg viewBox="0 0 ' + W + ' ' + Ht + '" width="' + W + '" height="' + Ht + '" role="img" aria-label="選的線與' + PXH + '的走勢">' + s + '</svg><div class="tip" hidden></div>';
  const svg = box.querySelector('svg'), tip = box.querySelector('.tip'), cx = svg.querySelector('.cx');
  const move = ev => {
    const r = svg.getBoundingClientRect();
    const x = (ev.clientX - r.left) * (W / r.width);
    let j = Math.round((x - PL) / ((W - PL - PR) || 1) * (n - 1));
    j = Math.max(0, Math.min(n - 1, j));
    const i = w.i0 + j, xx = X(i).toFixed(1);
    cx.setAttribute('x1', xx); cx.setAttribute('x2', xx); cx.setAttribute('visibility', 'visible');
    tip.textContent = '';
    const h = document.createElement('b'); h.textContent = ymd(w.ds[i]); tip.appendChild(h);
    lines.forEach(L => {
      const row = document.createElement('div');
      const k = document.createElement('i'); k.style.background = pal(L.slot); row.appendChild(k);
      const vv = document.createElement('strong');
      const v = L.v[j];
      vv.textContent = v == null ? '—' : (raw ? fmtRaw(L.id, v) : sc0(v));
      row.appendChild(vv);
      row.appendChild(document.createTextNode(' ' + SHORT[L.id]));
      tip.appendChild(row);
    });
    const pr = document.createElement('div'); pr.className = 'tpx';
    pr.textContent = PXN + ' ' + (w.px[i] == null ? '—' : Math.round(w.px[i]).toLocaleString('en-US'));
    tip.appendChild(pr);
    tip.hidden = false;
    const bx = box.getBoundingClientRect(), tw = tip.offsetWidth;
    let left = ev.clientX - bx.left + 14;
    if (left + tw > bx.width) left = ev.clientX - bx.left - tw - 14;
    tip.style.left = Math.max(0, left) + 'px';
    tip.style.top = Math.max(0, ev.clientY - bx.top - 12) + 'px';
  };
  svg.addEventListener('pointermove', move);
  svg.addEventListener('pointerdown', move);
  svg.addEventListener('pointerleave', () => { cx.setAttribute('visibility', 'hidden'); tip.hidden = true; });
  let cap = raw ? '上圖：' + NAME[st.sel[0].id] + '的原始值。' : '上圖：0～100（100 最熱；淡紅底＝80 以上、淡藍底＝20 以下）。';
  if (st.sel.some(x => isAcc(x.id))) cap += '加速度線＝組內幾成在加速（100＝全部在加速）。';
  if (st.sel.length === 1) cap += isAcc(st.sel[0].id) ? '下圖淡紅＝八成以上在加速的期間，淡藍＝兩成以下。' : '下圖淡紅＝這一項 ≥ 80（過熱）的期間，淡藍＝< 20（過冷）。';
  cap += w.daily ? '近 1 年用每天的值。' : '用每週最後一個交易日的值。';
  $('#cmp-cap').textContent = cap;
}

// ── 單項分析（研究檔的結果）
function g(o, h) { return o ? (o[h] || o[String(h)]) : null; }
function llBlock(ll, W) {
  const H = M.llh;
  const bars = H.slice().reverse().map(h => ({h: h, e: g(ll.past, h), f: false})).concat(H.map(h => ({h: h, e: g(ll.fut, h), f: true})));
  const Hh = 176, PL = 30, PB = 38, top = 10, bw = (W - PL - 30) / bars.length;
  const Y = v => top + (Hh - top - PB) * (1 - (v + 1) / 2);
  let s = '';
  [-1, -0.5, 0, 0.5, 1].forEach(t => {
    s += '<line class="' + (t === 0 ? 'zl' : 'gl') + '" x1="' + PL + '" x2="' + (W - 6) + '" y1="' + Y(t).toFixed(1) + '" y2="' + Y(t).toFixed(1) + '"/><text class="gt" x="' + (PL - 4) + '" y="' + (Y(t) + 3.5).toFixed(1) + '" text-anchor="end">' + t + '</text>';
  });
  bars.forEach((b, k) => {
    const x = PL + 8 + k * bw + (b.f ? 16 : 0), r = b.e ? b.e.rho : null;
    if (r != null) {
      const ya = Y(Math.max(r, 0)), hh = Math.max(1, Math.abs(Y(r) - Y(0)));
      s += '<rect class="' + (b.f ? 'bf' : 'bp') + '" x="' + (x + bw * 0.22).toFixed(1) + '" y="' + ya.toFixed(1) + '" width="' + (bw * 0.56).toFixed(1) + '" height="' + hh.toFixed(1) + '"><title>' + (b.f ? '之後 ' : '之前 ') + b.h + ' 日：' + rho(r) + '</title></rect>';
      if (b.f && b.e.lo != null) { const c = (x + bw / 2).toFixed(1); s += '<line class="ci" x1="' + c + '" x2="' + c + '" y1="' + Y(b.e.lo).toFixed(1) + '" y2="' + Y(b.e.hi).toFixed(1) + '"/>'; }
    }
    s += '<text class="gt" x="' + (x + bw / 2).toFixed(1) + '" y="' + (Hh - PB + 14) + '" text-anchor="middle">' + b.h + '</text>';
  });
  const half = H.length * bw;
  s += '<text class="gt" x="' + (PL + 8 + half / 2).toFixed(1) + '" y="' + (Hh - 6) + '" text-anchor="middle">' + MKH + '之前 N 日的漲跌</text>';
  s += '<text class="gt" x="' + (PL + 24 + half * 1.5).toFixed(1) + '" y="' + (Hh - 6) + '" text-anchor="middle">' + MKH + '之後 N 日的漲跌</text>';
  const txt = [];
  if (ll.follow) { const e = g(ll.past, ll.follow_h); txt.push('主要反映' + MKT + '已經走過的路：和之前 ' + ll.follow_h + ' 日漲跌的相關 ' + rho(e && e.rho) + '，比和之後漲跌的相關大得多。'); }
  if (ll.lead) { const e = g(ll.fut, ll.lead); txt.push('之後 ' + ll.lead + ' 日有領先關係：熱了之後' + MKT + '較' + (e.rho > 0 ? '強' : '弱') + '（相關 ' + rho(e.rho) + '［' + rho(e.lo) + ', ' + rho(e.hi) + '］，前後兩半 ' + rho(e.h1) + '／' + rho(e.h2) + '）。'); }
  if (!txt.length) txt.push('看不出領先：之後 5～250 日的相關，信賴區間都含 0，或前後兩半方向不同。');
  const rows = H.map(h => { const p = g(ll.past, h), f = g(ll.fut, h); return '<tr><td>' + h + ' 日</td><td>' + rho(p && p.rho) + '</td><td>' + rho(f && f.rho) + (f && f.lo != null ? '<span class="hw">［' + rho(f.lo) + ', ' + rho(f.hi) + '］' + esc(VERD[f.verdict] || '') + '</span>' : '') + '</td></tr>'; }).join('');
  return '<h4>跟著走還是領先？</h4><p><b>' + esc(txt.join('')) + '</b></p><svg viewBox="0 0 ' + W + ' ' + Hh + '" width="' + W + '" height="' + Hh + '" role="img" aria-label="和' + MKH + '之前、之後漲跌的相關">' + s + '</svg>'
    + '<details><summary class="note">看數字</summary><div class="tw"><table><tr><th>期間</th><th>和之前漲跌的相關</th><th>和之後漲跌的相關［95% 信賴區間］</th></tr>' + rows + '</table></div></details>'
    + '<p class="note">等級相關：+1＝這一項越熱、' + MKH + '漲越多；−1 相反；0＝沒有關係。灰色長條是「之前」的漲跌，深色是「之後」，直線是信賴區間。</p>';
}
function grBlock(id, gr) {
  const A = gr && gr.A, B = gr && gr.B;
  let h = '<h4>預測力檢定（Granger）</h4>';
  if (!A || A.verdict === 'few') return h + '<p class="note">每月樣本不到 96 個月，不檢定。</p>';
  const FN = M.famn || {item: 44, dim: 5};
  const fam = isDim(id) ? FN.dim + ' 個面向一起校正' : ((M.items[id] || {}).dim === 'bubl' ? '泡沫 ' + FN.bubl + ' 項一起校正' : FN.item + ' 項一起校正');
  const va = {strong: '有額外的預測力：熱了之後，下個月' + MKT + '較強', weak: '有額外的預測力：熱了之後，下個月' + MKT + '較弱', none: '看不出額外的預測力'}[A.verdict];
  const rob = Object.keys(A.rob || {}).sort((a, b) => a - b).map(k => '落後 ' + k + ' 個月 ' + pq('p', A.rob[k])).join('、');
  h += '<p>扣掉' + MKH + '自己過去 ' + M.grmain + ' 個月的走勢之後，這一項過去 ' + M.grmain + ' 個月的 0～100：<b>' + esc(va) + '</b>（' + A.n + ' 個月；' + pq('p', A.p) + '，' + fam + '後 ' + pq('q', A.q) + (rob ? '；' + rob : '') + '）。</p>';
  const vb = {strong: '可以，' + MKT + '漲了之後這一項變熱', weak: '可以，' + MKT + '漲了之後這一項變冷', none: '看不出', few: '樣本不足'}[B ? B.verdict : 'few'];
  h += '<p>反過來，' + MKH + '過去 ' + M.grmain + ' 個月的報酬能不能預測這一項：<b>' + esc(vb) + '</b>（' + pq('p', B && B.p) + '，' + pq('q', B && B.q) + '）。</p>';
  return h + '<p class="note">q ≤ ' + M.bhq + '、前後兩半方向一樣才算。這是預測上的先後關係，不等於真正的因果；兩個方向都成立時，多半是互相影響。</p>';
}
function rollBlock(roll, W) {
  let h = '<h4>關係穩不穩定（滾動相關）</h4>';
  const pts = (roll || []).filter(p => p[1] != null);
  if (pts.length < 2) return h + '<p class="note">歷史不到 5 年，沒有滾動相關。</p>';
  const Hh = 140, PL = 30, PR = 8, top = 8, PB = 20, n = pts.length;
  const X = k => PL + (W - PL - PR) * k / (n - 1), Y = v => top + (Hh - top - PB) * (1 - (v + 1) / 2);
  let s = '';
  [-1, -0.5, 0, 0.5, 1].forEach(t => {
    s += '<line class="' + (t === 0 ? 'zl' : 'gl') + '" x1="' + PL + '" x2="' + (W - PR) + '" y1="' + Y(t).toFixed(1) + '" y2="' + Y(t).toFixed(1) + '"/><text class="gt" x="' + (PL - 4) + '" y="' + (Y(t) + 3.5).toFixed(1) + '" text-anchor="end">' + t + '</text>';
  });
  s += '<path class="lr" d="' + pts.map((p, k) => (k ? 'L' : 'M') + X(k).toFixed(1) + ' ' + Y(p[1]).toFixed(1)).join('') + '"/>';
  let prev = '';
  const yrs = [];
  pts.forEach((p, k) => { const y = p[0].slice(0, 4); if (y !== prev) { yrs.push([k, y]); prev = y; } });
  const step = Math.max(1, Math.ceil(yrs.length / (W < 480 ? 4 : 7)));
  yrs.filter((_, k) => k % step === 0).forEach(t => { s += '<text class="gt" x="' + X(t[0]).toFixed(1) + '" y="' + (Hh - 4) + '" text-anchor="middle">' + t[1] + '</text>'; });
  const lastp = pts[n - 1];
  return h + '<svg viewBox="0 0 ' + W + ' ' + Hh + '" width="' + W + '" height="' + Hh + '" role="img" aria-label="滾動相關">' + s + '</svg><p class="note">每 4 週一點：取到那一週為止的 ' + Math.round(M.roll[0] / 52) + ' 年，熱度和之後 ' + M.roll[1] + ' 日' + PXH + '漲跌的等級相關。在 0 上面＝那幾年熱了之後較強；線在 0 上下來回，代表關係不穩定。最近一點 ' + rho(lastp[1]) + '（' + ymd(lastp[0]) + '）。</p>';
}
function lastHeat(id) { const t = D.s[id] && D.s[id].h; return t ? val(t, D.w.d.length - 1) : null; }
function bandBlock(id, bands) {
  const cur = lastHeat(id), cb = cur == null ? null : bandName(cur);
  const names = M.bands.map(b => b[2]).concat(['全部']);
  const rows = names.map((nm, k) => {
    const cells = M.relh.map(h => { const r = (g(bands, h) || [])[k]; return '<td>' + (r && r.n ? pct(r.avg) + '<span class="hw">上漲 ' + Math.round(r.up) + '%</span>' : '—') + '</td>'; }).join('');
    const r60 = (g(bands, 60) || [])[k];
    const nw = r60 ? r60.n.toLocaleString('en-US') : '—', dd = r60 && r60.dd != null ? pct(r60.dd) : '—';
    return '<tr' + (nm === cb ? ' class="cur"' : '') + '><td class="l">' + esc(nm) + (nm === cb ? '（現在）' : '') + '<span class="hw mob">' + nw + ' 週</span><span class="hw mob">跌幅 ' + dd + '</span></td><td class="dsk">' + nw + '</td>' + cells + '<td class="dsk">' + dd + '</td></tr>';
  }).join('');
  return '<h4>回測：這一項在各區時，之後' + MKH + '的表現</h4><div class="tw"><table><tr><th class="l">這一項在</th><th class="dsk">週數</th>' + M.relh.map(h => '<th>之後 ' + h + ' 日</th>').join('') + '<th class="dsk">60 日內最大跌幅中位數</th></tr>' + rows + '</table></div>'
    + '<p class="note">平均＝之後 N 個交易日' + PXH + '的平均漲跌（t＋1 收盤起算），小字是上漲機率。同一段行情會連續很多週落在同一區，週數不等於獨立的次數。<span class="mob">手機上「跌幅」＝之後 60 日內最大跌幅的中位數。</span></p>';
}
function evtBlock(evt) {
  const kinds = [['hot', '進入過熱（升到 ' + M.evt.hot[0] + ' 以上）'], ['cold', '進入過冷（降到 ' + M.evt.cold[0] + ' 以下）']];
  const rows = kinds.map(kn => {
    const ev = evt ? evt[kn[0]] : null, n = ev ? (g(ev, M.evtfwd[0]) || {}).n || 0 : 0;
    const cells = M.evtfwd.map(h => {
      const e = ev ? g(ev, h) : null;
      if (!e || !e.n) return '<td>—</td>';
      return '<td>' + pct(100 * e.avg) + '<span class="hw">比所有日子 ' + pct(100 * e.diff) + '</span>' + (e.lo != null ? '<span class="hw">［' + pct(100 * e.lo) + ', ' + pct(100 * e.hi) + '］</span>' : '') + '<span class="hw">' + esc(VERD[e.verdict] || '') + '</span></td>';
    }).join('');
    return '<tr><td class="l">' + esc(kn[1]) + '<span class="hw mob">' + n + ' 次</span></td><td class="dsk">' + n + '</td>' + cells + '</tr>';
  }).join('');
  const lists = kinds.map(kn => {
    const L = evt && evt[kn[0]] && evt[kn[0]].list;
    if (!L || !L.length) return '';
    return '<details><summary class="note">' + esc(kn[1]) + '：每一次的日期（' + L.length + ' 次）</summary><p class="evl">' + L.map(x => ymd(x[0]) + '：' + M.evtfwd.map((h, k) => h + ' 日 ' + pct(x[k + 1] == null ? null : 100 * x[k + 1])).join('、')).join('；') + '</p></details>';
  }).join('');
  return '<h4>回測：剛進入過熱、過冷的那一天之後</h4><div class="tw"><table class="ct"><tr><th class="l">事件</th><th class="dsk">次數</th>' + M.evtfwd.map(h => '<th>之後 ' + h + ' 日平均</th>').join('') + '</tr>' + rows + '</table></div>' + lists
    + '<p class="note">前 ' + M.evt.hot[1] + ' 個交易日都還沒到那一區，今天第一天到，才算一次。和這一項有 0～100 的所有日子比；少於 20 次寫樣本不足。</p>';
}
const VER6 = {pred: '有預測性', in_only: '樣本內看得到、樣本外沒有', in_untested: '樣本內看得到（這個期間沒有做樣本外）', none: '看不出', few: '樣本不足'};
const OOS6 = {pred: '樣本外也成立', fail: '樣本外沒有成立', untested: '那段期間沒有做樣本外', few: '樣本不足'};
function rspPanel(rows, labs, W, y0, y1, title) {
  const Hh = 168, PL = 40, PR = 6, top = 20, PB = 34, n = rows.length, bw = (W - PL - PR) / Math.max(1, n);
  const Y = v => top + (Hh - top - PB) * (1 - (v - y0) / (y1 - y0));
  let s = '<text class="gt" x="' + PL + '" y="12">' + esc(title) + '</text>';
  nice(y0, y1, 4).forEach(t => {
    s += '<line class="' + (t === 0 ? 'zl' : 'gl') + '" x1="' + PL + '" x2="' + (W - PR) + '" y1="' + Y(t).toFixed(1) + '" y2="' + Y(t).toFixed(1) + '"/><text class="gt" x="' + (PL - 4) + '" y="' + (Y(t) + 3.5).toFixed(1) + '" text-anchor="end">' + (t > 0 ? '+' : '') + t + '</text>';
  });
  rows.forEach((r, k) => {
    const cx = PL + bw * (k + 0.5);
    if (r[1] != null) {
      if (r[2] != null && r[3] != null) s += '<line class="ci" x1="' + cx.toFixed(1) + '" x2="' + cx.toFixed(1) + '" y1="' + Y(r[2]).toFixed(1) + '" y2="' + Y(r[3]).toFixed(1) + '"/>';
      const cls = r[4] === 'pred' ? 'rp' : (r[4] === 'in_only' || r[4] === 'in_untested' ? 'ri' : 'rn');
      s += '<circle class="' + cls + '" cx="' + cx.toFixed(1) + '" cy="' + Y(r[1]).toFixed(1) + '" r="4.5"><title>' + esc(labs[k] + '：' + pct(r[1], 2).replace('%', ' 個百分點') + (r[2] != null ? '［' + pct(r[2], 2).replace('%', '') + ', ' + pct(r[3], 2).replace('%', '') + '］' : '') + '，' + (VER6[r[4]] || '')) + '</title></circle>';
    }
    s += '<text class="gt" x="' + cx.toFixed(1) + '" y="' + (Hh - PB + 14) + '" text-anchor="middle">' + esc(labs[k]) + '</text>';
  });
  s += '<text class="gt" x="' + ((PL + W - PR) / 2).toFixed(1) + '" y="' + (Hh - 4) + '" text-anchor="middle">個月</text>';
  return '<svg viewBox="0 0 ' + W + ' ' + Hh + '" width="' + W + '" height="' + Hh + '" role="img" aria-label="' + esc(title) + '">' + s + '</svg>';
}
function respBlock(id, W) {
  const r = D.m6 ? D.m6[id] : null;
  let h = '<h4>' + (isAcc(id) ? '多數項目加速之後，幾個月有反應？' : '這一項加速之後，幾個月有反應？') + '</h4>';
  const d = r ? (r.d || []) : [], c = r ? (r.c || []) : [];
  if (!d.concat(c).some(x => x[1] != null)) return h + '<p class="note">每月樣本不到 ' + M.m6.minn + ' 個月，或研究檔還沒有第六版的結果。</p>';
  const oo = OOS6[(r.sum || {}).oos];
  h += '<p><b>' + esc(r.txt ? '加速時，' + r.txt + (oo ? '（' + oo + '）' : '') + '。' : '看不出：0～24 個月的反應，多重比較校正後都不成立，或前後兩半、相鄰期間的方向不一致。') + '</b></p>';
  let lo = 0, hi = 0;
  d.concat(c).forEach(x => { [x[1], x[2], x[3]].forEach(v => { if (v != null) { lo = Math.min(lo, v); hi = Math.max(hi, v); } }); });
  const pad = (hi - lo) * 0.08 || 1;
  lo -= pad; hi += pad;
  const wide = W >= 560, w1 = wide ? Math.floor((W - 12) * 8 / 14) : W, w2 = wide ? W - 12 - w1 : W;
  const dl = d.map(x => x[0] + '～' + (x[0] + M.m6.win)), cl = c.map(x => String(x[0]));
  h += '<div class="rsp">' + rspPanel(d, dl, w1, lo, hi, '之後第幾個月的 ' + M.m6.win + ' 個月報酬（百分點）') + rspPanel(c, cl, w2, lo, hi, '從現在起累積幾個月的報酬（百分點）') + '</div>';
  const unit = isAcc(id) ? '全部在加速（相對一半在加速）' : '二階在近 10 年最高（相對中位數）';
  const row = (lab, x, key) => '<tr><td class="l">' + esc(lab) + '</td><td data-h="係數（百分點）">' + (x[1] == null ? '—' : pct(x[1], 2).replace('%', '') + (x[2] != null ? '<span class="hw">［' + pct(x[2], 2).replace('%', '') + ', ' + pct(x[3], 2).replace('%', '') + '］</span>' : '')) + '</td><td data-h="月數">' + (x[5] || '—') + '</td><td class="l" data-h="判定">' + esc(VER6[x[4]] || '—') + '</td><td data-h="樣本外">' + oosCell(r.oos, key) + '</td></tr>';
  const rows = d.map((x, k) => row(dl[k] + ' 個月後', x, x[0] + ',' + M.m6.win)).join('') + c.map((x, k) => row('累積 ' + cl[k] + ' 個月', x, '0,' + x[0])).join('');
  h += '<details><summary class="note">看數字</summary><div class="tw"><table class="stk"><tr><th class="l">期間</th><th>係數（百分點）</th><th>月數</th><th class="l">判定</th><th>樣本外</th></tr>' + rows + '</table></div></details>';
  return h + '<p class="note">點＝' + esc(unit) + '時，那段期間' + MKH + '的報酬多（少）幾個百分點，已扣掉' + MKH + '過去 1、12 個月的漲跌；直線＝95% 信賴區間（區塊重抽）。'
    + '深色實心＝多重比較校正後成立、前後兩半與相鄰期間方向一致（藍色＝樣本外也成立），空心＝看不出。每個月一個樣本，1997 年 7 月起；樣本外＝2008 年起每月只用當時的資料重新估計。</p>';
}
function oosCell(oos, key) {
  const o = oos ? oos[key] : null;
  if (!o || !o[0]) return '—';
  if (o[3]) return '樣本不足';
  return o[1] == null ? '—' : 'R² ' + pct(o[1], 2) + '<span class="hw">p ' + (o[2] == null ? '—' : o[2].toFixed(3)) + '</span>';
}
function single(box, id) {
  const a = D.an ? D.an[id] : null;
  let h = '<h3>' + esc(NAME[id]) + '和' + MKH + '的關係<span class="sub">只當參考；研究檔的結果，資料或規格改了才重算</span></h3>';
  const W = Math.max(280, Math.min(620, Math.floor(box.clientWidth || 600)));
  if (isAcc(id)) {
    box.innerHTML = '<div class="an">' + h + '<p class="note">這條線＝' + ACC[id].n + ' 項裡有幾成在加速（一階比之前高）；研究用每個月底的值。</p>' + respBlock(id, W) + '</div>';
    return;
  }
  if (!a || !a.first) { box.innerHTML = '<div class="an">' + h + '<p class="note">這一項歷史還不夠，或研究檔還沒有這一項的結果。</p>' + (D.m6 && D.m6[id] ? respBlock(id, W) : '') + '</div>'; return; }
  h += '<p class="note">' + esc(NAME[id]) + '從 ' + ymd(a.first) + ' 起有 0～100；以下用每週最後一個交易日的值（Granger 用每月最後一個交易日）。</p>';
  box.innerHTML = '<div class="an">' + h + llBlock(a.ll, W) + (D.m6 && D.m6[id] ? respBlock(id, W) : '') + grBlock(id, a.gr) + rollBlock(a.roll, W) + bandBlock(id, a.bands) + evtBlock(a.evt) + '</div>';
}

// ── 多條線一起看：「之後怎麼走？」面板裡的情境，框出只用到這幾個面向的（2026-10-20 起取代交互分析；docs/lab_heatviz_v2_plan.md 第 5、11 節；
//    2026-10-21 情境從主畫面搬進面板，docs/lab_noise_plan.md 第 11 節）
let SQSEL = null;                                          // 選到的面向（null＝不框）
function sqOn(c) { return !!SQSEL && (c.dataset.dims || '').split(' ').every(g => g.split(',').some(d => SQSEL.has(d))); }
function sqMark(root) {                                    // 面板開著（或剛打開）時框起來；框到的收在「其他情境」裡就展開
  if (!root) return;
  root.querySelectorAll('#scen .sqr').forEach(c => { const on = sqOn(c); c.classList.toggle('hl', on); if (on) { const f = c.closest('details.osq'); if (f) f.open = true; } });
}
window.heatScenHl = sqMark;
function scenHint(box, ids) {                              // 每一列的 data-dims＝情境用到的面向（以空白分組；台股資金一組兩個，選到任一個就算）
  const dims = new Set(ids.map(id => (M.items[id] && M.items[id].dim) || id));
  const def = M.dims.slice(0, M.max).map(d => d.id), dflt = ids.length === def.length && def.every(d => ids.includes(d));   // 預設的幾條＝不框
  SQSEL = dflt ? null : dims;
  const t = document.getElementById('ot-out');
  let n = 0;
  if (t && SQSEL) t.content.querySelectorAll('.sqr').forEach(c => { if (sqOn(c)) n++; });
  sqMark(document.getElementById('drw-c'));
  box.innerHTML = '<div class="an"><h3>多條線一起看</h3><p class="note">幾個面向一起看，請看「之後怎麼走？」裡的情境：事先定義好的面向組合，'
    + '過去出現之後 3 個月上漲、大跌的機率（判定同訊號總覽）。' + (dflt ? '' : n ? '只用到這幾條線的有 ' + n + ' 個，打開後會用虛線框起來。' : '沒有情境只用到這幾條線。')
    + '</p><p><button type="button" class="tb" data-open="out:out" data-to="scen">看情境 →</button></p></div>';
}
function analysis() {
  const box = $('#cmp-an');
  box.textContent = '';
  if (!D || !st.sel.length) return;
  if (st.sel.length === 1) { SQSEL = null; sqMark(document.getElementById('drw-c')); single(box, st.sel[0].id); }
  else scenHint(box, st.sel.map(x => x.id));
}

function render() { controls(); draw(); aw = $('#cmp-an').clientWidth; analysis(); }
function getP() {                                           // 同一個檔只下載一次（雷達、階段、3D、面板共用）
  const C = window.__heatP = window.__heatP || {};
  if (!C[M.data]) C[M.data] = fetch(M.data || 'x9mh.json', {cache: 'no-cache'}).then(r => { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
    .catch(e => { delete C[M.data]; throw e; });
  return C[M.data];
}
window.heatGet = getP;
function load() {
  failed = false;
  draw();
  getP().then(d => { if (AC.signal.aborted) return; D = d; render(); })
    .catch(() => { if (AC.signal.aborted) return; failed = true; draw(); });
}
$('#cmp-more').addEventListener('click', () => { st.pick = !st.pick; msg(''); controls(); });
document.addEventListener('click', e => {                  // 點項目名稱：打開右側面板（沒有面板的組線直接放進對照圖）；面板裡的按鈕放進對照圖
  const b = e.target.closest && e.target.closest('.nmb, .cmpk');
  if (!b || !b.dataset.k) return;
  e.preventDefault();
  if (b.classList.contains('nmb') && window.heatOpen && window.heatOpen(b.dataset.k)) return;
  if (window.heatClose) window.heatClose();
  only(b.dataset.k);
}, SIG);
let rt = null;
let aw = 0;
window.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(() => { if (!D) return; draw(); const w = $('#cmp-an').clientWidth; if (Math.abs(w - aw) > 40) { aw = w; analysis(); } }, 150); }, SIG);
controls();
load();
if (window.heatViz) window.heatViz();
};
window.heatInit();
"""
