"use client";

import { useEffect, useState } from "react";
import {
  FolderInput,
  HardDriveDownload,
  Loader2,
  Plug,
  PlugZap,
  Plus,
  Server,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
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
import type { Share, ShareCreate, ShareType } from "@/lib/types";

const EMPTY: ShareCreate = {
  name: "",
  type: "smb",
  remote: "",
  mount_point: "",
  username: "",
  password: "",
  domain: "",
  options: "",
  auto_mount: false,
};

export function SharesManager() {
  const [shares, setShares] = useState<Share[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [draft, setDraft] = useState<ShareCreate>(EMPTY);
  const [busy, setBusy] = useState<number | "new" | null>(null);

  async function refresh() {
    try {
      setShares(await api.getShares());
    } catch (e) {
      toast.error("Failed to load shares", {
        description: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  function setField<K extends keyof ShareCreate>(k: K, v: ShareCreate[K]) {
    setDraft((d) => ({ ...d, [k]: v }));
  }

  async function handleCreate() {
    if (!draft.name || !draft.remote || !draft.mount_point) {
      toast.error("Name, remote, and mount point are required");
      return;
    }
    setBusy("new");
    try {
      await api.createShare(draft);
      toast.success("Share added");
      setDraft(EMPTY);
      setShowForm(false);
      await refresh();
    } catch (e) {
      toast.error("Could not add share", {
        description: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setBusy(null);
    }
  }

  async function handleMountToggle(s: Share) {
    setBusy(s.id);
    try {
      const res = s.mounted
        ? await api.unmountShare(s.id)
        : await api.mountShare(s.id);
      if (s.mounted) {
        res.mounted
          ? toast.error("Unmount failed", { description: res.message ?? "" })
          : toast.success("Unmounted");
      } else {
        res.mounted
          ? toast.success("Mounted")
          : toast.error("Mount failed", { description: res.message ?? "" });
      }
      await refresh();
    } catch (e) {
      toast.error("Action failed", {
        description: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setBusy(null);
    }
  }

  async function handleDelete(s: Share) {
    setBusy(s.id);
    try {
      await api.deleteShare(s.id);
      toast.success("Share removed");
      await refresh();
    } catch (e) {
      toast.error("Delete failed", {
        description: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setBusy(null);
    }
  }

  async function setAsDownloadFolder(s: Share) {
    try {
      await api.updateSettings({ download_folder: s.mount_point });
      toast.success("Download folder set", { description: s.mount_point });
    } catch (e) {
      toast.error("Could not update settings", {
        description: e instanceof Error ? e.message : String(e),
      });
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
        <div className="space-y-1.5">
          <CardTitle className="text-base">Network shares</CardTitle>
          <CardDescription>
            Mount an SMB/CIFS or NFS share and save downloads to it.
          </CardDescription>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setShowForm((v) => !v)}
        >
          <Plus className="h-4 w-4" /> Add
        </Button>
      </CardHeader>

      <CardContent className="flex flex-col gap-4">
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading…
          </div>
        ) : shares.length === 0 && !showForm ? (
          <div className="rounded-lg border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
            No shares configured yet.
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {shares.map((s) => (
              <div
                key={s.id}
                className="flex flex-col gap-3 rounded-lg border p-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="flex min-w-0 items-start gap-3">
                  <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-muted">
                    <Server className="h-4 w-4" />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="truncate font-medium">{s.name}</span>
                      <Badge variant="outline" className="uppercase">
                        {s.type}
                      </Badge>
                      <Badge variant={s.mounted ? "success" : "secondary"}>
                        {s.mounted ? "Mounted" : "Not mounted"}
                      </Badge>
                    </div>
                    <p className="truncate text-xs text-muted-foreground">
                      {s.remote} → {s.mount_point}
                    </p>
                  </div>
                </div>

                <div className="flex shrink-0 flex-wrap gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={busy === s.id}
                    onClick={() => handleMountToggle(s)}
                  >
                    {busy === s.id ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : s.mounted ? (
                      <PlugZap className="h-4 w-4" />
                    ) : (
                      <Plug className="h-4 w-4" />
                    )}
                    {s.mounted ? "Unmount" : "Mount"}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    title="Use as download folder"
                    onClick={() => setAsDownloadFolder(s)}
                  >
                    <FolderInput className="h-4 w-4" /> Use
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-muted-foreground hover:text-destructive"
                    disabled={busy === s.id}
                    onClick={() => handleDelete(s)}
                    title="Delete"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}

        {showForm && (
          <div className="grid gap-4 rounded-lg border bg-muted/30 p-4 sm:grid-cols-2">
            <div className="grid gap-2">
              <Label>Name</Label>
              <Input
                value={draft.name}
                onChange={(e) => setField("name", e.target.value)}
                placeholder="Media NAS"
              />
            </div>
            <div className="grid gap-2">
              <Label>Type</Label>
              <Select
                value={draft.type}
                onValueChange={(v) => setField("type", v as ShareType)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="smb">SMB / CIFS</SelectItem>
                  <SelectItem value="nfs">NFS</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="grid gap-2 sm:col-span-2">
              <Label>Remote</Label>
              <Input
                value={draft.remote}
                onChange={(e) => setField("remote", e.target.value)}
                placeholder={
                  draft.type === "smb"
                    ? "//192.168.1.10/media"
                    : "192.168.1.10:/export/media"
                }
              />
            </div>

            <div className="grid gap-2 sm:col-span-2">
              <Label>Mount point</Label>
              <Input
                value={draft.mount_point}
                onChange={(e) => setField("mount_point", e.target.value)}
                placeholder="/mnt/shares/media"
              />
            </div>

            {draft.type === "smb" && (
              <>
                <div className="grid gap-2">
                  <Label>Username</Label>
                  <Input
                    value={draft.username ?? ""}
                    onChange={(e) => setField("username", e.target.value)}
                    placeholder="(blank = guest)"
                    autoComplete="off"
                  />
                </div>
                <div className="grid gap-2">
                  <Label>Password</Label>
                  <Input
                    type="password"
                    value={draft.password ?? ""}
                    onChange={(e) => setField("password", e.target.value)}
                    autoComplete="new-password"
                  />
                </div>
                <div className="grid gap-2">
                  <Label>Domain (optional)</Label>
                  <Input
                    value={draft.domain ?? ""}
                    onChange={(e) => setField("domain", e.target.value)}
                  />
                </div>
              </>
            )}

            <div className="grid gap-2">
              <Label>Extra mount options (optional)</Label>
              <Input
                value={draft.options ?? ""}
                onChange={(e) => setField("options", e.target.value)}
                placeholder={draft.type === "smb" ? "vers=3.0" : "soft,timeo=30"}
              />
            </div>

            <label className="flex items-center gap-2 text-sm sm:col-span-2">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-input accent-primary"
                checked={draft.auto_mount}
                onChange={(e) => setField("auto_mount", e.target.checked)}
              />
              Mount automatically on startup
            </label>

            <div className="flex gap-2 sm:col-span-2">
              <Button onClick={handleCreate} disabled={busy === "new"}>
                {busy === "new" ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <HardDriveDownload className="h-4 w-4" />
                )}
                Save share
              </Button>
              <Button
                variant="ghost"
                onClick={() => {
                  setShowForm(false);
                  setDraft(EMPTY);
                }}
              >
                Cancel
              </Button>
            </div>
          </div>
        )}

        <p className="text-xs text-muted-foreground">
          Mounting requires the backend to run with mount privileges (in Docker:{" "}
          <code className="rounded bg-muted px-1">cap_add: SYS_ADMIN</code> and{" "}
          <code className="rounded bg-muted px-1">cifs-utils</code>/
          <code className="rounded bg-muted px-1">nfs-common</code>). See the
          README.
        </p>
      </CardContent>
    </Card>
  );
}
