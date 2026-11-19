"""Use case: harvest every configured catalogue into one snapshot of MOSAIC resources.

For each source: read its records -> skip the unchanged ones (same SHA-256 as last time) ->
translate the rest -> assess quality against the MOSAIC minimum -> keep. Then link the same
resource across catalogues (DOI) and derive landscapes from bounding boxes.

A failing source does not stop the harvest: its previous resources are kept and the error is
recorded in the source state, so one catalogue being down never empties the website. A source that
suddenly returns no records counts as failing. One unreadable or untranslatable record does not fail
its source: it becomes an issue and its previous version, if any, is kept.

Reuse is only safe while what a translation depends on stays the same: the snapshot stores a
fingerprint of the API code and the standard, and when it differs every record is translated again.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from ..domain.linking import derive_landscapes, link_same_resources
from ..domain.model import Bbox, Resource
from ..domain.standard import Standard
from ..ports import CatalogSource, QualityAssessor, Snapshot, SnapshotStore, StandardProvider, Translator
from ..ports.store import SourceState

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceBinding:
    source: CatalogSource
    translator: Translator


@dataclass(frozen=True)
class HarvestReport:
    snapshot: Snapshot
    translated: dict[str, int]
    reused: dict[str, int]


def _landscape_boxes(standard: Standard) -> dict[str, Bbox]:
    vocab = standard.vocabularies.get("landscapes")
    if vocab is None:
        return {}
    boxes: dict[str, Bbox] = {}
    for code, attrs in vocab.extra.items():
        bb = attrs.get("bbox")
        if isinstance(bb, list) and len(bb) == 4:
            boxes[code] = (float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3]))
    return boxes


def _landscape_countries(standard: Standard) -> dict[str, list[str]]:
    vocab = standard.vocabularies.get("landscapes")
    if vocab is None:
        return {}
    return {code: list(attrs.get("countries") or []) for code, attrs in vocab.extra.items()}


def fingerprint(standard: Standard, code_version: str) -> str:
    """Changes when the API code or the standard (version, vocabularies, crosswalks) changes."""
    parts = {
        "code": code_version,
        "standard": standard.version,
        "vocabularies": {n: [v.labels, v.extra] for n, v in sorted(standard.vocabularies.items())},
        "crosswalks": standard.crosswalks,
    }
    blob = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class HarvestService:
    def __init__(
        self,
        standard: StandardProvider,
        bindings: Sequence[SourceBinding],
        assessor: QualityAssessor,
        store: SnapshotStore,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        code_version: str = "",
    ) -> None:
        self._standard = standard
        self._bindings = bindings
        self._assessor = assessor
        self._store = store
        self._clock = clock
        self._code_version = code_version

    def run(self) -> HarvestReport:
        standard = self._standard.load()
        previous = self._store.load()
        fp = fingerprint(standard, self._code_version)
        prev_by_id = {r.id: r for r in (previous.resources if previous else [])}
        prev_sources = {s.id: s for s in (previous.sources if previous else [])}
        # previous translations are reused only if they were made by the same code and standard
        reusable = prev_by_id if previous is not None and previous.fingerprint == fp else {}
        if previous is not None and not reusable:
            log.info("API code or standard changed since the last harvest: every record is translated again")
        now = self._clock()
        resources: list[Resource] = []
        states: list[SourceState] = []
        translated: dict[str, int] = {}
        reused: dict[str, int] = {}
        for binding in self._bindings:
            info = binding.source.info
            last = prev_sources.get(info.id)
            last_issues = last.issues if last else {}
            kept_before = [r for r in prev_by_id.values() if r.gid.source == info.id]
            issues: dict[str, list[str]] = {}
            got: list[Resource] = []
            n_new = n_reused = 0
            try:
                for raw in binding.source.records():
                    gid = f"{info.id}:{raw.local_id}"
                    if raw.error is not None:
                        issues[raw.local_id] = [f"unreadable record file: {raw.error}"]
                        if gid in prev_by_id:  # keep what it was
                            got.append(prev_by_id[gid])
                        continue
                    old = reusable.get(gid)
                    if old is not None and old.provenance.source_hash == raw.sha256:
                        if old.provenance.record_url != raw.record_url:  # the source's link changed in config
                            prov = old.provenance.model_copy(update={"record_url": raw.record_url})
                            old = old.model_copy(update={"provenance": prov})
                        got.append(old)
                        if raw.local_id in last_issues:  # its issues are still true
                            issues[raw.local_id] = last_issues[raw.local_id]
                        n_reused += 1
                        continue
                    try:
                        result = binding.translator.translate(raw, info, standard, now)
                        if result.resource is None:
                            if result.issues:
                                issues[raw.local_id] = result.issues
                            continue
                        quality = self._assessor.assess(result.resource.to_record())
                    except Exception as exc:  # one record must not fail its source
                        log.exception("record %s could not be translated", gid)
                        issues[raw.local_id] = [f"translation failed: {type(exc).__name__}: {exc}"]
                        if gid in prev_by_id:
                            got.append(prev_by_id[gid])
                        continue
                    if result.issues:
                        issues[raw.local_id] = result.issues
                    got.append(result.resource.model_copy(update={"quality": quality}))
                    n_new += 1
                if not got and kept_before:
                    raise RuntimeError(f"no records (the previous harvest had {len(kept_before)})")
            except Exception as exc:  # a source failing must not empty the catalogue
                log.exception("source %s failed", info.id)
                resources.extend(kept_before)
                states.append(
                    SourceState(
                        info.id,
                        info.name,
                        info.homepage,
                        info.format,
                        last.harvested_at if last else None,
                        len(kept_before),
                        last_issues,
                        f"{type(exc).__name__}: {exc}",
                    )
                )
                continue
            resources.extend(got)
            translated[info.id], reused[info.id] = n_new, n_reused
            states.append(SourceState(info.id, info.name, info.homepage, info.format, now, len(got), issues))
        resources = link_same_resources(resources)
        resources = derive_landscapes(resources, _landscape_boxes(standard), _landscape_countries(standard))
        resources.sort(key=lambda r: r.id)
        snapshot = Snapshot(resources, states, standard.version, now, fingerprint=fp)
        self._store.save(snapshot)
        return HarvestReport(snapshot, translated, reused)
