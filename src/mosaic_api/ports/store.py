"""Keeps the harvested resources between runs. No database: files are enough today."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from ..domain.model import Resource


@dataclass(frozen=True)
class SourceState:
    id: str
    name: str
    homepage: str | None
    format: str
    harvested_at: datetime | None
    records: int
    issues: dict[str, list[str]] = field(default_factory=dict)  # local id -> translation issues
    error: str | None = None


@dataclass(frozen=True)
class Snapshot:
    resources: list[Resource]
    sources: list[SourceState]
    standard_version: str
    harvested_at: datetime | None
    extra: dict[str, Any] = field(default_factory=dict)


class SnapshotStore(Protocol):
    def load(self) -> Snapshot | None: ...

    def save(self, snapshot: Snapshot) -> None: ...
