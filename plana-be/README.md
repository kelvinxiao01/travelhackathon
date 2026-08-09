# Plana SMS reply service

This service receives a Telnyx `message.received` webhook, acknowledges it
immediately, generates one reply with the OpenAI Agents SDK, and sends that
reply back through Telnyx. It intentionally has no conversation storage or
media processing yet.

## Configure

Set these server-only environment variables before testing:

```bash
export OPENAI_API_KEY="..."
export TELNYX_API_KEY="..."
export TELNYX_PUBLIC_KEY="..."
```

- `OPENAI_API_KEY` authorizes the OpenAI Agents SDK.
- `TELNYX_API_KEY` authorizes the outbound SMS API call.
- `TELNYX_PUBLIC_KEY` is the Base64 public key from Telnyx **Account Settings →
  Keys & Credentials → Public Key**. It verifies inbound webhook signatures;
  it is not a secret.

Keep the first two values out of source control and out of the frontend.

## Run locally

```bash
uv run main.py
```

In another terminal, expose the server:

```bash
ngrok http 8000
```

In Telnyx, configure the Messaging Profile's **Inbound → Webhook URL** as:

```text
https://YOUR-NGROK-DOMAIN/webhooks/telnyx/inbound
```

Leave the failover URL blank for this local setup. The endpoint returns HTTP
200 before it contacts OpenAI or Telnyx, so it meets Telnyx's short webhook
acknowledgement window.

## Telnyx requirements for outbound replies

Before sending a real reply to a US mobile number:

1. In this profile's **Allowed destinations** tab, include `US`.
2. Keep the profile enabled, on webhook API version 2, with
   `+1-347-273-8658` assigned as its sender.
3. Create an API key in Telnyx and use it only as `TELNYX_API_KEY` on this
   backend.
4. For the US local number, register the brand and an approved 10DLC campaign,
   then assign this number to that campaign. Use a truthful **Customer Care**
   use case only for user-initiated travel-planning conversations; use a
   broader use case such as **Mixed** if you later add proactive reminders or
   marketing.
5. Keep Telnyx's `STOP`, `START`, and `HELP` handling enabled in the profile's
   **Keywords** settings. The service intentionally does not send an agent
   response to those events.

Without the campaign assignment, Telnyx can accept the API request but the
carrier may reject delivery with error `47000`.

## Behaviour and limits

- Replies use the same Telnyx number that received the message.
- `message.sent` events are acknowledged and ignored; failed outbound
  `message.finalized` events are logged without message text or phone numbers.
- Telnyx `STOP`, `START`, and `HELP` auto-response events are acknowledged
  without an agent reply.
- Duplicate inbound message IDs are ignored for the lifetime of the process.
- Media-only MMS is acknowledged but not passed to the agent yet.
- This is best-effort local processing: durable retries, cross-process
  deduplication, and conversation persistence are intentionally deferred.

## Test

```bash
uv run python -m pytest
```
