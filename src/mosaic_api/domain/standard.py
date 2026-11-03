"""The MOSAIC metadata standard as the domain sees it: vocabularies and crosswalks.

It is loaded from the standard published by mosaic-catalog (dist/vocab, dist/crosswalks) through a
port, so the API and the catalogue always use the same lists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .text import key


def slugify(text: str) -> str:
    return key(text)


@dataclass(frozen=True)
class Vocabulary:
    name: str
    labels: dict[str, str]  # id -> label
    extra: dict[str, dict[str, Any]] = field(default_factory=dict)  # id -> other attributes

    def __contains__(self, item: object) -> bool:
        return item in self.labels

    def label(self, concept_id: str) -> str:
        return self.labels.get(concept_id, concept_id)


@dataclass(frozen=True)
class Standard:
    version: str
    vocabularies: dict[str, Vocabulary]
    crosswalks: dict[str, dict[str, Any]]

    def vocab(self, name: str) -> Vocabulary:
        return self.vocabularies[name]

    def geography_by_slug(self) -> dict[str, str]:
        """Slug of each geography label -> MOSAIC id (e.g. 'latin-america-and-the-caribbean' -> 'm49:419')."""
        geo = self.vocab("geography")
        out = {slugify(label): gid for gid, label in geo.labels.items()}
        out["world"] = "global"
        return out

    def geography_by_m49(self) -> dict[str, str]:
        geo = self.vocab("geography")
        return {str(attrs["m49"]): gid for gid, attrs in geo.extra.items() if "m49" in attrs}
