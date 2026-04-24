from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

import requests
import pandas as pd
from django.conf import settings

from .data_loader import get_fuel_data, geocode_from_csv
from .route_optimizer import compute_fuel_stops


ORS_DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"


# ── Page view ────────────────────────────────────────────────────────────────

def index(request):
    """Serve the fuel route planner UI."""
    return render(request, "fuel_route/index.html")


def get_route(start_coords, end_coords, api_key):
    """Single ORS call — returns road polyline and distance in miles."""
    payload = {
        "coordinates": [start_coords, end_coords],
        "instructions": False,
        "geometry_simplify": False,
    }
    headers = {"Authorization": api_key, "Content-Type": "application/json"}
    resp = requests.post(ORS_DIRECTIONS_URL, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()

    feature = resp.json()["features"][0]
    polyline = feature["geometry"]["coordinates"]
    distance_miles = feature["properties"]["summary"]["distance"] / 1609.344
    return polyline, distance_miles


# ── API view ──────────────────────────────────────────────────────────────────

class RouteView(APIView):
    """
    POST /api/route/
    Body: { "start": "Chicago, IL", "end": "Los Angeles, CA" }

    Returns a human-readable breakdown of fuel stops with costs.
    """

    def post(self, request):
        start = request.data.get("start", "").strip()
        end   = request.data.get("end", "").strip()

        if not start or not end:
            return Response(
                {"error": "Both 'start' and 'end' fields are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 1. Geocode from local CSV — zero API calls
        start_coords = geocode_from_csv(start)
        end_coords   = geocode_from_csv(end)
        

        if not start_coords:
            return Response(
                {"error": f"City not found: '{start}'. Use format 'City, ST' e.g. 'Chicago, IL'"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not end_coords:
            return Response(
                {"error": f"City not found: '{end}'. Use format 'City, ST' e.g. 'Los Angeles, CA'"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        if start_coords == end_coords:
            return Response(
                {"error": "Start and end locations are the same."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        import time
        # 2. Get route — 1 ORS API call
        try:
            t0 = time.time()
            polyline, total_miles = get_route(start_coords, end_coords, settings.ORS_API_KEY)
            print(f"ORS routing took {time.time() - t0:.2f} seconds")
        except Exception as e:
            return Response(
                {"error": f"Routing failed: {str(e)}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # 3. Load fuel stations — zero API calls
        stations, kdtree = get_fuel_data()

        # 4. Compute optimal fuel stops — pure Python
        fuel_stops, distance_miles, total_cost, starting_fuel_cost = compute_fuel_stops(polyline, stations, kdtree)
        return Response({
            "start": start,
            "end": end,
            "total_distance_miles": round(distance_miles, 1),
            "total_fuel_cost_usd": round(total_cost, 2),
            "starting_fuel_cost_usd": round(starting_fuel_cost, 2),
            "mpg": settings.MPG,
            "fuel_stops": [
                {
                    "stop_number":        i + 1,
                    "name":               stop["name"],
                    "address":            stop.get("address", ""),
                    "city":               stop["city"],
                    "state":              stop["state"],
                    "lat":                stop["lat"],
                    "lon":                stop["lon"],
                    "mile_marker":        round(stop["mile_marker"], 1),
                    "price_per_gallon":   round(stop["price_per_gallon"], 3),
                    "gallons_purchased":  round(stop["gallons_purchased"], 2),
                    "stop_cost_usd":      round(stop["stop_cost_usd"], 2),
                }
                for i, stop in enumerate(fuel_stops)
            ],
        })