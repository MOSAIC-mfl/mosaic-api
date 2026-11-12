"""Loads the MOSAIC standard from the files mosaic-catalog publishes (its dist/ folder or Pages)."""

from __future__ import annotations

import json
from typing import Any

import yaml

from ...domain.standard import Standard, Vocabulary
from ..fetch import FetchError, Location

VOCABULARIES = (
    "themes",
    "landscapes",
    "geography",
    "resource_type",
    "access",
    "data_kind",
    "access_method",
    "contact_role",
    "service_type",
    "update_frequency",
)
# Vocabularies added after 0.2.0 was first published: read when the standard has them, so the API also
# runs on an older build of the standard.
OPTIONAL_VOCABULARIES = ("processing_status",)
CROSSWALKS = ("cdh",)
SCHEMAS = ("record.schema.json", "vocab.schema.json", "levels/minimum.schema.json", "levels/recommended.schema.json")


class DistStandard:
    """StandardProvider reading ``<location>/{manifest.json, vocab/, crosswalks/, schema/}``."""

    def __init__(self, location: Location) -> None:
        self._loc = location
        self._cache: Standard | None = None

    def load(self) -> Standard:
        if self._cache is None:
            manifest = json.loads(self._loc.read("manifest.json"))
            vocabs = {}
            for name in (*VOCABULARIES, *OPTIONAL_VOCABULARIES):
                try:
                    data = json.loads(self._loc.read(f"vocab/{name}.json"))
                except (FileNotFoundError, FetchError):
                    if name in OPTIONAL_VOCABULARIES:
                        continue
                    raise
                labels = {c["id"]: c["label"] for c in data["concepts"]}
                extra = {c["id"]: {k: v for k, v in c.items() if k not in ("id", "label")} for c in data["concepts"]}
                vocabs[name] = Vocabulary(name, labels, extra)
            crosswalks = {n: yaml.safe_load(self._loc.read(f"crosswalks/{n}.yaml")) for n in CROSSWALKS}
            self._cache = Standard(str(manifest["standard_version"]), vocabs, crosswalks)
        return self._cache

    def schemas(self) -> dict[str, dict[str, Any]]:
        return {name: json.loads(self._loc.read(f"schema/{name}")) for name in SCHEMAS}
