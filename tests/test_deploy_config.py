"""The server configuration (Jenkins deploy) loads and reads only published https locations."""

from __future__ import annotations

from mosaic_api.config import ROOT, load_settings


def test_server_config_reads_everything_over_https() -> None:
    s = load_settings(ROOT / "config" / "mosaic-api.server.yaml")
    assert s.standard.startswith("https://")
    assert [src.id for src in s.sources] == ["mosaic", "cdh"]
    assert all(src.location.startswith("https://") for src in s.sources)
    assert "https://mosaic-mfl.github.io" in s.http.cors_origins
    assert s.resolve(s.state).endswith("state/snapshot.json")
