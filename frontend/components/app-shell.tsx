import type { Route } from "next";
import Link from "next/link";
import { ReactNode } from "react";

const navItems = [
  { href: "/", label: "Dashboard" },
  { href: "/events", label: "Event Intelligence" },
  { href: "/developer", label: "Developer" },
] as const satisfies ReadonlyArray<{ href: Route; label: string }>;

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(210,228,238,0.85),_transparent_40%),linear-gradient(180deg,_#edf3f7_0%,_#e4ecf2_100%)] text-ink">
      <div className="mx-auto max-w-7xl px-6 py-8">
        <header className="mb-8 rounded-[1.8rem] border border-white/70 bg-white/78 px-6 py-5 shadow-panel backdrop-blur">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="flex items-center gap-3">
                <div className="rounded-xl bg-slate px-3 py-2 text-sm font-semibold uppercase tracking-[0.24em] text-white">
                  3x
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.22em] text-slate/50">Power intelligence platform</p>
                  <h1 className="font-display text-3xl text-slate">Energy Market Intelligence</h1>
                </div>
              </div>
            </div>
            <nav className="flex flex-wrap gap-3">
              {navItems.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="rounded-full border border-slate/10 bg-[#f5f8fb] px-4 py-2 text-sm text-slate transition hover:border-slate/20 hover:bg-white"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>
        {children}
      </div>
    </div>
  );
}
