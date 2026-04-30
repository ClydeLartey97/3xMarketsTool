"use client";

import { useEffect, useRef, useState } from "react";

import { runRiskAssessment, type RiskAssessment } from "@/lib/api";

const HORIZONS: Array<{ label: string; value: number }> = [
  { label: "6H", value: 6 },
  { label: "12H", value: 12 },
  { label: "24H", value: 24 },
  { label: "48H", value: 48 },
  { label: "72H", value: 72 },
];

const PRESETS = [1000, 5000, 10000, 25000, 100000];

function formatGbp(value: number) {
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${sign}£${(abs / 1_000_000).toFixed(2)}m`;
  if (abs >= 10_000) return `${sign}£${(abs / 1000).toFixed(1)}k`;
  return `${sign}£${abs.toFixed(0)}`;
}

export type RiskPanelProps = {
  marketCode: string;
  cursorTimestampMs: number | null;
  dataStatus?: string;
  initialPosition?: number;
  initialHorizon?: number;
};

export function RiskPanel({
  marketCode,
  cursorTimestampMs,
  dataStatus = "ready",
  initialPosition = 10000,
  initialHorizon = 24,
}: RiskPanelProps) {
  const [position, setPosition] = useState<number>(initialPosition);
  const [horizon, setHorizon] = useState<number>(initialHorizon);
  const [direction, setDirection] = useState<"long" | "short">("long");
  const [data, setData] = useState<RiskAssessment | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isDegraded = dataStatus === "degraded";

  useEffect(() => {
    if (isDegraded) {
      setData(null);
      setLoading(false);
      setError(null);
      return;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      let cancelled = false;
      setLoading(true);
      setError(null);
      runRiskAssessment({
        market_code: marketCode,
        position_gbp: position,
        horizon_hours: horizon,
        direction,
        target_timestamp: cursorTimestampMs ? new Date(cursorTimestampMs).toISOString() : null,
      })
        .then((res) => {
          if (!cancelled) setData(res);
        })
        .catch((err: unknown) => {
          if (!cancelled) setError(err instanceof Error ? err.message : "assessment failed");
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
      return () => {
        cancelled = true;
      };
    }, 220);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [marketCode, position, horizon, direction, cursorTimestampMs, isDegraded]);

  const riskColor = data && data.edge_score > 0.5 ? "text-price-up" : data && data.edge_score < -0.2 ? "text-price-dn" : "text-ink/80";
  const provider = data?.scorer_provider ?? "—";

  return (
    <div className="rounded-2xl border border-seam bg-surface p-5">
      <div className="mb-4 flex items-baseline justify-between gap-2">
        <div>
          <p className="text-[10px] uppercase tracking-widest text-ink/40">Position assessment</p>
          <h3 className="mt-1 text-base font-semibold text-ink">Risk · Likely · Upside</h3>
        </div>
        <span
          className={`rounded-md px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider ${
            provider === "gemini" ? "bg-accent/10 text-accent" : "bg-ink/5 text-ink/50"
          }`}
        >
          {isDegraded ? "degraded" : provider === "gemini" ? "AI scoring" : "heuristic"}
        </span>
      </div>

      {/* Position input */}
      <div className="mb-4 space-y-2">
        <label className="block">
          <span className="mb-1 block text-[10px] uppercase tracking-widest text-ink/40">Position size (GBP)</span>
          <div className="flex items-center gap-2">
            <span className="text-lg text-ink/60">£</span>
            <input
              type="number"
              min={100}
              step={100}
              value={position}
              onChange={(e) => setPosition(Math.max(100, Number(e.target.value) || 0))}
              className="w-full rounded-lg border border-seam bg-bg px-3 py-2 text-lg font-mono tabular-nums text-ink outline-none focus:border-seam-hi"
            />
          </div>
        </label>
        <div className="flex flex-wrap gap-1.5">
          {PRESETS.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setPosition(p)}
              className={`rounded-md px-2 py-1 text-[11px] font-mono transition ${
                position === p ? "bg-ink/10 text-ink" : "bg-bg text-ink/55 hover:bg-ink/5 hover:text-ink"
              }`}
            >
              {p >= 1000 ? `${p / 1000}k` : p}
            </button>
          ))}
        </div>
      </div>

      {/* Horizon + direction */}
      <div className="mb-5 grid grid-cols-2 gap-2">
        <div>
          <span className="mb-1 block text-[10px] uppercase tracking-widest text-ink/40">Horizon</span>
          <div className="flex rounded-lg border border-seam bg-bg p-0.5">
            {HORIZONS.map((h) => (
              <button
                key={h.value}
                type="button"
                onClick={() => setHorizon(h.value)}
                className={`flex-1 rounded px-1.5 py-1 text-[11px] font-mono transition ${
                  horizon === h.value ? "bg-ink/10 text-ink" : "text-ink/50 hover:text-ink"
                }`}
              >
                {h.label}
              </button>
            ))}
          </div>
        </div>
        <div>
          <span className="mb-1 block text-[10px] uppercase tracking-widest text-ink/40">Direction</span>
          <div className="flex rounded-lg border border-seam bg-bg p-0.5">
            {(["long", "short"] as const).map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => setDirection(d)}
                className={`flex-1 rounded px-1.5 py-1 text-[11px] font-mono uppercase tracking-wider transition ${
                  direction === d
                    ? d === "long"
                      ? "bg-price-up/15 text-price-up"
                      : "bg-price-dn/15 text-price-dn"
                    : "text-ink/50 hover:text-ink"
                }`}
              >
                {d}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* The three numbers */}
      {isDegraded ? (
        <div className="rounded-xl border border-price-dn/25 bg-price-dn/10 p-4 text-sm leading-relaxed text-ink/70">
          <p className="font-semibold text-price-dn">Insufficient real data - try refresh.</p>
          <p className="mt-1 text-xs text-ink/50">
            Risk numbers are hidden until this market has a real price source in the selected window.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-2">
          <div className="rounded-xl border border-seam bg-bg p-3">
            <p className="text-[10px] uppercase tracking-widest text-ink/40">Risk (95% CVaR)</p>
            <p className="mt-1.5 font-mono text-xl font-semibold tabular-nums text-price-dn">
              {data ? formatGbp(data.risk_gbp) : "—"}
            </p>
            <p className="mt-1 text-[10px] text-ink/40">expected loss in worst 5%</p>
          </div>
          <div className="rounded-xl border border-seam bg-bg p-3">
            <p className="text-[10px] uppercase tracking-widest text-ink/40">Likely</p>
            <p className={`mt-1.5 font-mono text-xl font-semibold tabular-nums ${data && data.likely_gbp >= 0 ? "text-price-up" : "text-price-dn"}`}>
              {data ? formatGbp(data.likely_gbp) : "—"}
            </p>
            <p className="mt-1 text-[10px] text-ink/40">expected P&amp;L</p>
          </div>
          <div className="rounded-xl border border-seam bg-bg p-3">
            <p className="text-[10px] uppercase tracking-widest text-ink/40">Upside</p>
            <p className="mt-1.5 font-mono text-xl font-semibold tabular-nums text-price-up">
              {data ? formatGbp(data.upside_gbp) : "—"}
            </p>
            <p className="mt-1 text-[10px] text-ink/40">95th percentile</p>
          </div>
        </div>
      )}

      {/* Edge / regime */}
      <div className="mt-4 grid grid-cols-3 gap-2 text-center">
        <div className="rounded-lg bg-bg p-2">
          <p className="text-[9px] uppercase tracking-widest text-ink/40">Edge</p>
          <p className={`mt-0.5 font-mono text-sm font-semibold tabular-nums ${riskColor}`}>
            {data ? data.edge_score.toFixed(2) : "—"}
          </p>
        </div>
        <div className="rounded-lg bg-bg p-2">
          <p className="text-[9px] uppercase tracking-widest text-ink/40">Regime</p>
          <p className="mt-0.5 font-mono text-sm font-semibold uppercase text-ink">
            {data?.regime ?? "—"}
          </p>
        </div>
        <div className="rounded-lg bg-bg p-2">
          <p className="text-[9px] uppercase tracking-widest text-ink/40">Confidence</p>
          <p className="mt-0.5 font-mono text-sm font-semibold tabular-nums text-ink">
            {data ? `${Math.round(data.confidence * 100)}%` : "—"}
          </p>
        </div>
      </div>

      {/* Rationale */}
      <div className="mt-4 rounded-lg border border-seam bg-bg p-3">
        <p className="text-[10px] uppercase tracking-widest text-ink/40">Read</p>
        <p className="mt-1 text-[12px] leading-relaxed text-ink/75">
          {error ? `Error: ${error}` : data?.rationale ?? (loading ? "scoring…" : "—")}
        </p>
        {data && cursorTimestampMs ? (
          <p className="mt-2 text-[10px] text-ink/40">
            anchored to{" "}
            <span className="font-mono text-ink/55">
              {new Date(cursorTimestampMs).toUTCString().replace("GMT", "UTC")}
            </span>
          </p>
        ) : null}
      </div>

      <p className="mt-3 text-[10px] text-ink/30">
        Educational tool. Not financial advice. Numbers reflect modelled distributions, not realised outcomes.
      </p>
    </div>
  );
}
