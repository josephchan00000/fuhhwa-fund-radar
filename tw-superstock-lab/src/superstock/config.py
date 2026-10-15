"""設定檔與環境變數讀取。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class FinMindConfig:
    api_url: str = "https://api.finmindtrade.com/api/v4/data"
    user_info_url: str = "https://api.web.finmindtrade.com/v2/user_info"
    token_env: str = "FINMIND_TOKEN"
    requests_per_hour: int = 600
    safety_margin: float = 0.92
    min_interval_sec: float = 1.0
    timeout_sec: int = 60
    max_retries: int = 6
    rate_limit_wait_sec: int = 600


@dataclass
class UniverseConfig:
    markets: list[str] = field(default_factory=lambda: ["twse", "tpex"])
    include_delisted: bool = True
    stock_id_pattern: str = r"^[1-9][0-9]{3}$"


@dataclass
class Config:
    start_date: str = "2008-01-01"
    data_dir: Path = Path("data")
    reports_dir: Path = Path("reports")
    finmind: FinMindConfig = field(default_factory=FinMindConfig)
    universe: UniverseConfig = field(default_factory=UniverseConfig)
    download_groups: list[str] = field(default_factory=lambda: ["meta", "core", "events"])

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def manifest_path(self) -> Path:
        return self.data_dir / "manifest.sqlite"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"


def _merge_dataclass(obj: Any, values: dict[str, Any]) -> None:
    for key, value in (values or {}).items():
        if not hasattr(obj, key):
            raise ValueError(f"config.yaml 有未知設定：{key}")
        setattr(obj, key, value)


def load_config(path: str | Path | None = None) -> Config:
    """讀取 config.yaml；檔案不存在時使用預設值。"""
    cfg = Config()
    cfg_path = Path(path) if path else Path("config.yaml")
    if not cfg_path.exists():
        return cfg
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    base_dir = cfg_path.parent
    for key, value in raw.items():
        if key == "finmind":
            _merge_dataclass(cfg.finmind, value)
        elif key == "universe":
            _merge_dataclass(cfg.universe, value)
        elif key in ("data_dir", "reports_dir"):
            p = Path(value)
            setattr(cfg, key, p if p.is_absolute() else base_dir / p)
        elif hasattr(cfg, key):
            setattr(cfg, key, value)
        else:
            raise ValueError(f"config.yaml 有未知設定：{key}")
    return cfg


def _read_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def get_token(cfg: Config, dotenv_path: str | Path = ".env") -> str:
    """環境變數優先，其次讀 .env。永遠不要把 token 印出來或寫進 log。"""
    token = os.environ.get(cfg.finmind.token_env, "").strip()
    if token:
        return token
    return _read_dotenv(Path(dotenv_path)).get(cfg.finmind.token_env, "").strip()
