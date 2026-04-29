import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        /* ── Theme-aware semantic tokens (CSS var backed) ── */
        bg:       "rgb(var(--bg) / <alpha-value>)",
        surface:  "rgb(var(--surface) / <alpha-value>)",
        well:     "rgb(var(--well) / <alpha-value>)",
        seam:     "rgb(var(--seam) / <alpha-value>)",
        "seam-hi":"rgb(var(--seam-hi) / <alpha-value>)",
        ink:      "rgb(var(--ink) / <alpha-value>)",
        accent:   "rgb(var(--accent) / <alpha-value>)",
        "accent-fg": "rgb(var(--accent-fg) / <alpha-value>)",
        "price-up":  "rgb(var(--price-up) / <alpha-value>)",
        "price-dn":  "rgb(var(--price-dn) / <alpha-value>)",
        "price-hot": "rgb(var(--price-hot) / <alpha-value>)",
        "price-warn":"rgb(var(--price-warn) / <alpha-value>)",
        "price-info":"rgb(var(--price-info) / <alpha-value>)",

        /* ── Static legacy tokens (kept for backwards compat) ── */
        signal:   "#f97316",
        positive: "#10b981",
        caution:  "#f59e0b",
        danger:   "#ef4444",
      },
      fontFamily: {
        sans:    ["Inter", "Segoe UI", "Helvetica Neue", "sans-serif"],
        display: ["Inter", "Segoe UI", "Helvetica Neue", "sans-serif"],
        mono:    ["JetBrains Mono", "Fira Code", "ui-monospace", "monospace"],
      },
      boxShadow: {
        panel:      "0 1px 3px rgba(0,0,0,0.06), 0 8px 32px rgba(0,0,0,0.04)",
        "panel-dark":"0 20px 60px rgba(4,10,18,0.55), 0 2px 8px rgba(0,0,0,0.3)",
        glow:       "0 0 0 1px rgba(16,185,129,0.25), 0 0 20px rgba(16,185,129,0.08)",
        "glow-danger":"0 0 0 1px rgba(239,68,68,0.25), 0 0 20px rgba(239,68,68,0.08)",
        float:      "0 24px 80px rgba(7,14,22,0.65)",
      },
      borderRadius: {
        card: "1.5rem",
        pill: "99px",
      },
      animation: {
        "fade-in":  "fadeIn 0.2s ease-out",
        "slide-up": "slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1)",
      },
      keyframes: {
        fadeIn:  { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        slideUp: { "0%": { opacity: "0", transform: "translateY(8px)" }, "100%": { opacity: "1", transform: "translateY(0)" } },
      },
    },
  },
  plugins: [],
};

export default config;
