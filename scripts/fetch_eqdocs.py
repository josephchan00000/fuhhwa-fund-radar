#!/usr/bin/env python3
"""抓個股報告的官方文件包（docs/lab_eq_docs_plan.md；arm/lab/eqdocs.py）。只在 CI 跑（.github/workflows/eq_docs.yml）：容器擋觀測站。

    python3 scripts/fetch_eqdocs.py --ping .ping/eqdocs --out DIR          # push 觸發：讀請求 {"id", "codes", "raw"?}
    python3 scripts/fetch_eqdocs.py --codes "tw:6870 tw:7730" --out DIR     # 手動

寫 DIR/id.txt（請求編號）、DIR/tw-{代號}.json（全文）、DIR/tw-{代號}.md（給子代理讀）、DIR/index.json（每家狀態與文件清單）。
請求裡 "raw": true＝另存每個觀測站回應的前 60KB 到 DIR/raw/（做測試樣本用）。代號與編號照格式驗過才用，不進任何指令。"""
import argparse
import json
import secrets
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arm.clock import now_tw, today_tw  # noqa: E402
from arm.http import get_bytes  # noqa: E402
from arm.lab import eqdocs as E  # noqa: E402
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
    bad = [c for c in codes if not E.CODE_RE.fullmatch(c)]
    if bad or not codes or len(codes) > MAX_CODES:
        raise SystemExit(f"代號格式不對或數量不對（1～{MAX_CODES} 個）：{codes!r}")
    return rid, list(dict.fromkeys(codes)), raw


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ping")
    ap.add_argument("--codes")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
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
    for c in codes:
        code = c.split(":", 1)[1]
        t0 = datetime.now()
        pk = E.build(code, today_tw(), post, get)
        (out / f"tw-{code}.json").write_text(json.dumps(pk, ensure_ascii=False), encoding="utf-8")
        (out / f"tw-{code}.md").write_text(E.render_md(pk), encoding="utf-8")
        idx["codes"][c] = E.index(pk)
        print(f"[eqdocs] {c} {pk.get('name')}：{pk['st']}（{(datetime.now() - t0).seconds}s）", flush=True)
    (out / "index.json").write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
