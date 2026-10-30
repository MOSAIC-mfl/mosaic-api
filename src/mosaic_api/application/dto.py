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
    facets: dict[str, dict[str, int]] | None = Field(None, description="Counts over ALL results of the query.")


class SourceOut(Out):
    id: str
    name: str
    homepage: str | None
    format: str
    harvested_at: datetime | None
    records: int
    records_with_issues: int
    error: str | None


class Labels(Out):
    """Display labels for facet values, per facet (from the MOSAIC vocabularies)."""

    labels: dict[str, dict[str, str]]


class ShardRef(Out):
    path: str
    sha256: str
    records: int


class Manifest(Out):
    api_version: str
    standard_version: str
    harvested_at: datetime | None
    counts: dict[str, int]
    sources: list[str]
    files: dict[str, Any] = Field(default_factory=dict, description="Static export only: file paths with hashes.")


class Problem(Out):
    """RFC 9457 problem details."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
