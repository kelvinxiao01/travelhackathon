import urllib.parse
from typing import Any, Dict, List

class SMSFormatter:
    @staticmethod
    def format_progress(node: str, status: str = "running") -> str:
        """Format agent reasoning status updates into a short progress SMS."""
        icons = {
            "understand": "🧠",
            "discover": "🏨",
            "routing": "🚗",
            "optimize": "⚙️",
            "validate": "🔍",
            "replan": "🔄"
        }
        steps = {
            "understand": "Extracting your travel dates and budget...",
            "discover": "Researching Stay22 hotels & local spots...",
            "routing": "Fetching real travel times...",
            "optimize": "Solving optimal daily route schedule...",
            "validate": "Checking opening hours & walk buffers...",
            "replan": "Conflict detected! Running replanning loop..."
        }
        
        icon = icons.get(node, "✈️")
        desc = steps.get(node, "Thinking...")
        return f"ROAM {icon} {desc}"

    @staticmethod
    def generate_google_maps_url(
        orig_lat: float, orig_lng: float, 
        dest_lat: float, dest_lng: float, 
        mode: str = "walking"
    ) -> str:
        """Generate a direct clickable Google Maps directions URL."""
        # Maps travel modes: walking, transit, driving
        map_mode = "walking"
        if mode == "transit":
            map_mode = "transit"
        elif mode == "driving":
            map_mode = "driving"
            
        params = {
            "api": "1",
            "origin": f"{orig_lat},{orig_lng}",
            "destination": f"{dest_lat},{dest_lng}",
            "travelmode": map_mode
        }
        return f"https://www.google.com/maps/dir/?{urllib.parse.urlencode(params)}"

    @classmethod
    def format_itinerary_day(cls, itinerary: Dict[str, Any], hotel: Dict[str, Any], offer: Dict[str, Any], day_number: int) -> str:
        """Format a single day timeline page for the user's phone screen."""
        days = itinerary.get("days", [])
        day = next((d for d in days if d["day_number"] == day_number), None)
        if not day:
            return f"ROAM: Day {day_number} not found."

        date_str = day["date"]
        events = day["events"]
        
        header = f"ROAM ✈️ DAY {day_number} ({date_str})\n"
        hotel_section = f"🏨 Stay: {hotel['name']} (${offer['price']}/nt)\nBook: {offer['booking_url']}\n\n"
        
        timeline = []
        last_lat, last_lng = hotel["lat"], hotel["lng"]
        
        for e in events:
            ev_type = e["type"]
            start = e["start_time"]
            name = e["name"]
            
            if ev_type == "travel":
                mode_icon = "🚶" if e.get("transport_mode") == "walking" else "🚇"
                timeline.append(f"{mode_icon} {start}: {name} ({e['duration_minutes']} min)")
            elif ev_type in ["activity", "meal"]:
                emoji = "🍱" if ev_type == "meal" else "🎨"
                lat, lng = e.get("lat"), e.get("lng")
                
                # Append Maps link if coordinates exist
                maps_link = ""
                if lat is not None and lng is not None:
                    maps_link = f" (Dir: {cls.generate_google_maps_url(last_lat, last_lng, lat, lng, e.get('transport_mode', 'walking'))})"
                    last_lat, last_lng = lat, lng # Update last position
                
                timeline.append(f"{emoji} {start}: {name}{maps_link}")
                
        footer = f"\n\nReply:\nNEXT -> Day {day_number + 1}\nPREV -> Day {day_number - 1}\nHOTEL -> Details\nHELP -> List Commands"
        
        # Adjust footer boundaries
        if day_number == len(days):
            footer = footer.replace("NEXT -> Day " + str(day_number + 1), "SAVE -> Confirm Trip")
        if day_number == 1:
            footer = footer.replace("PREV -> Day 0\n", "")
            
        return header + hotel_section + "\n".join(timeline) + footer

    @classmethod
    def format_hotel_details(cls, hotel: Dict[str, Any], selected_offer: Dict[str, Any]) -> str:
        """Format detailed supplier rate list and cancellation details for SMS."""
        header = f"ROAM 🏨 HOTEL DETAILS\n\n"
        name = hotel["name"]
        rating = hotel["rating"]
        stars = hotel["stars"]
        address = hotel["address"]
        policy = hotel["cancellation_policy"]
        
        details = (
            f"{name} ({stars}★ • ⭐{rating}/5)\n"
            f"📍 {address}\n\n"
            f"Supplier Offers:\n"
        )
        
        offers_list = []
        for o in hotel["offers"]:
            marker = " [Selected]" if o["supplier"] == selected_offer["supplier"] else ""
            offers_list.append(f"• {o['supplier']}: ${o['price']}/nt{marker}")
            
        footer = f"\n👉 Book Link: {selected_offer['booking_url']}\n\nReply:\nITINERARY -> Back to schedule"
        
        return header + details + "\n".join(offers_list) + f"\n\nCancel: {policy}" + footer

    @classmethod
    def format_help(cls) -> str:
        """Return the list of active SMS control command keywords."""
        return (
            "ROAM ✈️ COMMANDS\n\n"
            "Text in natural language to plan/chat with the bot. Use these keywords anytime:\n\n"
            "• PLAN -> Start new trip\n"
            "• ITINERARY -> View current plan\n"
            "• NEXT -> Page to next day\n"
            "• PREV -> Page to previous day\n"
            "• HOTEL -> View hotel rates\n"
            "• SAVE -> Save final trip\n"
            "• HELP -> Show commands"
        )
