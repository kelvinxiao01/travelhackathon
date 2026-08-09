import { randomUUID } from "node:crypto";

import { RoomAgentDispatch, RoomConfiguration } from "@livekit/protocol";
import { AccessToken } from "livekit-server-sdk";

export const runtime = "nodejs";

const DEFAULT_AGENT_NAME = "plana-voice";
const MAX_SESSION_ID_LENGTH = 200;

function requiredEnvironmentVariable(name: string): string | null {
  const value = process.env[name];
  return value?.trim() || null;
}

function sessionIdFromBody(body: unknown): string | null {
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return null;
  }

  const sessionId = (body as Record<string, unknown>).sessionId;
  if (typeof sessionId !== "string") {
    return null;
  }

  const normalized = sessionId.trim();
  return normalized && normalized.length <= MAX_SESSION_ID_LENGTH
    ? normalized
    : null;
}

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "A trip session is required." }, { status: 400 });
  }

  const sessionId = sessionIdFromBody(body);
  if (!sessionId) {
    return Response.json(
      { error: "Start a trip in the planner before opening a voice session." },
      { status: 422 },
    );
  }

  const serverUrl = requiredEnvironmentVariable("LIVEKIT_URL");
  const apiKey = requiredEnvironmentVariable("LIVEKIT_API_KEY");
  const apiSecret = requiredEnvironmentVariable("LIVEKIT_API_SECRET");

  if (!serverUrl || !apiKey || !apiSecret) {
    return Response.json(
      { error: "LiveKit is not configured on the server." },
      { status: 503 },
    );
  }

  const roomName = `plana-voice-${randomUUID()}`;
  const participantIdentity = `guest-${randomUUID()}`;
  const token = new AccessToken(apiKey, apiSecret, {
    identity: participantIdentity,
    name: "Plan A guest",
    ttl: "10m",
  });

  token.addGrant({
    canPublish: true,
    canSubscribe: true,
    room: roomName,
    roomJoin: true,
  });
  token.roomConfig = new RoomConfiguration({
    agents: [
      new RoomAgentDispatch({
        agentName: process.env.LIVEKIT_AGENT_NAME?.trim() || DEFAULT_AGENT_NAME,
        metadata: JSON.stringify({ sessionId }),
      }),
    ],
  });

  return Response.json({
    participantToken: await token.toJwt(),
    serverUrl,
  });
}
