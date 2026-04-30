"use client";

import { useEffect, useMemo, useState } from "react";

import { getMarketHistory } from "@/lib/api";
import { PricePoint } from "@/types/domain";

export type MarketHistoryRange = "1D" | "1W" | "1M" | "1Y" | "2Y" | "Max";

export const MARKET_HISTORY_RANGES: MarketHistoryRange[] = ["1D", "1W", "1M", "1Y", "2Y", "Max"];

const RANGE_DAYS: Partial<Record<MarketHistoryRange, number>> = {
  "1D": 1,
  "1W": 7,
  "1M": 30,
  "1Y": 365,
  "2Y": 730,
};

function dateRangeFor(range: MarketHistoryRange): { from?: string; to?: string } {
  if (range === "Max") {
    return {};
  }
  const days = RANGE_DAYS[range] ?? 30;
  const to = new Date();
  const from = new Date(to);
  from.setUTCDate(from.getUTCDate() - days);
  return { from: from.toISOString(), to: to.toISOString() };
}

export function useMarketHistory(
  marketCode: string,
  range: MarketHistoryRange,
  marketId: number | undefined,
  fallback: PricePoint[],
) {
  const [history, setHistory] = useState<PricePoint[]>(fallback);
  const [isLoading, setIsLoading] = useState(false);

  const windowParams = useMemo(() => dateRangeFor(range), [range]);

  useEffect(() => {
    setHistory(fallback);
  }, [fallback, marketCode]);

  useEffect(() => {
    if (!marketId) {
      return;
    }

    let cancelled = false;
    setIsLoading(true);

    getMarketHistory(marketId, windowParams.from, windowParams.to)
      .then((points) => {
        if (!cancelled) {
          setHistory(points);
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
  }, [marketCode, marketId, windowParams.from, windowParams.to]);

  return { history, isLoading };
}
