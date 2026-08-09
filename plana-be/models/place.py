from typing import List, Optional, Dict
from pydantic import BaseModel

class OpeningHours(BaseModel):
    weekday_text: List[str]

class Place(BaseModel):
    place_id: str
    name: str
    address: str
    lat: float
    lng: float
    types: List[str]
    rating: float
    review_count: int
    phone: Optional[str] = None
    website: Optional[str] = None
    opening_hours: OpeningHours
