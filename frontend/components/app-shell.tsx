"use client";

import type { Route } from "next";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode } from "react";

import { ThemeToggle } from "@/components/theme-toggle";

const navItems = [
  { href: "/", label: "Markets" },
  { href: "/radar", label: "Radar" },
  { href: "/grid", label: "Grid" },
  { href: "/events", label: "Events" },
  { href: "/power-bi", label: "Reports" },
  { href: "/developer", label: "API" },
] as const satisfies ReadonlyArray<{ href: Route; label: string }>;

function BrandLogo() {
  // Masthead-style wordmark: display serif with an italic "x", set straight
  // on the header — no icon, no glow, no box. The type itself is the mark.
  return (
    <Link href="/" className="group flex items-baseline" aria-label="3xMarkets home">
      <span className="font-display text-[22px] font-medium leading-none tracking-[-0.01em] text-ink">
        3<span className="italic text-accent">x</span>Markets
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
          {/* Left: section nav */}
          <div className="flex items-center gap-3">
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
      <div className="mx-auto max-w-[1440px] px-6 py-8 sm:px-8 sm:py-10">{children}</div>
    </div>
  );
}
