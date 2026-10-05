from analysis import shoes
from analysis.zones import MI

SETTINGS = {"gear_names": {"g1": "Nike Vomero 18 Voms ", "g2": "PUMA Velocity NITRO 4"},
            "gear_info": {"g1": {"distance_m": 100 * MI, "retired": False}, "g2": {"distance_m": 310 * MI, "retired": False}}}
ROWS = [{"gear_id": "g1", "runs": 6, "meters": 21.7 * MI, "last_day": "2026-10-03"}, {"gear_id": "g2", "runs": 5, "meters": 14.4 * MI, "last_day": "2026-09-26"}]


def by_name(out):
    return {s["name"]: s for s in out["shoes"]}


def test_miles_come_from_strava_total_and_names_are_tidied():
    out = by_name(shoes.summarize(ROWS, {"runs": 54, "meters": 116.5 * MI}, SETTINGS))
    assert out["Nike Vomero 18 Voms"]["miles"] == 100.0 and out["Nike Vomero 18 Voms"]["left_mi"] == 300.0
    assert out["PUMA Velocity NITRO 4"]["miles"] == 310.0


def test_status_goes_ok_then_close_then_replace_at_the_limit():
    s = SETTINGS | {"shoes": {"g2": {"limit_mi": 400}}}
    assert by_name(shoes.summarize(ROWS, {"runs": 0, "meters": 0}, s))["PUMA Velocity NITRO 4"]["status"] == "close"       # 310 of 400 = 77%
    assert by_name(shoes.summarize(ROWS, {"runs": 0, "meters": 0}, SETTINGS | {"shoes": {"g2": {"limit_mi": 300}}}))["PUMA Velocity NITRO 4"]["status"] == "replace"
    assert by_name(shoes.summarize(ROWS, {"runs": 0, "meters": 0}, SETTINGS))["Nike Vomero 18 Voms"]["status"] == "ok"


def test_starting_miles_add_on_and_tagged_runs_floor_the_total():
    s = {"gear_names": {}, "gear_info": {}, "shoes": {"g1": {"start_mi": 120}}}        # no Strava total yet: fall back to the tagged runs
    out = shoes.summarize(ROWS[:1], {"runs": 0, "meters": 0}, s)["shoes"][0]
    assert out["miles"] == 141.7 and out["name"] == "Shoes ...g1"


def test_untagged_runs_are_counted_and_most_recent_shoe_is_first():
    out = shoes.summarize(ROWS, {"runs": 54, "meters": 116.5 * MI}, SETTINGS)
    assert out["untagged"] == {"runs": 54, "miles": 116.5, "covered": False}
    assert [s["id"] for s in out["shoes"]] == ["g1", "g2"]


def test_retired_shoes_sort_last():
    s = SETTINGS | {"gear_info": {**SETTINGS["gear_info"], "g1": {"distance_m": 100 * MI, "retired": True}}}
    assert [x["id"] for x in shoes.summarize(ROWS, {"runs": 0, "meters": 0}, s)["shoes"]] == ["g2", "g1"]


def test_untagged_runs_count_as_covered_once_starting_miles_add_up():
    s = SETTINGS | {"shoes": {"g1": {"start_mi": 116.5}}}
    assert shoes.summarize(ROWS, {"runs": 54, "meters": 116.5 * MI}, s)["untagged"]["covered"] is True
