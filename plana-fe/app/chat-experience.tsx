"use client";

import {
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { Room, RoomEvent, Track, type RemoteTrack } from "livekit-client";

type ChatRole = "assistant" | "user";

type VoiceStatus = "idle" | "connecting" | "connected" | "error";

type VoiceTokenResponse = {
  participantToken: string;
  serverUrl: string;
};

type ChatMessage = {
  id: number;
  role: ChatRole;
  content: string;
  suggestions?: string[];
  showBrief?: boolean;
};

type StarterIdea = {
  label: string;
  detail: string;
  prompt: string;
  icon: "city" | "sun" | "route" | "spark";
};

type IconName =
  | "add"
  | "arrow"
  | "attach"
  | "calendar"
  | "city"
  | "close"
  | "compass"
  | "menu"
  | "mic"
  | "route"
  | "send"
  | "spark"
  | "sun";

const starterIdeas: StarterIdea[] = [
  {
    label: "Plan a weekend getaway",
    detail: "A short escape that feels worth it",
    prompt:
      "I want a long weekend somewhere walkable with great food and a relaxed pace.",
    icon: "city",
  },
  {
    label: "Find a beach escape",
    detail: "Sun, salt water, zero overplanning",
    prompt:
      "Help me find a warm beach escape with a mix of good food and quiet time.",
    icon: "sun",
  },
  {
    label: "Build an itinerary",
    detail: "Make the most of a trip already on the books",
    prompt:
      "I have a four-day trip coming up and want a simple itinerary that leaves room to wander.",
    icon: "route",
  },
  {
    label: "Show me an example",
    detail: "See how Plan A helps shape a trip",
    prompt:
      "I’m planning a long weekend in Lisbon this fall—great food, walkable neighborhoods, not too expensive.",
    icon: "spark",
  },
];

function replyFor(message: string): Omit<ChatMessage, "id" | "role"> {
  const lowerCaseMessage = message.toLowerCase();

  if (lowerCaseMessage.includes("compare neighborhoods")) {
    return {
      content:
        "For an easy long weekend, I’d weigh Chiado or Príncipe Real for central, food-forward days. Alfama is more atmospheric, but its hills make it a slower choice. Do you want the stay to feel classic and central, or more lived-in?",
      suggestions: ["Classic and central", "Lived-in and local"],
    };
  }

  if (lowerCaseMessage.includes("under $800")) {
    return {
      content:
        "That can be a useful target if the dates stay flexible. I’d focus first on departure city and the kind of stay you’re happy with, then use the budget to narrow the options instead of forcing the whole trip too early. Where would you be flying from?",
      suggestions: ["Flying from New York", "Flying from Boston", "Dates are flexible"],
    };
  }

  if (lowerCaseMessage.includes("beach day")) {
    return {
      content:
        "A beach day can make the city break feel much less rushed. I’d keep it to one simple out-and-back day so the rest of the weekend stays anchored in Lisbon. Would you rather prioritize a quieter beach or a livelier promenade?",
      suggestions: ["Quieter beach", "Lively promenade"],
    };
  }

  if (lowerCaseMessage.includes("lisbon") || lowerCaseMessage.includes("portugal")) {
    return {
      content:
        "Lisbon is a great fit for that. You can stay central, eat remarkably well, and keep most days delightfully unplanned. What dates are you considering, where are you flying from, and what’s your rough per-person budget?",
      suggestions: [
        "Compare neighborhoods",
        "Keep it under $800",
        "Add a beach day",
      ],
      showBrief: true,
    };
  }

  if (lowerCaseMessage.includes("beach")) {
    return {
      content:
        "That sounds like the right kind of reset. I’d start by narrowing the season, flight time you can tolerate, and whether you want somewhere lively or mostly quiet. What month are you thinking?",
      suggestions: [
        "Somewhere in Europe", "Under a 6-hour flight", "Mostly quiet"],
    };
  }

  if (lowerCaseMessage.includes("itinerary")) {
    return {
      content:
        "Absolutely. The best itineraries have a little structure and a lot of breathing room. Tell me the destination, dates, and the one thing you don’t want to miss, and I’ll help you shape the days around it.",
      suggestions: ["Food first", "A slower pace", "One big day out"],
    };
  }

  return {
    content:
      "That sounds promising. I can help turn it into a trip that feels like you. What dates are in play, where are you leaving from, and what matters most this time?",
    suggestions: ["I’m flexible on dates", "I have a budget", "Keep it simple"],
  };
}

const iconPaths: Record<IconName, ReactNode> = {
  add: <path d="M12 5v14M5 12h14" />,
  arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
  attach: <path d="m20.5 11.5-8.2 8.2a5 5 0 0 1-7.1-7.1l8.2-8.2a3.5 3.5 0 0 1 5 5l-8.2 8.2a2 2 0 1 1-2.8-2.8l7.5-7.5" />,
  calendar: <><rect x="3" y="5" width="18" height="16" rx="3" /><path d="M8 3v4M16 3v4M3 10h18" /></>,
  city: <><path d="M4 20V9l6-4v15M10 20V4l6 3v13M16 20v-8l4 2v6M2 20h20" /><path d="M7 12h.01M7 16h.01M13 10h.01M13 14h.01" /></>,
  close: <path d="m6 6 12 12M18 6 6 18" />,
  compass: <><circle cx="12" cy="12" r="9" /><path d="m15.5 8.5-2.3 4.7-4.7 2.3 2.3-4.7 4.7-2.3Z" /></>,
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  mic: <><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M8.5 21h7" /></>,
  route: <><circle cx="6" cy="18" r="2" /><circle cx="18" cy="6" r="2" /><path d="M8 18c5 0 1-8 8-8M8 8c2.5 0 4-2 4-4" /></>,
  send: <path d="m21 3-7.5 18-3.2-7.3L3 10.5 21 3ZM10.3 13.7 15 9" />,
  spark: <path d="m12 3 1.5 5.4L19 10l-5.5 1.6L12 17l-1.5-5.4L5 10l5.5-1.6L12 3ZM19 16l.6 2.4L22 19l-2.4.6L19 22l-.6-2.4L16 19l2.4-.6L19 16Z" />,
  sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" /></>,
};

function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  const common = {
    fill: "none",
    height: size,
    stroke: "currentColor",
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    strokeWidth: 1.8,
    viewBox: "0 0 24 24",
    width: size,
    "aria-hidden": true,
  };

  return <svg {...common}>{iconPaths[name]}</svg>;
}

function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <span className={`brand-mark${compact ? " brand-mark--compact" : ""}`} aria-hidden="true">
      <span />
      <span />
      <span />
    </span>
  );
}

async function requestVoiceToken(): Promise<VoiceTokenResponse> {
  const response = await fetch("/api/livekit/token", { method: "POST" });
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
    return "Microphone access was blocked. Allow it in your browser, then try again.";
  }

  if (error instanceof Error && error.message) {
    return error.message;
  }

  return "Plan A could not start a voice session. Please try again.";
}

export default function ChatExperience() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isThinking, setIsThinking] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isRailCollapsed, setIsRailCollapsed] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus>("idle");
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const messageSequence = useRef(0);
  const turnToken = useRef(0);
  const connectionAttempt = useRef(0);
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

  const stopVoiceSession = useCallback(async () => {
    connectionAttempt.current += 1;
    const room = roomRef.current;
    roomRef.current = null;
    clearRemoteAudio();

    try {
      await room?.disconnect();
    } finally {
      setVoiceError(null);
      setVoiceStatus("idle");
    }
  }, [clearRemoteAudio]);

  const startVoiceSession = useCallback(async () => {
    if (roomRef.current || voiceStatus === "connecting") {
      return;
    }

    const attempt = connectionAttempt.current + 1;
    connectionAttempt.current = attempt;
    setVoiceError(null);
    setVoiceStatus("connecting");

    let room: Room | null = null;

    try {
      room = new Room({ adaptiveStream: true, dynacast: true });
      roomRef.current = room;
      room.on(RoomEvent.TrackSubscribed, attachRemoteAudio);
      room.on(RoomEvent.TrackUnsubscribed, detachRemoteAudio);
      room.on(RoomEvent.Disconnected, () => {
        if (roomRef.current !== room) {
          return;
        }

        roomRef.current = null;
        clearRemoteAudio();
        setVoiceError(null);
        setVoiceStatus("idle");
      });

      // Invoke this before the first await so the click that starts the session also
      // unlocks browser audio playback on platforms with strict autoplay policies.
      const unlockAudio = room.startAudio();
      void unlockAudio.catch(() => undefined);

      const { participantToken, serverUrl } = await requestVoiceToken();
      if (connectionAttempt.current !== attempt) {
        return;
      }

      await room.connect(serverUrl, participantToken);
      if (connectionAttempt.current !== attempt) {
        roomRef.current = null;
        await room.disconnect();
        return;
      }

      await unlockAudio;
      await room.localParticipant.setMicrophoneEnabled(true);

      if (connectionAttempt.current !== attempt) {
        roomRef.current = null;
        await room.disconnect();
        return;
      }

      setVoiceStatus("connected");
    } catch (error) {
      if (connectionAttempt.current !== attempt) {
        return;
      }

      if (room && roomRef.current === room) {
        roomRef.current = null;
        await room.disconnect();
      }
      clearRemoteAudio();
      setVoiceError(voiceErrorMessage(error));
      setVoiceStatus("error");
    }
  }, [attachRemoteAudio, clearRemoteAudio, detachRemoteAudio, voiceStatus]);

  const handleAgentClick = () => {
    if (voiceStatus === "connected") {
      void stopVoiceSession();
      return;
    }

    void startVoiceSession();
  };

  const voiceButtonLabel =
    voiceStatus === "connected"
      ? "End voice session"
      : voiceStatus === "connecting"
        ? "Connecting to Plan A"
        : "Talk to Plan A";

  useEffect(() => {
    return () => {
      connectionAttempt.current += 1;
      const room = roomRef.current;
      roomRef.current = null;
      clearRemoteAudio();
      void room?.disconnect();
    };
  }, [clearRemoteAudio]);

  const createMessageId = () => {
    messageSequence.current += 1;
    return messageSequence.current;
  };

  const sendMessage = (candidate: string) => {
    const content = candidate.trim();

    if (!content || isThinking) {
      return;
    }

    const activeToken = turnToken.current;
    setMessages((currentMessages) => [
      ...currentMessages,
      { content, id: createMessageId(), role: "user" },
    ]);
    setInput("");
    setIsThinking(true);
    setIsSidebarOpen(false);

    window.setTimeout(() => {
      if (turnToken.current !== activeToken) {
        return;
      }

      setMessages((currentMessages) => [
        ...currentMessages,
        { id: createMessageId(), role: "assistant", ...replyFor(content) },
      ]);
      setIsThinking(false);
    }, 700);
  };

  const startNewChat = () => {
    turnToken.current += 1;
    setMessages([]);
    setInput("");
    setIsThinking(false);
    setIsSidebarOpen(false);
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    sendMessage(input);
  };

  const handleInputKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage(input);
    }
  };

  return (
    <div className="chat-shell">
      <aside
        className={`chat-sidebar${isSidebarOpen ? " is-open" : ""}${
          isRailCollapsed ? " is-collapsed" : ""
        }`}
        aria-label="Travel planning controls"
      >
        <div className="sidebar-topline">
          <button className="brand-button" onClick={startNewChat} type="button">
            <BrandMark compact={isRailCollapsed} />
            <span className="sidebar-copy brand-wordmark">plana</span>
          </button>
          <button
            className="sidebar-close"
            onClick={() => setIsSidebarOpen(false)}
            type="button"
            aria-label="Close navigation"
          >
            <Icon name="close" />
          </button>
        </div>

        <button className="new-chat-button" onClick={startNewChat} type="button">
          <Icon name="add" />
          <span className="sidebar-copy">New conversation</span>
        </button>

        <div className="sidebar-section">
          <p className="sidebar-label sidebar-copy">Planning starters</p>
          <div className="starter-list">
            {starterIdeas.slice(0, 3).map((idea) => (
              <button
                className="starter-link"
                disabled={isThinking}
                key={idea.label}
                onClick={() => sendMessage(idea.prompt)}
                type="button"
              >
                <span className="starter-link-icon">
                  <Icon name={idea.icon} size={17} />
                </span>
                <span className="starter-link-copy sidebar-copy">
                  <strong>{idea.label}</strong>
                  <small>{idea.detail}</small>
                </span>
              </button>
            ))}
          </div>
        </div>

        <div className="sidebar-tip">
          <span className="sidebar-tip-icon">
            <Icon name="spark" size={17} />
          </span>
          <p className="sidebar-copy">
            <strong>Keep it casual.</strong>
            <span>Start with a place, a feeling, or a free weekend.</span>
          </p>
        </div>

        <button
          aria-label={voiceButtonLabel}
          aria-pressed={voiceStatus === "connected"}
          className={`sidebar-footer agent-launcher${
            voiceStatus === "connected" ? " is-live" : ""
          }`}
          disabled={voiceStatus === "connecting"}
          onClick={handleAgentClick}
          type="button"
        >
          <span className="avatar avatar--plan">P</span>
          <span className="sidebar-copy sidebar-footer-copy">
            <strong>Plan A</strong>
            <small>
              {voiceStatus === "connected"
                ? "Voice session live"
                : "Your travel sidekick"}
            </small>
          </span>
          <span className="online-dot" aria-hidden="true" />
        </button>
      </aside>

      {isSidebarOpen && (
        <button
          className="sidebar-scrim"
          onClick={() => setIsSidebarOpen(false)}
          type="button"
          aria-label="Close navigation"
        />
      )}

      <section className="chat-panel" aria-label="Plan A chat">
        <header className="chat-header">
          <div className="header-leading">
            <button
              className="mobile-menu-button"
              onClick={() => setIsSidebarOpen(true)}
              type="button"
              aria-label="Open navigation"
            >
              <Icon name="menu" />
            </button>
            <button
              className="rail-toggle-button"
              onClick={() => setIsRailCollapsed((isCollapsed) => !isCollapsed)}
              type="button"
              aria-label={isRailCollapsed ? "Expand navigation" : "Collapse navigation"}
            >
              <Icon name="menu" />
            </button>
            <div>
              <p className="header-eyebrow">Travel planning, simply</p>
              <p className="header-title">Plan A</p>
            </div>
          </div>
          <div className="header-actions">
            <button
              aria-label={voiceButtonLabel}
              aria-pressed={voiceStatus === "connected"}
              className="assistant-status assistant-status-button"
              disabled={voiceStatus === "connecting"}
              onClick={handleAgentClick}
              type="button"
            >
              <span />
              {voiceStatus === "connected"
                ? "Voice session live"
                : voiceStatus === "connecting"
                  ? "Connecting…"
                  : "Talk to Plan A"}
            </button>
            <button className="more-button" onClick={startNewChat} type="button" aria-label="Start a new conversation">
              <Icon name="add" />
            </button>
          </div>
        </header>

        <main className="conversation-stage">
          {messages.length === 0 ? (
            <section className="empty-state" aria-labelledby="greeting-title">
              <span className="eyebrow-pill">
                <span className="eyebrow-pulse" />
                Your travel-planning sidekick
              </span>
              <h1 id="greeting-title">Where do you want to go next?</h1>
              <p>
                Tell Plan A where you’re dreaming of, when you can get away, and
                what you want the trip to feel like.
              </p>
              <button
                className={`voice-launch-button${
                  voiceStatus === "connected" ? " is-live" : ""
                }`}
                disabled={voiceStatus === "connecting"}
                onClick={handleAgentClick}
                type="button"
              >
                <span className="voice-launch-icon">
                  <Icon name="mic" size={18} />
                </span>
                <span>{voiceButtonLabel}</span>
              </button>
              <div className="suggestion-grid" aria-label="Suggested prompts">
                {starterIdeas.map((idea) => (
                  <button
                    className="suggestion-card"
                    disabled={isThinking}
                    key={idea.label}
                    onClick={() => sendMessage(idea.prompt)}
                    type="button"
                  >
                    <span className="suggestion-icon">
                      <Icon name={idea.icon} size={19} />
                    </span>
                    <span>
                      <strong>{idea.label}</strong>
                      <small>{idea.detail}</small>
                    </span>
                    <Icon name="arrow" size={17} />
                  </button>
                ))}
              </div>
            </section>
          ) : (
            <section className="message-thread" aria-label="Conversation">
              <div className="conversation-note">
                <BrandMark />
                <div>
                  <p>Plan A is here to make the first step easier.</p>
                  <span>Share the rough outline. We’ll figure out the details together.</span>
                </div>
              </div>

              {messages.map((message) => (
                <article
                  className={`message message--${message.role}`}
                  key={message.id}
                >
                  {message.role === "assistant" && <span className="avatar avatar--plan">P</span>}
                  <div className="message-content">
                    <div className="message-meta">
                      <span>{message.role === "assistant" ? "Plan A" : "You"}</span>
                      {message.role === "assistant" && <span className="message-meta-dot" />}
                      {message.role === "assistant" && <span>Travel sidekick</span>}
                    </div>
                    <div className="message-bubble">
                      <p>{message.content}</p>
                    </div>

                    {message.showBrief && (
                      <div className="trip-brief">
                        <div className="trip-brief-topline">
                          <span className="trip-brief-icon"><Icon name="compass" size={16} /></span>
                          <span>To make this useful fast</span>
                        </div>
                        <p>Send three details and I’ll help you find the shape of the trip.</p>
                        <div className="brief-tags">
                          <span><Icon name="calendar" size={14} /> Dates</span>
                          <span><Icon name="route" size={14} /> Departure city</span>
                          <span><span className="budget-glyph">$</span> Budget</span>
                        </div>
                      </div>
                    )}

                    {message.suggestions && (
                      <div className="reply-chips" aria-label="Suggested replies">
                        {message.suggestions.map((suggestion) => (
                          <button
                            disabled={isThinking}
                            key={suggestion}
                            onClick={() => sendMessage(suggestion)}
                            type="button"
                          >
                            {suggestion}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                  {message.role === "user" && <span className="avatar avatar--you">Y</span>}
                </article>
              ))}

              {isThinking && (
                <article className="message message--assistant message--thinking" aria-live="polite">
                  <span className="avatar avatar--plan">P</span>
                  <div className="thinking-bubble">
                    <span />
                    <span />
                    <span />
                  </div>
                </article>
              )}
            </section>
          )}
        </main>

        <div className="composer-area">
          <form className="composer" onSubmit={handleSubmit}>
            <button
              aria-label="Attachments are unavailable in this demo"
              className="composer-attach"
              disabled
              title="Attachments are unavailable in this demo"
              type="button"
            >
              <Icon name="attach" size={19} />
            </button>
            <textarea
              aria-label="Ask Plan A about a trip"
              disabled={isThinking}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleInputKeyDown}
              placeholder="Ask Plan A about a trip..."
              rows={1}
              value={input}
            />
            <div className="composer-actions">
              <span className="composer-hint">Enter to send</span>
              <button
                aria-label="Send message"
                className="send-button"
                disabled={!input.trim() || isThinking}
                type="submit"
              >
                <Icon name="send" size={18} />
              </button>
            </div>
          </form>
          <p className="composer-disclaimer">
            Demo interface — use it to explore a trip, then verify plans before booking.
          </p>
        </div>
      </section>

      {voiceStatus !== "idle" && (
        <div className="voice-session-backdrop">
          <section
            aria-labelledby="voice-session-title"
            aria-modal="true"
            className="voice-session-card"
            role="dialog"
          >
            <button
              aria-label="Close voice session"
              className="voice-session-close"
              onClick={() => void stopVoiceSession()}
              type="button"
            >
              <Icon name="close" />
            </button>
            <span className={`voice-orb voice-orb--${voiceStatus}`} aria-hidden="true">
              <span />
              <span />
              <span />
            </span>
            <p className="voice-session-eyebrow">Plan A voice</p>
            <h2 id="voice-session-title">
              {voiceStatus === "connected" ? "You’re talking with Plan A" : "Meet Plan A"}
            </h2>
            <p aria-live="polite" className="voice-session-status">
              {voiceStatus === "connecting"
                ? "Connecting your microphone and bringing Plan A into the room…"
                : voiceStatus === "connected"
                  ? voiceError ?? "You’re live. Say hello whenever you’re ready."
                  : voiceError}
            </p>
            {voiceStatus === "error" ? (
              <button
                className="voice-session-action"
                onClick={() => void startVoiceSession()}
                type="button"
              >
                Try again
              </button>
            ) : (
              <button
                className="voice-session-action voice-session-action--secondary"
                onClick={() => void stopVoiceSession()}
                type="button"
              >
                End voice session
              </button>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
