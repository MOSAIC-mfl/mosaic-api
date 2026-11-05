"""Translator for CGIAR Climate Data Hub records (CDH YAML, standard v0.5.0).

Since the MOSAIC standard v0.2 the MOSAIC core is the CDH core, so most fields are copied as they
are; mosaic-catalog crosswalks/cdh.yaml lists the differences (cdh.domain -> themes, cdh.usage ->
usage, geography slugs -> ISO / M49 codes). What MOSAIC adds and CDH does not state (the kind of
each data entry and how it is reached) is derived from media types and URLs and listed in
`derived`. Anything that cannot be mapped is returned as an issue; nothing is silently dropped.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse

from ...domain.standard import Standard
from ...ports.sources import RawRecord, SourceInfo
from ...ports.translator import TranslationResult
from .common import CORE_FIELDS, bbox_list, build

COPIED = ("title", "description", "note", "resource_type", "version", "keywords", "commodities", "license",
          "access_note", "attribution", "citation", "doi", "funding", "related_publications", "additional_links",
          "structures", "processing")  # fmt: skip
MORE = ("series", "parent", "previous_version", "deprecated", "additional_assets")
SERVICE_TYPES = {"earth-engine": "gee", "stac-api": "stac-api"}

MEDIA_KIND = (
    (re.compile(r"geotiff|image/tiff|netcdf|zarr|x-hdf|grib|jp2", re.I), "raster"),
    (re.compile(r"geo\+json|flatgeobuf|geopackage|shapefile|kml|x-esri", re.I), "vector"),
    (re.compile(r"csv|parquet|spreadsheet|excel|tab-separated|text/plain", re.I), "tabular"),
    (re.compile(r"pdf|msword|wordprocessing|text/html", re.I), "document"),
)
FILE_EXT = re.compile(r"\.(tif|tiff|nc|zarr|csv|parquet|gpkg|geojson|fgb|zip|vrt|json|xlsx?|pdf|txt)$", re.I)
UNITS = {"degree": "degree", "deg": "degree", "m": "m", "km": "km", "arcsec": "arcsec", "arcmin": "arcmin"}
DATE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?")


def _date(value: Any) -> str | None:
    if value is None:
        return None
    m = DATE.match(str(value))
    return m.group(0) if m else None


def _kind(media_type: str | None, structures: list[dict[str, Any]]) -> str:
    for rx, kind in MEDIA_KIND:
        if media_type and rx.search(media_type):
            if kind == "tabular" and any(s.get("geometry_column") for s in structures):
                return "vector"
            return kind
    dims = [d for s in structures for d in s.get("dimensions", [])]
    if any(d.get("type") in ("xy", "x", "y") for d in dims):
        return "raster"
    if any(s.get("geometry_column") for s in structures):
        return "vector"
    return "other"


def _method(url: str) -> tuple[str, str | None]:
    """(method, service_type) for a location URL."""
    u = urlparse(url)
    if u.scheme == "ee" or "earthengine.googleapis.com" in (u.hostname or ""):
        return "service", "earth-engine"
    if "/api/stac/" in u.path or u.path.endswith("/stac"):
        return "service", "stac-api"
    if u.scheme in ("s3", "gs") or u.path.endswith("/") or FILE_EXT.search(PurePosixPath(u.path).name):
        return "download", None
    return "landing_page", None


def _resolution(structures: list[dict[str, Any]]) -> dict[str, Any] | None:
    for s in structures:
        for d in s.get("dimensions", []):
            if d.get("type") in ("xy", "x") and isinstance(d.get("step"), int | float):
                unit = UNITS.get(str(d.get("unit", "")).lower())
                if unit:
                    return {"value": float(d["step"]), "unit": unit}
    return None


class CdhTranslator:
    def translate(
        self, raw: RawRecord, source: SourceInfo, standard: Standard, fetched_at: datetime
    ) -> TranslationResult:
        d: dict[str, Any] = raw.data
        cw = standard.crosswalks["cdh"]["vocabularies"]
        issues: list[str] = []
        derived: list[str] = []
        f: dict[str, Any] = {k: d.get(k) for k in COPIED}
        f["created"], f["updated"] = _date(d.get("created")), _date(d.get("updated"))

        # Themes from CDH domains (closed vocabulary, all eight have a MOSAIC theme).
        cdh_block = d.get("cdh") or {}
        themes = []
        for dom in cdh_block.get("domain") or []:
            theme = cw["domain_to_theme"].get(dom)
            if theme:
                themes.append(theme)
            else:
                issues.append(f"cdh.domain {dom!r} has no MOSAIC theme")
        f["themes"] = list(dict.fromkeys(themes))
        f["usage"] = cdh_block.get("usage")

        spatial = d.get("spatial") or {}
        geo = standard.geography_by_slug()
        geography = []
        for slug in spatial.get("geography") or []:
            if slug in geo:
                geography.append(geo[slug])
            else:
                issues.append(f"geography {slug!r} not found in the MOSAIC geography vocabulary")
        structures = d.get("structures") or []
        sp: dict[str, Any] = {"bbox": bbox_list(spatial.get("bbox")), "crs": spatial.get("crs"), "geography": geography}
        res = _resolution(structures)
        if res:
            sp["resolution"] = res
            derived.append("spatial.resolution")
        f["spatial"] = {k: v for k, v in sp.items() if v}

        temporal = dict(d.get("temporal") or {})
        freq = temporal.get("update_frequency")
        if freq and freq not in standard.vocab("update_frequency"):
            issues.append(f"temporal.update_frequency {freq!r} not in the MOSAIC vocabulary")
            temporal.pop("update_frequency")
        for k in ("date", "start_date", "end_date"):
            if temporal.get(k) is not None:
                temporal[k] = str(temporal[k])
        f["temporal"] = temporal or None

        f["access"] = cw["access"].get(d.get("access") or "public")  # CDH: absent means public
        roles = cw["contact_role"]
        f["contact"] = [
            {
                **{k: c[k] for k in ("name", "organization", "email", "url", "ror", "orcid") if c.get(k)},
                "roles": [roles[r] for r in c.get("roles", []) if r in roles],
            }
            for c in d.get("contact") or []
        ]
        f["data"] = self._data(d, structures, derived)
        extensions = []
        for url in d.get("extensions") or []:
            name = str(url).rstrip("/").split("/")[-2] if "/extensions/" in str(url) else str(url)
            if name == "climate":
                extensions.append("climate@0.2.0")
            elif name not in ("cdh", "agriculture"):  # cdh -> themes / usage, agriculture -> commodities
                issues.append(f"CDH extension {url} has no MOSAIC equivalent: its block is not kept")
        f["extensions"] = extensions
        more = {k: d[k] for k in MORE if d.get(k) not in (None, [], {})}
        if "climate@0.2.0" in extensions and d.get("climate"):
            more["climate"] = d["climate"]
        f["more"] = more
        f["derived"] = sorted(set(derived))
        unknown = set(d) - set(CORE_FIELDS) - set(MORE) - {"id", "cdh_schema_version", "cdh", "climate"}
        issues += [f"CDH field {k!r} has no MOSAIC place" for k in sorted(unknown)]
        return build(f, raw, source, fetched_at, issues)

    @staticmethod
    def _data(d: dict[str, Any], structures: list[dict[str, Any]], derived: list[str]) -> list[dict[str, Any]]:
        """CDH data entries as they are, plus what MOSAIC adds: kind and access_method (derived)."""
        entries: list[dict[str, Any]] = []
        for asset in d.get("data") or []:
            e = dict(asset)
            e["kind"] = _kind(asset.get("media_type"), structures)
            derived.append("data[].kind")
            url = next((loc.get("url") for loc in asset.get("locations") or [] if loc.get("url")), None)
            if url:
                method, service_type = _method(url)
                e["access_method"] = method
                if service_type:
                    e["service"] = {"type": SERVICE_TYPES.get(service_type, "other")}
            elif d.get("access") in ("restricted", "non-public"):
                e["access_method"] = "request"
            if e.get("access_method"):
                derived.append("data[].access_method")
            entries.append({k: v for k, v in e.items() if v not in (None, "")})
        return entries
