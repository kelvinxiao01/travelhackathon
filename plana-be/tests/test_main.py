from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_health_check_reports_service_ready() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_inbound_telnyx_message_is_acknowledged() -> None:
    response = client.post(
        "/webhooks/telnyx/inbound",
        json={
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
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
