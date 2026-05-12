"use client";

import dynamic from "next/dynamic";
import type { Route } from "next";
import { useRouter } from "next/navigation";
import { useCallback, useMemo, useState } from "react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";

import { CalibrationPanel } from "@/components/calibration-panel";
import { ClientErrorBoundary } from "@/components/client-error-boundary";
import { DecisionDiary } from "@/components/decision-diary";
import { EventFeed } from "@/components/event-feed";
import { NewsBriefs } from "@/components/news-briefs";
import { PositionBlotter } from "@/components/position-blotter";
import { RiskDecompositionPanel } from "@/components/risk-decomposition-panel";
import { RiskPanel } from "@/components/risk-panel";
import { RiskPathFan } from "@/components/risk-path-fan";
import { RiskSensitivityLadder } from "@/components/risk-sensitivity-ladder";
import { SignalStack } from "@/components/signal-stack";
import { useMarketStream } from "@/lib/use-market-stream";
import { DashboardData, Market, RiskAssessment } from "@/types/domain";

// Chart is canvas-based — render only on client
const KlinePriceChart = dynamic(() => import("@/components/kline-price-chart").then((m) => m.KlinePriceChart), {
  ssr: false,
  loading: () => (
    <div className="flex h-[620px] items-center justify-center rounded-2xl border border-seam bg-surface text-sm text-ink/40">
      Loading chart…
    </div>
  ),
});

function buildHistory(dashboard: DashboardData) {
  return dashboard.recent_prices.map((p) => ({ timestamp: p.timestamp, value: p.price_value }));
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
  const [decisionRefresh, setDecisionRefresh] = useState(0);
  const history = useMemo(() => buildHistory(dashboard), [dashboard]);
  const forecast = useMemo(() => buildForecast(dashboard), [dashboard]);
  const stream = useMarketStream(dashboard.market.code);
  const livePriceTick = stream.priceTick
    ? { timestamp: stream.priceTick.timestamp, value: stream.priceTick.price_value }
    : null;

  const lastObserved = dashboard.recent_prices[dashboard.recent_prices.length - 1];
  const latestForecast = dashboard.forecasts[0] ?? dashboard.latest_forecast;
  const front = lastObserved && latestForecast ? latestForecast.point_estimate - lastObserved.price_value : null;
  const directionalAccuracy = Math.round((dashboard.key_metrics.directional_accuracy ?? 0) * 100);
  const spikePrecision = Math.round((dashboard.key_metrics.spike_precision ?? 0) * 100);
  const handleRiskResult = useCallback((result: RiskAssessment | null, loading: boolean) => {
    setRisk(result);
    setRiskLoading(loading);
  }, []);
  const handleDecisionSaved = useCallback(() => {
    setDecisionRefresh((value) => value + 1);
  }, []);

  return (
    <main className="space-y-5">
      {/* Header */}
      <section className="rounded-2xl border border-seam bg-surface p-5">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="mb-2 flex items-center gap-2">
              <span className="rounded-md bg-ink/5 px-2 py-0.5 text-[10px] font-mono uppercase tracking-widest text-ink/55">
                {dashboard.market.code}
              </span>
              <span className="text-[11px] text-ink/45">{dashboard.market.region}</span>
              <span className="text-[11px] text-ink/35">·</span>
              <span className="text-[11px] text-ink/45">{dashboard.market.timezone}</span>
            </div>
            <h1 className="text-3xl font-semibold tracking-tight text-ink">{dashboard.market.name}</h1>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={dashboard.market.code}
              onChange={(event) => router.push(`/markets/${event.target.value}` as Route)}
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

        {/* KPI strip */}
        <div className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-5">
          <KpiTile label="Spot" value={lastObserved ? `$${lastObserved.price_value.toFixed(2)}` : "—"} />
          <KpiTile label="Next H" value={latestForecast ? `$${latestForecast.point_estimate.toFixed(2)}` : "—"} accent />
          <KpiTile
            label="Front gap"
            value={typeof front === "number" ? `${front >= 0 ? "+" : ""}${front.toFixed(2)}` : "—"}
            tone={typeof front === "number" && front >= 0 ? "up" : "dn"}
          />
          <KpiTile label="Spike risk" value={`${Math.round((latestForecast?.spike_probability ?? 0) * 100)}%`} />
          <KpiTile label="Model dir-acc" value={`${directionalAccuracy}%`} sub={`spike ${spikePrecision}%`} />
        </div>
      </section>

      <section className="h-[calc(100vh-220px)] min-h-[980px]">
        <PanelGroup autoSaveId="frontier-workbench-rows-v2" direction="vertical" className="h-full">
          {/* TOP ROW — assessment-focused: chart (with path-fan below) + 3 right-column panels */}
          <Panel defaultSize={64} minSize={44}>
            <PanelGroup autoSaveId="frontier-workbench-top-v2" direction="horizontal" className="h-full">
              <Panel defaultSize={58} minSize={36}>
                <div className="flex h-full flex-col gap-2 pr-2">
                  <ClientErrorBoundary
                    fallbackTitle="Chart engine recovering"
                    fallbackBody="The chart hit a client-side issue. Refresh once. The rest of the desk stays live."
                  >
                    <div className="flex-1 min-h-0 overflow-hidden">
                      <KlinePriceChart
                        marketId={dashboard.market.id}
                        history={history}
                        forecast={forecast}
                        livePriceTick={livePriceTick}
                        events={dashboard.recent_events}
                        timezoneLabel={dashboard.market.timezone}
                        onCrosshair={(p) => setCursorTs(p?.timestampMs ?? null)}
                      />
                    </div>
                  </ClientErrorBoundary>
                  <div className="shrink-0">
                    <RiskPathFan data={risk} loading={riskLoading} />
                  </div>
                </div>
              </Panel>
              <ResizeHandle direction="horizontal" />
              <Panel defaultSize={42} minSize={30}>
                <div className="grid h-full grid-rows-[auto_minmax(0,1fr)_minmax(0,1fr)] gap-3 overflow-hidden pl-2">
                  <RiskPanel
                    marketId={dashboard.market.id}
                    marketCode={dashboard.market.code}
                    cursorTimestampMs={cursorTs}
                    dataStatus={dashboard.market.data_status}
                    onResult={handleRiskResult}
                    onDecisionSaved={handleDecisionSaved}
                  />
                  <div className="min-h-0 scroll-pane">
                    <RiskDecompositionPanel data={risk} loading={riskLoading} />
                  </div>
                  <div className="min-h-0 scroll-pane">
                    <RiskSensitivityLadder data={risk} loading={riskLoading} />
                  </div>
                </div>
              </Panel>
            </PanelGroup>
          </Panel>
          <ResizeHandle direction="vertical" />
          {/* BOTTOM ROW — market context + portfolio state. 5 columns. */}
          <Panel defaultSize={36} minSize={24}>
            <PanelGroup autoSaveId="frontier-workbench-bottom-v2" direction="horizontal" className="h-full">
              <Panel defaultSize={22} minSize={14}>
                <div className="h-full scroll-pane pr-2">
                  <SignalStack dashboard={dashboard} />
                </div>
              </Panel>
              <ResizeHandle direction="horizontal" />
              <Panel defaultSize={20} minSize={14}>
                <div className="h-full scroll-pane px-2">
                  <NewsBriefs items={dashboard.recent_news.slice(0, 8)} />
                </div>
              </Panel>
              <ResizeHandle direction="horizontal" />
              <Panel defaultSize={20} minSize={14}>
                <div className="h-full scroll-pane px-2">
                  <EventFeed
                    events={dashboard.recent_events.slice(0, 8)}
                    compact
                    title="Recent structured events"
                    subtitle="Events"
                  />
                </div>
              </Panel>
              <ResizeHandle direction="horizontal" />
              <Panel defaultSize={16} minSize={12}>
                <div className="h-full scroll-pane px-2">
                  <CalibrationPanel marketId={dashboard.market.id} />
                </div>
              </Panel>
              <ResizeHandle direction="horizontal" />
              <Panel defaultSize={22} minSize={16}>
                <div className="flex h-full flex-col gap-3 overflow-hidden pl-2">
                  <div className="min-h-0 flex-1 scroll-pane">
                    <PositionBlotter refreshKey={decisionRefresh} />
                  </div>
                  <div className="min-h-0 flex-1 scroll-pane">
                    <DecisionDiary marketId={dashboard.market.id} refreshKey={decisionRefresh} />
                  </div>
                </div>
              </Panel>
            </PanelGroup>
          </Panel>
        </PanelGroup>
      </section>
    </main>
  );
}

function ResizeHandle({ direction }: { direction: "horizontal" | "vertical" }) {
  const className =
    direction === "horizontal"
      ? "mx-2 w-1 rounded-full bg-seam transition hover:bg-seam-hi data-[resize-handle-active]:bg-seam-hi"
      : "my-2 h-1 rounded-full bg-seam transition hover:bg-seam-hi data-[resize-handle-active]:bg-seam-hi";
  return <PanelResizeHandle className={className} />;
}

function KpiTile({
  label,
  value,
  sub,
  tone,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "up" | "dn";
  accent?: boolean;
}) {
  const valueClass = accent
    ? "text-price-up"
    : tone === "up"
      ? "text-price-up"
      : tone === "dn"
        ? "text-price-dn"
        : "text-ink";
  return (
    <div className="rounded-xl border border-seam bg-bg p-3">
      <p className="text-[10px] uppercase tracking-widest text-ink/40">{label}</p>
      <p className={`mt-1.5 font-mono text-xl font-semibold tabular-nums ${valueClass}`}>{value}</p>
      {sub ? <p className="mt-0.5 text-[10px] text-ink/40">{sub}</p> : null}
    </div>
  );
}
