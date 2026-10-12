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


# ── ② 列印版的兩段歷史——鎖「舊作法」不回歸、「新作法」不走樣 ──
# 2026-07-20：第一版「晨會列印版」（把螢幕區塊套 @media print 硬印、beforeprint 動手腳）使用者看過
#   後指示「格式醜、整個功能刪掉」，本測試原本鎖的是「整組不得回來」。
# 2026-09-07：使用者重新提出明確需求（每天早上可列印／存 PDF、排版乾淨不可切頁、字小無妨、
#   五組重點、基金 ETF 報酬率單獨一頁）——改為獨立的 #print 樹（arm/printview.py），與舊版
#   「硬印螢幕區塊」是不同作法。守法改成：舊版殘留符號不得回來；新版必須是獨立樹、且 @media print
#   只印 #print（不是再把螢幕區塊拿去印）。

def test_print_feature_is_independent_tree_not_old_overlay():
    from arm import fund_dashboard, printview
    html = fund_dashboard.render()
    assert "printhead" not in html and "beforeprint" not in html          # 舊版殘留
    assert '\n<div id="print" class="pr">' in html                          # 新版＝body 直屬獨立樹
    assert "body>*:not(#print){display:none!important}" in printview.CSS   # 只印 #print
    assert "@media print" not in fund_dashboard._CSS                       # 螢幕版 CSS 不再夾帶列印規則


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


# ── 速覽／總覽文風閘門（2026-09-01 使用者：「整段粗體的偏少…廢話不要太多、用詞精準」）──

def _brief_doc(body: str) -> str:
    return "# 〈台股盤前重點〉2026/09/01\n\n## 🔹盤前速覽\n\n" + body + "\n\n---\n\n## 🔹盤前卡\n"


def test_check_head_sections_gate(tmp_path, monkeypatch):
    # 2026-10-13 使用者：「印出來的昨夜美股總覽那欄都是空的」——總覽／速覽抽不到時網頁與列印版
    # 只會安靜少一塊，其他閘門照樣 🟢；此閘門讓它變紅。段名寫成粗體行也要認得（同儀表板）。
    import importlib
    sys.path.insert(0, str(ROOT / "scripts"))
    check = importlib.import_module("check_reports")
    monkeypatch.setattr(check, "ROOT", tmp_path)
    d = check.HEAD_SINCE

    def put(rel: str, text: str) -> None:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text + "\n### 卡 1｜某事（來源｜【新事件】｜重要度 7/10）\n內文。\n", encoding="utf-8")

    put(f"reports/usnews/{d}_v1.md", "# 標題\n\n🔹**前後24小時重大公司與產業事項總覽**\n\n- 費半跌 **2%**。\n\n---")
    put(f"reports/macronews/{d}.md", "# 標題\n\n## 🔹前後 24 小時政策總覽\n\n**油價**領漲。\n\n---")
    put(f"reports/twnews/{d}.md", "# 標題\n\n### 🔹盤前速覽\n\n夜盤收跌。\n\n────")
    assert check._check_head_sections(d) == []               # 三種寫法都認得
    put(f"reports/usnews/{d}_v1.md", "# 標題\n\n- 費半跌 **2%**。\n\n---")
    put(f"reports/twnews/{d}.md", "# 標題\n\n## 🔹指數速覽\n\n加權收高。\n")
    errs = check._check_head_sections(d)
    assert len(errs) == 2 and "usnews" in errs[0] and "twnews" in errs[1]
    assert "列印版" in errs[0]                                # 訊息要講清楚後果


def test_check_brief_style_gate():
    import importlib
    sys.path.insert(0, str(ROOT / "scripts"))
    check = importlib.import_module("check_reports")

    ok = _brief_doc("昨夜訊號分歧：**費半 +0.57%**，台積電 ADR **-0.53%**。資金集中記憶體。")
    assert check._check_brief(ok, "x.md") == []

    long_one = _brief_doc("台指期夜盤在 **45,983 點**附近整理。" + "補充說明。" * 70)
    assert any("超過上限" in e for e in check._check_brief(long_one, "x.md"))

    tagged = _brief_doc("國際背景一句帶過（細節留給總經報告）：**油價**走高，**電子權值**承壓。")
    assert any("版型標籤" in e for e in check._check_brief(tagged, "x.md"))

    plain = _brief_doc("昨夜三大指數收黑，資金集中記憶體與設備族群，權值代工持平。")
    assert any("粗體不足" in e for e in check._check_brief(plain, "x.md"))


def test_check_brief_counts_prose_and_bullets_separately():
    """索引式總覽（指數收盤條列＋一段解析）不可因「條列＋散文合計」被誤殺——
    條列本來就是好掃的版式，不是使用者抱怨的長篇敘述；改以條數／每條長度設限。"""
    import importlib
    sys.path.insert(0, str(ROOT / "scripts"))
    check = importlib.import_module("check_reports")
    bullets = "\n".join(f"- **指數{i}**：收 1,00{i} 點，下跌 0.{i}%，為八月最後一個交易日。"
                        for i in range(4))
    doc = _brief_doc(bullets + "\n\n八月最後一日是**板塊分流**，**能源**收紅、道瓊吃下最大跌點。")
    assert check._check_brief(doc, "x.md") == []
    too_many = _brief_doc("\n".join(f"- **項{i}**：內容內容內容。" for i in range(9))
                          + "\n\n結論一句，**方向**明確、**族群**分歧。")
    assert any("條列" in e and "超過" in e for e in check._check_brief(too_many, "x.md"))
    fat = _brief_doc("- **項**：" + "把整段長文塞進條列想繞過上限。" * 12
                     + "\n\n結論一句，**方向**明確、**族群**分歧。")
    assert any("條列是索引" in e for e in check._check_brief(fat, "x.md"))


# ── 卡片可讀性閘門（2026-09-01 使用者：「不只是速覽，整個新聞卡也要套用」）──

def _read_card(summary: str, points: str = "影響很大，**族群**受惠。") -> str:
    return ("# 〈台股盤前重點〉2026-09-02\n\n## 🔹盤前卡\n\n"
            "### 測試卡（來源：X｜2026/09/02｜【新事件】｜重要度 7/10）\n\n"
            f"1. **新聞摘要**：{summary}\n"
            "3. **漲跌分析**：收 **100 元、跌 1%**，主因外資調節。\n"
            f"4. **對持股／族群影響**：{points}\n"
            "6. **參考連結**：[來源](https://example.com/a)\n")


def test_check_card_read_gate():
    import importlib
    sys.path.insert(0, str(ROOT / "scripts"))
    check = importlib.import_module("check_reports")
    p = Path  # noqa: F841

    ok = _read_card("公司公告新案，總額 **39 億美元**，創**歷史新高**。買方為產業龍頭。")
    assert check._check_card_read(_tmp_md(ok), "x.md") == []

    thin = _read_card("公司公告新案，總額 39 億美元，創歷史新高。", points="影響有限。")
    assert any("粗體僅" in e for e in check._check_card_read(_tmp_md(thin), "x.md"))

    longsent = _read_card("公司公告新案，" + "並且同時說明後續安排與各項配套細節" * 5 + "。"
                          + "另外" + "補充說明各項配套與時程安排的具體內容" * 4 + "。"
                          + "再者" + "說明未來數年的產能與物料成本安排規劃" * 4 + "。"
                          "總額 **39 億美元**、創**新高**、買方為**龍頭**。")
    assert any("超過 60 字" in e for e in check._check_card_read(_tmp_md(longsent), "x.md"))

    filler = _read_card("值得注意的是，公司公告新案，總額 **39 億**，創**新高**，買方為**龍頭**。")
    assert any("填充語" in e for e in check._check_card_read(_tmp_md(filler), "x.md"))


def _tmp_md(text: str) -> Path:
    import tempfile
    f = Path(tempfile.mkdtemp()) / "r.md"
    f.write_text(text, encoding="utf-8")
    return f
