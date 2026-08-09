import pytest
from fastapi.testclient import TestClient
import os
import json

from main import app
from database import (
    get_or_create_conversation,
    add_conversation_message,
    get_conversation_messages,
    get_active_trip,
    save_trip
)
from tools.stay22 import search_accommodations
from tools.routes import calculate_mock_route, haversine_distance

client = TestClient(app)

def test_health_check_reports_service_ready() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_sms_database_persistence() -> None:
    import asyncio
    test_number = "+18888888888"
    
    # 1. Get or create conversation record
    conv = asyncio.run(get_or_create_conversation(test_number))
    assert conv is not None
    assert conv["phone_number"] == test_number
    conv_id = conv["id"]
    
    # 2. Add message log
    asyncio.run(add_conversation_message(conv_id, "inbound", "I want to visit NYC"))
    msgs = asyncio.run(get_conversation_messages(conv_id))
    assert len(msgs) > 0
    assert msgs[-1]["message"] == "I want to visit NYC"
    assert msgs[-1]["direction"] == "inbound"
    
    # 3. Get active trip state
    trip = asyncio.run(get_active_trip(conv_id))
    assert trip is not None
    trip_id = trip["id"]
    
    # 4. Save trip state
    state = {"destination": "New York City", "interests": ["museums"]}
    asyncio.run(save_trip(trip_id, state, "draft"))
    
    # 5. Reload active trip and check contents
    loaded_trip = asyncio.run(get_active_trip(conv_id, trip_id))
    assert loaded_trip["state_json"]["destination"] == "New York City"
    assert loaded_trip["state_json"]["interests"] == ["museums"]

def test_stay22_booking_link_builder() -> None:
    import asyncio
    hotels = asyncio.run(search_accommodations("New York City", "2027-06-01", "2027-06-04", 2))
    assert len(hotels) > 0
    for hotel in hotels:
        for offer in hotel["offers"]:
            url = offer["booking_url"]
            assert "stay22.com/allez/roam" in url
            assert "checkin=2027-06-01" in url
            assert "checkout=2027-06-04" in url
            assert "guests=2" in url

def test_geographical_distance_routing() -> None:
    dist = haversine_distance(40.7462, -73.9847, 40.7484, -73.9857)
    assert dist > 0.1
    assert dist < 0.5
    
    route = calculate_mock_route(40.7462, -73.9847, 40.7484, -73.9857, "walking")
    assert route["mode"] == "walking"
    assert route["duration_seconds"] > 60
    assert route["distance_meters"] > 200

def test_sms_webhook_endpoint_accepts_payload() -> None:
    response = client.post(
        "/api/webhooks/sms",
        headers={"X-Roam-Secret": os.getenv("ROAM_BACKEND_SECRET", "hackathon_secret_roam")},
        json={
            "from_number": "+15555550100",
            "to_number": "+13472738658",
            "text": "Help me plan a trip to NYC"
        }
    )
    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
