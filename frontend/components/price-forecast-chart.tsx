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

type ChartPoint = {
  timestamp: string;
  actual?: number;
  forecast?: number;
  lower?: number;
  upper?: number;
  confidenceRatio?: number;
};

function buildSegments(forecast: ChartPoint[]) {
  const segmentCount = Math.min(6, Math.max(3, forecast.length));
  const colors = ["#14a17a", "#35a06f", "#7ea24e", "#c68c22", "#d56522", "#cf4339"];
  return Array.from({ length: segmentCount }, (_, segmentIndex) => {
    const start = Math.floor((segmentIndex * forecast.length) / segmentCount);
    const end = Math.floor(((segmentIndex + 1) * forecast.length) / segmentCount);
    const slice = forecast.slice(start, Math.max(end, start + 1));
    if (!slice.length) {
      return { key: `segment_${segmentIndex}`, color: colors[segmentIndex], data: [] as ChartPoint[] };
    }

    const points = segmentIndex === 0 ? slice : [forecast[start - 1], ...slice].filter(Boolean);
    return {
      key: `segment_${segmentIndex}`,
      color: colors[Math.min(segmentIndex, colors.length - 1)],
      data: points.map((point) => ({
        timestamp: point.timestamp,
        [`segment_${segmentIndex}`]: point.forecast,
      })),
    };
  });
}

export function PriceForecastChart({
  history,
  forecast,
}: {
  history: ChartPoint[];
  forecast: ChartPoint[];
}) {
  const bandData = forecast.map((point) => ({
    timestamp: point.timestamp,
    lower: point.lower,
    band: (point.upper ?? 0) - (point.lower ?? 0),
  }));
  const combinedData = [...history, ...forecast];
  const segments = buildSegments(forecast);
  const splitTimestamp = forecast[0]?.timestamp;

  return (
    <div className="h-[400px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={combinedData} margin={{ top: 10, right: 14, left: 0, bottom: 8 }}>
          <defs>
            <linearGradient id="band" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="#17a57a" stopOpacity={0.22} />
              <stop offset="45%" stopColor="#d78a22" stopOpacity={0.18} />
              <stop offset="100%" stopColor="#cf4339" stopOpacity={0.12} />
            </linearGradient>
          </defs>
          <XAxis dataKey="timestamp" minTickGap={20} tick={{ fill: "#415466", fontSize: 11 }} />
          <YAxis tick={{ fill: "#415466", fontSize: 11 }} width={64} />
          <Tooltip />
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
            strokeWidth={2.2}
            dot={false}
            connectNulls={false}
            isAnimationActive={false}
            name="Actual price"
          />
          {segments.map((segment, index) => (
            <Line
              key={segment.key}
              data={segment.data}
              type="monotone"
              dataKey={segment.key}
              stroke={segment.color}
              strokeWidth={index < 2 ? 3.1 : 2.7}
              dot={false}
              connectNulls
              isAnimationActive={false}
              name={index === 0 ? "Forecast confidence path" : undefined}
            />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
