from app.providers import water

ORIGIN = (32.8556, -117.2536)  # La Jolla Shores


def _row(name, category, type_, lat, lon, osm_type="node", osm_id=1):
    return {
        "name": name,
        "category": category,
        "type": type_,
        "lat": str(lat),
        "lon": str(lon),
        "osm_type": osm_type,
        "osm_id": osm_id,
    }


def test_nominatim_rows_keep_only_the_asked_category():
    rows = [
        _row("Windansea Beach", "natural", "beach", 32.83, -117.28),
        _row("Lagoon", "shop", "furniture", 32.84, -117.27),
        _row("", "natural", "beach", 32.84, -117.27),
    ]
    out = water.parse_nominatim(rows, "beach")
    assert [f["name"] for f in out] == ["Windansea Beach"]
    assert out[0]["kind"] == "beach" and out[0]["osm_id"] == "N1"


def test_nhd_keeps_lakes_and_named_lagoons_but_not_marshes():
    square = {"type": "Polygon", "coordinates": [[[-117.0, 32.9], [-116.99, 32.9], [-116.99, 32.91], [-117.0, 32.9]]]}
    payload = {
        "features": [
            {"properties": {"GNIS_NAME": "Lake Miramar", "FTYPE": 390}, "geometry": square},
            {"properties": {"GNIS_NAME": "San Elijo Lagoon", "FTYPE": 466}, "geometry": square},
            {"properties": {"GNIS_NAME": "Los Penasquitos Marsh", "FTYPE": 466}, "geometry": square},
            {"properties": {"GNIS_NAME": None, "FTYPE": 390}, "geometry": square},
        ]
    }
    out = water.parse_nhd(payload)
    assert [(f["name"], f["kind"]) for f in out] == [("Lake Miramar", "lake"), ("San Elijo Lagoon", "lagoon")]


def test_merge_joins_duplicates_and_river_segments():
    point = {
        "name": "Windansea Beach",
        "kind": "beach",
        "lat": 32.8300,
        "lon": -117.2800,
        "geometry": None,
        "source": "OpenStreetMap",
    }
    outline = dict(
        point,
        name="Windansea  beach",
        geometry={"type": "Polygon", "coordinates": [[[-117.28, 32.83], [-117.279, 32.83], [-117.28, 32.831], [-117.28, 32.83]]]},
    )
    seg1 = {
        "name": "Rose Creek",
        "kind": "river",
        "lat": 32.80,
        "lon": -117.22,
        "source": "OpenStreetMap",
        "geometry": {"type": "LineString", "coordinates": [[-117.22, 32.80], [-117.22, 32.81]]},
    }
    seg2 = dict(seg1, lat=32.83, geometry={"type": "LineString", "coordinates": [[-117.22, 32.83], [-117.22, 32.84]]})
    out = water.merge([point, outline, seg1, seg2], *ORIGIN, radius_km=10)
    by_name = {f["name"]: f for f in out}
    assert len(out) == 2
    assert by_name["Windansea Beach"]["geometry"]["type"] == "Polygon"  # the outline replaces the point
    river = by_name["Rose Creek"]
    assert river["geometry"]["type"] == "GeometryCollection" and len(river["geometry"]["geometries"]) == 2
    assert river["lat"] == 32.83  # the segment nearest the origin


def test_merge_drops_osm_results_in_the_square_corners_but_trusts_nhd():
    far = {"name": "Corner Beach", "kind": "beach", "lat": 32.92, "lon": -117.17, "geometry": None, "source": "OpenStreetMap"}
    lake = dict(far, name="Corner Lake", kind="lake", source="USGS NHD")
    out = water.merge([far, lake], *ORIGIN, radius_km=8)
    assert [f["name"] for f in out] == ["Corner Lake"]


def test_viewbox_is_a_square_around_the_circle():
    lon1, lat1, lon2, lat2 = map(float, water.viewbox(*ORIGIN, 8.0).split(","))
    assert lat1 > ORIGIN[0] > lat2 and lon1 < ORIGIN[1] < lon2
    assert abs((lat1 - lat2) / 2 - 8.0 / 111.32) < 1e-3
