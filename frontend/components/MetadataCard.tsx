"use client";

import { Clock, User } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { formatDuration } from "@/lib/utils";
import type { Metadata } from "@/lib/types";

export function MetadataCard({ metadata }: { metadata: Metadata }) {
  return (
    <Card className="overflow-hidden">
      <CardContent className="flex flex-col gap-4 p-4 sm:flex-row">
        {metadata.thumbnail && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={metadata.thumbnail}
            alt={metadata.title}
            className="h-40 w-full rounded-lg object-cover sm:w-72"
          />
        )}
        <div className="flex flex-col justify-center gap-2">
          <h2 className="text-lg font-semibold leading-snug">
            {metadata.title}
          </h2>
          {metadata.uploader && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <User className="h-4 w-4" />
              {metadata.uploader}
            </div>
          )}
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Clock className="h-4 w-4" />
            {formatDuration(metadata.duration)}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
