"""Download Curiosity navigation camera photos for every rover stop in a range of sols.

Usage: uv run python scout/fetch_drive.py [first_sol] [last_sol]
Default sols 4600-4899: Curiosity's exploration of the boxwork ridges on Mount Sharp.

At each stop the scout looks around: one photo facing the next stop ("ahead"), and where
available one each to the right, behind and left. Only full-resolution frames that look
down at the ground are used.

Sources (both NASA/JPL):
- stops:  https://mars.nasa.gov/mmgis-maps/MSL/Layers/json/MSL_waypoints.json
- photos: https://mars.nasa.gov/api/v1/raw_image_items/ (left navigation camera)

Writes data/curiosity/drive/<stop>_<direction>.jpg and data/curiosity/drive/stops.json.
"""
import json
import math
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/curiosity/drive"
WAYPOINTS_URL = "https://mars.nasa.gov/mmgis-maps/MSL/Layers/json/MSL_waypoints.json"
API = ("https://mars.nasa.gov/api/v1/raw_image_items/?order=sol+asc&per_page=200&page={page}"
       "&condition_1=msl:mission&condition_2={first}:sol:gte&condition_3={last}:sol:lte&search=NAV_LEFT_B")
DIRECTIONS = {"ahead": 0, "right": 90, "behind": 180, "left": 270}
MAX_OFF_DEG = {"ahead": 45, "right": 30, "behind": 30, "left": 30}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "mars-scout (Space Apps project)"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


def bearing(a, b):
    """Compass bearing in degrees from stop a to stop b (flat approximation, fine over metres)."""
    north = b["lat"] - a["lat"]
    east = (b["lon"] - a["lon"]) * math.cos(math.radians(a["lat"]))
    return math.degrees(math.atan2(east, north)) % 360


def main():
    first = int(sys.argv[1]) if len(sys.argv) > 1 else 4600
    last = int(sys.argv[2]) if len(sys.argv) > 2 else 4899
    OUT.mkdir(parents=True, exist_ok=True)

    waypoints = get(WAYPOINTS_URL)
    (OUT.parent / "MSL_waypoints.json").write_bytes(waypoints)
    features = json.loads(waypoints)["features"]
    stops = [f["properties"] for f in features if first <= f["properties"]["sol"] <= last]

    # photo metadata, cached because it takes a few minutes to page through
    cache = OUT / f"photo_index_{first}_{last}.json"
    if cache.exists():
        photos = json.loads(cache.read_text())
    else:
        photos, page = [], 0
        while True:
            data = json.loads(get(API.format(page=page, first=first, last=last + 5)))
            photos += [{k: p[k] for k in ["site", "drive", "sol", "imageid", "url", "subframe_rect",
                                          "scale_factor", "camera_vector"]} for p in data["items"]]
            print(f"photo index page {page}: {len(photos)} of {data.get('total')}", flush=True)
            if not data.get("more"):
                break
            page += 1
        cache.write_text(json.dumps(photos))
    print(f"{len(stops)} stops, {len(photos)} left navigation camera photos")

    by_stop = {}
    for p in photos:
        if p["subframe_rect"] != "(1,1,1024,1024)" or p["scale_factor"] != 1 or "EDR_F" not in p["imageid"]:
            continue  # full-resolution full frames only
        # pointing vector in the local frame: x north, y east, z down
        x, y, z = (float(v) for v in p["camera_vector"].strip("()").split(","))
        down = math.degrees(math.asin(max(-1, min(1, z))))
        if 8 <= down <= 40:  # ground in view, not sky or the rover deck
            by_stop.setdefault((p["site"], p["drive"]), []).append((math.degrees(math.atan2(y, x)) % 360, down, p))

    result, downloads = [], []
    for i, stop in enumerate(stops):
        # "ahead" faces the next stop; at the last stop, keep the previous heading
        heading = bearing(stop, stops[i + 1]) if i + 1 < len(stops) else bearing(stops[i - 1], stop)
        name = f"sol{stop['sol']}_{stop['RMC']}"
        views = []
        for direction, turn in DIRECTIONS.items():
            want = (heading + turn) % 360
            best = min(by_stop.get((stop["site"], stop["drive"]), []),
                       key=lambda c: abs((c[0] - want + 180) % 360 - 180), default=None)
            if best is None or abs((best[0] - want + 180) % 360 - 180) > MAX_OFF_DEG[direction]:
                continue
            azimuth, down, p = best
            if any(v["photo_id"] == p["imageid"] for v in views):
                continue
            views.append({"direction": direction, "file": f"{name}_{direction}.jpg",
                          "photo_azimuth_deg": round(azimuth, 1), "photo_down_deg": round(down, 1),
                          "photo_sol": p["sol"], "photo_id": p["imageid"], "photo_url": p["url"]})
            downloads.append((OUT / f"{name}_{direction}.jpg", p["url"]))
        if not any(v["direction"] == "ahead" for v in views):
            print(f"sol {stop['sol']} stop {stop['RMC']}: no photo facing ahead, skipped")
            continue
        result.append({"id": name, "sol": stop["sol"], "lat": stop["lat"], "lon": stop["lon"],
                       "elevation_m": stop["elev_geoid"], "rover_tilt_deg": stop["tilt"],
                       "drive_m": stop["dist_m"], "heading_to_next_deg": round(heading, 1), "views": views})

    def download(job):
        path, url = job
        if not path.exists():
            path.write_bytes(get(url))

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(download, downloads))
    (OUT / "stops.json").write_text(json.dumps(result, indent=1))
    n_views = sum(len(s["views"]) for s in result)
    print(f"wrote {len(result)} stops with {n_views} photos to {OUT / 'stops.json'}")


if __name__ == "__main__":
    main()
