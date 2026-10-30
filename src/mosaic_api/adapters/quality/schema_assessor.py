"""QualityAssessor that applies the MOSAIC level schemas (minimum, recommended) published by
mosaic-catalog. The API does not re-implement the rules: it runs the same JSON Schemas the
catalogue's validator runs, on every resource whatever its source.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from ...domain.model import Quality, Status

LEVELS = ("minimum", "recommended")


class SchemaAssessor:
    def __init__(self, schemas: Mapping[str, dict[str, Any]]) -> None:
        registry: Registry = Registry().with_resources(
            (s["$id"], Resource.from_contents(s)) for s in schemas.values() if "$id" in s
        )
        self._levels = {lv: schemas[f"levels/{lv}.schema.json"] for lv in LEVELS}
        self._validators = {lv: Draft202012Validator(s, registry=registry) for lv, s in self._levels.items()}

    def assess(self, record: dict[str, Any]) -> Quality:
        completeness: dict[str, float] = {}
        missing: set[str] = set()
        for lv, schema in self._levels.items():
            failing = self._failing_fields(lv, schema, record)
            fields = set(schema.get("required", [])) | set(schema.get("properties", {}))
            fields |= {r["x-field"] for r in schema.get("allOf", []) if "x-field" in r}
            if record.get("access") not in ("restricted", "internal"):
                fields.discard("access_note")
            completeness[lv] = round(1 - len(failing & fields) / len(fields), 3) if fields else 1.0
            if lv == "minimum":
                missing = failing
        status = Status.INCOMPLETE if missing else Status.COMPLETE
        return Quality(status=status, completeness=completeness, missing_minimum=tuple(sorted(missing)))

    def _failing_fields(self, level: str, schema: Mapping[str, Any], record: dict[str, Any]) -> set[str]:
        out: set[str] = set()
        for err in self._validators[level].iter_errors(record):
            path = list(err.absolute_path)
            if path:
                out.add(str(path[0]))
                continue
            node: Any = schema
            hint = None
            for step in err.absolute_schema_path:
                if isinstance(node, Mapping):
                    hint = node.get("x-field", hint)
                    node = node.get(step) if isinstance(step, str) else None
                elif isinstance(node, list) and isinstance(step, int) and step < len(node):
                    node = node[step]
            if hint:
                out.add(str(hint))
            elif err.validator == "required" and isinstance(err.validator_value, list):
                out.update(str(m) for m in err.validator_value if m not in record)
        return out
