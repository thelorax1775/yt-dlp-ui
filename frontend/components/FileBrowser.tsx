"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ChevronRight,
  Download,
  File as FileIcon,
  Folder,
  FolderPlus,
  Loader2,
  Pencil,
  RefreshCw,
  Trash2,
  X,
} from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/EmptyState";
import { api } from "@/lib/api";
import { formatBytes, formatDate } from "@/lib/utils";
import type { FileEntry } from "@/lib/types";

function Breadcrumbs({
  path,
  onNavigate,
}: {
  path: string;
  onNavigate: (p: string) => void;
}) {
  const parts = path ? path.split("/") : [];
  const crumbs = parts.map((part, i) => ({
    name: part,
    full: parts.slice(0, i + 1).join("/"),
  }));

  return (
    <div className="flex flex-wrap items-center gap-1 text-sm">
      <button
        onClick={() => onNavigate("")}
        className="font-medium text-foreground hover:underline"
      >
        downloads
      </button>
      {crumbs.map((c) => (
        <span key={c.full} className="flex items-center gap-1">
          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
          <button
            onClick={() => onNavigate(c.full)}
            className="text-muted-foreground hover:text-foreground hover:underline"
          >
            {c.name}
          </button>
        </span>
      ))}
    </div>
  );
}

export function FileBrowser() {
  const [path, setPath] = useState("");
  const [entries, setEntries] = useState<FileEntry[]>([]);
  const [root, setRoot] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [creatingFolder, setCreatingFolder] = useState(false);
  const [folderName, setFolderName] = useState("");

  const load = useCallback(async (p: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listFiles(p);
      setEntries(res.entries);
      setRoot(res.root);
      setPath(res.path);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load("");
  }, [load]);

  async function handleDelete(entry: FileEntry) {
    if (
      !window.confirm(
        `Delete ${entry.is_dir ? "folder" : "file"} "${entry.name}"?` +
          (entry.is_dir ? "\nThis removes everything inside it." : "")
      )
    )
      return;
    setBusy(entry.path);
    try {
      await api.deleteFile(entry.path);
      toast.success("Deleted", { description: entry.name });
      await load(path);
    } catch (e) {
      toast.error("Delete failed", {
        description: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setBusy(null);
    }
  }

  function startRename(entry: FileEntry) {
    setRenaming(entry.path);
    setRenameValue(entry.name);
  }

  async function submitRename(entry: FileEntry) {
    const name = renameValue.trim();
    if (!name || name === entry.name) {
      setRenaming(null);
      return;
    }
    setBusy(entry.path);
    try {
      await api.renameFile(entry.path, name);
      toast.success("Renamed", { description: `${entry.name} → ${name}` });
      setRenaming(null);
      await load(path);
    } catch (e) {
      toast.error("Rename failed", {
        description: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setBusy(null);
    }
  }

  async function submitNewFolder() {
    const name = folderName.trim();
    if (!name) {
      setCreatingFolder(false);
      return;
    }
    try {
      await api.makeDir(path, name);
      toast.success("Folder created", { description: name });
      setFolderName("");
      setCreatingFolder(false);
      await load(path);
    } catch (e) {
      toast.error("Could not create folder", {
        description: e instanceof Error ? e.message : String(e),
      });
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Breadcrumbs path={path} onNavigate={load} />
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setCreatingFolder((v) => !v)}
          >
            <FolderPlus className="h-4 w-4" /> New folder
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => load(path)}
            disabled={loading}
          >
            <RefreshCw className={loading ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
            Refresh
          </Button>
        </div>
      </div>

      {root && (
        <p className="truncate text-xs text-muted-foreground" title={root}>
          Root: {root}
        </p>
      )}

      {creatingFolder && (
        <Card className="flex items-center gap-2 p-3">
          <Folder className="h-4 w-4 shrink-0 text-muted-foreground" />
          <Input
            autoFocus
            value={folderName}
            onChange={(e) => setFolderName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submitNewFolder();
              if (e.key === "Escape") setCreatingFolder(false);
            }}
            placeholder="Folder name"
            className="h-8 flex-1"
          />
          <Button size="sm" onClick={submitNewFolder}>
            Create
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="h-8 w-8"
            onClick={() => setCreatingFolder(false)}
          >
            <X className="h-4 w-4" />
          </Button>
        </Card>
      )}

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading…
        </div>
      ) : error ? (
        <Card className="p-4 text-sm text-destructive">
          {error}
          <p className="mt-1 text-xs text-muted-foreground">
            The download folder may not exist yet. It is created on the first
            download.
          </p>
        </Card>
      ) : entries.length === 0 ? (
        <EmptyState
          icon={Folder}
          title="This folder is empty"
          description="Downloaded files will appear here."
        />
      ) : (
        <Card className="divide-y overflow-hidden">
          {entries.map((entry) => (
            <div
              key={entry.path}
              className="flex items-center gap-3 px-3 py-2.5 hover:bg-accent/40"
            >
              <div className="shrink-0 text-muted-foreground">
                {entry.is_dir ? (
                  <Folder className="h-5 w-5" />
                ) : (
                  <FileIcon className="h-5 w-5" />
                )}
              </div>

              <div className="min-w-0 flex-1">
                {renaming === entry.path ? (
                  <Input
                    autoFocus
                    value={renameValue}
                    onChange={(e) => setRenameValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") submitRename(entry);
                      if (e.key === "Escape") setRenaming(null);
                    }}
                    onBlur={() => submitRename(entry)}
                    className="h-8"
                  />
                ) : entry.is_dir ? (
                  <button
                    onClick={() => load(entry.path)}
                    className="truncate font-medium hover:underline"
                    title={entry.name}
                  >
                    {entry.name}
                  </button>
                ) : (
                  <span className="block truncate font-medium" title={entry.name}>
                    {entry.name}
                  </span>
                )}
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  {entry.is_dir ? (
                    <Badge variant="secondary" className="px-1.5 py-0">
                      folder
                    </Badge>
                  ) : (
                    <span>{formatBytes(entry.size)}</span>
                  )}
                  <span>·</span>
                  <span>{formatDate(entry.modified)}</span>
                </div>
              </div>

              <div className="flex shrink-0 items-center gap-1">
                {!entry.is_dir && (
                  <a href={api.fileDownloadUrl(entry.path)} download>
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-8 w-8"
                      title="Download"
                    >
                      <Download className="h-4 w-4" />
                    </Button>
                  </a>
                )}
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-8 w-8"
                  title="Rename"
                  disabled={busy === entry.path}
                  onClick={() => startRename(entry)}
                >
                  <Pencil className="h-4 w-4" />
                </Button>
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-8 w-8 text-muted-foreground hover:text-destructive"
                  title="Delete"
                  disabled={busy === entry.path}
                  onClick={() => handleDelete(entry)}
                >
                  {busy === entry.path ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Trash2 className="h-4 w-4" />
                  )}
                </Button>
              </div>
            </div>
          ))}
        </Card>
      )}
    </div>
  );
}
