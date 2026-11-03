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
from ..domain.text import key
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
        self._by_key = {key(r.id): r for r in snapshot.resources}
        self._aliases = self._build_aliases()

    def _build_aliases(self) -> dict[str, dict[str, str]]:
        """Per facet: folded id or folded label -> canonical value. Lets people filter with
        'PERU', 'Perú', 'Peru' or 'per' and get PER; 'CC BY 4.0' and get CC-BY-4.0."""
        aliases: dict[str, dict[str, str]] = {f: {} for f in facet_rules.FACETS}
        for facet, values in facet_rules.count(self._snap.resources).items():
            for value in values:
                aliases[facet][key(value)] = value
        for facet, labels in self.labels().labels.items():
            for value, lab in labels.items():
                aliases.setdefault(facet, {}).setdefault(key(value), value)
                aliases[facet].setdefault(key(lab), value)
        return aliases

    def resolve_filters(self, filters: dict[str, frozenset[str]]) -> tuple[dict[str, frozenset[str]], list[str]]:
        """Canonical filter values, and a warning for each value that matches nothing known."""
        out: dict[str, frozenset[str]] = {}
        warnings: list[str] = []
        for facet, values in filters.items():
            known = self._aliases.get(facet, {})
            resolved = set()
            for v in values:
                canon = known.get(key(v))
                if canon is None:
                    warnings.append(f"{facet}={v!r} matches no value of this filter")
                    resolved.add(v)
                else:
                    resolved.add(canon)
            out[facet] = frozenset(resolved)
        return out, warnings

    @property
    def resources(self) -> list[Resource]:
        return self._snap.resources

    def search(self, q: search.Query, with_facets: bool = False) -> ResourcePage:
        filters, warnings = self.resolve_filters(q.filters)
        q = search.Query(q.text, filters, q.bbox, q.year_from, q.year_to, q.sort, q.page, q.page_size)
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
            warnings=warnings,
        )

    def summaries(self) -> list[ResourceSummary]:
        return [ResourceSummary.of(r) for r in self._snap.resources]

    def get(self, gid: str) -> ResourceDetail | None:
        """Exact id first; otherwise case-, accent- and separator-insensitive (mosaic:mfl-2026-079)."""
        r = self._by_id.get(gid) or self._by_key.get(key(gid))
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
