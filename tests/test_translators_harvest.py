"""Translators speak the MOSAIC model; the harvest is incremental and survives a failing source."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from conftest import CDH, FETCHER, FIX, NOW, make_harvest
from mosaic_api.adapters.sources.git_yaml import GitYamlSource
from mosaic_api.adapters.standard.dist import DistStandard
from mosaic_api.adapters.translators.cdh import CdhTranslator
from mosaic_api.application.harvest import SourceBinding
from mosaic_api.domain import facets
from mosaic_api.domain.standard import Standard
from mosaic_api.ports.sources import RawRecord, SourceInfo


def _cdh(local: str, standard: Standard):  # type: ignore[no-untyped-def]
    raw = next(r for r in GitYamlSource(CDH, str(FIX / "cdh"), FETCHER).records() if r.local_id == local)
    return CdhTranslator().translate(raw, CDH, standard, NOW)


def test_cdh_worldcover(standard: Standard) -> None:
    res = _cdh("esa-worldcover-2021", standard)
    r = res.resource
    assert r is not None and res.issues == []
    assert r.themes == ("land-cover-land-use",)
    assert r.geography == ("global",)
    assert r.access == "public"  # CDH: absent means public; MOSAIC writes it
    assert r.license == "CC-BY-4.0"
    assert {(p.kind, p.access_method) for p in r.data} == {("raster", "download"), ("raster", "service")}
    ee = next(p for p in r.data if p.access_method == "service")
    assert ee.service is not None and ee.service.type == "gee"
    assert r.doi == "10.5281/zenodo.7254221"
    assert "data[].kind" in r.derived  # MOSAIC read the kind, CDH did not state it
    assert r.provenance.source == "cdh" and r.provenance.source_hash


def test_cdh_table_without_geometry_is_not_spatial(standard: Standard) -> None:
    r = _cdh("ecocrop", standard).resource
    assert r is not None
    assert r.data[0].kind == "tabular"
    assert facets.facet_values(r)["spatial"] == ["no"]  # described columns, no coordinates


def test_harvest_quality_and_incremental(tmp_path: Path, dist_standard: DistStandard) -> None:
    first = make_harvest(tmp_path, dist_standard).run()
    by_id = {r.id: r for r in first.snapshot.resources}
    assert len(by_id) == 7
    assert by_id["cdh:esa-worldcover-2021"].quality.status == "complete"
    assert by_id["mosaic:MFL-2026-079"].quality.status == "incomplete"
    assert set(by_id["mosaic:MFL-2026-079"].quality.missing_minimum) == {"contact"}
    assert by_id["cdh:africa-spei-drought"].landscapes_derived  # Africa box -> African landscapes
    second = make_harvest(tmp_path, dist_standard).run()
    assert second.translated == {"mosaic": 0, "cdh": 0}
    assert second.reused == {"mosaic": 4, "cdh": 3}


class Broken:
    info = SourceInfo("cdh", "CDH", None, "x")

    def records(self) -> Iterator[RawRecord]:
        raise ConnectionError("host down")


def test_a_failing_source_keeps_its_previous_records(tmp_path: Path, dist_standard: DistStandard) -> None:
    make_harvest(tmp_path, dist_standard).run()
    harvest = make_harvest(tmp_path, dist_standard)
    harvest._bindings = [harvest._bindings[0], SourceBinding(Broken(), CdhTranslator())]  # type: ignore[attr-defined]
    report = harvest.run()
    cdh_state = next(s for s in report.snapshot.sources if s.id == "cdh")
    assert cdh_state.error == "ConnectionError: host down"
    assert sum(r.gid.source == "cdh" for r in report.snapshot.resources) == 3


def test_translation_errors_become_issues_not_crashes(standard: Standard) -> None:
    raw = RawRecord("bad", {"id": "bad", "title": "", "cdh": {"domain": ["astrology"]}}, "h")
    res = CdhTranslator().translate(raw, CDH, standard, NOW)
    assert res.resource is None
    assert any("astrology" in i for i in res.issues) and any("title" in i for i in res.issues)


def test_git_yaml_reads_a_github_tarball(tmp_path: Path) -> None:
    """Remote mode: one tarball request; the <repo>-<ref>/ prefix is dropped; only the pattern is read."""
    import io
    import tarfile

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, body in {
            "cdh-catalog-main/records/a/a.yaml": b"id: a\ntitle: A\n",
            "cdh-catalog-main/README.md": b"# not a record\n",
            "cdh-catalog-main/records/a/notes.csv": b"x\n",
        }.items():
            info = tarfile.TarInfo(name)
            info.size = len(body)
            tar.addfile(info, io.BytesIO(body))

    class FakeFetcher:
        def __init__(self) -> None:
            self.urls: list[str] = []

        def get(self, url: str) -> bytes:
            self.urls.append(url)
            return buf.getvalue()

    fake = FakeFetcher()
    src = GitYamlSource(
        CDH,
        "https://github.com/CGIAR-Climate-Data-Hub/cdh-catalog",
        fake,  # type: ignore[arg-type]
        record_url_template="https://github.com/x/y/blob/{ref}/{path}",
    )
    recs = list(src.records())
    assert fake.urls == ["https://codeload.github.com/CGIAR-Climate-Data-Hub/cdh-catalog/tar.gz/main"]
    assert [(r.local_id, r.record_url) for r in recs] == [("a", "https://github.com/x/y/blob/main/records/a/a.yaml")]
