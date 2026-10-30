"""Configuration (config/mosaic-api.yaml), validated with Pydantic. Paths are relative to the file.

Environment overrides: MOSAIC_API_CONFIG (config file path).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "mosaic-api.yaml"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceConfig(Strict):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{1,30}$")
    name: str
    type: Literal["mosaic_catalog", "git_yaml"]
    translator: Literal["mosaic", "cdh"]
    location: str
    homepage: str | None = None
    format: str
    ref: str = "main"
    pattern: str = "records/*/*.yaml"
    record_url_template: str | None = None
    enabled: bool = True


class HttpConfig(Strict):
    cors_origins: list[str] = Field(default_factory=list)
    max_page_size: int = Field(100, ge=1, le=1000)
    expose_emails: bool = True


class Settings(Strict):
    standard: str = Field(description="Folder or https URL of the published MOSAIC standard (mosaic-catalog dist).")
    state: str = "state/snapshot.json"
    export_dir: str = "site"
    allowed_hosts: list[str]
    max_download_mb: int = 50
    sources: list[SourceConfig]
    http: HttpConfig = HttpConfig()

    base_dir: Path = Path(".")

    def resolve(self, value: str) -> str:
        if value.startswith(("http://", "https://")):
            return value
        return str((self.base_dir / value).resolve())


def load_settings(path: Path | None = None) -> Settings:
    path = path or Path(os.environ.get("MOSAIC_API_CONFIG", DEFAULT_CONFIG))
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Settings(**raw, base_dir=path.parent.resolve())
