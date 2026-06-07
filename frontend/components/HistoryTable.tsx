"use client";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDate } from "@/lib/utils";
import type { HistoryEntry } from "@/lib/types";

export function HistoryTable({ entries }: { entries: HistoryEntry[] }) {
  if (entries.length === 0) {
    return <p className="text-sm text-muted-foreground">No history yet.</p>;
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-28">Thumbnail</TableHead>
          <TableHead>Title</TableHead>
          <TableHead>Date</TableHead>
          <TableHead>File</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {entries.map((e) => (
          <TableRow key={e.id}>
            <TableCell>
              {e.thumbnail ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={e.thumbnail}
                  alt=""
                  className="h-12 w-20 rounded object-cover"
                />
              ) : (
                <div className="h-12 w-20 rounded bg-muted" />
              )}
            </TableCell>
            <TableCell className="max-w-xs">
              <div className="truncate font-medium" title={e.title || ""}>
                {e.title || "Unknown"}
              </div>
              {e.url && (
                <a
                  href={e.url}
                  target="_blank"
                  rel="noreferrer"
                  className="truncate text-xs text-muted-foreground hover:underline block max-w-xs"
                  title={e.url}
                >
                  {e.url}
                </a>
              )}
            </TableCell>
            <TableCell className="whitespace-nowrap text-sm text-muted-foreground">
              {formatDate(e.finished_at)}
            </TableCell>
            <TableCell className="max-w-xs">
              <span
                className="truncate text-xs text-muted-foreground block max-w-xs"
                title={e.file_path || ""}
              >
                {e.file_path || "—"}
              </span>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
