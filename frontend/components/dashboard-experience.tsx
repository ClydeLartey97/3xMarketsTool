"use client";

import type { Route } from "next";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { DriverList } from "@/components/driver-list";
import { EventFeed } from "@/components/event-feed";
import { PriceForecastChart } from "@/components/price-forecast-chart";
import { getDashboard } from "@/lib/api";
import { DashboardData, Market } from "@/types/domain";

const TIMEFRAME_OPTIONS = [
  { label: "Next 12 hours", value: 12 },
  { label: "Next 24 hours", value: 24 },
  { label: "Next 48 hours", value: 48 },
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

export function DashboardExperience({
  markets,
  initialDashboard,
}: {
  markets: Market[];
  initialDashboard: DashboardData;
}) {
  const [selectedMarketCode, setSelectedMarketCode] = useState(initialDashboard.market.code);
  const [timeframeHours, setTimeframeHours] = useState(24);
  const [dashboard, setDashboard] = useState(initialDashboard);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (selectedMarketCode === dashboard.market.code) {
      return;
    }

    let cancelled = false;
    setIsLoading(true);

    getDashboard(selectedMarketCode)
      .then((nextDashboard) => {
        if (!cancelled) {
          setDashboard(nextDashboard);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedMarketCode, dashboard.market.code]);

  const selectedMarket = markets.find((market) => market.code === selectedMarketCode) ?? markets[0];
  const chartData = useMemo(() => buildChartData(dashboard, timeframeHours), [dashboard, timeframeHours]);
  const latestForecast = dashboard.forecasts[0] ?? dashboard.latest_forecast;
  const visibleEvents = dashboard.recent_events.slice(0, 3);

  return (
    <main className="space-y-6">
      <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur">
        <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
          <div>
            <p className="text-xs uppercase tracking-[0.26em] text-slate/55">Market Selection</p>
            <h2 className="mt-2 font-display text-4xl text-slate">Choose a market, then inspect the signal.</h2>
            <p className="mt-3 max-w-2xl text-sm leading-7 text-slate/72">
              Start with the market you care about, then move straight into actual versus forecast price behavior,
              the confidence profile of the horizon, and the event context moving the curve.
            </p>
            <div className="mt-6 flex flex-col gap-3 sm:flex-row">
              <label className="flex min-w-[280px] flex-1 flex-col gap-2">
                <span className="text-xs uppercase tracking-[0.2em] text-slate/50">Power market</span>
                <select
                  value={selectedMarketCode}
                  onChange={(event) => setSelectedMarketCode(event.target.value)}
                  className="rounded-2xl border border-slate/10 bg-[#f4f7fb] px-4 py-3 text-sm text-slate outline-none ring-0 transition focus:border-slate/30"
                >
                  {markets.map((market) => (
                    <option key={market.code} value={market.code}>
                      {market.name} · {market.region}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex min-w-[220px] flex-col gap-2">
                <span className="text-xs uppercase tracking-[0.2em] text-slate/50">Forecast horizon</span>
                <select
                  value={timeframeHours}
                  onChange={(event) => setTimeframeHours(Number(event.target.value))}
                  className="rounded-2xl border border-slate/10 bg-[#f4f7fb] px-4 py-3 text-sm text-slate outline-none ring-0 transition focus:border-slate/30"
                >
                  {TIMEFRAME_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
            <article className="rounded-[1.5rem] border border-slate/10 bg-[#f7fafc] p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-slate/50">Selected Market</p>
              <p className="mt-2 text-xl font-semibold text-slate">{selectedMarket.name}</p>
              <p className="mt-1 text-sm text-slate/65">{selectedMarket.region} · {selectedMarket.timezone}</p>
            </article>
            <article className="rounded-[1.5rem] border border-slate/10 bg-[#f7fafc] p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-slate/50">Latest Forecast</p>
              <p className="mt-2 text-xl font-semibold text-slate">
                ${latestForecast?.point_estimate.toFixed(2) ?? "--"}/MWh
              </p>
              <p className="mt-1 text-sm text-slate/65">
                Spike probability {Math.round((latestForecast?.spike_probability ?? 0) * 100)}%
              </p>
            </article>
            <article className="rounded-[1.5rem] border border-slate/10 bg-[#f7fafc] p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-slate/50">Confidence Signal</p>
              <p className="mt-2 text-xl font-semibold text-slate">
                ${latestForecast?.lower_bound.toFixed(0) ?? "--"}-${latestForecast?.upper_bound.toFixed(0) ?? "--"}
              </p>
              <p className="mt-1 text-sm text-slate/65">Green near-term, warmer as horizon uncertainty expands</p>
            </article>
          </div>
        </div>
      </section>

      <section className="rounded-[2rem] border border-[#d8e2ea] bg-white/88 p-6 shadow-panel">
        <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-slate/55">Actual vs Forecast</p>
            <h2 className="mt-2 text-3xl font-semibold text-slate">
              Price path and confidence decay across the selected horizon
            </h2>
          </div>
          <div className="rounded-full border border-slate/10 bg-[#f5f8fb] px-4 py-2 text-sm text-slate/68">
            {isLoading ? "Loading market..." : `${timeframeHours}-hour view · ${dashboard.market.name}`}
          </div>
        </div>

        <PriceForecastChart history={chartData.history} forecast={chartData.forward} />

        <div className="mt-5 grid gap-3 md:grid-cols-3">
          <div className="rounded-2xl border border-slate/10 bg-[#f8fafc] px-4 py-3 text-sm text-slate/72">
            <span className="font-semibold text-[#128267]">Near-term segments</span> are more trusted because they stay
            close to observed state and recent event conditions.
          </div>
          <div className="rounded-2xl border border-slate/10 bg-[#f8fafc] px-4 py-3 text-sm text-slate/72">
            <span className="font-semibold text-[#c06b11]">Mid-horizon segments</span> reflect moderate uncertainty as
            weather and demand assumptions start to dominate.
          </div>
          <div className="rounded-2xl border border-slate/10 bg-[#f8fafc] px-4 py-3 text-sm text-slate/72">
            <span className="font-semibold text-[#bd3f35]">Far-horizon segments</span> warn that the signal is still
            useful, but structurally less certain than the front of the curve.
          </div>
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-2">
        <DriverList
          drivers={[
            {
              id: "rationale",
              title: "Model read",
              body: dashboard.latest_forecast?.rationale_summary ?? "Model rationale unavailable.",
            },
            {
              id: "market-context",
              title: "Observed context",
              body: `Average price over the latest window is $${dashboard.key_metrics.avg_price_24h.toFixed(2)} with ${dashboard.key_metrics.high_severity_events} high-severity events currently influencing context.`,
            },
            {
              id: "confidence",
              title: "Confidence profile",
              body: "Confidence fades further out because the system relies more heavily on weather, load, and event persistence assumptions at longer horizons.",
            },
          ]}
          compact
        />
        <EventFeed events={visibleEvents} compact title="News and event context" subtitle="Structured market-moving developments" />
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {markets.map((market) => (
          <Link
            key={market.code}
            href={`/markets/${market.code}` as Route}
            className="rounded-[1.6rem] border border-white/70 bg-white/82 p-5 shadow-panel transition hover:-translate-y-0.5 hover:border-slate/20"
          >
            <p className="text-xs uppercase tracking-[0.18em] text-slate/50">{market.region}</p>
            <h3 className="mt-2 text-xl font-semibold text-slate">{market.name}</h3>
            <p className="mt-2 text-sm text-slate/68">{market.timezone}</p>
            <p className="mt-4 text-sm text-slate/72">Open the full detail view for market-specific charts and event overlays.</p>
          </Link>
        ))}
      </section>
    </main>
  );
}
