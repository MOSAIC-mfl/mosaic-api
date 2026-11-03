"""Reads the landscape profiles mosaic-catalog publishes: <location>/landscapes/index.json + <CODE>.json."""

from __future__ import annotations

import json
import logging

from ...domain.landscape import LandscapeProfile
from ..fetch import FetchError, Location

log = logging.getLogger(__name__)


class DistLandscapes:
    def __init__(self, location: Location) -> None:
        self._loc = location
        self._cache: list[LandscapeProfile] | None = None

    def all(self) -> list[LandscapeProfile]:
        if self._cache is None:
            try:
                index = json.loads(self._loc.read("landscapes/index.json"))
            except (FetchError, OSError) as exc:  # a catalogue published before profiles existed
                log.warning("no landscape profiles: %s", exc)
                index = {"landscapes": []}
            self._cache = [
                LandscapeProfile(str(e["code"]), json.loads(self._loc.read(str(e["file"]))))
                for e in index.get("landscapes") or []
            ]
        return self._cache
