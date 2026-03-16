import { AlertsPanel } from "@/components/alerts-panel";
import { EventFeed } from "@/components/event-feed";
import { MetricCard } from "@/components/metric-card";
import { PriceForecastChart } from "@/components/price-forecast-chart";
import { getAlerts, getDashboard, getEvents, getForecast, getMarkets, getPrices } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function MarketDetailPage({ params }: { params: Promise<{ marketCode: string }> }) {
  const { marketCode } = await params;
  const markets = await getMarkets();
  const market = markets.find((item) => item.code === marketCode) ?? markets[0];
  const [dashboard, prices, forecasts, events, alerts] = await Promise.all([
    getDashboard(market.code),
    getPrices(market.id),
    getForecast(market.id),
    getEvents(market.id),
    getAlerts(market.id),
  ]);

  const historyData = prices.slice(-48).map((point) => ({
    timestamp: new Date(point.timestamp).toLocaleString([], { month: "short", day: "numeric", hour: "numeric" }),
    actual: point.price_value,
  }));
  const forecastChart = forecasts.slice(0, 24).map((point, index, arr) => ({
    timestamp: new Date(point.forecast_for_timestamp).toLocaleString([], { month: "short", day: "numeric", hour: "numeric" }),
    forecast: point.point_estimate,
    lower: point.lower_bound,
    upper: point.upper_bound,
    confidenceRatio: arr.length <= 1 ? 0 : index / (arr.length - 1),
  }));

  return (
    <main className="space-y-6">
      <section className="grid gap-4 md:grid-cols-4">
        <MetricCard label="Market" value={market.name} helper={market.region} />
        <MetricCard label="Commodity" value={market.commodity_type} helper="Configured through market definitions" />
        <MetricCard
          label="Forecasted Spike Risk"
          value={`${Math.round((dashboard.latest_forecast?.spike_probability ?? 0) * 100)}%`}
          tone="danger"
          helper="Near-term abnormal price probability"
        />
        <MetricCard
          label="Model Version"
          value={dashboard.latest_forecast?.model_version ?? "n/a"}
          helper="Upgradeable shared forecast interface"
        />
      </section>

      <section className="rounded-[2rem] border border-white/60 bg-white/85 p-6 shadow-panel">
        <div className="mb-5 flex items-end justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-slate/60">Market Detail</p>
            <h2 className="mt-2 text-2xl font-semibold text-slate">Historical prices and forward view</h2>
          </div>
          <div className="text-sm text-slate/65">Timezone: {market.timezone}</div>
        </div>
        <PriceForecastChart history={historyData} forecast={forecastChart} />
      </section>

      <section className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <EventFeed events={events} />
        <AlertsPanel alerts={alerts} />
      </section>
    </main>
  );
}
