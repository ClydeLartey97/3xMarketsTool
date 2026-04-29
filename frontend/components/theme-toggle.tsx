"use client";

import { useTheme } from "next-themes";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";

const THEMES = ["system", "light", "dark"] as const;
type Theme = (typeof THEMES)[number];

const LABELS: Record<Theme, string> = { system: "Auto", light: "Light", dark: "Dark" };

const ICONS: Record<Theme, ReactNode> = {
  system: (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <path d="M12 2a10 10 0 0 1 0 20" fill="currentColor" stroke="none" opacity="0.35" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  ),
  light: (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="4" />
      <line x1="12" y1="2" x2="12" y2="5" />
      <line x1="12" y1="19" x2="12" y2="22" />
      <line x1="4.22" y1="4.22" x2="6.34" y2="6.34" />
      <line x1="17.66" y1="17.66" x2="19.78" y2="19.78" />
      <line x1="2" y1="12" x2="5" y2="12" />
      <line x1="19" y1="12" x2="22" y2="12" />
      <line x1="4.22" y1="19.78" x2="6.34" y2="17.66" />
      <line x1="17.66" y1="6.34" x2="19.78" y2="4.22" />
    </svg>
  ),
  dark: (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  ),
};

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return <div className="h-7 w-16 rounded-lg border border-seam bg-well" />;
  }

  const current = (THEMES.includes(theme as Theme) ? theme : "system") as Theme;
  const next = THEMES[(THEMES.indexOf(current) + 1) % THEMES.length];

  return (
    <button
      onClick={() => setTheme(next)}
      aria-label={`Theme: ${LABELS[current]}. Click to switch to ${LABELS[next]}.`}
      title={`Theme: ${LABELS[current]} — click for ${LABELS[next]}`}
      className="flex items-center gap-1.5 rounded-lg border border-seam bg-well px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-widest text-ink/40 transition-all hover:border-seam-hi hover:text-ink/70"
    >
      <span className="text-accent">{ICONS[current]}</span>
      {LABELS[current]}
    </button>
  );
}
