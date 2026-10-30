"""Checks a resource against the MOSAIC minimum and returns its quality (status, completeness)."""

from __future__ import annotations

from typing import Any, Protocol

from ..domain.model import Quality


class QualityAssessor(Protocol):
    def assess(self, record: dict[str, Any]) -> Quality:
        """``record`` is the resource as a MOSAIC standard record (Resource.to_record())."""
        ...
