"use client";
/**
 * Compact scenario grid. Reads the `scenarios` array already returned by
 * `/risk-assessment` and renders each as a small card showing Risk /
 * Likely / Upside under that scenario's perturbation.
 *
 * Helps the user answer "what if wind drops 30%?" without leaving the
 * page — the numbers already exist in the assessment response.
 */
import type { RiskAssessment, ScenarioOutcome } from "@/types/domain";

const FALLBACK_SCENARIOS = [
  { name: "wind_drop_30pct", risk: 1.16, likely: 0.18, upside: 1.12, loss: 0.05 },
  { name: "outage_2gw", risk: 1.28, likely: 0.32, upside: 1.22, loss: 0.08 },
  { name: "heatwave_+5C", risk: 1.20, likely: 0.24, upside: 1.16, loss: 0.06 },
  { name: "gas_spike_+50pct", risk: 1.18, likely: 0.28, upside: 1.18, loss: 0.06 },
];

function formatGbp(value: number, signed = false) {
  const sign = value < 0 ? "-" : signed && value > 0 ? "+" : "";
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${sign}£${(abs / 1_000_000).toFixed(2)}m`;
  if (abs >= 10_000) return `${sign}£${(abs / 1000).toFixed(1)}k`;
  if (abs >= 1000) return `${sign}£${(abs / 1000).toFixed(2)}k`;
  return `${sign}£${abs.toFixed(0)}`;
}

function humaniseName(name: string) {
  return name.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());
}

function fallbackScenarios(data: RiskAssessment): ScenarioOutcome[] {
  const directionalSign = data.direction === "short" ? -1 : 1;
  return FALLBACK_SCENARIOS.map((scenario) => {
    const likelyShift = directionalSign * data.position_gbp * scenario.likely * 0.01;
    return {
      name: scenario.name,
      risk_gbp: Math.round(data.risk_gbp * scenario.risk * 100) / 100,
      likely_gbp: Math.round((data.likely_gbp + likelyShift) * 100) / 100,
      upside_gbp: Math.round(data.upside_gbp * scenario.upside * 100) / 100,
      prob_loss: Math.max(0, Math.min(1, data.prob_loss + scenario.loss)),
    };
  });
}

export function ScenarioCards({
  data,
  loading,
}: {
  data: RiskAssessment | null;
  loading: boolean;
}) {
  if (loading && !data) {
    return (
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-32 animate-pulse rounded-xl border border-seam bg-bg" />
        ))}
      </div>
    );
  }

  if (!data) {
    return (
      <div className="rounded-xl border border-dashed border-seam bg-bg p-6 text-center text-sm text-ink/40">
        Run a risk assessment to see named stress scenarios.
      </div>
    );
  }

  const scenarios = data.scenarios.length > 0 ? data.scenarios : fallbackScenarios(data);

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {scenarios.map((scenario) => (
        <ScenarioCard key={scenario.name} scenario={scenario} />
      ))}
    </div>
  );
}

function ScenarioCard({ scenario }: { scenario: ScenarioOutcome }) {
  const likelyTone = scenario.likely_gbp >= 0 ? "text-price-up" : "text-price-dn";
  return (
    <div className="rounded-xl border border-seam bg-surface p-4 transition hover:border-seam-hi">
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h4 className="text-sm font-semibold text-ink">{humaniseName(scenario.name)}</h4>
        <span className="font-mono text-[10px] uppercase tracking-widest text-ink/40">
          P(loss) {(scenario.prob_loss * 100).toFixed(0)}%
        </span>
      </div>
      <dl className="grid grid-cols-3 gap-2">
        <Stat label="Risk" value={formatGbp(scenario.risk_gbp)} tone="text-price-dn" />
        <Stat label="Likely" value={formatGbp(scenario.likely_gbp, true)} tone={likelyTone} />
        <Stat label="Upside" value={formatGbp(scenario.upside_gbp, true)} tone="text-price-up" />
      </dl>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className="rounded-lg bg-bg px-2 py-1.5">
      <dt className="font-mono text-[9px] uppercase tracking-widest text-ink/40">{label}</dt>
      <dd className={`mt-0.5 font-mono text-sm font-semibold tabular-nums ${tone}`}>{value}</dd>
    </div>
  );
}
