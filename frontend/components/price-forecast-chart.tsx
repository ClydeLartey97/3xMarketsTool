"use client";

import {
  Area,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { PointerEvent as ReactPointerEvent, useEffect, useMemo, useRef, useState } from "react";

type ChartPoint = {
  timestamp: string;
  label?: string;
  actual?: number;
  forecast?: number;
  lower?: number;
  upper?: number;
  confidenceRatio?: number;
};

type EnrichedChartPoint = ChartPoint & {
  timestampMs: number;
};

type PlotBounds = {
  left: number;
  top: number;
  width: number;
  height: number;
};

type DrawingTool = "cursor" | "trendline" | "level" | "range";

type NormalizedPoint = {
  x: number;
  y: number;
};

type TrendlineDrawing = {
  id: number;
  type: "trendline";
  start: NormalizedPoint;
  end: NormalizedPoint;
};

type LevelDrawing = {
  id: number;
  type: "level";
  y: number;
};

type RangeDrawing = {
  id: number;
  type: "range";
  start: NormalizedPoint;
  end: NormalizedPoint;
};

type Drawing = TrendlineDrawing | LevelDrawing | RangeDrawing;

const TOOL_OPTIONS: Array<{ label: string; value: DrawingTool }> = [
  { label: "Cursor", value: "cursor" },
  { label: "Trend line", value: "trendline" },
  { label: "Level", value: "level" },
  { label: "Range box", value: "range" },
];

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function formatTime(timestampMs: number) {
  return new Date(timestampMs).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
  });
}

function DrawingOverlay({
  bounds,
  drawings,
  draft,
}: {
  bounds: PlotBounds;
  drawings: Drawing[];
  draft: Drawing | null;
}) {
  const renderDrawing = (drawing: Drawing, isDraft = false) => {
    const stroke = drawing.type === "range" ? "#d07a1c" : drawing.type === "level" ? "#8a3ffc" : "#138d67";
    const opacity = isDraft ? 0.7 : 1;
    if (drawing.type === "level") {
      const y = bounds.top + drawing.y * bounds.height;
      return (
        <line
          key={`${drawing.id}-${isDraft ? "draft" : "solid"}`}
          x1={bounds.left}
          x2={bounds.left + bounds.width}
          y1={y}
          y2={y}
          stroke={stroke}
          strokeDasharray="8 6"
          strokeWidth={2}
          opacity={opacity}
        />
      );
    }

    const x1 = bounds.left + drawing.start.x * bounds.width;
    const y1 = bounds.top + drawing.start.y * bounds.height;
    const x2 = bounds.left + drawing.end.x * bounds.width;
    const y2 = bounds.top + drawing.end.y * bounds.height;

    if (drawing.type === "trendline") {
      return (
        <g key={`${drawing.id}-${isDraft ? "draft" : "solid"}`} opacity={opacity}>
          <line x1={x1} x2={x2} y1={y1} y2={y2} stroke={stroke} strokeWidth={2.4} />
          <circle cx={x1} cy={y1} r={3.2} fill={stroke} />
          <circle cx={x2} cy={y2} r={3.2} fill={stroke} />
        </g>
      );
    }

    return (
      <g key={`${drawing.id}-${isDraft ? "draft" : "solid"}`} opacity={opacity}>
        <rect
          x={Math.min(x1, x2)}
          y={Math.min(y1, y2)}
          width={Math.max(Math.abs(x2 - x1), 3)}
          height={Math.max(Math.abs(y2 - y1), 3)}
          fill="#f7b267"
          fillOpacity={0.12}
          stroke={stroke}
          strokeWidth={2}
          rx={8}
        />
      </g>
    );
  };

  return (
    <svg className="pointer-events-none absolute inset-0 z-20 h-full w-full">
      {drawings.map((drawing) => renderDrawing(drawing))}
      {draft ? renderDrawing(draft, true) : null}
    </svg>
  );
}

export function PriceForecastChart({
  history,
  forecast,
  evidenceScore,
}: {
  history: ChartPoint[];
  forecast: ChartPoint[];
  evidenceScore?: number;
}) {
  const chartRef = useRef<HTMLDivElement | null>(null);
  const nextDrawingId = useRef(1);
  const [tool, setTool] = useState<DrawingTool>("cursor");
  const [drawings, setDrawings] = useState<Drawing[]>([]);
  const [draft, setDraft] = useState<Drawing | null>(null);
  const [bounds, setBounds] = useState<PlotBounds>({
    left: 72,
    top: 22,
    width: 400,
    height: 300,
  });

  const historyData = useMemo<EnrichedChartPoint[]>(
    () =>
      history.map((point) => ({
        ...point,
        timestampMs: new Date(point.timestamp).getTime(),
      })),
    [history],
  );

  const forecastData = useMemo<EnrichedChartPoint[]>(
    () =>
      forecast.map((point) => ({
        ...point,
        timestampMs: new Date(point.timestamp).getTime(),
      })),
    [forecast],
  );

  const combinedData = useMemo(
    () =>
      [...historyData, ...forecastData]
        .sort((a, b) => a.timestampMs - b.timestampMs)
        .map((point) => ({ ...point, label: point.label ?? formatTime(point.timestampMs) })),
    [forecastData, historyData],
  );

  const bandData = useMemo(
    () =>
      forecastData.map((point) => ({
        timestampMs: point.timestampMs,
        lower: point.lower,
        band: (point.upper ?? 0) - (point.lower ?? 0),
      })),
    [forecastData],
  );

  const yDomain = useMemo(() => {
    const values = combinedData.flatMap((point) => [point.actual, point.forecast, point.lower, point.upper]).filter(
      (value): value is number => typeof value === "number",
    );
    if (!values.length) {
      return [0, 100];
    }
    const min = Math.min(...values);
    const max = Math.max(...values);
    const padding = Math.max(6, (max - min) * 0.14);
    return [Math.floor(min - padding), Math.ceil(max + padding)];
  }, [combinedData]);

  const splitTimestamp = forecastData[0]?.timestampMs;
  const confidenceSignal = evidenceScore ?? 0.5;
  const greenStop = `${Math.round(12 + confidenceSignal * 32)}%`;
  const amberStop = `${Math.round(36 + confidenceSignal * 34)}%`;
  const riskLabel =
    confidenceSignal >= 0.72 ? "Evidence stack is deep, so confidence decays more slowly." : confidenceSignal >= 0.45
      ? "Confidence decays at a moderate pace because evidence is mixed."
      : "Thin evidence stack forces the curve into higher caution quickly.";

  useEffect(() => {
    if (!chartRef.current) {
      return;
    }

    const updateBounds = () => {
      if (!chartRef.current) {
        return;
      }
      const rect = chartRef.current.getBoundingClientRect();
      setBounds({
        left: 72,
        top: 22,
        width: Math.max(rect.width - 96, 120),
        height: Math.max(rect.height - 74, 120),
      });
    };

    updateBounds();

    const observer = new ResizeObserver(updateBounds);
    observer.observe(chartRef.current);
    return () => observer.disconnect();
  }, []);

  const toNormalizedPoint = (clientX: number, clientY: number): NormalizedPoint | null => {
    if (!chartRef.current) {
      return null;
    }
    const rect = chartRef.current.getBoundingClientRect();
    const x = clamp(clientX - rect.left, bounds.left, bounds.left + bounds.width);
    const y = clamp(clientY - rect.top, bounds.top, bounds.top + bounds.height);
    return {
      x: (x - bounds.left) / bounds.width,
      y: (y - bounds.top) / bounds.height,
    };
  };

  const handlePointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (tool === "cursor") {
      return;
    }
    const point = toNormalizedPoint(event.clientX, event.clientY);
    if (!point) {
      return;
    }

    if (tool === "level") {
      setDrawings((current) => [
        ...current,
        {
          id: nextDrawingId.current++,
          type: "level",
          y: point.y,
        },
      ]);
      return;
    }

    const id = nextDrawingId.current++;
    const nextDraft: Drawing =
      tool === "trendline"
        ? { id, type: "trendline", start: point, end: point }
        : { id, type: "range", start: point, end: point };
    setDraft(nextDraft);
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const handlePointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!draft) {
      return;
    }
    const point = toNormalizedPoint(event.clientX, event.clientY);
    if (!point) {
      return;
    }
    setDraft({ ...draft, end: point } as Drawing);
  };

  const handlePointerUp = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!draft) {
      return;
    }
    const nextDraft = draft;
    setDraft(null);
    setDrawings((current) => [...current, nextDraft]);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          {TOOL_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => setTool(option.value)}
              className={`rounded-full px-4 py-2 text-sm transition ${
                tool === option.value
                  ? "bg-slate text-white shadow-sm"
                  : "border border-slate/10 bg-[#f5f8fb] text-slate/72 hover:bg-white"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setDrawings((current) => current.slice(0, -1))}
            className="rounded-full border border-slate/10 bg-[#f5f8fb] px-4 py-2 text-sm text-slate/72 transition hover:bg-white"
          >
            Undo
          </button>
          <button
            type="button"
            onClick={() => {
              setDrawings([]);
              setDraft(null);
            }}
            className="rounded-full border border-slate/10 bg-[#f5f8fb] px-4 py-2 text-sm text-slate/72 transition hover:bg-white"
          >
            Clear
          </button>
          <div className="rounded-full border border-[#f0d6b4] bg-[#fff8ef] px-4 py-2 text-sm text-[#9a6217]">
            Desk tools beta
          </div>
          <div className="rounded-full border border-slate/10 bg-[#f5f8fb] px-4 py-2 text-sm text-slate/66">
            {riskLabel}
          </div>
        </div>
      </div>

      <div
        ref={chartRef}
        className="relative h-[460px] overflow-hidden rounded-[1.6rem] border border-[#d9e5ec] bg-[radial-gradient(circle_at_top,_rgba(226,238,247,0.72),_transparent_50%),linear-gradient(180deg,_rgba(249,252,254,0.98)_0%,_rgba(240,246,250,0.92)_100%)]"
      >
        <div
          className={`absolute inset-0 z-10 ${tool === "cursor" ? "pointer-events-none" : "pointer-events-auto"}`}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
        />
        <DrawingOverlay bounds={bounds} drawings={drawings} draft={draft} />
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={combinedData} margin={{ top: 22, right: 24, left: 8, bottom: 32 }}>
            <defs>
              <linearGradient id="band" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor="#17a57a" stopOpacity={0.18} />
                <stop offset="55%" stopColor="#d78a22" stopOpacity={0.14} />
                <stop offset="100%" stopColor="#cf4339" stopOpacity={0.1} />
              </linearGradient>
              <linearGradient id="forecastLine" x1="0%" x2="100%" y1="0%" y2="0%">
                <stop offset="0%" stopColor="#119d76" />
                <stop offset={greenStop} stopColor="#119d76" />
                <stop offset={amberStop} stopColor="#d07a1c" />
                <stop offset="100%" stopColor="#cf4339" />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="timestampMs"
              domain={["dataMin", "dataMax"]}
              minTickGap={22}
              tick={{ fill: "#415466", fontSize: 11 }}
              tickFormatter={(value) => formatTime(Number(value))}
              type="number"
            />
            <YAxis domain={yDomain} tick={{ fill: "#415466", fontSize: 11 }} width={64} />
            <Tooltip
              content={({ active, payload, label }) => {
                if (!active || !payload?.length || typeof label !== "number") {
                  return null;
                }
                const actual = payload.find((entry) => entry.dataKey === "actual")?.value;
                const projected = payload.find((entry) => entry.dataKey === "forecast")?.value;
                const lower = payload.find((entry) => entry.dataKey === "lower")?.value;
                const upper = payload.find((entry) => entry.dataKey === "band")
                  ? Number(lower) + Number(payload.find((entry) => entry.dataKey === "band")?.value ?? 0)
                  : undefined;

                return (
                  <div className="min-w-[210px] rounded-2xl border border-slate/10 bg-white/96 p-4 shadow-lg">
                    <p className="text-sm font-semibold text-slate">{formatTime(label)}</p>
                    {typeof actual === "number" ? (
                      <p className="mt-3 text-sm text-slate/78">Actual price: ${actual.toFixed(2)}</p>
                    ) : null}
                    {typeof projected === "number" ? (
                      <p className="mt-2 text-sm text-slate/78">Forecast: ${projected.toFixed(2)}</p>
                    ) : null}
                    {typeof lower === "number" && typeof upper === "number" ? (
                      <p className="mt-2 text-sm text-slate/68">
                        Confidence band: ${Number(lower).toFixed(2)}-${Number(upper).toFixed(2)}
                      </p>
                    ) : null}
                  </div>
                );
              }}
            />
            {splitTimestamp ? <ReferenceLine x={splitTimestamp} stroke="#b4c0cb" strokeDasharray="5 5" /> : null}
            <Area
              data={bandData}
              type="monotone"
              dataKey="lower"
              stackId="confidence"
              stroke="transparent"
              fill="transparent"
              isAnimationActive={false}
            />
            <Area
              data={bandData}
              type="monotone"
              dataKey="band"
              stackId="confidence"
              stroke="transparent"
              fill="url(#band)"
              isAnimationActive={false}
              name="Confidence band"
            />
            <Line
              type="monotone"
              dataKey="actual"
              stroke="#0c1724"
              strokeWidth={2.25}
              dot={false}
              connectNulls={false}
              isAnimationActive={false}
              name="Actual price"
            />
            <Line
              type="monotone"
              dataKey="forecast"
              stroke="url(#forecastLine)"
              strokeWidth={3.35}
              dot={false}
              connectNulls={false}
              isAnimationActive={false}
              name="Forecast curve"
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
