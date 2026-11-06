"""Static exporter: writes the API as files for GitHub Pages (no server, no database).

It calls the FastAPI app route by route (TestClient), so every file is exactly what the live API
would return. Layout under the export folder:

    v1/sources.json                      = GET /v1/sources
    v1/records.json                      = GET /v1/records with no filters: the whole catalogue
                                           (every record as a card, with the counts per filter)
    v1/records/<source>/<id>.json        = GET /v1/records/<source>/<id>
    v1/landscapes.json                   = GET /v1/landscapes
    v1/landscapes/<CODE>.json            = GET /v1/landscapes/<CODE>
    v1/openapi.json                      contract of the live API (the website's types come from it)
    docs/                                documentation of these files (Swagger UI, docs/openapi.json)

GitHub Pages only serves files: it ignores ?q= and the filters. Filtering on Pages is done by the
client over v1/records.json (each card carries its filter values in `facets`), or with the live
API. The website searches in the browser, with the same rules, over files kept out of the contract:

    v1/_index/index.json                 the files below, with their hashes
    v1/_index/summaries/<sha12>.json     record cards, in shards of SHARD_SIZE (content-hashed:
                                         they never change, so browsers and the CDN cache them)
    v1/_index/search/<sha12>.json        normalized searchable text per record
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ...application.catalog import CatalogService
from ...domain import search as search_rules

SHARD_SIZE = 2000
# Swagger UI for docs/ (static page on Pages). Pinned; loaded from jsDelivr like the live /docs.
SWAGGER_UI = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14"

# Public files of the static API: live route -> file, and the summary shown in docs/.
STATIC_ROUTES: list[tuple[str, str, str]] = [
    ("/v1/sources", "/v1/sources.json", "Catalogues MOSAIC reads, with their records and last harvest"),
    ("/v1/records", "/v1/records.json", "The whole catalogue: every record as a card, with counts per filter"),
    (
        "/v1/records/{source_id}/{local_id}",
        "/v1/records/{source_id}/{local_id}.json",
        "One record: the record, its provenance and quality",
    ),
    ("/v1/landscapes", "/v1/landscapes.json", "Every living landscape and its page sections"),
    ("/v1/landscapes/{code}", "/v1/landscapes/{code}.json", "One landscape page: profile and data status"),
]


def _dump(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _write(root: Path, rel: str, data: bytes) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _hashed(root: Path, folder: str, data: bytes) -> dict[str, Any]:
    digest = hashlib.sha256(data).hexdigest()
    rel = f"v1/_index/{folder}/{digest[:12]}.json"
    _write(root, rel, data)
    return {"path": rel, "sha256": digest}


def export(app: FastAPI, catalog: CatalogService, out: Path) -> dict[str, Any]:
    """Write the static API to `out` and return a summary (versions and totals)."""
    client = TestClient(app)

    def get(url: str) -> Any:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.json()

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / ".nojekyll").write_bytes(b"")
    routes = {r.path for r in app.routes if hasattr(r, "path")}

    sources = get("/v1/sources")
    _write(out, "v1/sources.json", _dump(sources))
    everything = catalog.search(
        search_rules.Query(sort=search_rules.Sort.TITLE, page_size=max(len(catalog.resources), 1)), with_facets=True
    )
    _write(out, "v1/records.json", _dump(everything.model_dump(mode="json")))
    for r in catalog.resources:
        source, local = r.gid.source, r.gid.local_id
        _write(out, f"v1/records/{source}/{local}.json", _dump(get(f"/v1/records/{source}/{local}")))
    summary = catalog.summary()
    if "/v1/landscapes" in routes:
        index = get("/v1/landscapes")
        _write(out, "v1/landscapes.json", _dump(index))
        for land in index:
            _write(out, f"v1/landscapes/{land['code']}.json", _dump(get(f"/v1/landscapes/{land['code']}")))

    # In-browser search (internal: not part of the public contract).
    summaries = [s.model_dump(mode="json") for s in catalog.summaries()]
    shards = [
        {
            **_hashed(out, "summaries", _dump(summaries[i : i + SHARD_SIZE])),
            "records": len(summaries[i : i + SHARD_SIZE]),
        }
        for i in range(0, max(len(summaries), 1), SHARD_SIZE)
    ]
    search = {**_hashed(out, "search", _dump(catalog.search_texts())), "records": len(summaries)}
    index_file = {"harvested_at": summary["harvested_at"], "summaries": shards, "search": search}
    _write(out, "v1/_index/index.json", json.dumps(index_file, ensure_ascii=False, indent=1).encode("utf-8"))

    live = app.openapi()
    _write(out, "v1/openapi.json", _dump(live))
    _write(out, "docs/openapi.json", json.dumps(static_openapi(live, routes), ensure_ascii=False, indent=1).encode())
    _write(out, "docs/index.html", _docs_html().encode("utf-8"))
    example = summaries[0]["id"].replace(":", "/", 1) if summaries else "mosaic/MFL-2026-079"
    _write(out, "index.html", _index_html(summary, sources, example).encode("utf-8"))
    return summary


def static_openapi(live: dict[str, Any], routes: set[str]) -> dict[str, Any]:
    """The contract of the files on Pages: same schemas as the live API, paths ending in .json.
    The server is the site root ("..", relative to docs/), so "Try it out" works wherever it is hosted."""
    paths: dict[str, Any] = {}
    for route, file, summary in STATIC_ROUTES:
        if route not in routes or route not in live["paths"]:
            continue
        op = copy.deepcopy(live["paths"][route]["get"])
        op["summary"] = summary
        op["operationId"] = "static_" + op.get("operationId", file)
        op["responses"] = {k: v for k, v in op["responses"].items() if k == "200"}
        op["responses"]["404"] = {"description": "No such file (unknown id or code)."}
        if route == "/v1/records":
            op["parameters"] = []
            op["description"] = (
                "Every record as a card (sorted by title), the total, and the count of each filter value. "
                "GitHub Pages serves files, so ?q= and the filters are not available here: filter on the client "
                "with each card's `facets` (source, theme, landscape, geography), or use the live API."
            )
        if route == "/v1/landscapes/{code}":
            for p in op.get("parameters", []):
                if p["name"] == "code":
                    p["description"] = "Landscape code in capitals, e.g. KEN-LVB (files are case-sensitive)."
                    p["example"] = "KEN-LVB"
        for p in op.get("parameters", []):
            if p["name"] == "source_id":
                p["example"] = "mosaic"
            if p["name"] == "local_id":
                p["example"] = "MFL-2026-079"
        paths[file] = {"get": op}
    info = dict(live["info"])
    info["title"] = "MOSAIC API (static files on GitHub Pages)"
    info["description"] = (
        "The MOSAIC API as published on GitHub Pages: one JSON file per answer. These are the same answers "
        "as the live API (see v1/openapi.json). Searching with ?q= and filters needs the live API "
        "(python -m mosaic_api serve); on Pages, the MOSAIC website searches in the browser."
    )
    return {
        "openapi": live["openapi"],
        "info": info,
        "servers": [{"url": "..", "description": "This site"}],
        "paths": paths,
        "components": live.get("components", {}),
    }


def _docs_html() -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>MOSAIC API docs</title>
<link rel="stylesheet" href="{SWAGGER_UI}/swagger-ui.css"></head>
<body><div id="ui"></div>
<script src="{SWAGGER_UI}/swagger-ui-bundle.js"></script>
<script>SwaggerUIBundle({{url: "openapi.json", dom_id: "#ui", tryItOutEnabled: true}})</script>
</body></html>
"""


def _index_html(summary: dict[str, Any], sources: list[dict[str, Any]], example: str) -> str:
    """The site root opens the documentation; the links stay for clients without redirects."""
    names = ", ".join(s["name"] for s in sources)
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>MOSAIC API</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="0; url=docs/">
<link rel="canonical" href="docs/">
<body style="font-family:system-ui,sans-serif;max-width:46rem;margin:2rem auto;padding:0 1rem;line-height:1.5">
<h1>MOSAIC API</h1>
<p>Opening the <a href="docs/">documentation</a>…</p>
<p>{summary["records"]} records from {names}; standard v{summary["standard_version"]};
harvested {summary["harvested_at"]}.
Files: <a href="v1/sources.json">sources</a> · <a href="v1/records.json">records</a> ·
<a href="v1/records/{example}.json">a record</a> · <a href="v1/landscapes.json">landscapes</a></p>
</body></html>
"""
