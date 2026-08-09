"""Receive Telnyx messages and send a minimal Agent SDK reply."""

import asyncio
import base64
import binascii
import json
import logging
import os
import time
from typing import Any

import uvicorn
from agents import Agent, Runner
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, status
from telnyx import Telnyx


logger = logging.getLogger(__name__)

WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS = 300
AUTORESPONSE_TYPES = {"START", "STOP", "HELP"}
processed_message_ids: set[str] = set()

plan_a_agent = Agent(
    name="Plan A",
    instructions=(
        "You are Plan A, a helpful travel-planning assistant communicating by SMS. "
        "Reply concisely, in plain text, and ask a useful next question when needed."
    ),
)

app = FastAPI(title="Plana messaging webhook")


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Return service readiness for local and tunnel checks."""
    return {"status": "ok"}


def verify_telnyx_signature(body: bytes, request: Request) -> None:
    """Reject webhook requests that are not recent, signed Telnyx events."""
    public_key = os.getenv("TELNYX_PUBLIC_KEY")
    if not public_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TELNYX_PUBLIC_KEY is not configured.",
        )

    signature = request.headers.get("telnyx-signature-ed25519")
    timestamp = request.headers.get("telnyx-timestamp")
    if not signature or not timestamp:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing Telnyx webhook signature.",
        )

    try:
        timestamp_value = int(timestamp)
        if abs(time.time() - timestamp_value) > WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS:
            raise ValueError("Webhook timestamp is outside the accepted window.")

        public_key_bytes = base64.b64decode(public_key.strip(), validate=True)
        signature_bytes = base64.b64decode(signature, validate=True)
        signed_payload = timestamp.encode() + b"|" + body
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(
            signature_bytes,
            signed_payload,
        )
    except (binascii.Error, InvalidSignature, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Telnyx webhook signature.",
        ) from error


async def generate_agent_reply(inbound_text: str) -> str:
    """Run the single-turn travel agent for an inbound text message."""
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    result = await Runner.run(plan_a_agent, inbound_text)
    return str(result.final_output).strip()


def send_sms_reply(*, from_phone_number: str, to_phone_number: str, text: str) -> None:
    """Send a plain-text reply from the Telnyx number that received the message."""
    api_key = os.getenv("TELNYX_API_KEY")
    if not api_key:
        raise RuntimeError("TELNYX_API_KEY is not configured.")

    Telnyx(api_key=api_key).messages.send(
        from_=from_phone_number,
        to=to_phone_number,
        text=text,
    )


async def reply_to_inbound_message(
    *,
    message_id: str,
    sender_phone_number: str,
    recipient_phone_number: str,
    inbound_text: str,
) -> None:
    """Generate and send a reply after the webhook has been acknowledged."""
    try:
        reply_text = await generate_agent_reply(inbound_text)
        if not reply_text:
            logger.warning("Agent returned an empty reply message_id=%s", message_id)
            return

        await asyncio.to_thread(
            send_sms_reply,
            from_phone_number=recipient_phone_number,
            to_phone_number=sender_phone_number,
            text=reply_text,
        )
        logger.info("Sent agent reply message_id=%s", message_id)
    except Exception:
        logger.exception("Could not send agent reply message_id=%s", message_id)


def log_outbound_delivery_failure(data: dict[str, Any]) -> None:
    """Log failed carrier delivery without recording message contents or numbers."""
    payload = data.get("payload")
    if not isinstance(payload, dict) or payload.get("direction") != "outbound":
        return

    recipients = payload.get("to")
    statuses = (
        {
            recipient["status"]
            for recipient in recipients
            if isinstance(recipient, dict) and isinstance(recipient.get("status"), str)
        }
        if isinstance(recipients, list)
        else set()
    )
    if not statuses.intersection({"delivery_failed", "sending_failed"}):
        return

    errors = payload.get("errors")
    error_codes = (
        [
            error["code"]
            for error in errors
            if isinstance(error, dict) and error.get("code") is not None
        ]
        if isinstance(errors, list)
        else []
    )
    logger.warning(
        "Telnyx outbound delivery failed event_id=%s message_id=%s statuses=%s "
        "error_codes=%s",
        data.get("id"),
        payload.get("id"),
        sorted(statuses),
        error_codes,
    )


@app.post("/webhooks/telnyx/inbound", status_code=status.HTTP_200_OK)
async def receive_telnyx_message(
    request: Request, background_tasks: BackgroundTasks
) -> dict[str, str]:
    """Verify and acknowledge inbound texts, then reply asynchronously."""
    body = await request.body()
    verify_telnyx_signature(body, request)

    try:
        event = json.loads(body)
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

    event_type = data.get("event_type")
    if event_type != "message.received":
        if event_type == "message.finalized":
            log_outbound_delivery_failure(data)
        else:
            logger.info("Ignoring Telnyx event type %r", event_type)
        return {"status": "accepted"}

    payload: Any = data.get("payload")
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inbound message is missing a payload object.",
        )

    if payload.get("autoresponse_type") in AUTORESPONSE_TYPES:
        logger.info("Ignoring Telnyx auto-response event_id=%s", data.get("id"))
        return {"status": "accepted"}

    message_id = payload.get("id")
    if not isinstance(message_id, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inbound message is missing an id.",
        )

    sender = payload.get("from")
    recipients = payload.get("to")
    if not isinstance(sender, dict) or not isinstance(recipients, list) or not recipients:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inbound message is missing phone number details.",
        )

    recipient = recipients[0]
    sender_phone_number = sender.get("phone_number")
    recipient_phone_number = (
        recipient.get("phone_number") if isinstance(recipient, dict) else None
    )
    if not isinstance(sender_phone_number, str) or not isinstance(
        recipient_phone_number, str
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inbound message phone numbers must be strings.",
        )

    inbound_text = payload.get("text")
    if not isinstance(inbound_text, str) or not inbound_text.strip():
        logger.info("Ignoring message without text message_id=%s", message_id)
        return {"status": "accepted"}

    if message_id in processed_message_ids:
        logger.info("Ignoring duplicate Telnyx message message_id=%s", message_id)
        return {"status": "accepted"}

    processed_message_ids.add(message_id)
    logger.info(
        "Received inbound Telnyx message event_id=%s message_id=%s type=%s media_count=%s",
        data.get("id"),
        message_id,
        payload.get("type"),
        len(payload.get("media") or []),
    )
    background_tasks.add_task(
        reply_to_inbound_message,
        message_id=message_id,
        sender_phone_number=sender_phone_number,
        recipient_phone_number=recipient_phone_number,
        inbound_text=inbound_text.strip(),
    )

    return {"status": "accepted"}


def main() -> None:
    """Start the local webhook server."""
    uvicorn.run("main:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
