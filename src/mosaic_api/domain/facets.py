"""Facets: the values each resource exposes to the website filters, and their counts.

Only source, theme, landscape and geography are filters (FILTERS); the others are shown on each
resource. Rules:

* data_kind  - kinds of all data entries;
* geometry   - vector geometry types, plus ``point`` for tables with coordinate columns (x / y
               dimensions in their data dictionary); ``not_specified`` for a vector without one;
* spatial    - ``yes`` (raster, vector, or a table with coordinates or a geometry column), ``no``
               (only described tables without them and/or documents), otherwise ``not_specified``;
* license    - the SPDX expression; ``other`` for LicenseRef-… or a licence text;
* every other facet is the value in the record, or ``not_specified``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any

from .model import DataEntry, Resource

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
    if r.license and not r.license.startswith("LicenseRef-"):
        return r.license
    return "other" if (r.license or r.license_text) else NOT_SPECIFIED


def _structures_of(r: Resource, p: DataEntry) -> list[dict[str, Any]]:
    """The data dictionary of a data entry: the structures it names, or the record's only one."""
    if p.structures:
        return [s for s in r.structures if s.get("name") in p.structures]
    return list(r.structures) if len(r.structures) == 1 else []


def _table_geo(r: Resource, p: DataEntry) -> tuple[bool, bool]:
    """(coordinate columns, geometry column) of a table entry."""
    sts = _structures_of(r, p)
    coords = any(d.get("type") in ("x", "y", "xy") for s in sts for d in s.get("dimensions", []))
    geom = any(s.get("geometry_column") for s in sts)
    return coords, geom


def _geometry(r: Resource) -> set[str]:
    out: set[str] = set()
    for p in r.data:
        if p.kind == "vector":
            out.add(p.geometry_type or NOT_SPECIFIED)
        elif p.kind == "tabular" and _table_geo(r, p)[0]:
            out.add("point")
    return out


def _spatial(r: Resource) -> str:
    kinds = {p.kind for p in r.data}
    if kinds & {"raster", "vector"} or any(p.kind == "tabular" and any(_table_geo(r, p)) for p in r.data):
        return "yes"
    tables = [p for p in r.data if p.kind == "tabular"]
    described = all(_structures_of(r, p) for p in tables)  # a known table without coordinates is not spatial
    if kinds and kinds <= {"tabular", "document"} and described:
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
        "method": or_ns(p.access_method for p in r.data),
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
