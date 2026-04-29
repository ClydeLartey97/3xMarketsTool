"use client";

import dynamic from "next/dynamic";
import type { Route } from "next";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { ClientErrorBoundary } from "@/components/client-error-boundary";
import { NewsBriefs } from "@/components/news-briefs";
import { RiskPanel } from "@/components/risk-panel";
import { SignalStack } from "@/components/signal-stack";
import { DashboardData, Market } from "@/types/domain";

// Chart is canvas-based — render only on client
const PriceChart = dynamic(() => import("@/components/price-chart").then((m) => m.PriceChart), {
  ssr: false,
  loading: () => (
    <div className="flex h-[620px] items-center justify-center rounded-2xl border border-seam bg-surface text-sm text-ink/40">
      Loading chart…
    </div>
  ),
});

function buildHistory(dashboard: DashboardData) {
  return dashboard.recent_prices.map((p) => ({ timestamp: p.timestamp, value: p.price_value }));
}

function buildForecast(dashboard: DashboardData) {
  return dashboard.forecasts.map((f) => ({
    timestamp: f.forecast_for_timestamp,
    point: f.point_estimate,
    lower: f.lower_bound,
    upper: f.upper_bound,
  }));
}

export function MarketWorkbench({
  markets,
  dashboard,
}: {
  markets: Market[];
  dashboard: DashboardData;
}) {
  const router = useRouter();
  const [cursorTs, setCursorTs] = useState<number | null>(null);
  const history = useMemo(() => buildHistory(dashboard), [dashboard]);
  const forecast = useMemo(() => buildForecast(dashboard), [dashboard]);

  const lastObserved = dashboard.recent_prices[dashboard.recent_prices.length - 1];
  const latestForecast = dashboard.forecasts[0] ?? dashboard.latest_forecast;
  const front = lastObserved && latestForecast ? latestForecast.point_estimate - lastObserved.price_value : null;
  const directionalAccuracy = Math.round((dashboard.key_metrics.directional_accuracy ?? 0) * 100);
  const spikePrecision = Math.round((dashboard.key_metrics.spike_precision ?? 0) * 100);

  return (
    <main className="space-y-5">
      {/* Header */}
      <section className="rounded-2xl border border-seam bg-surface p-5">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="mb-2 flex items-center gap-2">
              <span className="rounded-md bg-ink/5 px-2 py-0.5 text-[10px] font-mono uppercase tracking-widest text-ink/55">
                {dashboard.market.code}
              </span>
              <span className="text-[11px] text-ink/45">{dashboard.market.region}</span>
              <span className="text-[11px] text-ink/35">·</span>
              <span className="text-[11px] text-ink/45">{dashboard.market.timezone}</span>
            </div>
            <h1 className="text-3xl font-semibold tracking-tight text-ink">{dashboard.market.name}</h1>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={dashboard.market.code}
              onChange={(event) => router.push(`/markets/${event.target.value}` as Route)}
              className="rounded-lg border border-seam bg-bg px-3 py-2 text-sm text-ink outline-none focus:border-seam-hi"
            >
              {markets.map((m) => (
                <option key={m.code} value={m.code}>
                  {m.name} · {m.region}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* KPI strip */}
        <div className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-5">
          <KpiTile label="Spot" value={lastObserved ? `$${lastObserved.price_value.toFixed(2)}` : "—"} />
          <KpiTile label="Next H" value={latestForecast ? `$${latestForecast.point_estimate.toFixed(2)}` : "—"} accent />
          <KpiTile
            label="Front gap"
            value={typeof front === "number" ? `${front >= 0 ? "+" : ""}${front.toFixed(2)}` : "—"}
            tone={typeof front === "number" && front >= 0 ? "up" : "dn"}
          />
          <KpiTile label="Spike risk" value={`${Math.round((latestForecast?.spike_probability ?? 0) * 100)}%`} />
          <KpiTile label="Model dir-acc" value={`${directionalAccuracy}%`} sub={`spike ${spikePrecision}%`} />
        </div>
      </section>

      {/* Chart + risk panel — the desk */}
      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <ClientErrorBoundary
          fallbackTitle="Chart engine recovering"
          fallbackBody="The chart hit a client-side issue. Refresh once. The rest of the desk stays live."
        >
          <PriceChart
            history={history}
            forecast={forecast}
            timezoneLabel={dashboard.market.timezone}
            onCrosshair={(p) => setCursorTs(p?.timestampMs ?? null)}
          />
        </ClientErrorBoundary>
        <RiskPanel marketCode={dashboard.market.code} cursorTimestampMs={cursorTs} />
      </section>

      {/* Signals + news */}
      <SignalStack dashboard={dashboard} />

      <section className="grid gap-4 xl:grid-cols-2">
        <NewsBriefs items={dashboard.recent_news.slice(0, 8)} />
        <div className="rounded-2xl border border-seam bg-surface p-5">
          <p className="text-[10px] uppercase tracking-widest text-ink/40">Model rationale</p>
          <p className="mt-2 text-sm leading-relaxed text-ink/80">
            {dashboard.latest_forecast?.rationale_summary ?? "No rationale available."}
          </p>
          <div className="mt-4 flex flex-wrap gap-3 text-[11px] text-ink/45">
            <span>Directional accuracy <span className="font-mono text-ink/70">{directionalAccuracy}%</span></span>
            <span>Spike precision <span className="font-mono text-ink/70">{spikePrecision}%</span></span>
            <span>
              Avg spike risk (12h){" "}
              <span className="font-mono text-ink/70">
                {Math.round((dashboard.key_metrics.avg_spike_probability_12h ?? 0) * 100)}%
              </span>
            </span>
          </div>
        </div>
      </section>
    </main>
  );
}

function KpiTile({
  label,
  value,
  sub,
  tone,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "up" | "dn";
  accent?: boolean;
}) {
  const valueClass = accent
    ? "text-price-up"
    : tone === "up"
      ? "text-price-up"
      : tone === "dn"
        ? "text-price-dn"
        : "text-ink";
  return (
    <div className="rounded-xl border border-seam bg-bg p-3">
      <p className="text-[10px] uppercase tracking-widest text-ink/40">{label}</p>
      <p className={`mt-1.5 font-mono text-xl font-semibold tabular-nums ${valueClass}`}>{value}</p>
      {sub ? <p className="mt-0.5 text-[10px] text-ink/40">{sub}</p> : null}
    </div>
  );
}
