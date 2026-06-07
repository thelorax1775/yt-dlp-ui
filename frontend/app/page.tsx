"use client";

import { useState } from "react";
import { Loader2, Search } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/PageHeader";
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
    <div>
      <PageHeader
        title="Download a video"
        description="Paste a video or playlist URL to fetch its details."
      />

      <form onSubmit={handleFetch} className="flex flex-col gap-2 sm:flex-row">
        <Input
          placeholder="https://www.youtube.com/watch?v=..."
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          className="flex-1"
        />
        <Button type="submit" disabled={loading} className="sm:w-32">
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Search className="h-4 w-4" />
          )}
          Fetch
        </Button>
      </form>

      {metadata && (
        <div className="mt-6 grid gap-4 lg:grid-cols-5">
          <div className="lg:col-span-3">
            <MetadataCard metadata={metadata} />
          </div>
          <div className="lg:col-span-2">
            <DownloadForm metadata={metadata} />
          </div>
        </div>
      )}
    </div>
  );
}
