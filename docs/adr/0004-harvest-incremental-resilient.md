# ADR-0004: Harvest, then query; incremental and resilient

- Status: proposed (2026-10-30)

## Decision

- The API never calls a catalogue while answering a request. A harvest builds a snapshot, and
  queries read the snapshot.
- Each source record carries a SHA-256. If it is unchanged, the previous translation is reused.
- A source that fails (down, invalid, too large) keeps its previous resources. The error is shown
  in `/v1/sources`, so one catalogue being down never empties the website.
