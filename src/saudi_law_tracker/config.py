"""Runtime settings and source-registry loading."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "sources.yaml"


class Settings(BaseSettings):
    """Process-wide configuration, overridable via environment or .env."""

    model_config = SettingsConfigDict(
        env_prefix="SLT_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    data_dir: Path = PROJECT_ROOT / "data"
    http_timeout: float = 30.0
    http_max_retries: int = 4
    http_user_agent: str = "saudi-law-tracker/0.1 (+research)"
    request_delay: float = 2.0
    max_concurrency: int = 4
    log_level: str = "INFO"
    notify_webhook_url: str | None = None

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def state_dir(self) -> Path:
        return self.data_dir / "state"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "regulations.db"

    def ensure_dirs(self) -> None:
        for d in (self.raw_dir, self.state_dir):
            d.mkdir(parents=True, exist_ok=True)


class SourceConfig(BaseModel):
    """One entry from config/sources.yaml."""

    key: str
    name: str
    name_ar: str | None = None
    scraper: str
    enabled: bool = True
    base_url: str
    start_paths: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    request_delay: float = 2.0
    timeout: float = 30.0
    max_retries: int = 4
    language: str = "ar"
    extra: dict[str, Any] = Field(default_factory=dict)


def load_sources(path: Path | None = None) -> list[SourceConfig]:
    """Parse the source registry, folding `defaults` into each entry."""

    path = path or DEFAULT_CONFIG_PATH
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    defaults: dict[str, Any] = data.get("defaults", {})
    sources: list[SourceConfig] = []
    for raw in data.get("sources", []):
        known = set(SourceConfig.model_fields)
        merged = {**defaults, **{k: v for k, v in raw.items() if k in known}}
        merged["extra"] = {k: v for k, v in raw.items() if k not in known}
        sources.append(SourceConfig.model_validate(merged))
    return sources


@lru_cache
def get_settings() -> Settings:
    return Settings()
