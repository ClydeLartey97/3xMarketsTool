"use client";
/**
 * The compact follow-down strip that anchors below the top nav once the
 * hero scrolls out of view. Shows the same three numbers as the hero
 * bubbles, but inline and minimal so the user never loses sight of their
 * read while exploring the evidence beneath.
 *
 * The "Edit" affordance scrolls back to the hero and re-focuses the input.
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
  // The sheet is only "open" if the bar is also visible — derived, no effect needed.
  const mobileExpanded = visible && mobileExpandRequested;

  const risk = data ? formatGbp(data.risk_gbp) : loading ? "…" : "—";
  const likely = data ? formatGbp(data.likely_gbp, true) : loading ? "…" : "—";
  const upside = data ? formatGbp(data.upside_gbp, true) : loading ? "…" : "—";

  return (
    <>
      {/* Desktop / tablet inline bar */}
      <div
        aria-hidden={!visible}
        className={`fixed inset-x-0 z-40 hidden border-b border-seam bg-surface/95 backdrop-blur-md transition-transform duration-200 ease-out sm:block ${
          visible ? "translate-y-0" : "-translate-y-full"
        }`}
        style={{ top: APP_NAV_HEIGHT_PX }}
      >
        <div className="mx-auto flex max-w-[1440px] items-center gap-4 px-6 py-2">
          <div className="flex min-w-0 items-center gap-2">
            <span className="rounded-md bg-ink/5 px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest text-ink/55">
              {marketCode}
            </span>
            <span className="truncate text-xs font-medium text-ink/70">{marketName}</span>
          </div>

          <div className="ml-auto flex items-center gap-4">
            <InlineFigure label="Risk" value={risk} tone="dn" loading={loading} />
            <span className="text-ink/20">·</span>
            <InlineFigure
              label="Likely"
              value={likely}
              tone={data && data.likely_gbp < 0 ? "dn" : "up"}
              loading={loading}
            />
            <span className="text-ink/20">·</span>
            <InlineFigure label="Upside" value={upside} tone="up" loading={loading} />
          </div>

          <span
            title="Modelled distributions, not realised outcomes. Educational tool — not financial advice."
            className="ml-3 hidden rounded-md border border-seam/60 bg-bg px-2 py-1 font-mono text-[9px] uppercase tracking-wider text-ink/40 md:inline-block"
          >
            Not advice
          </span>
          <button
            type="button"
            onClick={onEdit}
            className="ml-2 rounded-md border border-seam bg-bg px-3 py-1.5 font-mono text-[10px] uppercase tracking-wider text-ink/60 transition hover:border-seam-hi hover:text-ink"
          >
            Edit
          </button>
        </div>
      </div>

      {/* Mobile collapsed bar — shows only Risk, taps to open sheet */}
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
          <span className="rounded-md bg-ink/5 px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest text-ink/55">
            {marketCode}
          </span>
          <InlineFigure label="Risk" value={risk} tone="dn" loading={loading} />
          <span className="ml-auto font-mono text-xs text-ink/40">{mobileExpanded ? "−" : "···"}</span>
        </button>
        {mobileExpanded ? (
          <div className="border-t border-seam bg-surface px-4 pb-3 pt-2">
            <div className="grid grid-cols-3 gap-2">
              <CompactCell label="Risk" value={risk} tone="dn" />
              <CompactCell
                label="Likely"
                value={likely}
                tone={data && data.likely_gbp < 0 ? "dn" : "up"}
              />
              <CompactCell label="Upside" value={upside} tone="up" />
            </div>
            <button
              type="button"
              onClick={onEdit}
              className="mt-2 w-full rounded-md border border-seam bg-bg px-3 py-1.5 font-mono text-[10px] uppercase tracking-wider text-ink/65"
            >
              Edit inputs
            </button>
          </div>
        ) : null}
      </div>
    </>
  );
}

function InlineFigure({
  label,
  value,
  tone,
  loading,
}: {
  label: string;
  value: string;
  tone: "up" | "dn";
  loading: boolean;
}) {
  const toneClass = tone === "up" ? "text-price-up" : "text-price-dn";
  return (
    <span className={`inline-flex items-baseline gap-1.5 ${loading ? "opacity-60" : ""}`}>
      <span className="font-mono text-[10px] uppercase tracking-widest text-ink/40">{label}</span>
      <span className={`font-mono text-sm font-semibold tabular-nums ${toneClass}`}>{value}</span>
    </span>
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
      <p className="font-mono text-[9px] uppercase tracking-widest text-ink/45">{label}</p>
      <p className={`mt-0.5 font-mono text-sm font-semibold tabular-nums ${toneClass}`}>{value}</p>
    </div>
  );
}
