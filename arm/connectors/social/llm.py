"""Claude 逐則深析（M4-3）—— social.analyze(m, llm=) 的 LLM callable（Anthropic SDK）。

把確定性 baseline 升級為 Claude 深析：情緒、賣點萃取、疑似業配（附理由）、**可借用說法**、
**套用到復華的改法**、一句話摘要。用結構化輸出（output_config.format）確保可解析。

gated on ANTHROPIC_API_KEY；未設或未安裝 anthropic → available()=False、不啟用（baseline 照常）。
模型預設 claude-opus-4-8（最新最強；使用者未另指定）。回傳 dict 併入 baseline，呼叫端不變。
合規：仍是行銷素材判讀；業配為「疑似・推估」，不對外指控。
"""
from __future__ import annotations

import json
import os

MODEL = "claude-opus-4-8"

_SCHEMA = {
    "type": "object",
    "properties": {
        "sentiment": {"type": "string", "enum": ["正面", "負面", "中性"]},
        "selling_points": {"type": "array", "items": {"type": "string"}},
        "suspected_ad": {"type": "boolean"},
        "ad_reason": {"type": "string"},
        "reusable_phrasing": {"type": "string"},
        "fh_adaptation": {"type": "string"},
        "summary": {"type": "string"},
    },
    "required": ["sentiment", "selling_points", "suspected_ad", "ad_reason",
                 "reusable_phrasing", "fh_adaptation", "summary"],
    "additionalProperties": False,
}

_SYS = (
    "你是復華投信的行銷情報分析師。逐則分析社群/新聞對 ETF 的提及，輸出 JSON："
    "sentiment（對該檔的情緒）；selling_points（文中觸及的賣點，繁中短語）；"
    "suspected_ad（是否疑似業配/合作/邀稿）與 ad_reason（依據，無則寫『無明顯業配訊號』）；"
    "reusable_phrasing（可借用的說法，一句）；fh_adaptation（套用到復華主動式ETF的改法，一句）；"
    "summary（一句話摘要）。業配僅為『疑似・推估』判讀，不是指控。只依文本，勿杜撰數字。"
)


def available() -> bool:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def claude_analyzer(model: str = MODEL):
    """回傳 analyze() 用的 llm callable：(mention, baseline) -> dict（併入 baseline）。

    未設金鑰/未安裝 SDK → 回 None（呼叫端據此略過、用 baseline）。
    """
    if not available():
        return None
    import anthropic

    client = anthropic.Anthropic()

    def _llm(m, baseline: dict) -> dict:
        content = (f"平台：{m.platform}\n作者：{m.author}\n日期：{m.date}\n"
                   f"提及ETF：{', '.join(m.etfs) or '（泛論）'}\n內容：{m.text}")
        try:
            resp = client.messages.create(
                model=model, max_tokens=1024, system=_SYS,
                messages=[{"role": "user", "content": content}],
                output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
            )
            text = next((b.text for b in resp.content if b.type == "text"), "")
            data = json.loads(text)
        except Exception:
            return {}                          # 失敗→保留 baseline，誠實降級
        return {
            "sentiment": data.get("sentiment", baseline.get("sentiment")),
            "selling_points": data.get("selling_points") or baseline.get("selling_points", []),
            "suspected_ad": bool(data.get("suspected_ad", baseline.get("suspected_ad"))),
            "llm": True,
            "llm_ad_reason": data.get("ad_reason", ""),
            "llm_reusable_phrasing": data.get("reusable_phrasing", ""),
            "llm_fh_adaptation": data.get("fh_adaptation", ""),
            "llm_summary": data.get("summary", ""),
        }

    return _llm
