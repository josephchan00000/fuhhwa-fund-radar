"""守門測試（2026-07-18 審查補強）：SyntaxWarning 回歸鎖／列印版不變量／內容 QA 閘門。"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


# ── ① _JS 的 \/ 曾在 CI 噴 SyntaxWarning：整包模組在 -W error 下編譯須乾淨 ──

def test_no_syntax_warnings_in_arm_modules():
    r = subprocess.run(
        [sys.executable, "-W", "error::SyntaxWarning", "-c",
         "import arm.fund_dashboard, arm.usnews, arm.etfwatch, arm.fund_insights"],
        cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ── ② 晨會列印版不變量（列印壞版難以測試截圖，鎖住關鍵 CSS/JS 存在性） ──

def test_print_invariants():
    from arm import fund_dashboard
    html = fund_dashboard.render()
    assert "beforeprint" in html and "afterprint" in html   # 列印前展開新聞卡、印後還原
    assert 'class="printhead"' in html                      # 晨會抬頭（僅列印顯示）
    assert "@media print" in html
    prt = html.split("@media print", 1)[1]
    assert "#details" in prt.split("}", 3)[1] or "#details" in prt[:600]  # 詳情列印隱藏


# ── ③ 內容 QA 閘門：通過／缺檔／卡數不足三條路徑 ──

def _write_ok_report(p: Path, cards: int = 4):
    body = ["# 報告"]
    for i in range(1, cards + 1):
        body += [f"### 卡 {i}｜標題{i}（來源：X｜2026/07/01｜【新事件】｜重要度 7/10）",
                 "1. **新聞摘要**：略。",
                 "6. **參考資料**：[來源](https://example.com/a)。", ""]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(body), encoding="utf-8")


def _write_cal(p: Path, date_slash: str):
    rows = "\n".join(f"| 07/{10+i} | 美：測試項{i} | — | — | — | 未公布 |" for i in range(12))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"# 本週重點財經行事曆（07/13–07/17）\n> 更新：{date_slash}；本週美股正常交易\n\n"
                 f"| 日期 | 項目 | 預期 | 實際 | 前值 | 狀態 |\n|---|---|---|---|---|---|\n{rows}\n",
                 encoding="utf-8")


def test_check_reports_pass_and_failures(tmp_path, monkeypatch):
    import importlib
    sys.path.insert(0, str(ROOT / "scripts"))
    check = importlib.import_module("check_reports")
    monkeypatch.setattr(check, "ROOT", tmp_path)
    d = "2026-07-18"
    _write_ok_report(tmp_path / f"reports/usnews/{d}_v1.md")
    _write_ok_report(tmp_path / f"reports/usnews/{d}_v2.md")
    _write_ok_report(tmp_path / f"reports/twnews/{d}.md")
    _write_ok_report(tmp_path / f"reports/macronews/{d}.md")
    _write_cal(tmp_path / f"reports/macrocal/{d}.md", "2026/07/18")
    assert check.run(d) == 0                                  # 全齊 → 通過
    (tmp_path / f"reports/twnews/{d}.md").unlink()
    assert check.run(d) == 1                                  # 缺檔 → 擋下
    _write_ok_report(tmp_path / f"reports/twnews/{d}.md", cards=2)
    assert check.run(d) == 1                                  # 卡數不足 → 擋下
