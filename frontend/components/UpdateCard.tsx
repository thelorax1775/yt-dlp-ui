"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";
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
import { api } from "@/lib/api";
import type { UpdateCheck, UpdateJob } from "@/lib/types";

const short = (v: string) => (/^[0-9a-f]{40}$/.test(v) ? v.slice(0, 7) : v);

export function UpdateCard() {
  const [check, setCheck] = useState<UpdateCheck | null>(null);
  const [job, setJob] = useState<UpdateJob | null>(null);
  const [checking, setChecking] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [token, setToken] = useState("");
  const [starting, setStarting] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async () => {
    setChecking(true);
    try {
      setCheck(await api.checkUpdate());
    } catch (e) {
      toast.error("Update check failed", {
        description: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    (async () => {
      await refresh();
      try {
        setJob((await api.getUpdateStatus()).job);
      } catch {
        /* status is optional */
      }
    })();
  }, [refresh]);

  const active = job?.status === "running" || job?.status === "restarting";

  // Poll the job. While the backend restarts the request fails; keep trying.
  useEffect(() => {
    if (!active) return;
    timer.current = setInterval(async () => {
      try {
        const r = await api.getUpdateStatus();
        setJob(r.job);
        if (r.job && r.job.status !== "running" && r.job.status !== "restarting") {
          refresh();
        }
      } catch {
        /* backend restarting */
      }
    }, 2000);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [active, refresh]);

  async function start() {
    setStarting(true);
    try {
      const r = await api.startUpdate(token);
      setJob(r.job);
      setConfirming(false);
      setToken("");
    } catch (e) {
      toast.error("Could not start the update", {
        description: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setStarting(false);
    }
  }

  const canUpdate = !!check?.update_available && !active;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Updates</CardTitle>
        <CardDescription>
          Update this app to the newest version on GitHub.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          <dt className="text-muted-foreground">Installed</dt>
          <dd className="font-mono" data-testid="update-installed">
            {check ? short(check.installed) : "…"}
          </dd>
          <dt className="text-muted-foreground">Newest</dt>
          <dd className="font-mono" data-testid="update-latest">
            {check?.latest ? `${check.latest.label}` : "—"}
          </dd>
        </dl>
        {check && (
          <p className="text-sm text-muted-foreground" data-testid="update-message">
            {check.message}
            {check.update_available && !check.update_enabled &&
              " Updating from here is not enabled on this install (see README, Updating)."}
          </p>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" onClick={refresh} disabled={checking || active}>
            {checking ? <Loader2 className="animate-spin" /> : <RefreshCw />}
            Check
          </Button>
          <Button
            onClick={() => setConfirming(true)}
            disabled={!canUpdate || !check?.update_enabled}
          >
            Update
          </Button>
        </div>

        {confirming && canUpdate && (
          <div className="space-y-2 rounded-md border p-3">
            <p className="text-sm">
              Update from {check && short(check.installed)} to{" "}
              {check?.latest?.label}? The app restarts for a short while. Enter
              the admin token (<code>UPDATE_ADMIN_TOKEN</code>) to confirm.
            </p>
            <Input
              type="password"
              autoComplete="off"
              placeholder="Admin token"
              value={token}
              onChange={(e) => setToken(e.target.value)}
            />
            <div className="flex gap-2">
              <Button onClick={start} disabled={!token || starting}>
                {starting && <Loader2 className="animate-spin" />}
                Confirm update
              </Button>
              <Button variant="ghost" onClick={() => setConfirming(false)}>
                Cancel
              </Button>
            </div>
          </div>
        )}

        {job && (
          <div className="space-y-1">
            <p className="text-sm font-medium" data-testid="update-job-status">
              Last update: {job.status}
              {job.error ? ` — ${job.error}` : ""}
            </p>
            <pre className="max-h-64 overflow-auto rounded-md bg-muted p-2 text-xs">
              {job.log.join("\n")}
            </pre>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
