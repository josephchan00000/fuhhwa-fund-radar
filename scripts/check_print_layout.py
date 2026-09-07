#!/usr/bin/env python3
"""列印版分頁驗證（2026-09-07）：headless Chromium 真的把儀表板印成 A4 PDF，再用 PyMuPDF 讀回檢查。

pytest 只能守字串與 CSS 規則；「同一資訊不可切到兩頁」只有真的印出來才知道。本腳本：
  ① 印 PDF（Playwright page.pdf、A4、含背景）並在印前於每個列印區塊／新聞卡首尾插入
     微小白字標記 @@BEG:id@@／@@END:id@@（PyMuPDF 抽文字時可見、肉眼看不到）；
  ② 讀回：每個區塊首尾標記須落在同一頁（🔴＝被切頁）；⑤ 報酬率頁須獨占一頁
     （該頁只准有 p-ret 與頁尾）；① 行事曆須從第 1 頁開始；總頁數列出供人判斷；
  ③ --png DIR：每頁另存 PNG（110 dpi）供人眼複核版面（本容器可用 Read 看圖）。

用法：TZ=Asia/Taipei python3 scripts/check_print_layout.py [dashboard/index.html] [--pdf out.pdf] [--png DIR]
依賴：pip install playwright pymupdf；瀏覽器依序取 env PRINT_CHROME → /opt/pw-browsers/chromium-*/chrome-linux/chrome
      → playwright 預設 chromium。任何 infra 失敗（無瀏覽器／套件）以 ⚪ 結束、exit 2；斷言失敗 exit 1。
"""
from __future__ import annotations

import argparse
import glob
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARK_RE = re.compile(r"@@(BEG|END):([\w-]+)@@")
# 標記放法（首版踩坑）：零高度的 block 標記會被 Chromium 排到「前一頁的尾巴」——強制分頁前的
# 零高度盒子塞得進上一頁餘白，結果 ⑤ 明明從新頁開始、BEG 卻在前頁。改為：BEG＝塞進標題列
# （h2／卡片標題列）內的 inline 字、跟著可見標題走；END＝約 3px 高的小 block（2pt 字、正常行高）。
MARK_JS = r"""
(() => {
  const txt = (kind, id) => '@@' + kind + ':' + id + '@@';
  const beg = (host, id) => { const s = document.createElement('span'); s.textContent = txt('BEG', id);
    s.style.cssText = 'font-size:2pt;color:#fff;line-height:1'; host.prepend(s); };
  const end = (host, id) => { const s = document.createElement('span'); s.textContent = txt('END', id);
    s.style.cssText = 'display:block;font-size:2pt;color:#fff;line-height:1'; host.append(s); };
  const flow = [];
  document.querySelectorAll('#print .pr-sec').forEach(el => {
    beg(el.querySelector('h2') || el, el.id); end(el, el.id);
    if (el.classList.contains('pr-flow')) flow.push(el.id);
  });
  document.querySelectorAll('#print .pr-card').forEach((el, i) => {
    beg(el.querySelector('.pr-ch') || el, 'card-' + (i + 1)); end(el, 'card-' + (i + 1)); });
  const f = document.querySelector('#print .pr-foot'); if (f) { beg(f, 'foot'); end(f, 'foot'); }
  return { cards: document.querySelectorAll('#print .pr-card').length, flow: flow };
})()
"""


def find_chrome() -> str | None:
    import os
    if os.environ.get("PRINT_CHROME"):
        return os.environ["PRINT_CHROME"]
    hits = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))
    return hits[-1] if hits else None


def _launch(p):
    """瀏覽器來源同 smoke_dashboard：指定路徑（env／本機 /opt/pw-browsers）→ runner 內建 Chrome
    （channel=chrome，零下載）→ playwright 預設 chromium。"""
    exe = find_chrome()
    if exe:
        return p.chromium.launch(executable_path=exe)
    try:
        return p.chromium.launch(channel="chrome")
    except Exception:  # noqa: BLE001
        return p.chromium.launch()


def make_pdf(html_path: Path, pdf_path: Path) -> dict:
    """印成 PDF；回 {cards: 新聞卡數, flow: [允許跨頁流動的區塊 id]}。"""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = _launch(p)
        pg = b.new_page()
        pg.goto(html_path.resolve().as_uri())
        info = pg.evaluate(MARK_JS) or {}
        pg.pdf(path=str(pdf_path), format="A4", print_background=True, prefer_css_page_size=True)
        b.close()
    return {"cards": int(info.get("cards") or 0), "flow": list(info.get("flow") or [])}


def analyze(pdf_path: Path) -> tuple[int, dict[str, dict[str, int]], list[set[str]]]:
    """回 (頁數, {id: {BEG: 頁, END: 頁}}, 每頁出現的 id 集合)。頁碼 1-based。"""
    import fitz  # PyMuPDF
    doc = fitz.open(str(pdf_path))
    marks: dict[str, dict[str, int]] = {}
    per_page: list[set[str]] = []
    for i, page in enumerate(doc, start=1):
        ids: set[str] = set()
        for kind, mid in MARK_RE.findall(page.get_text()):
            marks.setdefault(mid, {})[kind] = i
            ids.add(mid)
        per_page.append(ids)
    return len(doc), marks, per_page


def check(n_pages: int, marks: dict, per_page: list[set[str]], flow: list[str] | None = None) -> list[str]:
    """flow＝允許卡與卡之間換頁的區塊（④ 新聞）：不要求首尾同頁，但標題須與第一張卡同頁
    （標題不可孤懸頁尾）、每張卡各自不可切頁。其餘區塊首尾必須同頁。"""
    probs: list[str] = []
    flow = flow or []
    if not marks:
        return ["PDF 內找不到任何區塊標記——#print 沒印出來（@media print 規則或標記注入失敗）"]
    cards = sorted((m for m in marks if m.startswith("card-")), key=lambda s: int(s.split("-")[1]))
    for mid, kv in marks.items():
        if "BEG" not in kv or "END" not in kv:
            probs.append(f"{mid}：標記不完整 {kv}（區塊可能被截斷或文字未輸出）")
        elif mid in flow:
            if cards and marks[cards[0]].get("BEG") != kv["BEG"]:
                probs.append(f"{mid}：標題在第 {kv['BEG']} 頁、第一張卡在第 {marks[cards[0]].get('BEG')} 頁（標題孤懸）")
        elif kv["BEG"] != kv["END"]:
            probs.append(f"{mid}：被切頁（第 {kv['BEG']} 頁 → 第 {kv['END']} 頁）")
    cal = marks.get("p-cal", {})
    if cal.get("BEG") not in (None, 1):
        probs.append(f"p-cal：行事曆應從第 1 頁開始，實際第 {cal.get('BEG')} 頁")
    ret = marks.get("p-ret", {})
    if ret.get("BEG"):
        others = per_page[ret["BEG"] - 1] - {"p-ret", "foot"}
        if others:
            probs.append(f"p-ret：報酬率頁應獨占一頁，同頁還有 {sorted(others)}")
    if n_pages > 8:
        probs.append(f"總頁數 {n_pages} 過多（預期 3～6 頁）——檢查新聞卡數或字級")
    return probs


def dump_png(pdf_path: Path, out_dir: Path, dpi: int = 110) -> list[Path]:
    import fitz
    out_dir.mkdir(parents=True, exist_ok=True)
    outs = []
    for i, page in enumerate(fitz.open(str(pdf_path)), start=1):
        fp = out_dir / f"page-{i}.png"
        page.get_pixmap(dpi=dpi).save(str(fp))
        outs.append(fp)
    return outs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("html", nargs="?", default=str(ROOT / "dashboard" / "index.html"))
    ap.add_argument("--pdf", default=None)
    ap.add_argument("--png", default=None)
    a = ap.parse_args()
    html_path = Path(a.html)
    # 預設寫到系統暫存目錄——別落在 dashboard/（那裡的檔案會被 Vercel 部署出去）
    pdf_path = Path(a.pdf) if a.pdf else Path(tempfile.gettempdir()) / "fuhhwa-print-check.pdf"
    try:
        info = make_pdf(html_path, pdf_path)
        n_pages, marks, per_page = analyze(pdf_path)
    except Exception as e:  # noqa: BLE001 — infra 故障不算紅
        print(f"[列印驗證] ⚪ 無法產生／讀取 PDF（{type(e).__name__}: {e}）——需 playwright＋pymupdf＋Chromium")
        return 2
    print(f"[列印驗證] PDF {pdf_path}：{n_pages} 頁、新聞卡 {info['cards']} 張、可流動區塊 {info['flow']}")
    for mid, kv in marks.items():
        print(f"  {mid:<10} 第 {kv.get('BEG')}→{kv.get('END')} 頁")
    for i, ids in enumerate(per_page, start=1):
        print(f"  第 {i} 頁：{'、'.join(sorted(ids)) or '（無標記）'}")
    probs = check(n_pages, marks, per_page, info["flow"])
    if a.png:
        for fp in dump_png(pdf_path, Path(a.png)):
            print(f"  PNG → {fp}")
    if probs:
        for p_ in probs:
            print(f"[列印驗證] 🔴 {p_}")
        return 1
    print("[列印驗證] 🟢 每個區塊皆未切頁；報酬率頁獨占一頁")
    return 0


if __name__ == "__main__":
    sys.exit(main())
