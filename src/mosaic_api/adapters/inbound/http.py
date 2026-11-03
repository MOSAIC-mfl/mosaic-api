"""HTTP adapter (FastAPI). Read-only: only GET routes exist.

The same app is (a) served live with uvicorn when a server is available and (b) called route by
route by the static exporter to produce the files published on GitHub Pages. One contract for both.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from ...application.catalog import API_VERSION, CatalogService
from ...application.dto import Labels, Manifest, Problem, ResourceDetail, ResourcePage, ResourceSummary, SourceOut
from ...domain import search
from ...domain.facets import FACETS
from ...domain.jsonld import to_jsonld

Csv = Annotated[str | None, Query(max_length=500, description="Comma-separated values (OR).")]


DOCS_PATHS = ("/docs", "/redoc")
# JSON responses never need to load anything: lock them down completely.
API_CSP = "default-src 'none'; frame-ancestors 'none'"
# The documentation pages (Swagger UI / ReDoc) load their script and styles from jsDelivr and run an
# inline bootstrap script; they get exactly that and nothing more.
DOCS_CSP = (
    "default-src 'none'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; img-src 'self' data: https://fastapi.tiangolo.com https://cdn.redoc.ly; "
    "connect-src 'self'; worker-src blob:; frame-ancestors 'none'"
)


class SecurityHeaders(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["X-Frame-Options"] = "DENY"
        is_docs = request.url.path.startswith(DOCS_PATHS)
        resp.headers["Content-Security-Policy"] = DOCS_CSP if is_docs else API_CSP
        resp.headers.setdefault("Cache-Control", "public, max-age=300")
        return resp


def wants_html(request: Request) -> bool:
    """A browser navigating to a page asks for HTML first (Accept: text/html,...). API clients
    (fetch, httpx, curl) ask for JSON or */*. Content negotiation, not the User-Agent: a fetch()
    from the website also carries a browser User-Agent and must still get JSON."""
    accept = request.headers.get("accept", "")
    return "text/html" in accept.split(",")[0] or accept.startswith("text/html")


def _split(value: str | None) -> frozenset[str]:
    return frozenset(v.strip() for v in value.split(",") if v.strip()) if value else frozenset()


def create_app(catalog: CatalogService, cors_origins: list[str] | None = None, max_page_size: int = 100) -> FastAPI:
    app = FastAPI(
        title="MOSAIC API",
        version=API_VERSION,
        description=(
            "Read-only API of MOSAIC, a network of metadata. It gathers records from several catalogues "
            "(MOSAIC, CGIAR Climate Data Hub, ...) and serves them in the MOSAIC metadata model. "
            "Each resource keeps its provenance: MOSAIC links to the data where it lives."
        ),
        responses={422: {"model": Problem}, 404: {"model": Problem}},
    )
    app.add_middleware(SecurityHeaders)
    if cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=cors_origins, allow_methods=["GET"], allow_headers=[])

    @app.exception_handler(HTTPException)
    async def http_problem(_: Request, exc: HTTPException) -> JSONResponse:
        body = Problem(title=str(exc.detail), status=exc.status_code)
        return JSONResponse(body.model_dump(), status_code=exc.status_code, media_type="application/problem+json")

    @app.exception_handler(RequestValidationError)
    async def validation_problem(_: Request, exc: RequestValidationError) -> JSONResponse:
        detail = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        body = Problem(title="Invalid request", status=422, detail=detail)
        return JSONResponse(body.model_dump(), status_code=422, media_type="application/problem+json")

    @app.get("/", include_in_schema=False, response_model=None)
    def root(request: Request) -> RedirectResponse | dict[str, str]:
        """Browsers are sent to the interactive docs; programs get a short description as JSON."""
        if wants_html(request):
            return RedirectResponse(url="/docs", status_code=307)
        return {
            "name": "MOSAIC API",
            "version": API_VERSION,
            "description": "Read-only API of MOSAIC, a network of metadata.",
            "docs": "/docs",
            "openapi": "/openapi.json",
            "manifest": "/v1/manifest",
        }

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/manifest", response_model=Manifest, tags=["catalogue"])
    def manifest() -> Manifest:
        return catalog.manifest()

    @app.get("/v1/sources", response_model=list[SourceOut], tags=["catalogue"])
    def sources() -> list[SourceOut]:
        """Catalogues MOSAIC reads from, with the date and outcome of the last harvest."""
        return catalog.sources()

    @app.get(
        "/v1/facets",
        response_model=dict[str, dict[str, int]],
        tags=["catalogue"],
        description="Counts per filter value over the whole catalogue. Facets: " + ", ".join(FACETS),
    )
    def facets() -> dict[str, dict[str, int]]:
        return catalog.facets()

    @app.get("/v1/labels", response_model=Labels, tags=["catalogue"])
    def labels() -> Labels:
        """Display labels for facet values (from the MOSAIC vocabularies)."""
        return catalog.labels()

    @app.get("/v1/resources", response_model=ResourcePage, tags=["resources"])
    def list_resources(
        q: Annotated[str, Query(max_length=200, description="Words to search (all must match).")] = "",
        source: Csv = None,
        resource_type: Csv = None,
        theme: Csv = None,
        landscape: Csv = None,
        geography: Csv = None,
        data_kind: Csv = None,
        geometry: Csv = None,
        spatial: Csv = None,
        method: Csv = None,
        access: Csv = None,
        license: Csv = None,
        status: Csv = None,
        bbox: Annotated[
            str | None, Query(pattern=r"^-?[\d.]+,-?[\d.]+,-?[\d.]+,-?[\d.]+$", description="west,south,east,north")
        ] = None,
        year_from: Annotated[int | None, Query(ge=1000, le=3000)] = None,
        year_to: Annotated[int | None, Query(ge=1000, le=3000)] = None,
        sort: search.Sort = search.Sort.RELEVANCE,
        page: Annotated[int, Query(ge=1, le=100_000)] = 1,
        page_size: Annotated[int, Query(ge=1)] = 20,
        include_facets: bool = False,
    ) -> ResourcePage:
        """Search and filter. OR inside one filter (comma-separated), AND across filters."""
        if page_size > max_page_size:
            raise HTTPException(422, f"page_size must be at most {max_page_size}")
        values = {
            "source": source,
            "resource_type": resource_type,
            "theme": theme,
            "landscape": landscape,
            "geography": geography,
            "data_kind": data_kind,
            "geometry": geometry,
            "spatial": spatial,
            "method": method,
            "access": access,
            "license": license,
            "status": status,
        }
        box = None
        if bbox:
            w, s, e, n = (float(x) for x in bbox.split(","))
            if not (-180 <= w <= 180 and -180 <= e <= 180 and -90 <= s <= n <= 90):
                raise HTTPException(422, "bbox out of range")
            box = (w, s, e, n)
        query = search.Query(
            text=q,
            filters={k: _split(v) for k, v in values.items() if v},
            bbox=box,
            year_from=year_from,
            year_to=year_to,
            sort=sort,
            page=page,
            page_size=page_size,
        )
        return catalog.search(query, with_facets=include_facets)

    @app.get("/v1/resources/{source_id}/{local_id}", response_model=ResourceDetail, tags=["resources"])
    def get_resource(source_id: str, local_id: str) -> ResourceDetail:
        """One resource: the full record in the MOSAIC model, its provenance and its quality."""
        found = catalog.get(f"{source_id}:{local_id}")
        if found is None:
            raise HTTPException(404, "resource not found")
        return found

    @app.get("/v1/resources/{source_id}/{local_id}/jsonld", tags=["resources"])
    def get_resource_jsonld(source_id: str, local_id: str) -> JSONResponse:
        """schema.org Dataset (JSON-LD), for search engines and FAIR harvesters."""
        found = catalog.get(f"{source_id}:{local_id}")
        if found is None:
            raise HTTPException(404, "resource not found")
        return JSONResponse(to_jsonld(found.record, found.provenance.record_url), media_type="application/ld+json")

    @app.get("/v1/summaries", response_model=list[ResourceSummary], tags=["resources"])
    def summaries() -> list[ResourceSummary]:
        """Every resource as a light card (what the static site loads for in-browser search)."""
        return catalog.summaries()

    return app
