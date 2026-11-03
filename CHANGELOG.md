# Changelog

## [0.1.0] - unreleased (local draft)

### Added
- Landscape pages: `GET /v1/landscapes` and `GET /v1/landscapes/{code}` (static:
  `v1/landscapes.json`, `v1/landscapes/<CODE>.json`). Profiles come from mosaic-catalog's
  `dist/landscapes/` (port `LandscapeProfiles`, adapter `DistLandscapes`); the API adds each
  landscape's data status from the catalogue. A catalogue published without profiles gives an empty
  list, not an error.

### Fixed
- **Filters, sorting and ids now ignore case, accents and symbols:**
  - `source=MOSAIC`, `geography=Perú`, `theme=Pressures / drivers`, `license=cc by 4.0`,
    `sort=Title` and `/v1/resources/MOSAIC/mfl-2026-079` all work;
  - a filter value can also be given by its label;
  - values that match nothing are reported in `warnings`;
  - one folding rule, `domain/text.py`, is used everywhere. It also handles ß, ø and æ, and keeps
    non-Latin letters, which the first version dropped.
- `/docs` was blank: the strict CSP blocked Swagger UI. The docs pages now get their own CSP
  (scripts and styles from cdn.jsdelivr.net only).

### Added (later)
- `GET /`: a browser (`Accept: text/html`) is redirected to `/docs`. Any other client gets a short
  JSON description. The decision uses content negotiation, not the User-Agent, so `fetch()` from the
  website is never redirected.

### Added
- Hexagonal core:
  - MOSAIC model (Pydantic, frozen);
  - facets: data kind, geometry, spatial, theme, landscape, geography, access, method, licence,
    source, status;
  - search (accent-insensitive, AND words, OR/AND filters, bbox, years, sort, pages);
  - DOI links across catalogues (`same_as`) and landscapes derived from bboxes;
  - JSON-LD (schema.org Dataset).
- Sources:
  - MOSAIC catalogue build (`mosaic_catalog`);
  - git YAML repositories (`git_yaml`: local checkout or GitHub tarball).
- Translators:
  - MOSAIC v0.1;
  - CGIAR Climate Data Hub v0.5 (from mosaic-catalog `crosswalks/cdh.yaml`).
- Quality computed with the MOSAIC level schemas, for every source.
- Harvest is incremental (SHA-256 per record) and resilient (a failing source keeps its previous
  records).
- FastAPI app, GET only:
  - routes: manifest, sources, facets, labels, resources (search), resource, JSON-LD, summaries;
  - errors as RFC 9457 problem+json;
  - security headers, CORS allow-list.
- Static exporter for GitHub Pages: hashed shards, manifest, one file per resource.
- CLI: `harvest`, `export`, `serve`, `openapi`.
- Docs: architecture, adding a source, security, ADR-0001…0005. CI and publish workflows (not
  active).
- First run: 119 resources (102 MOSAIC + 17 CDH); 14 complete, 105 incomplete.
