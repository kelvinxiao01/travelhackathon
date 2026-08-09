"""Authenticated client for the Plana planning backend.

The LiveKit worker deliberately has no Supabase credential. All trip reads and
writes travel through this small server-to-server client instead.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx


class TripBackendError(RuntimeError):
    """An actionable error returned by the planning backend."""


@dataclass(frozen=True)
class VoiceTripContext:
    session_id: str
    trip_id: str
    revision: int
    trip: dict[str, Any]


@dataclass(frozen=True)
class ItineraryUpdate:
    session_id: str
    trip_id: str
    revision: int
    summary: str


class TripBackendClient:
    def __init__(self, *, base_url: str, shared_secret: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._shared_secret = shared_secret

    @classmethod
    def from_environment(cls) -> TripBackendClient | None:
        shared_secret = os.getenv("PLANA_VOICE_AGENT_SECRET", "").strip()
        if not shared_secret:
            return None

        return cls(
            base_url=os.getenv("PLANA_BACKEND_URL", "http://127.0.0.1:8000"),
            shared_secret=shared_secret,
        )

    async def get_trip_context(self, session_id: str) -> VoiceTripContext:
        payload = await self._request(
            "GET",
            f"/api/internal/voice/trips/{quote(session_id, safe='')}/context",
        )
        trip = payload.get("trip")
        if not isinstance(trip, dict):
            raise TripBackendError(
                "The planning backend returned an invalid trip context."
            )

        return VoiceTripContext(
            session_id=_required_string(payload, "sessionId"),
            trip_id=_required_string(payload, "tripId"),
            revision=_required_revision(payload),
            trip=trip,
        )

    async def reschedule_itinerary_event(
        self,
        *,
        session_id: str,
        request_id: str,
        expected_revision: int,
        day_number: int,
        event_name: str,
        new_start_time: str,
        new_end_time: str,
    ) -> ItineraryUpdate:
        payload = await self._request(
            "POST",
            f"/api/internal/voice/trips/{quote(session_id, safe='')}/itinerary-edits",
            json={
                "request_id": request_id,
                "expected_revision": expected_revision,
                "day_number": day_number,
                "event_name": event_name,
                "new_start_time": new_start_time,
                "new_end_time": new_end_time,
            },
        )
        return ItineraryUpdate(
            session_id=_required_string(payload, "sessionId"),
            trip_id=_required_string(payload, "tripId"),
            revision=_required_revision(payload),
            summary=_required_string(payload, "summary"),
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.request(
                    method,
                    f"{self._base_url}{path}",
                    headers={"Authorization": f"Bearer {self._shared_secret}"},
                    json=json,
                )
        except httpx.HTTPError as error:
            raise TripBackendError(
                "I could not reach the trip-planning service."
            ) from error

        try:
            payload = response.json()
        except ValueError as error:
            raise TripBackendError(
                "The trip-planning service returned an invalid response."
            ) from error

        if not response.is_success:
            detail = payload.get("detail") if isinstance(payload, dict) else None
            raise TripBackendError(
                str(detail or "The trip-planning service rejected that edit.")
            )
        if not isinstance(payload, dict):
            raise TripBackendError(
                "The trip-planning service returned an invalid response."
            )
        return payload


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise TripBackendError(
            "The trip-planning service returned an invalid response."
        )
    return value


def _required_revision(payload: dict[str, Any]) -> int:
    value = payload.get("revision")
    if not isinstance(value, int) or value < 0:
        raise TripBackendError(
            "The trip-planning service returned an invalid response."
        )
    return value
