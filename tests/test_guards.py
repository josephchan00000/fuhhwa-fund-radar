"""守門測試（2026-07-18 審查補強）：SyntaxWarning 回歸鎖／列印功能移除回歸鎖／內容 QA 閘門。"""
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


# ── ② 晨會列印功能已整組移除（2026-07-20 使用者指示：列印版面醜、無法維護）——鎖回歸 ──

def test_print_feature_removed():
    from arm import fund_dashboard
    html = fund_dashboard.render()
    assert "beforeprint" not in html and "afterprint" not in html
    assert "printhead" not in html and "tb-print" not in html
    assert "@media print" not in html and "window.print" not in html


# ── ②b fundID 錯置防呆：官網名稱與 config 名稱不符即跳過（2026-07-20） ──
# 背景：新募集基金的官網頁常未被搜尋引擎收錄，config/funds.json 的 id 只能由相鄰檔號推定；
# 推錯會整檔抓成別的基金且名稱被 API 權威值覆寫——儀表板看不出異狀，故在抓取端擋下。

def test_fetch_holdings_name_mismatch_guard():
    import importlib
    sys.path.insert(0, str(ROOT / "scripts"))
    fh = importlib.import_module("fetch_holdings")
    ok = fh._name_matches
    assert ok("復華美國新星基金-新臺幣", "復華美國新星基金-新臺幣")          # 完全一致
    assert ok("復華台灣菁英50指數基金", "復華台灣菁英50指數基金-新臺幣")     # 互為前綴（幣別後綴）
    assert ok(None, "任意") and ok("任意", None)                             # 任一缺名放行（維持舊行為）
    assert not ok("復華全球AI動力成長指數基金-新臺幣", "復華全球創新金融指數基金-美元")  # 錯置
    assert not ok("復華台灣菁英50指數基金", "復華全方位基金A類型")


# ── ②c 【…】徽章長度閘門：長標注不得包進 nowrap 徽章（手機會撐破卡片，2026-07-20） ──

def test_inline_tag_badge_only_for_short_annotations():
    from arm import fund_dashboard as fd
    assert '<span class="tag">【延伸】</span>' in fd._inline("【延伸】新進展")
    assert '<span class="tag">【週末合併時窗說明】</span>' in fd._inline("【週末合併時窗說明】")
    long = fd._inline("【延伸・新在哪：昨報已列 Alphabet／特斯拉主軸，本卡補週日最新共識】內文")
    assert 'class="tag"' not in long                     # 長標注維持一般文字、可自然換行


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
