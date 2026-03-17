"use client";

import type { Route } from "next";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { DriverEvidence, DriverList } from "@/components/driver-list";
import { NewsBriefs } from "@/components/news-briefs";
import { PriceForecastChart } from "@/components/price-forecast-chart";
import { DashboardData, Market } from "@/types/domain";

const TIMEFRAME_OPTIONS = [
  { label: "12H", value: 12 },
  { label: "24H", value: 24 },
  { label: "48H", value: 48 },
];

function buildChartData(dashboard: DashboardData, horizonHours: number) {
  const historyWindow = horizonHours <= 12 ? 18 : horizonHours <= 24 ? 30 : 48;
  const history = dashboard.recent_prices.slice(-historyWindow).map((point) => ({
    timestamp: point.timestamp,
    label: new Date(point.timestamp).toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "numeric",
    }),
    actual: point.price_value,
  }));
  const forward = dashboard.forecasts.slice(0, horizonHours).map((point, index, arr) => ({
    timestamp: point.forecast_for_timestamp,
    label: new Date(point.forecast_for_timestamp).toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "numeric",
    }),
    forecast: point.point_estimate,
    lower: point.lower_bound,
    upper: point.upper_bound,
    confidenceRatio: arr.length <= 1 ? 0 : index / (arr.length - 1),
  }));
  return { history, forward };
}

function computeEvidenceScore(dashboard: DashboardData) {
  if (!dashboard.recent_news.length) {
    return 0.18;
  }
  const now = Date.now();
  const weighted = dashboard.recent_news.slice(0, 8).reduce((sum, item) => {
    const ageHours = (now - new Date(item.published_at).getTime()) / (1000 * 60 * 60);
    const freshness = Math.max(0.18, 1 - ageHours / 168);
    return sum + (item.credibility_rating / 100) * freshness;
  }, 0);
  return Math.min(1, weighted / 4.8);
}

function buildDriverEvidence(dashboard: DashboardData, directionalAccuracy: number, spikePrecision: number): DriverEvidence[] {
  const newsDrivers = dashboard.recent_news.slice(0, 3).map((item, index) => ({
    id: `news-${item.id}`,
    title: index === 0 ? "Primary evidence" : index === 1 ? "Secondary evidence" : "Context evidence",
    body: item.display_summary,
    href: item.source_url,
    sourceName: item.source_name,
    sourceMeta: `${Math.round(item.credibility_rating)}/100 credibility`,
  }));

  return [
    {
      id: "rationale",
      title: "Model read",
      body: dashboard.latest_forecast?.rationale_summary ?? "Model rationale unavailable.",
      sourceMeta: `${directionalAccuracy}% directional accuracy · ${spikePrecision}% spike precision`,
    },
    ...newsDrivers,
  ];
}

export function MarketWorkbench({
  markets,
  dashboard,
}: {
  markets: Market[];
  dashboard: DashboardData;
}) {
  const router = useRouter();
  const [timeframeHours, setTimeframeHours] = useState(24);
  const chartData = useMemo(() => buildChartData(dashboard, timeframeHours), [dashboard, timeframeHours]);
  const latestForecast = dashboard.forecasts[0] ?? dashboard.latest_forecast;
  const directionalAccuracy = Math.round((dashboard.key_metrics.directional_accuracy ?? 0) * 100);
  const spikePrecision = Math.round((dashboard.key_metrics.spike_precision ?? 0) * 100);
  const evidenceScore = useMemo(() => computeEvidenceScore(dashboard), [dashboard]);
  const driverStack = useMemo(
    () => buildDriverEvidence(dashboard, directionalAccuracy, spikePrecision),
    [dashboard, directionalAccuracy, spikePrecision],
  );
  const curveSource = dashboard.market.metadata?.curve_source as
    | { label?: string; url?: string; kind?: string }
    | undefined;

  return (
    <main className="space-y-6">
      <section className="rounded-[2rem] border border-white/75 bg-white/86 p-6 shadow-panel">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.26em] text-slate/55">Market Workbench</p>
            <h2 className="mt-2 font-display text-5xl text-slate">{dashboard.market.name}</h2>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-slate/72">
              Event-aware forward curve, article-level evidence, and a desk-style chart surface for serious power-market
              positioning.
            </p>
          </div>
          <div className="grid gap-3 lg:grid-cols-[minmax(280px,_1fr)_160px_auto]">
            <label className="flex min-w-[260px] flex-col gap-2">
              <span className="text-xs uppercase tracking-[0.18em] text-slate/50">Market</span>
              <select
                value={dashboard.market.code}
                onChange={(event) => router.push(`/markets/${event.target.value}` as Route)}
                className="rounded-2xl border border-slate/10 bg-[#f5f8fb] px-4 py-3 text-sm text-slate"
              >
                {markets.map((market) => (
                  <option key={market.code} value={market.code}>
                    {market.name} · {market.region}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex min-w-[140px] flex-col gap-2">
              <span className="text-xs uppercase tracking-[0.18em] text-slate/50">Horizon</span>
              <select
                value={timeframeHours}
                onChange={(event) => setTimeframeHours(Number(event.target.value))}
                className="rounded-2xl border border-slate/10 bg-[#f5f8fb] px-4 py-3 text-sm text-slate"
              >
                {TIMEFRAME_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <div className="flex flex-col gap-2">
              <span className="text-xs uppercase tracking-[0.18em] text-slate/50">Desk mode</span>
              <div className="flex rounded-2xl border border-slate/10 bg-[#f5f8fb] p-1">
                <button type="button" className="rounded-[1rem] bg-white px-4 py-3 text-sm text-slate shadow-sm">
                  Single
                </button>
                <button
                  type="button"
                  className="rounded-[1rem] px-4 py-3 text-sm text-slate/54 transition hover:text-slate/72"
                >
                  Split screen beta
                </button>
              </div>
            </div>
          </div>
        </div>

        <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-[1.5rem] border border-slate/10 bg-[#f7fafc] p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate/50">Latest Forward Price</p>
            <p className="mt-2 text-3xl font-semibold text-slate">${latestForecast?.point_estimate.toFixed(2) ?? "--"}</p>
            <p className="mt-1 text-sm text-slate/66">next interval point estimate</p>
          </div>
          <div className="rounded-[1.5rem] border border-slate/10 bg-[#f7fafc] p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate/50">Spike Probability</p>
            <p className="mt-2 text-3xl font-semibold text-slate">
              {Math.round((latestForecast?.spike_probability ?? 0) * 100)}%
            </p>
            <p className="mt-1 text-sm text-slate/66">abnormal move risk in the front of curve</p>
          </div>
          <div className="rounded-[1.5rem] border border-slate/10 bg-[#f7fafc] p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate/50">Confidence Band</p>
            <p className="mt-2 text-3xl font-semibold text-slate">
              ${latestForecast?.lower_bound.toFixed(0) ?? "--"}-${latestForecast?.upper_bound.toFixed(0) ?? "--"}
            </p>
            <p className="mt-1 text-sm text-slate/66">
              {Math.round(evidenceScore * 100)} evidence score · redder faster when the evidence stack is thin
            </p>
          </div>
          <div className="rounded-[1.5rem] border border-slate/10 bg-[#f7fafc] p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate/50">Directional Accuracy</p>
            <p className="mt-2 text-3xl font-semibold text-slate">{directionalAccuracy}%</p>
            <p className="mt-1 text-sm text-slate/66">latest validation split</p>
          </div>
        </div>
      </section>

      <section className="rounded-[2rem] border border-white/75 bg-white/90 p-6 shadow-panel">
        <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-slate/55">Actual vs Forecast</p>
            <h2 className="mt-2 text-3xl font-semibold text-slate">Actual price against the forward curve</h2>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="rounded-full border border-slate/10 bg-[#f5f8fb] px-4 py-2 text-sm text-slate/66">
              {timeframeHours}-hour view · {dashboard.market.timezone}
            </div>
            <div className="rounded-full border border-[#d7e5df] bg-[#eef8f3] px-4 py-2 text-sm text-[#127255]">
              Hybrid signal model
            </div>
            {curveSource?.url ? (
              <a
                href={curveSource.url}
                target="_blank"
                rel="noreferrer"
                className="rounded-full border border-[#d9dfeb] bg-[#f7f9fc] px-4 py-2 text-sm text-slate/66 transition hover:bg-white"
              >
                {curveSource.label ?? "Official market source"}
              </a>
            ) : null}
          </div>
        </div>
        <PriceForecastChart history={chartData.history} forecast={chartData.forward} evidenceScore={evidenceScore} />
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        <DriverList compact drivers={driverStack} />
        <NewsBriefs items={dashboard.recent_news.slice(0, 8)} />
      </section>
    </main>
  );
}
