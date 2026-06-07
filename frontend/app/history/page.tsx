"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { HistoryTable } from "@/components/HistoryTable";
import { api } from "@/lib/api";
import type { HistoryEntry } from "@/lib/types";

export default function HistoryPage() {
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);

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

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">History</h1>
        <p className="text-muted-foreground">Previously completed downloads.</p>
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (
        <HistoryTable entries={entries} />
      )}
    </div>
  );
}
