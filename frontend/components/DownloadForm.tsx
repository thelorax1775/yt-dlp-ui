"use client";

import { useState } from "react";
import { AudioLines, Download, Loader2, Video } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import type { Metadata } from "@/lib/types";

interface Props {
  metadata: Metadata;
}

type Mode = "bestvideo" | "bestaudio" | "custom";

export function DownloadForm({ metadata }: Props) {
  const [mode, setMode] = useState<Mode>("bestvideo");
  const [customFormat, setCustomFormat] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleDownload() {
    const formatId =
      mode === "bestvideo"
        ? "bestvideo"
        : mode === "bestaudio"
        ? "bestaudio"
        : customFormat.trim();

    if (mode === "custom" && !formatId) {
      toast.error("Enter a custom format ID");
      return;
    }

    setSubmitting(true);
    try {
      await api.startDownload({ url: metadata.url, format_id: formatId });
      toast.success("Download queued", { description: metadata.title });
    } catch (e) {
      toast.error("Failed to queue download", {
        description: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Download options</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid gap-2">
          <Label>Format</Label>
          <Select value={mode} onValueChange={(v) => setMode(v as Mode)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="bestvideo">
                <span className="flex items-center gap-2">
                  <Video className="h-4 w-4" /> Best video + audio
                </span>
              </SelectItem>
              <SelectItem value="bestaudio">
                <span className="flex items-center gap-2">
                  <AudioLines className="h-4 w-4" /> Best audio (extract)
                </span>
              </SelectItem>
              <SelectItem value="custom">Custom format</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {mode === "custom" && (
          <div className="grid gap-2">
            <Label>Custom format ID</Label>
            <Input
              placeholder="e.g. 137+140 or 22"
              value={customFormat}
              onChange={(e) => setCustomFormat(e.target.value)}
            />
            {metadata.formats.length > 0 && (
              <p className="text-xs text-muted-foreground">
                {metadata.formats.length} formats available — use a format_id
                from yt-dlp.
              </p>
            )}
          </div>
        )}

        <Button
          onClick={handleDownload}
          disabled={submitting}
          className="w-full"
        >
          {submitting ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Download className="h-4 w-4" />
          )}
          Download
        </Button>
      </CardContent>
    </Card>
  );
}
