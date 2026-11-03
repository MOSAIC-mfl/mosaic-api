# Architecture

## 1. Layers (hexagonal)

```
src/mosaic_api/
  domain/        the MOSAIC model and its rules: model, facets, search, cross-catalogue
                 linking, JSON-LD. Pure Python + Pydantic (types only). No I/O.
  ports/         interfaces the core needs: CatalogSource, Translator, QualityAssessor,
                 SnapshotStore, StandardProvider (typing.Protocol)
  application/   use cases: HarvestService (write side), CatalogService (read side),
                 DTOs (the public contract)
  adapters/      implementations:
    sources/       mosaic_catalog (dist JSON), git_yaml (local checkout or GitHub tarball)
    translators/   mosaic, cdh  (source format -> MOSAIC model)
    quality/       schema_assessor (runs the MOSAIC level schemas)
    standard/      dist (loads vocabularies, crosswalks, schemas published by mosaic-catalog)
    store/         fs_json (one snapshot file; no database)
    inbound/       http (FastAPI), exporter (static API)
    fetch.py       safe file/HTTPS reading (allow-list, limits)
  bootstrap.py   composition root: the only place adapters are chosen
  cli.py         entry point: harvest | export | serve | openapi
```

`import-linter` enforces the order `cli → bootstrap → adapters → application → ports → domain`. It
also forbids FastAPI, Starlette, httpx, yaml, jsonschema and the adapters inside `domain`,
`application` and `ports`. A violation fails CI.

Pydantic in the domain is a deliberate choice ([ADR-0001](adr/0001-hexagonal-pydantic-domain.md)):
it is used only for typed, validated, immutable data, never for I/O.

## 2. Write side: harvest

```
for each configured source:
    source.records()                     # RawRecord(local_id, data, sha256, record_url)
      ├─ same sha256 as last snapshot? → reuse the previous Resource (incremental)
      └─ translator.translate(...)       # → Resource in the MOSAIC model + issues
            └─ assessor.assess(record)   # MOSAIC minimum / recommended → Quality
  (a source that raises keeps its previous resources; its error is recorded)
link_same_resources()                    # same DOI in two catalogues → same_as on both
derive_landscapes()                      # bbox ∩ landscape boxes → landscapes (flagged derived)
store.save(snapshot)
```

- **Our language.** The core only sees `Resource`. CDH's `cdh.domain`, `contact`, `locations`,
  `access` (absent = public) and other conventions stop at its translator. The vocabulary
  mappings come from the standard's crosswalks (`mosaic-catalog/crosswalks/cdh.yaml`), not from
  code.
- **One set of rules.** Quality is computed with the same JSON Schemas that mosaic-catalog's
  validator uses, for every source.
- **Nothing silent.** Values a translator cannot map are recorded as issues per record, in
  `/v1/sources`, with `records_with_issues`.

## 3. Read side: queries and the static API

`CatalogService` holds the snapshot in memory and answers search, get, facets, labels and sources.
`create_app()` exposes these as GET routes. The exporter calls the same routes and writes the
answers as files, so the static API **is** the live API, frozen at harvest time.

**What the website does with the static API:**

1. Fetch `v1/manifest.json`. It is small and the only file that changes name-stably.
2. Fetch the files it lists that are not cached yet: `summaries/<hash>.json` and
   `search/<hash>.json`. Hashed names never change, so they can be cached for good, in the browser
   (HTTP cache or IndexedDB) and on the CDN.
3. Filter and search in the browser with the same rules as `domain/search.py` and
   `domain/text.py`:
   - **fold** every text before comparing it: casefold (ß→ss); NFKD with accents removed; ø, æ,
     œ, đ, ł and þ transliterated; any run of spaces, punctuation or symbols becomes one
     separator; letters of any script are kept. `fold("Côte d’Ivoire – 2021")` gives
     `"cote d ivoire 2021"`;
   - **words:** every word of the folded query must appear in the folded searchable text
     (`search/<hash>.json` is already folded);
   - **filters:** compare `key(value)`, which is `fold` with `-` as the separator, on both sides.
     `CC BY 4.0`, `cc-by-4.0` and `CC-BY-4.0` are therefore the same, and so are `PER` and `per`.
     A value may also be given by its label (`Perú` → `PER`), resolved with `v1/labels.json`;
   - OR inside a filter, AND across filters (`summary.facets` already carries each resource's
     values);
   - bbox intersection and year overlap.
4. Fetch `v1/resources/<source>/<id>.json` when a card is opened.

**Scale:**

- Summaries are sharded at 2,000 records per file.
- Today, with 119 resources, the whole export is about 1.3 MB.
- GitHub Pages limits: 1 GB per site, about 100 GB of traffic a month, 10 builds an hour. They
  leave room for tens of thousands of records.
- When in-browser search becomes too heavy, run `serve` on a free server and point the website at
  it. Contract and filters stay the same; only the base URL changes.

## 4. Data contract

- Field names are the MOSAIC standard's (`snake_case`), the same as in the records
  ([ADR-0003](adr/0003-standard-field-names.md)).
- **A resource's id is `<source>:<local id>`.** Its URL path is `/v1/resources/<source>/<local id>`.
- **`ResourceDetail.record`** is a valid MOSAIC standard record, plus provenance, quality, facets
  and `same_as`.
- **The contract is `openapi.json`.** The website generates its TypeScript types from it with
  `openapi-typescript`, so a breaking change fails the website build instead of production.

## 5. Facet rules

These are in `domain/facets.py`; the catalogue's `docs/standard.md` §5.1 describes the same.

| Facet | Value |
|---|---|
| `data_kind` | Kinds of all access points |
| `geometry` | Vector `geometry_type`, `point` for tables with `coordinate_columns`, `not_specified` for vector data without a type |
| `spatial` | `yes` for raster, vector, or a table with `spatial: true`; `no` for tables with `spatial: false` and/or documents; otherwise `not_specified` |
| any other | The value in the record, or `not_specified` |
