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


# ── ② 晨會列印版已整組移除（2026-07-20 使用者指示：格式醜、整個功能刪掉）——鎖回歸 ──

def test_print_feature_removed():
    from arm import fund_dashboard
    html = fund_dashboard.render()
    assert "tb-print" not in html and "printhead" not in html
    assert "beforeprint" not in html and "@media print" not in html


# ── ③ 內容 QA 閘門：通過／缺檔／卡數不足三條路徑 ──

def _write_ok_report(p: Path, cards: int = 4):
    body = ["# 報告"]
    for i in range(1, cards + 1):
        body += [f"### 卡 {i}｜標題{i}（來源：X｜2026/07/01｜【新事件】｜重要度 7/10）",
                 "1. **新聞摘要**：略。",
                 "2. **一句話重點**：略。",
                 "3. **對公司影響**：略。",
                 "6. **參考資料**：[來源](https://example.com/a)。", ""]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(body), encoding="utf-8")


def _write_bare_numbered_report(p: Path, cards: int = 4):
    """裸編號卡（缺 **新聞摘要**：／**對…影響**： 粗體標籤）——2026-07-30 實際踩到的壞格式：
    卡數／連結／重要度全過，但儀表板解析不到內容、展開後只剩連結。"""
    body = ["# 報告"]
    for i in range(1, cards + 1):
        body += [f"### {i}. 標題{i}（來源：X，2026/07/01｜【新事件】｜重要度 7/10）",
                 f"1. 某項事實敘述{i}；[來源](https://example.com/a)。",
                 "2. 對公司影響：略。",          # 無粗體標籤 → 解析不到
                 ""]
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
    # 卡數／連結／重要度全合格，但內文寫成裸編號（缺粗體欄位標籤）→ 仍須擋下
    # （2026-07-30 回歸鎖：此格式曾誤報 🟢 上線，儀表板該報整片無摘要與影響分析）
    _write_bare_numbered_report(tmp_path / f"reports/twnews/{d}.md", cards=6)
    assert check.run(d) == 1
