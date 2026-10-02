import math

import pytest

from analysis import places

LAT, LNG = 43.04, -76.13
M_PER_DEG_LAT = 111_000.0


def offset(lat, lng, north_m=0.0, east_m=0.0):
    return [lat + north_m / M_PER_DEG_LAT, lng + east_m / (M_PER_DEG_LAT * math.cos(math.radians(lat)))]


def square_loop(center, half_m=500):
    n, e = half_m, half_m
    pts = [offset(*center, -n, -e), offset(*center, n, -e), offset(*center, n, e), offset(*center, -n, e), offset(*center, -n, -e)]
    return pts


def route(rid, date, pts, miles=3.0):
    return {"id": rid, "date": date, "miles": miles, "pts": pts}


def test_haversine_known_distance():
    # one degree of latitude is ~111.2 km
    assert places.haversine_m((43.0, -76.0), (44.0, -76.0)) == pytest.approx(111_195, rel=0.002)


def test_cells_densify_a_long_segment():
    pts = [offset(LAT, LNG, 0, 0), offset(LAT, LNG, 0, 1000)]       # two points 1 km apart
    cells = places.cells_for_route(pts, LAT, size_m=250)
    assert 4 <= len(cells) <= 6


def test_cells_do_not_bridge_gps_gaps():
    pts = [offset(LAT, LNG, 0, 0), offset(LAT, LNG, 0, 20_000)]     # a 20 km jump is a GPS gap, not a run
    assert len(places.cells_for_route(pts, LAT, size_m=250)) == 2


def test_repeat_route_adds_no_new_ground():
    loop = square_loop([LAT, LNG])
    out = places.analyze([route("1", "2026-05-01", loop), route("2", "2026-06-08", loop)])
    cum = out["exploration"]["cumulative"]
    assert cum[0]["cells"] > 0 and cum[1]["cells"] == cum[0]["cells"] and cum[1]["new"] == 0
    by_month = {m["month"]: m for m in out["exploration"]["monthly"]}
    assert by_month["2026-05"]["share_new"] == pytest.approx(1.0)
    assert by_month["2026-06"]["share_new"] == pytest.approx(0.0)


def test_new_neighbourhood_adds_ground_and_month_shares():
    a = square_loop([LAT, LNG])
    b = square_loop(offset(LAT, LNG, 0, 6000))                      # 6 km east: all new
    out = places.analyze([route("1", "2026-05-01", a), route("2", "2026-06-02", a), route("3", "2026-06-09", b)])
    cum = out["exploration"]["cumulative"]
    assert cum[2]["cells"] > cum[1]["cells"] == cum[0]["cells"]
    june = next(m for m in out["exploration"]["monthly"] if m["month"] == "2026-06")
    may = next(m for m in out["exploration"]["monthly"] if m["month"] == "2026-05")
    assert may["share_new"] == pytest.approx(1.0)
    assert 0.3 < june["share_new"] < 0.8                            # mix of repeat loop and a brand-new area


def test_home_base_is_the_most_common_start():
    home = square_loop([LAT, LNG])
    away = square_loop(offset(LAT, LNG, 8000, 0))
    out = places.analyze([route(str(i), f"2026-05-{i + 1:02d}", home) for i in range(5)] + [route("x", "2026-05-20", away)])
    assert out["home"]["runs"] == 5
    assert places.haversine_m((out["home"]["lat"], out["home"]["lng"]), home[0]) < 1000


def test_farthest_run_measured_from_home():
    home = square_loop([LAT, LNG])
    far = [offset(LAT, LNG, 0, 0), offset(LAT, LNG, 0, 8000)]
    runs = [route(str(i), f"2026-05-{i + 1:02d}", home) for i in range(4)] + [route("far", "2026-06-01", far, miles=10)]
    out = places.analyze(runs)
    assert out["farthest"]["run_id"] == "far"
    assert places.haversine_m((out["farthest"]["lat"], out["farthest"]["lng"]), far[1]) < 50
    assert out["farthest"]["miles"] == pytest.approx(8000 / 1609.344, rel=0.15)


def test_top_areas_group_nearby_starts_and_sum_miles():
    a = square_loop([LAT, LNG])
    runs = [route("1", "2026-05-01", a, 3.0), route("2", "2026-05-03", a, 4.0), route("3", "2026-05-05", square_loop(offset(LAT, LNG, 9000, 0)), 5.0)]
    areas = places.analyze(runs)["areas"]
    assert areas[0]["runs"] == 2 and areas[0]["miles"] == pytest.approx(7.0)
    assert areas[1]["runs"] == 1


def test_empty_input_is_safe():
    out = places.analyze([])
    assert out["home"] is None and out["exploration"]["cumulative"] == [] and out["areas"] == []


def test_far_apart_cities_become_separate_regions_with_bounds():
    home = square_loop([LAT, LNG])
    away = square_loop([36.0, -86.8])                                       # roughly Nashville
    runs = [route(str(i), f"2026-05-{i + 1:02d}", home) for i in range(5)] + [route("t1", "2026-08-01", away), route("t2", "2026-08-03", away)]
    regions = places.analyze(runs)["regions"]
    assert [r["runs"] for r in regions] == [5, 2]
    assert regions[0]["home"] is True and regions[1]["home"] is False
    assert regions[1]["first"] == "2026-08-01" and regions[1]["last"] == "2026-08-03" and set(regions[1]["route_ids"]) == {"t1", "t2"}
    (lat0, lng0), (lat1, lng1) = regions[1]["bounds"]
    assert lat0 <= 36.0 - 0.003 and lat1 >= 36.0 + 0.003 and lng0 < lng1


def test_neighbouring_start_areas_in_one_city_stay_one_region():
    a = square_loop([LAT, LNG])
    b = square_loop(offset(LAT, LNG, 6000, 0))                              # 6 km north: same city, different start area
    regions = places.analyze([route("1", "2026-05-01", a), route("2", "2026-05-02", b)])["regions"]
    assert len(regions) == 1 and regions[0]["runs"] == 2
