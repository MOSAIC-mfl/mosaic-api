# mosaic-api

> **Status: v0.1.0, first publication.** Repository: https://github.com/MOSAIC-mfl/mosaic-api.
> Static API: https://mosaic-mfl.github.io/mosaic-api/ · documentation: https://mosaic-mfl.github.io/mosaic-api/docs/

Read-only API of **MOSAIC**, a network of metadata. It reads several catalogues, translates their
records into the **MOSAIC metadata model**, and serves them as JSON to the website and to anyone
else. The catalogues are the MOSAIC catalogue itself and the CGIAR Climate Data Hub, with others to
follow. Every resource keeps its provenance: MOSAIC links to the data where it lives.

```
 catalogues (repos / APIs)        mosaic-api                                         consumers
 ┌─────────────────────┐   harvest ┌──────────────────────────────────────────────┐   ┌──────────┐
 │ mosaic-catalog dist │──────────▶│ source adapters → translators → CORE          │──▶│ website  │
 │ cdh-catalog (YAML)  │──────────▶│ (MOSAIC model, quality, filters, search,      │   │ others   │
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
<workspace>/
  mosaic-api/            this repo
  mosaic-catalog/dist/   python -m mosaic_catalog build   (standard + MOSAIC records)
  cdh/cdh-catalog/       CDH records (git clone)
```

## Publishing (GitHub Actions → Pages)

One workflow, [.github/workflows/pages.yml](.github/workflows/pages.yml):

| Job | When | What |
|---|---|---|
| `check` | every pull request and every run | `ruff check`, `ruff format --check`, `mypy`, `lint-imports`, `pytest` |
| `build` | push to `main`, daily (05:17 UTC), manual, `repository_dispatch: catalog-updated`; only if `check` passes | clones MOSAIC-mfl/catalog, builds its `dist/`, harvests every source with [config/mosaic-api.ci.yaml](config/mosaic-api.ci.yaml), exports the static API |
| `deploy` | after `build` | publishes the export on GitHub Pages |

The catalogue is taken from `main` of MOSAIC-mfl/catalog when it holds the metadata standard
(`mosaic.config.yaml`), otherwise from the branch `metadata-standard-v0.1`. The repository
variable `CATALOG_REF` forces a branch or tag. Nothing has to change when that branch is merged.

Once, in the repository settings: **Settings → Pages → Build and deployment → Source: GitHub
Actions**. Then run the workflow by hand (Actions → Check and publish → Run workflow) or push to
`main`.

When the catalogue publishes its own Pages site (mosaic-mfl.github.io/catalog), the workflow can
read it over https with [config/mosaic-api.published.yaml](config/mosaic-api.published.yaml)
instead of cloning it.

## Endpoints (v1)

Four things, nothing else ([ADR-0006](docs/adr/0006-four-endpoints.md)):

| Live | File on Pages | What |
|---|---|---|
| `GET /v1/sources` | `v1/sources.json` | The catalogues MOSAIC reads (MOSAIC, CGIAR Climate Data Hub, …): records, last harvest, errors |
| `GET /v1/filters` | `v1/filters.json` | Read once before searching: versions and totals, the filters of `/v1/resources` with every option (`value`, `label`, `count`), and labels for the other coded values |
| `GET /v1/resources?q=&source=&theme=&landscape=&geography=` | (searched in the browser) | The catalogue: search and filters, sorted and paged; `include_facets=true` adds the count of each filter value over all the results |
| `GET /v1/resources/{source}/{id}` | `v1/resources/{source}/{id}.json` | One resource: MOSAIC record, provenance, quality |
| `GET /v1/landscapes` | `v1/landscapes.json` | Every living landscape: its page sections, dataset counts, the records its profile names |
| `GET /v1/landscapes/{code}` | `v1/landscapes/{CODE}.json` | One landscape page: its profile and its data status |

Documentation: `/docs` on the live API; on Pages, [`docs/`](https://mosaic-mfl.github.io/mosaic-api/docs/)
describes the files (Swagger UI, "Try it out" works). The full contract of the live API is
`/openapi.json` (on Pages: `v1/openapi.json`).

**Filters** of `/v1/resources`: `source`, `theme`, `landscape`, `geography`. Values are
comma-separated, combined with OR inside a filter and AND across filters; a value can be given by
its id or by its label, ignoring case, accents and symbols (`geography=Perú` = `PER`). Also `q`
(every word must appear), `sort` (`relevance`, `title`, `updated`, `year`), `order`, `page`,
`page_size` (at most 100).

**On Pages there is no `?q=`:** GitHub Pages serves files. The website searches in the browser
with the same rules, over files kept outside the contract (`v1/_index/`).

Landscape profiles are written in the catalogue (`landscapes/<CODE>/`, published in its
`dist/landscapes/`) and read from the same place as the standard. The API serves them as published
and adds what only the catalogue knows: which resources cover the landscape and how complete their
metadata is (`data_status`). The code is case-insensitive in the live API (`KEN-LVB` or `ken-lvb`);
the files on Pages use capitals.

## Documentation

- [docs/architecture.md](docs/architecture.md): layers, flows, static API, how the website uses it.
- [docs/adding-a-source.md](docs/adding-a-source.md): connect a new catalogue.
- [docs/security.md](docs/security.md): threats and measures.
- [docs/adr/](docs/adr/): decisions.
- [CHANGELOG.md](CHANGELOG.md).

## Rules for changes

- A branch per topic, pull request, green checks (`check` runs on every pull request).
- Lizeth reviews changes to the model, the translators or what is published.
