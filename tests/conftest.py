from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from mosaic_api.adapters.fetch import Location, SafeFetcher
from mosaic_api.adapters.quality.schema_assessor import SchemaAssessor
from mosaic_api.adapters.sources.git_yaml import GitYamlSource
from mosaic_api.adapters.sources.mosaic_catalog import MosaicCatalogSource
from mosaic_api.adapters.standard.dist import DistStandard
from mosaic_api.adapters.store.fs_json import FileSnapshotStore
from mosaic_api.adapters.translators.cdh import CdhTranslator
from mosaic_api.adapters.translators.mosaic import MosaicTranslator
from mosaic_api.application.catalog import CatalogService
from mosaic_api.application.harvest import HarvestService, SourceBinding
from mosaic_api.domain.standard import Standard
from mosaic_api.ports.sources import SourceInfo

FIX = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
FETCHER = SafeFetcher(frozenset({"example.org"}))
MOSAIC = SourceInfo("mosaic", "MOSAIC", None, "mosaic-v0.1")
CDH = SourceInfo("cdh", "CGIAR Climate Data Hub", None, "cdh-yaml-v0.5")


@pytest.fixture(scope="session")
def dist_standard() -> DistStandard:
    return DistStandard(Location(str(FIX / "standard"), FETCHER))


@pytest.fixture(scope="session")
def standard(dist_standard: DistStandard) -> Standard:
    return dist_standard.load()


def make_harvest(
    tmp_path: Path, dist_standard: DistStandard, extra: list[SourceBinding] | None = None
) -> HarvestService:
    bindings = [
        SourceBinding(MosaicCatalogSource(MOSAIC, Location(str(FIX / "mosaic"), FETCHER)), MosaicTranslator()),
        SourceBinding(GitYamlSource(CDH, str(FIX / "cdh"), FETCHER), CdhTranslator()),
        *(extra or []),
    ]
    store = FileSnapshotStore(tmp_path / "snapshot.json")
    return HarvestService(dist_standard, bindings, SchemaAssessor(dist_standard.schemas()), store, clock=lambda: NOW)


@pytest.fixture
def catalog(tmp_path: Path, dist_standard: DistStandard, standard: Standard) -> CatalogService:
    report = make_harvest(tmp_path, dist_standard).run()
    return CatalogService(report.snapshot, standard)
