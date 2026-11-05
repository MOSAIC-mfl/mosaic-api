"""HTTP adapter (FastAPI). Read-only: only GET routes exist.

The same app is (a) served live with uvicorn when a server is available and (b) called route by
route by the static exporter to produce the files published on GitHub Pages. One contract for both.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from ...application.catalog import API_VERSION, CatalogService
from ...application.dto import (
    FiltersOut,
    LandscapeOut,
    LandscapeSummaryOut,
    Problem,
    ResourceDetail,
    ResourcePage,
    SourceOut,
)
from ...application.landscapes import LandscapeService
from ...domain import search


class Order(str, Enum):
    ASC = "asc"
    DESC = "desc"

    @classmethod
    def _missing_(cls, value: object) -> Order | None:
        return next((m for m in cls if m.value == str(value).strip().lower()), None)


def _csv(what: str) -> Any:
    return Query(
        max_length=500, description=f"{what}. Comma-separated values (OR). Values and labels: GET /v1/filters."
    )


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


def create_app(
    catalog: CatalogService,
    cors_origins: list[str] | None = None,
    max_page_size: int = 100,
    landscapes: LandscapeService | None = None,
) -> FastAPI:
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
            "endpoints": "/v1/sources, /v1/filters, /v1/resources, /v1/resources/{source}/{id}, /v1/landscapes",
        }

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/sources", response_model=list[SourceOut], tags=["catalogue"])
    def sources() -> list[SourceOut]:
        """The catalogues MOSAIC reads (MOSAIC, CGIAR Climate Data Hub, ...): how many records each
        one has, and the date and outcome of the last harvest."""
        return catalog.sources()

    @app.get("/v1/filters", response_model=FiltersOut, tags=["catalogue"])
    def filters() -> FiltersOut:
        """Read once before searching: versions and totals, the filters of GET /v1/resources with
        every option (value, label, count), and display labels for the other coded values."""
        return catalog.filters()

    @app.get("/v1/resources", response_model=ResourcePage, tags=["resources"])
    def list_resources(
        q: Annotated[str, Query(max_length=200, description="Words to search (all must match).")] = "",
        source: Annotated[str | None, _csv("Catalogue, e.g. mosaic, cdh")] = None,
        theme: Annotated[str | None, _csv("Theme, e.g. water")] = None,
        landscape: Annotated[str | None, _csv("Living landscape, e.g. KEN-LVB")] = None,
        geography: Annotated[str | None, _csv("Country or region, e.g. KEN")] = None,
        sort: search.Sort = search.Sort.RELEVANCE,
        order: Annotated[Order | None, Query(description="asc | desc; default: the sort's natural order.")] = None,
        page: Annotated[int, Query(ge=1, le=100_000)] = 1,
        page_size: Annotated[int, Query(ge=1)] = 20,
        include_facets: Annotated[
            bool, Query(description="Also return the count of each filter value over all the results.")
        ] = False,
    ) -> ResourcePage:
        """The catalogue: search and filter. OR inside one filter (comma-separated), AND across
        filters. Values are case-, accent- and symbol-insensitive, and a label works as well as its id."""
        if page_size > max_page_size:
            raise HTTPException(422, f"page_size must be at most {max_page_size}")
        values = {"source": source, "theme": theme, "landscape": landscape, "geography": geography}
        query = search.Query(
            text=q,
            filters={k: _split(v) for k, v in values.items() if v},
            sort=sort,
            descending=None if order is None else order == Order.DESC,
            page=page,
            page_size=page_size,
        )
        return catalog.search(query, with_facets=include_facets)

    @app.get("/v1/resources/{source_id}/{local_id}", response_model=ResourceDetail, tags=["resources"])
    def get_resource(source_id: str, local_id: str) -> ResourceDetail:
        """One resource, by catalogue and id: the full record in the MOSAIC model, where it comes from
        (provenance) and how complete it is (quality)."""
        found = catalog.get(f"{source_id}:{local_id}")
        if found is None:
            raise HTTPException(404, "resource not found")
        return found

    if landscapes is not None:

        @app.get("/v1/landscapes", response_model=list[LandscapeSummaryOut], tags=["landscapes"])
        def list_landscapes() -> list[LandscapeSummaryOut]:
            """Every living landscape with its page sections and how many resources cover it."""
            return landscapes.list()

        @app.get("/v1/landscapes/{code}", response_model=LandscapeOut, tags=["landscapes"])
        def get_landscape(code: str) -> LandscapeOut:
            """One landscape page: its profile (sections and their configuration) and its data status.
            The code is case-insensitive (KEN-LVB or ken-lvb)."""
            found = landscapes.get(code)
            if found is None:
                raise HTTPException(404, "landscape not found")
            return found

    return app
