# ADR-0006: Four endpoints: sources, filters, resources, landscapes

- Status: accepted (2026-11-05, team review with Steven Sotelo and Andrés Aguilar)

## Context

The first version had eleven routes: manifest, sources, facets, labels, resources, one resource,
its JSON-LD, summaries, and the two landscape routes. People reading the documentation did not
know which ones to use. Several only existed to configure the website, and the JSON-LD and
summaries routes had no user. `/v1/resources` also took twelve filters plus bbox and years.

## Decision

- **`GET /v1/sources`** stays on its own: the catalogues MOSAIC reads, useful by itself.
- **`GET /v1/filters`** replaces `manifest`, `facets` and `labels`: versions, totals, the filters
  of `/v1/resources` with each option as `{value, label, count}`, and labels for the other coded
  values a resource shows.
- **`GET /v1/resources`** is the catalogue, with four filters: `source`, `theme`, `landscape`,
  `geography`, plus `q`, sort and paging. `include_facets=true` returns the counts per filter value
  over the results.
- **`GET /v1/resources/{source}/{id}`** is one resource.
- **`GET /v1/landscapes`** and **`/v1/landscapes/{code}`** serve the landscape pages.
- Removed: `/v1/manifest`, `/v1/facets`, `/v1/labels`, `/v1/summaries`, `/v1/resources/…/jsonld`.
- On Pages, the files the website needs for in-browser search go to `v1/_index/` and are not part
  of the contract. `docs/` documents the files with their own contract (`docs/openapi.json`).

## Consequences

- The website reads `filters` and `sources` once, then `resources`.
- The other facet values (data kind, access, licence, …) are still on each resource for display,
  but are not filters.
- schema.org JSON-LD is no longer published. If search engines need it, the website can embed it
  in the dataset page.
