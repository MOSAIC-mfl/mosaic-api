"""schema.org Dataset (JSON-LD) from a MOSAIC record: what search engines and FAIR harvesters read."""

from __future__ import annotations

from typing import Any


def to_jsonld(record: dict[str, Any], url: str | None) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "@context": "https://schema.org/",
        "@type": "Dataset",
        "name": record.get("title"),
        "description": record.get("description"),
        "identifier": f"https://doi.org/{record['doi']}" if record.get("doi") else record.get("id"),
        "keywords": [k["term"] if isinstance(k, dict) else k for k in record.get("keywords", [])],
        "isAccessibleForFree": record.get("access") == "public",
    }
    if url:
        doc["url"] = url
    lic = record.get("license") or {}
    if lic.get("url") or lic.get("spdx"):
        doc["license"] = lic.get("url") or f"https://spdx.org/licenses/{lic['spdx']}.html"
    creators = [
        {
            "@type": "Organization" if c.get("organization") and not c.get("name") else "Person",
            "name": c.get("name") or c.get("organization"),
        }
        for c in record.get("contacts", [])
        if "producer" in c.get("roles", [])
    ]
    if creators:
        doc["creator"] = creators
    t = record.get("temporal") or {}
    if t.get("start") or t.get("end"):
        doc["temporalCoverage"] = f"{t.get('start') or '..'}/{t.get('end') or '..'}"
    sp = record.get("spatial") or {}
    bbox = sp.get("bbox")
    if bbox:
        b = bbox if isinstance(bbox[0], int | float) else bbox[0]
        doc["spatialCoverage"] = {"@type": "Place", "geo": {"@type": "GeoShape", "box": f"{b[1]} {b[0]} {b[3]} {b[2]}"}}
    dist = [
        {
            "@type": "DataDownload",
            "name": p.get("name"),
            "contentUrl": p["url"],
            **({"encodingFormat": p["media_type"]} if p.get("media_type") else {}),
        }
        for p in record.get("data", [])
        if p.get("url") and p.get("method") == "download"
    ]
    if dist:
        doc["distribution"] = dist
    return {k: v for k, v in doc.items() if v not in (None, [], "")}
