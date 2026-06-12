"use client";

import type { Route } from "next";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode } from "react";

import { ThemeToggle } from "@/components/theme-toggle";

const navItems = [
  { href: "/", label: "Markets" },
  { href: "/grid", label: "Grid" },
  { href: "/events", label: "Events" },
  { href: "/power-bi", label: "Reports" },
  { href: "/developer", label: "API" },
] as const satisfies ReadonlyArray<{ href: Route; label: string }>;

function BrandLogo() {
  // Compact inline wordmark — adapts to the page's ink colour so it works
  // in both light and dark themes without an extra asset.
  return (
    <Link href="/" className="group flex items-center gap-3" aria-label="3xMarkets home">
      {/* Mark: a stylised mini chart spark inside a rounded accent square */}
      <span className="relative flex h-9 w-9 items-center justify-center overflow-hidden rounded-lg bg-ink shadow-sm">
        <svg viewBox="0 0 32 32" className="h-5 w-5" aria-hidden="true">
          <polyline
            points="3,22 9,18 13,20 18,12 23,15 29,7"
            fill="none"
            stroke="rgb(var(--accent))"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <circle cx="29" cy="7" r="2.2" fill="rgb(var(--accent))" />
        </svg>
      </span>
      <span className="flex items-baseline leading-none">
        <span className="font-display text-lg font-bold tracking-tight text-ink">3xMarkets</span>
      </span>
    </Link>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen bg-bg text-ink">
      {/* Top nav — 3-column grid keeps the brand dead-centre regardless of side content width */}
      <header className="sticky top-0 z-50 border-b border-seam bg-well/95 backdrop-blur-md">
        <div className="mx-auto grid max-w-[1440px] grid-cols-[1fr_auto_1fr] items-center gap-6 px-6 py-3">
          {/* Left: live indicator + section nav */}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 rounded-full border border-seam bg-surface px-3 py-1.5">
              <span className="live-dot h-1.5 w-1.5 rounded-full bg-accent" />
              <span className="font-mono text-[10px] uppercase tracking-widest text-accent">Live</span>
            </div>
            <nav className="hidden items-center gap-1 md:flex">
              {navItems.map((item) => {
                const active =
                  pathname === item.href ||
                  (item.href !== "/" && pathname.startsWith(item.href));
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-all ${
                      active
                        ? "border border-seam bg-surface text-ink shadow-sm"
                        : "text-ink/50 hover:bg-surface/60 hover:text-ink/80"
                    }`}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </div>

          {/* Centre: brand */}
          <div className="flex justify-center">
            <BrandLogo />
          </div>

          {/* Right: utilities */}
          <div className="flex items-center justify-end gap-2">
            <ThemeToggle />
          </div>
        </div>
      </header>

      {/* Page content */}
      <div className="mx-auto max-w-[1440px] px-6 py-6">{children}</div>
    </div>
  );
}
