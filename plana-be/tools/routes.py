import os
import math
import logging
from typing import Any, Dict, List, Optional
import httpx
from langsmith import traceable

logger = logging.getLogger(__name__)

def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate distance in kilometers between two points."""
    R = 6371.0  # Earth's radius in km
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def calculate_mock_route(lat1: float, lng1: float, lat2: float, lng2: float, mode: str) -> Dict[str, Any]:
    """Calculate distance and duration using a dynamic routing model based on coordinates."""
    dist_km = haversine_distance(lat1, lng1, lat2, lng2)
    circuity = 1.3
    actual_dist_km = dist_km * circuity
    
    if mode == "walking":
        speed_kmh = 4.5
        duration_sec = (actual_dist_km / speed_kmh) * 3600
    elif mode == "transit":
        speed_kmh = 16.0
        duration_sec = (actual_dist_km / speed_kmh) * 3600 + 360
    else:  # driving
        speed_kmh = 24.0
        duration_sec = (actual_dist_km / speed_kmh) * 3600 + 120

    if duration_sec < 60:
        duration_sec = 60
        
    return {
        "distance_meters": int(actual_dist_km * 1000),
        "duration_seconds": int(duration_sec),
        "mode": mode
    }

@traceable
async def get_route(
    origin: Dict[str, float],
    destination: Dict[str, float],
    mode: str = "walking",
    departure_time: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculate a route using Google Routes API.
    """
    api_key = os.getenv("GOOGLE_MAPS_SERVER_KEY")
    if api_key:
        logger.info("Executing real Google Routes calculation for: %s -> %s (%s)", origin, destination, mode)
        url = "https://routes.googleapis.com/directions/v2:computeRoutes"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "routes.distanceMeters,routes.duration"
        }
        payload = {
            "origin": {"location": {"latLng": {"latitude": origin["lat"], "longitude": origin["lng"]}}},
            "destination": {"location": {"latLng": {"latitude": destination["lat"], "longitude": destination["lng"]}}},
            "travelMode": mode.upper() if mode != "transit" else "TRANSIT",
            "routingPreference": "TRAFFIC_AWARE" if mode == "driving" else "ROUTING_PREFERENCE_UNSPECIFIED"
        }
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json=payload, headers=headers, timeout=10.0)
                if response.status_code == 200:
                    data = response.json()
                    routes = data.get("routes", [])
                    if routes:
                        r = routes[0]
                        dur_str = r.get("duration", "0s").replace("s", "")
                        return {
                            "distance_meters": r.get("distanceMeters"),
                            "duration_seconds": int(dur_str),
                            "mode": mode
                        }
            except Exception as e:
                logger.error("Routes API failed: %s", e)

    # Fallback solver
    return calculate_mock_route(origin["lat"], origin["lng"], destination["lat"], destination["lng"], mode)

@traceable
async def get_route_matrix(
    origins: List[Dict[str, Any]],
    destinations: List[Dict[str, Any]],
    mode: str = "walking"
) -> Dict[str, Any]:
    """
    Calculate distance/duration matrix between origins and destinations.
    """
    matrix = {}
    for origin in origins:
        orig_id = origin.get("id") or origin.get("place_id") or origin.get("hotel_id")
        orig_lat = origin.get("lat") or origin.get("latitude")
        orig_lng = origin.get("lng") or origin.get("longitude")
        
        matrix[orig_id] = {}
        
        for dest in destinations:
            dest_id = dest.get("id") or dest.get("place_id") or dest.get("hotel_id")
            dest_lat = dest.get("lat") or dest.get("latitude")
            dest_lng = dest.get("lng") or dest.get("longitude")
            
            if orig_id == dest_id:
                matrix[orig_id][dest_id] = {"distance_meters": 0, "duration_seconds": 0}
            else:
                route_res = calculate_mock_route(orig_lat, orig_lng, dest_lat, dest_lng, mode)
                matrix[orig_id][dest_id] = {
                    "distance_meters": route_res["distance_meters"],
                    "duration_seconds": route_res["duration_seconds"]
                }
                
    return matrix
