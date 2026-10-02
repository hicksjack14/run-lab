import pytest

from analysis import zones


def test_vdot_matches_daniels_table():
    # Daniels: VDOT 50 is roughly a 19:57 5K and a 41:21 10K
    assert zones.vdot(5000, 19 * 60 + 57) == pytest.approx(50, abs=0.3)
    assert zones.vdot(10000, 41 * 60 + 21) == pytest.approx(50, abs=0.3)


def test_predict_time_round_trips():
    for v in (35, 45, 55):
        t = zones.predict_time(v, 5000)
        assert zones.vdot(5000, t) == pytest.approx(v, abs=0.01)


def test_race_predictions_scale_sensibly():
    p = zones.race_predictions(50)
    assert p["5K"] == pytest.approx(19 * 60 + 57, abs=15)
    assert p["5K"] < p["10K"] < p["Half marathon"] < p["Marathon"]
    # marathon for VDOT 50 is about 3:10
    assert p["Marathon"] == pytest.approx(3 * 3600 + 10 * 60, abs=300)


def test_training_paces_are_ordered_slow_to_fast():
    p = zones.training_paces(45)
    assert p["easy_slow"] > p["easy_fast"] > p["marathon"] > p["threshold"] > p["interval"]
    # sanity: VDOT 45 easy pace is somewhere between 8:30 and 11:00 per mile
    assert 8.5 * 60 < p["easy_fast"] < 11 * 60


def test_faster_runner_has_faster_paces():
    assert zones.training_paces(55)["threshold"] < zones.training_paces(40)["threshold"]


def test_hr_zones_cover_range_with_percent_of_max():
    z = zones.hr_zones(200)
    assert [(a["lo"], a["hi"]) for a in z] == [(100, 119), (120, 139), (140, 159), (160, 179), (180, 200)]
    assert z[0]["name"] and z[4]["name"]


def test_zone_for_hr():
    assert zones.zone_for_hr(150, 200) == 3
    assert zones.zone_for_hr(90, 200) == 1
    assert zones.zone_for_hr(210, 200) == 5


def test_max_hr_ignores_a_single_spike():
    runs = [170, 175, 172, 180, 178, 176, 181, 179, 177, 174, 225]  # 225 = optical sensor spike
    assert zones.estimate_max_hr(runs) < 200
    assert zones.estimate_max_hr(runs) >= 181


def test_max_hr_with_few_runs_drops_top_value():
    assert zones.estimate_max_hr([170, 180, 250]) == 180
    assert zones.estimate_max_hr([]) is None


def test_estimate_vdot_prefers_long_efforts_and_reports_basis():
    efforts = [
        {"type": "Fastest5k", "seconds": 28 * 60, "date": "2026-09-01"},
        {"type": "FastestMile", "seconds": 7 * 60 + 30, "date": "2026-09-10"},
        {"type": "Fastest400", "seconds": 80, "date": "2026-09-10"},  # too short to trust
    ]
    est = zones.estimate_vdot(efforts, today="2026-10-01")
    assert est is not None
    assert est["basis"]["type"] in ("Fastest5k", "FastestMile")
    assert 30 < est["vdot"] < 45


def test_estimate_vdot_ignores_stale_efforts():
    efforts = [{"type": "Fastest5k", "seconds": 20 * 60, "date": "2025-01-01"}]
    assert zones.estimate_vdot(efforts, today="2026-10-01", window_days=120) is None


def test_format_pace_and_time():
    assert zones.fmt_pace(9 * 60 + 5) == "9:05"
    assert zones.fmt_pace(9 * 60 + 59.6) == "10:00"
    assert zones.fmt_time(3725) == "1:02:05"
    assert zones.fmt_time(1500) == "25:00"
