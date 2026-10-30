"""Ports: the interfaces the application needs. Adapters implement them; the core only sees these."""

from .quality import QualityAssessor
from .sources import CatalogSource, RawRecord, SourceInfo
from .standard import StandardProvider
from .store import Snapshot, SnapshotStore
from .translator import TranslationResult, Translator

__all__ = [
    "CatalogSource",
    "QualityAssessor",
    "RawRecord",
    "Snapshot",
    "SnapshotStore",
    "SourceInfo",
    "StandardProvider",
    "TranslationResult",
    "Translator",
]
