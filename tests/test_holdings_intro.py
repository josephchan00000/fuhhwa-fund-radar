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
