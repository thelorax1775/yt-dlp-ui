"use client";

import { useEffect, useReducer } from "react";
import { JobCard } from "@/components/JobCard";
import { api } from "@/lib/api";
import type { Job } from "@/lib/types";

type State = Record<string, Job>;
type Action =
  | { type: "upsert"; job: Job }
  | { type: "init"; jobs: Job[] };

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
      es.onerror = () => {
        // EventSource auto-reconnects; nothing to do
      };
    })();

    return () => {
      cancelled = true;
      es?.close();
    };
  }, []);

  return jobs;
}

export default function DownloadsPage() {
  const jobsMap = useJobStream();
  const jobs = Object.values(jobsMap).sort((a, b) => {
    const ta = a.created_at ? Date.parse(a.created_at) : 0;
    const tb = b.created_at ? Date.parse(b.created_at) : 0;
    return tb - ta;
  });

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Downloads</h1>
        <p className="text-muted-foreground">
          Live progress for active and recent jobs.
        </p>
      </div>

      {jobs.length === 0 ? (
        <p className="text-sm text-muted-foreground">No download jobs yet.</p>
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
