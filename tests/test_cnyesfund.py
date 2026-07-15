"""arm/connectors/cnyesfund —— 鉅亨每日報酬覆蓋層（離線 fixture；真端點由正式區 CI 驗證）。"""
import json

from arm.connectors import cnyesfund
from arm import fund_insights


def _item(**kw):
    base = {"cnyesId": "A2C011", "displayNameLocal": "復華高成長基金",
            "nav": 126.75, "navDate": "2026-07-14", "changePercent": -3.3,
            "return1M": -5.21, "return3M": 80.1, "return6M": 99.9,
            "returnYTD": 95.3, "return1Y": 230.4, "return3Y": 350.0}
    base.update(kw)
    return base


# ── 解析防禦 ─────────────────────────────────────────────────

def test_items_unwraps_common_shapes():
    it = [_item()]
    assert cnyesfund._items({"items": {"data": it}}) == it
    assert cnyesfund._items({"items": it}) == it
    assert cnyesfund._items({"data": {"data": it}}) == it
    assert cnyesfund._items({"data": it}) == it
    assert cnyesfund._items({"statusCode": 404}) == []
    assert cnyesfund._items(None) == []


def test_overlay_from_item_maps_fields():
    ov = cnyesfund.overlay_from_item(_item())
    assert ov["cnyes_id"] == "A2C011" and ov["nav"] == 126.75
    assert ov["nav_date"] == "2026/07/14" and ov["chg_pct"] == -3.3
    assert ov["returns_daily"]["ytd"] == 95.3 and ov["returns_daily"]["1m"] == -5.21
    assert "1w" not in ov["returns_daily"]          # 缺鍵不硬造


def test_date_and_num_normalization():
    assert cnyesfund._date(1784000000) is not None          # epoch 可解析
    assert cnyesfund._date("2026/7/9 18:00") == "2026/07/09"
    assert cnyesfund._num("12.34%") == 12.34 and cnyesfund._num(None) is None


def test_norm_name_unifies_dashes_and_spaces():
    assert (cnyesfund.norm_name("復華全球短期收益基金—新臺幣")
            == cnyesfund.norm_name("復華全球短期收益基金-新臺幣"))
    assert cnyesfund.norm_name(" 復華高成長 基金 ") == "復華高成長基金"


# ── 覆蓋規則 ─────────────────────────────────────────────────

def _doc(**kw):
    d = {"fund_id": "01", "name": "復華高成長基金", "short_name": "復華高成長",
         "nav": 131.07, "nav_date": "2026/07/13", "nav_change_pct": "-1.00%",
         "returns": {"ytd": "106.70%", "1y": "241.13%", "3y": "362.57%"}}
    d.update(kw)
    return d


def test_apply_overlay_writes_daily_and_newer_nav(tmp_path, monkeypatch):
    monkeypatch.setattr(cnyesfund, "MAP_PATH", tmp_path / "map.json")
    monkeypatch.setattr(cnyesfund, "fetch_detail", lambda *a, **kw: {})
    monkeypatch.setattr(cnyesfund, "search_all", lambda *a, **kw: [_item()])
    doc = _doc()
    n = cnyesfund.apply_overlay([doc], tmp_path)
    assert n == 1
    assert doc["returns_daily"]["ytd"] == 95.3
    assert doc["returns_daily_asof"] == "2026/07/14"
    assert doc["nav"] == 126.75 and doc["nav_src"] == "cnyes"   # 較新才覆蓋
    assert doc["nav_change_pct"] == "-3.30%"
    saved = json.loads((tmp_path / "01.json").read_text(encoding="utf-8"))
    assert saved["returns_daily_asof"] == "2026/07/14"
    fmap = json.loads((tmp_path / "map.json").read_text(encoding="utf-8"))
    assert fmap["01"]["cnyesId"] == "A2C011"


def test_apply_overlay_keeps_official_nav_when_not_newer(tmp_path, monkeypatch):
    monkeypatch.setattr(cnyesfund, "MAP_PATH", tmp_path / "map.json")
    monkeypatch.setattr(cnyesfund, "fetch_detail", lambda *a, **kw: {})
    monkeypatch.setattr(cnyesfund, "search_all",
                        lambda *a, **kw: [_item(navDate="2026-07-13", nav=999.0)])
    doc = _doc()
    cnyesfund.apply_overlay([doc], tmp_path)
    assert doc["nav"] == 131.07 and "nav_src" not in doc        # 同日不覆蓋 NAV
    assert doc["returns_daily"]["ytd"] == 95.3                  # 但每日報酬照收


def test_apply_overlay_no_match_no_write(tmp_path, monkeypatch):
    monkeypatch.setattr(cnyesfund, "MAP_PATH", tmp_path / "map.json")
    monkeypatch.setattr(cnyesfund, "fetch_detail", lambda *a, **kw: {})
    monkeypatch.setattr(cnyesfund, "search_all",
                        lambda *a, **kw: [_item(displayNameLocal="別家基金")])
    doc = _doc()
    assert cnyesfund.apply_overlay([doc], tmp_path) == 0
    assert "returns_daily" not in doc and not (tmp_path / "01.json").exists()


def test_apply_overlay_pinned_id_wins(tmp_path, monkeypatch):
    monkeypatch.setattr(cnyesfund, "MAP_PATH", tmp_path / "map.json")
    monkeypatch.setattr(cnyesfund, "fetch_detail", lambda *a, **kw: {})
    (tmp_path / "map.json").write_text(
        json.dumps({"01": {"cnyesId": "A2C011"}}), encoding="utf-8")
    monkeypatch.setattr(cnyesfund, "search_all",
                        lambda *a, **kw: [_item(displayNameLocal="名稱對不上但ID釘住")])
    doc = _doc()
    assert cnyesfund.apply_overlay([doc], tmp_path) == 1


# ── 總覽逐欄回退鏈 ────────────────────────────────────────────

def test_overview_prefers_daily_then_official():
    doc = _doc(returns_daily={"ytd": 95.3, "1y": 230.4}, group_label="x")
    row = fund_insights.overview_rows([doc])[0]
    assert row["ytd"] == 95.3 and row["y1"] == 230.4    # 鉅亨每日值優先
    assert row["y3"] == 362.57                          # 鉅亨缺 3y → 回退官網
    doc2 = _doc(group_label="x")
    row2 = fund_insights.overview_rows([doc2])[0]
    assert row2["ytd"] == 106.7                         # 無覆蓋層 → 官網值
