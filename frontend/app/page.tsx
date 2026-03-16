import Link from "next/link";

import { AlertsPanel } from "@/components/alerts-panel";
import { DriverList } from "@/components/driver-list";
import { EventFeed } from "@/components/event-feed";
import { MetricCard } from "@/components/metric-card";
import { PriceForecastChart } from "@/components/price-forecast-chart";
import { getDashboard, getMarkets } from "@/lib/api";

export const dynamic = "force-dynamic";

function formatChartData(
  prices: Awaited<ReturnType<typeof getDashboard>>["recent_prices"],
  forecasts: Awaited<ReturnType<typeof getDashboard>>["forecasts"],
) {
  const history = prices.slice(-36).map((point) => ({
    timestamp: new Date(point.timestamp).toLocaleString([], { month: "short", day: "numeric", hour: "numeric" }),
    actual: point.price_value,
  }));
  const forward = forecasts.slice(0, 24).map((point) => ({
    timestamp: new Date(point.forecast_for_timestamp).toLocaleString([], { month: "short", day: "numeric", hour: "numeric" }),
    forecast: point.point_estimate,
    lower: point.lower_bound,
    upper: point.upper_bound,
  }));
  return [...history, ...forward];
}

export default async function HomePage() {
  const markets = await getMarkets();
  const selectedMarket = markets[0];
  const dashboard = await getDashboard(selectedMarket.code);
  const chartData = formatChartData(dashboard.recent_prices, dashboard.forecasts);

  return (
    <main className="space-y-6">
      <section className="grid gap-6 lg:grid-cols-[1.25fr_0.75fr]">
        <div className="rounded-[2rem] border border-white/60 bg-slate p-7 text-white shadow-panel">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.28em] text-white/55">Launch Market</p>
              <h2 className="mt-2 font-display text-4xl">{dashboard.market.name}</h2>
              <p className="mt-3 max-w-xl text-sm text-white/72">
                3x is tracking forecast risk, event-driven dislocations, and local power price sensitivity
                across the first launch market with a backend-driven intelligence stack.
              </p>
            </div>
            <Link href={`/markets/${dashboard.market.code}`} className="rounded-full bg-white px-5 py-3 text-sm font-semibold text-slate">
              Open market detail
            </Link>
          </div>
          <div className="mt-8 grid gap-4 md:grid-cols-3">
            <MetricCard
              label="Latest Forecast"
              value={`$${dashboard.latest_forecast?.point_estimate.toFixed(2) ?? "--"}/MWh`}
              tone="positive"
              helper="Next interval point estimate"
            />
            <MetricCard
              label="Spike Probability"
              value={`${Math.round((dashboard.latest_forecast?.spike_probability ?? 0) * 100)}%`}
              tone="caution"
              helper="Probability of abnormal hourly spike"
            />
            <MetricCard
              label="Confidence Band"
              value={
                dashboard.latest_forecast
                  ? `$${dashboard.latest_forecast.lower_bound.toFixed(0)}-$${dashboard.latest_forecast.upper_bound.toFixed(0)}`
                  : "--"
              }
              tone="default"
              helper="80% model confidence interval"
            />
          </div>
        </div>
        <AlertsPanel alerts={dashboard.active_alerts} />
      </section>

      <section className="rounded-[2rem] border border-white/60 bg-white/85 p-6 shadow-panel">
        <div className="mb-5 flex items-end justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-slate/60">Forecast Surface</p>
            <h2 className="mt-2 text-2xl font-semibold text-slate">Actual versus forecast price path</h2>
          </div>
          <div className="text-sm text-slate/65">
            24h average price: ${dashboard.key_metrics.avg_price_24h.toFixed(2)} | high-severity events:{" "}
            {dashboard.key_metrics.high_severity_events}
          </div>
        </div>
        <PriceForecastChart data={chartData} />
      </section>

      <section className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <DriverList
          drivers={[
            dashboard.latest_forecast?.rationale_summary ?? "Model rationale unavailable.",
            "Event intelligence remains bullish when outages overlap the evening ramp or tight reserve conditions.",
            "The architecture keeps raw articles, extracted events, and market forecasts separated for auditability.",
          ]}
        />
        <EventFeed events={dashboard.recent_events.slice(0, 5)} />
      </section>
    </main>
  );
}
