"""docs/openapi.json is the contract the website generates its types from: it must match the code."""

from __future__ import annotations

import json
from pathlib import Path

from mosaic_api.adapters.inbound.http import create_app
from mosaic_api.application.catalog import CatalogService
from mosaic_api.application.landscapes import LandscapeService

CONTRACT = Path(__file__).resolve().parents[1] / "docs" / "openapi.json"


def test_docs_openapi_matches_the_code(catalog: CatalogService, landscapes: LandscapeService) -> None:
    current = create_app(catalog, [], 100, landscapes).openapi()
    stored = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert stored == current, (
        "docs/openapi.json is behind the code: python -m mosaic_api openapi --out docs/openapi.json"
    )
