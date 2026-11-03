"""Landscape profiles: one page per living landscape, published by mosaic-catalog (dist/landscapes/).

The profile document (sections and their configuration) is curated content: the API serves it as
published and only adds what it knows from the catalogue - which resources cover the landscape and
how complete their metadata is (the "data status" of the landscape). No I/O here.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from .facets import facet_values
from .model import Resource
from .text import key


@dataclass(frozen=True)
class LandscapeProfile:
    code: str
    document: Mapping[str, Any]  # dist/landscapes/<CODE>.json, as published

    @property
    def slug(self) -> str:
        return self.code.lower()

    def matches(self, code_or_slug: str) -> bool:
        return key(code_or_slug) == key(self.code)

    def sections(self) -> list[Mapping[str, Any]]:
        return [s for s in self.document.get("sections") or [] if isinstance(s, Mapping)]

    def referenced_records(self) -> list[str]:
        """Catalogue records (source:id) named anywhere in the sections' configuration."""
        return sorted(set(_records(self.sections())))


def _records(node: Any) -> Iterator[str]:
    if isinstance(node, Mapping):
        rec = node.get("record")
        if isinstance(rec, str) and ":" in rec:
            yield rec
        for v in node.values():
            yield from _records(v)
    elif isinstance(node, list):
        for v in node:
            yield from _records(v)


@dataclass(frozen=True)
class DataStatus:
    """What the catalogue holds for a landscape and how complete it is (a gap analysis)."""

    total: int
    complete: int
    incomplete: int
    stated: int  # resources that name the landscape (the rest are derived from their bounding box)
    by_kind: dict[str, int]
    by_theme: dict[str, int]
    by_access: dict[str, int]
    missing_minimum: dict[str, int]  # field -> number of resources missing it


def covering(code: str, resources: Iterable[Resource]) -> list[Resource]:
    return [r for r in resources if code in r.landscapes]


def data_status(code: str, resources: Iterable[Resource]) -> DataStatus:
    found = covering(code, resources)
    status = Counter(str(getattr(r.quality.status, "value", r.quality.status)) for r in found)
    kinds: Counter[str] = Counter()
    themes: Counter[str] = Counter()
    access: Counter[str] = Counter()
    missing: Counter[str] = Counter()
    for r in found:
        f = facet_values(r)
        kinds.update(f.get("data_kind", []))
        themes.update(f.get("theme", []))
        access.update(f.get("access", []))
        missing.update(r.quality.missing_minimum)
    return DataStatus(
        total=len(found),
        complete=status.get("complete", 0),
        incomplete=status.get("incomplete", 0),
        stated=sum(not r.landscapes_derived for r in found),
        by_kind=dict(kinds.most_common()),
        by_theme=dict(themes.most_common()),
        by_access=dict(access.most_common()),
        missing_minimum=dict(missing.most_common()),
    )
