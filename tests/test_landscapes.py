"""Landscape pages: the profile as published by mosaic-catalog, plus the catalogue's data status."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from mosaic_api.adapters.fetch import Location, SafeFetcher
from mosaic_api.adapters.inbound.exporter import export
from mosaic_api.adapters.inbound.http import create_app
from mosaic_api.adapters.landscapes.dist import DistLandscapes
from mosaic_api.application.catalog import CatalogService
from mosaic_api.application.landscapes import LandscapeService


def test_list_and_get(catalog: CatalogService, landscapes: LandscapeService) -> None:
    client = TestClient(create_app(catalog, landscapes=landscapes))
    index = client.get("/v1/landscapes").json()
    assert [x["code"] for x in index] == ["KEN-LVB", "PER-PCL"]
    lvb = index[0]
    assert lvb["curated"] and lvb["records"] == ["mosaic:MFL-2026-090"]
    assert lvb["counts"]["datasets"] >= 1

    page = client.get("/v1/landscapes/ken-lvb").json()  # slug or code, any case
    assert page["code"] == "KEN-LVB" and page["sections"][0]["config"]["overlays"][0]["id"] == "conflicts"
    assert [r["id"] for r in page["linked"]] == ["mosaic:MFL-2026-090"]
    status = page["data_status"]
    assert status["total"] == status["complete"] + status["incomplete"] == lvb["counts"]["datasets"]
    assert client.get("/v1/landscapes/XXX-YY").status_code == 404


def test_data_status_counts_resources_of_the_landscape(catalog: CatalogService, landscapes: LandscapeService) -> None:
    pcl = landscapes.get("PER-PCL")
    assert pcl is not None
    covering = [r for r in catalog.resources if "PER-PCL" in r.landscapes]
    assert pcl.data_status.total == len(covering) > 0
    assert sum(pcl.data_status.by_access.values()) >= pcl.data_status.total


def test_no_profiles_published_means_no_landscapes(tmp_path: Path, catalog: CatalogService) -> None:
    empty = LandscapeService(DistLandscapes(Location(str(tmp_path), SafeFetcher(frozenset()))), catalog)
    assert empty.list() == []


def test_export_writes_landscape_files(tmp_path: Path, catalog: CatalogService, landscapes: LandscapeService) -> None:
    out = tmp_path / "site"
    manifest = export(create_app(catalog, landscapes=landscapes), catalog, out)
    assert manifest["files"]["landscape"] == "v1/landscapes/{code}.json"
    page = json.loads((out / "v1/landscapes/KEN-LVB.json").read_text(encoding="utf-8"))
    assert page["title"] == "Lake Victoria Basin"
    assert len(json.loads((out / "v1/landscapes.json").read_text(encoding="utf-8"))) == 2
