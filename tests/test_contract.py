"""docs/openapi.json is the contract the website generates its types from: it must match the code."""

from __future__ import annotations

import json
from pathlib import Path

from mosaic_api.adapters.inbound.http import create_app
from mosaic_api.application.catalog import CatalogService
from mosaic_api.application.landscapes import LandscapeService

CONTRACT = Path(__file__).resolve().parents[1] / "docs" / "openapi.json"


def _same_on_every_python(spec: str) -> str:
    """FastAPI names the 422 response after Python's HTTP status phrase, which Python 3.13 renamed
    ("Unprocessable Entity" -> "Unprocessable Content"). The file is written with the pipeline's Python
    (3.12, as published on Pages); the comparison ignores that one wording."""
    return spec.replace('"Unprocessable Content"', '"Unprocessable Entity"')


def test_docs_openapi_matches_the_code(catalog: CatalogService, landscapes: LandscapeService) -> None:
    current = json.loads(_same_on_every_python(json.dumps(create_app(catalog, [], 100, landscapes).openapi())))
    stored = json.loads(_same_on_every_python(CONTRACT.read_text(encoding="utf-8")))
    assert stored == current, (
        "docs/openapi.json is behind the code: python -m mosaic_api openapi --out docs/openapi.json"
    )
