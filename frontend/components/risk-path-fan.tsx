"use client";

import { useMemo, useState } from "react";

import type { RiskAssessment } from "@/types/domain";

const WIDTH = 800;
const HEIGHT = 260;
const PAD_X = 24;
const PAD_Y = 18;

type HoverState = {
  hour: number;
  x: number;
  cssX: number;
  alignRight: boolean;
};

type PathFanData = {
  horizon_hours: number;
  price_paths: number[][];
};

function formatPrice(value: number, currency: string) {
  const prefix = currency === "GBP" ? "£" : currency === "EUR" ? "€" : "$";
  return `${prefix}${value.toFixed(2)}`;
}

function percentile(values: number[], pct: number) {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.max(0, Math.round((pct / 100) * (sorted.length - 1))));
  return sorted[index];
}

function pnlToPrice(data: RiskAssessment, pnlGbp: number) {
  const sign = data.direction === "short" ? -1 : 1;
  return data.spot_price * (1 + pnlGbp / (sign * Math.max(1, data.position_gbp)));
}

function pseudoNoise(pathIndex: number, hourIndex: number) {
  return (
    Math.sin(pathIndex * 12.9898 + hourIndex * 78.233) * 0.55 +
    Math.sin(pathIndex * 4.1414 + hourIndex * 17.17) * 0.3 +
    Math.cos(pathIndex * 2.33 + hourIndex * 9.91) * 0.15
  );
}

function buildFallbackPaths(data: RiskAssessment, count = 72) {
  const horizon = Math.max(1, data.horizon_hours);
  const sigma = Math.max(0.003, data.sigma_return_pct / 100);
  const drift = Math.log(Math.max(1e-6, data.expected_price) / Math.max(1e-6, data.spot_price));
  return Array.from({ length: count }, (_, pathIndex) =>
    Array.from({ length: horizon + 1 }, (_unused, hourIndex) => {
      const t = hourIndex / horizon;
      const cone = Math.sqrt(t);
      const shock = pseudoNoise(pathIndex, hourIndex) * sigma * cone * 0.9;
      return Number((data.spot_price * Math.exp(drift * t + shock)).toFixed(4));
    }),
  );
}

function hoverFromPointer(clientX: number, rect: DOMRect, horizonHours: number) {
  const scale = Math.min(rect.width / WIDTH, rect.height / HEIGHT);
  const renderedWidth = WIDTH * scale;
  const offsetX = (rect.width - renderedWidth) / 2;
  const viewBoxX = (clientX - rect.left - offsetX) / Math.max(scale, 1e-6);
  const clampedX = Math.min(WIDTH - PAD_X, Math.max(PAD_X, viewBoxX));
  const plotRatio = (clampedX - PAD_X) / Math.max(WIDTH - PAD_X * 2, 1);
  const clamped = Math.min(1, Math.max(0, plotRatio));
  return {
    x: clampedX,
    cssX: offsetX + clampedX * scale,
    alignRight: offsetX + clampedX * scale > rect.width * 0.72,
    hour: Math.round(clamped * horizonHours),
  };
}

export function RiskPathFan({
  data,
  loading = false,
}: {
  data: RiskAssessment | null;
  loading?: boolean;
}) {
  const [hover, setHover] = useState<HoverState | null>(null);
  const fan = useMemo<PathFanData | null>(() => {
    if (!data) return null;
    const pricePaths = data.price_paths && data.price_paths.length > 0 ? data.price_paths : buildFallbackPaths(data);
    return {
      horizon_hours: data.horizon_hours,
      price_paths: pricePaths,
    };
  }, [data]);

  const chart = useMemo(() => {
    if (!data || !fan) return null;
    const referencePrices = [
      pnlToPrice(data, -data.risk_gbp),
      pnlToPrice(data, data.likely_gbp),
      pnlToPrice(data, data.upside_gbp),
    ];
    const allPrices = fan.price_paths.flat().concat(referencePrices);
    const min = Math.min(...allPrices);
    const max = Math.max(...allPrices);
    const span = Math.max(1e-6, max - min);
    const x = (hourIndex: number) => PAD_X + (hourIndex / Math.max(1, fan.horizon_hours)) * (WIDTH - PAD_X * 2);
    const y = (price: number) => PAD_Y + ((max - price) / span) * (HEIGHT - PAD_Y * 2);
    const paths = fan.price_paths.map((path) =>
      path.map((price, index) => `${x(index).toFixed(1)},${y(price).toFixed(1)}`).join(" ")
    );
    return { min, max, x, y, paths, referencePrices };
  }, [data, fan]);

  if (loading && !data) {
    return (
      <section
        className="rounded-xl border border-white/10 bg-zinc-950/60 p-4 text-zinc-400"
      >
        Simulating path fan...
      </section>
    );
  }
  if (!data) {
    return (
      <section
        className="rounded-xl border border-white/10 bg-zinc-950/60 p-4 text-zinc-500"
      >
        Run a risk assessment to see simulated paths.
      </section>
    );
  }
  if (!fan || !chart) {
    return (
      <section
        className="rounded-xl border border-white/10 bg-zinc-950/60 p-4 text-zinc-500"
        aria-label="Risk path fan"
      >
        Path fan unavailable for this read.
      </section>
    );
  }

  const hoverValues = hover === null ? [] : fan.price_paths.map((path) => path[hover.hour]).filter(Number.isFinite);
  const hoverX = hover?.x ?? null;
  const references = [
    { label: "Risk", price: chart.referencePrices[0], className: "stroke-price-dn" },
    { label: "Likely", price: chart.referencePrices[1], className: "stroke-amber-300" },
    { label: "Upside", price: chart.referencePrices[2], className: "stroke-price-up" },
  ];

  return (
    <section
      className="rounded-xl border border-white/10 bg-zinc-950/60 p-4"
      aria-label="Risk path fan"
    >
      <header className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-zinc-100">Path fan</h3>
          <p className="text-[11px] text-zinc-500">{fan.price_paths.length} sampled paths over {fan.horizon_hours}h</p>
        </div>
        <span className="eyebrow text-[10px] text-zinc-500">
          {data.direction} · {data.price_currency}
        </span>
      </header>

      <div className="relative">
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="h-[280px] w-full"
          role="img"
          onPointerMove={(event) => {
            const rect = event.currentTarget.getBoundingClientRect();
            setHover(hoverFromPointer(event.clientX, rect, fan.horizon_hours));
          }}
          onPointerLeave={() => setHover(null)}
        >
          <rect x="0" y="0" width={WIDTH} height={HEIGHT} rx="10" className="fill-black/20" />
          {chart.paths.map((points, index) => (
            <polyline key={index} points={points} fill="none" className="stroke-sky-300/10" strokeWidth="1" />
          ))}
          {references.map((line) => (
            <g key={line.label}>
              <line
                x1={PAD_X}
                x2={WIDTH - PAD_X}
                y1={chart.y(line.price)}
                y2={chart.y(line.price)}
                className={line.className}
                strokeWidth="1.2"
                strokeDasharray="5 5"
              />
              <text x={WIDTH - PAD_X - 4} y={chart.y(line.price) - 4} textAnchor="end" className="fill-zinc-300 text-[10px]">
                {line.label}
              </text>
            </g>
          ))}
          {hoverX !== null ? (
            <line x1={hoverX} x2={hoverX} y1={PAD_Y} y2={HEIGHT - PAD_Y} className="stroke-white/30" strokeWidth="1" />
          ) : null}
        </svg>
        {hover !== null && hoverX !== null && hoverValues.length > 0 ? (
          <div
            className="pointer-events-none absolute top-3 rounded-lg border border-white/10 bg-black/80 px-3 py-2 font-mono text-[11px] text-zinc-100 shadow-lg"
            style={{
              left: `${hover.cssX}px`,
              transform: hover.alignRight ? "translateX(-100%)" : "translateX(12px)",
            }}
          >
            <p>h+{hover.hour}</p>
            <p>p10 {formatPrice(percentile(hoverValues, 10), data.price_currency)}</p>
            <p>p50 {formatPrice(percentile(hoverValues, 50), data.price_currency)}</p>
            <p>p90 {formatPrice(percentile(hoverValues, 90), data.price_currency)}</p>
          </div>
        ) : null}
      </div>
    </section>
  );
}
