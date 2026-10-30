"""Translator for CGIAR Climate Data Hub records (CDH YAML, standard v0.5.0).

Follows mosaic-catalog crosswalks/cdh.yaml (read from the published standard, so vocabulary
mappings live in one place). Anything that cannot be mapped is returned as an issue; nothing is
silently dropped or invented.
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
from .common import bbox_list, build

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
        f: dict[str, Any] = {k: d.get(k) for k in ("title", "description", "resource_type", "doi", "version")}
        f["created"], f["updated"] = _date(d.get("created")), _date(d.get("updated"))

        # Themes from CDH domains; the domain itself is kept as a linked keyword (nothing lost).
        domains = (d.get("cdh") or {}).get("domain") or []
        themes = []
        for dom in domains:
            theme = cw["domain_to_theme"].get(dom)
            if theme:
                themes.append(theme)
            else:
                issues.append(f"cdh.domain {dom!r} has no MOSAIC theme")
        f["themes"] = list(dict.fromkeys(themes))
        keywords = []
        for k in d.get("keywords") or []:
            if isinstance(k, dict):
                keywords.append({x: k[x] for x in ("term", "scheme", "uri", "lang") if k.get(x)})
            else:
                keywords.append({"term": str(k)})
        keywords += [{"term": dom, "scheme": "cdh-domain"} for dom in domains]
        f["keywords"] = keywords

        note = d.get("note") or ""
        usage = (d.get("cdh") or {}).get("usage") or {}
        if usage.get("intended_uses"):
            note += "\nIntended uses (CDH): " + "; ".join(usage["intended_uses"])
        for nr in usage.get("not_recommended_for") or []:
            alt = f" Use instead: {nr['use_instead']}" if nr.get("use_instead") else ""
            note += f"\nNot recommended for {nr['use']}: {nr['reason']}{alt}"
        f["note"] = note.strip() or None

        spatial = d.get("spatial") or {}
        geo = standard.geography_by_slug()
        f["geography"] = []
        for slug in spatial.get("geography") or []:
            if slug in geo:
                f["geography"].append(geo[slug])
            else:
                issues.append(f"geography {slug!r} not found in the MOSAIC geography vocabulary")
        structures = d.get("structures") or []
        if spatial.get("bbox") or spatial.get("crs"):
            f["spatial"] = {
                "bbox": bbox_list(spatial.get("bbox")),
                "crs": spatial.get("crs"),
                "resolution": _resolution(structures),
            }

        links = d.get("additional_links") or []
        lic = d.get("license")
        lic_url = next((lk.get("url") for lk in links if lk.get("rel") == "license"), None)
        if lic and not str(lic).startswith("LicenseRef-") and " " not in str(lic):
            f["license"] = {"spdx": lic, "url": lic_url or f"https://spdx.org/licenses/{lic}.html"}
        elif lic:
            f["license"] = {"spdx": lic if " " in str(lic) else None, "url": lic_url, "text": str(lic)}

        access_map = cw["access"]
        f["access"] = access_map.get(d.get("access") or "public")  # CDH: absent means public
        f["access_note"] = d.get("access_note")

        roles = cw["contact_role"]
        f["contacts"] = [
            {
                **{k: c[k] for k in ("name", "organization", "email", "url", "ror", "orcid") if c.get(k)},
                "roles": [roles[r] for r in c.get("roles", []) if r in roles],
            }
            for c in d.get("contact") or []
        ]

        cit = d.get("citation")
        if isinstance(cit, dict):
            f["citation"] = {
                "title": cit.get("title"),
                "date": _date(cit.get("date")),
                "publisher": cit.get("publisher"),
                "authors": [
                    {k: a[k] for k in ("family", "given", "organization", "orcid") if a.get(k)}
                    for a in cit.get("authors") or []
                ],
            }

        temporal = d.get("temporal") or {}
        if temporal.get("date"):
            f["temporal"] = {"start": _date(temporal["date"]), "end": _date(temporal["date"])}
        elif temporal.get("start_date") or temporal.get("end_date"):
            f["temporal"] = {"start": _date(temporal.get("start_date")), "end": _date(temporal.get("end_date"))}
        freq = temporal.get("update_frequency")
        if freq:
            if freq in standard.vocab("update_frequency"):
                f["update_frequency"] = freq
            else:
                issues.append(f"update_frequency {freq!r} not in the MOSAIC vocabulary")

        f["funding"] = [{k: x[k] for k in ("name", "url") if x.get(k)} for x in d.get("funding") or []]
        f["related"] = self._related(d, links)
        f["data"] = self._data(d, structures)
        return build(f, raw, source, fetched_at, issues)

    @staticmethod
    def _related(d: dict[str, Any], links: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for pub in d.get("related_publications") or []:
            cit = pub.get("citation") or {}
            if pub.get("doi"):
                out.append(
                    {"relation": "IsDocumentedBy", "scheme": "doi", "value": pub["doi"], "title": cit.get("title")}
                )
            elif cit.get("url"):
                out.append(
                    {"relation": "IsDocumentedBy", "scheme": "url", "value": cit["url"], "title": cit.get("title")}
                )
        for step in d.get("processing") or []:
            for src in step.get("derived_from") or []:
                if src.get("url"):
                    out.append(
                        {"relation": "IsDerivedFrom", "scheme": "url", "value": src["url"], "title": src.get("title")}
                    )
        rel_map = {"describedby": "IsDocumentedBy"}
        for lk in links:
            if lk.get("url") and lk.get("rel") != "license":
                out.append(
                    {
                        "relation": rel_map.get(lk.get("rel", ""), "References"),
                        "scheme": "url",
                        "value": lk["url"],
                        "title": lk.get("title"),
                    }
                )
        series = d.get("series") or {}
        if series.get("url"):
            out.append({"relation": "IsPartOf", "scheme": "url", "value": series["url"], "title": series.get("name")})
        for asset in d.get("additional_assets") or []:
            loc: dict[str, Any] = next(iter(asset.get("locations") or []), {})
            if loc.get("url", "").startswith(("http://", "https://")):
                out.append(
                    {"relation": "IsSupplementedBy", "scheme": "url", "value": loc["url"], "title": asset.get("name")}
                )
        return [{k: v for k, v in r.items() if v} for r in out]

    @staticmethod
    def _data(d: dict[str, Any], structures: list[dict[str, Any]]) -> list[dict[str, Any]]:
        points: list[dict[str, Any]] = []
        for asset in d.get("data") or []:
            kind = _kind(asset.get("media_type"), structures)
            locations = asset.get("locations") or [{}]
            for loc in locations:
                url = loc.get("url")
                name = asset.get("name", "data")
                if len(locations) > 1 and loc.get("title"):
                    name = f"{name} ({loc['title']})"
                p: dict[str, Any] = {
                    "name": name,
                    "kind": kind,
                    "url": url,
                    "description": asset.get("description"),
                    "media_type": asset.get("media_type"),
                    "size": asset.get("file_size"),
                }
                if asset.get("href_template"):
                    extra = f"Files: {asset['href_template']} under this location."
                    p["description"] = f"{p['description'] or ''} {extra}".strip()
                if url:
                    method, service_type = _method(url)
                    p["method"] = method
                    if service_type:
                        p["service"] = {"service_type": service_type}
                else:
                    p["method"] = "request" if d.get("access") in ("restricted", "non-public") else None
                if kind == "raster" and _resolution(structures):
                    p["raster"] = {"resolution": _resolution(structures)}
                if kind == "tabular" and structures:
                    has_geo = any(s.get("geometry_column") for s in structures)
                    p["tabular"] = {"spatial": has_geo}
                    p["derived"] = ["tabular.spatial"]
                points.append({k: v for k, v in p.items() if v not in (None, "")})
        return points
