from typing import Annotated, Any, Dict, List, Optional, TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

class TripState(TypedDict):
    # Traveler
    travelers: int
    traveler_profiles: List[Dict[str, Any]]

    # Destination
    destination: str
    start_date: str
    end_date: str
    start_time: Optional[str]  # e.g. "05:00 PM"
    end_time: Optional[str]    # e.g. "09:00 PM"

    # Preferences
    interests: List[str]
    dislikes: List[str]
    travel_style: List[str]

    # Constraints
    budget: Dict[str, Any]  # e.g., {"hotel_max_price": 600, "total_max_budget": 2000}
    max_walking_minutes: Optional[int]
    preferred_transport_modes: List[str]  # e.g., ["walking", "transit", "driving"]

    # Accommodation
    hotel_candidates: List[Dict[str, Any]]
    selected_hotel: Optional[Dict[str, Any]]
    selected_offer: Optional[Dict[str, Any]]

    # Experiences
    experience_candidates: List[Dict[str, Any]]
    selected_experiences: List[Dict[str, Any]]

    # Places (verified data)
    places: List[Dict[str, Any]]

    # Routing
    route_matrix: Optional[Dict[str, Any]]

    # Itinerary
    itinerary: Optional[Dict[str, Any]]

    # Validation
    issues: List[Dict[str, Any]]
    validation_status: str  # e.g., "valid", "invalid", "uninitialized"
    replan_count: Optional[int]

    # Agent Planning Status
    current_goal: str
    missing_information: List[str]

    # Conversation messages
    messages: Annotated[List[AnyMessage], add_messages]
