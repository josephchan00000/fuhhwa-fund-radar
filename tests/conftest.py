"""pytest 共用：路徑設定 + 合成 xlsx 產生器（離線、零網路）。"""
import sys
import zipfile
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


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
