"""Second opinion on the terrain, with no machine learning.

Two classical image-processing checks on the greyscale photo:

1. Rocks, from shadows. A rock standing above the ground casts a compact dark shadow.
   A black-hat filter picks out dark spots smaller than a set size, thin cracks are
   removed, and the remaining blobs are outlined as contours. Each blob is grown a
   little to cover the rock next to its shadow.
2. Smooth ground, from edges. Sand and dust are low in texture. The local average of
   edge strength (Sobel gradient) is thresholded to find smooth patches.

Sizes scale with the row in the image, because things near the camera look bigger.
"""
import cv2
import numpy as np

MIN_ROCK_AREA = 90  # px at the bottom of a 512 px photo; shrinks with distance
SHADOW_SIGMA = 2.2  # how much darker than typical a shadow must be
SMOOTH_FRACTION = 0.52  # smooth = edge strength below this fraction of the photo's median


def analyze(grey, valid, far):
    """grey: uint8 (H, W). valid: bool mask of ground to judge. far: top row of that ground (0-1).

    Returns rock mask, smooth mask, and the list of rock contours.
    """
    h, w = grey.shape
    img = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(grey)
    img = cv2.GaussianBlur(img, (5, 5), 0)

    # perspective: 1.0 at the bottom row, about 0.3 at the far row
    rows = np.arange(h) / h
    scale = np.clip(0.3 + 0.7 * (rows - far) / max(1 - far, 1e-6), 0.3, 1.0)

    # --- rocks from shadows ---
    blackhat = cv2.morphologyEx(img, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (41, 41)))
    level = blackhat[valid].mean() + SHADOW_SIGMA * blackhat[valid].std()
    shadows = ((blackhat > max(level, 25)) & valid).astype(np.uint8) * 255
    # opening removes thin cracks between bedrock plates, which are not obstacles
    shadows = cv2.morphologyEx(shadows, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    contours, _ = cv2.findContours(shadows, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    rocks = np.zeros((h, w), np.uint8)
    kept = []
    for c in contours:
        area = cv2.contourArea(c)
        x, y, bw, bh = cv2.boundingRect(c)
        s = scale[min(y + bh, h - 1)]
        if area < MIN_ROCK_AREA * s * s or area > 0.05 * h * w:
            continue
        if area / max(cv2.contourArea(cv2.convexHull(c)), 1) < 0.5:
            continue  # ragged shape: more likely a crack network than a shadow
        if max(bw, bh) / max(min(bw, bh), 1) > 4:
            continue  # long and thin
        kept.append(c)
        cv2.drawContours(rocks, [cv2.convexHull(c)], -1, 255, -1)
    grow = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    rock_mask = (cv2.dilate(rocks, grow) > 0) & valid

    # --- smooth ground from edge strength ---
    gx = cv2.Sobel(img, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(img, cv2.CV_32F, 0, 1, ksize=3)
    edges = cv2.blur(cv2.magnitude(gx, gy), (21, 21))
    # distant ground looks finer, so compare each row with its own expected texture
    edges = edges / scale[:, None] ** 0.5
    smooth = ((edges < SMOOTH_FRACTION * np.median(edges[valid])) & valid).astype(np.uint8) * 255
    smooth = cv2.morphologyEx(smooth, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25)))
    smooth_mask = (smooth > 0) & ~rock_mask

    return rock_mask, smooth_mask, kept


def draw(base_rgb, rock_mask, smooth_mask, contours, valid):
    """Overlay for the map: smooth ground tinted cyan, rocks outlined in magenta."""
    out = base_rgb.astype(np.float32).copy()
    out[smooth_mask] = 0.6 * out[smooth_mask] + 0.4 * np.array([60, 210, 230], np.float32)
    out[rock_mask] = 0.65 * out[rock_mask] + 0.35 * np.array([255, 60, 200], np.float32)
    out[~valid] *= 0.45
    out = np.ascontiguousarray(out.astype(np.uint8))
    cv2.drawContours(out, contours, -1, (255, 60, 200), 2)
    return out
