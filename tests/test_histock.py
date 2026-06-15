"""Histock 券商分點 adapter 解析測試（離線，純 parse_branch）。

關鍵回歸：分點表每列 10 欄、買/賣兩側並排，**空白欄必須保留**（曾因過濾空白欄導致
買賣兩側錯位、整檔只解析到 1 筆）。樣本仿 histock branch.aspx 真實結構。
"""
from arm.connectors.brokers import histock

# 表頭 + 3 列；第 1 列買超側『賣張』為空白（真實頁面常見），測欄位對齊不崩。
HTML = """
<html><body>資料日期 2026/06/12
<table>
<tr><th>券商名稱</th><th>買張</th><th>賣張</th><th>賣超</th><th>均價</th>
    <th>券商名稱</th><th>買張</th><th>賣張</th><th>買超</th><th>均價</th></tr>
<tr><td>台新</td><td>1,395</td><td>7,065</td><td>-5,669</td><td>19.21</td>
    <td>港商野村</td><td>7,899</td><td></td><td>7,899</td><td>19.17</td></tr>
<tr><td>富邦</td><td>1,179</td><td>5,706</td><td>-4,526</td><td>19.13</td>
    <td>美林</td><td>2,500</td><td>4</td><td>2,496</td><td>19.15</td></tr>
<tr><td>合計</td><td></td><td></td><td>-10,195</td><td></td>
    <td>合計</td><td></td><td></td><td>10,395</td><td></td></tr>
</table></body></html>
"""


def test_parse_date_and_both_sides():
    date, flows = histock.parse_branch(HTML, "00991A")
    assert date == "2026-06-12"
    by = {f.broker_name: f.net for f in flows}
    # 買超側（正）：空白『賣張』不得讓欄位錯位
    assert by["港商野村"] == 7899 and by["美林"] == 2496
    # 賣超側（負）
    assert by["台新"] == -5669 and by["富邦"] == -4526
    # 合計列被略過
    assert "合計" not in by


def test_target_id_and_no_empty_collapse():
    _, flows = histock.parse_branch(HTML, "00991A")
    assert all(f.target_id == "00991A" for f in flows)
    assert len(flows) == 4            # 2 列 × 2 側；合計列排除（回歸：不應只剩 1 筆）


def test_empty_table_returns_no_flows():
    date, flows = histock.parse_branch("<html>2026/06/12 no table here</html>", "9999")
    assert date == "2026-06-12" and flows == []
