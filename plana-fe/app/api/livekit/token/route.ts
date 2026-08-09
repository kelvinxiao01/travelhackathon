import { randomUUID } from "node:crypto";

import { RoomAgentDispatch, RoomConfiguration } from "@livekit/protocol";
import { AccessToken } from "livekit-server-sdk";

export const runtime = "nodejs";

const DEFAULT_AGENT_NAME = "plana-voice";

function requiredEnvironmentVariable(name: string): string | null {
  const value = process.env[name];
  return value?.trim() || null;
}

export async function POST() {
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
      }),
    ],
  });

  return Response.json({
    participantToken: await token.toJwt(),
    serverUrl,
  });
}
