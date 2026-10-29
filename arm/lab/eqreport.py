"""個股報告與產業報告的格式、估值重算、檢查（docs/lab_equity_report_plan.md 第 4、6、9 節）。

報告檔＝`reports/eq/{tw|us}/{代號}/{報告日}.md`：開頭 `---` 包住的欄位（一行一個「名稱: 值」，值是 JSON 就照 JSON 讀），
後面是固定的 `## 段落`。撰寫者只寫文字；圖表、表格、評等框、方法、免責聲明由頁面程式依資料包放進去。
產業報告＝`reports/eq/ind/{產業代號}/{日期}.md`，段落見 IND_SECTIONS。
"""
from __future__ import annotations

import json
import re
from datetime import date

from . import eqspec as S

SECTIONS = ("重點", "投資論點", "風險", "公司概況", "產業與競爭", "財務分析", "同業比較", "估值", "催化劑與籌碼",
            "為什麼被選上", "資料來源")
IND_SECTIONS = ("重點", "產業定義與產業鏈", "市場規模與成長", "供需與價格", "主要廠商", "台灣成員營收與估值",
                "接下來要看的", "風險", "資料來源")
FM_REQ = ("code", "name", "mk", "made", "asof", "title", "rating", "tp", "method", "mult", "peers", "ind")
IND_FM_REQ = ("key", "name", "mk", "made", "asof", "title")
PROSE_MIN, PROSE_MAX = 6000, 14000
IND_PROSE_MIN, IND_PROSE_MAX = 3000, 9000
SRC_MIN, IND_SRC_MIN = 8, 6
OFFICIAL = re.compile(r"mops\.twse|twse\.com\.tw|tpex\.org\.tw|sec\.gov|法說|年報|財報|公開資訊觀測站|投資人關係|IR|股東會")
PROCESS = re.compile(r"資料包|落檔|\.json|eqfacts|eqspec|x9t|x9f|icchain|依內規|查證過程|未取得兩個|本文一律不列")
FILLER = re.compile(r"值得注意的是|值得一提的是|整體而言|整體來看|換言之|可以說是|綜上所述|總的來說|不容小覷|蓄勢待發|不言而喻")
NUM = re.compile(r"(約\s*)?([-+−]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[-+−]?\d+(?:\.\d+)?)\s*"
                 r"(個百分點|%|億元|億|萬元|萬張|萬|美元|元|倍|張|位|家)")
LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
ISO = re.compile(r"(20\d\d-\d\d-\d\d)")


# ── 解析 ─────────────────────────────────────────────────────────────────

def parse(text: str) -> dict:
    """→ {"fm": {...}, "sec": {段名: 內文}, "order": [段名…]}。"""
    fm: dict = {}
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            for line in text[3:end].strip().splitlines():
                if ":" not in line or line.strip().startswith("#"):
                    continue
                k, v = line.split(":", 1)
                v = v.strip()
                try:
                    fm[k.strip()] = json.loads(v) if v and v[0] in '[{"0123456789-' else v
                except ValueError:
                    fm[k.strip()] = v
            body = text[end + 4:]
    sec: dict = {}
    order = []
    cur = None
    for line in body.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m and not line.startswith("###"):
            cur = m.group(1)
            sec[cur] = []
            order.append(cur)
        elif cur is not None:
            sec[cur].append(line)
    return {"fm": fm, "sec": {k: "\n".join(v).strip() for k, v in sec.items()}, "order": order}


def paragraphs(text: str) -> list[str]:
    """段落＝空行分開的區塊；條列每一項自成一段（數字要附來源時以「那一段」為單位）。"""
    out, buf = [], []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            if buf:
                out.append(" ".join(buf))
                buf = []
            continue
        if re.match(r"^([-*■]|\d+\.)\s", s) or s.startswith("###"):
            if buf:
                out.append(" ".join(buf))
            buf = [s]
        else:
            buf.append(s)
    if buf:
        out.append(" ".join(buf))
    return out


def prose_len(p: dict, skip=("資料來源",)) -> int:
    t = "".join(v for k, v in p["sec"].items() if k not in skip)
    t = LINK.sub(lambda m: m.group(1), t)
    return len(re.sub(r"[\s#*■\-]", "", t))


# ── 估值（頁面與檢查共用） ────────────────────────────────────────────────

def valuation(pack: dict, fm: dict) -> dict:
    """撰寫者選的倍數 → 目標價、評等、上檔空間、和共識比、情境。"""
    v = pack.get("val") or {}
    px = v.get("px")
    mk = pack.get("mk", "tw")
    base = v.get("base")
    mult = fm.get("mult")
    out = {"method": v.get("method"), "px": px, "base": base, "range": v.get("range"), "dflt": (v.get("range") or {}).get("dflt"),
           "mult": mult, "tp_dflt": v.get("tp_dflt"), "rating_dflt": v.get("rating_dflt")}
    if v.get("method") not in ("pe", "pb") or not base or mult is None:
        out.update({"tp": None, "rating": "暫不評等"})
        return out
    tp = S.round_tp(base * float(mult), mk)
    out["tp"] = tp
    out["rating"] = S.rating(tp, px)
    out["up"] = round((tp / px - 1) * 100, 1) if px else None
    ct = ((pack.get("cons") or {}).get("tp") or {}).get("v")
    out["vs_cons"] = round((tp / ct - 1) * 100, 1) if ct else None
    out["cons_tp"] = ct
    rng = v.get("range")
    out["scen"] = S.scenarios(base, rng, tp, mk, pe=v.get("method") == "pe")
    if out["scen"] and px:
        out["scen_up"] = {k: round((x / px - 1) * 100, 1) for k, x in out["scen"].items()}
    f12 = (v.get("f12m") or {}).get("eps")
    if v.get("method") == "pe" and f12:
        out["tp_pe"] = round(tp / f12, 1)
    return out


def derived_numbers(pack: dict, fm: dict) -> set[float]:
    val = valuation(pack, fm)
    out: set[float] = set()

    def walk(x):
        if isinstance(x, bool) or x is None:
            return
        if isinstance(x, (int, float)):
            out.add(float(x))
        elif isinstance(x, dict):
            for y in x.values():
                walk(y)
        elif isinstance(x, (list, tuple)):
            for y in x:
                walk(y)
    walk(val)
    for k in ("mult",):
        if fm.get(k) is not None:
            out.add(float(fm[k]))
    return out


# ── 數字比對 ─────────────────────────────────────────────────────────────

class NumSet:
    """資料包的數字，依小數位數先四捨五入好（取絕對值）；「約」容許 3%。"""

    def __init__(self, nums: set[float]):
        self.raw = sorted(abs(x) for x in nums)
        self.r = {k: {round(abs(x), k) for x in nums} for k in range(0, 4)}

    def has(self, v: float, dec: int, approx: bool = False) -> bool:
        v = abs(v)
        if round(v, min(dec, 3)) in self.r[min(dec, 3)]:
            return True
        if approx:
            return any(abs(x - v) <= 0.03 * max(v, 1e-9) for x in self.raw)
        return False

    def has_diff(self, v: float, dec: int) -> bool:
        """個百分點：兩個數字相減（四捨五入到同樣位數後相等）。"""
        import bisect
        v = abs(v)
        h = 0.5 * 10 ** -dec + 1e-9
        xs = [x for x in self.raw if x <= 1000]
        for a in xs:
            lo, hi = a - v - h, a - v + h
            j = bisect.bisect_left(xs, lo)
            if j < len(xs) and xs[j] <= hi:
                return True
        return False


def number_issues(p: dict, nums: set[float], skip=("資料來源",)) -> list[str]:
    ns = NumSet(nums)
    bad = []
    for name, text in p["sec"].items():
        if name in skip:
            continue
        for para in paragraphs(text):
            if LINK.search(para):
                continue                                      # 同一段有來源連結＝網路查到的數字
            for m in NUM.finditer(para):
                raw = m.group(2).replace(",", "").replace("−", "-").replace("+", "")
                try:
                    v = float(raw)
                except ValueError:
                    continue
                dec = len(raw.split(".")[1]) if "." in raw else 0
                unit = m.group(3)
                if unit == "個百分點":
                    ok = ns.has(v, dec) or ns.has_diff(v, dec)
                else:
                    ok = ns.has(v, dec, approx=bool(m.group(1)))
                if not ok:
                    bad.append(f"{name}：{m.group(0).strip()}（資料包沒有這個數字，同一段也沒有來源連結）")
    return bad


# ── 檢查 ─────────────────────────────────────────────────────────────────

def _banned(text: str) -> list[str]:
    from .. import usnews
    return [w for w in usnews.compliance_scan(text) if w != "目標價"]


def _common(p: dict, sections: tuple, req: tuple, src_min: int, pmin: int, pmax: int) -> list[str]:
    errs = []
    fm = p["fm"]
    miss = [k for k in req if fm.get(k) in (None, "", [])]
    if miss:
        errs.append(f"開頭欄位缺：{'、'.join(miss)}")
    lack = [s for s in sections if not p["sec"].get(s)]
    if lack:
        errs.append(f"段落缺或是空的：{'、'.join(lack)}")
    extra = [s for s in p["order"] if s not in sections]
    if extra:
        errs.append(f"多了不認得的段落：{'、'.join(extra)}")
    allt = "\n".join(p["sec"].values())
    b = _banned(allt + " " + str(fm.get("title", "")))
    if b:
        errs.append(f"禁用詞：{'、'.join(b)}")
    m = PROCESS.search("\n".join(v for k, v in p["sec"].items() if k != "資料來源"))     # 資料侷限只准寫在資料來源段
    if m:
        errs.append(f"正文出現查證過程或檔名：「{m.group(0)}」")
    m = FILLER.search(allt)
    if m:
        errs.append(f"填充語：「{m.group(0)}」")
    if allt.count("——") > 3:
        errs.append(f"破折號用太多（{allt.count('——')} 個，最多 3 個）")
    links = LINK.findall(p["sec"].get("資料來源", ""))
    if len(links) < src_min:
        errs.append(f"資料來源連結只有 {len(links)} 條（至少 {src_min} 條）")
    if links and not any(OFFICIAL.search(t + " " + u) for t, u in links):
        errs.append("資料來源沒有公司官方文件（公開資訊觀測站、法說會、年報、財報、IR、SEC）")
    n = prose_len(p)
    if not pmin <= n <= pmax:
        errs.append(f"正文 {n:,} 字（要 {pmin:,}～{pmax:,} 字）")
    made = fm.get("made")
    try:
        date.fromisoformat(str(made))
    except ValueError:
        errs.append(f"報告日格式不對：{made}")
    return errs


def check(text: str, pack: dict) -> list[str]:
    """個股報告 → 錯誤清單（空＝🟢）。"""
    p = parse(text)
    fm = p["fm"]
    errs = _common(p, SECTIONS, FM_REQ, SRC_MIN, PROSE_MIN, PROSE_MAX)
    if str(fm.get("code")) != str(pack.get("code")):
        errs.append(f"代號和資料包不同：{fm.get('code')} vs {pack.get('code')}")
    if fm.get("asof") != pack.get("asof"):
        errs.append(f"資料日和資料包不同：{fm.get('asof')} vs {pack.get('asof')}")
    if len(str(fm.get("title", ""))) > 40:
        errs.append("標題超過 40 字")
    hl = [ln for ln in p["sec"].get("重點", "").splitlines() if ln.strip().startswith("■")]
    if not 3 <= len(hl) <= 4:
        errs.append(f"重點要 3～4 條（■ 開頭），現在 {len(hl)} 條")
    th = re.split(r"^###\s+", p["sec"].get("投資論點", ""), flags=re.M)[1:]
    if len(th) != 3:
        errs.append(f"投資論點要 3 個（### 小標），現在 {len(th)} 個")
    elif any(len(re.sub(r"\s", "", t)) < 250 for t in th):
        errs.append("每個論點至少 250 字")
    rk = [ln for ln in p["sec"].get("風險", "").splitlines() if re.match(r"^\s*-\s", ln)]
    if not 4 <= len(rk) <= 6:
        errs.append(f"風險要 4～6 條，現在 {len(rk)} 條")
    elif any("觀察" not in r for r in rk):
        errs.append("每條風險都要寫「觀察：」看什麼數字或事件")
    made = str(fm.get("made"))
    cats = [m.group(1) for ln in p["sec"].get("催化劑與籌碼", "").splitlines()
            if re.match(r"^\s*-\s", ln) for m in [ISO.search(ln)] if m]
    if len(cats) < 3:
        errs.append(f"催化劑要至少 3 個有日期（YYYY-MM-DD）的項目，現在 {len(cats)} 個")
    elif any(c < made for c in cats):
        errs.append(f"催化劑日期早於報告日：{[c for c in cats if c < made]}")
    # 估值
    val = valuation(pack, fm)
    v = pack.get("val") or {}
    if fm.get("method") != v.get("method"):
        errs.append(f"方法要照規則：{v.get('method')}（報告寫 {fm.get('method')}）")
    rng = v.get("range") or {}
    mult = fm.get("mult")
    if v.get("method") in ("pe", "pb"):
        if not isinstance(mult, (int, float)):
            errs.append("倍數不是數字")
        else:
            if not rng.get("lo", 0) - 0.005 <= mult <= rng.get("hi", 0) + 0.005:
                errs.append(f"倍數 {mult} 不在可用範圍 {rng.get('lo')}～{rng.get('hi')}")
            if abs(mult - (rng.get("dflt") or mult)) > 0.05 and len(str(fm.get("mult_why", ""))) < 20:
                errs.append(f"倍數和預設 {rng.get('dflt')} 不同，要寫 mult_why（至少 20 字）")
        if fm.get("tp") != val.get("tp"):
            errs.append(f"目標價要等於 {val.get('tp')}（{v.get('base')} × {mult} 進位）")
    if fm.get("rating") != val.get("rating"):
        errs.append(f"評等要照門檻：{val.get('rating')}（報告寫 {fm.get('rating')}）")
    pk = [p_["c"] for p_ in pack.get("peers") or []]
    if [str(x) for x in fm.get("peers") or []] != pk:
        errs.append(f"同業要和資料包一致：{pk}")
    if pk != (pack.get("peers_auto") or pk) and len(str(fm.get("peers_why", ""))) < 20:
        errs.append("換過同業，要寫 peers_why（至少 20 字）")
    from .eqfacts import numbers
    errs += number_issues(p, numbers(pack) | derived_numbers(pack, fm))
    return errs


def check_ind(text: str, ipack: dict) -> list[str]:
    p = parse(text)
    errs = _common(p, IND_SECTIONS, IND_FM_REQ, IND_SRC_MIN, IND_PROSE_MIN, IND_PROSE_MAX)
    if p["fm"].get("key") != ipack.get("key"):
        errs.append(f"產業代號和資料包不同：{p['fm'].get('key')} vs {ipack.get('key')}")
    hl = [ln for ln in p["sec"].get("重點", "").splitlines() if ln.strip().startswith("■")]
    if not 3 <= len(hl) <= 4:
        errs.append(f"重點要 3～4 條（■ 開頭），現在 {len(hl)} 條")
    from .eqfacts import numbers
    errs += number_issues(p, numbers(ipack))
    return errs
