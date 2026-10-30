"""Translator for MOSAIC's own records (standard v0.1). Same model, so the mapping is direct; it
still goes through a translator like every other catalogue (the core treats MOSAIC as one source
among others)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ...domain.standard import Standard
from ...ports.sources import RawRecord, SourceInfo
from ...ports.translator import TranslationResult
from .common import bbox_list, build

COPIED = (
    "title",
    "description",
    "note",
    "slug",
    "resource_type",
    "themes",
    "geography",
    "license",
    "contacts",
    "doi",
    "access",
    "access_note",
    "data",
    "temporal",
    "version",
    "update_frequency",
    "source_updated",
    "language",
    "funding",
    "related",
    "created",
    "updated",
    "derived",
)


class MosaicTranslator:
    def translate(
        self, raw: RawRecord, source: SourceInfo, standard: Standard, fetched_at: datetime
    ) -> TranslationResult:
        d: dict[str, Any] = raw.data
        fields: dict[str, Any] = {k: d.get(k) for k in COPIED}
        fields["keywords"] = [k if isinstance(k, dict) else {"term": k} for k in d.get("keywords") or []]
        cit = d.get("citation")
        fields["citation"] = {"text": cit} if isinstance(cit, str) else cit
        sp = d.get("spatial")
        if sp:
            fields["spatial"] = {**sp, "bbox": bbox_list(sp.get("bbox"))}
        fields["landscapes"] = (d.get("mosaic") or {}).get("landscapes")
        issues = [f"unknown theme {t!r}" for t in d.get("themes") or [] if t not in standard.vocab("themes")]
        return build(fields, raw, source, fetched_at, issues)
