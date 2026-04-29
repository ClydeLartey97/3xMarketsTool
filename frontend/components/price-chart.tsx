"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import {
  init,
  dispose,
  ActionType,
  CandleType,
  TooltipShowRule,
  TooltipShowType,
  type Chart,
  type KLineData,
} from "klinecharts";

export type ChartHistoryPoint = { timestamp: string; value: number };
export type ChartForecastPoint = {
  timestamp: string;
  point: number;
  lower: number;
  upper: number;
};

type CrosshairPayload = {
  timestampMs: number;
  price: number;
  isForecast: boolean;
};

type ChartType = CandleType.Area | CandleType.CandleSolid | CandleType.Ohlc;

const DRAW_TOOLS: Array<{ label: string; value: string; tip: string }> = [
  { label: "Cursor", value: "", tip: "Pan + crosshair" },
  { label: "Trend", value: "segment", tip: "Trendline between two points" },
  { label: "Ray", value: "rayLine", tip: "Ray from a point" },
  { label: "Horizontal", value: "horizontalStraightLine", tip: "Horizontal price level" },
  { label: "Channel", value: "parallelStraightLine", tip: "Parallel channel" },
  { label: "Fib", value: "fibonacciLine", tip: "Fibonacci retracement" },
  { label: "Rect", value: "rectangle", tip: "Rectangle / range box" },
  { label: "Note", value: "simpleAnnotation", tip: "Annotation marker" },
];

function buildKlineData(
  history: ChartHistoryPoint[],
  forecast: ChartForecastPoint[],
): { kline: KLineData[]; forecastStartMs: number | null } {
  const kline: KLineData[] = [];
  let prevClose: number | null = null;

  for (const h of history) {
    const ts = new Date(h.timestamp).getTime();
    const close = h.value;
    const open = prevClose ?? close;
    const wick = Math.max(Math.abs(close - open) * 0.5, Math.abs(close) * 0.004, 0.5);
    const high = Math.max(open, close) + wick;
    const low = Math.min(open, close) - wick;
    kline.push({ timestamp: ts, open, high, low, close });
    prevClose = close;
  }

  const forecastStartMs = forecast.length ? new Date(forecast[0].timestamp).getTime() : null;

  for (const f of forecast) {
    const ts = new Date(f.timestamp).getTime();
    const close = f.point;
    const open = prevClose ?? close;
    kline.push({
      timestamp: ts,
      open,
      high: f.upper,
      low: f.lower,
      close,
      // custom fields used by overlays
      forecast: 1,
      forecast_lower: f.lower,
      forecast_upper: f.upper,
    } as KLineData);
    prevClose = close;
  }

  kline.sort((a, b) => a.timestamp - b.timestamp);
  return { kline, forecastStartMs };
}

export type PriceChartProps = {
  history: ChartHistoryPoint[];
  forecast: ChartForecastPoint[];
  timezoneLabel?: string;
  onCrosshair?: (payload: CrosshairPayload | null) => void;
};

export function PriceChart({ history, forecast, timezoneLabel, onCrosshair }: PriceChartProps) {
  const containerId = useId().replace(/[:]/g, "_");
  const chartRef = useRef<Chart | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [chartType, setChartType] = useState<ChartType>(CandleType.Area);
  const [activeTool, setActiveTool] = useState<string>("");
  const [overlayIds, setOverlayIds] = useState<string[]>([]);

  const { kline, forecastStartMs } = useMemo(() => buildKlineData(history, forecast), [history, forecast]);

  // Init chart
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const chart = init(container, {
      timezone: timezoneLabel,
      styles: {
        grid: {
          horizontal: { color: "rgba(120,140,165,0.10)" },
          vertical: { color: "rgba(120,140,165,0.06)" },
        },
        candle: {
          tooltip: { showRule: TooltipShowRule.FollowCross, showType: TooltipShowType.Rect },
          priceMark: {
            high: { color: "#dce8ff" },
            low: { color: "#dce8ff" },
            last: {
              upColor: "rgba(34, 197, 94, 0.85)",
              downColor: "rgba(239, 68, 68, 0.85)",
              noChangeColor: "rgba(150, 165, 185, 0.85)",
            },
          },
          bar: {
            upColor: "#22c55e",
            downColor: "#ef4444",
            noChangeColor: "#94a3b8",
            upBorderColor: "#22c55e",
            downBorderColor: "#ef4444",
            noChangeBorderColor: "#94a3b8",
            upWickColor: "#22c55e",
            downWickColor: "#ef4444",
            noChangeWickColor: "#94a3b8",
          },
          area: {
            lineColor: "#5eead4",
            lineSize: 2,
            value: "close",
            backgroundColor: [
              { offset: 0, color: "rgba(94, 234, 212, 0.35)" },
              { offset: 1, color: "rgba(94, 234, 212, 0.0)" },
            ],
          },
        },
        crosshair: {
          horizontal: {
            line: { color: "rgba(180, 200, 225, 0.55)", dashedValue: [4, 6] },
            text: { backgroundColor: "#0d1622", color: "#e2e8f0", borderColor: "#334155" },
          },
          vertical: {
            line: { color: "rgba(180, 200, 225, 0.55)", dashedValue: [4, 6] },
            text: { backgroundColor: "#0d1622", color: "#e2e8f0", borderColor: "#334155" },
          },
        },
        xAxis: {
          axisLine: { color: "rgba(120,140,165,0.35)" },
          tickText: { color: "#94a3b8" },
          tickLine: { color: "rgba(120,140,165,0.35)" },
        },
        yAxis: {
          axisLine: { color: "rgba(120,140,165,0.35)" },
          tickText: { color: "#94a3b8" },
          tickLine: { color: "rgba(120,140,165,0.35)" },
        },
      },
    });
    if (!chart) return;
    chart.setStyles({ candle: { type: chartType } });
    chartRef.current = chart;

    return () => {
      dispose(container);
      chartRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Push data
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    chart.applyNewData(kline);
  }, [kline]);

  // Forecast band overlay (rectangle from forecast start to chart end)
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !forecastStartMs || forecast.length === 0) return;
    const last = forecast[forecast.length - 1];
    const lastMs = new Date(last.timestamp).getTime();
    const allUpper = forecast.map((f) => f.upper);
    const allLower = forecast.map((f) => f.lower);
    const top = Math.max(...allUpper);
    const bottom = Math.min(...allLower);
    const id = chart.createOverlay({
      name: "rectangle",
      lock: true,
      points: [
        { timestamp: forecastStartMs, value: top },
        { timestamp: lastMs, value: bottom },
      ],
      styles: {
        rectangle: {
          color: "rgba(94, 234, 212, 0.08)",
          borderColor: "rgba(94, 234, 212, 0.35)",
          borderSize: 1,
          borderStyle: "dashed",
        },
      },
    }) as string | null;
    return () => {
      if (id) chart.removeOverlay(id);
    };
  }, [forecastStartMs, forecast]);

  // Chart type toggle
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    chart.setStyles({ candle: { type: chartType } });
  }, [chartType]);

  // Crosshair → callback
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !onCrosshair) return;
    const handler = (data: unknown) => {
      const d = data as { kLineData?: KLineData } | null;
      if (!d || !d.kLineData) {
        onCrosshair(null);
        return;
      }
      const ts = d.kLineData.timestamp;
      onCrosshair({
        timestampMs: ts,
        price: d.kLineData.close,
        isForecast: forecastStartMs !== null && ts >= forecastStartMs,
      });
    };
    chart.subscribeAction(ActionType.OnCrosshairChange, handler);
    return () => chart.unsubscribeAction(ActionType.OnCrosshairChange, handler);
  }, [onCrosshair, forecastStartMs]);

  // Drawing tool activation
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !activeTool) return;
    const id = chart.createOverlay({ name: activeTool }) as string | null;
    if (id) {
      setOverlayIds((current) => [...current, id]);
    }
    setActiveTool("");
  }, [activeTool]);

  const handleClear = () => {
    const chart = chartRef.current;
    if (!chart) return;
    chart.removeOverlay();
    setOverlayIds([]);
  };

  const handleUndo = () => {
    const chart = chartRef.current;
    if (!chart || !overlayIds.length) return;
    const last = overlayIds[overlayIds.length - 1];
    chart.removeOverlay(last);
    setOverlayIds((current) => current.slice(0, -1));
  };

  return (
    <div className="rounded-2xl border border-seam bg-surface p-3">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="flex rounded-lg border border-seam bg-bg p-0.5">
          {([CandleType.Area, CandleType.CandleSolid, CandleType.Ohlc] as ChartType[]).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setChartType(t)}
              className={`rounded px-2.5 py-1 text-[11px] font-mono uppercase tracking-wider transition ${
                chartType === t ? "bg-ink/10 text-ink" : "text-ink/45 hover:text-ink/70"
              }`}
            >
              {t === CandleType.Area ? "Line" : t === CandleType.CandleSolid ? "Candle" : "OHLC"}
            </button>
          ))}
        </div>
        <div className="h-5 w-px bg-seam" />
        <div className="flex flex-wrap gap-1">
          {DRAW_TOOLS.filter((t) => t.value).map((t) => (
            <button
              key={t.value}
              type="button"
              title={t.tip}
              onClick={() => setActiveTool(t.value)}
              className="rounded border border-seam bg-bg px-2.5 py-1 text-[11px] text-ink/70 hover:border-seam-hi hover:text-ink"
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="ml-auto flex gap-1">
          <button
            type="button"
            onClick={handleUndo}
            className="rounded border border-seam bg-bg px-2.5 py-1 text-[11px] text-ink/60 hover:text-ink"
          >
            Undo
          </button>
          <button
            type="button"
            onClick={handleClear}
            className="rounded border border-seam bg-bg px-2.5 py-1 text-[11px] text-ink/60 hover:text-ink"
          >
            Clear
          </button>
        </div>
      </div>
      <div
        ref={containerRef}
        id={containerId}
        className="h-[560px] w-full overflow-hidden rounded-xl border border-seam bg-bg"
      />
      <p className="mt-2 px-1 text-[11px] text-ink/40">
        Scroll to zoom · drag axes to scale · click drawing tools then click two points · forecast band shaded ahead of last print.
      </p>
    </div>
  );
}
