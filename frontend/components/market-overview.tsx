import Link from "next/link";

import { DriverEvidence, DriverList } from "@/components/driver-list";
import { NewsBriefs } from "@/components/news-briefs";
import { SignalStack } from "@/components/signal-stack";
import { DashboardData, Market } from "@/types/domain";

function formatMarketTime(value: string, timeZone: string) {
  return new Intl.DateTimeFormat("en-US", {
    timeZone,
    month: "short",
    day: "numeric",
    hour: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function formatMoney(value: number | null | undefined) {
  return typeof value === "number" ? `$${value.toFixed(2)}` : "--";
}

function formatSigned(value: number | null | undefined) {
  if (typeof value !== "number") return "--";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}`;
}

function computeEvidenceScore(dashboard: DashboardData) {
  if (!dashboard.recent_news.length) return 18;
  const now = Date.now();
  const weighted = dashboard.recent_news.slice(0, 8).reduce((sum, item) => {
    const ageHours = (now - new Date(item.published_at).getTime()) / (1000 * 60 * 60);
    const freshness = Math.max(0.18, 1 - ageHours / 168);
    return sum + (item.credibility_rating / 100) * freshness;
  }, 0);
  return Math.round(Math.min(1, weighted / 4.8) * 100);
}

function buildDriverEvidence(dashboard: DashboardData): DriverEvidence[] {
  const directionalAccuracy = Math.round((dashboard.key_metrics.directional_accuracy ?? 0) * 100);
  const spikePrecision = Math.round((dashboard.key_metrics.spike_precision ?? 0) * 100);
  const newsDrivers = dashboard.recent_news.slice(0, 3).map((item, index) => ({
    id: `news-${item.id}`,
    title: index === 0 ? "Primary evidence" : index === 1 ? "Secondary evidence" : "Context evidence",
    body: item.display_summary,
    href: item.source_url,
    sourceName: item.source_name,
    sourceMeta: `${Math.round(item.credibility_rating)}/100 credibility`,
  }));

  return [
    {
      id: "rationale",
      title: "Model read",
      body: dashboard.latest_forecast?.rationale_summary ?? "Model rationale unavailable.",
      sourceMeta: `${directionalAccuracy}% directional · ${spikePrecision}% spike precision`,
    },
    ...newsDrivers,
  ];
}

type CurvePoint = {
  x: number;
  y: number;
  timestamp: string;
  label: string;
  actual?: number;
  forecast?: number;
  lower?: number;
  upper?: number;
};

type RawCurvePoint = {
  timestamp: string;
  label: string;
  actual?: number;
  forecast?: number;
  lower?: number;
  upper?: number;
};

function buildCurvePoints(dashboard: DashboardData) {
  const history = dashboard.recent_prices.slice(-28);
  const forecast = dashboard.forecasts.slice(0, 24);
  const lastObserved = history[history.length - 1];

  const combined: RawCurvePoint[] = [
    ...history.map((point) => ({
      timestamp: point.timestamp,
      actual: point.price_value,
      label: formatMarketTime(point.timestamp, dashboard.market.timezone),
    })),
    ...(lastObserved
      ? [{
          timestamp: lastObserved.timestamp,
          forecast: lastObserved.price_value,
          lower: lastObserved.price_value,
          upper: lastObserved.price_value,
          label: formatMarketTime(lastObserved.timestamp, dashboard.market.timezone),
        }]
      : []),
    ...forecast.map((point) => ({
      timestamp: point.forecast_for_timestamp,
      forecast: point.point_estimate,
      lower: point.lower_bound,
      upper: point.upper_bound,
      label: formatMarketTime(point.forecast_for_timestamp, dashboard.market.timezone),
    })),
  ];

  const unique = combined.filter(
    (point, index) => index === combined.findIndex((c) => c.timestamp === point.timestamp),
  );

  const values = unique
    .flatMap((p) => [p.actual, p.forecast, p.lower, p.upper])
    .filter((v): v is number => typeof v === "number");
  const min = Math.min(...values);
  const max = Math.max(...values);
  const padding = Math.max(8, (max - min) * 0.18);
  const domainMin = min - padding;
  const domainMax = max + padding;
  const W = 920, H = 280, L = 18, R = W - 22, T = 14, B = H - 26;
  const xStep = unique.length > 1 ? (R - L) / (unique.length - 1) : 0;

  const points: CurvePoint[] = unique.map((point, i) => {
    const value = point.actual ?? point.forecast ?? domainMin;
    const x = L + i * xStep;
    const y = B - ((value - domainMin) / (domainMax - domainMin || 1)) * (B - T);
    return { ...point, x, y };
  });

  const actualPts = points.filter((p) => typeof p.actual === "number");
  const forecastPts = points.filter((p) => typeof p.forecast === "number");
  const bandUpper = forecastPts
    .filter((p) => typeof p.upper === "number")
    .map((p) => `${p.x},${B - (((p.upper ?? domainMin) - domainMin) / (domainMax - domainMin || 1)) * (B - T)}`);
  const bandLower = [...forecastPts]
    .reverse()
    .filter((p) => typeof p.lower === "number")
    .map((p) => `${p.x},${B - (((p.lower ?? domainMin) - domainMin) / (domainMax - domainMin || 1)) * (B - T)}`);

  return {
    width: W,
    height: H,
    points,
    actualPath: actualPts.map((p) => `${p.x},${p.y}`).join(" "),
    forecastPath: forecastPts.map((p) => `${p.x},${p.y}`).join(" "),
    bandPath: [...bandUpper, ...bandLower].join(" "),
    domainMin,
    domainMax,
    lastObserved,
    firstForecast: forecast[0],
  };
}

function curveSourceLabel(market: Market) {
  const source = market.metadata?.curve_source as { label?: string } | undefined;
  return source?.label ?? "Official market source";
}

const REGION_FLAGS: Record<string, string> = {
  "Texas": "🇺🇸",
  "U.S. East Coast": "🇺🇸",
  "United Kingdom": "🇬🇧",
  "Germany": "🇩🇪",
  "France": "🇫🇷",
  "Nordics": "🇸🇪",
};

export function MarketOverview({
  markets,
  dashboard,
}: {
  markets: Market[];
  dashboard: DashboardData;
}) {
  const latestForecast = dashboard.forecasts[0] ?? dashboard.latest_forecast;
  const lastObserved = dashboard.recent_prices[dashboard.recent_prices.length - 1];
  const evidenceScore = computeEvidenceScore(dashboard);
  const curve = buildCurvePoints(dashboard);
  const frontGap =
    lastObserved && latestForecast ? latestForecast.point_estimate - lastObserved.price_value : null;
  const flag = REGION_FLAGS[dashboard.market.region] ?? "🌐";

  return (
    <main className="animate-fade-in space-y-4">

      {/* Header */}
      <div className="rounded-2xl border border-seam bg-surface p-5 shadow-panel">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="live-dot h-1.5 w-1.5 rounded-full bg-accent" />
              <span className="font-mono text-[10px] uppercase tracking-widest text-accent">Live</span>
              <span className="ml-1 font-mono text-[10px] uppercase tracking-widest text-ink/35">
                · {dashboard.market.timezone}
              </span>
            </div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-lg">{flag}</span>
              <span className="font-mono text-xs uppercase tracking-widest text-ink/35">
                {dashboard.market.code}
              </span>
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-ink">{dashboard.market.name}</h1>
            <p className="mt-1 text-xs text-ink/45">{dashboard.market.region} · {curveSourceLabel(dashboard.market)}</p>
          </div>

          {/* Market switcher */}
          <div className="flex flex-wrap gap-1.5">
            {markets.map((market) => (
              <Link
                key={market.code}
                href={`/markets/${market.code}`}
                className={`rounded-lg px-3 py-1.5 font-mono text-[11px] uppercase tracking-widest transition-all ${
                  market.code === dashboard.market.code
                    ? "border border-accent/35 bg-accent/10 text-accent"
                    : "border border-seam text-ink/42 hover:border-seam-hi hover:text-ink/72"
                }`}
              >
                {market.code}
              </Link>
            ))}
          </div>
        </div>

        {/* Metrics strip */}
        <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
          {[
            { label: "Spot", value: formatMoney(lastObserved?.price_value), color: "text-ink" },
            {
              label: "Next H forecast",
              value: formatMoney(latestForecast?.point_estimate),
              color: "text-price-up",
            },
            {
              label: "Gap",
              value: formatSigned(frontGap),
              color: typeof frontGap === "number" && frontGap >= 0 ? "text-price-hot" : "text-price-info",
            },
            {
              label: "Spike risk",
              value: `${Math.round((latestForecast?.spike_probability ?? 0) * 100)}%`,
              color:
                (latestForecast?.spike_probability ?? 0) > 0.4 ? "text-price-hot" : "text-ink",
            },
            { label: "Evidence score", value: `${evidenceScore}%`, color: "text-ink" },
            {
              label: "24h avg",
              value: formatMoney(dashboard.key_metrics.avg_price_24h),
              color: "text-ink/70",
            },
          ].map(({ label, value, color }) => (
            <div key={label} className="rounded-xl border border-seam bg-well p-3">
              <p className="mb-1.5 font-mono text-[9px] uppercase tracking-widest text-ink/30">{label}</p>
              <p className={`font-mono text-lg font-semibold tabular-nums ${color}`}>{value}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Forward curve */}
      <div className="rounded-2xl border border-seam bg-surface p-5 shadow-panel">
        <div className="flex items-center justify-between mb-4">
          <div>
            <p className="mb-1 font-mono text-[10px] uppercase tracking-widest text-ink/35">Forward Curve</p>
            <h2 className="text-lg font-semibold text-ink">Actual print path · 24h forecast strip</h2>
          </div>
          <div className="flex items-center gap-4 text-[11px] text-ink/35">
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-px w-5 bg-ink/60" />
              Observed
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-px w-5 bg-accent" />
              Forecast
            </span>
          </div>
        </div>

        <div className="rounded-xl border border-seam bg-well p-3">
          <svg viewBox={`0 0 ${curve.width} ${curve.height}`} className="w-full" style={{ height: "280px" }}>
            <defs>
              <linearGradient id="fg-gradient" x1="0%" x2="100%" y1="0%" y2="0%">
                <stop offset="0%" style={{ stopColor: "rgb(var(--accent))" }} />
                <stop offset="60%" style={{ stopColor: "rgb(var(--price-warn))" }} />
                <stop offset="100%" style={{ stopColor: "rgb(var(--price-dn))" }} />
              </linearGradient>
              <linearGradient id="band-fill" x1="0%" x2="0%" y1="0%" y2="100%">
                <stop offset="0%" style={{ stopColor: "rgb(var(--accent))", stopOpacity: 0.12 }} />
                <stop offset="100%" style={{ stopColor: "rgb(var(--accent))", stopOpacity: 0.03 }} />
              </linearGradient>
            </defs>

            {/* Grid lines */}
            {[0.2, 0.4, 0.6, 0.8].map((ratio) => (
              <line
                key={ratio}
                x1="18" x2="898"
                y1={14 + ratio * 240} y2={14 + ratio * 240}
                style={{ stroke: "var(--svg-grid)" }}
                strokeDasharray="4 8"
              />
            ))}

            {/* Confidence band */}
            {curve.bandPath ? (
              <polygon points={curve.bandPath} fill="url(#band-fill)" />
            ) : null}

            {/* Actual price line */}
            <polyline
              points={curve.actualPath}
              fill="none"
              style={{ stroke: "var(--svg-line)" }}
              strokeWidth="2"
              strokeLinejoin="round"
              strokeLinecap="round"
            />

            {/* Forecast line */}
            <polyline
              points={curve.forecastPath}
              fill="none"
              stroke="url(#fg-gradient)"
              strokeWidth="2.5"
              strokeLinejoin="round"
              strokeLinecap="round"
              strokeDasharray="6 3"
            />

            {/* Last observed dot */}
            {curve.lastObserved && curve.points.find((p) => p.timestamp === curve.lastObserved?.timestamp) && (() => {
              const pt = curve.points.find((p) => p.timestamp === curve.lastObserved?.timestamp)!;
              return <circle cx={pt.x} cy={pt.y} r="4" fill="rgb(var(--accent))" />;
            })()}
          </svg>
        </div>

        {/* Curve stats */}
        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {[
            {
              label: "Observed time",
              value: curve.lastObserved
                ? formatMarketTime(curve.lastObserved.timestamp, dashboard.market.timezone)
                : "--",
              color: "text-ink/72",
            },
            { label: "Observed price", value: formatMoney(curve.lastObserved?.price_value), color: "text-ink" },
            {
              label: "Front forecast",
              value: formatMoney(curve.firstForecast?.point_estimate),
              color: "text-price-up",
            },
            {
              label: "Confidence band",
              value: `${formatMoney(curve.firstForecast?.lower_bound)} – ${formatMoney(curve.firstForecast?.upper_bound)}`,
              color: "text-ink/55",
            },
          ].map(({ label, value, color }) => (
            <div key={label} className="rounded-lg border border-seam bg-well p-3">
              <p className="mb-1 font-mono text-[9px] uppercase tracking-widest text-ink/28">{label}</p>
              <p className={`font-mono text-sm font-medium tabular-nums ${color}`}>{value}</p>
            </div>
          ))}
        </div>
      </div>

      <SignalStack dashboard={dashboard} />

      <div className="grid items-start gap-4 xl:grid-cols-2">
        <DriverList compact drivers={buildDriverEvidence(dashboard)} />
        <NewsBriefs items={dashboard.recent_news.slice(0, 8)} />
      </div>
    </main>
  );
}
