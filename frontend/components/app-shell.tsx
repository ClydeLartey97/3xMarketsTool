"use client";

import type { Route } from "next";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode } from "react";

import { ThemeToggle } from "@/components/theme-toggle";

const navItems = [
  { href: "/", label: "Markets" },
  { href: "/events", label: "Event Intel" },
  { href: "/developer", label: "API" },
] as const satisfies ReadonlyArray<{ href: Route; label: string }>;

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen bg-bg text-ink">
      {/* Top nav */}
      <header className="sticky top-0 z-50 border-b border-seam bg-well/95 backdrop-blur-md">
        <div className="mx-auto flex max-w-[1440px] items-center gap-6 px-6 py-3">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-3 shrink-0">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent font-mono text-sm font-bold text-accent-fg">
              3x
            </div>
            <span className="hidden font-semibold tracking-tight text-ink/80 sm:block">
              Market Intelligence
            </span>
          </Link>

          {/* Live indicator */}
          <div className="flex items-center gap-2 rounded-full border border-seam bg-surface px-3 py-1.5">
            <span className="live-dot h-1.5 w-1.5 rounded-full bg-accent" />
            <span className="font-mono text-[10px] uppercase tracking-widest text-accent">Live</span>
          </div>

          {/* Nav */}
          <nav className="flex items-center gap-1 ml-auto">
            {navItems.map((item) => {
              const active = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`rounded-lg px-3.5 py-2 text-sm font-medium transition-all ${
                    active
                      ? "bg-surface text-ink shadow-sm border border-seam"
                      : "text-ink/45 hover:bg-surface/60 hover:text-ink/80"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>

          {/* Theme toggle */}
          <ThemeToggle />
        </div>
      </header>

      {/* Page content */}
      <div className="mx-auto max-w-[1440px] px-6 py-6">
        {children}
      </div>
    </div>
  );
}
