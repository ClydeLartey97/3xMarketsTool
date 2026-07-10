"use client";
/**
 * Right-rail bubble stack. When the hero scrolls out of view, three
 * smaller bubbles slide in from the right edge of the viewport,
 * vertically stacked, so the user never loses sight of their Risk /
 * Likely / Upside while reading the evidence below.
 *
 * The "Edit" affordance scrolls back to the hero and re-focuses the
 * input bar. On mobile (< sm) we fall back to a slim top-bar collapsed
 * sheet because a side rail eats too much horizontal width on phones.
 */
import { useState } from "react";

import type { RiskAssessment } from "@/lib/api";

const APP_NAV_HEIGHT_PX = 60; // matches the sticky header in app-shell.tsx

export type RiskStickyBarProps = {
  visible: boolean;
  data: RiskAssessment | null;
  loading: boolean;
  marketName: string;
  marketCode: string;
  onEdit: () => void;
};

function formatGbp(value: number, signed = false): string {
  const sign = value < 0 ? "-" : signed && value > 0 ? "+" : "";
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${sign}£${(abs / 1_000_000).toFixed(2)}m`;
  if (abs >= 10_000) return `${sign}£${(abs / 1000).toFixed(1)}k`;
  if (abs >= 1000) return `${sign}£${(abs / 1000).toFixed(2)}k`;
  return `${sign}£${abs.toFixed(0)}`;
}

export function RiskStickyBar({
  visible,
  data,
  loading,
  marketName,
  marketCode,
  onEdit,
}: RiskStickyBarProps) {
  const [mobileExpandRequested, setMobileExpandRequested] = useState(false);
  const mobileExpanded = visible && mobileExpandRequested;

  const risk = data ? formatGbp(data.risk_gbp) : loading ? "…" : "—";
  const likely = data ? formatGbp(data.likely_gbp, true) : loading ? "…" : "—";
  const upside = data ? formatGbp(data.upside_gbp, true) : loading ? "…" : "—";
  const likelyTone: "up" | "dn" = data && data.likely_gbp < 0 ? "dn" : "up";

  return (
    <>
      {/* Desktop / tablet: right-rail vertical bubble stack */}
      <aside
        aria-hidden={!visible}
        aria-label="Risk read"
        className={`fixed right-4 z-40 hidden flex-col items-center gap-3 transition-all duration-300 ease-out sm:flex ${
          visible ? "translate-x-0 opacity-100" : "translate-x-[140%] opacity-0 pointer-events-none"
        }`}
        style={{ top: APP_NAV_HEIGHT_PX + 24 }}
      >
        <div className="mb-1 flex flex-col items-center gap-0.5">
          <span className="rounded-md bg-ink/5 px-2 py-0.5 text-[11px] font-medium text-ink/55">
            {marketCode}
          </span>
          <span className="max-w-[120px] truncate text-center text-[10px] text-ink/45">
            {marketName}
          </span>
        </div>

        <MiniBubble label="Risk" value={risk} tone="risk" loading={loading} />
        <MiniBubble label="Likely" value={likely} tone={likelyTone === "up" ? "likely" : "risk"} loading={loading} />
        <MiniBubble label="Upside" value={upside} tone="upside" loading={loading} />

        <button
          type="button"
          onClick={onEdit}
          title="Jump back to inputs"
          className="mt-1 rounded-full border border-seam bg-surface px-3 py-1.5 text-xs font-medium text-ink/60 shadow-sm transition hover:border-seam-hi hover:text-ink"
        >
          Edit
        </button>
        <span
          title="Modelled distributions, not realised outcomes. Educational tool — not financial advice."
          className="mt-1 rounded-full border border-seam/60 bg-surface/70 px-2 py-0.5 text-[11px] font-medium text-ink/35"
        >
          Not advice
        </span>
      </aside>

      {/* Mobile (< sm): slim top bar that can expand to a sheet */}
      <div
        aria-hidden={!visible}
        className={`fixed inset-x-0 z-40 border-b border-seam bg-surface/95 backdrop-blur-md transition-transform duration-200 ease-out sm:hidden ${
          visible ? "translate-y-0" : "-translate-y-full"
        }`}
        style={{ top: APP_NAV_HEIGHT_PX }}
      >
        <button
          type="button"
          onClick={() => setMobileExpandRequested((v) => !v)}
          className="flex w-full items-center gap-3 px-4 py-2 text-left"
        >
          <span className="rounded-md bg-ink/5 px-2 py-0.5 text-[11px] font-medium text-ink/55">
            {marketCode}
          </span>
          <span className="inline-flex items-baseline gap-1.5">
            <span className="text-xs font-medium text-ink/40">Risk</span>
            <span className="text-sm font-semibold tabular-nums text-price-dn">{risk}</span>
          </span>
          <span className="ml-auto text-xs text-ink/40">{mobileExpanded ? "−" : "···"}</span>
        </button>
        {mobileExpanded ? (
          <div className="border-t border-seam bg-surface px-4 pb-3 pt-2">
            <div className="grid grid-cols-3 gap-2">
              <CompactCell label="Risk" value={risk} tone="dn" />
              <CompactCell label="Likely" value={likely} tone={likelyTone} />
              <CompactCell label="Upside" value={upside} tone="up" />
            </div>
            <button
              type="button"
              onClick={onEdit}
              className="mt-2 w-full rounded-md border border-seam bg-bg px-3 py-1.5 text-xs font-medium text-ink/65"
            >
              Edit inputs
            </button>
          </div>
        ) : null}
      </div>
    </>
  );
}

// Colour lives only in the number — the circles themselves stay neutral
// (hairline border, flat surface, no glow), matching the hero bubbles.
const TONE_BUBBLE: Record<"risk" | "likely" | "upside", { text: string }> = {
  risk: { text: "text-price-dn" },
  likely: { text: "text-price-up" },
  upside: { text: "text-price-up" },
};

function MiniBubble({
  label,
  value,
  tone,
  loading,
}: {
  label: string;
  value: string;
  tone: "risk" | "likely" | "upside";
  loading: boolean;
}) {
  const cls = TONE_BUBBLE[tone];
  return (
    <div
      className={`flex h-[88px] w-[88px] flex-col items-center justify-center rounded-full border border-seam bg-surface/95 shadow-sm backdrop-blur transition ${
        loading ? "animate-pulse" : ""
      }`}
    >
      <span className="mb-0.5 text-[10px] font-medium text-ink/40">{label}</span>
      <span className={`font-mono text-[13px] font-semibold tabular-nums leading-tight ${cls.text}`}>
        {value}
      </span>
    </div>
  );
}

function CompactCell({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "up" | "dn";
}) {
  const toneClass = tone === "up" ? "text-price-up" : "text-price-dn";
  return (
    <div className="rounded-lg border border-seam bg-bg px-2.5 py-1.5 text-center">
      <p className="text-[11px] font-medium text-ink/45">{label}</p>
      <p className={`mt-0.5 text-sm font-semibold tabular-nums ${toneClass}`}>{value}</p>
    </div>
  );
}
