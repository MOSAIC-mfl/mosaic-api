"""Use case: harvest every configured catalogue into one snapshot of MOSAIC resources.

For each source: read its records -> skip the unchanged ones (same SHA-256 as last time) ->
translate the rest -> assess quality against the MOSAIC minimum -> keep. Then link the same
resource across catalogues (DOI) and derive landscapes from bounding boxes.

A failing source does not stop the harvest: its previous resources are kept and the error is
recorded in the source state, so one catalogue being down never empties the website.
"""

from __future__ import annotations

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


class HarvestService:
    def __init__(
        self,
        standard: StandardProvider,
        bindings: Sequence[SourceBinding],
        assessor: QualityAssessor,
        store: SnapshotStore,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._standard = standard
        self._bindings = bindings
        self._assessor = assessor
        self._store = store
        self._clock = clock

    def run(self) -> HarvestReport:
        standard = self._standard.load()
        previous = self._store.load()
        prev_by_id = {r.id: r for r in (previous.resources if previous else [])}
        prev_sources = {s.id: s for s in (previous.sources if previous else [])}
        now = self._clock()
        resources: list[Resource] = []
        states: list[SourceState] = []
        translated: dict[str, int] = {}
        reused: dict[str, int] = {}
        for binding in self._bindings:
            info = binding.source.info
            issues: dict[str, list[str]] = {}
            got: list[Resource] = []
            n_new = n_reused = 0
            try:
                for raw in binding.source.records():
                    old = prev_by_id.get(f"{info.id}:{raw.local_id}")
                    if old is not None and old.provenance.source_hash == raw.sha256:
                        got.append(old)
                        n_reused += 1
                        continue
                    result = binding.translator.translate(raw, info, standard, now)
                    if result.issues:
                        issues[raw.local_id] = result.issues
                    if result.resource is None:
                        continue
                    quality = self._assessor.assess(result.resource.to_record())
                    got.append(result.resource.model_copy(update={"quality": quality}))
                    n_new += 1
            except Exception as exc:  # a source failing must not empty the catalogue
                log.exception("source %s failed", info.id)
                kept = [r for r in prev_by_id.values() if r.gid.source == info.id]
                resources.extend(kept)
                last = prev_sources.get(info.id)
                states.append(
                    SourceState(
                        info.id,
                        info.name,
                        info.homepage,
                        info.format,
                        last.harvested_at if last else None,
                        len(kept),
                        {},
                        f"{type(exc).__name__}: {exc}",
                    )
                )
                continue
            resources.extend(got)
            translated[info.id], reused[info.id] = n_new, n_reused
            states.append(SourceState(info.id, info.name, info.homepage, info.format, now, len(got), issues))
        resources = link_same_resources(resources)
        resources = derive_landscapes(resources, _landscape_boxes(standard))
        resources.sort(key=lambda r: r.id)
        snapshot = Snapshot(resources, states, standard.version, now)
        self._store.save(snapshot)
        return HarvestReport(snapshot, translated, reused)
