"use client";

import { useEffect, useState } from "react";
import { Loader2, Save } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
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
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  return (
    <div className="flex max-w-lg flex-col gap-5">
      <div className="grid gap-2">
        <Label>Default download folder</Label>
        <Input
          value={settings.download_folder}
          onChange={(e) => update("download_folder", e.target.value)}
          placeholder="/downloads"
        />
      </div>

      <div className="grid gap-2">
        <Label>Audio format (for audio extraction)</Label>
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
          Takes effect after a backend restart.
        </p>
      </div>

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

      <Button onClick={handleSave} disabled={saving} className="w-fit">
        {saving ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Save className="h-4 w-4" />
        )}
        Save settings
      </Button>
    </div>
  );
}
