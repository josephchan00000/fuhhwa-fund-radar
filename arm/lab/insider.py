"""成分股內部人買賣（景氣頁美股版 heatspec_us VER 3 的 S7；docs/lab_us_chip_plan.md 第 7、8 節）。

只在 CI 抓（本容器的 proxy 擋 sec.gov）。SEC 要求 User-Agent 帶聯絡 email：只從環境變數 SEC_CONTACT_EMAIL 讀
（secfin.contact），程式、日誌、存檔都不出現；沒有設就整段跳過。

來源：
  SEC 內部人每季資料集（Form 3／4／5，2006q1 起）：網址從資料集頁讀（兩種路徑混用），
      SUBMISSION（申報日、文件類型、發行人 CIK 與代號）、REPORTINGOWNER（身分）、NONDERIV_TRANS（交易代碼、股數）
  EDGAR 每日索引的 Form 4 原件：最新一季資料集還沒涵蓋的日子
  成分股：S&P 500 歷史成分股期間（fja05680，代號是當時的代號）、現在的那斯達克 100 與費半成分股
      （fwdfetch.constituents，代號經 company_tickers.json 換成 CIK）、SEC 產業代碼 3674 的公司（EDGAR 公司查詢）

只留：Form 4（不含 4/A）、非衍生性交易、交易代碼 P（公開市場買進）與 S（公開市場賣出）、申報人之一是董事或經理人。
同一天同一家公司加總成「P 股數 − S 股數」。只存三個名單裡的公司（申報日當時在 S&P 500 裡，或 CIK 在
那斯達克 100、半導體名單裡）——那斯達克 100 之後新加入、又不在另外兩個名單的公司，加入之前的申報沒有存。

存檔：
  data/lab/ins/{YYYY-MM}.json.gz（依申報日）：{"d": {申報日: {CIK: [淨股數, 申報日當時在 S&P 500 是 1 否則 0]}}}
  data/lab/heat/ins_members.json.gz（heatdata）：{"spx": [[代號, 起日, 迄日], ...], "ndx": [CIK…], "semi": [CIK…],
                                                  "asof": 抓的日期}
  data/lab/heat/ins_state.json.gz（heatdata）：{"q": [做完的季], "days": [做完的每日索引日期], "through": 涵蓋到哪天}
"""
from __future__ import annotations

import csv
import io
import json
import re
import threading
import time
import urllib.error
import urllib.request
import zipfile
from bisect import bisect_right
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from . import heatdata as HD
from . import heatspec_us as HU
from . import secfin as SF
from . import store

KIND = "ins"
MEMBERS = "ins_members"
STATE = "ins_state"
DS_PAGE = "https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets"
DAILY_IDX = "https://www.sec.gov/Archives/edgar/daily-index/{y}/QTR{q}/form.{ymd}.idx"
ARCHIVE = "https://www.sec.gov/Archives/"
SIC_URL = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&SIC={sic}&type=&dateb=&owner=include"
           "&start={start}&count=100&output=atom")
RATE = 8.0                                     # SEC 上限每秒 10 個請求；這裡最多 8 個
MON = {m: i for i, m in enumerate(("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), 1)}


def log(*a) -> None:
    print("[ins]", *a, flush=True)


def norm(sym: str | None) -> str:
    """代號只留英數字（BRK.B、BRK-B、BRKB 都是 BRKB）。"""
    return re.sub(r"[^A-Z0-9]", "", (sym or "").upper())


# ── 名單 ───────────────────────────────────────────────────────────────────────

class Spans:
    """S&P 500 成分股期間：in_spx(代號, 日期)＝那天在指數裡（起日當天算、迄日當天不算）。"""

    def __init__(self, rows: list):
        self.by: dict[str, list[tuple[str, str | None]]] = {}
        for sym, a, z in rows or []:
            self.by.setdefault(norm(sym), []).append((a, z))

    def __call__(self, sym: str | None, d: str) -> bool:
        return any(a <= d and (z is None or d < z) for a, z in self.by.get(norm(sym), ()))


def load_members() -> dict:
    return HD.load(MEMBERS)


def group_ciks(M: dict) -> dict[str, set[int]]:
    return {"ndx": {int(c) for c in M.get("ndx") or []}, "semi": {int(c) for c in M.get("semi") or []}}


# ── 解析（不碰網路；tests/test_insider.py 用探針看到的格式測） ─────────────────────────

def iso_date(s: str) -> str | None:
    """資料集的日期：31-MAR-2006 → 2006-03-31；也收 2006-03-31。"""
    s = (s or "").strip()
    m = re.match(r"^(\d{1,2})-([A-Za-z]{3})-(\d{4})$", s)
    if m and m.group(2).upper() in MON:
        return f"{m.group(3)}-{MON[m.group(2).upper()]:02d}-{int(m.group(1)):02d}"
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    return m.group(0) if m else None


def _tsv(z: zipfile.ZipFile, prefix: str):
    name = next((n for n in z.namelist() if n.upper().startswith(prefix)), None)
    if not name:
        raise ValueError(f"壓縮檔裡沒有 {prefix}")
    with z.open(name) as f:
        rd = csv.reader(io.TextIOWrapper(f, encoding="utf-8", errors="replace", newline=""),
                        delimiter="\t", quoting=csv.QUOTE_NONE)
        head = next(rd)
        ix = {h.strip(): i for i, h in enumerate(head)}
        for r in rd:
            yield ix, r


def _col(r: list, ix: dict, k: str) -> str:
    i = ix.get(k)
    return r[i].strip() if i is not None and i < len(r) else ""


def is_do(rel: str) -> bool:
    return bool(re.search(r"director|officer", rel or "", re.I))


def _num(x: str) -> float | None:
    try:
        return float(str(x).replace(",", "").strip())
    except ValueError:
        return None


def parse_dataset(zb: bytes) -> dict[str, tuple[str, int, str, float]]:
    """一季資料集 → {accession: (申報日, 發行人 CIK, 發行人代號, P 股數 − S 股數)}（只留合格的 Form 4）。"""
    z = zipfile.ZipFile(io.BytesIO(zb))
    sub: dict[str, tuple[str, int, str]] = {}
    for ix, r in _tsv(z, "SUBMISSION"):
        if _col(r, ix, "DOCUMENT_TYPE") != "4":
            continue
        d, c = iso_date(_col(r, ix, "FILING_DATE")), _col(r, ix, "ISSUERCIK")
        if d and c.isdigit():
            sub[_col(r, ix, "ACCESSION_NUMBER")] = (d, int(c), _col(r, ix, "ISSUERTRADINGSYMBOL"))
    do = set()
    for ix, r in _tsv(z, "REPORTINGOWNER"):
        a = _col(r, ix, "ACCESSION_NUMBER")
        if a in sub and is_do(_col(r, ix, "RPTOWNER_RELATIONSHIP")):
            do.add(a)
    net: dict[str, float] = {}
    for ix, r in _tsv(z, "NONDERIV_TRANS"):
        a = _col(r, ix, "ACCESSION_NUMBER")
        if a not in do:
            continue
        code = _col(r, ix, "TRANS_CODE")
        if code not in (HU.INS_CODES["buy"], HU.INS_CODES["sell"]):
            continue
        n = _num(_col(r, ix, "TRANS_SHARES"))
        if n is None:
            continue
        net[a] = net.get(a, 0.0) + (n if code == HU.INS_CODES["buy"] else -n)
    return {a: (*sub[a], v) for a, v in net.items()}


def _tag(txt: str, tag: str) -> str | None:
    m = re.search(rf"<{tag}>\s*(?:<value>)?\s*([^<]*?)\s*(?:</value>\s*)?</{tag}>", txt, re.S)
    return m.group(1).strip() if m else None


def parse_form4(txt: str) -> tuple[int, str, float] | None:
    """Form 4 原件（完整申報 .txt，內含 XML）→（發行人 CIK, 代號, P 股數 − S 股數）；不合格回 None。"""
    m = re.search(r"<ownershipDocument>(.*?)</ownershipDocument>", txt, re.S)
    if not m:
        return None
    x = m.group(1)
    if (_tag(x, "documentType") or "") != "4":
        return None
    c = _tag(x, "issuerCik") or ""
    if not c.isdigit():
        return None
    rel = " ".join(re.findall(r"<reportingOwnerRelationship>(.*?)</reportingOwnerRelationship>", x, re.S))
    if not re.search(r"<is(?:Director|Officer)>\s*(?:1|true)\s*</is(?:Director|Officer)>", rel, re.I):
        return None                                           # 申報人之一是董事或經理人才算
    net, hit = 0.0, False
    for t in re.findall(r"<nonDerivativeTransaction>(.*?)</nonDerivativeTransaction>", x, re.S):
        code = _tag(t, "transactionCode")
        if code not in (HU.INS_CODES["buy"], HU.INS_CODES["sell"]):
            continue
        sh = re.search(r"<transactionShares>\s*<value>\s*([^<]+?)\s*</value>", t, re.S)
        n = _num(sh.group(1)) if sh else None
        if n is None:
            continue
        hit = True
        net += n if code == HU.INS_CODES["buy"] else -n
    if not hit:
        return None
    return int(c), _tag(x, "issuerTradingSymbol") or "", net


def parse_index(txt: str) -> list[tuple[int, str]]:
    """每日 form 索引 → [(該行的 CIK, 檔案路徑)]（只留表單「4」；同一份申報會在發行人與申報人各列一次）。"""
    out = []
    for ln in txt.splitlines():
        if not ln.startswith("4 "):
            continue
        parts = ln.split()
        m = re.search(r"(edgar/data/(\d+)/[\d-]+\.txt)$", ln.strip())
        if m and len(parts) >= 4:
            cik = parts[-3]
            out.append((int(cik) if cik.isdigit() else int(m.group(2)), m.group(1)))
    return out


def no_index(status: int, body: bytes) -> bool:
    """每日索引不存在：EDGAR 的檔案庫對不存在的檔回 403（AccessDenied）或 404；SEC 擋太快的請求也回 403，
    但內容寫 Request Rate Threshold Exceeded——那種不算（下次再試）。"""
    return status in (403, 404) and b"Rate Threshold" not in (body or b"")


def parse_sic(txt: str) -> list[int]:
    return [int(c) for c in re.findall(r"<cik>(\d+)</cik>", txt)]


def keep(cik: int, sym: str, d: str, spans: Spans, G: dict[str, set[int]]) -> int | None:
    """存不存：申報日當時在 S&P 500 裡 → 1；CIK 在那斯達克 100 或半導體名單 → 0；都不是 → None。"""
    if spans(sym, d):
        return 1
    if cik in G["ndx"] or cik in G["semi"]:
        return 0
    return None


def to_shards(rows, spans: Spans, G: dict[str, set[int]]) -> dict[str, dict[str, dict[str, list]]]:
    """[(申報日, CIK, 代號, 淨股數), ...] → {月: {申報日: {CIK: [淨股數, 在 S&P 500]}}}（同一天同一家加總）。"""
    out: dict[str, dict[str, dict[str, list]]] = {}
    for d, cik, sym, n in rows:
        f = keep(cik, sym, d, spans, G)
        if f is None:
            continue
        day = out.setdefault(d[:7], {}).setdefault(d, {})
        k = str(cik)
        if k in day:
            day[k] = [day[k][0] + n, max(day[k][1], f)]
        else:
            day[k] = [n, f]
    for m in out.values():
        for day in m.values():
            for k in list(day):
                day[k] = [round(day[k][0]), day[k][1]]
    return out


# ── 存檔 ───────────────────────────────────────────────────────────────────────

def months() -> list[str]:
    return [m for m in store.dates(KIND) if re.match(r"^\d{4}-\d{2}$", m)]


def load_month(m: str) -> dict:
    return (store.read(KIND, m) or {}).get("d") or {}


def save_month(m: str, d: dict) -> bool:
    return store.write(KIND, m, {"d": dict(sorted(d.items()))})


def load_all() -> dict[str, dict[str, list]]:
    out: dict[str, dict[str, list]] = {}
    for m in months():
        out.update(load_month(m))
    return out


def state() -> dict:
    return HD.load(STATE) or {}


def save_state(st: dict) -> None:
    HD.save(STATE, "sec", {"q": sorted(set(st.get("q") or [])), "days": sorted(set(st.get("days") or []))[-400:],
                           "through": st.get("through")})


def q_end(q: str) -> str:
    y, n = int(q[:4]), int(q[5])
    return (date(y + (n == 4), 1 if n == 4 else 3 * n + 1, 1) - timedelta(days=1)).isoformat()


def through(st: dict) -> str | None:
    """申報涵蓋到哪一天：最新做完的季底，加上之後連續做完的每日索引（平日）。"""
    qs = sorted(st.get("q") or [])
    if not qs:
        return None
    t = date.fromisoformat(q_end(qs[-1]))
    done = set(st.get("days") or [])
    d = t + timedelta(days=1)
    while d.weekday() >= 5 or d.isoformat() in done:
        if d.weekday() < 5:
            t = d
        d += timedelta(days=1)
        if d > date.today():
            break
    return t.isoformat()


# ── 抓取（只在 CI） ───────────────────────────────────────────────────────────

class Client:
    def __init__(self, email: str):
        self.ua = SF._ua(email)
        self.lock = threading.Lock()
        self.t = 0.0

    def get(self, url: str, timeout: int = 120) -> tuple[int, bytes]:
        from ..http import _CTX
        with self.lock:                                       # 全部執行緒合起來每秒最多 RATE 個請求
            w = self.t + 1.0 / RATE - time.time()
            if w > 0:
                time.sleep(w)
            self.t = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": self.ua, "Accept": "*/*"})
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            try:
                return e.code, e.read()[:2000]
            except Exception:                                 # noqa: BLE001
                return e.code, b""


def update_members(C: Client) -> dict:
    """名單：S&P 500 歷史期間、現在的那斯達克 100、半導體（產業代碼 3674 ∪ 現在的費半）。抓不到的部分沿用舊的。"""
    from . import fwdfetch as F
    from . import usbreadth as UB
    old = load_members()
    out = dict(old)
    try:
        sp = UB.parse_spans(F._get(UB.SPANS_URL, timeout=60).decode("utf-8"))
        if len(sp) >= 1000:
            out["spx"] = [list(r) for r in sp]
    except Exception as e:                                    # noqa: BLE001
        log("S&P 500 期間 ✗", type(e).__name__, str(e)[:120])
    st, b = C.get(SF.TICKERS_URL, timeout=60)
    tick = SF.ticker_map(json.loads(b.decode("utf-8"))) if st == 200 and b else {}
    cons = F.constituents(date.today().isoformat())
    if tick and len(cons.get("ndx") or []) >= 90:
        ndx = sorted({tick[s] for s in cons["ndx"] if s in tick})
        if len(ndx) >= 80:
            out["ndx"] = ndx
    sic: list[int] = []
    for start in range(0, 3000, 100):
        st, b = C.get(SIC_URL.format(sic=HU.INS_SIC, start=start), timeout=60)
        cs = parse_sic(b.decode("utf-8", "replace")) if st == 200 else []
        sic += cs
        if len(cs) < 100:
            break
    sox = {tick[s] for s in cons.get("sox") or [] if s in tick} if tick else set()
    if len(sic) >= 300:
        out["semi"] = sorted(set(sic) | sox)
    out["asof"] = date.today().isoformat()
    if out != old:
        HD.save(MEMBERS, "sec", out)
    log(f"名單：S&P 500 期間 {len(out.get('spx') or [])}、那斯達克 100 {len(out.get('ndx') or [])}、"
        f"半導體 {len(out.get('semi') or [])}（產業代碼 3674 {len(set(sic))}、費半 {len(sox)}）")
    return out


def dataset_links(C: Client) -> dict[str, str]:
    st, b = C.get(DS_PAGE, timeout=60)
    if st != 200:
        raise RuntimeError(f"資料集頁 HTTP {st}")
    out = {}
    for u in re.findall(r'href="([^"]*?(\d{4}q[1-4])_form345\.zip)"', b.decode("utf-8", "replace")):
        out[u[1]] = u[0] if u[0].startswith("http") else "https://www.sec.gov" + u[0]
    return out


def write_rows(rows, M: dict, replace_months: set[str] | None = None) -> int:
    """寫進月分片。replace_months 裡的月份整個換掉（季資料集是那幾個月的完整資料），其他月份逐日覆蓋。"""
    spans, G = Spans(M.get("spx")), group_ciks(M)
    sh = to_shards(rows, spans, G)
    n = 0
    for m in sorted(set(sh) | (replace_months or set())):
        new = sh.get(m, {})
        cur = {} if m in (replace_months or set()) else load_month(m)
        cur.update(new)
        n += save_month(m, cur)
    return n


def do_quarters(C: Client, M: dict, st: dict, budget_s: float) -> None:
    t0 = time.time()
    links = dataset_links(C)
    log(f"資料集 {len(links)} 季（{min(links) if links else '-'}～{max(links) if links else '-'}）")
    done = set(st.get("q") or [])
    for q in sorted(links):
        if q in done or q < HU.INS_SINCE[:4] + "q1":
            continue
        if time.time() - t0 > budget_s:
            log("時間到，下次續做季資料集")
            break
        s, b = C.get(links[q], timeout=300)
        if s != 200 or b[:2] != b"PK":
            log(f"{q} HTTP {s}，跳過")
            continue
        acc = parse_dataset(b)
        y, k = int(q[:4]), int(q[5])
        ms = {f"{y}-{3 * (k - 1) + j:02d}" for j in (1, 2, 3)}
        rows = [v for v in acc.values() if v[0][:7] in ms]
        n = write_rows(rows, M, replace_months=ms)
        st.setdefault("q", []).append(q)
        save_state(st)
        log(f"{q}：合格的 Form 4 {len(acc)} 份、寫了 {n} 個月分片（{time.time() - t0:.0f}s）")


def do_days(C: Client, M: dict, st: dict, budget_s: float, workers: int = 4) -> None:
    """最新一季資料集之後的日子：每日索引的 Form 4，只抓名單裡的發行人（索引那一行的 CIK）。"""
    qs = sorted(st.get("q") or [])
    if not qs:
        log("季資料集還沒做，先不做每日索引")
        return
    t0 = time.time()
    spans, G = Spans(M.get("spx")), group_ciks(M)
    st2, b = C.get(SF.TICKERS_URL, timeout=60)
    if st2 != 200 or not b:
        log(f"company_tickers.json HTTP {st2}，這次不做每日索引")
        return
    tick = SF.ticker_map(json.loads(b.decode("utf-8")))
    done = set(st.get("days") or [])
    d = date.fromisoformat(q_end(qs[-1])) + timedelta(days=1)
    d0, today = d.isoformat(), date.today().isoformat()       # 每日索引那一行只有 CIK：用這段期間頭尾在 S&P 500 裡的公司
    tick_ok: set[int] = set(G["ndx"]) | set(G["semi"]) | {c for s, c in tick.items() if spans(s, d0) or spans(s, today)}
    last = date.today() - timedelta(days=1)                   # 今天的索引晚上才有
    while d <= last:
        ds = d.isoformat()
        if d.weekday() >= 5 or ds in done:
            d += timedelta(days=1)
            continue
        if time.time() - t0 > budget_s:
            log("時間到，下次續做每日索引")
            break
        s, b = C.get(DAILY_IDX.format(y=d.year, q=(d.month - 1) // 3 + 1, ymd=d.strftime("%Y%m%d")), timeout=120)
        if no_index(s, b) and d <= date.today() - timedelta(days=3):
            st.setdefault("days", []).append(ds)                # SEC 休息日（聯邦假日，例 10/12 哥倫布日）沒有索引
            d += timedelta(days=1)
            continue
        if s != 200:
            log(f"{ds} 索引 HTTP {s}，下次再試")
            break
        by_acc: dict[str, str] = {}                           # 同一份申報在發行人與申報人底下各列一次：依申報編號去重
        for c, p in parse_index(b.decode("latin-1")):
            if c in tick_ok:
                by_acc.setdefault(p.rsplit("/", 1)[-1], p)
        paths = sorted(by_acc.values())

        def one(p: str):
            s2, b2 = C.get(ARCHIVE + p, timeout=120)
            return parse_form4(b2.decode("utf-8", "replace")) if s2 == 200 else ("err", s2)

        with ThreadPoolExecutor(max_workers=workers) as ex:
            got = list(ex.map(one, paths))
        errs = [g for g in got if isinstance(g, tuple) and g and g[0] == "err"]
        if errs:
            log(f"{ds}：{len(errs)}／{len(paths)} 份抓不到，下次再試")
            break
        rows = [(ds, c, sym, n) for c, sym, n in (g for g in got if g)]
        cur = load_month(ds[:7])
        sh = to_shards(rows, spans, G).get(ds[:7], {})
        cur[ds] = sh.get(ds, {})
        save_month(ds[:7], cur)
        st.setdefault("days", []).append(ds)
        save_state(st)
        log(f"{ds}：名單裡的 Form 4 {len(paths)} 份、合格 {len(cur[ds])} 家（{time.time() - t0:.0f}s）")
        d += timedelta(days=1)


def run(budget_s: float = 150.0, members: bool | None = None) -> dict:
    """抓一輪：名單（7 天更新一次，或沒有時）→ 季資料集 → 每日索引。沒有設 SEC_CONTACT_EMAIL＝跳過。"""
    email = SF.contact()
    if not email:
        log("沒有 SEC_CONTACT_EMAIL，跳過")
        return {}
    C = Client(email)
    t0 = time.time()
    M = load_members()
    if members or members is None and (not M or (M.get("asof") or "") <= (date.today() - timedelta(days=7)).isoformat()):
        M = update_members(C)
    if not (M.get("spx") and M.get("ndx") and M.get("semi")):
        log("名單不齊，這次不抓")
        return {}
    st = state()
    do_quarters(C, M, st, budget_s)
    do_days(C, M, st, max(0.0, budget_s - (time.time() - t0)))
    st["through"] = through(st)
    save_state(st)
    log(f"涵蓋到 {st['through']}（{time.time() - t0:.0f}s）")
    return st


# ── 算 S7（不碰網路） ─────────────────────────────────────────────────────────

def ratio_series(cal: list[str], group: str, D: dict | None = None, M: dict | None = None,
                 st: dict | None = None) -> dict[str, float]:
    """S7：每個交易日 t，申報日在 t 之前、最近 INS_DAYS 個交易日內的申報（申報日隔天才算拿得到），
    名單裡每家公司加總淨股數；淨買的公司占（淨買＋淨賣）的百分比。家數少於 INS_MIN 或申報還沒涵蓋到前一個交易日＝沒有值。"""
    D = load_all() if D is None else D
    M = load_members() if M is None else M
    st = state() if st is None else st
    thr = st.get("through") or through(st)
    if not cal or not D or not thr:
        return {}
    ciks = set(str(c) for c in group_ciks(M).get(group, set()))
    by_i: dict[int, dict[str, float]] = {}
    for d, day in D.items():
        i = bisect_right(cal, d)                             # 申報日之後的第一個交易日才算拿得到
        if i >= len(cal):
            continue
        for c, (n, f) in day.items():
            if (group == "spx" and f) or (group != "spx" and c in ciks):
                if n:
                    tgt = by_i.setdefault(i, {})
                    tgt[c] = tgt.get(c, 0.0) + n
    W, need = HU.INS_DAYS, HU.INS_MIN[group]
    acc: dict[str, float] = {}
    out = {}
    for i, t in enumerate(cal):
        for c, n in (by_i.get(i) or {}).items():
            acc[c] = acc.get(c, 0.0) + n
        j = i - W
        if j >= 0:
            for c, n in (by_i.get(j) or {}).items():
                v = acc.get(c, 0.0) - n
                if abs(v) < 0.5:
                    acc.pop(c, None)
                else:
                    acc[c] = v
        if i == 0 or cal[i - 1] > thr:
            continue
        pos = sum(1 for v in acc.values() if v > 0)
        neg = sum(1 for v in acc.values() if v < 0)
        if pos + neg >= need:
            out[t] = 100.0 * pos / (pos + neg)
    return out
