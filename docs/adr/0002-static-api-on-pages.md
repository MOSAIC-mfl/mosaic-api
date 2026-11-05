# ADR-0002: Static API on GitHub Pages now; the same FastAPI app live later

- Status: proposed (2026-10-30)

## Context

There is no budget for a server or a database. The data changes a few times a week.

## Decision

- `harvest` and `export` run in GitHub Actions: on a schedule, when a catalogue changes, or by
  hand. They publish JSON files on GitHub Pages.
- The files are produced by calling the FastAPI app's routes, so they are exactly what the live API
  answers.
- Large files have content-hashed names and are listed in `v1/_index/index.json`; clients cache
  them for good. (Until 2026-11 this list was `v1/manifest.json`; see ADR-0006.)
- Search and filtering run in the browser on the exported summaries, with the same rules as
  `domain/search.py`.
- When a free server is available, `python -m mosaic_api serve` provides the same contract. The
  website changes only its base URL.

## Consequences

- No running costs and no server to secure. The data is as fresh as the last harvest.
- In-browser search works up to tens of thousands of records. Beyond that, the live API is needed.
