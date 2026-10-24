"""前十大持股簡介覆蓋率防呆（2026-07-23 使用者：前十大簡介一再漏掉）。

守住兩件事：
  1. uncovered_top_holdings() 能正確抓出缺 intro 的持股（單元）。
  2. 已入庫的基金快照，前十大 100% 有簡介（覆蓋率斷言）——容器端一旦看到含新標的的
     CI 快照就會紅，逼在發佈前補齊。
"""
import json

from arm import fund_intro


def test_uncovered_detects_missing(tmp_path, monkeypatch):
    # 造兩檔基金、共用一個缺 intro 的持股「新標的X」
    funds_dir = tmp_path / "funds"
    funds_dir.mkdir()
    (funds_dir / "01.json").write_text(json.dumps({
        "fund_id": "01", "short_name": "甲基金",
        "top_holdings": [{"name": "台積電", "weight": 10.0, "sector": "半導體"},
                         {"name": "新標的X", "weight": 5.0, "sector": "測試"}]}), encoding="utf-8")
    (funds_dir / "02.json").write_text(json.dumps({
        "fund_id": "02", "short_name": "乙基金",
        "top_holdings": [{"name": "新標的X", "weight": 4.0, "sector": "測試"}]}), encoding="utf-8")
    monkeypatch.setattr(fund_intro, "FUNDS_DIR", funds_dir)
    monkeypatch.setattr(fund_intro, "config",
                        type("C", (), {"funds": staticmethod(lambda: [{"id": "01"}, {"id": "02"}])}))
    monkeypatch.setattr(fund_intro, "_profiles",
                        lambda: {"台積電": {"intro": "台灣台積電…"}})   # 新標的X 無 intro

    gaps = fund_intro.uncovered_top_holdings(10)
    names = [g["name"] for g in gaps]
    assert names == ["新標的X"]           # 台積電有 intro、不列
    assert gaps[0]["count"] == 2          # 出現於兩檔
    assert {f["short_name"] for f in gaps[0]["funds"]} == {"甲基金", "乙基金"}


def test_all_committed_funds_top10_have_intro():
    """已入庫的所有基金快照，前十大持股簡介覆蓋率須 100%。

    這是使用者一再反映的「前十大簡介漏掉」的最後防線：CI 抓到新持股後，容器端下一輪
    看到該快照時，此測試會紅，逼在發佈前把缺的標的補進 config/holding_profiles.json。
    """
    gaps = fund_intro.uncovered_top_holdings(10)
    detail = "、".join(f'{g["name"]}（{g["count"]}檔）' for g in gaps)
    assert not gaps, (f"{len(gaps)} 檔前十大持股缺簡介，請補進 config/holding_profiles.json："
                      f"{detail}（跑 scripts/check_holdings_intro.py 看細節）")


def test_norm_ticker_剝掉交易所字尾():
    """海外持股代號帶彭博式交易所碼（`AMD US`／`8035 JP`），簡介庫存的是純代號。"""
    assert fund_intro.norm_ticker("AMD US") == "AMD"
    assert fund_intro.norm_ticker("8035 JP") == "8035"
    assert fund_intro.norm_ticker(" ifx gr ") == "IFX"
    assert fund_intro.norm_ticker("AV/ LN") == "AV/"          # 帶符號的代號原樣保留
    assert fund_intro.norm_ticker("2330") == "2330"            # 台股純代號不受影響
    assert fund_intro.norm_ticker("009150 KS") == "009150"
    assert fund_intro.norm_ticker("002463 C2") == "002463"     # 陸股通字尾（深股通 C2／滬股通 C1）
    assert fund_intro.norm_ticker("600183 C1") == "600183"
    assert fund_intro.norm_ticker(None) == ""


def test_intro_lookup_代號索引同時收原樣與正規化():
    profs = {"超微半導體": {"intro": "AMD 簡介", "ticker": "AMD"},
             "東京威力科創": {"intro": "TEL 簡介", "ticker": "8035 JP"}}
    import arm.fund_intro as fi
    orig = fi._profiles
    fi._profiles = lambda: profs
    try:
        by_tk, by_nm = fi.intro_lookup()
    finally:
        fi._profiles = orig
    assert by_tk[fi.norm_ticker("AMD US")] == "AMD 簡介"   # 庫存純代號、快照帶字尾
    assert by_tk["8035 JP"] == "TEL 簡介"                  # 庫存帶字尾、原樣也查得到
    assert by_tk["8035"] == "TEL 簡介"
    assert by_nm["超微半導體"] == "AMD 簡介"


def test_etf_持股簡介覆蓋率不倒退():
    """ETF 持股（含海外）的簡介覆蓋率——2026-07-31 補到 100%，這裡守住不倒退。

    與上面的「基金前十大」不同：ETF 持股在 CI 端抓，新標的同樣只會先出現在 CI 快照裡，
    容器端下一輪看到就該補。門檻設 95%（留一點新標的緩衝），低於即紅。
    """
    import json
    from pathlib import Path
    fp = Path(fund_intro.ROOT) / "data" / "etf_holdings.json"
    if not fp.exists():
        return
    by_tk, by_nm = fund_intro.intro_lookup()
    tot = miss_w = 0.0
    miss = []
    for e in (json.loads(fp.read_text(encoding="utf-8")).get("etfs") or {}).values():
        for r in (e.get("detail") or {}).get("all") or []:
            sid = str(r.get("stock_id") or "").strip()
            nm = str(r.get("name") or "").strip()
            w = r.get("weight") or 0
            tot += w
            if not (by_tk.get(sid) or by_tk.get(fund_intro.norm_ticker(sid))
                    or by_nm.get(nm) or by_nm.get(nm.upper())):
                miss_w += w
                miss.append(f"{sid} {nm}")
    if tot <= 0:
        return
    cov = 1 - miss_w / tot
    assert cov >= 0.95, (f"ETF 持股簡介權重覆蓋率 {cov:.1%} 低於 95%，"
                         f"請補進 config/holding_profiles.json：{'、'.join(sorted(set(miss))[:20])}")


def test_名稱帶_html_實體也對得上簡介_且顯示乾淨名稱(tmp_path, monkeypatch):
    """復華 xlsx 解析 2026-10-21 前沒還原 XML 實體，舊快照名稱是 `JPMORGAN CHASE &amp; CO`；
    網頁再跳脫一次就顯示成字面「&amp;」。讀取端還原後，舊快照與新抓的乾淨名稱都要對得上簡介。"""
    funds_dir = tmp_path / "funds"
    funds_dir.mkdir()
    (funds_dir / "01.json").write_text(json.dumps({
        "fund_id": "01", "short_name": "甲基金",
        "top_holdings": [{"name": "JPMORGAN CHASE &amp; CO", "weight": 3.0},
                         {"name": "WELLS FARGO & CO", "weight": 2.0}]}), encoding="utf-8")
    prof_fp = tmp_path / "profiles.json"
    prof_fp.write_text(json.dumps({"profiles": {
        "JPMORGAN CHASE & CO": {"intro": "摩根大通簡介", "ticker": "JPM"},
        "WELLS FARGO &amp; CO": {"intro": "富國銀行簡介", "ticker": "WFC"}}}), encoding="utf-8")
    monkeypatch.setattr(fund_intro, "FUNDS_DIR", funds_dir)
    monkeypatch.setattr(fund_intro, "PROFILES", prof_fp)
    monkeypatch.setattr(fund_intro, "_prof_cache", None)
    monkeypatch.setattr(fund_intro, "config",
                        type("C", (), {"funds": staticmethod(lambda: [{"id": "01"}])}))
    doc = fund_intro.load("01")
    names = [h["name"] for h in doc["top_holdings"]]
    assert names == ["JPMORGAN CHASE & CO", "WELLS FARGO & CO"]
    assert [h["intro"] for h in doc["top_holdings"]] == ["摩根大通簡介", "富國銀行簡介"]
    assert fund_intro.uncovered_top_holdings(10) == []
    _by_tk, by_nm = fund_intro.intro_lookup()
    assert by_nm["WELLS FARGO & CO"] == "富國銀行簡介"


def test_uncovered_etf_holdings_用代號與名稱比對並排序(tmp_path, monkeypatch):
    """ETF 持股缺簡介（2026-10-21：只有測試 95% 門檻守、滑到 97% 沒人發現 → 納入每日缺口檔）。"""
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "etf_holdings.json").write_text(json.dumps({"etfs": {
        "00998A": {"holdings": [{"stock_id": "C US", "name": "花旗集團公司", "weight": 1.9},
                                {"stock_id": "MNG LN", "name": "M&amp;G公開有限公司", "weight": 1.9},
                                {"stock_id": "002463 C2", "name": "WUS Printed Circuit", "weight": 2.1}]},
        "00412A": {"holdings": [{"stock_id": "3406", "name": "玉晶光", "weight": 2.1}]},
        "00993A": {"holdings": [{"stock_id": "3406", "name": "玉晶光", "weight": 1.31},
                                {"stock_id": "2330", "name": "台積電", "weight": 9.0}]}}}),
        encoding="utf-8")
    monkeypatch.setattr(fund_intro, "ROOT", tmp_path)
    monkeypatch.setattr(fund_intro, "_profiles", lambda: {
        "台積電": {"intro": "台積電簡介", "ticker": "2330"},
        "滬士電子股份有限公司": {"intro": "滬電簡介", "ticker": "002463"},   # 陸股通字尾剝掉才對得上
        "花旗集團": {"intro": "花旗簡介", "ticker": "C"}})
    gaps = fund_intro.uncovered_etf_holdings()
    assert [g["ticker"] for g in gaps] == ["3406", "MNG"]          # 兩檔 ETF 持有的排前面
    assert gaps[0]["etfs"] == ["00412A", "00993A"] and gaps[0]["count"] == 2
    assert gaps[0]["weight"] == 2.1
    assert gaps[1]["name"] == "M&G公開有限公司" and gaps[1]["sid"] == "MNG LN"   # 名稱已還原實體


def test_check_holdings_intro_缺口檔含_etf_持股(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "chk_intro", Path(fund_intro.ROOT) / "scripts" / "check_holdings_intro.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "GAP_FP", tmp_path / "gap.json")
    monkeypatch.setattr(fund_intro, "uncovered_top_holdings", lambda n=10: [
        {"name": "新標的X", "sector": "測試", "count": 1,
         "funds": [{"short_name": "甲基金", "weight": 3.0}]}])
    monkeypatch.setattr(fund_intro, "uncovered_etf_holdings", lambda: [
        {"name": "玉晶光", "ticker": "3406", "sid": "3406", "etfs": ["00412A"], "count": 1, "weight": 2.1}])
    monkeypatch.setattr(fund_intro, "uncovered_us_qm", lambda: [{"name": "Paycom Software, Inc.", "ticker": "PAYC"}])
    assert mod.main() == 1
    doc = json.loads((tmp_path / "gap.json").read_text(encoding="utf-8"))
    assert doc["count"] == 3 and doc["fund_count"] == 1 and doc["etf_count"] == 1 and doc["usqm_count"] == 1
    assert doc["items"][0] == {"src": "fund", "name": "新標的X", "sector": "測試", "count": 1,
                               "funds": ["甲基金"]}
    assert doc["items"][1] == {"src": "etf", "name": "玉晶光", "ticker": "3406", "count": 1,
                               "etfs": ["00412A"], "weight": 2.1}
    assert doc["items"][2] == {"src": "usqm", "name": "Paycom Software, Inc.", "ticker": "PAYC"}
    monkeypatch.setattr(fund_intro, "uncovered_top_holdings", lambda n=10: [])
    monkeypatch.setattr(fund_intro, "uncovered_etf_holdings", lambda: [])
    monkeypatch.setattr(fund_intro, "uncovered_us_qm", lambda: [])
    assert mod.main() == 0
    assert json.loads((tmp_path / "gap.json").read_text(encoding="utf-8"))["count"] == 0


def test_intro_gap_chip_分基金與_etf(tmp_path, monkeypatch):
    from arm import fund_dashboard as fd
    (tmp_path / "data").mkdir()
    fp = tmp_path / "data" / "holdings_intro_gap.json"
    monkeypatch.setattr(fd, "ROOT_DIR", tmp_path)
    fp.write_text(json.dumps({"count": 2, "items": [
        {"src": "fund", "name": "新標的X"}, {"src": "etf", "name": "M&G公開有限公司", "ticker": "MNG"}]}),
        encoding="utf-8")
    chip = fd._intro_gap_chip()
    assert "<b>持股簡介</b>" in chip and "2 檔缺簡介" in chip
    assert "基金前十大 1・ETF 持股 1" in chip and "M&amp;G公開有限公司" in chip   # 顯示時只跳脫一次
    fp.write_text(json.dumps({"count": 1, "items": [{"name": "新標的X"}]}), encoding="utf-8")
    assert "<b>前十大簡介</b>" in fd._intro_gap_chip()          # 舊格式（沒有 src）照舊
    fp.write_text(json.dumps({"count": 0, "items": []}), encoding="utf-8")
    assert fd._intro_gap_chip() == ""


def test_uncovered_us_qm_配置頁美股列的股票(tmp_path, monkeypatch):
    """2026-10-24 使用者：美股只有代號看不懂 → 配置頁美股列的股票（手上的、要買的、名單前 5 名裡手上沒有的）缺簡介就進缺口檔；
    依代號查、名稱用每週紀錄的英文名（沒有就是代號）。"""
    (tmp_path / "data" / "lab").mkdir(parents=True)
    (tmp_path / "data" / "lab" / "ussx_qm_live.json").write_text(json.dumps({
        "names": {"PAYC": "Paycom Software, Inc."},
        "now": {"hold": [{"c": "INSW"}, {"c": "VLO"}], "buy": ["MPC"],
                "list": [{"c": c, "rs": 90} for c in ["VLO", "PAYC", "QLYS", "FTNT", "HALO", "NTAP", "CON"]]}}),
        encoding="utf-8")
    monkeypatch.setattr(fund_intro, "ROOT", tmp_path)
    monkeypatch.setattr(fund_intro, "_profiles", lambda: {"International Seaways Inc": {"intro": "美國 …", "ticker": "INSW"},
                                                          "Fortinet": {"intro": "美國 Fortinet…", "ticker": "FTNT"}})
    codes, names = fund_intro.us_qm_codes()
    assert codes == ["INSW", "VLO", "MPC", "PAYC", "QLYS", "FTNT", "HALO", "NTAP"]      # 名單前 5 名不含手上的 VLO、要買的 MPC
    assert fund_intro.uncovered_us_qm() == [{"name": c, "ticker": c} for c in ("VLO", "MPC")] + [
        {"name": "Paycom Software, Inc.", "ticker": "PAYC"}] + [{"name": c, "ticker": c} for c in ("QLYS", "HALO", "NTAP")]
    (tmp_path / "data" / "lab" / "ussx_qm_live.json").unlink()
    assert fund_intro.uncovered_us_qm() == []                                             # 沒有紀錄＝沒有缺口


def test_intro_gap_chip_含美股三成(tmp_path, monkeypatch):
    from arm import fund_dashboard as fd
    (tmp_path / "data").mkdir()
    fp = tmp_path / "data" / "holdings_intro_gap.json"
    monkeypatch.setattr(fd, "ROOT_DIR", tmp_path)
    fp.write_text(json.dumps({"count": 2, "items": [{"src": "etf", "name": "玉晶光"}, {"src": "usqm", "name": "PAYC"}]}),
                  encoding="utf-8")
    chip = fd._intro_gap_chip()
    assert "<b>持股簡介</b>" in chip and "ETF 持股 1・美股三成 1" in chip
    fp.write_text(json.dumps({"count": 1, "items": [{"src": "usqm", "name": "PAYC"}]}), encoding="utf-8")
    assert "美股三成；PAYC" in fd._intro_gap_chip()
