#!/usr/bin/env python3
"""抓個股報告的官方文件包（docs/lab_eq_docs_plan.md；arm/lab/eqdocs.py）。只在 CI 跑（.github/workflows/eq_docs.yml）：容器擋觀測站。

    python3 scripts/fetch_eqdocs.py --ping .ping/eqdocs --out DIR          # push 觸發：讀請求 {"id", "codes", "raw"?}
    python3 scripts/fetch_eqdocs.py --codes "tw:6870 tw:7730" --out DIR     # 手動
    python3 scripts/fetch_eqdocs.py --log 主幹/data/eq_docs_log.json --index DIR/index.json   # 抓完：記錄、標「連續沒抓到的日子」

寫 DIR/id.txt（請求編號）、DIR/{tw|us}-{代號}.json（全文）、DIR/{tw|us}-{代號}.md（給子代理讀）、DIR/index.json（每家狀態與文件清單）。
美股（us:代號）抓 SEC 的 10-K／10-Q／8-K（arm/lab/eqdocs_us.py），聯絡 email 只從 SEC_CONTACT_EMAIL 讀，不印、不存。
請求裡 "raw": true＝另存每個觀測站回應的前 60KB 到 DIR/raw/（做測試樣本用）。代號與編號照格式驗過才用，不進任何指令。"""
import argparse
import json
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arm.clock import now_tw, today_tw  # noqa: E402
from arm.http import get_bytes  # noqa: E402
from arm.lab import eqdocs as E  # noqa: E402
from arm.lab import eqdocs_us as U  # noqa: E402
from arm.lab.market import _decode, post_bytes  # noqa: E402

MAX_CODES = 6


def request(args) -> tuple[str, list[str], bool]:
    if args.ping:
        req = json.loads(Path(args.ping).read_text(encoding="utf-8"))
        rid, codes, raw = str(req.get("id") or ""), [str(c) for c in req.get("codes") or []], bool(req.get("raw"))
    else:
        rid = f"{now_tw():%Y%m%d-%H%M}-{secrets.token_hex(3)}"
        codes, raw = (args.codes or "").split(), False
    if not E.ID_RE.fullmatch(rid):
        raise SystemExit(f"請求編號格式不對：{rid!r}")
    bad = [c for c in codes if not (E.CODE_RE.fullmatch(c) or U.CODE_RE.fullmatch(c))]
    if bad or not codes or len(codes) > MAX_CODES:
        raise SystemExit(f"代號格式不對或數量不對（1～{MAX_CODES} 個）：{codes!r}")
    return rid, list(dict.fromkeys(codes)), raw


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ping")
    ap.add_argument("--codes")
    ap.add_argument("--out")
    ap.add_argument("--log", help="data/eq_docs_log.json（CI 寫回 main 的那一份）")
    ap.add_argument("--index", help="這次的 index.json（會補上每家的 fails）")
    args = ap.parse_args()
    if args.log:
        return log(Path(args.log), Path(args.index))
    if not args.out:
        ap.error("要給 --out")
    rid, codes, raw = request(args)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "id.txt").write_text(rid + "\n", encoding="utf-8")
    n = [0]

    def keep(name: str, b: bytes) -> None:
        if raw:
            (out / "raw").mkdir(exist_ok=True)
            n[0] += 1
            (out / "raw" / f"{n[0]:03d}-{name}.html").write_bytes(b[:60000])

    def post(ep: str, form: dict) -> str:
        b = post_bytes(f"{E.OV}/mops/web/ajax_{ep}", form, timeout=60, retries=2)
        keep(f"{ep}-{form.get('co_id', '')}-{form.get('step', '')}", b)
        return _decode(b)

    def get(url: str) -> bytes:
        b = get_bytes(url, retries=2, timeout=180, use_cache=False)
        if not b.startswith(b"%PDF"):
            keep("get-" + url.rsplit("/", 1)[-1].split("?")[0][:40], b)
        return b

    idx = {"id": rid, "at": f"{now_tw():%Y-%m-%d %H:%M}", "codes": {}}
    sec = sec_client() if any(c.startswith("us:") for c in codes) else None
    for c in codes:
        mk, code = c.split(":", 1)
        t0 = now_tw()
        if mk == "us":
            pk = us_pack(code, sec)
            md = U.render_md(pk)
            ix = U.index(pk)
        else:
            pk = E.build(code, today_tw(), post, get)
            md = E.render_md(pk)
            ix = E.index(pk)
        (out / f"{mk}-{code}.json").write_text(json.dumps(pk, ensure_ascii=False), encoding="utf-8")
        (out / f"{mk}-{code}.md").write_text(md, encoding="utf-8")
        idx["codes"][c] = ix
        print(f"[eqdocs] {c} {pk.get('name')}：{pk['st']}（{(now_tw() - t0).seconds}s）", flush=True)
    (out / "index.json").write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


def sec_client():
    """SEC 的取用器（每秒最多 5 個請求、User-Agent 帶聯絡 email）與代號 → CIK 表；沒有 SEC_CONTACT_EMAIL → None。"""
    import time
    import urllib.error
    import urllib.request
    from arm.http import _CTX
    from arm.lab import secfin as SF
    email = SF.contact()
    if not email:
        print("[eqdocs] 沒有 SEC_CONTACT_EMAIL，美股文件包跳過", flush=True)
        return None
    last = [0.0]

    def get(url: str) -> tuple[int, bytes]:
        w = last[0] + 0.2 - time.time()
        if w > 0:
            time.sleep(w)
        last[0] = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": SF._ua(email), "Accept": "*/*"})
        try:
            with urllib.request.urlopen(req, timeout=120, context=_CTX) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, b""
        except Exception:                                              # noqa: BLE001
            return 0, b""
    try:
        tick = SF.fetch_tickers(email)
    except Exception as e:                                             # noqa: BLE001
        print(f"[eqdocs] SEC 代號表抓不到：{type(e).__name__}", flush=True)
        tick = {}
    return get, tick


def us_pack(sym: str, sec) -> dict:
    if not sec:
        return {"v": U.VER, "mk": "us", "code": sym, "made": today_tw().isoformat(), "ok": False, "st": {"sub": "err 沒有 SEC 聯絡設定"}}
    get, tick = sec
    cik = tick.get(sym)
    if not cik:
        return {"v": U.VER, "mk": "us", "code": sym, "made": today_tw().isoformat(), "ok": False, "st": {"sub": "err 代號查不到 CIK"}}
    return U.build(sym, cik, today_tw(), get)


def log(lp: Path, ip: Path) -> int:
    idx = json.loads(ip.read_text(encoding="utf-8"))
    lg = json.loads(lp.read_text(encoding="utf-8")) if lp.exists() else {}
    E.log_update(lg, idx)
    lp.parent.mkdir(parents=True, exist_ok=True)
    lp.write_text(json.dumps(lg, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    ip.write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
    for c, x in idx["codes"].items():
        print(f"[eqdocs] {c}：{E.d2(x)}（連續沒抓到 {len(x['fails'])} 天）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
