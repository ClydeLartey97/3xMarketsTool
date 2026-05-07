"use client";

import { useMemo } from "react";

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
      <header className="mb-3 flex items-baseline justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-zinc-100">Risk decomposition</h3>
          <p className="text-[11px] text-zinc-500">
            Every parameter that drives risk · likely · upside, exposed for audit.
          </p>
        </div>
        <span className="text-[10px] uppercase tracking-wider text-zinc-500">
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
              <h4 className={`mb-1.5 text-[10.5px] font-semibold uppercase tracking-wider ${tone}`}>
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
                      <td className="w-[17%] truncate pl-1 text-right text-[9.5px] uppercase tracking-wide text-zinc-500">
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
    </section>
  );
}
