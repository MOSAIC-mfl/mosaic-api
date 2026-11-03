"""Search and filtering over resources: pure functions, same rules for the live API and for the
static export (the website applies the same rules in the browser to the exported index).

* text: accent- and case-insensitive; every word must appear (AND) in the searchable text
  (title, description, keywords, theme and geography labels, contact organizations, id);
* filters: OR inside one facet, AND across facets;
* bbox: the resource's box intersects the query box;
* years: the resource's period overlaps [year_from, year_to].
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from enum import Enum

from .facets import facet_values
from .model import Bbox, Resource
from .text import fold, key


class Sort(str, Enum):
    RELEVANCE = "relevance"
    TITLE = "title"
    UPDATED = "updated"
    YEAR = "year"

    @classmethod
    def _missing_(cls, value: object) -> Sort | None:  # "Title", " TITLE " -> Sort.TITLE
        folded = key(str(value))
        return next((m for m in cls if m.value == folded), None)


@dataclass(frozen=True)
class Query:
    text: str = ""
    filters: dict[str, frozenset[str]] = field(default_factory=dict)
    bbox: Bbox | None = None
    year_from: int | None = None
    year_to: int | None = None
    sort: Sort = Sort.RELEVANCE
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True)
class Page:
    items: list[Resource]
    total: int
    page: int
    page_size: int


def normalize(text: str) -> str:
    """Kept for callers of the first version; the rule lives in domain.text.fold."""
    return fold(text)


def searchable_text(r: Resource, label: Callable[[str, str], str]) -> str:
    """Everything a word search should find, normalized. ``label(vocab, id)`` gives labels."""
    parts: list[str] = [r.id, r.title, r.description or "", r.note or ""]
    parts += [k.term for k in r.keywords]
    parts += [label("themes", t) for t in r.themes]
    parts += [label("geography", g) for g in r.geography]
    parts += [label("landscapes", ls) for ls in r.landscapes]
    parts += [c.organization or "" for c in r.contacts]
    return normalize(" ".join(parts))


def _years(r: Resource) -> tuple[int | None, int | None]:
    if not r.temporal:
        return None, None
    start = int(r.temporal.start[:4]) if r.temporal.start else None
    end = int(r.temporal.end[:4]) if r.temporal.end else None
    return start, end


def _intersects(a: Bbox, b: Bbox) -> bool:
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def matches(r: Resource, q: Query, text: str) -> bool:
    words = normalize(q.text).split()
    if words and not all(w in text for w in words):
        return False
    values = facet_values(r)
    for facet, wanted in q.filters.items():
        if wanted and not {key(w) for w in wanted} & {key(v) for v in values.get(facet, [])}:
            return False
    if q.bbox is not None:
        boxes = r.spatial.bbox if r.spatial else ()
        if not any(_intersects(b, q.bbox) for b in boxes):
            return False
    if q.year_from is not None or q.year_to is not None:
        start, end = _years(r)
        if start is None and end is None:
            return False
        lo, hi = start or end, end or 9999
        if q.year_from is not None and hi < q.year_from:
            return False
        if q.year_to is not None and lo is not None and lo > q.year_to:
            return False
    return True


def score(r: Resource, q: Query) -> int:
    words = normalize(q.text).split()
    title = normalize(r.title)
    keywords = normalize(" ".join(k.term for k in r.keywords))
    return sum(3 * (w in title) + 2 * (w in keywords) + 1 for w in words)


def run(resources: Iterable[Resource], q: Query, texts: dict[str, str]) -> Page:
    hits = [r for r in resources if matches(r, q, texts[r.id])]
    keys: dict[Sort, Callable[[Resource], tuple[object, ...]]] = {
        Sort.RELEVANCE: lambda r: (-score(r, q), normalize(r.title)),
        Sort.TITLE: lambda r: (normalize(r.title),),
        Sort.UPDATED: lambda r: (r.updated or "",),
        Sort.YEAR: lambda r: (_years(r)[1] or _years(r)[0] or 0,),
    }
    hits.sort(key=keys[q.sort], reverse=q.sort in (Sort.UPDATED, Sort.YEAR))
    start = (q.page - 1) * q.page_size
    items: Sequence[Resource] = hits[start : start + q.page_size]
    return Page(list(items), len(hits), q.page, q.page_size)
