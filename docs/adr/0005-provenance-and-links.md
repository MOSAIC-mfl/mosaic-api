# ADR-0005: Every resource keeps its provenance; the same resource in two catalogues is linked

- Status: proposed (2026-10-30)

## Decision

- **Ids are `<source>:<local id>`.** MOSAIC never renames another catalogue's ids.
- **Every resource carries `provenance`:** source, record URL, format, fetch time and hash. The
  website shows where each record comes from.
- **Same DOI, two catalogues.** Both records are kept, and each lists the other in `same_as`.
  Neither is merged nor dropped: connect, don't duplicate.
- **Derived landscapes.** A resource without landscapes gets those its bbox intersects, with
  `landscapes_derived: true`. Global boxes are ignored, because they would match every landscape.
