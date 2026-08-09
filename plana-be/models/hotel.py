from typing import List, Optional
from pydantic import BaseModel

class SupplierOffer(BaseModel):
    supplier: str
    price: float
    booking_url: str

class Hotel(BaseModel):
    hotel_id: str
    name: str
    address: str
    lat: float
    lng: float
    rating: float
    review_count: int
    stars: int
    capacity: int
    cancellation_policy: str
    images: List[str]
    offers: List[SupplierOffer]
