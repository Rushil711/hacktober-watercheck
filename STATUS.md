# WaterCheck status (rough draft, 2026-10-25 4:15 PM PT)

## Done and verified

- **Backend starts and serves live data.** `uvicorn app.main:app` on http://127.0.0.1:8000; `GET /api/health` returns ok. Ruff lint passes.
- **Frontend compiles.** `tsc -b`, `eslint .`, and `vite build` all pass. Dev server on http://127.0.0.1:5173 proxies `/api` to the backend (checked with curl through the proxy).
- **Feature 1 report, live, rendered in headless Chrome** for La Jolla Shores and Black's Beach (via the deep link `/?lat=…&lon=…&name=…`). It shows:
  - Satellite photo: NASA GIBS `VIIRS_NOAA20_CorrectedReflectance_TrueColor`. The app checks today's tile and falls back to yesterday when today's is still black (it was at 3:15 PM).
  - Chlorophyll with a 7-day trend: ERDDAP `noaacwN20VIIRSchlaDaily`, `chlor_a`. Last cloud-free value near La Jolla is 2026-10-16, about 9.5 days old, and it is flagged **stale**. The trend shows "no cloud-free pixels" instead of fake zeros.
  - SST: ERDDAP `noaacwBLENDEDsstDNDaily`, `analysed_sst` in °C, converted to °F. It shows 73–74 °F with the "not shore or swim-depth temperature" caveat.
  - Official status: the live San Diego County Beach & Bay feed (sdbeachinfo). It currently shows a **general rain advisory issued 2026-10-23** for both beaches. Matched stations: EH-320 "Vallecitos" for La Jolla Shores (0.09 km) and FM-090 "Black's Beach" (0.18 km).
  - Data age, Cached badges, partial-data warnings, halo, water-feel gauge, jump meter with the safety line, and the best-time strip (NOAA CO-OPS 9410230 tides plus NWS hourly).
  - Evidence receipts are attached to every number (source, dataset, observed time, fetched time, link). The popover renders, but the click was not exercised by automation.
- **Search and beach picker.** `GET /api/search?q=La Jolla Shores` returns the Nominatim place plus nearby OpenStreetMap beaches. Tested through the Vite proxy; the click-through was not automated.
- **Gemma card (hosted Gemma 4 `gemma-4-26b-a4b-it` via the Gemini API, the same integration as the old `server.py`).** Explanation, swim/jump verdicts, and best-hours reasons were generated live and validated with Pydantic. Checks: one retry on bad output, numbers must appear in the evidence, levels and labels must match the code's, and "safe" claims are rejected. On failure the card is hidden and the data stays.
- **Tests:** `pytest` passes 11 tests: ERDDAP metadata and grid parsing, stale data, missing data shown as "Unavailable", "no advisory found" vs. unverified, old BeachWatch records shown as unverified, bad Gemma JSON with retry then fallback, invented-number rejection, safe-claim rule, and unicode grounding.
- **Key handling:** `backend/.env` is gitignored and was only appended to (missing variable names). No key values were written or printed. `XAI_API_KEY` loads and passes the format check (starts with `xai-`, no brackets or quotes).

## Not completed

- **Feature 2, Find water near me:** backend `/api/nearby` (Overpass + OSRM + regional grids) and `NearbyPanel` are written but not verified. The UI shows "Near me (coming soon)" as disabled (`frontend/src/features.ts` → `nearMe`).
- **Gemma natural search** ("warm water within 30 min of UCSD"): `/api/gemma/search` is written but not verified. It is part of Feature 2, so it's hidden.
- **Presentation mode (keys P and O) and the Live/Cached toggle:** code is written but turned off (`presentationKeys`). The badge always reads "Live".
- **Offline / DEMO_MODE cache fill for the 3 demo beaches:** the cache layer works (it was used on every request), but the demo beaches were not pre-filled and offline mode was not tested. The `backend/cache/` folder is gitignored.
- **Grok Voice briefing (required for the SpaceXSI track):** `/api/voice/status` and `/api/voice/briefing` (xAI `POST /v1/tts`) are built, and the key passes the format check. It has **not been called live yet**, so the button is hidden (`voice`).
- **Drive ring and halo map for Feature 2:** built inside `MapView` but only visible in Near-me mode, which is hidden.
- **Eval set** (`backend/tests/evals/`, 10 fixtures, `pytest -m eval`): the marker is configured in `pyproject.toml`, but there are no fixtures yet.
- **Chlorophyll color lens:** the slider and the WMS proxy (EPSG:4326 per tile) are built. The chlorophyll overlay was not visually verified; near La Jolla it is mostly cloud gaps.
- **Overpass is slow:** the first search for a new place took about 82 s on the public server. It is now capped at 30 s and falls back to "check this exact point". Cached searches are instant.
- **Known Gemma imprecision:** one explanation called the chlorophyll cell "5 km" (it is 4 km). This passes the number check because 5 km appears in the SST caveat.
- **Human checks from the README:** confirm the 3 station matches, approve the thresholds in `backend/app/config.py`, and read Gemma output for 3 beaches.
- **Dataset change to confirm:** the README's `noaacwNPPN20VIIRSchlociDaily` ended 2021-09-02 (variable `chl_oci`). The app uses `noaacwN20VIIRSchlaDaily` (`chlor_a`, current). Confirm on the ERDDAP page.

## How to run

Node is not installed system-wide on this Mac; a project-local Node 24 LTS is in `.tools/node` (gitignored).

```bash
# Terminal 1: backend (keys go in backend/.env: GEMINI_API_KEY and XAI_API_KEY)
cd ~/Projects/hacktober/water-check/backend
python3 -m venv .venv            # first time only
.venv/bin/pip install -r requirements.txt   # first time only
.venv/bin/uvicorn app.main:app --reload --port 8000

# Terminal 2: frontend
cd ~/Projects/hacktober/water-check/frontend
export PATH="$HOME/Projects/hacktober/water-check/.tools/node/bin:$PATH"
npm install                      # first time only
npm run dev                      # http://localhost:5173

# Checks
cd ~/Projects/hacktober/water-check/backend && .venv/bin/python -m pytest -q && .venv/bin/ruff check app tests
cd ~/Projects/hacktober/water-check/frontend && npm run typecheck && npm run lint && npm run build
```

Deep link to a report: http://localhost:5173/?lat=32.85585&lon=-117.25897&name=La%20Jolla%20Shores%20Beach
