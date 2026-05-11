"use client";

import { useEffect, useMemo, useState } from "react";

import {
  PriceChart,
  type ChartForecastPoint,
  type ChartHistoryPoint,
} from "@/components/price-chart";
import {
  getMarketTimeseries,
  type MarketTimeseriesPoint,
} from "@/lib/api";
import type { EventItem } from "@/types/domain";

type CrosshairPayload = {
  timestampMs: number;
  price: number;
  isForecast: boolean;
};

export type KlinePriceChartProps = {
  marketId: number;
  history: ChartHistoryPoint[];
  forecast: ChartForecastPoint[];
  livePriceTick?: ChartHistoryPoint | null;
  events?: EventItem[];
  timezoneLabel?: string;
  onCrosshair?: (payload: CrosshairPayload | null) => void;
};

const SEVERITY_CLASS: Record<string, string> = {
  high: "border-price-dn bg-price-dn text-bg",
  medium: "border-amber-300 bg-amber-300 text-bg",
  low: "border-price-up bg-price-up text-bg",
};

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function eventTimeMs(event: EventItem) {
  return new Date(event.start_time ?? event.created_at).getTime();
}

export function KlinePriceChart({
  marketId,
  history,
  forecast,
  livePriceTick,
  events = [],
  timezoneLabel,
  onCrosshair,
}: KlinePriceChartProps) {
  const [fundamentals, setFundamentals] = useState<MarketTimeseriesPoint[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<EventItem | null>(null);

  useEffect(() => {
    let cancelled = false;
    getMarketTimeseries(marketId)
      .then((result) => {
        if (!cancelled) setFundamentals(result);
      })
      .catch(() => {
        if (!cancelled) setFundamentals([]);
      });
    return () => {
      cancelled = true;
    };
  }, [marketId]);

  const timeBounds = useMemo(() => {
    const timestamps = [...history.map((p) => p.timestamp), ...forecast.map((p) => p.timestamp)]
      .map((timestamp) => new Date(timestamp).getTime())
      .filter(Number.isFinite);
    return {
      min: Math.min(...timestamps),
      max: Math.max(...timestamps),
    };
  }, [history, forecast]);

  const eventMarkers = useMemo(() => {
    const span = Math.max(1, timeBounds.max - timeBounds.min);
    return events
      .map((event) => ({
        event,
        leftPct: clamp(((eventTimeMs(event) - timeBounds.min) / span) * 100, 0, 100),
      }))
      .filter((item) => Number.isFinite(item.leftPct));
  }, [events, timeBounds]);

  const fundamentalSlice = fundamentals.slice(-96);

  return (
    <div className="space-y-2">
      <PriceChart
        history={history}
        forecast={forecast}
        livePriceTick={livePriceTick}
        timezoneLabel={timezoneLabel}
        onCrosshair={onCrosshair}
      />

      <div className="rounded-xl border border-seam bg-surface p-3">
        <div className="mb-2 flex items-center justify-between text-[10px] uppercase tracking-widest text-ink/40">
          <span>Wind / solar share</span>
          <span>{fundamentalSlice.length}h</span>
        </div>
        <div className="flex h-10 items-end gap-px overflow-hidden rounded-md bg-bg p-1">
          {fundamentalSlice.map((point) => {
            const wind = clamp(point.wind_share ?? 0, 0, 1);
            const solar = clamp(point.solar_share ?? 0, 0, 1);
            return (
              <div key={point.timestamp} className="flex min-w-[3px] flex-1 flex-col justify-end gap-px">
                <span className="block rounded-sm bg-sky-300/70" style={{ height: `${Math.max(2, wind * 34)}px` }} />
                <span className="block rounded-sm bg-amber-300/75" style={{ height: `${Math.max(2, solar * 34)}px` }} />
              </div>
            );
          })}
        </div>
      </div>

      <div className="relative rounded-xl border border-seam bg-surface p-3">
        <div className="mb-2 flex items-center justify-between text-[10px] uppercase tracking-widest text-ink/40">
          <span>Event markers</span>
          <span>{eventMarkers.length}</span>
        </div>
        <div className="relative h-10 rounded-md bg-bg">
          {eventMarkers.map(({ event, leftPct }) => (
            <button
              key={event.id}
              type="button"
              title={event.title}
              onClick={() => setSelectedEvent(event)}
              className={`absolute top-3 h-0 w-0 -translate-x-1/2 border-x-[7px] border-b-[13px] border-x-transparent ${
                SEVERITY_CLASS[event.severity] ?? SEVERITY_CLASS.low
              }`}
              style={{ left: `${leftPct}%` }}
            />
          ))}
        </div>
        {selectedEvent ? (
          <div className="mt-3 rounded-lg border border-seam bg-bg p-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-xs font-semibold text-ink">{selectedEvent.title}</p>
                <p className="mt-1 text-[11px] leading-relaxed text-ink/60">{selectedEvent.description}</p>
              </div>
              <button
                type="button"
                onClick={() => setSelectedEvent(null)}
                className="rounded px-2 py-1 text-sm text-ink/45 hover:bg-surface hover:text-ink"
              >
                ×
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
