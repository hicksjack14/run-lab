"""Goal races (NYC Half, NYC Marathon, Boston Marathon): what it takes to get in, and where Jack stands.

The requirements are FACTS THAT CHANGE EVERY YEAR, so they live here as data with a source and a "verified" date, not
scattered through the page. Re-check the sources and bump VERIFIED when they are refreshed.

Verified 2026-10-05:
  - Boston: read from the B.A.A.'s own qualify page (https://www.baa.org/races/boston-marathon/qualify/).
  - NYC Half / NYC Marathon: NYRR's own pages block automated reading, so these come from search results quoting
    nyrr.org pages; double-check on nyrr.org before relying on a deadline.
Standards are for ONE division, men 18-34 (Jack's choice); other divisions would need their own numbers.
"""
from datetime import date

from analysis import zones

VERIFIED = "2026-10-05"
DIVISION = {"label": "Men 18-34", "age_group": "18-34"}
MI = 1609.344
HALF_M, MARATHON_M = 21097.5, 42195.0

SRC_BAA = {"label": "B.A.A.: Qualify for the Boston Marathon", "url": "https://www.baa.org/races/boston-marathon/qualify/"}
SRC_NYC_QUAL = {"label": "NYRR: Marathon time qualifiers", "url": "https://www.nyrr.org/tcsnycmarathon/time-qualifiers"}
SRC_NYC_9P1 = {"label": "NYRR: 9+1 program", "url": "https://www.nyrr.org/run/guaranteed-entry/tcs-new-york-city-marathon-9plus1-program"}
SRC_NYC_HALF = {"label": "NYRR: How to enter the NYC Half", "url": "https://www.nyrr.org/run/guaranteed-entry/united-airlines-nyc-half"}

GOALS = [
    {
        "key": "nyc-half", "name": "United Airlines NYC Half", "short": "NYC Half", "city": "New York",
        "when": "March 2027", "distance_m": HALF_M, "distance_label": "Half marathon",
        "standard": {"seconds": 4860, "text": "1:21:00", "distance_m": HALF_M, "distance_label": "half marathon",
                     "window": ("2025-11-02", "2026-10-11")},
        "routes": [
            {"title": "Run a qualifying time", "detail": "A half marathon in 1:21:00 or faster (men 18-34) at an NYRR race: the NYC Half, Maybelline Women's Half, RBC Brooklyn Half or NYRR Staten Island Half. Guaranteed entry. A certified half marathon run elsewhere also counts, but only for a limited number of spots."},
            {"title": "4 of 6 program", "detail": "Complete four qualifying NYRR events in 2026 as a member (the last one is the NYRR Staten Island Half on October 11, 2026) for guaranteed entry. It is nearly too late for 2027.", "counts_nyrr_year": 2026, "counts_needed": 4},
            {"title": "The drawing", "detail": "Anyone can apply to the general drawing, with no guarantee. NYRR members are also in a member-only second-chance drawing."},
        ],
        "notes": "The qualifying window for the 2027 race ends with the Staten Island Half on October 11, 2026.",
        "sources": [SRC_NYC_HALF],
    },
    {
        "key": "nyc-marathon", "name": "TCS New York City Marathon", "short": "NYC Marathon", "city": "New York",
        "when": "November 7, 2027", "distance_m": MARATHON_M, "distance_label": "Marathon",
        "standard": {"seconds": 10380, "text": "2:53:00", "distance_m": MARATHON_M, "distance_label": "marathon",
                     "alt": {"seconds": 4860, "text": "1:21:00", "distance_m": HALF_M, "distance_label": "half marathon"},
                     "window": ("2026-01-01", "2026-12-31")},
        "routes": [
            {"title": "Run a qualifying time", "detail": "A marathon in 2:53:00 or faster, or a half marathon in 1:21:00 or faster (men 18-34), by net time, between January 1 and December 31, 2026. Guaranteed entry if run at an in-person NYRR marathon or half. At another certified marathon you join a limited pool, and if it fills only the fastest in each age and gender group get in. Half marathon qualifiers must be an eligible NYRR half (NYC Half, Maybelline Women's Half, RBC Brooklyn Half, Staten Island Half). Your age on race day (November 7, 2027) sets the standard."},
            {"title": "9+1 program", "detail": "In calendar year 2027: nine qualifying NYRR races, one volunteer shift, and an active NYRR membership through December 31, 2027, for guaranteed entry to the 2028 marathon. Joining the program is now limited to about 15,000 members chosen by a free drawing (this year's ran September 17-29, 2026, drawn October 1; you had to be a member by September 16).", "counts_nyrr_year": 2027, "counts_needed": 9},
            {"title": "Other ways in", "detail": "The general drawing, charity teams and tour operators also exist. See NYRR for the current rules."},
        ],
        "notes": "Qualifying runs for the 2027 race must happen in 2026, so the window is closing soon.",
        "sources": [SRC_NYC_QUAL, SRC_NYC_9P1],
    },
    {
        "key": "boston-marathon", "name": "Boston Marathon", "short": "Boston", "city": "Boston",
        "when": "April 19, 2027 (the 2027 field is already full)", "distance_m": MARATHON_M, "distance_label": "Marathon",
        "standard": {"seconds": 10500, "text": "2:55:00", "distance_m": MARATHON_M, "distance_label": "marathon",
                     "window": ("2025-09-13", "2027-01-01")},
        "routes": [
            {"title": "Run a qualifying time", "detail": "A certified full marathon in 2:55:00 or faster (men 18-34), by net (chip) time. Only a full marathon counts: shorter races, time trials, treadmill and handicapped marathons do not, and the course must be certified (USATF, AIMS or the national equivalent). The standard is set by your age on race day."},
            {"title": "The cut-off", "detail": "Meeting the standard only lets you apply; acceptance is not guaranteed. For 2027 you had to beat it by 5 minutes 17 seconds (2:49:43 or faster for men 18-34). Registration for 2027 closed September 18, 2026, and it was not first come, first served."},
            {"title": "Other ways in", "detail": "Charity numbers and other routes exist. See baa.org for the current rules. The qualifying window for the following Boston is set by the B.A.A. each year, so check before you run your qualifier."},
        ],
        "notes": "The 2027 window opened September 13, 2025 and registration has closed. The next window is not confirmed here: check baa.org.",
        "sources": [SRC_BAA],
    },
]
GOAL_KEYS = {g["key"] for g in GOALS}


def _fmt(seconds):
    return zones.fmt_time(seconds)


def _near(entry_m, target_m):
    return abs(entry_m - target_m) / target_m <= 0.02          # 2%: GPS-measured and course-measured both fit


def _best_time(log, target_m, window):
    lo, hi = window
    times = [e for e in log if e.get("time_s") and _near(e["distance_m"], target_m) and lo <= e["race_date"] <= hi]
    return min(times, key=lambda e: e["time_s"]) if times else None


def evaluate(goal, log, predictions, today):
    """Where Jack stands against one goal race.

    log: race log entries (dicts with race_date, distance_m, time_s, event, nyrr).
    predictions: {"Half marathon": seconds, "Marathon": seconds, ...} from his current fitness, or None.
    """
    std = goal["standard"]
    options = [std] + ([std["alt"]] if std.get("alt") else [])
    qualifier = None
    for opt in options:
        best = _best_time(log, opt["distance_m"], std["window"])
        if best and best["time_s"] <= opt["seconds"]:
            qualifier = {"entry": best, "standard_text": opt["text"], "distance_label": opt["distance_label"]}
            break
    closest = None
    for opt in options:
        best = _best_time(log, opt["distance_m"], std["window"])
        if best:
            gap = best["time_s"] - opt["seconds"]
            if closest is None or gap < closest["gap_s"]:
                closest = {"time_s": best["time_s"], "text": _fmt(best["time_s"]), "race_date": best["race_date"], "name": best.get("name"),
                           "standard_text": opt["text"], "distance_label": opt["distance_label"], "gap_s": gap}
    completed = [e for e in log if e.get("event") == goal["key"]]
    status = "completed" if completed else "qualified" if qualifier else "not_yet"

    # how far current fitness is from the standard (what he'd need to cut)
    predicted = None
    if predictions:
        for opt in options:
            key = "Marathon" if opt["distance_m"] == MARATHON_M else "Half marathon"
            pred = predictions.get(key)
            if pred:
                gap = pred - opt["seconds"]
                if predicted is None or gap < predicted["gap_s"]:
                    predicted = {"distance_label": opt["distance_label"], "predicted_text": _fmt(pred), "standard_text": opt["text"], "gap_s": gap,
                                 "gap_text": _fmt(abs(gap)), "pace_needed_s": opt["seconds"] / (opt["distance_m"] / MI)}

    counters = []
    for r in goal["routes"]:
        if r.get("counts_nyrr_year"):
            y = str(r["counts_nyrr_year"])
            n = sum(1 for e in log if e.get("nyrr") and e["race_date"].startswith(y))
            counters.append({"title": r["title"], "have": n, "need": r["counts_needed"], "year": r["counts_nyrr_year"]})

    window_end = std["window"][1]
    return {
        "status": status, "completed": completed,
        "qualified_with": qualifier, "closest": closest, "predicted": predicted, "counters": counters,
        "window_closed": window_end < today.isoformat(),
        "days_left": max(0, (date.fromisoformat(window_end) - today).days) if window_end >= today.isoformat() else 0,
    }


def goals_with_status(log, predictions, today):
    return [{**g, "standard": {k: v for k, v in g["standard"].items()}, **{"progress": evaluate(g, log, predictions, today)}} for g in GOALS]
