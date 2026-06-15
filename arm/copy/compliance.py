"""文案合規（M6 設計決策 ③）—— 兩層、皆不擋。

第一層「規則層」：讀 config/compliance.(yaml|json) 的關鍵字/條件，標注命中規則、
需補的揭露語與建議改法。第二層「LLM 語意層」由 `llm.py` 在有 callable 時加碼補強。
**兩層都只標注、永不阻擋、永不丟例外**（先發揮、事後標注；發布前法遵複核）。

規則外部化（不再寫死在 ideas.py）：行銷/法遵可直接改 yaml，不動程式碼。
雲端（無 PyYAML）自動退讀 compliance.json。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

CFG = Path(__file__).resolve().parents[2] / "config"
SEV_EMOJI = {"高": "🔴", "中": "🟡", "低": "🟢"}
_NEG = ("非", "不", "無", "未", "免")          # 「非保證／不保證」等揭露語 ≠ 違規


def _violates(text: str, kw: str) -> bool:
    """kw 是否以「非揭露語」形式出現（排除『非保證』這類免責用法）；大小寫不敏感。"""
    t, k = text.lower(), kw.lower()
    i = t.find(k)
    while i != -1:
        if (t[i - 1] if i > 0 else "") not in _NEG:
            return True
        i = t.find(k, i + 1)
    return False


@dataclass(frozen=True)
class Flag:
    rule_id: str
    severity: str          # 高/中/低
    name: str
    hit: str               # 命中的關鍵字
    fix: str
    disclosures: tuple = ()   # 需補的揭露語（已展開成句子）

    @property
    def emoji(self) -> str:
        return SEV_EMOJI.get(self.severity, "⚠️")

    def render(self) -> str:
        d = ("；須補：" + "、".join(self.disclosures)) if self.disclosures else ""
        return f"{self.emoji}合規[{self.severity}] {self.name}（命中「{self.hit}」）→ {self.fix}{d}"


@lru_cache(maxsize=1)
def _load() -> dict:
    """有 PyYAML 讀 yaml（人類可讀來源），否則退讀 json（雲端）。讀檔失敗 → 空規則（不擋）。"""
    yml, js = CFG / "compliance.yaml", CFG / "compliance.json"
    try:
        import yaml  # type: ignore
        if yml.exists():
            return yaml.safe_load(yml.read_text(encoding="utf-8")) or {}
    except Exception:
        pass
    try:
        return json.loads(js.read_text(encoding="utf-8"))
    except Exception:
        return {"disclosures": {}, "rules": []}


def annotate(text: str) -> list[Flag]:
    """規則層：回傳文本命中的合規旗標（不擋、不丟例外）。"""
    cfg = _load()
    disc = cfg.get("disclosures") or {}
    flags: list[Flag] = []
    for rule in cfg.get("rules") or []:
        try:
            anys = rule.get("any") or []
            unless = rule.get("unless") or []
            if any(u in text for u in unless):
                continue
            # 命中＝關鍵字至少一次以「非揭露語」形式出現（『非保證』不算違規）
            hit = next((k for k in anys if _violates(text, k)), None)
            if hit is None:
                continue
            flags.append(Flag(
                rule_id=rule.get("id", ""), severity=rule.get("severity", "低"),
                name=rule.get("name", ""), hit=hit, fix=rule.get("fix", ""),
                disclosures=tuple(disc.get(d, d) for d in (rule.get("disclosure") or [])),
            ))
        except Exception:
            continue                              # 單一規則壞掉不影響其他（不擋）
    return flags


def required_disclosures(flags: list[Flag]) -> list[str]:
    """彙整所有旗標需補的揭露語（去重、保留順序）。"""
    out: list[str] = []
    for f in flags:
        for d in f.disclosures:
            if d not in out:
                out.append(d)
    return out
