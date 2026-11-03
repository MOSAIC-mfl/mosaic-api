"""Where landscape profiles are read from."""

from __future__ import annotations

from typing import Protocol

from ..domain.landscape import LandscapeProfile


class LandscapeProfiles(Protocol):
    def all(self) -> list[LandscapeProfile]: ...
