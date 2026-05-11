/**
 * Centralised typography tokens for the workbench panels.
 *
 * Seven explicit categories. Each one has exactly one casing/style rule.
 * Components import the className strings from here so we never end up with
 * four different casings on the same row again.
 */

/** Tiny tracked-wider UPPERCASE label sitting at the top-left of every panel. */
export const labelClass =
  "text-[10px] uppercase tracking-widest text-ink/45";

/** Panel headline title. Sentence case, semibold. */
export const titleClass = "text-[14px] font-semibold tracking-tight text-ink";

/** Status value (`honest`, `binding`, `open`, `degraded`). Sentence case. */
export const statusClass =
  "text-[14px] font-semibold tracking-tight";

/** Tag / chip — the only thing in the body that's ALL CAPS. */
export const tagClass =
  "rounded-md bg-ink/5 px-1.5 py-0.5 text-[10px] font-mono uppercase tracking-wider text-ink/65";

/** Source-line metadata (timestamp, region). Sentence case. */
export const metaClass = "text-[11px] text-ink/55";

/** Counter chip ("8 articles", "3 reads"). Lowercase noun. */
export const counterClass =
  "rounded-md bg-ink/5 px-1.5 py-0.5 text-[10px] font-mono lowercase text-ink/55";

/** Big readout (a metric like 4.7%). Mono, tabular. */
export const bigMetricClass =
  "font-mono text-2xl font-semibold tabular-nums tracking-tight text-ink";

/** Helper to format an event-type id ("regulatory_policy_announcement") for display. */
export function prettyEventType(eventType: string): string {
  return eventType
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/^(.)/, (s) => s.toUpperCase());
}

/** Helper to format a region/source label for display in Sentence case. */
export function prettyRegion(region: string): string {
  if (!region) return "";
  // Special-case acronyms that should stay capitalised.
  const acronyms = new Set(["GB", "UK", "US", "EU", "ERCOT", "PJM", "NYISO", "ISO-NE", "EPEX", "DE", "FR", "SE3"]);
  return region
    .split(/\s+/)
    .map((word) => {
      const upper = word.toUpperCase();
      if (acronyms.has(upper)) return upper;
      return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
    })
    .join(" ");
}
