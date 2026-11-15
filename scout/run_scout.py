"""The scout: classify terrain in each photo, pick the safest path, write map pins.

Usage: uv run python scout/run_scout.py
Reads  data/curiosity/drive/ (from fetch_drive.py) and checkpoints/terrain.pt.
Writes docs/data/pins.json and docs/data/pins/<stop>_<direction>_{photo,paths,edge}.jpg.

Each stop has up to four views (ahead, right, behind, left). For each view:

Path picking is 2D only: straight candidate paths fan out from the bottom of the photo
to the far edge of the near ground. Each path is scored by the share of its corridor
that is an obstacle: sand or big rock according to the model, or a rock found by the
classical edge check in classic_cv.py. Where the two detectors disagree, the view is
never reported as clear.

Rover hardware in the photo is recognised by the model (a class learned from the
AI4Mars rover masks) and ignored.
"""
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "model"))
from common import CHECKPOINTS, CLASSES, ROVER, SIZE, build_model, to_input  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
import classic_cv  # noqa: E402

DRIVE = ROOT / "data/curiosity/drive"
OUT = ROOT / "docs/data"
COLORS = np.array([(166, 118, 74), (70, 130, 220), (240, 200, 60), (220, 50, 50), (90, 90, 90)], dtype=float)
HAZARD = [2, 3]  # sand, big rock
N_PATHS = 7
VIEW = 512  # size of the saved images
HALF_FOV = math.radians(22.5)  # navigation camera field of view is about 45 degrees
CLEAR_BELOW, BLOCKED_ABOVE = 0.05, 0.25  # hazard share thresholds for status
MAX_ROVER = 0.40  # skip photos that are mostly rover hardware
MIN_ROVER_AREA = 0.01 * SIZE * SIZE  # rover patches smaller than 1% of the photo are treated as model noise


def far_row(down_deg):
    """Image row (0-1) where the near ground ends, from how far down the camera points.

    The model was trained only on ground within 30 m, so paths stop a little below
    the horizon. Ignores rover tilt and terrain slope, so it is approximate.
    """
    horizon = 0.5 - 0.5 * math.tan(math.radians(down_deg)) / math.tan(HALF_FOV)
    return min(max(horizon + 0.10, 0.12), 0.45)


def valid_ground(far, rover):
    """Ground the scout judges: below the far row and not rover hardware."""
    valid = np.zeros((SIZE, SIZE), dtype=bool)
    valid[int(far * SIZE):, :] = True
    # ignore specks: the model sometimes marks a thin sliver on the photo's border as rover
    n, labels, stats, _ = cv2.connectedComponentsWithStats(rover.astype(np.uint8))
    big = [k for k in range(1, n) if stats[k, cv2.CC_STAT_AREA] >= MIN_ROVER_AREA]
    rover = np.isin(labels, big)
    # grow the rover mask a little: its edges are where the model is least sure
    grown = cv2.dilate(rover.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21))) > 0
    return valid & ~grown


def start_point(valid):
    """Where paths begin: the lowest point of clear ground, preferring the centre."""
    best = None
    for x in np.arange(0.2, 0.81, 0.05):
        rows = np.nonzero(valid[:, int(x * SIZE)])[0]
        if len(rows) == 0:
            continue
        y = rows[-1]  # lowest clear row in this column, above any rover hardware
        key = (round(y / SIZE, 1), -abs(x - 0.5))
        if best is None or key > best[0]:
            best = (key, [float(x), float((y + 1) / SIZE)])
    return best[1] if best else None


def corridor(start, end, size):
    """Mask of the strip a walker would cover: wide near the camera, narrow far away."""
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    for t in np.linspace(0, 1, 80):
        x = (start[0] + (end[0] - start[0]) * t) * size
        y = (start[1] + (end[1] - start[1]) * t) * size
        r = size * (0.07 - 0.05 * t)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=255)
    return np.array(mask) > 0


def scout_view(model, device, grey, down_deg, name):
    """Analyse one photo. Returns the view's results, or None if no usable ground is in view."""
    with torch.no_grad():
        prob = model(to_input(torch.from_numpy(np.array(grey)).to(device)[None])).softmax(1)[0]
    cls = prob.argmax(0).cpu().numpy()
    conf = prob.max(0).values.cpu().numpy()

    far = far_row(down_deg)
    valid = valid_ground(far, cls == ROVER)
    start = start_point(valid)
    if start is None or start[1] - far < 0.3 or valid.mean() < 0.15 or (cls == ROVER).mean() > MAX_ROVER:
        return None

    # second opinion without machine learning: rocks from shadows, smooth ground from edges
    rock_cv, smooth_cv, contours = classic_cv.analyze(np.array(grey), valid, far)
    model_hazard = np.isin(cls, HAZARD)

    paths = []
    for k, ex in enumerate(np.linspace(0.08, 0.92, N_PATHS)):
        end = [float(ex), far]
        strip = corridor(start, end, SIZE)
        usable = strip & valid
        if usable.sum() < 0.6 * strip.sum():
            continue  # path runs mostly through rover hardware
        share = [float((cls[usable] == c).mean()) for c in range(len(CLASSES))]
        paths.append({"index": k, "start": start, "end": end,
                      # hazard = what either detector calls an obstacle
                      "hazard": round(float((model_hazard | rock_cv)[usable].mean()), 3),
                      "model_hazard": round(sum(share[c] for c in HAZARD), 3),
                      "edge_rock": round(float(rock_cv[usable].mean()), 3),
                      "edge_smooth": round(float(smooth_cv[usable].mean()), 3),
                      "terrain": {n: round(s, 3) for n, s in zip(CLASSES, share)}})
    if not paths:
        return None
    centre = (N_PATHS - 1) / 2
    # safest first; among near-equal paths prefer the one closest to straight ahead
    best = min(paths, key=lambda p: (round(p["hazard"], 2), abs(p["index"] - centre)))
    straight = min(paths, key=lambda p: abs(p["index"] - centre))
    status = "clear" if best["hazard"] < CLEAR_BELOW else "blocked" if best["hazard"] > BLOCKED_ABOVE else "caution"
    if status == "clear" and straight["hazard"] >= CLEAR_BELOW:
        status = "caution"  # a safe path exists, but not straight ahead

    # cross-check: where do the two detectors disagree on the chosen path?
    notes = []
    if best["edge_rock"] >= 0.03 and best["terrain"]["big rock"] < 0.01:
        notes.append(f"Edge check finds rock shadows on {best['edge_rock']:.0%} of the chosen path; the model sees no big rock there.")
    if best["edge_smooth"] >= 0.08 and best["terrain"]["sand"] < 0.03:
        notes.append(f"Edge check finds smooth ground on {best['edge_smooth']:.0%} of the chosen path; the model does not call it sand.")
    sand = (cls == 2) & valid
    if sand.mean() >= 0.03:
        confirmed = float(smooth_cv[sand].mean())
        if confirmed < 0.15:
            notes.append(f"The model marks sand in view, but only {confirmed:.0%} of it is smooth in the edge check. It may be rippled sand or a model error.")
    agreement = "disagree" if notes else "agree"
    if agreement == "disagree" and status == "clear":
        status = "caution"  # do not report clear when the two detectors disagree

    # images for the map
    photo = ImageOps.autocontrast(grey, cutoff=1).convert("RGB")
    base = np.array(photo).astype(float)
    tint = base.copy()
    tint[valid] = 0.55 * base[valid] + 0.45 * COLORS[cls][valid]
    tint[~valid] *= 0.45  # dim the areas the scout ignores
    outlined = np.ascontiguousarray(tint.astype(np.uint8))
    cv2.drawContours(outlined, contours, -1, (255, 60, 200), 2)  # edge-check rocks
    drawn = Image.fromarray(outlined).resize((VIEW, VIEW), Image.LANCZOS)
    d = ImageDraw.Draw(drawn)
    for p in sorted(paths, key=lambda p: p is best):  # chosen path drawn last, on top
        chosen = p is best
        xy = [(p["start"][0] * VIEW, p["start"][1] * VIEW), (p["end"][0] * VIEW, p["end"][1] * VIEW)]
        if chosen:
            d.line(xy, fill=(255, 255, 255), width=9)
        d.line(xy, fill=(40, 220, 90) if chosen else (235, 60, 60), width=6 if chosen else 2)
    edge = Image.fromarray(classic_cv.draw(np.array(photo), rock_cv, smooth_cv, contours, valid))
    photo.resize((VIEW, VIEW), Image.LANCZOS).save(OUT / "pins" / f"{name}_photo.jpg", quality=80)
    drawn.save(OUT / "pins" / f"{name}_paths.jpg", quality=80)
    edge.resize((VIEW, VIEW), Image.LANCZOS).save(OUT / "pins" / f"{name}_edge.jpg", quality=80)

    return {
        "status": status,
        "ground": {n: round(float((cls[valid] == c).mean()), 3) for c, n in enumerate(CLASSES)},
        "rover_in_view": round(float((cls == ROVER).mean()), 3),
        "model_confidence": round(float(conf[valid].mean()), 2),
        "chosen_path": best["index"], "straight_path": straight["index"],
        "chosen_hazard": best["hazard"], "straight_hazard": straight["hazard"],
        "edge_check": {"agreement": agreement, "notes": notes, "rocks_found": len(contours),
                       "rock_share": round(float(rock_cv[valid].mean()), 3),
                       "smooth_share": round(float(smooth_cv[valid].mean()), 3)},
    }


def main():
    stops = json.loads((DRIVE / "stops.json").read_text())
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = build_model().to(device).eval()
    model.load_state_dict(torch.load(CHECKPOINTS / "terrain.pt", map_location=device))
    (OUT / "pins").mkdir(parents=True, exist_ok=True)
    for old in (OUT / "pins").glob("*.jpg"):
        old.unlink()

    pins, counts, skipped = [], {}, 0
    for stop in stops:
        views = []
        for v in stop["views"]:
            grey = Image.open(DRIVE / v["file"]).convert("L").resize((SIZE, SIZE), Image.BILINEAR)
            name = f"{stop['id']}_{v['direction']}"
            result = scout_view(model, device, grey, v["photo_down_deg"], name)
            if result is None:
                skipped += 1
                continue
            views.append({"direction": v["direction"], "name": name, "photo_id": v["photo_id"],
                          "photo_url": v["photo_url"], "photo_azimuth_deg": v["photo_azimuth_deg"], **result})
        if not views:
            continue
        safest = min(views, key=lambda v: v["chosen_hazard"])
        # the stop's status is the view toward the next stop; if that photo is unusable, the safest other view
        ahead = next((v for v in views if v["direction"] == "ahead"), safest)
        pins.append({**{k: stop[k] for k in ["id", "sol", "lat", "lon", "elevation_m", "rover_tilt_deg",
                                             "drive_m", "heading_to_next_deg"]},
                     "status": ahead["status"], "status_direction": ahead["direction"],
                     "safest_direction": safest["direction"], "views": views})
        counts[ahead["status"]] = counts.get(ahead["status"], 0) + 1
        print(f"sol {stop['sol']}: {ahead['direction']} {ahead['status']:8s} hazard {ahead['chosen_hazard']:.0%} "
              f"(straight {ahead['straight_hazard']:.0%}); views " + ", ".join(f"{v['direction']} {v['status']}" for v in views))

    meta = {
        "note": "Replay of real Curiosity drives, sols %d-%d. Terrain classes are model predictions, not ground truth."
                % (pins[0]["sol"], pins[-1]["sol"]),
        "classes": {n: [int(v) for v in COLORS[i]] for i, n in enumerate(CLASSES)},
        "hazard_classes": [CLASSES[c] for c in HAZARD],
        "thresholds": {"clear_below": CLEAR_BELOW, "blocked_above": BLOCKED_ABOVE},
        "pins": pins,
    }
    (OUT / "pins.json").write_text(json.dumps(meta, indent=1))
    n_views = sum(len(p["views"]) for p in pins)
    print(f"wrote {len(pins)} stops, {n_views} views ({skipped} views skipped: no usable ground); ahead status {counts}")


if __name__ == "__main__":
    main()
