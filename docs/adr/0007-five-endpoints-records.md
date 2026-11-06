# ADR-0007: Five endpoints, named like the catalogue

- Status: accepted (2026-11-06, review of the catalogue). Supersedes ADR-0006 in part.

## Context

ADR-0006 left four groups of endpoints: sources, filters, resources and landscapes. The review asked
for the API to use the names of the catalogue (`records/`, `landscapes/`) and to drop the filters
endpoint: the website keeps the filter options and their labels itself.

## Decision

Five endpoints:

| Live | File on Pages |
|---|---|
| `GET /v1/sources` | `v1/sources.json` |
| `GET /v1/records` | `v1/records.json` |
| `GET /v1/records/{source}/{id}` | `v1/records/{source}/{id}.json` |
| `GET /v1/landscapes` | `v1/landscapes.json` |
| `GET /v1/landscapes/{code}` | `v1/landscapes/{CODE}.json` |

- `/v1/resources` is now `/v1/records` (`RecordSummary`, `RecordDetail`, `RecordPage` in the
  contract). The filters of `/v1/records` do not change (`source`, `theme`, `landscape`,
  `geography`; ids or labels) and `include_facets=true` still counts the values.
- `/v1/filters` (and `v1/filters.json`) is removed. The website has the options and labels of the
  four filters and counts them over the records it receives.

## Consequences

- A new filter value (a new theme, landscape or country) needs a change in the website's list;
  values outside the list are still shown, with their code.
- Clients of `/v1/resources` or `/v1/filters` must move; there were none besides the website.
