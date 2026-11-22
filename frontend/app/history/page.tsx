"use client";

import { useEffect, useState } from "react";
import { History, Loader2, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { HistoryTable } from "@/components/HistoryTable";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { HistoryEntry } from "@/lib/types";

export default function HistoryPage() {
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [clearing, setClearing] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        setEntries(await api.getHistory());
      } catch (e) {
        toast.error("Failed to load history", {
          description: e instanceof Error ? e.message : String(e),
        });
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function handleClear() {
    if (!window.confirm("Clear the whole download history? Downloaded files are kept.")) {
      return;
    }
    setClearing(true);
    try {
      const result = await api.clearHistory();
      setEntries([]);
      toast.success("History cleared", {
        description: `${result.count} ${result.count === 1 ? "entry" : "entries"} removed. Downloaded files are kept.`,
      });
    } catch (e) {
      toast.error("Failed to clear history", {
        description: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setClearing(false);
    }
  }

  async function handleDelete(id: string) {
    try {
      await api.deleteHistoryEntry(id);
      setEntries((current) => current.filter((entry) => entry.id !== id));
      toast.success("History entry deleted");
    } catch (e) {
      toast.error("Failed to delete history entry", {
        description: e instanceof Error ? e.message : String(e),
      });
    }
  }

  return (
    <div>
      <PageHeader
        title="History"
        description="Previously completed downloads."
        action={
          <Button
            variant="outline"
            onClick={handleClear}
            disabled={loading || clearing || entries.length === 0}
          >
            <Trash2 /> Clear history
          </Button>
        }
      />

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading…
        </div>
      ) : entries.length === 0 ? (
        <EmptyState
          icon={History}
          title="No history yet"
          description="Completed downloads will be listed here."
        />
      ) : (
        <HistoryTable entries={entries} onDelete={handleDelete} />
      )}
    </div>
  );
}
