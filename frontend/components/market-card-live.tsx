"use client";
/**
 * Client component that fetches the per-market spot + forecast after the
 * page has already streamed. Keeps the home page first-paint instant —
 * users see the grid of market cards immediately, prices fade in as the
 * backend responds (in parallel across all cards, not blocking render).
 */
import { useEffect, useState } from "react";

import { getForecast, getPrices } from "@/lib/api";
import type { ForecastPoint, PricePoint } from "@/types/domain";

export type MarketLiveStats = {
  spot: number | null;
  change: number | null;
  forecast: ForecastPoint | null;
  avgPrice: number | null;
};

const EMPTY: MarketLiveStats = { spot: null, change: null, forecast: null, avgPrice: null };

export function MarketCardLive({
  marketId,
  render,
}: {
  marketId: number;
  render: (stats: MarketLiveStats, loading: boolean) => React.ReactNode;
}) {
  const [stats, setStats] = useState<MarketLiveStats>(EMPTY);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getPrices(marketId), getForecast(marketId)])
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
  }, [marketId]);

  return <>{render(stats, loading)}</>;
}
