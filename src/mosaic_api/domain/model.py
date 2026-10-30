"""The MOSAIC model: what every resource looks like inside the API, whatever catalogue it came from.

This is "our language". Each source's translator converts its records into these types; nothing
outside ``adapters/`` knows any source format. Field names follow the MOSAIC metadata standard
(mosaic-catalog/schema), so a MOSAIC record and a translated record have the same shape.

Pydantic is used here only as typed, validated, immutable data structures; the domain does no I/O
and does not know FastAPI (enforced by import-linter, see pyproject.toml).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Text = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
DateStr = Annotated[str, StringConstraints(pattern=r"^\d{4}(-\d{2}(-\d{2})?)?$")]
Bbox = tuple[float, float, float, float]


class Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", use_enum_values=True)


class ResourceType(str, Enum):
    DATASET = "dataset"
    SERVICE = "service"
    DOCUMENT = "document"
    SOFTWARE = "software"
    MODEL = "model"


class Access(str, Enum):
    PUBLIC = "public"
    RESTRICTED = "restricted"
    INTERNAL = "internal"


class DataKind(str, Enum):
    RASTER = "raster"
    VECTOR = "vector"
    TABULAR = "tabular"
    DOCUMENT = "document"
    MIXED = "mixed"
    OTHER = "other"


class AccessMethod(str, Enum):
    DOWNLOAD = "download"
    LANDING_PAGE = "landing_page"
    SERVICE = "service"
    REQUEST = "request"


class Status(str, Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


# -- value objects ---------------------------------------------------------------------------------
class GlobalId(Model):
    """A resource's identity across catalogues: ``<source>:<local id>`` (ADR-0003 of mosaic-catalog)."""

    source: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]{1,30}$")]
    local_id: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")]

    def __str__(self) -> str:
        return f"{self.source}:{self.local_id}"


class License(Model):
    spdx: str | None = None
    url: str | None = None
    text: str | None = None


class Contact(Model):
    name: str | None = None
    organization: str | None = None
    email: str | None = None
    url: str | None = None
    ror: str | None = None
    orcid: str | None = None
    roles: tuple[str, ...] = ()


class Keyword(Model):
    term: Text
    scheme: str | None = None
    uri: str | None = None
    lang: str | None = None


class Author(Model):
    family: str | None = None
    given: str | None = None
    organization: str | None = None
    orcid: str | None = None


class Citation(Model):
    text: str | None = None
    title: str | None = None
    authors: tuple[Author, ...] = ()
    date: str | None = None
    publisher: str | None = None
    version: str | None = None


class Temporal(Model):
    start: DateStr | None = None
    end: DateStr | None = None
    text: str | None = None


class Resolution(Model):
    value: float | None = None
    unit: str | None = None
    text: str | None = None


class Spatial(Model):
    bbox: tuple[Bbox, ...] = ()  # one or more boxes [west, south, east, north]
    crs: str | None = None
    resolution: Resolution | None = None


class VectorInfo(Model):
    geometry_type: str | None = None  # point | line | polygon | mixed
    feature_count: int | None = None
    crs: str | None = None
    attributes: tuple[dict[str, Any], ...] = ()


class TabularInfo(Model):
    spatial: bool | None = None
    coordinate_columns: dict[str, str] | None = None
    geometry_column: str | None = None
    row_count: int | None = None
    columns: tuple[dict[str, Any], ...] = ()


class RasterInfo(Model):
    resolution: Resolution | None = None
    crs: str | None = None
    bands: tuple[dict[str, Any], ...] = ()


class ServiceInfo(Model):
    service_type: str | None = None
    layers: tuple[str, ...] = ()
    auth_required: bool | None = None


class DocumentInfo(Model):
    pages: int | None = None
    language: str | None = None


class AccessPoint(Model):
    name: Text
    kind: DataKind | None = None
    method: AccessMethod | None = None
    url: str | None = None
    description: str | None = None
    media_type: str | None = None
    access: Access | None = None
    size: str | None = None
    files: str | None = None
    raster: RasterInfo | None = None
    vector: VectorInfo | None = None
    tabular: TabularInfo | None = None
    document: DocumentInfo | None = None
    service: ServiceInfo | None = None
    derived: tuple[str, ...] = ()


class Related(Model):
    relation: str
    scheme: str
    value: Text
    title: str | None = None


class Funding(Model):
    name: Text
    url: str | None = None
    ror: str | None = None
    award: str | None = None


class Provenance(Model):
    """Where a resource came from. Shown to users: MOSAIC connects, it does not own."""

    source: str
    source_name: str
    record_url: str | None = None  # the record in its own catalogue, when it has a page or file
    format: str  # e.g. mosaic-v0.1, cdh-v0.5.0
    fetched_at: datetime
    source_hash: str  # SHA-256 of the source record: drives incremental harvests


class Quality(Model):
    status: Status
    completeness: dict[str, float] = Field(default_factory=dict)
    missing_minimum: tuple[str, ...] = ()


class Resource(Model):
    """One resource in the MOSAIC model."""

    gid: GlobalId
    title: Text
    description: str | None = None
    note: str | None = None
    slug: str | None = None
    resource_type: ResourceType | None = None
    themes: tuple[str, ...] = ()
    keywords: tuple[Keyword, ...] = ()
    geography: tuple[str, ...] = ()
    landscapes: tuple[str, ...] = ()
    landscapes_derived: bool = False
    license: License = License()
    contacts: tuple[Contact, ...] = ()
    citation: Citation | None = None
    doi: str | None = None
    access: Access | None = None
    access_note: str | None = None
    data: tuple[AccessPoint, ...] = ()
    temporal: Temporal | None = None
    spatial: Spatial | None = None
    version: str | None = None
    update_frequency: str | None = None
    source_updated: str | None = None
    language: tuple[str, ...] = ()
    funding: tuple[Funding, ...] = ()
    related: tuple[Related, ...] = ()
    created: str | None = None
    updated: str | None = None
    derived: tuple[str, ...] = ()
    provenance: Provenance
    quality: Quality
    same_as: tuple[str, ...] = ()  # other catalogues' copies of this record (same DOI)

    @property
    def id(self) -> str:
        return str(self.gid)

    def to_record(self) -> dict[str, Any]:
        """The resource as a MOSAIC standard record (for the standard's own validator)."""
        skip = {"gid", "landscapes", "landscapes_derived", "provenance", "quality", "same_as"}
        data = self.model_dump(mode="json", exclude=skip, exclude_none=True, exclude_defaults=True)
        data = {"id": self.gid.local_id, **data}
        if data.get("spatial", {}).get("bbox"):
            boxes = data["spatial"]["bbox"]
            data["spatial"]["bbox"] = boxes[0] if len(boxes) == 1 else boxes
        if self.landscapes and not self.landscapes_derived:
            data["mosaic"] = {"landscapes": list(self.landscapes)}
        return data
