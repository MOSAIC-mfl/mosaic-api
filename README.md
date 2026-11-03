# mosaic-api

> **Status: local draft (v0.1.0).** Not pushed anywhere, not reviewed yet.

Read-only API of **MOSAIC**, a network of metadata. It reads several catalogues, translates their
records into the **MOSAIC metadata model**, and serves them as JSON to the website and to anyone
else. The catalogues are the MOSAIC catalogue itself and the CGIAR Climate Data Hub, with others to
follow. Every resource keeps its provenance: MOSAIC links to the data where it lives.

```
 catalogues (repos / APIs)        mosaic-api                                         consumers
 ┌─────────────────────┐   harvest ┌──────────────────────────────────────────────┐   ┌──────────┐
 │ mosaic-catalog dist │──────────▶│ source adapters → translators → CORE          │──▶│ website  │
 │ cdh-catalog (YAML)  │──────────▶│ (MOSAIC model, quality, facets, search,       │   │ others   │
 │ … (STAC, Dataverse) │──────────▶│  cross-catalogue links)  → FastAPI / exporter │   └──────────┘
 └─────────────────────┘           └──────────────────────────────────────────────┘
```

- **Hexagonal.** The core (domain + use cases) knows no framework, no file format and no source.
  Each catalogue is an adapter plus a translator. Adding a catalogue does not touch the core
  ([docs/adding-a-source.md](docs/adding-a-source.md)).
- **No server, no database (today).** `harvest` and `export` run in GitHub Actions and publish a
  **static JSON API** on GitHub Pages. The same FastAPI app can run live on a free server later,
  with the same contract.
- **Typed end to end.** Pydantic v2 models, `mypy --strict`, an OpenAPI contract the website
  generates its TypeScript types from, and `import-linter` enforcing the layers.

## Use

Python 3.10+.

```sh
pip install -e ".[dev]"
python -m mosaic_api harvest        # read the sources in config/mosaic-api.yaml -> state/snapshot.json
python -m mosaic_api serve          # live API on http://127.0.0.1:8000 (docs at /docs)
python -m mosaic_api export         # static API -> site/ (what GitHub Pages serves)
python -m mosaic_api openapi --out docs/openapi.json
pytest -q && ruff check src tests && mypy src && lint-imports
```

Local layout expected by the default config (repos side by side):

```
D:\Code\Mosaic\
  mosaic-api\            this repo
  mosaic-catalog\dist\   python -m mosaic_catalog build   (standard + MOSAIC records)
  cdh\cdh-catalog\       CDH records (git clone)
```

## Endpoints (v1)

| Live | Static file | What |
|---|---|---|
| `GET /v1/manifest` | `v1/manifest.json` | Versions, counts, sources and, in the static API, the list of files with their hashes |
| `GET /v1/sources` | `v1/sources.json` | Catalogues read, last harvest, errors |
| `GET /v1/facets` | `v1/facets.json` | Counts per filter value |
| `GET /v1/labels` | `v1/labels.json` | Labels for filter values (from the vocabularies) |
| `GET /v1/resources?q=&theme=&…` | `v1/summaries/<hash>.json` + `v1/search/<hash>.json` | Search and filters. Live: on the server. Static: in the browser, same rules |
| `GET /v1/resources/{source}/{id}` | `v1/resources/{source}/{id}.json` | One resource: MOSAIC record, provenance, quality, links |
| `GET /v1/resources/{source}/{id}/jsonld` | `v1/resources/{source}/{id}.jsonld` | schema.org Dataset (FAIR, search engines) |
| `GET /v1/landscapes` | `v1/landscapes.json` | Every living landscape: its page sections, dataset counts, the records its profile names |
| `GET /v1/landscapes/{code}` | `v1/landscapes/{CODE}.json` | One landscape page: its profile (sections and their configuration) and its data status |
| `GET /openapi.json` | `v1/openapi.json` | The contract |

Landscape profiles are written in mosaic-catalog (`landscapes/<CODE>/`, published in its
`dist/landscapes/`) and read from the same place as the standard. The API serves them as published
and adds what only the catalogue knows: which resources cover the landscape and how complete their
metadata is (`data_status`: totals, data types, themes, access, minimum fields missing). The code is
case-insensitive (`KEN-LVB` or `ken-lvb`).

Filters are `source`, `resource_type`, `theme`, `landscape`, `geography`, `data_kind`, `geometry`,
`spatial`, `method`, `access`, `license` and `status`. Values are comma-separated, combined with OR
inside a filter and AND across filters. There are also `bbox=w,s,e,n`, `year_from`, `year_to`,
`sort` (`relevance`, `title`, `updated`, `year`), `page`, `page_size` (at most 100) and
`include_facets`.

## Documentation

- [docs/architecture.md](docs/architecture.md): layers, flows, static API, how the website uses it.
- [docs/adding-a-source.md](docs/adding-a-source.md): connect a new catalogue.
- [docs/security.md](docs/security.md): threats and measures.
- [docs/adr/](docs/adr/): decisions.
- [CHANGELOG.md](CHANGELOG.md).

## Rules for changes

- Branch `santiago/<topic>`, pull request, green checks.
- Lizeth reviews changes to the model, the translators or what is published.
