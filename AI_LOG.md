# AI use log

Kept for the Space Apps AI-use disclosure. One line per thing an AI tool produced.

| Date | Tool | What it produced |
|---|---|---|
| 2026-11-14 | Claude (chat) | Project concept and brief |
| 2026-11-14 | Claude Code | Repo scaffold: folder structure, README, pyproject.toml, .gitignore, this log |
| 2026-11-15 | Claude Code | PLAN.md schedule; `model/preview_samples.py` (exports sample photos with colored label masks) |
| 2026-11-15 | Claude Code | Terrain model code: `model/common.py`, `prepare_data.py`, `train.py`, `evaluate.py`; ran data preparation and training |
| 2026-11-15 | Claude Code | Chose the drive (sols 4647–4711, boxwork ridges); `scout/fetch_drive.py` (downloads one navigation camera photo per rover stop) |
| 2026-11-15 | Claude Code | `scout/run_scout.py` (terrain overlay, candidate path scoring, pin status, `pins.json`) and `scout/photo_masks.json` (hand-set rover hardware masks) |
| 2026-11-15 | Claude Code | `scout/build_route.py` (route, walk-back times, REMS weather per stop); the map page `docs/index.html`, `style.css`, `app.js` |
| 2026-11-15 | Claude Code | `scout/classic_cv.py` (non-ML rock and smooth-ground detector) and its cross-check in `run_scout.py`; environment section, charts (`docs/charts.js`) and radiation figures on the page |
| 2026-11-15 | Claude Code | Rover class added to the model and retrained; scout extended to 60 stops and four directions (`fetch_drive.py`, `run_scout.py` rewritten); `scout/fetch_dem.py` and `scout/terrain_hazards.py` (slope and drop-off hazards from the HiRISE elevation model); matching page changes |
| 2026-11-15 | Claude Code | Page redesigned for presentation: welcome screen, guided 30-second tour, play-the-walk timeline, tabbed panel, model report card (`docs/index.html`, `style.css`, `app.js`); demo video `docs/demo.mp4` assembled from screenshots of the tour; `README.md` and `submission/PROJECT_PAGE.md` text |
| 2026-11-15 | Claude Code | Demo slides: `slides/build.py`, the seven slide images, `slides/mars-scout-demo.pptx` and `slides/walk.mp4` (all assembled from NASA photos and screenshots of the site; no AI-generated imagery) |
| 2026-11-15 | Claude Code | Renamed to Scout Ahead; README rewritten with screenshots (`docs/img/`, taken from the site and NASA photos); fix for false rover patches in `scout/run_scout.py` |
