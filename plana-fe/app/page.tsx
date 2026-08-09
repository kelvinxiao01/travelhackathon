"use client";

import React, { useState, useEffect, useRef } from "react";
import { 
  Send, Compass, Calendar, Users, DollarSign, 
  MapPin, Clock, Train, HelpCircle, AlertTriangle, 
  CheckCircle, ArrowRight, ShieldCheck, RefreshCw, Eye
} from "lucide-react";
import { useTripSession } from "./trip-session-context";

interface Message {
  type: "human" | "ai";
  content: string;
}

interface SupplierOffer {
  supplier: string;
  price: number;
  booking_url: string;
}

interface Hotel {
  hotel_id: string;
  name: string;
  address: string;
  lat: number;
  lng: number;
  rating: number;
  review_count: number;
  stars: number;
  capacity: number;
  cancellation_policy: string;
  images: string[];
  offers: SupplierOffer[];
}

interface ItineraryEvent {
  type: "hotel" | "activity" | "travel" | "meal";
  name: string;
  place_id?: string;
  start_time: string;
  end_time: string;
  duration_minutes: number;
  address?: string;
  lat?: number;
  lng?: number;
  transport_mode?: string;
  travel_time_minutes?: number;
  price?: number;
  booking_url?: string;
  description?: string;
}

interface DailyTimeline {
  day_number: number;
  date: string;
  events: ItineraryEvent[];
}

interface Itinerary {
  days: DailyTimeline[];
  total_cost: number;
  selected_hotel_id: string;
}

interface ValidationIssue {
  severity: string;
  message: string;
  affected_day?: number;
  affected_event?: string;
}

interface TripState {
  destination?: string;
  start_date?: string;
  end_date?: string;
  travelers?: number;
  interests?: string[];
  dislikes?: string[];
  budget?: { hotel_max_price?: number; total_max_budget?: number };
  hotel_candidates?: Hotel[];
  selected_hotel?: Hotel;
  selected_offer?: SupplierOffer;
  places?: any[];
  itinerary?: Itinerary;
  issues?: ValidationIssue[];
  validation_status?: string;
  current_goal?: string;
  messages?: Message[];
}

async function fetchTripSessionState(sessionId: string): Promise<TripState> {
  const response = await fetch(
    `http://localhost:8000/api/trips/${encodeURIComponent(sessionId)}`,
  );
  if (!response.ok) {
    throw new Error("Could not load the current trip.");
  }
  return (await response.json()) as TripState;
}

export default function Home() {
  const {
    sessionId: tripId,
    setSessionId: setTripId,
    voiceTripUpdate,
  } = useTripSession();
  const [inputText, setInputText] = useState("");
  const [messages, setMessages] = useState<Message[]>([
    { type: "ai", content: "Hi! I am ROAM. Where are we heading? Tell me your destination, dates, preferences, and hotel budget." }
  ]);
  const [tripState, setTripState] = useState<TripState | null>(null);
  const [activeTab, setActiveTab] = useState<"itinerary" | "hotels" | "map" | "budget">("itinerary");
  const [activeDay, setActiveDay] = useState(1);
  const [isPlanning, setIsPlanning] = useState(false);
  const [currentStep, setCurrentStep] = useState<string | null>(null);
  const [pastTrips, setPastTrips] = useState<any[]>([]);
  const [voiceUpdateSummary, setVoiceUpdateSummary] = useState<string | null>(null);
  
  // Track visualizer states
  const [planningSteps, setPlanningSteps] = useState({
    understand: "idle",  // idle | running | done
    discover: "idle",
    routing: "idle",
    optimize: "idle",
    validate: "idle",
    replan: "idle"
  });

  const chatEndRef = useRef<HTMLDivElement>(null);

  // Sync scroll
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, currentStep]);

  // Load list of past trips from the API
  const loadPastTrips = async () => {
    try {
      const response = await fetch("http://localhost:8000/api/trips");
      if (response.ok) {
        const data = await response.json();
        setPastTrips(data);
      }
    } catch (e) {
      console.error("Error loading past trips:", e);
    }
  };

  // Load trip session if trip_id is in URL query parameters
  useEffect(() => {
    loadPastTrips();
    if (typeof window !== "undefined") {
      const urlParams = new URLSearchParams(window.location.search);
      const urlTripId = urlParams.get("trip_id");
      if (urlTripId) {
        setTripId(urlTripId);
        loadExistingTrip(urlTripId);
      }
    }
  }, []);

  const loadExistingTrip = async (id: string) => {
    try {
      const state = await fetchTripSessionState(id);
      setTripState(state);
      if (state.messages && state.messages.length > 0) {
        setMessages(state.messages);
      } else {
        setMessages([
          { type: "ai", content: "Hi! I am ROAM. Where are we heading? Tell me your destination, dates, preferences, and hotel budget." }
        ]);
      }
    } catch (e) {
      console.error("Error loading existing trip:", e);
    }
  };

  // The voice worker publishes this only after the backend has saved and
  // validated the edit. Updating the same state that drives the calendar makes
  // the itinerary change visible immediately without exposing Supabase to the
  // browser or waiting for a polling interval.
  useEffect(() => {
    if (!voiceTripUpdate || voiceTripUpdate.sessionId !== tripId) {
      return;
    }

    let cancelled = false;
    let timeoutId: number | undefined;
    const showVoiceUpdate = (summary: string) => {
      if (cancelled) {
        return;
      }
      setVoiceUpdateSummary(summary);
      timeoutId = window.setTimeout(() => setVoiceUpdateSummary(null), 5000);
    };

    // This is a state-only refresh. It deliberately does not change the shared
    // session ID, so VoiceAgent keeps the current LiveKit room connected.
    void fetchTripSessionState(tripId)
      .then((state) => {
        if (cancelled) {
          return;
        }
        setTripState(state);
        showVoiceUpdate(voiceTripUpdate.summary);
      })
      .catch((error) => {
        console.error("Could not refresh the itinerary after a voice edit:", error);
        showVoiceUpdate(
          `${voiceTripUpdate.summary} The change is saved, but this page could not refresh yet.`,
        );
      });

    return () => {
      cancelled = true;
      if (timeoutId !== undefined) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [tripId, voiceTripUpdate]);

  const handleNewTrip = () => {
    setTripId("");
    setTripState(null);
    setMessages([
      { type: "ai", content: "Hi! I am ROAM. Where are we heading? Tell me your destination, dates, preferences, and hotel budget." }
    ]);
    setInputText("");
    if (typeof window !== "undefined") {
      window.history.pushState({}, '', window.location.pathname);
    }
  };

  const handleSelectPastTrip = (id: string) => {
    setTripId(id);
    loadExistingTrip(id);
    if (typeof window !== "undefined") {
      window.history.pushState({}, '', `?trip_id=${encodeURIComponent(id)}`);
    }
  };

  const handleSendMessage = async (textToSend?: string) => {
    const text = textToSend || inputText;
    if (!text.trim()) return;

    // Append user message
    const userMsg: Message = { type: "human", content: text };
    setMessages(prev => [...prev, userMsg]);
    setInputText("");
    setIsPlanning(true);

    // Initialize/Reset visualizer states
    setPlanningSteps({
      understand: "running",
      discover: "idle",
      routing: "idle",
      optimize: "idle",
      validate: "idle",
      replan: "idle"
    });

    const activeId = tripId || `trip_${crypto.randomUUID()}`;
    setTripId(activeId);

    try {
      const response = await fetch("http://localhost:8000/api/roam", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, trip_id: activeId })
      });

      if (!response.body) {
        throw new Error("No streaming body found");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith("data: ")) {
            const rawData = trimmed.slice(6);
            try {
              const data = JSON.parse(rawData);
              
              if (data.event === "started") {
                setCurrentStep("Analyzing your travel request...");
              } else if (data.event === "node_complete") {
                const node = data.node;
                
                // Update reasoning statuses
                setPlanningSteps(prev => {
                  const updated = { ...prev };
                  if (node === "understand") {
                    updated.understand = "done";
                    updated.discover = "running";
                    setCurrentStep("Discovering accommodation options & local spots...");
                  } else if (node === "discover") {
                    updated.discover = "done";
                    updated.routing = "running";
                    setCurrentStep("Calculating transit routes and travel matrix...");
                  } else if (node === "routing") {
                    updated.routing = "done";
                    updated.optimize = "running";
                    setCurrentStep("Optimizing physical timeline schedules...");
                  } else if (node === "optimize") {
                    updated.optimize = "done";
                    updated.validate = "running";
                    setCurrentStep("Validating constraints, opening hours & buffer rules...");
                  } else if (node === "validate") {
                    updated.validate = "done";
                    if (data.updates.validation_status === "invalid") {
                      updated.replan = "running";
                      setCurrentStep("Resolving itinerary conflicts (replanning loop)...");
                    } else {
                      setCurrentStep("Finalizing complete travel package...");
                    }
                  } else if (node === "replan") {
                    updated.replan = "done";
                    updated.optimize = "running";
                    setCurrentStep("Re-optimizing adjusted timelines...");
                  }
                  return updated;
                });
              } else if (data.event === "completed") {
                const finalState = data.state;
                setTripState(finalState);
                
                // Get last AI response
                if (finalState.messages && finalState.messages.length > 0) {
                  const lastMsg = finalState.messages[finalState.messages.length - 1];
                  if (lastMsg.type === "ai") {
                    setMessages(prev => [...prev, { type: "ai", content: lastMsg.content }]);
                  }
                }
                
                setPlanningSteps({
                  understand: "done",
                  discover: "done",
                  routing: "done",
                  optimize: "done",
                  validate: "done",
                  replan: finalState.issues?.length > 0 ? "done" : "idle"
                });
                
                setIsPlanning(false);
                setCurrentStep(null);
                loadPastTrips();
              }
            } catch (err) {
              console.error("Failed to parse chunk JSON:", err);
            }
          }
        }
      }
    } catch (error) {
      console.error("API error:", error);
      setMessages(prev => [...prev, { type: "ai", content: "Sorry, I ran into an error connection issues. Please try again." }]);
      setIsPlanning(false);
      setCurrentStep(null);
    }
  };

  // Pre-load direct test queries
  const selectQuickPrompt = (prompt: string) => {
    setInputText(prompt);
  };

  // Custom Map Coordinate plotting (relative sizing)
  const renderSVGMap = () => {
    if (!tripState || !tripState.places || tripState.places.length === 0 || !tripState.selected_hotel) {
      return (
        <div className="flex flex-col items-center justify-center h-full text-zinc-500">
          <HelpCircle className="w-12 h-12 mb-2 animate-bounce" />
          <p>Itinerary must be loaded to render the path map.</p>
        </div>
      );
    }

    const hotel = tripState.selected_hotel;
    const places = tripState.places;
    const coords = [
      { id: hotel.hotel_id, name: hotel.name, lat: hotel.lat, lng: hotel.lng, isHotel: true },
      ...places.map(p => ({ id: p.place_id, name: p.name, lat: p.lat, lng: p.lng, isHotel: false }))
    ];

    // Scale boundaries
    const lats = coords.map(c => c.lat);
    const lngs = coords.map(c => c.lng);
    const minLat = Math.min(...lats);
    const maxLat = Math.max(...lats);
    const minLng = Math.min(...lngs);
    const maxLng = Math.max(...lngs);

    const padding = 40;
    const width = 450;
    const height = 350;

    const getX = (lng: number) => {
      const denom = maxLng - minLng || 1;
      return padding + ((lng - minLng) / denom) * (width - 2 * padding);
    };

    const getY = (lat: number) => {
      const denom = maxLat - minLat || 1;
      // Latitude increases upwards, so subtract from height
      return height - (padding + ((lat - minLat) / denom) * (height - 2 * padding));
    };

    // Calculate paths for active day timeline
    const activeTimeline = tripState.itinerary?.days.find(d => d.day_number === activeDay);
    const pathPoints: { x: number; y: number }[] = [];

    if (activeTimeline) {
      activeTimeline.events.forEach(e => {
        if (e.lat && e.lng) {
          pathPoints.push({ x: getX(e.lng), y: getY(e.lat) });
        }
      });
    }

    return (
      <div className="relative bg-zinc-950 p-4 rounded-xl border border-zinc-800/80 overflow-hidden h-[380px] flex items-center justify-center">
        <svg width="100%" height="100%" viewBox={`0 0 ${width} ${height}`} className="w-full h-full">
          {/* Grid lines */}
          <defs>
            <pattern id="grid" width="40" width-height="40" patternUnits="userSpaceOnUse">
              <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#27272a" strokeWidth="0.5" />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#grid)" />

          {/* Paths connecting events */}
          {pathPoints.length > 1 && (
            <path
              d={`M ${pathPoints.map(p => `${p.x} ${p.y}`).join(" L ")}`}
              fill="none"
              stroke="#6366f1"
              strokeWidth="2.5"
              strokeDasharray="6,4"
              className="animate-dash"
            />
          )}

          {/* Coordinate points */}
          {coords.map((c, i) => {
            const cx = getX(c.lng);
            const cy = getY(c.lat);
            return (
              <g key={c.id} className="cursor-pointer group">
                <circle
                  cx={cx}
                  cy={cy}
                  r={c.isHotel ? 8 : 6}
                  fill={c.isHotel ? "#ec4899" : "#6366f1"}
                  className="transition duration-300 group-hover:scale-150"
                />
                {c.isHotel && (
                  <circle
                    cx={cx}
                    cy={cy}
                    r="12"
                    fill="none"
                    stroke="#ec4899"
                    strokeWidth="1"
                    className="animate-ping opacity-60"
                  />
                )}
                {/* Labels */}
                <rect
                  x={cx + 10}
                  y={cy - 12}
                  width={c.name.length * 6 + 10}
                  height="18"
                  rx="4"
                  fill="#09090b"
                  stroke="#27272a"
                  strokeWidth="0.5"
                  className="opacity-0 group-hover:opacity-100 transition-opacity duration-200"
                />
                <text
                  x={cx + 15}
                  y={cy}
                  fill="#fafafa"
                  fontSize="9"
                  className="opacity-0 group-hover:opacity-100 transition-opacity duration-200"
                >
                  {c.name}
                </text>
                <text
                  x={cx}
                  y={cy + 18}
                  fill="#a1a1aa"
                  fontSize="7"
                  textAnchor="middle"
                  className="pointer-events-none"
                >
                  {c.isHotel ? "🏨" : i}
                </text>
              </g>
            );
          })}
        </svg>
        <div className="absolute bottom-2 left-2 flex gap-4 text-xs bg-zinc-900/90 py-1 px-2.5 rounded border border-zinc-800">
          <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-pink-500 block"></span>Hotel</span>
          <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-indigo-500 block"></span>Attractions</span>
        </div>
        <div className="absolute top-2 right-2 text-xs text-zinc-400 bg-zinc-900/80 px-2 py-0.5 rounded">
          Day {activeDay} Paths
        </div>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-black text-zinc-100 font-sans flex flex-col antialiased">
      {voiceUpdateSummary && (
        <div
          className="fixed bottom-24 right-6 z-40 max-w-sm rounded-xl border border-emerald-500/30 bg-emerald-950/95 px-4 py-3 text-sm text-emerald-100 shadow-xl shadow-black/30"
          role="status"
        >
          <span className="mr-2 font-semibold text-emerald-300">Plan A updated the itinerary:</span>
          {voiceUpdateSummary}
        </div>
      )}
      {/* Navigation header */}
      <header className="border-b border-zinc-800/80 bg-zinc-950/60 backdrop-blur-md px-6 py-4 flex items-center justify-between sticky top-0 z-50">
        <div className="flex items-center gap-3">
          <div className="bg-gradient-to-tr from-indigo-600 to-pink-500 p-2 rounded-lg text-white font-bold tracking-wider text-sm">
            ROAM
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight text-white">ROAM AI</h1>
            <p className="text-xs text-zinc-400">Agentic Travel Planner</p>
          </div>
        </div>
        <div className="flex items-center gap-4 text-xs">
          {tripId && (
            <span className="bg-zinc-850 px-2.5 py-1 rounded-full text-zinc-300 border border-zinc-800">
              Session ID: <span className="font-mono text-pink-400">{tripId}</span>
            </span>
          )}
          <span className="bg-zinc-900 px-3 py-1 rounded text-zinc-400 border border-zinc-800 flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            SMS channel active
          </span>
        </div>
      </header>

      {/* Main split dashboard */}
      <div className="flex flex-1 flex-col lg:flex-row overflow-hidden w-full">
        {/* Far Left Side: Sidebar for past trips */}
        <div className="w-full lg:w-[240px] border-r border-zinc-800/80 bg-zinc-950 flex flex-col max-h-[calc(100vh-73px)] shrink-0">
          <div className="p-4 border-b border-zinc-800/80">
            <button 
              onClick={handleNewTrip}
              className="w-full bg-gradient-to-r from-indigo-600 to-pink-500 hover:from-indigo-500 hover:to-pink-400 text-white font-semibold py-2 px-4 rounded-lg flex items-center justify-center gap-2 text-xs transition duration-150 shadow-md"
            >
              + New Trip
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            <span className="text-[10px] uppercase font-bold text-zinc-500 tracking-wider px-2 block mb-1">Past Conversations</span>
            {pastTrips.length === 0 ? (
              <span className="text-xs text-zinc-600 px-2 block italic">No history yet</span>
            ) : (
              pastTrips.map((trip) => {
                // `phone_number` is the stable conversation/session key in the
                // existing backend. `trip.id` is a separate DB record id and
                // cannot bind a LiveKit voice room to this itinerary.
                const sessionId = trip.phone_number as string | undefined;
                return (
                  <button
                    key={trip.id}
                    disabled={!sessionId}
                    onClick={() => sessionId && handleSelectPastTrip(sessionId)}
                    className={`w-full text-left p-2.5 rounded-lg border text-xs transition duration-150 block disabled:cursor-not-allowed disabled:opacity-50 ${
                      tripId === sessionId
                        ? "bg-indigo-600/10 border-indigo-500/50 text-indigo-300"
                        : "bg-zinc-900/40 border-zinc-800/60 text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
                    }`}
                  >
                    <div className="font-semibold truncate">
                      {trip.state_json?.destination || `New Trip (${sessionId || "Draft"})`}
                    </div>
                    {trip.state_json?.start_date && (
                      <div className="text-[10px] text-zinc-500 truncate mt-0.5">
                        {trip.state_json.start_date} to {trip.state_json.end_date}
                      </div>
                    )}
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* Middle: Agent Conversational Log */}
        <div className="w-full lg:w-[440px] border-r border-zinc-800/80 flex flex-col bg-zinc-950/20 max-h-[calc(100vh-73px)] min-h-[400px]">
          
          {/* Agent reasoning loading steps */}
          {isPlanning && (
            <div className="bg-zinc-900/50 p-4 border-b border-zinc-800/60 flex flex-col gap-3">
              <div className="flex items-center justify-between text-xs">
                <span className="text-indigo-400 font-medium flex items-center gap-1.5">
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Reasoning Trace
                </span>
                <span className="text-zinc-500 font-mono">{currentStep}</span>
              </div>
              <div className="grid grid-cols-6 gap-1 bg-zinc-950 p-1.5 rounded border border-zinc-800">
                {Object.entries(planningSteps).map(([step, status]) => (
                  <div 
                    key={step} 
                    className={`text-[9px] text-center py-1 rounded uppercase tracking-wider ${
                      status === "running" ? "bg-indigo-600/30 text-indigo-300 font-bold border border-indigo-500 animate-pulse" :
                      status === "done" ? "bg-emerald-950/40 text-emerald-400 border border-emerald-800/80" : 
                      "bg-zinc-900 text-zinc-500 border border-zinc-800/40"
                    }`}
                  >
                    {step}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Chat conversations */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.map((msg, idx) => (
              <div 
                key={idx} 
                className={`flex flex-col ${msg.type === "human" ? "items-end" : "items-start"}`}
              >
                <div 
                  className={`max-w-[85%] rounded-xl px-4 py-3 text-sm leading-relaxed ${
                    msg.type === "human" 
                      ? "bg-indigo-600 text-white rounded-br-none" 
                      : "bg-zinc-900 text-zinc-100 rounded-bl-none border border-zinc-800/60"
                  }`}
                >
                  {msg.content}
                </div>
                <span className="text-[10px] text-zinc-500 mt-1 px-1">
                  {msg.type === "human" ? "You" : "ROAM AI"}
                </span>
              </div>
            ))}
            <div ref={chatEndRef} />
          </div>

          {/* Preset Prompts selection on blank state */}
          {messages.length === 1 && (
            <div className="p-4 border-t border-zinc-800/50 space-y-3 bg-zinc-950">
              <span className="text-xs text-zinc-400 block font-medium">Quick Prompts:</span>
              <div className="space-y-2">
                <button 
                  onClick={() => selectQuickPrompt("Plan a 3-day NYC trip for two people. We love Japanese food, museums and nightlife, and have a $600 hotel budget.")}
                  className="w-full text-left text-xs bg-zinc-900 hover:bg-zinc-850 p-2.5 rounded border border-zinc-800 transition duration-150 block text-zinc-300 truncate"
                >
                  Plan 3-day NYC trip (Japanese food, museums, nightlife, $600 budget)
                </button>
                <button 
                  onClick={() => selectQuickPrompt("Find me a hotel in NYC.")}
                  className="w-full text-left text-xs bg-zinc-900 hover:bg-zinc-850 p-2.5 rounded border border-zinc-800 transition duration-150 block text-zinc-300"
                >
                  Find me a hotel in NYC
                </button>
              </div>
            </div>
          )}

          {/* Chat input box */}
          <div className="p-4 border-t border-zinc-800/80 bg-zinc-950 flex gap-2">
            <input 
              type="text" 
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSendMessage()}
              placeholder="Ask ROAM to plan a trip..."
              className="flex-1 bg-zinc-900 border border-zinc-800 rounded-lg px-3.5 py-2.5 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-indigo-500 transition duration-200"
              disabled={isPlanning}
            />
            <button 
              onClick={() => handleSendMessage()}
              className="bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg p-2.5 transition duration-150 disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={isPlanning || !inputText.trim()}
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Right Side: Travel Workspace UI */}
        <div className="flex-1 p-6 flex flex-col overflow-y-auto max-h-[calc(100vh-73px)]">
          {tripState?.destination ? (
            <div className="space-y-6">
              {/* Workspace Header banner */}
              <div className="bg-gradient-to-r from-zinc-900 to-zinc-950 p-5 rounded-2xl border border-zinc-800/80 flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-xl">
                <div>
                  <div className="flex items-center gap-2 text-indigo-400 text-xs font-semibold uppercase tracking-wider mb-1">
                    <Compass className="w-4.5 h-4.5" /> Destination Workspace
                  </div>
                  <h2 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
                    {tripState.destination}
                  </h2>
                  <div className="flex flex-wrap items-center gap-4 text-sm text-zinc-400 mt-2">
                    <span className="flex items-center gap-1.5"><Calendar className="w-4 h-4 text-zinc-500" /> {tripState.start_date} to {tripState.end_date}</span>
                    <span className="flex items-center gap-1.5"><Users className="w-4 h-4 text-zinc-500" /> {tripState.travelers} guests</span>
                    {tripState.budget?.hotel_max_price && (
                      <span className="flex items-center gap-1.5"><DollarSign className="w-4 h-4 text-zinc-500" /> Hotel Max: ${tripState.budget.hotel_max_price}/nt</span>
                    )}
                  </div>
                </div>

                {/* Validation Status display */}
                <div className="flex items-center">
                  {tripState.validation_status === "valid" ? (
                    <div className="flex items-center gap-2 bg-emerald-500/10 text-emerald-400 px-3.5 py-1.5 rounded-full border border-emerald-500/20 text-xs font-medium">
                      <ShieldCheck className="w-4 h-4" /> Schedule Feasible & Verified
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 bg-amber-500/10 text-amber-400 px-3.5 py-1.5 rounded-full border border-amber-500/20 text-xs font-medium">
                      <AlertTriangle className="w-4 h-4" /> Verification Warnings ({tripState.issues?.length})
                    </div>
                  )}
                </div>
              </div>

              {/* Validation Warning list if any issues exist */}
              {tripState.issues && tripState.issues.length > 0 && (
                <div className="bg-amber-950/25 border border-amber-500/20 p-4 rounded-xl space-y-2">
                  <span className="text-xs font-bold text-amber-400 uppercase tracking-wider flex items-center gap-1.5">
                    <AlertTriangle className="w-4 h-4" /> Agent Validation Alerts (Replanning triggered)
                  </span>
                  <ul className="text-xs text-amber-300/90 list-disc list-inside space-y-1">
                    {tripState.issues.map((issue, idx) => (
                      <li key={idx}>{issue.message}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Workspace Navigation Tabs */}
              <div className="flex border-b border-zinc-800 gap-4">
                {(["itinerary", "hotels", "map", "budget"] as const).map(tab => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`py-2 px-3 text-sm font-semibold capitalize border-b-2 transition duration-200 -mb-[2px] ${
                      activeTab === tab 
                        ? "border-indigo-500 text-white" 
                        : "border-transparent text-zinc-400 hover:text-zinc-200"
                    }`}
                  >
                    {tab}
                  </button>
                ))}
              </div>

              {/* Tab content panel */}
              <div className="mt-4">
                
                {/* 1. ITINERARY TIMELINE VIEW */}
                {activeTab === "itinerary" && tripState.itinerary && (
                  <div className="space-y-6">
                    {/* Day tabs selection */}
                    <div className="flex gap-2">
                      {tripState.itinerary.days.map(day => (
                        <button
                          key={day.day_number}
                          onClick={() => setActiveDay(day.day_number)}
                          className={`px-4 py-2 rounded-lg text-xs font-semibold border transition duration-150 ${
                            activeDay === day.day_number
                              ? "bg-indigo-600 text-white border-indigo-500"
                              : "bg-zinc-900 text-zinc-400 border-zinc-800 hover:bg-zinc-850"
                          }`}
                        >
                          Day {day.day_number} ({day.date})
                        </button>
                      ))}
                    </div>

                    {/* Timeline card sequence */}
                    <div className="space-y-4 relative border-l-2 border-zinc-800/80 ml-3.5 pl-6 py-2">
                      {tripState.itinerary.days
                        .find(d => d.day_number === activeDay)
                        ?.events.map((event) => (
                          <div
                            key={`${event.name}-${event.start_time}-${event.end_time}`}
                            className="relative transition-all duration-500"
                          >
                            
                            {/* Bullet icon representing event category */}
                            <span className={`absolute -left-[35px] top-1.5 w-6 h-6 rounded-full flex items-center justify-center text-[10px] border shadow ${
                              event.type === "hotel" ? "bg-pink-600 border-pink-500 text-white" :
                              event.type === "activity" ? "bg-indigo-600 border-indigo-500 text-white" :
                              event.type === "meal" ? "bg-amber-600 border-amber-500 text-white" :
                              "bg-zinc-900 border-zinc-800 text-zinc-400"
                            }`}>
                              {event.type === "hotel" ? "🏨" :
                               event.type === "activity" ? "🎨" :
                               event.type === "meal" ? "🍱" :
                               event.transport_mode === "walking" ? "🚶" : "🚇"}
                            </span>

                            {/* Card Details */}
                            {event.type === "travel" ? (
                              <div className="bg-zinc-950 p-2.5 rounded-lg border border-zinc-900 flex items-center gap-3 text-xs text-zinc-400">
                                <Clock className="w-3.5 h-3.5 text-zinc-500" />
                                <span>{event.start_time} - {event.end_time}</span>
                                <span className="font-semibold text-zinc-300 uppercase tracking-wide">
                                  {event.transport_mode === "walking" ? "Walk" : "Transit"}
                                </span>
                                <span>({event.duration_minutes} mins travel & buffer)</span>
                              </div>
                            ) : (
                              <div className="bg-zinc-900/60 p-4 rounded-xl border border-zinc-800/60 space-y-1">
                                <div className="flex items-center justify-between">
                                  <span className="text-[10px] text-zinc-500 font-mono tracking-wider uppercase bg-zinc-950 px-2 py-0.5 rounded">
                                    {event.type}
                                  </span>
                                  <div className="flex items-center gap-1 text-xs text-zinc-400">
                                    <Clock className="w-3.5 h-3.5 text-zinc-500" />
                                    <span>{event.start_time} - {event.end_time}</span>
                                  </div>
                                </div>
                                <h4 className="text-sm font-bold text-white mt-1">{event.name}</h4>
                                {event.address && (
                                  <p className="text-xs text-zinc-400 flex items-center gap-1"><MapPin className="w-3 h-3 text-zinc-500" /> {event.address}</p>
                                )}
                                {event.description && (
                                  <p className="text-xs text-zinc-400/90 pt-1.5 border-t border-zinc-800/30 mt-1.5 italic">
                                    {event.description}
                                  </p>
                                )}
                              </div>
                            )}

                          </div>
                        ))}
                    </div>
                  </div>
                )}

                {/* 2. HOTELS (STAY22 INTEGRATION) */}
                {activeTab === "hotels" && (
                  <div className="space-y-6">
                    {tripState.selected_hotel && (
                      <div className="bg-gradient-to-br from-indigo-950/20 to-zinc-950 p-6 rounded-2xl border border-indigo-500/20 space-y-4">
                        <span className="bg-pink-600/10 text-pink-400 px-3 py-1 rounded text-xs font-bold uppercase tracking-wider border border-pink-500/20">
                          Selected Recommendation
                        </span>
                        
                        <div className="flex flex-col md:flex-row gap-6 mt-2">
                          {tripState.selected_hotel.images?.[0] && (
                            <img 
                              src={tripState.selected_hotel.images[0]} 
                              alt={tripState.selected_hotel.name}
                              className="w-full md:w-48 h-32 object-cover rounded-xl border border-zinc-800"
                            />
                          )}
                          <div className="flex-1 space-y-2">
                            <h3 className="text-lg font-bold text-white">{tripState.selected_hotel.name}</h3>
                            <p className="text-xs text-zinc-400 flex items-center gap-1">
                              <MapPin className="w-3.5 h-3.5 text-zinc-500" /> {tripState.selected_hotel.address}
                            </p>
                            <div className="flex items-center gap-4 text-xs text-zinc-300">
                              <span>Rating: {tripState.selected_hotel.rating} ⭐ ({tripState.selected_hotel.review_count} reviews)</span>
                              <span>Stars: {tripState.selected_hotel.stars} ★</span>
                            </div>
                            <p className="text-xs text-zinc-500">{tripState.selected_hotel.cancellation_policy}</p>
                          </div>
                        </div>

                        {/* Supplier Price Table */}
                        <div className="border-t border-zinc-800/80 pt-4 space-y-3">
                          <h4 className="text-xs font-bold text-zinc-400 uppercase tracking-wider">Stay22 Supplier Price Comparison</h4>
                          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                            {tripState.selected_hotel.offers.map((offer, idx) => (
                              <div 
                                key={idx} 
                                className={`p-3 rounded-lg border flex items-center justify-between ${
                                  tripState.selected_offer?.supplier === offer.supplier 
                                    ? "bg-indigo-600/10 border-indigo-500/40 text-white" 
                                    : "bg-zinc-900 border-zinc-800 text-zinc-300"
                                }`}
                              >
                                <div>
                                  <span className="text-[10px] text-zinc-500 block uppercase font-mono">{offer.supplier}</span>
                                  <span className="text-sm font-extrabold">${offer.price} / night</span>
                                </div>
                                {tripState.selected_offer?.supplier === offer.supplier && (
                                  <span className="text-[10px] bg-indigo-600 text-white px-1.5 py-0.5 rounded font-bold">
                                    Best
                                  </span>
                                )}
                              </div>
                            ))}
                          </div>
                          
                          {/* Stay22 CTA redirect */}
                          {tripState.selected_offer && (
                            <a 
                              href={tripState.selected_offer.booking_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="mt-4 w-full text-center bg-indigo-600 hover:bg-indigo-500 transition text-white py-3 rounded-xl font-bold block text-sm shadow-lg shadow-indigo-600/20"
                            >
                              Book this hotel on {tripState.selected_offer.supplier} — ${tripState.selected_offer.price}/nt
                            </a>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Candidate listings */}
                    {tripState.hotel_candidates && tripState.hotel_candidates.length > 1 && (
                      <div className="space-y-3">
                        <h4 className="text-xs font-bold text-zinc-400 uppercase tracking-wider">Other Discovered Properties</h4>
                        <div className="space-y-2">
                          {tripState.hotel_candidates
                            .filter(h => h.hotel_id !== tripState.selected_hotel?.hotel_id)
                            .map(h => {
                              const minOffer = h.offers.reduce((prev, curr) => prev.price < curr.price ? prev : curr);
                              return (
                                <div key={h.hotel_id} className="bg-zinc-900 p-4 rounded-xl border border-zinc-800 flex items-center justify-between text-xs gap-4">
                                  <div>
                                    <h5 className="font-bold text-white text-sm">{h.name}</h5>
                                    <p className="text-zinc-400">{h.address}</p>
                                    <span className="text-zinc-500 block mt-1">{h.rating} ⭐ • {h.stars} Stars</span>
                                  </div>
                                  <div className="text-right">
                                    <span className="text-zinc-500 block font-mono">Cheapest supplier</span>
                                    <span className="font-bold text-white text-sm">${minOffer.price} / nt</span>
                                    <button 
                                      onClick={() => {
                                        // Update state selection
                                        setTripState(prev => {
                                          if (!prev) return null;
                                          return {
                                            ...prev,
                                            selected_hotel: h,
                                            selected_offer: minOffer
                                          };
                                        });
                                      }}
                                      className="mt-2 block bg-zinc-800 hover:bg-zinc-750 border border-zinc-700 text-zinc-300 py-1 px-2.5 rounded font-semibold text-[10px]"
                                    >
                                      Select property
                                    </button>
                                  </div>
                                </div>
                              );
                            })}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* 3. DYNAMIC PATH ROUTING MAP */}
                {activeTab === "map" && (
                  <div className="space-y-4">
                    <div className="flex gap-2">
                      {tripState.itinerary?.days.map(day => (
                        <button
                          key={day.day_number}
                          onClick={() => setActiveDay(day.day_number)}
                          className={`px-3 py-1.5 rounded text-[10px] font-semibold border transition duration-150 ${
                            activeDay === day.day_number
                              ? "bg-indigo-600 text-white border-indigo-500"
                              : "bg-zinc-900 text-zinc-400 border-zinc-800"
                          }`}
                        >
                          Day {day.day_number} Routes
                        </button>
                      ))}
                    </div>
                    {renderSVGMap()}
                    <p className="text-xs text-zinc-400 italic text-center mt-1">
                      Connecting path indicates optimized sequencing computed by our physical mobility engine.
                    </p>
                  </div>
                )}

                {/* 4. BUDGET BREAKDOWN */}
                {activeTab === "budget" && tripState.itinerary && (
                  <div className="bg-zinc-900/60 p-6 rounded-2xl border border-zinc-800 space-y-4">
                    <h3 className="text-lg font-bold text-white">Estimated Cost Matrix</h3>
                    
                    <table className="w-full text-xs text-left text-zinc-300">
                      <thead className="text-[10px] text-zinc-500 uppercase tracking-wider border-b border-zinc-800">
                        <tr>
                          <th className="py-2.5">Expense Item</th>
                          <th className="py-2.5">Category</th>
                          <th className="py-2.5 text-right">Cost</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-800/40">
                        <tr>
                          <td className="py-3 font-semibold text-white">
                            {tripState.selected_hotel?.name}
                          </td>
                          <td className="py-3 text-zinc-400">Hotel Accommodation</td>
                          <td className="py-3 text-right font-bold text-white">
                            ${tripState.itinerary.total_cost}
                          </td>
                        </tr>
                        {tripState.places?.map((p, idx) => (
                          <tr key={idx}>
                            <td className="py-3 text-zinc-300">{p.name}</td>
                            <td className="py-3 text-zinc-400">Admissions / Verified entry</td>
                            <td className="py-3 text-right font-semibold">$0.00 (Self pay / Free)</td>
                          </tr>
                        ))}
                        <tr className="border-t border-zinc-800">
                          <td className="py-4 font-bold text-white text-sm">Total Projected Cost</td>
                          <td className="py-4"></td>
                          <td className="py-4 text-right font-extrabold text-white text-sm">
                            ${tripState.itinerary.total_cost}
                          </td>
                        </tr>
                      </tbody>
                    </table>

                    {tripState.budget?.total_max_budget && (
                      <div className="bg-zinc-950 p-4 rounded-xl border border-zinc-800 flex items-center justify-between text-xs">
                        <div>
                          <span className="text-zinc-500 block">Maximum Budget Target</span>
                          <span className="font-bold text-zinc-300">${tripState.budget.total_max_budget}</span>
                        </div>
                        <div>
                          <span className="text-zinc-500 block">Status</span>
                          {tripState.itinerary.total_cost <= tripState.budget.total_max_budget ? (
                            <span className="text-emerald-400 font-bold flex items-center gap-1">
                              <CheckCircle className="w-3.5 h-3.5" /> Under Budget
                            </span>
                          ) : (
                            <span className="text-red-400 font-bold flex items-center gap-1">
                              <AlertTriangle className="w-3.5 h-3.5" /> Budget Exceeded
                            </span>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )}

              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center flex-1 text-center py-20 bg-zinc-950/20 border border-dashed border-zinc-850 rounded-2xl px-6">
              <Compass className="w-16 h-16 text-zinc-700 mb-4 animate-spin-slow" />
              <h3 className="text-lg font-bold text-white">No active trip session</h3>
              <p className="text-sm text-zinc-400 max-w-sm mt-1.5">
                Submit a travel planning request in the chat panel on the left (or click a quick prompt) to populate this workspace.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
