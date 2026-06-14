"use client";

import { useTheme } from "next-themes";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";

const THEMES = ["light", "dark", "system"] as const;
type Theme = (typeof THEMES)[number];

const LABELS: Record<Theme, string> = { system: "System", light: "Sun", dark: "Moon" };

const ICONS: Record<Theme, ReactNode> = {
  system: (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2v2" />
      <path d="M12 20v2" />
      <path d="M4.93 4.93l1.41 1.41" />
      <path d="M17.66 17.66l1.41 1.41" />
      <path d="M2 12h2" />
      <path d="M20 12h2" />
      <circle cx="12" cy="12" r="4" />
      <path d="M21 12.6A7.5 7.5 0 0 1 11.4 3" />
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
    return <div className="h-8 w-[92px] rounded-lg border border-seam bg-well" />;
  }

  const current = (THEMES.includes(theme as Theme) ? theme : "system") as Theme;

  return (
    <div
      className="flex h-8 items-center rounded-lg border border-seam bg-well p-0.5 text-ink/40"
      aria-label="Theme"
      role="group"
    >
      {THEMES.map((item) => {
        const selected = item === current;
        return (
          <button
            key={item}
            type="button"
            onClick={() => setTheme(item)}
            aria-label={`${LABELS[item]} theme`}
            aria-pressed={selected}
            title={`${LABELS[item]} theme`}
            className={`flex h-7 w-7 items-center justify-center rounded-md transition-all ${
              selected
                ? "bg-surface text-accent shadow-sm"
                : "hover:bg-surface/60 hover:text-ink/70"
            }`}
          >
            {ICONS[item]}
          </button>
        );
      })}
    </div>
  );
}
