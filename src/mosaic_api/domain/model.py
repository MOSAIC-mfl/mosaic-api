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
    NON_PUBLIC = "non-public"


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
    description: str | None = None


class Author(Model):
    family: str | None = None
    given: str | None = None
    organization: str | None = None
    orcid: str | None = None
    ror: str | None = None


class Citation(Model):
    text: str | None = None
    title: str | None = None
    authors: tuple[Author, ...] = ()
    date: str | None = None
    publisher: str | None = None
    url: str | None = None


class Temporal(Model):
    date: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    text: str | None = None
    update_frequency: str | None = None

    def years(self) -> tuple[int | None, int | None]:
        """(start year, end year) of the period; None = open or unknown."""
        if self.date:
            y = int(self.date[:4])
            return y, y
        start = int(self.start_date[:4]) if self.start_date else None
        end = int(self.end_date[:4]) if self.end_date else None
        return start, end


class Resolution(Model):
    value: float | None = None
    unit: str | None = None
    text: str | None = None


class Spatial(Model):
    bbox: tuple[Bbox, ...] = ()  # one or more boxes [west, south, east, north]
    crs: str | None = None
    geography: tuple[str, ...] = ()
    landscapes: tuple[str, ...] = ()  # as the record states them (derived ones live on Resource)
    resolution: Resolution | None = None


class Location(Model):
    url: Text
    title: str | None = None


class Service(Model):
    type: str | None = None
    layers: tuple[str, ...] = ()


class DataEntry(Model):
    """One way to reach the data (standard v0.2 data[]; same fields as the CDH core plus MOSAIC's)."""

    name: Text
    locations: tuple[Location, ...] = ()
    access_method: AccessMethod | None = None
    kind: DataKind | None = None
    description: str | None = None
    media_type: str | None = None
    file_size: int | str | None = None
    checksum: str | None = None
    access: Access | None = None
    geometry_type: str | None = None  # point | line | polygon | mixed
    feature_count: int | None = None
    service: Service | None = None
    spatial: dict[str, Any] | None = None
    structures: tuple[str, ...] = ()
    href_template: str | None = None
    file_index: tuple[dict[str, Any], ...] = ()
    processing_steps: tuple[str, ...] = ()

    @property
    def url(self) -> str | None:
        return self.locations[0].url if self.locations else None


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
    format: str  # e.g. mosaic-v0.2, cdh-yaml-v0.5
    fetched_at: datetime
    source_hash: str  # SHA-256 of the source record: drives incremental harvests


class Quality(Model):
    status: Status
    completeness: dict[str, float] = Field(default_factory=dict)
    missing_minimum: tuple[str, ...] = ()


class Resource(Model):
    """One resource in the MOSAIC model (the fields of the MOSAIC standard v0.2, which follows the
    CGIAR Climate Data Hub core). Fields the API does not reason about travel in ``more``."""

    gid: GlobalId
    title: Text
    description: str | None = None
    note: str | None = None
    resource_type: ResourceType | None = None
    version: str | None = None
    language: tuple[str, ...] = ()
    themes: tuple[str, ...] = ()
    keywords: tuple[Keyword | Text, ...] = ()  # a plain term, or a term linked to a vocabulary
    commodities: tuple[str, ...] = ()
    usage: dict[str, Any] | None = None
    spatial: Spatial | None = None
    temporal: Temporal | None = None
    license: str | None = None
    license_text: str | None = None
    access: Access | None = None
    access_note: str | None = None
    attribution: str | None = None
    contact: tuple[Contact, ...] = ()
    citation: Citation | None = None
    doi: str | None = None
    funding: tuple[Funding, ...] = ()
    related_publications: tuple[dict[str, Any], ...] = ()
    additional_links: tuple[dict[str, Any], ...] = ()
    data: tuple[DataEntry, ...] = ()
    structures: tuple[dict[str, Any], ...] = ()
    processing: tuple[dict[str, Any], ...] = ()
    derived: tuple[str, ...] = ()
    created: str | None = None
    updated: str | None = None
    source_updated: str | None = None
    extensions: tuple[str, ...] = ()
    more: dict[str, Any] = Field(default_factory=dict)  # series, parent, deprecated, extension blocks…
    landscapes: tuple[str, ...] = ()  # stated (spatial.landscapes) or derived from the bbox
    landscapes_derived: bool = False
    provenance: Provenance
    quality: Quality
    same_as: tuple[str, ...] = ()  # other catalogues' copies of this record (same DOI)

    @property
    def id(self) -> str:
        return str(self.gid)

    @property
    def keyword_terms(self) -> list[str]:
        return [k if isinstance(k, str) else k.term for k in self.keywords]

    @property
    def geography(self) -> tuple[str, ...]:
        return self.spatial.geography if self.spatial else ()

    @property
    def bbox(self) -> tuple[Bbox, ...]:
        return self.spatial.bbox if self.spatial else ()

    def to_record(self) -> dict[str, Any]:
        """The resource as a MOSAIC standard record (v0.2), for the standard's own validator and for
        clients. Derived landscapes are not part of the record (they are on the resource)."""
        skip = {"gid", "landscapes", "landscapes_derived", "provenance", "quality", "same_as", "more"}
        data = self.model_dump(mode="json", exclude=skip, exclude_none=True, exclude_defaults=True)
        data = {"id": self.gid.local_id, **data, **self.more}
        spatial = data.get("spatial")
        if spatial and spatial.get("bbox"):
            boxes = spatial["bbox"]
            spatial["bbox"] = boxes[0] if len(boxes) == 1 else boxes
        return data
