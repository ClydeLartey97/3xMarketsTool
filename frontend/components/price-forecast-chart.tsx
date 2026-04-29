"use client";

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  PointerEvent as ReactPointerEvent,
  WheelEvent as ReactWheelEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

type ChartPoint = {
  timestamp: string;
  label?: string;
  actual?: number;
  forecast?: number;
  lower?: number;
  upper?: number;
};

type EnrichedChartPoint = ChartPoint & {
  timestampMs: number;
  isForecastAnchor?: boolean;
};

type PlotBounds = {
  left: number;
  top: number;
  width: number;
  height: number;
};

type HoverState = {
  x: number;
  y: number;
  point: EnrichedChartPoint;
};

type DrawingTool = "cursor" | "trendline" | "level" | "range";
type ChartMode = "curve" | "area" | "candles";

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

type CandlePoint = {
  timestampMs: number;
  open: number;
  high: number;
  low: number;
  close: number;
  isForecast: boolean;
};

const TOOL_OPTIONS: Array<{ label: string; value: DrawingTool }> = [
  { label: "Cursor", value: "cursor" },
  { label: "Trend line", value: "trendline" },
  { label: "Level", value: "level" },
  { label: "Range box", value: "range" },
];

const MODE_OPTIONS: Array<{ label: string; value: ChartMode }> = [
  { label: "Curve", value: "curve" },
  { label: "Area", value: "area" },
  { label: "Candles", value: "candles" },
];

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function formatTime(timestampMs: number, timeZone = "UTC") {
  return new Intl.DateTimeFormat("en-US", {
    timeZone,
    month: "short",
    day: "numeric",
    hour: "2-digit",
    hour12: false,
  }).format(new Date(timestampMs));
}

function formatAxisTime(timestampMs: number, timeZone = "UTC") {
  return new Intl.DateTimeFormat("en-US", {
    timeZone,
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(timestampMs));
}

function formatPrice(value: number) {
  const digits = Math.abs(value) >= 100 ? 0 : 2;
  return `$${value.toFixed(digits)}`;
}

function buildCandles(points: EnrichedChartPoint[]): CandlePoint[] {
  let previousClose = points[0]?.actual ?? points[0]?.forecast ?? 0;
  return points.map((point) => {
    const close = point.actual ?? point.forecast ?? previousClose;
    const open = previousClose;
    const spread = Math.max(Math.abs(close - open) * 0.35, 1.1);
    const high = point.upper ?? Math.max(open, close) + spread;
    const low = point.lower ?? Math.min(open, close) - spread;
    previousClose = close;
    return {
      timestampMs: point.timestampMs,
      open,
      high,
      low,
      close,
      isForecast: typeof point.forecast === "number" && typeof point.actual !== "number",
    };
  });
}

function CandlestickOverlay({
  bounds,
  candles,
  yDomain,
}: {
  bounds: PlotBounds;
  candles: CandlePoint[];
  yDomain: [number, number];
}) {
  if (!candles.length) {
    return null;
  }
  const minTs = candles[0].timestampMs;
  const maxTs = candles[candles.length - 1].timestampMs;
  const xSpan = Math.max(maxTs - minTs, 1);
  const ySpan = Math.max(yDomain[1] - yDomain[0], 1);
  const candleWidth = Math.max(5, Math.min(16, (bounds.width / Math.max(candles.length, 1)) * 0.55));
  const toX = (timestampMs: number) => bounds.left + ((timestampMs - minTs) / xSpan) * bounds.width;
  const toY = (value: number) => bounds.top + (1 - (value - yDomain[0]) / ySpan) * bounds.height;

  return (
    <svg className="pointer-events-none absolute inset-0 z-[12] h-full w-full">
      {candles.map((candle) => {
        const x = toX(candle.timestampMs);
        const openY = toY(candle.open);
        const closeY = toY(candle.close);
        const highY = toY(candle.high);
        const lowY = toY(candle.low);
        const top = Math.min(openY, closeY);
        const height = Math.max(Math.abs(closeY - openY), 2.5);
        const bullish = candle.close >= candle.open;
        const bodyFill = candle.isForecast ? (bullish ? "#75b69a" : "#e59a6c") : bullish ? "#14926d" : "#c94b42";
        const wickStroke = candle.isForecast ? "#7d8896" : "#1d2a38";

        return (
          <g key={`${candle.timestampMs}-${candle.open}-${candle.close}`} opacity={candle.isForecast ? 0.8 : 1}>
            <line x1={x} x2={x} y1={highY} y2={lowY} stroke={wickStroke} strokeWidth={1.4} />
            <rect
              x={x - candleWidth / 2}
              y={top}
              width={candleWidth}
              height={height}
              fill={bodyFill}
              stroke={wickStroke}
              strokeWidth={1}
              rx={3}
            />
          </g>
        );
      })}
    </svg>
  );
}

function CrosshairOverlay({
  bounds,
  hover,
  priceLabel,
  timeLabel,
}: {
  bounds: PlotBounds;
  hover: HoverState | null;
  priceLabel: string | null;
  timeLabel: string | null;
}) {
  if (!hover || !priceLabel || !timeLabel) {
    return null;
  }

  const x = clamp(hover.x, bounds.left, bounds.left + bounds.width);
  const y = clamp(hover.y, bounds.top, bounds.top + bounds.height);
  const timeWidth = 128;
  const timeHeight = 24;
  const priceWidth = 86;
  const priceHeight = 24;
  const timeX = clamp(x - timeWidth / 2, bounds.left, bounds.left + bounds.width - timeWidth);
  const priceY = clamp(y - priceHeight / 2, bounds.top, bounds.top + bounds.height - priceHeight);
  const priceX = bounds.left + bounds.width - priceWidth - 6;

  return (
    <svg className="pointer-events-none absolute inset-0 z-[18] h-full w-full">
      <line
        x1={x}
        x2={x}
        y1={bounds.top}
        y2={bounds.top + bounds.height}
        stroke="#6a89a3"
        strokeDasharray="4 6"
        strokeWidth={1.15}
        opacity={0.9}
      />
      <line
        x1={bounds.left}
        x2={bounds.left + bounds.width}
        y1={y}
        y2={y}
        stroke="#6a89a3"
        strokeDasharray="4 6"
        strokeWidth={1.15}
        opacity={0.9}
      />

      <rect x={timeX} y={bounds.top + bounds.height + 10} width={timeWidth} height={timeHeight} rx={8} fill="#0a1623" stroke="#294155" />
      <text
        x={timeX + timeWidth / 2}
        y={bounds.top + bounds.height + 26}
        fill="#dce9f7"
        fontSize="11"
        textAnchor="middle"
      >
        {timeLabel}
      </text>

      <rect x={priceX} y={priceY} width={priceWidth} height={priceHeight} rx={8} fill="#0a1623" stroke="#294155" />
      <text
        x={priceX + priceWidth / 2}
        y={priceY + 16}
        fill="#dce9f7"
        fontSize="11"
        textAnchor="middle"
      >
        {priceLabel}
      </text>
    </svg>
  );
}

function resolveActivePoint(
  activeLabel: string | number | undefined,
  visibleData: EnrichedChartPoint[],
): EnrichedChartPoint | null {
  if (typeof activeLabel !== "number") {
    return null;
  }
  return visibleData.find((point) => point.timestampMs === activeLabel) ?? null;
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

function NavigatorStrip({
  data,
  windowStart,
  windowEnd,
  onJumpToIndex,
  onMoveWindowToStart,
  timeZone,
}: {
  data: EnrichedChartPoint[];
  windowStart: number;
  windowEnd: number;
  onJumpToIndex: (index: number) => void;
  onMoveWindowToStart: (startIndex: number) => void;
  timeZone: string;
}) {
  const navigatorRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<{ pointerId: number; startClientX: number; startIndex: number } | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const viewWidth = 1000;
  const viewHeight = 92;
  const paddingX = 14;
  const paddingY = 12;
  const innerWidth = viewWidth - paddingX * 2;
  const innerHeight = viewHeight - paddingY * 2;
  const windowLength = windowEnd - windowStart + 1;
  const values = data.map((point) => point.actual ?? point.forecast ?? 0);
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 1);
  const span = Math.max(max - min, 1);
  const step = data.length > 1 ? innerWidth / (data.length - 1) : 0;

  const path = data
    .map((point, index) => {
      const value = point.actual ?? point.forecast ?? 0;
      const x = paddingX + index * step;
      const y = paddingY + innerHeight - ((value - min) / span) * innerHeight;
      return `${index === 0 ? "M" : "L"}${x} ${y}`;
    })
    .join(" ");

  const fillPath = path
    ? `${path} L${paddingX + (data.length - 1) * step} ${paddingY + innerHeight} L${paddingX} ${paddingY + innerHeight} Z`
    : "";

  const clampStartIndex = (startIndex: number) => {
    return clamp(startIndex, 0, Math.max(data.length - windowLength, 0));
  };

  const indexFromClientX = (clientX: number) => {
    if (!navigatorRef.current || data.length <= 1) {
      return 0;
    }
    const rect = navigatorRef.current.getBoundingClientRect();
    const ratio = clamp((clientX - rect.left) / Math.max(rect.width, 1), 0, 1);
    return Math.round(ratio * (data.length - 1));
  };

  const handleTrackPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!data.length) {
      return;
    }
    onJumpToIndex(indexFromClientX(event.clientX));
  };

  const handleViewportPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!data.length) {
      return;
    }
    event.stopPropagation();
    dragRef.current = {
      pointerId: event.pointerId,
      startClientX: event.clientX,
      startIndex: windowStart,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
    setIsDragging(true);
  };

  const handleViewportPointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!dragRef.current || !navigatorRef.current || data.length <= 1) {
      return;
    }
    const rect = navigatorRef.current.getBoundingClientRect();
    const deltaX = event.clientX - dragRef.current.startClientX;
    const pixelsPerPoint = rect.width / Math.max(data.length - 1, 1);
    const deltaIndex = Math.round(deltaX / Math.max(pixelsPerPoint, 1));
    onMoveWindowToStart(clampStartIndex(dragRef.current.startIndex + deltaIndex));
  };

  const handleViewportPointerUp = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (dragRef.current && event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    dragRef.current = null;
    setIsDragging(false);
  };

  if (!data.length) {
    return null;
  }

  const viewportLeftPercent = (windowStart / data.length) * 100;
  const viewportWidthPercent = Math.max((windowLength / data.length) * 100, 8);

  return (
    <div className="rounded-[1.2rem] border border-white/8 bg-[#09131d] px-3 py-3">
      <div className="mb-2 flex items-center justify-between text-[10px] uppercase tracking-[0.22em] text-white/34">
        <span>Navigator</span>
        <span>{formatTime(data[windowStart]?.timestampMs ?? data[0].timestampMs, timeZone)} - {formatTime(data[windowEnd]?.timestampMs ?? data[data.length - 1].timestampMs, timeZone)}</span>
      </div>
      <div
        ref={navigatorRef}
        className="relative h-[92px] cursor-pointer overflow-hidden rounded-[1rem] border border-white/8 bg-[linear-gradient(180deg,_rgba(8,17,27,0.94)_0%,_rgba(9,19,30,1)_100%)]"
        onPointerDown={handleTrackPointerDown}
      >
        <svg viewBox={`0 0 ${viewWidth} ${viewHeight}`} className="h-full w-full">
          <defs>
            <linearGradient id="navigatorFill" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="#2ecf9f" stopOpacity={0.26} />
              <stop offset="100%" stopColor="#2ecf9f" stopOpacity={0.04} />
            </linearGradient>
          </defs>
          <path d={fillPath} fill="url(#navigatorFill)" />
          <path d={path} fill="none" stroke="#6fd8b5" strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round" />
        </svg>
        <div
          className={`absolute inset-y-[6px] min-w-[28px] rounded-[10px] border border-[#7da9c7] bg-[rgba(124,173,212,0.14)] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.03)] ${
            isDragging ? "cursor-grabbing" : "cursor-grab"
          }`}
          style={{
            left: `${viewportLeftPercent}%`,
            width: `${viewportWidthPercent}%`,
          }}
          onPointerDown={handleViewportPointerDown}
          onPointerMove={handleViewportPointerMove}
          onPointerUp={handleViewportPointerUp}
        >
          <div className="absolute inset-y-[18px] left-2 w-[2px] rounded-full bg-[#9fc7e3]" />
          <div className="absolute inset-y-[18px] right-2 w-[2px] rounded-full bg-[#9fc7e3]" />
        </div>
      </div>
    </div>
  );
}

export function PriceForecastChart({
  history,
  forecast,
  evidenceScore,
  marketLabel,
  marketCode,
  timezoneLabel,
  directionalAccuracy,
  spikePrecision,
}: {
  history: ChartPoint[];
  forecast: ChartPoint[];
  evidenceScore?: number;
  marketLabel?: string;
  marketCode?: string;
  timezoneLabel?: string;
  directionalAccuracy?: number;
  spikePrecision?: number;
}) {
  const chartRef = useRef<HTMLDivElement | null>(null);
  const nextDrawingId = useRef(1);
  const [tool, setTool] = useState<DrawingTool>("cursor");
  const [chartMode, setChartMode] = useState<ChartMode>("candles");
  const [drawings, setDrawings] = useState<Drawing[]>([]);
  const [draft, setDraft] = useState<Drawing | null>(null);
  const [selectedPoint, setSelectedPoint] = useState<EnrichedChartPoint | null>(null);
  const [hoverState, setHoverState] = useState<HoverState | null>(null);
  const [bounds, setBounds] = useState<PlotBounds>({ left: 72, top: 22, width: 400, height: 300 });
  const [windowSize, setWindowSize] = useState(36);
  const [windowEnd, setWindowEnd] = useState(35);

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

  const combinedData = useMemo(() => {
    const merged = new Map<number, EnrichedChartPoint>();

    historyData.forEach((point) => {
      merged.set(point.timestampMs, { ...point, label: point.label ?? formatTime(point.timestampMs, timezoneLabel ?? "UTC") });
    });

    forecastData.forEach((point) => {
      const existing = merged.get(point.timestampMs);
      merged.set(point.timestampMs, {
        ...(existing ?? {
          timestamp: point.timestamp,
          timestampMs: point.timestampMs,
          label: point.label ?? formatTime(point.timestampMs, timezoneLabel ?? "UTC"),
        }),
        forecast: point.forecast,
        lower: point.lower,
        upper: point.upper,
      });
    });

    const lastHistoryPoint = historyData[historyData.length - 1];
    const firstForecastPoint = forecastData[0];
    if (
      lastHistoryPoint &&
      firstForecastPoint &&
      typeof lastHistoryPoint.actual === "number" &&
      lastHistoryPoint.timestampMs < firstForecastPoint.timestampMs
    ) {
      const existing = merged.get(lastHistoryPoint.timestampMs) ?? lastHistoryPoint;
      merged.set(lastHistoryPoint.timestampMs, {
        ...existing,
        label: existing.label ?? formatTime(lastHistoryPoint.timestampMs, timezoneLabel ?? "UTC"),
        forecast: lastHistoryPoint.actual,
        lower: lastHistoryPoint.actual,
        upper: lastHistoryPoint.actual,
        isForecastAnchor: true,
      });
    }

    return [...merged.values()].sort((a, b) => a.timestampMs - b.timestampMs);
  }, [forecastData, historyData, timezoneLabel]);

  useEffect(() => {
    if (!combinedData.length) {
      return;
    }
    const nextWindow = Math.min(Math.max(20, Math.min(42, combinedData.length)), combinedData.length);
    setWindowSize(nextWindow);
    setWindowEnd(combinedData.length - 1);
    setSelectedPoint(combinedData[combinedData.length - 1]);
  }, [combinedData]);

  const moveWindowToStart = (startIndex: number) => {
    const nextStart = clamp(startIndex, 0, Math.max(combinedData.length - windowSize, 0));
    setWindowEnd(nextStart + windowSize - 1);
  };

  const jumpWindowToIndex = (centerIndex: number) => {
    const nextStart = clamp(centerIndex - Math.floor(windowSize / 2), 0, Math.max(combinedData.length - windowSize, 0));
    setWindowEnd(nextStart + windowSize - 1);
  };

  const resizeWindow = (nextSize: number, anchorIndex = windowEnd) => {
    const clampedSize = clamp(nextSize, 12, Math.max(combinedData.length, 12));
    const nextStart = clamp(anchorIndex - Math.floor(clampedSize / 2), 0, Math.max(combinedData.length - clampedSize, 0));
    setWindowSize(Math.min(clampedSize, combinedData.length));
    setWindowEnd(Math.min(combinedData.length - 1, nextStart + Math.min(clampedSize, combinedData.length) - 1));
  };

  const visibleStart = Math.max(0, windowEnd - windowSize + 1);
  const visibleData = combinedData.slice(visibleStart, windowEnd + 1);
  const chartData = useMemo(
    () =>
      visibleData.map((point) => ({
        ...point,
        cursorValue:
          typeof point.actual === "number" && point.timestampMs < (forecastData[0]?.timestampMs ?? Number.POSITIVE_INFINITY)
            ? point.actual
            : point.forecast ?? point.actual,
      })),
    [forecastData, visibleData],
  );
  const visibleForecast = chartData.filter((point) => typeof point.forecast === "number");
  const visibleForwardOnly = visibleForecast.filter((point) => !point.isForecastAnchor);
  const bandData = visibleForecast.map((point) => ({
    timestampMs: point.timestampMs,
    lower: point.lower,
    band: (point.upper ?? 0) - (point.lower ?? 0),
  }));
  const candles = useMemo(() => buildCandles(chartData), [chartData]);
  const candleLookup = useMemo(() => new Map(candles.map((candle) => [candle.timestampMs, candle])), [candles]);

  const yDomain = useMemo<[number, number]>(() => {
    const values = chartData.flatMap((point) => [point.actual, point.forecast, point.lower, point.upper]).filter(
      (value): value is number => typeof value === "number",
    );
    if (!values.length) {
      return [0, 100];
    }
    const min = Math.min(...values);
    const max = Math.max(...values);
    const padding = Math.max(6, (max - min) * 0.18);
    return [Math.floor(min - padding), Math.ceil(max + padding)];
  }, [chartData]);

  const splitTimestamp = forecastData[0]?.timestampMs;
  const confidenceSignal = evidenceScore ?? 0.5;
  const greenStop = `${Math.round(10 + confidenceSignal * 28)}%`;
  const amberStop = `${Math.round(34 + confidenceSignal * 32)}%`;
  const zoomStep = Math.max(4, Math.floor(windowSize / 3));
  const latestObserved = [...chartData].reverse().find((point) => typeof point.actual === "number");
  const firstForward = visibleForwardOnly[0];
  const lastForward = visibleForwardOnly[visibleForwardOnly.length - 1];
  const fullRangeValues = chartData.flatMap((point) => [point.actual, point.forecast]).filter(
    (value): value is number => typeof value === "number",
  );
  const rangeLow = fullRangeValues.length ? Math.min(...fullRangeValues) : null;
  const rangeHigh = fullRangeValues.length ? Math.max(...fullRangeValues) : null;
  const frontBandWidth =
    typeof firstForward?.lower === "number" && typeof firstForward?.upper === "number"
      ? firstForward.upper - firstForward.lower
      : null;
  const forwardGap =
    typeof latestObserved?.actual === "number" && typeof firstForward?.forecast === "number"
      ? firstForward.forecast - latestObserved.actual
      : null;
  const evidencePercent = Math.round(confidenceSignal * 100);
  const inspectorPoint = selectedPoint ?? chartData[chartData.length - 1] ?? null;
  const livePoint = hoverState?.point ?? inspectorPoint;
  const liveCandle = livePoint ? candleLookup.get(livePoint.timestampMs) ?? null : null;
  const livePrice = livePoint ? livePoint.actual ?? livePoint.forecast ?? null : null;
  const crosshairTime = hoverState ? formatAxisTime(hoverState.point.timestampMs, timezoneLabel ?? "UTC") : null;
  const crosshairPrice = hoverState && typeof livePrice === "number" ? formatPrice(livePrice) : null;

  useEffect(() => {
    if (typeof ResizeObserver === "undefined" || !chartRef.current) {
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
        height: Math.max(rect.height - 106, 120),
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
    return { x: (x - bounds.left) / bounds.width, y: (y - bounds.top) / bounds.height };
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
      setDrawings((current) => [...current, { id: nextDrawingId.current++, type: "level", y: point.y }]);
      return;
    }

    const id = nextDrawingId.current++;
    setDraft(tool === "trendline" ? { id, type: "trendline", start: point, end: point } : { id, type: "range", start: point, end: point });
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
    setDrawings((current) => [...current, draft]);
    setDraft(null);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  };

  const handleWheel = (event: ReactWheelEvent<HTMLDivElement>) => {
    event.preventDefault();
    const anchorIndex = hoverState
      ? combinedData.findIndex((point) => point.timestampMs === hoverState.point.timestampMs)
      : windowEnd;
    const nextSize = event.deltaY < 0 ? Math.floor(windowSize * 0.82) : Math.ceil(windowSize * 1.18);
    resizeWindow(nextSize, anchorIndex >= 0 ? anchorIndex : windowEnd);
  };

  return (
    <section className="rounded-[2rem] border border-[#172938] bg-[radial-gradient(circle_at_top,_rgba(35,83,116,0.22),_transparent_24%),linear-gradient(180deg,_rgba(7,16,24,0.98)_0%,_rgba(10,20,31,0.98)_48%,_rgba(8,17,27,1)_100%)] p-4 text-white shadow-[0_28px_80px_rgba(6,14,24,0.42)] sm:p-5">
      <div className="flex flex-col gap-4 border-b border-white/8 pb-4">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <p className="text-[11px] uppercase tracking-[0.34em] text-white/38">Forward curve terminal</p>
            <div className="mt-3 flex flex-wrap items-end gap-x-4 gap-y-2">
              <h3 className="text-3xl font-semibold tracking-tight text-white">{marketLabel ?? "Selected market"}</h3>
              {marketCode ? <span className="rounded-full border border-white/10 px-3 py-1 text-xs uppercase tracking-[0.22em] text-white/54">{marketCode}</span> : null}
              {timezoneLabel ? <span className="text-sm text-white/46">{timezoneLabel}</span> : null}
            </div>
            <div className="mt-4 flex flex-wrap gap-3">
              <div className="rounded-2xl border border-[#1e3345] bg-[#0d1824] px-4 py-3">
                <p className="text-[10px] uppercase tracking-[0.24em] text-white/38">Last observed</p>
                <p className="mt-1 text-xl font-semibold tabular-nums text-[#d7e5ff]">
                  {typeof latestObserved?.actual === "number" ? `$${latestObserved.actual.toFixed(2)}` : "No print"}
                </p>
              </div>
              <div className="rounded-2xl border border-[#1e3345] bg-[#0d1824] px-4 py-3">
                <p className="text-[10px] uppercase tracking-[0.24em] text-white/38">Next forward</p>
                <p className="mt-1 text-xl font-semibold tabular-nums text-[#9ee2c6]">
                  {typeof firstForward?.forecast === "number" ? `$${firstForward.forecast.toFixed(2)}` : "N/A"}
                </p>
              </div>
              <div className="rounded-2xl border border-[#1e3345] bg-[#0d1824] px-4 py-3">
                <p className="text-[10px] uppercase tracking-[0.24em] text-white/38">Front gap</p>
                <p className={`mt-1 text-xl font-semibold tabular-nums ${typeof forwardGap === "number" && forwardGap >= 0 ? "text-[#f1c389]" : "text-[#9ac4ff]"}`}>
                  {typeof forwardGap === "number" ? `${forwardGap > 0 ? "+" : ""}${forwardGap.toFixed(2)}` : "N/A"}
                </p>
              </div>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-3 xl:min-w-[420px]">
            <div className="rounded-2xl border border-[#1e3345] bg-[#0c1621] px-4 py-3">
              <p className="text-[10px] uppercase tracking-[0.24em] text-white/38">Evidence score</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums text-white">{evidencePercent}%</p>
              <p className="mt-1 text-xs text-white/46">confidence fades faster when evidence is thin</p>
            </div>
            <div className="rounded-2xl border border-[#1e3345] bg-[#0c1621] px-4 py-3">
              <p className="text-[10px] uppercase tracking-[0.24em] text-white/38">Directional accuracy</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums text-white">{directionalAccuracy ?? "--"}%</p>
              <p className="mt-1 text-xs text-white/46">latest validation split</p>
            </div>
            <div className="rounded-2xl border border-[#1e3345] bg-[#0c1621] px-4 py-3">
              <p className="text-[10px] uppercase tracking-[0.24em] text-white/38">Spike precision</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums text-white">{spikePrecision ?? "--"}%</p>
              <p className="mt-1 text-xs text-white/46">front-strip abnormal-move detection</p>
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              {MODE_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setChartMode(option.value)}
                  className={`rounded-full border px-3 py-2 text-xs uppercase tracking-[0.18em] transition ${
                    chartMode === option.value
                      ? "border-[#1f3f57] bg-[#102638] text-white"
                      : "border-white/10 bg-white/5 text-white/56 hover:border-white/16 hover:bg-white/8 hover:text-white/78"
                  }`}
                >
                  {option.label}
                </button>
              ))}
              <div className="mx-1 hidden h-6 w-px bg-white/10 xl:block" />
              {TOOL_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setTool(option.value)}
                  className={`rounded-full border px-3 py-2 text-xs uppercase tracking-[0.18em] transition ${
                    tool === option.value
                      ? "border-[#33546c] bg-[#112333] text-white"
                      : "border-white/10 bg-white/5 text-white/56 hover:border-white/16 hover:bg-white/8 hover:text-white/78"
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <p className="text-[11px] text-white/38">
              Scroll to zoom. Click a point to pin the inspector. Drag inside the navigator to pan the window.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {[
              { label: "Zoom in", action: () => resizeWindow(Math.floor(windowSize * 0.72)) },
              { label: "Zoom out", action: () => resizeWindow(Math.ceil(windowSize * 1.35)) },
              { label: "Pan left", action: () => setWindowEnd((current) => Math.max(windowSize - 1, current - zoomStep)) },
              { label: "Pan right", action: () => setWindowEnd((current) => Math.min(combinedData.length - 1, current + zoomStep)) },
              {
                label: "Reset",
                action: () => {
                  const nextWindow = Math.min(Math.max(20, Math.min(42, combinedData.length)), combinedData.length);
                  setWindowSize(nextWindow);
                  setWindowEnd(combinedData.length - 1);
                  setSelectedPoint(combinedData[combinedData.length - 1] ?? null);
                },
              },
              { label: "Undo", action: () => setDrawings((current) => current.slice(0, -1)) },
              {
                label: "Clear",
                action: () => {
                  setDrawings([]);
                  setDraft(null);
                },
              },
            ].map((control) => (
              <button
                key={control.label}
                type="button"
                onClick={control.action}
                className="rounded-full border border-white/10 bg-white/5 px-3 py-2 text-xs uppercase tracking-[0.18em] text-white/60 transition hover:border-white/16 hover:bg-white/8 hover:text-white/82"
              >
                {control.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,_1fr)_260px]">
        <div className="space-y-4">
          <div
            ref={chartRef}
            className="relative h-[580px] overflow-hidden rounded-[1.65rem] border border-[#1f3446] bg-[linear-gradient(180deg,_rgba(9,18,28,0.96)_0%,_rgba(11,21,33,0.98)_42%,_rgba(8,16,25,1)_100%)]"
            onWheel={handleWheel}
          >
            <div className="pointer-events-none absolute inset-x-0 top-0 z-[2] h-28 bg-[linear-gradient(180deg,_rgba(74,139,193,0.08)_0%,_transparent_100%)]" />
            <div className="pointer-events-none absolute left-4 top-4 z-[16] flex flex-wrap items-center gap-x-4 gap-y-2 rounded-2xl border border-white/8 bg-[#09131d]/86 px-4 py-3 backdrop-blur">
              <div>
                <p className="text-[10px] uppercase tracking-[0.22em] text-white/35">Time</p>
                <p className="mt-1 text-sm font-semibold text-white">
                  {livePoint ? formatAxisTime(livePoint.timestampMs, timezoneLabel ?? "UTC") : "No selection"}
                </p>
              </div>
              {liveCandle ? (
                <>
                  <div>
                    <p className="text-[10px] uppercase tracking-[0.22em] text-white/35">Open</p>
                    <p className="mt-1 font-mono text-sm text-[#dce8ff]">{formatPrice(liveCandle.open)}</p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-[0.22em] text-white/35">High</p>
                    <p className="mt-1 font-mono text-sm text-[#f5d09f]">{formatPrice(liveCandle.high)}</p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-[0.22em] text-white/35">Low</p>
                    <p className="mt-1 font-mono text-sm text-[#8ac4ff]">{formatPrice(liveCandle.low)}</p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-[0.22em] text-white/35">Close</p>
                    <p className="mt-1 font-mono text-sm text-[#9ee2c6]">{formatPrice(liveCandle.close)}</p>
                  </div>
                </>
              ) : null}
              {typeof livePoint?.forecast === "number" ? (
                <div>
                  <p className="text-[10px] uppercase tracking-[0.22em] text-white/35">Forward</p>
                  <p className="mt-1 font-mono text-sm text-[#9ee2c6]">{formatPrice(livePoint.forecast)}</p>
                </div>
              ) : null}
            </div>
            <div
              className={`absolute inset-0 z-10 ${tool === "cursor" ? "pointer-events-none" : "pointer-events-auto"}`}
              onPointerDown={handlePointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerUp}
            />
            {chartMode === "candles" ? <CandlestickOverlay bounds={bounds} candles={candles} yDomain={yDomain} /> : null}
            <DrawingOverlay bounds={bounds} drawings={drawings} draft={draft} />
            <CrosshairOverlay bounds={bounds} hover={hoverState} priceLabel={crosshairPrice} timeLabel={crosshairTime} />
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart
                data={chartData}
                margin={{ top: 18, right: 18, left: 10, bottom: 48 }}
                onMouseMove={(state) => {
                  const point = resolveActivePoint(state?.activeLabel, chartData);
                  const activeX = state?.activeCoordinate?.x;
                  const activeY = state?.activeCoordinate?.y;
                  if (point && typeof activeX === "number" && typeof activeY === "number") {
                    setHoverState({
                      x: activeX,
                      y: activeY,
                      point,
                    });
                  } else {
                    setHoverState(null);
                  }
                }}
                onMouseLeave={() => setHoverState(null)}
                onClick={(state) => {
                  const point = resolveActivePoint(state?.activeLabel, chartData);
                  if (point) {
                    setSelectedPoint(point);
                  }
                }}
              >
                <defs>
                  <linearGradient id="band" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor="#3cbf9a" stopOpacity={0.22} />
                    <stop offset="60%" stopColor="#d47b20" stopOpacity={0.14} />
                    <stop offset="100%" stopColor="#d64f45" stopOpacity={0.08} />
                  </linearGradient>
                  <linearGradient id="forecastLine" x1="0%" x2="100%" y1="0%" y2="0%">
                    <stop offset="0%" stopColor="#16b788" />
                    <stop offset={greenStop} stopColor="#16b788" />
                    <stop offset={amberStop} stopColor="#d57d24" />
                    <stop offset="100%" stopColor="#db5648" />
                  </linearGradient>
                  <linearGradient id="forecastArea" x1="0%" x2="100%" y1="0%" y2="0%">
                    <stop offset="0%" stopColor="#1cc493" stopOpacity={0.2} />
                    <stop offset={greenStop} stopColor="#1cc493" stopOpacity={0.15} />
                    <stop offset={amberStop} stopColor="#d57d24" stopOpacity={0.11} />
                    <stop offset="100%" stopColor="#db5648" stopOpacity={0.1} />
                  </linearGradient>
                  <linearGradient id="actualLine" x1="0%" x2="0%" y1="0%" y2="100%">
                    <stop offset="0%" stopColor="#e8edf5" />
                    <stop offset="100%" stopColor="#bcc7d6" />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#203140" strokeDasharray="3 6" vertical={true} />
                <XAxis
                  dataKey="timestampMs"
                  domain={["dataMin", "dataMax"]}
                  interval="preserveStartEnd"
                  minTickGap={28}
                  tick={{ fill: "#8ea4b9", fontSize: 11 }}
                  tickFormatter={(value) => formatAxisTime(Number(value), timezoneLabel ?? "UTC")}
                  type="number"
                  axisLine={false}
                  tickLine={false}
                  tickMargin={12}
                />
                <YAxis
                  domain={yDomain}
                  tick={{ fill: "#8ea4b9", fontSize: 11 }}
                  tickFormatter={(value) => formatPrice(Number(value))}
                  tickCount={8}
                  width={78}
                  orientation="right"
                  axisLine={false}
                  tickLine={false}
                  tickMargin={10}
                />
                <Tooltip
                  cursor={false}
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
                    const candle = candleLookup.get(label);

                    return (
                      <div className="min-w-[230px] rounded-2xl border border-[#294155] bg-[#0b1621]/95 p-4 shadow-2xl backdrop-blur">
                        <p className="text-sm font-semibold text-white">{formatAxisTime(label, timezoneLabel ?? "UTC")}</p>
                        {candle ? (
                          <p className="mt-3 font-mono text-[11px] uppercase tracking-[0.18em] text-white/56">
                            O {formatPrice(candle.open)} · H {formatPrice(candle.high)} · L {formatPrice(candle.low)} · C {formatPrice(candle.close)}
                          </p>
                        ) : null}
                        {typeof actual === "number" ? <p className="mt-3 text-sm text-white/78">Actual: {formatPrice(Number(actual))}</p> : null}
                        {typeof projected === "number" ? <p className="mt-2 text-sm text-white/78">Forward: {formatPrice(Number(projected))}</p> : null}
                        {typeof lower === "number" && typeof upper === "number" ? (
                          <p className="mt-2 text-sm text-white/64">
                            Band: {formatPrice(Number(lower))}-{formatPrice(Number(upper))}
                          </p>
                        ) : null}
                        <p className="mt-3 text-[11px] uppercase tracking-[0.18em] text-white/38">Click to pin inspector</p>
                      </div>
                    );
                  }}
                />
                {splitTimestamp ? <ReferenceLine x={splitTimestamp} stroke="#41576b" strokeDasharray="5 5" /> : null}
                {typeof latestObserved?.actual === "number" ? (
                  <ReferenceLine y={latestObserved.actual} stroke="#314455" strokeDasharray="4 5" />
                ) : null}
                <Area data={bandData} type="monotone" dataKey="lower" stackId="confidence" stroke="transparent" fill="transparent" isAnimationActive={false} />
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
                {chartMode === "area" ? (
                  <Area
                    type="monotone"
                    dataKey="actual"
                    stroke="url(#actualLine)"
                    fill="#88aaf8"
                    fillOpacity={0.08}
                    strokeWidth={2.4}
                    isAnimationActive={false}
                    activeDot={false}
                    name="Actual price"
                  />
                ) : chartMode !== "candles" ? (
                  <Line
                    type="monotone"
                    dataKey="actual"
                    stroke="url(#actualLine)"
                    strokeWidth={2.35}
                    dot={false}
                    activeDot={false}
                    connectNulls={false}
                    isAnimationActive={false}
                    name="Actual price"
                  />
                ) : null}
                {chartMode === "area" ? (
                  <Area
                    type="monotone"
                    dataKey="forecast"
                    stroke="url(#forecastLine)"
                    fill="url(#forecastArea)"
                    strokeWidth={3.05}
                    dot={false}
                    activeDot={false}
                    connectNulls={false}
                    isAnimationActive={false}
                    name="Forward curve"
                  />
                ) : chartMode !== "candles" ? (
                  <Line
                    type={chartMode === "curve" ? "monotone" : "stepAfter"}
                    dataKey="forecast"
                    stroke="url(#forecastLine)"
                    strokeWidth={3.1}
                    dot={false}
                    activeDot={false}
                    connectNulls={false}
                    isAnimationActive={false}
                    name="Forward curve"
                  />
                ) : (
                  <Line
                    type="monotone"
                    dataKey="forecast"
                    stroke="url(#forecastLine)"
                    strokeWidth={2.2}
                    strokeDasharray="6 6"
                    dot={false}
                    activeDot={false}
                    connectNulls={false}
                    isAnimationActive={false}
                    name="Forward curve"
                  />
                )}
                <Line
                  type="monotone"
                  dataKey="cursorValue"
                  stroke="transparent"
                  strokeWidth={1}
                  dot={false}
                  connectNulls={true}
                  isAnimationActive={false}
                  legendType="none"
                  activeDot={{ r: 5, fill: "#f3f6fb", stroke: "#0b1621", strokeWidth: 2 }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          <NavigatorStrip
            data={combinedData}
            windowStart={visibleStart}
            windowEnd={windowEnd}
            onJumpToIndex={jumpWindowToIndex}
            onMoveWindowToStart={moveWindowToStart}
            timeZone={timezoneLabel ?? "UTC"}
          />

          {inspectorPoint ? (
            <div className="grid gap-3 md:grid-cols-4">
              <div className="rounded-[1.2rem] border border-white/8 bg-white/4 p-4">
                <p className="text-[10px] uppercase tracking-[0.2em] text-white/38">Pinned time</p>
                <p className="mt-2 text-base font-semibold text-white">{formatTime(inspectorPoint.timestampMs, timezoneLabel ?? "UTC")}</p>
              </div>
              <div className="rounded-[1.2rem] border border-white/8 bg-white/4 p-4">
                <p className="text-[10px] uppercase tracking-[0.2em] text-white/38">Observed</p>
                <p className="mt-2 text-base font-semibold tabular-nums text-[#d6e4ff]">
                  {typeof inspectorPoint.actual === "number" ? `$${inspectorPoint.actual.toFixed(2)}` : "No print"}
                </p>
              </div>
              <div className="rounded-[1.2rem] border border-white/8 bg-white/4 p-4">
                <p className="text-[10px] uppercase tracking-[0.2em] text-white/38">Forward</p>
                <p className="mt-2 text-base font-semibold tabular-nums text-[#a5e6ca]">
                  {typeof inspectorPoint.forecast === "number" ? `$${inspectorPoint.forecast.toFixed(2)}` : "N/A"}
                </p>
              </div>
              <div className="rounded-[1.2rem] border border-white/8 bg-white/4 p-4">
                <p className="text-[10px] uppercase tracking-[0.2em] text-white/38">Confidence band</p>
                <p className="mt-2 text-base font-semibold tabular-nums text-white">
                  {typeof inspectorPoint.lower === "number" && typeof inspectorPoint.upper === "number"
                    ? `$${inspectorPoint.lower.toFixed(2)}-$${inspectorPoint.upper.toFixed(2)}`
                    : "N/A"}
                </p>
              </div>
            </div>
          ) : null}
        </div>

        <aside className="rounded-[1.65rem] border border-[#1e3345] bg-[#0d1722] p-4">
          <p className="text-[11px] uppercase tracking-[0.28em] text-white/36">Readout</p>
          <div className="mt-4 space-y-3">
            <div className="rounded-2xl border border-white/8 bg-white/4 p-4">
              <p className="text-[10px] uppercase tracking-[0.2em] text-white/38">Session range</p>
              <p className="mt-2 text-xl font-semibold tabular-nums text-white">
                {typeof rangeLow === "number" && typeof rangeHigh === "number"
                  ? `$${rangeLow.toFixed(2)}-$${rangeHigh.toFixed(2)}`
                  : "N/A"}
              </p>
              <p className="mt-1 text-xs text-white/46">observed and forward values in the visible window</p>
            </div>
            <div className="rounded-2xl border border-white/8 bg-white/4 p-4">
              <p className="text-[10px] uppercase tracking-[0.2em] text-white/38">Front confidence width</p>
              <p className="mt-2 text-xl font-semibold tabular-nums text-white">
                {typeof frontBandWidth === "number" ? `$${frontBandWidth.toFixed(2)}` : "N/A"}
              </p>
              <p className="mt-1 text-xs text-white/46">spread between lower and upper front-strip estimates</p>
            </div>
            <div className="rounded-2xl border border-white/8 bg-white/4 p-4">
              <p className="text-[10px] uppercase tracking-[0.2em] text-white/38">Curve destination</p>
              <p className="mt-2 text-xl font-semibold tabular-nums text-white">
                {typeof lastForward?.forecast === "number" ? `$${lastForward.forecast.toFixed(2)}` : "N/A"}
              </p>
              <p className="mt-1 text-xs text-white/46">furthest visible forecast point in the selected window</p>
            </div>
          </div>

          <div className="mt-5 rounded-2xl border border-white/8 bg-white/4 p-4">
            <p className="text-[10px] uppercase tracking-[0.2em] text-white/38">Legend</p>
            <div className="mt-4 space-y-3 text-sm text-white/72">
              <div className="flex items-center gap-3">
                <span className="h-0.5 w-8 rounded-full bg-[#bcd3ff]" />
                <span>Actual print path</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="h-0.5 w-8 rounded-full bg-[linear-gradient(90deg,#16b788_0%,#d57d24_62%,#db5648_100%)]" />
                <span>Forward curve with evidence-sensitive decay</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="h-3 w-8 rounded-full bg-[#266f5b]/40 ring-1 ring-white/10" />
                <span>Confidence band</span>
              </div>
            </div>
          </div>
        </aside>
      </div>
    </section>
  );
}
