"""arm/stockmeta.py：個股產業別對照（方塊圖外層分組）——解析、代碼轉名、落檔合併。"""
from arm import stockmeta as sm


def test_rows_to_map_中文鍵名_上市格式():
    rows = [{"出表日期": "1150730", "公司代號": "2330", "公司名稱": "台積電", "產業別": "24"},
            {"公司代號": "1303", "公司名稱": "南亞", "產業別": "03"}]
    assert sm.rows_to_map(rows) == {"2330": "半導體業", "1303": "塑膠工業"}


def test_rows_to_map_英文鍵名_上櫃格式():
    rows = [{"SecuritiesCompanyCode": "6488", "CompanyName": "環球晶", "IndustryCode": "24"}]
    assert sm.rows_to_map(rows) == {"6488": "半導體業"}


def test_rows_to_map_產業別已是名稱時原樣沿用():
    rows = [{"公司代號": "3008", "產業別": "光電業"}]
    assert sm.rows_to_map(rows) == {"3008": "光電業"}


def test_rows_to_map_忽略無代號或無產業的列():
    rows = [{"公司名稱": "沒有代號", "產業別": "24"},
            {"公司代號": "2330"},
            {"公司代號": "abc", "產業別": "24"},
            "字串不是物件"]
    assert sm.rows_to_map(rows) == {}


def test_rows_to_map_未知代碼不亂猜():
    assert sm.rows_to_map([{"公司代號": "9999", "產業別": "99"}]) == {}


def test_sample_keys_供CI收斂():
    assert "公司代號" in sm.sample_keys([{"公司代號": "2330", "產業別": "24"}])
    assert "非物件" in sm.sample_keys(["x"])


def test_merge_本次全空不洗掉既有對照(monkeypatch, tmp_path):
    fp = tmp_path / "stock_industry.json"
    monkeypatch.setattr(sm, "DATA_FP", fp)
    assert sm.save(sm.merge({"2330": "半導體業"}))
    assert sm.merge({})["industry"] == {"2330": "半導體業"}
    assert sm.save(sm.merge({})) is True                    # 既有非空 → 照樣落檔
    assert sm.industry_map() == {"2330": "半導體業"}


def test_merge_新值覆蓋舊值並保留其他(monkeypatch, tmp_path):
    monkeypatch.setattr(sm, "DATA_FP", tmp_path / "s.json")
    sm.save(sm.merge({"2330": "半導體業", "1303": "塑膠工業"}))
    sm.save(sm.merge({"1303": "化學工業"}))
    m = sm.industry_map()
    assert m == {"2330": "半導體業", "1303": "化學工業"}


def test_save_全空不建檔(monkeypatch, tmp_path):
    fp = tmp_path / "s.json"
    monkeypatch.setattr(sm, "DATA_FP", fp)
    assert sm.save({"industry": {}}) is False
    assert not fp.exists()
