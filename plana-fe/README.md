# Plana frontend

The browser connects to the Plan A voice agent through a short-lived LiveKit room
token. The browser receives no Google credential: the Python worker uses
`GOOGLE_API_KEY` to connect directly to Gemini Live.

## Local setup

1. Copy `.env.example` to `.env.local`.
2. Set `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET` to the same
   LiveKit project used by `plana-voice`.
3. Start the Python worker from `plana-voice` with `uv run python src/agent.py dev`.
4. Start this app with `npm run dev`, then click **Talk to Plan A**.

`LIVEKIT_AGENT_NAME` defaults to `plana-voice`, matching the worker registration in
`plana-voice/src/agent.py`.

## Verification

```bash
npm run lint
npm run build -- --webpack
```

The standard production build is `npm run build`; the webpack form is also useful in
restricted local environments where Turbopack cannot open its helper port.
