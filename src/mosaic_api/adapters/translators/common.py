"""Helpers shared by translators."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import ValidationError

from ...domain.model import GlobalId, Provenance, Quality, Resource, Status
from ...ports.sources import RawRecord, SourceInfo
from ...ports.translator import TranslationResult

PENDING = Quality(status=Status.INCOMPLETE)  # replaced by the QualityAssessor during the harvest

# Fields of the MOSAIC standard v0.2 the domain model holds; the rest of a record travels in `more`.
CORE_FIELDS = (
    "title", "description", "note", "resource_type", "version", "language", "themes", "keywords", "commodities",
    "usage", "spatial", "temporal", "license", "license_text", "access", "access_note", "attribution", "contact",
    "citation", "doi", "funding", "related_publications", "additional_links", "data", "structures", "processing",
    "derived", "created", "updated", "source_updated", "extensions",
)  # fmt: skip


def provenance(raw: RawRecord, source: SourceInfo, fetched_at: datetime) -> Provenance:
    return Provenance(
        source=source.id,
        source_name=source.name,
        record_url=raw.record_url,
        format=source.format,
        fetched_at=fetched_at,
        source_hash=raw.sha256,
    )


def build(
    fields: dict[str, Any], raw: RawRecord, source: SourceInfo, fetched_at: datetime, issues: list[str]
) -> TranslationResult:
    """Validate the translated fields into a Resource; a validation error is an issue, not a crash."""
    try:
        res = Resource(
            gid=GlobalId(source=source.id, local_id=raw.local_id),
            provenance=provenance(raw, source, fetched_at),
            quality=PENDING,
            **{k: v for k, v in fields.items() if v not in (None, [], (), {})},
        )
    except ValidationError as exc:
        issues = [*issues, *(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())]
        return TranslationResult(None, issues)
    return TranslationResult(res, issues)


def bbox_list(value: Any) -> list[tuple[float, float, float, float]]:
    """One box [w, s, e, n] or a list of boxes -> list of 4-tuples (3D boxes keep x/y only)."""
    if not value:
        return []
    boxes = value if isinstance(value[0], list | tuple) else [value]
    out = []
    for b in boxes:
        if len(b) == 6:
            b = [b[0], b[1], b[3], b[4]]
        out.append((float(b[0]), float(b[1]), float(b[2]), float(b[3])))
    return out
