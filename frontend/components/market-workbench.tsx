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

import { CalibrationPanel } from "@/components/calibration-panel";
import { ClientErrorBoundary } from "@/components/client-error-boundary";
import { DecisionDiary } from "@/components/decision-diary";
import { DecisionGateStrip } from "@/components/decision-gate-strip";
import { EventFeed } from "@/components/event-feed";
import { MarketHero } from "@/components/market-hero";
import { NewsBriefs } from "@/components/news-briefs";
import { PositionBlotter } from "@/components/position-blotter";
import { PowerBIReport } from "@/components/power-bi-report";
import { RiskDecompositionPanel } from "@/components/risk-decomposition-panel";
import { RiskPathFan } from "@/components/risk-path-fan";
import { RiskSensitivityLadder } from "@/components/risk-sensitivity-ladder";
import { ScenarioCards } from "@/components/scenario-cards";
import { SignalStack } from "@/components/signal-stack";
import type { TradeInputState } from "@/components/trade-input-bar";
import { useMarketStream } from "@/lib/use-market-stream";
import { DashboardData, Market, RiskAssessment } from "@/types/domain";

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

function buildHistory(dashboard: DashboardData) {
  return dashboard.recent_prices.map((p) => ({
    timestamp: p.timestamp,
    value: p.price_value,
  }));
}

function buildForecast(dashboard: DashboardData) {
  return dashboard.forecasts.map((f) => ({
    timestamp: f.forecast_for_timestamp,
    point: f.point_estimate,
    lower: f.lower_bound,
    upper: f.upper_bound,
  }));
}

export function MarketWorkbench({
  markets,
  dashboard,
}: {
  markets: Market[];
  dashboard: DashboardData;
}) {
  const router = useRouter();
  const [cursorTs, setCursorTs] = useState<number | null>(null);
  const [risk, setRisk] = useState<RiskAssessment | null>(null);
  const [riskLoading, setRiskLoading] = useState(false);
  const [decisionRefresh] = useState(0);

  const history = useMemo(() => buildHistory(dashboard), [dashboard]);
  const forecast = useMemo(() => buildForecast(dashboard), [dashboard]);
  const stream = useMarketStream(dashboard.market.code);
  const livePriceTick = stream.priceTick
    ? { timestamp: stream.priceTick.timestamp, value: stream.priceTick.price_value }
    : null;

  const lastObserved = dashboard.recent_prices[dashboard.recent_prices.length - 1];
  const latestForecast = dashboard.forecasts[0] ?? dashboard.latest_forecast;
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
        market={dashboard.market}
        markets={markets}
        spot={lastObserved?.price_value}
        nextH={latestForecast?.point_estimate}
        front={front ?? undefined}
        onChangeMarket={(code) => router.push(`/markets/${code}` as Route)}
      />

      {/* 2. Hero — the three numbers */}
      <MarketHero
        marketId={dashboard.market.id}
        marketCode={dashboard.market.code}
        marketName={dashboard.market.name}
        dataStatus={dashboard.market.data_status}
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
            <KlinePriceChart
              marketId={dashboard.market.id}
              history={history}
              forecast={forecast}
              livePriceTick={livePriceTick}
              events={dashboard.recent_events}
              timezoneLabel={dashboard.market.timezone}
              onCrosshair={(p) => setCursorTs(p?.timestampMs ?? null)}
              riskOverlay={riskOverlay}
            />
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
        <PowerBIReport marketCode={dashboard.market.code} compact />
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
            <NewsBriefs items={dashboard.recent_news.slice(0, 10)} />
          </div>
          <div className="rounded-2xl border border-seam bg-surface p-4">
            <EventFeed
              events={dashboard.recent_events.slice(0, 10)}
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
            <DecisionDiary marketId={dashboard.market.id} refreshKey={decisionRefresh} />
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
          <CalibrationPanel marketId={dashboard.market.id} />
          <SignalStack dashboard={dashboard} />
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
