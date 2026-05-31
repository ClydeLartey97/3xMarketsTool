"use client";
/**
 * Market workbench — the single market page.
 *
 * Information hierarchy (top to bottom):
 *   1. Market identity (compact strip with selector + spot)
 *   2. HERO: trade input + three bubbles + sticky follow-down bar
 *   3. Decision gate strip
 *   4. Price chart
 *   5. Scenario cards
 *   6. Path fan
 *   7. Audit layer (decomposition + sensitivity ladder, side by side)
 *   8. News briefs
 *   9. Events timeline
 *  10. Decisions diary + positions blotter
 *  11. Calibration panel + signal stack
 *
 * The three numbers are the gravitational centre. Everything beneath
 * exists to explain or back them up.
 */
import dynamic from "next/dynamic";
import type { Route } from "next";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { getDashboard, getDashboardSummary, type DashboardSummary } from "@/lib/api";

import { ClientErrorBoundary } from "@/components/client-error-boundary";
import { DecisionGateStrip } from "@/components/decision-gate-strip";
import { MarketHero } from "@/components/market-hero";
import type { TradeInputState } from "@/components/trade-input-bar";
import { useMarketStream } from "@/lib/use-market-stream";
import { DashboardData, Market, RiskAssessment } from "@/types/domain";

/**
 * Below-the-fold panels are lazy-loaded so the hero (the three bubbles)
 * paints first and the heavier chart / audit / news / blotter chunks only
 * fetch their JS when the user actually scrolls toward them. Massively
 * shrinks the initial bundle on every page load.
 */
const PanelSkeleton = ({ height = 200 }: { height?: number }) => (
  <div
    className="animate-pulse rounded-2xl border border-seam bg-bg"
    style={{ height }}
  />
);

const ScenarioCards = dynamic(
  () => import("@/components/scenario-cards").then((m) => m.ScenarioCards),
  { ssr: false, loading: () => <PanelSkeleton height={140} /> },
);
const RiskPathFan = dynamic(
  () => import("@/components/risk-path-fan").then((m) => m.RiskPathFan),
  { ssr: false, loading: () => <PanelSkeleton height={260} /> },
);
const RiskDecompositionPanel = dynamic(
  () => import("@/components/risk-decomposition-panel").then((m) => m.RiskDecompositionPanel),
  { ssr: false, loading: () => <PanelSkeleton height={300} /> },
);
const RiskSensitivityLadder = dynamic(
  () => import("@/components/risk-sensitivity-ladder").then((m) => m.RiskSensitivityLadder),
  { ssr: false, loading: () => <PanelSkeleton height={300} /> },
);
const NewsBriefs = dynamic(
  () => import("@/components/news-briefs").then((m) => m.NewsBriefs),
  { ssr: false, loading: () => <PanelSkeleton height={200} /> },
);
const EventFeed = dynamic(
  () => import("@/components/event-feed").then((m) => m.EventFeed),
  { ssr: false, loading: () => <PanelSkeleton height={200} /> },
);
const PositionBlotter = dynamic(
  () => import("@/components/position-blotter").then((m) => m.PositionBlotter),
  { ssr: false, loading: () => <PanelSkeleton height={200} /> },
);
const DecisionDiary = dynamic(
  () => import("@/components/decision-diary").then((m) => m.DecisionDiary),
  { ssr: false, loading: () => <PanelSkeleton height={200} /> },
);
const CalibrationPanel = dynamic(
  () => import("@/components/calibration-panel").then((m) => m.CalibrationPanel),
  { ssr: false, loading: () => <PanelSkeleton height={200} /> },
);
const SignalStack = dynamic(
  () => import("@/components/signal-stack").then((m) => m.SignalStack),
  { ssr: false, loading: () => <PanelSkeleton height={200} /> },
);
const PowerBIReport = dynamic(
  () => import("@/components/power-bi-report").then((m) => m.PowerBIReport),
  { ssr: false, loading: () => <PanelSkeleton height={200} /> },
);

const KlinePriceChart = dynamic(
  () => import("@/components/kline-price-chart").then((m) => m.KlinePriceChart),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-[500px] items-center justify-center rounded-2xl border border-seam bg-surface text-sm text-ink/40">
        Loading chart…
      </div>
    ),
  },
);

type PriceSource = Pick<DashboardData, "recent_prices" | "forecasts">;

function buildHistory(source: PriceSource) {
  return source.recent_prices.map((p) => ({
    timestamp: p.timestamp,
    value: p.price_value,
  }));
}

function buildForecast(source: PriceSource) {
  return source.forecasts.map((f) => ({
    timestamp: f.forecast_for_timestamp,
    point: f.point_estimate,
    lower: f.lower_bound,
    upper: f.upper_bound,
  }));
}

export function MarketWorkbench({
  markets,
  market,
}: {
  markets: Market[];
  market: Market;
}) {
  const router = useRouter();
  const [cursorTs, setCursorTs] = useState<number | null>(null);
  const [risk, setRisk] = useState<RiskAssessment | null>(null);
  const [riskLoading, setRiskLoading] = useState(false);
  const [decisionRefresh] = useState(0);

  // Plan §5.4 — split the workbench load:
  //   1. `summary` (lightweight, no alert refresh, no news/events) lands
  //      first and feeds the chart + identity strip + hero context.
  //   2. `dashboard` (full canonical payload) lands next and fills in the
  //      news, events, and signal-stack panels.
  // Both run in parallel so first useful paint is bounded by the smaller
  // request, while no evidence panel is removed.
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  useEffect(() => {
    let cancelled = false;
    getDashboardSummary(market.code)
      .then((result) => {
        if (!cancelled) setSummary(result);
      })
      .catch(() => {
        if (!cancelled) setSummary(null);
      });
    getDashboard(market.code)
      .then((result) => {
        if (!cancelled) setDashboard(result);
      })
      .catch(() => {
        if (!cancelled) setDashboard(null);
      });
    return () => {
      cancelled = true;
    };
  }, [market.code]);

  // Prefer the full dashboard for chart data once it arrives so the
  // chart and news panels stay perfectly in sync; fall back to the
  // summary while the full dashboard is in flight.
  const chartSource: PriceSource | null = dashboard ?? summary;
  const history = useMemo(() => (chartSource ? buildHistory(chartSource) : []), [chartSource]);
  const forecast = useMemo(() => (chartSource ? buildForecast(chartSource) : []), [chartSource]);
  const stream = useMarketStream(market.code);
  const livePriceTick = stream.priceTick
    ? { timestamp: stream.priceTick.timestamp, value: stream.priceTick.price_value }
    : null;

  const lastObserved =
    chartSource?.recent_prices[chartSource.recent_prices.length - 1];
  const latestForecast =
    dashboard?.forecasts[0] ??
    dashboard?.latest_forecast ??
    summary?.forecasts[0] ??
    summary?.latest_forecast ??
    null;
  const front =
    lastObserved && latestForecast ? latestForecast.point_estimate - lastObserved.price_value : null;

  // Translate the three P&L numbers into price levels on the chart. Same
  // formula as `pnlToPrice` in risk-path-fan.tsx; kept inline so the chart
  // and the fan agree to the cent. For a short, gains come from a falling
  // price, so the sign flips through the position-sign denominator.
  const riskOverlay = useMemo(() => {
    if (!risk) return null;
    const sign = risk.direction === "short" ? -1 : 1;
    const denominator = sign * Math.max(1, risk.position_gbp);
    return {
      riskPrice: risk.spot_price * (1 + -risk.risk_gbp / denominator),
      likelyPrice: risk.spot_price * (1 + risk.likely_gbp / denominator),
      upsidePrice: risk.spot_price * (1 + risk.upside_gbp / denominator),
    };
  }, [risk]);

  const handleAssessmentChange = useCallback(
    (next: { data: RiskAssessment | null; loading: boolean; inputs: TradeInputState }) => {
      setRisk(next.data);
      setRiskLoading(next.loading);
    },
    [],
  );

  return (
    <main className="space-y-8 pb-16">
      {/* 1. Identity strip */}
      <IdentityStrip
        market={market}
        markets={markets}
        spot={lastObserved?.price_value}
        nextH={latestForecast?.point_estimate}
        front={front ?? undefined}
        onChangeMarket={(code) => router.push(`/markets/${code}` as Route)}
      />

      {/* 2. Hero — the three numbers */}
      <MarketHero
        marketId={market.id}
        marketCode={market.code}
        marketName={market.name}
        dataStatus={market.data_status}
        cursorTimestampMs={cursorTs}
        onAssessmentChange={handleAssessmentChange}
      />

      {/* 3. Decision gate */}
      {risk ? (
        <SectionFrame title="Decision gate" subtitle="Should you put this trade on?">
          <DecisionGateStrip data={risk} loading={riskLoading} />
        </SectionFrame>
      ) : null}

      {/* 4. Chart */}
      <SectionFrame
        title="Price · forecast"
        subtitle="Live spot, modelled distribution, and the events shaping it."
      >
        <ClientErrorBoundary
          fallbackTitle="Chart engine recovering"
          fallbackBody="The chart hit a client-side issue. Refresh once. The rest of the page stays live."
        >
          <div className="h-[500px] overflow-hidden rounded-2xl border border-seam bg-surface">
            {chartSource ? (
              <KlinePriceChart
                marketId={market.id}
                history={history}
                forecast={forecast}
                livePriceTick={livePriceTick}
                events={dashboard?.recent_events ?? []}
                timezoneLabel={market.timezone}
                onCrosshair={(p) => setCursorTs(p?.timestampMs ?? null)}
                riskOverlay={riskOverlay}
              />
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-ink/40">
                Loading chart…
              </div>
            )}
          </div>
        </ClientErrorBoundary>
      </SectionFrame>

      {/* 5. Scenarios */}
      <SectionFrame title="Scenarios" subtitle="How the three numbers shift under named stress events.">
        <ScenarioCards data={risk} loading={riskLoading} />
      </SectionFrame>

      {/* 6. Path fan */}
      <SectionFrame
        title="Path fan"
        subtitle="A sample of the simulated price paths behind the three numbers."
        collapsibleOnMobile
        defaultOpen={false}
      >
        <div className="rounded-2xl border border-seam bg-surface p-4">
          <RiskPathFan data={risk} loading={riskLoading} />
        </div>
      </SectionFrame>

      {/* 7. Audit layer */}
      <SectionFrame
        title="Audit"
        subtitle="Every coefficient feeding the read, and how each one moves the result."
        collapsibleOnMobile
        defaultOpen={false}
      >
        <div className="grid gap-4 xl:grid-cols-2">
          <RiskDecompositionPanel data={risk} loading={riskLoading} />
          <RiskSensitivityLadder data={risk} loading={riskLoading} />
        </div>
      </SectionFrame>

      {/* 8. Power BI */}
      <SectionFrame
        title="Power BI analytics"
        subtitle="Embedded report scoped to this market."
        collapsibleOnMobile
        defaultOpen={false}
      >
        <PowerBIReport marketCode={market.code} compact />
      </SectionFrame>

      {/* 9. News + events */}
      <SectionFrame
        title="Market context"
        subtitle="The news and structured events feeding the model."
        collapsibleOnMobile
        defaultOpen={false}
      >
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-2xl border border-seam bg-surface p-4">
            <NewsBriefs items={dashboard?.recent_news.slice(0, 10) ?? []} />
          </div>
          <div className="rounded-2xl border border-seam bg-surface p-4">
            <EventFeed
              events={dashboard?.recent_events.slice(0, 10) ?? []}
              compact
              title="Recent structured events"
              subtitle="Events"
            />
          </div>
        </div>
      </SectionFrame>

      {/* 10. Decisions + positions */}
      <SectionFrame
        title="Your book"
        subtitle="Open positions and the diary of past reads on this market."
        collapsibleOnMobile
        defaultOpen={false}
      >
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-2xl border border-seam bg-surface p-4">
            <PositionBlotter refreshKey={decisionRefresh} />
          </div>
          <div className="rounded-2xl border border-seam bg-surface p-4">
            <DecisionDiary marketId={market.id} refreshKey={decisionRefresh} />
          </div>
        </div>
      </SectionFrame>

      {/* 11. Deep calibration + signals */}
      <SectionFrame
        title="Honesty &amp; signals"
        subtitle="Long-run calibration and the model's current signal stack."
        collapsibleOnMobile
        defaultOpen={false}
      >
        <div className="grid gap-4 lg:grid-cols-[1fr_1.6fr]">
          <CalibrationPanel marketId={market.id} />
          {dashboard ? <SignalStack dashboard={dashboard} /> : <div className="h-40 animate-pulse rounded-2xl border border-seam bg-bg" />}
        </div>
      </SectionFrame>
    </main>
  );
}

function IdentityStrip({
  market,
  markets,
  spot,
  nextH,
  front,
  onChangeMarket,
}: {
  market: Market;
  markets: Market[];
  spot?: number;
  nextH?: number;
  front?: number;
  onChangeMarket: (code: string) => void;
}) {
  return (
    <section className="rounded-2xl border border-seam bg-surface p-4 sm:p-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="mb-1.5 flex items-center gap-2">
            <span className="rounded-md bg-ink/5 px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest text-ink/55">
              {market.code}
            </span>
            <span className="text-[11px] text-ink/45">{market.region}</span>
            <span className="text-[11px] text-ink/30">·</span>
            <span className="text-[11px] text-ink/45">{market.timezone}</span>
          </div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink sm:text-3xl">{market.name}</h1>
        </div>
        <div className="flex items-center gap-3">
          {spot !== undefined ? (
            <MiniStat label="Spot" value={`$${spot.toFixed(2)}`} />
          ) : null}
          {nextH !== undefined ? (
            <MiniStat label="Next h" value={`$${nextH.toFixed(2)}`} accent />
          ) : null}
          {front !== undefined ? (
            <MiniStat
              label="Front"
              value={`${front >= 0 ? "+" : ""}${front.toFixed(2)}`}
              tone={front >= 0 ? "up" : "dn"}
            />
          ) : null}
          <select
            value={market.code}
            onChange={(event) => onChangeMarket(event.target.value)}
            className="rounded-lg border border-seam bg-bg px-3 py-2 text-sm text-ink outline-none focus:border-seam-hi"
          >
            {markets.map((m) => (
              <option key={m.code} value={m.code}>
                {m.name} · {m.region}
              </option>
            ))}
          </select>
        </div>
      </div>
    </section>
  );
}

function MiniStat({
  label,
  value,
  tone,
  accent,
}: {
  label: string;
  value: string;
  tone?: "up" | "dn";
  accent?: boolean;
}) {
  const toneClass = accent
    ? "text-price-up"
    : tone === "up"
      ? "text-price-up"
      : tone === "dn"
        ? "text-price-dn"
        : "text-ink";
  return (
    <div className="hidden rounded-lg border border-seam bg-bg px-3 py-1.5 text-right sm:block">
      <p className="font-mono text-[9px] uppercase tracking-widest text-ink/40">{label}</p>
      <p className={`mt-0.5 font-mono text-sm font-semibold tabular-nums ${toneClass}`}>{value}</p>
    </div>
  );
}

/**
 * Section wrapper with a sticky-ish header. On mobile, sections beyond
 * the first two collapse by default and are tap-to-expand so the user
 * isn't dumped into a 10-screen scroll. The hero is always visible —
 * collapse only applies to the evidence zone.
 */
function SectionFrame({
  title,
  subtitle,
  children,
  collapsibleOnMobile = false,
  defaultOpen = true,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  collapsibleOnMobile?: boolean;
  defaultOpen?: boolean;
}) {
  const [mobileOpen, setMobileOpen] = useState<boolean>(defaultOpen);
  const [isMobile, setIsMobile] = useState<boolean>(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const mq = window.matchMedia("(max-width: 767px)");
    const update = () => setIsMobile(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  const collapsed = collapsibleOnMobile && isMobile && !mobileOpen;

  return (
    <section className="space-y-3">
      <header
        className={`flex items-baseline justify-between gap-3 border-b border-seam/60 pb-2 ${
          collapsibleOnMobile ? "cursor-pointer md:cursor-default" : ""
        }`}
        onClick={() => {
          if (collapsibleOnMobile && isMobile) setMobileOpen((v) => !v);
        }}
      >
        <h2 className="text-sm font-semibold uppercase tracking-[0.18em] text-ink/70">{title}</h2>
        {subtitle ? <p className="hidden text-[11px] text-ink/45 sm:block">{subtitle}</p> : null}
        {collapsibleOnMobile ? (
          <span className="font-mono text-xs text-ink/45 md:hidden">{collapsed ? "+" : "−"}</span>
        ) : null}
      </header>
      {collapsed ? null : children}
    </section>
  );
}
