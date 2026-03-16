import Link from "next/link";
import { ReactNode } from "react";

const navItems = [
  { href: "/", label: "Dashboard" },
  { href: "/events", label: "Event Intelligence" },
  { href: "/developer", label: "Developer" },
];

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(15,159,124,0.12),_transparent_40%),linear-gradient(180deg,_#f3f7fb_0%,_#e8eff5_100%)] text-ink">
      <div className="mx-auto max-w-7xl px-6 py-8">
        <header className="mb-8 rounded-[2rem] border border-white/60 bg-white/75 px-6 py-5 shadow-panel backdrop-blur">
          <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.28em] text-slate/70">3x</p>
              <h1 className="font-display text-4xl text-slate">Energy Market Intelligence</h1>
              <p className="mt-2 max-w-2xl text-sm text-slate/75">
                Probabilistic electricity market forecasts, structured event intelligence, and
                operational alerts designed for traders, battery operators, and analysts.
              </p>
            </div>
            <nav className="flex gap-3">
              {navItems.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="rounded-full border border-slate/10 bg-slate px-4 py-2 text-sm text-white transition hover:bg-ink"
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
