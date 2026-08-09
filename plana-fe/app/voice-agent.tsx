"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Room, RoomEvent, Track, type RemoteTrack } from "livekit-client";
import { useTripSession, type VoiceTripUpdate } from "./trip-session-context";

type VoiceStatus = "idle" | "connecting" | "connected" | "error";

type AgentActivity =
  | "initializing"
  | "idle"
  | "listening"
  | "thinking"
  | "speaking";

type VoiceTokenResponse = {
  participantToken: string;
  serverUrl: string;
};

function MicrophoneIcon({ muted }: { muted: boolean }) {
  return (
    <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M8.5 21h7" />
      {muted && <path d="m4 4 16 16" />}
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">
      <path d="m6 6 12 12M18 6 6 18" />
    </svg>
  );
}

async function requestVoiceToken(
  sessionId: string,
): Promise<VoiceTokenResponse> {
  const response = await fetch("/api/livekit/token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sessionId }),
  });
  const body = (await response.json()) as Partial<VoiceTokenResponse> & {
    error?: string;
  };

  if (!response.ok || !body.participantToken || !body.serverUrl) {
    throw new Error(body.error ?? "Plan A could not start a voice session.");
  }

  return {
    participantToken: body.participantToken,
    serverUrl: body.serverUrl,
  };
}

function voiceErrorMessage(error: unknown): string {
  if (error instanceof DOMException && error.name === "NotAllowedError") {
    return "Allow microphone access to talk with Plan A.";
  }

  if (error instanceof Error && error.message) {
    return error.message;
  }

  return "Plan A could not start a voice session.";
}

function isAgentActivity(value: string | undefined): value is AgentActivity {
  return ["initializing", "idle", "listening", "thinking", "speaking"].includes(
    value ?? "",
  );
}

function currentAgentActivity(room: Room): AgentActivity | null {
  const agent = Array.from(room.remoteParticipants.values()).find(
    (participant) => participant.isAgent,
  );

  if (!agent) {
    return null;
  }

  const state = agent.attributes["lk.agent.state"];
  return isAgentActivity(state) ? state : "initializing";
}

function isVoiceTripUpdate(value: unknown): value is VoiceTripUpdate {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }

  const update = value as Record<string, unknown>;
  return (
    update.type === "trip.updated" &&
    typeof update.sessionId === "string" &&
    typeof update.revision === "number" &&
    typeof update.summary === "string"
  );
}

export default function VoiceAgent() {
  const { sessionId, publishVoiceTripUpdate } = useTripSession();
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus>("idle");
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [hasMicrophoneTrack, setHasMicrophoneTrack] = useState(false);
  const [isMicrophoneMuted, setIsMicrophoneMuted] = useState(true);
  const [isAgentSpeaking, setIsAgentSpeaking] = useState(false);
  const [agentActivity, setAgentActivity] = useState<AgentActivity | null>(null);
  const connectionAttempt = useRef(0);
  const boundSessionId = useRef<string | null>(null);
  const roomRef = useRef<Room | null>(null);
  const remoteAudioElements = useRef(new Set<HTMLMediaElement>());

  const clearRemoteAudio = useCallback(() => {
    for (const audioElement of remoteAudioElements.current) {
      audioElement.remove();
    }
    remoteAudioElements.current.clear();
  }, []);

  const attachRemoteAudio = useCallback((track: RemoteTrack) => {
    if (track.kind !== Track.Kind.Audio) {
      return;
    }

    const audioElement = track.attach();
    audioElement.autoplay = true;
    audioElement.setAttribute("data-livekit-audio", "true");
    document.body.appendChild(audioElement);
    remoteAudioElements.current.add(audioElement);
  }, []);

  const detachRemoteAudio = useCallback((track: RemoteTrack) => {
    if (track.kind !== Track.Kind.Audio) {
      return;
    }

    for (const audioElement of track.detach()) {
      audioElement.remove();
      remoteAudioElements.current.delete(audioElement);
    }
  }, []);

  const resetVoiceState = useCallback(() => {
    setHasMicrophoneTrack(false);
    setIsMicrophoneMuted(true);
    setIsAgentSpeaking(false);
    setAgentActivity(null);
  }, []);

  const stopVoiceSession = useCallback(async () => {
    connectionAttempt.current += 1;
    const room = roomRef.current;
    roomRef.current = null;
    boundSessionId.current = null;
    clearRemoteAudio();
    resetVoiceState();

    try {
      await room?.disconnect();
    } finally {
      setVoiceError(null);
      setVoiceStatus("idle");
    }
  }, [clearRemoteAudio, resetVoiceState]);

  const startVoiceSession = useCallback(async () => {
    if (roomRef.current || voiceStatus === "connecting") {
      return;
    }
    if (!sessionId) {
      setVoiceError("Start a trip in the planner before using voice edits.");
      setVoiceStatus("error");
      return;
    }

    const attempt = connectionAttempt.current + 1;
    connectionAttempt.current = attempt;
    boundSessionId.current = sessionId;
    setVoiceError(null);
    resetVoiceState();
    setVoiceStatus("connecting");

    let room: Room | null = null;

    try {
      const voiceRoom = new Room({ adaptiveStream: true, dynacast: true });
      room = voiceRoom;
      roomRef.current = voiceRoom;

      const syncMicrophoneState = () => {
        if (roomRef.current !== voiceRoom) {
          return;
        }

        const publication = voiceRoom.localParticipant.getTrackPublication(
          Track.Source.Microphone,
        );
        const hasLiveTrack = Boolean(
          publication?.audioTrack &&
            !publication.isUpstreamPaused &&
            publication.audioTrack.mediaStreamTrack.readyState === "live",
        );

        setHasMicrophoneTrack(hasLiveTrack);
        setIsMicrophoneMuted(!voiceRoom.localParticipant.isMicrophoneEnabled);
      };

      const syncAgentState = () => {
        if (roomRef.current !== voiceRoom) {
          return;
        }

        setAgentActivity(currentAgentActivity(voiceRoom));
        setIsAgentSpeaking(
          Array.from(voiceRoom.remoteParticipants.values()).some(
            (participant) => participant.isAgent && participant.isSpeaking,
          ),
        );
      };

      voiceRoom.on(RoomEvent.TrackSubscribed, attachRemoteAudio);
      voiceRoom.on(RoomEvent.TrackUnsubscribed, detachRemoteAudio);
      voiceRoom.on(RoomEvent.LocalTrackPublished, (publication) => {
        if (publication.source === Track.Source.Microphone) {
          syncMicrophoneState();
        }
      });
      voiceRoom.on(RoomEvent.LocalTrackUnpublished, (publication) => {
        if (publication.source === Track.Source.Microphone) {
          syncMicrophoneState();
        }
      });
      voiceRoom.on(RoomEvent.TrackMuted, (publication, participant) => {
        if (
          participant.isLocal &&
          publication.source === Track.Source.Microphone
        ) {
          syncMicrophoneState();
        }
      });
      voiceRoom.on(RoomEvent.TrackUnmuted, (publication, participant) => {
        if (
          participant.isLocal &&
          publication.source === Track.Source.Microphone
        ) {
          syncMicrophoneState();
        }
      });
      voiceRoom.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
        if (roomRef.current !== voiceRoom) {
          return;
        }

        setIsAgentSpeaking(speakers.some((participant) => participant.isAgent));
      });
      voiceRoom.on(RoomEvent.ParticipantConnected, syncAgentState);
      voiceRoom.on(RoomEvent.ParticipantDisconnected, syncAgentState);
      voiceRoom.on(
        RoomEvent.DataReceived,
        (payload, participant, _kind, topic) => {
          if (
            roomRef.current !== voiceRoom ||
            !participant?.isAgent ||
            topic !== "plana.trip.updated"
          ) {
            return;
          }

          try {
            const update = JSON.parse(new TextDecoder().decode(payload)) as unknown;
            if (isVoiceTripUpdate(update) && update.sessionId === sessionId) {
              publishVoiceTripUpdate(update);
            }
          } catch {
            // Ignore unrelated or malformed room data. Audio should remain usable.
          }
        },
      );
      voiceRoom.on(
        RoomEvent.ParticipantAttributesChanged,
        (_changedAttributes, participant) => {
          if (participant.isAgent) {
            syncAgentState();
          }
        },
      );
      voiceRoom.on(RoomEvent.Disconnected, () => {
        if (roomRef.current !== voiceRoom) {
          return;
        }

        roomRef.current = null;
        boundSessionId.current = null;
        clearRemoteAudio();
        resetVoiceState();
        setVoiceError(null);
        setVoiceStatus("idle");
      });

      // Start playback before the first await to retain the initiating click's
      // browser user gesture on strict autoplay platforms.
      const unlockAudio = voiceRoom.startAudio();
      void unlockAudio.catch(() => undefined);

      const { participantToken, serverUrl } = await requestVoiceToken(sessionId);
      if (connectionAttempt.current !== attempt) {
        return;
      }

      await voiceRoom.connect(serverUrl, participantToken);
      if (connectionAttempt.current !== attempt) {
        roomRef.current = null;
        await voiceRoom.disconnect();
        return;
      }

      await unlockAudio;
      await voiceRoom.localParticipant.setMicrophoneEnabled(true);
      syncMicrophoneState();
      syncAgentState();

      if (connectionAttempt.current !== attempt) {
        roomRef.current = null;
        await voiceRoom.disconnect();
        return;
      }

      setVoiceStatus("connected");
    } catch (error) {
      if (connectionAttempt.current !== attempt) {
        return;
      }

      if (room && roomRef.current === room) {
        roomRef.current = null;
        boundSessionId.current = null;
        await room.disconnect();
      }
      clearRemoteAudio();
      resetVoiceState();
      setVoiceError(voiceErrorMessage(error));
      setVoiceStatus("error");
    }
  }, [
    attachRemoteAudio,
    clearRemoteAudio,
    detachRemoteAudio,
    publishVoiceTripUpdate,
    resetVoiceState,
    sessionId,
    voiceStatus,
  ]);

  const toggleMicrophone = useCallback(async () => {
    const room = roomRef.current;
    if (!room || voiceStatus !== "connected") {
      return;
    }

    const shouldEnable = isMicrophoneMuted || !hasMicrophoneTrack;
    setVoiceError(null);
    setIsMicrophoneMuted(!shouldEnable);

    try {
      await room.localParticipant.setMicrophoneEnabled(shouldEnable);

      if (roomRef.current !== room) {
        return;
      }

      const publication = room.localParticipant.getTrackPublication(
        Track.Source.Microphone,
      );
      setHasMicrophoneTrack(
        Boolean(
          publication?.audioTrack &&
            !publication.isUpstreamPaused &&
            publication.audioTrack.mediaStreamTrack.readyState === "live",
        ),
      );
      setIsMicrophoneMuted(!room.localParticipant.isMicrophoneEnabled);
    } catch (error) {
      setVoiceError(voiceErrorMessage(error));
    }
  }, [hasMicrophoneTrack, isMicrophoneMuted, voiceStatus]);

  useEffect(() => {
    if (
      roomRef.current &&
      boundSessionId.current &&
      boundSessionId.current !== sessionId
    ) {
      void stopVoiceSession();
    }
  }, [sessionId, stopVoiceSession]);

  useEffect(() => {
    return () => {
      connectionAttempt.current += 1;
      const room = roomRef.current;
      roomRef.current = null;
      boundSessionId.current = null;
      clearRemoteAudio();
      void room?.disconnect();
    };
  }, [clearRemoteAudio]);

  const voiceIsSpeaking = voiceStatus === "connected" && isAgentSpeaking;
  const voiceLabel = voiceError
    ? voiceError
    : voiceStatus === "connecting"
      ? "Connecting to Plan A"
      : voiceStatus === "error"
        ? "Try Plan A again"
        : voiceIsSpeaking
          ? "Plan A is speaking"
          : agentActivity === "thinking"
            ? "Plan A is thinking"
            : isMicrophoneMuted
              ? "Microphone muted"
              : voiceStatus === "connected"
                ? "Plan A is listening"
                : sessionId
                  ? "Talk to Plan A about this trip"
                  : "Start a trip before using voice edits";

  return (
    <aside
      aria-label="Plan A voice controls"
      className={`voice-dock voice-dock--${voiceStatus}${
        voiceIsSpeaking ? " is-speaking" : ""
      }`}
    >
      <span aria-live="polite" className="sr-only" role="status">
        {voiceLabel}
      </span>
      {voiceStatus === "connected" && (
        <button
          aria-label={
            isMicrophoneMuted ? "Unmute microphone" : "Mute microphone"
          }
          aria-pressed={!isMicrophoneMuted}
          className={`voice-dock__control${
            isMicrophoneMuted ? " is-muted" : ""
          }`}
          onClick={() => void toggleMicrophone()}
          type="button"
        >
          <MicrophoneIcon muted={isMicrophoneMuted} />
        </button>
      )}
      <button
        aria-label={
          voiceStatus === "connected"
            ? "Plan A voice session is active"
            : voiceStatus === "connecting"
              ? "Connecting to Plan A"
              : voiceStatus === "error"
                ? "Try connecting to Plan A again"
                : "Talk to Plan A"
        }
        className="voice-dock__main"
        disabled={voiceStatus === "connecting" || voiceStatus === "connected"}
        onClick={() => void startVoiceSession()}
        type="button"
      >
        <span className="voice-dock__mark" aria-hidden="true">P</span>
        {voiceStatus === "connecting" && (
          <span className="voice-dock__spinner" aria-hidden="true" />
        )}
        {voiceStatus === "connected" && (
          <span className="voice-dock__waves" aria-hidden="true">
            <span />
            <span />
            <span />
            <span />
          </span>
        )}
      </button>
      {voiceStatus === "connected" && (
        <button
          aria-label="End voice session"
          className="voice-dock__control voice-dock__control--end"
          onClick={() => void stopVoiceSession()}
          type="button"
        >
          <CloseIcon />
        </button>
      )}
      <span className="voice-dock__label" aria-hidden="true">
        {voiceLabel}
      </span>
    </aside>
  );
}
