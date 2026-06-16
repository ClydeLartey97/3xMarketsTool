"use client";

import { useMemo } from "react";
import type { ReactNode } from "react";

import type { CoefficientItem, RiskAssessment } from "@/types/domain";

const GROUP_ORDER: { key: string; label: string; tone: string }[] = [
  { key: "result",       label: "Result",          tone: "text-amber-300" },
  { key: "forecast",     label: "Forecast",        tone: "text-sky-300" },
  { key: "realised_vol", label: "Realised vol",    tone: "text-emerald-300" },
  { key: "llm",          label: "LLM context",    tone: "text-violet-300" },
  { key: "fx",           label: "FX",              tone: "text-rose-300" },
  { key: "position",     label: "Position",        tone: "text-cyan-300" },
];

function formatValue(value: number, unit: string): string {
  if (!Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  if (unit === "GBP") {
    if (abs >= 1_000_000) return `£${(value / 1_000_000).toFixed(2)}m`;
    if (abs >= 10_000) return `£${(value / 1000).toFixed(1)}k`;
    return `£${value.toFixed(0)}`;
  }
  if (unit === "%") return `${value.toFixed(3)}%`;
  if (unit === "ratio" || unit === "[0,1]" || unit === "[-1,1]" || unit === "x") {
    return value.toFixed(4);
  }
  if (unit === "log-return" || unit === "log-return/hr") {
    return value.toExponential(3);
  }
  if (unit === "count") return value.toFixed(0);
  if (unit === "hours") return `${value.toFixed(0)}h`;
  if (abs >= 1000) return value.toFixed(2);
  if (abs >= 1) return value.toFixed(4);
  return value.toFixed(6);
}

export type RiskDecompositionPanelProps = {
  data: RiskAssessment | null;
  loading?: boolean;
};

export function RiskDecompositionPanel({ data, loading = false }: RiskDecompositionPanelProps) {
  const grouped = useMemo(() => {
    if (!data) return new Map<string, CoefficientItem[]>();
    const out = new Map<string, CoefficientItem[]>();
    for (const item of data.coefficients?.items ?? []) {
      const list = out.get(item.group) ?? [];
      list.push(item);
      out.set(item.group, list);
    }
    return out;
  }, [data]);

  if (loading) {
    return (
      <div className="rounded-xl border border-white/10 bg-zinc-950/60 p-4 text-zinc-400">
        Computing decomposition…
      </div>
    );
  }
  if (!data) {
    return (
      <div className="rounded-xl border border-white/10 bg-zinc-950/60 p-4 text-zinc-500">
        Run a risk assessment to see how every coefficient contributes.
      </div>
    );
  }

  return (
    <section
      className="rounded-xl border border-white/10 bg-zinc-950/60 p-4"
      aria-label="Risk coefficient decomposition"
    >
      <header className="sticky-panel-header -mx-4 -mt-4 mb-3 flex items-baseline justify-between gap-2 rounded-t-xl bg-zinc-950 px-4 pb-3 pt-4">
        <div>
          <h3 className="text-sm font-semibold text-zinc-100">Risk decomposition</h3>
          <p className="text-[11px] text-zinc-500">
            Every parameter that drives risk · likely · upside, exposed for audit.
          </p>
        </div>
        <span className="eyebrow text-[10px] text-zinc-500">
          n_paths {data.n_paths.toLocaleString()} · metric {data.risk_metric}
        </span>
      </header>

      <pre className="mb-4 whitespace-pre-wrap rounded-md bg-black/40 p-2 font-mono text-[10.5px] leading-snug text-zinc-300">
        {data.coefficients?.equation_summary ?? ""}
      </pre>

      <div className="grid gap-3 lg:grid-cols-2">
        {GROUP_ORDER.map(({ key, label, tone }) => {
          const items = grouped.get(key) ?? [];
          if (items.length === 0) return null;
          return (
            <div key={key} className="rounded-lg border border-white/5 bg-black/30 p-2">
              <h4 className={`mb-1.5 eyebrow text-[10.5px] font-semibold ${tone}`}>
                {label}
              </h4>
              <table className="w-full table-fixed border-separate border-spacing-y-0.5 text-[11px]">
                <tbody>
                  {items.map((item) => (
                    <tr key={item.key} className="text-zinc-300">
                      <td className="w-[55%] truncate pr-2 align-top" title={item.description}>
                        <span className="text-zinc-200">{item.label}</span>
                        <div className="text-[9.5px] text-zinc-500">{item.description}</div>
                      </td>
                      <td className="w-[28%] truncate text-right font-mono text-zinc-100">
                        {formatValue(item.value, item.unit)}
                      </td>
                      <td className="w-[17%] truncate pl-1 text-right eyebrow text-[9.5px] text-zinc-500">
                        {item.unit}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        })}
      </div>

      <CalculationWalkthrough data={data} />
    </section>
  );
}

function CalculationWalkthrough({ data }: { data: RiskAssessment }) {
  const coeffByKey = useMemo(() => {
    const m: Record<string, number> = {};
    for (const item of data.coefficients?.items ?? []) {
      m[item.key] = item.value;
    }
    return m;
  }, [data]);

  const c = (key: string) => coeffByKey[key] ?? null;

  const driftBase = c("drift_hourly_base");
  const driftAsym = c("asym_drift_per_hour");
  const driftTotal = c("drift_hourly_total");
  const wRealised = c("realised_vol_weight");
  const posNative = data.position_gbp / Math.max(data.fx_to_gbp, 1e-6);
  const dirSign = data.direction === "short" ? -1 : 1;

  return (
    <div className="mt-4 rounded-lg border border-white/5 bg-black/30 p-3">
      <h4 className="mb-3 eyebrow text-[10.5px] font-semibold text-zinc-400">
        Step-by-step: how the three numbers are produced
      </h4>
      <ol className="space-y-3">
        <WalkStep n={1} label="Price anchor">
          <WalkRow k="Spot (P₀)" v={`${data.spot_price.toFixed(2)} ${data.price_currency}/MWh`} />
          <WalkRow k={`Model forecast (P̂_h) at ${data.horizon_hours}h`} v={`${data.forecast_price.toFixed(2)} ${data.price_currency}/MWh`} />
        </WalkStep>

        <WalkStep n={2} label="Volatility (σ) blended to your horizon">
          <WalkRow k="Hourly σ (log-return)" v={`${data.sigma_hourly_pct.toFixed(3)}%`} />
          <WalkRow k={`Scaled to ${data.horizon_hours}h  →  σ × √h`} v={`${data.sigma_return_pct.toFixed(2)}%`} />
          <WalkRow k="Blended σ in price units" v={`${data.sigma_price.toFixed(2)} ${data.price_currency}/MWh`} dim />
          {wRealised !== null && (
            <WalkRow k="Blend weight (realised vs model)" v={`${(wRealised * 100).toFixed(0)}% realised`} dim />
          )}
        </WalkStep>

        <WalkStep n={3} label="Drift (μ) per hour">
          {driftBase !== null && <WalkRow k="Base drift  =  ln(P̂_h / P₀) ÷ h" v={driftBase.toExponential(3)} />}
          {driftAsym !== null && <WalkRow k="LLM asymmetry nudge" v={driftAsym.toExponential(3)} dim />}
          {driftTotal !== null && <WalkRow k="Total μ fed to simulator" v={driftTotal.toExponential(3)} />}
        </WalkStep>

        <WalkStep n={4} label="LLM tail inflation">
          <WalkRow k="Tail multiplier" v={`${data.tail_multiplier.toFixed(4)}×`} />
          <WalkRow
            k="CVaR formula"
            v={data.tail_multiplier <= 1.2 ? "Gaussian (normal market)" : "t(5) blend (stressed tails)"}
            dim
          />
        </WalkStep>

        <WalkStep n={5} label={`Monte Carlo — ${data.n_paths.toLocaleString()} simulated price paths`}>
          <WalkRow k="Process" v="dln(P) = μ dt + σ·tail × dW" mono />
          <WalkRow k="Position (native)" v={`${posNative.toFixed(0)} ${data.price_currency}`} dim />
          <WalkRow k="P&L per path" v={`${dirSign > 0 ? "+" : "−"}position × (P_T − P₀)/P₀ × ${data.fx_to_gbp.toFixed(4)} FX`} mono />
        </WalkStep>

        <WalkStep n={6} label="Three numbers read off the empirical P&L distribution">
          <WalkRow k="Risk  =  avg of worst 5% of paths  (CVaR 95)" v={`£${Math.abs(data.risk_gbp).toFixed(0)}`} tone="dn" />
          <WalkRow k="Likely  =  mean across all paths" v={`${data.likely_gbp >= 0 ? "+" : ""}£${data.likely_gbp.toFixed(0)}`} tone={data.likely_gbp >= 0 ? "up" : "dn"} />
          <WalkRow k="Upside  =  avg of best 5% of paths" v={`+£${data.upside_gbp.toFixed(0)}`} tone="up" />
        </WalkStep>
      </ol>
    </div>
  );
}

function WalkStep({ n, label, children }: { n: number; label: string; children: ReactNode }) {
  return (
    <li className="flex gap-3">
      <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-zinc-800 font-mono text-[9px] text-zinc-400">
        {n}
      </span>
      <div className="min-w-0 flex-1">
        <div className="mb-1 text-[11px] font-semibold text-zinc-200">{label}</div>
        <div className="space-y-0.5">{children}</div>
      </div>
    </li>
  );
}

function WalkRow({
  k,
  v,
  dim,
  mono,
  tone,
}: {
  k: string;
  v: string;
  dim?: boolean;
  mono?: boolean;
  tone?: "up" | "dn";
}) {
  const valueClass =
    tone === "up"
      ? "text-emerald-400"
      : tone === "dn"
        ? "text-red-400"
        : dim
          ? "text-zinc-500"
          : "text-zinc-100";
  return (
    <div className="flex items-baseline justify-between gap-2 text-[11px]">
      <span className={dim ? "text-zinc-500" : "text-zinc-400"}>{k}</span>
      <span className={`shrink-0 ${mono ? "font-mono" : ""} ${valueClass}`}>{v}</span>
    </div>
  );
}
