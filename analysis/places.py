"""Where he runs: home base, farthest run, favourite start areas, and how much new ground he covers over time.

Pure functions over routes shaped like {"id", "date" (YYYY-MM-DD), "miles", "pts": [[lat, lng], ...]}.
Ground is measured in a grid of 250 m squares ("cells"): a cell counts once the first time any run passes through it.
Everything stays on the machine; nothing here calls a geocoder.
"""
import math
from collections import defaultdict

MI = 1609.344
EARTH_M = 6_371_000.0
GPS_GAP_M = 5_000        # a jump bigger than this between samples is a GPS gap, not running
AREA_CELL_M = 1_000      # starts within the same 1 km square count as the same place
REGION_LINK_M = 25_000   # start areas within 25 km of each other belong to the same region (a city and its suburbs)


def haversine_m(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * EARTH_M * math.asin(math.sqrt(h))


def _xy(pt, lat0):
    """Local metres east/north of the equator-meridian origin, fine for city-scale distances."""
    return pt[1] * 111_320.0 * math.cos(math.radians(lat0)), pt[0] * 110_574.0


def cells_for_route(pts, lat0, size_m=250, step_m=50):
    """Grid cells a route passes through, densifying long gaps between samples (but not GPS jumps)."""
    cells = set()
    prev = None
    for p in pts:
        x, y = _xy(p, lat0)
        if prev is not None:
            dx, dy = x - prev[0], y - prev[1]
            d = math.hypot(dx, dy)
            if d <= GPS_GAP_M:
                for i in range(1, int(d // step_m) + 1):
                    f = i * step_m / d
                    cells.add((int((prev[0] + dx * f) // size_m), int((prev[1] + dy * f) // size_m)))
        cells.add((int(x // size_m), int(y // size_m)))
        prev = (x, y)
    return cells


def _regions(routes, groups, home):
    """Group start areas that are close together into regions (e.g. Syracuse, a summer in NYC, home for break)."""
    cells = list(groups)
    parent = {c: c for c in cells}

    def find(c):
        while parent[c] != c:
            parent[c] = parent[parent[c]]
            c = parent[c]
        return c

    centre = {c: (sum(r["pts"][0][0] for r in groups[c]) / len(groups[c]), sum(r["pts"][0][1] for r in groups[c]) / len(groups[c])) for c in cells}
    for i, a in enumerate(cells):
        for b in cells[i + 1:]:
            if haversine_m(centre[a], centre[b]) <= REGION_LINK_M:
                parent[find(a)] = find(b)
    merged = defaultdict(list)
    for c in cells:
        merged[find(c)].extend(groups[c])
    out = []
    for rs in merged.values():
        pts = [p for r in rs for p in r["pts"]]
        starts = [r["pts"][0] for r in rs]
        out.append({"runs": len(rs), "miles": round(sum(r["miles"] for r in rs), 2), "first": min(r["date"] for r in rs), "last": max(r["date"] for r in rs),
                    "lat": sum(p[0] for p in starts) / len(starts), "lng": sum(p[1] for p in starts) / len(starts),
                    "bounds": [[min(p[0] for p in pts), min(p[1] for p in pts)], [max(p[0] for p in pts), max(p[1] for p in pts)]],
                    "route_ids": [r["id"] for r in rs], "home": any(haversine_m((home["lat"], home["lng"]), r["pts"][0]) <= REGION_LINK_M for r in rs)})
    out.sort(key=lambda r: (-r["runs"], r["first"]))
    return out


def analyze(routes, size_m=250):
    routes = sorted((r for r in routes if r.get("pts")), key=lambda r: r["date"])
    if not routes:
        return {"home": None, "farthest": None, "areas": [], "regions": [], "exploration": {"cells_total": 0, "cumulative": [], "monthly": []}}
    all_pts = [p for r in routes for p in r["pts"]]
    lat0 = sum(p[0] for p in all_pts) / len(all_pts)

    # ---- favourite start areas (1 km squares), most-used first
    groups = defaultdict(list)
    for r in routes:
        x, y = _xy(r["pts"][0], lat0)
        groups[(int(x // AREA_CELL_M), int(y // AREA_CELL_M))].append(r)
    areas = []
    for rs in groups.values():
        starts = [r["pts"][0] for r in rs]
        areas.append({"lat": sum(p[0] for p in starts) / len(starts), "lng": sum(p[1] for p in starts) / len(starts),
                      "runs": len(rs), "miles": round(sum(r["miles"] for r in rs), 2), "last": max(r["date"] for r in rs)})
    areas.sort(key=lambda a: (-a["runs"], -a["miles"]))
    home = {"lat": areas[0]["lat"], "lng": areas[0]["lng"], "runs": areas[0]["runs"]}

    # ---- farthest point from home
    far = None
    for r in routes:
        d, pt = max(((haversine_m((home["lat"], home["lng"]), p), p) for p in r["pts"]), key=lambda x: x[0])
        if far is None or d > far["_m"]:
            far = {"_m": d, "run_id": r["id"], "date": r["date"], "pt": pt}
    farthest = {"miles": far["_m"] / MI, "run_id": far["run_id"], "date": far["date"], "lat": far["pt"][0], "lng": far["pt"][1]}

    # ---- new ground: cumulative unique cells, and per month the share of visited cells that were new that month
    seen, cumulative = set(), []
    month_new, month_visited = defaultdict(set), defaultdict(set)
    for r in routes:
        cells = cells_for_route(r["pts"], lat0, size_m)
        new = cells - seen
        month = r["date"][:7]
        month_new[month] |= new
        month_visited[month] |= cells
        seen |= cells
        cumulative.append({"date": r["date"], "id": r["id"], "cells": len(seen), "new": len(new)})
    monthly = [{"month": m, "new": len(month_new[m]), "visited": len(month_visited[m]),
                "share_new": len(month_new[m]) / len(month_visited[m]) if month_visited[m] else 0.0}
               for m in sorted(month_visited)]
    return {"home": home, "farthest": farthest, "areas": areas[:6], "regions": _regions(routes, groups, home),
            "exploration": {"cells_total": len(seen), "cell_m": size_m, "cumulative": cumulative, "monthly": monthly}}
