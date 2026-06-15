"""prompt-pack 手動路（M6 設計決策 ①，**預設、免 API key**）。

不接 Anthropic API key 時的 LLM 升級路：
  1. 系統把證據 + 可用數字 + 基線稿 + 規則 + 回傳格式，組成一份 prompt（write_prompt）。
  2. 你把 prompt 貼進**自己的 Claude**（claude.ai），複製回覆 JSON。
  3. 存成 responses/{date}_{etf}.json，跑 `gen_copy.py --ingest` → as_llm() 當 llm= 注入。

與自動 API 路同形狀 dict、共用 generate() 注入點；唯一差別是「人在迴圈」。
品質相同（同模型，甚至可用你訂閱的更強模型），但雲端無人值守時只能出基線稿、待你回灌。
數字防杜撰：prompt 明列可用數字、回灌後仍由 numbers.check 把關（不信任輸入）。
"""
from __future__ import annotations

import json
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parents[2] / "reports" / "copy" / "prompts"
RESP_DIR = Path(__file__).resolve().parents[2] / "reports" / "copy" / "responses"


def build_prompt(doc, ideas_with_allowed: list[tuple]) -> str:
    """組一份可直接貼進 Claude 的 prompt。

    ideas_with_allowed：[(Idea, base_channels: dict, allowed: set[str]), ...]
    """
    L = [
        f"# 復華文案潤飾任務 — {doc.name}（{doc.etf_id}） 資料日 {doc.date}",
        "",
        "你是復華投信資深文案。請把下列每一則想法的**基線稿**潤飾成更有渲染力的四通路文案：",
        "`punchy`（一句 hook）、`line`（LINE 推播短文）、`ig`（社群貼文，可含 hashtag）、`sales`（理專話術）。",
        "",
        "## 硬規則（務必遵守）",
        "1. **數字只能用每則列出的「可用數字」，禁止出現任何其他數字或自創數據**（系統會逐字檢查，違者標 🔴）。",
        "2. 不得使用「保證／穩賺／零風險／必賺」等絕對化字眼。",
        "3. 績效、配息訴求語氣保守；揭露語（免責）系統會自動補，你不必加。",
        "4. 只回**一段 JSON**，格式如下，鍵為想法編號字串：",
        "",
        "```json",
        '{ "ideas": { "1": {"punchy":"…","line":"…","ig":"…","sales":"…"}, "2": { … } } }',
        "```",
        "",
        "---",
        "",
    ]
    for idea, base, allowed in ideas_with_allowed:
        nums = "、".join(sorted(allowed)) or "（無數字，請勿出現任何數字）"
        L += [
            f"## 想法 {idea.idx}　〔{idea.category}〕 {idea.conf}",
            f"- 想法：{idea.headline}",
            f"- 佐證：{idea.evidence}",
            f"- ✅ 可用數字：{nums}",
            "- 基線稿：",
        ]
        for ch, txt in base.items():
            one = txt.replace("\n", " ⏎ ")
            L.append(f"    - [{ch}] {one}")
        L.append("")
    L += ["---", "完成後請只貼回上述 JSON。"]
    return "\n".join(L)


def write_prompt(doc, ideas_with_allowed: list[tuple]) -> Path:
    PROMPT_DIR.mkdir(parents=True, exist_ok=True)
    path = PROMPT_DIR / f"{doc.date}_{doc.etf_id}.md"
    path.write_text(build_prompt(doc, ideas_with_allowed), encoding="utf-8")
    return path


def response_path(doc) -> Path:
    return RESP_DIR / f"{doc.date}_{doc.etf_id}.json"


def load_response(path: str | Path) -> dict:
    """讀回灌的 JSON；容錯：吃 {"ideas":{...}} 或直接 {idx:{...}}。失敗回 {}。"""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(data, dict) and "ideas" in data:
        data = data["ideas"]
    return data if isinstance(data, dict) else {}


def as_llm(response: dict):
    """把回灌 JSON 包成 generate() 用的 llm callable：(idea, base, allowed) -> {channel: text}。"""
    def _llm(idea, base: dict, allowed: set[str]) -> dict:
        item = response.get(str(idea.idx)) or response.get(idea.idx)
        if not isinstance(item, dict):
            return {}
        return {k: item[k] for k in ("punchy", "line", "ig", "sales")
                if isinstance(item.get(k), str) and item[k].strip()}
    return _llm
