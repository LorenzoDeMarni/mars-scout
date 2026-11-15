# mars-scout

NASA Space Apps Challenge 2026, "Interplanetary Survival Guide: Martian Map".

A Marswalk planner for Mount Sharp, Gale Crater, with a robotic scout that checks the ground ahead of the astronaut. The scout classifies terrain in rover camera photos, picks a safe path, and pins what it finds on the astronaut's map.

The scout is a replay of a real Curiosity drive, not a live feed.

## Layout

| Path | Contents |
|---|---|
| `model/` | Train and evaluate the terrain segmentation model on AI4Mars |
| `scout/` | Run the model on drive photos, pick paths, write pin images and `pins.json` |
| `docs/` | Static Leaflet map page, served by GitHub Pages |
| `docs/data/` | `pins.json` and overlay images the page reads |
| `submission/` | Project page text and demo script |
| `data/` | Downloaded datasets (gitignored) |
| `AI_LOG.md` | Log of AI-generated work, for the AI-use disclosure |

See [PLAN.md](PLAN.md) for the schedule and cut order.

## Setup

```bash
uv sync
```
