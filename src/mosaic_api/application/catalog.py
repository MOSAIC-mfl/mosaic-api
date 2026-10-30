"""Use cases for reading: search, get one resource, facets, sources, labels, manifest.

Built once from a snapshot (in memory; ~1-2 KB per resource, so tens of thousands fit in a free
server and in the static export). The same object serves the live API and the static exporter.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain import facets as facet_rules
from ..domain import search
from ..domain.model import Resource
from ..domain.standard import Standard
from ..ports import Snapshot
from .dto import Labels, Manifest, ResourceDetail, ResourcePage, ResourceSummary, SourceOut

API_VERSION = "0.1.0"

# facet -> vocabulary that labels its values
FACET_VOCAB = {
    "theme": "themes",
    "landscape": "landscapes",
    "geography": "geography",
    "resource_type": "resource_type",
    "data_kind": "data_kind",
    "method": "access_method",
    "access": "access",
}
FIXED_LABELS = {
    "spatial": {"yes": "Spatial", "no": "Not spatial"},
    "geometry": {"point": "Points", "line": "Lines", "polygon": "Polygons", "mixed": "Mixed"},
    "status": {"complete": "Complete", "incomplete": "Incomplete"},
    "license": {"other": "Other licence"},
}


@dataclass(frozen=True)
class CatalogOptions:
    expose_emails: bool = True  # project decision: contact e-mails are public


class CatalogService:
    def __init__(self, snapshot: Snapshot, standard: Standard, options: CatalogOptions | None = None) -> None:
        self._snap = snapshot
        self._std = standard
        self._opts = options or CatalogOptions()
        self._by_id = {r.id: r for r in snapshot.resources}

        def label(vocab: str, concept: str) -> str:
            v = standard.vocabularies.get(vocab)
            return v.label(concept) if v else concept

        self._texts = {r.id: search.searchable_text(r, label) for r in snapshot.resources}

    @property
    def resources(self) -> list[Resource]:
        return self._snap.resources

    def search(self, q: search.Query, with_facets: bool = False) -> ResourcePage:
        page = search.run(self._snap.resources, q, self._texts)
        counts = None
        if with_facets:
            everything = search.Query(q.text, q.filters, q.bbox, q.year_from, q.year_to, page=1, page_size=10**9)
            counts = facet_rules.count(search.run(self._snap.resources, everything, self._texts).items)
        return ResourcePage(
            items=[ResourceSummary.of(r) for r in page.items],
            total=page.total,
            page=page.page,
            page_size=page.page_size,
            facets=counts,
        )

    def summaries(self) -> list[ResourceSummary]:
        return [ResourceSummary.of(r) for r in self._snap.resources]

    def get(self, gid: str) -> ResourceDetail | None:
        r = self._by_id.get(gid)
        return ResourceDetail.of(r, self._opts.expose_emails) if r else None

    def facets(self) -> dict[str, dict[str, int]]:
        return facet_rules.count(self._snap.resources)

    def search_texts(self) -> dict[str, str]:
        """Normalized searchable text per resource (exported for in-browser search)."""
        return dict(self._texts)

    def sources(self) -> list[SourceOut]:
        return [
            SourceOut(
                id=s.id,
                name=s.name,
                homepage=s.homepage,
                format=s.format,
                harvested_at=s.harvested_at,
                records=s.records,
                records_with_issues=len(s.issues),
                error=s.error,
            )
            for s in self._snap.sources
        ]

    def labels(self) -> Labels:
        out: dict[str, dict[str, str]] = {f: dict(v) for f, v in FIXED_LABELS.items()}
        for facet, vocab in FACET_VOCAB.items():
            v = self._std.vocabularies.get(vocab)
            if v:
                out[facet] = dict(v.labels)
        out["source"] = {s.id: s.name for s in self._snap.sources}
        for facet in facet_rules.FACETS:
            out.setdefault(facet, {})[facet_rules.NOT_SPECIFIED] = "Not specified"
        return Labels(labels=out)

    def manifest(self) -> Manifest:
        statuses: list[str] = [str(getattr(r.quality.status, "value", r.quality.status)) for r in self._snap.resources]
        return Manifest(
            api_version=API_VERSION,
            standard_version=self._snap.standard_version,
            harvested_at=self._snap.harvested_at,
            counts={
                "resources": len(statuses),
                "complete": statuses.count("complete"),
                "incomplete": statuses.count("incomplete"),
            },
            sources=[s.id for s in self._snap.sources],
        )
