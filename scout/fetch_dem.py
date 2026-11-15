"""Download the part of NASA's 1 m HiRISE elevation model that covers the walk area.

Usage: uv run python scout/fetch_dem.py   (after fetch_drive.py)
Source: MSL Gale DEM Mosaic, 1 m/pixel, from HiRISE stereo pairs (USGS Astrogeology / NASA PDS).
The full file is 3.9 GB, so only a window around the scouted stops is read over HTTP.

Writes data/dem/walk_area.npy (elevation in metres) and data/dem/walk_area.json (its bounds).
"""
import json
import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.env import Env
from rasterio.windows import Window, from_bounds

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/dem"
# planetarymaps.usgs.gov/mosaic/Mars/MSL/MSL_Gale_DEM_Mosaic_1m_v3.tif redirects here
URL = "/vsicurl/https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/Mars/MSL/MSL_Gale_DEM_Mosaic_1m_v3.tif"
CHUNK_ROWS = 40
MARS_RADIUS_M = 3_396_190  # the DEM's map projection is x = R * lon, y = R * lat on this sphere
MARGIN_M = 150


def main():
    stops = json.loads((ROOT / "data/curiosity/drive/stops.json").read_text())
    xs = [math.radians(s["lon"]) * MARS_RADIUS_M for s in stops]
    ys = [math.radians(s["lat"]) * MARS_RADIUS_M for s in stops]
    left, right = min(xs) - MARGIN_M, max(xs) + MARGIN_M
    bottom, top = min(ys) - MARGIN_M, max(ys) + MARGIN_M

    OUT.mkdir(parents=True, exist_ok=True)
    with Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
             GDAL_HTTP_TIMEOUT="60", GDAL_HTTP_MAX_RETRY="5"):
        with rasterio.open(URL) as ds:
            window = from_bounds(left, bottom, right, top, ds.transform).round_offsets().round_lengths()
            print(f"reading {int(window.width)} x {int(window.height)} pixels at {ds.res[0]} m", flush=True)
            # read a few rows at a time and retry: long reads over HTTP sometimes fail part-way
            parts = []
            for row in range(0, int(window.height), CHUNK_ROWS):
                part = Window(window.col_off, window.row_off + row, window.width,
                              min(CHUNK_ROWS, int(window.height) - row))
                for attempt in range(5):
                    try:
                        parts.append(ds.read(1, window=part))
                        break
                    except rasterio.errors.RasterioIOError:
                        if attempt == 4:
                            raise
                print(f"rows {row + part.height}/{int(window.height)}", flush=True)
            dem = np.vstack(parts).astype(np.float32)
            dem[dem == ds.nodata] = np.nan
            b = ds.window_bounds(window)

    np.save(OUT / "walk_area.npy", dem)
    deg = lambda m: math.degrees(m / MARS_RADIUS_M)  # noqa: E731
    meta = {"west": deg(b[0]), "south": deg(b[1]), "east": deg(b[2]), "north": deg(b[3]),
            "pixel_m": 1.0, "shape": list(dem.shape),
            "source": "MSL Gale DEM Mosaic 1 m v3 (HiRISE stereo), USGS Astrogeology Science Center"}
    (OUT / "walk_area.json").write_text(json.dumps(meta, indent=1))
    print(f"elevation {np.nanmin(dem):.1f} to {np.nanmax(dem):.1f} m, {np.isnan(dem).mean():.1%} missing")


if __name__ == "__main__":
    main()
