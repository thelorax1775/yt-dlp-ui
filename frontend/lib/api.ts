import type {
  DownloadRequest,
  HistoryEntry,
  Job,
  Metadata,
  MountResult,
  Settings,
  Share,
  ShareCreate,
} from "./types";

async function handle<T>(resPromise: Promise<Response>): Promise<T> {
  const res = await resPromise;
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  fetchMetadata: (url: string) =>
    handle<Metadata>(fetch(`/api/info?url=${encodeURIComponent(url)}`)),

  startDownload: (req: DownloadRequest) =>
    handle<Job>(
      fetch("/api/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      })
    ),

  getJobs: () => handle<Job[]>(fetch("/api/jobs")),

  cancelJob: (id: string) =>
    handle<{ status: string }>(fetch(`/api/jobs/${id}`, { method: "DELETE" })),

  retryJob: (id: string) =>
    handle<Job>(fetch(`/api/jobs/${id}/retry`, { method: "POST" })),

  getHistory: () => handle<HistoryEntry[]>(fetch("/api/history")),

  getSettings: () => handle<Settings>(fetch("/api/settings")),

  updateSettings: (data: Partial<Settings>) =>
    handle<Settings>(
      fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      })
    ),

  getShares: () => handle<Share[]>(fetch("/api/shares")),

  createShare: (data: ShareCreate) =>
    handle<Share>(
      fetch("/api/shares", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      })
    ),

  deleteShare: (id: number) =>
    handle<{ status: string }>(fetch(`/api/shares/${id}`, { method: "DELETE" })),

  mountShare: (id: number) =>
    handle<MountResult>(fetch(`/api/shares/${id}/mount`, { method: "POST" })),

  unmountShare: (id: number) =>
    handle<MountResult>(fetch(`/api/shares/${id}/unmount`, { method: "POST" })),
};
