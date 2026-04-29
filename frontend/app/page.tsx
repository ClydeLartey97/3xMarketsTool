import type { Route } from "next";
import Link from "next/link";

import { BackendOfflineState } from "@/components/backend-offline-state";
import { getDashboard, getMarkets } from "@/lib/api";

export const dynamic = "force-dynamic";

const REGION_FLAGS: Record<string, string> = {
  Texas: "🇺🇸",
  "U.S. East Coast": "🇺🇸",
  "United Kingdom": "🇬🇧",
  Germany: "🇩🇪",
  France: "🇫🇷",
  Nordics: "🇸🇪",
};

export default async function HomePage() {
  try {
    const markets = await getMarkets();

    const dashboardResults = await Promise.allSettled(
      markets.map((market) => getDashboard(market.code)),
    );

    const marketData = markets.map((market, index) => {
      const result = dashboardResults[index];
      if (result.status === "fulfilled") {
        const dashboard = result.value;
        const latestPrice = dashboard.recent_prices[dashboard.recent_prices.length - 1];
        const prevPrice = dashboard.recent_prices[dashboard.recent_prices.length - 2];
        const change =
          latestPrice && prevPrice ? latestPrice.price_value - prevPrice.price_value : null;
        const forecast = dashboard.forecasts[0];
        return {
          market,
          latestPrice,
          change,
          forecast,
          avgPrice: dashboard.key_metrics.avg_price_24h,
        };
      }

      return {
        market,
        latestPrice: null,
        change: null,
        forecast: null,
        avgPrice: null,
      };
    });

    return (
      <main className="animate-fade-in">
        <div className="mb-8">
          <div className="mb-3 flex items-center gap-3">
            <span className="live-dot h-2 w-2 rounded-full bg-accent" />
            <span className="font-mono text-xs uppercase tracking-widest text-accent">
              Live market data
            </span>
          </div>
          <h1 className="mb-2 text-4xl font-bold tracking-tight text-ink">
            Power Market Intelligence
          </h1>
          <p className="max-w-xl text-base text-ink/50">
            Real-time prices, forward curves, and event-driven signals for wholesale electricity
            markets.
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {marketData.map(({ market, latestPrice, change, forecast, avgPrice }) => {
            const price = latestPrice?.price_value;
            const isUp = typeof change === "number" && change > 0;
            const isDown = typeof change === "number" && change < 0;
            const flag = REGION_FLAGS[market.region] ?? "🌐";

            return (
              <Link
                key={market.code}
                href={`/markets/${market.code}` as Route}
                className="group relative overflow-hidden rounded-2xl border border-seam bg-surface p-5 transition-all duration-200 hover:border-seam-hi hover:shadow-sm"
              >
                <div className="mb-4 flex items-start justify-between gap-3">
                  <div>
                    <div className="mb-1 flex items-center gap-2">
                      <span className="text-sm">{flag}</span>
                      <span className="font-mono text-[10px] uppercase tracking-widest text-ink/30">
                        {market.code}
                      </span>
                    </div>
                    <h3 className="text-base font-semibold leading-tight text-ink">
                      {market.name}
                    </h3>
                    <p className="mt-0.5 text-xs text-ink/40">
                      {market.region} · {market.timezone}
                    </p>
                  </div>
                  <div
                    className={`rounded-lg px-2.5 py-1.5 text-[10px] font-mono font-semibold uppercase tracking-wider ${
                      isUp
                        ? "bg-price-up/10 text-price-up"
                        : isDown
                          ? "bg-price-dn/10 text-price-dn"
                          : "bg-ink/5 text-ink/40"
                    }`}
                  >
                    {isUp ? "▲" : isDown ? "▼" : "—"}
                    {typeof change === "number" ? ` ${Math.abs(change).toFixed(1)}` : ""}
                  </div>
                </div>

                <div className="mb-4 flex items-end gap-3">
                  <div>
                    <p className="mb-1 text-[10px] uppercase tracking-widest text-ink/30">Spot</p>
                    <p className="font-mono text-2xl font-semibold tabular-nums text-ink">
                      {typeof price === "number" ? (
                        `$${price.toFixed(2)}`
                      ) : (
                        <span className="skeleton block h-7 w-20" />
                      )}
                    </p>
                  </div>
                  {forecast ? (
                    <div className="ml-auto mb-0.5 text-right">
                      <p className="mb-1 text-[10px] uppercase tracking-widest text-ink/30">
                        Next H
                      </p>
                      <p className="font-mono text-lg font-medium tabular-nums text-price-up">
                        ${forecast.point_estimate.toFixed(2)}
                      </p>
                    </div>
                  ) : null}
                </div>

                <div className="flex items-center justify-between border-t border-seam pt-3">
                  <div className="flex items-center gap-3 text-[11px] text-ink/35">
                    {typeof avgPrice === "number" ? (
                      <span>
                        24h avg{" "}
                        <span className="font-mono text-ink/55">${avgPrice.toFixed(0)}</span>
                      </span>
                    ) : null}
                    {forecast ? (
                      <span>
                        spike risk{" "}
                        <span
                          className={`font-mono font-medium ${
                            forecast.spike_probability > 0.4
                              ? "text-price-hot"
                              : "text-ink/55"
                          }`}
                        >
                          {Math.round(forecast.spike_probability * 100)}%
                        </span>
                      </span>
                    ) : null}
                  </div>
                  <span className="text-[11px] font-medium text-ink/25 transition-colors group-hover:text-ink/50">
                    Open desk →
                  </span>
                </div>
              </Link>
            );
          })}
        </div>

        <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-2 text-[11px] text-ink/25">
          <span>Prices derived from real grid data · Weather via Open-Meteo</span>
          <span>GB prices via ELEXON BMRS · Gas via CME NG=F</span>
          <span>Refreshes every 30 min</span>
        </div>
      </main>
    );
  } catch {
    return <BackendOfflineState title="Start the backend to load markets." />;
  }
}
