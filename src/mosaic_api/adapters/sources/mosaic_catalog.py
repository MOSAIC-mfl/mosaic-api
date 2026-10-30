"""Source: a MOSAIC catalogue build (mosaic-catalog dist/: catalog.json + manifest.json).

The manifest carries a SHA-256 per record, so unchanged records are not translated again.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

from ...ports.sources import RawRecord, SourceInfo
from ..fetch import Location


class MosaicCatalogSource:
    def __init__(self, info: SourceInfo, location: Location, record_url_template: str | None = None) -> None:
        self._info = info
        self._loc = location
        self._url_tpl = record_url_template

    @property
    def info(self) -> SourceInfo:
        return self._info

    def records(self) -> Iterator[RawRecord]:
        manifest = json.loads(self._loc.read("manifest.json"))
        hashes = {r["id"]: r["sha256"] for r in manifest.get("records", [])}
        catalog = json.loads(self._loc.read(manifest.get("files", {}).get("catalog", "catalog.json")))
        for rec in catalog["records"]:
            rid = str(rec["id"])
            url = self._url_tpl.format(id=rid) if self._url_tpl else None
            yield RawRecord(local_id=rid, data=rec, sha256=hashes.get(rid, ""), record_url=url)
