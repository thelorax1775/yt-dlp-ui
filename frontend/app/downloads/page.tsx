"use client";

import { useEffect, useReducer } from "react";
import { Download } from "lucide-react";
import { JobCard } from "@/components/JobCard";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState } from "@/components/EmptyState";
import { api } from "@/lib/api";
import type { Job } from "@/lib/types";

type State = Record<string, Job>;
type Action = { type: "upsert"; job: Job } | { type: "init"; jobs: Job[] };

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "init": {
      const next: State = {};
      for (const j of action.jobs) next[j.id] = j;
      return next;
    }
    case "upsert":
      return { ...state, [action.job.id]: action.job };
    default:
      return state;
  }
}

function useJobStream(): State {
  const [jobs, dispatch] = useReducer(reducer, {});

  useEffect(() => {
    let es: EventSource | null = null;
    let cancelled = false;

    (async () => {
      try {
        const initial = await api.getJobs();
        if (!cancelled) dispatch({ type: "init", jobs: initial });
      } catch {
        /* ignore */
      }

      es = new EventSource("/api/jobs/stream");
      es.onmessage = (e) => {
        try {
          const job: Job = JSON.parse(e.data);
          dispatch({ type: "upsert", job });
        } catch {
          /* ignore malformed */
        }
      };
    })();

    return () => {
      cancelled = true;
      es?.close();
    };
  }, []);

  return jobs;
}

const STATUS_ORDER: Record<string, number> = {
  downloading: 0,
  queued: 1,
  failed: 2,
  cancelled: 3,
  finished: 4,
};

export default function DownloadsPage() {
  const jobsMap = useJobStream();
  const jobs = Object.values(jobsMap).sort((a, b) => {
    const sa = STATUS_ORDER[a.status] ?? 9;
    const sb = STATUS_ORDER[b.status] ?? 9;
    if (sa !== sb) return sa - sb;
    const ta = a.created_at ? Date.parse(a.created_at) : 0;
    const tb = b.created_at ? Date.parse(b.created_at) : 0;
    return tb - ta;
  });

  const active = jobs.filter(
    (j) => j.status === "downloading" || j.status === "queued"
  ).length;

  return (
    <div>
      <PageHeader
        title="Downloads"
        description={
          active > 0
            ? `${active} active · live progress updates`
            : "Live progress for active and recent jobs."
        }
      />

      {jobs.length === 0 ? (
        <EmptyState
          icon={Download}
          title="No download jobs yet"
          description="Queue a download from the Home page and it will appear here with live progress."
        />
      ) : (
        <div className="flex flex-col gap-3">
          {jobs.map((job) => (
            <JobCard key={job.id} job={job} />
          ))}
        </div>
      )}
    </div>
  );
}
