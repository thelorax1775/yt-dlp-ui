"use client";

import { useState } from "react";
import { Loader2, Search } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MetadataCard } from "@/components/MetadataCard";
import { DownloadForm } from "@/components/DownloadForm";
import { api } from "@/lib/api";
import type { Metadata } from "@/lib/types";

export default function HomePage() {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [metadata, setMetadata] = useState<Metadata | null>(null);

  async function handleFetch(e?: React.FormEvent) {
    e?.preventDefault();
    if (!url.trim()) return;
    setLoading(true);
    setMetadata(null);
    try {
      const data = await api.fetchMetadata(url.trim());
      setMetadata(data);
    } catch (err) {
      toast.error("Could not fetch metadata", {
        description: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Download a video</h1>
        <p className="text-muted-foreground">
          Paste a video or playlist URL to fetch its details.
        </p>
      </div>

      <form onSubmit={handleFetch} className="flex gap-2">
        <Input
          placeholder="https://www.youtube.com/watch?v=..."
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          className="flex-1"
        />
        <Button type="submit" disabled={loading}>
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Search className="h-4 w-4" />
          )}
          Fetch
        </Button>
      </form>

      {metadata && (
        <div className="flex flex-col gap-4">
          <MetadataCard metadata={metadata} />
          <DownloadForm metadata={metadata} />
        </div>
      )}
    </div>
  );
}
