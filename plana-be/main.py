"""HTTP endpoints for receiving Telnyx messaging webhooks."""

import json
import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status


logger = logging.getLogger(__name__)

app = FastAPI(title="Plana messaging webhook")


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Return service readiness for local and tunnel checks."""
    return {"status": "ok"}


@app.post("/webhooks/telnyx/inbound", status_code=status.HTTP_200_OK)
async def receive_telnyx_message(request: Request) -> dict[str, str]:
    """Acknowledge inbound Telnyx messages without blocking webhook delivery."""
    try:
        event = json.loads(await request.body())
    except json.JSONDecodeError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body must be valid JSON.",
        ) from error

    if not isinstance(event, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook payload must be a JSON object.",
        )

    data = event.get("data")
    if not isinstance(data, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook payload is missing a data object.",
        )

    if data.get("event_type") != "message.received":
        logger.info("Ignoring Telnyx event type %r", data.get("event_type"))
        return {"status": "accepted"}

    payload: Any = data.get("payload")
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inbound message is missing a payload object.",
        )

    logger.info(
        "Received inbound Telnyx message event_id=%s message_id=%s type=%s media_count=%s",
        data.get("id"),
        payload.get("id"),
        payload.get("type"),
        len(payload.get("media") or []),
    )

    return {"status": "accepted"}
