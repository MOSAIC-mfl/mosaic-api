"""A catalogue MOSAIC reads from (MOSAIC itself, CDH, a STAC API, ...)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class SourceInfo:
    id: str  # short id used in global ids: mosaic, cdh, ...
    name: str
    homepage: str | None
    format: str  # the record format, e.g. mosaic-v0.2, cdh-yaml-v0.5


@dataclass(frozen=True)
class RawRecord:
    """A record exactly as the source gives it, plus what is needed to trace it back."""

    local_id: str
    data: dict[str, Any]
    sha256: str  # hash of the source bytes or canonical JSON: unchanged hash = nothing to redo
    record_url: str | None = None


class CatalogSource(Protocol):
    @property
    def info(self) -> SourceInfo: ...

    def records(self) -> Iterator[RawRecord]:
        """Every record of the catalogue. Implementations must be safe against untrusted input
        (size and time limits, allow-listed hosts, safe parsers)."""
        ...
