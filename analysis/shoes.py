"""Shoe mileage: how many miles each pair has, and how close it is to needing replacing.

Miles come from Strava's own lifetime total for each shoe (refreshed every sync, so re-tagging an old run in Strava is picked up), never less than
the runs we have tagged. A shoe can also carry starting miles (miles from before it was tagged in Strava) and its own replace-at limit.
Pure functions; the server passes in rows and settings.
"""
from analysis.zones import MI

DEFAULT_LIMIT_MI = 400          # a common rule of thumb is 300-500 mi for cushioned trainers
CLOSE_FRACTION = 0.75


def _name(gid, names):
    return (names.get(gid) or "").strip() or f"Shoes ...{str(gid)[-4:]}"


def summarize(rows, untagged, settings):
    """rows: [{gear_id, runs, meters, last_day}] for tagged runs. untagged: {runs, meters}. Returns {shoes: [...], untagged: {...}}."""
    names, info, mine = settings.get("gear_names", {}), settings.get("gear_info", {}), settings.get("shoes", {})
    by_id = {r["gear_id"]: r for r in rows}
    shoes = []
    for gid in sorted(set(by_id) | set(info)):
        run = by_id.get(gid, {"runs": 0, "meters": 0.0, "last_day": None})
        own = mine.get(gid, {})
        strava_mi = (info.get(gid, {}).get("distance_m") or 0) / MI
        tagged_mi = (run["meters"] or 0) / MI
        start_mi = float(own.get("start_mi") or 0)
        limit_mi = float(own.get("limit_mi") or DEFAULT_LIMIT_MI)
        miles = max(strava_mi, tagged_mi) + start_mi
        frac = miles / limit_mi
        shoes.append({"id": gid, "name": _name(gid, names), "miles": round(miles, 1), "runs": run["runs"], "last_day": run["last_day"],
                      "start_mi": start_mi, "limit_mi": limit_mi, "left_mi": round(max(0.0, limit_mi - miles), 1), "fraction": frac,
                      "status": "replace" if frac >= 1 else "close" if frac >= CLOSE_FRACTION else "ok",
                      "retired": bool(info.get(gid, {}).get("retired"))})
    shoes.sort(key=lambda s: (not s["retired"], s["last_day"] or ""), reverse=True)        # active shoes first, most recently worn first
    untagged_mi = round((untagged["meters"] or 0) / MI, 1)
    covered = sum(s["start_mi"] for s in shoes) >= untagged_mi - 0.5          # starting miles already account for the untagged runs
    return {"shoes": shoes, "untagged": {"runs": untagged["runs"], "miles": untagged_mi, "covered": covered}}
