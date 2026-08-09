import os
import json
import uuid
import logging
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
import httpx
import urllib.parse

logger = logging.getLogger(__name__)

SQLITE_DB = "roam.db"

def init_sqlite():
    """Initialize local SQLite database with the new multi-table schema."""
    conn = sqlite3.connect(SQLITE_DB)
    cursor = conn.cursor()
    
    # Create conversations
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            phone_number TEXT UNIQUE NOT NULL,
            active_trip_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create messages
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            direction TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
    """)
    
    # Create trips
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trips (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            state_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
    """)
    
    conn.commit()
    conn.close()

# Initialize database schema immediately
init_sqlite()

def get_supabase_client() -> Tuple[Optional[str], Optional[Dict[str, str]]]:
    """Helper to get Supabase URL and headers if configured."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if url and key:
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
        return url.rstrip("/"), headers
    return None, None

async def get_or_create_conversation(phone_number: str) -> Dict[str, Any]:
    """Retrieve or create a conversation record by phone number."""
    url, headers = get_supabase_client()
    
    if url and headers:
        async with httpx.AsyncClient() as client:
            try:
                # 1. Try to fetch conversation
                fetch_url = f"{url}/rest/v1/conversations?phone_number=eq.{urllib.parse.quote(phone_number)}"
                res = await client.get(fetch_url, headers=headers)
                res.raise_for_status()
                data = res.json()
                if data:
                    return data[0]
                
                # 2. Not found, create conversation
                insert_payload = {
                    "id": str(uuid.uuid4()),
                    "phone_number": phone_number
                }
                res = await client.post(f"{url}/rest/v1/conversations", headers=headers, json=insert_payload)
                res.raise_for_status()
                data = res.json()
                if data:
                    return data[0]
            except Exception as e:
                logger.error("Supabase conversation fetch/create error: %s", e)
                
    # Local SQLite Fallback
    logger.info("Using local SQLite to get/create conversation: %s", phone_number)
    conn = sqlite3.connect(SQLITE_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM conversations WHERE phone_number = ?", (phone_number,))
    row = cursor.fetchone()
    
    if row:
        res = dict(row)
        conn.close()
        return res
        
    # Create new
    conv_id = str(uuid.uuid4())
    cursor.execute(
        "INSERT INTO conversations (id, phone_number) VALUES (?, ?)",
        (conv_id, phone_number)
    )
    conn.commit()
    
    cursor.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,))
    row = cursor.fetchone()
    res = dict(row)
    conn.close()
    return res

async def update_conversation_active_trip(conversation_id: str, trip_id: str) -> None:
    """Link the active trip to a conversation."""
    url, headers = get_supabase_client()
    
    if url and headers:
        async with httpx.AsyncClient() as client:
            try:
                patch_url = f"{url}/rest/v1/conversations?id=eq.{conversation_id}"
                await client.patch(patch_url, headers=headers, json={"active_trip_id": trip_id})
                return
            except Exception as e:
                logger.error("Supabase active trip update error: %s", e)
                
    # SQLite fallback
    conn = sqlite3.connect(SQLITE_DB)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE conversations SET active_trip_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (trip_id, conversation_id)
    )
    conn.commit()
    conn.close()

async def get_conversation_messages(conversation_id: str) -> List[Dict[str, Any]]:
    """Retrieve message logs for a conversation."""
    url, headers = get_supabase_client()
    
    if url and headers:
        async with httpx.AsyncClient() as client:
            try:
                fetch_url = f"{url}/rest/v1/messages?conversation_id=eq.{conversation_id}&order=created_at.asc"
                res = await client.get(fetch_url, headers=headers)
                if res.status_code == 200:
                    return res.json()
            except Exception as e:
                logger.error("Supabase messages query error: %s", e)
                
    # SQLite fallback
    conn = sqlite3.connect(SQLITE_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC", (conversation_id,))
    rows = cursor.fetchall()
    res = [dict(row) for row in rows]
    conn.close()
    return res

async def add_conversation_message(conversation_id: str, direction: str, message: str) -> None:
    """Save an inbound or outbound message."""
    url, headers = get_supabase_client()
    
    if url and headers:
        async with httpx.AsyncClient() as client:
            try:
                payload = {
                    "id": str(uuid.uuid4()),
                    "conversation_id": conversation_id,
                    "direction": direction,
                    "message": message
                }
                res = await client.post(f"{url}/rest/v1/messages", headers=headers, json=payload)
                res.raise_for_status()
                return
            except Exception as e:
                logger.error("Supabase add message error: %s", e)
                
    # SQLite fallback
    conn = sqlite3.connect(SQLITE_DB)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO messages (id, conversation_id, direction, message) VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), conversation_id, direction, message)
    )
    conn.commit()
    conn.close()

async def get_active_trip(conversation_id: str, active_trip_id: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve or create the active trip JSON state."""
    url, headers = get_supabase_client()
    
    if url and headers:
        async with httpx.AsyncClient() as client:
            try:
                trip = None
                if active_trip_id:
                    # Fetch specific trip
                    res = await client.get(f"{url}/rest/v1/trips?id=eq.{active_trip_id}", headers=headers)
                    res.raise_for_status()
                    if res.json():
                        trip = res.json()[0]
                else:
                    # Fetch latest trip
                    res = await client.get(
                        f"{url}/rest/v1/trips?conversation_id=eq.{conversation_id}&order=updated_at.desc&limit=1",
                        headers=headers
                    )
                    res.raise_for_status()
                    if res.json():
                        trip = res.json()[0]
                        
                if trip:
                    # Make sure state_json is loaded if it is returned as string
                    state = trip["state_json"]
                    if isinstance(state, str):
                        trip["state_json"] = json.loads(state)
                    return trip
                
                # None found, create a new draft trip
                new_id = str(uuid.uuid4())
                payload = {
                    "id": new_id,
                    "conversation_id": conversation_id,
                    "state_json": {},
                    "status": "draft"
                }
                res = await client.post(f"{url}/rest/v1/trips", headers=headers, json=payload)
                res.raise_for_status()
                if res.json():
                    return res.json()[0]
            except Exception as e:
                logger.error("Supabase active trip retrieval error: %s", e)
                
    # SQLite fallback
    conn = sqlite3.connect(SQLITE_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    row = None
    if active_trip_id:
        cursor.execute("SELECT * FROM trips WHERE id = ?", (active_trip_id,))
        row = cursor.fetchone()
    else:
        cursor.execute("SELECT * FROM trips WHERE conversation_id = ? ORDER BY updated_at DESC LIMIT 1", (conversation_id,))
        row = cursor.fetchone()
        
    if row:
        res = dict(row)
        res["state_json"] = json.loads(res["state_json"])
        conn.close()
        return res
        
    # Create new
    new_id = str(uuid.uuid4())
    cursor.execute(
        "INSERT INTO trips (id, conversation_id, state_json, status) VALUES (?, ?, ?, ?)",
        (new_id, conversation_id, "{}", "draft")
    )
    conn.commit()
    
    cursor.execute("SELECT * FROM trips WHERE id = ?", (new_id,))
    row = cursor.fetchone()
    res = dict(row)
    res["state_json"] = json.loads(res["state_json"])
    conn.close()
    return res

async def save_trip(trip_id: str, state: Dict[str, Any], status: str = "draft") -> None:
    """Save updated trip state JSON."""
    url, headers = get_supabase_client()
    serialized_state = json.loads(json.dumps(state, default=str))
    
    if url and headers:
        async with httpx.AsyncClient() as client:
            try:
                patch_url = f"{url}/rest/v1/trips?id=eq.{trip_id}"
                payload = {
                    "state_json": serialized_state,
                    "status": status
                }
                res = await client.patch(patch_url, headers=headers, json=payload)
                res.raise_for_status()
                return
            except Exception as e:
                logger.error("Supabase save trip error: %s", e)
                
    # SQLite fallback
    conn = sqlite3.connect(SQLITE_DB)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE trips SET state_json = ?, status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (json.dumps(serialized_state), status, trip_id)
    )
    conn.commit()
    conn.close()

async def get_all_trips() -> List[Dict[str, Any]]:
    """Retrieve all trips (with their corresponding phone_number/name)."""
    url, headers = get_supabase_client()
    
    if url and headers:
        async with httpx.AsyncClient() as client:
            try:
                # Query trips join conversation
                fetch_url = f"{url}/rest/v1/trips?select=*,conversations(phone_number)"
                res = await client.get(fetch_url, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    trips = []
                    for t in data:
                        conv = t.get("conversations", {})
                        phone = conv.get("phone_number") if isinstance(conv, dict) else ""
                        trips.append({
                            "id": t["id"],
                            "phone_number": phone,
                            "status": t["status"],
                            "created_at": t["created_at"],
                            "state_json": t["state_json"] if not isinstance(t["state_json"], str) else json.loads(t["state_json"])
                        })
                    return trips
            except Exception as e:
                logger.error("Supabase get_all_trips error: %s", e)
                
    # SQLite Fallback
    conn = sqlite3.connect(SQLITE_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT trips.id, trips.status, trips.created_at, trips.state_json, conversations.phone_number
        FROM trips
        JOIN conversations ON trips.conversation_id = conversations.id
        ORDER BY trips.updated_at DESC
    """)
    rows = cursor.fetchall()
    trips = []
    for r in rows:
        try:
            state = json.loads(r["state_json"])
        except Exception:
            state = {}
        trips.append({
            "id": r["id"],
            "phone_number": r["phone_number"],
            "status": r["status"],
            "created_at": r["created_at"],
            "state_json": state
        })
    conn.close()
    return trips
