import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Plana — Your travel-planning sidekick",
  description: "A mock chat experience for easygoing travel planning.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
