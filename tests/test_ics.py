from datetime import date, datetime

from analysis import ics

W = [
    {"date": "2026-10-06", "title": "Tempo, 5.0 mi", "description": "2 mi warm-up, 3 mi @ 8:40; cool-down.\nKeep it smooth.",
     "distance_mi": 5.0, "duration_min": 48, "kind": "tempo"},
    {"date": "2026-10-08", "title": "Easy 4.0 mi", "description": "Conversational", "distance_mi": 4.0,
     "duration_min": 40, "kind": "easy"},
]
NOW = datetime(2026, 10, 1, 12, 0, 0)


def test_calendar_structure():
    text = ics.to_ics(W, "Run Lab: Syracuse Half", plan_id="p1", now=NOW)
    assert text.startswith("BEGIN:VCALENDAR\r\n")
    assert text.rstrip().endswith("END:VCALENDAR")
    assert text.count("BEGIN:VEVENT") == 2
    assert "VERSION:2.0" in text and "X-WR-CALNAME:Run Lab: Syracuse Half" in text


def test_event_fields():
    text = ics.to_ics(W, "x", plan_id="p1", start_time="17:30", now=NOW)
    assert "DTSTART:20261006T173000" in text
    assert "DTEND:20261006T181800" in text  # 48 min after 17:30
    assert "DTSTAMP:20261001T120000Z" in text
    assert "UID:p1-2026-10-06-tempo@runlab.local" in text


def test_text_is_escaped():
    text = ics.to_ics(W, "x", plan_id="p1", now=NOW)
    assert "warm-up\\, 3 mi @ 8:40\\; cool-down.\\nKeep it smooth." in text.replace("\r\n ", "")


def test_lines_fold_at_75_octets_and_use_crlf():
    long = {**W[0], "description": "é" * 200}
    text = ics.to_ics([long], "x", plan_id="p1", now=NOW)
    assert "\n" not in text.replace("\r\n", "")
    for line in text.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75, line


def test_uids_are_stable_across_exports():
    a = ics.to_ics(W, "x", plan_id="p1", now=NOW)
    b = ics.to_ics(W, "x", plan_id="p1", now=datetime(2026, 11, 1))
    uids = lambda t: sorted(l for l in t.split("\r\n") if l.startswith("UID:"))
    assert uids(a) == uids(b)


def test_two_workouts_same_day_get_distinct_uids():
    twice = [W[0], {**W[1], "date": "2026-10-06"}]
    text = ics.to_ics(twice, "x", plan_id="p1", now=NOW)
    uids = [l for l in text.split("\r\n") if l.startswith("UID:")]
    assert len(set(uids)) == 2
