from typing import List, Optional, Dict
from pydantic import BaseModel
from .hotel import Hotel
from .place import Place
from .itinerary import Itinerary

class BudgetConstraint(BaseModel):
    hotel_max_price: Optional[float] = None
    total_max_budget: Optional[float] = None

class TravelerProfile(BaseModel):
    age: Optional[int] = None
    interests: List[str] = []

class ValidationIssue(BaseModel):
    # e.g., "warning", "error"
    severity: str
    message: str
    affected_day: Optional[int] = None
    affected_event: Optional[str] = None
