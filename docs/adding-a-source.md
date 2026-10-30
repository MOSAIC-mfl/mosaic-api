# Adding a catalogue

MOSAIC reads other catalogues; they do not have to change anything. Their records are translated
into the MOSAIC model at harvest time.

## 1. The catalogue's format is already supported

Supported today:

- a MOSAIC catalogue build (`mosaic_catalog`);
- a git repo of YAML records in the CDH format (`git_yaml` + `cdh`).

For one of these, add an entry to `config/mosaic-api.yaml` and add the host to `allowed_hosts`:

```yaml
sources:
  - id: ilri            # short, lowercase; becomes the prefix of the ids (ilri:<id>)
    name: ILRI Datasets
    type: git_yaml
    translator: cdh
    format: cdh-yaml-v0.5
    location: https://github.com/<owner>/<repo>
    ref: main
    pattern: records/*/*.yaml
    record_url_template: https://github.com/<owner>/<repo>/blob/{ref}/{path}
```

Run `python -m mosaic_api harvest`. The output gives the number of records and of records with
issues; the issues themselves are in `state/snapshot.json`, under the source.

## 2. A new format

For example a STAC API, Dataverse, CKAN or OAI-PMH. These steps never touch `domain/` or
`application/`:

1. **Source adapter** (`adapters/sources/<type>.py`), implementing `ports.CatalogSource`:
   - `info` and `records()`, which yields `RawRecord(local_id, data, sha256, record_url)`;
   - read through `SafeFetcher`, never with raw HTTP calls;
   - set `sha256` from the record's bytes or canonical JSON, so unchanged records are skipped.
2. **Crosswalk** in mosaic-catalog (`crosswalks/<source>.yaml`): field mapping and vocabulary
   mappings (their themes to MOSAIC themes, their access values to ours, roles). Add its name to
   `CROSSWALKS` in `adapters/standard/dist.py`.
3. **Translator** (`adapters/translators/<source>.py`), implementing `ports.Translator`:
   - return `build(fields, raw, source, fetched_at, issues)`;
   - put every value you cannot map in `issues`, never drop it silently;
   - never invent a value; derived values are listed in `derived`.
4. **Register** the adapter and translator in `bootstrap.py` and in the `Literal` types of
   `config.py`.
5. **Tests:** two or three real records under `tests/fixtures/<source>/` (check their licence and
   say so in `tests/fixtures/README.md`), plus a translator test like `test_cdh_worldcover`.
