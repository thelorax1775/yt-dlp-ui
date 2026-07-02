"use client";

import { useEffect, useState } from "react";
import { Cookie, Loader2, Save, Trash2 } from "lucide-react";
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
import { Textarea } from "@/components/ui/textarea";
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
  // Cookie text is write-only (the API never returns it), so it lives in its
  // own state and is only sent when the user actually pasted something.
  const [cookiesText, setCookiesText] = useState("");
  const [clearingCookies, setClearingCookies] = useState(false);

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
      const payload = cookiesText.trim()
        ? { ...settings, cookies_content: cookiesText }
        : settings;
      const saved = await api.updateSettings(payload);
      setSettings(saved);
      setCookiesText("");
      toast.success("Settings saved");
    } catch (e) {
      toast.error("Save failed", {
        description: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setSaving(false);
    }
  }

  async function handleClearCookies() {
    setClearingCookies(true);
    try {
      const saved = await api.updateSettings({ cookies_content: "" });
      setSettings(saved);
      setCookiesText("");
      toast.success("Cookies cleared");
    } catch (e) {
      toast.error("Failed to clear cookies", {
        description: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setClearingCookies(false);
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
            <p className="text-xs text-muted-foreground">
              {settings.ytdlp_version
                ? `Installed version: ${settings.ytdlp_version}. `
                : "yt-dlp not found at this path. "}
              Keep yt-dlp current — outdated versions fail on YouTube (e.g.
              &quot;Requested format is not available&quot;). In Docker it
              updates automatically on container restart.
            </p>
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

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Cookie className="h-4 w-4" /> Cookies / authentication
          </CardTitle>
          <CardDescription>
            YouTube may require sign-in cookies (&quot;Sign in to confirm
            you&apos;re not a bot&quot;). Export cookies from your browser with a
            &quot;Get cookies.txt&quot; extension and paste them here — see the{" "}
            <a
              href="https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp"
              target="_blank"
              rel="noreferrer"
              className="underline underline-offset-2"
            >
              yt-dlp FAQ
            </a>
            .
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-5">
          <div className="grid gap-2">
            <div className="flex items-center justify-between">
              <Label>Cookies (Netscape cookies.txt format)</Label>
              {settings.cookies_configured && (
                <span className="text-xs text-emerald-600 dark:text-emerald-400">
                  Cookies are configured
                </span>
              )}
            </div>
            <Textarea
              value={cookiesText}
              onChange={(e) => setCookiesText(e.target.value)}
              placeholder={
                settings.cookies_configured
                  ? "Cookies are saved. Paste new content to replace them."
                  : "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t…"
              }
              rows={6}
              spellCheck={false}
              className="font-mono text-xs"
            />
            <p className="text-xs text-muted-foreground">
              Stored on the server and passed to yt-dlp via --cookies. Saved
              cookies are never shown here again.
            </p>
            {settings.cookies_configured && (
              <div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={handleClearCookies}
                  disabled={clearingCookies}
                >
                  {clearingCookies ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Trash2 className="h-4 w-4" />
                  )}
                  Clear cookies
                </Button>
              </div>
            )}
          </div>

          <div className="grid gap-2">
            <Label>Cookies file path (advanced)</Label>
            <Input
              value={settings.cookies_file_path ?? ""}
              onChange={(e) => update("cookies_file_path", e.target.value)}
              placeholder="/config/cookies.txt"
            />
            <p className="text-xs text-muted-foreground">
              Use an existing cookies file on the server instead (e.g. mounted
              into the container). Takes precedence over pasted cookies.
            </p>
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
