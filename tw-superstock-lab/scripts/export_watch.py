"""W1 研究結果 → fuhhwa 機會頁用的小檔（../data/lab/watch_research.json）。只搬數字、不重算。

    python3 scripts/export_watch.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "reports" / "W1_watch.json"
OUT = ROOT.parent / "data" / "lab" / "watch_research.json"
KEEP = ("size", "week_B", "rand_week_B", "week_C", "early_B", "early_C", "prec_A", "base_A", "prec_B", "base_B",
        "prec_C", "base_C", "early_D", "early_E", "early_F", "prec_D", "base_D", "prec_E", "base_E", "prec_F", "base_F",
        "rem_E")


def _r(x, d=4):
    return round(x, d) if isinstance(x, float) else x


def per_stock(cases: list[dict], s: str) -> dict:
    """10 倍股以股票為單位（同一檔取漲最多的那段）：名單列出過幾檔、抓得早幾檔、第一次列出時已漲幾倍、之後還剩幾倍（中位數）。"""
    best: dict = {}
    for r in cases:
        if r["c"] not in best or r["x"] > best[r["c"]]["x"]:
            best[r["c"]] = r
    rows = list(best.values())
    hit = [r for r in rows if s in r["by"]]
    early = [r for r in hit if r["by"][s]["early"]]
    ups = sorted(r["by"][s]["up"] for r in hit if r["by"][s]["up"] is not None)
    rems = sorted(r["by"][s]["rem"] for r in hit if r["by"][s]["rem"] is not None)
    big = [r for r in rows if r["x"] >= 20]
    return {"n": len(rows), "hit": len(hit), "early": len(early), "up_med": ups[len(ups) // 2] if ups else None,
            "rem_med": rems[len(rems) // 2] if rems else None, "n20": len(big),
            "early20": sum(1 for r in big if s in r["by"] and r["by"][s]["early"]),
            "examples": [{"c": r["c"], "name": r["name"], "t0": r["t0"], "pk": r["pk"], "x": r["x"], **r["by"][s]}
                         for r in sorted(early, key=lambda r: -r["x"])[:12]],
            "missed": [{"c": r["c"], "name": r["name"], "x": r["x"]} for r in sorted(rows, key=lambda r: -r["x"])
                       if s not in r["by"]][:8]}


def main() -> None:
    o = json.loads(SRC.read_text("utf-8"))
    st = o["stats"]
    out = {"v": 2, "asof": o["asof"], "plan": o["plan"], "chosen": o["chosen"], "missing": o["missing"], "lists": {}}
    for s in ("S9", "S1", "S3", "S6"):
        out["lists"][s] = {p: {k: _r(v) for k, v in st[s][p].items() if k in KEEP} for p in ("IS", "VAL", "HO", "ALL")}
        out["lists"][s]["stock10"] = per_stock(o["cases_10x"], s)
    OUT.write_text(json.dumps(out, ensure_ascii=False, sort_keys=True, separators=(",", ":")), "utf-8")
    print(f"→ {OUT}（{OUT.stat().st_size:,} bytes）")


if __name__ == "__main__":
    main()
