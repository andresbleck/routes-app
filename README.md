# Weather-Aware Truck Routing

A React + Django web app that helps a truck driver pick the safest route. It compares three truck routes, samples the weather at each checkpoint for the truck's estimated arrival time, classifies the risk with the given rules and load weight, and recommends a route that balances weather risk and travel time. A heatmap shows the 0–48 h forecast along the trip corridor.

- **Live app:** _add the Vercel URL here_ · API: https://routes-app-api.onrender.com/api/health
- **Walkthrough (Loom):** _add the video link here_

## Requirements → implementation

| Requirement | How it is done |
|---|---|
| Origin, destination, departure, load weight | Form with place autocomplete (TomTom Search), date/time picker and load in lb. Validation matches the backend. |
| 3 route options from a routing API | TomTom Routing in **truck mode** (vehicle weight included) with 2 alternatives. When TomTom returns fewer than 3, the missing ones are generated through a detour waypoint (see below). |
| Weather every 10 / 25 / 50 miles at the truck's ETA | Checkpoints are placed every 10, 25 or 50 mi (automatic by trip length, or chosen by the user). Each checkpoint's ETA comes from TomTom's traffic-aware travel times. The forecast hour closest to that ETA is used. |
| Risk from the risk / load rules | Exact thresholds and load rules from the brief; a checkpoint takes the worst of wind, rain and snow. |
| Recommend the best route | Ranked by fewest Severe miles, then High miles, then average risk, then travel time. The UI explains which criterion decided. |
| Routes, checkpoints, risk, ETAs and summaries on a map | Selected route colored by risk; checkpoints with a popup (ETA, gusts, rain, snow, level, cause); alternatives in grey; one summary card per route. |
| Weather heatmap with a 0–48 h slider | Severity heatmap over a corridor around the three routes, one frame per hour. All 49 frames arrive with the plan, so the slider makes no requests. |

## How it works

### Routes
- `GET calculateRoute` with `travelMode=truck`, `vehicleWeight` (load + an assumed 35,000 lb tractor/trailer tare), `traffic=true`, `departAt` and `maxAlternatives=2`.
- TomTom sometimes returns only two routes (e.g. Dallas → Denver). Then up to four detour waypoints are tried in parallel: the midpoint of the trip moved sideways by ±15 % and ±30 % of the straight-line distance. A detour is kept only if it shares less than 80 % of its length with every other route and takes at most 1.5× the fastest route. The UI says when a route was generated this way.

### Checkpoints and ETA
- Interval: ≤ 150 mi → every 10 mi, ≤ 600 mi → every 25 mi, longer → every 50 mi. The longest route decides, so all three routes are sampled the same way. Routes are capped at 80 checkpoints; a requested interval is widened if needed, with a warning.
- Checkpoints go at 0, N, 2N… miles plus the destination. Positions are interpolated along the polyline.
- **ETA** = departure + cumulative driving time at that point. TomTom's turn-by-turn instructions give the cumulative time at many points of the route; time is interpolated by distance between them, so slow and fast stretches are reflected.
- Each checkpoint represents half the road to its neighbours (`segment_miles`). These add up exactly to the route distance and are used for "miles per risk level".

### Weather
- [Open-Meteo](https://open-meteo.com/) hourly forecast (no API key), in mph and inches, many locations per request (batches of 100, sent in parallel).
- **Wind uses gusts** (`wind_gusts_10m`), the conservative choice for high-profile vehicles. Sustained wind is shown for reference.
- **Rain** = `rain + showers` (in/hr). **Snow** = `snowfall` (in/hr). Open-Meteo's hourly precipitation is the amount over the preceding hour.
- The forecast hour closest to each checkpoint's ETA is used.

### Risk rules

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind gusts (mph) | < 25 | 25 – < 35 | 35 – < 45 | 45 – < 55 | ≥ 55 |
| Rain (in/hr) | < 0.10 | 0.10 – < 0.25 | 0.25 – < 0.50 | 0.50 – 1.00 | > 1.00 |
| Snow (in/hr) | < 0.5 | 0.5 – < 1.0 | 1.0 – < 2.0 | 2.0 – 3.0 | > 3.0 |

- The brief's ranges touch (e.g. rain 0.10–0.25 and 0.25–0.50), so **lower bounds are inclusive**. Rain and snow reach No Travel only when strictly above the top value (`> 1.00`, `> 3.0`), as written; wind at `≥ 55`.
- **Load rules** (applied to wind): 45–54 mph with **more than** 30,000 lb → No Travel; 35–44 mph with **more than** 40,000 lb → Severe; ≥ 55 mph is No Travel for any load. Exactly 30,000 / 40,000 lb does not trigger a rule.
- A checkpoint's level is the **worst** of wind (after load rules), rain and snow. The popup says which variable caused it and whether the load raised it.

### Recommendation
Routes are sorted by, in order:
1. fewest **No Travel** miles (added in front: the brief does not rank No Travel, and it is worse than Severe — without this, 10 No Travel miles would beat 11 Severe miles),
2. fewest **Severe** miles,
3. fewest **High** miles,
4. lowest **average risk** (distance-weighted, Low = 0 … No Travel = 4),
5. shortest **travel time**.

Values are rounded before comparing (miles to 0.1, average risk to 0.01, time to minutes) so floating-point noise never decides. The response says which criterion separated the first two routes, e.g. *"Recommended for fewest High miles (150 mi vs 200 mi)"*. If every route has No Travel miles, the least bad one is still shown with a warning.

### Heatmap
- **Grid:** points on a fixed lattice (0.1°, 0.2°, 0.25°, 0.5°…) inside a 30-mile corridor around the three routes, using the finest step that keeps at most 150 points. A fixed lattice means similar trips reuse the same points and their cached forecasts.
- **Value:** a continuous 0–4 severity built from the same rules: the integer part is exactly the risk level and the fraction is how far into its band the value is (e.g. 30 mph gusts → 1.5). The heatmap therefore never contradicts the checkpoints. A test checks this over 1,386 combinations.
- **Frames:** 49 hourly frames from the departure hour to +48 h, sent with the plan (~21 KB gzipped for the whole response).
- **Smoothness:** the layer is created once; moving the slider only swaps the points of the existing layer (`setLatLngs`), and the slider's state lives in a small component, so routes and cards don't re-render. The point radius is recalculated from the grid spacing on zoom so the surface stays continuous.
- `leaflet.heat` reads its canvas back on every redraw; with a GPU-backed canvas that took 100+ ms per step. Creating it with `willReadFrequently` brought it to ~10 ms.

## API

`GET /api/health` → `{"status": "ok"}`

`GET /api/geocode?q=denv` → `{"results": [{"label": "Denver, CO", "lat": 39.738453, "lon": -104.984853}, …]}`

`POST /api/trips/plan`

```json
{
  "origin": {"label": "Dallas, TX", "lat": 32.777976, "lon": -96.796215},
  "destination": {"label": "Denver, CO", "lat": 39.738453, "lon": -104.984853},
  "departure_time": "2026-10-22T22:00:00Z",
  "load_weight_lb": 42000,
  "interval_miles": "auto"
}
```

Response (abridged):

```json
{
  "interval_miles": 50,
  "departure_time": "2026-10-22T22:00:00Z",
  "load_weight_lb": 42000,
  "recommendation": {
    "route_id": "route-1",
    "decided_by": "high_miles",
    "explanation": "Recommended for fewest High miles (150 mi vs 200 mi)."
  },
  "routes": [
    {
      "id": "route-1", "rank": 1, "is_recommended": true,
      "distance_miles": 883.1, "duration_minutes": 738, "arrival_time": "2026-10-23T10:18:00Z",
      "geometry": [[32.77598, -96.79621], "…"],
      "risk_summary": {
        "miles_by_level": {"low": 391.2, "moderate": 341.4, "high": 150.5, "severe": 0, "no_travel": 0},
        "average_risk": 0.73, "max_level": "high", "has_no_travel": false
      },
      "checkpoints": [
        {
          "index": 11, "lat": 38.8, "lon": -100.3, "distance_miles": 550, "segment_miles": 50,
          "eta": "2026-10-23T07:53:00Z",
          "weather": {"forecast_time": "2026-10-23T08:00:00Z", "wind_mph": 17, "gust_mph": 35, "rain_in_hr": 0, "snow_in_hr": 0},
          "risk": {"level": "high", "score": 2, "drivers": ["wind"], "load_adjusted": false}
        }
      ]
    }
  ],
  "heatmap": {
    "start_time": "2026-10-22T22:00:00Z", "step_minutes": 60, "frame_count": 49, "grid_step_degrees": 0.5,
    "points": [[32.5, -97.0], "…"],
    "frames": [[0.12, 0.30, "…"], "…"]
  },
  "warnings": ["The routing provider returned 2 route(s); 1 more generated through a detour waypoint."]
}
```

Errors: `400` with per-field messages, `422 {"code": "no_route"}` when no truck route exists, `502 {"code": "upstream_error", "provider": …}` when TomTom or Open-Meteo fails.

## Assumptions and design decisions
- **Providers.** TomTom for routing and geocoding (truck mode with weight, real alternatives on long trips, free key without a card). OpenRouteService was ruled out because its hosted API only computes alternatives for trips under 100 km. Open-Meteo for weather. Esri World Light Gray tiles for the base map (CARTO now requires a key).
- **Continuous driving.** ETAs follow TomTom's driving time with traffic for the departure time; hours-of-service breaks and stops are not modelled.
- **Gross vs. load weight.** Routing uses load + 35,000 lb assumed tare; the risk rules use the load weight entered by the user, as the brief states.
- **US trips.** Place search is limited to the US, consistent with the miles / inches / lb units.
- **Departure window.** From 1 h ago to 7 days ahead, so the trip plus the 48 h heatmap stay within Open-Meteo's forecast range.
- **Times.** The API works in UTC; the UI shows the browser's local time.
- **Stateless backend.** No database. Forecasts are cached in memory per point for 30 minutes.
- **Open-Meteo free tier** counts every location as one call (~10,000 / day). A new search asks for the checkpoints of the three routes plus up to 150 grid points (roughly 100–300 locations); repeated or similar searches mostly hit the cache.
- **Geometry.** Polylines are simplified (~50 m tolerance) before being sent to the browser; sampling and risk use the full-resolution route.

## Project structure

```
backend/                      Django + Django REST Framework
  config/                     settings, urls, wsgi
  trips/
    domain/                   pure logic, no I/O
      risk.py                 thresholds, load rules, severity index
      sampling.py             checkpoints, intervals, ETA interpolation
      ranking.py              route summaries and recommendation
      route_geometry.py       detour points, route overlap
      heatmap_grid.py         corridor grid
    clients/                  tomtom.py, open_meteo.py (HTTP only)
    services/                 route_options.py, trip_planner.py (orchestration)
    serializers.py, views.py  request validation and endpoints
    tests/                    pytest suite (152 tests, providers mocked)
frontend/                     React + Vite + TypeScript + Tailwind + shadcn/ui
  src/
    api/                      typed client for the API contract
    hooks/                    usePlanTrip, usePlaceSearch
    components/               form, route cards, recommendation
    map/                      react-leaflet map, routes, checkpoints, heatmap, slider
    lib/                      risk colors, route segments, formatting
render.yaml                   Render Blueprint for the API (frontend on Vercel)
```

## Run locally

Requirements: Python 3.12, Node 22+, a free [TomTom API key](https://developer.tomtom.com/) with the Routing and Search APIs.

```bash
# Backend (http://localhost:8000)
cd backend
python -m venv .venv
.venv/Scripts/activate            # Windows; on macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env              # then set TOMTOM_API_KEY
python manage.py runserver 8000

# Frontend (http://localhost:5173)
cd frontend
npm install
npm run dev
```

With `DJANGO_DEBUG=true` the API can also be tried in the browser at http://localhost:8000/api/trips/plan.

## Tests

```bash
cd backend
pytest
```

152 tests cover every threshold boundary and load rule, checkpoint placement and ETA interpolation, each ranking criterion and tie-break, the detour fallback, the heatmap grid, both API clients (HTTP mocked) and the endpoints' contract, validation and errors. Frontend checks: `npm run build` (TypeScript) and `npm run lint`.

## Deploy

The API runs on **Render** and the React app on **Vercel**.

**API on Render** — the repo includes a [Render Blueprint](render.yaml).
1. **New → Blueprint**, select this repository.
2. Fill in `TOMTOM_API_KEY` and `CORS_ALLOWED_ORIGINS` (the Vercel URL, e.g. `https://routes-app.vercel.app`; several origins can be separated by commas). `DJANGO_SECRET_KEY` is generated by Render and `DJANGO_DEBUG` is `false`.
3. Check `https://<api>.onrender.com/api/health` returns `{"status": "ok"}`.

**Frontend on Vercel**
1. **Add New → Project**, import this repository and set **Root Directory** to `frontend` (Vercel detects Vite: build `npm run build`, output `dist`).
2. Add the environment variable `VITE_API_BASE_URL` = the API URL, e.g. `https://routes-app-api.onrender.com` (no trailing slash). It is read at build time, so redeploy after changing it.
3. Put the Vercel production URL in the API's `CORS_ALLOWED_ORIGINS` on Render.

On Render's free plan the API sleeps after inactivity; the first request can take ~1 minute. The app pings `/api/health` on load to wake it up early.

## Not included (by design)
Accounts, saved trips, live tracking, tolls or bridge clearances, and hours-of-service planning. The brief asks for correctness and clarity over extra features.
