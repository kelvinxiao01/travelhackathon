import type { Metadata } from "next";
import "./globals.css";
import VoiceAgent from "./voice-agent";

export const metadata: Metadata = {
  title: "Plana — Your travel-planning sidekick",
  description: "A calm, voice-first home for your travel itinerary.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col">
        {children}
        <VoiceAgent />
      </body>
    </html>
  );
}
