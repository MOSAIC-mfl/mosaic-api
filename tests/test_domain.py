"""Domain rules: facets, search, cross-catalogue linking. No I/O."""

from __future__ import annotations

from typing import Any

from conftest import NOW
from mosaic_api.domain import facets, search
from mosaic_api.domain.linking import derive_landscapes, link_same_resources
from mosaic_api.domain.model import GlobalId, Provenance, Quality, Resource


def res(local: str, source: str = "mosaic", **kw: Any) -> Resource:
    prov = Provenance(source=source, source_name=source, format="t", fetched_at=NOW, source_hash="h")
    return Resource(
        gid=GlobalId(source=source, local_id=local),
        provenance=prov,
        quality=Quality(status="incomplete"),
        **{"title": kw.pop("title", local), **kw},
    )


def point(**kw: Any) -> dict[str, Any]:
    return {"name": "p", **kw}


def test_spatial_facet() -> None:
    assert facets.facet_values(res("a", data=[point(kind="raster")]))["spatial"] == ["yes"]
    assert facets.facet_values(res("b", data=[point(kind="tabular", tabular={"spatial": True})]))["spatial"] == ["yes"]
    assert facets.facet_values(res("c", data=[point(kind="tabular", tabular={"spatial": False})]))["spatial"] == ["no"]
    assert facets.facet_values(res("d", data=[point(kind="tabular")]))["spatial"] == ["not_specified"]
    assert facets.facet_values(res("e", data=[point(kind="document")]))["spatial"] == ["no"]


def test_geometry_facet() -> None:
    r = res("a", data=[point(kind="vector", vector={"geometry_type": "polygon"}), point(kind="vector")])
    assert facets.facet_values(r)["geometry"] == ["not_specified", "polygon"]
    t = res(
        "b", data=[point(kind="tabular", tabular={"spatial": True, "coordinate_columns": {"x": "lon", "y": "lat"}})]
    )
    assert facets.facet_values(t)["geometry"] == ["point"]


def test_empty_values_are_not_specified() -> None:
    v = facets.facet_values(res("a"))
    assert v["theme"] == v["access"] == v["license"] == ["not_specified"]


def _run(items: list[Resource], **q: Any) -> list[str]:
    texts = {r.id: search.searchable_text(r, lambda _v, c: c) for r in items}
    return [r.id for r in search.run(items, search.Query(**q), texts).items]


def test_text_search_is_accent_insensitive_and_and() -> None:
    items = [res("a", title="Deforestación anual Ucayali"), res("b", title="Annual rainfall")]
    assert _run(items, text="deforestacion") == ["mosaic:a"]
    assert _run(items, text="annual rainfall") == ["mosaic:b"]
    assert _run(items, text="annual ucayali") == []


def test_filters_or_inside_and_across() -> None:
    items = [
        res("a", themes=["climate"], access="public"),
        res("b", themes=["water-hydrology"], access="restricted"),
        res("c", themes=["climate"], access="restricted"),
    ]
    both = frozenset({"climate", "water-hydrology"})
    assert _run(items, filters={"theme": both}) == ["mosaic:a", "mosaic:b", "mosaic:c"]
    assert _run(items, filters={"theme": both, "access": frozenset({"restricted"})}) == ["mosaic:b", "mosaic:c"]


def test_bbox_and_years() -> None:
    items = [
        res("peru", spatial={"bbox": [(-76, -10, -74, -8)]}, temporal={"start": "2001", "end": "2024"}),
        res("kenya", spatial={"bbox": [(34, -1, 35, 1)]}, temporal={"start": "1990", "end": "1995"}),
    ]
    assert _run(items, bbox=(-80, -15, -70, 0)) == ["mosaic:peru"]
    assert _run(items, year_from=2000) == ["mosaic:peru"]
    assert _run(items, year_to=1999) == ["mosaic:kenya"]


def test_pagination() -> None:
    items = [res(f"r{i:02d}") for i in range(25)]
    texts = {r.id: search.searchable_text(r, lambda _v, c: c) for r in items}
    page = search.run(items, search.Query(sort=search.Sort.TITLE, page=3, page_size=10), texts)
    assert page.total == 25 and [r.gid.local_id for r in page.items] == ["r20", "r21", "r22", "r23", "r24"]


def test_same_doi_links_both_records() -> None:
    linked = link_same_resources([res("x", doi="10.1/ABC"), res("y", source="cdh", doi="10.1/abc"), res("z")])
    assert [r.same_as for r in linked] == [("cdh:y",), ("mosaic:x",), ()]


def test_landscapes_derived_from_bbox_but_not_for_global_boxes() -> None:
    boxes = {"PER-PCL": (-75.9, -9.4, -74.3, -7.9)}
    out = derive_landscapes(
        [
            res("in", spatial={"bbox": [(-76, -10, -74, -8)]}),
            res("world", spatial={"bbox": [(-180, -90, 180, 90)]}),
            res("stated", landscapes=["KEN-LVB"], spatial={"bbox": [(-76, -10, -74, -8)]}),
        ],
        boxes,
    )
    assert [(r.landscapes, r.landscapes_derived) for r in out] == [
        (("PER-PCL",), True),
        ((), False),
        (("KEN-LVB",), False),
    ]


def test_fold_handles_case_accents_symbols_and_other_scripts() -> None:
    from mosaic_api.domain.text import fold, key

    assert fold("Côte d’Ivoire – 2021") == "cote d ivoire 2021"
    assert fold("STRAßE Ørsted Æble") == "strasse orsted aeble"
    assert fold("ລາວ Lao") == "ລາວ lao"  # non-Latin letters are kept
    assert key("CC BY 4.0") == key("cc-by-4.0") == "cc-by-4-0"
    assert key("Land cover / land use") == "land-cover-land-use"


def test_fold_matches_the_website_rule() -> None:
    """Same expectations as mosaic-web src/lib/domain/text.test.ts."""
    from mosaic_api.domain.text import fold

    assert fold("हिंदी नक्शा") == "हद नकश"  # marks of any script removed, as in the browser
    assert fold("Ｆｕｌｌ ﬁle") == "full file"
