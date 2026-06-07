import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import { Toaster } from "@/components/ui/sonner";

export const metadata: Metadata = {
  title: "yt-dlp Web UI",
  description: "A self-hosted web interface for yt-dlp",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-background antialiased">
        <div className="flex min-h-screen">
          <Sidebar />
          <main className="flex-1 overflow-y-auto px-8 py-8">
            <div className="mx-auto max-w-4xl">{children}</div>
          </main>
        </div>
        <Toaster />
      </body>
    </html>
  );
}
