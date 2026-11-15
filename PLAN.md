# Plan

Deadline: Sunday, November 15, 2026, 11:59 PM Eastern. Target finish: 8 PM.

## Schedule

### Saturday night

| Time (ET) | Work |
|---|---|
| 7:30–8:30 PM | Install dependencies, download the AI4Mars Curiosity subset, inspect mask encoding and the expert-labeled test split |
| 8:30–10:00 PM | Write `model/train.py`, run a short training pass to prove the loop works, then start the real run |
| 10:00–11:30 PM | While it trains: pick the Curiosity drive, collect about 15 navigation camera photos with positions, verify the Mars Trek tile URL |
| 11:30 PM–12:30 AM | Evaluate on the expert test set and record the accuracy number. Leave a longer run going overnight if useful |

### Sunday

| Time (ET) | Work |
|---|---|
| 9:00–11:00 AM | `scout/`: path picking, overlay images, `pins.json` |
| 11:00 AM–1:00 PM | `docs/`: Leaflet map, pins, click to see photo with overlay |
| 1:00–2:00 PM | Route to 2–3 science stops with distance and walking time |
| 2:00–3:30 PM | Re-route moment and safety panel |
| 3:30–4:30 PM | Push to GitHub, enable Pages, add the honesty notes, finish the README |
| 4:30–6:30 PM | Demo video, project page text, AI log |
| 6:30–8:00 PM | Buffer, then submit |

## Cut order if behind

1. Nice-to-haves (slope layer, live space weather alerts, globe zoom). Not scheduled at all.
2. Safety panel becomes static values with their sources and dates, no data fetching.
3. Drop the re-route moment.
4. Reduce pins from 15 to 8.
5. Shorten training and report the lower accuracy number honestly.

Never cut: the public link, the demo video, the project page text.

## Data sources to verify before use

- AI4Mars Curiosity subset on Hugging Face (`hassanjbara/AI4MARS`, a third-party re-upload; check mask encoding and license against the NASA release)
- Mars Trek orbital basemap tiles
- Curiosity navigation camera photos and per-sol rover positions
- Curiosity REMS weather, RAD radiation, NASA DONKI alerts
