"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Download, History, Home, Settings } from "lucide-react";
import { cn } from "@/lib/utils";

const nav = [
  { href: "/", label: "Home", icon: Home },
  { href: "/downloads", label: "Downloads", icon: Download },
  { href: "/history", label: "History", icon: History },
  { href: "/settings", label: "Settings", icon: Settings },
];

function useNavItems() {
  const pathname = usePathname();
  return nav.map((item) => ({
    ...item,
    active:
      item.href === "/"
        ? pathname === "/"
        : pathname.startsWith(item.href),
  }));
}

/** Vertical sidebar — shown on md+ screens. */
export function Sidebar() {
  const items = useNavItems();

  return (
    <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r bg-card px-3 py-6 md:flex">
      <div className="mb-8 flex items-center gap-2 px-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <Download className="h-4 w-4" />
        </div>
        <span className="text-lg font-bold tracking-tight">yt-dlp UI</span>
      </div>
      <nav className="flex flex-col gap-1">
        {items.map(({ href, label, icon: Icon, active }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              active
                ? "bg-accent text-accent-foreground"
                : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
            )}
          >
            <Icon className="h-4 w-4 shrink-0" />
            {label}
          </Link>
        ))}
      </nav>
      <div className="mt-auto px-3 text-xs text-muted-foreground">
        Self-hosted yt-dlp
      </div>
    </aside>
  );
}

/** Top bar with horizontal nav — shown on small screens only. */
export function MobileNav() {
  const items = useNavItems();

  return (
    <header className="sticky top-0 z-20 border-b bg-card/95 backdrop-blur md:hidden">
      <div className="flex items-center gap-2 px-4 py-3">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <Download className="h-4 w-4" />
        </div>
        <span className="font-bold tracking-tight">yt-dlp UI</span>
      </div>
      <nav className="flex gap-1 overflow-x-auto px-2 pb-2">
        {items.map(({ href, label, icon: Icon, active }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex shrink-0 items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
              active
                ? "bg-accent text-accent-foreground"
                : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
