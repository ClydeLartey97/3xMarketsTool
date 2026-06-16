"use client";

import { useMemo } from "react";

import {
  type RiskSensitivityCell,
  type RiskSensitivityResponse,
  type SensitivityCoefficient,
} from "@/lib/api";
import type { RiskAssessment } from "@/types/domain";

const COEFFICIENTS: SensitivityCoefficient[] = [
  "tail_multiplier",
  "asymmetry",
  "sigma_hourly",
  "fx_to_gbp",
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

const PERTURBATIONS = [-25, 0, 25];

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

// Heat tint per cell. Neutral cells use a theme-aware ink wash (works in
// both light and dark); movement is a soft red (risk up) / green (risk down)
// tint that reads on either background.
function heatStyle(risk: number, baseline: number) {
  if (!Number.isFinite(risk) || !Number.isFinite(baseline) || baseline <= 0) {
    return { backgroundColor: "rgb(var(--ink) / 0.05)" };
  }
  const delta = (risk - baseline) / baseline;
  const alpha = Math.min(0.4, 0.08 + Math.abs(delta) * 0.7);
  if (Math.abs(delta) < 0.005) {
    return { backgroundColor: "rgb(var(--ink) / 0.06)" };
  }
  if (delta > 0) {
    return { backgroundColor: `rgba(220, 38, 38, ${alpha})` };
  }
  return { backgroundColor: `rgba(5, 150, 105, ${alpha})` };
}

function coefficientBase(data: RiskAssessment, coefficient: SensitivityCoefficient) {
  switch (coefficient) {
    case "tail_multiplier":
      return data.tail_multiplier;
    case "asymmetry":
      return data.asymmetry;
    case "sigma_hourly":
      return data.sigma_hourly_pct / 100;
    case "fx_to_gbp":
      return data.fx_to_gbp;
    case "catalyst_severity":
      return data.catalyst_severity;
    case "drift_hourly":
    case "hedge_ratio":
      return 0;
  }
}

function cellForPerturbation(
  data: RiskAssessment,
  coefficient: SensitivityCoefficient,
  perturbationPct: number,
): RiskSensitivityCell {
  if (perturbationPct === 0) {
    return {
      perturbation_pct: 0,
      risk_gbp: data.risk_gbp,
      likely_gbp: data.likely_gbp,
      upside_gbp: data.upside_gbp,
    };
  }

  const p = perturbationPct / 100;
  const directionSign = data.direction === "short" ? -1 : 1;
  let riskScale = 1;
  let likelyScale = 1;
  let upsideScale = 1;
  let likelyShift = 0;

  switch (coefficient) {
    case "tail_multiplier":
      riskScale = 1 + p * 0.9;
      likelyScale = 1 + p * 0.06;
      upsideScale = 1 + p * 0.55;
      break;
    case "sigma_hourly":
      riskScale = 1 + p * 0.8;
      likelyScale = 1 + p * 0.05;
      upsideScale = 1 + p * 0.45;
      break;
    case "fx_to_gbp":
      riskScale = 1 + p;
      likelyScale = 1 + p;
      upsideScale = 1 + p;
      break;
    case "asymmetry":
      riskScale = 1 + Math.abs(p) * 0.12;
      likelyShift = data.position_gbp * p * 0.012 * directionSign;
      upsideScale = 1 + p * 0.3 * directionSign;
      break;
    case "catalyst_severity":
      riskScale = 1 + p * 0.35;
      likelyScale = 1 + p * 0.18;
      upsideScale = 1 + p * 0.25;
      break;
    case "drift_hourly":
      likelyShift = data.position_gbp * p * 0.01 * directionSign;
      upsideScale = 1 + p * 0.2 * directionSign;
      riskScale = 1 - p * 0.1 * directionSign;
      break;
    case "hedge_ratio":
      riskScale = 1 + p;
      likelyScale = 1 + p;
      upsideScale = 1 + p;
      break;
  }

  return {
    perturbation_pct: perturbationPct,
    risk_gbp: Math.max(0, data.risk_gbp * riskScale),
    likely_gbp: data.likely_gbp * likelyScale + likelyShift,
    upside_gbp: data.upside_gbp * upsideScale,
  };
}

function buildInstantSensitivity(data: RiskAssessment): RiskSensitivityResponse {
  return {
    market_code: data.market_code,
    position_gbp: data.position_gbp,
    direction: data.direction,
    horizon_hours: data.horizon_hours,
    perturbations_pct: PERTURBATIONS,
    rows: COEFFICIENTS.map((coefficient) => ({
      coefficient,
      base_value: coefficientBase(data, coefficient),
      cells: PERTURBATIONS.map((p) => cellForPerturbation(data, coefficient, p)),
    })),
  };
}

export type RiskSensitivityLadderProps = {
  data: RiskAssessment | null;
  loading?: boolean;
};

export function RiskSensitivityLadder({ data, loading = false }: RiskSensitivityLadderProps) {
  const sensitivity = useMemo(() => (data ? buildInstantSensitivity(data) : null), [data]);

  const baselineByCoefficient = useMemo(() => {
    const out = new Map<SensitivityCoefficient, number>();
    for (const row of sensitivity?.rows ?? []) {
      const baseline = row.cells.find((cell) => cell.perturbation_pct === 0);
      out.set(row.coefficient, baseline?.risk_gbp ?? 0);
    }
    return out;
  }, [sensitivity]);

  if (loading && !data) {
    return (
      <section className="rounded-2xl border border-seam bg-surface p-4 text-ink/45">
        Computing sensitivity ladder...
      </section>
    );
  }

  if (!data) {
    return (
      <section className="rounded-2xl border border-seam bg-surface p-4 text-ink/40">
        Run a risk assessment to see coefficient sensitivity.
      </section>
    );
  }

  if (!sensitivity) {
    return (
      <section
        className="rounded-2xl border border-seam bg-surface p-4 text-ink/40"
        aria-label="Risk sensitivity ladder"
      >
        Sensitivity ladder unavailable for this read.
      </section>
    );
  }

  return (
    <section
      className="rounded-2xl border border-seam bg-surface p-4"
      aria-label="Risk sensitivity ladder"
    >
      <header className="sticky-panel-header -mx-4 -mt-4 mb-3 flex flex-wrap items-baseline justify-between gap-2 rounded-t-2xl bg-surface px-4 pb-3 pt-4">
        <div>
          <h3 className="text-sm font-semibold text-ink">Sensitivity ladder</h3>
          <p className="text-[11px] text-ink/45">Perturb one coefficient at a time; colour tracks risk movement.</p>
        </div>
        <span className="eyebrow text-[10px] text-ink/45">
          {formatGbp(sensitivity.position_gbp)} · {sensitivity.horizon_hours}h · {sensitivity.direction}
        </span>
      </header>

      <table className="w-full table-fixed border-separate border-spacing-1 text-[11px]">
        <thead>
          <tr>
            <th className="w-36 px-2 py-1 eyebrow text-left font-semibold text-ink/45">
              Coefficient
            </th>
            {sensitivity.perturbations_pct.map((p) => (
              <th key={p} className="px-2 py-1 text-center font-mono font-semibold text-ink/55">
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
                <th className="rounded-md bg-ink/[0.04] px-2 py-2 text-left align-middle">
                  <span className="block text-ink">{LABELS[row.coefficient]}</span>
                  <span className="mt-0.5 block font-mono text-[10px] text-ink/45">
                    base {row.base_value.toPrecision(4)}
                  </span>
                </th>
                {row.cells.map((cell) => (
                  <td
                    key={`${row.coefficient}-${cell.perturbation_pct}`}
                    style={heatStyle(cell.risk_gbp, baseline)}
                    className="rounded-md px-2 py-2 text-center align-middle text-ink"
                  >
                    <span className="block font-mono text-[12px] font-semibold tabular-nums">
                      {formatGbp(cell.risk_gbp)}
                    </span>
                    <span className="mt-1 block font-mono text-[10px] leading-tight text-ink/55">
                      L {formatGbp(cell.likely_gbp)}
                    </span>
                    <span className="block font-mono text-[10px] leading-tight text-ink/55">
                      U {formatGbp(cell.upside_gbp)}
                    </span>
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
