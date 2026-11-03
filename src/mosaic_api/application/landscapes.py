"""Use cases for landscape pages: the list of landscapes and one landscape with its data status."""

from __future__ import annotations

from ..domain.landscape import LandscapeProfile, data_status
from ..ports.landscapes import LandscapeProfiles
from .catalog import CatalogService
from .dto import DataStatusOut, LandscapeOut, LandscapeSummaryOut, ResourceSummary, SectionOut


class LandscapeService:
    def __init__(self, profiles: LandscapeProfiles, catalog: CatalogService) -> None:
        self._profiles = profiles.all()
        self._catalog = catalog

    def _summary(self, p: LandscapeProfile) -> LandscapeSummaryOut:
        doc = p.document
        land = doc.get("landscape") or {}
        status = data_status(p.code, self._catalog.resources)
        return LandscapeSummaryOut(
            code=p.code,
            slug=p.slug,
            label=str(land.get("label") or p.code),
            countries=list(land.get("countries") or []),
            bbox=land.get("bbox"),
            title=str(doc.get("title") or land.get("label") or p.code),
            summary=doc.get("summary"),
            status=str(doc.get("status") or "draft"),
            curated=bool(doc.get("curated")),
            sections=[
                SectionOut(id=str(s.get("id")), kind=str(s.get("kind")), title=s.get("title")) for s in p.sections()
            ],
            counts={"datasets": status.total, "complete": status.complete, "incomplete": status.incomplete},
            records=p.referenced_records(),
        )

    def list(self) -> list[LandscapeSummaryOut]:
        return [self._summary(p) for p in self._profiles]

    def get(self, code_or_slug: str) -> LandscapeOut | None:
        p = next((x for x in self._profiles if x.matches(code_or_slug)), None)
        if p is None:
            return None
        doc = p.document
        status = data_status(p.code, self._catalog.resources)
        referenced = set(p.referenced_records())
        return LandscapeOut(
            **self._summary(p).model_dump(exclude={"sections"}),
            credits=list(doc.get("credits") or []),
            origin=doc.get("origin"),
            sections=[
                SectionOut(
                    id=str(s.get("id")),
                    kind=str(s.get("kind")),
                    title=s.get("title"),
                    intro=s.get("intro"),
                    options=s.get("options"),
                    config=s.get("config"),
                )
                for s in p.sections()
            ],
            data_status=DataStatusOut(**vars(status)),
            linked=[ResourceSummary.of(r) for r in self._catalog.resources if r.id in referenced],
        )
