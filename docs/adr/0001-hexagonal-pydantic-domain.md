# ADR-0001: Hexagonal architecture; Pydantic as the domain's data types

- Status: proposed (2026-10-30)

## Decision

- The core (`domain`, `ports`, `application`) depends on no framework and no I/O library. Sources,
  translators, storage, quality checks and HTTP are adapters wired in `bootstrap.py`.
  `import-linter` checks this in CI.
- The domain uses Pydantic v2 models (frozen, `extra="forbid"`) as its data types. It gets
  validation and typing without writing a second set of classes. Pydantic does no I/O here; FastAPI
  stays out of the core.

## Consequences

- A new catalogue, a database or another web framework is an adapter change.
- Pydantic becomes a dependency of the domain. That is acceptable: it is a typing library, not a
  framework.
