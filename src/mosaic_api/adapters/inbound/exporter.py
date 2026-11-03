"""Static exporter: writes the API as files for GitHub Pages (no server, no database).

It calls the FastAPI app route by route (TestClient), so every file is exactly what the live API
would return. Layout under the export folder:

    v1/manifest.json                     entry point: counts, versions and the files below with hashes
    v1/sources.json, v1/facets.json, v1/labels.json
    v1/summaries/<sha8>.json             resource cards, in shards of SHARD_SIZE (content-hashed,
                                         never change: browsers and the CDN cache them for good)
    v1/search/<sha8>.json                normalized searchable text per resource (in-browser search)
    v1/resources/<source>/<id>.json      one resource (= GET /v1/resources/<source>/<id>)
    v1/resources/<source>/<id>.jsonld    schema.org Dataset
    v1/landscapes.json                   living landscapes and their page sections (= GET /v1/landscapes)
    v1/landscapes/<CODE>.json            one landscape page (= GET /v1/landscapes/<CODE>)
    v1/openapi.json                      the contract (TypeScript types for the website come from it)

Only manifest.json changes name-stably; a client reads it first and fetches the hashed files it
does not have yet.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ...application.catalog import CatalogService

SHARD_SIZE = 2000


def _dump(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _write(root: Path, rel: str, data: bytes) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _hashed(root: Path, folder: str, data: bytes) -> dict[str, Any]:
    digest = hashlib.sha256(data).hexdigest()
    rel = f"v1/{folder}/{digest[:12]}.json"
    _write(root, rel, data)
    return {"path": rel, "sha256": digest}


def export(app: FastAPI, catalog: CatalogService, out: Path) -> dict[str, Any]:
    client = TestClient(app)

    def get(url: str) -> Any:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.json()

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / ".nojekyll").write_bytes(b"")
    files: dict[str, Any] = {}
    for name in ("sources", "facets", "labels"):
        _write(out, f"v1/{name}.json", _dump(get(f"/v1/{name}")))
        files[name] = f"v1/{name}.json"
    _write(out, "v1/openapi.json", _dump(app.openapi()))
    files["openapi"] = "v1/openapi.json"

    summaries = get("/v1/summaries")
    files["summaries"] = []
    for i in range(0, max(len(summaries), 1), SHARD_SIZE):
        shard = summaries[i : i + SHARD_SIZE]
        files["summaries"].append({**_hashed(out, "summaries", _dump(shard)), "records": len(shard)})
    files["search"] = {**_hashed(out, "search", _dump(catalog.search_texts())), "records": len(summaries)}

    for r in catalog.resources:
        source, local = r.gid.source, r.gid.local_id
        _write(out, f"v1/resources/{source}/{local}.json", _dump(get(f"/v1/resources/{source}/{local}")))
        _write(out, f"v1/resources/{source}/{local}.jsonld", _dump(get(f"/v1/resources/{source}/{local}/jsonld")))
    files["resource"] = "v1/resources/{source}/{local_id}.json"
    files["resource_jsonld"] = "v1/resources/{source}/{local_id}.jsonld"

    if any(r.path == "/v1/landscapes" for r in app.routes if hasattr(r, "path")):
        index = get("/v1/landscapes")
        _write(out, "v1/landscapes.json", _dump(index))
        for land in index:
            _write(out, f"v1/landscapes/{land['code']}.json", _dump(get(f"/v1/landscapes/{land['code']}")))
        files["landscapes"] = "v1/landscapes.json"
        files["landscape"] = "v1/landscapes/{code}.json"

    manifest = {**get("/v1/manifest"), "files": files}
    _write(out, "v1/manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1).encode("utf-8"))
    _write(out, "index.html", _index_html(manifest).encode("utf-8"))
    return manifest


def _index_html(manifest: dict[str, Any]) -> str:
    c = manifest["counts"]
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>MOSAIC API</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<body style="font-family:system-ui,sans-serif;max-width:46rem;margin:2rem auto;padding:0 1rem;line-height:1.5">
<h1>MOSAIC API (static)</h1>
<p>{c["resources"]} resources from {", ".join(manifest["sources"])}; standard v{manifest["standard_version"]};
harvested {manifest["harvested_at"]}.</p>
<p>Start at <a href="v1/manifest.json">v1/manifest.json</a>.
Contract: <a href="v1/openapi.json">v1/openapi.json</a>.</p>
</body></html>
"""
