"""SnapshotStore on the file system: one JSON file. No database (no budget, no need yet); the port
lets a database adapter replace it later without touching the core.

The file carries the version of its layout (`snapshot_format`). A snapshot written by an older model
(e.g. before the standard v0.2) cannot be read back: it is ignored with a warning and the next
harvest translates every record again, instead of failing."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ...domain.model import Resource
from ...ports.store import Snapshot, SourceState

log = logging.getLogger(__name__)

# Bump when the stored Resource changes shape (2: the standard v0.2 field names).
SNAPSHOT_FORMAT = 2


class FileSnapshotStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> Snapshot | None:
        if not self._path.exists():
            return None
        data = json.loads(self._path.read_text(encoding="utf-8"))
        if data.get("snapshot_format") != SNAPSHOT_FORMAT:
            log.warning(
                "%s: snapshot format %s, expected %s; ignored (full harvest)",
                self._path,
                data.get("snapshot_format"),
                SNAPSHOT_FORMAT,
            )
            return None
        try:
            return self._read(data)
        except (ValidationError, KeyError, ValueError) as err:
            log.warning("%s: unreadable snapshot (%s); ignored (full harvest)", self._path, type(err).__name__)
            return None

    @staticmethod
    def _read(data: dict[str, Any]) -> Snapshot:
        sources = [
            SourceState(
                id=s["id"],
                name=s["name"],
                homepage=s.get("homepage"),
                format=s["format"],
                harvested_at=datetime.fromisoformat(s["harvested_at"]) if s.get("harvested_at") else None,
                records=s["records"],
                issues=s.get("issues", {}),
                error=s.get("error"),
            )
            for s in data["sources"]
        ]
        return Snapshot(
            resources=[Resource.model_validate(r) for r in data["resources"]],
            sources=sources,
            standard_version=data["standard_version"],
            harvested_at=datetime.fromisoformat(data["harvested_at"]) if data.get("harvested_at") else None,
        )

    def save(self, snapshot: Snapshot) -> None:
        data = {
            "snapshot_format": SNAPSHOT_FORMAT,
            "standard_version": snapshot.standard_version,
            "harvested_at": snapshot.harvested_at.isoformat() if snapshot.harvested_at else None,
            "sources": [
                {
                    "id": s.id,
                    "name": s.name,
                    "homepage": s.homepage,
                    "format": s.format,
                    "harvested_at": s.harvested_at.isoformat() if s.harvested_at else None,
                    "records": s.records,
                    "issues": s.issues,
                    "error": s.error,
                }
                for s in snapshot.sources
            ],
            "resources": [r.model_dump(mode="json") for r in snapshot.resources],
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Write atomically: a crash mid-write never leaves a half snapshot.
        fd, tmp = tempfile.mkstemp(dir=self._path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
        os.replace(tmp, self._path)
