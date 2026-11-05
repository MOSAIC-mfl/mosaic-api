"""What the API returns. These schemas are the public contract (OpenAPI -> TypeScript types for the
website). They are separate from the domain model: a field reaches the outside only if it is
listed here, so nothing internal can leak by accident.

Field names follow the MOSAIC metadata standard (snake_case), the same names as in the records.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..domain.facets import facet_values
from ..domain.model import Resource


class Out(BaseModel):
    model_config = ConfigDict(frozen=True)


class ProvenanceOut(Out):
    source: str = Field(description="Catalogue id, e.g. mosaic, cdh.")
    source_name: str
    record_url: str | None = Field(None, description="The record in its own catalogue.")
    format: str
    fetched_at: datetime


class QualityOut(Out):
    status: str = Field(description="complete | incomplete (against the MOSAIC minimum).")
    completeness: dict[str, float]
    missing_minimum: list[str]


def _producer(r: Resource) -> str | None:
    for c in r.contacts:
        if "producer" in c.roles:
            return c.organization or c.name
    return None


def _access_url(r: Resource) -> str | None:
    points = sorted((p for p in r.data if p.url), key=lambda p: (p.access or r.access) != "public")
    return points[0].url if points else None


class ResourceSummary(Out):
    """A light card for lists and maps."""

    id: str = Field(description="Global id <source>:<local id>, e.g. mosaic:MFL-2026-079.")
    source: str
    local_id: str
    title: str
    description: str | None = Field(None, description="First 300 characters.")
    resource_type: str | None
    themes: list[str]
    geography: list[str]
    landscapes: list[str]
    landscapes_derived: bool
    facets: dict[str, list[str]] = Field(description="Values this resource shows in each filter.")
    bbox: list[list[float]]
    period: list[int | None] | None = Field(None, description="[start year, end year]; null = open/unknown.")
    access: str | None
    license: str | None = Field(None, description="SPDX id, or the licence text.")
    status: str
    completeness: dict[str, float]
    same_as: list[str]
    updated: str | None
    producer: str | None = Field(None, description="First producer organization (or person).")
    access_url: str | None = Field(None, description="First access point URL, public ones first.")

    @classmethod
    def of(cls, r: Resource) -> ResourceSummary:
        t = r.temporal
        period = [int(t.start[:4]) if t.start else None, int(t.end[:4]) if t.end else None] if t else None
        desc = r.description
        if desc and len(desc) > 300:
            desc = desc[:297].rsplit(" ", 1)[0] + "…"
        return cls(
            id=r.id,
            source=r.gid.source,
            local_id=r.gid.local_id,
            title=r.title,
            description=desc,
            resource_type=r.resource_type,
            themes=list(r.themes),
            geography=list(r.geography),
            landscapes=list(r.landscapes),
            landscapes_derived=r.landscapes_derived,
            facets=facet_values(r),
            bbox=[list(b) for b in (r.spatial.bbox if r.spatial else ())],
            period=period,
            access=r.access,
            license=r.license.spdx or r.license.text,
            status=r.quality.status,
            completeness=r.quality.completeness,
            same_as=list(r.same_as),
            updated=r.updated,
            producer=_producer(r),
            access_url=_access_url(r),
        )


class ResourceDetail(Out):
    """The full resource in the MOSAIC model, plus where it came from and how complete it is."""

    id: str
    source: str
    local_id: str
    record: dict[str, Any] = Field(description="The resource as a MOSAIC standard record (see the standard's schema).")
    landscapes: list[str]
    landscapes_derived: bool
    facets: dict[str, list[str]]
    provenance: ProvenanceOut
    quality: QualityOut
    same_as: list[str]

    @classmethod
    def of(cls, r: Resource, expose_emails: bool) -> ResourceDetail:
        record = r.to_record()
        if not expose_emails:
            for c in record.get("contacts", []):
                c.pop("email", None)
        return cls(
            id=r.id,
            source=r.gid.source,
            local_id=r.gid.local_id,
            record=record,
            landscapes=list(r.landscapes),
            landscapes_derived=r.landscapes_derived,
            facets=facet_values(r),
            provenance=ProvenanceOut.model_validate(r.provenance.model_dump()),
            quality=QualityOut.model_validate(r.quality.model_dump()),
            same_as=list(r.same_as),
        )


class ResourcePage(Out):
    items: list[ResourceSummary]
    total: int
    page: int
    page_size: int
    facets: dict[str, dict[str, int]] | None = Field(
        None, description="With include_facets: counts per filter value over ALL results of the query."
    )
    warnings: list[str] = Field(default_factory=list, description="Filter values that match nothing known.")


class SourceOut(Out):
    id: str
    name: str
    homepage: str | None
    format: str
    harvested_at: datetime | None
    records: int
    records_with_issues: int
    error: str | None


class FilterOption(Out):
    value: str = Field(description="What goes in the query, e.g. theme=water.")
    label: str = Field(description="What people read, from the MOSAIC vocabularies.")
    count: int = Field(description="Resources with this value in the whole catalogue.")


class FiltersOut(Out):
    """Everything a client needs before searching: versions, totals, the filters of
    GET /v1/resources with their options, and display labels for the other coded values."""

    api_version: str
    standard_version: str
    harvested_at: datetime | None
    totals: dict[str, int] = Field(description="resources, complete, incomplete.")
    filters: dict[str, list[FilterOption]] = Field(
        description="One entry per filter of GET /v1/resources (source, theme, landscape, geography): "
        "the values present in the catalogue, most frequent first."
    )
    labels: dict[str, dict[str, str]] = Field(
        description="Display labels of the other coded values a resource shows (resource_type, data_kind, "
        "access, method, geometry, spatial, license, status)."
    )


class Problem(Out):
    """RFC 9457 problem details."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None


class SectionOut(Out):
    """One section of a landscape page. `kind` names the module that draws it on the website."""

    id: str
    kind: str = Field(description="overview | map-explorer | catalogue-datasets | data-status | <custom>")
    title: str | None = None
    intro: str | None = None
    options: dict[str, Any] | None = None
    config: dict[str, Any] | None = Field(
        None, description="Configuration of the section (map-explorer: see the standard's landscape/explorer schema)."
    )


class DataStatusOut(Out):
    """What the catalogue holds for the landscape and how complete it is."""

    total: int
    complete: int
    incomplete: int
    stated: int = Field(description="Resources that name the landscape; the others cover it by bounding box.")
    by_kind: dict[str, int]
    by_theme: dict[str, int]
    by_access: dict[str, int]
    missing_minimum: dict[str, int] = Field(description="Minimum field -> resources missing it.")


class LandscapeSummaryOut(Out):
    code: str = Field(description="Landscape code, e.g. KEN-LVB.")
    slug: str = Field(description="Code in lower case, used in page URLs.")
    label: str
    countries: list[str]
    bbox: list[float] | None
    title: str
    summary: str | None
    status: str = Field(description="draft | review | published")
    curated: bool = Field(description="false = the default page (no profile written yet).")
    sections: list[SectionOut]
    counts: dict[str, int]
    records: list[str] = Field(description="Catalogue records the profile names (source:id).")


class LandscapeOut(LandscapeSummaryOut):
    credits: list[dict[str, Any]]
    origin: dict[str, Any] | None
    data_status: DataStatusOut
    linked: list[ResourceSummary] = Field(description="Named records that cover the landscape.")
