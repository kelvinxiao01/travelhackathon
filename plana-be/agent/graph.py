import os
import json
import logging
import re
import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END

from .state import TripState
from tools.stay22 import search_accommodations
from tools.tavily import web_research
from tools.places import search_places, get_place_details
from tools.routes import get_route_matrix
from tools.aeroxplorer import search_flight_information

logger = logging.getLogger(__name__)

# --- Helper parser for opening hours ---
def parse_time_to_minutes(time_str: str) -> Optional[int]:
    """Parse time string like '10:00 AM' or '5:30 PM' or '22:00' to minutes from midnight."""
    time_str = time_str.strip().upper()
    try:
        if "AM" in time_str or "PM" in time_str:
            # e.g., "10:00 AM" or "5:30 PM"
            match = re.match(r"(\d+):(\d+)\s*(AM|PM)", time_str)
            if not match:
                return None
            hours, minutes, period = match.groups()
            h = int(hours)
            m = int(minutes)
            if period == "PM" and h < 12:
                h += 12
            elif period == "AM" and h == 12:
                h = 0
            return h * 60 + m
        else:
            # e.g. "17:30" or "22:00"
            parts = time_str.split(":")
            if len(parts) >= 2:
                return int(parts[0]) * 60 + int(parts[1])
    except Exception as e:
        logger.error("Failed parsing time string %r: %s", time_str, e)
    return None

def get_opening_hours_for_day(weekday_text: List[str], target_day_name: str) -> Tuple[Optional[int], Optional[int]]:
    """
    Returns (open_minutes, close_minutes) from midnight.
    If closed all day, returns (None, None).
    """
    day_name = target_day_name.lower()
    for text in weekday_text:
        text_lower = text.lower()
        if text_lower.startswith(day_name):
            if "closed" in text_lower:
                return None, None
            # e.g. "Monday: 10:00 AM – 5:30 PM" or "Monday: 10:00 AM - 10:00 PM"
            # Split after colon
            parts = text.split(":", 1)
            if len(parts) < 2:
                continue
            time_part = parts[1].replace("–", "-").replace("—", "-")
            time_ranges = time_part.split("-")
            if len(time_ranges) < 2:
                # E.g., "Open 24 hours"
                if "24 hours" in time_part.lower():
                    return 0, 24 * 60
                continue
            
            open_min = parse_time_to_minutes(time_ranges[0])
            close_min = parse_time_to_minutes(time_ranges[1])
            return open_min, close_min
            
    # Default to open if not specified
    return 0, 24 * 60

# --- Graph Node Functions ---

async def understand_node(state: TripState) -> Dict[str, Any]:
    """Node: Extract parameters and constraints from user prompt using LLM."""
    last_message = state["messages"][-1].content if state["messages"] else ""
    openai_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")

    extracted = {
        "intent": "plan",
        "destination": state.get("destination"),
        "start_date": state.get("start_date"),
        "end_date": state.get("end_date"),
        "start_time": state.get("start_time"),
        "end_time": state.get("end_time"),
        "travelers": state.get("travelers", 2),
        "interests": state.get("interests", []),
        "dislikes": state.get("dislikes", []),
        "budget": state.get("budget", {"hotel_max_price": 600.0, "total_max_budget": 2000.0}),
        "preferred_transport_modes": state.get("preferred_transport_modes", ["walking", "transit"]),
        "max_walking_minutes": state.get("max_walking_minutes", 30),
        "missing_information": []
    }

    if openai_key:
        try:
            base_url = "https://openrouter.ai/api/v1" if "sk-or-" in openai_key else None
            model_name = "google/gemini-2.5-flash" if "sk-or-" in openai_key else "gpt-4o-mini"
            llm = ChatOpenAI(
                api_key=openai_key,
                base_url=base_url,
                model=model_name,
                temperature=0
            )
            system_msg = SystemMessage(content=(
                f"The current date and time is: {datetime.now().strftime('%A, %B %d, %Y %I:%M %p')}.\n"
                "You are the request extraction node for ROAM, an AI travel planner.\n"
                "Extract structured data from the user messages.\n"
                "Output ONLY a raw valid JSON object. Do not wrap in markdown ```json."
                "If the user is saying greeting words (like 'hi', 'hello') or asking questions unrelated to planning a specific trip, classify intent as 'chat'.\n"
                "JSON format:\n"
                "{\n"
                '  "intent": "plan" or "chat",\n'
                '  "destination": "string or null",\n'
                '  "start_date": "YYYY-MM-DD or null",\n'
                '  "end_date": "YYYY-MM-DD or null",\n'
                '  "start_time": "HH:MM AM/PM or null (e.g. 05:00 PM)",\n'
                '  "end_time": "HH:MM AM/PM or null (e.g. 09:00 PM)",\n'
                '  "travelers": int or null,\n'
                '  "interests": ["string"],\n'
                '  "dislikes": ["string"],\n'
                '  "budget": {"hotel_max_price": float or null, "total_max_budget": float or null},\n'
                '  "preferred_transport_modes": ["string"],\n'
                '  "max_walking_minutes": int or null,\n'
                '  "missing_information": ["string"]\n'
                "}"
            ))
            # Format message history
            history = []
            for msg in state["messages"]:
                if isinstance(msg, HumanMessage):
                    history.append(f"User: {msg.content}")
                else:
                    history.append(f"Agent: {msg.content}")
            
            user_msg = HumanMessage(content="Extract from conversation:\n" + "\n".join(history))
            res = await llm.ainvoke([system_msg, user_msg])
            content = res.content.strip()
            if content.startswith("```"):
                content = re.sub(r"^```[a-zA-Z]*\n", "", content)
                content = re.sub(r"\n```$", "", content)
            
            parsed = json.loads(content)
            # Merge extracted data
            for k, v in parsed.items():
                if v is not None:
                    extracted[k] = v
        except Exception as e:
            logger.error("LLM Extraction failed, using default extraction: %s", e)

    # Safety fallback: default end_date to start_date + 1 day if end_date is missing
    if extracted.get("start_date") and not extracted.get("end_date"):
        try:
            start_dt = datetime.strptime(extracted["start_date"], "%Y-%m-%d")
            end_dt = start_dt + timedelta(days=1)
            extracted["end_date"] = end_dt.strftime("%Y-%m-%d")
            logger.info("understand_node: Defaulted end_date to %s", extracted["end_date"])
        except Exception as e:
            logger.error("Failed to default end_date: %s", e)
            extracted["end_date"] = extracted["start_date"]
    else:
        # High fidelity local extraction fallback
        logger.info("Using local regex-based understanding node")
        text = last_message.lower()
        if "hi" in text or "hello" in text:
            extracted["intent"] = "chat"
        if "hotel under" in text:
            match = re.search(r"under \$?(\d+)", text)
            if match:
                extracted["budget"]["hotel_max_price"] = float(match.group(1))
        
        interests = []
        if "japanese" in text or "food" in text:
            interests.append("japanese food")
        if "museum" in text:
            interests.append("museums")
        if "nightlife" in text or "jazz" in text:
            interests.append("nightlife")
        if interests:
            extracted["interests"] = interests

    return {
        "intent": extracted["intent"],
        "destination": extracted["destination"],
        "start_date": extracted["start_date"],
        "end_date": extracted["end_date"],
        "start_time": extracted.get("start_time"),
        "end_time": extracted.get("end_time"),
        "travelers": extracted["travelers"],
        "interests": extracted["interests"],
        "dislikes": extracted["dislikes"],
        "budget": extracted["budget"],
        "preferred_transport_modes": extracted["preferred_transport_modes"],
        "max_walking_minutes": extracted["max_walking_minutes"],
        "missing_information": extracted["missing_information"],
        "current_goal": "discover_options" if extracted["intent"] == "plan" else "chat"
    }

async def converse_node(state: TripState) -> Dict[str, Any]:
    """Node: Ask for missing information or chat with the user."""
    openai_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
    
    reply = "Hi! I am ROAM. Where would you like to travel, and what are your dates? E.g., 'Plan a 3-day trip to NYC starting June 1st'."
    
    if openai_key:
        try:
            base_url = "https://openrouter.ai/api/v1" if "sk-or-" in openai_key else None
            model_name = "google/gemini-2.5-flash" if "sk-or-" in openai_key else "gpt-4o-mini"
            llm = ChatOpenAI(
                api_key=openai_key,
                base_url=base_url,
                model=model_name,
                temperature=0.7
            )
            system_msg = SystemMessage(content=(
                f"The current date and time is: {datetime.now().strftime('%A, %B %d, %Y %I:%M %p')}.\n"
                "You are ROAM, an intelligent agentic travel planner.\n"
                "You are conversing with a user to help them plan their next trip.\n"
                "Your goal is to gather their destination, dates, travelers, and preferences.\n"
                "Ask clarifying questions one at a time, keeping it brief and friendly. Do not overwhelm them.\n"
                "If they ask questions, answer them warmly based on travel knowledge.\n"
                "If they just say 'hi' or greet you, respond with a friendly greeting and ask where they are traveling to."
            ))
            
            history = []
            for msg in state["messages"]:
                history.append(msg)
                
            res = await llm.ainvoke([system_msg] + history)
            reply = res.content.strip()
        except Exception as e:
            logger.error("Chat conversation failed: %s", e)

    new_message = AIMessage(content=reply)
    
    return {
        "messages": state["messages"] + [new_message],
        "current_goal": "chat"
    }

async def discover_node(state: TripState) -> Dict[str, Any]:
    """Node: Search hotels on Stay22, web research on Tavily, and verify on Places."""
    dest = state.get("destination")
    checkin = state.get("start_date")
    checkout = state.get("end_date")
    guests = state.get("travelers") or 2
    budget_limit = state.get("budget", {}).get("hotel_max_price") or 600
    interests = state.get("interests") or ["tourist attraction"]

    # 1. Stay22 search
    logger.info("Searching hotels on Stay22 for %s", dest)
    hotel_candidates = await search_accommodations(
        destination=dest,
        check_in=checkin,
        check_out=checkout,
        guests=guests,
        budget=budget_limit
    )

    # Pick best hotel fit
    selected_hotel = None
    selected_offer = None
    if hotel_candidates:
        # Choose the hotel with highest rating within budget
        sorted_hotels = sorted(hotel_candidates, key=lambda h: h["rating"], reverse=True)
        selected_hotel = sorted_hotels[0]
        # Choose cheapest offer for this hotel
        sorted_offers = sorted(selected_hotel["offers"], key=lambda o: o["price"])
        selected_offer = sorted_offers[0]

    # 2. Tavily & Google Places discovery
    experience_candidates = []
    verified_places = []
    
    # Run research based on interests
    for interest in interests[:3]:
        logger.info("Searching activities for interest: %s", interest)
        research_docs = await web_research(query=interest, location=dest)
        
        # Parse names from research doc using simple rules or LLM
        # For simplicity, extract matching items from Places database based on research keywords
        places_found = await search_places(query=interest, location=dest)
        for pf in places_found[:2]:
            if pf["place_id"] not in [v["place_id"] for v in verified_places]:
                # Verify details
                details = await get_place_details(pf["place_id"])
                if details:
                    verified_places.append(details)
                    experience_candidates.append({
                        "place_id": details["place_id"],
                        "name": details["name"],
                        "address": details["address"],
                        "lat": details["lat"],
                        "lng": details["lng"],
                        "rating": details["rating"],
                        "types": details["types"]
                    })

    return {
        "hotel_candidates": hotel_candidates,
        "selected_hotel": selected_hotel,
        "selected_offer": selected_offer,
        "experience_candidates": experience_candidates,
        "places": verified_places,
        "current_goal": "calculate_routes"
    }

async def routing_node(state: TripState) -> Dict[str, Any]:
    """Node: Calculate the travel matrix between selected hotels and verified places."""
    hotel = state["selected_hotel"]
    places = state["places"]

    if not hotel or not places:
        return {"route_matrix": None}

    # All nodes: hotel + all attractions
    origins = [hotel] + places
    destinations = [hotel] + places

    # Calculate matrices for both walking and transit
    walking_matrix = await get_route_matrix(origins, destinations, mode="walking")
    transit_matrix = await get_route_matrix(origins, destinations, mode="transit")

    route_matrix = {
        "walking": walking_matrix,
        "transit": transit_matrix
    }

    return {
        "route_matrix": route_matrix,
        "current_goal": "optimize_itinerary"
    }

async def optimize_node(state: TripState) -> Dict[str, Any]:
    """Node: Deterministic scheduling optimizer."""
    hotel = state["selected_hotel"]
    places = state["places"]
    matrix = state["route_matrix"]
    start_date_str = state["start_date"]
    end_date_str = state["end_date"]
    
    if not hotel or not places or not matrix:
        return {"itinerary": None}

    # Calculate days count
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
    days_count = (end_date - start_date).days
    if days_count <= 0:
        days_count = 1

    # Deterministic Scheduling Solver
    day_plans = []
    assigned_places = set()

    # Distribute places among days (simple clustering or sequential order)
    places_per_day = len(places) // days_count
    if places_per_day == 0:
        places_per_day = 1

    # Daily scheduling timeframes
    # Slots: Morning (10:00 - 12:30), Afternoon (15:00 - 17:30), Dinner (19:00 - 21:00)
    for day_idx in range(1, days_count + 1):
        curr_date = start_date + timedelta(days=day_idx - 1)
        weekday_name = curr_date.strftime("%A")
        
        # Determine day start time and end time constraints
        start_min = 9 * 60  # Default 9 AM
        if state.get("start_time"):
            parsed_start = parse_time_to_minutes(state["start_time"])
            if parsed_start is not None:
                start_min = parsed_start

        end_min = 21 * 60  # Default 9 PM
        if state.get("end_time"):
            parsed_end = parse_time_to_minutes(state["end_time"])
            if parsed_end is not None:
                end_min = parsed_end

        def format_min_to_ampm(m: int) -> str:
            h = m // 60
            mins = m % 60
            period = "AM"
            if h >= 12:
                period = "PM"
                if h > 12:
                    h -= 12
            if h == 0:
                h = 12
            return f"{h}:{mins:02d} {period}"

        events = []
        # Start at Hotel
        events.append({
            "type": "hotel",
            "name": f"Depart {hotel['name']}",
            "place_id": hotel["hotel_id"],
            "start_time": format_min_to_ampm(start_min),
            "end_time": format_min_to_ampm(start_min),
            "duration_minutes": 0,
            "address": hotel["address"],
            "lat": hotel["lat"],
            "lng": hotel["lng"]
        })

        # Select up to 3 attractions for this day
        day_places = []
        for p in places:
            if p["place_id"] not in assigned_places:
                day_places.append(p)
                assigned_places.add(p["place_id"])
                if len(day_places) >= 3:
                    break

        curr_time_min = start_min
        last_loc_id = hotel["hotel_id"]
        last_lat = hotel["lat"]
        last_lng = hotel["lng"]

        for idx, place in enumerate(day_places):
            # Check opening hours for the day
            open_min, close_min = get_opening_hours_for_day(place["opening_hours"]["weekday_text"], weekday_name)
            
            # Determine travel duration (default to walking, fallback to transit if far)
            travel_time_sec = matrix["walking"].get(last_loc_id, {}).get(place["place_id"], {}).get("duration_seconds", 900)
            mode = "walking"
            if travel_time_sec > 1200: # > 20 mins walking, switch to transit
                travel_time_sec = matrix["transit"].get(last_loc_id, {}).get(place["place_id"], {}).get("duration_seconds", 600)
                mode = "transit"

            travel_min = int(math.ceil(travel_time_sec / 60))
            buffer_min = 10
            required_gap = travel_min + buffer_min

            # Ensure travel + activity fits within user daily timeframe bounds
            required_duration = required_gap + 120
            if curr_time_min + required_duration > end_min:
                assigned_places.discard(place["place_id"])
                continue

            # Harness/Safety: delay departure time if arrival is before opening hours
            arrival_time = curr_time_min + required_gap
            if open_min is not None and arrival_time < open_min:
                curr_time_min = open_min - required_gap

            # Add Travel segment
            travel_start = f"{curr_time_min // 60:02d}:{curr_time_min % 60:02d}"
            curr_time_min += required_gap
            travel_end = f"{curr_time_min // 60:02d}:{curr_time_min % 60:02d}"
            
            events.append({
                "type": "travel",
                "name": f"Travel to {place['name']}",
                "start_time": travel_start,
                "end_time": travel_end,
                "duration_minutes": required_gap,
                "transport_mode": mode,
                "travel_time_minutes": travel_min
            })

            # Check if attraction is closed
            is_closed = False
            if open_min is None or close_min is None:
                is_closed = True
            elif curr_time_min < open_min or curr_time_min + 120 > close_min:
                # If we arrive before it opens or can't spend 2 hours before it closes
                is_closed = True

            # Decide activity duration (2 hours, or less if close_min is tight)
            duration = 120
            if close_min and curr_time_min + duration > close_min:
                duration = max(30, close_min - curr_time_min)

            activity_start = f"{(curr_time_min) // 60:02d}:{(curr_time_min) % 60:02d}"
            curr_time_min += duration
            activity_end = f"{(curr_time_min) // 60:02d}:{(curr_time_min) % 60:02d}"

            # Format times to standard AM/PM format
            def format_min_to_ampm(m: int) -> str:
                h = m // 60
                mins = m % 60
                period = "AM"
                if h >= 12:
                    period = "PM"
                    if h > 12:
                        h -= 12
                if h == 0:
                    h = 12
                return f"{h}:{mins:02d} {period}"

            # Update event structure with accurate formatted times
            events[-1]["start_time"] = format_min_to_ampm(curr_time_min - duration - required_gap)
            events[-1]["end_time"] = format_min_to_ampm(curr_time_min - duration)

            events.append({
                "type": "activity" if "restaurant" not in place["types"] else "meal",
                "name": place["name"],
                "place_id": place["place_id"],
                "start_time": format_min_to_ampm(curr_time_min - duration),
                "end_time": format_min_to_ampm(curr_time_min),
                "duration_minutes": duration,
                "address": place["address"],
                "lat": place["lat"],
                "lng": place["lng"],
                "description": f"Verified rating: {place['rating']} stars ({place['review_count']} reviews)."
            })

            last_loc_id = place["place_id"]
            last_lat = place["lat"]
            last_lng = place["lng"]
            
            # Simple break for lunch/dinner timings
            if idx == 0:
                # Add 30 mins break
                curr_time_min += 30

        # Return to Hotel
        travel_time_sec = matrix["walking"].get(last_loc_id, {}).get(hotel["hotel_id"], {}).get("duration_seconds", 900)
        mode = "walking"
        if travel_time_sec > 1200:
            travel_time_sec = matrix["transit"].get(last_loc_id, {}).get(hotel["hotel_id"], {}).get("duration_seconds", 600)
            mode = "transit"
            
        travel_min = int(math.ceil(travel_time_sec / 60))
        required_gap = travel_min + 10
        
        travel_start = f"{curr_time_min // 60:02d}:{curr_time_min % 60:02d}"
        curr_time_min += required_gap
        travel_end = f"{curr_time_min // 60:02d}:{curr_time_min % 60:02d}"
        
        def format_min_to_ampm(m: int) -> str:
            h = m // 60
            mins = m % 60
            period = "AM"
            if h >= 12:
                period = "PM"
                if h > 12:
                    h -= 12
            if h == 0:
                h = 12
            return f"{h}:{mins:02d} {period}"

        events.append({
            "type": "travel",
            "name": f"Return to {hotel['name']}",
            "start_time": format_min_to_ampm(curr_time_min - required_gap),
            "end_time": format_min_to_ampm(curr_time_min),
            "duration_minutes": required_gap,
            "transport_mode": mode,
            "travel_time_minutes": travel_min
        })

        events.append({
            "type": "hotel",
            "name": f"Arrive {hotel['name']}",
            "place_id": hotel["hotel_id"],
            "start_time": format_min_to_ampm(curr_time_min),
            "end_time": format_min_to_ampm(curr_time_min),
            "duration_minutes": 0,
            "address": hotel["address"],
            "lat": hotel["lat"],
            "lng": hotel["lng"]
        })

        day_plans.append({
            "day_number": day_idx,
            "date": curr_date.strftime("%Y-%m-%d"),
            "events": events
        })

    # Total hotel price
    hotel_rate = state["selected_offer"]["price"] if state["selected_offer"] else 300.0
    total_hotel_cost = hotel_rate * days_count

    itinerary = {
        "days": day_plans,
        "total_cost": total_hotel_cost,
        "selected_hotel_id": hotel["hotel_id"]
    }

    return {
        "itinerary": itinerary,
        "current_goal": "validate_itinerary"
    }

async def validate_node(state: TripState) -> Dict[str, Any]:
    """Node: Rule-based validation checking conflicts, overlaps, and buffers."""
    itinerary = state["itinerary"]
    places = state["places"]
    hotel = state["selected_hotel"]
    issues = []
    
    if not itinerary:
        return {"issues": [{"severity": "error", "message": "Itinerary has not been generated."}], "validation_status": "invalid"}

    # We map place_id to place details for fast lookup
    places_map = {p["place_id"]: p for p in places}

    for day in itinerary["days"]:
        weekday_name = datetime.strptime(day["date"], "%Y-%m-%d").strftime("%A")
        events = day["events"]
        
        for idx, event in enumerate(events):
            # Check opening hours for activities/meals
            if event["type"] in ["activity", "meal"] and event["place_id"]:
                place = places_map.get(event["place_id"])
                if place:
                    open_min, close_min = get_opening_hours_for_day(place["opening_hours"]["weekday_text"], weekday_name)
                    
                    # Convert event start/end times to minutes
                    start_min = parse_time_to_minutes(event["start_time"])
                    end_min = parse_time_to_minutes(event["end_time"])
                    
                    if open_min is None or close_min is None:
                        issues.append({
                            "severity": "error",
                            "message": f"{event['name']} is closed on {weekday_name}!",
                            "affected_day": day["day_number"],
                            "affected_event": event["name"]
                        })
                    elif start_min is not None and end_min is not None:
                        if start_min < open_min or end_min > close_min:
                            issues.append({
                                "severity": "error",
                                "message": f"{event['name']} is scheduled from {event['start_time']} to {event['end_time']}, but it is only open {weekday_name}: " + ", ".join(place["opening_hours"]["weekday_text"]),
                                "affected_day": day["day_number"],
                                "affected_event": event["name"]
                            })

            # Check travel buffers
            if event["type"] == "travel":
                # Ensure travel time fits inside start/end time
                start_min = parse_time_to_minutes(event["start_time"])
                end_min = parse_time_to_minutes(event["end_time"])
                if start_min is not None and end_min is not None:
                    allocated_minutes = end_min - start_min
                    travel_minutes = event.get("travel_time_minutes", 0)
                    if allocated_minutes < travel_minutes:
                        issues.append({
                            "severity": "error",
                            "message": f"Travel block to {events[idx+1]['name']} is only {allocated_minutes} minutes, but Google Routes says it requires {travel_minutes} minutes.",
                            "affected_day": day["day_number"],
                            "affected_event": event["name"]
                        })

    # Check overall budget constraints
    max_budget = state.get("budget", {}).get("total_max_budget")
    if max_budget and itinerary["total_cost"] > max_budget:
        issues.append({
            "severity": "error",
            "message": f"Total hotel cost is ${itinerary['total_cost']}, which exceeds total budget of ${max_budget}.",
            "affected_day": None,
            "affected_event": None
        })

    validation_status = "valid" if not issues else "invalid"
    return {
        "issues": issues,
        "validation_status": validation_status,
        "current_goal": "replan_or_finish"
    }

async def replan_node(state: TripState) -> Dict[str, Any]:
    """Node: Replan itinerary using LLM to resolve issues dynamically without hardcoded values."""
    issues = state.get("issues", [])
    places = list(state.get("places", []))
    experience_candidates = state.get("experience_candidates", [])
    
    # Circuit breaker: prevent runaway infinite loops
    replan_count = state.get("replan_count") or 0
    if replan_count >= 2:
        logger.warning("LANGGRAPH CIRCUIT BREAKER: Maximum replan iterations reached. Forcing valid status to avoid loop.")
        return {
            "validation_status": "valid",
            "current_goal": "finalize",
            "replan_count": replan_count + 1
        }
        
    logger.info("Validation issues found: %s. Initiating LLM replanner node.", issues)
    openai_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
    
    if not openai_key or not issues:
        # Fallback: remove conflicting place from active itinerary to resolve schedule block
        for issue in issues:
            evt_name = issue.get("affected_event")
            if evt_name:
                places = [p for p in places if p["name"] != evt_name]
        return {
            "places": places,
            "validation_status": "uninitialized",
            "issues": [],
            "current_goal": "optimize_itinerary",
            "replan_count": replan_count + 1
        }
        
    try:
        base_url = "https://openrouter.ai/api/v1" if "sk-or-" in openai_key else None
        model_name = "google/gemini-2.5-flash" if "sk-or-" in openai_key else "gpt-4o-mini"
        llm = ChatOpenAI(
            api_key=openai_key,
            base_url=base_url,
            model=model_name,
            temperature=0
        )
        
        system_msg = SystemMessage(content=(
            "You are the dynamic replanning node for ROAM, an AI travel planner.\n"
            "Your goal is to resolve validation schedule conflicts (e.g. closed attractions, exceeded budget).\n"
            "You are provided with:\n"
            "1. The current selected places/attractions.\n"
            "2. The validation issues/conflicts.\n"
            "3. Other alternative experience candidates.\n"
            "Output a JSON object containing the updated list of places to include in the trip.\n"
            "If an attraction is closed on a day, replace it with a suitable alternative candidate that fits the user's interests.\n"
            "Output ONLY a raw valid JSON array of updated place objects. Do not wrap in markdown.\n"
            "JSON format:\n"
            "[\n"
            "  { \"place_id\": \"string\", \"name\": \"string\", \"address\": \"string\", \"lat\": float, \"lng\": float, \"rating\": float, \"types\": [\"string\"] }\n"
            "]"
        ))
        
        user_content = (
            f"Current selected places: {json.dumps(places)}\n"
            f"Validation Issues: {json.dumps(issues)}\n"
            f"Alternative Candidates: {json.dumps(experience_candidates)}"
        )
        user_msg = HumanMessage(content=user_content)
        res = await llm.ainvoke([system_msg, user_msg])
        content = res.content.strip()
        
        if content.startswith("```"):
            content = re.sub(r"^```[a-zA-Z]*\n", "", content)
            content = re.sub(r"\n```$", "", content)
            
        new_places = json.loads(content)
        return {
            "places": new_places,
            "validation_status": "uninitialized",
            "issues": [],
            "current_goal": "optimize_itinerary",
            "replan_count": replan_count + 1
        }
    except Exception as e:
        logger.error("LLM Replanner failed, removing conflicting events: %s", e)
        for issue in issues:
            evt_name = issue.get("affected_event")
            if evt_name:
                places = [p for p in places if p["name"] != evt_name]
        return {
            "places": places,
            "validation_status": "uninitialized",
            "issues": [],
            "current_goal": "optimize_itinerary",
            "replan_count": replan_count + 1
        }

# --- Router Logic ---

def should_continue(state: TripState) -> str:
    """Conditional routing edge."""
    dest = state.get("destination")
    start = state.get("start_date")
    end = state.get("end_date")
    goal = state.get("current_goal")
    status = state.get("validation_status")

    if not dest or not start or not end or goal == "chat":
        return "converse"

    if status == "invalid":
        return "replan"
    elif goal == "optimize_itinerary":
        return "optimize"
    elif status == "valid" or goal == "finalize":
        return END
    else:
        # Step transitions
        next_goals = {
            "discover_options": "discover",
            "calculate_routes": "routing",
            "optimize_itinerary": "optimize",
            "validate_itinerary": "validate"
        }
        return next_goals.get(goal, END)

# --- Graph Definition ---

def build_workflow() -> StateGraph:
    workflow = StateGraph(TripState)

    # Add Nodes
    workflow.add_node("understand", understand_node)
    workflow.add_node("converse", converse_node)
    workflow.add_node("discover", discover_node)
    workflow.add_node("routing", routing_node)
    workflow.add_node("optimize", optimize_node)
    workflow.add_node("validate", validate_node)
    workflow.add_node("replan", replan_node)

    # Set Entry Point
    workflow.set_entry_point("understand")

    # Add Edges
    router_map = {
        "converse": "converse",
        "discover": "discover",
        "routing": "routing",
        "optimize": "optimize",
        "validate": "validate",
        "replan": "replan",
        END: END
    }

    workflow.add_conditional_edges("understand", should_continue, router_map)
    workflow.add_edge("converse", END)
    workflow.add_conditional_edges("discover", should_continue, router_map)
    workflow.add_conditional_edges("routing", should_continue, router_map)
    workflow.add_conditional_edges("optimize", should_continue, router_map)
    workflow.add_conditional_edges("validate", should_continue, router_map)
    workflow.add_conditional_edges("replan", should_continue, router_map)

    return workflow

# Compile graph
workflow = build_workflow()
roam_graph = workflow.compile()
