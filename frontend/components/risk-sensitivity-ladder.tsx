"use client";

import { useEffect, useMemo, useState } from "react";

import {
  runRiskSensitivity,
  type RiskSensitivityResponse,
  type SensitivityCoefficient,
} from "@/lib/api";
import type { RiskAssessment } from "@/types/domain";

const COEFFICIENTS: SensitivityCoefficient[] = [
  "tail_multiplier",
  "asymmetry",
  "catalyst_severity",
  "sigma_hourly",
  "drift_hourly",
  "fx_to_gbp",
  "hedge_ratio",
];

const LABELS: Record<SensitivityCoefficient, string> = {
  tail_multiplier: "Tail multiplier",
  asymmetry: "Asymmetry",
  catalyst_severity: "Catalyst severity",
  sigma_hourly: "Hourly sigma",
  drift_hourly: "Hourly drift",
  fx_to_gbp: "FX to GBP",
  hedge_ratio: "Hedge ratio",
};

function formatGbp(value: number) {
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${sign}£${(abs / 1_000_000).toFixed(2)}m`;
  if (abs >= 10_000) return `${sign}£${(abs / 1000).toFixed(1)}k`;
  return `${sign}£${abs.toFixed(0)}`;
}

function formatPerturbation(value: number) {
  if (value === 0) return "0%";
  return `${value > 0 ? "+" : ""}${value.toFixed(0)}%`;
}

function heatStyle(risk: number, baseline: number) {
  if (!Number.isFinite(risk) || !Number.isFinite(baseline) || baseline <= 0) {
    return { backgroundColor: "rgba(39, 39, 42, 0.55)" };
  }
  const delta = (risk - baseline) / baseline;
  const alpha = Math.min(0.42, 0.08 + Math.abs(delta) * 0.7);
  if (Math.abs(delta) < 0.005) {
    return { backgroundColor: "rgba(63, 63, 70, 0.55)" };
  }
  if (delta > 0) {
    return { backgroundColor: `rgba(239, 68, 68, ${alpha})` };
  }
  return { backgroundColor: `rgba(34, 197, 94, ${alpha})` };
}

export type RiskSensitivityLadderProps = {
  data: RiskAssessment | null;
  loading?: boolean;
};

export function RiskSensitivityLadder({ data, loading = false }: RiskSensitivityLadderProps) {
  const [sensitivity, setSensitivity] = useState<RiskSensitivityResponse | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!data || loading) {
      setSensitivity(null);
      setPending(false);
      setError(null);
      return;
    }

    let cancelled = false;
    setPending(true);
    setError(null);
    runRiskSensitivity({
      market_code: data.market_code,
      position_gbp: data.position_gbp,
      position_unit: "GBP",
      hedge_ratio: 1,
      horizon_hours: data.horizon_hours,
      direction: data.direction === "short" ? "short" : "long",
      target_timestamp: data.target_timestamp,
      n_paths: 5000,
      scenarios: [],
      coefficients_to_perturb: COEFFICIENTS,
    })
      .then((result) => {
        if (!cancelled) setSensitivity(result);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setSensitivity(null);
          setError(err instanceof Error ? err.message : "sensitivity failed");
        }
      })
      .finally(() => {
        if (!cancelled) setPending(false);
      });

    return () => {
      cancelled = true;
    };
  }, [data, loading]);

  const baselineByCoefficient = useMemo(() => {
    const out = new Map<SensitivityCoefficient, number>();
    for (const row of sensitivity?.rows ?? []) {
      const baseline = row.cells.find((cell) => cell.perturbation_pct === 0);
      out.set(row.coefficient, baseline?.risk_gbp ?? 0);
    }
    return out;
  }, [sensitivity]);

  if (loading || pending) {
    return (
      <section className="rounded-xl border border-white/10 bg-zinc-950/60 p-4 text-zinc-400">
        Computing sensitivity ladder…
      </section>
    );
  }

  if (!data) {
    return (
      <section className="rounded-xl border border-white/10 bg-zinc-950/60 p-4 text-zinc-500">
        Run a risk assessment to see coefficient sensitivity.
      </section>
    );
  }

  if (error) {
    return (
      <section className="rounded-xl border border-price-dn/25 bg-price-dn/10 p-4 text-sm text-price-dn">
        Sensitivity unavailable: {error}
      </section>
    );
  }

  if (!sensitivity) return null;

  return (
    <section className="rounded-xl border border-white/10 bg-zinc-950/60 p-4" aria-label="Risk sensitivity ladder">
      <header className="sticky-panel-header -mx-4 -mt-4 mb-3 flex flex-wrap items-baseline justify-between gap-2 rounded-t-xl bg-zinc-950 px-4 pb-3 pt-4">
        <div>
          <h3 className="text-sm font-semibold text-zinc-100">Sensitivity ladder</h3>
          <p className="text-[11px] text-zinc-500">Perturb one coefficient at a time; colour tracks risk movement.</p>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-wider text-zinc-500">
          {formatGbp(sensitivity.position_gbp)} · {sensitivity.horizon_hours}h · {sensitivity.direction}
        </span>
      </header>

      <div className="overflow-x-auto">
        <table className="min-w-[760px] w-full table-fixed border-separate border-spacing-1 text-[11px]">
          <thead>
            <tr>
              <th className="w-40 px-2 py-1 text-left font-semibold uppercase tracking-wider text-zinc-500">
                Coefficient
              </th>
              {sensitivity.perturbations_pct.map((p) => (
                <th key={p} className="px-2 py-1 text-center font-mono font-semibold text-zinc-400">
                  {formatPerturbation(p)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sensitivity.rows.map((row) => {
              const baseline = baselineByCoefficient.get(row.coefficient) ?? 0;
              return (
                <tr key={row.coefficient}>
                  <th className="rounded-md bg-black/30 px-2 py-2 text-left align-middle">
                    <span className="block text-zinc-100">{LABELS[row.coefficient]}</span>
                    <span className="mt-0.5 block font-mono text-[10px] text-zinc-500">
                      base {row.base_value.toPrecision(4)}
                    </span>
                  </th>
                  {row.cells.map((cell) => (
                    <td
                      key={`${row.coefficient}-${cell.perturbation_pct}`}
                      style={heatStyle(cell.risk_gbp, baseline)}
                      className="rounded-md px-2 py-2 text-center align-middle text-zinc-100"
                    >
                      <span className="block font-mono text-[12px] font-semibold tabular-nums">
                        {formatGbp(cell.risk_gbp)}
                      </span>
                      <span className="mt-1 block font-mono text-[10px] leading-tight text-zinc-300/80">
                        L {formatGbp(cell.likely_gbp)}
                      </span>
                      <span className="block font-mono text-[10px] leading-tight text-zinc-300/80">
                        U {formatGbp(cell.upside_gbp)}
                      </span>
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
