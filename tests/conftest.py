"""pytest 共用：路徑設定 + 合成 xlsx 產生器（離線、零網路）＋籌碼雷達整站（labsite，瀏覽器測試用）。"""
import functools
import glob
import http.server
import sys
import threading
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CHROME = next(iter(sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))), None)


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


@pytest.fixture(scope="session")
def labsite(tmp_path_factory):
    """用真的資料照每天建頁的順序（scripts/gen_fund_dashboard.py）建好整站：配置頁、市場頁（台股、美股）、
    泡沫與訊號總覽的轉址頁、舊大神策略頁、研究紀錄頁，起一個本機 HTTP 伺服器、開一個無頭 Chromium
    → (瀏覽器, 網址開頭, 目錄)。整個測試只建一次（約 3 分鐘）；瀏覽器或資料不在就跳過。
    tests/test_plain.py（主頁面用字）、tests/test_old_urls.py（舊網址、頂欄）共用。"""
    sync_api = pytest.importorskip("playwright.sync_api")
    if not CHROME:
        pytest.skip("沒有 Chromium")
    from arm.lab import bubpage, heatpage, heatpage_us, page, research_page, sigpage, xspage
    O = tmp_path_factory.mktemp("labsite")
    if not page.build(O / "x9.html", O / "x9s.json") and not (O / "x9.html").exists():
        pytest.skip("配置頁建不起來（資料不在）")
    heatpage.build(O / "x9m.html", O / "x9mh.json")
    heatpage_us.build(O / "x9mu.html", O)
    bubpage.build(O / "x9b.html")
    sigpage.build(O / "x9o.html", O / "x9oh.json")             # 指標面板每一次的清單 x9oh-{市場}.json、研究卡 x9or-*.json
    page.finish()                                             # 配置頁用今天的警訊讀數
    xspage.build(O / "x9x.html", O / "x9xh.json")
    research_page.build(O / "x9r.html")
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(O)))
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME)
        yield b, f"http://127.0.0.1:{srv.server_address[1]}", O
        b.close()
    srv.shutdown()


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def make_xlsx(title: str, date_str: str, meta: dict, sections: list) -> bytes:
    """造一份與復華 assetsExcel 同結構的最小 xlsx（全部用 shared strings）。

    meta：{基金資產淨值, 基金在外流通單位數, 基金每單位淨值}
    sections：[(header_list, [data_row_list, ...]), ...]
    """
    rows: list[list[str]] = [[title], [f"日期: {date_str}"]]
    for k in ("基金資產淨值", "基金在外流通單位數", "基金每單位淨值"):
        rows.append([k])
        rows.append([str(meta[k])])
    for header, datarows in sections:
        rows.append(list(header))
        rows.extend([list(r) for r in datarows])

    strings: list[str] = []

    def sid(s: str) -> int:
        s = str(s)
        if s not in strings:
            strings.append(s)
        return strings.index(s)

    for r in rows:
        for c in r:
            sid(c)

    ss = ('<?xml version="1.0"?><x:sst xmlns:x="z">'
          + "".join(f"<x:si><x:t>{_esc(s)}</x:t></x:si>" for s in strings)
          + "</x:sst>")
    body = []
    for r in rows:
        cells = "".join(f'<x:c t="s"><x:v>{sid(c)}</x:v></x:c>' for c in r)
        body.append(f"<x:row>{cells}</x:row>")
    sheet = ('<?xml version="1.0"?><x:worksheet xmlns:x="z"><x:sheetData>'
             + "".join(body) + "</x:sheetData></x:worksheet>")

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/sharedStrings.xml", ss)
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    return buf.getvalue()
