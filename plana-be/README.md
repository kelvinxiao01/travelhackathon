# Plana inbound messaging webhook

This service receives Telnyx inbound SMS and MMS webhooks. It only acknowledges
and logs safe metadata; it does not create an agent or send replies.

## Run locally

```bash
uv run main.py
```

In another terminal, confirm the service is available:

```bash
curl http://localhost:8000/health
```

Then expose it through ngrok:

```bash
ngrok http 8000
```

In Telnyx, set the Messaging Profile's **Inbound → Webhook URL** to:

```text
https://YOUR-NGROK-DOMAIN/webhooks/telnyx/inbound
```

Leave the failover URL blank for now. Telnyx should receive an HTTP 200 for an
inbound `message.received` event.

## Test

```bash
uv run python -m pytest
```

## Before production

Verify Telnyx's webhook signature before acting on message contents. The current
endpoint deliberately keeps that configuration out of this transport-only slice.
