# ADR-0003: The API uses the MOSAIC standard's field names (snake_case)

- Status: proposed (2026-10-30). This replaces the camelCase idea in the planning document.

## Decision

Responses use the field names of the MOSAIC metadata standard (`resource_type`, `access_note`,
...), the same as in the records and the JSON Schemas.

## Why

- A resource's record in the API is a valid MOSAIC record, so it can be validated with the
  standard's schemas.
- The website and other consumers learn one set of names, documented once.
- The TypeScript types are generated from the OpenAPI contract, so the casing costs nothing on the
  website.
