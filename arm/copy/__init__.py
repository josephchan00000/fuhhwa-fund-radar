"""M6 文案層 —— 把每日想法報告轉成可用文案，LLM 可選、合規事後標注、數字不得杜撰。

設計決策（與隔壁徹底解耦：只讀 reports/*.md，不碰 pipeline/ideas/brokers/chips/etfinfo）：
  ① LLM-agnostic：baseline 模板恆可出稿；`llm=` 雙路可注入（自動 API / prompt-pack 手動）。
  ② 數字不得杜撰：可用數字 = 證據（想法+佐證+表頭）；文案內其他數字 → 標 🔴。
  ③ 合規兩層皆不擋：規則層（compliance.yaml）+ LLM 語意層；只標注、補揭露、不阻擋。
  ④ 防打架：全新 arm/copy/ + scripts/gen_copy.py，零既有檔編輯。

對外主要入口：`generate(idea, doc, llm=)`、`generate_doc(doc, llm=)`、`render_markdown(doc, results)`。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import baseline, compliance, llm as _llm_mod, numbers, parse, prompt_pack
from .compliance import Flag
from .parse import Idea, ReportDoc, latest_report, list_etf_ids, parse_file, parse_text

CONF_BADGE = {"🟢": "🟢", "🟡": "🟡", "🔴": "🔴"}


@dataclass
class ChannelCopy:
    channel: str
    text: str
    flags: list = field(default_factory=list)        # list[Flag]（規則層）
    fabricated: list = field(default_factory=list)   # 疑似杜撰數字
    source: str = "baseline"                          # baseline / llm

    @property
    def ok(self) -> bool:
        return not self.fabricated and not any(f.severity == "高" for f in self.flags)


@dataclass
class CopyResult:
    idea: Idea
    allowed: set
    channels: dict = field(default_factory=dict)     # {channel: ChannelCopy}


def default_llm():
    """雙路預設：有 ANTHROPIC_API_KEY → 自動 API callable；否則 None（走基線，prompt-pack 由 CLI 補）。"""
    return _llm_mod.auto_analyzer()


def generate(idea: Idea, doc: ReportDoc, llm=None) -> CopyResult:
    """單則想法 → 四通路文案（含合規標注與數字防杜撰）。"""
    allowed = numbers.allowed_set(idea.headline, idea.evidence, doc.header)
    # 識別碼（產品名數字、代號、0050 基準）非杜撰數據：放行檢查、但不列入顯示用「可用數字」。
    idents = numbers.extract(f"{doc.name} {doc.etf_id} 0050")
    check_set = allowed | idents
    base = baseline.render(idea, doc)

    overlay: dict[str, str] = {}
    if llm is not None:
        try:
            overlay = llm(idea, base, allowed) or {}
        except Exception:
            overlay = {}                              # LLM 壞掉→誠實降級回基線

    res = CopyResult(idea=idea, allowed=allowed)
    for ch in baseline.CHANNELS:
        core = overlay.get(ch) or base[ch]
        src = "llm" if overlay.get(ch) else "baseline"
        flags = compliance.annotate(core)
        disc = compliance.required_disclosures(flags)
        final = core + ("\n※ " + "；".join(disc)) if disc else core
        fabricated = numbers.check(final, check_set)
        res.channels[ch] = ChannelCopy(channel=ch, text=final, flags=flags,
                                       fabricated=fabricated, source=src)
    return res


def generate_doc(doc: ReportDoc, llm=None) -> list[CopyResult]:
    return [generate(i, doc, llm=llm) for i in doc.ideas]


# ───────────────────────── 報告渲染 ─────────────────────────
_CH_LABEL = {"punchy": "Hook", "line": "LINE 推播", "ig": "IG 貼文", "sales": "理專話術"}


def render_markdown(doc: ReportDoc, results: list[CopyResult]) -> str:
    used_llm = any(c.source == "llm" for r in results for c in r.channels.values())
    fab = sum(len(c.fabricated) for r in results for c in r.channels.values())
    sev_hi = sum(1 for r in results for c in r.channels.values()
                 for f in c.flags if f.severity == "高")
    mode = "Claude 潤稿" if used_llm else "baseline 模板（未接 LLM）"
    L = [
        f"# 每日文案 — {doc.name}（{doc.etf_id}）　資料日 {doc.date}",
        f"> 模式：{mode}　|　想法 {len(results)} 則　|　"
        f"疑似杜撰數字 {fab} 處{'（🔴需修）' if fab else '（✅0）'}　|　"
        f"禁用字眼 {sev_hi} 處",
        "",
    ]
    for r in results:
        idea = r.idea
        nums = "、".join(sorted(r.allowed)) or "—"
        L.append(f"### {idea.idx}. 〔{idea.category}〕{idea.conf}　{idea.headline}")
        L.append(f"*可用數字：{nums}*")
        for ch in baseline.CHANNELS:
            c = r.channels[ch]
            tag = "🟢" if c.source == "baseline" else "✨"
            body = c.text.replace("\n", "  \n      ")
            L.append(f"- **{_CH_LABEL[ch]}** {tag}")
            L.append(f"      {body}")
            if c.fabricated:
                L.append(f"      - 🔴 疑似杜撰數字（不在證據內）：{('、'.join(c.fabricated))} → 請刪除或改回證據數字")
            for f in c.flags:
                L.append(f"      - {f.render()}")
        L.append("")
    L.append("---")
    L.append("*文案層自動產出：合規為事後標注、**不阻擋**發想；數字僅取自當日證據，疑似杜撰者標 🔴。*")
    L.append("*發布前請由法遵複核；LLM 潤稿可走自動 API 或 prompt-pack（免 key）。*")
    return "\n".join(L)


__all__ = [
    "Idea", "ReportDoc", "Flag", "ChannelCopy", "CopyResult",
    "generate", "generate_doc", "render_markdown", "default_llm",
    "parse_text", "parse_file", "latest_report", "list_etf_ids",
    "baseline", "compliance", "numbers", "parse", "prompt_pack",
]
