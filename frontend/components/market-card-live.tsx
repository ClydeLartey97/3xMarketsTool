"use client";
/**
 * Client component for a single market card on the home page.
 *
 * Per performance preservation plan §4.2, the home page now batches all
 * card stats via /markets/overview and passes them down through the
 * `preloaded` prop. If `preloaded` is omitted (or set to `undefined`),
 * the card falls back to its legacy per-card fetch so any caller still
 * using the original prop shape keeps working.
 *
 * Owns its full UI (not a render prop) because render props can't be
 * passed from server components to client components — functions don't
 * cross the RSC boundary.
 */
import type { Route } from "next";
import Link from "next/link";
import { useEffect, useState } from "react";

import { getForecast, getPrices, type MarketOverviewItem } from "@/lib/api";
import type { ForecastPoint, Market, PricePoint } from "@/types/domain";

type Stats = {
  spot: number | null;
  change: number | null;
  forecast: ForecastPoint | null;
  avgPrice: number | null;
};

const EMPTY: Stats = { spot: null, change: null, forecast: null, avgPrice: null };

function statsFromOverview(entry: MarketOverviewItem): Stats {
  const f = entry.next_forecast;
  return {
    spot: entry.spot,
    change: entry.change,
    forecast: f
      ? ({
          forecast_for_timestamp: f.forecast_for_timestamp,
          point_estimate: f.point_estimate,
          lower_bound: f.lower_bound,
          upper_bound: f.upper_bound,
          currency: f.currency,
          spike_probability: f.spike_probability,
        } as unknown as ForecastPoint)
      : null,
    avgPrice: entry.avg_price_24h,
  };
}

export function MarketCardLive({
  market,
  flag,
  preloaded,
}: {
  market: Market;
  flag: string;
  preloaded?: MarketOverviewItem | null;
}) {
  const [stats, setStats] = useState<Stats>(() =>
    preloaded ? statsFromOverview(preloaded) : EMPTY,
  );
  const [loading, setLoading] = useState(() => preloaded == null);

  useEffect(() => {
    if (preloaded) {
      setStats(statsFromOverview(preloaded));
      setLoading(false);
      return;
    }
    // Fallback: legacy per-card fetch path (kept per plan §4.3).
    let cancelled = false;
    setLoading(true);
    Promise.all([getPrices(market.id), getForecast(market.id)])
      .then(([prices, forecasts]: [PricePoint[], ForecastPoint[]]) => {
        if (cancelled) return;
        const latest = prices[prices.length - 1];
        const prev = prices[prices.length - 2];
        const change = latest && prev ? latest.price_value - prev.price_value : null;
        const lastDay = prices.slice(-24);
        const avgPrice = lastDay.length
          ? lastDay.reduce((sum, p) => sum + p.price_value, 0) / lastDay.length
          : null;
        setStats({
          spot: latest?.price_value ?? null,
          change,
          forecast: forecasts[0] ?? null,
          avgPrice,
        });
      })
      .catch(() => {
        if (!cancelled) setStats(EMPTY);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [market.id, preloaded]);

  const { spot, change, forecast, avgPrice } = stats;
  const isUp = typeof change === "number" && change > 0;
  const isDown = typeof change === "number" && change < 0;

  return (
    <Link
      href={`/markets/${market.code}` as Route}
      className="group relative overflow-hidden rounded-2xl border border-seam bg-surface p-5 transition-all duration-200 hover:-translate-y-1 hover:border-seam-hi hover:shadow-panel"
    >
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <div className="mb-1 flex items-center gap-2">
            <span className="text-sm">{flag}</span>
            <span className="eyebrow text-[10px] text-ink/30">
              {market.code}
            </span>
          </div>
          <h3 className="text-base font-semibold leading-tight text-ink">{market.name}</h3>
          <p className="mt-0.5 text-xs text-ink/40">
            {market.region} · {market.timezone}
          </p>
        </div>
        <div
          className={`rounded-lg px-2.5 py-1.5 text-[10px] eyebrow font-semibold ${
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
          <p className="mb-1 eyebrow text-[10px] text-ink/30">Spot</p>
          <p className="font-mono text-2xl font-semibold tabular-nums text-ink">
            {typeof spot === "number" ? (
              `$${spot.toFixed(2)}`
            ) : loading ? (
              <span className="skeleton block h-7 w-20" />
            ) : (
              "—"
            )}
          </p>
        </div>
        {forecast ? (
          <div className="ml-auto mb-0.5 text-right">
            <p className="mb-1 eyebrow text-[10px] text-ink/30">Next H</p>
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
              24h avg <span className="font-mono text-ink/55">${avgPrice.toFixed(0)}</span>
            </span>
          ) : null}
          {forecast ? (
            <span>
              spike risk{" "}
              <span
                className={`font-mono font-medium ${
                  forecast.spike_probability > 0.4 ? "text-price-hot" : "text-ink/55"
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
}
