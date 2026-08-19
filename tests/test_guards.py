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


def _deep_card(i: int, move: bool = True, pts: int = 2, pad: int = 40) -> list[str]:
    """新版深度格式卡（2026-08-20 起）：粗體標籤＋漲跌分析＋≥2 條影響欄。"""
    lines = [f"### 卡 {i}｜標題{i}（來源：X｜2026/08/20｜【新事件】｜重要度 7/10）",
             "1. **新聞摘要**：" + "事" * pad + "。"]
    if move:
        lines.append("3. **漲跌分析**：個股大漲 4.2%，主因財報優於預期，次因外資回補。")
    for j, lab in enumerate(["對持股／族群影響", "對市場情緒影響"][:pts], 4):
        lines.append(f"{j}. **{lab}**：" + "析" * pad + "。後續觀察：下次法說。")
    lines += ["6. **參考資料**：[來源](https://example.com/a)。", ""]
    return lines


def test_check_reports_move_and_depth_gate(tmp_path, monkeypatch):
    # 2026-08-19 使用者需求：每卡「漲跌分析」欄＋深度下限——2026-08-20 起強制、【深度】卡豁免
    import importlib
    sys.path.insert(0, str(ROOT / "scripts"))
    check = importlib.import_module("check_reports")
    monkeypatch.setattr(check, "ROOT", tmp_path)
    from arm import usnews
    monkeypatch.setattr(usnews, "_load_chips", lambda: {})   # 隔離真實落檔（大變動閘門另測）
    d = "2026-08-20"                                   # ≥ MOVE_SINCE

    def write_all(card_lines: list[str]) -> None:
        body = "\n".join(["# 報告"] + card_lines)
        for rel in (f"reports/usnews/{d}_v1.md", f"reports/usnews/{d}_v2.md",
                    f"reports/twnews/{d}.md", f"reports/macronews/{d}.md"):
            p = tmp_path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body, encoding="utf-8")
        _write_cal(tmp_path / f"reports/macrocal/{d}.md", "2026/08/20")

    ok = [l for i in range(1, 5) for l in _deep_card(i)]
    write_all(ok)
    assert check.run(d) == 0                           # 新版格式 → 通過
    write_all([l for i in range(1, 5) for l in _deep_card(i, move=False)])
    assert check.run(d) == 1                           # 缺漲跌分析 → 擋下
    write_all([l for i in range(1, 5) for l in _deep_card(i, pts=1)])
    assert check.run(d) == 1                           # 影響分析僅 1 條 → 擋下
    write_all([l for i in range(1, 5) for l in _deep_card(i, pad=5)])
    assert check.run(d) == 1                           # 分析過薄（<120 字）→ 擋下
    deep = ["### 【深度】產業鏈專題（來源：工商時報｜2026/08/20｜【深度】｜重要度 6/10）",
            "1. **新聞摘要**：略。", "2. **為什麼值得讀**：略。",
            "3. **參考資料**：[來源](https://example.com/a)。", ""]
    write_all(ok + deep)
    assert check.run(d) == 0                           # 【深度】精選卡免漲跌分析／深度下限


def test_check_big_moves_gate():
    # 大變動提及閘門（2026-08-19 使用者要求「不可限縮新聞範圍」的下限保證設計）：
    # 只擋「官方序列旗標大變動、全文隻字未提」；提及即過、flags 空＝跳過、未旗標不查。
    import importlib
    sys.path.insert(0, str(ROOT / "scripts"))
    check = importlib.import_module("check_reports")
    flags = {"sox": {"label": "費半 ^SOX", "disp": "11,992.46（-4.98%）", "flag": True},
             "tsm_adr": {"label": "台積電 ADR", "disp": "413.41（-4.06%）", "flag": False}}
    keys = ("sox", "tsm_adr")
    miss = [("reports/usnews/x_v1.md", "🔹總覽：昨夜科技股大跌。", keys)]
    errs = check._check_big_moves(miss, flags)
    assert len(errs) == 1 and "費半" in errs[0]         # 旗標未提及 → 1 錯；未旗標的 ADR 不查
    hit = [("reports/usnews/x_v1.md", "🔹總覽：費半重挫近 5%，主因記憶體股獲利了結。", keys)]
    assert check._check_big_moves(hit, flags) == []     # 提及（任何段落）即過
    assert check._check_big_moves(miss, {}) == []       # 落檔讀不到 → fail-open 不擋發佈


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
