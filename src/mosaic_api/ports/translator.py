"""Turns a source record into the MOSAIC model ("they speak our language")."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from ..domain.model import Resource
from ..domain.standard import Standard
from .sources import RawRecord, SourceInfo


@dataclass(frozen=True)
class TranslationResult:
    resource: Resource | None
    issues: list[str] = field(default_factory=list)  # values that could not be mapped (never silent)


class Translator(Protocol):
    def translate(
        self, raw: RawRecord, source: SourceInfo, standard: Standard, fetched_at: datetime
    ) -> TranslationResult: ...
