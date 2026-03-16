"use client";

import type { Route } from "next";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { DriverList } from "@/components/driver-list";
import { NewsBriefs } from "@/components/news-briefs";
import { PriceForecastChart } from "@/components/price-forecast-chart";
import { SourceNetwork } from "@/components/source-network";
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

  return (
    <main className="space-y-6">
      <section className="rounded-[2rem] border border-white/75 bg-white/86 p-6 shadow-panel">
        <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.26em] text-slate/55">Market Workbench</p>
            <h2 className="mt-2 font-display text-5xl text-slate">{dashboard.market.name}</h2>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-slate/72">
              This view is designed for a serious power-market user: forecast path, confidence decay, click-through
              source news, structured events, and a reputation-scored source network in one place.
            </p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row">
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
            <div className="flex min-w-[180px] flex-col gap-2">
              <span className="text-xs uppercase tracking-[0.18em] text-slate/50">Beta</span>
              <div className="rounded-2xl border border-dashed border-slate/20 bg-[#fff8ef] px-4 py-3 text-sm text-slate/72">
                Split-screen compare coming soon
              </div>
            </div>
          </div>
        </div>

        <div className="mt-6 grid gap-4 md:grid-cols-3">
          <div className="rounded-[1.5rem] border border-slate/10 bg-[#f7fafc] p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate/50">Latest Forecast</p>
            <p className="mt-2 text-3xl font-semibold text-slate">${latestForecast?.point_estimate.toFixed(2) ?? "--"}</p>
            <p className="mt-1 text-sm text-slate/66">per MWh next interval</p>
          </div>
          <div className="rounded-[1.5rem] border border-slate/10 bg-[#f7fafc] p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate/50">Spike Probability</p>
            <p className="mt-2 text-3xl font-semibold text-slate">
              {Math.round((latestForecast?.spike_probability ?? 0) * 100)}%
            </p>
            <p className="mt-1 text-sm text-slate/66">near-term abnormal move risk</p>
          </div>
          <div className="rounded-[1.5rem] border border-slate/10 bg-[#f7fafc] p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate/50">Confidence Band</p>
            <p className="mt-2 text-3xl font-semibold text-slate">
              ${latestForecast?.lower_bound.toFixed(0) ?? "--"}-${latestForecast?.upper_bound.toFixed(0) ?? "--"}
            </p>
            <p className="mt-1 text-sm text-slate/66">green near-term, warmer further out</p>
          </div>
        </div>
      </section>

      <section className="rounded-[2rem] border border-white/75 bg-white/90 p-6 shadow-panel">
        <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-slate/55">Actual vs Forecast</p>
            <h2 className="mt-2 text-3xl font-semibold text-slate">Price path and confidence profile</h2>
          </div>
          <div className="rounded-full border border-slate/10 bg-[#f5f8fb] px-4 py-2 text-sm text-slate/66">
            {timeframeHours}-hour view · {dashboard.market.timezone}
          </div>
        </div>
        <PriceForecastChart history={chartData.history} forecast={chartData.forward} />
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        <DriverList
          compact
          drivers={[
            dashboard.latest_forecast?.rationale_summary ?? "Model rationale unavailable.",
            `Recent 24-hour average price is $${dashboard.key_metrics.avg_price_24h.toFixed(2)} with ${dashboard.key_metrics.high_severity_events} high-severity events in the current context window.`,
            "Further-out forecast segments are intentionally shown as less certain because their signal depends more on weather path, load evolution, and event persistence assumptions.",
          ]}
        />
        <NewsBriefs items={dashboard.recent_news.slice(0, 8)} />
      </section>

      <SourceNetwork sources={dashboard.tracked_sources} />
    </main>
  );
}
