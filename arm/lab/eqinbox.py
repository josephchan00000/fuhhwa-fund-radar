"""個股報告申請的收件匣（docs/lab_eq_request_plan.md 第 3.2 節）：GitHub 申請單 → data/eq_requests.json。

每次跑都從 GitHub 讀開著的申請單重新對帳，不靠事件內容；單上的文字只取「代號」那一欄、用固定格式比對，不放進任何指令。
排程（每天晚上那班）只讀 data/eq_requests.json，不讀單上的文字。
- 看網站的人都能申請（使用者 2026-10-30 選）；站長那邊的單排前面，其餘照申請先後。
- 每個帳號同時最多 PER_USER 件、佇列最多 MAX_QUEUE 件；同一家已在佇列＝回「已經有人申請」並關單。
- 90 天內做過、之後沒有新一季財報＝回現有報告並關單（eqqueue.need）；報告日 ≥ 申請日＝回連結、關單、移到 done。
- 檔案不存帳號名稱（公開 repo）；每個帳號的件數每次從開著的單現算。
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import eqqueue as Q

ROOT = Path(__file__).resolve().parents[2]
FILE = ROOT / "data" / "eq_requests.json"
LABEL = "eq-request"
HEADING = "### 代號"
PER_USER = 2
MAX_QUEUE = 30
DONE_DAYS = 30
OWNER_ROLES = ("OWNER", "MEMBER", "COLLABORATOR")
SITE = "https://fuhhwa-fund-radar.vercel.app"
TW_RE = re.compile(r"^\d{4}$")
US_RE = re.compile(r"^[A-Z]{1,5}(?:[.-][A-Z]{1,2})?$")
TPE = timezone(timedelta(hours=8))


def _read(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def tw_date(iso: str) -> str:
    """GitHub 的時間（UTC，…Z）→ 台北日期。"""
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(TPE).date().isoformat()


def parse(body: str | None) -> tuple[str, str] | None:
    """申請單內容 → (市場, 代號)；看不懂＝None。只看「### 代號」下面第一行的第一段字。"""
    if not body or len(body) > 5000 or HEADING not in body:
        return None
    after = body.split(HEADING, 1)[1].splitlines()
    val = next((ln.strip() for ln in after if ln.strip()), "")
    val = unicodedata.normalize("NFKC", val).split()[0] if val else ""
    if TW_RE.match(val):
        return "tw", val
    up = val.upper()
    if US_RE.match(up):
        return "us", up
    return None


def known(mk: str, code: str, root: Path = ROOT) -> str | None:
    """資料庫裡有這家才收（台股＝選股頁資料庫 dashboard/co；美股＝個股報告資料包做得出來的那幾檔）→ 名稱。"""
    if mk == "tw":
        co = _read(root / "dashboard" / "co" / f"{code}.json", None)
        return (co.get("n") or code) if isinstance(co, dict) else None
    fin = _read(root / "data" / "lab" / "ussx_fin.json", {}) or {}
    card = _read(root / "data" / "lab" / "ussx_card.json", {}) or {}
    if code in (fin.get("s") or {}) and code in (card.get("s") or {}):
        return (fin.get("names") or {}).get(code) or code
    return None


def link(mk: str, code: str) -> str:
    return f"{SITE}/rp/{mk}-{code}"


def is_request(it: dict) -> bool:
    """開著的單裡哪些是申請單：有標籤，或內容有申請單那一欄（標籤還沒建好時開的單）。"""
    if "pull_request" in it:                               # issues API 也會列出 PR
        return False
    labels = {(lb.get("name") if isinstance(lb, dict) else lb) for lb in it.get("labels") or []}
    return LABEL in labels or HEADING in (it.get("body") or "")


def _owner(it: dict) -> bool:
    return (it.get("author_association") or "") in OWNER_ROLES


def reconcile(issues: list[dict], state: dict | None, today: str, now: str, root: Path = ROOT,
              last_report=Q.last_report, need=Q.need) -> tuple[dict, list[tuple]]:
    """開著的申請單＋上一份佇列 → (新佇列, 要做的事 [("comment", 單號, 文字), ("close", 單號, "completed"/"not_planned"), ("label", 單號)])。"""
    state = state or {}
    prev = {int(x["issue"]): x for x in state.get("items") or []}
    done = [x for x in state.get("done") or [] if x.get("made", "") >= _days_before(today, DONE_DAYS)]
    acts: list[tuple] = []
    reqs = sorted((it for it in issues if is_request(it)), key=lambda it: (it.get("created_at") or "", int(it["number"])))
    items: list[dict] = []
    per_user: dict[str, int] = {}

    def close(n: int, text: str, why: str = "not_planned"):
        acts.append(("comment", n, text))
        acts.append(("close", n, why))

    for it in reqs:
        n = int(it["number"])
        labels = {(lb.get("name") if isinstance(lb, dict) else lb) for lb in it.get("labels") or []}
        if LABEL not in labels:
            acts.append(("label", n))
        p = parse(it.get("body"))
        if not p:
            close(n, "看不懂代號。請用網頁上的「要個股報告」開單，或在「代號」填台股 4 碼（例 4958）、美股代號（例 PAYC）。這張單先關掉。")
            continue
        mk, code = p
        name = known(mk, code, root)
        if not name:
            close(n, f"資料庫裡沒有 {code}：台股只收月底市值 40 億以上的上市櫃公司，美股目前只收選股頁上有財報資料的那幾檔。這張單先關掉。")
            continue
        at = prev[n]["at"] if n in prev else tw_date(it.get("created_at") or now)
        lr = last_report(mk, code)
        if lr and lr[0] >= at:                                     # 申請之後做好了
            done.append({"mk": mk, "code": code, "name": name, "issue": n, "at": at, "made": lr[0]})
            close(n, f"報告好了：{name}（{code}），{lr[0]}。{link(mk, code)}", "completed")
            continue
        if n not in prev:
            ok, why = need(mk, code, today)
            if not ok and lr:                                      # 90 天內做過、之後沒有新一季財報
                close(n, f"{name}（{code}）{lr[0]} 已經有報告，之後還沒有新一季財報，先不重做：{link(mk, code)}", "completed")
                continue
        dup = next((x for x in items if (x["mk"], x["code"]) == (mk, code)), None)
        if dup:
            close(n, f"{name}（{code}）已經在佇列裡（#{dup['issue']}），一起等那張；這張先關掉。")
            continue
        who = str((it.get("user") or {}).get("login") or "")
        if per_user.get(who, 0) >= PER_USER and not _owner(it):
            close(n, f"每個帳號同時最多 {PER_USER} 件申請，等前面的做好再申請。這張先關掉。")
            continue
        if len(items) >= MAX_QUEUE and not _owner(it):
            close(n, f"佇列已滿（{MAX_QUEUE} 件），過幾天再申請。這張先關掉。")
            continue
        per_user[who] = per_user.get(who, 0) + 1
        items.append({"mk": mk, "code": code, "name": name, "issue": n, "at": at, "owner": _owner(it)})

    items.sort(key=lambda x: (not x["owner"], x["at"], x["issue"]))
    for i, x in enumerate(items, 1):
        if x["issue"] not in prev:
            acts.append(("comment", x["issue"], f"收到，{x['name']}（{x['code']}）已排進個股報告佇列，現在第 {i} 位。"
                                                 "排程照順序做，做好會在這張單回報告連結並關單。"))
    done.sort(key=lambda x: (x["made"], x["issue"]))
    return {"as_of": now, "items": items, "done": done}, acts


def _days_before(day: str, n: int) -> str:
    return (datetime.fromisoformat(day) - timedelta(days=n)).date().isoformat()


def same(a: dict | None, b: dict) -> bool:
    """除了 as_of 都一樣＝不用寫檔（沒事的那幾輪不產生 commit）。"""
    if not a:
        return False
    return {k: v for k, v in a.items() if k != "as_of"} == {k: v for k, v in b.items() if k != "as_of"}


def pending(path: Path = FILE) -> list[dict]:
    """排程與頁面讀的佇列（照順序）。"""
    return list((_read(path, {}) or {}).get("items") or [])
