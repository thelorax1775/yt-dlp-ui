"use client";

import { RotateCw, X } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { api } from "@/lib/api";
import type { Job, JobStatus } from "@/lib/types";

const statusVariant: Record<
  JobStatus,
  "default" | "secondary" | "destructive" | "success" | "warning"
> = {
  queued: "secondary",
  downloading: "default",
  finished: "success",
  failed: "destructive",
  cancelled: "warning",
};

export function JobCard({ job }: { job: Job }) {
  const isActive = job.status === "queued" || job.status === "downloading";
  const canRetry = job.status === "failed" || job.status === "cancelled";

  async function handleCancel() {
    try {
      await api.cancelJob(job.id);
    } catch (e) {
      toast.error("Cancel failed", {
        description: e instanceof Error ? e.message : String(e),
      });
    }
  }

  async function handleRetry() {
    try {
      await api.retryJob(job.id);
      toast.success("Job re-queued");
    } catch (e) {
      toast.error("Retry failed", {
        description: e instanceof Error ? e.message : String(e),
      });
    }
  }

  return (
    <Card className="p-4">
      <div className="flex items-start gap-3">
        {job.thumbnail ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={job.thumbnail}
            alt=""
            className="hidden h-16 w-28 shrink-0 rounded object-cover sm:block"
          />
        ) : null}
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate font-medium" title={job.title || job.url}>
                {job.title || job.url}
              </p>
              <p className="truncate text-xs text-muted-foreground">{job.url}</p>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              <Badge variant={statusVariant[job.status]}>{job.status}</Badge>
              {isActive && (
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-7 w-7"
                  onClick={handleCancel}
                  title="Cancel"
                >
                  <X className="h-4 w-4" />
                </Button>
              )}
              {canRetry && (
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-7 w-7"
                  onClick={handleRetry}
                  title="Retry"
                >
                  <RotateCw className="h-4 w-4" />
                </Button>
              )}
            </div>
          </div>

          {isActive && (
            <div className="mt-3 flex flex-col gap-1">
              <Progress value={job.progress} />
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>{job.progress.toFixed(1)}%</span>
                <span className="truncate pl-2">
                  {job.speed ? job.speed : ""}
                  {job.eta ? ` · ETA ${job.eta}` : ""}
                </span>
              </div>
            </div>
          )}

          {job.status === "finished" && job.file_path && (
            <p
              className="mt-2 truncate text-xs text-muted-foreground"
              title={job.file_path}
            >
              Saved to {job.file_path}
            </p>
          )}

          {job.status === "failed" && job.error && (
            <p className="mt-2 break-words text-xs text-destructive">
              {job.error}
            </p>
          )}
        </div>
      </div>
    </Card>
  );
}
