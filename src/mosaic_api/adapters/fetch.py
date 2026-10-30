"""Reading files from a local folder or over HTTPS, safely.

Every remote read goes through ``SafeFetcher``: https only, host allow-list (also after
redirects), size limit, timeout. Sources are configured by people, but their content is not
trusted.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx


class FetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class SafeFetcher:
    allowed_hosts: frozenset[str]
    max_bytes: int = 50 * 1024 * 1024
    timeout_s: float = 30.0
    max_redirects: int = 5

    def check(self, url: str) -> None:
        u = urlparse(url)
        if u.scheme != "https":
            raise FetchError(f"only https is allowed: {url}")
        if u.hostname not in self.allowed_hosts:
            raise FetchError(f"host not in the allow-list (config allowed_hosts): {u.hostname}")

    def get(self, url: str) -> bytes:
        headers = {"User-Agent": "mosaic-api/0.1 (+https://github.com/MOSAIC-mfl)"}
        with httpx.Client(timeout=self.timeout_s, follow_redirects=False, headers=headers) as client:
            for _ in range(self.max_redirects + 1):
                self.check(url)
                with client.stream("GET", url) as resp:
                    if resp.is_redirect:
                        url = urljoin(url, resp.headers["location"])
                        continue
                    resp.raise_for_status()
                    chunks, size = [], 0
                    for chunk in resp.iter_bytes():
                        size += len(chunk)
                        if size > self.max_bytes:
                            raise FetchError(f"response larger than {self.max_bytes} bytes: {url}")
                        chunks.append(chunk)
                    return b"".join(chunks)
        raise FetchError(f"too many redirects: {url}")


@dataclass(frozen=True)
class Location:
    """A folder that is either local or remote (https). ``read('vocab/themes.json')``."""

    base: str
    fetcher: SafeFetcher

    @property
    def is_remote(self) -> bool:
        return self.base.startswith(("http://", "https://"))

    def read(self, rel: str) -> bytes:
        if self.is_remote:
            return self.fetcher.get(urljoin(self.base.rstrip("/") + "/", rel))
        path = (Path(self.base) / rel).resolve()
        if not path.is_relative_to(Path(self.base).resolve()):
            raise FetchError(f"path escapes its folder: {rel}")
        if path.stat().st_size > self.fetcher.max_bytes:
            raise FetchError(f"file larger than {self.fetcher.max_bytes} bytes: {path}")
        return path.read_bytes()
