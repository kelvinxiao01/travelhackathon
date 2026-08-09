import base64
import json
import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

import main


client = TestClient(main.app)


@pytest.fixture(autouse=True)
def _clear_processed_message_ids() -> None:
    main.processed_message_ids.clear()


def _signed_webhook_payload(event: dict[str, object]) -> tuple[bytes, dict[str, str]]:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    body = json.dumps(event, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    signature = private_key.sign(timestamp.encode() + b"|" + body)

    return body, {
        "content-type": "application/json",
        "telnyx-timestamp": timestamp,
        "telnyx-signature-ed25519": base64.b64encode(signature).decode(),
        "x-test-telnyx-public-key": base64.b64encode(public_key).decode(),
    }


def test_health_check_reports_service_ready() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_inbound_message_generates_and_sends_a_reply(monkeypatch) -> None:
    sent_messages: list[dict[str, str]] = []

    async def generate_agent_reply(inbound_text: str) -> str:
        assert inbound_text == "Help me plan a trip"
        return "Where would you like to go?"

    def send_sms_reply(
        *, from_phone_number: str, to_phone_number: str, text: str
    ) -> None:
        sent_messages.append(
            {
                "from_phone_number": from_phone_number,
                "to_phone_number": to_phone_number,
                "text": text,
            }
        )

    monkeypatch.setattr(main, "generate_agent_reply", generate_agent_reply)
    monkeypatch.setattr(main, "send_sms_reply", send_sms_reply)

    event = {
        "data": {
            "event_type": "message.received",
            "id": "event-123",
            "payload": {
                "id": "message-123",
                "direction": "inbound",
                "from": {"phone_number": "+15555550100"},
                "to": [{"phone_number": "+13472738658"}],
                "text": "Help me plan a trip",
                "type": "SMS",
            },
        }
    }
    body, headers = _signed_webhook_payload(event)
    monkeypatch.setenv("TELNYX_PUBLIC_KEY", headers.pop("x-test-telnyx-public-key"))

    response = client.post("/webhooks/telnyx/inbound", content=body, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    assert sent_messages == [
        {
            "from_phone_number": "+13472738658",
            "to_phone_number": "+15555550100",
            "text": "Where would you like to go?",
        }
    ]


def test_webhook_rejects_an_unsigned_message(monkeypatch) -> None:
    body, headers = _signed_webhook_payload(
        {"data": {"event_type": "message.received", "payload": {}}}
    )
    monkeypatch.setenv("TELNYX_PUBLIC_KEY", headers.pop("x-test-telnyx-public-key"))
    headers.pop("telnyx-timestamp")
    headers.pop("telnyx-signature-ed25519")

    response = client.post("/webhooks/telnyx/inbound", content=body, headers=headers)

    assert response.status_code == 403


def test_telnyx_stop_is_acknowledged_without_an_agent_reply(monkeypatch) -> None:
    async def generate_agent_reply(_: str) -> str:
        raise AssertionError("An opt-out keyword must not reach the agent.")

    monkeypatch.setattr(main, "generate_agent_reply", generate_agent_reply)
    body, headers = _signed_webhook_payload(
        {
            "data": {
                "event_type": "message.received",
                "id": "event-stop",
                "payload": {"autoresponse_type": "STOP", "text": "STOP"},
            }
        }
    )
    monkeypatch.setenv("TELNYX_PUBLIC_KEY", headers.pop("x-test-telnyx-public-key"))

    response = client.post("/webhooks/telnyx/inbound", content=body, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}


def test_outbound_delivery_failures_are_logged(monkeypatch, caplog) -> None:
    body, headers = _signed_webhook_payload(
        {
            "data": {
                "event_type": "message.finalized",
                "id": "event-finalized",
                "payload": {
                    "direction": "outbound",
                    "id": "message-finalized",
                    "to": [{"status": "delivery_failed"}],
                    "errors": [{"code": "47000"}],
                },
            }
        }
    )
    monkeypatch.setenv("TELNYX_PUBLIC_KEY", headers.pop("x-test-telnyx-public-key"))

    response = client.post("/webhooks/telnyx/inbound", content=body, headers=headers)

    assert response.status_code == 200
    assert "Telnyx outbound delivery failed" in caplog.text
    assert "47000" in caplog.text
