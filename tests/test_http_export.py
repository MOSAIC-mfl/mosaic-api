"""The HTTP contract, its safety rules, and the static export (same answers as the live API)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mosaic_api.adapters.fetch import FetchError, Location, SafeFetcher
from mosaic_api.adapters.inbound.exporter import export
from mosaic_api.adapters.inbound.http import create_app
from mosaic_api.application.catalog import CatalogService
from mosaic_api.domain.facets import FILTERS


@pytest.fixture
def client(catalog: CatalogService) -> TestClient:
    return TestClient(create_app(catalog, ["http://localhost:4321"], max_page_size=50))


def test_search_and_filters(client: TestClient) -> None:
    page = client.get("/v1/records", params={"q": "forest", "include_facets": True}).json()
    assert [i["id"] for i in page["items"]] == ["mosaic:MFL-2026-079"]
    assert page["facets"]["source"] == {"mosaic": 1}
    assert set(page["facets"]) == set(FILTERS)
    cdh = client.get("/v1/records", params={"source": "cdh"}).json()
    assert cdh["total"] == 3 and {i["source"] for i in cdh["items"]} == {"cdh"}


def test_only_the_listed_filters_exist(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    params = {p["name"] for p in spec["paths"]["/v1/records"]["get"]["parameters"]}
    assert params == {
        "q",
        *FILTERS,
        "sort",
        "order",
        "page",
        "page_size",
        "include_facets",
    }
    assert set(spec["paths"]) == {
        "/v1/sources",
        "/v1/records",
        "/v1/records/{source_id}/{local_id}",
        "/v1/landscapes",
        "/v1/landscapes/{code}",
    } - ({"/v1/landscapes", "/v1/landscapes/{code}"} - set(spec["paths"]))


def test_five_endpoints_and_no_filters_endpoint(client: TestClient) -> None:
    # the filter options and their labels live in the website; the API answers 404 for /v1/filters
    assert client.get("/v1/filters").status_code == 404
    assert client.get("/v1/resources").status_code == 404
    paths = set(client.app.openapi()["paths"])  # type: ignore[attr-defined]
    assert paths == {"/v1/sources", "/v1/records", "/v1/records/{source_id}/{local_id}"}  # + 2 landscape routes
    page = client.get("/v1/records", params={"include_facets": True}).json()
    assert page["facets"]["source"] == {"mosaic": 4, "cdh": 3}  # counts per value, for the client


def test_record_detail(client: TestClient) -> None:
    d = client.get("/v1/records/cdh/esa-worldcover-2021").json()
    assert d["record"]["id"] == "esa-worldcover-2021"
    assert d["provenance"]["source_name"] == "CGIAR Climate Data Hub"
    # metadata completeness is internal (the standard's review lists), not part of the public API
    assert "quality" not in d and "status" not in d["facets"]
    summary = client.get("/v1/records").json()["items"][0]
    assert "status" not in summary and "completeness" not in summary
    for gone in (
        "/v1/manifest",
        "/v1/facets",
        "/v1/labels",
        "/v1/summaries",
        "/v1/records/cdh/esa-worldcover-2021/jsonld",
    ):
        assert client.get(gone).status_code == 404, gone


def test_errors_are_problem_json(client: TestClient) -> None:
    r = client.get("/v1/records/mosaic/NOPE")
    assert r.status_code == 404 and r.headers["content-type"] == "application/problem+json"
    assert client.get("/v1/records", params={"page_size": 51}).status_code == 422
    assert client.get("/v1/records", params={"q": "x" * 201}).status_code == 422


def test_read_only_and_headers(client: TestClient) -> None:
    assert client.post("/v1/records").status_code == 405
    r = client.get("/v1/sources", headers={"Origin": "http://localhost:4321"})
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["access-control-allow-origin"] == "http://localhost:4321"
    other = client.get("/v1/sources", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in other.headers


def test_emails_can_be_hidden(catalog: CatalogService) -> None:
    from mosaic_api.application.catalog import CatalogOptions

    hidden = CatalogService(catalog._snap, catalog._std, CatalogOptions(expose_emails=False))  # type: ignore[attr-defined]
    detail = hidden.get("mosaic:MFL-2026-079")
    assert detail is not None and all("email" not in c for c in detail.record["contact"])


def test_static_export_matches_live_api(tmp_path: Path, catalog: CatalogService, client: TestClient) -> None:
    out = tmp_path / "site"
    summary = export(client.app, catalog, out)  # type: ignore[arg-type]
    assert summary["records"] == 7 and summary["standard_version"]
    index = json.loads((out / "v1/_index/index.json").read_text(encoding="utf-8"))
    for ref in [*index["summaries"], index["search"]]:
        data = (out / ref["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == ref["sha256"]
    on_disk = json.loads((out / "v1/records/mosaic/MFL-2026-104.json").read_text(encoding="utf-8"))
    assert on_disk == client.get("/v1/records/mosaic/MFL-2026-104").json()
    for name in ("sources",):
        assert json.loads((out / f"v1/{name}.json").read_text(encoding="utf-8")) == client.get(f"/v1/{name}").json()
    assert not list(out.rglob("*.jsonld")) and not (out / "v1/manifest.json").exists()
    everything = json.loads((out / "v1/records.json").read_text(encoding="utf-8"))
    assert everything["total"] == 7 and len(everything["items"]) == 7
    assert set(everything["facets"]) == set(FILTERS)
    assert 'http-equiv="refresh" content="0; url=docs/"' in (out / "index.html").read_text(encoding="utf-8")
    assert (out / "v1/openapi.json").exists() and (out / ".nojekyll").exists()


def test_static_docs_describe_the_files(tmp_path: Path, catalog: CatalogService, client: TestClient) -> None:
    out = tmp_path / "site"
    export(client.app, catalog, out)  # type: ignore[arg-type]
    assert "swagger-ui-bundle.js" in (out / "docs/index.html").read_text(encoding="utf-8")
    spec = json.loads((out / "docs/openapi.json").read_text(encoding="utf-8"))
    assert spec["servers"] == [{"url": "..", "description": "This site"}]
    for path in spec["paths"]:
        assert path.endswith(".json")
        concrete = (
            path.replace("{source_id}", "mosaic").replace("{local_id}", "MFL-2026-079").replace("{code}", "PER-PCL")
        )
        if "landscapes" not in concrete:
            assert (out / concrete.lstrip("/")).exists(), concrete


def test_fetcher_refuses_unsafe_locations(tmp_path: Path) -> None:
    f = SafeFetcher(frozenset({"example.org"}))
    with pytest.raises(FetchError):
        f.check("http://example.org/x")  # not https
    with pytest.raises(FetchError):
        f.check("https://evil.example/x")  # host not allowed
    (tmp_path / "a").mkdir()
    with pytest.raises(FetchError):
        Location(str(tmp_path / "a"), f).read("../secret")


def test_openapi_lists_only_get_routes(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    methods = {m for path in spec["paths"].values() for m in path}
    assert methods == {"get"}
    assert "/v1/records/{source_id}/{local_id}" in spec["paths"]


def test_root_redirects_browsers_only(client: TestClient) -> None:
    browser = client.get(
        "/",
        headers={"Accept": "text/html,application/xhtml+xml,*/*;q=0.8", "User-Agent": "Mozilla/5.0"},
        follow_redirects=False,
    )
    assert browser.status_code == 307 and browser.headers["location"] == "/docs"
    # fetch() from the website: browser User-Agent, but it asks for JSON -> no redirect
    fetch = client.get("/", headers={"Accept": "*/*", "User-Agent": "Mozilla/5.0"}, follow_redirects=False)
    assert fetch.status_code == 200 and fetch.json()["docs"] == "/docs"
    assert client.get("/", headers={"Accept": "application/json"}).json()["name"] == "MOSAIC API"
    # API routes are never redirected, whatever the client asks for
    assert client.get("/v1/sources", headers={"Accept": "text/html"}, follow_redirects=False).status_code == 200


def test_docs_page_may_load_swagger_ui(client: TestClient) -> None:
    docs = client.get("/docs")
    assert docs.status_code == 200
    assert "https://cdn.jsdelivr.net" in docs.headers["content-security-policy"]
    assert client.get("/v1/sources").headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"source": "MOSAIC"}, 4),
        ({"source": " Mosaic "}, 4),
        ({"source": "cdh"}, 3),
        ({"geography": "PER"}, 1),
        ({"geography": "per"}, 1),
        ({"geography": "Perú"}, 1),  # label, with an accent
        ({"theme": "Pressures / drivers"}, 1),  # label with symbols
        ({"theme": "PRESSURES-DRIVERS"}, 1),
        ({"landscape": "per-pcl"}, 1),
        ({"q": "DEFORESTACIÓN FOREST"}, 0),  # every word must appear
        ({"q": "  Forest   LOSS "}, 1),
        ({"q": "non-forest"}, 1),  # hyphen in the text and in the query
    ],
)
def test_filters_and_search_ignore_case_accents_and_symbols(
    client: TestClient, params: dict[str, str], expected: int
) -> None:
    page = client.get("/v1/records", params=params).json()
    assert page["total"] == expected, page
    assert page["warnings"] == []


def test_unknown_filter_value_is_reported(client: TestClient) -> None:
    page = client.get("/v1/records", params={"theme": "astrology"}).json()
    assert page["total"] == 0 and page["warnings"] == ["theme='astrology' matches no value of this filter"]


def test_sort_and_ids_ignore_case(client: TestClient) -> None:
    assert client.get("/v1/records", params={"sort": "Title"}).status_code == 200
    assert client.get("/v1/records", params={"sort": "nonsense"}).status_code == 422
    detail = client.get("/v1/records/MOSAIC/mfl-2026-079")
    assert detail.status_code == 200 and detail.json()["id"] == "mosaic:MFL-2026-079"


def test_sort_order_and_summary_fields(client: TestClient) -> None:
    az = [i["title"] for i in client.get("/v1/records", params={"sort": "title"}).json()["items"]]
    za = [i["title"] for i in client.get("/v1/records", params={"sort": "title", "order": "DESC"}).json()["items"]]
    assert za == list(reversed(az))
    item = client.get("/v1/records", params={"q": "worldcover"}).json()["items"][0]
    assert item["producer"] == "European Space Agency (ESA)"
    assert item["access_url"].startswith("https://")


def test_processing_status_is_declared_never_inferred(client: TestClient) -> None:
    page = client.get("/v1/records", params={"processing_status": "validated", "include_facets": True}).json()
    assert [i["id"] for i in page["items"]] == ["mosaic:MFL-2026-079"]
    assert page["items"][0]["processing_status"] == "validated"
    stated = client.get("/v1/records", params={"include_facets": True, "page_size": 50}).json()
    assert stated["facets"]["processing_status"]["validated"] == 1
    assert stated["facets"]["processing_status"]["not_specified"] == stated["total"] - 1
    cdh = [i for i in stated["items"] if i["source"] == "cdh"]
    assert cdh and all(i["processing_status"] is None for i in cdh)


def test_more_filters_by_kind_access_and_licence(client: TestClient) -> None:
    every = client.get("/v1/records", params={"include_facets": True}).json()
    for facet in ("data_kind", "access", "license"):
        value, n = next(iter(every["facets"][facet].items()))
        page = client.get("/v1/records", params={facet: value}).json()
        assert page["total"] == n, facet


def test_summary_gives_the_resolution_as_text(client: TestClient) -> None:
    items = client.get("/v1/records", params={"page_size": 50}).json()["items"]
    shown = [i["resolution"] for i in items if i["resolution"]]
    assert shown and all(isinstance(x, str) and x.strip() for x in shown)
