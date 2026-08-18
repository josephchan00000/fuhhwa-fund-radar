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


def test_check_reports_blocks_process_language_in_body():
    # 正文禁流程性字句（2026-08-17 踩坑：總覽出現「數字取自本機官方落檔 `series.sox`」；
    # 同 08-04「未取得兩來源／見資料侷限」句式）——資料侷限/合規段內豁免
    import importlib, sys as _s
    _s.path.insert(0, str(ROOT / "scripts"))
    check = importlib.import_module("check_reports")
    body_bad = ("## 🔹總覽\n費半收 12,417.05 點（取自本機官方落檔 `series.sox`）。\n"
                "## 🔹速覽\n櫃買方向詳見資料侷限說明。\n"
                "## 資料侷限說明\n費半採 `data/macro_chips.json` 之 `series.sox`。\n"
                "## I. 合規揭露\n本文引自官方落檔。\n")
    errs = check._check_process_language(body_bad, "x.md")
    assert len(errs) == 2                                     # 總覽+速覽各一；侷限/合規段不報
    assert "官方落檔" in errs[0] and "見資料侷限" in errs[1]
    clean = "## 🔹總覽\n費半收 12,417.05 點（−0.31%）。\n## 資料侷限說明\n採官方落檔。\n"
    assert check._check_process_language(clean, "x.md") == []


def test_check_reports_date_wording():
    # 收盤值日期用詞（2026-08-18 使用者：「收在 430.97 美元，較上一個交易日（8/14）上漲逾 1%」
    # 讀起來像只抓到 8/14 的價格）：①基準用詞統一「前一交易日」；②收盤值自身日期須先於基準日
    import importlib, sys as _s
    _s.path.insert(0, str(ROOT / "scripts"))
    check = importlib.import_module("check_reports")
    bad = ("## 🔹盤前速覽\n"
           "- **台積電ADR**：收在 **430.97 美元**，較上一個交易日（8/14）上漲逾 1%。\n")
    errs = check._check_date_wording(bad, "x.md")
    assert len(errs) == 2                                     # 用詞變體＋只標基準日各一
    assert "前一交易日" in errs[0] and "只標了比較基準日" in errs[1]
    good = ("## 🔹盤前速覽\n"
            "- **台積電ADR**：8/17（美東週一）收在 **430.97 美元**，較前一交易日（8/14）上漲逾 1%。\n"
            "- **費城半導體指數（SOX）**：8/17 收在 **12,621 點附近**，上漲逾 1.6%。\n"
            "- **加權指數**：前一交易日（8/14，週五）收在 45,811.01 點、下跌 0.46%。\n"
            "- 公司 7 月營收 120 億元，較 7/15 法說預估上修。\n"       # 營收非收盤、不觸發
            "## 🔹資料侷限說明\n收在 430 美元係較（8/14）之估算。\n"      # 侷限段豁免句型檢查
            "- [台股收在45,811 較上一交易日跌0.46%](https://example.com/x)\n")  # 連結原題不受規範
    assert check._check_date_wording(good, "x.md") == []
