"""Composition root: the only place where adapters are chosen and wired to the ports."""

from __future__ import annotations

from pathlib import Path

from .adapters.fetch import Location, SafeFetcher
from .adapters.landscapes.dist import DistLandscapes
from .adapters.quality.schema_assessor import SchemaAssessor
from .adapters.sources.git_yaml import GitYamlSource
from .adapters.sources.mosaic_catalog import MosaicCatalogSource
from .adapters.standard.dist import DistStandard
from .adapters.store.fs_json import FileSnapshotStore
from .adapters.translators.cdh import CdhTranslator
from .adapters.translators.mosaic import MosaicTranslator
from .application.catalog import CatalogOptions, CatalogService
from .application.harvest import HarvestService, SourceBinding
from .application.landscapes import LandscapeService
from .config import Settings, SourceConfig
from .ports import CatalogSource, Translator
from .ports.sources import SourceInfo

TRANSLATORS: dict[str, type[MosaicTranslator] | type[CdhTranslator]] = {
    "mosaic": MosaicTranslator,
    "cdh": CdhTranslator,
}


def fetcher(settings: Settings) -> SafeFetcher:
    return SafeFetcher(frozenset(settings.allowed_hosts), max_bytes=settings.max_download_mb * 1024 * 1024)


def standard(settings: Settings) -> DistStandard:
    return DistStandard(Location(settings.resolve(settings.standard), fetcher(settings)))


def source(cfg: SourceConfig, settings: Settings) -> CatalogSource:
    info = SourceInfo(cfg.id, cfg.name, cfg.homepage, cfg.format)
    location = settings.resolve(cfg.location)
    if cfg.type == "mosaic_catalog":
        return MosaicCatalogSource(info, Location(location, fetcher(settings)), cfg.record_url_template)
    return GitYamlSource(info, location, fetcher(settings), cfg.ref, cfg.pattern, cfg.record_url_template)


def harvest_service(settings: Settings) -> HarvestService:
    std = standard(settings)
    bindings = []
    for cfg in settings.sources:
        if cfg.enabled:
            translator: Translator = TRANSLATORS[cfg.translator]()
            bindings.append(SourceBinding(source(cfg, settings), translator))
    return HarvestService(std, bindings, SchemaAssessor(std.schemas()), snapshot_store(settings))


def snapshot_store(settings: Settings) -> FileSnapshotStore:
    return FileSnapshotStore(Path(settings.resolve(settings.state)))


def catalog_service(settings: Settings) -> CatalogService:
    snap = snapshot_store(settings).load()
    if snap is None:
        raise RuntimeError("no harvested data yet: run `python -m mosaic_api harvest` first")
    return CatalogService(snap, standard(settings).load(), CatalogOptions(expose_emails=settings.http.expose_emails))


def landscape_service(settings: Settings, catalog: CatalogService) -> LandscapeService:
    """Profiles are read from the same place as the standard (mosaic-catalog's published dist)."""
    return LandscapeService(DistLandscapes(Location(settings.resolve(settings.standard), fetcher(settings))), catalog)
