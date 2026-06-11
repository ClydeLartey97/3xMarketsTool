"use client";
/**
 * Compact scenario grid. Reads the `scenarios` array already returned by
 * `/risk-assessment` and renders each as a small card showing Risk /
 * Likely / Upside under that scenario's perturbation.
 *
 * Helps the user answer "what if wind drops 30%?" without leaving the
 * page — the numbers already exist in the assessment response.
 */
import { useEffect, useMemo, useState } from "react";

import { runRiskAssessment } from "@/lib/api";
import { useNearViewport } from "@/lib/use-near-viewport";
import type { RiskAssessment, ScenarioOutcome } from "@/types/domain";

const DEFAULT_SCENARIOS = [
  { name: "wind_drop_30pct" },
  { name: "outage_2gw" },
  { name: "heatwave_+5C" },
  { name: "gas_spike_+50pct" },
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

export function ScenarioCards({
  data,
  loading,
}: {
  data: RiskAssessment | null;
  loading: boolean;
}) {
  const [scenarioData, setScenarioData] = useState<ScenarioOutcome[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastFetchedKey, setLastFetchedKey] = useState<string | null>(null);
  const { ref: viewportRef, visible } = useNearViewport<HTMLDivElement>({ rootMargin: "250px" });
  const baseScenarios = useMemo(() => data?.scenarios ?? [], [data?.scenarios]);
  const requestKey = data
    ? [
        data.market_code,
        data.position_gbp,
        data.direction,
        data.horizon_hours,
        data.target_timestamp ?? "",
      ].join("|")
    : null;
  const scenarios = baseScenarios.length > 0 ? baseScenarios : scenarioData;

  useEffect(() => {
    if (!data || loading) {
      setScenarioData([]);
      setPending(false);
      setError(null);
      setLastFetchedKey(null);
      return;
    }
    if (!visible || baseScenarios.length > 0 || lastFetchedKey === requestKey) {
      return;
    }

    let cancelled = false;
    setPending(true);
    setError(null);
    runRiskAssessment({
      market_code: data.market_code,
      position_gbp: data.position_gbp,
      horizon_hours: data.horizon_hours,
      direction: data.direction === "short" ? "short" : "long",
      target_timestamp: data.target_timestamp,
      n_paths: 500,
      preview: true,
      scenarios: DEFAULT_SCENARIOS,
    })
      .then((result) => {
        if (cancelled) return;
        setScenarioData(result.scenarios ?? []);
        setLastFetchedKey(requestKey);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setScenarioData([]);
        setError(err instanceof Error ? err.message : "scenario analysis failed");
      })
      .finally(() => {
        if (!cancelled) setPending(false);
      });

    return () => {
      cancelled = true;
    };
  }, [baseScenarios.length, data, lastFetchedKey, loading, requestKey, visible]);

  if ((loading || pending) && scenarios.length === 0) {
    return (
      <div ref={viewportRef} className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-32 animate-pulse rounded-xl border border-seam bg-bg" />
        ))}
      </div>
    );
  }

  if (!data) {
    return (
      <div ref={viewportRef} className="rounded-xl border border-dashed border-seam bg-bg p-6 text-center text-sm text-ink/40">
        Run a risk assessment to see named stress scenarios.
      </div>
    );
  }

  if (error) {
    return (
      <div ref={viewportRef} className="rounded-xl border border-dashed border-seam bg-bg p-6 text-center text-sm text-ink/40">
        Scenario analysis is temporarily unavailable.
      </div>
    );
  }

  if (scenarios.length === 0) {
    return (
      <div ref={viewportRef} className="rounded-xl border border-dashed border-seam bg-bg p-6 text-center text-sm text-ink/40">
        Scenario analysis will load when this section comes into view.
      </div>
    );
  }

  return (
    <div ref={viewportRef} className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
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
