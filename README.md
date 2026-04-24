# Fuel Route Planner

A Django REST API that plans the most cost-effective fuel stops for a road trip anywhere within the USA. Given a start and end city, it returns the optimal gas stations to stop at along the route — minimising fuel spend based on real price data — along with the total estimated fuel cost for the journey.

---

## How it works
 
1. **Geocoding** — start and end cities (e.g. `Chicago, IL`) are resolved to coordinates using a local CSV database. Zero external API calls.
2. **Routing** — a single call to the [OpenRouteService](https://openrouteservice.org/) API returns the road polyline and total distance in miles.
3. **Fuel stop optimisation** — the route is walked in 400-mile windows. At each window, the cheapest gas station within 50 miles of the road is selected from a pre-loaded KD-Tree index of ~8,000 US stations. The station is then snapped to the nearest point on the route polyline to determine the real mile marker of the stop. Pure Python, zero extra API calls.
4. **Cost calculation** — assumes a 500-mile tank range and 10 mpg. Fills a **full tank (50 gallons) at every stop**, so the truck always leaves each station with maximum range and arrives at the destination ready to drive again immediately.
**Result:** one ORS API call per unique route, everything else runs locally in memory.

---

## Features
 
- Optimal fuel stops based on real US gas price data
- 500-mile tank range with configurable MPG
- Full tank fill at every stop — truck never risks running dry between stops
- Accurate mile markers — each stop is snapped to the nearest point on the actual route polyline, not the window boundary
- Total fuel cost estimate for the full journey
- Per-stop breakdown: station name, address, price per gallon, gallons purchased, stop cost
- Route caching — repeated requests for the same route skip the ORS call entirely
- Clean web UI for manual testing
- REST API for programmatic access
- Dockerised for one-command setup
---
 

## Quick start with Docker

### 1. Clone the repo

```bash
git clone https://github.com/rahul-08-11/fuel-router-planner
cd fuel-router-planner
```

### 2. Set up environment variables

```bash
cp .env.example .env
```

Open `.env` and add your OpenRouteService API key:

```env
ORS_API_KEY=your_openrouteservice_api_key_here
SECRET_KEY=your_django_secret_key_here
DEBUG=True
```

Get a free ORS API key at [openrouteservice.org](https://openrouteservice.org/dev/#/signup) — no credit card required.

### 3. Build and run

```bash
docker-compose up --build
```

The app will be available at `http://localhost:8000`.

---

## Manual setup (without Docker Compose)

### Requirements

- Python 3.12+
- pip

### Steps

```bash
# 1. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up environment variables
cp .env.example .env
# Edit .env and add your ORS_API_KEY

# 4. Run migrations
python manage.py migrate

# 5. Start the server
python manage.py runserver
```

---

## API reference

### `POST /api/route/`

Plans the optimal fuel route between two US cities.

**Request**

```
POST /api/route/
Content-Type: application/json
```

```json
{
  "start": "Chicago, IL",
  "end": "Miami, FL"
}
```

| Field   | Type   | Required | Description                           |
|---------|--------|----------|---------------------------------------|
| `start` | string | Yes      | Starting city in `City, ST` format    |
| `end`   | string | Yes      | Destination city in `City, ST` format |

**Response `200 OK`**

```json
{
    "start": "Chicago, IL",
    "end": "Miami, FL",
    "total_distance_miles": 1380.6,
    "total_fuel_cost_usd": 418.1,
    "starting_fuel_cost_usd": 148.73,
    "mpg": 10,
    "fuel_stops": [
        {
            "stop_number": 1,
            "name": "Circle K #4703975",
            "address": "SR-109 & US-70",
            "city": "Lebanon",
            "state": "TN",
            "lat": 36.204,
            "lon": -86.3481,
            "mile_marker": 486.2,
            "price_per_gallon": 2.872,
            "gallons_purchased": 48.62,
            "stop_cost_usd": 139.65
        },
        {
            "stop_number": 2,
            "name": "Bp",
            "address": "SR-76",
            "city": "Adel",
            "state": "GA",
            "lat": 31.1264,
            "lon": -83.4229,
            "mile_marker": 923.1,
            "price_per_gallon": 2.969,
            "gallons_purchased": 43.69,
            "stop_cost_usd": 129.72
        },
        {
            "stop_number": 3,
            "name": "4 Points Market",
            "address": "US-441/SR-7 & SR-804",
            "city": "Boynton Beach",
            "state": "FL",
            "lat": 26.5281,
            "lon": -80.0811,
            "mile_marker": 1327.1,
            "price_per_gallon": 3.229,
            "gallons_purchased": 0.0,
            "stop_cost_usd": 0.0
        }
    ]
}
```

| Field | Description |
|-------|-------------|
| `total_distance_miles` | Total road distance for the route |
| `total_fuel_cost_usd` | Total estimated fuel cost for the trip |
| `mpg` | Miles per gallon assumed (10) |
| `fuel_stops[]` | Ordered list of recommended fuel stops |
| `mile_marker` | Actual distance from start where this stop falls on the route, snapped to the nearest polyline point |
| `gallons_purchased` | Always a full tank (50 gal) — ensures the truck has maximum range leaving every stop |
| `stop_cost_usd` | Cost at this specific stop |

**Error responses**

```json
// 400 — missing or unrecognised city
{ "error": "City not found: 'Springfield'. Use format 'City, ST' e.g. 'Chicago, IL'" }

// 400 — same start and end
{ "error": "Start and end locations are the same." }

// 502 — ORS routing failed
{ "error": "Routing failed: ..." }
```

---

## Calling the API

### Using curl

```bash
curl -X POST http://localhost:8000/api/route/ \
  -H "Content-Type: application/json" \
  -d '{"start": "Chicago, IL", "end": "Los Angeles, CA"}'
```

### Using Postman

1. Open Postman and create a new request
2. Set method to `POST`
3. Set URL to `http://localhost:8000/api/route/`
4. Go to **Body** → select **raw** → set type to **JSON**
5. Paste the request body:
```json
{
  "start": "Chicago, IL",
  "end": "Los Angeles, CA"
}
```
6. Click **Send**

### Using the web UI

Navigate to `http://localhost:8000` in your browser. Enter a start and end city in `City, ST` format and click **Plan route**.

---

## Fuel stop algorithm

The optimiser walks the route in overlapping windows to decide when and where to stop:

1. **Window** — starting from the last stop (or trip start), look for stations between `FUEL_WINDOW_MILES` and `TANK_RANGE_MILES` ahead (default: 400–500 miles).
2. **Candidate search** — a KD-Tree of all ~8,000 US stations is queried for every route point inside the window. Any station within `SEARCH_RADIUS_MILES` (50 miles) of the road is a candidate.
3. **Selection** — the cheapest candidate by price per gallon is chosen. If no station is found, the search radius is doubled before giving up.
4. **Route snapping** — the chosen station is off the highway. Its mile marker is determined by finding the route polyline point closest to the station's GPS coordinates. This ensures gallons purchased and the next window both reflect the real stop position, not just the window boundary.
5. **Fill up** — a full tank (50 gallons) is purchased at every stop. This guarantees the truck can always reach the next stop (400-mile window, 500-mile tank = 100-mile buffer) and arrives at the destination ready to drive again immediately.

---

## Configuration

All tuneable parameters live in `config/settings.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `TANK_RANGE_MILES` | `500` | Maximum range on a full tank |
| `FUEL_WINDOW_MILES` | `400` | Distance before starting to look for next stop |
| `SEARCH_RADIUS_MILES` | `50` | How far off-route to search for stations |
| `MPG` | `10` | Assumed fuel efficiency |
| `EARTH_RADIUS_MILES` | `3958.8` | Used for haversine distance calculation |

The 100-mile buffer between `FUEL_WINDOW_MILES` and `TANK_RANGE_MILES` is intentional — it ensures the truck can always reach a station even when the next cheapest option falls near the far end of the window.

---

## Example routes

| Route | Distance | Stops | Est. Cost |
|-------|----------|-------|-----------|
| Chicago, IL → Los Angeles, CA | 2,026 mi | 4 | ~$472.33 |
| Chicago, IL → Miami, FL | 1,280 mi | 2 | ~$269.37 |
| Seattle, WA → Houston, TX | 2,426 mi | 5 | ~$597.07 |