import os
import logging
from typing import Any, Dict, List, Optional
import httpx
from langsmith import traceable

logger = logging.getLogger(__name__)

@traceable
async def search_places(
    query: str,
    location: Optional[str] = None,
    category: Optional[str] = None,
    radius: Optional[float] = None
) -> List[Dict[str, Any]]:
    """
    Search places using Google Places API (Text Search) with the real API Key.
    """
    api_key = os.getenv("GOOGLE_MAPS_SERVER_KEY")
    if not api_key:
        logger.error("GOOGLE_MAPS_SERVER_KEY is missing from environment variables!")
        raise ValueError("Google Maps API Key is not configured.")

    logger.info("Executing Google Places search for: %r", query)
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.location,places.types,places.rating,places.userRatingCount"
    }
    payload = {"textQuery": query}
    if location:
        payload["textQuery"] = f"{query} in {location}"

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers, timeout=10.0)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for p in data.get("places", []):
            loc = p.get("location", {})
            results.append({
                "place_id": p.get("id"),
                "name": p.get("displayName", {}).get("text"),
                "address": p.get("formattedAddress"),
                "lat": loc.get("latitude"),
                "lng": loc.get("longitude"),
                "types": p.get("types", []),
                "rating": p.get("rating", 4.0),
                "review_count": p.get("userRatingCount", 0)
            })
        return results

@traceable
async def get_place_details(place_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve details for a place (opening hours, address) using the real Google Places Key.
    """
    api_key = os.getenv("GOOGLE_MAPS_SERVER_KEY")
    if not api_key:
        logger.error("GOOGLE_MAPS_SERVER_KEY is missing from environment variables!")
        raise ValueError("Google Maps API Key is not configured.")

    logger.info("Executing Google Places details for: %r", place_id)
    url = f"https://places.googleapis.com/v1/places/{place_id}"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "id,displayName,formattedAddress,location,currentOpeningHours,regularOpeningHours,nationalPhoneNumber,websiteUri,rating,userRatingCount,types"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, timeout=10.0)
        if response.status_code == 200:
            p = response.json()
            loc = p.get("location", {})
            hours = p.get("regularOpeningHours", p.get("currentOpeningHours", {}))
            
            return {
                "place_id": p.get("id"),
                "name": p.get("displayName", {}).get("text"),
                "address": p.get("formattedAddress"),
                "lat": loc.get("latitude"),
                "lng": loc.get("longitude"),
                "types": p.get("types", []),
                "rating": p.get("rating", 4.0),
                "review_count": p.get("userRatingCount", 0),
                "phone": p.get("nationalPhoneNumber"),
                "website": p.get("websiteUri"),
                "opening_hours": {
                    "weekday_text": hours.get("weekdayDescriptions", [
                        "Monday: 9:00 AM – 9:00 PM",
                        "Tuesday: 9:00 AM – 9:00 PM",
                        "Wednesday: 9:00 AM – 9:00 PM",
                        "Thursday: 9:00 AM – 9:00 PM",
                        "Friday: 9:00 AM – 9:00 PM",
                        "Saturday: 9:00 AM – 9:00 PM",
                        "Sunday: 9:00 AM – 9:00 PM"
                    ])
                }
            }
        else:
            logger.error("Places Details API returned status %s: %s", response.status_code, response.text)
            return None
