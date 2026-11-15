"""Build the walk route and safety data for the map.

Usage: uv run python scout/build_route.py   (after run_scout.py)
Reads  docs/data/pins.json and NASA's Curiosity REMS weather feed.
Writes docs/data/route.json.

Everything estimated or assumed here is labeled as such in the output, and the page
shows those labels.
"""
import json
import math
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs/data"
WEATHER_URL = "https://mars.nasa.gov/rss/api/?feed=weather&category=msl&feedtype=json"
MARS_RADIUS_M = 3_396_190
WALK_SPEED_M_S = 0.5  # assumption: slow suited walk on rough ground
# Proposed science stops, by sol of the scout pin they sit at.
SCIENCE_STOPS = {
    4660: ("Stop A: ridge and hollow", "Bedrock ridge next to a sand-filled hollow. Compare ridge and hollow material."),
    4671: ("Stop B: fractured bedrock", "Wide exposure of fractured bedrock plates between ridges."),
    4711: ("Stop C: Nevado Sajama drill area", "Where Curiosity drilled a boxwork ridge in November 2025. Sample the same ridge."),
}
REROUTE_SOL = 4660
DETOUR_M, DETOUR_TURN_DEG = 8, -30  # how far and how far left the drawn detour goes


def metres(a, b):
    north = math.radians(b["lat"] - a["lat"]) * MARS_RADIUS_M
    east = math.radians(b["lon"] - a["lon"]) * MARS_RADIUS_M * math.cos(math.radians(a["lat"]))
    return math.hypot(north, east)


def offset(p, bearing_deg, dist_m):
    b = math.radians(bearing_deg)
    return [p["lat"] + math.degrees(dist_m * math.cos(b) / MARS_RADIUS_M),
            p["lon"] + math.degrees(dist_m * math.sin(b) / (MARS_RADIUS_M * math.cos(math.radians(p["lat"]))))]


def main():
    pins = json.loads((DATA / "pins.json").read_text())["pins"]
    # Curiosity's whole traverse since landing, as context on the map
    waypoints = json.loads((ROOT / "data/curiosity/MSL_waypoints.json").read_text())["features"]
    traverse = [[round(f["properties"]["lat"], 6), round(f["properties"]["lon"], 6)] for f in waypoints]
    traverse_km = waypoints[-1]["properties"]["dist_km"]
    last_sol = waypoints[-1]["properties"]["sol"]
    req = urllib.request.Request(WEATHER_URL, headers={"User-Agent": "mars-scout (Space Apps project)"})
    with urllib.request.urlopen(req, timeout=90) as r:
        weather = {int(s["sol"]): s for s in json.loads(r.read())["soles"]}

    # distance along the scout's stops, and the walk back to the start from each one
    along = [0.0]
    for a, b in zip(pins, pins[1:]):
        along.append(along[-1] + metres(a, b))

    stops = []
    for pin, dist in zip(pins, along):
        w = weather.get(pin["sol"])
        stops.append({
            "id": pin["id"], "sol": pin["sol"],
            "distance_from_start_m": round(dist, 1),
            "walk_back_min": round(dist / WALK_SPEED_M_S / 60, 1),
            "science": dict(zip(["name", "why"], SCIENCE_STOPS[pin["sol"]])) if pin["sol"] in SCIENCE_STOPS else None,
            "weather": None if w is None else {
                "earth_date": w["terrestrial_date"], "air_temp_min_c": w["min_temp"], "air_temp_max_c": w["max_temp"],
                "ground_temp_min_c": w["min_gts_temp"], "ground_temp_max_c": w["max_gts_temp"],
                "pressure_pa": w["pressure"], "sky": w["atmo_opacity"], "uv": w["local_uv_irradiance_index"],
                "sunrise": w["sunrise"], "sunset": w["sunset"],
            },
        })

    # every sol of the drive, for the temperature chart (some sols have no REMS reading)
    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    daily = []
    for sol in range(pins[0]["sol"], pins[-1]["sol"] + 1):
        w = weather.get(sol)
        if w and num(w["min_temp"]) is not None and num(w["max_temp"]) is not None:
            daily.append({"sol": sol, "earth_date": w["terrestrial_date"],
                          "air_min_c": num(w["min_temp"]), "air_max_c": num(w["max_temp"]),
                          "ground_min_c": num(w["min_gts_temp"]), "ground_max_c": num(w["max_gts_temp"]),
                          "pressure_pa": num(w["pressure"]), "uv": w["local_uv_irradiance_index"],
                          "sky": w["atmo_opacity"], "sunrise": w["sunrise"], "sunset": w["sunset"]})

    def minutes(t):
        h, m = t.split(":")
        return int(h) * 60 + int(m)

    daylight = [minutes(d["sunset"]) - minutes(d["sunrise"]) for d in daily]
    pressures = [d["pressure_pa"] for d in daily if d["pressure_pa"]]
    uv = {}
    for d in daily:
        uv[d["uv"]] = uv.get(d["uv"], 0) + 1
    sky = {}
    for d in daily:
        sky[d["sky"]] = sky.get(d["sky"], 0) + 1
    dose_day = 0.67
    environment = {
        "sols_with_readings": len(daily),
        "air_min_c": min(d["air_min_c"] for d in daily), "air_max_c": max(d["air_max_c"] for d in daily),
        "ground_min_c": min(d["ground_min_c"] for d in daily if d["ground_min_c"] is not None),
        "ground_max_c": max(d["ground_max_c"] for d in daily if d["ground_max_c"] is not None),
        "pressure_min_pa": min(pressures), "pressure_max_pa": max(pressures),
        "earth_sea_level_pa": 101325,
        "daylight_hours_min": round(min(daylight) / 60, 1), "daylight_hours_max": round(max(daylight) / 60, 1),
        "uv_sol_counts": uv, "sky_sol_counts": sky,
        "daily": daily,
    }
    elevation = [{"id": p["id"], "sol": p["sol"], "distance_m": round(d, 1), "elevation_m": round(p["elevation_m"], 1),
                  "tilt_deg": p["rover_tilt_deg"]} for p, d in zip(pins, along)]

    line = [[p["lat"], p["lon"]] for p in pins]
    science = [p for p in pins if p["sol"] in SCIENCE_STOPS]
    orbital = [line[0]] + [[p["lat"], p["lon"]] for p in science] + [line[-1]]

    # Re-route: the scout picked a path to the left of straight ahead in the photo.
    # The photo is not geolocated, so the bend drawn on the map is illustrative.
    i = next(k for k, p in enumerate(pins) if p["sol"] == REROUTE_SOL)
    ahead = next((v for v in pins[i]["views"] if v["direction"] == "ahead"), pins[i]["views"][0])
    detour = offset(pins[i], ahead["photo_azimuth_deg"] + DETOUR_TURN_DEG, DETOUR_M)
    scouted = line[: i + 1] + [detour] + line[i + 1:]

    out = {
        "walk_speed_m_s": WALK_SPEED_M_S,
        "total_distance_m": round(along[-1], 1),
        "total_walk_min": round(along[-1] / WALK_SPEED_M_S / 60, 1),
        "scouted_route": scouted,
        "orbital_plan": orbital,
        "reroute": {"pin_id": pins[i]["id"], "detour_point": detour,
                    "straight_hazard": ahead["straight_hazard"], "chosen_hazard": ahead["chosen_hazard"]},
        "traverse": traverse, "traverse_km": traverse_km, "traverse_last_sol": last_sol,
        "photos_analysed": sum(len(p["views"]) for p in pins),
        "stops": stops,
        "environment": environment,
        "elevation_profile": elevation,
        "climb_m": round(max(e["elevation_m"] for e in elevation) - min(e["elevation_m"] for e in elevation), 1),
        "radiation": {
            "dose_msv_per_day": dose_day,
            "dose_msv_this_walk": round(dose_day * (along[-1] / WALK_SPEED_M_S) / 86400, 4),
            "dose_msv_8h_eva": round(dose_day * 8 / 24, 2),
            "earth_background_msv_per_day": round(2.4 / 365, 4),
            "times_earth_background": round(dose_day / (2.4 / 365)),
            "source": "Curiosity RAD surface average, Aug 2012 to Jun 2013 (Hassler et al., Science, 2014)",
            "note": "Published long-term average, not a reading for these sols.",
            "earth_source": "Earth: 2.4 mSv/year world average natural background (UNSCEAR)",
            "storm_note": "Solar storms can raise the dose sharply for hours. Live solar-storm alerts are not included in this replay.",
        },
        "assumptions": [
            f"Walking speed {WALK_SPEED_M_S} m/s is an assumption for a suited astronaut on rough ground.",
            "Distances are straight lines between rover stops; the real path is longer.",
            "The re-route bend is illustrative: the scout picks its path in the photo, which is not geolocated.",
            "Weather is the Curiosity REMS reading for the sol the rover reached each stop.",
            "Each stop's status is for the view ahead, toward the next stop. Other directions are shown for looking around.",
        ],
    }
    (DATA / "route.json").write_text(json.dumps(out, indent=1))
    missing = [s["sol"] for s in stops if s["weather"] is None]
    print(f"route {out['total_distance_m']} m, {out['total_walk_min']} min; weather missing for sols {missing}")


if __name__ == "__main__":
    main()
