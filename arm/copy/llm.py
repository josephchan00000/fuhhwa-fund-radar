"""自動 API 路（M6 設計決策 ①：可注入 llm=）—— 用 Claude 把基線稿升級為潤飾稿。

雙路之一（自動）：有 ANTHROPIC_API_KEY 時回傳 callable，呼叫 Anthropic SDK 產四通路潤稿；
預設走 prompt-pack（手動、免 key，見 prompt_pack.py）。兩路回傳同形狀 dict，呼叫端不變。

硬規則：**只能使用「可用數字」清單內的數字，不得新增任何數字**（提示 + 事後 numbers.check 把關）。
模型預設 claude-opus-4-8（最新最強）。失敗一律回 {} → 誠實降級回基線稿。
"""
from __future__ import annotations

import json
import os

MODEL = "claude-opus-4-8"

_SCHEMA = {
    "type": "object",
    "properties": {
        "punchy": {"type": "string"},
        "line": {"type": "string"},
        "ig": {"type": "string"},
        "sales": {"type": "string"},
    },
    "required": ["punchy", "line", "ig", "sales"],
    "additionalProperties": False,
}

_SYS = (
    "你是復華投信的資深文案。把基線稿潤飾成更有渲染力的四通路文案"
    "（punchy 一句 hook、line 推播短文、ig 社群貼文、sales 理專話術）。"
    "嚴格規則：(1) **只能使用我提供的「可用數字」清單內的數字，禁止出現任何其他數字或自創數據**；"
    "(2) 不得使用保證/穩賺/零風險等絕對化字眼；(3) 績效/配息訴求語氣保守，揭露語系統會另外補。"
    "只回 JSON。"
)


def available() -> bool:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def auto_analyzer(model: str = MODEL):
    """回傳 generate() 用的 llm callable：(idea, base, allowed) -> {channel: text}。

    未設金鑰/未裝 SDK → 回 None（呼叫端據此略過、用基線稿）。
    """
    if not available():
        return None
    import anthropic

    client = anthropic.Anthropic()

    def _llm(idea, base: dict, allowed: set[str]) -> dict:
        nums = "、".join(sorted(allowed)) or "（無）"
        user = (f"面向：{idea.category}\n想法：{idea.headline}\n佐證：{idea.evidence}\n"
                f"可用數字（只准用這些）：{nums}\n\n基線稿：\n"
                + "\n".join(f"[{k}] {v}" for k, v in base.items()))
        try:
            resp = client.messages.create(
                model=model, max_tokens=1500, system=_SYS,
                messages=[{"role": "user", "content": user}],
                output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
            )
            text = next((b.text for b in resp.content if b.type == "text"), "")
            data = json.loads(text)
        except Exception:
            return {}                              # 失敗→保留基線稿
        return {k: data[k] for k in ("punchy", "line", "ig", "sales") if data.get(k)}

    return _llm
