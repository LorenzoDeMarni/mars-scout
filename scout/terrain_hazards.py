"""Find steep ground and drop-offs around the walk from NASA's 1 m HiRISE elevation model.

Usage: uv run python scout/terrain_hazards.py   (after fetch_dem.py and run_scout.py)
Writes docs/data/slope.png (map overlay) and docs/data/terrain.json.

Slope is computed from the elevation model after light smoothing. A drop-off is a place
where elevation changes by more than DROP_M within a 3 m window (scarps, ledges, pits).
The slope limits are assumptions for a suited astronaut on foot, not NASA limits.
"""
import json
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DEM = ROOT / "data/dem"
OUT = ROOT / "docs/data"
CAUTION_DEG, AVOID_DEG = 15, 25
DROP_M = 1.5
MARS_RADIUS_M = 3_396_190


def main():
    dem = np.load(DEM / "walk_area.npy")
    meta = json.loads((DEM / "walk_area.json").read_text())
    pins = json.loads((OUT / "pins.json").read_text())["pins"]
    h, w = dem.shape
    missing = np.isnan(dem)
    filled = np.where(missing, np.nanmean(dem), dem).astype(np.float32)

    smooth = cv2.GaussianBlur(filled, (0, 0), 2.5)  # the 1 m model is noisy; smooth to about rover scale
    dy, dx = np.gradient(smooth, meta["pixel_m"])
    slope = np.degrees(np.arctan(np.hypot(dx, dy)))
    kernel = np.ones((3, 3), np.uint8)
    relief = cv2.dilate(filled, kernel) - cv2.erode(filled, kernel)  # on the unsmoothed model, to keep sharp edges
    drop = relief > DROP_M

    # map overlay: yellow = caution slope, red = avoid slope or drop-off
    rgba = np.zeros((h, w, 4), np.uint8)
    rgba[slope >= CAUTION_DEG] = (242, 182, 50, 105)
    rgba[(slope >= AVOID_DEG) | drop] = (229, 72, 77, 150)
    rgba[missing] = 0
    Image.fromarray(rgba).save(OUT / "slope.png", optimize=True)

    def pixel(lat, lon):
        row = (meta["north"] - lat) / (meta["north"] - meta["south"]) * h
        col = (lon - meta["west"]) / (meta["east"] - meta["west"]) * w
        return row, col

    def around(arr, lat, lon, radius=3):
        r, c = (int(round(v)) for v in pixel(lat, lon))
        return arr[max(r - radius, 0):r + radius + 1, max(c - radius, 0):c + radius + 1]

    stops = []
    for p in pins:
        stops.append({"id": p["id"],
                      "dem_slope_deg": round(float(np.median(around(slope, p["lat"], p["lon"]))), 1),
                      "dem_elevation_m": round(float(np.median(around(smooth, p["lat"], p["lon"]))), 1),
                      "rover_tilt_deg": p["rover_tilt_deg"], "rover_elevation_m": round(p["elevation_m"], 1)})

    # the straight line between consecutive stops, sampled every half metre
    segments = []
    for a, b in zip(pins, pins[1:]):
        (r0, c0), (r1, c1) = pixel(a["lat"], a["lon"]), pixel(b["lat"], b["lon"])
        n = max(int(math.hypot(r1 - r0, c1 - c0) * 2), 2)
        rows = np.clip(np.linspace(r0, r1, n).round().astype(int), 0, h - 1)
        cols = np.clip(np.linspace(c0, c1, n).round().astype(int), 0, w - 1)
        s = slope[rows, cols]
        drops = int(drop[rows, cols].sum())
        level = "avoid" if (s >= AVOID_DEG).mean() > 0.10 or drops >= 3 else \
                "caution" if (s >= CAUTION_DEG).mean() > 0.20 or drops else "ok"
        segments.append({"from": a["id"], "to": b["id"], "line": [[a["lat"], a["lon"]], [b["lat"], b["lon"]]],
                         "length_m": round(n / 2, 1), "max_slope_deg": round(float(s.max()), 1),
                         "mean_slope_deg": round(float(s.mean()), 1),
                         "share_over_caution": round(float((s >= CAUTION_DEG).mean()), 3),
                         "crosses_drop_off": drops > 0, "level": level})

    # validation: does the orbital slope agree with the tilt Curiosity measured on the ground?
    tilt = np.array([s["rover_tilt_deg"] for s in stops])
    orbital = np.array([s["dem_slope_deg"] for s in stops])
    elev_diff = np.array([s["dem_elevation_m"] - s["rover_elevation_m"] for s in stops])
    valid = ~missing
    out = {
        "bounds": [[meta["south"], meta["west"]], [meta["north"], meta["east"]]],
        "source": meta["source"],
        "thresholds": {"caution_deg": CAUTION_DEG, "avoid_deg": AVOID_DEG, "drop_m": DROP_M},
        "area": {"width_m": w, "height_m": h,
                 "share_caution": round(float(((slope >= CAUTION_DEG) & (slope < AVOID_DEG) & valid).sum() / valid.sum()), 3),
                 "share_avoid": round(float((((slope >= AVOID_DEG) | drop) & valid).sum() / valid.sum()), 3),
                 "max_slope_deg": round(float(slope[valid].max()), 1)},
        "validation": {"stops": len(stops),
                       "tilt_vs_orbital_slope_r": round(float(np.corrcoef(tilt, orbital)[0, 1]), 2),
                       "mean_abs_difference_deg": round(float(np.abs(tilt - orbital).mean()), 1),
                       "elevation_mean_difference_m": round(float(elev_diff.mean()), 1),
                       "elevation_difference_spread_m": round(float(elev_diff.std()), 1)},
        "stops": stops, "segments": segments,
    }
    (OUT / "terrain.json").write_text(json.dumps(out, indent=1))
    levels = {k: sum(s["level"] == k for s in segments) for k in ["ok", "caution", "avoid"]}
    print(f"area {w} x {h} m: {out['area']}")
    print(f"segments {levels}; validation {out['validation']}")


if __name__ == "__main__":
    main()
