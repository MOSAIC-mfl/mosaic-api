"""The harvest notices what goes wrong instead of publishing it silently (audit of 2026-11-18)."""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from conftest import CDH, FETCHER, FIX, make_harvest
from mosaic_api.adapters.fetch import Location
from mosaic_api.adapters.sources.git_yaml import GitYamlSource
from mosaic_api.adapters.standard.dist import DistStandard
from mosaic_api.adapters.translators.cdh import CdhTranslator
from mosaic_api.application.harvest import HarvestService, SourceBinding
from mosaic_api.ports.sources import RawRecord, SourceInfo


def _with_cdh(harvest: HarvestService, source: Any, translator: Any = None) -> HarvestService:
    harvest._bindings = [harvest._bindings[0], SourceBinding(source, translator or CdhTranslator())]  # type: ignore[attr-defined]
    return harvest


def _cdh_copy(tmp_path: Path) -> Path:
    folder = tmp_path / "cdh"
    shutil.copytree(FIX / "cdh", folder)
    return folder


def _state(report: Any, source: str) -> Any:
    return next(s for s in report.snapshot.sources if s.id == source)


def _count(report: Any, source: str) -> int:
    return sum(r.gid.source == source for r in report.snapshot.resources)


class Empty:
    info = SourceInfo("cdh", "CDH", None, "x")

    def records(self) -> Iterator[RawRecord]:
        return iter(())


def test_a_source_that_suddenly_has_no_records_fails_and_keeps_the_previous(
    tmp_path: Path, dist_standard: DistStandard
) -> None:
    make_harvest(tmp_path, dist_standard).run()
    report = _with_cdh(make_harvest(tmp_path, dist_standard), Empty()).run()
    assert _state(report, "cdh").error == "RuntimeError: no records (the previous harvest had 3)"
    assert _count(report, "cdh") == 3


def test_an_empty_source_on_the_first_harvest_is_not_an_error(tmp_path: Path, dist_standard: DistStandard) -> None:
    report = _with_cdh(make_harvest(tmp_path, dist_standard), Empty()).run()
    assert _state(report, "cdh").error is None and _count(report, "cdh") == 0


def test_one_unreadable_file_does_not_fail_its_source(tmp_path: Path, dist_standard: DistStandard) -> None:
    folder = _cdh_copy(tmp_path)
    first = _with_cdh(make_harvest(tmp_path, dist_standard), GitYamlSource(CDH, str(folder), FETCHER)).run()
    before = next(r for r in first.snapshot.resources if r.id == "cdh:ecocrop")
    (folder / "records" / "ecocrop" / "ecocrop.yaml").write_text("id: ecocrop\ntitle: [unclosed\n", encoding="utf-8")
    (folder / "records" / "esa-worldcover-2021" / "esa-worldcover-2021.yaml").write_text(
        (FIX / "cdh/records/esa-worldcover-2021/esa-worldcover-2021.yaml").read_text(encoding="utf-8") + "\n# edited\n",
        encoding="utf-8",
    )
    report = _with_cdh(make_harvest(tmp_path, dist_standard), GitYamlSource(CDH, str(folder), FETCHER)).run()
    state = _state(report, "cdh")
    assert state.error is None
    assert state.issues["ecocrop"][0].startswith("unreadable record file: ParserError: while parsing")
    assert report.translated["cdh"] == 1  # the edited record was still read
    kept = next(r for r in report.snapshot.resources if r.id == "cdh:ecocrop")
    assert kept == before  # its previous version stays published


class Exploding:
    def translate(self, raw: RawRecord, *args: Any) -> Any:
        if raw.local_id == "ecocrop":
            raise KeyError("unexpected shape")
        return CdhTranslator().translate(raw, *args)


def test_a_record_that_breaks_the_translator_does_not_fail_its_source(
    tmp_path: Path, dist_standard: DistStandard
) -> None:
    source = GitYamlSource(CDH, str(FIX / "cdh"), FETCHER)
    report = _with_cdh(make_harvest(tmp_path, dist_standard), source, Exploding()).run()
    state = _state(report, "cdh")
    assert state.error is None
    assert state.issues["ecocrop"] == ["translation failed: KeyError: 'unexpected shape'"]
    assert _count(report, "cdh") == 2


def test_a_change_of_code_or_standard_translates_everything_again(tmp_path: Path, dist_standard: DistStandard) -> None:
    make_harvest(tmp_path, dist_standard).run()
    same = make_harvest(tmp_path, dist_standard).run()
    assert same.translated == {"mosaic": 0, "cdh": 0}
    changed = make_harvest(tmp_path, dist_standard)
    changed._code_version = "another version of the translators"  # type: ignore[attr-defined]
    report = changed.run()
    assert report.translated == {"mosaic": 4, "cdh": 3} and report.reused == {"mosaic": 0, "cdh": 0}
    assert json.loads((tmp_path / "snapshot.json").read_text(encoding="utf-8"))["fingerprint"]


def test_a_snapshot_without_fingerprint_is_not_reused(tmp_path: Path, dist_standard: DistStandard) -> None:
    make_harvest(tmp_path, dist_standard).run()
    snap = tmp_path / "snapshot.json"
    data = json.loads(snap.read_text(encoding="utf-8"))
    del data["fingerprint"]  # written before fingerprints existed
    snap.write_text(json.dumps(data), encoding="utf-8")
    assert make_harvest(tmp_path, dist_standard).run().translated == {"mosaic": 4, "cdh": 3}


def test_issues_of_an_unchanged_record_are_still_reported(tmp_path: Path, dist_standard: DistStandard) -> None:
    first = make_harvest(tmp_path, dist_standard).run()
    second = make_harvest(tmp_path, dist_standard).run()
    assert second.reused == {"mosaic": 4, "cdh": 3}
    for source in ("mosaic", "cdh"):
        assert _state(second, source).issues == _state(first, source).issues


def test_a_missing_remote_file_reads_as_missing() -> None:
    class NotFound:
        def get(self, url: str) -> bytes:
            raise httpx.HTTPStatusError("404", request=httpx.Request("GET", url), response=httpx.Response(404))

    loc = Location("https://example.org/dist/", NotFound())  # type: ignore[arg-type]
    with pytest.raises(FileNotFoundError):
        loc.read("vocab/processing_status.json")
