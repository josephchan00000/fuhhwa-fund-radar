"""社群/KOL 情報層單元測試（M4）：source-agnostic、確定性 baseline 分析、drop-in 承接。
2026-11-01 拿掉舊的本機流程（arm/ideas.py 的 g_kol 兩個測試一起拿掉）；臉書抓取留著，這裡測它用到的 base。"""
import json

from arm.connectors import social
from arm.connectors.social import base


def _m(**kw):
    d = {"platform": "youtube", "author": "KOL", "date": "2026-06-11", "text": "", "reach": 0}
    d.update(kw)
    return base.SocialMention(**d)


def test_analyze_selling_points_and_sentiment():
    a = base.analyze(_m(text="這檔主動式ETF主動度高、季配息殖利率不錯，值得長期佈局"))
    assert "主動選股" in a["selling_points"] and "配息入息" in a["selling_points"]
    assert a["sentiment"] == "正面"


def test_analyze_detects_suspected_ad():
    a = base.analyze(_m(text="今年績效贏0050（本影片與廠商合作、業配）"))
    assert a["suspected_ad"] is True
    assert "業配" in a["ad_terms"] and "合作" in a["ad_terms"]
    assert "績效贏大盤" in a["selling_points"]


def test_analyze_negative_and_reach_bucket():
    a = base.analyze(_m(text="費用率偏高又集中科技股，怕套牢，這價位太貴", reach=800))
    assert a["sentiment"] == "負面" and a["reach_bucket"] == "低"
    assert base.analyze(_m(reach=52000))["reach_bucket"] == "高"


def test_analyze_llm_hook_can_override():
    a = base.analyze(_m(text="主動選股"), llm=lambda m, base_r: {"sentiment": "正面(LLM)"})
    assert a["sentiment"] == "正面(LLM)"            # 預留的 LLM 接口可覆蓋 baseline


def test_curated_mentions_window_and_skip_underscore(tmp_path, monkeypatch):
    monkeypatch.setattr(base, "DROP_DIR", tmp_path)
    (tmp_path / "2026-06-12.json").write_text(json.dumps({"mentions": [
        {"platform": "ptt", "author": "A", "date": "2026-06-11", "text": "主動", "etfs": ["00991A"], "reach": 10},
        {"platform": "ptt", "author": "B", "date": "2026-05-01", "text": "太舊", "reach": 5},  # 窗外
    ]}), encoding="utf-8")
    (tmp_path / "_SAMPLE.json").write_text(json.dumps([{"platform": "x", "author": "ZZ", "date": "2026-06-12", "text": "不該載入"}]), encoding="utf-8")
    got = base.curated_mentions(as_of="2026-06-12", window_days=7)
    authors = {m.author for m in got}
    assert authors == {"A"}                          # B 窗外、_SAMPLE 不載入


def test_recent_mentions_merges_live_adapter(monkeypatch):
    monkeypatch.setattr(base, "DROP_DIR", base.DROP_DIR)  # 真實 drop-in 不影響
    monkeypatch.setitem(social.LIVE_ADAPTERS, "fake",
                        lambda a, w: [_m(author="LIVE", date="2026-06-12", reach=999999)])
    out = social.recent_mentions(as_of="2026-06-12", window_days=7)
    assert out and out[0].author == "LIVE"           # 聲量最高排最前、live 來源有被併入
    social.LIVE_ADAPTERS.pop("fake", None)
