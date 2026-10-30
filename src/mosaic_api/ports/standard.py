"""Where the MOSAIC standard (vocabularies, crosswalks, schemas) is loaded from."""

from __future__ import annotations

from typing import Protocol

from ..domain.standard import Standard


class StandardProvider(Protocol):
    def load(self) -> Standard: ...
