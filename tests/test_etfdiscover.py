"""新 ETF 自動發現（arm/etfdiscover）測試——離線、純函式，不打任何網路。

守的是 2026-08-10 使用者問的「你是怎麼確保之後都抓得到的呢？」：既有守門只認得
已登錄條目，這層負責讓「從沒登錄過的檔」也會現形。
"""
import json
from datetime import date

from arm import etfdiscover, fund_dashboard


# ── 代碼樣式 ─────────────────────────────────────────────────

def test_is_etf_code_covers_all_shapes_and_rejects_others():
    for ok in ("0050", "0056", "00878", "006208", "009827", "009829",
               "00991A", "00986D", "00411A", "00679B"):
        assert etfdiscover.is_etf_code(ok), ok
    # 個股（1101~9958）／ETN（02 開頭）／權證（03~08 開頭）／空值一律不是 ETF
    for no in ("2330", "1101", "020019", "030001", "089999", "", None, "TSM", "00", "001234567"):
        assert not etfdiscover.is_etf_code(no), no


# ── 首見台帳：baseline 與新檔偵測 ────────────────────────────

def _mkt(n: int) -> dict[str, str]:
    """n 檔唯一的合法 ETF 代碼（006000 起遞增，6 碼、00 開頭）。"""
    return {f"00{6000 + i}": f"既有{i}" for i in range(n)}


def test_first_build_is_baseline_and_reports_nothing():
    """首次建帳：市場上 200+ 檔既有 ETF 一次認列 baseline（first=None）、不報缺口——
    否則第一輪就會噴出整個市場，警示直接變雜訊。"""
    market = _mkt(150)
    seen, fresh = etfdiscover.merge_seen({"codes": {}}, market, date(2026, 8, 10))
    assert fresh == []
    assert all(v["first"] is None for v in seen["codes"].values())
    assert seen["seeded"] == "2026-08-10"
    assert etfdiscover.listed_gaps(seen, known=set(), today=date(2026, 8, 10)) == []


def test_baseline_refused_when_market_looks_partial():
    """首建那輪若單邊交易所掛掉（2026-08-05 tpex openapi 曾整輪失敗），baseline 只會含
    半個市場 → 隔天另一半全被誤判成新掛牌。檔數不足就不建帳，下一輪再說。"""
    partial = _mkt(20)
    seen, fresh = etfdiscover.merge_seen({"codes": {}}, partial, date(2026, 8, 10))
    assert seen["codes"] == {} and fresh == []                 # 沒建帳
    # 下一輪拿到完整市場才建，且此時既有檔仍全是 baseline、不報缺口
    seen2, fresh2 = etfdiscover.merge_seen(seen, _mkt(150), date(2026, 8, 11))
    assert fresh2 == [] and len(seen2["codes"]) == 150
    assert etfdiscover.listed_gaps(seen2, set(), date(2026, 8, 11)) == []


def test_new_code_after_baseline_becomes_gap():
    """baseline 之後才出現的代碼＝真的新掛牌 → 不在清單裡就報缺口。"""
    seen = {"codes": {"0050": {"first": None, "name": "元大台灣50"}}, "seeded": "2026-07-01"}
    seen2, fresh = etfdiscover.merge_seen(
        seen, {"0050": "元大台灣50", "009829": "大華銀韓國KOSPI50"}, date(2026, 8, 21))
    assert fresh == ["009829"]
    assert seen2["codes"]["009829"]["first"] == "2026-08-21"
    assert seen2["codes"]["0050"]["first"] is None              # 既有檔首見日不被改寫
    gaps = etfdiscover.listed_gaps(seen2, known={"0050"}, today=date(2026, 8, 21))
    assert [g["code"] for g in gaps] == ["009829"]
    assert gaps[0]["name"] == "大華銀韓國KOSPI50" and gaps[0]["kind"] == "listed"
    # 已登錄（含 track:False 的展示檔）就不再是缺口
    assert etfdiscover.listed_gaps(seen2, {"0050", "009829"}, date(2026, 8, 21)) == []


def test_listed_gap_expires_after_discover_days():
    """掛牌逾 DISCOVER_DAYS 還沒登錄＝策展決定（不是每檔新 ETF 都要追），不再一直紅。"""
    seen = {"codes": {"009900": {"first": "2026-06-01", "name": "舊的新檔"}}}
    assert etfdiscover.listed_gaps(seen, set(), date(2026, 8, 10), days=60) == []
    assert len(etfdiscover.listed_gaps(seen, set(), date(2026, 7, 20), days=60)) == 1


def test_unreachable_sources_leave_ledger_untouched():
    """本容器 proxy 擋 twse/tpex → market 空：台帳原封不動、不誤把既有檔當新檔。"""
    seen = {"codes": {"0050": {"first": None, "name": "x"}}, "seeded": "2026-07-01"}
    out, fresh = etfdiscover.merge_seen(seen, {}, date(2026, 8, 10))
    assert fresh == [] and out["codes"] == seen["codes"]


def test_name_backfill_does_not_touch_first_seen():
    seen = {"codes": {"00929": {"first": "2026-08-01", "name": ""}}}
    out, fresh = etfdiscover.merge_seen(seen, {"00929": "復華台灣科技優息"}, date(2026, 8, 10))
    assert fresh == [] and out["codes"]["00929"]["first"] == "2026-08-01"
    assert out["codes"]["00929"]["name"] == "復華台灣科技優息"


# ── 募集頁前瞻層 ─────────────────────────────────────────────

def test_parse_offering_codes_respects_word_boundary():
    html = ('<td>009827</td><td>00411A</td><a href="/x?id=00987D">x</a>'
            '<span>1000988</span><span>abc00500def</span>')
    got = etfdiscover.parse_offering_codes(html)
    assert got == {"009827", "00411A", "00987D"}          # 長數字串中間不切出假代碼


def test_offering_gaps_filters_already_listed_and_known():
    """交叉條件（本層的核心）：募集中的新 ETF 還沒掛牌 → 不在市場台帳裡。
    既有 ETF 的參照連結會被『已掛牌』差集濾掉，所以版式再漂移也不會誤報一堆。"""
    seen = {"codes": {"0050": {"first": None}, "00878": {"first": None}}}
    offering = {"0050", "00878", "009827", "00413A"}      # 前兩個是頁面上的既有 ETF 連結
    gaps = etfdiscover.offering_gaps(offering, seen, known={"009827"})
    assert [g["code"] for g in gaps] == ["00413A"]
    assert gaps[0]["kind"] == "offering"


# ── 名稱型前瞻（鉅亨 IPO 頁，2026-08-10 使用者提供）──────────

def test_norm_name_aligns_cnyes_and_registry_styles():
    """兩邊寫法不同、核心一致：cnyes 全名 vs 登錄短名要正規化到同一字串。"""
    assert etfdiscover._norm_name("統一前沿科技主動式ETF基金") == "統一前沿科技"
    assert etfdiscover._norm_name("主動統一前沿科技") == "統一前沿科技"
    assert etfdiscover._norm_name(
        "玉山未來全球算力ETF基金(本基金之配息來源可能為收益平準金)") == "玉山未來全球算力"
    assert etfdiscover._norm_name("大華銀優利美國非投資等級債券ETF") == "大華銀優利美國非投資等級債券"
    # 泛稱標籤核心 <4 字：extract 端會丟掉、name_match 也不比
    assert not etfdiscover.name_match(etfdiscover._norm_name("台股ETF"), "台股什麼都好")


def test_extract_etf_names_is_layout_agnostic():
    """HTML 表格與內嵌 JSON 都吃得到；泛稱標籤（核心 <4 字）不收；括注剝除；去重。"""
    html = ('<td>安聯加密科技與金融創新主動式ETF基金</td>'
            '"displayNameLocal":"統一前沿科技主動式ETF基金(本基金之配息來源可能為收益平準金)"'
            '<a>台股ETF</a><a>高股息ETF</a>'
            '<span>統一前沿科技主動式ETF基金</span>')          # 重複 → 去重
    names = etfdiscover.extract_etf_names(html)
    assert names == ["安聯加密科技與金融創新主動式ETF基金", "統一前沿科技主動式ETF基金"]


def test_extract_keeps_leading_digits_and_drops_english_fragments():
    """2026-08-10 CI 首輪修正：原本限定 CJK 起頭 →「10年期AAA…」的 10 被切掉、
    名稱殘缺成「年期AAA至A級美元公司債券ETF基金」對不上任何清單而誤報。"""
    html = '<td>國泰10年期以上AAA至A級美元公司債券ETF基金</td><span>iShares ETF</span><b>AI ETF</b>'
    names = etfdiscover.extract_etf_names(html)
    assert names == ["國泰10年期以上AAA至A級美元公司債券ETF基金"]   # 純英文/泛稱片段不收


def test_name_match_handles_exchange_abbreviations():
    """交易所短名是全名的縮寫、中間跳字 → 必須用子序列比對，否則同一檔被判成兩檔
    （2026-08-10 CI 首輪實例：0052 富邦科技、00410A 永豐科技趨勢 雙雙誤報）。"""
    nm = etfdiscover._norm_name
    assert etfdiscover.name_match(nm("富邦科技"), nm("富邦台灣科技指數ETF"))
    assert etfdiscover.name_match(nm("主動永豐科技趨勢"), nm("永豐台灣科技趨勢主動式ETF基金"))
    # 但不可過度合併：同投信的不同檔仍須判為相異
    assert not etfdiscover.name_match(nm("群益台灣精選高息"), nm("群益台灣核心50主動式ETF基金"))
    assert not etfdiscover.name_match(nm("主動復華未來50"), nm("復華台美策略精準高息股債平衡ETF基金"))
    assert not etfdiscover.name_match(nm("復華台灣科技優息"), nm("復華台美策略精準高息股債平衡ETF基金"))


def test_offering_name_gaps_filters_known_and_listed():
    """交叉條件（名稱空間版）：已登錄（含 hint 條目）與已掛牌（台帳名，擋既有 ETF
    廣告連結）都濾掉，只留真正沒人知道的新募集檔。"""
    seen = {"codes": {"00929": {"first": None, "name": "復華台灣科技優息"}}}
    knowns = {etfdiscover._norm_name("主動統一前沿科技"),
              etfdiscover._norm_name("安聯加密科技與金融創新主動式ETF")}
    raw = ["統一前沿科技主動式ETF基金",            # 已登錄 → 濾
           "安聯加密科技與金融創新主動式ETF基金",  # 已登錄（hint、未派碼）→ 濾
           "復華台灣科技優息ETF基金",              # 已掛牌（台帳名）→ 濾
           "野村神祕新兵主動式ETF基金"]            # 真缺口
    gaps = etfdiscover.offering_name_gaps(raw, seen, knowns)
    assert [g["name"] for g in gaps] == ["野村神祕新兵主動式ETF基金"]
    assert gaps[0]["code"] is None and gaps[0]["src"] == "cnyes"


def test_known_names_covers_watchlist_and_codeless_upcoming():
    kn = etfdiscover.known_names()
    assert etfdiscover._norm_name("復華台灣科技優息") in kn           # WATCHLIST
    assert etfdiscover._norm_name("大華銀優利美國非投資等級債券ETF") in kn  # 未派碼 hint 條目


# ── 落檔防呆與儀表板紅章 ─────────────────────────────────────

def test_save_gap_never_writes_when_sources_down(tmp_path, monkeypatch):
    """來源整批不可達時「不覆寫」也「不新建」（2026-08-10 實跑抓到的 bug）：
    · 覆寫會把 CI 抓到的真缺口洗成 0（同 factcheck.json 2026-07-29 的坑）；
    · 新建會把「沒檢查」寫成「0 缺口 🟢」並 commit 進去＝靜默失敗。"""
    fp = tmp_path / "etf_upcoming_gap.json"
    monkeypatch.setattr(etfdiscover, "GAP_FP", fp)
    _p, saved = etfdiscover.save_gap([], sources_ok=False)             # 無既有檔也不建
    assert saved is False and not fp.exists()
    etfdiscover.save_gap([{"code": "00413A", "name": "", "first_seen": None,
                           "kind": "offering"}], sources_ok=True)
    assert etfdiscover.load_gap()["count"] == 1
    _p, saved = etfdiscover.save_gap([], sources_ok=False)
    assert saved is False and etfdiscover.load_gap()["count"] == 1     # 舊缺口保住
    etfdiscover.save_gap([], sources_ok=True)                          # 真的檢查過才歸零
    assert etfdiscover.load_gap()["count"] == 0


def test_new_etf_chip_shows_only_when_gap(tmp_path, monkeypatch):
    fp = tmp_path / "gap.json"
    monkeypatch.setattr(etfdiscover, "GAP_FP", fp)
    assert fund_dashboard._new_etf_chip() == ""                        # 無檔＝不顯示
    fp.write_text(json.dumps({"count": 0, "items": []}), encoding="utf-8")
    assert fund_dashboard._new_etf_chip() == ""                        # 0 缺口＝不顯示
    fp.write_text(json.dumps({"count": 1, "items": [
        {"code": "00413A", "name": "主動測試", "kind": "listed"}]}), encoding="utf-8")
    chip = fund_dashboard._new_etf_chip()
    assert "🔴" in chip and "00413A" in chip and "新 ETF 未登錄" in chip and "stale" in chip


def test_known_codes_includes_watchlist_and_upcoming():
    """已登錄＝追蹤清單＋UPCOMING（含 track:False 展示檔與已升級檔），未派碼條目跳過。"""
    known = etfdiscover.known_codes()
    assert {"0050", "00991A", "00409A", "009829"} <= known      # 追蹤＋前瞻＋展示檔都算已知
    assert all(c for c in known)                                # 不含 None（未派碼 hint 條目）
