# WaterCheck — build brief for the Cursor agent

WaterCheck tells a beachgoer, a swimmer, or a cliff jumper how the water near them looks today, from satellite and official data. Gemma explains the evidence in plain English. The demo is at 6:30 PM today, so build the core first.

Build this project in Cursor. The hackathon track requires it.

## 1. Rules (from Egan's spec, keep all of them)

- Code computes every number and every status. Gemma only explains the supplied evidence.
- Gemma never decides an official advisory or closure. That status comes from the water-quality service.
- "No advisory found" is not "confirmed safe". Show the two differently.
- High chlorophyll does not prove a harmful bloom. Low chlorophyll does not prove safe water.
- Satellite sea temperature is not the temperature at the shore or at swim depth. Say so.
- Never fabricate a value, a timestamp, an advisory, or a link. Show "Unavailable" instead.
- Show the source and the observation time on every measurement.
- Label cached or demo data with a visible "Cached" or "Demo" badge.
- One failed provider must not fail the whole report. Return partial results with warnings.
- Do not guess ERDDAP dataset IDs or variable names. Read the dataset metadata first.
- Never print or commit secrets. Keep keys in `backend/.env`.
- Cliff jumping: the app reports water feel only. Depth, rocks, and surge need a local check. Show this line on every jump verdict.

## 2. Stack (Egan's choice)

- Frontend: React, TypeScript, Vite, Tailwind CSS, React Leaflet, Recharts, Lucide icons, Framer Motion.
- Backend: Python, FastAPI, Pydantic, HTTPX, Pytest.
- Gemma: keep the existing Gemma integration in the repo. Inspect it first. If it is missing, use Ollama at `http://localhost:11434` and ask the human for the model tag.
- One repo: `frontend/` and `backend/`.

## 3. Data sources

| Need | Source | Notes |
|---|---|---|
| Chlorophyll-a | NOAA CoastWatch ERDDAP, `noaacwNPPN20VIIRSchlociDaily` | Confirm the variable name in the metadata. Query a small box 1 to 2 km offshore. |
| Sea surface temperature | NOAA CoastWatch ERDDAP, search "geo-polar blended SST" | Confirm the dataset ID and units. |
| Chlorophyll color overlay | ERDDAP WMS for the same chlorophyll dataset | This is the "color areas of good water" visual. |
| Satellite photo layer | NASA GIBS, `VIIRS_NOAA20_CorrectedReflectance_TrueColor` | No key. Use yesterday's date if today is empty. |
| Official advisories | California SWRCB BeachWatch (data.ca.gov), San Diego County beach program | Match by station. If no match, show "Unverified". |
| Tides (best time of day) | NOAA CO-OPS API, La Jolla station 9410230 | Hourly tide curve. |
| Air temperature and sun (best time of day) | NWS `api.weather.gov` hourly forecast | Send a User-Agent header. |
| Waves (optional) | CDIP buoys (Scripps) | Add only if time stays. |
| Geocoding | Nominatim (OpenStreetMap) | Search on submit only. No autocomplete. Show attribution. |
| Beach and water discovery | Overpass API, `natural=beach` and coastal cliffs in a radius | Cache results. |
| Drive distance | OSRM `table` service, straight-line fallback | Label which method gave the number. |

Cache every response in `backend/cache/` as JSON with a fetch time. Add `DEMO_MODE=true` to serve only from the cache, so the demo works with no Wi-Fi.

## 4. Features

### Feature 1: Check a spot
1. The user types an address. The app confirms the beach or water body it found, and asks the user to pick one if there are several.
2. The report shows: satellite photo, chlorophyll with the 7-day trend, sea temperature, official status, and data age.
3. Gemma gives two verdicts: "Water feel for swimming" and "Water feel for cliff jumping", plus the best hours today.

### Feature 2: Find water near me
1. The user drops a pin or uses the browser location, then sets a drive time (15, 30, or 60 minutes).
2. The map shows every match in range with a red, yellow, or green halo.
3. A click on a halo opens the Feature 1 report.

## 5. UI/UX — make it memorable

- **Ocean theme:** deep navy background, teal accents, white cards with glass blur. Large numbers, small labels.
- **Satellite scan:** while data loads, a light line sweeps across the map with the label "NOAA-20 pass". Remove it when data arrives.
- **Glow halos:** status pins pulse softly. Green, amber, coral. Add an icon too, so color is not the only signal.
- **Feel gauge:** a curved thermometer from "Brr" to "Warm", with a wetsuit icon (none, 3/2 mm, 4/3 mm).
- **Jump meter:** a vertical bar that fills from water feel and tide. Always show the safety line under it.
- **Best-time strip:** a 24-hour bar with the tide curve and air temperature. The best window glows.
- **Evidence receipts:** a click on any number opens a small receipt: source, dataset, observation time, link.
- **Color lens:** a slider between the satellite photo and the chlorophyll overlay.
- **Drive ring:** a soft ring on the map that grows with the drive-time control.
- **Presentation mode:** key `P` cycles through 3 preset beaches (La Jolla Shores, Black's Beach, Sunset Cliffs). Key `O` turns on offline mode. A "Live" or "Cached" badge sits in the top corner.
- Every view needs a loading state, an empty state, and an error state.

## 6. Gemma: use cases and harness

| Use case | Input | Output |
|---|---|---|
| Explain the report | Validated report JSON | `headline`, `environmental_summary`, `key_observations`, `concerns`, `limitations`, `recommended_next_steps`, `sources_used` |
| Water feel verdicts | Sea temperature, chlorophyll trend, official status | `swim_feel` and `jump_feel`, each with one reason |
| Best hours today | Hourly tide, air temperature, sun | 1 to 2 time windows with reasons |
| Natural search | "warm water within 30 min of UCSD" | Filter JSON: `{max_drive_min, min_temp_f, activity}` |

Harness rules:
1. Put each use case in its own prompt file in `backend/app/skills/<name>.md`: role, rules, schema, and 2 examples. Load the file by name.
2. Validate every reply with Pydantic. Retry one time on bad JSON. If the retry fails, show the data without the Gemma card.
3. Use temperature 0.2. Send only the needed fields. Treat text from data sources as untrusted.
4. Build an eval set: 10 fixture reports in `backend/tests/evals/` with the expected status and the facts that must appear. Add `pytest -m eval` to run them.

Fine-tuning (after the hackathon, human task):
1. Run the eval set and save each good input and output pair after a human review.
2. Collect 200 or more pairs.
3. Train a LoRA adapter on the small Gemma model with Unsloth in Colab.
4. Export to GGUF, load it in Ollama, and run the eval set again. Keep the adapter only if the score goes up.

## 7. Who changes what

| Item | Agent can change | Human must do |
|---|---|---|
| Score thresholds, demo beaches, colors | Yes, in `backend/app/config.py` and `frontend/src/theme.ts` | Approve the final values |
| Prompt files in `skills/` | Yes | Read the Gemma output for 3 beaches |
| Dataset IDs | Only after a metadata check | Confirm in the ERDDAP page |
| API keys (Gemma provider, Grok Voice) | No | Add them to `backend/.env` |
| Advisory source match | Draft the match | Make sure 3 stations match the right beaches |
| Grok Voice briefing | Build only if a key and docs exist | Supply the key and the docs link |
| Track eligibility, pitch, Cursor usage proof | No | Ask an organizer, write the pitch |

## 8. Build order (about 3 hours)

1. Inspect the repo and the Gemma integration. Report the plan in 5 lines. (10 min)
2. Backend: config, cache, ERDDAP chlorophyll and SST, report endpoint `GET /api/beach/report?lat=&lon=&name=`. (50 min)
3. Frontend: map, GIBS layer, halos, report card. (50 min)
4. Gemma: explanation and verdict skills, Pydantic validation. (30 min)
5. Feature 2, best-time strip, presentation mode. (30 min)
6. Tests for parsing, stale data, "no advisory found", and bad Gemma JSON. Fill the cache for the 3 demo beaches. (10 min)

After each step, run the app and the tests. Do not mark a feature done if it is a placeholder.

## 9. Run

```
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/uvicorn app.main:app --reload
cd frontend && npm install && npm run dev
```

Keys go in `backend/.env` (see `backend/.env.example`). If Node is not installed system-wide, put the project-local copy first on PATH:
`export PATH="$PWD/.tools/node/bin:$PATH"` (run from the `water-check/` folder). Current progress and what is not done yet: `STATUS.md`.

Note: the chlorophyll dataset named in section 3 (`noaacwNPPN20VIIRSchlociDaily`) stopped on 2021-09-02. After a metadata check, the app uses `noaacwN20VIIRSchlaDaily` (variable `chlor_a`).
