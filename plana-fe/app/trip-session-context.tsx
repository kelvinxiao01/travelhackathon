"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type VoiceTripUpdate = {
  sessionId: string;
  revision: number;
  summary: string;
};

type TripSessionContextValue = {
  sessionId: string;
  setSessionId: (sessionId: string) => void;
  voiceTripUpdate: VoiceTripUpdate | null;
  publishVoiceTripUpdate: (update: VoiceTripUpdate) => void;
};

const TripSessionContext = createContext<TripSessionContextValue | null>(null);

export function TripSessionProvider({ children }: { children: ReactNode }) {
  const [sessionId, setActiveSessionId] = useState("");
  const [voiceTripUpdate, setVoiceTripUpdate] = useState<VoiceTripUpdate | null>(
    null,
  );

  const setSessionId = useCallback((nextSessionId: string) => {
    setActiveSessionId(nextSessionId);
    setVoiceTripUpdate(null);
  }, []);

  const publishVoiceTripUpdate = useCallback((update: VoiceTripUpdate) => {
    setVoiceTripUpdate(update);
  }, []);

  const value = useMemo(
    () => ({
      sessionId,
      setSessionId,
      voiceTripUpdate,
      publishVoiceTripUpdate,
    }),
    [publishVoiceTripUpdate, sessionId, setSessionId, voiceTripUpdate],
  );

  return (
    <TripSessionContext.Provider value={value}>
      {children}
    </TripSessionContext.Provider>
  );
}

export function useTripSession(): TripSessionContextValue {
  const value = useContext(TripSessionContext);
  if (!value) {
    throw new Error("useTripSession must be used within TripSessionProvider.");
  }
  return value;
}
