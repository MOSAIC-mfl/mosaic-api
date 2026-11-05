"""Facets: the values each resource exposes to the website filters, and their counts.

Rules (mosaic-catalog docs/standard.md §5.1):

* data_kind  - kinds of all access points;
* geometry   - vector geometry types, plus ``point`` for tables with coordinate columns;
               ``not_specified`` when a vector point has no geometry type;
* spatial    - ``yes`` (raster, vector, or a table with spatial: true), ``no`` (only tables with
               spatial: false and/or documents), otherwise ``not_specified``;
* every other facet is the value in the record, or ``not_specified``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from .model import Resource

NOT_SPECIFIED = "not_specified"

FACETS = (
    "source",
    "resource_type",
    "theme",
    "landscape",
    "geography",
    "data_kind",
    "geometry",
    "spatial",
    "method",
    "access",
    "license",
    "status",
)

# The facets people can filter by (GET /v1/resources and the website). The others stay as values
# on each resource (``facets`` of a summary) for display.
FILTERS = ("source", "theme", "landscape", "geography")


def _license(r: Resource) -> str:
    if r.license.spdx:
        return r.license.spdx
    return "other" if (r.license.text or r.license.url) else NOT_SPECIFIED


def _geometry(r: Resource) -> set[str]:
    out: set[str] = set()
    for p in r.data:
        if p.kind == "vector":
            out.add(p.vector.geometry_type if p.vector and p.vector.geometry_type else NOT_SPECIFIED)
        elif p.kind == "tabular" and p.tabular and p.tabular.coordinate_columns:
            out.add("point")
    return out


def _spatial(r: Resource) -> str:
    kinds = {p.kind for p in r.data}
    if kinds & {"raster", "vector"} or any(p.tabular and p.tabular.spatial for p in r.data):
        return "yes"
    tables = [p for p in r.data if p.kind == "tabular"]
    if kinds and kinds <= {"tabular", "document"} and all(p.tabular and p.tabular.spatial is False for p in tables):
        return "no"
    return NOT_SPECIFIED


def facet_values(r: Resource) -> dict[str, list[str]]:
    """Facet values of one resource. A resource may have several values per facet."""

    def or_ns(values: Iterable[str | None]) -> list[str]:
        vals = sorted({v for v in values if v})
        return vals or [NOT_SPECIFIED]

    return {
        "source": [r.gid.source],
        "resource_type": or_ns([r.resource_type]),
        "theme": or_ns(r.themes),
        "landscape": or_ns(r.landscapes),
        "geography": or_ns(r.geography),
        "data_kind": or_ns(p.kind for p in r.data),
        "geometry": sorted(_geometry(r)),
        "spatial": [_spatial(r)],
        "method": or_ns(p.method for p in r.data),
        "access": or_ns([r.access]),
        "license": [_license(r)],
        "status": [r.quality.status],
    }


def count(resources: Iterable[Resource], facets: Iterable[str] = FACETS) -> dict[str, dict[str, int]]:
    """Counts per facet value across resources (sorted by count, then value)."""
    counters: dict[str, Counter[str]] = {f: Counter() for f in facets}
    for r in resources:
        values = facet_values(r)
        for facet, counter in counters.items():
            counter.update(values[facet])
    return {f: dict(sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))) for f, c in counters.items()}
