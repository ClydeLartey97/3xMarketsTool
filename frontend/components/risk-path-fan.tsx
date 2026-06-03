"use client";

import { useEffect, useMemo, useState } from "react";

import { getRiskPaths, type RiskPathFanResponse } from "@/lib/api";
import { useNearViewport } from "@/lib/use-near-viewport";
import type { RiskAssessment } from "@/types/domain";

const WIDTH = 800;
const HEIGHT = 260;
const PAD_X = 24;
const PAD_Y = 18;

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

function hoverHourFromPointer(clientX: number, rect: DOMRect, horizonHours: number) {
  const viewBoxX = ((clientX - rect.left) / Math.max(rect.width, 1)) * WIDTH;
  const plotRatio = (viewBoxX - PAD_X) / Math.max(WIDTH - PAD_X * 2, 1);
  const clamped = Math.min(1, Math.max(0, plotRatio));
  return Math.round(clamped * horizonHours);
}

export function RiskPathFan({
  data,
  loading = false,
}: {
  data: RiskAssessment | null;
  loading?: boolean;
}) {
  const [fan, setFan] = useState<RiskPathFanResponse | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hoverHour, setHoverHour] = useState<number | null>(null);
  const { ref: viewportRef, visible } = useNearViewport<HTMLElement>();

  // Stable dedupe key per plan §3.4 — identical logical inputs must not
  // retrigger the heavy path-fan call. Falls back to nothing when there is
  // no risk read yet.
  const requestKey = data
    ? [
        data.market_code,
        data.position_gbp,
        data.direction,
        data.horizon_hours,
        data.target_timestamp ?? "",
        1500,
      ].join("|")
    : null;
  const [lastFetchedKey, setLastFetchedKey] = useState<string | null>(null);

  useEffect(() => {
    if (!data || loading) {
      setFan(null);
      setPending(false);
      setError(null);
      setLastFetchedKey(null);
      return;
    }
    // Plan §3.2: do not request /risk-assessment/paths until the section
    // is near the viewport. Once it loads, scrolling away does not wipe
    // it (the visible flag latches in useNearViewport).
    if (!visible) return;
    if (lastFetchedKey === requestKey) return;

    let cancelled = false;
    setPending(true);
    setError(null);
    getRiskPaths({
      market_code: data.market_code,
      position_gbp: data.position_gbp,
      horizon_hours: data.horizon_hours,
      direction: data.direction === "short" ? "short" : "long",
      target_timestamp: data.target_timestamp,
      n_paths: 1500,
      preview: true,
      scenarios: [],
    })
      .then((result) => {
        if (!cancelled) {
          setFan(result);
          setLastFetchedKey(requestKey);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setFan(null);
          setError(err instanceof Error ? err.message : "path fan failed");
        }
      })
      .finally(() => {
        if (!cancelled) setPending(false);
      });
    return () => {
      cancelled = true;
    };
  }, [data, loading, visible, requestKey, lastFetchedKey]);

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

  if (loading || pending) {
    return (
      <section
        ref={viewportRef as React.Ref<HTMLElement>}
        className="rounded-xl border border-white/10 bg-zinc-950/60 p-4 text-zinc-400"
      >
        Simulating path fan...
      </section>
    );
  }
  if (!data) {
    return (
      <section
        ref={viewportRef as React.Ref<HTMLElement>}
        className="rounded-xl border border-white/10 bg-zinc-950/60 p-4 text-zinc-500"
      >
        Run a risk assessment to see simulated paths.
      </section>
    );
  }
  if (error) {
    return (
      <section
        ref={viewportRef as React.Ref<HTMLElement>}
        className="rounded-xl border border-price-dn/25 bg-price-dn/10 p-4 text-sm text-price-dn"
      >
        Path fan unavailable: {error}
      </section>
    );
  }
  if (!fan || !chart) {
    // Section is mounted but not yet near viewport — keep a placeholder
    // so the IntersectionObserver has a DOM node to observe.
    return (
      <section
        ref={viewportRef as React.Ref<HTMLElement>}
        className="rounded-xl border border-white/10 bg-zinc-950/60 p-4 text-zinc-500"
        aria-label="Risk path fan"
      >
        Path fan will load when this section comes into view.
      </section>
    );
  }

  const hoverValues = hoverHour === null ? [] : fan.price_paths.map((path) => path[hoverHour]).filter(Number.isFinite);
  const hoverX = hoverHour === null ? null : chart.x(hoverHour);
  const references = [
    { label: "Risk", price: chart.referencePrices[0], className: "stroke-price-dn" },
    { label: "Likely", price: chart.referencePrices[1], className: "stroke-amber-300" },
    { label: "Upside", price: chart.referencePrices[2], className: "stroke-price-up" },
  ];

  return (
    <section
      ref={viewportRef as React.Ref<HTMLElement>}
      className="rounded-xl border border-white/10 bg-zinc-950/60 p-4"
      aria-label="Risk path fan"
    >
      <header className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-zinc-100">Path fan</h3>
          <p className="text-[11px] text-zinc-500">{fan.price_paths.length} sampled paths over {fan.horizon_hours}h</p>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-wider text-zinc-500">
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
            setHoverHour(hoverHourFromPointer(event.clientX, rect, fan.horizon_hours));
          }}
          onPointerLeave={() => setHoverHour(null)}
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
        {hoverHour !== null && hoverX !== null && hoverValues.length > 0 ? (
          <div
            className="pointer-events-none absolute top-3 rounded-lg border border-white/10 bg-black/80 px-3 py-2 font-mono text-[11px] text-zinc-100 shadow-lg"
            style={{
              left: `${(hoverX / WIDTH) * 100}%`,
              transform: hoverX > WIDTH * 0.72 ? "translateX(-100%)" : "translateX(12px)",
            }}
          >
            <p>h+{hoverHour}</p>
            <p>p10 {formatPrice(percentile(hoverValues, 10), data.price_currency)}</p>
            <p>p50 {formatPrice(percentile(hoverValues, 50), data.price_currency)}</p>
            <p>p90 {formatPrice(percentile(hoverValues, 90), data.price_currency)}</p>
          </div>
        ) : null}
      </div>
    </section>
  );
}
