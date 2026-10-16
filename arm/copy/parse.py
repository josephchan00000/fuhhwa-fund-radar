"""把每日想法報告（reports/{date}_{etf}.md）解析成結構化 ideas。

這是文案層唯一的輸入邊界：只讀**已發布的報告 markdown**，與 pipeline/ideas/籌碼引擎
徹底解耦（M6 設計決策 ④：不碰 pipeline.py / ideas.py / brokers / chips / etfinfo）。

報告格式（見 ideas.render_markdown）：
    # 每日想法組合 — {name}（{id}）  資料日 {date}
    > {header 脈絡：收盤 / 折溢價 / AUM …}
    ### N. [面向] 🟢
    - **想法**：…
    - 佐證：…
    - 內容形式：…
      - ⚠️合規[中] `(…)`：… → 建議…
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

REPORTS = Path(__file__).resolve().parents[2] / "reports"

_H1 = re.compile(r"^#\s*每日想法組合\s*[—\-]\s*(?P<name>.+?)（(?P<id>[0-9A-Za-z]+)）\s*資料日\s*(?P<date>\d{4}-\d{2}-\d{2})")
_IDEA = re.compile(r"^###\s*\d+\.\s*\[(?P<cat>[^\]]+)\]\s*(?P<emoji>[🟢🟡🔴]?)")


@dataclass
class Idea:
    idx: int
    category: str
    conf: str                 # 🟢/🟡/🔴（信心/合規燈號，沿用報告）
    headline: str = ""
    evidence: str = ""
    content_format: str = ""
    src_compliance: list = field(default_factory=list)   # 報告既有合規標注（原文）


@dataclass
class ReportDoc:
    etf_id: str
    name: str
    date: str
    header: str = ""          # `>` 脈絡行（收盤/折溢價/AUM…）
    ideas: list = field(default_factory=list)


def parse_text(md: str) -> ReportDoc:
    lines = md.splitlines()
    doc = ReportDoc(etf_id="", name="", date="")
    cur: Idea | None = None
    for raw in lines:
        line = raw.rstrip()
        if not doc.etf_id:
            m = _H1.match(line)
            if m:
                doc.name = m.group("name").strip()
                doc.etf_id = m.group("id").strip()
                doc.date = m.group("date")
                continue
        if line.startswith(">") and not doc.header:
            doc.header = line.lstrip("> ").strip()
            continue
        mi = _IDEA.match(line)
        if mi:
            cur = Idea(idx=len(doc.ideas) + 1, category=mi.group("cat").strip(),
                       conf=mi.group("emoji") or "🟡")
            doc.ideas.append(cur)
            continue
        if cur is None:
            continue
        s = line.strip()
        if s.startswith("- **想法**"):
            cur.headline = s.split("：", 1)[-1].strip()
        elif s.startswith("- 佐證"):
            cur.evidence = s.split("：", 1)[-1].strip()
        elif s.startswith("- 內容形式"):
            cur.content_format = s.split("：", 1)[-1].strip()
        elif s.startswith("- ⚠️合規") or s.startswith("⚠️合規"):
            cur.src_compliance.append(s.lstrip("- ").strip())
    return doc


def parse_file(path: str | Path) -> ReportDoc:
    return parse_text(Path(path).read_text(encoding="utf-8"))


def latest_report(etf_id: str, *, date: str | None = None) -> Path:
    """找某主角最新（或指定日）的報告檔。找不到丟 FileNotFoundError。"""
    if date:
        p = REPORTS / f"{date}_{etf_id}.md"
        if not p.exists():
            raise FileNotFoundError(f"找不到報告 {p}")
        return p
    cands = sorted(REPORTS.glob(f"*_{etf_id}.md"))
    if not cands:
        raise FileNotFoundError(f"reports/ 沒有 {etf_id} 的報告，請先跑 scripts/run_daily.py {etf_id}")
    return cands[-1]


def list_etf_ids() -> list[str]:
    """reports/ 內出現過的所有主角代號（去重）。"""
    ids = {p.stem.split("_", 1)[1] for p in REPORTS.glob("*_*.md") if "_" in p.stem}
    return sorted(ids)
