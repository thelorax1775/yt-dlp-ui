"use client";

import { Clock, User } from "lucide-react";
import { Card } from "@/components/ui/card";
import { formatDuration } from "@/lib/utils";
import type { Metadata } from "@/lib/types";

export function MetadataCard({ metadata }: { metadata: Metadata }) {
  return (
    <Card className="overflow-hidden">
      {metadata.thumbnail && (
        <div className="relative aspect-video w-full bg-muted">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={metadata.thumbnail}
            alt={metadata.title}
            className="h-full w-full object-cover"
          />
          {metadata.duration ? (
            <span className="absolute bottom-2 right-2 rounded bg-black/80 px-1.5 py-0.5 text-xs font-medium text-white">
              {formatDuration(metadata.duration)}
            </span>
          ) : null}
        </div>
      )}
      <div className="flex flex-col gap-2 p-4">
        <h2 className="font-semibold leading-snug" title={metadata.title}>
          {metadata.title}
        </h2>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
          {metadata.uploader && (
            <span className="flex items-center gap-1.5">
              <User className="h-4 w-4 shrink-0" />
              <span className="truncate">{metadata.uploader}</span>
            </span>
          )}
          <span className="flex items-center gap-1.5">
            <Clock className="h-4 w-4 shrink-0" />
            {formatDuration(metadata.duration)}
          </span>
        </div>
      </div>
    </Card>
  );
}
