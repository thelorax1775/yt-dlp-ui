"use client";

import { ExternalLink } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Card } from "@/components/ui/card";
import { formatDate } from "@/lib/utils";
import type { HistoryEntry } from "@/lib/types";

function Thumb({ src }: { src?: string | null }) {
  return src ? (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt="" className="h-12 w-20 rounded object-cover" />
  ) : (
    <div className="h-12 w-20 rounded bg-muted" />
  );
}

export function HistoryTable({ entries }: { entries: HistoryEntry[] }) {
  return (
    <>
      {/* Mobile: stacked cards */}
      <div className="flex flex-col gap-3 md:hidden">
        {entries.map((e) => (
          <Card key={e.id} className="flex gap-3 p-3">
            <Thumb src={e.thumbnail} />
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium" title={e.title || ""}>
                {e.title || "Unknown"}
              </p>
              <p className="text-xs text-muted-foreground">
                {formatDate(e.finished_at)}
              </p>
              {e.file_path && (
                <p
                  className="mt-1 truncate text-xs text-muted-foreground"
                  title={e.file_path}
                >
                  {e.file_path}
                </p>
              )}
              {e.url && (
                <a
                  href={e.url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-1 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground hover:underline"
                >
                  <ExternalLink className="h-3 w-3" /> Source
                </a>
              )}
            </div>
          </Card>
        ))}
      </div>

      {/* Desktop: table */}
      <Card className="hidden overflow-hidden md:block">
        <Table className="table-fixed">
          <TableHeader>
            <TableRow>
              <TableHead className="w-24">Thumbnail</TableHead>
              <TableHead className="w-[40%]">Title</TableHead>
              <TableHead className="w-44">Date</TableHead>
              <TableHead>File</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {entries.map((e) => (
              <TableRow key={e.id}>
                <TableCell>
                  <Thumb src={e.thumbnail} />
                </TableCell>
                <TableCell>
                  <div className="truncate font-medium" title={e.title || ""}>
                    {e.title || "Unknown"}
                  </div>
                  {e.url && (
                    <a
                      href={e.url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex max-w-full items-center gap-1 truncate text-xs text-muted-foreground hover:text-foreground hover:underline"
                      title={e.url}
                    >
                      <ExternalLink className="h-3 w-3 shrink-0" />
                      <span className="truncate">{e.url}</span>
                    </a>
                  )}
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {formatDate(e.finished_at)}
                </TableCell>
                <TableCell>
                  <span
                    className="block truncate text-xs text-muted-foreground"
                    title={e.file_path || ""}
                  >
                    {e.file_path || "—"}
                  </span>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </>
  );
}
