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
      {/* Desktop / tablet: right-rail compact read panel */}
      <aside
        aria-hidden={!visible}
        aria-label="Risk read"
        className={`fixed right-4 z-40 hidden w-[168px] flex-col transition-all duration-300 ease-out sm:flex ${
          visible ? "translate-x-0 opacity-100" : "translate-x-[140%] opacity-0 pointer-events-none"
        }`}
        style={{ top: APP_NAV_HEIGHT_PX + 24 }}
      >
        <div
          className={`overflow-hidden rounded-xl border border-seam bg-surface/95 shadow backdrop-blur ${
            loading ? "animate-pulse" : ""
          }`}
        >
          <div className="border-b border-seam px-3 py-2">
            <p className="text-[11px] font-semibold text-ink/70">{marketCode}</p>
            <p className="truncate text-[10px] text-ink/40">{marketName}</p>
          </div>
          <dl className="divide-y divide-seam/60">
            <RailRow label="Risk" value={risk} tone="text-price-dn" />
            <RailRow
              label="Likely"
              value={likely}
              tone={likelyTone === "up" ? "text-price-up" : "text-price-dn"}
            />
            <RailRow label="Upside" value={upside} tone="text-price-up" />
          </dl>
          <button
            type="button"
            onClick={onEdit}
            title="Jump back to inputs"
            className="w-full border-t border-seam px-3 py-2 text-left text-[11px] font-medium text-ink/55 transition hover:bg-ink/5 hover:text-ink"
          >
            Edit inputs
          </button>
        </div>
        <p
          title="Modelled distributions, not realised outcomes. Educational tool — not financial advice."
          className="mt-2 text-center text-[10px] text-ink/30"
        >
          Modelled · not advice
        </p>
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

// Colour lives only in the number — the panel itself stays neutral,
// matching the hero stat panel.
function RailRow({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className="flex items-baseline justify-between px-3 py-2">
      <dt className="text-[11px] font-medium text-ink/45">{label}</dt>
      <dd className={`font-mono text-[13px] font-semibold tabular-nums ${tone}`}>{value}</dd>
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
