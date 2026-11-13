"""Cross-catalogue rules: the same resource in two catalogues, and landscapes derived from bboxes.

Connect, don't duplicate: when two catalogues describe the same resource (same DOI), both records
stay, each with its own provenance, and each points to the other in ``same_as``. The website can
then show one card with "also in: …".
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence

from .model import Bbox, Resource


def _doi_key(doi: str | None) -> str | None:
    return doi.strip().lower() if doi else None


def link_same_resources(resources: Sequence[Resource]) -> list[Resource]:
    by_doi: dict[str, list[str]] = defaultdict(list)
    for r in resources:
        key = _doi_key(r.doi)
        if key:
            by_doi[key].append(r.id)
    out = []
    for r in resources:
        key = _doi_key(r.doi)
        others = tuple(sorted(i for i in by_doi.get(key, []) if i != r.id)) if key else ()
        out.append(r.model_copy(update={"same_as": others}) if others != r.same_as else r)
    return out


def _intersects(a: Bbox, b: Bbox) -> bool:
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def derive_landscapes(
    resources: Sequence[Resource],
    landscape_boxes: Mapping[str, Bbox],
    landscape_countries: Mapping[str, Sequence[str]] | None = None,
) -> list[Resource]:
    """A resource without landscapes gets those it covers, flagged as derived:

    - with a bbox, the landscapes it intersects (global boxes, wider than 300 degrees, are not used:
      they would match every landscape and say nothing);
    - without a bbox, a national dataset (geography = countries, ISO 3166-1 alpha-3) covers the
      landscapes in those countries (as the first website showed national datasets).

    Records that state their landscapes are left as they are.
    """
    countries_of = landscape_countries or {}
    out = []
    for r in resources:
        if r.landscapes:
            out.append(r)
            continue
        boxes = r.bbox
        if boxes:
            if not landscape_boxes or any(b[2] - b[0] > 300 for b in boxes):
                out.append(r)
                continue
            hits = tuple(sorted(c for c, lb in landscape_boxes.items() if any(_intersects(b, lb) for b in boxes)))
        else:
            iso3 = {g for g in r.geography if len(g) == 3 and g.isupper()}
            hits = tuple(sorted(c for c, cs in countries_of.items() if iso3 & set(cs)))
        out.append(r.model_copy(update={"landscapes": hits, "landscapes_derived": True}) if hits else r)
    return out
