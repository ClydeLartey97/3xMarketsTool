"use client";
/**
 * Single-row decision gate readout. Sits between the bubbles and the
 * chart, telling the user: should they actually put this trade on?
 *
 * Pulls `decision_gate` from the live assessment and renders the action
 * (clear / watch / block) with the supporting checks inline.
 */
import type { RiskAssessment } from "@/types/domain";

export function DecisionGateStrip({
  data,
  loading,
}: {
  data: RiskAssessment | null;
  loading: boolean;
}) {
  const gate = data?.decision_gate;

  if (loading && !data) {
    return (
      <div className="h-20 animate-pulse rounded-xl border border-seam bg-bg" />
    );
  }

  if (!gate) {
    return null;
  }

  const toneClass =
    gate.action === "clear"
      ? "border-price-up/35 bg-price-up/10"
      : gate.action === "block"
        ? "border-price-dn/35 bg-price-dn/10"
        : "border-price-warn/35 bg-price-warn/10";

  const labelTone =
    gate.action === "clear"
      ? "text-price-up"
      : gate.action === "block"
        ? "text-price-dn"
        : "text-price-warn";

  return (
    <section
      aria-label="Decision gate"
      className={`flex flex-col gap-3 rounded-xl border p-4 md:flex-row md:items-center md:gap-6 ${toneClass}`}
    >
      <div className="flex items-center gap-4">
        <div className="text-center">
          <p className="font-mono text-[9px] uppercase tracking-widest text-ink/45">Action</p>
          <p className={`mt-1 font-mono text-base font-semibold uppercase tracking-wider ${labelTone}`}>
            {gate.action}
          </p>
        </div>
        <div>
          <p className="text-sm font-semibold text-ink">{gate.label}</p>
          <p className="mt-0.5 text-[11px] text-ink/55">Score · {gate.score.toFixed(1)}</p>
        </div>
      </div>

      <div className="ml-0 grid flex-1 grid-cols-2 gap-2 sm:grid-cols-4 md:ml-auto md:max-w-xl">
        {gate.checks.slice(0, 4).map((check) => (
          <div
            key={check.label}
            className="rounded-lg border border-seam/60 bg-surface/60 px-2 py-1.5"
          >
            <p className="truncate font-mono text-[9px] uppercase tracking-widest text-ink/40">
              {check.label}
            </p>
            <p
              className={`mt-0.5 truncate font-mono text-[11px] font-medium ${
                check.status === "pass"
                  ? "text-price-up"
                  : check.status === "fail"
                    ? "text-price-dn"
                    : "text-price-warn"
              }`}
            >
              {check.value}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
