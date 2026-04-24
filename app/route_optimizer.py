import math
import numpy as np
from django.conf import settings


def haversine_miles(lat1, lon1, lat2, lon2):
    """Straight-line distance in miles between two GPS points."""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * settings.EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def polyline_to_mile_markers(polyline):
    """
    Convert a list of [lon, lat] coords (ORS format) to
    cumulative mile markers: [(miles, lat, lon), ...].
    """
    markers = [(0.0, polyline[0][1], polyline[0][0])]
    total = 0.0
    for i in range(1, len(polyline)):
        prev, curr = polyline[i - 1], polyline[i]
        total += haversine_miles(prev[1], prev[0], curr[1], curr[0])
        markers.append((total, curr[1], curr[0]))
    return markers


def find_cheapest_station(route_segment, stations, kdtree, radius_miles):
    """
    Return the cheapest station within radius_miles of any point in route_segment.
    Returns None if no station is found.
    """
    search_radius_rad = radius_miles / settings.EARTH_RADIUS_MILES
    candidate_indices = set()

    for _, lat, lon in route_segment:
        hits = kdtree.query_ball_point(np.radians([lat, lon]), search_radius_rad)
        candidate_indices.update(hits)

    if not candidate_indices:
        return None

    return min((stations[i] for i in candidate_indices), key=lambda s: s["price"])


def _closest_route_mile(station, segment):
    """
    Return the cumulative mile value of the route point in segment
    that is geographically closest to the given station.
    This pins the station onto the route so gallons and advancement
    are based on where we actually stop, not the window boundary.
    """
    return min(
        segment,
        key=lambda p: haversine_miles(p[1], p[2], station["lat"], station["lon"])
    )[0]
def compute_fuel_stops(polyline, stations, kdtree):
    mile_markers = polyline_to_mile_markers(polyline)
    total_miles = mile_markers[-1][0]

    fuel_stops = []
    last_stop_mile = 0.0
    total_cost = 0.0
    tank_level_miles = settings.TANK_RANGE_MILES  # start full

    # ── Cost of fuel already in the tank at departure ──────────────────
    # The truck starts full. That fuel was bought near the origin.
    # We charge for however much of it gets consumed before the first stop
    # (or the whole trip if no stops). We price it at the cheapest station
    # near the start of the route.
    start_segment = mile_markers[:max(1, len(mile_markers) // 10)]  # first 10% of route
    start_station = (
        find_cheapest_station(start_segment, stations, kdtree, settings.SEARCH_RADIUS_MILES)
        or find_cheapest_station(start_segment, stations, kdtree, settings.SEARCH_RADIUS_MILES * 2)
    )
    start_price = start_station["price"] if start_station else 4.0

    while True:
        window_start = last_stop_mile + settings.FUEL_WINDOW_MILES
        window_end   = last_stop_mile + settings.TANK_RANGE_MILES

        if window_start >= total_miles:
            break

        is_last_stop = (window_start + settings.FUEL_WINDOW_MILES) >= total_miles

        segment = [
            (m, lat, lon)
            for m, lat, lon in mile_markers
            if window_start <= m <= window_end
        ]

        if not segment:
            break

        station = (
            find_cheapest_station(segment, stations, kdtree, settings.SEARCH_RADIUS_MILES)
            or find_cheapest_station(segment, stations, kdtree, settings.SEARCH_RADIUS_MILES * 2)
        )

        if not station:
            last_stop_mile = segment[len(segment) // 2][0]
            continue

        actual_stop_mile = _closest_route_mile(station, segment)
        miles_driven     = actual_stop_mile - last_stop_mile
        tank_level_miles -= miles_driven

        if is_last_stop:
            miles_to_dest  = total_miles - actual_stop_mile
            gallons_needed = (miles_to_dest - tank_level_miles) / settings.MPG
            gallons        = max(0.0, round(gallons_needed, 2))
        else:
            gallons_needed   = (settings.TANK_RANGE_MILES - tank_level_miles) / settings.MPG
            gallons          = round(gallons_needed, 2)
            tank_level_miles = settings.TANK_RANGE_MILES  # topped up to full

        stop_cost   = round(gallons * station["price"], 2)
        total_cost += stop_cost

        fuel_stops.append({
            "name":              station["name"],
            "address":           station["address"],
            "city":              station["city"],
            "state":             station["state"],
            "lat":               station["lat"],
            "lon":               station["lon"],
            "price_per_gallon":  station["price"],
            "gallons_purchased": round(gallons, 2),
            "stop_cost_usd":     stop_cost,
            "mile_marker":       round(actual_stop_mile, 1),
            "full_tank_fill":    not is_last_stop,
        })

        last_stop_mile = actual_stop_mile

    # ── Charge for starting tank fuel consumed ──────────────────────────
    # if fuel_stops:
    #     # Miles driven on starting tank = distance to first stop
    #     starting_miles_used = fuel_stops[0]["mile_marker"]
    # else:
    #     # No stops — entire trip ran on starting tank
    #     starting_miles_used = total_miles

    # at the very end, before return
    starting_gallons_used = (fuel_stops[0]["mile_marker"] if fuel_stops else total_miles) / settings.MPG
    starting_cost = round(starting_gallons_used * start_price, 2)
    total_cost += starting_cost

    return fuel_stops, round(total_miles, 1), round(total_cost, 2), starting_cost