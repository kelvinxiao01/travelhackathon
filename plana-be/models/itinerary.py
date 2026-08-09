from typing import List, Optional
from pydantic import BaseModel

class ItineraryEvent(BaseModel):
    # Event types: "activity", "hotel", "travel", "meal"
    type: str
    name: str
    place_id: Optional[str] = None
    start_time: str  # Format: "HH:MM"
    end_time: str    # Format: "HH:MM"
    duration_minutes: int
    address: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    transport_mode: Optional[str] = None
    travel_time_minutes: Optional[int] = None
    price: Optional[float] = 0.0
    booking_url: Optional[str] = None
    description: Optional[str] = None

class DailyTimeline(BaseModel):
    day_number: int
    date: str
    events: List[ItineraryEvent]

class Itinerary(BaseModel):
    days: List[DailyTimeline]
    total_cost: float
    selected_hotel_id: str
