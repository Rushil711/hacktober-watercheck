# WaterCheck status (rough draft, updated 2026-10-25 5:10 PM PT)

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
- **Map imagery, fixed 2026-10-25 4:20 PM.** The blur came from NASA GIBS NOAA-20 tiles, which exist only up to zoom 9 (about 250 m per pixel). Leaflet was stretching them up to zoom 18, and the opaque layer also hid the base map. Now:
  - Zoom 10–16 shows USDA/USGS orthoimagery from The National Map (`USGSImageryOnly`, public domain, no key, native up to zoom 16).
  - Zoom 9 and below shows the daily NOAA-20 pass.
  - Every layer's `maxZoom` equals its native zoom, and the map stops at zoom 16.
  - The chlorophyll WMS is remapped row by row from EPSG:4326 to Web Mercator. Checked by drawing ERDDAP's own coastline through the same code path over the imagery.
  - Checked in headless Chrome at La Jolla Shores and Sunset Cliffs at zoom 16 (coastline legible) and at zoom 9 (daily layer).
- **Search and beach picker.** `GET /api/search?q=La Jolla Shores` returns the Nominatim place plus nearby OpenStreetMap beaches. Tested through the Vite proxy. The UI no longer calls it: the Search nearby top bar replaced the single-spot search box.
- **Search nearby (Feature 2, first slice), checked in Chrome.** The top bar has "Enter a starting address", "Radius in miles" (0.5 to 25), and a **Search nearby** button. `GET /api/nearby?address=…&radius_mi=…` geocodes the address and returns the named water bodies inside the circle, nearest first, with GeoJSON outlines. Beaches, bays, and rivers come from a Nominatim category search plus `/lookup` for outlines. Lakes, reservoirs, and estuaries come from the USGS NHD waterbody layer (US only). Beaches and bays also get the halo, sea temperature, and county status. The map draws the dashed circle and highlights each water body (beaches in sand color, water in blue). A hover on a list row highlights its shape. A beach or bay opens the Feature 1 report, with "Back to N results". A lake or river zooms the map to its outline. Live results: La Jolla Shores, 5 mi: 25 water bodies in 7.5 s (16 beaches, 7 bays, 1 river, 1 estuary). Santee, 6 mi: 7 lakes, 1 reservoir, and the San Diego River.
- **Gemma card (hosted Gemma 4 `gemma-4-26b-a4b-it` via the Gemini API, the same integration as the old `server.py`).** Explanation, swim/jump verdicts, and best-hours reasons were generated live and validated with Pydantic. Checks: one retry on bad output, numbers must appear in the evidence, levels and labels must match the code's, and "safe" claims are rejected. On failure the card is hidden and the data stays.
- **Grok Voice briefing (SpaceXSI track):** `POST /api/voice/briefing` was called live against xAI `POST /v1/tts`. It returned a 31-second MP3 (MPEG layer III, 24 kHz, 128 kbps) in 3.7 s. The spoken script is built by code from the report, with Gemma's headline included only when that card passed validation. The "Play Grok Voice briefing" button shows in the report, with a native audio player as fallback. Clicking it was not automated. The briefing turns on or off as soon as `XAI_API_KEY` in `backend/.env` changes, with no restart.
- **Tests:** `pytest` passes 17 tests: the water-body merge (5 tests in `tests/test_water.py`), the chlorophyll tile remap, ERDDAP metadata and grid parsing, stale data, missing data shown as "Unavailable", "no advisory found" vs. unverified, old BeachWatch records shown as unverified, bad Gemma JSON with retry then fallback, invented-number rejection, safe-claim rule, and unicode grounding.
- **Key handling:** `backend/.env` is gitignored and was only appended to (missing variable names). No key values were written or printed. `XAI_API_KEY` loads and passes the format check (starts with `xai-`, no brackets or quotes).

## Not completed

- **Search nearby, open items:**
  - Overpass was at capacity on 2026-10-25 (HTTP 502 and timeouts on 3 public servers). For this reason, Search nearby uses Nominatim and USGS NHD. OSRM drive times were removed.
  - A cold USGS NHD query takes 9 to 40 s (the timeout is 45 s). A warm or cached query takes less than 1 s. On a timeout, the panel shows "Lakes and reservoirs unavailable".
  - Nominatim returns at most 40 results for each category. A large radius in a dense area can miss beaches. The panel shows a warning when a category hits the limit.
  - Cliffs are not in the results, because they are not water bodies. The ocean report covers beaches and bays only. Lakes and rivers have no water-quality data yet.
  - At high zoom the satellite photo is blurry (GIBS max zoom 9), and it hides the street map under the outlines.
  - The "Use my location" button and the Ask Gemma box were removed from the panel.
- **Gemma natural search** ("warm water within 30 min of UCSD"): `/api/gemma/search` is written but not verified, and the UI does not call it. It now turns the drive time into a straight-line radius (0.8 km per minute). Its `jump` filter finds nothing, because the results do not include cliffs.
- **Presentation mode (keys P and O) and the Live/Cached toggle:** code is written but turned off (`presentationKeys`). The badge always reads "Live".
- **Offline / DEMO_MODE cache fill for the 3 demo beaches:** the cache layer works (it was used on every request), but the demo beaches were not pre-filled and offline mode was not tested. The `backend/cache/` folder is gitignored.
- **Eval set** (`backend/tests/evals/`, 10 fixtures, `pytest -m eval`): the marker is configured in `pyproject.toml`, but there are no fixtures yet.
- **Chlorophyll color lens:** the slider and the WMS proxy (EPSG:4326 per tile) are built. The chlorophyll overlay was not visually verified; near La Jolla it is mostly cloud gaps.
- **Detail imagery limits:** USGS orthoimagery covers the US only; elsewhere the dark map shows at zoom 10+. It ends a few km offshore, where the service returns black. It is aerial imagery last refreshed June 2024, not same-day; the on-map legend says so. Same-day imagery is only the zoom ≤ 9 NOAA-20 layer.
- **Overpass is slow (`/api/search` only):** the first search for a new place took about 82 s on the public server. It is now capped at 30 s and falls back to "check this exact point". Cached searches are instant.
- **Known Gemma imprecision:** one explanation called the chlorophyll cell "5 km" (it is 4 km). This passes the number check because 5 km appears in the SST caveat.
- **Human checks from the README:** confirm the 3 station matches (La Jolla Shores → EH-320 "Vallecitos" 0.09 km, Black's Beach → FM-090 0.18 km, Sunset Cliffs → PL-070 "Ladera Street" 0.72 km), approve the thresholds in `backend/app/config.py`, and read Gemma output for 3 beaches.
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
