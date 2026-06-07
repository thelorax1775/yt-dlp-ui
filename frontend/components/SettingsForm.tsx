"use client";

import { useEffect, useState } from "react";
import { Loader2, Save } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";
import type { Settings } from "@/lib/types";

const AUDIO_FORMATS = ["mp3", "m4a", "opus", "flac", "wav", "aac"];

export function SettingsForm() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        setSettings(await api.getSettings());
      } catch (e) {
        toast.error("Failed to load settings", {
          description: e instanceof Error ? e.message : String(e),
        });
      }
    })();
  }, []);

  function update<K extends keyof Settings>(key: K, value: Settings[K]) {
    setSettings((s) => (s ? { ...s, [key]: value } : s));
  }

  async function handleSave() {
    if (!settings) return;
    setSaving(true);
    try {
      const saved = await api.updateSettings(settings);
      setSettings(saved);
      toast.success("Settings saved");
    } catch (e) {
      toast.error("Save failed", {
        description: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setSaving(false);
    }
  }

  if (!settings) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading…
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Downloads</CardTitle>
          <CardDescription>Where files go and how they download.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-5 sm:grid-cols-2">
          <div className="grid gap-2 sm:col-span-2">
            <Label>Default download folder</Label>
            <Input
              value={settings.download_folder}
              onChange={(e) => update("download_folder", e.target.value)}
              placeholder="/downloads"
            />
            <p className="text-xs text-muted-foreground">
              Point this at a mounted network share to save downloads there.
            </p>
          </div>

          <div className="grid gap-2">
            <Label>Audio format</Label>
            <Select
              value={settings.audio_format}
              onValueChange={(v) => update("audio_format", v)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {AUDIO_FORMATS.map((f) => (
                  <SelectItem key={f} value={f}>
                    {f}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid gap-2">
            <Label>Concurrent downloads</Label>
            <Input
              type="number"
              min={1}
              max={10}
              value={settings.concurrent_downloads}
              onChange={(e) =>
                update("concurrent_downloads", Number(e.target.value) || 1)
              }
            />
            <p className="text-xs text-muted-foreground">
              Applied after a backend restart.
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Tool paths</CardTitle>
          <CardDescription>
            Leave as defaults if yt-dlp and ffmpeg are on the system PATH.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-5 sm:grid-cols-2">
          <div className="grid gap-2">
            <Label>yt-dlp path</Label>
            <Input
              value={settings.ytdlp_path}
              onChange={(e) => update("ytdlp_path", e.target.value)}
              placeholder="yt-dlp"
            />
          </div>
          <div className="grid gap-2">
            <Label>ffmpeg path</Label>
            <Input
              value={settings.ffmpeg_path}
              onChange={(e) => update("ffmpeg_path", e.target.value)}
              placeholder="ffmpeg"
            />
          </div>
        </CardContent>
      </Card>

      <div>
        <Button onClick={handleSave} disabled={saving}>
          {saving ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Save className="h-4 w-4" />
          )}
          Save settings
        </Button>
      </div>
    </div>
  );
}
