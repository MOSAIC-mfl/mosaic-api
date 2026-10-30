"""Source: a git repository whose records are YAML files (e.g. CGIAR Climate Data Hub cdh-catalog).

``location`` is either a local checkout or a GitHub repository URL. For GitHub, the whole repo is
read in ONE request (the tarball of ``ref``), so a harvest is cheap and does not hit API limits.
Files are matched by ``pattern`` (default ``records/*/*.yaml``) and parsed with yaml.safe_load.
"""

from __future__ import annotations

import fnmatch
import hashlib
import io
import tarfile
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

import yaml

from ...ports.sources import RawRecord, SourceInfo
from ..fetch import SafeFetcher

MAX_RECORD_BYTES = 2 * 1024 * 1024


class GitYamlSource:
    def __init__(
        self,
        info: SourceInfo,
        location: str,
        fetcher: SafeFetcher,
        ref: str = "main",
        pattern: str = "records/*/*.yaml",
        record_url_template: str | None = None,
    ) -> None:
        self._info = info
        self._location = location
        self._fetcher = fetcher
        self._ref = ref
        self._pattern = pattern
        self._url_tpl = record_url_template

    @property
    def info(self) -> SourceInfo:
        return self._info

    def _files(self) -> Iterator[tuple[str, bytes]]:
        if self._location.startswith("https://"):
            u = urlparse(self._location)
            owner, repo = PurePosixPath(u.path).parts[1:3]
            tar_url = f"https://codeload.github.com/{owner}/{repo}/tar.gz/{self._ref}"
            data = self._fetcher.get(tar_url)
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
                for m in tar.getmembers():
                    if not m.isfile() or m.size > MAX_RECORD_BYTES:
                        continue
                    rel = "/".join(PurePosixPath(m.name).parts[1:])  # drop the "<repo>-<ref>/" prefix
                    if fnmatch.fnmatch(rel, self._pattern):
                        fh = tar.extractfile(m)
                        if fh is not None:
                            yield rel, fh.read()
        else:
            root = Path(self._location)
            for p in sorted(root.glob(self._pattern)):
                if p.is_file() and p.stat().st_size <= MAX_RECORD_BYTES:
                    yield p.relative_to(root).as_posix(), p.read_bytes()

    def records(self) -> Iterator[RawRecord]:
        for rel, raw in sorted(self._files()):
            data: Any = yaml.safe_load(raw.decode("utf-8"))
            if not isinstance(data, dict) or "id" not in data:
                continue
            url = self._url_tpl.format(path=rel, ref=self._ref) if self._url_tpl else None
            yield RawRecord(str(data["id"]), data, hashlib.sha256(raw).hexdigest(), url)
