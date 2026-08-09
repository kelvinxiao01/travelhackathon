import asyncio
import hmac
import json
import logging
import os
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

import uvicorn
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage

load_dotenv()

from agent.graph import roam_graph
from database import (
    get_or_create_conversation,
    add_conversation_message,
    get_conversation_messages,
    get_active_trip,
    save_trip,
    update_conversation_active_trip,
    get_all_trips
)
from sms_formatter import SMSFormatter
from voice_itinerary import (
    VoiceItineraryConflictError,
    VoiceItineraryEdit,
    VoiceTripNotFoundError,
    get_voice_trip_context,
    reschedule_voice_itinerary_event,
)
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="ROAM API Engine")


def require_voice_agent_auth(request: Request) -> None:
    """Authorize calls made by the separately deployed LiveKit worker.

    Supabase credentials remain in this backend. The worker receives only this
    short server-to-server credential, which must never be sent to the browser.
    """
    expected_secret = os.getenv("PLANA_VOICE_AGENT_SECRET")
    if not expected_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PLANA_VOICE_AGENT_SECRET is not configured.",
        )

    authorization = request.headers.get("Authorization", "")
    provided_secret = authorization.removeprefix("Bearer ").strip()
    if not provided_secret or not hmac.compare_digest(provided_secret, expected_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid voice-agent credentials.",
        )

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check() -> Dict[str, str]:
    return {"status": "ok"}

async def send_telnyx_sms(to_number: str, from_number: str, text: str) -> None:
    """Send outbound SMS via Telnyx API, with mock fallback logging."""
    api_key = os.getenv("TELNYX_API_KEY")
    if not api_key:
        logger.info(
            f"\n========================================\n"
            f"[MOCK SMS OUTBOUND]\n"
            f"From: {from_number}\n"
            f"To: {to_number}\n"
            f"Content: {text}\n"
            f"========================================\n"
        )
        return
    
    url = "https://api.telnyx.com/v2/messages"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "from": from_number,
        "to": to_number,
        "text": text
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            logger.info("Sent Telnyx SMS to %s successfully", to_number)
        except Exception as e:
            logger.error("Error sending Telnyx SMS: %s", e)

async def process_sms_background(phone_number: str, bot_number: str, text: str):
    """Background processing of SMS message or commands."""
    try:
        conv = await get_or_create_conversation(phone_number)
        conv_id = conv["id"]
        
        await add_conversation_message(conv_id, "inbound", text)
        
        cmd = text.strip().upper()
        trip = await get_active_trip(conv_id, conv.get("active_trip_id"))
        trip_id = trip["id"]
        trip_state = trip["state_json"]
        
        if conv.get("active_trip_id") != trip_id:
            await update_conversation_active_trip(conv_id, trip_id)

        if cmd == "HELP":
            reply = SMSFormatter.format_help()
            await add_conversation_message(conv_id, "outbound", reply)
            await send_telnyx_sms(phone_number, bot_number, reply)
            return

        elif cmd in ["PLAN", "RESTART"]:
            await save_trip(trip_id, {}, status="draft")
            reply = "ROAM ✈️ New trip initialized! Where would you like to go, and what dates? E.g., 'Plan a 3-day trip to NYC, budget $500.'"
            await add_conversation_message(conv_id, "outbound", reply)
            await send_telnyx_sms(phone_number, bot_number, reply)
            return

        elif cmd == "SAVE":
            await save_trip(trip_id, trip_state, status="saved")
            reply = "ROAM ✈️ Your itinerary is saved! Text ITINERARY to view your schedule at any time."
            await add_conversation_message(conv_id, "outbound", reply)
            await send_telnyx_sms(phone_number, bot_number, reply)
            return

        elif cmd == "HOTEL":
            hotel = trip_state.get("selected_hotel")
            offer = trip_state.get("selected_offer")
            if hotel and offer:
                reply = SMSFormatter.format_hotel_details(hotel, offer)
            else:
                reply = "ROAM 🏨 No hotel selected yet. Ask me to plan a trip first!"
            await add_conversation_message(conv_id, "outbound", reply)
            await send_telnyx_sms(phone_number, bot_number, reply)
            return

        elif cmd == "ITINERARY":
            itinerary = trip_state.get("itinerary")
            hotel = trip_state.get("selected_hotel")
            offer = trip_state.get("selected_offer")
            if itinerary and hotel and offer:
                trip_state["current_page_day"] = 1
                await save_trip(trip_id, trip_state, status=trip["status"])
                reply = SMSFormatter.format_itinerary_day(itinerary, hotel, offer, 1)
            else:
                reply = "ROAM ✈️ No active plan found. Tell me where you are traveling to build an itinerary!"
            await add_conversation_message(conv_id, "outbound", reply)
            await send_telnyx_sms(phone_number, bot_number, reply)
            return

        elif cmd == "NEXT":
            itinerary = trip_state.get("itinerary")
            hotel = trip_state.get("selected_hotel")
            offer = trip_state.get("selected_offer")
            if itinerary and hotel and offer:
                curr_day = trip_state.get("current_page_day", 1)
                total_days = len(itinerary.get("days", []))
                if curr_day < total_days:
                    next_day = curr_day + 1
                    trip_state["current_page_day"] = next_day
                    await save_trip(trip_id, trip_state, status=trip["status"])
                    reply = SMSFormatter.format_itinerary_day(itinerary, hotel, offer, next_day)
                else:
                    reply = "ROAM ✈️ You are already at the final day of your itinerary."
            else:
                reply = "ROAM: Ask me to plan a trip first!"
            await add_conversation_message(conv_id, "outbound", reply)
            await send_telnyx_sms(phone_number, bot_number, reply)
            return

        elif cmd == "PREV":
            itinerary = trip_state.get("itinerary")
            hotel = trip_state.get("selected_hotel")
            offer = trip_state.get("selected_offer")
            if itinerary and hotel and offer:
                curr_day = trip_state.get("current_page_day", 1)
                if curr_day > 1:
                    prev_day = curr_day - 1
                    trip_state["current_page_day"] = prev_day
                    await save_trip(trip_id, trip_state, status=trip["status"])
                    reply = SMSFormatter.format_itinerary_day(itinerary, hotel, offer, prev_day)
                else:
                    reply = "ROAM ✈️ You are at the first day of your itinerary."
            else:
                reply = "ROAM: Ask me to plan a trip first!"
            await add_conversation_message(conv_id, "outbound", reply)
            await send_telnyx_sms(phone_number, bot_number, reply)
            return

        await send_telnyx_sms(phone_number, bot_number, "ROAM ✈️ I'm researching destinations, hotels, routes, and building your plan. Give me a minute...")

        db_msgs = await get_conversation_messages(conv_id)
        messages_history = []
        for m in db_msgs[-12:]:
            content = m["message"]
            if m["direction"] == "inbound":
                messages_history.append(HumanMessage(content=content))
            else:
                messages_history.append(AIMessage(content=content))

        input_state = {
            "messages": messages_history,
            "travelers": trip_state.get("travelers", 2),
            "destination": trip_state.get("destination", ""),
            "start_date": trip_state.get("start_date", ""),
            "end_date": trip_state.get("end_date", ""),
            "interests": trip_state.get("interests", []),
            "dislikes": trip_state.get("dislikes", []),
            "budget": trip_state.get("budget", {}),
            "places": trip_state.get("places", []),
            "hotel_candidates": trip_state.get("hotel_candidates", []),
            "selected_hotel": trip_state.get("selected_hotel"),
            "selected_offer": trip_state.get("selected_offer"),
            "itinerary": trip_state.get("itinerary"),
            "issues": trip_state.get("issues", []),
            "validation_status": trip_state.get("validation_status", "uninitialized"),
            "current_goal": "understand"
        }

        final_state = await roam_graph.ainvoke(input_state)

        new_trip_state = dict(final_state)
        if "messages" in new_trip_state:
            new_trip_state.pop("messages")
            
        new_trip_state["current_page_day"] = 1
        await save_trip(trip_id, new_trip_state, status="planned" if final_state.get("itinerary") else "draft")

        itinerary = final_state.get("itinerary")
        hotel = final_state.get("selected_hotel")
        offer = final_state.get("selected_offer")

        if itinerary and hotel and offer:
            reply = SMSFormatter.format_itinerary_day(itinerary, hotel, offer, 1)
        else:
            reply = f"ROAM ✈️ {final_state['messages'][-1].content}"

        await add_conversation_message(conv_id, "outbound", reply)
        await send_telnyx_sms(phone_number, bot_number, reply)

    except Exception as e:
        logger.error("Error processing SMS background task: %s", e, exc_info=True)
        await send_telnyx_sms(phone_number, bot_number, "ROAM: Sorry, I hit an error during planning. Send PLAN to reset.")

@app.post("/api/webhooks/sms", status_code=status.HTTP_202_ACCEPTED)
async def receive_sms_webhook(request: Request, background_tasks: BackgroundTasks) -> Dict[str, str]:
    secret_header = request.headers.get("X-Roam-Secret")
    expected_secret = os.getenv("ROAM_BACKEND_SECRET", "")
    if expected_secret and secret_header != expected_secret:
        raise HTTPException(status_code=401, detail="Unauthorized webhook credentials.")

    try:
        body = await request.json()
        from_number = body.get("from_number")
        to_number = body.get("to_number")
        text = body.get("text")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid webhook body.")

    if not from_number or not text:
        raise HTTPException(status_code=422, detail="Missing required parameters from_number or text.")

    background_tasks.add_task(process_sms_background, from_number, to_number, text)
    return {"status": "accepted"}

@app.post("/api/roam")
async def chat_roam_stream(request: Request) -> StreamingResponse:
    """
    Streaming HTTP endpoint (SSE) for Web UI chatbot.
    Streams agent reasoning workflow steps and yields final state.
    """
    try:
        body = await request.json()
        message_text = body.get("message", "")
        trip_id = body.get("trip_id")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body.")

    if not message_text and not trip_id:
        raise HTTPException(status_code=422, detail="Missing message or trip_id parameter.")

    # Get active session ID
    session_id = trip_id or "web_default_session"
    conv = await get_or_create_conversation(session_id)
    conv_id = conv["id"]
    
    trip = await get_active_trip(conv_id, conv.get("active_trip_id"))
    trip_id = trip["id"]
    trip_state = trip["state_json"]

    if conv.get("active_trip_id") != trip_id:
        await update_conversation_active_trip(conv_id, trip_id)

    if message_text:
        await add_conversation_message(conv_id, "inbound", message_text)

    async def event_generator():
        logger.info(f"\n=================================================="
                    f"\n[PROMPT RECEIVED]"
                    f"\nSession ID: {session_id}"
                    f"\nTrip ID: {trip_id}"
                    f"\nUser Query: {message_text}"
                    f"\n==================================================")
        # Load conversation messages history
        db_msgs = await get_conversation_messages(conv_id)
        messages_history = []
        for m in db_msgs[-12:]:
            content = m["message"]
            if m["direction"] == "inbound":
                messages_history.append(HumanMessage(content=content))
            else:
                messages_history.append(AIMessage(content=content))

        input_state = {
            "messages": messages_history,
            "travelers": trip_state.get("travelers", 2),
            "destination": trip_state.get("destination", ""),
            "start_date": trip_state.get("start_date", ""),
            "end_date": trip_state.get("end_date", ""),
            "interests": trip_state.get("interests", []),
            "dislikes": trip_state.get("dislikes", []),
            "budget": trip_state.get("budget", {}),
            "places": trip_state.get("places", []),
            "hotel_candidates": trip_state.get("hotel_candidates", []),
            "selected_hotel": trip_state.get("selected_hotel"),
            "selected_offer": trip_state.get("selected_offer"),
            "itinerary": trip_state.get("itinerary"),
            "issues": trip_state.get("issues", []),
            "validation_status": trip_state.get("validation_status", "uninitialized"),
            "current_goal": "understand"
        }

        yield f"data: {json.dumps({'event': 'started'})}\n\n"
        
        last_state = input_state
        try:
            async for chunk in roam_graph.astream(input_state, stream_mode="updates"):
                node_name = list(chunk.keys())[0]
                node_updates = chunk[node_name]
                
                logger.info(f"[GRAPH PROGRESS] Node '{node_name}' finished.")
                logger.info(f"Node Updates: {json.dumps(node_updates, default=str)}")
                
                yield f"data: {json.dumps({'event': 'node_complete', 'node': node_name, 'updates': node_updates}, default=str)}\n\n"
                last_state.update(node_updates)
                await asyncio.sleep(0.5)

            # Reformat messages history and update state
            final_messages = []
            for msg in last_state["messages"]:
                final_messages.append({
                    "type": "human" if isinstance(msg, HumanMessage) else "ai",
                    "content": msg.content
                })
            
            # Log final AI response to database
            final_ai_msg = last_state["messages"][-1].content
            await add_conversation_message(conv_id, "outbound", final_ai_msg)
            
            db_state = dict(last_state)
            db_state["messages"] = final_messages
            
            # Save final state back to trips
            await save_trip(trip_id, db_state, status="planned" if last_state.get("itinerary") else "draft")
            
            logger.info(f"\n=================================================="
                        f"\n[PROMPT COMPLETED SUCCESSFULLY]"
                        f"\nSession ID: {session_id}"
                        f"\nItinerary Generated: {True if last_state.get('itinerary') else False}"
                        f"\n==================================================")
            
            yield f"data: {json.dumps({'event': 'completed', 'state': db_state}, default=str)}\n\n"
        except Exception as e:
            logger.error("Error in graph execution stream: %s", e, exc_info=True)
            yield f"data: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/api/trips")
async def list_trips_endpoint():
    """Retrieve list of all active/past trip conversations."""
    return await get_all_trips()

@app.get("/api/trips/{trip_id}")
async def get_trip_endpoint(trip_id: str):
    """Retrieve details for a specific trip session (used by workspace)."""
    conv = await get_or_create_conversation(trip_id)
    trip = await get_active_trip(conv["id"], conv.get("active_trip_id"))
    
    db_msgs = await get_conversation_messages(conv["id"])
    messages = [{"type": "human" if m["direction"] == "inbound" else "ai", "content": m["message"]} for m in db_msgs]
    
    response_data = dict(trip["state_json"])
    response_data["messages"] = messages
    return response_data


@app.get("/api/internal/voice/trips/{session_id}/context")
async def get_voice_trip_context_endpoint(session_id: str, request: Request):
    """Return the current server-side trip context to the dispatched voice worker."""
    require_voice_agent_auth(request)
    try:
        return await get_voice_trip_context(session_id)
    except VoiceTripNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@app.post("/api/internal/voice/trips/{session_id}/itinerary-edits")
async def reschedule_voice_itinerary_event_endpoint(
    session_id: str,
    edit: VoiceItineraryEdit,
    request: Request,
):
    """Persist one validated itinerary edit requested through the voice agent."""
    require_voice_agent_auth(request)
    try:
        return await reschedule_voice_itinerary_event(session_id, edit)
    except VoiceTripNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except VoiceItineraryConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error

def main() -> None:
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
